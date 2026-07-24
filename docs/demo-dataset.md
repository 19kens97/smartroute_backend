# SmartRoute - Demo Dataset

## Objective

The demo dataset provides realistic local data for testing SmartRoute backend workflows: agents, personal users, persons, drivers, owners, vehicles, ownership history, insurance, documents, alerts, scans, tickets, infractions, delits and dashboard statistics.

## Command

Run from `smartroute_backend`:

```powershell
.\venv\Scripts\python.exe manage.py reset_smartroute_demo
```

Equivalent compatible command:

```powershell
.\venv\Scripts\python.exe manage.py seed_smartroute_demo --reset
```

## Production Guardrails

The command refuses to run when:

- `DEBUG=False`;
- `DJANGO_SETTINGS_MODULE=config.settings.prod`;
- `ENVIRONMENT=production`.

It is intended only for local development and demonstrations.

## Test Accounts

Password for all demo accounts: `SmartRoute@123`.

| Account | Role |
|---|---|
| admin1@smartroute.test | ADMIN |
| admin2@smartroute.test | ADMIN |
| saisie1@smartroute.test | AGENT_SAISIE |
| saisie2@smartroute.test | AGENT_SAISIE |
| terrain1@smartroute.test | AGENT_TERRAIN |
| terrain2@smartroute.test | AGENT_TERRAIN |
| terrain3@smartroute.test | AGENT_TERRAIN |

Personal accounts use usernames such as `personal-driver` and the same demo password.

## Data Created

The command creates at least:

- 14 professional users;
- 5 personal users;
- 10 owners;
- 10 drivers;
- 15 vehicles;
- current and historical `VehicleOwnership` records;
- insurance policies with valid, expired and suspended examples;
- private vehicle documents;
- active and resolved alerts;
- 30 manual scans plus GeminiScan examples;
- 20 tickets with verbalizations, infractions and proofs;
- demo delit cases where the delits app is available;
- sync devices and sessions for dashboard testing.

## Business Consistency

`Person` is the civil identity source. `Driver` and `Owner` reference `Person`. `VehicleOwnership` is the official vehicle ownership source, while `Vehicle.owner` is a synchronized cache. Ticket snapshots are legal frozen copies and are not recalculated after ticket creation.

## Limits

The dataset is fictitious. It does not activate a real antivirus engine, real OCR/Gemini calls, real payments, or production-grade legal validation.
