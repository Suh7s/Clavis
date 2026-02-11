# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

**Clavis** is a clinical workflow orchestration engine for hospital coordination. It tracks clinical actions (diagnostics, medications, referrals, care instructions, and custom types) through enforced state machine transitions with real-time WebSocket updates and SLA deadline tracking.

## Tech Stack

- **Backend:** FastAPI, SQLModel, Uvicorn
- **Database:** SQLite (local file `clavis.db`)
- **Frontend:** Jinja2 templates, vanilla JS, Tailwind CDN
- **Real-time:** FastAPI native WebSockets (in-memory connection store)
- **No auth, no Redis, no Celery, no Docker**

## Commands

```bash
# Install dependencies
pip install fastapi sqlmodel uvicorn jinja2

# Seed demo data
cd backend && python3 seed.py

# Run server
cd backend && python3 -m uvicorn main:app --reload --port 8000

# Reset demo (while running)
curl http://localhost:8000/demo/reset
```

## Repository Structure

```
backend/
├── main.py                  # App entry, lifespan, template routes, health, demo reset, WS endpoint
├── models.py                # SQLModel tables: Patient, ClinicalAction, ActionEvent, CustomActionType
├── database.py              # SQLite engine + session dependency
├── state_machine.py         # VALID_TRANSITIONS, validate_transition(), validate_custom_transition()
├── ws.py                    # ConnectionManager (in-memory per patient_id)
├── seed.py                  # Idempotent demo seeder (1 patient, 3 actions)
├── routers/
│   ├── patients.py          # CRUD + GET /patients/{id}/summary
│   ├── actions.py           # Create, transition, list, timeline
│   └── custom_types.py      # CRUD for CustomActionType
├── services/
│   └── sla.py               # SLA deadline computation, overdue detection, terminal state checks
└── templates/
    ├── base.html             # Layout + Tailwind CDN
    ├── index.html            # Patient list + create form
    └── patient.html          # Patient dashboard: summary, actions, transitions, timeline, WebSocket
```

## Architecture

### State Machine

Core transitions validated server-side in `state_machine.py`. Invalid transitions return 422.

| Action Type      | Transitions                                            |
|------------------|--------------------------------------------------------|
| DIAGNOSTIC       | REQUESTED → SAMPLE_COLLECTED → PROCESSING → COMPLETED |
| MEDICATION       | PRESCRIBED → DISPENSED → ADMINISTERED                  |
| REFERRAL         | INITIATED → ACKNOWLEDGED → REVIEWED → CLOSED          |
| CARE_INSTRUCTION | ISSUED → ACKNOWLEDGED → IN_PROGRESS → COMPLETED       |

### Custom Action Types

`CustomActionType` model stores an ordered `states` list (JSON). Transitions are sequential-forward only, built dynamically from the list. Custom types define their own terminal state and SLA durations per priority.

A `ClinicalAction` has either `action_type` (core enum) OR `custom_action_type_id` (FK), never both.

### Event Log

Every state transition appends a row to `ActionEvent`. The timeline endpoint returns events sorted by timestamp with `action_name` resolved (core enum value or custom type name).

### SLA

Deadlines auto-assigned on action creation based on priority:
- Core: ROUTINE=2h, URGENT=30m, CRITICAL=10m
- Custom: per-type configurable minutes

`is_overdue` computed dynamically (not stored) — checks `sla_deadline < now()` unless action is in terminal state.

### WebSocket

`ConnectionManager` in `ws.py` maintains `dict[patient_id, list[WebSocket]]`. Broadcasts on action create and transition. Frontend auto-reconnects on disconnect.

## API Endpoints

| Method  | Endpoint                          | Purpose                              |
|---------|-----------------------------------|--------------------------------------|
| `GET`   | `/health`                         | Health + DB check + timestamp        |
| `GET`   | `/demo/reset`                     | Wipe DB and re-seed                  |
| `GET`   | `/`                               | Patient list UI                      |
| `GET`   | `/patients/{id}/view`             | Patient dashboard UI                 |
| `POST`  | `/patients`                       | Create patient                       |
| `GET`   | `/patients`                       | List patients                        |
| `GET`   | `/patients/{id}`                  | Patient + actions with `is_overdue`  |
| `GET`   | `/patients/{id}/summary`          | Computed summary stats               |
| `POST`  | `/actions`                        | Create action (core or custom type)  |
| `GET`   | `/actions`                        | List all actions                     |
| `PATCH` | `/actions/{id}/transition`        | Advance state                        |
| `GET`   | `/actions/patients/{id}/timeline` | Chronological event log              |
| `POST`  | `/custom-action-types`            | Create custom action type            |
| `GET`   | `/custom-action-types`            | List custom types                    |
| `GET`   | `/custom-action-types/{id}`       | Get custom type                      |
| `WS`    | `/ws/patients/{id}`               | Real-time patient updates            |

## Key Design Decisions

- `action_type` OR `custom_action_type_id` — mutually exclusive, validated on creation
- SLA `is_overdue` is computed dynamically, never stored in DB
- ActionEvent is append-only — immutable audit trail
- Priority (ROUTINE/URGENT/CRITICAL) drives SLA deadlines and UI color coding
- Global exception handler returns `{"error": "Internal server error"}` — no stack traces leak
- Console logging on action create, transition, and demo reset
