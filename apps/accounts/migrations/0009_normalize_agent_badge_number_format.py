from django.db import migrations


def format_badge(value):
    digits = "".join(char for char in str(value or "") if char.isdigit())
    if len(digits) != 11:
        return None
    return f"{digits[:2]}-{digits[2:4]}-{digits[4:6]}-{digits[6:]}"


def fallback_badge(profile_id):
    digits = f"98{profile_id % 1000000000:09d}"
    return f"{digits[:2]}-{digits[2:4]}-{digits[4:6]}-{digits[6:]}"


def normalize_agent_badges(apps, schema_editor):
    AgentProfile = apps.get_model("accounts", "AgentProfile")
    seen = set()
    for profile in AgentProfile.objects.all().only("id", "badge_number").order_by("id"):
        normalized = format_badge(profile.badge_number) or fallback_badge(profile.id)
        while normalized in seen:
            normalized = fallback_badge(profile.id + len(seen) + 1)
        seen.add(normalized)
        if profile.badge_number != normalized:
            profile.badge_number = normalized
            profile.save(update_fields=["badge_number"])


class Migration(migrations.Migration):

    dependencies = [
        ("accounts", "0008_normalize_person_nif_format"),
    ]

    operations = [
        migrations.RunPython(normalize_agent_badges, migrations.RunPython.noop),
    ]
