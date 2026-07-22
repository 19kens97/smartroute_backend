import logging
import re
from decimal import Decimal, InvalidOperation

from django.db import transaction

from apps.core.cache import (
    get_cache,
    safe_cache_get,
    safe_cache_set,
)

from .catalog import OFFICIAL_INFRACTIONS
from .models import Infraction
from .serializers import InfractionSerializer


logger = logging.getLogger(__name__)

INFRACTION_CATALOG_CACHE_KEY = (
    "smartroute:infractions:active:v2"
)
INFRACTION_CATALOG_CACHE_TTL_SECONDS = 900
CATALOG_VERSION = "2026.07.21"


CATEGORY_BY_NUMBER = {
    Infraction.Category.PARKING: {
        2, 11, 22, 23,
    },
    Infraction.Category.DOCUMENTS: {
        5, 6, 7, 8, 31, 43, 54, 56, 57, 60, 70,
    },
    Infraction.Category.REGISTRATION: {
        10, 13, 37, 58,
    },
    Infraction.Category.EQUIPMENT: {
        9, 12, 14, 17, 18, 32, 33, 51, 74,
    },
    Infraction.Category.DRIVER_BEHAVIOR: {
        4, 19, 20, 24, 25, 26, 27, 29, 30, 34,
        35, 36, 38, 42, 45, 46, 47, 52, 59, 63,
        65, 66, 67, 73,
    },
    Infraction.Category.PUBLIC_TRANSPORT: {
        28, 39, 40, 41, 44, 48, 50,
    },
    Infraction.Category.ACCIDENT: {
        21, 61, 62, 64,
    },
    Infraction.Category.ROAD_INFRASTRUCTURE: {
        53, 68, 69,
    },
}

LEGAL_REVIEW_CANDIDATES = {
    "I006": (
        "Libellé mixte : conduite sans permis, sans carte "
        "d'enregistrement ou avec assurance expirée. "
        "À scinder et faire qualifier juridiquement."
    ),
    "I021": (
        "Fuite après accident : transmission à l'autorité "
        "et qualification pénale à confirmer."
    ),
    "I036": (
        "Refus d'obtempérer à l'injonction d'un agent : "
        "qualification et procédure d'interpellation à confirmer."
    ),
    "I037": (
        "Transfert de plaques sur un autre véhicule : "
        "risque de fraude documentaire à confirmer."
    ),
    "I060": (
        "Prêt, don ou usage du permis d'autrui : "
        "risque de fraude ou d'usurpation à confirmer."
    ),
    "I064": (
        "Accident causé en franchissant un feu rouge : "
        "la qualification dépend notamment des dommages."
    ),
    "I068": (
        "Le catalogue mentionne explicitement des poursuites "
        "pénales et le coût de remplacement."
    ),
    "I071": (
        "Circulation avec un véhicule déclaré hors service : "
        "mesures d'immobilisation et qualification à confirmer."
    ),
}


def normalize_infraction_code(value):
    return str(value or "").strip().upper()


def infer_category(number):
    for category, numbers in CATEGORY_BY_NUMBER.items():
        if number in numbers:
            return category

    return Infraction.Category.CIRCULATION


def _decimal(value):
    try:
        return Decimal(str(value))
    except (InvalidOperation, TypeError, ValueError):
        return None


def parse_penalty(item):
    amount = _decimal(item.get("amount"))
    text = str(item.get("penalty_text") or "").strip()

    if amount is not None:
        return {
            "penalty_type": Infraction.PenaltyType.FIXED,
            "amount": amount,
            "minimum_amount": None,
            "maximum_amount": None,
            "amount_options": [],
        }

    range_match = re.fullmatch(
        r"\s*(\d+(?:[.,]\d+)?)\s*-\s*"
        r"(\d+(?:[.,]\d+)?)\s*",
        text,
    )
    if range_match:
        return {
            "penalty_type": Infraction.PenaltyType.RANGE,
            "amount": None,
            "minimum_amount": _decimal(
                range_match.group(1).replace(",", ".")
            ),
            "maximum_amount": _decimal(
                range_match.group(2).replace(",", ".")
            ),
            "amount_options": [],
        }

    multiple_match = re.fullmatch(
        r"\s*(\d+(?:[.,]\d+)?(?:\s*/\s*"
        r"\d+(?:[.,]\d+)?)+)\s*",
        text,
    )
    if multiple_match:
        options = [
            value.strip().replace(",", ".")
            for value in text.split("/")
        ]
        return {
            "penalty_type": Infraction.PenaltyType.MULTIPLE,
            "amount": None,
            "minimum_amount": None,
            "maximum_amount": None,
            "amount_options": options,
        }

    if text:
        return {
            "penalty_type": Infraction.PenaltyType.TEXT_ONLY,
            "amount": None,
            "minimum_amount": None,
            "maximum_amount": None,
            "amount_options": [],
        }

    return {
        "penalty_type": Infraction.PenaltyType.NONE,
        "amount": None,
        "minimum_amount": None,
        "maximum_amount": None,
        "amount_options": [],
    }


