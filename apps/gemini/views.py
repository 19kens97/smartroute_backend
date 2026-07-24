import logging
import re
import time
from datetime import date, datetime

from django.conf import settings
from django.http import JsonResponse
from django.utils import timezone
from google import genai
from google.api_core import exceptions
from google.genai import errors as genai_errors
from google.genai import types
from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import IsAuthenticated
from rest_framework import serializers

from apps.insurance.models import InsurancePolicy
from apps.media_storage.services import MEDIA_TYPE_IMAGE, get_image_limits, validate_uploaded_media
from apps.scans.models import GeminiScan, Scan
from apps.tickets.models import Ticket
from apps.tickets.serializers import TicketSerializer
from apps.vehicles.models import Vehicle

logger = logging.getLogger(__name__)

PROMPT = (
    "Identifie la plaque d'immatriculation sur cette image. "
    "Renvoie uniquement le numero de la plaque, sans texte additionnel, "
    "sans ponctuation inutile, en majuscules."
)


class GeminiConfigurationError(Exception):
    pass


def get_gemini_client():
    api_key = getattr(settings, "GEMINI_API_KEY", "")
    if not api_key:
        raise GeminiConfigurationError("GEMINI_API_KEY is not configured.")
    return genai.Client(api_key=api_key)


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


def format_plate_display(plate: str) -> str:
    normalized = normalize_plate_candidate(plate)
    if len(normalized) <= 5:
        return normalized
    return f"{normalized[:-5]}-{normalized[-5:]}"


def get_vehicle_by_plate(plate_number_display: str):
    if not plate_number_display:
        return None
    compact = normalize_plate_candidate(plate_number_display)
    candidates = {plate_number_display, compact, format_plate_display(compact)}
    return Vehicle.objects.select_related("owner", "owner__person").filter(plate_number__in=candidates).first()


def serialize_owner(owner):
    if owner is None:
        return None
    person = getattr(owner, "person", None)
    full_name = getattr(owner, "full_name", "") or ""
    return {
        "nif": getattr(person, "nif", "") or getattr(owner, "nif", "") or "",
        "nom": full_name,
        "prenom": "",
        "adresse": getattr(owner, "address", ""),
        "phone": getattr(owner, "phone", ""),
        "email": None,
    }


