# SmartRoute Backend

## Installation locale
```bash
python -m venv venv
venv\Scripts\activate
pip install -r requirements.txt
copy .env.example .env
python manage.py makemigrations
python manage.py migrate
python manage.py seed_demo
python manage.py runserver
```

## Endpoints utiles
- Swagger: `/api/docs/`
- Schema: `/api/schema/`
- JWT token: `/api/auth/token/`
- JWT refresh: `/api/auth/token/refresh/`
- JWT blacklist: `/api/auth/token/blacklist/`

## Notes techniques
- Nom officiel: **SmartRoute**
- Backend: Django + DRF
- Dev local: sans Docker
- Dev DB: SQLite
- Prod DB: PostgreSQL
- Redis/Celery: optionnels

## Gemini (OCR) integration

The project supports an optional Gemini-based OCR endpoint for license plate recognition.

Environment variables (add to your `.env`):

- `GEMINI_API_KEY` - API key for Google GenAI / Gemini.
- `GEMINI_MODEL` - Primary Gemini model (default: `gemini-2.5-flash`).
- `GEMINI_FALLBACK_MODELS` - Comma separated fallback models.
- `GEMINI_LOG_RESPONSE` - `True` or `False` to log parsed text responses.
- `GEMINI_LOG_RAW_RESPONSE` - `True` or `False` to log raw response objects.
- `ENABLE_RECOGNIZE_ENDPOINT` - `True` to enable the legacy `/api/scans/recognize/` demo endpoint.

API endpoints added:

- `POST /api/gemini/scan-plate/` - multipart form with `image` file. Returns parsed `plate_number`, `plate_detected`, `vehicle`, `documents` and `scanned_at`.

Running tests for scans:

```bash
# from project root
python -m venv venv
venv\Scripts\activate
pip install -r requirements.txt
python manage.py test apps.scans
```

Note: tests mock the Gemini client; to run end-to-end you must set `GEMINI_API_KEY` and have network access.
