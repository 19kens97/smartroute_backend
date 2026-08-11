# SmartRoute preproduction readiness

Date: 2026-08-11

This runbook turns the current SmartRoute preproduction preparation into an executable plan. It does not claim real validation where the required infrastructure, Android device, ClamAV daemon, printer, or preproduction endpoints are not available.

## Baseline

| Repo | Branch | Dirty | Last commits checked | Automated state |
| --- | --- | --- | --- | --- |
| backend | `feature_01` | Yes | `git log -10 --oneline` captured | `check`, tests, OpenAPI, `pip-audit` green |
| mobile | `feature_00` | Yes | `git log -10 --oneline` captured | TS, lint, Jest, Expo Doctor, install check green; npm audit has 23 tooling vulns |

No destructive Git command was used. No Expo migration was started.

## Change classification

### Backend

| File or group | Type of change | Domain | Version? | Recommended commit |
| --- | --- | --- | --- | --- |
| `.env.example` | preprod/prod placeholders and security variables | CONFIG/SECURITY | Yes, placeholders only | backend 1 |
| `.gitignore` | local artifact exclusions | CONFIG | Yes | backend 1 |
| `README.md`, `docs/deployment-production.md`, `docs/preproduction-readiness.md` | deployment/security documentation | DOC/SECURITY | Yes | backend 5 |
| `config/settings/base.py` | env parsing, logging, upload, email, Redis/Channels variables | CONFIG/SECURITY | Yes | backend 1 |
| `config/settings/prod.py` | production DB/security validation | CONFIG/SECURITY | Yes | backend 1 |
| `config/settings/production_checks.py` | fail-closed production guards | SECURITY/CONFIG/TEST | Yes | backend 1 |
| `apps/core/tests_production_settings.py` | regression tests for production guards | TEST/SECURITY | Yes | backend 1 |
| `apps/accounts/*password*`, `apps/accounts/throttles.py`, templates, auth tests | password reset and throttling | AUTH/SECURITY/TEST | Yes | backend 2 |
| `apps/accounts/views.py`, `apps/accounts/urls.py`, `apps/accounts/tests.py` | auth endpoints and test coverage | AUTH/SECURITY/TEST | Yes | backend 2 |
| `apps/core/security.py`, `apps/core/tests_security_redaction.py` | response/log redaction helpers/tests | SECURITY/TEST | Yes | backend 3 |
| `apps/media_storage/services.py`, `apps/media_storage/tests.py` | private media, AV checks, upload hardening | SECURITY/CLAMAV/TEST | Yes | backend 3 |
| `apps/*/serializers.py`, `apps/*/views.py` for alerts/delits/documents/drivers/insurance/scans/sync/tickets/vehicles/dashboard/reports | API/media/download auth and schema annotations | SECURITY/OPENAPI | Yes | backend 3 or 4 |
| `apps/alerts/tests_*`, `apps/core/tests_openapi_schema.py` | middleware/websocket/schema regression tests | TEST/OPENAPI | Yes | backend 4 |
| `apps/core/openapi.py` | OpenAPI customization | OPENAPI | Yes | backend 4 |
| `schema.yml` | generated API schema | GENERATED/OPENAPI | Decision required | backend 4 if treated as API contract |
| `docker-compose.clamav.yml`, `docs/security/clamav.md`, `apps/core/management/commands/test_clamav.py` | ClamAV preprod tooling | CLAMAV/DOC/TEST | Yes | backend 5 |
| `requirements.txt` | dependency additions for security/OpenAPI/audit support | CONFIG/SECURITY | Yes | backend 1 or 5 |

### Mobile

