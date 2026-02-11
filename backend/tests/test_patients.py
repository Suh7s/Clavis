def test_patient_crud_search_soft_delete(client, doctor_headers):
    p1 = client.post(
        "/patients",
        headers=doctor_headers,
        json={"name": "Alice Patel", "age": 50, "gender": "Female", "ward": "Ward 1"},
    )
    p2 = client.post(
        "/patients",
        headers=doctor_headers,
        json={"name": "Bob Singh", "age": 39, "gender": "Male", "ward": "Ward 2"},
    )
    assert p1.status_code == 201
    assert p2.status_code == 201

    listing = client.get("/patients?page=1&page_size=50", headers=doctor_headers)
    assert listing.status_code == 200
    payload = listing.json()
    assert "patients" in payload
    assert payload["total"] == 2

    search = client.get("/patients?search=Alice", headers=doctor_headers)
    assert search.status_code == 200
    assert len(search.json()["patients"]) == 1
    patient_id = search.json()["patients"][0]["id"]

    update = client.patch(
        f"/patients/{patient_id}",
        headers=doctor_headers,
        json={"ward": "Ward X", "blood_group": "A+"},
    )
    assert update.status_code == 200
    assert update.json()["ward"] == "Ward X"

    remove = client.delete(f"/patients/{patient_id}", headers=doctor_headers)
    assert remove.status_code == 200

    active_only = client.get("/patients", headers=doctor_headers)
    assert active_only.status_code == 200
    active_ids = {item["id"] for item in active_only.json()["patients"]}
    assert patient_id not in active_ids

    include_inactive = client.get("/patients?include_inactive=true", headers=doctor_headers)
    assert include_inactive.status_code == 200
    all_ids = {item["id"] for item in include_inactive.json()["patients"]}
    assert patient_id in all_ids


def test_patient_transfer_and_history(client, doctor_headers):
    created = client.post(
        "/patients",
        headers=doctor_headers,
        json={"name": "Transfer Case", "age": 60, "gender": "Female", "ward": "Ward A"},
    )
    assert created.status_code == 201
    patient_id = created.json()["id"]

    doctors = client.get("/patients/staff/doctors", headers=doctor_headers)
    assert doctors.status_code == 200
    options = doctors.json()
    assert options
    to_doctor = options[0]["id"]

    transfer = client.post(
        f"/patients/{patient_id}/transfer",
        headers=doctor_headers,
        json={"to_doctor_id": to_doctor, "to_ward": "ICU", "reason": "Higher acuity"},
    )
    assert transfer.status_code == 200
    transfer_payload = transfer.json()
    assert transfer_payload["to_ward"] == "ICU"
    assert transfer_payload["reason"] == "Higher acuity"

    history = client.get(f"/patients/{patient_id}/transfers", headers=doctor_headers)
    assert history.status_code == 200
    rows = history.json()
    assert len(rows) == 1
    assert rows[0]["to_ward"] == "ICU"


def test_discharge_requires_terminal_actions(client, doctor_headers, lab_headers):
    created = client.post(
        "/patients",
        headers=doctor_headers,
        json={"name": "Discharge Case", "age": 47, "gender": "Male"},
    )
    assert created.status_code == 201
    patient_id = created.json()["id"]

    action = client.post(
        "/actions",
        headers=doctor_headers,
        json={
            "patient_id": patient_id,
            "action_type": "DIAGNOSTIC",
            "priority": "ROUTINE",
            "title": "CBC Panel",
            "notes": "Routine check",
        },
    )
    assert action.status_code == 201
    action_id = action.json()["id"]

    blocked = client.post(
        f"/patients/{patient_id}/discharge",
        headers=doctor_headers,
        json={"notes": "Attempt early"},
    )
    assert blocked.status_code == 422

    t1 = client.patch(
        f"/actions/{action_id}/transition",
        headers=lab_headers,
        json={"new_state": "PROCESSING", "notes": "sample underway"},
    )
    assert t1.status_code == 200

    t2 = client.patch(
        f"/actions/{action_id}/transition",
        headers=lab_headers,
        json={"new_state": "COMPLETED", "notes": "done"},
    )
    assert t2.status_code == 200

    discharged = client.post(
        f"/patients/{patient_id}/discharge",
        headers=doctor_headers,
        json={"notes": "Stable"},
    )
    assert discharged.status_code == 200
    assert discharged.json()["admission_status"] == "DISCHARGED"
