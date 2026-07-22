from django.conf import settings
from django.db import models


class TimeStampedModel(models.Model):
    created_at = models.DateTimeField(auto_now_add=True, db_index=True)
    updated_at = models.DateTimeField(auto_now=True, db_index=True)

    class Meta:
        abstract = True


class AuditLog(TimeStampedModel):
    class Action(models.TextChoices):
        CREATE = "CREATE", "Création"
        UPDATE = "UPDATE", "Modification"
        STATUS_CHANGE = "STATUS_CHANGE", "Changement de statut"
        CANCEL = "CANCEL", "Annulation"
        CLOSE = "CLOSE", "Clôture"
        ADD_PROOF = "ADD_PROOF", "Ajout de preuve"
        ADD_EVIDENCE = "ADD_EVIDENCE", "Ajout de preuve de délit"
        ADD_ACTION = "ADD_ACTION", "Ajout d'action"
        SUBMIT_REVIEW = "SUBMIT_REVIEW", "Soumission pour examen"
        CONFIRM = "CONFIRM", "Confirmation"
        REJECT = "REJECT", "Rejet"
        REFER = "REFER", "Transmission"
        LOGIN = "LOGIN", "Connexion"
        LOGOUT = "LOGOUT", "Déconnexion"
        PASSWORD_RESET = "PASSWORD_RESET", "Réinitialisation du mot de passe"
        ACCOUNT_SUSPEND = "ACCOUNT_SUSPEND", "Suspension du compte"
        ACCOUNT_REACTIVATE = "ACCOUNT_REACTIVATE", "Réactivation du compte"
        DEVICE_REGISTER = "DEVICE_REGISTER", "Enregistrement d'appareil"
        DEVICE_REVOKE = "DEVICE_REVOKE", "Révocation d'appareil"
        LICENSE_RETAIN = "LICENSE_RETAIN", "Rétention de permis"
        LICENSE_RELEASE = "LICENSE_RELEASE", "Restitution de permis"
        OTHER = "OTHER", "Autre"

    actor = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="audit_logs",
    )
    actor_email_snapshot = models.EmailField(blank=True, default="")
    actor_role_snapshot = models.CharField(max_length=40, blank=True, default="")
    action = models.CharField(
        max_length=40,
        choices=Action.choices,
        db_index=True,
    )
    app_label = models.CharField(max_length=100, blank=True, default="")
    model_name = models.CharField(max_length=120, blank=True, default="")
    object_id = models.CharField(max_length=120, blank=True, default="")
    object_repr = models.CharField(max_length=255, blank=True, default="")
    request_id = models.CharField(max_length=64, blank=True, default="", db_index=True)
    request_method = models.CharField(max_length=12, blank=True, default="")
    request_path = models.CharField(max_length=500, blank=True, default="")
    ip_address = models.GenericIPAddressField(null=True, blank=True)
    user_agent = models.CharField(max_length=500, blank=True, default="")
    success = models.BooleanField(default=True, db_index=True)
    payload = models.JSONField(default=dict, blank=True)

    class Meta:
        ordering = ("-created_at", "-id")
        indexes = [
            models.Index(
                fields=("app_label", "model_name", "object_id"),
                name="audit_object_lookup_idx",
            ),
            models.Index(
                fields=("actor", "action", "created_at"),
                name="audit_actor_action_idx",
            ),
        ]

    def __str__(self):
        target = self.object_repr or self.object_id or "global"
        return f"{self.action} - {target}"
