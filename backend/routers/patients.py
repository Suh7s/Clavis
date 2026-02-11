from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlmodel import Session, select

from database import get_session
from models import ActionEvent, ClinicalAction, CustomActionType, Patient, User
from services.auth import get_current_user
from services.sla import is_action_overdue, is_terminal_state
from services.workflow import primary_queue_department, queue_departments_for_action

router = APIRouter(prefix="/patients", tags=["patients"])


class PatientCreate(BaseModel):
    name: str = Field(min_length=1, max_length=120)
    age: int = Field(ge=0, le=130)
    gender: str = Field(min_length=1, max_length=32)


def _custom_type(action: ClinicalAction, session: Session) -> CustomActionType | None:
    if action.custom_action_type_id is None:
        return None
    return session.get(CustomActionType, action.custom_action_type_id)


def _custom_terminal(action: ClinicalAction, session: Session) -> str | None:
    custom_type = _custom_type(action, session)
    return custom_type.terminal_state if custom_type else None


def _action_name(action: ClinicalAction, session: Session) -> str:
    custom_type = _custom_type(action, session)
    if custom_type:
        return custom_type.name
    if action.action_type is None:
        return "Unknown"
    return action.action_type.value


def _action_with_overdue(action: ClinicalAction, session: Session) -> dict:
    data = action.model_dump()
    custom_type = _custom_type(action, session)
    custom_terminal = custom_type.terminal_state if custom_type else None

    queue_departments = queue_departments_for_action(action, custom_terminal)
    data["is_overdue"] = is_action_overdue(action, custom_terminal)
    data["queue_departments"] = queue_departments
    data["queue_department"] = primary_queue_department(action, custom_terminal)
    data["is_terminal"] = len(queue_departments) == 0
    if custom_type:
        data["custom_type_name"] = custom_type.name
    return data


def _initial_state_for(action: ClinicalAction, session: Session) -> bool:
    if action.custom_action_type_id:
        custom_type = _custom_type(action, session)
        if custom_type:
            return action.current_state == custom_type.states[0]
    return action.current_state in ("REQUESTED", "PRESCRIBED", "INITIATED", "ISSUED")


def _compute_counts(actions: list[ClinicalAction], session: Session) -> dict:
    completed = 0
    in_progress = 0
    pending = 0
    overdue = 0

    for action in actions:
        custom_terminal = _custom_terminal(action, session)
        if is_terminal_state(action.action_type, action.current_state, custom_terminal):
            completed += 1
        elif _initial_state_for(action, session):
            pending += 1
        else:
            in_progress += 1

        if is_action_overdue(action, custom_terminal):
            overdue += 1

    return {
        "completed": completed,
        "in_progress": in_progress,
        "pending": pending,
        "overdue": overdue,
    }


def _latest_patient_event(patient_id: int, session: Session) -> ActionEvent | None:
    actions = session.exec(select(ClinicalAction.id).where(ClinicalAction.patient_id == patient_id)).all()
    action_ids = [action_id for action_id in actions if action_id is not None]
    if not action_ids:
        return None

    return session.exec(
        select(ActionEvent)
        .where(ActionEvent.action_id.in_(action_ids))  # type: ignore[union-attr]
        .order_by(ActionEvent.timestamp.desc())  # type: ignore[union-attr]
    ).first()


@router.post("", status_code=201)
def create_patient(
    body: PatientCreate,
    session: Session = Depends(get_session),
    _current_user: User = Depends(get_current_user),
):
    name = body.name.strip()
    gender = body.gender.strip()
    if not name:
        raise HTTPException(422, "Patient name cannot be empty")
    if not gender:
        raise HTTPException(422, "Gender cannot be empty")

    patient = Patient(
        name=name,
        age=body.age,
        gender=gender,
    )
    session.add(patient)
    try:
        session.commit()
        session.refresh(patient)
    except Exception:
        session.rollback()
        raise HTTPException(500, "Failed to create patient")
    return patient


@router.get("")
def list_patients(
    session: Session = Depends(get_session),
    _current_user: User = Depends(get_current_user),
):
    return session.exec(select(Patient).order_by(Patient.created_at.asc())).all()


