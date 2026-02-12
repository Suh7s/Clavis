from datetime import datetime
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlmodel import Session, select

from database import get_session
from models import ActionEvent, ActionType, ClinicalAction, CustomActionType, Patient, Priority, User, UserRole
from services.access import can_access_department_queue, roles_allowed_for_transition
from services.auth import get_current_user, require_roles
from services.drug_interactions import check_interactions
from services.safety_engine import (
    SafetySeverity,
    create_safety_event,
    medication_dependency_violation,
)
from services.sla import compute_custom_sla_deadline, compute_sla_deadline, is_action_overdue, is_terminal_state
from services.workflow import (
    default_department_for_action,
    department_matches,
    primary_queue_department,
    queue_departments_for_action,
)
from state_machine import INITIAL_STATES, validate_custom_transition, validate_transition
from ws import manager

router = APIRouter(prefix="/actions", tags=["actions"])

PRIORITY_RANK = {
    Priority.CRITICAL.value: 0,
    Priority.URGENT.value: 1,
    Priority.ROUTINE.value: 2,
}


def _get_custom_type(action: ClinicalAction, session: Session) -> CustomActionType | None:
    if action.custom_action_type_id is None:
        return None
    return session.get(CustomActionType, action.custom_action_type_id)


def _get_custom_terminal(action: ClinicalAction, session: Session) -> str | None:
    cat = _get_custom_type(action, session)
    return cat.terminal_state if cat else None


def _ensure_patient_not_discharged(patient: Patient):
    from models import AdmissionStatus

    if patient.admission_status == AdmissionStatus.DISCHARGED:
        raise HTTPException(422, "Cannot modify actions for a discharged patient")


def _ensure_action_patient_not_discharged(action: ClinicalAction, session: Session):
    patient = session.get(Patient, action.patient_id)
    if not patient:
        raise HTTPException(404, "Patient not found")
    _ensure_patient_not_discharged(patient)


def action_response(action: ClinicalAction, session: Session) -> dict:
    data = action.model_dump()
    custom_terminal = _get_custom_terminal(action, session)
    queue_departments = queue_departments_for_action(action, custom_terminal)
    data["is_overdue"] = is_action_overdue(action, custom_terminal)
    data["queue_departments"] = queue_departments
    data["queue_department"] = primary_queue_department(action, custom_terminal)
    data["is_terminal"] = len(queue_departments) == 0

    cat = _get_custom_type(action, session)
    if cat:
        data["custom_type_name"] = cat.name
    return data


async def _broadcast_action_change(
    action: ClinicalAction,
    session: Session,
    event_type: str,
    previous_queues: list[str] | None = None,
):
    payload = {
        "event": event_type,
        "action_id": action.id,
        "patient_id": action.patient_id,
        "new_state": action.current_state,
        "timestamp": datetime.utcnow().isoformat(),
    }
    data = action_response(action, session)
    payload["is_overdue"] = data["is_overdue"]
    payload["queue_departments"] = data["queue_departments"]

    await manager.broadcast_patient(action.patient_id, payload)
    await manager.broadcast_status(payload)

    departments = set(data["queue_departments"])
    if previous_queues:
        departments.update(previous_queues)
    for dept in departments:
        await manager.broadcast_department(dept, payload)


class ActionCreate(BaseModel):
    patient_id: int
    action_type: Optional[ActionType] = None
    custom_action_type_id: Optional[int] = None
    priority: Priority = Priority.ROUTINE
    title: str = Field(default="", max_length=200)
    notes: str = Field(default="", max_length=2000)
    department_target: Optional[str] = Field(default=None, max_length=80)


class ActionEdit(BaseModel):
    title: Optional[str] = Field(default=None, max_length=200)
    notes: Optional[str] = Field(default=None, max_length=2000)
    priority: Optional[Priority] = None


class TransitionRequest(BaseModel):
    new_state: str = Field(min_length=1, max_length=64)
    notes: str = Field(default="", max_length=2000)


class BulkCreateRequest(BaseModel):
    actions: list[ActionCreate] = Field(min_length=1, max_length=200)


class BulkTransitionItem(BaseModel):
    action_id: int
    new_state: str = Field(min_length=1, max_length=64)
    notes: str = Field(default="", max_length=2000)


class BulkTransitionRequest(BaseModel):
    transitions: list[BulkTransitionItem] = Field(min_length=1, max_length=200)


