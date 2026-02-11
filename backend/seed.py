from sqlmodel import Session, select

from database import engine, create_db
from models import (
    Patient, ClinicalAction, ActionEvent,
    ActionType, Priority,
)
from state_machine import INITIAL_STATES
from services.sla import compute_sla_deadline

DEPARTMENT_MAP = {
    ActionType.DIAGNOSTIC: "Laboratory",
    ActionType.MEDICATION: "Pharmacy",
    ActionType.REFERRAL: "Referral",
    ActionType.CARE_INSTRUCTION: "Nursing",
}

DEMO_ACTIONS = [
    {"action_type": ActionType.DIAGNOSTIC, "priority": Priority.URGENT},
    {"action_type": ActionType.MEDICATION, "priority": Priority.ROUTINE},
    {"action_type": ActionType.CARE_INSTRUCTION, "priority": Priority.ROUTINE},
]


def run_seed():
    create_db()

    with Session(engine) as session:
        existing = session.exec(select(Patient)).first()
        if existing:
            print("Database already seeded. Skipping.")
            return

        patient = Patient(name="Ravi Kumar", age=58, gender="Male")
        session.add(patient)
        session.commit()
        session.refresh(patient)
        print(f"Created patient: {patient.name} (id={patient.id})")

        for spec in DEMO_ACTIONS:
            atype = spec["action_type"]
            priority = spec["priority"]
            initial_state = INITIAL_STATES[atype]

            action = ClinicalAction(
                patient_id=patient.id,
                action_type=atype,
                current_state=initial_state,
                priority=priority,
                department=DEPARTMENT_MAP[atype],
                sla_deadline=compute_sla_deadline(priority),
            )
            session.add(action)
            session.commit()
            session.refresh(action)

            event = ActionEvent(
                action_id=action.id,
                previous_state="",
                new_state=initial_state,
            )
            session.add(event)
            session.commit()

            print(f"  Created action: {atype.value} [{initial_state}] priority={priority.value}")

        print("Seed complete.")


if __name__ == "__main__":
    run_seed()
