def _create_patient(client, headers, name="Action Case"):
    response = client.post(
        "/patients",
        headers=headers,
        json={"name": name, "age": 55, "gender": "Male", "ward": "Ward A"},
    )
    assert response.status_code == 201, response.text
    return response.json()["id"]


def test_medication_lifecycle_and_interaction_warning(
    client,
    doctor_headers,
    pharmacist_headers,
    nurse_headers,
):
    patient_id = _create_patient(client, doctor_headers)

    first_med = client.post(
        "/actions",
        headers=doctor_headers,
        json={
            "patient_id": patient_id,
            "action_type": "MEDICATION",
            "priority": "ROUTINE",
            "title": "Warfarin 2mg",
            "notes": "Evening",
        },
    )
    assert first_med.status_code == 201

    second_med = client.post(
        "/actions",
        headers=doctor_headers,
        json={
            "patient_id": patient_id,
            "action_type": "MEDICATION",
            "priority": "ROUTINE",
            "title": "Amoxicillin 500mg",
            "notes": "Three times daily",
        },
    )
    assert second_med.status_code == 201
    warnings = second_med.json().get("warnings", [])
    assert warnings, second_med.json()

    action_id = first_med.json()["id"]

    invalid = client.patch(
        f"/actions/{action_id}/transition",
        headers=nurse_headers,
        json={"new_state": "ADMINISTERED", "notes": "invalid jump"},
    )
    assert invalid.status_code == 422

    dispense = client.patch(
        f"/actions/{action_id}/transition",
        headers=pharmacist_headers,
        json={"new_state": "DISPENSED", "notes": "sent to nursing"},
    )
    assert dispense.status_code == 200

    administer = client.patch(
        f"/actions/{action_id}/transition",
        headers=nurse_headers,
        json={"new_state": "ADMINISTERED", "notes": "done"},
    )
    assert administer.status_code == 200
    assert administer.json()["current_state"] == "ADMINISTERED"


def test_bulk_create_and_bulk_transition(client, doctor_headers, pharmacist_headers):
    patient_id = _create_patient(client, doctor_headers, name="Bulk Case")

    bulk_create = client.post(
        "/actions/bulk",
        headers=doctor_headers,
        json={
            "actions": [
                {
                    "patient_id": patient_id,
                    "action_type": "MEDICATION",
                    "priority": "ROUTINE",
                    "title": "Ibuprofen 200mg",
                    "notes": "PRN",
                },
                {
                    "patient_id": 99999,
                    "action_type": "DIAGNOSTIC",
                    "priority": "ROUTINE",
                    "title": "CBC",
                    "notes": "invalid patient",
                },
            ]
        },
    )
    assert bulk_create.status_code == 200
    bulk_payload = bulk_create.json()
    assert len(bulk_payload["successful"]) == 1
    assert len(bulk_payload["failed"]) == 1

    action_id = bulk_payload["successful"][0]["action"]["id"]

    bulk_transition = client.patch(
        "/actions/bulk/transition",
        headers=pharmacist_headers,
        json={
            "transitions": [
                {"action_id": action_id, "new_state": "DISPENSED", "notes": "ok"},
                {"action_id": 123456, "new_state": "DISPENSED", "notes": "missing"},
            ]
        },
    )
    assert bulk_transition.status_code == 200
    trans_payload = bulk_transition.json()
    assert len(trans_payload["successful"]) == 1
    assert len(trans_payload["failed"]) == 1


def test_discharged_patient_blocks_action_mutations(client, doctor_headers, lab_headers):
    patient_id = _create_patient(client, doctor_headers, name="Discharged Action Case")

    action = client.post(
        "/actions",
        headers=doctor_headers,
        json={
            "patient_id": patient_id,
            "action_type": "DIAGNOSTIC",
            "priority": "ROUTINE",
            "title": "CBC Panel",
            "notes": "test",
        },
    )
    assert action.status_code == 201
    action_id = action.json()["id"]

    to_processing = client.patch(
        f"/actions/{action_id}/transition",
        headers=lab_headers,
        json={"new_state": "PROCESSING", "notes": "started"},
    )
    assert to_processing.status_code == 200

    to_done = client.patch(
        f"/actions/{action_id}/transition",
        headers=lab_headers,
        json={"new_state": "COMPLETED", "notes": "completed"},
    )
    assert to_done.status_code == 200

    discharge = client.post(
        f"/patients/{patient_id}/discharge",
        headers=doctor_headers,
        json={"notes": "ready"},
    )
    assert discharge.status_code == 200

    create_blocked = client.post(
        "/actions",
        headers=doctor_headers,
        json={
            "patient_id": patient_id,
            "action_type": "MEDICATION",
            "priority": "ROUTINE",
            "title": "Aspirin 75mg",
            "notes": "blocked",
        },
    )
    assert create_blocked.status_code == 422

    transition_blocked = client.patch(
        f"/actions/{action_id}/transition",
        headers=doctor_headers,
        json={"new_state": "FAILED", "notes": "should not mutate"},
    )
    assert transition_blocked.status_code == 422
