from datetime import datetime
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field
from sqlmodel import Session, select

from database import get_session
from models import (
    ActionEvent, AdmissionStatus, ClinicalAction, CustomActionType,
    Patient, PatientTransfer, User, UserRole,
)
from services.auth import get_current_user, require_roles
from services.sla import is_action_overdue, is_terminal_state
from services.workflow import primary_queue_department, queue_departments_for_action

router = APIRouter(prefix="/patients", tags=["patients"])

requires_doctor_or_admin = require_roles(UserRole.DOCTOR, UserRole.ADMIN)


class PatientCreate(BaseModel):
    name: str = Field(min_length=1, max_length=120)
    age: int = Field(ge=0, le=130)
    gender: str = Field(min_length=1, max_length=32)
    blood_group: Optional[str] = Field(default=None, max_length=10)
    admission_date: Optional[datetime] = None
    ward: Optional[str] = Field(default=None, max_length=64)
    primary_doctor_id: Optional[int] = None


class PatientUpdate(BaseModel):
    name: Optional[str] = Field(default=None, min_length=1, max_length=120)
    age: Optional[int] = Field(default=None, ge=0, le=130)
    gender: Optional[str] = Field(default=None, min_length=1, max_length=32)
    blood_group: Optional[str] = Field(default=None, max_length=10)
    ward: Optional[str] = Field(default=None, max_length=64)
    primary_doctor_id: Optional[int] = None


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

    if body.primary_doctor_id is not None:
        doctor = session.get(User, body.primary_doctor_id)
        if not doctor:
            raise HTTPException(422, "Primary doctor not found")

    patient = Patient(
        name=name,
        age=body.age,
        gender=gender,
        blood_group=body.blood_group,
        admission_date=body.admission_date or datetime.utcnow(),
        ward=body.ward,
        primary_doctor_id=body.primary_doctor_id,
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
    include_inactive: bool = Query(False),
    search: str = Query("", max_length=120),
    page: int = Query(1, ge=1),
    page_size: int = Query(50, ge=1, le=100),
):
    query = select(Patient)
    if not include_inactive:
        query = query.where(Patient.is_active == True)  # noqa: E712
    if search.strip():
        query = query.where(Patient.name.contains(search.strip()))  # type: ignore[union-attr]
    total = len(session.exec(query).all())
    patients = session.exec(
        query.order_by(Patient.created_at.asc())  # type: ignore[union-attr]
        .offset((page - 1) * page_size)
        .limit(page_size)
    ).all()
    return {"patients": patients, "total": total, "page": page, "page_size": page_size}


@router.get("/status-board")
def status_board(
    session: Session = Depends(get_session),
    _current_user: User = Depends(get_current_user),
):
    patients = session.exec(
        select(Patient).where(Patient.is_active == True).order_by(Patient.created_at.asc())  # noqa: E712
    ).all()
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
                "ward": patient.ward,
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


@router.get("/staff/doctors")
def list_doctors_for_transfer(
    session: Session = Depends(get_session),
    _current_user: User = Depends(get_current_user),
):
    users = session.exec(
        select(User)
        .where(User.is_active == True)  # noqa: E712
        .where(User.role.in_([UserRole.DOCTOR, UserRole.ADMIN]))  # type: ignore[union-attr]
        .order_by(User.name.asc())  # type: ignore[union-attr]
    ).all()
    return [
        {
            "id": user.id,
            "name": user.name,
            "role": user.role.value,
            "department": user.department,
        }
        for user in users
        if user.id is not None
    ]


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


@router.patch("/{patient_id}")
def update_patient(
    patient_id: int,
    body: PatientUpdate,
    session: Session = Depends(get_session),
    _current_user: User = Depends(requires_doctor_or_admin),
):
    patient = session.get(Patient, patient_id)
    if not patient:
        raise HTTPException(404, "Patient not found")

    update_data = body.model_dump(exclude_unset=True)
    if "primary_doctor_id" in update_data and update_data["primary_doctor_id"] is not None:
        doctor = session.get(User, update_data["primary_doctor_id"])
        if not doctor:
            raise HTTPException(422, "Primary doctor not found")

    for field, value in update_data.items():
        setattr(patient, field, value)

    try:
        session.commit()
        session.refresh(patient)
    except Exception:
        session.rollback()
        raise HTTPException(500, "Failed to update patient")
    return patient


@router.delete("/{patient_id}")
def soft_delete_patient(
    patient_id: int,
    session: Session = Depends(get_session),
    _current_user: User = Depends(requires_doctor_or_admin),
):
    patient = session.get(Patient, patient_id)
    if not patient:
        raise HTTPException(404, "Patient not found")
    patient.is_active = False
    session.commit()
    return {"detail": "Patient deactivated"}


