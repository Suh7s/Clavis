def _create_patient(client, doctor_headers):
    response = client.post(
        "/patients",
        headers=doctor_headers,
        json={"name": "RBAC Patient", "age": 52, "gender": "Female"},
    )
    assert response.status_code == 201
    return response.json()["id"]


def test_rbac_create_patient_permissions(client, doctor_headers, nurse_headers, admin_headers):
    blocked = client.post(
        "/patients",
        headers=nurse_headers,
        json={"name": "Nurse Blocked", "age": 28, "gender": "Female"},
    )
    assert blocked.status_code == 403

    doctor_allowed = client.post(
        "/patients",
        headers=doctor_headers,
        json={"name": "Doctor Allowed", "age": 52, "gender": "Male"},
    )
    assert doctor_allowed.status_code == 201

    admin_allowed = client.post(
        "/patients",
        headers=admin_headers,
        json={"name": "Admin Allowed", "age": 41, "gender": "Female"},
    )
    assert admin_allowed.status_code == 201


def test_rbac_create_action_permissions(client, doctor_headers, nurse_headers):
    patient_id = _create_patient(client, doctor_headers)

    blocked = client.post(
        "/actions",
        headers=nurse_headers,
        json={
            "patient_id": patient_id,
            "action_type": "MEDICATION",
            "priority": "ROUTINE",
            "title": "Paracetamol",
            "notes": "nurse cannot create",
        },
    )
    assert blocked.status_code == 403

    allowed = client.post(
        "/actions",
        headers=doctor_headers,
        json={
            "patient_id": patient_id,
            "action_type": "MEDICATION",
            "priority": "ROUTINE",
            "title": "Paracetamol",
            "notes": "doctor can create",
        },
    )
    assert allowed.status_code == 201


def test_rbac_department_access(client, doctor_headers, pharmacist_headers, admin_headers):
    patient_id = _create_patient(client, doctor_headers)
    action = client.post(
        "/actions",
        headers=doctor_headers,
        json={
            "patient_id": patient_id,
            "action_type": "DIAGNOSTIC",
            "priority": "ROUTINE",
            "title": "CBC",
            "notes": "lab queue",
        },
    )
    assert action.status_code == 201

    blocked = client.get("/actions/department/Laboratory", headers=pharmacist_headers)
    assert blocked.status_code == 403

    allowed = client.get("/actions/department/Laboratory", headers=admin_headers)
    assert allowed.status_code == 200


def test_rbac_transition_permission(client, doctor_headers, lab_headers):
    patient_id = _create_patient(client, doctor_headers)
    action = client.post(
        "/actions",
        headers=doctor_headers,
        json={
            "patient_id": patient_id,
            "action_type": "DIAGNOSTIC",
            "priority": "ROUTINE",
            "title": "CBC",
            "notes": "lab queue",
        },
    )
    assert action.status_code == 201
    action_id = action.json()["id"]

    transition = client.patch(
        f"/actions/{action_id}/transition",
        headers=lab_headers,
        json={"new_state": "PROCESSING", "notes": "accepted"},
    )
    assert transition.status_code == 200
