from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlmodel import Session, select

from database import get_session
from models import Patient, ClinicalAction, ActionEvent, CustomActionType
from services.sla import is_action_overdue, is_terminal_state

router = APIRouter(prefix="/patients", tags=["patients"])


class PatientCreate(BaseModel):
    name: str
    age: int
    gender: str


def _custom_terminal(action: ClinicalAction, session: Session) -> str | None:
    if action.custom_action_type_id is None:
        return None
    cat = session.get(CustomActionType, action.custom_action_type_id)
    return cat.terminal_state if cat else None


def _action_with_overdue(action: ClinicalAction, session: Session) -> dict:
    d = action.model_dump()
    ct = _custom_terminal(action, session)
    d["is_overdue"] = is_action_overdue(action, ct)
    if action.custom_action_type_id:
        cat = session.get(CustomActionType, action.custom_action_type_id)
        if cat:
            d["custom_type_name"] = cat.name
    return d


def _initial_state_for(action: ClinicalAction, session: Session) -> bool:
    """Return True if action is in its initial state."""
    if action.custom_action_type_id:
        cat = session.get(CustomActionType, action.custom_action_type_id)
        if cat:
            return action.current_state == cat.states[0]
    return action.current_state in ("REQUESTED", "PRESCRIBED", "INITIATED", "ISSUED")


@router.post("", status_code=201)
def create_patient(body: PatientCreate, session: Session = Depends(get_session)):
    patient = Patient(**body.model_dump())
    session.add(patient)
    session.commit()
    session.refresh(patient)
    return patient


@router.get("")
def list_patients(session: Session = Depends(get_session)):
    return session.exec(select(Patient)).all()


@router.get("/{patient_id}")
def get_patient(patient_id: int, session: Session = Depends(get_session)):
    patient = session.get(Patient, patient_id)
    if not patient:
        raise HTTPException(404, "Patient not found")

    actions = session.exec(
        select(ClinicalAction)
        .where(ClinicalAction.patient_id == patient_id)
        .order_by(ClinicalAction.created_at.asc())  # type: ignore[union-attr]
    ).all()

    result = patient.model_dump()
    result["actions"] = [_action_with_overdue(a, session) for a in actions]
    return result


@router.get("/{patient_id}/summary")
def patient_summary(patient_id: int, session: Session = Depends(get_session)):
    patient = session.get(Patient, patient_id)
    if not patient:
        raise HTTPException(404, "Patient not found")

    actions = session.exec(
        select(ClinicalAction).where(ClinicalAction.patient_id == patient_id)
    ).all()

    completed = 0
    in_progress = 0
    pending = 0
    overdue = 0
    last_updated: datetime | None = None

    for a in actions:
        ct = _custom_terminal(a, session)
        if is_terminal_state(a.action_type, a.current_state, ct):
            completed += 1
        elif _initial_state_for(a, session):
            pending += 1
        else:
            in_progress += 1

        if is_action_overdue(a, ct):
            overdue += 1

    if actions:
        action_ids = [a.id for a in actions]
        latest_event = session.exec(
            select(ActionEvent)
            .where(ActionEvent.action_id.in_(action_ids))  # type: ignore[union-attr]
            .order_by(ActionEvent.timestamp.desc())  # type: ignore[union-attr]
        ).first()
        if latest_event:
            last_updated = latest_event.timestamp

    return {
        "total_actions": len(actions),
        "completed": completed,
        "in_progress": in_progress,
        "pending": pending,
        "overdue": overdue,
        "last_updated": last_updated.isoformat() if last_updated else None,
    }
