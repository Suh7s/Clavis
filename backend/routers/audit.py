from datetime import datetime

from fastapi import APIRouter, Depends, Query
from sqlmodel import Session, select

from database import get_session
from models import ActionEvent, ActionType, ClinicalAction, Patient, User, UserRole
from services.auth import require_roles

router = APIRouter(tags=["audit"])


@router.get("/audit-log")
def list_audit_log(
    start_date: datetime | None = Query(default=None),
    end_date: datetime | None = Query(default=None),
    actor_id: int | None = Query(default=None),
    department: str = Query(default="", max_length=80),
    action_type: str = Query(default="", max_length=64),
    patient_id: int | None = Query(default=None),
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=50, ge=1, le=200),
    session: Session = Depends(get_session),
    _current_user: User = Depends(require_roles(UserRole.ADMIN, UserRole.DOCTOR)),
):
    event_query = select(ActionEvent)

    if start_date is not None:
        event_query = event_query.where(ActionEvent.timestamp >= start_date)
    if end_date is not None:
        event_query = event_query.where(ActionEvent.timestamp <= end_date)
    if actor_id is not None:
        event_query = event_query.where(ActionEvent.actor_id == actor_id)

    department_filter = department.strip()
    action_type_filter = action_type.strip().upper()
    action_type_value = None
    if action_type_filter:
        try:
            action_type_value = ActionType(action_type_filter)
        except ValueError:
            return {
                "events": [],
                "total": 0,
                "page": page,
                "page_size": page_size,
            }
    has_action_filters = any([patient_id is not None, bool(department_filter), bool(action_type_filter)])
    if has_action_filters:
        action_query = select(ClinicalAction.id)
        if patient_id is not None:
            action_query = action_query.where(ClinicalAction.patient_id == patient_id)
        if department_filter:
            action_query = action_query.where(ClinicalAction.department == department_filter)
        if action_type_value is not None:
            action_query = action_query.where(ClinicalAction.action_type == action_type_value)

        action_ids = session.exec(action_query).all()
        if not action_ids:
            return {
                "events": [],
                "total": 0,
                "page": page,
                "page_size": page_size,
            }
        event_query = event_query.where(ActionEvent.action_id.in_(action_ids))  # type: ignore[union-attr]

    event_query = event_query.order_by(ActionEvent.timestamp.desc())  # type: ignore[union-attr]

    total = len(session.exec(event_query).all())
    events = session.exec(
        event_query.offset((page - 1) * page_size).limit(page_size)
    ).all()

    action_ids_for_page = sorted({event.action_id for event in events})
    action_map: dict[int, ClinicalAction] = {}
    if action_ids_for_page:
        actions = session.exec(
            select(ClinicalAction).where(ClinicalAction.id.in_(action_ids_for_page))  # type: ignore[union-attr]
        ).all()
        action_map = {action.id: action for action in actions if action.id is not None}

    patient_ids = sorted({action.patient_id for action in action_map.values()})
    patient_map: dict[int, Patient] = {}
    if patient_ids:
        patients = session.exec(
            select(Patient).where(Patient.id.in_(patient_ids))  # type: ignore[union-attr]
        ).all()
        patient_map = {patient.id: patient for patient in patients if patient.id is not None}

    actor_ids = sorted({event.actor_id for event in events if event.actor_id is not None})
    actor_map: dict[int, User] = {}
    if actor_ids:
        actors = session.exec(
            select(User).where(User.id.in_(actor_ids))  # type: ignore[union-attr]
        ).all()
        actor_map = {actor.id: actor for actor in actors if actor.id is not None}

    payload = []
    for event in events:
        row = event.model_dump()
        action = action_map.get(event.action_id)
        actor = actor_map.get(event.actor_id) if event.actor_id is not None else None

        if action:
            row["patient_id"] = action.patient_id
            row["department"] = action.department
            row["action_title"] = action.title
            row["action_type"] = action.action_type.value if action.action_type else None
            patient = patient_map.get(action.patient_id)
            row["patient_name"] = patient.name if patient else None
        else:
            row["patient_id"] = None
            row["department"] = None
            row["action_title"] = None
            row["action_type"] = None
            row["patient_name"] = None

        if actor:
            row["actor_name"] = actor.name
            row["actor_role"] = actor.role.value
            row["actor_department"] = actor.department
        else:
            row["actor_name"] = None
            row["actor_department"] = None
            if row.get("actor_role") is not None:
                row["actor_role"] = str(row["actor_role"])

        payload.append(row)

    return {
        "events": payload,
        "total": total,
        "page": page,
        "page_size": page_size,
    }
