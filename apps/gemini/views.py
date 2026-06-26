import logging
import re
import time
from datetime import date, datetime

from django.conf import settings
from django.db import transaction
from django.http import JsonResponse
from django.utils import timezone
from google.api_core import exceptions
from google.genai import errors as genai_errors
from google.genai import types
from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import IsAuthenticated

from apps.core.cache import invalidate_statistics_cache
from apps.scans.models import GeminiScan, Scan

logger = logging.getLogger(__name__)


def evaluate_vehicle_alert(vehicle, actor):
    if vehicle is None:
        return
    try:
        from apps.alerts.services import evaluate_judicial_alert

        evaluate_judicial_alert(vehicle=vehicle, actor=actor)
    except Exception:
        logger.exception("Impossible d'evaluer l'alerte judiciaire du vehicule.")


def is_temporary_gemini_unavailable(error: Exception) -> bool:
    status_code = getattr(error, "status_code", None)
    if status_code == 503:
        return True

    message = str(error).upper()
    return "503" in message or "UNAVAILABLE" in message


def normalize_plate_candidate(text: str) -> str:
    if not text:
        return ""
    return re.sub(r"[^A-Z0-9]", "", text.upper())


def is_usable_plate(plate: str) -> bool:
    if len(plate) < 4 or len(plate) > 12:
        return False
    has_letter = any(char.isalpha() for char in plate)
    has_digit = any(char.isdigit() for char in plate)
    return has_letter and has_digit


def mask_plate_for_log(plate: str) -> str:
    if not plate:
        return ""
    text = str(plate)
    return f"{text[:2]}***{text[-2:]}" if len(text) > 4 else "<masked>"


def format_plate_display(plate: str) -> str:
    normalized = normalize_plate_candidate(plate)
    if len(normalized) <= 5:
        return normalized
    return f"{normalized[:-5]}-{normalized[-5:]}"


def get_vehicle_by_plate(plate_number_display: str):
    if not plate_number_display:
        return None
    from apps.vehicles.models import Vehicle

    normalized = normalize_plate_candidate(plate_number_display)
    plate_variants = {plate_number_display, normalized}
    if "-" in plate_number_display:
        plate_variants.add(plate_number_display.replace("-", ""))
    return Vehicle.objects.select_related("owner").filter(plate_number__in=list(plate_variants)).first()


def serialize_owner(owner):
    if owner is None:
        return None
    return {
        "nif": getattr(owner, "national_id", None),
        "nom": getattr(owner, "full_name", None),
        "prenom": None,
        "adresse": getattr(owner, "address", None),
        "phone": getattr(owner, "phone", None),
        "email": None,
    }


def serialize_vehicle(vehicle):
    if vehicle is None:
        return None
    owner = getattr(vehicle, "owner", None)
    return {
        "plate_number": vehicle.plate_number,
        "brand": vehicle.brand,
        "model": vehicle.model,
        "color": vehicle.color,
        "year": vehicle.year,
        "owner": serialize_owner(owner),
    }


def format_date(value):
    if isinstance(value, date):
        return value.strftime("%Y-%m-%d")
    return value


def format_datetime(value):
    if isinstance(value, datetime):
        local_dt = timezone.localtime(value, timezone.get_current_timezone())
        return local_dt.strftime("%Y-%m-%d %H:%M:%S")
    return value


def build_documents_style_payload(vehicle):
    if vehicle is None:
        return {
            "vehicule": None,
            "proprietaire": None,
            "assurance": None,
            "immatriculation": None,
        }

    owner = getattr(vehicle, "owner", None)
    from apps.insurance.models import InsurancePolicy

    latest_insurance = InsurancePolicy.objects.filter(vehicle=vehicle).order_by("-valid_until").first()

    return {
        "vehicule": {
            "plaque": vehicle.plate_number,
            "marque": vehicle.brand,
            "modele": vehicle.model,
            "couleur": vehicle.color,
            "annee": vehicle.year,
        },
        "proprietaire": {
            "nif": getattr(owner, "national_id", None),
            "nom": getattr(owner, "full_name", None),
            "prenom": None,
            "adresse": getattr(owner, "address", None),
            "telephone": getattr(owner, "phone", None),
            "email": None,
        }
        if owner
        else None,
        "assurance": {
            "numero_police": latest_insurance.policy_number,
            "compagnie": latest_insurance.insurer,
            "date_emission": None,
            "date_expiration": format_date(latest_insurance.valid_until),
            "est_active": latest_insurance.status == InsurancePolicy.STATUS_VALID,
        }
        if latest_insurance
        else None,
        "immatriculation": {
            "numero_immatriculation": vehicle.plate_number,
            "type": None,
            "date_emission": None,
            "date_expiration": None,
        },
    }


