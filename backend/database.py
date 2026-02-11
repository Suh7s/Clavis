import os
from pathlib import Path

from sqlalchemy import inspect
from sqlmodel import SQLModel, Session, create_engine

DB_FILE = Path(os.getenv("CLAVIS_DB_FILE", str(Path(__file__).resolve().parent / "clavis.db")))
DATABASE_URL = f"sqlite:///{DB_FILE}"

engine = create_engine(DATABASE_URL, echo=False)


REQUIRED_COLUMNS = {
    "user": {
        "id",
        "name",
        "email",
        "password_hash",
        "role",
        "department",
        "is_active",
        "created_at",
    },
    "patient": {"id", "name", "age", "gender", "created_at"},
    "clinicalaction": {
        "id",
        "patient_id",
        "created_by",
        "assigned_to",
        "action_type",
        "custom_action_type_id",
        "title",
        "notes",
        "current_state",
        "priority",
        "department",
        "sla_deadline",
        "created_at",
    },
    "actionevent": {
        "id",
        "action_id",
        "actor_id",
        "actor_role",
        "previous_state",
        "new_state",
        "notes",
        "timestamp",
    },
    "customactiontype": {
        "id",
        "name",
        "department",
        "states_json",
        "terminal_state",
        "sla_routine_minutes",
        "sla_urgent_minutes",
        "sla_critical_minutes",
        "created_at",
    },
}


def _schema_needs_rebuild() -> bool:
    inspector = inspect(engine)
    existing_tables = set(inspector.get_table_names())

    for table_name, required_cols in REQUIRED_COLUMNS.items():
        if table_name not in existing_tables:
            continue
        existing_cols = {col["name"] for col in inspector.get_columns(table_name)}
        if not required_cols.issubset(existing_cols):
            return True

    return False


def create_db():
    if _schema_needs_rebuild():
        print("[DB] Schema mismatch detected. Rebuilding local SQLite schema.")
        SQLModel.metadata.drop_all(engine)
    SQLModel.metadata.create_all(engine)


def get_session():
    with Session(engine) as session:
        yield session
