# Rapports

## Endpoints

Les rapports sont exposes sous `/api/reports/` :

- `GET /api/reports/summary/`
- `GET /api/reports/tickets/`
- `GET /api/reports/verbalizations/`
- `GET /api/reports/infractions/`
- `GET /api/reports/delits/`
- `GET /api/reports/agents/`

## Permissions

`ReportsPermission` autorise les comptes professionnels actifs avec profil agent actif et role `ADMIN` ou `AGENT_SAISIE`.

## Filtres

Tickets :

- `status`
- `pricing_status`
- `ticket_number`
- `dossier_number`
- `nif`
- `driver`
- `opened_by`
- `plate_number`
- `opened_from`
- `opened_to`

Verbalisations :

- `ticket_number`
- `agent`
- `status`
- `dossier_number`
- `plate_number`
- `location`
- `occurred_from`
- `occurred_to`

Infractions :

- `code`
- `penalty_type`
- `ticket_number`
- `agent`
- `observed_from`
- `observed_to`

Delits :

- `qualification_status`
- `procedure_status`
- `source_type`
- `delit_type`
- `detected_by`
- `driver`
- `vehicle`
- `ticket`
- `detected_from`
- `detected_to`

Agents :

- `role`
- `badge_number`
- `active`

Les dates sont au format `YYYY-MM-DD`. Les bornes sont inclusives : debut a `00:00:00`, fin a `23:59:59.999999` dans le fuseau courant.

## Reponses

Les vues paginent les rapports et enveloppent les reponses via les renderers/API helpers du projet. Le resume retourne les compteurs `tickets`, `verbalizations` et `delits`.

## Exemples

```http
GET /api/reports/tickets/?opened_from=2026-08-01&opened_to=2026-08-03
GET /api/reports/agents/?role=AGENT_SAISIE&active=true
GET /api/reports/summary/
```

## Limites connues

L'implementation actuelle de `get_ticket_report_queryset` annote `verbalization_count`, nom qui entre en conflit avec la propriete `Ticket.verbalization_count` sans setter. L'evaluation du queryset peut donc lever `AttributeError`. Correction non appliquee en raison de la contrainte de modification.
