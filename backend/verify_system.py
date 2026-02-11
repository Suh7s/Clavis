from __future__ import annotations

import os
from datetime import UTC, datetime, timedelta
from pathlib import Path
import sys
import traceback

from fastapi.testclient import TestClient
from sqlmodel import Session

ROOT = Path(__file__).resolve().parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

os.environ.setdefault("CLAVIS_ENABLE_DEMO_RESET", "1")

from database import engine  # noqa: E402
from main import app  # noqa: E402
from models import ClinicalAction  # noqa: E402


def _login(client: TestClient, email: str, password: str) -> str:
    response = client.post("/auth/login", json={"email": email, "password": password})
    if response.status_code != 200:
        raise RuntimeError(f"Login failed for {email}: {response.status_code} {response.text}")
    return response.json()["access_token"]


def _headers(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


def _assert_status(response, expected: int, label: str):
    if response.status_code != expected:
        raise RuntimeError(f"{label} failed: {response.status_code} {response.text}")


def run() -> int:
    results: list[tuple[str, bool, str]] = []
    client = TestClient(app)

    def check(name: str, fn):
        try:
            fn()
            results.append((name, True, "PASS"))
            print(f"[PASS] {name}")
        except Exception as exc:
            results.append((name, False, str(exc)))
            print(f"[FAIL] {name}: {exc}")
            traceback.print_exc()

    tokens: dict[str, str] = {}
    context: dict[str, int] = {}

    def smoke_checks():
        health = client.get("/health")
        _assert_status(health, 200, "health")
        body = health.json()
        if body.get("status") != "ok":
            raise RuntimeError(f"Unexpected health payload: {body}")

        index = client.get("/")
        _assert_status(index, 200, "index")

    def demo_reset():
        reset = client.get("/demo/reset")
        _assert_status(reset, 200, "demo reset")
        if reset.json().get("status") != "demo reset complete":
            raise RuntimeError(f"Unexpected reset payload: {reset.json()}")

    def auth_and_roles():
        tokens["doctor"] = _login(client, "doctor@clavis.local", "doctor123")
        tokens["nurse"] = _login(client, "nurse@clavis.local", "nurse123")
        tokens["pharmacist"] = _login(client, "pharmacy@clavis.local", "pharmacy123")
        tokens["lab"] = _login(client, "lab@clavis.local", "lab123")
        tokens["admin"] = _login(client, "admin@clavis.local", "admin123")

        denied = client.get("/analytics", headers=_headers(tokens["nurse"]))
        _assert_status(denied, 403, "nurse analytics access denied")
        allowed = client.get("/analytics", headers=_headers(tokens["doctor"]))
        _assert_status(allowed, 200, "doctor analytics access")

    def full_workflow():
        patient = client.post(
            "/patients",
            headers=_headers(tokens["doctor"]),
            json={"name": "Verify Patient", "age": 49, "gender": "Female", "ward": "Ward V"},
        )
        _assert_status(patient, 201, "create patient")
        context["patient_id"] = patient.json()["id"]

        diagnostic = client.post(
            "/actions",
            headers=_headers(tokens["doctor"]),
            json={
                "patient_id": context["patient_id"],
                "action_type": "DIAGNOSTIC",
                "priority": "URGENT",
                "title": "CBC",
                "notes": "verification flow",
            },
        )
        _assert_status(diagnostic, 201, "create diagnostic")
        context["diag_id"] = diagnostic.json()["id"]

        medication = client.post(
            "/actions",
            headers=_headers(tokens["doctor"]),
            json={
                "patient_id": context["patient_id"],
                "action_type": "MEDICATION",
                "priority": "ROUTINE",
                "title": "Paracetamol 500mg",
                "notes": "verification flow",
            },
        )
        _assert_status(medication, 201, "create medication")
        context["med_id"] = medication.json()["id"]

        diag_processing = client.patch(
            f"/actions/{context['diag_id']}/transition",
            headers=_headers(tokens["lab"]),
            json={"new_state": "PROCESSING", "notes": "lab in progress"},
        )
        _assert_status(diag_processing, 200, "diagnostic -> PROCESSING")

        diag_done = client.patch(
            f"/actions/{context['diag_id']}/transition",
            headers=_headers(tokens["lab"]),
            json={"new_state": "COMPLETED", "notes": "lab complete"},
        )
        _assert_status(diag_done, 200, "diagnostic -> COMPLETED")

        med_dispense = client.patch(
            f"/actions/{context['med_id']}/transition",
            headers=_headers(tokens["pharmacist"]),
            json={"new_state": "DISPENSED", "notes": "dispensed"},
        )
        _assert_status(med_dispense, 200, "medication -> DISPENSED")

        med_admin = client.patch(
            f"/actions/{context['med_id']}/transition",
            headers=_headers(tokens["nurse"]),
            json={"new_state": "ADMINISTERED", "notes": "administered"},
        )
        _assert_status(med_admin, 200, "medication -> ADMINISTERED")

        discharge = client.post(
            f"/patients/{context['patient_id']}/discharge",
            headers=_headers(tokens["doctor"]),
            json={"notes": "workflow complete"},
        )
        _assert_status(discharge, 200, "patient discharge")

    def sla_logic():
        fresh = client.post(
            "/patients",
            headers=_headers(tokens["doctor"]),
            json={"name": "SLA Verify", "age": 57, "gender": "Male", "ward": "Ward SLA"},
        )
        _assert_status(fresh, 201, "create SLA patient")
        sla_patient_id = fresh.json()["id"]

        action = client.post(
            "/actions",
            headers=_headers(tokens["doctor"]),
            json={
                "patient_id": sla_patient_id,
                "action_type": "VITALS_REQUEST",
                "priority": "URGENT",
                "title": "Vitals check",
                "notes": "SLA overdue check",
            },
        )
        _assert_status(action, 201, "create SLA action")
        action_id = action.json()["id"]

        with Session(engine) as session:
            row = session.get(ClinicalAction, action_id)
            if row is None:
                raise RuntimeError("SLA action missing from database")
            row.sla_deadline = datetime.now(UTC).replace(tzinfo=None) - timedelta(minutes=5)
            session.add(row)
            session.commit()

        escalations = client.get("/actions/escalations", headers=_headers(tokens["doctor"]))
        _assert_status(escalations, 200, "escalations endpoint")
        overdue_ids = {item["id"] for item in escalations.json()}
        if action_id not in overdue_ids:
            raise RuntimeError("SLA overdue action was not detected")

    def endpoint_smoke_matrix():
        patient_id = context["patient_id"]

        summary = client.get(f"/patients/{patient_id}/summary", headers=_headers(tokens["doctor"]))
        _assert_status(summary, 200, "patient summary")

        timeline = client.get(f"/patients/{patient_id}/timeline", headers=_headers(tokens["doctor"]))
        _assert_status(timeline, 200, "patient timeline")

        audit = client.get("/audit-log", headers=_headers(tokens["doctor"]))
        _assert_status(audit, 200, "audit log")

        analytics = client.get("/analytics", headers=_headers(tokens["doctor"]))
        _assert_status(analytics, 200, "analytics")

        csv_export = client.get(f"/export/patients/{patient_id}/csv", headers=_headers(tokens["doctor"]))
        _assert_status(csv_export, 200, "patient csv export")

        pdf_export = client.get(f"/export/patients/{patient_id}/pdf", headers=_headers(tokens["doctor"]))
        _assert_status(pdf_export, 200, "patient pdf export")
        if not pdf_export.content.startswith(b"%PDF-"):
            raise RuntimeError("PDF export did not return PDF bytes")

    check("Smoke checks", smoke_checks)
    check("Demo reset", demo_reset)
    check("Auth and role checks", auth_and_roles)
    check("Full workflow", full_workflow)
    check("SLA logic", sla_logic)
    check("Endpoint smoke matrix", endpoint_smoke_matrix)

    passed = sum(1 for _, ok, _ in results if ok)
    failed = len(results) - passed
    print("\n=== Verification Summary ===")
    print(f"Total checks: {len(results)}")
    print(f"Passed: {passed}")
    print(f"Failed: {failed}")

    for name, ok, detail in results:
        status = "PASS" if ok else "FAIL"
        print(f"- {status}: {name}" if ok else f"- {status}: {name} ({detail})")

    return 0 if failed == 0 else 1


if __name__ == "__main__":
    raise SystemExit(run())
