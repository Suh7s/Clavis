from datetime import UTC, datetime, timedelta

from sqlmodel import Session

from models import ClinicalAction
from tests.conftest import TEST_ENGINE


def _create_patient(client, headers, name="Lifecycle Patient"):
    created = client.post(
        "/patients",
        headers=headers,
        json={"name": name, "age": 59, "gender": "Female", "ward": "Ward A"},
    )
    assert created.status_code == 201, created.text
    return created.json()["id"]


def test_valid_invalid_transitions_and_role_enforcement(
    client,
    doctor_headers,
    nurse_headers,
    pharmacist_headers,
):
    patient_id = _create_patient(client, doctor_headers)

    medication = client.post(
        "/actions",
        headers=doctor_headers,
        json={
            "patient_id": patient_id,
            "action_type": "MEDICATION",
            "priority": "URGENT",
            "title": "Warfarin 5mg",
            "notes": "night dose",
        },
    )
    assert medication.status_code == 201, medication.text
    action_id = medication.json()["id"]

    bad_jump = client.patch(
        f"/actions/{action_id}/transition",
        headers=pharmacist_headers,
        json={"new_state": "ADMINISTERED", "notes": "invalid from PRESCRIBED"},
    )
    assert bad_jump.status_code == 422

    nurse_denied = client.patch(
        f"/actions/{action_id}/transition",
        headers=nurse_headers,
        json={"new_state": "DISPENSED", "notes": "nurse cannot dispense"},
    )
    assert nurse_denied.status_code == 403

    dispensed = client.patch(
        f"/actions/{action_id}/transition",
        headers=pharmacist_headers,
        json={"new_state": "DISPENSED", "notes": "dispensed"},
    )
    assert dispensed.status_code == 200
    assert dispensed.json()["current_state"] == "DISPENSED"


def test_bulk_lifecycle_warnings_and_sla_overdue_detection(
    client,
    doctor_headers,
    pharmacist_headers,
):
    patient_id = _create_patient(client, doctor_headers, name="Bulk Lifecycle")

    seed_med = client.post(
        "/actions",
        headers=doctor_headers,
        json={
            "patient_id": patient_id,
            "action_type": "MEDICATION",
            "priority": "ROUTINE",
            "title": "Warfarin 2mg",
            "notes": "base med",
        },
    )
    assert seed_med.status_code == 201

    warning_med = client.post(
        "/actions",
        headers=doctor_headers,
        json={
            "patient_id": patient_id,
            "action_type": "MEDICATION",
            "priority": "ROUTINE",
            "title": "Amoxicillin 500mg",
            "notes": "interaction check",
        },
    )
    assert warning_med.status_code == 201
    assert warning_med.json().get("warnings"), warning_med.json()

    bulk = client.post(
        "/actions/bulk",
        headers=doctor_headers,
        json={
            "actions": [
                {
                    "patient_id": patient_id,
                    "action_type": "MEDICATION",
                    "priority": "ROUTINE",
                    "title": "Ibuprofen 200mg",
                    "notes": "prn",
                },
                {
                    "patient_id": patient_id,
                    "action_type": "DIAGNOSTIC",
                    "priority": "URGENT",
                    "title": "CBC",
                    "notes": "lab",
                },
            ]
        },
    )
    assert bulk.status_code == 200, bulk.text
    created = bulk.json()["successful"]
    assert len(created) == 2
    med_id = next(item["action"]["id"] for item in created if item["action"]["action_type"] == "MEDICATION")

    transition = client.patch(
        "/actions/bulk/transition",
        headers=pharmacist_headers,
        json={
            "transitions": [
                {"action_id": med_id, "new_state": "DISPENSED", "notes": "ok"},
                {"action_id": 999999, "new_state": "DISPENSED", "notes": "missing"},
            ]
        },
    )
    assert transition.status_code == 200
    assert len(transition.json()["successful"]) == 1
    assert len(transition.json()["failed"]) == 1

    with Session(TEST_ENGINE) as session:
        action = session.get(ClinicalAction, med_id)
        assert action is not None
        action.sla_deadline = datetime.now(UTC).replace(tzinfo=None) - timedelta(minutes=5)
        session.add(action)
        session.commit()

    escalations = client.get("/actions/escalations", headers=doctor_headers)
    assert escalations.status_code == 200
    overdue_ids = {row["id"] for row in escalations.json()}
    assert med_id in overdue_ids