| File or group | Type of change | Domain | Version? | Recommended commit |
| --- | --- | --- | --- | --- |
| `.env` | local environment deletion tracked by Git status | LOCAL ONLY | No; keep ignored/local | do not commit until reviewed |
| `.gitignore` | local env/artifact exclusions | CONFIG | Yes | mobile 1 |
| `.env.example`, `README.md`, docs | documented API/WSS/offline/frontend setup | DOC/CONFIG | Yes | mobile 6 |
| `services/api/config.ts`, `services/api/client.ts`, `utils/apiErrors.ts` | transport validation and API error handling | SECURITY/AUTH/CENTRALISATION | Yes | mobile 1 |
| `services/auth.ts`, `stores/authStore.ts`, `utils/tokenStorage.ts` | session/SecureStore handling | AUTH/SECURITY | Yes | mobile 1 |
| `app/(auth)/login.tsx`, `app/(auth)/forgot-password.tsx`, `app/(auth)/reset-password.tsx` | auth UI and password reset flow | AUTH/UI/UX | Yes | mobile 3 |
| `services/api/endpoints.ts`, `types/index.ts` | API contracts/endpoints | AUTH/CENTRALISATION | Yes | mobile 3 or 4 |
| `database/sqlite.ts`, `hooks/useSyncQueue.ts`, `docs/offline-mode.md` | offline queue, failed payloads, owner key | OFFLINE/SECURITY/DOC | Yes | mobile 2 |
| `utils/logRedaction.ts`, `__tests__/logRedaction.test.ts` | mobile log redaction | SECURITY/TEST | Yes | mobile 1 |
| `services/realtime/alertSocket.ts`, `__tests__/alertSocket.test.ts` | WebSocket auth/reconnect tests | SECURITY/TEST | Yes | mobile 1 |
| `constants/`, `utils/capabilities.ts`, `utils/messages.ts` | role/capability/message centralization | CENTRALISATION/UI/UX | Yes | mobile 4 |
| `app/scan/*`, `app/ticket/*`, `app/alerts/*`, search/history/statistics/profile screens | UX/API consistency and offline owner key usage | UI/UX/OFFLINE | Yes | mobile 4 |
| `components/business/*`, `components/layout/Screen.tsx` | UI consistency | UI/UX | Yes | mobile 4 |
| `__tests__/*` modified/new | regression coverage | TEST | Yes | mobile 5 |
| `package.json`, `package-lock.json` | package metadata/dependency lock changes | CONFIG | Yes, after review | mobile 5 |
| `docs/frontend-architecture.md` | frontend architecture documentation | DOC | Yes | mobile 6 |

## Artifacts excluded from commits

| Artifact | Repo | State |
| --- | --- | --- |
| `.env`, `.env.*` | backend/mobile | ignored; do not commit real values |
| `db.sqlite3` | backend | ignored local SQLite artifact |
| `.expo/` | mobile | ignored local Expo cache |
| `node_modules/` | mobile | ignored dependencies |
| `logs/`, `media/`, `private/` | backend | ignored runtime/private data |
| `coverage/`, `dist/`, `build/`, `*.log` | both where applicable | local/generated only |

`schema.yml` is not currently ignored. Decision required: if it is the intended OpenAPI contract, commit and document regeneration; otherwise treat as local/generated and add an ignore rule in a separate review.

## Secret scan status

Path-only scans found names of sensitive variables in configuration, tests, and documentation, but no secret value was printed or confirmed as versioned.

| Variable class | Files matched | Status |
| --- | --- | --- |
| `SECRET_KEY`, `DATABASE_URL`, `EMAIL_HOST_PASSWORD`, `PASSWORD`, `TOKEN`, `Authorization` | backend config/docs/tests/auth code | expected placeholders/tests; inspect before commit |
| `EXPO_PUBLIC_API_BASE_URL`, `EXPO_PUBLIC_WS_BASE_URL`, `Authorization`, `TOKEN` | mobile config/docs/tests/API code | public URL names and auth code; inspect before commit |

Before commit, run a final secret scan with a dedicated tool if available. Do not commit real `.env` values.

## Proposed commit plan

