from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field
from sqlmodel import Session, select

from database import get_session
from models import Patient, PatientNote, User
from services.auth import get_current_user

router = APIRouter(prefix="/patients", tags=["notes"])


class NoteCreate(BaseModel):
    note_type: str = Field(default="general", max_length=64)
    content: str = Field(min_length=1, max_length=5000)


@router.post("/{patient_id}/notes", status_code=201)
def create_note(
    patient_id: int,
    body: NoteCreate,
    session: Session = Depends(get_session),
    current_user: User = Depends(get_current_user),
):
    patient = session.get(Patient, patient_id)
    if not patient:
        raise HTTPException(404, "Patient not found")

    note = PatientNote(
        patient_id=patient_id,
        author_id=current_user.id,
        note_type=body.note_type.strip() or "general",
        content=body.content.strip(),
    )
    session.add(note)
    try:
        session.commit()
        session.refresh(note)
    except Exception:
        session.rollback()
        raise HTTPException(500, "Failed to create note")

    result = note.model_dump()
    result["author_name"] = current_user.name
    return result


@router.get("/{patient_id}/notes")
def list_notes(
    patient_id: int,
    session: Session = Depends(get_session),
    _current_user: User = Depends(get_current_user),
):
    patient = session.get(Patient, patient_id)
    if not patient:
        raise HTTPException(404, "Patient not found")

    notes = session.exec(
        select(PatientNote)
        .where(PatientNote.patient_id == patient_id)
        .order_by(PatientNote.created_at.asc())  # type: ignore[union-attr]
    ).all()

    author_ids = sorted({n.author_id for n in notes})
    author_map: dict[int, User] = {}
    if author_ids:
        authors = session.exec(select(User).where(User.id.in_(author_ids))).all()  # type: ignore[union-attr]
        author_map = {a.id: a for a in authors if a.id is not None}

    result = []
    for note in notes:
        data = note.model_dump()
        author = author_map.get(note.author_id)
        data["author_name"] = author.name if author else None
        data["author_role"] = author.role if author else None
        result.append(data)
    return result