def _active_medication_titles_for_patient(
    patient_id: int,
    exclude_action_id: int,
    session: Session,
) -> list[str]:
    meds = session.exec(
        select(ClinicalAction).where(
            ClinicalAction.patient_id == patient_id,
            ClinicalAction.action_type == ActionType.MEDICATION,
            ClinicalAction.id != exclude_action_id,
        )
    ).all()

    active = []
    for med in meds:
        custom_terminal = _get_custom_terminal(med, session)
        if is_terminal_state(med.action_type, med.current_state, custom_terminal):
            continue
        active.append(med.title)
    return active


async def _create_single_action(
    body: ActionCreate,
    session: Session,
    current_user: User,
    broadcast: bool = True,
) -> dict:
    if body.action_type and body.custom_action_type_id:
        raise HTTPException(422, "Set action_type OR custom_action_type_id, not both")
    if not body.action_type and not body.custom_action_type_id:
        raise HTTPException(422, "Must set action_type or custom_action_type_id")

    patient = session.get(Patient, body.patient_id)
    if not patient:
        raise HTTPException(404, "Patient not found")
    _ensure_patient_not_discharged(patient)

    title = body.title.strip()
    notes = body.notes.strip()
    department_target = body.department_target.strip() if body.department_target else None
    if not title:
        raise HTTPException(422, "Action title cannot be empty")

    if body.custom_action_type_id:
        cat = session.get(CustomActionType, body.custom_action_type_id)
        if not cat:
            raise HTTPException(404, "Custom action type not found")
        if not cat.states:
            raise HTTPException(500, "Custom action type has no defined states")
        initial_state = cat.states[0]
        department = cat.department
        sla_deadline = compute_custom_sla_deadline(body.priority, cat)
        label = cat.name
    else:
        initial_state = INITIAL_STATES[body.action_type]
        department = default_department_for_action(
            body.action_type,
            title=title,
            department_target=department_target,
        )
        sla_deadline = compute_sla_deadline(body.priority)
        label = body.action_type.value

    action = ClinicalAction(
        patient_id=body.patient_id,
        created_by=current_user.id,
        action_type=body.action_type,
        custom_action_type_id=body.custom_action_type_id,
        title=title,
        notes=notes,
        current_state=initial_state,
        priority=body.priority,
        department=department,
        sla_deadline=sla_deadline,
    )

    try:
        session.add(action)
        session.flush()

        event = ActionEvent(
            action_id=action.id,
            actor_id=current_user.id,
            actor_role=current_user.role,
            previous_state="",
            new_state=initial_state,
        )
        session.add(event)
        session.commit()
        session.refresh(action)
    except Exception:
        session.rollback()
        raise HTTPException(500, "Failed to create action")

    print(f"[ACTION] Created #{action.id} {label} '{action.title}' for patient #{body.patient_id}")
    if broadcast:
        await _broadcast_action_change(action, session, "action_created")

    response = action_response(action, session)
    if body.action_type == ActionType.MEDICATION:
        warnings = check_interactions(
            title,
            _active_medication_titles_for_patient(body.patient_id, action.id, session),
        )
        if warnings:
            response["warnings"] = warnings

    return response


