from django.db.models.signals import post_delete, post_save
from django.dispatch import receiver

from .models import Infraction


@receiver(
    [post_save, post_delete],
    sender=Infraction,
)
def invalidate_catalog_after_change(**kwargs):
    from .services import (
        invalidate_infraction_catalog_cache,
    )

    invalidate_infraction_catalog_cache()
