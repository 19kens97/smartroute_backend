from django.utils import timezone


def _person_name(person):
    if not person:
        return ""
    return f"{person.first_name} {person.last_name}".strip()


def _evidence_payload(case, request=None):
    items = []
    for evidence in case.evidence.all():
        url = ""
        if evidence.file:
            path = f"/api/delits/{case.pk}/evidence/{evidence.pk}/download/"
            url = request.build_absolute_uri(path) if request else path
        items.append({
            "type": evidence.evidence_type,
            "nom_fichier": evidence.file.name.rsplit("/", 1)[-1] if evidence.file else "",
            "mime_type": evidence.mime_type,
            "duree_secondes": evidence.duration_seconds,
            "url": url,
        })
    return items


def build_dcpj_payload(case, request=None):
    detected_at = timezone.localtime(case.detected_at)
    agent_profile = getattr(case.detected_by, "agent_profile", None)
    agent_person = getattr(case.detected_by, "person", None)
    driver_person = getattr(case.driver, "person", None)
    infraction = case.infraction
    vehicle = case.vehicle

    return {
        "reference_smartroute": case.case_number,
        "date": detected_at.date().isoformat(),
        "heure": detected_at.strftime("%H:%M"),
        "lieu": case.location_label,
        "latitude": str(case.latitude) if case.latitude is not None else None,
        "longitude": str(case.longitude) if case.longitude is not None else None,
        "agent": {
            "nom": _person_name(agent_person) or getattr(case.detected_by, "email", ""),
            "matricule": getattr(agent_profile, "badge_number", "") or "",
        },
        "delit": {
            "type": case.delit_type.label,
            "code": case.delit_type.code,
            "article": getattr(infraction, "article", "") if infraction else "",
            "infraction": getattr(infraction, "label", "") if infraction else "",
            "observation": case.facts,
        },
        "conducteur": {
            "nom": _person_name(driver_person),
            "numero_dossier_permis": getattr(case.driver, "dossier_number", "") if case.driver else "",
        },
        "vehicule": {
            "immatriculation": case.plate_number_snapshot or getattr(vehicle, "plate_number", ""),
        },
        "preuves": _evidence_payload(case, request=request),
    }


def send_case_to_dcpj_demo(case, *, actor, request=None):
    payload = build_dcpj_payload(case, request=request)
    sent_at = timezone.now()
    reference = f"DCPJ-DEMO-{sent_at.year}-{case.pk:06d}"
    response = {
        "status": "ACKNOWLEDGED",
        "reference": reference,
        "message": "Transmission demo recue par la DCPJ.",
        "received_at": sent_at.isoformat(),
    }

    case.dcpj_status = case.DCPJStatus.ACKNOWLEDGED
    case.dcpj_reference = reference
    case.dcpj_sent_at = sent_at
    case.dcpj_last_error = ""
    case.dcpj_payload_snapshot = payload
    case.dcpj_response_snapshot = response
    case.save(update_fields=[
        "dcpj_status",
        "dcpj_reference",
        "dcpj_sent_at",
        "dcpj_last_error",
        "dcpj_payload_snapshot",
        "dcpj_response_snapshot",
        "updated_at",
    ])
    return response