async def _transition_single_action(
    action_id: int,
    body: TransitionRequest,
    session: Session,
    current_user: User,
    broadcast: bool = True,
) -> dict:
    action = session.get(ClinicalAction, action_id)
    if not action:
        raise HTTPException(404, "Action not found")
    _ensure_action_patient_not_discharged(action, session)

    new_state = body.new_state.strip().upper()
    if not new_state:
        raise HTTPException(422, "new_state cannot be empty")
    notes = body.notes.strip()

    custom_terminal = _get_custom_terminal(action, session)
    previous_queues = queue_departments_for_action(action, custom_terminal)

    try:
        if action.custom_action_type_id:
            cat = session.get(CustomActionType, action.custom_action_type_id)
            if not cat:
                raise HTTPException(404, "Custom action type not found")
            validate_custom_transition(cat, action.current_state, new_state)
        else:
            validate_transition(action.action_type, action.current_state, new_state)
    except ValueError as exc:
        await create_safety_event(
            session,
            patient_id=action.patient_id,
            action_id=action.id,
            event_type="UNSAFE_TRANSITION",
            severity=SafetySeverity.WARNING,
            description=str(exc),
            blocked=True,
        )
        raise HTTPException(422, str(exc)) from exc

    allowed_roles = roles_allowed_for_transition(action, new_state)
    if current_user.role not in allowed_roles:
        await create_safety_event(
            session,
            patient_id=action.patient_id,
            action_id=action.id,
            event_type="ROLE_VIOLATION",
            severity=SafetySeverity.WARNING,
            description=(
                f"Role '{current_user.role.value}' attempted blocked transition "
                f"to '{new_state}' for action #{action.id}"
            ),
            blocked=True,
        )
        raise HTTPException(
            status_code=403,
            detail=f"Role '{current_user.role.value}' cannot transition this action to '{new_state}'",
        )

    dependency_violation = medication_dependency_violation(
        action=action,
        new_state=new_state,
        session=session,
    )
    if dependency_violation:
        await create_safety_event(
            session,
            patient_id=action.patient_id,
            action_id=action.id,
            event_type="MEDICATION_DEPENDENCY",
            severity=SafetySeverity.CRITICAL,
            description=dependency_violation,
            blocked=True,
        )
        raise HTTPException(400, dependency_violation)

    prev = action.current_state
    action.current_state = new_state
    action.updated_at = datetime.utcnow()
    session.add(action)

    event = ActionEvent(
        action_id=action.id,
        actor_id=current_user.id,
        actor_role=current_user.role,
        previous_state=prev,
        new_state=new_state,
        notes=notes,
    )
    session.add(event)

    try:
        session.commit()
        session.refresh(action)
    except Exception:
        session.rollback()
        raise HTTPException(500, "Failed to save transition")

    print(f"[TRANSITION] Action #{action_id}: {prev} -> {new_state}")
    if broadcast:
        await _broadcast_action_change(action, session, "action_updated", previous_queues=previous_queues)

    return action_response(action, session)


@router.post("", status_code=201)
async def create_action(
    body: ActionCreate,
    session: Session = Depends(get_session),
    current_user: User = Depends(require_roles(UserRole.DOCTOR, UserRole.ADMIN)),
):
    return await _create_single_action(body, session, current_user)


@router.post("/bulk")
async def create_actions_bulk(
    body: BulkCreateRequest,
    session: Session = Depends(get_session),
    current_user: User = Depends(require_roles(UserRole.DOCTOR, UserRole.ADMIN)),
):
    successful: list[dict] = []
    failed: list[dict] = []

    for index, item in enumerate(body.actions):
        try:
            result = await _create_single_action(item, session, current_user)
            successful.append({"index": index, "action": result})
        except HTTPException as exc:
            session.rollback()
            failed.append(
                {
                    "index": index,
                    "status_code": exc.status_code,
                    "error": exc.detail,
                    "request": item.model_dump(),
                }
            )
        except Exception:
            session.rollback()
            failed.append(
                {
                    "index": index,
                    "status_code": 500,
                    "error": "Failed to create action",
                    "request": item.model_dump(),
                }
            )

    return {"successful": successful, "failed": failed}


@router.patch("/bulk/transition")
async def transition_actions_bulk(
    body: BulkTransitionRequest,
    session: Session = Depends(get_session),
    current_user: User = Depends(get_current_user),
):
    successful: list[dict] = []
    failed: list[dict] = []

    for index, item in enumerate(body.transitions):
        try:
            payload = TransitionRequest(new_state=item.new_state, notes=item.notes)
            result = await _transition_single_action(item.action_id, payload, session, current_user)
            successful.append({"index": index, "action_id": item.action_id, "action": result})
        except HTTPException as exc:
            session.rollback()
            failed.append(
                {
                    "index": index,
                    "action_id": item.action_id,
                    "status_code": exc.status_code,
                    "error": exc.detail,
                }
            )
        except Exception:
            session.rollback()
            failed.append(
                {
                    "index": index,
                    "action_id": item.action_id,
                    "status_code": 500,
                    "error": "Failed to transition action",
                }
            )

    return {"successful": successful, "failed": failed}


