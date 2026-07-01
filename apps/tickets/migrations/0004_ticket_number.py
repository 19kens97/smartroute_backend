# Generated manually for public ticket numbers.

import secrets

from django.db import migrations, models


def generate_number(existing):
    for _ in range(10):
        value = secrets.token_hex(4).upper()
        if value not in existing:
            existing.add(value)
            return value
    raise RuntimeError("Impossible de generer un numero de PV unique pendant la migration.")


def backfill_ticket_numbers(apps, schema_editor):
    Ticket = apps.get_model("tickets", "Ticket")
    existing = set(
        Ticket.objects.exclude(ticket_number="")
        .values_list("ticket_number", flat=True)
    )
    for ticket in Ticket.objects.order_by("id"):
        value = (ticket.ticket_number or "").strip().upper()
        if len(value) == 8 and all(char in "0123456789ABCDEF" for char in value) and value not in existing:
            ticket.ticket_number = value
            existing.add(value)
        else:
            ticket.ticket_number = generate_number(existing)
        ticket.save(update_fields=["ticket_number"])


class Migration(migrations.Migration):

    dependencies = [
        ("tickets", "0003_ticket_control_context"),
    ]

    operations = [
        migrations.RenameField(
            model_name="ticket",
            old_name="barcode_value",
            new_name="ticket_number",
        ),
        migrations.RunPython(backfill_ticket_numbers, migrations.RunPython.noop),
        migrations.AlterField(
            model_name="ticket",
            name="ticket_number",
            field=models.CharField(db_index=True, editable=False, max_length=8, unique=True),
        ),
    ]
