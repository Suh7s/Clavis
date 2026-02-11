from contextlib import asynccontextmanager
from datetime import datetime
from pathlib import Path

from fastapi import FastAPI, WebSocket, WebSocketDisconnect, Request
from fastapi.responses import JSONResponse, HTMLResponse
from fastapi.templating import Jinja2Templates
from sqlmodel import Session, text

from database import create_db, engine
import models  # noqa: F401 — ensure tables are registered before create_db
from models import ClinicalAction, ActionEvent, CustomActionType
from routers import patients, actions
from routers.custom_types import router as custom_types_router
from ws import manager

templates = Jinja2Templates(directory=str(Path(__file__).parent / "templates"))


@asynccontextmanager
async def lifespan(app: FastAPI):
    create_db()
    yield


app = FastAPI(title="Clavis", version="0.1.0", lifespan=lifespan)


@app.exception_handler(Exception)
async def global_exception_handler(request: Request, exc: Exception):
    return JSONResponse(status_code=500, content={"error": "Internal server error"})


app.include_router(patients.router)
app.include_router(actions.router)
app.include_router(custom_types_router)


# --- Template routes ---

@app.get("/", response_class=HTMLResponse)
def index_page(request: Request):
    return templates.TemplateResponse("index.html", {"request": request})


@app.get("/patients/{patient_id}/view", response_class=HTMLResponse)
def patient_page(request: Request, patient_id: int):
    return templates.TemplateResponse("patient.html", {"request": request, "patient_id": patient_id})


# --- API routes ---

@app.get("/health")
def health():
    try:
        with Session(engine) as session:
            session.exec(text("SELECT 1"))
        return {
            "status": "ok",
            "database": "connected",
            "timestamp": datetime.utcnow().isoformat(),
        }
    except Exception:
        return JSONResponse(status_code=500, content={"status": "error"})


@app.get("/demo/reset")
def demo_reset():
    print("[DEMO] Reset triggered")
    with Session(engine) as session:
        session.exec(ActionEvent.__table__.delete())  # type: ignore[arg-type]
        session.exec(ClinicalAction.__table__.delete())  # type: ignore[arg-type]
        session.exec(CustomActionType.__table__.delete())  # type: ignore[arg-type]
        session.exec(models.Patient.__table__.delete())  # type: ignore[arg-type]
        session.commit()

    from seed import run_seed
    run_seed()

    return {"status": "demo reset complete"}


@app.websocket("/ws/patients/{patient_id}")
async def patient_ws(websocket: WebSocket, patient_id: int):
    await manager.connect(patient_id, websocket)
    try:
        while True:
            await websocket.receive_text()
    except WebSocketDisconnect:
        manager.disconnect(patient_id, websocket)
