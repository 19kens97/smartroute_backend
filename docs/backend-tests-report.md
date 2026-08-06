# Backend Tests Report

Date de reference: 2026-08-04.
Version documentaire: 1.0.

## Etat final

- Commandes executees: `python manage.py check`, `python manage.py test`, plus des groupes cibles par application.
- Etat initial observe: 232 tests decouverts, 152 erreurs, 0 echecs visibles dans le resume final initial, suite non executable jusqu'au bout utilement a cause d'erreurs de fixtures.
- Etat final: 232 tests decouverts, 232 reussis, 0 erreur, 0 echec, 0 ignore, duree suite complete 13.951s.
- Avertissement restant: `RequestsDependencyWarning` sur la combinaison locale `urllib3` / `chardet` / `charset_normalizer`. Cela ne bloque pas les tests.

## Inventaire des tests

| Application | Fichier | Classes | Methodes | Couverture principale |
|---|---|---:|---:|---|
| accounts | `apps/accounts/tests.py` | 2 | 17 | signature, profil, email, changement mot de passe, API auth profile |
| accounts | `apps/accounts/tests_mobile_auth.py` | 1 | 5 | login mobile, refresh, roles autorises/refuses |
| accounts | `apps/accounts/tests_permissions_services.py` | 2 | 4 | permissions comptes/roles, revocation JWT |
| core | `apps/core/tests.py` | 4 | 11 | enveloppe API, renderer, securite, logging middleware |
| core | `apps/core/tests_audit.py` | 1 | 2 | audit log et snapshots acteur |
| core | `apps/core/tests_cache.py` | 1 | 5 | cache, cles, invalidation, tolerance erreurs backend |
| core | `apps/core/tests_demo_dataset.py` | 1 | 2 | commande seed demo complete et idempotence |
| core | `apps/core/tests_production_settings.py` | 1 | 11 | validation settings production |
| core | `apps/core/tests_seed_demo.py` | 1 | 2 | seed SmartRoute et reset commande |
| drivers | `apps/drivers/tests.py` | 1 | 14 | API drivers, recherche dossier/NIF, permissions, validation dates |
| drivers | `apps/drivers/tests_services.py` | 1 | 3 | normalisation dossier/NIF, validite permis |
| owners | `apps/owners/tests.py` | 2 | 8 | API owners, permissions, VehicleOwnership service |
| vehicles | `apps/vehicles/tests.py` | 2 | 17 | modele/serializer/API vehicles, owner sync, recherche plaque |
| documents | `apps/documents/tests.py` | 1 | 12 | API documents, permissions, stockage prive, download |
| insurance | `apps/insurance/tests.py` | 2 | 14 | modele/serializer/API assurance, recherche, permissions |
| scans | `apps/scans/tests.py` | 1 | 14 | scan plaque, historique, recherche, auth, payload mobile |
| gemini | `apps/gemini/tests.py` | 2 | 8 | helpers OCR, fallbacks Gemini, erreurs service |
| infractions | `apps/infractions/tests.py` | 3 | 12 | penalites, seed catalogue, API read-only |
| delits | `apps/delits/tests.py` | 1 | 6 | services delits, source type, DCPJ demo |
| tickets | `apps/tickets/tests.py` | 2 | 9 | modele/API tickets, verbalizations, close, barcode |
| tickets | `apps/tickets/tests_services_additional.py` | 1 | 2 | generation numero PV, recherche open ticket |
| alerts | `apps/alerts/tests.py` | 3 | 11 | alertes terrain/admin, expiration, warnings documents |
| alerts | `apps/alerts/tests_filters_websocket.py` | 3 | 5 | filtres, middleware JWT websocket, consumer Channels |
| dashboard | `apps/dashboard/tests.py` | 1 | 4 | statistiques dashboard, cache, auth |
| reports | `apps/reports/tests.py` | 1 | 7 | permissions rapports, read-only, dates invalides |
| reports | `apps/reports/tests_services_additional.py` | 1 | 3 | services rapports, dates, aggregations |
| sync | `apps/sync/tests.py` | 1 | 10 | API sync, devices, idempotence, conflits, limites |
| sync | `apps/sync/tests_handlers.py` | 2 | 5 | handlers sync, config, conflits, queryset pull |
| media_storage | `apps/media_storage/tests.py` | 1 | 6 | validation fichiers, MIME, taille, antivirus hook |

## Causes racines traitees

| Cause | Impact initial | Correction |
|---|---:|---|
| B. NIF ou identifiants au mauvais format | Majoritaire, erreurs de `setUp` | Remplacement des NIF de fixtures valides par 10 chiffres, conservation des tests negatifs |
| B/F. Badge agent invalide | Majoritaire, `AgentProfile.clean()` rejetait les badges alphabetiques | Remplacement par badges 11 chiffres normalisables |
| C. Valeurs dupliquees sur champs uniques | Sync apres correction naive | Badge/NIF distinct pour second utilisateur sync |
| I/J. Assertions API obsoletes | Scan attendait ancien NIF brut | Assertions mises a jour vers NIF normalise avec tirets |
| O. Dependence locale optionnelle | Barcode retourne 503 sans `reportlab` | Test verifie soit SVG si disponible, soit contrat 503 documente par la vue |
| I. Numero de permis obsolescent | Delits utilisait un NIF comme dossier permis apres remplacement | Restauration du format `XX-YYYYY-XX` |

## Conventions fixtures

- `Person.nif` valide: exactement 10 chiffres en entree ou format normalisable vers `XXX-XXX-XXX-X`.
- `AgentProfile.badge_number` valide: exactement 11 chiffres en entree ou format normalisable vers `XX-XX-XX-XXXXX`.
- Les valeurs lisibles comme `AGT-100` doivent rester dans `username`, `email`, references externes ou noms de scenario, pas dans `nif` ni `badge_number`.
- Les tests negatifs doivent conserver des valeurs invalides uniquement quand l'objectif est de tester un rejet.

## Resultats progressifs

| Commande | Resultat |
|---|---|
| `python manage.py check` | OK, 0 issue |
| `python manage.py test apps.accounts` | 26 tests OK |
| `python manage.py test apps.drivers apps.owners apps.vehicles` | 42 tests OK |
| `python manage.py test apps.documents apps.insurance` | 26 tests OK |
| `python manage.py test apps.infractions apps.delits apps.tickets apps.alerts` | 46 tests OK |
| `python manage.py test apps.sync apps.reports apps.dashboard apps.media_storage apps.gemini apps.scans apps.core` | 92 tests OK |
| `python manage.py test` | 232 tests OK en 13.951s |

## Couverture estimee

Les pourcentages de couverture presentes sont des estimations fonctionnelles et non une mesure de couverture par lignes.

| Domaine | Presence de tests | Executable et vert |
|---|---:|---:|
| Modeles | 80% | 100% des tests presents |
| Serializers | 75% | 100% des tests presents |
| API | 85% | 100% des tests presents |
| Permissions | 85% | 100% des tests presents |
| Services | 75% | 100% des tests presents |
| Erreurs et validations | 75% | 100% des tests presents |
| Flux critiques mobile/backend | 80% | 100% des tests presents |

## Limites connues

- La suite ne mesure pas la couverture par lignes car `coverage report` n'a pas ete execute.
- Le barcode depend de `reportlab`; sans ce paquet, le comportement attendu est un 503 controle.
- Les tests Gemini mockent l'appel externe, conformement au README.
- Les tests Channels utilisent un channel layer memoire.