| Order | Repo | Commit | Content |
| --- | --- | --- | --- |
| 1 | backend | `security: harden production settings` | `.env.example`, `.gitignore`, `config/settings/*`, production guard tests, relevant requirements |
| 2 | backend | `auth: secure login and password reset flows` | account views/urls/serializers/templates/throttles/auth tests |
| 3 | backend | `media: secure private uploads and downloads` | media storage service/tests, serializers/views touching private media and redaction |
| 4 | backend | `api: document OpenAPI contract and schema tests` | `apps/core/openapi.py`, OpenAPI tests, `schema.yml` if accepted as contract |
| 5 | backend | `docs: prepare ClamAV and preproduction runbook` | ClamAV compose/command/docs and this runbook |
| 6 | mobile | `auth: secure API transport and token handling` | API config/client, SecureStore/token/auth store, alert socket auth tests |
| 7 | mobile | `offline: harden SQLite queue and owner isolation` | SQLite queue, sync queue, ownerKey fixes, offline tests/docs |
| 8 | mobile | `auth: add password reset mobile flow` | forgot/reset screens, endpoints/types/messages, auth tests |
| 9 | mobile | `ui: centralize capabilities and status labels` | constants, capabilities, messages, screens/components UX consistency |
| 10 | mobile | `test: extend mobile regression coverage` | new/updated tests and test setup changes |
| 11 | mobile | `docs: update frontend and integration docs` | mobile docs/README updates |

Commits were not created automatically because the diffs are broad and should be reviewed lot-by-lot before staging.

## Environment matrix

| Variable | Dev | Preprod | Production | Secret | Validation |
| --- | --- | --- | --- | --- | --- |
| `DEBUG` | may be true | `False` | `False` | No | prod settings reject invalid/true |
| `SECRET_KEY` | dev placeholder allowed | strong unique env value | strong unique env value | Yes | production guard rejects placeholders |
| `ALLOWED_HOSTS` | localhost/LAN | explicit preprod hosts | explicit prod hosts | No | no `*`, non-empty |
| `CORS_ALLOWED_ORIGINS` | localhost/LAN | exact HTTPS origins | exact HTTPS origins | No | no wildcard policy |
| `CSRF_TRUSTED_ORIGINS` | local if needed | exact HTTPS origins | exact HTTPS origins | No | required for HTTPS admin/forms if cross-origin |
| `CORS_ALLOW_ALL_ORIGINS` | normally false | `False` | `False` | No | production guard rejects true |
| `POSTGRES_DB` | optional | preprod DB name | prod DB name | No | migrate/check succeeds |
| `POSTGRES_USER` | optional | dedicated least-privilege user | dedicated least-privilege user | Maybe | DB connection and migrations |
| `POSTGRES_PASSWORD` | optional | env-only credential | env-only credential | Yes | never in repo |
| `POSTGRES_HOST` | optional | private DB host | private DB host | No | network private/reachable |
| `POSTGRES_PORT` | optional | DB port | DB port | No | TCP reachable |
| `SECURE_SSL_REDIRECT` | dev off | enabled by prod settings | enabled by prod settings | No | HTTP redirect test |
| `SECURE_PROXY_SSL_HEADER` | proxy-dependent | `HTTP_X_FORWARDED_PROTO=https` | same | No | request scheme correct behind proxy |
| `SESSION_COOKIE_SECURE` | dev may be false | true | true | No | cookie flags verified |
| `CSRF_COOKIE_SECURE` | dev may be false | true | true | No | cookie flags verified |
| `REDIS_URL` | optional local | private Redis if `USE_REDIS=True` | private Redis | Maybe | Channels/cache healthcheck |
| `ANTIVIRUS_SCANNER` | `disabled` or local | `clamav_tcp` | `clamav_tcp` | No | production guard and ClamAV tests |
| `ANTIVIRUS_REQUIRED` | optional false | `True` | `True` | No | upload fails closed if scanner unavailable |
| `ANTIVIRUS_CLAMAV_HOST` | local/private | private clamd host | private clamd host | No | PING/PONG |
| `ANTIVIRUS_CLAMAV_PORT` | `3310` | internal TCP port | internal TCP port | No | TCP healthcheck |
| `EMAIL_BACKEND` | console | SMTP/provider | SMTP/provider | No | password reset email delivered |
| `EMAIL_HOST`, `EMAIL_PORT`, `EMAIL_USE_TLS`, `EMAIL_HOST_USER`, `EMAIL_HOST_PASSWORD` | dev optional | env-only SMTP config | env-only SMTP config | password yes | delivery and timeout tests |
| `API_RESPONSE_LOGGING_INCLUDE_BODY` | may be true in dev | false | false | No | production guard rejects true |
| `EXPO_PUBLIC_API_BASE_URL` | `http://` LAN allowed | `https://<preprod-api>` | `https://<prod-api>` | No | mobile startup validation |
| `EXPO_PUBLIC_WS_BASE_URL` | `ws://` LAN allowed | `wss://<preprod-api>` | `wss://<prod-api>` | No | mobile startup validation |