def serialize_vehicle(vehicle):
    if vehicle is None:
        return None
    return {
        "plate_number": vehicle.plate_number,
        "brand": vehicle.brand,
        "model": vehicle.model,
        "color": vehicle.color,
        "year": vehicle.year,
        "owner": serialize_owner(getattr(vehicle, "owner", None)),
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

    latest_insurance = InsurancePolicy.objects.filter(vehicle=vehicle).order_by("-valid_until", "-id").first()

    return {
        "vehicule": {
            "plaque": vehicle.plate_number,
            "marque": vehicle.brand,
            "modele": vehicle.model,
            "couleur": vehicle.color,
            "annee": vehicle.year,
        },
        "proprietaire": serialize_owner(getattr(vehicle, "owner", None)),
        "assurance": {
            "numero_police": latest_insurance.policy_number,
            "compagnie": latest_insurance.insurer,
            "date_emission": None,
            "date_expiration": format_date(latest_insurance.valid_until),
            "est_active": latest_insurance.status == InsurancePolicy.Status.VALID,
        }
        if latest_insurance
        else None,
        "immatriculation": {
            "numero_immatriculation": vehicle.plate_number,
            "type": "vehicule",
            "date_emission": None,
            "date_expiration": format_date(vehicle.registration_valid_until),
        }
        if vehicle.registration_valid_until
        else None,
    }


def build_vehicle_tickets_payload(vehicle):
    if vehicle is None:
        return {"summary": {"total": 0, "en_cours": 0, "regle": 0}, "items": []}

    tickets_qs = (
        Ticket.objects
        .select_related("driver", "driver__person", "opened_by", "opened_by__person")
        .prefetch_related(
            "verbalizations__agent",
            "verbalizations__agent__person",
            "verbalizations__agent__agent_profile",
            "verbalizations__vehicle",
            "verbalizations__infractions__infraction",
            "verbalizations__proofs",
        )
        .filter(verbalizations__vehicle=vehicle)
        .distinct()
        .order_by("-opened_at", "-id")
    )
    tickets_data = TicketSerializer(tickets_qs, many=True).data
    return {
        "summary": {
            "total": len(tickets_data),
            "en_cours": sum(1 for item in tickets_data if item.get("status") == Ticket.Status.OPEN),
            "regle": sum(1 for item in tickets_data if item.get("status") == Ticket.Status.CLOSED),
        },
        "items": tickets_data,
    }


def generate_with_fallbacks(contents):
    primary_model = getattr(settings, "GEMINI_MODEL", "gemini-2.5-flash")
    fallback_models = getattr(settings, "GEMINI_FALLBACK_MODELS", [])
    models = [primary_model, *fallback_models]
    client = get_gemini_client()
    last_error = None
    last_result = None

    for model in models:
        try:
            response = client.models.generate_content(model=model, contents=contents)
            raw_text = (getattr(response, "text", "") or "").strip()
            plate_candidate = normalize_plate_candidate(raw_text)
            last_result = (response, model, plate_candidate, raw_text)
            if is_usable_plate(plate_candidate):
                return last_result
        except exceptions.ServiceUnavailable as exc:
            last_error = exc
            time.sleep(0.4)
        except genai_errors.ServerError as exc:
            last_error = exc
            if is_temporary_gemini_unavailable(exc):
                time.sleep(0.4)
        except Exception as exc:
            last_error = exc

    if last_result is not None:
        return last_result
    if last_error is not None:
        raise last_error
    raise ValueError("Aucune reponse recue depuis les modeles Gemini.")


def build_scan_response(scan_entry, vehicle, tickets=None):
    message = ""
    if not scan_entry.plate_detected:
        message = "Aucune plaque exploitable n'a ete detectee par Gemini."
    return {
        "status": "success",
        "message": message,
        "raw_response": scan_entry.raw_response,
        "plate_number": scan_entry.plate_number,
        "plate_detected": scan_entry.plate_detected,
        "model_used": scan_entry.model_used,
        "vehicle": serialize_vehicle(vehicle),
        "documents": build_documents_style_payload(vehicle),
        "tickets": tickets if tickets is not None else build_vehicle_tickets_payload(vehicle),
        "scanned_at": format_datetime(scan_entry.scanned_at),
    }


def mark_scan_error(scan_entry, error_code: str):
    if scan_entry is None:
        return
    scan_entry.raw_response = error_code
    scan_entry.plate_detected = False
    scan_entry.save(update_fields=["raw_response", "plate_detected", "updated_at"])


@api_view(["POST"])
@permission_classes([IsAuthenticated])
def extract_license_plate(request):
    image_file = request.FILES.get("image")
    if not image_file:
        return JsonResponse({"status": "error", "message": "Image requise."}, status=400)

    scan_entry = None
    try:
        validate_uploaded_media(image_file, media_type=MEDIA_TYPE_IMAGE, field_name="image", **get_image_limits())
        scan_entry = GeminiScan.objects.create(agent=request.user, image=image_file)
        if hasattr(image_file, "seek"):
            image_file.seek(0)
        image_bytes = image_file.read()
        if hasattr(image_file, "seek"):
            image_file.seek(0)

        contents = [
            types.Part.from_bytes(data=image_bytes, mime_type=image_file.content_type or "image/jpeg"),
            PROMPT,
        ]
        _response, model_used, plate_number, raw_text = generate_with_fallbacks(contents)
        plate_number_display = format_plate_display(plate_number) if is_usable_plate(plate_number) else ""
        vehicle = get_vehicle_by_plate(plate_number_display) if plate_number_display else None

        scan_entry.plate_number = plate_number_display
        scan_entry.model_used = model_used
        scan_entry.raw_response = raw_text
        scan_entry.plate_detected = bool(plate_number_display)
        scan_entry.vehicle = vehicle
        scan_entry.save(update_fields=["plate_number", "model_used", "raw_response", "plate_detected", "vehicle", "updated_at"])
        return JsonResponse(build_scan_response(scan_entry, vehicle))
    except serializers.ValidationError as exc:
        return JsonResponse({"status": "error", "message": "Image invalide ou format non supporte.", "errors": exc.detail}, status=400)
    except GeminiConfigurationError:
        mark_scan_error(scan_entry, "gemini_config_missing")
        logger.error("event=gemini_config_missing")
        return JsonResponse({"status": "error", "message": "Configuration Gemini manquante."}, status=502)
    except ValueError as exc:
        mark_scan_error(scan_entry, "gemini_value_error")
        return JsonResponse({"status": "error", "message": str(exc)}, status=422)
    except exceptions.InvalidArgument:
        mark_scan_error(scan_entry, "gemini_invalid_argument")
        return JsonResponse({"status": "error", "message": "Image invalide ou format non supporte."}, status=400)
    except exceptions.Unauthenticated:
        mark_scan_error(scan_entry, "gemini_unauthenticated")
        return JsonResponse({"status": "error", "message": "Configuration Gemini invalide (authentification)."}, status=502)
    except exceptions.PermissionDenied:
        mark_scan_error(scan_entry, "gemini_permission_denied")
        return JsonResponse({"status": "error", "message": "Acces Gemini refuse. Verifiez la configuration du projet Google."}, status=502)
    except exceptions.ResourceExhausted:
        mark_scan_error(scan_entry, "gemini_quota_exhausted")
        return JsonResponse({"status": "error", "message": "Quota Gemini depasse. Reessayez plus tard."}, status=429)
    except exceptions.ServiceUnavailable:
        mark_scan_error(scan_entry, "gemini_service_unavailable")
        return JsonResponse({"status": "error", "message": "Le service Gemini est temporairement surcharge. Reessayez dans quelques instants."}, status=503)
    except genai_errors.ServerError as exc:
        if is_temporary_gemini_unavailable(exc):
            mark_scan_error(scan_entry, "gemini_service_unavailable")
            return JsonResponse({"status": "error", "message": "Le service Gemini est temporairement surcharge. Reessayez dans quelques instants."}, status=503)
        mark_scan_error(scan_entry, "gemini_server_error")
        logger.exception("Erreur Gemini (ServerError) pendant le scan de plaque.")
        return JsonResponse({"status": "error", "message": "Erreur de service Gemini pendant l'analyse de l'image."}, status=502)
    except Exception:
        mark_scan_error(scan_entry, "gemini_unexpected_error")
        logger.exception("Erreur inattendue pendant le scan de plaque Gemini.")
        return JsonResponse({"status": "error", "message": "Erreur interne pendant l'analyse de l'image."}, status=500)


@api_view(["GET"])
@permission_classes([IsAuthenticated])
def get_last_scan(request):
    last_scan = GeminiScan.objects.select_related("vehicle", "vehicle__owner", "vehicle__owner__person").filter(agent=request.user).order_by("-scanned_at").first()
    if not last_scan:
        return JsonResponse({"status": "error", "message": "Aucun scan disponible pour le moment."}, status=404)
    return JsonResponse(build_scan_response(last_scan, last_scan.vehicle))


@api_view(["GET"])
@permission_classes([IsAuthenticated])
def search_plate(request):
    plate_raw = (request.query_params.get("plate_number") or "").strip()
    if not plate_raw:
        return JsonResponse({"status": "error", "message": "Le parametre plate_number est requis."}, status=400)

    plate_number_display = format_plate_display(plate_raw)
    vehicle = get_vehicle_by_plate(plate_number_display)
    tickets_payload = build_vehicle_tickets_payload(vehicle)
    Scan.objects.create(agent=request.user, plate_number=plate_number_display, source="MANUAL")
    return JsonResponse(
        {
            "status": "success",
            "raw_response": "",
            "plate_number": plate_number_display,
            "plate_detected": bool(plate_number_display),
            "model_used": "manual-search",
            "vehicle": serialize_vehicle(vehicle),
            "documents": build_documents_style_payload(vehicle),
            "tickets": tickets_payload,
            "scanned_at": format_datetime(timezone.now()),
        }
    )
