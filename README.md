# Clavis

## 1. Project Title

**Clavis - Clinical Workflow Orchestration Engine**

## 2. Description

Clavis is a patient-centric hospital workflow platform built with FastAPI.  
It helps teams manage patient journeys (admission to discharge), coordinate actions across departments, and track SLAs in real time.

Core capabilities:
- Patient lifecycle management (admit, update, transfer, discharge)
- Role-based clinical action workflow and transitions
- Department queues (Nursing, Pharmacy, Laboratory, Radiology, Emergency)
- SLA tracking and escalation
- Notes, file attachments, analytics, audit log, and CSV/PDF exports
- Live UI refresh via WebSockets

## 3. Tech Stack Used

- **Backend:** Python 3.11+, FastAPI, SQLModel
- **Database:** SQLite
- **Frontend:** Jinja2 templates, TailwindCSS (CDN), vanilla JavaScript
- **Realtime:** WebSockets (Starlette/FastAPI)
- **Testing:** Pytest, FastAPI TestClient

## 4. How to Run the Project

1. Clone the repository and move into it.
```bash
git clone https://github.com/Suh7s/Clavis.git
cd Clavis
```

2. Create and activate a virtual environment.
```bash
python3 -m venv .venv
source .venv/bin/activate
```

3. Install dependencies.
```bash
pip install fastapi sqlmodel uvicorn jinja2 python-multipart pytest httpx
```

4. Seed the local database.
```bash
cd backend
python3 seed.py
```

5. Run the application.
```bash
cd backend
CLAVIS_ENABLE_DEMO_RESET=1 python3 -m uvicorn main:app --reload --port 8000
```

6. Open in browser.
- App login: [http://localhost:8000/login](http://localhost:8000/login)
- Swagger docs: [http://localhost:8000/docs](http://localhost:8000/docs)
- Health check: [http://localhost:8000/health](http://localhost:8000/health)

## 5. Dependencies

Direct dependencies used in this project:
- `fastapi`
- `sqlmodel`
- `uvicorn`
- `jinja2`
- `python-multipart`
- `pytest`
- `httpx`

Install command:
```bash
pip install fastapi sqlmodel uvicorn jinja2 python-multipart pytest httpx
```

## 6. Important Instructions

### Demo credentials
- `doctor@clavis.local / doctor123`
- `nurse@clavis.local / nurse123`
- `pharmacy@clavis.local / pharmacy123`
- `lab@clavis.local / lab123`
- `radiology@clavis.local / radiology123`
- `admin@clavis.local / admin123`

### Demo reset endpoint
- `GET /demo/reset` works only when `CLAVIS_ENABLE_DEMO_RESET=1` is set.
- Example:
```bash
curl http://localhost:8000/demo/reset
```

### Optional seed flags
- `CLAVIS_SEED_PATIENT=1` creates one demo patient
- `CLAVIS_SEED_ACTIONS=1` creates demo patient plus starter actions

### Key routes
- `/login`
- `/dashboard/view`
- `/patients/view`
- `/patients/{patient_id}/view`
- `/departments/{department}/view`
- `/status-board/view`
- `/analytics/view`
- `/audit-log/view`

### Basic verification
```bash
curl http://localhost:8000/health
```
Then manually verify:
- `/`
- `/patients/{id}/view`
- `PATCH /actions/{id}/transition` via UI or curl

## 7. Demo Videos of MVP

Add your MVP walkthrough links here:
- Full product walkthrough: `[Add link - Loom/YouTube/Drive]`
- Clinical workflow demo (admit -> action -> discharge): `[Add link]`
- Department queue + SLA escalation demo: `[Add link]`

## 8. Demo Images of MVP

Add screenshots here (recommended: create `docs/images/` and commit files):
- Login page screenshot: `[Add image path or URL]`
- Patient detail page screenshot: `[Add image path or URL]`
- Department board screenshot: `[Add image path or URL]`
- Analytics/status board screenshot: `[Add image path or URL]`

---

## Project Structure

```text
.
├── backend/
│   ├── main.py
│   ├── models.py
│   ├── database.py
│   ├── state_machine.py
│   ├── ws.py
│   ├── seed.py
│   ├── routers/
│   ├── services/
│   ├── templates/
│   ├── tests/
│   └── demo/
└── AGENTS.md
```

## Environment Variables

- `CLAVIS_DB_FILE` (default: `backend/clavis.db`)
- `CLAVIS_AUTH_SECRET` (set a strong value outside development)
- `CLAVIS_TOKEN_TTL_SECONDS` (default: `43200`)
- `CLAVIS_ENABLE_DEMO_RESET` (`1` to enable `/demo/reset`)
- `CLAVIS_SEED_PATIENT` (`1` to seed one demo patient)
- `CLAVIS_SEED_ACTIONS` (`1` to seed demo actions)
