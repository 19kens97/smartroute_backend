from django.db import migrations, models


def normalize_ticket_statuses(apps, schema_editor):
    Ticket = apps.get_model("tickets", "Ticket")
    Ticket.objects.filter(status__in=("DRAFT", "ISSUED")).update(status="VALIDATED")


class Migration(migrations.Migration):
    dependencies = [
        ("tickets", "0006_ticket_driver_name_snapshot"),
    ]

    operations = [
        migrations.RunPython(normalize_ticket_statuses, migrations.RunPython.noop),
        migrations.AlterField(
            model_name="ticket",
            name="status",
            field=models.CharField(
                choices=[
                    ("PENDING_SYNC", "En attente de synchronisation"),
                    ("VALIDATED", "Valide"),
                    ("PAID", "Paye"),
                    ("CANCELLED", "Annule"),
                ],
                default="VALIDATED",
                max_length=20,
            ),
        ),
    ]
