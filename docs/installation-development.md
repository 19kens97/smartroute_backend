# Installation Et Developpement Backend

## Prerequis

- Python compatible avec le projet local.
- Acces au dossier `smartroute_backend`.
- Dependances listées dans `requirements.txt`.
- Cle Gemini uniquement si le scan OCR reel doit etre teste.
- Redis facultatif en developpement.

## Installation

```bash
cd smartroute_backend
python -m venv venv
venv\Scripts\activate
pip install -r requirements.txt
copy .env.example .env
python manage.py migrate
python manage.py runserver 0.0.0.0:8000
```

## Variables D'Environnement

Copier `.env.example` vers `.env`, puis adapter au poste local. Ne jamais committer `.env`.

Variables principales: `SECRET_KEY`, `DEBUG`, `ALLOWED_HOSTS`, `CORS_ALLOWED_ORIGINS`, `USE_REDIS`, `REDIS_URL`, `GEMINI_API_KEY`, `GEMINI_MODEL`, `ENABLE_RECOGNIZE_ENDPOINT`.

## Donnees De Demonstration

```bash
python manage.py seed_demo
```

Cette commande cree des comptes et donnees de demonstration. Ces donnees sont locales/dev uniquement.

## Superutilisateur

```bash
python manage.py createsuperuser
```

A confirmer selon la procedure d'administration retenue.

## Verification

```bash
python manage.py check
python manage.py test
```

Swagger: `/api/docs/`. Schema OpenAPI: `/api/schema/`.

## Redis En Developpement

Laisser `USE_REDIS=False` pour un developpement isole. Activer Redis seulement pour tester cache/Channels multi-processus.