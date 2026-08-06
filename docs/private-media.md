# Medias prives

## Principe

SmartRoute stocke les fichiers binaires hors base de donnees. Les modeles conservent les metadonnees : chemin storage, MIME, taille, checksum SHA-256, duree et createur lorsque disponible.

## Types pris en charge

- images ;
- videos ;
- audios ;
- documents ;
- signatures.

## Chemins d'upload

Les fonctions de `apps.media_storage.services` generent les chemins suivants :

- preuves PV : `tickets/{ticket_number}/photos|videos|audio/{uuid}.{ext}` ;
- preuves d'alerte : `alerts/{alert_id}/audio|videos|photos/{uuid}.{ext}` ;
- signatures agents : `signatures/agents/{agent_id}/{uuid}.png` ;
- documents vehicule : `documents/vehicles/{vehicle_id}/{uuid}.{ext}` ;
- scans persistants : `scans/{uuid}.{ext}` ;
- profils : `profiles/{id}/{uuid}.{ext}`.

Le nom original fourni par le client n'est pas conserve comme nom final.

## Stockage prive

Les storages prives utilisent notamment :

- `PRIVATE_SIGNATURE_ROOT`
- `PRIVATE_ALERT_EVIDENCE_ROOT`
- `PRIVATE_TICKET_PROOF_ROOT`
- `PRIVATE_DOCUMENT_ROOT`
- `PRIVATE_SCAN_ROOT`
- `PRIVATE_DELIT_EVIDENCE_ROOT`

En developpement, `config.urls` sert `MEDIA_URL` seulement lorsque `DEBUG=True`. Les medias sensibles doivent passer par les endpoints authentifies existants.

## Validation

`validate_uploaded_media` verifie :

- presence du fichier ;
- fichier non vide ;
- extension dangereuse refusee (`.exe`, `.js`, `.php`, `.svg`, etc.) ;
- extension autorisee ;
- MIME autorise ;
- magic bytes pour JPEG, PNG et PDF ;
- taille maximale ;
- duree maximale si applicable.

Limites par defaut :

- image : `MAX_IMAGE_SIZE_MB`, borne par `SECURE_UPLOAD_MAX_MB` ;
- video : min de `MAX_VIDEO_SIZE_MB` et `ALERT_EVIDENCE_VIDEO_MAX_MB`, duree `ALERT_EVIDENCE_VIDEO_MAX_DURATION_SECONDS` ;
- audio : min de `MAX_AUDIO_SIZE_MB` et `ALERT_EVIDENCE_AUDIO_MAX_MB`, duree `ALERT_EVIDENCE_AUDIO_MAX_DURATION_SECONDS` ;
- document : `MAX_DOCUMENT_SIZE_MB`.

## Endpoints d'acces

- signature agent : `GET/PUT/DELETE /api/auth/profile/signature/` ;
- preuve alerte : endpoint detail d'evidence sous `/api/alerts/` ;
- preuve PV : endpoint de download de preuve sous `/api/tickets/` ;
- documents vehicule : endpoint de download sous `/api/documents/`.

Les URLs exactes detaillees dependent des routers DRF des applications concernees.

## Antivirus

`scan_file_for_virus` retourne actuellement `NOT_CONFIGURED`. Aucun moteur antivirus reel n'est branche dans le MVP.

## Nettoyage

Le nettoyage automatique des fichiers orphelins n'est pas defini dans l'implementation actuelle.