## PostgreSQL preproduction procedure

Real status: TO VALIDATE IN PREPRODUCTION.

1. Create a PostgreSQL database owned by a dedicated SmartRoute user.
2. Store credentials only in environment variables or a secret manager.
3. Point prod settings to `POSTGRES_*` values.
4. Run migrations with fictitious data only.
5. Verify constraints, indexes, timezone, transactions, and rollback behavior.
6. Create a backup before any migration rehearsal.
7. Test restore into a disposable database.

Commands:

```powershell
python manage.py migrate --settings=config.settings.prod
python manage.py check --settings=config.settings.prod
python manage.py test --settings=config.settings.prod
```

Minimal DB healthcheck: run a Django management command or shell snippet that opens a transaction, executes `SELECT 1`, writes and rolls back a harmless test row, and emits only pass/fail metadata.

## HTTPS and reverse proxy

Target path:

```text
Internet or Android device -> HTTPS -> reverse proxy/load balancer -> Django ASGI/Daphne
```

Required proxy behavior: preserve `Host`, set `X-Forwarded-Proto=https`, forward client IP chain, and block direct insecure backend exposure. Django prod settings already define SSL redirect, HSTS, secure cookies, content type nosniff, and frame denial.

## WSS and Redis

Target path:

```text
mobile -> wss://<preprod-api>/ws/alerts/ -> reverse proxy -> ASGI/Daphne -> Django Channels
```

Proxy must preserve `Upgrade`, `Connection`, and `Sec-WebSocket-Protocol`. JWT stays in the WebSocket subprotocol, never in query string.

Redis is optional in local/dev code. For preproduction with more than one ASGI worker or instance, enable `USE_REDIS=True` and provide private `REDIS_URL`; validate connect, publish/subscribe behavior, reconnect, and auth/TLS if configured.

## ClamAV

Real status: NOT TESTED REALLY on this machine.

Preprod requirements: private `clamd`, TCP port 3310 internal only, `freshclam` signatures updated, `ANTIVIRUS_REQUIRED=True`, `ANTIVIRUS_SCANNER=clamav_tcp`.

| Test | Expected result |
| --- | --- |
| PING | PONG |
| clean JPEG/PDF | accepted |
| EICAR | rejected |
| daemon unavailable | upload rejected fail-closed |
| timeout | upload rejected fail-closed |

Docker is not available locally and must not be forced on this machine.

## Media storage

Private media roots currently cover agent signatures, alert evidence, ticket proofs, documents, scans, and delit evidence. Preprod must verify private filesystem or object storage permissions, authenticated download endpoints, MIME/magic-byte validation, size limits, antivirus flow, backup/restore policy, and cleanup policy for temporary files.

Do not use temporary local directories as a production storage decision without documenting retention, backups, and access controls.

## Email

