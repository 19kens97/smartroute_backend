import django.db.models.deletion
import uuid
from django.conf import settings
from django.db import migrations, models
from django.utils import timezone


def backfill_ticket_refactor(apps, schema_editor):
    Ticket = apps.get_model("tickets", "Ticket")
    TicketVerbalization = apps.get_model("tickets", "TicketVerbalization")
    TicketInfraction = apps.get_model("tickets", "TicketInfraction")
    TicketProof = apps.get_model("tickets", "TicketProof")

    for ticket in Ticket.objects.all().order_by("id"):
        old_status = ticket.status
        occurred_at = getattr(ticket, "occurred_at", None) or ticket.created_at
        ticket.barcode_value = ticket.barcode_value or f"PV:{ticket.ticket_number}"
        ticket.opened_by_id = getattr(ticket, "agent_id", None)
        ticket.opened_at = occurred_at or timezone.now()
        ticket.driver_dossier_snapshot = getattr(ticket, "driver_license", "") or ""
        ticket.driver_name_snapshot = getattr(ticket, "driver_name_snapshot", "") or ""
        ticket.driver_nif_snapshot = ""
        ticket.sync_status = "PENDING" if old_status == "PENDING_SYNC" else "SYNCED"
        if old_status == "CANCELLED":
            ticket.status = "CANCELLED"
            ticket.cancelled_at = ticket.opened_at
            ticket.cancelled_by_id = ticket.opened_by_id
            ticket.cancellation_reason = ticket.note or "Migration ancien statut annule."
        elif old_status in ("PAID", "VALIDATED", "ISSUED"):
            ticket.status = "CLOSED"
            ticket.closed_at = ticket.opened_at
            ticket.closed_by_id = ticket.opened_by_id
            ticket.closure_reason = ticket.note or "Migration ancien statut cloture."
        else:
            ticket.status = "OPEN"
        ticket.save(
            update_fields=[
                "barcode_value",
                "opened_by",
                "opened_at",
                "driver_dossier_snapshot",
                "driver_name_snapshot",
                "driver_nif_snapshot",
                "sync_status",
                "status",
                "closed_at",
                "closed_by",
                "closure_reason",
                "cancelled_at",
                "cancelled_by",
                "cancellation_reason",
            ]
        )

        verbalization, _ = TicketVerbalization.objects.get_or_create(
            ticket=ticket,
            sequence_number=1,
            defaults={
                "client_uuid": uuid.uuid4(),
                "agent_id": getattr(ticket, "agent_id", None),
                "vehicle_id": getattr(ticket, "vehicle_id", None),
                "plate_number_snapshot": getattr(ticket, "plate_number_snapshot", "") or "",
                "occurred_at": occurred_at or timezone.now(),
                "location_label": getattr(ticket, "location_label", "") or "",
                "latitude": getattr(ticket, "latitude", None),
                "longitude": getattr(ticket, "longitude", None),
                "note": ticket.note or "",
                "status": "CANCELLED" if old_status == "CANCELLED" else "ACTIVE",
                "cancelled_at": ticket.cancelled_at,
                "cancelled_by_id": ticket.cancelled_by_id,
                "cancellation_reason": ticket.cancellation_reason,
            },
        )

        TicketProof.objects.filter(ticket=ticket, verbalization__isnull=True).update(
            verbalization=verbalization
        )
        for link in TicketInfraction.objects.filter(ticket=ticket, verbalization__isnull=True):
            infraction = link.infraction
            link.verbalization_id = verbalization.id
            link.code_snapshot = getattr(infraction, "code", "") or ""
            link.label_snapshot = getattr(infraction, "label", "") or ""
            link.article_snapshot = getattr(infraction, "article", "") or ""
            link.penalty_type_snapshot = getattr(infraction, "penalty_type", "") or ""
            link.minimum_amount_snapshot = getattr(infraction, "minimum_amount", None)
            link.maximum_amount_snapshot = getattr(infraction, "maximum_amount", None)
            link.amount_options_snapshot = getattr(infraction, "amount_options", []) or []
            link.penalty_text_snapshot = getattr(infraction, "penalty_text", "") or ""
            link.currency_snapshot = getattr(infraction, "currency", "HTG") or "HTG"
            link.save()


