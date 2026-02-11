from __future__ import annotations

from datetime import UTC, datetime, timedelta
import os
from pathlib import Path
import sys

from fastapi.testclient import TestClient
from sqlmodel import Session, select

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

os.environ.setdefault("CLAVIS_ENABLE_DEMO_RESET", "1")

from database import engine  # noqa: E402
from main import app  # noqa: E402
from models import ClinicalAction  # noqa: E402


def login(client: TestClient, email: str, password: str) -> dict:
    resp = client.post("/auth/login", json={"email": email, "password": password})
    if resp.status_code != 200:
        raise RuntimeError(f"Login failed for {email}: {resp.status_code}")
    token = resp.json()["access_token"]
    return {"Authorization": f"Bearer {token}"}


def assert_status(resp, expected: int, label: str):
    if resp.status_code != expected:
        raise RuntimeError(f"{label} failed: {resp.status_code} {resp.text}")
    print(f"[OK] {label}")


def transition(client: TestClient, headers: dict, action_id: int, new_state: str, notes: str = ""):
    resp = client.patch(
        f"/actions/{action_id}/transition",
        headers=headers,
        json={"new_state": new_state, "notes": notes},
    )
    assert_status(resp, 200, f"Transition #{action_id} -> {new_state}")


def main():
    client = TestClient(app)

    print("Step 0: Reset demo data")
    reset = client.get("/demo/reset")
    assert_status(reset, 200, "Demo reset")

    doctor_headers = login(client, "doctor@clavis.local", "doctor123")
    nurse_headers = login(client, "nurse@clavis.local", "nurse123")
    pharmacy_headers = login(client, "pharmacy@clavis.local", "pharmacy123")
    radiology_headers = login(client, "radiology@clavis.local", "radiology123")
    admin_headers = login(client, "admin@clavis.local", "admin123")
    print("[OK] Logged in all demo roles")

    patients_resp = client.get("/patients", headers=doctor_headers)
    assert_status(patients_resp, 200, "List patients")
    patients_data = patients_resp.json()
    patients = patients_data.get("patients", patients_data) if isinstance(patients_data, dict) else patients_data
    if patients:
        patient_id = patients[0]["id"]
    else:
        create_patient = client.post(
            "/patients",
            headers=doctor_headers,
            json={"name": "Demo Patient", "age": 58, "gender": "Male"},
        )
        assert_status(create_patient, 201, "Create demo patient")
        patient_id = create_patient.json()["id"]
    print(f"[OK] Using patient #{patient_id}")

    print("Step 1: Doctor opens patient summary")
    summary = client.get(f"/patients/{patient_id}/summary", headers=doctor_headers)
    assert_status(summary, 200, "Patient summary")

    print("Step 2: Doctor creates diagnostic request")
    create_diag = client.post(
        "/actions",
        headers=doctor_headers,
        json={
            "patient_id": patient_id,
            "action_type": "DIAGNOSTIC",
            "priority": "URGENT",
            "title": "Chest X-Ray",
            "notes": "Suspected pneumonia",
        },
    )
    assert_status(create_diag, 201, "Create diagnostic action")
    diag_id = create_diag.json()["id"]

    print("Step 3: Doctor creates medication")
    create_med = client.post(
        "/actions",
        headers=doctor_headers,
        json={
            "patient_id": patient_id,
            "action_type": "MEDICATION",
            "priority": "ROUTINE",
            "title": "Amoxicillin 500mg",
            "notes": "Oral, 3x daily for 7 days",
        },
    )
    assert_status(create_med, 201, "Create medication action")
    med_id = create_med.json()["id"]

    print("Step 4: Radiology transitions diagnostic to PROCESSING")
    queue_rad = client.get("/actions/department/Radiology", headers=radiology_headers)
    assert_status(queue_rad, 200, "Radiology queue read")
    transition(client, radiology_headers, diag_id, "PROCESSING", "X-Ray started")

    print("Step 5: Pharmacy dispenses medication")
    queue_pharm = client.get("/actions/department/Pharmacy", headers=pharmacy_headers)
    assert_status(queue_pharm, 200, "Pharmacy queue read")
    transition(client, pharmacy_headers, med_id, "DISPENSED", "Dispensed to nursing station")

    print("Step 6: Nurse administers medication")
    queue_nursing = client.get("/actions/department/Nursing", headers=nurse_headers)
    assert_status(queue_nursing, 200, "Nursing queue read")
    transition(client, nurse_headers, med_id, "ADMINISTERED", "Dose given")

    print("Step 7: Radiology completes with report")
    transition(
        client,
        radiology_headers,
        diag_id,
        "COMPLETED",
        "Bilateral infiltrates noted — suggest follow-up CT",
    )

    print("Step 8: SLA escalation simulation")
    escalation_action_id = None
    original_deadline = None
    original_state = None
    created_temp_escalation = False
    with Session(engine) as session:
        action = session.exec(
            select(ClinicalAction)
            .where(ClinicalAction.patient_id == patient_id)
            .where(ClinicalAction.current_state.in_(["REQUESTED", "PRESCRIBED", "ISSUED"]))  # type: ignore[union-attr]
        ).first()
        if action is None:
            temp_action = client.post(
                "/actions",
                headers=doctor_headers,
                json={
                    "patient_id": patient_id,
                    "action_type": "VITALS_REQUEST",
                    "priority": "URGENT",
                    "title": "Escalation Probe",
                    "notes": "Temporary action for escalation demo",
                },
            )
            assert_status(temp_action, 201, "Create temporary escalation action")
            created_temp_escalation = True
            action = session.get(ClinicalAction, temp_action.json()["id"])

        if action is not None:
            escalation_action_id = action.id
            original_deadline = action.sla_deadline
            original_state = action.current_state
            action.sla_deadline = datetime.now(UTC).replace(tzinfo=None) - timedelta(minutes=5)
            session.add(action)
            session.commit()
    escalations = client.get("/actions/escalations", headers=admin_headers)
    assert_status(escalations, 200, "Escalations endpoint")
    if not escalations.json():
        raise RuntimeError("Escalation simulation failed: no overdue actions found")
    print("[OK] Escalation visible")

    if escalation_action_id is not None:
        if created_temp_escalation:
            transition(
                client,
                nurse_headers,
                escalation_action_id,
                "RECORDED",
                "Escalation probe cleared after demo",
            )
        else:
            with Session(engine) as session:
                action = session.get(ClinicalAction, escalation_action_id)
                if action:
                    action.current_state = original_state or action.current_state
                    action.sla_deadline = original_deadline or (
                        datetime.now(UTC).replace(tzinfo=None) + timedelta(minutes=30)
                    )
                    session.add(action)
                    session.commit()

    print("Step 9: Final doctor summary")
    final_summary = client.get(f"/patients/{patient_id}/summary", headers=doctor_headers)
    assert_status(final_summary, 200, "Final summary")
    summary_payload = final_summary.json()
    print(
        "Final counts:",
        {
            "pending": summary_payload["pending"],
            "in_progress": summary_payload["in_progress"],
            "completed": summary_payload["completed"],
            "overdue": summary_payload["overdue"],
        },
    )

    print("\nDPR demo flow completed.")


if __name__ == "__main__":
    main()
