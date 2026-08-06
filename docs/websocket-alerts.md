# WebSocket alertes

## Objectif

Le WebSocket des alertes sert a pousser des evenements d'alerte en temps reel vers un utilisateur authentifie.

## URL

```text
ws/alerts/
```

Dans `config.asgi`, cette route est exposee via `JWTAuthMiddleware`, `URLRouter` et `AllowedHostsOriginValidator`.

## Authentification

Le middleware accepte un JWT SimpleJWT valide aux emplacements suivants :

- header HTTP `Authorization: Bearer <token>` ;
- sous-protocole WebSocket `bearer.<token>` dans `Sec-WebSocket-Protocol` ;
- query string `?token=<token>`.

Le token doit appartenir a un utilisateur actif de type `PROFESSIONAL`, avec un `AgentProfile` actif. Les comptes personnels, les utilisateurs inactifs et les comptes professionnels sans profil agent actif sont refuses.

## Groupes Channels

Le consumer ajoute la connexion au groupe :

```text
alerts.user.<user_id>
```

La fonction de construction est `apps.alerts.consumers.user_alert_group`.

## Connexion et fermeture

- utilisateur absent ou token manquant/invalide : fermeture `4401` ;
- utilisateur authentifie mais non autorise : fermeture `4403` ;
- erreur interne pendant l'ajout au groupe : fermeture `4500` ;
- payload entrant dont la representation texte depasse 4096 caracteres : fermeture `1009`.

## Messages client

L'implementation actuelle ne definit aucune commande applicative. Un message court, y compris `ping`, est accepte mais ne produit pas de reponse `pong`.

## Messages serveur

Le handler Channels `alert_created` envoie directement `event["payload"]` au client JSON.

Exemple de payload possible :

```json
{
  "type": "alert_created",
  "id": 7,
  "severity": "CRITICAL"
}
```

La structure exacte du payload est fournie par le code qui appelle `group_send`; elle n'est pas normalisee dans le consumer.

## Channel layer

Quand `USE_REDIS=False`, les settings utilisent `channels.layers.InMemoryChannelLayer`. Quand `USE_REDIS=True`, `channels_redis.core.RedisChannelLayer` est configure avec `REDIS_URL`.

## Exemple JavaScript

```javascript
const socket = new WebSocket(`${wsBaseUrl}/ws/alerts/?token=${accessToken}`);
socket.onmessage = (event) => {
  const payload = JSON.parse(event.data);
  console.log(payload);
};
```

## Limites connues

- Pas de reponse `pong` implementee pour `ping`.
- Pas de schema centralise du payload `alert_created`.
- Les tests utilisent le channel layer memoire; aucun Redis reel n'est requis.
