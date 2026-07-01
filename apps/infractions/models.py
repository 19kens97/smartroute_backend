from django.db import models
from apps.core.models import TimeStampedModel


class Infraction(TimeStampedModel):
    code = models.CharField(max_length=20, unique=True, db_index=True)
    number = models.PositiveIntegerField(null=True, blank=True, db_index=True)
    label = models.CharField(max_length=220)
    article = models.CharField(max_length=160, blank=True)
    category = models.CharField(max_length=80, blank=True)
    amount = models.DecimalField(max_digits=10, decimal_places=2, null=True, blank=True)
    penalty_text = models.CharField(max_length=120, blank=True)
    display_order = models.PositiveIntegerField(default=0, db_index=True)
    active = models.BooleanField(default=True, db_index=True)

    class Meta:
        ordering = ("display_order", "code")

    def save(self, *args, **kwargs):
        if self.code:
            self.code = self.code.strip().upper()
        super().save(*args, **kwargs)

    def __str__(self):
        return f"{self.code} - {self.label}"
