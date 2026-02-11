def test_login_success_and_me(client, seeded_users):
    response = client.post(
        "/auth/login",
        json={
            "email": seeded_users["doctor"]["email"],
            "password": seeded_users["doctor"]["password"],
        },
    )
    assert response.status_code == 200
    payload = response.json()
    assert payload["token_type"] == "bearer"
    assert payload["user"]["role"] == "doctor"

    me = client.get("/auth/me", headers={"Authorization": f"Bearer {payload['access_token']}"})
    assert me.status_code == 200
    assert me.json()["email"] == seeded_users["doctor"]["email"]


def test_login_invalid_password(client, seeded_users):
    response = client.post(
        "/auth/login",
        json={"email": seeded_users["doctor"]["email"], "password": "wrong-pass"},
    )
    assert response.status_code == 401


def test_auth_required_for_protected_endpoints(client, seeded_users):
    _ = seeded_users
    response = client.get("/patients")
    assert response.status_code == 401
