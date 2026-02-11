import pytest
from starlette.websockets import WebSocketDisconnect

from ws import manager


def _token(client, email: str, password: str) -> str:
    response = client.post("/auth/login", json={"email": email, "password": password})
    assert response.status_code == 200, response.text
    return response.json()["access_token"]


def _create_patient(client, doctor_token: str) -> int:
    created = client.post(
        "/patients",
        headers={"Authorization": f"Bearer {doctor_token}"},
        json={"name": "WS Patient", "age": 38, "gender": "Female", "ward": "Ward W"},
    )
    assert created.status_code == 201, created.text
    return created.json()["id"]


def test_websocket_connections_require_valid_token(client, seeded_users):
    _ = seeded_users
    with pytest.raises(WebSocketDisconnect):
        with client.websocket_connect("/ws/patients/1"):
            pass

    with pytest.raises(WebSocketDisconnect):
        with client.websocket_connect("/ws/patients/1?token=bad-token"):
            pass


def test_patient_channel_receives_broadcast_on_action_create(client, seeded_users):
    doctor_token = _token(client, seeded_users["doctor"]["email"], seeded_users["doctor"]["password"])
    patient_id = _create_patient(client, doctor_token)

    with client.websocket_connect(f"/ws/patients/{patient_id}?token={doctor_token}") as ws:
        created = client.post(
            "/actions",
            headers={"Authorization": f"Bearer {doctor_token}"},
            json={
                "patient_id": patient_id,
                "action_type": "DIAGNOSTIC",
                "priority": "URGENT",
                "title": "CBC",
                "notes": "websocket test",
            },
        )
        assert created.status_code == 201, created.text
        message = ws.receive_json()
        assert message["event"] == "action_created"
        assert message["patient_id"] == patient_id


def test_department_channel_routing_and_access(client, seeded_users):
    doctor_token = _token(client, seeded_users["doctor"]["email"], seeded_users["doctor"]["password"])
    pharmacist_token = _token(client, seeded_users["pharmacist"]["email"], seeded_users["pharmacist"]["password"])
    nurse_token = _token(client, seeded_users["nurse"]["email"], seeded_users["nurse"]["password"])

    patient_id = _create_patient(client, doctor_token)

    with pytest.raises(WebSocketDisconnect):
        with client.websocket_connect(f"/ws/department/Laboratory?token={pharmacist_token}"):
            pass

    with client.websocket_connect(f"/ws/department/Pharmacy?token={pharmacist_token}") as pharmacy_ws:
        with client.websocket_connect(f"/ws/department/Nursing?token={nurse_token}") as nursing_ws:
            action = client.post(
                "/actions",
                headers={"Authorization": f"Bearer {doctor_token}"},
                json={
                    "patient_id": patient_id,
                    "action_type": "MEDICATION",
                    "priority": "ROUTINE",
                    "title": "Paracetamol 500mg",
                    "notes": "q8h",
                },
            )
            assert action.status_code == 201, action.text
            action_id = action.json()["id"]

            pharmacy_message = pharmacy_ws.receive_json()
            assert pharmacy_message["event"] == "action_created"
            assert "Pharmacy" in pharmacy_message.get("queue_departments", [])

            dispensed = client.patch(
                f"/actions/{action_id}/transition",
                headers={"Authorization": f"Bearer {pharmacist_token}"},
                json={"new_state": "DISPENSED", "notes": "sent to nurse"},
            )
            assert dispensed.status_code == 200, dispensed.text

            nursing_message = nursing_ws.receive_json()
            assert nursing_message["event"] == "action_updated"
            assert "Nursing" in nursing_message.get("queue_departments", [])


def test_websocket_disconnect_cleans_manager_state(client, seeded_users):
    doctor_token = _token(client, seeded_users["doctor"]["email"], seeded_users["doctor"]["password"])
    patient_id = _create_patient(client, doctor_token)

    with client.websocket_connect(f"/ws/patients/{patient_id}?token={doctor_token}"):
        assert patient_id in manager.patient_connections
        assert len(manager.patient_connections[patient_id]) >= 1

    assert patient_id not in manager.patient_connections
