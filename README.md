# SmartRoute Backend

Backend Django REST Framework de SmartRoute. Il expose les APIs utilisees par l'application mobile: authentification JWT, profils agents, vehicules, documents, permis, assurances, scans Gemini, PV, alertes, statistiques, rapports et synchronisation.

## Installation

```bash
cd smartroute_backend
python -m venv venv
venv\Scripts\activate
pip install -r requirements.txt
copy .env.example .env
python manage.py migrate
python manage.py seed_demo
python manage.py runserver 0.0.0.0:8000
```

## Configuration

Variables principales, sans secrets reels:

| Variable | Obligatoire | Role | Exemple |
|---|---:|---|---|
| `SECRET_KEY` | Oui | Secret Django | `change-me-with-at-least-32-characters` |
| `DEBUG` | Non | Mode debug | `True` |
| `ALLOWED_HOSTS` | Oui | Hosts autorises | `127.0.0.1,localhost,192.168.0.10` |
| `CORS_ALLOWED_ORIGINS` | Non | Origines mobile/web | `http://localhost:8081` |
| `USE_REDIS` | Non | Active Redis cache + channel layer | `False` |
| `REDIS_URL` | Si Redis | URL Redis cache/WebSocket | `redis://127.0.0.1:6379/1` |
| `CACHE_KEY_PREFIX` | Non | Prefixe des cles cache | `smartroute` |
| `CACHE_TIMEOUT_SECONDS` | Non | TTL cache par defaut | `300` |
| `USE_CELERY` | Non | Active apps Celery | `False` |
| `CELERY_BROKER_URL` | Si Celery | Broker | `redis://127.0.0.1:6379/2` |
| `CELERY_RESULT_BACKEND` | Si Celery | Result backend | `redis://127.0.0.1:6379/3` |
| `GEMINI_API_KEY` | Pour OCR | Cle Google GenAI | vide dans l'exemple |
| `GEMINI_MODEL` | Non | Modele OCR principal | `gemini-2.5-flash` |
| `GEMINI_FALLBACK_MODELS` | Non | Modeles fallback | `gemini-2.0-flash` |

## Modules Et APIs

### Authentification

- `POST /api/auth/token/`: login JWT, corps `username`, `password`, reponse enveloppee `data.access`, `data.refresh`.
- `POST /api/auth/token/refresh/`: refresh JWT.
- `POST /api/auth/token/blacklist/`: deconnexion par blacklist du refresh token.
- `GET/PATCH /api/auth/me/`: profil agent authentifie.
- `POST /api/auth/change-password/`: changement de mot de passe avec validateurs Django.
- `GET/PUT/DELETE /api/auth/profile/signature/`: statut, upload et suppression de signature agent.

### Vehicules Et Documents

- `/api/owners/`, `/api/vehicles/`, `/api/documents/` utilisent des ViewSets DRF.
- Recherche mobile principale: `GET /api/vehicles/by-plate/<plate>/`.
- Les reponses standard passent par l'enveloppe `success`, `message`, `data`, `errors`.

### Conducteurs, Assurance, Immatriculation

- `GET /api/drivers/search-by-dossier/?dossier_number=...`.
- `GET /api/drivers/search-by-nif/?nif=...`.
- `GET /api/insurance/?policy_number=...` et `GET /api/insurance/?plate_number=...`.

### Scan Gemini

Endpoint reel unique utilise par le mobile:

```http
POST /api/scans/scan-plate/
Authorization: Bearer <access-token>
Content-Type: multipart/form-data
```

| Champ | Type | Obligatoire | Description |
|---|---|---:|---|
| `image` | fichier | Oui | Photo contenant la plaque |

Flux: image multipart -> `apps.gemini.views.extract_license_plate` -> logique Gemini existante -> normalisation -> recherche vehicule -> enregistrement `apps.scans.models.GeminiScan` -> reponse directe.

Reponse succes directe, non enveloppee:

```json
{
  "status": "success",
  "raw_response": "AA12345",
  "plate_number": "AA-12345",
  "plate_detected": true,
  "model_used": "gemini-2.5-flash",
  "vehicle": null,
  "documents": {"vehicule": null, "proprietaire": null, "assurance": null, "immatriculation": null},
  "scanned_at": "2026-06-26 10:30:00"
}
```

Erreurs: image absente `400`, image invalide `400`, plaque inexploitable `422`, quota Gemini `429`, Gemini indisponible `503`, auth/config Gemini `502`, erreur interne `500`. La cle Gemini n'est jamais retournee ni loggee.

Autres routes scan: `GET /api/scans/search/?plate_number=...`, `GET /api/scans/last-scan/`, `GET /api/scans/` historique DRF, `POST /api/scans/recognize/` desactive sauf `ENABLE_RECOGNIZE_ENDPOINT=True`.

### PV Et Infractions

- `/api/infractions/`: referentiel d'infractions.
- `/api/tickets/`: creation, modification, filtre `status`, `agent_id`, `client_uuid`.
- `POST /api/tickets/{id}/proofs/`: preuve de PV.
- La creation/modification de PV invalide le cache statistiques apres commit.

### Alertes

- `/api/alerts/`: creation, liste, detail, mise a jour.
- Actions: `recent-unread`, `mark-opened`, endpoint de preuve prive par alerte.
- WebSocket: `ws/alerts/` via Channels, Redis si `USE_REDIS=True`.
- Les preuves audio/video sont stockees dans `private/alert-evidence` et servies seulement via endpoints authentifies.

### Statistiques Et Cache

- `GET /api/dashboard/summary/?days=7`, `days` borne entre 1 et 31.
- Cache key: `smartroute:statistics:dashboard:days:<days>:v1`.
- TTL applicatif: 120 secondes pour le dashboard.
- Invalidation centrale: `apps.core.cache.invalidate_statistics_cache()` apres scan, PV et synchronisation via `transaction.on_commit()`.
- Si Redis/cache est indisponible, la vue recalcule depuis la base et logge l'incident sans retourner `500` pour le cache seul.

### Synchronisation Et Rapports

- `POST /api/sync/push/`, `POST /api/sync/pull/`, `GET /api/sync/status/?client_uuid=...`.
- `GET /api/reports/tickets/` pour les rapports PV.

## Tests

```bash
python manage.py check
python manage.py test
python manage.py test apps.core.tests_cache apps.dashboard.tests apps.gemini.tests apps.scans.tests
```

Les tests Gemini mockent uniquement l'appel externe. Les tests Redis/cache utilisent `LocMemCache`, pas un Redis externe.

## Documentation API

- Swagger: `/api/docs/`
- Schema OpenAPI: `/api/schema/`

## Notes De Securite

- `.env` est ignore par Git.
- `.env.example` ne contient aucune cle reelle.
- `GEMINI_API_KEY` reste backend uniquement.
- Les logs masquent plaques, NIF, telephone et reponses sensibles selon le middleware existant.
