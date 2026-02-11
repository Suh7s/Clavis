from datetime import datetime
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import JSONResponse
from pydantic import BaseModel
from sqlmodel import Session, select

from database import get_session
from models import ActionType, Priority, ClinicalAction, ActionEvent, Patient, CustomActionType
from state_machine import INITIAL_STATES, validate_transition, validate_custom_transition
from services.sla import compute_sla_deadline, compute_custom_sla_deadline, is_action_overdue
from ws import manager

router = APIRouter(prefix="/actions", tags=["actions"])

DEPARTMENT_MAP = {
    ActionType.DIAGNOSTIC: "Laboratory",
    ActionType.MEDICATION: "Pharmacy",
    ActionType.REFERRAL: "Referral",
    ActionType.CARE_INSTRUCTION: "Nursing",
}


def _get_custom_terminal(action: ClinicalAction, session: Session) -> str | None:
    if action.custom_action_type_id is None:
        return None
    cat = session.get(CustomActionType, action.custom_action_type_id)
    return cat.terminal_state if cat else None


def action_response(action: ClinicalAction, session: Session) -> dict:
    data = action.model_dump()
    custom_terminal = _get_custom_terminal(action, session)
    data["is_overdue"] = is_action_overdue(action, custom_terminal)
    if action.custom_action_type_id:
        cat = session.get(CustomActionType, action.custom_action_type_id)
        if cat:
            data["custom_type_name"] = cat.name
    return data


class ActionCreate(BaseModel):
    patient_id: int
    action_type: Optional[ActionType] = None
    custom_action_type_id: Optional[int] = None
    priority: Priority = Priority.ROUTINE


class TransitionRequest(BaseModel):
    new_state: str


@router.post("", status_code=201)
async def create_action(body: ActionCreate, session: Session = Depends(get_session)):
    if body.action_type and body.custom_action_type_id:
        raise HTTPException(422, "Set action_type OR custom_action_type_id, not both")
    if not body.action_type and not body.custom_action_type_id:
        raise HTTPException(422, "Must set action_type or custom_action_type_id")

    patient = session.get(Patient, body.patient_id)
    if not patient:
        raise HTTPException(404, "Patient not found")

    if body.custom_action_type_id:
        cat = session.get(CustomActionType, body.custom_action_type_id)
        if not cat:
            raise HTTPException(404, "Custom action type not found")
        initial_state = cat.states[0]
        department = cat.department
        sla_deadline = compute_custom_sla_deadline(body.priority, cat)
        label = cat.name
    else:
        initial_state = INITIAL_STATES[body.action_type]
        department = DEPARTMENT_MAP[body.action_type]
        sla_deadline = compute_sla_deadline(body.priority)
        label = body.action_type.value

    action = ClinicalAction(
        patient_id=body.patient_id,
        action_type=body.action_type,
        custom_action_type_id=body.custom_action_type_id,
        current_state=initial_state,
        priority=body.priority,
        department=department,
        sla_deadline=sla_deadline,
    )
    session.add(action)
    session.commit()
    session.refresh(action)

    event = ActionEvent(
        action_id=action.id,
        previous_state="",
        new_state=initial_state,
    )
    session.add(event)
    session.commit()
    session.refresh(action)

    resp = action_response(action, session)
    print(f"[ACTION] Created #{action.id} {label} for patient #{body.patient_id}")

    await manager.broadcast(body.patient_id, {
        "event": "action_created",
        "action_id": action.id,
        "patient_id": body.patient_id,
        "new_state": action.current_state,
        "is_overdue": resp["is_overdue"],
        "timestamp": datetime.utcnow().isoformat(),
    })

    return resp


@router.patch("/{action_id}/transition")
async def transition_action(
    action_id: int,
    body: TransitionRequest,
    session: Session = Depends(get_session),
):
    action = session.get(ClinicalAction, action_id)
    if not action:
        raise HTTPException(404, "Action not found")

    try:
        if action.custom_action_type_id:
            cat = session.get(CustomActionType, action.custom_action_type_id)
            if not cat:
                raise HTTPException(404, "Custom action type not found")
            validate_custom_transition(cat, action.current_state, body.new_state)
        else:
            validate_transition(action.action_type, action.current_state, body.new_state)
    except ValueError:
        return JSONResponse(status_code=422, content={"error": "Invalid state transition"})

    prev = action.current_state
    action.current_state = body.new_state
    session.add(action)

    event = ActionEvent(
        action_id=action.id,
        previous_state=prev,
        new_state=body.new_state,
    )
    session.add(event)

    try:
        session.commit()
        session.refresh(action)
    except Exception:
        session.rollback()
        return JSONResponse(status_code=500, content={"error": "Failed to save transition"})

    resp = action_response(action, session)
    print(f"[TRANSITION] Action #{action_id}: {prev} -> {body.new_state}")

    await manager.broadcast(action.patient_id, {
        "event": "action_updated",
        "action_id": action.id,
        "patient_id": action.patient_id,
        "new_state": body.new_state,
        "is_overdue": resp["is_overdue"],
        "timestamp": datetime.utcnow().isoformat(),
    })

    return resp


@router.get("/patients/{patient_id}/timeline")
def patient_timeline(patient_id: int, session: Session = Depends(get_session)):
    patient = session.get(Patient, patient_id)
    if not patient:
        raise HTTPException(404, "Patient not found")

    actions = session.exec(
        select(ClinicalAction).where(ClinicalAction.patient_id == patient_id)
    ).all()

    action_ids = [a.id for a in actions]
    if not action_ids:
        return []

    # Build action_id -> display name map
    name_map: dict[int, str] = {}
    for a in actions:
        if a.custom_action_type_id:
            cat = session.get(CustomActionType, a.custom_action_type_id)
            name_map[a.id] = cat.name if cat else "Custom"
        else:
            name_map[a.id] = a.action_type.value if a.action_type else "Unknown"

    events = session.exec(
        select(ActionEvent)
        .where(ActionEvent.action_id.in_(action_ids))  # type: ignore[union-attr]
        .order_by(ActionEvent.timestamp.asc())  # type: ignore[union-attr]
    ).all()

    results = []
    for e in events:
        d = e.model_dump()
        d["action_name"] = name_map.get(e.action_id, "Unknown")
        results.append(d)

    return results


@router.get("")
def list_actions(session: Session = Depends(get_session)):
    actions = session.exec(select(ClinicalAction)).all()
    return [action_response(a, session) for a in actions]
