from contextlib import asynccontextmanager
from datetime import datetime
import logging
import os
from pathlib import Path

from fastapi import FastAPI, HTTPException, Request, WebSocket, WebSocketDisconnect
from fastapi.responses import JSONResponse, HTMLResponse
from fastapi.templating import Jinja2Templates
from sqlmodel import Session, text

from database import create_db, engine
import models  # noqa: F401 — ensure tables are registered before create_db
from models import ClinicalAction, ActionEvent, CustomActionType, User
from routers import patients, actions
from routers.auth import router as auth_router
from routers.custom_types import router as custom_types_router
from services.access import can_access_department_queue
from services.auth import get_user_from_token
from ws import manager

templates = Jinja2Templates(directory=str(Path(__file__).parent / "templates"))
logger = logging.getLogger("clavis")


@asynccontextmanager
async def lifespan(app: FastAPI):
    create_db()
    yield


app = FastAPI(title="Clavis", version="0.1.0", lifespan=lifespan)


@app.exception_handler(Exception)
async def global_exception_handler(request: Request, exc: Exception):
    logger.exception("Unhandled server error for %s %s", request.method, request.url.path)
    return JSONResponse(status_code=500, content={"error": "Internal server error"})


app.include_router(patients.router)
app.include_router(actions.router)
app.include_router(custom_types_router)
app.include_router(auth_router)
app.include_router(patients.router, prefix="/api/v1")
app.include_router(actions.router, prefix="/api/v1")
app.include_router(custom_types_router, prefix="/api/v1")
app.include_router(auth_router, prefix="/api/v1")


# --- Template routes ---

@app.get("/", response_class=HTMLResponse)
def index_page(request: Request):
    return templates.TemplateResponse("index.html", {"request": request})


@app.get("/patients/{patient_id}/view", response_class=HTMLResponse)
def patient_page(request: Request, patient_id: int):
    return templates.TemplateResponse("patient.html", {"request": request, "patient_id": patient_id})


@app.get("/login", response_class=HTMLResponse)
def login_page(request: Request):
    return templates.TemplateResponse("login.html", {"request": request})


@app.get("/departments/{department}/view", response_class=HTMLResponse)
def department_page(request: Request, department: str):
    return templates.TemplateResponse("department.html", {"request": request, "department": department})


@app.get("/status-board/view", response_class=HTMLResponse)
def status_board_page(request: Request):
    return templates.TemplateResponse("status_board.html", {"request": request})


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
    if os.getenv("CLAVIS_ENABLE_DEMO_RESET", "1") != "1":
        raise HTTPException(status_code=404, detail="Not found")

    print("[DEMO] Reset triggered")
    create_db()
    with Session(engine) as session:
        session.exec(ActionEvent.__table__.delete())  # type: ignore[arg-type]
        session.exec(ClinicalAction.__table__.delete())  # type: ignore[arg-type]
        session.exec(CustomActionType.__table__.delete())  # type: ignore[arg-type]
        session.exec(models.Patient.__table__.delete())  # type: ignore[arg-type]
        session.exec(User.__table__.delete())  # type: ignore[arg-type]
        session.commit()

    from seed import run_seed
    run_seed()

    return {"status": "demo reset complete"}


@app.websocket("/ws/patients/{patient_id}")
async def patient_ws(websocket: WebSocket, patient_id: int):
    token = websocket.query_params.get("token")
    if not token:
        await websocket.close(code=1008)
        return

    try:
        with Session(engine) as session:
            get_user_from_token(token, session)
    except Exception:
        await websocket.close(code=1008)
        return

    await manager.connect_patient(patient_id, websocket)
    try:
        while True:
            await websocket.receive_text()
    except WebSocketDisconnect:
        manager.disconnect_patient(patient_id, websocket)


@app.websocket("/ws/department/{department}")
async def department_ws(websocket: WebSocket, department: str):
    token = websocket.query_params.get("token")
    if not token:
        await websocket.close(code=1008)
        return

    try:
        with Session(engine) as session:
            user = get_user_from_token(token, session)
            if not can_access_department_queue(user.role, department):
                await websocket.close(code=1008)
                return
    except Exception:
        await websocket.close(code=1008)
        return

    await manager.connect_department(department, websocket)
    try:
        while True:
            await websocket.receive_text()
    except WebSocketDisconnect:
        manager.disconnect_department(department, websocket)


@app.websocket("/ws/status-board")
async def status_board_ws(websocket: WebSocket):
    token = websocket.query_params.get("token")
    if not token:
        await websocket.close(code=1008)
        return

    try:
        with Session(engine) as session:
            get_user_from_token(token, session)
    except Exception:
        await websocket.close(code=1008)
        return

    await manager.connect_status(websocket)
    try:
        while True:
            await websocket.receive_text()
    except WebSocketDisconnect:
        manager.disconnect_status(websocket)
