import csv
import io
from datetime import datetime
from html import escape

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import HTMLResponse, StreamingResponse
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

    action_rows = "".join(
        f"<tr><td>{action.id}</td><td>{escape(action.action_type.value if action.action_type else '')}</td>"
        f"<td>{escape(action.title or '')}</td><td>{escape(action.current_state)}</td>"
        f"<td>{escape(str(action.priority))}</td><td>{escape(action.department)}</td></tr>"
        for action in actions
    )
    note_rows = "".join(
        f"<tr><td>{note.id}</td><td>{escape(note.note_type)}</td><td>{escape(note.content)}</td>"
        f"<td>{note.created_at.strftime('%Y-%m-%d %H:%M')}</td></tr>"
        for note in notes
    )

    html = f"""
<!doctype html>
<html>
<head>
  <meta charset=\"utf-8\" />
  <title>Patient Report #{patient.id}</title>
  <style>
    body {{ font-family: Arial, sans-serif; margin: 24px; color: #1f2937; }}
    h1, h2 {{ margin-bottom: 8px; }}
    .meta {{ margin-bottom: 16px; color: #4b5563; font-size: 14px; }}
    table {{ width: 100%; border-collapse: collapse; margin-bottom: 18px; }}
    th, td {{ border: 1px solid #d1d5db; padding: 8px; font-size: 13px; vertical-align: top; }}
    th {{ background: #f3f4f6; text-align: left; }}
  </style>
</head>
<body>
  <h1>Patient Report</h1>
  <div class=\"meta\">Patient #{patient.id} · {escape(patient.name)} · {patient.age}y · {escape(patient.gender)} · Ward {escape(patient.ward or '—')}</div>

  <h2>Clinical Actions</h2>
  <table>
    <thead>
      <tr><th>ID</th><th>Type</th><th>Title</th><th>State</th><th>Priority</th><th>Department</th></tr>
    </thead>
    <tbody>{action_rows or '<tr><td colspan="6">No actions</td></tr>'}</tbody>
  </table>

  <h2>Clinical Notes</h2>
  <table>
    <thead>
      <tr><th>ID</th><th>Type</th><th>Content</th><th>Created</th></tr>
    </thead>
    <tbody>{note_rows or '<tr><td colspan="4">No notes</td></tr>'}</tbody>
  </table>
</body>
</html>
""".strip()

    return HTMLResponse(
        content=html,
        headers={"Content-Disposition": f'attachment; filename="patient-{patient_id}-report.html"'},
    )


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
