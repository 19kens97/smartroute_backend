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