def build_vehicle_tickets_payload(vehicle):
    from apps.tickets.models import Ticket

    tickets_qs = (
        Ticket.objects.select_related("vehicle", "vehicle__owner", "agent")
        .filter(vehicle=vehicle)
        .order_by("-created_at")
    )
    tickets_data = []
    for ticket in tickets_qs:
        tickets_data.append(
            {
                "id": ticket.id,
                "status": ticket.status,
                "driver_license": ticket.driver_license,
                "plate_number_snapshot": ticket.plate_number_snapshot,
                "note": ticket.note,
                "created_at": ticket.created_at.isoformat(),
            }
        )
    return {
        "summary": {
            "total": len(tickets_data),
            "en_cours": sum(1 for item in tickets_data if item.get("status") == "PENDING_SYNC"),
            "regle": sum(1 for item in tickets_data if item.get("status") == "VALIDATED"),
        },
        "items": tickets_data,
    }


def generate_with_fallbacks(contents):
    if not getattr(settings, "GEMINI_API_KEY", "").strip():
        raise ValueError("GEMINI_API_KEY n'est pas configuree sur le backend.")

    from google import genai

    client = genai.Client(api_key=settings.GEMINI_API_KEY)
    primary_model = getattr(settings, "GEMINI_MODEL", "gemini-2.5-flash")
    fallback_models = getattr(settings, "GEMINI_FALLBACK_MODELS", [])
    models = [primary_model, *fallback_models]
    last_error = None

    for model in models:
        try:
            response = client.models.generate_content(
                model=model,
                contents=contents,
            )
            raw_text = (getattr(response, "text", "") or "").strip()
            plate_candidate = normalize_plate_candidate(raw_text)
            if settings.GEMINI_LOG_RESPONSE:
                logger.info("Gemini response for model %s: %s", model, raw_text)
            if settings.GEMINI_LOG_RAW_RESPONSE:
                logger.debug("Gemini raw response object: %s", response)
            if is_usable_plate(plate_candidate):
                return response, model, plate_candidate, raw_text
            logger.warning("Gemini model %s returned no usable plate: %s", model, raw_text)
            last_error = ValueError(f"Aucune plaque exploitable retournee par {model}: {raw_text or 'reponse vide'}")
            continue
        except exceptions.ServiceUnavailable as e:
            logger.warning("Gemini model %s unavailable: %s", model, e)
            last_error = e
            time.sleep(0.4)
            continue
        except genai_errors.ServerError as e:
            logger.warning("Gemini model %s server error: %s", model, e)
            last_error = e
            if is_temporary_gemini_unavailable(e):
                time.sleep(0.4)
            continue
        except Exception as e:
            logger.exception("Gemini model %s failed during plate scan.", model)
            last_error = e
            continue

    if last_error is not None:
        raise last_error
    raise ValueError("Aucune reponse recue depuis les modeles Gemini.")