Password reset requires real email in preprod. If no provider is selected, status is EMAIL REAL: TO CONFIGURE.

Required checks: SMTP/provider backend, from address, TLS, timeout, credentials env-only, successful reset email to test accounts, and no account enumeration leakage beyond the intended product decision.

## Mobile preproduction and Android identity

Mobile env values for preview builds:

```text
EXPO_PUBLIC_API_BASE_URL=https://<preprod-api>
EXPO_PUBLIC_WS_BASE_URL=wss://<preprod-api>
```

These URLs are public by design and must contain no credentials.

Android audit from `app.json`: version is `1.0.0`; permissions include camera and microphone; adaptive icons are configured; no explicit `android.package`; no explicit `android.versionCode`; no `eas.json` was found.

Status: ANDROID APPLICATION ID: DECISION REQUIRED. `versionCode` decision required before a real APK/AAB preview candidate.

## EAS/build proposal

No EAS authentication or external build was started.

If EAS is selected, create `eas.json` after approval with conceptual profiles:

| Profile | Purpose | Notes |
| --- | --- | --- |
| development | dev client/internal debugging | may use dev endpoints only |
| preview | preproduction candidate | uses HTTPS/WSS preprod and distinct app identity/name |
| production | store/release candidate | uses production endpoints and final identifiers |

Preview builds must be clearly identifiable as preproduction and must not use production secrets.

## Expo migration readiness

Current SDK: Expo 54, React Native 0.81.5, React 19.1.0, Expo Router 6.0.24, Jest Expo 54.

Future branch: `chore/expo-sdk-migration`.

Migration can start only when: mobile worktree is clean or intentionally committed, tests are green, Expo Doctor is green, npm audit baseline is captured, and a rollback commit is identifiable.

Current decision: migration cannot start yet because the mobile worktree is not stabilized.

## Rollback

Backend rollback requirements: identify previous deployable commit, backup PostgreSQL before migrations, review migration reversibility before deploy, keep previous application artifact, and define an application rollback path independent of irreversible data migrations.

Mobile rollback requirements: keep previous APK/AAB or EAS build, record `versionCode`, verify API backward compatibility, and avoid forcing users onto a build that requires backend endpoints unavailable in rollback.

## Test data

Use only fictitious agents, drivers, vehicles, insurance policies, tickets, signatures, and evidence files. No real citizen data is allowed in preproduction or field-test preparation.

## Real validation checklist

| Capability | PASS | FAIL | NOT TESTED | Notes |
| --- | --- | --- | --- | --- |
| PostgreSQL real |  |  | X | Requires preprod DB |
| HTTPS |  |  | X | Requires deployed TLS endpoint |
| WSS |  |  | X | Requires ASGI/proxy endpoint |
| ClamAV |  |  | X | Requires real clamd |
| storage uploads/downloads |  |  | X | Requires preprod media storage and AV |
| email reset |  |  | X | Requires SMTP/provider |
| Android APK install |  |  | X | Requires build and device |
| printing |  |  | X | Requires Android print service/printer |

## Risk register

| Priority | Risk | Action |
| --- | --- | --- |
| P0 | No real preproduction infrastructure validated | Provision and validate PostgreSQL, HTTPS/WSS, ClamAV, storage, email |
| P1 | Git worktrees remain dirty | Review/stage/commit by proposed lots |
| P1 | Expo/Metro npm audit vulnerabilities remain | Migrate Expo on dedicated branch after stabilization |
| P1 | Android application id/versionCode absent | Decide identifiers before APK candidate |
| P2 | `schema.yml` ownership undecided | Decide API contract vs ignored generated artifact |
| P2 | Field tests not run | Run only after APK and backend preprod are stable |

## Readiness decision

Current decision: GIT NOT STABILIZED.

The codebase is ready to continue preparation and review commits, but it is not ready to start Expo migration or declare preproduction deployed until Git is stabilized and real infrastructure is provisioned.
