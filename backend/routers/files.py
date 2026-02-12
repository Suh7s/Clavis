import uuid
from pathlib import Path

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile
from fastapi.responses import FileResponse
from sqlmodel import Session, select

from database import get_session
from models import Attachment, ClinicalAction, Patient, User
from services.auth import get_current_user

router = APIRouter(tags=["files"])

UPLOAD_DIR = Path(__file__).resolve().parent.parent / "uploads"
MAX_FILE_SIZE = 10 * 1024 * 1024  # 10 MB


@router.post("/patients/{patient_id}/files", status_code=201)
async def upload_file(
    patient_id: int,
    file: UploadFile = File(...),
    action_id: int | None = None,
    session: Session = Depends(get_session),
    current_user: User = Depends(get_current_user),
):
    patient = session.get(Patient, patient_id)
    if not patient:
        raise HTTPException(404, "Patient not found")
    if action_id is not None:
        action = session.get(ClinicalAction, action_id)
        if not action or action.patient_id != patient_id:
            raise HTTPException(422, "action_id must belong to this patient")

    content = await file.read()
    if len(content) > MAX_FILE_SIZE:
        raise HTTPException(422, f"File too large (max {MAX_FILE_SIZE // 1024 // 1024}MB)")

    ext = Path(file.filename or "file").suffix
    stored_name = f"{uuid.uuid4().hex}{ext}"
    stored_path = UPLOAD_DIR / stored_name
    UPLOAD_DIR.mkdir(parents=True, exist_ok=True)
    stored_path.write_bytes(content)

    attachment = Attachment(
        patient_id=patient_id,
        action_id=action_id,
        filename=file.filename or "file",
        file_type=file.content_type or "",
        file_size=len(content),
        stored_path=stored_name,
        created_by=current_user.id,
    )
    session.add(attachment)
    try:
        session.commit()
        session.refresh(attachment)
    except Exception:
        stored_path.unlink(missing_ok=True)
        session.rollback()
        raise HTTPException(500, "Failed to save attachment")

    result = attachment.model_dump()
    result["uploader_name"] = current_user.name
    result["uploader_role"] = current_user.role.value
    return result


@router.get("/patients/{patient_id}/files")
def list_files(
    patient_id: int,
    session: Session = Depends(get_session),
    _current_user: User = Depends(get_current_user),
):
    patient = session.get(Patient, patient_id)
    if not patient:
        raise HTTPException(404, "Patient not found")

    attachments = session.exec(
        select(Attachment)
        .where(Attachment.patient_id == patient_id)
        .order_by(Attachment.created_at.asc())  # type: ignore[union-attr]
    ).all()

    uploader_ids = sorted({a.created_by for a in attachments})
    uploader_map: dict[int, User] = {}
    if uploader_ids:
        users = session.exec(select(User).where(User.id.in_(uploader_ids))).all()  # type: ignore[union-attr]
        uploader_map = {u.id: u for u in users if u.id is not None}

    result = []
    for a in attachments:
        data = a.model_dump()
        uploader = uploader_map.get(a.created_by)
        data["uploader_name"] = uploader.name if uploader else None
        data["uploader_role"] = uploader.role.value if uploader else None
        result.append(data)
    return result


@router.get("/files/{file_id}")
def download_file(
    file_id: int,
    session: Session = Depends(get_session),
    _current_user: User = Depends(get_current_user),
):
    attachment = session.get(Attachment, file_id)
    if not attachment:
        raise HTTPException(404, "File not found")

    file_path = UPLOAD_DIR / attachment.stored_path
    if not file_path.exists():
        raise HTTPException(404, "File data missing")

    return FileResponse(
        path=str(file_path),
        filename=attachment.filename,
        media_type=attachment.file_type or "application/octet-stream",
    )
