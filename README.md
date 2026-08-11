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


## Configuration Production

Pour un deploiement production, definissez explicitement `DJANGO_SETTINGS_MODULE=config.settings.prod`. Les valeurs de developpement ne doivent pas etre reutilisees telles quelles. Le module production refuse de demarrer si `SECRET_KEY` est vide ou placeholder, si `DEBUG=True`, si `ALLOWED_HOSTS` contient `*`, si `CORS_ALLOW_ALL_ORIGINS=True`, ou si `API_RESPONSE_LOGGING_INCLUDE_BODY=True`.

Exemple minimal :

```env
DJANGO_SETTINGS_MODULE=config.settings.prod
DEBUG=False
SECRET_KEY=<secret-long-aleatoire-fourni-par-le-coffre>
ALLOWED_HOSTS=api.smartroute.example
CORS_ALLOW_ALL_ORIGINS=False
CORS_ALLOWED_ORIGINS=https://admin.smartroute.example
API_RESPONSE_LOGGING_INCLUDE_BODY=False
```

`config.settings.prod` active aussi HTTPS redirect, HSTS, cookies secure, `SECURE_CONTENT_TYPE_NOSNIFF`, `SECURE_REFERRER_POLICY=same-origin` et `X_FRAME_OPTIONS=DENY`. Le reverse proxy doit donc terminer HTTPS correctement et transmettre `X-Forwarded-Proto: https`.

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


## Validation locale Windows

Depuis le dossier `smartroute_backend`, utilisez toujours le venv local pour les commandes Django afin d'eviter d'utiliser le Python global :

```powershell
.\venv\Scripts\activate
python manage.py check
python manage.py test
```

Alternative sans activation :

```powershell
.\venv\Scripts\python.exe manage.py check
.\venv\Scripts\python.exe manage.py test
```

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

### Catalogue Des Infractions

Le backend est la source officielle du referentiel des infractions. Le catalogue DCPR versionne dans `apps/infractions/catalog.py` est charge en base avec:

```bash
python manage.py seed_infractions
```

La commande est idempotente: elle cree les codes manquants, met a jour les champs officiels, conserve les infractions historiques et ne supprime pas physiquement les lignes deja liees a des PV. Les codes metier stables sont `I001` a `I074`; l'ID SQL reste interne et ne doit pas etre utilise comme numero visible.

`GET /api/infractions/` retourne uniquement les infractions actives, sans pagination pour ce referentiel court, dans `data.items` avec `id`, `code`, `number`, `label`, `article`, `category`, `amount`, `penalty_text`, `active`, `display_order`, `updated_at`, et `data.version` basee sur le dernier `updated_at`.

Le catalogue actif est mis en cache cote backend avec la cle Redis/cache `smartroute:infractions:active:v1` pendant 3600 secondes. L'invalidation est centralisee via `invalidate_infraction_catalog_cache()` apres import, creation, modification ou desactivation.

La creation de PV utilise les codes metier:

```json
{
  "driver_license": "D-123",
  "plate_number_snapshot": "AA12345",
  "infraction_codes": ["I001", "I005"]
}
```

Le serializer valide que chaque code existe, est actif, unique dans la requete et normalise en majuscules avant de creer les relations `TicketInfraction`.

## Stockage media centralise

SmartRoute ne stocke pas les fichiers binaires dans la base de donnees. Les modeles conservent uniquement les metadonnees utiles (chemin Django storage, type MIME, taille, checksum SHA-256, duree lorsque disponible et createur lorsque pertinent).

Le module `apps.media_storage.services` centralise les chemins, la validation MIME/extension/taille et le calcul de checksum. Les chemins generes n'utilisent pas le nom original fourni par le client et suivent les conventions suivantes :

- preuves PV : `tickets/{ticket_number}/photos|videos|audio/{uuid}.{ext}`
- preuves d'alerte : `alerts/{alert_id}/audio|videos/{uuid}.{ext}`
- signatures agents : `signatures/agents/{agent_id}/{uuid}.png`
- documents vehicule : `documents/vehicles/{vehicle_id}/{uuid}.{ext}`

Configuration principale : `MEDIA_STORAGE_BACKEND`, `MEDIA_ROOT`, `MEDIA_URL`, `MEDIA_BASE_URL`, `PRIVATE_MEDIA_ENABLED`, `PRIVATE_SIGNATURE_ROOT`, `PRIVATE_ALERT_EVIDENCE_ROOT`, `PRIVATE_TICKET_PROOF_ROOT`, `PRIVATE_DELIT_EVIDENCE_ROOT`, `MAX_IMAGE_SIZE_MB`, `MAX_VIDEO_SIZE_MB`, `MAX_AUDIO_SIZE_MB`, `MAX_DOCUMENT_SIZE_MB`. En developpement, `config.urls` sert `MEDIA_URL` lorsque `DEBUG=True`; les medias sensibles utilisent de preference des endpoints authentifies.

Les endpoints multipart existants restent les points d'entree :

- `POST /api/tickets/{id}/proofs/` avec `file`, `evidence_type`, `duration_seconds` optionnel. La reponse expose `url` vers `/api/tickets/{ticket_id}/proofs/{proof_id}/download/`, pas une URL directe de fichier.
- `POST /api/alerts/` avec `evidence_file`, `evidence_type`, `evidence_duration_seconds` optionnel. La lecture passe par `/api/alerts/{alert_id}/evidence/{evidence_id}/`.
- `PUT /api/auth/profile/signature/` accepte soit un fichier `signature`, soit le payload de traits actuel; le backend rend et stocke une image PNG privee.
- `POST /api/scans/scan-plate/` valide l'image en entree mais ne la persiste pas.

