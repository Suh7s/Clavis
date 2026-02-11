from __future__ import annotations

from pathlib import Path
import sys

from fastapi.testclient import TestClient
from sqlmodel import Session, select

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from database import engine  # noqa: E402
from main import app  # noqa: E402
from models import ActionEvent  # noqa: E402


def assert_status(response, expected: int, label: str):
    if response.status_code != expected:
        raise RuntimeError(f"{label} failed: {response.status_code} {response.text}")
    print(f"[OK] {label}")


def login_headers(client: TestClient, email: str, password: str) -> dict[str, str]:
    response = client.post("/auth/login", json={"email": email, "password": password})
    assert_status(response, 200, f"Login {email}")
    return {"Authorization": f"Bearer {response.json()['access_token']}"}


def run():
    client = TestClient(app)

    print("1) Reset demo data")
    reset = client.get("/demo/reset")
    assert_status(reset, 200, "Demo reset")

    print("2) Login role accounts")
    doctor_headers = login_headers(client, "doctor@clavis.local", "doctor123")
    nurse_headers = login_headers(client, "nurse@clavis.local", "nurse123")
    radiology_headers = login_headers(client, "radiology@clavis.local", "radiology123")
    admin_headers = login_headers(client, "admin@clavis.local", "admin123")

    print("3) Nurse can create patient and doctor can see same patient")
    create_patient = client.post(
        "/patients",
        headers=nurse_headers,
        json={"name": "Asha Verma", "age": 41, "gender": "Female"},
    )
    assert_status(create_patient, 201, "Create patient by nurse")
    patient_id = create_patient.json()["id"]

    list_patients = client.get("/patients", headers=doctor_headers)
    assert_status(list_patients, 200, "List patients for doctor")
    if patient_id not in {item["id"] for item in list_patients.json()}:
        raise RuntimeError("Doctor did not see nurse-created patient")
    print("[OK] Shared patient visibility")

    print("4) Create diagnostic action and verify initial event exists")
    action_resp = client.post(
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
    assert_status(action_resp, 201, "Create diagnostic action")
    action_id = action_resp.json()["id"]

    with Session(engine) as session:
        event = session.exec(
            select(ActionEvent).where(ActionEvent.action_id == action_id)
        ).first()
        if event is None:
            raise RuntimeError("Missing initial ActionEvent for new action")
    print("[OK] Initial event written atomically")

    print("5) Invalid and unauthorized transitions are blocked")
    unauthorized = client.patch(
        f"/actions/{action_id}/transition",
        headers=nurse_headers,
        json={"new_state": "PROCESSING", "notes": ""},
    )
    assert_status(unauthorized, 403, "Unauthorized transition rejected")

    invalid = client.patch(
        f"/actions/{action_id}/transition",
        headers=radiology_headers,
        json={"new_state": "ADMINISTERED", "notes": ""},
    )
    assert_status(invalid, 422, "Invalid transition rejected")

    print("6) Status-board websocket receives live action updates")
    with client.websocket_connect(
        f"/ws/status-board?token={admin_headers['Authorization'].split(' ', 1)[1]}"
    ) as ws:
        follow_up = client.post(
            "/actions",
            headers=doctor_headers,
            json={
                "patient_id": patient_id,
                "action_type": "MEDICATION",
                "priority": "ROUTINE",
                "title": "Amoxicillin 500mg",
                "notes": "3x daily",
            },
        )
        assert_status(follow_up, 201, "Create medication action")
        ws_msg = ws.receive_json()
        if ws_msg.get("event") != "action_created":
            raise RuntimeError(f"Unexpected websocket event: {ws_msg}")
    print("[OK] Status-board websocket live event")

    print("7) Custom type validation catches duplicates")
    invalid_custom_type = client.post(
        "/custom-action-types",
        headers=doctor_headers,
        json={
            "name": "BLOOD_PANEL",
            "department": "Laboratory",
            "states": ["ORDERED", "ORDERED", "COMPLETED"],
            "terminal_state": "COMPLETED",
            "sla_routine_minutes": 120,
            "sla_urgent_minutes": 30,
            "sla_critical_minutes": 10,
        },
    )
    assert_status(invalid_custom_type, 422, "Duplicate custom states rejected")

    print("8) Status board API returns patient row and escalation list")
    board = client.get("/patients/status-board", headers=admin_headers)
    escalations = client.get("/actions/escalations", headers=admin_headers)
    assert_status(board, 200, "Status board endpoint")
    assert_status(escalations, 200, "Escalations endpoint")
    if not board.json().get("patients"):
        raise RuntimeError("Status board returned no patient rows")
    print("[OK] Status board payload looks valid")

    print("\nPreflight checks passed.")


if __name__ == "__main__":
    run()
