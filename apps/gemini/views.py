import re
import logging
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

from .models import GeminiScan
from Documents.models import VehicleInsurance, VehicleRegistration
from Tickets.models import Ticket
from Tickets.serializers import TicketReadSerializer
from Vehicles.models import Vehicle

# Remplacez par votre cle API reelle ou utilisez une variable d'environnement
client = genai.Client(api_key=settings.GOOGLE_API_KEY)
logger = logging.getLogger(__name__)


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
    return (
        Vehicle.objects.select_related("owner")
        .filter(plate_number=plate_number_display)
        .first()
    )


def serialize_owner(owner):
    if owner is None:
        return None
    return {
        "nif": owner.nif,
        "nom": owner.nom,
        "prenom": owner.prenom,
        "adresse": owner.adresse,
        "phone": owner.phone,
        "email": owner.email,
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

    owner = getattr(vehicle, "owner", None)
    latest_insurance = (
        VehicleInsurance.objects.filter(vehicle=vehicle)
        .order_by("-issued_date", "-id")
        .first()
    )
    latest_registration = (
        VehicleRegistration.objects.filter(vehicle=vehicle)
        .order_by("-issued_date", "-id")
        .first()
    )

    return {
        "vehicule": {
            "plaque": vehicle.plate_number,
            "marque": vehicle.brand,
            "modele": vehicle.model,
            "couleur": vehicle.color,
            "annee": vehicle.year,
        },
        "proprietaire": {
            "nif": owner.nif,
            "nom": owner.nom,
            "prenom": owner.prenom,
            "adresse": owner.adresse,
            "telephone": owner.phone,
            "email": owner.email,
        }
        if owner
        else None,
        "assurance": {
            "numero_police": latest_insurance.policy_number,
            "compagnie": latest_insurance.company_name,
            "date_emission": format_date(latest_insurance.issued_date),
            "date_expiration": format_date(latest_insurance.expiration_date),
            "est_active": latest_insurance.is_active,
        }
        if latest_insurance
        else None,
        "immatriculation": {
            "numero_immatriculation": latest_registration.registration_code,
            "type": latest_registration.registration_type,
            "date_emission": format_date(latest_registration.issued_date),
            "date_expiration": format_date(latest_registration.expiry_date),
        }
        if latest_registration
        else None,
    }


def build_vehicle_tickets_payload(vehicle):
    tickets_qs = (
        Ticket.objects.select_related(
            "vehicle",
            "vehicle__owner",
            "driver_license",
            "driver_license__user",
            "infraction",
            "agent",
        )
        .prefetch_related("infractions")
        .filter(vehicle=vehicle)
        .order_by("-timestamp")
    )
    tickets_data = TicketReadSerializer(tickets_qs, many=True).data
    return {
        "summary": {
            "total": len(tickets_data),
            "en_cours": sum(1 for item in tickets_data if item.get("status") == Ticket.STATUS_EN_COURS),
            "regle": sum(1 for item in tickets_data if item.get("status") == Ticket.STATUS_REGLE),
        },
        "items": tickets_data,
    }


def generate_with_fallbacks(contents):
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
            # Flux simple: on renvoie la reponse Gemini meme si elle n'est pas
            # encore exploitable, puis on traite ensuite pour l'affichage.
            return response, model, plate_candidate, raw_text
        except exceptions.ServiceUnavailable as e:
            last_error = e
            time.sleep(0.4)
            continue
        except genai_errors.ServerError as e:
            last_error = e
            if is_temporary_gemini_unavailable(e):
                time.sleep(0.4)
            continue
        except Exception as e:
            last_error = e
            continue

    if last_error is not None:
        raise last_error
    raise ValueError("Aucune reponse recue depuis les modeles Gemini.")


@api_view(["POST"])
@permission_classes([IsAuthenticated])
def extract_license_plate(request):
    if request.FILES.get("image"):
        try:
            # 1. Recuperer l'image depuis la requete
            image_file = request.FILES["image"]
            image_bytes = image_file.read()

            # 2. Preparer le prompt specifique pour le LPR (License Plate Recognition)
            prompt = (
                "Identifie la plaque d'immatriculation sur cette image. "
                "Renvoie uniquement le numero de la plaque, sans texte additionnel, "
                "sans ponctuation inutile, en majuscules."
            )

            # 3. Appel a Gemini avec fallback automatique par modele
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
            scan_entry = None
            try:
                if plate_number_display:
                    scan_entry = GeminiScan.objects.create(
                        plate_number=plate_number_display,
                        model_used=model_used,
                        vehicle=vehicle,
                        agent=request.user,
                    )
            except Exception:
                logger.exception("Impossible d'enregistrer le scan Gemini en base.")

            documents_payload = build_documents_style_payload(vehicle)

            return JsonResponse(
                {
                    "status": "success",
                    "raw_response": raw_text,
                    "plate_number": plate_number_display,
                    "plate_detected": bool(plate_number_display),
                    "model_used": model_used,
                    "vehicle": serialize_vehicle(vehicle),
                    "documents": documents_payload,
                    "scanned_at": format_datetime(getattr(scan_entry, "scanned_at", timezone.now())),
                }
            )

        except ValueError as e:
            return JsonResponse(
                {"status": "error", "message": str(e)},
                status=422,
            )
        except exceptions.InvalidArgument:
            return JsonResponse(
                {
                    "status": "error",
                    "message": "Image invalide ou format non supporte.",
                },
                status=400,
            )
        except exceptions.Unauthenticated:
            return JsonResponse(
                {
                    "status": "error",
                    "message": "Configuration Gemini invalide (authentification).",
                },
                status=502,
            )
        except exceptions.PermissionDenied:
            return JsonResponse(
                {
                    "status": "error",
                    "message": "Acces Gemini refuse. Verifiez la configuration du projet Google.",
                },
                status=502,
            )
        except exceptions.ResourceExhausted:
            return JsonResponse(
                {
                    "status": "error",
                    "message": "Quota Gemini depasse. Reessayez plus tard.",
                },
                status=429,
            )
        except exceptions.ServiceUnavailable:
            return JsonResponse(
                {
                    "status": "error",
                    "message": "Le service est temporairement surcharge. Reessayez dans quelques instants.",
                },
                status=503,
            )
        except genai_errors.ServerError as e:
            if is_temporary_gemini_unavailable(e):
                return JsonResponse(
                    {
                        "status": "error",
                        "message": "Le service Gemini est temporairement surcharge. Reessayez dans quelques instants.",
                    },
                    status=503,
                )
            logger.exception("Erreur Gemini (ServerError) pendant le scan de plaque.")
            return JsonResponse(
                {
                    "status": "error",
                    "message": "Erreur de service Gemini pendant l'analyse de l'image.",
                },
                status=502,
            )
        except Exception:
            logger.exception("Erreur inattendue pendant le scan de plaque Gemini.")
            return JsonResponse(
                {
                    "status": "error",
                    "message": "Erreur interne pendant l'analyse de l'image.",
                },
                status=500,
            )

    return JsonResponse({"status": "error", "message": "Invalid request"}, status=400)


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
        return JsonResponse(
            {"status": "error", "message": "Aucun scan disponible pour le moment."},
            status=404,
        )

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
        return JsonResponse(
            {"status": "error", "message": "Le parametre plate_number est requis."},
            status=400,
        )

    plate_number_display = format_plate_display(plate_raw)
    vehicle = get_vehicle_by_plate(plate_number_display)
    if vehicle is None:
        return JsonResponse(
            {
                "status": "error",
                "message": "Vehicule introuvable pour cette plaque.",
                "plate_number": plate_number_display,
            },
            status=404,
        )

    return JsonResponse(
        {
            "status": "success",
            "plate_number": plate_number_display,
            "vehicle": serialize_vehicle(vehicle),
            "tickets": build_vehicle_tickets_payload(vehicle),
        }
    )
