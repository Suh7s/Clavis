from datetime import UTC, datetime, timedelta

from sqlmodel import Session, select

from models import ActionEvent, ClinicalAction
from tests.conftest import TEST_ENGINE


def _create_patient(client, doctor_headers, name="Audit Analytics Patient"):
    created = client.post(
        "/patients",
        headers=doctor_headers,
        json={"name": name, "age": 54, "gender": "Male", "ward": "Ward A"},
    )
    assert created.status_code == 201, created.text
    return created.json()["id"]


def test_audit_log_events_and_filters(client, doctor_headers, lab_headers):
    patient_id = _create_patient(client, doctor_headers, name="Audit Filter")

    action = client.post(
        "/actions",
        headers=doctor_headers,
        json={
            "patient_id": patient_id,
            "action_type": "DIAGNOSTIC",
            "priority": "URGENT",
            "title": "CBC",
            "notes": "audit trail",
        },
    )
    assert action.status_code == 201, action.text
    action_id = action.json()["id"]

    p1 = client.patch(
        f"/actions/{action_id}/transition",
        headers=lab_headers,
        json={"new_state": "PROCESSING", "notes": "in process"},
    )
    assert p1.status_code == 200

    p2 = client.patch(
        f"/actions/{action_id}/transition",
        headers=lab_headers,
        json={"new_state": "COMPLETED", "notes": "complete"},
    )
    assert p2.status_code == 200

    all_events = client.get("/audit-log", headers=doctor_headers)
    assert all_events.status_code == 200
    payload = all_events.json()
    assert payload["total"] >= 3
    action_events = [event for event in payload["events"] if event["action_id"] == action_id]
    assert len(action_events) >= 3

    by_patient = client.get(f"/audit-log?patient_id={patient_id}", headers=doctor_headers)
    assert by_patient.status_code == 200
    assert by_patient.json()["total"] >= 3
    assert all(row["patient_id"] == patient_id for row in by_patient.json()["events"])

    lab_me = client.get("/auth/me", headers=lab_headers)
    assert lab_me.status_code == 200
    lab_id = lab_me.json()["id"]
    by_actor = client.get(f"/audit-log?actor_id={lab_id}", headers=doctor_headers)
    assert by_actor.status_code == 200
    assert by_actor.json()["total"] >= 2
    assert all(row["actor_id"] == lab_id for row in by_actor.json()["events"])

    by_department = client.get("/audit-log?department=Laboratory", headers=doctor_headers)
    assert by_department.status_code == 200
    assert any(row["action_id"] == action_id for row in by_department.json()["events"])

    by_type = client.get("/audit-log?action_type=DIAGNOSTIC", headers=doctor_headers)
    assert by_type.status_code == 200
    assert any(row["action_id"] == action_id for row in by_type.json()["events"])


