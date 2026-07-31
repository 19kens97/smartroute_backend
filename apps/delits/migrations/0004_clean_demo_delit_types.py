from django.db import migrations


DELIT_TYPE_RENAMES = [
    ("DEMO_DANGEROUS_DRIVING", "DANGEROUS_DRIVING", "Conduite dangereuse", "Manoeuvre dangereuse constatee pendant un controle.", "Code routier", 10),
    ("DEMO_HIT_AND_RUN", "HIT_AND_RUN", "Fuite apres accident", "Depart du conducteur apres un accident ou dommage constate.", "Code routier", 20),
    ("DEMO_DOCUMENT_FRAUD", "DOCUMENT_FRAUD", "Fraude documentaire", "Document falsifie, incoherent ou presente comme authentique.", "Code penal :", 30),
    ("DEMO_REFUSED_ORDER", "REFUSED_ORDER", "Refus d'obtemperer", "Refus d'executer une injonction reguliere d'un agent.", "Code routier", 40),
    ("DEMO_RECKLESS_ENDANGERMENT", "RECKLESS_ENDANGERMENT", "Mise en danger", "Comportement exposant les usagers a un risque grave.", "Code penal :", 50),
]


def clean_delit_types(apps, schema_editor):
    DelitType = apps.get_model("delits", "DelitType")
    for old_code, new_code, label, description, legal_basis, display_order in DELIT_TYPE_RENAMES:
        old_item = DelitType.objects.filter(code=old_code).first()
        new_item = DelitType.objects.filter(code=new_code).first()
        defaults = {
            "label": label,
            "description": description,
            "legal_basis": legal_basis,
            "active": True,
            "display_order": display_order,
        }
        if old_item and new_item and old_item.pk != new_item.pk:
            old_item.cases.update(delit_type=new_item)
            old_item.delete()
            DelitType.objects.filter(pk=new_item.pk).update(**defaults)
        elif old_item:
            DelitType.objects.filter(pk=old_item.pk).update(code=new_code, **defaults)
        else:
            DelitType.objects.update_or_create(code=new_code, defaults=defaults)


def restore_demo_codes(apps, schema_editor):
    DelitType = apps.get_model("delits", "DelitType")
    for old_code, new_code, label, description, legal_basis, display_order in DELIT_TYPE_RENAMES:
        DelitType.objects.filter(code=new_code).update(code=old_code)


class Migration(migrations.Migration):
    dependencies = [
        ("delits", "0003_delitcase_plate_number_snapshot"),
    ]

    operations = [
        migrations.RunPython(clean_delit_types, restore_demo_codes),
    ]