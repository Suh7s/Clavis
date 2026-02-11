import os

from sqlmodel import Session, select

from database import engine, create_db
from models import (
    ActionEvent,
    ActionType,
    ClinicalAction,
    Patient,
    Priority,
    User,
    UserRole,
)
from services.auth import hash_password
from state_machine import INITIAL_STATES
from services.sla import compute_sla_deadline
from services.workflow import default_department_for_action

DEMO_ACTIONS = [
    {"action_type": ActionType.DIAGNOSTIC, "priority": Priority.URGENT, "title": "Chest X-Ray", "notes": "Suspected bilateral infiltrates — rule out pneumonia"},
    {"action_type": ActionType.MEDICATION, "priority": Priority.ROUTINE, "title": "Amoxicillin 500mg", "notes": "Oral, 3x daily for 7 days"},
    {"action_type": ActionType.CARE_INSTRUCTION, "priority": Priority.ROUTINE, "title": "IV Fluids — Normal Saline", "notes": "1L over 4 hours, monitor output"},
]

DEMO_USERS = [
    {
        "name": "Dr. Priya",
        "email": "doctor@clavis.local",
        "password": "doctor123",
        "role": UserRole.DOCTOR,
        "department": "Medicine",
    },
    {
        "name": "Nurse Riya",
        "email": "nurse@clavis.local",
        "password": "nurse123",
        "role": UserRole.NURSE,
        "department": "Nursing",
    },
    {
        "name": "Pharmacist Arjun",
        "email": "pharmacy@clavis.local",
        "password": "pharmacy123",
        "role": UserRole.PHARMACIST,
        "department": "Pharmacy",
    },
    {
        "name": "Lab Tech Meera",
        "email": "lab@clavis.local",
        "password": "lab123",
        "role": UserRole.LAB_TECH,
        "department": "Laboratory",
    },
    {
        "name": "Radiology Tech Akash",
        "email": "radiology@clavis.local",
        "password": "radiology123",
        "role": UserRole.RADIOLOGIST,
        "department": "Radiology",
    },
    {
        "name": "Admin Sahana",
        "email": "admin@clavis.local",
        "password": "admin123",
        "role": UserRole.ADMIN,
        "department": "Operations",
    },
]


def run_seed(seed_actions: bool = False, seed_patient: bool = False):
    create_db()

    with Session(engine) as session:
        existing_user = session.exec(select(User)).first()
        existing_patient = session.exec(select(Patient)).first()
        if existing_user or existing_patient:
            print("Database already seeded. Skipping.")
            return

        users_by_email: dict[str, User] = {}
        for spec in DEMO_USERS:
            user = User(
                name=spec["name"],
                email=spec["email"],
                password_hash=hash_password(spec["password"]),
                role=spec["role"],
                department=spec["department"],
            )
            session.add(user)
            session.commit()
            session.refresh(user)
            users_by_email[user.email] = user
            print(f"Created user: {user.email} ({user.role.value})")

        doctor = users_by_email["doctor@clavis.local"]

        patient: Patient | None = None
        if seed_patient or seed_actions:
            patient = Patient(name="Demo Patient", age=58, gender="Male")
            session.add(patient)
            session.commit()
            session.refresh(patient)
            print(f"Created patient: {patient.name} (id={patient.id})")

        if seed_actions and patient is not None:
            for spec in DEMO_ACTIONS:
                atype = spec["action_type"]
                priority = spec["priority"]
                initial_state = INITIAL_STATES[atype]

                action = ClinicalAction(
                    patient_id=patient.id,
                    created_by=doctor.id,
                    action_type=atype,
                    current_state=initial_state,
                    priority=priority,
                    department=default_department_for_action(atype, title=spec["title"]),
                    sla_deadline=compute_sla_deadline(priority),
                    title=spec["title"],
                    notes=spec["notes"],
                )
                session.add(action)
                session.commit()
                session.refresh(action)

                event = ActionEvent(
                    action_id=action.id,
                    actor_id=doctor.id,
                    actor_role=doctor.role,
                    previous_state="",
                    new_state=initial_state,
                )
                session.add(event)
                session.commit()

                print(f"  Created action: {spec['title']} [{initial_state}] priority={priority.value}")
        else:
            print("No default patient/actions seeded (clean slate).")

        print("Demo credentials:")
        for spec in DEMO_USERS:
            print(f"  {spec['email']} / {spec['password']}")
        print("Seed complete.")


if __name__ == "__main__":
    run_seed(
        seed_actions=os.getenv("CLAVIS_SEED_ACTIONS", "0") == "1",
        seed_patient=os.getenv("CLAVIS_SEED_PATIENT", "0") == "1",
    )
