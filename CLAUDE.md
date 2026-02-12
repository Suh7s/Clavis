# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Commands

```bash
# Install dependencies
pip install fastapi sqlmodel uvicorn jinja2 python-multipart pytest httpx

# Seed demo data (run from backend/)
cd backend && python3 seed.py

# Run dev server (run from backend/)
cd backend && python3 -m uvicorn main:app --reload --port 8000

# Run all tests (run from backend/)
cd backend && pytest -q

# Run a single test file
cd backend && pytest tests/test_actions.py -q

# Run a single test function
cd backend && pytest tests/test_actions.py::test_create_action -q

# Reset demo data (server must be running, requires CLAVIS_ENABLE_DEMO_RESET=1)
curl http://localhost:8000/demo/reset

# Run preflight validation checks (run from backend/)
CLAVIS_ENABLE_DEMO_RESET=1 python3 demo/preflight_checks.py

# Run automated 9-step demo (run from backend/)
CLAVIS_ENABLE_DEMO_RESET=1 python3 demo/dpr_demo_run.py
```

### Testing

Tests use pytest with FastAPI TestClient against an in-memory SQLite database (see `tests/conftest.py`). Each test gets a fresh DB via the `reset_db` autouse fixture. Shared fixtures provide pre-authenticated headers for each role (`doctor_headers`, `nurse_headers`, etc.) and a `patient_id` factory. Additional validation via `demo/preflight_checks.py` (8 checks covering RBAC, events, WebSocket, custom types, status board) and `demo/dpr_demo_run.py` (end-to-end workflow).

## Environment Variables

| Variable | Default | Purpose |
|---|---|---|
| `CLAVIS_DB_FILE` | `backend/clavis.db` | SQLite file path |
| `CLAVIS_AUTH_SECRET` | `clavis-dev-secret-change-me` | JWT HMAC-SHA256 signing secret |
| `CLAVIS_TOKEN_TTL_SECONDS` | `43200` (12h) | JWT expiry |
| `CLAVIS_ENABLE_DEMO_RESET` | unset | Must be `"1"` to enable `/demo/reset` |
| `CLAVIS_SEED_PATIENT` / `CLAVIS_SEED_ACTIONS` | unset | Set to `"1"` to include demo patient/actions in seed |

## Architecture

### Request Flow

All API routers are mounted at both `/` and `/api/v1/` prefixes. Routers: `patients`, `actions`, `auth`, `notes`, `files`, `custom_types`, `audit`, `analytics`, `export`. Template routes serve Jinja2 HTML at `/`, `/login`, `/dashboard/view`, `/patients/view`, `/patients/{id}/view`, `/departments/{department}/view`, `/status-board/view`, `/audit-log/view`, `/analytics/view`. Auth is JWT Bearer tokens stored in `sessionStorage` on the frontend; `base.html` has a global fetch interceptor that attaches tokens and redirects to `/login` on 401.

### Patient Management

`GET /patients` returns paginated results `{patients, total, page, page_size}` with optional `?search=`, `?include_inactive=true`, `?page=`, `?page_size=` query params. `PATCH /patients/{id}` updates patient fields (doctor/admin). `DELETE /patients/{id}` performs soft delete (sets `is_active=False`). Notes: `POST /patients/{id}/notes` and `GET /patients/{id}/notes`.

### State Machine (`state_machine.py`)

Central workflow engine. `VALID_TRANSITIONS` dict maps each `ActionType` to allowed `{current_state: [next_states]}`. Transitions are validated server-side; invalid ones return 422. Custom action types build their transition map dynamically from an ordered `states` list (sequential-forward only). `TERMINAL_STATES` = {COMPLETED, ADMINISTERED, CLOSED, RECORDED, FAILED, CANCELLED}.

### RBAC (`services/access.py`)

`roles_allowed_for_transition()` enforces per-action-type, per-state role restrictions. For example, only PHARMACIST can dispense medications, only NURSE can administer. ADMIN bypasses all department restrictions. Department queue access is gated by `DEPARTMENT_ROLE_MAP`.

### Action Routing (`services/workflow.py`)

Actions auto-route to departments on creation: MEDICATION → Pharmacy, DIAGNOSTIC → Laboratory or Radiology (keyword detection on title: xray, ct, mri, ultrasound, scan), REFERRAL → Referral, CARE_INSTRUCTION/VITALS_REQUEST → Nursing. Multi-hop: medications move from Pharmacy queue (PRESCRIBED) to Nursing queue (DISPENSED).

### SLA (`services/sla.py`)

`is_overdue` is **always computed dynamically** (never stored in DB). Core SLA: ROUTINE=2h, URGENT=30m, CRITICAL=10m. Custom types define their own per-priority SLA minutes. Terminal states are never overdue. A background task (`_sla_checker` in `main.py`) runs every 60 seconds, broadcasting overdue actions to department and status board WebSocket channels.

### WebSocket (`ws.py`)

`ConnectionManager` maintains three in-memory connection pools: per-patient, per-department (case-folded keys), and global status board. Broadcasts fire on action create and transition. Frontend auto-reconnects every 2 seconds on disconnect. WS endpoints authenticate via query param token.

### Models (`models.py`)

`Patient` includes `blood_group`, `admission_date`, `ward`, `primary_doctor_id` (FK User), and `is_active` (soft delete flag). `ClinicalAction` has **mutually exclusive** `action_type` (core enum) OR `custom_action_type_id` (FK) — never both, validated on creation. `ClinicalAction.updated_at` is set on edit/transition. `ActionEvent` is append-only (immutable audit trail). `PatientNote` stores free-text clinical notes per patient (author, note_type, content). `CustomActionType.states_json` stores ordered states as a JSON string with a property accessor.

### Files & Attachments (`routers/files.py`)

File uploads stored in `backend/uploads/` (created at startup). Attached to patients via the `Attachment` model. Upload endpoint at `POST /patients/{id}/files`, download at `GET /files/{file_id}`.

### Database (`database.py`)

SQLite with `check_same_thread=False`. Has automatic schema rebuild: `_schema_needs_rebuild()` checks required columns and drops/recreates all tables if schema drifts. The `get_session()` dependency yields SQLModel sessions.

## Coding Conventions

- Python 4-space indent, PEP 8, `snake_case` functions, `PascalCase` for SQLModel classes
- Routers go in `backend/routers/` with a module-level `router = APIRouter()` object
- Domain logic goes in `backend/services/`
- Templates in `backend/templates/`, extending `base.html`
- Frontend is vanilla JS + Tailwind CDN — no build step
- Commit style: `Clavis: <short scope>`

## Demo Credentials

| Role | Email | Password |
|---|---|---|
| Doctor | doctor@clavis.local | doctor123 |
| Nurse | nurse@clavis.local | nurse123 |
| Pharmacist | pharmacy@clavis.local | pharmacy123 |
| Lab Tech | lab@clavis.local | lab123 |
| Radiologist | radiology@clavis.local | radiology123 |
| Admin | admin@clavis.local | admin123 |
