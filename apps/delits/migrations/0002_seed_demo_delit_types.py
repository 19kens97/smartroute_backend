from django.db import migrations


DELIT_TYPES = [
    (
        "DEMO_DANGEROUS_DRIVING",
        "Conduite dangereuse demo",
        "Manoeuvre dangereuse constatee pendant un controle.",
        "Code routier demo",
        10,
    ),
    (
        "DEMO_HIT_AND_RUN",
        "Fuite apres accident demo",
        "Depart du conducteur apres un accident ou dommage constate.",
        "Code routier demo",
        20,
    ),
    (
        "DEMO_DOCUMENT_FRAUD",
        "Fraude documentaire demo",
        "Document falsifie, incoherent ou presente comme authentique.",
        "Code penal demo",
        30,
    ),
    (
        "DEMO_REFUSED_ORDER",
        "Refus d'obtemperer demo",
        "Refus d'executer une injonction reguliere d'un agent.",
        "Code routier demo",
        40,
    ),
    (
        "DEMO_RECKLESS_ENDANGERMENT",
        "Mise en danger demo",
        "Comportement exposant les usagers a un risque grave.",
        "Code penal demo",
        50,
    ),
]


def seed_delit_types(apps, schema_editor):
    DelitType = apps.get_model("delits", "DelitType")
    for code, label, description, legal_basis, display_order in DELIT_TYPES:
        DelitType.objects.update_or_create(
            code=code,
            defaults={
                "label": label,
                "description": description,
                "legal_basis": legal_basis,
                "active": True,
                "display_order": display_order,
            },
        )


def unseed_delit_types(apps, schema_editor):
    DelitType = apps.get_model("delits", "DelitType")
    DelitType.objects.filter(code__in=[item[0] for item in DELIT_TYPES]).delete()


class Migration(migrations.Migration):
    dependencies = [
        ("delits", "0001_initial"),
    ]

    operations = [
        migrations.RunPython(seed_delit_types, unseed_delit_types),
    ]
