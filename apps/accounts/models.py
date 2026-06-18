import uuid

from django.conf import settings
from django.contrib.auth.models import AbstractUser
from django.core.files.storage import FileSystemStorage
from django.db import models
from django.utils.deconstruct import deconstructible


def user_signature_upload_path(instance, filename):
    return f"{instance.pk}/{uuid.uuid4()}.png"


@deconstructible
class PrivateSignatureStorage(FileSystemStorage):
    def __init__(self, *args, **kwargs):
        kwargs.setdefault("location", settings.PRIVATE_SIGNATURE_ROOT)
        kwargs.setdefault("base_url", None)
        super().__init__(*args, **kwargs)


private_signature_storage = PrivateSignatureStorage()


class User(AbstractUser):
    class Role(models.TextChoices):
        ADMIN = "ADMIN", "ADMIN"
        AGENT_TERRAIN = "AGENT_TERRAIN", "AGENT_TERRAIN"
        AGENT_SAISIE = "AGENT_SAISIE", "AGENT_SAISIE"

    role = models.CharField(max_length=20, choices=Role.choices, default=Role.AGENT_SAISIE)
    badge_number = models.CharField(max_length=40, blank=True, default="")
    nif = models.CharField(max_length=40, blank=True, default="")
    phone = models.CharField(max_length=30, blank=True, default="")
    post = models.CharField(max_length=120, blank=True, default="")
    precinct = models.CharField(max_length=120, blank=True, default="")
    signature_file = models.ImageField(
        upload_to=user_signature_upload_path,
        storage=private_signature_storage,
        blank=True,
        null=True,
    )
    signature_sha256 = models.CharField(max_length=64, blank=True, default="")
    signature_updated_at = models.DateTimeField(blank=True, null=True)
