from django.db import migrations, models

import apps.alerts.taxonomy


LEGACY_FIELD_TYPE_SPECIFICATIONS = {
    "FIELD_ESCAPE": "ACTIVE_CHECKPOINT",
    "REFUSED_CONTROL": "DOCUMENT_CONTROL",
    "SUSPICIOUS_BEHAVIOR": "IMMEDIATE_RISK_AREA",
    "KIDNAPPING": "KIDNAPPING",
}


def migrate_legacy_kidnapping(apps, schema_editor):
    Alert = apps.get_model("alerts", "Alert")
    Alert.objects.filter(alert_type="KIDNAPPING").update(
        alert_type="SPECIAL_EVENT",
        specification="KIDNAPPING",
    )
    for legacy_type, specification in LEGACY_FIELD_TYPE_SPECIFICATIONS.items():
        if legacy_type == "KIDNAPPING":
            continue
        Alert.objects.filter(alert_type=legacy_type, specification="").update(
            alert_type="ROAD_CONTROL" if legacy_type in {"FIELD_ESCAPE", "REFUSED_CONTROL"} else "DANGEROUS_CONDITION",
            specification=specification,
        )


class Migration(migrations.Migration):

    dependencies = [
        ("alerts", "0008_alter_alert_alert_type_alter_alert_source_and_more"),
    ]

    operations = [
        migrations.AddField(
            model_name="alert",
            name="specification",
            field=models.CharField(
                blank=True,
                choices=apps.alerts.taxonomy.alert_specification_choices,
                db_index=True,
                default="",
                max_length=60,
            ),
        ),
        migrations.RunPython(migrate_legacy_kidnapping, migrations.RunPython.noop),
        migrations.AlterField(
            model_name="alert",
            name="alert_type",
            field=models.CharField(
                choices=[
                    ("TRAFFIC_ACCIDENT", "Accident de circulation"),
                    ("TRAFFIC", "Route / circulation"),
                    ("ROAD_OBSTACLE", "Obstacle sur la chaussee"),
                    ("ROAD_CONDITION", "Etat de la route"),
                    ("DANGEROUS_CONDITION", "Conditions dangereuses"),
                    ("ROAD_CONTROL", "Controle routier / operation"),
                    ("REINFORCEMENT", "Situation necessitant du renfort"),
                    ("SPECIAL_EVENT", "Evenement particulier"),
                    ("WANTED_VEHICLE", "Vehicule vole ou recherche"),
                    ("STOLEN_PLATE", "Plaque volee"),
                    ("JUDICIAL_ALERT", "Alerte judiciaire"),
                    ("DOCUMENT_EXPIRY_WARNING", "Document proche de l'expiration"),
                ],
                db_index=True,
                max_length=40,
            ),
        ),
    ]
