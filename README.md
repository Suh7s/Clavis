# Clavis

Clinical workflow orchestration engine for patient-centric hospital operations.

Clavis is a FastAPI + SQLModel application with a server-rendered Jinja2 UI and live WebSocket updates for patient threads, department queues, and the global status board.

## Core capabilities

- Patient lifecycle management (admit, update, transfer, discharge).
- Clinical action orchestration with role-based state transitions.
- Department queues (Nursing, Pharmacy, Laboratory, Radiology, Emergency).
- SLA tracking with overdue escalation signals.
- Live UI updates over WebSockets.
- Notes, attachments, analytics, audit log, and export (CSV/PDF).

## Tech stack

- Python 3.11+ (validated on Python 3.13).
- FastAPI
- SQLModel + SQLite
- Jinja2 templates + Tailwind (CDN)
- WebSockets (Starlette/FastAPI)
- Pytest + FastAPI TestClient

## Repository layout

```text
.
├── backend/
│   ├── main.py                 # FastAPI app + template routes + WS endpoints
│   ├── models.py               # SQLModel entities
│   ├── database.py             # DB engine/session/bootstrap
│   ├── state_machine.py        # Action transition rules
│   ├── ws.py                   # WebSocket connection manager
│   ├── seed.py                 # Demo seed script
│   ├── routers/                # API routers (patients/actions/auth/etc.)
│   ├── services/               # Domain logic (auth/sla/workflow/access)
│   ├── templates/              # Jinja2 UI templates
│   ├── tests/                  # Pytest suite
│   └── demo/                   # DPR checklist + demo automation scripts
└── AGENTS.md
```

## Quick start

1. Create a virtual environment and install dependencies.

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install fastapi sqlmodel uvicorn jinja2 python-multipart pytest httpx
```

2. Seed users (and optionally demo data).

```bash
cd backend
python3 seed.py
```

Optional seed flags:

- `CLAVIS_SEED_PATIENT=1` creates one demo patient.
- `CLAVIS_SEED_ACTIONS=1` creates demo patient + starter actions.

3. Run the app.

```bash
cd backend
CLAVIS_ENABLE_DEMO_RESET=1 python3 -m uvicorn main:app --reload --port 8000
```

4. Open the app.

- UI: [http://localhost:8000/login](http://localhost:8000/login)
- API docs (Swagger): [http://localhost:8000/docs](http://localhost:8000/docs)
- Health: [http://localhost:8000/health](http://localhost:8000/health)

## Demo accounts

- `doctor@clavis.local / doctor123`
- `nurse@clavis.local / nurse123`
- `pharmacy@clavis.local / pharmacy123`
- `lab@clavis.local / lab123`
- `radiology@clavis.local / radiology123`
- `admin@clavis.local / admin123`

## Demo reset

`/demo/reset` is disabled by default and only available when:

```bash
CLAVIS_ENABLE_DEMO_RESET=1
```

Example:

```bash
curl http://localhost:8000/demo/reset
```

## Main UI routes

- `/login`
- `/dashboard/view`
- `/patients/view`
- `/patients/{patient_id}/view`
- `/departments/{department}/view`
- `/status-board/view`
- `/analytics/view`
- `/audit-log/view`

## API summary

Unversioned and `/api/v1` prefixed endpoints are both available.

- Auth: `/auth/login`, `/auth/me`
- Patients: CRUD, timeline, summary, transfer, discharge, status-board
- Actions: create/update/transition, bulk operations, department queue, escalations
- Notes: `/patients/{id}/notes`
- Files: `/patients/{id}/files`, `/files/{file_id}`
- Custom action types: `/custom-action-types`
- Audit: `/audit-log`
- Analytics: `/analytics`
- Export: patient CSV/PDF and audit CSV

Use `Authorization: Bearer <token>` for protected endpoints.

## WebSocket endpoints

- `/ws/patients/{patient_id}`
- `/ws/department/{department}`
- `/ws/status-board`

Pass auth token as query param:

```text
?token=<access_token>
```

## Tests

Run from `backend/`:

```bash
cd backend
pytest -q
```

Current baseline in this workspace: `19 passed`.

## DPR demo scripts

From `backend/`:

```bash
python3 demo/preflight_checks.py
python3 demo/dpr_demo_run.py
```

Detailed click-path checklist:

- `backend/demo/DPR_DEMO_CHECKLIST.md`

## Environment variables

- `CLAVIS_DB_FILE` (default: `backend/clavis.db`)
- `CLAVIS_AUTH_SECRET` (default: dev value in code; set in production)
- `CLAVIS_TOKEN_TTL_SECONDS` (default: 43200 / 12h)
- `CLAVIS_ENABLE_DEMO_RESET` (`1` to enable `/demo/reset`)
- `CLAVIS_SEED_PATIENT` (`1` to seed a demo patient)
- `CLAVIS_SEED_ACTIONS` (`1` to seed demo actions)

## Notes for production hardening

- Replace default `CLAVIS_AUTH_SECRET` with a strong secret.
- Move from local SQLite to a managed DB if concurrency/load grows.
- Serve Tailwind assets through your build pipeline or trusted CDN policy.
- Add CI for tests and linting.

