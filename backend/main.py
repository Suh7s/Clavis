import asyncio
from contextlib import asynccontextmanager, suppress
from datetime import datetime
import logging
import os
from pathlib import Path

from fastapi import FastAPI, HTTPException, Request, WebSocket, WebSocketDisconnect
from fastapi.responses import JSONResponse, HTMLResponse
from fastapi.templating import Jinja2Templates
from sqlmodel import Session, select, text

from database import create_db, engine
import models  # noqa: F401 — ensure tables are registered before create_db
from models import Attachment, ClinicalAction, ActionEvent, CustomActionType, PatientNote, PatientTransfer, User
from routers import patients, actions
from routers.analytics import router as analytics_router
from routers.auth import router as auth_router
from routers.custom_types import router as custom_types_router
from routers.export import router as export_router
from routers.files import UPLOAD_DIR, router as files_router
from routers.notes import router as notes_router
from routers.audit import router as audit_router
from services.access import can_access_department_queue
from services.auth import get_user_from_token
from services.safety_engine import SafetyEvent
from ws import manager

templates = Jinja2Templates(directory=str(Path(__file__).parent / "templates"))
logger = logging.getLogger("clavis")


async def _sla_checker():
    """Background task: check for overdue actions every 60 seconds and broadcast."""
    from services.sla import is_action_overdue, is_terminal_state
    from services.workflow import primary_queue_department

    while True:
        await asyncio.sleep(60)
        try:
            with Session(engine) as session:
                actions = session.exec(
                    select(ClinicalAction).where(ClinicalAction.current_state.notin_(  # type: ignore[union-attr]
                        ["COMPLETED", "ADMINISTERED", "CLOSED", "RECORDED", "FAILED", "CANCELLED"]
                    ))
                ).all()
                overdue_ids = []
                for action in actions:
                    ct = None
                    if action.custom_action_type_id:
                        ct = session.get(CustomActionType, action.custom_action_type_id)
                    custom_terminal = ct.terminal_state if ct else None
                    if is_action_overdue(action, custom_terminal):
                        overdue_ids.append(action.id)
                        dept = primary_queue_department(action, custom_terminal)
                        await manager.broadcast_department(dept, {
                            "event": "sla_overdue",
                            "action_id": action.id,
                            "patient_id": action.patient_id,
                            "current_state": action.current_state,
                            "timestamp": datetime.utcnow().isoformat(),
                        })
                if overdue_ids:
                    await manager.broadcast_status({
                        "event": "sla_check",
                        "overdue_count": len(overdue_ids),
                        "timestamp": datetime.utcnow().isoformat(),
                    })
        except Exception:
            logger.exception("SLA checker error")


@asynccontextmanager
async def lifespan(app: FastAPI):
    create_db()
    UPLOAD_DIR.mkdir(parents=True, exist_ok=True)
    sla_task = asyncio.create_task(_sla_checker())
    yield
    sla_task.cancel()
    with suppress(asyncio.CancelledError):
        await sla_task


app = FastAPI(title="Clavis", version="0.1.0", lifespan=lifespan)


@app.exception_handler(Exception)
async def global_exception_handler(request: Request, exc: Exception):
    logger.exception("Unhandled server error for %s %s", request.method, request.url.path)
    return JSONResponse(status_code=500, content={"error": "Internal server error"})


@app.middleware("http")
async def no_cache_api_responses(request: Request, call_next):
    response = await call_next(request)
    if request.url.path.startswith(
        (
            "/patients",
            "/actions",
            "/auth",
            "/custom-action-types",
            "/audit-log",
            "/analytics",
            "/export",
            "/files",
            "/api/v1/",
        )
    ):
        response.headers["Cache-Control"] = "no-store, max-age=0"
        response.headers["Pragma"] = "no-cache"
        response.headers["Expires"] = "0"
    return response


app.include_router(patients.router)
app.include_router(actions.router)
app.include_router(custom_types_router)
app.include_router(auth_router)
app.include_router(notes_router)
app.include_router(files_router)
app.include_router(audit_router)
app.include_router(analytics_router)
app.include_router(export_router)
app.include_router(patients.router, prefix="/api/v1")
app.include_router(actions.router, prefix="/api/v1")
app.include_router(custom_types_router, prefix="/api/v1")
app.include_router(auth_router, prefix="/api/v1")
app.include_router(notes_router, prefix="/api/v1")
app.include_router(files_router, prefix="/api/v1")
app.include_router(audit_router, prefix="/api/v1")
app.include_router(analytics_router, prefix="/api/v1")
app.include_router(export_router, prefix="/api/v1")


# --- Template routes ---

@app.get("/", response_class=HTMLResponse)
def index_page(request: Request):
    return templates.TemplateResponse("index.html", {"request": request})


@app.get("/dashboard/view", response_class=HTMLResponse)
def dashboard_page(request: Request):
    return templates.TemplateResponse("dashboard.html", {"request": request})


@app.get("/patients/view", response_class=HTMLResponse)
def patients_page(request: Request):
    return templates.TemplateResponse("patients.html", {"request": request})


@app.get("/patients/{patient_id}/view", response_class=HTMLResponse)
def patient_page(request: Request, patient_id: int):
    return templates.TemplateResponse("patient_detail.html", {"request": request, "patient_id": patient_id})


@app.get("/login", response_class=HTMLResponse)
def login_page(request: Request):
    return templates.TemplateResponse("login.html", {"request": request})


@app.get("/departments/{department}/view", response_class=HTMLResponse)
def department_page(request: Request, department: str):
    return templates.TemplateResponse("department.html", {"request": request, "department": department})


@app.get("/status-board/view", response_class=HTMLResponse)
def status_board_page(request: Request):
    return templates.TemplateResponse("status_board.html", {"request": request})


@app.get("/audit-log/view", response_class=HTMLResponse)
def audit_log_page(request: Request):
    return templates.TemplateResponse("audit_log.html", {"request": request})


@app.get("/analytics/view", response_class=HTMLResponse)
def analytics_page(request: Request):
    return templates.TemplateResponse("analytics.html", {"request": request})


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
    if os.getenv("CLAVIS_ENABLE_DEMO_RESET", "0") != "1":
        raise HTTPException(status_code=404, detail="Not found")

    print("[DEMO] Reset triggered")
    create_db()
    with Session(engine) as session:
        session.exec(Attachment.__table__.delete())  # type: ignore[arg-type]
        session.exec(PatientTransfer.__table__.delete())  # type: ignore[arg-type]
        session.exec(ActionEvent.__table__.delete())  # type: ignore[arg-type]
        session.exec(ClinicalAction.__table__.delete())  # type: ignore[arg-type]
        session.exec(CustomActionType.__table__.delete())  # type: ignore[arg-type]
        session.exec(SafetyEvent.__table__.delete())  # type: ignore[arg-type]
        session.exec(PatientNote.__table__.delete())  # type: ignore[arg-type]
        session.exec(models.Patient.__table__.delete())  # type: ignore[arg-type]
        session.exec(User.__table__.delete())  # type: ignore[arg-type]
        session.commit()
    for path in UPLOAD_DIR.glob("*"):
        if path.is_file():
            path.unlink(missing_ok=True)

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
