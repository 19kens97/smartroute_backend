from collections import OrderedDict


ALERT_TYPE_SPECIFICATIONS = OrderedDict(
    [
        ("TRAFFIC_ACCIDENT", {"label": "Accident de circulation", "specifications": OrderedDict([("LIGHT_ACCIDENT", "Accident leger"), ("INJURY_ACCIDENT", "Accident avec blesses"), ("SERIOUS_ACCIDENT", "Accident grave"), ("OVERTURNED_VEHICLE", "Vehicule renverse"), ("MULTIPLE_COLLISION", "Collision multiple")])}),
        ("TRAFFIC", {"label": "Route / circulation", "specifications": OrderedDict([("BLOCKED_ROAD", "Route bloquee"), ("PARTIALLY_BLOCKED_ROAD", "Route partiellement bloquee"), ("HEAVY_TRAFFIC", "Embouteillage important"), ("SLOW_TRAFFIC", "Circulation ralentie"), ("TEMPORARY_DETOUR", "Deviation temporaire"), ("CLOSED_ROAD", "Route fermee"), ("TEMPORARY_DIRECTION_CHANGE", "Sens de circulation temporairement modifie")])}),
        ("ROAD_OBSTACLE", {"label": "Obstacle sur la chaussee", "specifications": OrderedDict([("BROKEN_DOWN_VEHICLE", "Vehicule en panne"), ("ABANDONED_VEHICLE", "Vehicule abandonne"), ("FALLEN_TREE", "Arbre tombe"), ("ROAD_DEBRIS", "Debris sur la route"), ("FALLEN_ELECTRICAL_CABLE", "Cable electrique tombe"), ("FALLEN_GOODS", "Marchandises tombees d'un vehicule"), ("ANIMAL_ON_ROAD", "Animal sur la chaussee")])}),
        ("ROAD_CONDITION", {"label": "Etat de la route", "specifications": OrderedDict([("FLOODED_ROAD", "Route inondee"), ("LANDSLIDE", "Glissement de terrain"), ("ROAD_SUBSIDENCE", "Affaissement de chaussee"), ("DANGEROUS_POTHOLE", "Nid-de-poule dangereux"), ("DAMAGED_BRIDGE", "Pont endommage"), ("ROAD_WORKS", "Travaux routiers"), ("IMPASSABLE_ROAD", "Chaussee impraticable")])}),
        ("DANGEROUS_CONDITION", {"label": "Conditions dangereuses", "specifications": OrderedDict([("HEAVY_RAIN", "Forte pluie"), ("FOG_REDUCED_VISIBILITY", "Brouillard / visibilite reduite"), ("FIRE_NEAR_ROAD", "Incendie a proximite de la route"), ("HEAVY_SMOKE", "Fumee importante"), ("IMMEDIATE_RISK_AREA", "Zone a risque immediat"), ("OIL_OR_LIQUID_ON_ROAD", "Presence de liquide ou d'huile sur la chaussee")])}),
        ("ROAD_CONTROL", {"label": "Controle routier / operation", "specifications": OrderedDict([("ACTIVE_CHECKPOINT", "Point de controle actif"), ("REINFORCED_CONTROL", "Controle renforce"), ("SPECIAL_OPERATION", "Operation speciale en cours"), ("HEAVY_VEHICLE_CONTROL", "Controle poids lourds"), ("DOCUMENT_CONTROL", "Controle documents"), ("ALCOHOL_CONTROL", "Controle alcoolemie"), ("SPEED_CONTROL", "Controle de vitesse")])}),
        ("REINFORCEMENT", {"label": "Situation necessitant du renfort", "specifications": OrderedDict([("REINFORCEMENT_REQUESTED", "Renfort demande"), ("MEDICAL_ASSISTANCE_REQUESTED", "Assistance medicale demandee"), ("TOW_TRUCK_NEEDED", "Depanneuse necessaire"), ("ADDITIONAL_POLICE_NEEDED", "Police supplementaire necessaire"), ("FIREFIGHTERS_NEEDED", "Pompiers necessaires"), ("AMBULANCE_NEEDED", "Ambulance necessaire")])}),
        ("SPECIAL_EVENT", {"label": "Evenement particulier", "specifications": OrderedDict([("DEMONSTRATION", "Manifestation"), ("LARGE_GATHERING", "Rassemblement important"), ("PROCESSION", "Cortege"), ("PUBLIC_EVENT", "Evenement public"), ("MARKET_ON_ROAD", "Marche occupant la chaussee"), ("HIGH_TRAFFIC_ACTIVITY", "Activite provoquant une forte circulation"), ("KIDNAPPING", "Enlevement")])}),
    ]
)


def alert_type_choices():
    return [(code, item["label"]) for code, item in ALERT_TYPE_SPECIFICATIONS.items()]


def alert_specification_choices():
    return [(code, label) for item in ALERT_TYPE_SPECIFICATIONS.values() for code, label in item["specifications"].items()]


def is_alert_taxonomy_type(alert_type):
    return alert_type in ALERT_TYPE_SPECIFICATIONS


def is_valid_specification(alert_type, specification):
    return specification in ALERT_TYPE_SPECIFICATIONS.get(alert_type, {}).get("specifications", {})


def get_alert_specification_label(specification):
    for item in ALERT_TYPE_SPECIFICATIONS.values():
        label = item["specifications"].get(specification)
        if label:
            return label
    return specification or ""


def alert_options_payload():
    return {
        "types": [
            {
                "value": type_code,
                "label": item["label"],
                "specifications": [
                    {"value": specification_code, "label": specification_label}
                    for specification_code, specification_label in item["specifications"].items()
                ],
            }
            for type_code, item in ALERT_TYPE_SPECIFICATIONS.items()
        ]
    }
