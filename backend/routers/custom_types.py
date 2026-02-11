import json
import re

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlmodel import Session, select

from database import get_session
from models import CustomActionType, User, UserRole
from services.auth import get_current_user, require_roles

router = APIRouter(prefix="/custom-action-types", tags=["custom-action-types"])


class CustomActionTypeCreate(BaseModel):
    name: str = Field(min_length=1, max_length=80)
    department: str = Field(min_length=1, max_length=80)
    states: list[str]
    terminal_state: str = Field(min_length=1, max_length=64)
    sla_routine_minutes: int = Field(default=120, ge=1, le=1440)
    sla_urgent_minutes: int = Field(default=30, ge=1, le=1440)
    sla_critical_minutes: int = Field(default=10, ge=1, le=1440)


@router.post("", status_code=201)
def create_custom_type(
    body: CustomActionTypeCreate,
    session: Session = Depends(get_session),
    _current_user: User = Depends(require_roles(UserRole.DOCTOR, UserRole.ADMIN)),
):
    name = body.name.strip().upper().replace(" ", "_")
    department = body.department.strip()
    terminal_state = body.terminal_state.strip().upper().replace(" ", "_")
    states = [state.strip().upper().replace(" ", "_") for state in body.states if state.strip()]

    if len(states) < 2:
        raise HTTPException(422, "At least 2 states required")
    if len(set(states)) != len(states):
        raise HTTPException(422, "States must be unique")
    if any(not re.fullmatch(r"[A-Z0-9_]+", state) for state in states):
        raise HTTPException(422, "States must contain only A-Z, 0-9, and underscore")
    if terminal_state != states[-1]:
        raise HTTPException(422, "terminal_state must be the last state in the list")
    if not department:
        raise HTTPException(422, "department cannot be empty")

    existing = session.exec(select(CustomActionType)).all()
    if any(cat.name.strip().casefold() == name.casefold() for cat in existing):
        raise HTTPException(409, f"Custom action type '{body.name}' already exists")

    cat = CustomActionType(
        name=name,
        department=department,
        states_json=json.dumps(states),
        terminal_state=terminal_state,
        sla_routine_minutes=body.sla_routine_minutes,
        sla_urgent_minutes=body.sla_urgent_minutes,
        sla_critical_minutes=body.sla_critical_minutes,
    )
    try:
        session.add(cat)
        session.commit()
        session.refresh(cat)
    except Exception:
        session.rollback()
        raise HTTPException(500, "Failed to create custom action type")

    result = cat.model_dump()
    result["states"] = cat.states
    return result


@router.get("")
def list_custom_types(
    session: Session = Depends(get_session),
    _current_user: User = Depends(get_current_user),
):
    cats = session.exec(select(CustomActionType)).all()
    results = []
    for cat in cats:
        item = cat.model_dump()
        item["states"] = cat.states
        results.append(item)
    return results


@router.get("/{type_id}")
def get_custom_type(
    type_id: int,
    session: Session = Depends(get_session),
    _current_user: User = Depends(get_current_user),
):
    cat = session.get(CustomActionType, type_id)
    if not cat:
        raise HTTPException(404, "Custom action type not found")
    result = cat.model_dump()
    result["states"] = cat.states
    return result
