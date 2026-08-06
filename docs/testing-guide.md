# Guide Des Tests Backend

## Commandes

```bash
python manage.py check
python manage.py test
python manage.py test apps.accounts
python manage.py test apps.alerts
python manage.py test apps.sync
```

## Settings De Test

`config.settings.test` desactive le debug, utilise `MD5PasswordHasher`, un cache memoire et un logging minimal.

## Organisation

- `tests.py`: tests principaux du module.
- `tests_*.py`: tests complementaires specialises.
- `test_factories.py`: helpers exclusivement reserves aux tests.

## Types De Tests

La suite couvre unitaires, serializers, API DRF, permissions, services, cache, configuration, seed demo, WebSocket Channels, synchronisation et medias.

## Fixtures

- NIF valide: 10 chiffres, par exemple `0000000001`.
- Badge valide: 11 chiffres, rendu `XX-XX-XX-XXXXX`.
- Dossier permis valide: `AB-12345-CD`.
- Ne pas utiliser `AGT-100` ou `OWNER-001` dans des champs stricts sauf test negatif explicite.

## Utilisateurs De Test

Utiliser la factory commune `apps.accounts.test_factories` quand possible. Elle genere NIF et badges conformes.

## Services Externes

Gemini est mocke aux frontieres externes. Les tests ne doivent pas dependre d'Internet.

## Channels

Les tests WebSocket utilisent un channel layer memoire.

## Barcode

Le endpoint barcode retourne un SVG si `reportlab` est disponible. Sinon le contrat backend est un `503` explicite.

## Procedure Lors D'Un Changement De Modele

1. Lire le modele et le serializer.
2. Mettre a jour les factories valides.
3. Conserver les tests negatifs invalides.
4. Relancer le module cible.
5. Relancer la suite complete.

## Bonnes Pratiques

Chaque test doit avoir une assertion precise, etre independant, utiliser la base de test et mocker uniquement les frontieres externes.