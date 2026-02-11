import csv
import io
from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import Response, StreamingResponse
from sqlmodel import Session, select

from database import get_session
from models import ActionEvent, ActionType, ClinicalAction, Patient, PatientNote, User, UserRole
from services.auth import require_roles

router = APIRouter(prefix="/export", tags=["export"])


def _csv_response(filename: str, rows: list[list[str]]) -> StreamingResponse:
    buffer = io.StringIO()
    writer = csv.writer(buffer)
    writer.writerows(rows)
    buffer.seek(0)
    return StreamingResponse(
        iter([buffer.getvalue()]),
        media_type="text/csv",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


def _pdf_escape(value: str) -> str:
    safe = value.encode("latin-1", "replace").decode("latin-1")
    return safe.replace("\\", "\\\\").replace("(", "\\(").replace(")", "\\)")


def _pdf_page_stream(lines: list[str]) -> bytes:
    ops = ["BT", "/F1 10 Tf", "14 TL", "40 760 Td"]
    for i, line in enumerate(lines):
        if i > 0:
            ops.append("T*")
        ops.append(f"({_pdf_escape(line)}) Tj")
    ops.append("ET")
    return ("\n".join(ops) + "\n").encode("latin-1", "replace")


def _build_simple_pdf(lines: list[str], lines_per_page: int = 48) -> bytes:
    chunks = [lines[i:i + lines_per_page] for i in range(0, len(lines), lines_per_page)] or [[""]]
    pages = len(chunks)

    font_id = 1
    first_content_id = 2
    first_page_id = first_content_id + pages
    pages_id = first_page_id + pages
    catalog_id = pages_id + 1
    total_objects = catalog_id

    objects: dict[int, bytes] = {
        font_id: b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>",
    }

    for index, chunk in enumerate(chunks):
        content_id = first_content_id + index
        page_id = first_page_id + index
        stream = _pdf_page_stream(chunk)
        content_obj = (
            f"<< /Length {len(stream)} >>\nstream\n".encode("latin-1")
            + stream
            + b"endstream"
        )
        page_obj = (
            f"<< /Type /Page /Parent {pages_id} 0 R /MediaBox [0 0 612 792] "
            f"/Resources << /Font << /F1 {font_id} 0 R >> >> /Contents {content_id} 0 R >>"
        ).encode("latin-1")
        objects[content_id] = content_obj
        objects[page_id] = page_obj

    kids = " ".join(f"{first_page_id + index} 0 R" for index in range(pages))
    objects[pages_id] = f"<< /Type /Pages /Kids [{kids}] /Count {pages} >>".encode("latin-1")
    objects[catalog_id] = f"<< /Type /Catalog /Pages {pages_id} 0 R >>".encode("latin-1")

    output = bytearray()
    output.extend(b"%PDF-1.4\n%\xe2\xe3\xcf\xd3\n")
    offsets = [0] * (total_objects + 1)

    for object_id in range(1, total_objects + 1):
        offsets[object_id] = len(output)
        output.extend(f"{object_id} 0 obj\n".encode("latin-1"))
        output.extend(objects[object_id])
        output.extend(b"\nendobj\n")

    xref_offset = len(output)
    output.extend(f"xref\n0 {total_objects + 1}\n".encode("latin-1"))
    output.extend(b"0000000000 65535 f \n")
    for object_id in range(1, total_objects + 1):
        output.extend(f"{offsets[object_id]:010} 00000 n \n".encode("latin-1"))

    trailer = (
        f"trailer\n<< /Size {total_objects + 1} /Root {catalog_id} 0 R >>\n"
        f"startxref\n{xref_offset}\n%%EOF\n"
    )
    output.extend(trailer.encode("latin-1"))
    return bytes(output)


def _pdf_response(filename: str, content: bytes) -> Response:
    return Response(
        content=content,
        media_type="application/pdf",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


@router.get("/patients/{patient_id}/csv")
def export_patient_csv(
    patient_id: int,
    session: Session = Depends(get_session),
    _current_user: User = Depends(require_roles(UserRole.ADMIN, UserRole.DOCTOR, UserRole.NURSE)),
):
    patient = session.get(Patient, patient_id)
    if not patient:
        raise HTTPException(404, "Patient not found")

    actions = session.exec(
        select(ClinicalAction)
        .where(ClinicalAction.patient_id == patient_id)
        .order_by(ClinicalAction.created_at.asc())  # type: ignore[union-attr]
    ).all()
    notes = session.exec(
        select(PatientNote)
        .where(PatientNote.patient_id == patient_id)
        .order_by(PatientNote.created_at.asc())  # type: ignore[union-attr]
    ).all()

    author_ids = sorted({note.author_id for note in notes})
    author_map: dict[int, User] = {}
    if author_ids:
        authors = session.exec(select(User).where(User.id.in_(author_ids))).all()  # type: ignore[union-attr]
        author_map = {author.id: author for author in authors if author.id is not None}

    rows = [
        [
            "record_type",
            "patient_id",
            "patient_name",
            "age",
            "gender",
            "blood_group",
            "ward",
            "admission_status",
            "action_id",
            "action_type",
            "action_title",
            "action_state",
            "priority",
            "department",
            "action_notes",
            "note_id",
            "note_type",
            "note_content",
            "note_author",
            "created_at",
        ]
    ]

    rows.append(
        [
            "patient",
            str(patient.id),
            patient.name,
            str(patient.age),
            patient.gender,
            patient.blood_group or "",
            patient.ward or "",
            patient.admission_status.value if hasattr(patient.admission_status, "value") else str(patient.admission_status),
            "",
            "",
            "",
            "",
            "",
            "",
            "",
            "",
            "",
            "",
            "",
            patient.created_at.isoformat(),
        ]
    )

    for action in actions:
        rows.append(
            [
                "action",
                str(patient.id),
                patient.name,
                str(patient.age),
                patient.gender,
                patient.blood_group or "",
                patient.ward or "",
                patient.admission_status.value if hasattr(patient.admission_status, "value") else str(patient.admission_status),
                str(action.id),
                action.action_type.value if action.action_type else "",
                action.title,
                action.current_state,
                action.priority.value if hasattr(action.priority, "value") else str(action.priority),
                action.department,
                action.notes,
                "",
                "",
                "",
                "",
                action.created_at.isoformat(),
            ]
        )

    for note in notes:
        author = author_map.get(note.author_id)
        rows.append(
            [
                "note",
                str(patient.id),
                patient.name,
                str(patient.age),
                patient.gender,
                patient.blood_group or "",
                patient.ward or "",
                patient.admission_status.value if hasattr(patient.admission_status, "value") else str(patient.admission_status),
                "",
                "",
                "",
                "",
                "",
                "",
                "",
                str(note.id),
                note.note_type,
                note.content,
                author.name if author else "",
                note.created_at.isoformat(),
            ]
        )

    return _csv_response(f"patient-{patient_id}-report.csv", rows)


@router.get("/patients/{patient_id}/pdf")
def export_patient_pdf(
    patient_id: int,
    session: Session = Depends(get_session),
    _current_user: User = Depends(require_roles(UserRole.ADMIN, UserRole.DOCTOR, UserRole.NURSE)),
):
    patient = session.get(Patient, patient_id)
    if not patient:
        raise HTTPException(404, "Patient not found")

    actions = session.exec(
        select(ClinicalAction)
        .where(ClinicalAction.patient_id == patient_id)
        .order_by(ClinicalAction.created_at.asc())  # type: ignore[union-attr]
    ).all()
    notes = session.exec(
        select(PatientNote)
        .where(PatientNote.patient_id == patient_id)
        .order_by(PatientNote.created_at.asc())  # type: ignore[union-attr]
    ).all()

    lines = [
        f"Patient Report #{patient.id}",
        f"Name: {patient.name}",
        f"Age/Gender: {patient.age} / {patient.gender}",
        f"Ward: {patient.ward or '-'}",
        f"Status: {patient.admission_status.value if hasattr(patient.admission_status, 'value') else patient.admission_status}",
        "",
        "Clinical Actions",
        "ID | Type | Title | State | Priority | Department",
    ]

    if actions:
        for action in actions:
            lines.append(
                f"{action.id} | "
                f"{action.action_type.value if action.action_type else ''} | "
                f"{action.title or ''} | "
                f"{action.current_state} | "
                f"{action.priority.value if hasattr(action.priority, 'value') else action.priority} | "
                f"{action.department}"
            )
    else:
        lines.append("No actions")

    lines.extend(["", "Clinical Notes", "ID | Type | Content | Created"])
    if notes:
        for note in notes:
            lines.append(
                f"{note.id} | {note.note_type} | {note.content} | {note.created_at.strftime('%Y-%m-%d %H:%M')}"
            )
    else:
        lines.append("No notes")

    pdf = _build_simple_pdf(lines)
    return _pdf_response(f"patient-{patient_id}-report.pdf", pdf)


@router.get("/audit-log/csv")
def export_audit_csv(
    start_date: datetime | None = Query(default=None),
    end_date: datetime | None = Query(default=None),
    actor_id: int | None = Query(default=None),
    department: str = Query(default="", max_length=80),
    action_type: str = Query(default="", max_length=64),
    patient_id: int | None = Query(default=None),
    session: Session = Depends(get_session),
    _current_user: User = Depends(require_roles(UserRole.ADMIN, UserRole.DOCTOR)),
):
    query = select(ActionEvent).order_by(ActionEvent.timestamp.desc())  # type: ignore[union-attr]

    if start_date is not None:
        query = query.where(ActionEvent.timestamp >= start_date)
    if end_date is not None:
        query = query.where(ActionEvent.timestamp <= end_date)
    if actor_id is not None:
        query = query.where(ActionEvent.actor_id == actor_id)

    department_filter = department.strip()
    action_type_filter = action_type.strip().upper()
    action_type_value = None
    if action_type_filter:
        try:
            action_type_value = ActionType(action_type_filter)
        except ValueError:
            return _csv_response(
                "audit-log.csv",
                [[
                    "event_id",
                    "action_id",
                    "patient_id",
                    "patient_name",
                    "actor_id",
                    "actor_name",
                    "department",
                    "action_type",
                    "action_title",
                    "previous_state",
                    "new_state",
                    "notes",
                    "timestamp",
                ]],
            )
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
            return _csv_response(
                "audit-log.csv",
                [["event_id", "action_id", "patient_id", "patient_name", "actor_id", "actor_name", "department", "action_type", "previous_state", "new_state", "timestamp"]],
            )
        query = query.where(ActionEvent.action_id.in_(action_ids))  # type: ignore[union-attr]

    events = session.exec(query).all()

    action_ids = sorted({event.action_id for event in events})
    action_map: dict[int, ClinicalAction] = {}
    if action_ids:
        actions = session.exec(
            select(ClinicalAction).where(ClinicalAction.id.in_(action_ids))  # type: ignore[union-attr]
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

    rows = [[
        "event_id",
        "action_id",
        "patient_id",
        "patient_name",
        "actor_id",
        "actor_name",
        "department",
        "action_type",
        "action_title",
        "previous_state",
        "new_state",
        "notes",
        "timestamp",
    ]]

    for event in events:
        action = action_map.get(event.action_id)
        patient = patient_map.get(action.patient_id) if action else None
        actor = actor_map.get(event.actor_id) if event.actor_id is not None else None
        rows.append(
            [
                str(event.id),
                str(event.action_id),
                str(action.patient_id) if action else "",
                patient.name if patient else "",
                str(event.actor_id) if event.actor_id is not None else "",
                actor.name if actor else "",
                action.department if action else "",
                action.action_type.value if action and action.action_type else "",
                action.title if action else "",
                event.previous_state,
                event.new_state,
                event.notes,
                event.timestamp.isoformat(),
            ]
        )

    return _csv_response("audit-log.csv", rows)
