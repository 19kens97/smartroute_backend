from django.core.exceptions import ValidationError
from django.core.validators import MinValueValidator
from django.db import models

from apps.core.models import TimeStampedModel


class Infraction(TimeStampedModel):
    class Category(models.TextChoices):
        CIRCULATION = "CIRCULATION", "Circulation"
        PARKING = "PARKING", "Arrêt et stationnement"
        DOCUMENTS = "DOCUMENTS", "Documents"
        REGISTRATION = "REGISTRATION", "Immatriculation"
        EQUIPMENT = "EQUIPMENT", "Équipement du véhicule"
        DRIVER_BEHAVIOR = "DRIVER_BEHAVIOR", "Comportement du conducteur"
        PUBLIC_TRANSPORT = "PUBLIC_TRANSPORT", "Transport public"
        ACCIDENT = "ACCIDENT", "Accident"
        ROAD_INFRASTRUCTURE = "ROAD_INFRASTRUCTURE", "Voie et signalisation"
        OTHER = "OTHER", "Autre"

    class PenaltyType(models.TextChoices):
        FIXED = "FIXED", "Montant fixe"
        RANGE = "RANGE", "Intervalle"
        MULTIPLE = "MULTIPLE", "Plusieurs montants possibles"
        TEXT_ONLY = "TEXT_ONLY", "Sanction textuelle"
        NONE = "NONE", "Aucun montant renseigné"

    class LegalClassification(models.TextChoices):
        CONTRAVENTION = "CONTRAVENTION", "Contravention"
        POSSIBLE_OFFENSE = (
            "POSSIBLE_OFFENSE",
            "Délit potentiel à valider",
        )
        OFFENSE = "OFFENSE", "Délit confirmé"
        TO_VALIDATE = "TO_VALIDATE", "Qualification à valider"

    code = models.CharField(
        max_length=20,
        unique=True,
        db_index=True,
    )
    number = models.PositiveIntegerField(
        unique=True,
        db_index=True,
    )
    label = models.CharField(max_length=255)
    official_label = models.CharField(
        max_length=255,
        blank=True,
        default="",
    )
    article = models.CharField(
        max_length=160,
        blank=True,
        default="",
    )
    category = models.CharField(
        max_length=40,
        choices=Category.choices,
        default=Category.OTHER,
        db_index=True,
    )
    penalty_type = models.CharField(
        max_length=20,
        choices=PenaltyType.choices,
        default=PenaltyType.NONE,
        db_index=True,
    )
    amount = models.DecimalField(
        max_digits=12,
        decimal_places=2,
        null=True,
        blank=True,
        validators=[MinValueValidator(0)],
    )
    minimum_amount = models.DecimalField(
        max_digits=12,
        decimal_places=2,
        null=True,
        blank=True,
        validators=[MinValueValidator(0)],
    )
    maximum_amount = models.DecimalField(
        max_digits=12,
        decimal_places=2,
        null=True,
        blank=True,
        validators=[MinValueValidator(0)],
    )
    amount_options = models.JSONField(
        default=list,
        blank=True,
    )
    penalty_text = models.CharField(
        max_length=255,
        blank=True,
        default="",
    )
    currency = models.CharField(
        max_length=3,
        default="HTG",
    )
    legal_classification = models.CharField(
        max_length=24,
        choices=LegalClassification.choices,
        default=LegalClassification.CONTRAVENTION,
        db_index=True,
    )
    requires_authority_review = models.BooleanField(
        default=False,
        db_index=True,
    )
    authority_review_note = models.CharField(
        max_length=255,
        blank=True,
        default="",
    )
    display_order = models.PositiveIntegerField(
        default=0,
        db_index=True,
    )
    active = models.BooleanField(
        default=True,
        db_index=True,
    )

    class Meta:
        ordering = ("display_order", "code")
        constraints = [
            models.CheckConstraint(
                condition=models.Q(number__gt=0),
                name="infraction_number_gt_zero",
            ),
        ]
        indexes = [
            models.Index(
                fields=["active", "category", "display_order"],
                name="inf_active_category_idx",
            ),
            models.Index(
                fields=["legal_classification", "requires_authority_review"],
                name="inf_legal_review_idx",
            ),
        ]
        verbose_name = "Infraction"
        verbose_name_plural = "Infractions"

    def clean(self):
        super().clean()

        self.code = (self.code or "").strip().upper()
        self.label = (self.label or "").strip()
        self.official_label = (
            self.official_label or self.label
        ).strip()
        self.article = (self.article or "").strip()
        self.penalty_text = (self.penalty_text or "").strip()
        self.currency = (self.currency or "HTG").strip().upper()
        self.authority_review_note = (
            self.authority_review_note or ""
        ).strip()

        if not self.code:
            raise ValidationError(
                {"code": "Le code est obligatoire."}
            )

        if not self.label:
            raise ValidationError(
                {"label": "Le libellé est obligatoire."}
            )

        if self.currency != "HTG":
            raise ValidationError(
                {"currency": "La devise attendue est HTG."}
            )

        if self.penalty_type == self.PenaltyType.FIXED:
            if self.amount is None:
                raise ValidationError(
                    {"amount": "Un montant fixe est obligatoire."}
                )
            self.minimum_amount = None
            self.maximum_amount = None
            self.amount_options = []

        elif self.penalty_type == self.PenaltyType.RANGE:
            if (
                self.minimum_amount is None
                or self.maximum_amount is None
            ):
                raise ValidationError(
                    {
                        "minimum_amount": (
                            "Les montants minimum et maximum "
                            "sont obligatoires."
                        )
                    }
                )
            if self.maximum_amount < self.minimum_amount:
                raise ValidationError(
                    {
                        "maximum_amount": (
                            "Le maximum ne peut pas être inférieur "
                            "au minimum."
                        )
                    }
                )
            self.amount = None
            self.amount_options = []

        elif self.penalty_type == self.PenaltyType.MULTIPLE:
            if not self.amount_options:
                raise ValidationError(
                    {
                        "amount_options": (
                            "Au moins deux montants possibles "
                            "doivent être fournis."
                        )
                    }
                )
            normalized = sorted(
                {
                    str(value)
                    for value in self.amount_options
                    if value not in (None, "")
                }
            )
            if len(normalized) < 2:
                raise ValidationError(
                    {
                        "amount_options": (
                            "Au moins deux montants distincts "
                            "sont requis."
                        )
                    }
                )
            self.amount_options = normalized
            self.amount = None
            self.minimum_amount = None
            self.maximum_amount = None

        else:
            self.amount = None
            self.minimum_amount = None
            self.maximum_amount = None
            self.amount_options = []

        if (
            self.legal_classification
            in {
                self.LegalClassification.POSSIBLE_OFFENSE,
                self.LegalClassification.OFFENSE,
                self.LegalClassification.TO_VALIDATE,
            }
            and not self.requires_authority_review
        ):
            raise ValidationError(
                {
                    "requires_authority_review": (
                        "Une qualification non standard doit "
                        "être transmise pour validation."
                    )
                }
            )

    def save(self, *args, **kwargs):
        self.full_clean()
        super().save(*args, **kwargs)

    @property
    def penalty_summary(self):
        if self.penalty_type == self.PenaltyType.FIXED:
            return f"{self.amount} {self.currency}"

        if self.penalty_type == self.PenaltyType.RANGE:
            return (
                f"{self.minimum_amount} à "
                f"{self.maximum_amount} {self.currency}"
            )

        if self.penalty_type == self.PenaltyType.MULTIPLE:
            return (
                " / ".join(self.amount_options)
                + f" {self.currency}"
            )

        return self.penalty_text or "Non renseignée"

    def __str__(self):
        return f"{self.code} - {self.label}"
