# Vue Generale Des API

## Prefixes

Toutes les API metier sont sous `/api/`. Documentation dynamique: `/api/docs/`; schema OpenAPI: `/api/schema/`.

## Authentification

Les endpoints proteges utilisent JWT Bearer. Le mobile utilise `/api/auth/mobile/login/` et `/api/auth/mobile/token/refresh/`.

## Enveloppe Standard

La majorite des reponses suivent:

```json
{
  "success": true,
  "message": "Message lisible.",
  "data": {},
  "errors": {}
}
```

Exception notable: le scan plaque retourne une reponse directe pour compatibilite mobile.

## Groupes D'API

| Prefixe | Usage principal |
|---|---|
| `/api/auth/` | login, refresh, profil, mot de passe, signature, utilisateurs |
| `/api/owners/` | proprietaires et historiques de possession |
| `/api/vehicles/` | vehicules et recherche par plaque |
| `/api/documents/` | documents vehicule et lecture privee |
| `/api/drivers/` | permis, recherche dossier/NIF |
| `/api/insurance/` | polices assurance, recherche par plaque ou police |
| `/api/scans/` | scan plaque, historique, recherche |
| `/api/infractions/` | catalogue officiel |
| `/api/delits/` | types et dossiers delits |
| `/api/tickets/` | PV, verbalisation, preuves, barcode, signature agent |
| `/api/alerts/` | alertes, preuves, unread, mark-opened |
| `/api/dashboard/` | statistiques de synthese |
| `/api/reports/` | rapports globaux |
| `/api/sync/` | devices, push, pull, statut |

## Codes Courants

- `200`: lecture ou action reussie.
- `201`: ressource creee.
- `400`: payload invalide.
- `401`: authentification manquante ou invalide.
- `403`: role non autorise.
- `404`: ressource absente.
- `405`: methode HTTP non supportee.
- `422`: plaque inexploitable pour le scan.
- `503`: service optionnel ou externe indisponible.

## Pagination Et Filtres

Plusieurs ViewSets utilisent pagination, filtres, recherche et ordering DRF. Consulter Swagger pour le detail exact des parametres disponibles.