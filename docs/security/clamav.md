# ClamAV pour SmartRoute

SmartRoute valide les uploads avec les controles locaux MIME, extension, magic bytes, taille et duree, puis transmet le fichier a ClamAV lorsque `ANTIVIRUS_SCANNER=clamav_tcp`.

## Architecture

```text
Django SmartRoute -> TCP prive -> clamd
```

Le port clamd n'est pas authentifie et ne chiffre pas le trafic. Il ne doit pas etre expose publiquement. En developpement local Windows, le compose publie uniquement `127.0.0.1:3310:3310` pour permettre a Django lance hors Docker de joindre clamd.

## Demarrage local

```powershell
docker compose -f docker-compose.clamav.yml up -d
docker compose -f docker-compose.clamav.yml ps
docker compose -f docker-compose.clamav.yml logs clamav
```

Au premier demarrage, le telechargement des signatures peut prendre plusieurs minutes. Le volume `clamav-signatures` persiste `/var/lib/clamav` pour eviter de tout retelecharger a chaque lancement.

## Configuration Django locale

```env
ANTIVIRUS_SCANNER=clamav_tcp
ANTIVIRUS_REQUIRED=False
ANTIVIRUS_CLAMAV_HOST=127.0.0.1
ANTIVIRUS_CLAMAV_PORT=3310
ANTIVIRUS_TIMEOUT_SECONDS=5
```

`ANTIVIRUS_REQUIRED=False` est accepte en developpement isole pour ne pas bloquer les uploads lorsque le daemon n'est pas lance. Le backend logge alors le scan saute ou indisponible, sans contenu de fichier.

## Configuration production

```env
ANTIVIRUS_SCANNER=clamav_tcp
ANTIVIRUS_REQUIRED=True
ANTIVIRUS_CLAMAV_HOST=<hostname-prive-clamd>
ANTIVIRUS_CLAMAV_PORT=3310
ANTIVIRUS_TIMEOUT_SECONDS=5
```

En production, `config.settings.prod` refuse une configuration antivirus desactivee ou incoherente. Si clamd est indisponible, timeout, refuse la connexion ou renvoie une reponse inconnue, l'upload est refuse. Il n'y a pas de fallback vers CLEAN.

## Test d'integration reel

Avec le daemon lance :

```powershell
python manage.py test_clamav --host 127.0.0.1 --port 3310 --timeout 5
```

La commande verifie :

1. PING/PONG clamd ;
2. fichier texte sain -> CLEAN ;
3. chaine standard EICAR generee en memoire -> INFECTED ;
4. port local invalide -> UNAVAILABLE.

La chaine EICAR n'est pas stockee durablement dans le depot.

## Test manuel upload

1. lancer ClamAV avec Docker Compose ;
2. attendre le healthcheck healthy ;
3. configurer Django avec `ANTIVIRUS_SCANNER=clamav_tcp` ;
4. demarrer Django ;
5. uploader un fichier autorise sain ;
6. verifier que l'upload est accepte ;
7. uploader un fichier de test EICAR genere temporairement ;
8. verifier que l'upload est refuse ;
9. arreter ClamAV ;
10. relancer avec `ANTIVIRUS_REQUIRED=True` ;
11. verifier que l'upload est refuse lorsque le scanner est indisponible.

## Arret

```powershell
docker compose -f docker-compose.clamav.yml down
```

Ne supprimez pas le volume signatures sauf besoin explicite de reinitialiser les bases ClamAV.

## Depannage

- `clamd PING failed` : attendre la fin du chargement des signatures puis relancer.
- `UNAVAILABLE` : verifier host, port, firewall local et healthcheck Docker.
- timeouts frequents : augmenter `ANTIVIRUS_TIMEOUT_SECONDS` et verifier la RAM disponible. ClamAV peut consommer plusieurs Go pendant le chargement des signatures.
- en production, ne publiez pas `0.0.0.0:3310`; utilisez un reseau prive, un sidecar ou un service interne.