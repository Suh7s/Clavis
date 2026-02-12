from __future__ import annotations

from datetime import datetime, timedelta
from enum import Enum
from typing import Optional

from sqlmodel import Field, SQLModel, Session, select

from models import ActionType, ClinicalAction, CustomActionType, Priority
from services.sla import is_action_overdue, is_terminal_state
from services.workflow import primary_queue_department


class SafetySeverity(str, Enum):
    INFO = "INFO"
    WARNING = "WARNING"
    CRITICAL = "CRITICAL"


class SafetyEvent(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    patient_id: Optional[int] = Field(default=None, index=True)
    action_id: Optional[int] = Field(default=None, index=True)
    event_type: str = Field(default="", max_length=80, index=True)
    severity: SafetySeverity = Field(default=SafetySeverity.INFO, index=True)
    description: str = Field(default="", max_length=2000)
    blocked: bool = Field(default=False, index=True)
    created_at: datetime = Field(default_factory=datetime.utcnow, index=True)


def _custom_terminal(action: ClinicalAction, session: Session) -> str | None:
    if action.custom_action_type_id is None:
        return None
    custom_type = session.get(CustomActionType, action.custom_action_type_id)
    return custom_type.terminal_state if custom_type else None


async def create_safety_event(
    session: Session,
    *,
    patient_id: int | None,
    action_id: int | None = None,
    event_type: str,
    severity: SafetySeverity,
    description: str,
    blocked: bool,
) -> SafetyEvent | None:
    event = SafetyEvent(
        patient_id=patient_id,
        action_id=action_id,
        event_type=event_type.strip().upper(),
        severity=severity,
        description=description.strip(),
        blocked=blocked,
    )
    try:
        session.add(event)
        session.commit()
        session.refresh(event)
    except Exception:
        session.rollback()
        return None

    if patient_id is None:
        return event

    payload = {
        "event": "safety_alert",
        "patient_id": patient_id,
        "severity": event.severity.value,
        "description": event.description,
        "blocked": bool(event.blocked),
    }
    try:
        from ws import manager

        await manager.broadcast_patient(patient_id, payload)
        await manager.broadcast_status(payload)
    except Exception:
        pass

    return event


def discharge_violations(patient_id: int, session: Session) -> list[str]:
    actions = session.exec(
        select(ClinicalAction).where(ClinicalAction.patient_id == patient_id)
    ).all()
    violations: list[str] = []

    non_terminal = []
    critical_unresolved = []
    overdue = []

    for action in actions:
        custom_terminal = _custom_terminal(action, session)
        terminal = is_terminal_state(action.action_type, action.current_state, custom_terminal)
        if not terminal:
            non_terminal.append(action)
        if action.priority == Priority.CRITICAL and not terminal:
            critical_unresolved.append(action)
        if is_action_overdue(action, custom_terminal):
            overdue.append(action)

    if non_terminal:
        violations.append(f"active actions pending ({len(non_terminal)})")
    if critical_unresolved:
        violations.append(f"unresolved CRITICAL actions ({len(critical_unresolved)})")
    if overdue:
        violations.append(f"overdue actions present ({len(overdue)})")

    return violations


def medication_dependency_violation(
    *,
    action: ClinicalAction,
    new_state: str,
    session: Session,
) -> str | None:
    if new_state != "ADMINISTERED":
        return None
    if action.action_type != ActionType.MEDICATION:
        return None

    diagnostics = session.exec(
        select(ClinicalAction).where(
            ClinicalAction.patient_id == action.patient_id,
            ClinicalAction.action_type == ActionType.DIAGNOSTIC,
        )
    ).all()

    if not diagnostics:
        return None

    incomplete = [
        diagnostic
        for diagnostic in diagnostics
        if str(diagnostic.current_state or "").upper() != "COMPLETED"
    ]
    if not incomplete:
        return None

    return (
        "Cannot administer medication before linked diagnostic actions are COMPLETED "
        f"({len(incomplete)} pending)."
    )


def compute_patient_risk(patient_id: int, session: Session) -> dict[str, int | str]:
    actions = session.exec(
        select(ClinicalAction).where(ClinicalAction.patient_id == patient_id)
    ).all()

    overdue_count = 0
    critical_unresolved_count = 0
    active_departments: set[str] = set()

    for action in actions:
        custom_terminal = _custom_terminal(action, session)
        terminal = is_terminal_state(action.action_type, action.current_state, custom_terminal)
        if is_action_overdue(action, custom_terminal):
            overdue_count += 1
        if action.priority == Priority.CRITICAL and not terminal:
            critical_unresolved_count += 1
        if not terminal:
            department = primary_queue_department(action, custom_terminal)
            if department:
                active_departments.add(department.strip().casefold())

    cross_department_active_chains = max(0, len(active_departments) - 1)
    since = datetime.utcnow() - timedelta(hours=24)
    blocked_recent = session.exec(
        select(SafetyEvent).where(
            SafetyEvent.patient_id == patient_id,
            SafetyEvent.blocked == True,  # noqa: E712
            SafetyEvent.created_at >= since,
        )
    ).all()

    score = 0
    score += overdue_count * 2
    score += critical_unresolved_count * 3
    score += cross_department_active_chains * 1
    score += len(blocked_recent) * 5

    if score <= 2:
        level = "LOW"
    elif score <= 6:
        level = "MEDIUM"
    else:
        level = "HIGH"

    return {"score": score, "level": level}


def list_patient_safety_events(
    patient_id: int,
    *,
    page: int,
    page_size: int,
    session: Session,
) -> dict:
    query = select(SafetyEvent).where(SafetyEvent.patient_id == patient_id)
    total = len(session.exec(query).all())
    rows = session.exec(
        query
        .order_by(SafetyEvent.created_at.desc())  # type: ignore[union-attr]
        .offset((page - 1) * page_size)
        .limit(page_size)
    ).all()
    return {
        "events": [row.model_dump() for row in rows],
        "total": total,
        "page": page,
        "page_size": page_size,
    }
