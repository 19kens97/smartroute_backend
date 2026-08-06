# Deploiement Production Backend

## Statut

Le backend contient un module `config.settings.prod` avec garde-fous de production. L'infrastructure finale de production reste a confirmer.

## Variables Critiques

- `DJANGO_SETTINGS_MODULE=config.settings.prod`
- `DEBUG=False`
- `SECRET_KEY` non placeholder
- `ALLOWED_HOSTS` explicite, sans wildcard
- `CORS_ALLOW_ALL_ORIGINS=False`
- `CORS_ALLOWED_ORIGINS` limite aux origines autorisees
- `API_RESPONSE_LOGGING_INCLUDE_BODY=False`
- `GEMINI_API_KEY` si OCR actif

## Securite Activee

Le module production active les protections Django attendues: redirection HTTPS, HSTS, cookies securises, `SECURE_CONTENT_TYPE_NOSNIFF`, `SECURE_REFERRER_POLICY=same-origin`, `X_FRAME_OPTIONS=DENY`.

## Base De Donnees

Le code de base configure SQLite par defaut. Une base production externe doit etre configuree et validee avant livraison. A confirmer.

## Fichiers Statiques Et Medias

- Executer `python manage.py collectstatic` si le mode de deploiement sert les fichiers statiques.
- Configurer les racines de medias prives: signatures, alertes, preuves PV, documents, scans, delits.
- Verifier sauvegarde et restauration des medias.

## Redis Et Workers

Redis est recommande pour cache et Channels en production multi-processus. Celery est optionnel via `USE_CELERY`; les workers ne doivent etre declares operationnels qu'apres validation d'infrastructure.

## Commandes De Validation

```bash
python manage.py check
python manage.py test
python manage.py migrate --check
```

## Limites Actuelles

- Provider de base production: a confirmer.
- Strategie de sauvegarde: a confirmer.
- Observabilite et monitoring: a confirmer.