class Migration(migrations.Migration):
    dependencies = [
        ("drivers", "0004_driver_person_identity"),
        ("tickets", "0007_normalize_ticket_statuses"),
        ("vehicles", "0003_vehicle_registration_valid_until"),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.AddField(
            model_name="ticket",
            name="barcode_value",
            field=models.CharField(blank=True, db_index=True, editable=False, max_length=120, null=True, unique=True),
        ),
        migrations.AddField(
            model_name="ticket",
            name="driver",
            field=models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.PROTECT, related_name="tickets", to="drivers.driver"),
        ),
        migrations.AddField(
            model_name="ticket",
            name="driver_dossier_snapshot",
            field=models.CharField(blank=True, db_index=True, default="", max_length=80),
        ),
        migrations.AddField(
            model_name="ticket",
            name="driver_nif_snapshot",
            field=models.CharField(blank=True, db_index=True, default="", max_length=40),
        ),
        migrations.AddField(
            model_name="ticket",
            name="opened_at",
            field=models.DateTimeField(blank=True, db_index=True, null=True),
        ),
        migrations.AddField(
            model_name="ticket",
            name="opened_by",
            field=models.ForeignKey(null=True, on_delete=django.db.models.deletion.PROTECT, related_name="opened_tickets", to=settings.AUTH_USER_MODEL),
        ),
        migrations.AddField(
            model_name="ticket",
            name="sync_status",
            field=models.CharField(choices=[("PENDING", "En attente"), ("SYNCED", "Synchronise"), ("FAILED", "Echec")], db_index=True, default="SYNCED", max_length=20),
        ),
        migrations.AddField(
            model_name="ticket",
            name="pricing_status",
            field=models.CharField(choices=[("NOT_REQUESTED", "Non demande"), ("PENDING", "Demande en cours"), ("AVAILABLE", "Disponible"), ("FAILED", "Echec")], db_index=True, default="NOT_REQUESTED", max_length=20),
        ),
        migrations.AddField(model_name="ticket", name="pricing_authority", field=models.CharField(blank=True, default="", max_length=40)),
        migrations.AddField(model_name="ticket", name="pricing_external_reference", field=models.CharField(blank=True, default="", max_length=120)),
        migrations.AddField(model_name="ticket", name="pricing_requested_at", field=models.DateTimeField(blank=True, null=True)),
        migrations.AddField(model_name="ticket", name="pricing_last_checked_at", field=models.DateTimeField(blank=True, null=True)),
        migrations.AddField(model_name="ticket", name="pricing_message", field=models.CharField(blank=True, default="", max_length=255)),
        migrations.AddField(model_name="ticket", name="closed_at", field=models.DateTimeField(blank=True, null=True)),
        migrations.AddField(
            model_name="ticket",
            name="closed_by",
            field=models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.PROTECT, related_name="closed_tickets", to=settings.AUTH_USER_MODEL),
        ),
        migrations.AddField(model_name="ticket", name="closure_reason", field=models.TextField(blank=True, default="")),
        migrations.AddField(model_name="ticket", name="cancelled_at", field=models.DateTimeField(blank=True, null=True)),
        migrations.AddField(
            model_name="ticket",
            name="cancelled_by",
            field=models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.PROTECT, related_name="cancelled_tickets", to=settings.AUTH_USER_MODEL),
        ),
        migrations.AddField(model_name="ticket", name="cancellation_reason", field=models.TextField(blank=True, default="")),
        migrations.CreateModel(
            name="TicketVerbalization",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("created_at", models.DateTimeField(auto_now_add=True, db_index=True)),
                ("updated_at", models.DateTimeField(auto_now=True, db_index=True)),
                ("client_uuid", models.UUIDField(db_index=True, default=uuid.uuid4, editable=False, unique=True)),
                ("sequence_number", models.PositiveIntegerField()),
                ("plate_number_snapshot", models.CharField(db_index=True, max_length=20)),
                ("occurred_at", models.DateTimeField(db_index=True, default=timezone.now)),
                ("location_label", models.CharField(blank=True, default="", max_length=255)),
                ("latitude", models.DecimalField(blank=True, decimal_places=6, max_digits=9, null=True)),
                ("longitude", models.DecimalField(blank=True, decimal_places=6, max_digits=9, null=True)),
                ("note", models.TextField(blank=True, default="")),
                ("status", models.CharField(choices=[("ACTIVE", "Active"), ("CANCELLED", "Annulee")], db_index=True, default="ACTIVE", max_length=20)),
                ("cancelled_at", models.DateTimeField(blank=True, null=True)),
                ("cancellation_reason", models.TextField(blank=True, default="")),
                ("agent", models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name="ticket_verbalizations", to=settings.AUTH_USER_MODEL)),
                ("cancelled_by", models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.PROTECT, related_name="cancelled_ticket_verbalizations", to=settings.AUTH_USER_MODEL)),
                ("ticket", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="verbalizations", to="tickets.ticket")),
                ("vehicle", models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name="ticket_verbalizations", to="vehicles.vehicle")),
            ],
            options={
                "ordering": ("sequence_number", "id"),
            },
        ),
        migrations.AddField(
            model_name="ticketproof",
            name="verbalization",
            field=models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.CASCADE, related_name="proofs", to="tickets.ticketverbalization"),
        ),
        migrations.AddField(
            model_name="ticketinfraction",
            name="verbalization",
            field=models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.CASCADE, related_name="infractions", to="tickets.ticketverbalization"),
        ),
        migrations.AddField(model_name="ticketinfraction", name="code_snapshot", field=models.CharField(blank=True, default="", max_length=20)),
        migrations.AddField(model_name="ticketinfraction", name="label_snapshot", field=models.CharField(blank=True, default="", max_length=255)),
        migrations.AddField(model_name="ticketinfraction", name="article_snapshot", field=models.CharField(blank=True, default="", max_length=160)),
        migrations.AddField(model_name="ticketinfraction", name="penalty_type_snapshot", field=models.CharField(blank=True, default="", max_length=20)),
        migrations.AddField(model_name="ticketinfraction", name="minimum_amount_snapshot", field=models.DecimalField(blank=True, decimal_places=2, max_digits=12, null=True)),
        migrations.AddField(model_name="ticketinfraction", name="maximum_amount_snapshot", field=models.DecimalField(blank=True, decimal_places=2, max_digits=12, null=True)),
        migrations.AddField(model_name="ticketinfraction", name="amount_options_snapshot", field=models.JSONField(blank=True, default=list)),
        migrations.AddField(model_name="ticketinfraction", name="penalty_text_snapshot", field=models.CharField(blank=True, default="", max_length=255)),
        migrations.AddField(model_name="ticketinfraction", name="currency_snapshot", field=models.CharField(default="HTG", max_length=3)),
        migrations.AlterField(model_name="ticket", name="note", field=models.TextField(blank=True, default="")),
        migrations.AlterField(model_name="ticketproof", name="caption", field=models.CharField(blank=True, default="", max_length=200)),
        migrations.RunPython(backfill_ticket_refactor, migrations.RunPython.noop),
        migrations.AlterField(model_name="ticket", name="barcode_value", field=models.CharField(db_index=True, editable=False, max_length=120, unique=True)),
        migrations.AlterField(model_name="ticket", name="opened_at", field=models.DateTimeField(db_index=True, default=timezone.now)),
        migrations.AlterField(model_name="ticket", name="opened_by", field=models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name="opened_tickets", to=settings.AUTH_USER_MODEL)),
        migrations.AlterField(
            model_name="ticket",
            name="status",
            field=models.CharField(choices=[("OPEN", "En cours"), ("CLOSED", "Cloture"), ("CANCELLED", "Annule")], db_index=True, default="OPEN", max_length=20),
        ),
        migrations.AlterField(model_name="ticketinfraction", name="amount_snapshot", field=models.DecimalField(blank=True, decimal_places=2, max_digits=12, null=True)),
        migrations.AlterField(model_name="ticketinfraction", name="code_snapshot", field=models.CharField(max_length=20)),
        migrations.AlterField(model_name="ticketinfraction", name="label_snapshot", field=models.CharField(max_length=255)),
        migrations.AlterField(model_name="ticketinfraction", name="penalty_type_snapshot", field=models.CharField(max_length=20)),
        migrations.AlterField(model_name="ticketproof", name="checksum_sha256", field=models.CharField(blank=True, default="", max_length=64)),
        migrations.AlterField(model_name="ticketproof", name="created_by", field=models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name="ticket_proofs", to=settings.AUTH_USER_MODEL)),
        migrations.AlterField(model_name="ticketproof", name="verbalization", field=models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="proofs", to="tickets.ticketverbalization")),
        migrations.RemoveField(model_name="ticket", name="agent"),
        migrations.RemoveField(model_name="ticket", name="barcode_image"),
        migrations.RemoveField(model_name="ticket", name="driver_license"),
        migrations.RemoveField(model_name="ticket", name="latitude"),
        migrations.RemoveField(model_name="ticket", name="location_label"),
        migrations.RemoveField(model_name="ticket", name="longitude"),
        migrations.RemoveField(model_name="ticket", name="occurred_at"),
        migrations.RemoveField(model_name="ticket", name="plate_number_snapshot"),
        migrations.RemoveField(model_name="ticket", name="vehicle"),
        migrations.RemoveField(model_name="ticketinfraction", name="ticket"),
        migrations.RemoveField(model_name="ticketproof", name="ticket"),
        migrations.AddConstraint(
            model_name="ticketverbalization",
            constraint=models.UniqueConstraint(fields=("ticket", "sequence_number"), name="unique_verbalization_sequence_per_ticket"),
        ),
        migrations.AddConstraint(
            model_name="ticketinfraction",
            constraint=models.UniqueConstraint(fields=("verbalization", "infraction"), name="unique_infraction_per_verbalization"),
        ),
        migrations.AlterModelOptions(name="ticket", options={"ordering": ("-opened_at", "-id")}),
        migrations.AlterModelOptions(name="ticketinfraction", options={"ordering": ("id",)}),
        migrations.AlterModelOptions(name="ticketproof", options={"ordering": ("created_at", "id")}),
        migrations.AddIndex(model_name="ticket", index=models.Index(fields=("status", "opened_at"), name="ticket_status_opened_idx")),
        migrations.AddIndex(model_name="ticket", index=models.Index(fields=("driver", "status"), name="ticket_driver_status_idx")),
        migrations.AddIndex(model_name="ticket", index=models.Index(fields=("pricing_status", "status"), name="ticket_pricing_status_idx")),
        migrations.AddIndex(model_name="ticketverbalization", index=models.Index(fields=("ticket", "status", "occurred_at"), name="verbal_ticket_status_idx")),
        migrations.AddIndex(model_name="ticketverbalization", index=models.Index(fields=("plate_number_snapshot", "occurred_at"), name="verbal_plate_occurred_idx")),
    ]
