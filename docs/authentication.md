# Authentification Backend

## Types De Comptes

- `PROFESSIONAL`: compte institutionnel pouvant avoir un `AgentProfile`.
- `PERSONAL`: compte personnel, refuse pour les API professionnelles et le mobile terrain.

## Roles Agents

Roles reels presents: `ADMIN`, `AGENT_SAISIE`, `AGENT_TERRAIN`.

## Mobile

Endpoint principal:

```http
POST /api/auth/mobile/login/
```

Le mobile envoie un identifiant dans le champ email et un mot de passe. Le backend n'emet des tokens que si le compte est `PROFESSIONAL`, actif, avec `AgentProfile` actif et role `AGENT_TERRAIN`.

Refresh mobile:

```http
POST /api/auth/mobile/token/refresh/
```

Le refresh reverifie l'etat courant du compte, du profil et du role.

## Backoffice Et Compatibilite

Endpoints historiques conserves:

- `POST /api/auth/auth/professional/login/`
- `POST /api/auth/auth/personal/login/`
- `POST /api/auth/auth/token/refresh/`

Le backoffice web est en cours de developpement.

## Profil Et Mot De Passe

- `GET /api/auth/me/`
- `PATCH /api/auth/me/`
- `POST /api/auth/change-password/`
- `GET|PUT|DELETE /api/auth/profile/signature/`

## Revocation Et Suspension

Des tests couvrent la revocation de refresh tokens et le refus mobile apres changement de role ou profil inactif. La politique operationnelle de suspension reste a confirmer cote administration.

## Reponses Et Erreurs

Les reponses API suivent l'enveloppe standard `success`, `message`, `data`, `errors`. Les refus attendus sont `401` pour auth absente/invalide et `403` pour role non autorise.