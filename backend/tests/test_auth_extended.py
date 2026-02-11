import pytest


@pytest.mark.anyio
async def test_register_login_and_me(async_client, seeded_users):
    admin_login = await async_client.post(
        "/auth/login",
        json={
            "email": seeded_users["admin"]["email"],
            "password": seeded_users["admin"]["password"],
        },
    )
    assert admin_login.status_code == 200
    admin_token = admin_login.json()["access_token"]
    admin_headers = {"Authorization": f"Bearer {admin_token}"}

    register = await async_client.post(
        "/auth/register",
        headers=admin_headers,
        json={
            "name": "New Nurse",
            "email": "new-nurse@clavis.local",
            "password": "new-nurse-123",
            "role": "nurse",
            "department": "Nursing",
        },
    )
    assert register.status_code == 201, register.text
    payload = register.json()
    assert payload["email"] == "new-nurse@clavis.local"
    assert payload["role"] == "nurse"

    login = await async_client.post(
        "/auth/login",
        json={"email": "new-nurse@clavis.local", "password": "new-nurse-123"},
    )
    assert login.status_code == 200, login.text
    token = login.json()["access_token"]

    me = await async_client.get("/auth/me", headers={"Authorization": f"Bearer {token}"})
    assert me.status_code == 200
    assert me.json()["email"] == "new-nurse@clavis.local"


@pytest.mark.anyio
async def test_register_requires_admin_and_duplicate_rejected(async_client, seeded_users):
    nurse_login = await async_client.post(
        "/auth/login",
        json={
            "email": seeded_users["nurse"]["email"],
            "password": seeded_users["nurse"]["password"],
        },
    )
    assert nurse_login.status_code == 200
    nurse_headers = {"Authorization": f"Bearer {nurse_login.json()['access_token']}"}

    forbidden = await async_client.post(
        "/auth/register",
        headers=nurse_headers,
        json={
            "name": "Unauthorized Register",
            "email": "forbidden@clavis.local",
            "password": "password-123",
            "role": "nurse",
            "department": "Nursing",
        },
    )
    assert forbidden.status_code == 403

    admin_login = await async_client.post(
        "/auth/login",
        json={
            "email": seeded_users["admin"]["email"],
            "password": seeded_users["admin"]["password"],
        },
    )
    assert admin_login.status_code == 200
    admin_headers = {"Authorization": f"Bearer {admin_login.json()['access_token']}"}

    first = await async_client.post(
        "/auth/register",
        headers=admin_headers,
        json={
            "name": "User One",
            "email": "user-one@clavis.local",
            "password": "password-123",
            "role": "doctor",
            "department": "Medicine",
        },
    )
    assert first.status_code == 201, first.text

    duplicate = await async_client.post(
        "/auth/register",
        headers=admin_headers,
        json={
            "name": "User One Duplicate",
            "email": "user-one@clavis.local",
            "password": "password-123",
            "role": "doctor",
            "department": "Medicine",
        },
    )
    assert duplicate.status_code == 409


def test_invalid_token_rejected(client, seeded_users):
    _ = seeded_users
    bad = client.get("/auth/me", headers={"Authorization": "Bearer invalid.token.value"})
    assert bad.status_code == 401


def test_role_restriction_enforced(client, nurse_headers, admin_headers):
    denied = client.get("/analytics", headers=nurse_headers)
    assert denied.status_code == 403

    allowed = client.get("/analytics", headers=admin_headers)
    assert allowed.status_code == 200