class DischargeRequest(BaseModel):
    notes: str = Field(default="", max_length=2000)


@router.post("/{patient_id}/discharge")
def discharge_patient(
    patient_id: int,
    body: DischargeRequest,
    session: Session = Depends(get_session),
    _current_user: User = Depends(requires_doctor_or_admin),
):
    patient = session.get(Patient, patient_id)
    if not patient:
        raise HTTPException(404, "Patient not found")
    if patient.admission_status == AdmissionStatus.DISCHARGED:
        raise HTTPException(422, "Patient already discharged")

    actions = session.exec(
        select(ClinicalAction).where(ClinicalAction.patient_id == patient_id)
    ).all()
    for action in actions:
        custom_terminal = _custom_terminal(action, session)
        if not is_terminal_state(action.action_type, action.current_state, custom_terminal):
            raise HTTPException(
                422,
                f"Cannot discharge: action #{action.id} ({action.title or 'Untitled'}) is still active",
            )

    patient.admission_status = AdmissionStatus.DISCHARGED
    patient.discharge_date = datetime.utcnow()
    patient.discharge_notes = body.notes.strip()
    session.commit()
    session.refresh(patient)
    return patient


class TransferRequest(BaseModel):
    to_doctor_id: Optional[int] = None
    to_ward: Optional[str] = Field(default=None, max_length=64)
    reason: str = Field(default="", max_length=2000)


@router.post("/{patient_id}/transfer")
def transfer_patient(
    patient_id: int,
    body: TransferRequest,
    session: Session = Depends(get_session),
    current_user: User = Depends(requires_doctor_or_admin),
):
    patient = session.get(Patient, patient_id)
    if not patient:
        raise HTTPException(404, "Patient not found")
    if patient.admission_status == AdmissionStatus.DISCHARGED:
        raise HTTPException(422, "Cannot transfer a discharged patient")

    if body.to_doctor_id is not None:
        doctor = session.get(User, body.to_doctor_id)
        if not doctor:
            raise HTTPException(422, "Target doctor not found")

    transfer = PatientTransfer(
        patient_id=patient_id,
        from_doctor_id=patient.primary_doctor_id,
        to_doctor_id=body.to_doctor_id,
        from_ward=patient.ward,
        to_ward=body.to_ward,
        reason=body.reason.strip(),
        transferred_by=current_user.id,
    )
    session.add(transfer)

    if body.to_doctor_id is not None:
        patient.primary_doctor_id = body.to_doctor_id
    if body.to_ward is not None:
        patient.ward = body.to_ward
    patient.admission_status = AdmissionStatus.TRANSFERRED

    session.commit()
    session.refresh(transfer)

    result = transfer.model_dump()
    result["from_doctor_name"] = None
    result["to_doctor_name"] = None
    if transfer.from_doctor_id:
        from_doc = session.get(User, transfer.from_doctor_id)
        if from_doc:
            result["from_doctor_name"] = from_doc.name
    if transfer.to_doctor_id:
        to_doc = session.get(User, transfer.to_doctor_id)
        if to_doc:
            result["to_doctor_name"] = to_doc.name
    return result


@router.get("/{patient_id}/transfers")
def list_transfers(
    patient_id: int,
    session: Session = Depends(get_session),
    _current_user: User = Depends(get_current_user),
):
    patient = session.get(Patient, patient_id)
    if not patient:
        raise HTTPException(404, "Patient not found")

    transfers = session.exec(
        select(PatientTransfer)
        .where(PatientTransfer.patient_id == patient_id)
        .order_by(PatientTransfer.created_at.asc())  # type: ignore[union-attr]
    ).all()

    user_ids = set()
    for t in transfers:
        if t.from_doctor_id:
            user_ids.add(t.from_doctor_id)
        if t.to_doctor_id:
            user_ids.add(t.to_doctor_id)
        user_ids.add(t.transferred_by)
    user_map: dict[int, User] = {}
    if user_ids:
        users = session.exec(select(User).where(User.id.in_(sorted(user_ids)))).all()  # type: ignore[union-attr]
        user_map = {u.id: u for u in users if u.id is not None}

    result = []
    for t in transfers:
        data = t.model_dump()
        data["from_doctor_name"] = user_map.get(t.from_doctor_id, None) and user_map[t.from_doctor_id].name if t.from_doctor_id else None
        data["to_doctor_name"] = user_map.get(t.to_doctor_id, None) and user_map[t.to_doctor_id].name if t.to_doctor_id else None
        data["transferred_by_name"] = user_map.get(t.transferred_by, None) and user_map[t.transferred_by].name
        result.append(data)
    return result
