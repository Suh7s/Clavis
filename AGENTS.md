# Repository Guidelines

## Project Structure & Module Organization
- `backend/` is the FastAPI app root and the working directory for most commands.
- `backend/main.py` boots the app, registers routers, serves templates, and owns the WS endpoint.
- `backend/routers/` contains API modules (`patients.py`, `actions.py`, `custom_types.py`).
- `backend/services/` holds domain helpers (for example, SLA logic in `sla.py`).
- `backend/state_machine.py` defines valid transitions; `backend/ws.py` manages WebSockets.
- `backend/templates/` contains Jinja2 HTML (`base.html`, `index.html`, `patient.html`).
- `backend/clavis.db` is the local SQLite file (gitignored).

## Build, Test, and Development Commands
- `pip install fastapi sqlmodel uvicorn jinja2` — install runtime dependencies (no lockfile yet).
- `cd backend && python3 seed.py` — seed demo data into `clavis.db`.
- `cd backend && python3 -m uvicorn main:app --reload --port 8000` — run the dev server.
- `curl http://localhost:8000/demo/reset` — wipe and re-seed demo data while running.

## Coding Style & Naming Conventions
- Use Python with 4-space indentation and PEP 8 conventions.
- Use `snake_case` for modules/functions and `PascalCase` for SQLModel classes.
- Keep FastAPI routers in `backend/routers/` with a module-level `router` object.
- Add new domain logic under `backend/services/`; keep templates in `backend/templates/`.

## Testing Guidelines
- No automated tests yet. Use manual checks:
  - `GET /health` for DB connectivity.
  - Open `/` and `/patients/{id}/view` for UI smoke tests.
  - Exercise `PATCH /actions/{id}/transition` via UI or `curl`.

## Commit & Pull Request Guidelines
- Git history is minimal; follow the existing descriptive summary style (example: `Clavis: <short scope>`).
- PRs should include: summary, verification steps, and screenshots for template/UI changes.

## Configuration & Data
- Local data (`backend/clavis.db`) and `.env` are gitignored—don’t commit them.
- The stack is intentionally lightweight (no Docker/Redis/Celery); document new services here.
