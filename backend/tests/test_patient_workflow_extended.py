def test_patient_create_search_and_pagination(client, doctor_headers):
    names = ["Alpha Case", "Bravo Case", "Charlie Case"]
    for idx, name in enumerate(names):
        created = client.post(
            "/patients",
            headers=doctor_headers,
            json={"name": name, "age": 30 + idx, "gender": "Female", "ward": "Ward A"},
        )
        assert created.status_code == 201, created.text

    page_1 = client.get("/patients?page=1&page_size=2", headers=doctor_headers)
    assert page_1.status_code == 200
    payload_1 = page_1.json()
    assert payload_1["total"] == 3
    assert len(payload_1["patients"]) == 2

    page_2 = client.get("/patients?page=2&page_size=2", headers=doctor_headers)
    assert page_2.status_code == 200
    payload_2 = page_2.json()
    assert len(payload_2["patients"]) == 1

    search = client.get("/patients?search=Bravo", headers=doctor_headers)
    assert search.status_code == 200
    search_payload = search.json()
    assert search_payload["total"] == 1
    assert search_payload["patients"][0]["name"] == "Bravo Case"


def test_transfer_and_discharge_guards(client, doctor_headers, lab_headers):
    created = client.post(
        "/patients",
        headers=doctor_headers,
        json={"name": "Transfer Guard", "age": 46, "gender": "Male", "ward": "Ward 1"},
    )
    assert created.status_code == 201
    patient_id = created.json()["id"]

    doctor_pool = client.get("/patients/staff/doctors", headers=doctor_headers)
    assert doctor_pool.status_code == 200
    to_doctor_id = doctor_pool.json()[0]["id"]

    transfer = client.post(
        f"/patients/{patient_id}/transfer",
        headers=doctor_headers,
        json={"to_doctor_id": to_doctor_id, "to_ward": "ICU", "reason": "Monitoring"},
    )
    assert transfer.status_code == 200
    assert transfer.json()["to_ward"] == "ICU"

    action = client.post(
        "/actions",
        headers=doctor_headers,
        json={
            "patient_id": patient_id,
            "action_type": "DIAGNOSTIC",
            "priority": "URGENT",
            "title": "CBC",
            "notes": "Pre-discharge",
        },
    )
    assert action.status_code == 201
    action_id = action.json()["id"]

    to_processing = client.patch(
        f"/actions/{action_id}/transition",
        headers=lab_headers,
        json={"new_state": "PROCESSING", "notes": "in lab"},
    )
    assert to_processing.status_code == 200

    to_complete = client.patch(
        f"/actions/{action_id}/transition",
        headers=lab_headers,
        json={"new_state": "COMPLETED", "notes": "done"},
    )
    assert to_complete.status_code == 200

    discharged = client.post(
        f"/patients/{patient_id}/discharge",
        headers=doctor_headers,
        json={"notes": "Clear for discharge"},
    )
    assert discharged.status_code == 200
    assert discharged.json()["admission_status"] == "DISCHARGED"

    blocked_transfer = client.post(
        f"/patients/{patient_id}/transfer",
        headers=doctor_headers,
        json={"to_ward": "Ward 2", "reason": "should fail"},
    )
    assert blocked_transfer.status_code == 422
