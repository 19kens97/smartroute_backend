import logging
from decimal import Decimal

from django.db import transaction

from apps.core.cache import get_cache, safe_cache_get, safe_cache_set
from .catalog import OFFICIAL_INFRACTIONS
from .models import Infraction
from .serializers import InfractionSerializer

logger = logging.getLogger(__name__)

INFRACTION_CATALOG_CACHE_KEY = "smartroute:infractions:active:v1"
INFRACTION_CATALOG_CACHE_TTL_SECONDS = 3600


def normalize_infraction_code(value):
    return str(value or "").strip().upper()


def invalidate_infraction_catalog_cache():
    try:
        get_cache().delete(INFRACTION_CATALOG_CACHE_KEY)
        logger.info("event=infraction_catalog_cache_invalidated")
    except Exception:
        logger.warning("event=infraction_catalog_cache_invalidation_failed", exc_info=True)


def build_infraction_catalog_payload(request=None):
    qs = Infraction.objects.filter(active=True).order_by("display_order", "code")
    items = InfractionSerializer(qs, many=True, context={"request": request}).data
    version = qs.order_by("-updated_at").values_list("updated_at", flat=True).first()
    return {
        "version": version.isoformat() if version else None,
        "count": len(items),
        "items": items,
    }


def get_active_infraction_catalog(request=None):
    cached = safe_cache_get(INFRACTION_CATALOG_CACHE_KEY)
    if cached is not None:
        logger.info("event=infraction_catalog_cache_hit count=%s", cached.get("count"))
        return cached
    logger.info("event=infraction_catalog_cache_miss")
    payload = build_infraction_catalog_payload(request=request)
    safe_cache_set(INFRACTION_CATALOG_CACHE_KEY, payload, timeout=INFRACTION_CATALOG_CACHE_TTL_SECONDS)
    return payload


def seed_official_infractions():
    logger.info("event=infraction_catalog_import_started source=official_dcpr count=%s", len(OFFICIAL_INFRACTIONS))
    created = 0
    updated = 0
    unchanged = 0
    errors = []
    seen = set()

    with transaction.atomic():
        for item in OFFICIAL_INFRACTIONS:
            code = normalize_infraction_code(item["code"])
            if code in seen:
                errors.append(f"Duplicate code in source: {code}")
                continue
            seen.add(code)
            defaults = {
                "number": item.get("number"),
                "label": item["label"],
                "article": item.get("article", ""),
                "category": item.get("category", ""),
                "amount": Decimal(item["amount"]) if item.get("amount") is not None else None,
                "penalty_text": item.get("penalty_text", ""),
                "display_order": item.get("display_order") or item.get("number") or 0,
                "active": item.get("active", True),
            }
            obj, was_created = Infraction.objects.get_or_create(code=code, defaults=defaults)
            if was_created:
                created += 1
                continue
            changed = False
            for field, value in defaults.items():
                if getattr(obj, field) != value:
                    setattr(obj, field, value)
                    changed = True
            if changed:
                obj.save(update_fields=[*defaults.keys(), "updated_at"])
                updated += 1
            else:
                unchanged += 1

    transaction.on_commit(invalidate_infraction_catalog_cache)
    result = {
        "created": created,
        "updated": updated,
        "unchanged": unchanged,
        "disabled": 0,
        "errors": errors,
        "active_count": Infraction.objects.filter(active=True).count(),
    }
    logger.info(
        "event=infraction_catalog_import_completed created=%s updated=%s unchanged=%s disabled=%s errors=%s active_count=%s",
        result["created"],
        result["updated"],
        result["unchanged"],
        result["disabled"],
        len(result["errors"]),
        result["active_count"],
    )
    return result