@api_view(["POST"])
@permission_classes([IsAuthenticated])
def extract_license_plate(request):
    image_file = request.FILES.get("image")
    if image_file is None:
        return JsonResponse({"status": "error", "message": "Une image est requise."}, status=400)

    try:
        logger.info(
            "event=gemini_scan_started request_id=%s user_id=%s filename=%s content_type=%s",
            getattr(request, "request_id", "-"),
            request.user.pk,
            getattr(image_file, "name", ""),
            getattr(image_file, "content_type", ""),
        )
        image_bytes = image_file.read()
        if not image_bytes:
            return JsonResponse({"status": "error", "message": "Le fichier image est vide."}, status=400)

        prompt = (
            "Identifie la plaque d'immatriculation sur cette image. "
            "Renvoie uniquement le numero de la plaque, sans texte additionnel, "
            "sans ponctuation inutile, en majuscules."
        )

        contents = [
            types.Part.from_bytes(
                data=image_bytes,
                mime_type=image_file.content_type or "image/jpeg",
            ),
            prompt,
        ]
        _response, model_used, plate_number, raw_text = generate_with_fallbacks(contents)
        plate_number_display = format_plate_display(plate_number) if plate_number else ""
        vehicle = get_vehicle_by_plate(plate_number_display) if plate_number_display else None
        logger.info(
            "event=gemini_plate_detected request_id=%s user_id=%s plate=%s model=%s vehicle_id=%s",
            getattr(request, "request_id", "-"),
            request.user.pk,
            mask_plate_for_log(plate_number_display),
            model_used,
            getattr(vehicle, "pk", None),
        )
        evaluate_vehicle_alert(vehicle, request.user)

        scan_entry = None
        try:
            with transaction.atomic():
                scan_entry = GeminiScan.objects.create(
                    plate_number=plate_number_display,
                    model_used=model_used,
                    raw_response=raw_text,
                    plate_detected=bool(plate_number_display and is_usable_plate(plate_number_display)),
                    vehicle=vehicle,
                    agent=request.user,
                )
                transaction.on_commit(invalidate_statistics_cache)
            logger.info(
                "event=gemini_scan_saved request_id=%s scan_id=%s user_id=%s plate=%s vehicle_id=%s",
                getattr(request, "request_id", "-"),
                scan_entry.pk,
                request.user.pk,
                mask_plate_for_log(plate_number_display),
                getattr(vehicle, "pk", None),
            )
        except Exception:
            logger.exception("Impossible d'enregistrer le scan Gemini en base.")

        return JsonResponse(
            {
                "status": "success",
                "raw_response": raw_text,
                "plate_number": plate_number_display,
                "plate_detected": bool(plate_number_display and is_usable_plate(plate_number_display)),
                "model_used": model_used,
                "vehicle": serialize_vehicle(vehicle),
                "documents": build_documents_style_payload(vehicle),
                "scanned_at": format_datetime(getattr(scan_entry, "scanned_at", timezone.now())),
            }
        )

    except ValueError as e:
        return JsonResponse({"status": "error", "message": str(e)}, status=422)
    except exceptions.InvalidArgument:
        return JsonResponse({"status": "error", "message": "Image invalide ou format non supporte."}, status=400)
    except exceptions.Unauthenticated:
        return JsonResponse({"status": "error", "message": "Configuration Gemini invalide (authentification)."}, status=502)
    except exceptions.PermissionDenied:
        return JsonResponse({"status": "error", "message": "Acces Gemini refuse. Verifiez la configuration du projet Google."}, status=502)
    except exceptions.ResourceExhausted:
        return JsonResponse({"status": "error", "message": "Quota Gemini depasse. Reessayez plus tard."}, status=429)
    except exceptions.ServiceUnavailable:
        return JsonResponse({"status": "error", "message": "Le service est temporairement surcharge. Reessayez dans quelques instants."}, status=503)
    except genai_errors.ServerError as e:
        if is_temporary_gemini_unavailable(e):
            return JsonResponse(
                {"status": "error", "message": "Le service Gemini est temporairement surcharge. Reessayez dans quelques instants."},
                status=503,
            )
        logger.exception("Erreur Gemini (ServerError) pendant le scan de plaque.")
        return JsonResponse({"status": "error", "message": "Erreur de service Gemini pendant l'analyse de l'image."}, status=502)
    except Exception:
        logger.exception("Erreur inattendue pendant le scan de plaque Gemini.")
        return JsonResponse({"status": "error", "message": "Erreur interne pendant l'analyse de l'image."}, status=500)


@api_view(["GET"])
@permission_classes([IsAuthenticated])
def get_last_scan(request):
    last_scan = (
        GeminiScan.objects.select_related("vehicle", "vehicle__owner")
        .filter(agent=request.user)
        .order_by("-scanned_at")
        .first()
    )
    if not last_scan:
        return JsonResponse({"status": "error", "message": "Aucun scan disponible pour le moment."}, status=404)

    return JsonResponse(
        {
            "status": "success",
            "plate_number": last_scan.plate_number,
            "model_used": last_scan.model_used,
            "scanned_at": last_scan.scanned_at.isoformat(),
            "vehicle": serialize_vehicle(last_scan.vehicle),
        }
    )


@api_view(["GET"])
@permission_classes([IsAuthenticated])
def search_plate(request):
    plate_raw = (request.query_params.get("plate_number") or "").strip()
    if not plate_raw:
        return JsonResponse({"status": "error", "message": "Le parametre plate_number est requis."}, status=400)

    plate_number_display = format_plate_display(plate_raw)
    if not is_usable_plate(plate_number_display):
        return JsonResponse(
            {"status": "error", "message": "Le numero de plaque est invalide.", "plate_number": plate_number_display},
            status=422,
        )

    vehicle = get_vehicle_by_plate(plate_number_display)
    evaluate_vehicle_alert(vehicle, request.user)

    try:
        scan = Scan.objects.create(agent=request.user, plate_number=plate_number_display, source="MANUAL")
        transaction.on_commit(invalidate_statistics_cache)
        logger.info(
            "event=manual_plate_search_saved request_id=%s scan_id=%s user_id=%s plate=%s vehicle_id=%s",
            getattr(request, "request_id", "-"),
            scan.pk,
            request.user.pk,
            mask_plate_for_log(plate_number_display),
            getattr(vehicle, "pk", None),
        )
    except Exception:
        logger.exception("Impossible d'enregistrer la recherche manuelle en base.")

    return JsonResponse(
        {
            "status": "success",
            "plate_number": plate_number_display,
            "plate_detected": True,
            "vehicle": serialize_vehicle(vehicle),
            "documents": build_documents_style_payload(vehicle),
            "scanned_at": format_datetime(timezone.now()),
            "tickets": build_vehicle_tickets_payload(vehicle) if vehicle else {"summary": {"total": 0, "en_cours": 0, "regle": 0}, "items": []},
        }
    )