def validate_catalog_source():
    errors = []
    seen_codes = set()
    seen_numbers = set()

    if len(OFFICIAL_INFRACTIONS) != 74:
        errors.append(
            "Le catalogue doit contenir exactement 74 entrées."
        )

    for index, item in enumerate(
        OFFICIAL_INFRACTIONS,
        start=1,
    ):
        code = normalize_infraction_code(
            item.get("code")
        )
        number = item.get("number")
        label = str(item.get("label") or "").strip()

        if not code:
            errors.append(
                f"Entrée {index}: code manquant."
            )
        elif code in seen_codes:
            errors.append(
                f"Code dupliqué: {code}."
            )
        seen_codes.add(code)

        if not isinstance(number, int) or number <= 0:
            errors.append(
                f"{code or index}: numéro invalide."
            )
        elif number in seen_numbers:
            errors.append(
                f"Numéro dupliqué: {number}."
            )
        seen_numbers.add(number)

        if not label:
            errors.append(
                f"{code or index}: libellé manquant."
            )

        parsed = parse_penalty(item)
        if (
            parsed["penalty_type"]
            == Infraction.PenaltyType.RANGE
            and parsed["maximum_amount"]
            < parsed["minimum_amount"]
        ):
            errors.append(
                f"{code}: intervalle de sanction invalide."
            )

    return errors


def invalidate_infraction_catalog_cache():
    try:
        get_cache().delete(
            INFRACTION_CATALOG_CACHE_KEY
        )
    except Exception:
        logger.warning(
            "event=infraction_catalog_cache_invalidation_failed",
            exc_info=True,
        )


def build_infraction_catalog_payload(request=None):
    queryset = (
        Infraction.objects
        .filter(active=True)
        .order_by("display_order", "code")
    )
    items = InfractionSerializer(
        queryset,
        many=True,
        context={"request": request},
    ).data

    return {
        "version": CATALOG_VERSION,
        "count": len(items),
        "currency": "HTG",
        "items": items,
    }


def get_active_infraction_catalog(request=None):
    cached = safe_cache_get(
        INFRACTION_CATALOG_CACHE_KEY
    )

    if cached is not None:
        return cached

    payload = build_infraction_catalog_payload(
        request=request
    )
    safe_cache_set(
        INFRACTION_CATALOG_CACHE_KEY,
        payload,
        timeout=(
            INFRACTION_CATALOG_CACHE_TTL_SECONDS
        ),
    )
    return payload


@transaction.atomic
def seed_official_infractions(
    *,
    disable_missing=False,
):
    errors = validate_catalog_source()

    if errors:
        return {
            "created": 0,
            "updated": 0,
            "unchanged": 0,
            "disabled": 0,
            "errors": errors,
            "active_count": (
                Infraction.objects.filter(
                    active=True
                ).count()
            ),
        }

    created = 0
    updated = 0
    unchanged = 0
    seen_codes = set()

    for item in OFFICIAL_INFRACTIONS:
        code = normalize_infraction_code(
            item["code"]
        )
        number = item["number"]
        seen_codes.add(code)

        legal_note = LEGAL_REVIEW_CANDIDATES.get(
            code,
            "",
        )
        penalty = parse_penalty(item)

        defaults = {
            "number": number,
            "label": item["label"].strip(),
            "official_label": item["label"].strip(),
            "article": str(
                item.get("article") or ""
            ).strip(),
            "category": infer_category(number),
            **penalty,
            "penalty_text": str(
                item.get("penalty_text") or ""
            ).strip(),
            "currency": "HTG",
            "legal_classification": (
                Infraction.LegalClassification.POSSIBLE_OFFENSE
                if legal_note
                else Infraction.LegalClassification.CONTRAVENTION
            ),
            "requires_authority_review": bool(
                legal_note
            ),
            "authority_review_note": legal_note,
            "display_order": (
                item.get("display_order")
                or number
            ),
            "active": item.get("active", True),
        }

        obj, was_created = (
            Infraction.objects.get_or_create(
                code=code,
                defaults=defaults,
            )
        )

        if was_created:
            created += 1
            continue

        changed_fields = []

        for field, value in defaults.items():
            if getattr(obj, field) != value:
                setattr(obj, field, value)
                changed_fields.append(field)

        if changed_fields:
            obj.save(
                update_fields=[
                    *changed_fields,
                    "updated_at",
                ]
            )
            updated += 1
        else:
            unchanged += 1

    disabled = 0

    if disable_missing:
        missing = (
            Infraction.objects
            .exclude(code__in=seen_codes)
            .filter(active=True)
        )
        disabled = missing.count()
        from django.utils import timezone

        missing.update(
            active=False,
            updated_at=timezone.now(),
        )

    transaction.on_commit(
        invalidate_infraction_catalog_cache
    )

    return {
        "created": created,
        "updated": updated,
        "unchanged": unchanged,
        "disabled": disabled,
        "errors": [],
        "active_count": (
            Infraction.objects.filter(
                active=True
            ).count()
        ),
    }
