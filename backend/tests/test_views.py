def test_patient_view_route_embeds_requested_patient_id(client):
    patient_ids = [1, 17, 999]

    for patient_id in patient_ids:
        response = client.get(f"/patients/{patient_id}/view")
        assert response.status_code == 200
        assert f"const PID = Number({patient_id});" in response.text
        assert 'id="createActionForm"' in response.text
        assert 'id="transitionForm"' in response.text
        assert 'id="summaryNarrative"' in response.text


def test_patient_view_route_does_not_render_static_placeholder_name(client):
    response = client.get("/patients/1/view")
    assert response.status_code == 200
    assert "Meera Gupta" not in response.text
    assert "Patient stabilized and assigned to Cardiology workflow." not in response.text
    assert 'id="btnCustomType"' not in response.text


def test_base_layout_includes_theme_toggle_and_shortcut_hooks(client):
    response = client.get("/dashboard/view")
    assert response.status_code == 200
    assert 'id="themeToggleButton"' in response.text
    assert "function toggleDarkMode()" in response.text
    assert "Ctrl/Cmd+K search" in response.text