Les logs media utilisent notamment `media_upload_started`, `media_validation_failed`, `media_saved`, `media_downloaded`, `media_access_denied` et `media_deleted`, sans journaliser de contenu binaire ni de donnees sensibles.


## Documentation Technique Complementaire

- `docs/websocket-alerts.md`
- `docs/offline-sync.md`
- `docs/roles-permissions.md`
- `docs/reports.md`
- `docs/private-media.md`

## Tests Complementaires

Commandes generales :

```bash
python manage.py check
python manage.py test
```

Commandes ciblees utiles pour les zones sensibles :

```bash
python manage.py test apps.alerts.tests_filters_websocket
python manage.py test apps.sync.tests_handlers
python manage.py test apps.reports.tests_services_additional
python manage.py test apps.accounts.tests_permissions_services
python manage.py test apps.tickets.tests_services_additional
python manage.py test apps.drivers.tests_services
```

Les tests Gemini mockent uniquement l'appel externe. Les tests Redis/cache et Channels utilisent des backends locaux (`LocMemCache` et channel layer memoire), pas un Redis externe. Si `coverage` est disponible dans l'environnement local, utilisez `coverage run manage.py test` puis `coverage report`.

### Authentification mobile et backoffice

L'application mobile utilise exclusivement les endpoints dedies suivants:

- `POST /api/auth/mobile/login/`: accepte `email` ou `username` + `password`, et n'emet des tokens JWT que pour un compte `PROFESSIONAL` actif ayant un `AgentProfile` actif avec le role `AGENT_TERRAIN`.
- `POST /api/auth/mobile/token/refresh/`: renouvelle le token mobile uniquement si le compte et le profil sont encore actifs et si le role courant reste `AGENT_TERRAIN`.

Les comptes `AGENT_SAISIE`, `ADMIN`, `PERSONAL` et les comptes professionnels sans profil agent actif sont refuses sur mobile. Ils doivent etre orientes vers la future plateforme web/backoffice, afin de ne pas leur exposer les fonctions de scan terrain.

Les endpoints historiques `POST /api/auth/auth/professional/login/`, `POST /api/auth/auth/personal/login/` et `POST /api/auth/auth/token/refresh/` sont conserves pour compatibilite et pour les usages web/backoffice. Les endpoints sensibles de scan sous `/api/scans/` exigent aussi la permission `IsAgentTerrain` cote backend.

## Documentation complete

- [Index backend](docs/README.md)
- [Architecture](docs/architecture.md)
- [Installation developpement](docs/installation-development.md)
- [Deploiement production](docs/deployment-production.md)
- [Authentification](docs/authentication.md)
- [Vue d'ensemble API](docs/api-overview.md)
- [Roles et permissions](docs/roles-permissions.md)
- [Regles metier](docs/business-data-rules.md)
- [Guide de tests](docs/testing-guide.md)
- [Depannage](docs/troubleshooting.md)
- [Limites connues](docs/known-limitations.md)

### Recuperation de mot de passe

- `POST /api/auth/forgot-password/`: demande publique de reinitialisation. Corps: `{ "email": "agent@example.com" }`. La reponse est toujours generique pour eviter l'enumeration de comptes. Un email est envoye uniquement si un compte `PROFESSIONAL` actif correspond a l'adresse.
- `POST /api/auth/reset-password/`: confirmation de reinitialisation. Corps: `{ "uid": "...", "token": "...", "new_password": "...", "confirm_password": "..." }`. Le backend valide le token Django, applique `validate_password`, utilise `set_password` et revoque les refresh tokens existants.

Configuration associee:

- `EMAIL_BACKEND`, `EMAIL_HOST`, `EMAIL_PORT`, `EMAIL_HOST_USER`, `EMAIL_HOST_PASSWORD`, `EMAIL_USE_TLS`, `EMAIL_USE_SSL`, `DEFAULT_FROM_EMAIL`
- `PASSWORD_RESET_MOBILE_URL`, par defaut `smartroutemobile://reset-password`
- `PASSWORD_RESET_TIMEOUT`, par defaut `3600` secondes

En developpement, `django.core.mail.backends.console.EmailBackend` permet de lire le lien de reset dans la console sans fournisseur SMTP reel.
## Security Operations

Production must run with `DJANGO_SETTINGS_MODULE=config.settings.prod`, `DEBUG=False`, a strong external `SECRET_KEY`, explicit `ALLOWED_HOSTS`, `CORS_ALLOW_ALL_ORIGINS=False`, explicit `CORS_ALLOWED_ORIGINS`, HTTPS security settings enabled, and PostgreSQL as the default database engine. Run `python manage.py check --deploy --settings=config.settings.prod` with non-secret test values in CI before deployment.

Do not transfer `.env`, `db.sqlite3`, `media/`, `private/`, `logs/`, or `backups/` by email or include them in source archives. Backups must be encrypted, access-controlled, and rotated. Private media roots should stay outside public static/media serving paths.

Uploads support a configurable antivirus layer. Local development may use `ANTIVIRUS_SCANNER=disabled` with `ANTIVIRUS_REQUIRED=False`, or run ClamAV locally with `docker compose -f docker-compose.clamav.yml up -d` and `ANTIVIRUS_SCANNER=clamav_tcp`. Production must set `ANTIVIRUS_SCANNER=clamav_tcp`, `ANTIVIRUS_REQUIRED=True`, and a private clamd host; if required scanning is unavailable, uploads fail closed. See `docs/security/clamav.md`.

Recommended security checks: `python manage.py check`, `python manage.py test`, `python manage.py check --deploy --settings=config.settings.prod`, and `pip-audit` when available.
