def test_create_and_list_notes(client, patient_id, nurse_headers):
    created = client.post(
        f"/patients/{patient_id}/notes",
        headers=nurse_headers,
        json={"note_type": "clinical", "content": "Patient is responding well."},
    )
    assert created.status_code == 201
    payload = created.json()
    assert payload["note_type"] == "clinical"

    listed = client.get(f"/patients/{patient_id}/notes", headers=nurse_headers)
    assert listed.status_code == 200
    notes = listed.json()
    assert len(notes) == 1
    assert notes[0]["author_name"]


def test_note_validation(client, patient_id, nurse_headers):
    invalid = client.post(
        f"/patients/{patient_id}/notes",
        headers=nurse_headers,
        json={"note_type": "clinical", "content": ""},
    )
    assert invalid.status_code == 422