def test_analytics_sla_compliance_and_throughput(client, doctor_headers, pharmacist_headers, nurse_headers, lab_headers):
    patient_id = _create_patient(client, doctor_headers, name="Analytics Patient")

    medication = client.post(
        "/actions",
        headers=doctor_headers,
        json={
            "patient_id": patient_id,
            "action_type": "MEDICATION",
            "priority": "URGENT",
            "title": "Paracetamol 500mg",
            "notes": "analytics medication",
        },
    )
    assert medication.status_code == 201
    med_id = medication.json()["id"]

    client.patch(
        f"/actions/{med_id}/transition",
        headers=pharmacist_headers,
        json={"new_state": "DISPENSED", "notes": "dispensed"},
    )
    client.patch(
        f"/actions/{med_id}/transition",
        headers=nurse_headers,
        json={"new_state": "ADMINISTERED", "notes": "administered"},
    )

    diagnostic = client.post(
        "/actions",
        headers=doctor_headers,
        json={
            "patient_id": patient_id,
            "action_type": "DIAGNOSTIC",
            "priority": "ROUTINE",
            "title": "CBC",
            "notes": "analytics diagnostic",
        },
    )
    assert diagnostic.status_code == 201
    diag_id = diagnostic.json()["id"]

    client.patch(
        f"/actions/{diag_id}/transition",
        headers=lab_headers,
        json={"new_state": "PROCESSING", "notes": "processing"},
    )
    client.patch(
        f"/actions/{diag_id}/transition",
        headers=lab_headers,
        json={"new_state": "COMPLETED", "notes": "complete"},
    )

    overdue = client.post(
        "/actions",
        headers=doctor_headers,
        json={
            "patient_id": patient_id,
            "action_type": "VITALS_REQUEST",
            "priority": "URGENT",
            "title": "Vitals check",
            "notes": "left pending",
        },
    )
    assert overdue.status_code == 201
    overdue_id = overdue.json()["id"]

    now = datetime.now(UTC).replace(tzinfo=None)
    with Session(TEST_ENGINE) as session:
        med = session.get(ClinicalAction, med_id)
        diag = session.get(ClinicalAction, diag_id)
        late = session.get(ClinicalAction, overdue_id)
        assert med is not None and diag is not None and late is not None

        med.sla_deadline = now - timedelta(minutes=30)  # completed before this deadline -> compliant
        diag.sla_deadline = now - timedelta(hours=5)  # completed after this deadline -> non-compliant
        late.sla_deadline = now - timedelta(minutes=5)  # active overdue bottleneck

        session.add(med)
        session.add(diag)
        session.add(late)
        session.commit()

        med_events = session.exec(select(ActionEvent).where(ActionEvent.action_id == med_id)).all()
        diag_events = session.exec(select(ActionEvent).where(ActionEvent.action_id == diag_id)).all()

        med_times = [now - timedelta(hours=2), now - timedelta(hours=1, minutes=30), now - timedelta(hours=1)]
        for event, ts in zip(sorted(med_events, key=lambda row: row.id), med_times):
            event.timestamp = ts
            session.add(event)

        diag_times = [now - timedelta(hours=6), now - timedelta(hours=5, minutes=30), now - timedelta(hours=4)]
        for event, ts in zip(sorted(diag_events, key=lambda row: row.id), diag_times):
            event.timestamp = ts
            session.add(event)
        session.commit()

    analytics = client.get("/analytics", headers=doctor_headers)
    assert analytics.status_code == 200, analytics.text
    payload = analytics.json()

    overall = payload["sla_compliance"]["overall"]
    assert overall["total"] >= 2
    assert overall["compliant"] >= 1
    assert 0 <= overall["rate"] <= 100

    throughput = payload["department_throughput"]
    assert sum(int(row["last_24h"]) for row in throughput) >= 2

    bottlenecks = payload["bottlenecks"]
    assert any(int(row["overdue_count"]) >= 1 for row in bottlenecks)


def test_export_csv_pdf_and_audit_csv(client, doctor_headers, nurse_headers):
    patient_id = _create_patient(client, doctor_headers, name="Export Patient")

    note = client.post(
        f"/patients/{patient_id}/notes",
        headers=nurse_headers,
        json={"note_type": "clinical", "content": "Export validation note"},
    )
    assert note.status_code == 201

    patient_csv = client.get(f"/export/patients/{patient_id}/csv", headers=doctor_headers)
    assert patient_csv.status_code == 200
    assert "text/csv" in patient_csv.headers.get("content-type", "")
    assert "record_type" in patient_csv.text

    patient_pdf = client.get(f"/export/patients/{patient_id}/pdf", headers=doctor_headers)
    assert patient_pdf.status_code == 200
    assert "application/pdf" in patient_pdf.headers.get("content-type", "")
    assert patient_pdf.content.startswith(b"%PDF-")

    audit_csv = client.get("/export/audit-log/csv", headers=doctor_headers)
    assert audit_csv.status_code == 200
    assert "text/csv" in audit_csv.headers.get("content-type", "")
    assert "event_id" in audit_csv.text
