# Depannage Backend

## `ValidationError` Sur NIF

Verifier que la fixture fournit 10 chiffres ou une valeur normalisable vers `XXX-XXX-XXX-X`.

## `ValidationError` Sur Badge

Verifier que le badge contient 11 chiffres ou une valeur normalisable vers `XX-XX-XX-XXXXX`.

## Mobile Ne Joint Pas Le Backend

Verifier `ALLOWED_HOSTS`, CORS, URL LAN, port `8000`, pare-feu local et token JWT.

## Scan Plaque Indisponible

Verifier `GEMINI_API_KEY`, connectivite serveur, format multipart et taille/type MIME de l'image.

## WebSocket Alertes

Verifier `EXPO_PUBLIC_WS_BASE_URL`, `REDIS_URL` si multi-processus, token JWT et route `ws/alerts/`.

## Barcode 503

Installer/configurer `reportlab` si le SVG barcode est requis. Sinon le `503` est le comportement controle.