@router.patch("/{action_id}", response_model=None)
async def edit_action(
    action_id: int,
    body: ActionEdit,
    session: Session = Depends(get_session),
    _current_user: User = Depends(require_roles(UserRole.DOCTOR, UserRole.ADMIN)),
):
    action = session.get(ClinicalAction, action_id)
    if not action:
        raise HTTPException(404, "Action not found")

    if body.title is not None:
        title = body.title.strip()
        if not title:
            raise HTTPException(422, "Action title cannot be empty")
        action.title = title
    if body.notes is not None:
        action.notes = body.notes.strip()
    action.updated_at = datetime.utcnow()
    if body.priority is not None:
        action.priority = body.priority
        if action.custom_action_type_id:
            cat = session.get(CustomActionType, action.custom_action_type_id)
            if cat:
                action.sla_deadline = compute_custom_sla_deadline(body.priority, cat)
        else:
            action.sla_deadline = compute_sla_deadline(body.priority)

    session.add(action)

    try:
        session.commit()
        session.refresh(action)
    except Exception:
        session.rollback()
        raise HTTPException(500, "Failed to save changes")

    print(f"[EDIT] Action #{action_id} updated")
    await _broadcast_action_change(action, session, "action_updated")
    return action_response(action, session)


@router.patch("/{action_id}/transition")
async def transition_action(
    action_id: int,
    body: TransitionRequest,
    session: Session = Depends(get_session),
    current_user: User = Depends(get_current_user),
):
    return await _transition_single_action(action_id, body, session, current_user)


@router.get("/patients/{patient_id}/timeline")
def patient_timeline(
    patient_id: int,
    session: Session = Depends(get_session),
    _current_user: User = Depends(get_current_user),
):
    patient = session.get(Patient, patient_id)
    if not patient:
        raise HTTPException(404, "Patient not found")

    actions = session.exec(select(ClinicalAction).where(ClinicalAction.patient_id == patient_id)).all()
    action_ids = [a.id for a in actions]
    if not action_ids:
        return []

    name_map: dict[int, str] = {}
    dept_map: dict[int, str] = {}
    for action in actions:
        if action.custom_action_type_id:
            cat = session.get(CustomActionType, action.custom_action_type_id)
            name_map[action.id] = cat.name if cat else "Custom"
        else:
            name_map[action.id] = action.action_type.value if action.action_type else "Unknown"
        dept_map[action.id] = action.department

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

    results = []
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
        results.append(data)

    return results


@router.get("/department/{department}")
async def department_queue(
    department: str,
    include_terminal: bool = False,
    session: Session = Depends(get_session),
    current_user: User = Depends(get_current_user),
):
    if not can_access_department_queue(current_user.role, department):
        await create_safety_event(
            session,
            patient_id=None,
            action_id=None,
            event_type="ROLE_VIOLATION",
            severity=SafetySeverity.WARNING,
            description=(
                f"Role '{current_user.role.value}' blocked from department queue '{department}'"
            ),
            blocked=True,
        )
        raise HTTPException(
            status_code=403,
            detail=f"Role '{current_user.role.value}' cannot access '{department}' queue",
        )

    actions = session.exec(
        select(ClinicalAction).order_by(ClinicalAction.created_at.asc())  # type: ignore[union-attr]
    ).all()

    results = []
    for action in actions:
        data = action_response(action, session)
        queue_departments = data["queue_departments"]
        if department_matches(department, queue_departments):
            results.append(data)
            continue
        if include_terminal and department_matches(department, [action.department]):
            results.append(data)

    results.sort(
        key=lambda action_data: (
            0 if action_data["is_overdue"] else 1,
            PRIORITY_RANK.get(action_data["priority"], 9),
            action_data.get("sla_deadline") or "",
        )
    )
    return results


@router.get("/escalations")
def list_escalations(
    session: Session = Depends(get_session),
    _current_user: User = Depends(get_current_user),
):
    actions = session.exec(select(ClinicalAction)).all()
    escalations = []

    for action in actions:
        data = action_response(action, session)
        if not data["is_overdue"]:
            continue

        patient = session.get(Patient, action.patient_id)
        data["patient_name"] = patient.name if patient else "Unknown"
        escalations.append(data)

    escalations.sort(
        key=lambda action_data: (
            PRIORITY_RANK.get(action_data["priority"], 9),
            action_data.get("sla_deadline") or "",
        )
    )
    return escalations


@router.get("")
def list_actions(
    session: Session = Depends(get_session),
    _current_user: User = Depends(get_current_user),
):
    actions = session.exec(select(ClinicalAction)).all()
    return [action_response(action, session) for action in actions]
