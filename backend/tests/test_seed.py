import os
import sqlite3
import subprocess
import sys
from pathlib import Path


BACKEND_DIR = Path(__file__).resolve().parents[1]
SEED_SCRIPT = BACKEND_DIR / "seed.py"

EXPECTED_PATIENTS = {
    "Mr. Rao",
    "Ms. Ananya Iyer",
    "Aarav Mehta",
    "Nisha Verma",
    "Rahul Kapoor",
    "Kavya Nair",
    "Sandeep Kulkarni",
    "Pooja Menon",
    "Vivek Sharma",
    "Neha Joshi",
}

EXPECTED_USERS = {
    "doctor@clavis.local",
    "nurse@clavis.local",
    "pharmacy@clavis.local",
    "lab@clavis.local",
    "radiology@clavis.local",
    "admin@clavis.local",
}


def _run_seed(db_file: Path):
    env = os.environ.copy()
    env["CLAVIS_DB_FILE"] = str(db_file)
    env["CLAVIS_SEED_ACTIONS"] = "0"
    env["CLAVIS_SEED_PATIENT"] = "1"
    run = subprocess.run(
        [sys.executable, str(SEED_SCRIPT)],
        cwd=str(BACKEND_DIR),
        env=env,
        capture_output=True,
        text=True,
        check=False,
    )
    assert run.returncode == 0, f"seed.py failed\nSTDOUT:\n{run.stdout}\nSTDERR:\n{run.stderr}"


def _read_rows(db_file: Path):
    with sqlite3.connect(db_file) as conn:
        patients = [row[0] for row in conn.execute("SELECT name FROM patient").fetchall()]
        users = [row[0] for row in conn.execute('SELECT email FROM "user"').fetchall()]
    return patients, users


def test_seed_is_idempotent_for_demo_users_and_patients(tmp_path):
    db_file = tmp_path / "seed-idempotent.db"

    _run_seed(db_file)
    _run_seed(db_file)

    patients, users = _read_rows(db_file)

    assert len(patients) == len(EXPECTED_PATIENTS)
    assert len(set(patients)) == len(EXPECTED_PATIENTS)
    assert set(patients) == EXPECTED_PATIENTS

    assert len(users) == len(EXPECTED_USERS)
    assert len(set(users)) == len(EXPECTED_USERS)
    assert set(users) == EXPECTED_USERS
