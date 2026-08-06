# Synchronisation hors ligne

## Objectif

La synchronisation permet a un appareil client d'envoyer et recuperer des donnees operationnelles sans serveur externe autre que l'API Django.

## Endpoints

Les routes sont sous `/api/sync/` :

- `POST /api/sync/devices/register/`
- `POST /api/sync/devices/revoke/`
- `GET /api/sync/devices/`
- `POST /api/sync/push/`
- `POST /api/sync/pull/`
- `GET /api/sync/status/?request_uuid=<uuid>`

## Permissions

`SyncPermission` autorise uniquement les comptes `PROFESSIONAL` actifs avec un profil agent actif et un role `ADMIN`, `AGENT_TERRAIN` ou `AGENT_SAISIE`. Les comptes personnels sont refuses.

## Entites supportees

`SyncItemLog.EntityType` declare :

- `TICKET`
- `VERBALIZATION`
- `TICKET_PROOF`
- `DELIT_CASE`
- `DELIT_EVIDENCE`

Le push est desactive pour `TICKET_PROOF` et `DELIT_EVIDENCE`; ces entites doivent passer par leurs endpoints multipart dedies. Elles restent disponibles en pull si configurees.

## Push

Format attendu :

```json
{
  "device_uuid": "00000000-0000-0000-0000-000000000001",
  "request_uuid": "00000000-0000-0000-0000-000000000002",
  "items": [
    {
      "entity_type": "TICKET",
      "operation": "CREATE",
      "client_uuid": "00000000-0000-0000-0000-000000000003",
      "base_version": null,
      "data": {}
    }
  ]
}
```

Operations supportees : `CREATE`, `UPDATE`, `UPSERT`. Un lot contient au maximum 100 items. Une operation dupliquee dans le meme lot est rejetee par validation.

La reponse contient une session serialisee avec les compteurs `success_count`, `failure_count`, `conflict_count` et les items traites.

## Versions et conflits

Par defaut, la version serveur est derivee de `updated_at` en microsecondes. Si une mise a jour fournit un `base_version` different de la version serveur, `SyncConflictError` est levee et l'item est marque `CONFLICT`.

Si `base_version` est absent, la verification de conflit est ignoree.

## Pull

Format attendu :

```json
{
  "device_uuid": "00000000-0000-0000-0000-000000000001",
  "request_uuid": "00000000-0000-0000-0000-000000000004",
  "cursor": null,
  "entity_types": ["TICKET", "VERBALIZATION", "DELIT_CASE"],
  "limit": 100
}
```

`limit` est borne entre 1 et 200. Sans `entity_types`, le pull utilise `TICKET`, `VERBALIZATION` et `DELIT_CASE`.

Les resultats sont ordonnes par `updated_at`, puis `pk`. Quand une entite a un `owner_field`, les donnees sont limitees a l'utilisateur proprietaire.

## Idempotence

Une meme `request_uuid` rejouee avec le meme payload retourne le resultat existant. La meme `request_uuid` avec un contenu different est rejetee.

## Limites connues

- La strategie de conflit est stricte et basee sur `base_version`.
- Les preuves avec fichiers ne sont pas poussees par le handler generique.
- Aucun mecanisme de resolution automatique des conflits n'est defini.