@router.get("/status-board")
def status_board(
    session: Session = Depends(get_session),
    _current_user: User = Depends(get_current_user),
):
    patients = session.exec(select(Patient).order_by(Patient.created_at.asc())).all()
    rows = []
    total_overdue = 0

    for patient in patients:
        actions = session.exec(
            select(ClinicalAction)
            .where(ClinicalAction.patient_id == patient.id)
            .order_by(ClinicalAction.created_at.asc())  # type: ignore[union-attr]
        ).all()
        counts = _compute_counts(actions, session)
        total_overdue += counts["overdue"]

        bottleneck_department = None
        for action in actions:
            data = _action_with_overdue(action, session)
            if data["is_overdue"]:
                bottleneck_department = data["queue_department"]
                break
        if bottleneck_department is None:
            for action in actions:
                data = _action_with_overdue(action, session)
                if not data["is_terminal"]:
                    bottleneck_department = data["queue_department"]
                    break

        latest_event = _latest_patient_event(patient.id, session)

        rows.append(
            {
                "patient_id": patient.id,
                "patient_name": patient.name,
                "pending": counts["pending"],
                "in_progress": counts["in_progress"],
                "completed": counts["completed"],
                "overdue": counts["overdue"],
                "bottleneck_department": bottleneck_department,
                "last_updated": latest_event.timestamp.isoformat() if latest_event else None,
            }
        )

    return {
        "total_patients": len(rows),
        "overdue_actions": total_overdue,
        "patients": rows,
    }


@router.get("/{patient_id}/timeline")
def patient_timeline(
    patient_id: int,
    session: Session = Depends(get_session),
    _current_user: User = Depends(get_current_user),
):
    patient = session.get(Patient, patient_id)
    if not patient:
        raise HTTPException(404, "Patient not found")

    actions = session.exec(select(ClinicalAction).where(ClinicalAction.patient_id == patient_id)).all()
    action_ids = [action.id for action in actions]
    if not action_ids:
        return []

    name_map = {action.id: _action_name(action, session) for action in actions}
    dept_map = {action.id: action.department for action in actions}
    events = session.exec(
        select(ActionEvent)
        .where(ActionEvent.action_id.in_(action_ids))  # type: ignore[union-attr]
        .order_by(ActionEvent.timestamp.asc())  # type: ignore[union-attr]
    ).all()

    actor_ids = sorted({event.actor_id for event in events if event.actor_id is not None})
    actor_map: dict[int, User] = {}
    if actor_ids:
        actors = session.exec(select(User).where(User.id.in_(actor_ids))).all()  # type: ignore[union-attr]
        actor_map = {actor.id: actor for actor in actors if actor.id is not None}

    timeline = []
    for event in events:
        data = event.model_dump()
        data["action_name"] = name_map.get(event.action_id, "Unknown")
        data["department"] = dept_map.get(event.action_id)
        actor = actor_map.get(event.actor_id) if event.actor_id is not None else None
        if actor:
            data["actor_name"] = actor.name
            data["actor_department"] = actor.department
        else:
            data["actor_name"] = None
            data["actor_department"] = None
        timeline.append(data)
    return timeline


@router.get("/{patient_id}")
def get_patient(
    patient_id: int,
    session: Session = Depends(get_session),
    _current_user: User = Depends(get_current_user),
):
    patient = session.get(Patient, patient_id)
    if not patient:
        raise HTTPException(404, "Patient not found")

    actions = session.exec(
        select(ClinicalAction)
        .where(ClinicalAction.patient_id == patient_id)
        .order_by(ClinicalAction.created_at.asc())  # type: ignore[union-attr]
    ).all()

    result = patient.model_dump()
    result["actions"] = [_action_with_overdue(action, session) for action in actions]
    return result


@router.get("/{patient_id}/summary")
def patient_summary(
    patient_id: int,
    session: Session = Depends(get_session),
    _current_user: User = Depends(get_current_user),
):
    patient = session.get(Patient, patient_id)
    if not patient:
        raise HTTPException(404, "Patient not found")

    actions = session.exec(select(ClinicalAction).where(ClinicalAction.patient_id == patient_id)).all()
    counts = _compute_counts(actions, session)
    latest_event = _latest_patient_event(patient_id, session)

    active_action_snippets = []
    for action in actions:
        custom_terminal = _custom_terminal(action, session)
        if is_terminal_state(action.action_type, action.current_state, custom_terminal):
            continue
        action_name = action.title.strip() or _action_name(action, session).replace("_", " ")
        queue_department = primary_queue_department(action, custom_terminal)
        overdue_text = " overdue" if is_action_overdue(action, custom_terminal) else ""
        active_action_snippets.append(
            f"{action_name} ({action.current_state}, {queue_department}{overdue_text})"
        )

    if active_action_snippets:
        actions_text = "; ".join(active_action_snippets[:3])
    else:
        actions_text = "No active actions"

    last_update_text = (
        latest_event.timestamp.isoformat() if latest_event else "No updates yet"
    )

    summary_text = (
        f"Patient has {counts['pending'] + counts['in_progress']} active actions: "
        f"{actions_text}. Last update: {last_update_text}."
    )

    return {
        "total_actions": len(actions),
        "completed": counts["completed"],
        "in_progress": counts["in_progress"],
        "pending": counts["pending"],
        "overdue": counts["overdue"],
        "last_updated": latest_event.timestamp.isoformat() if latest_event else None,
        "summary_text": summary_text,
    }
