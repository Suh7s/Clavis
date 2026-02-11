import json

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlmodel import Session, select

from database import get_session
from models import CustomActionType

router = APIRouter(prefix="/custom-action-types", tags=["custom-action-types"])


class CustomActionTypeCreate(BaseModel):
    name: str
    department: str
    states: list[str]
    terminal_state: str
    sla_routine_minutes: int = 120
    sla_urgent_minutes: int = 30
    sla_critical_minutes: int = 10


@router.post("", status_code=201)
def create_custom_type(body: CustomActionTypeCreate, session: Session = Depends(get_session)):
    if len(body.states) < 2:
        raise HTTPException(422, "At least 2 states required")
    if body.terminal_state != body.states[-1]:
        raise HTTPException(422, "terminal_state must be the last state in the list")

    existing = session.exec(
        select(CustomActionType).where(CustomActionType.name == body.name)
    ).first()
    if existing:
        raise HTTPException(409, f"Custom action type '{body.name}' already exists")

    cat = CustomActionType(
        name=body.name,
        department=body.department,
        states_json=json.dumps(body.states),
        terminal_state=body.terminal_state,
        sla_routine_minutes=body.sla_routine_minutes,
        sla_urgent_minutes=body.sla_urgent_minutes,
        sla_critical_minutes=body.sla_critical_minutes,
    )
    session.add(cat)
    session.commit()
    session.refresh(cat)

    result = cat.model_dump()
    result["states"] = cat.states
    return result


@router.get("")
def list_custom_types(session: Session = Depends(get_session)):
    cats = session.exec(select(CustomActionType)).all()
    results = []
    for c in cats:
        d = c.model_dump()
        d["states"] = c.states
        return_val = d
        results.append(return_val)
    return results


@router.get("/{type_id}")
def get_custom_type(type_id: int, session: Session = Depends(get_session)):
    cat = session.get(CustomActionType, type_id)
    if not cat:
        raise HTTPException(404, "Custom action type not found")
    result = cat.model_dump()
    result["states"] = cat.states
    return result
