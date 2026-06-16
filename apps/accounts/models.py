from django.contrib.auth.models import AbstractUser
from django.db import models


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
