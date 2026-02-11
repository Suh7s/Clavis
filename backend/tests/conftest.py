from __future__ import annotations

import pytest
import httpx
from fastapi.testclient import TestClient
from sqlalchemy.pool import StaticPool
from sqlmodel import SQLModel, Session, create_engine

from database import get_session
from main import app
from models import User, UserRole
from services.auth import hash_password

TEST_ENGINE = create_engine(
    "sqlite://",
    connect_args={"check_same_thread": False},
    poolclass=StaticPool,
)


def _override_get_session():
    with Session(TEST_ENGINE) as session:
        yield session


@pytest.fixture(autouse=True)
def reset_db():
    SQLModel.metadata.drop_all(TEST_ENGINE)
    SQLModel.metadata.create_all(TEST_ENGINE)


@pytest.fixture
def anyio_backend():
    return "asyncio"


@pytest.fixture
def client():
    app.dependency_overrides[get_session] = _override_get_session
    with TestClient(app) as test_client:
        yield test_client
    app.dependency_overrides.clear()


@pytest.fixture
async def async_client():
    app.dependency_overrides[get_session] = _override_get_session
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://testserver") as test_client:
        yield test_client
    app.dependency_overrides.clear()


@pytest.fixture
def seeded_users():
    users = {
        "doctor": {
            "name": "Doctor",
            "email": "doctor@clavis.local",
            "password": "doctor123",
            "role": UserRole.DOCTOR,
            "department": "Medicine",
        },
        "nurse": {
            "name": "Nurse",
            "email": "nurse@clavis.local",
            "password": "nurse123",
            "role": UserRole.NURSE,
            "department": "Nursing",
        },
        "pharmacist": {
            "name": "Pharmacist",
            "email": "pharmacy@clavis.local",
            "password": "pharmacy123",
            "role": UserRole.PHARMACIST,
            "department": "Pharmacy",
        },
        "lab_tech": {
            "name": "Lab Tech",
            "email": "lab@clavis.local",
            "password": "lab123",
            "role": UserRole.LAB_TECH,
            "department": "Laboratory",
        },
        "radiologist": {
            "name": "Radiologist",
            "email": "radiology@clavis.local",
            "password": "radiology123",
            "role": UserRole.RADIOLOGIST,
            "department": "Radiology",
        },
        "admin": {
            "name": "Admin",
            "email": "admin@clavis.local",
            "password": "admin123",
            "role": UserRole.ADMIN,
            "department": "Operations",
        },
    }

    with Session(TEST_ENGINE) as session:
        for spec in users.values():
            user = User(
                name=spec["name"],
                email=spec["email"],
                password_hash=hash_password(spec["password"]),
                role=spec["role"],
                department=spec["department"],
            )
            session.add(user)
        session.commit()

    return users


def _login(client: TestClient, email: str, password: str) -> dict[str, str]:
    response = client.post("/auth/login", json={"email": email, "password": password})
    assert response.status_code == 200, response.text
    token = response.json()["access_token"]
    return {"Authorization": f"Bearer {token}"}


@pytest.fixture
def doctor_headers(client: TestClient, seeded_users):
    return _login(client, seeded_users["doctor"]["email"], seeded_users["doctor"]["password"])


@pytest.fixture
def nurse_headers(client: TestClient, seeded_users):
    return _login(client, seeded_users["nurse"]["email"], seeded_users["nurse"]["password"])


@pytest.fixture
def pharmacist_headers(client: TestClient, seeded_users):
    return _login(client, seeded_users["pharmacist"]["email"], seeded_users["pharmacist"]["password"])


@pytest.fixture
def lab_headers(client: TestClient, seeded_users):
    return _login(client, seeded_users["lab_tech"]["email"], seeded_users["lab_tech"]["password"])


@pytest.fixture
def radiology_headers(client: TestClient, seeded_users):
    return _login(client, seeded_users["radiologist"]["email"], seeded_users["radiologist"]["password"])


@pytest.fixture
def admin_headers(client: TestClient, seeded_users):
    return _login(client, seeded_users["admin"]["email"], seeded_users["admin"]["password"])


@pytest.fixture
def patient_id(client: TestClient, doctor_headers):
    response = client.post(
        "/patients",
        headers=doctor_headers,
        json={"name": "Patient One", "age": 44, "gender": "Female", "ward": "Ward A"},
    )
    assert response.status_code == 201, response.text
    return response.json()["id"]
