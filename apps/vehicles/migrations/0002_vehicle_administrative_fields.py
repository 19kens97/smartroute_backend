import apps.vehicles.models
import django.core.validators
import django.db.models.deletion
from django.db import migrations, models


def normalize_existing_vehicles(apps, schema_editor):
    Vehicle = apps.get_model("vehicles", "Vehicle")
    normalized_by_id = {
        vehicle.pk: "".join((vehicle.plate_number or "").split()).upper()
        for vehicle in Vehicle.objects.only("id", "plate_number")
    }
    ids_by_plate = {}
    for vehicle_id, plate in normalized_by_id.items():
        ids_by_plate.setdefault(plate, []).append(vehicle_id)
    duplicates = {plate: ids for plate, ids in ids_by_plate.items() if len(ids) > 1}
    if duplicates:
        details = ", ".join(f"{plate or '<vide>'}: {ids}" for plate, ids in duplicates.items())
        raise RuntimeError(
            "La normalisation des plaques detecte des doublons. Corrigez-les manuellement "
            "sans supprimer de donnees, puis relancez la migration: " + details
        )
    for vehicle_id, plate in normalized_by_id.items():
        Vehicle.objects.filter(pk=vehicle_id).update(plate_number=plate)


class Migration(migrations.Migration):
    dependencies = [("vehicles", "0001_initial")]
    operations = [
        migrations.AddField(
            model_name="vehicle",
            name="year",
            field=models.IntegerField(blank=True, null=True, validators=[django.core.validators.MinValueValidator(1900), apps.vehicles.models.validate_vehicle_year]),
        ),
        migrations.AddField(
            model_name="vehicle",
            name="engine_number",
            field=models.CharField(blank=True, max_length=100, null=True),
        ),
        migrations.AlterField(
            model_name="vehicle",
            name="owner",
            field=models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name="vehicles", to="owners.owner"),
        ),
        migrations.RunPython(normalize_existing_vehicles, migrations.RunPython.noop),
    ]
