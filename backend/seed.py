import os
from datetime import datetime, timedelta
from pathlib import Path

from sqlmodel import Session, select

from database import create_db, engine
from models import (
    ActionEvent,
    ActionType,
    AdmissionStatus,
    Attachment,
    ClinicalAction,
    CustomActionType,
    Patient,
    PatientNote,
    PatientTransfer,
    Priority,
    User,
    UserRole,
)
from services.auth import hash_password

UPLOAD_DIR = Path(__file__).resolve().parent / "uploads"

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

DEMO_PATIENT_SPECS = [
    {
        "name": "Aarav Mehta",
        "age": 34,
        "gender": "Male",
        "blood_group": "B+",
        "ward": "General Ward 1",
    },
    {
        "name": "Nisha Verma",
        "age": 41,
        "gender": "Female",
        "blood_group": "A-",
        "ward": "Cardiology Ward 2",
    },
    {
        "name": "Rahul Kapoor",
        "age": 52,
        "gender": "Male",
        "blood_group": "O+",
        "ward": "Medicine Ward 3",
    },
    {
        "name": "Kavya Nair",
        "age": 29,
        "gender": "Female",
        "blood_group": "AB+",
        "ward": "General Ward 4",
    },
    {
        "name": "Sandeep Kulkarni",
        "age": 63,
        "gender": "Male",
        "blood_group": "B-",
        "ward": "Pulmonology Ward 1",
    },
    {
        "name": "Pooja Menon",
        "age": 47,
        "gender": "Female",
        "blood_group": "A+",
        "ward": "Endocrinology Ward 2",
    },
    {
        "name": "Vivek Sharma",
        "age": 56,
        "gender": "Male",
        "blood_group": "O-",
        "ward": "Neurology Ward 1",
    },
    {
        "name": "Neha Joshi",
        "age": 38,
        "gender": "Female",
        "blood_group": "AB-",
        "ward": "General Ward 5",
    },
]

DEMO_PATIENT_PROFILES = {
    "Aarav Mehta": {
        "allergies": "Penicillin rash (mild).",
        "past_medical_history": "Appendicitis (post laparoscopic appendectomy), episodic gastritis.",
        "chronic_conditions": "None documented.",
        "current_medications": "Pantoprazole 40 mg OD, post-op analgesics as needed.",
        "surgical_history": "Laparoscopic appendectomy (current admission).",
        "family_history": "Father with hypertension.",
        "social_history": "Non-smoker, occasional alcohol, software engineer.",
        "immunization_history": "Routine adult vaccines up to date as per patient.",
    },
    "Nisha Verma": {
        "allergies": "No known drug allergies.",
        "past_medical_history": "Intermittent chest pain, dyslipidemia.",
        "chronic_conditions": "Hypertension, dyslipidemia.",
        "current_medications": "Amlodipine 5 mg OD, Rosuvastatin 10 mg HS.",
        "surgical_history": "No prior major surgery.",
        "family_history": "Mother with ischemic heart disease.",
        "social_history": "Sedentary lifestyle, no tobacco, occasional caffeine excess.",
        "immunization_history": "Influenza vaccine last season.",
    },
    "Rahul Kapoor": {
        "allergies": "Sulfa drug intolerance (GI upset).",
        "past_medical_history": "Recent febrile illness with worsening weakness.",
        "chronic_conditions": "Type 2 diabetes mellitus.",
        "current_medications": "Metformin 500 mg BD (held during acute illness).",
        "surgical_history": "No prior surgeries.",
        "family_history": "Sibling with type 2 diabetes.",
        "social_history": "Former smoker (quit 6 years ago).",
        "immunization_history": "Unknown pneumococcal vaccination status.",
    },
    "Kavya Nair": {
        "allergies": "Dust mite allergy; no known medication allergy.",
        "past_medical_history": "Recurrent wheeze episodes since adolescence.",
        "chronic_conditions": "Mild persistent asthma.",
        "current_medications": "Budesonide-formoterol inhaler, rescue salbutamol.",
        "surgical_history": "No surgical history.",
        "family_history": "Brother with atopy.",
        "social_history": "Non-smoker, yoga instructor, no alcohol use.",
        "immunization_history": "Annual influenza vaccination reported.",
    },
    "Sandeep Kulkarni": {
        "allergies": "No known allergies.",
        "past_medical_history": "Multiple prior admissions for COPD exacerbation.",
        "chronic_conditions": "COPD, hypertension.",
        "current_medications": "Tiotropium inhaler, home nebulization, Telmisartan 40 mg OD.",
        "surgical_history": "No major surgery.",
        "family_history": "Father had chronic lung disease.",
        "social_history": "Ex-smoker with 30 pack-year history.",
        "immunization_history": "Pneumococcal vaccine received; influenza due this season.",
    },
    "Pooja Menon": {
        "allergies": "No known drug allergies.",
        "past_medical_history": "Poor glycemic control with prior ER visits for hyperglycemia.",
        "chronic_conditions": "Type 2 diabetes mellitus, obesity.",
        "current_medications": "Glimepiride 2 mg OD, Metformin 1 g BD (home regimen).",
        "surgical_history": "Cesarean section (2012).",
        "family_history": "Both parents have diabetes.",
        "social_history": "Sedentary office work; vegetarian diet.",
        "immunization_history": "Tetanus updated in last 5 years.",
    },
    "Vivek Sharma": {
        "allergies": "No known allergies.",
        "past_medical_history": "Recent ischemic stroke with mild residual weakness.",
        "chronic_conditions": "Hypertension, carotid atherosclerosis.",
        "current_medications": "Aspirin, Atorvastatin, Losartan.",
        "surgical_history": "No major surgical history.",
        "family_history": "Father had stroke at age 68.",
        "social_history": "Former smoker, currently in structured rehab.",
        "immunization_history": "Influenza and COVID boosters received.",
    },
    "Neha Joshi": {
        "allergies": "Nitrofurantoin causes nausea (non-anaphylactic).",
        "past_medical_history": "Recurrent urinary tract infections.",
        "chronic_conditions": "Hypothyroidism.",
        "current_medications": "Levothyroxine 75 mcg OD.",
        "surgical_history": "No surgical history.",
        "family_history": "Mother with hypothyroidism.",
        "social_history": "Non-smoker, adequate oral hydration encouraged.",
        "immunization_history": "Routine adult schedule reported complete.",
    },
    "Mr. Rao": {
        "allergies": "No known drug allergies.",
        "past_medical_history": "Acute chest pain episode with high cardiac risk features.",
        "chronic_conditions": "Hypertension, prediabetes.",
        "current_medications": "Amlodipine 5 mg OD (home), acute antiplatelet protocol ongoing.",
        "surgical_history": "No previous cardiac procedures reported.",
        "family_history": "Brother with early coronary artery disease.",
        "social_history": "Former smoker; high-stress occupation.",
        "immunization_history": "COVID primary series completed; influenza unknown.",
    },
    "Ms. Ananya Iyer": {
        "allergies": "Mild iodine contrast sensitivity (premedication protocol used).",
        "past_medical_history": "Acute neurologic symptoms requiring MRI pathway.",
        "chronic_conditions": "Migraine disorder.",
        "current_medications": "Propranolol low-dose prophylaxis (home).",
        "surgical_history": "No major surgeries reported.",
        "family_history": "Mother with migraine history.",
        "social_history": "Non-smoker, no alcohol use.",
        "immunization_history": "Routine immunization records available.",
    },
}

STORY_PATIENT_NAMES = ["Mr. Rao", "Ms. Ananya Iyer"]
MRI_WORKFLOW_NAME = "MRI_TRACKING_WORKFLOW"
EXPECTED_DEMO_PATIENT_COUNT = 10


def _normalize_name(value: str) -> str:
    return value.strip().casefold()


def _validate_demo_seed_config():
    if len(DEMO_USERS) == 0:
        raise RuntimeError("DEMO_USERS cannot be empty.")

    emails = [spec["email"].strip().casefold() for spec in DEMO_USERS]
    if len(emails) != len(set(emails)):
        raise RuntimeError("DEMO_USERS contains duplicate emails.")

    for spec in DEMO_PATIENT_SPECS:
        required_fields = {"name", "age", "gender", "blood_group", "ward"}
        missing = required_fields.difference(spec.keys())
        if missing:
            raise RuntimeError(
                f"Demo patient spec for {spec.get('name', '<unknown>')} is missing fields: {sorted(missing)}"
            )
        if not str(spec["name"]).strip():
            raise RuntimeError("Demo patient name cannot be empty.")
        age = int(spec["age"])
        if age < 0 or age > 130:
            raise RuntimeError(f"Demo patient age out of range for {spec['name']}: {age}")

    configured_names = STORY_PATIENT_NAMES + [spec["name"] for spec in DEMO_PATIENT_SPECS]
    normalized_names = [_normalize_name(name) for name in configured_names]
    if len(normalized_names) != len(set(normalized_names)):
        raise RuntimeError("Demo patient names must be unique.")

    if len(configured_names) != EXPECTED_DEMO_PATIENT_COUNT:
        raise RuntimeError(
            "Demo seed must define exactly "
            f"{EXPECTED_DEMO_PATIENT_COUNT} patients; found {len(configured_names)}."
        )


def _expected_demo_patient_name_map() -> dict[str, str]:
    names = STORY_PATIENT_NAMES + [spec["name"] for spec in DEMO_PATIENT_SPECS]
    return {_normalize_name(name): name for name in names}


def _remove_unused_custom_type_by_name(session: Session, custom_type_name: str) -> int:
    removed = 0
    custom_types = session.exec(
        select(CustomActionType).where(CustomActionType.name == custom_type_name)
    ).all()
    for custom_type in custom_types:
        has_linked_action = session.exec(
            select(ClinicalAction.id).where(
                ClinicalAction.custom_action_type_id == custom_type.id
            )
        ).first()
        if has_linked_action is not None:
            continue
        session.delete(custom_type)
        removed += 1
    if removed:
        session.flush()
    return removed


def _ensure_demo_users(session: Session) -> dict[str, User]:
    users_by_email = {
        user.email.strip().casefold(): user
        for user in session.exec(select(User)).all()
    }
    ensured: dict[str, User] = {}

    for spec in DEMO_USERS:
        email_key = spec["email"].strip().casefold()
        password_hash = hash_password(spec["password"])
        existing = users_by_email.get(email_key)

        if existing is None:
            existing = User(
                name=spec["name"],
                email=spec["email"],
                password_hash=password_hash,
                role=spec["role"],
                department=spec["department"],
                is_active=True,
            )
            session.add(existing)
            session.flush()
            print(f"Created user: {existing.email} ({existing.role.value})")
        else:
            changed = (
                existing.name != spec["name"]
                or existing.password_hash != password_hash
                or existing.role != spec["role"]
                or existing.department != spec["department"]
                or existing.is_active is not True
            )
            if changed:
                existing.name = spec["name"]
                existing.password_hash = password_hash
                existing.role = spec["role"]
                existing.department = spec["department"]
                existing.is_active = True
                session.flush()
                print(f"Updated user: {existing.email} ({existing.role.value})")

        ensured[spec["email"]] = existing

    return ensured


def _replace_demo_patients(
    session: Session,
    users_by_email: dict[str, User],
    *,
    include_actions: bool,
):
    removed_patients = 0
    for display_name in _expected_demo_patient_name_map().values():
        removed_patients += _remove_existing_patient_by_name(session, display_name)

    removed_custom_types = _remove_unused_custom_type_by_name(session, MRI_WORKFLOW_NAME)
    if removed_patients or removed_custom_types:
        print(
            "Removed stale demo data "
            f"(patients={removed_patients}, custom_types={removed_custom_types})."
        )

    _seed_story_patients(session, users_by_email, include_actions=include_actions)

    expected_name_map = _expected_demo_patient_name_map()
    observed_counts = {key: 0 for key in expected_name_map}
    for name in session.exec(select(Patient.name)).all():
        normalized = _normalize_name(name)
        if normalized in observed_counts:
            observed_counts[normalized] += 1

    missing = [
        expected_name_map[key]
        for key, count in observed_counts.items()
        if count == 0
    ]
    duplicates = [
        f"{expected_name_map[key]} ({count})"
        for key, count in observed_counts.items()
        if count > 1
    ]
    if missing or duplicates:
        raise RuntimeError(
            "Demo patient seed validation failed. "
            f"Missing={missing or 'none'}, duplicates={duplicates or 'none'}"
        )

def _create_action(
    session: Session,
    *,
    patient_id: int,
    created_by: User,
    priority: Priority,
    title: str,
    notes: str,
    current_state: str,
    department: str,
    created_at: datetime,
    updated_at: datetime,
    sla_deadline: datetime,
    action_type: ActionType | None = None,
    custom_type: CustomActionType | None = None,
) -> ClinicalAction:
    action = ClinicalAction(
        patient_id=patient_id,
        created_by=created_by.id,
        action_type=action_type,
        custom_action_type_id=custom_type.id if custom_type else None,
        title=title,
        notes=notes,
        current_state=current_state,
        priority=priority,
        department=department,
        sla_deadline=sla_deadline,
        created_at=created_at,
        updated_at=updated_at,
    )
    session.add(action)
    session.flush()
    return action


def _add_event(
    session: Session,
    *,
    action: ClinicalAction,
    actor: User,
    previous_state: str,
    new_state: str,
    notes: str,
    timestamp: datetime,
):
    session.add(
        ActionEvent(
            action_id=action.id,
            actor_id=actor.id,
            actor_role=actor.role,
            previous_state=previous_state,
            new_state=new_state,
            notes=notes,
            timestamp=timestamp,
        )
    )


def _add_note(
    session: Session,
    *,
    patient: Patient,
    author: User,
    note_type: str,
    content: str,
    created_at: datetime,
):
    session.add(
        PatientNote(
            patient_id=patient.id,
            author_id=author.id,
            note_type=note_type,
            content=content,
            created_at=created_at,
        )
    )


def _add_attachment(
    session: Session,
    *,
    patient: Patient,
    action: ClinicalAction | None,
    created_by: User,
    filename: str,
    stored_name: str,
    content: str,
    created_at: datetime,
):
    UPLOAD_DIR.mkdir(parents=True, exist_ok=True)
    payload = content.encode("utf-8")
    (UPLOAD_DIR / stored_name).write_bytes(payload)

    session.add(
        Attachment(
            patient_id=patient.id,
            action_id=action.id if action else None,
            filename=filename,
            file_type="text/plain",
            file_size=len(payload),
            stored_path=stored_name,
            created_by=created_by.id,
            created_at=created_at,
        )
    )


def _remove_patient_with_dependencies(session: Session, patient: Patient):
    action_ids = session.exec(
        select(ClinicalAction.id).where(ClinicalAction.patient_id == patient.id)
    ).all()

    attachments = session.exec(
        select(Attachment).where(Attachment.patient_id == patient.id)
    ).all()
    for attachment in attachments:
        stored_name = (attachment.stored_path or "").strip()
        if stored_name:
            (UPLOAD_DIR / stored_name).unlink(missing_ok=True)
        session.delete(attachment)

    if action_ids:
        events = session.exec(
            select(ActionEvent).where(ActionEvent.action_id.in_(action_ids))  # type: ignore[union-attr]
        ).all()
        for event in events:
            session.delete(event)

    actions = session.exec(
        select(ClinicalAction).where(ClinicalAction.patient_id == patient.id)
    ).all()
    for action in actions:
        session.delete(action)

    notes = session.exec(
        select(PatientNote).where(PatientNote.patient_id == patient.id)
    ).all()
    for note in notes:
        session.delete(note)

    transfers = session.exec(
        select(PatientTransfer).where(PatientTransfer.patient_id == patient.id)
    ).all()
    for transfer in transfers:
        session.delete(transfer)

    session.delete(patient)
    session.flush()


def _remove_existing_patient_by_name(session: Session, patient_name: str) -> int:
    target = patient_name.strip().casefold()
    removed = 0

    patients = session.exec(select(Patient)).all()
    for patient in patients:
        if patient.name.strip().casefold() != target:
            continue
        _remove_patient_with_dependencies(session, patient)
        removed += 1

    return removed


def _seed_mr_rao_story(
    session: Session,
    users_by_email: dict[str, User],
    *,
    include_actions: bool,
    now: datetime,
) -> Patient:
    doctor = users_by_email["doctor@clavis.local"]
    nurse = users_by_email["nurse@clavis.local"]
    pharmacist = users_by_email["pharmacy@clavis.local"]
    lab = users_by_email["lab@clavis.local"]

    rao_base = now - timedelta(minutes=44)

    mr_rao = Patient(
        name="Mr. Rao",
        age=58,
        gender="Male",
        blood_group="O+",
        allergies=DEMO_PATIENT_PROFILES["Mr. Rao"]["allergies"],
        past_medical_history=DEMO_PATIENT_PROFILES["Mr. Rao"]["past_medical_history"],
        chronic_conditions=DEMO_PATIENT_PROFILES["Mr. Rao"]["chronic_conditions"],
        current_medications=DEMO_PATIENT_PROFILES["Mr. Rao"]["current_medications"],
        surgical_history=DEMO_PATIENT_PROFILES["Mr. Rao"]["surgical_history"],
        family_history=DEMO_PATIENT_PROFILES["Mr. Rao"]["family_history"],
        social_history=DEMO_PATIENT_PROFILES["Mr. Rao"]["social_history"],
        immunization_history=DEMO_PATIENT_PROFILES["Mr. Rao"]["immunization_history"],
        ward="Emergency - Bay 2",
        primary_doctor_id=doctor.id,
        admission_date=now,
        created_at=now,
    )
    session.add(mr_rao)
    session.flush()
    print(f"Created patient: {mr_rao.name} (id={mr_rao.id})")

    if not include_actions:
        return mr_rao

    blood_panel = _create_action(
        session,
        patient_id=mr_rao.id,
        created_by=doctor,
        action_type=ActionType.DIAGNOSTIC,
        priority=Priority.CRITICAL,
        title="Cardiac Enzyme Panel (Troponin + CK-MB)",
        notes="STAT blood work for chest pain protocol.",
        current_state="COMPLETED",
        department="Laboratory",
        created_at=rao_base + timedelta(minutes=1),
        updated_at=rao_base + timedelta(minutes=24),
        sla_deadline=now + timedelta(minutes=12),
    )
    _add_event(
        session,
        action=blood_panel,
        actor=doctor,
        previous_state="",
        new_state="REQUESTED",
        notes="Immediate blood tests ordered.",
        timestamp=rao_base + timedelta(minutes=1),
    )
    _add_event(
        session,
        action=blood_panel,
        actor=nurse,
        previous_state="REQUESTED",
        new_state="SAMPLE_COLLECTED",
        notes="Sample drawn and transferred to lab.",
        timestamp=rao_base + timedelta(minutes=6),
    )
    _add_event(
        session,
        action=blood_panel,
        actor=lab,
        previous_state="SAMPLE_COLLECTED",
        new_state="PROCESSING",
        notes="Sample in analyzer queue.",
        timestamp=rao_base + timedelta(minutes=13),
    )
    _add_event(
        session,
        action=blood_panel,
        actor=lab,
        previous_state="PROCESSING",
        new_state="COMPLETED",
        notes="Panel complete; report ready but pending physician acknowledgment.",
        timestamp=rao_base + timedelta(minutes=24),
    )

    ecg_action = _create_action(
        session,
        patient_id=mr_rao.id,
        created_by=doctor,
        action_type=ActionType.DIAGNOSTIC,
        priority=Priority.CRITICAL,
        title="12-Lead ECG",
        notes="Rule out acute ischemic changes.",
        current_state="PROCESSING",
        department="Laboratory",
        created_at=rao_base + timedelta(minutes=2),
        updated_at=rao_base + timedelta(minutes=30),
        sla_deadline=now + timedelta(minutes=8),
    )
    _add_event(
        session,
        action=ecg_action,
        actor=doctor,
        previous_state="",
        new_state="REQUESTED",
        notes="ECG ordered at triage.",
        timestamp=rao_base + timedelta(minutes=2),
    )
    _add_event(
        session,
        action=ecg_action,
        actor=nurse,
        previous_state="REQUESTED",
        new_state="SAMPLE_COLLECTED",
        notes="Patient connected to ECG leads.",
        timestamp=rao_base + timedelta(minutes=9),
    )
    _add_event(
        session,
        action=ecg_action,
        actor=lab,
        previous_state="SAMPLE_COLLECTED",
        new_state="PROCESSING",
        notes="ECG tracing under review.",
        timestamp=rao_base + timedelta(minutes=30),
    )

    vitals_action = _create_action(
        session,
        patient_id=mr_rao.id,
        created_by=doctor,
        action_type=ActionType.VITALS_REQUEST,
        priority=Priority.URGENT,
        title="Cardiac Vitals Monitoring (q15min)",
        notes="Track BP, pulse, and oxygen saturation.",
        current_state="RECORDED",
        department="Nursing",
        created_at=rao_base + timedelta(minutes=3),
        updated_at=rao_base + timedelta(minutes=18),
        sla_deadline=now + timedelta(minutes=20),
    )
    _add_event(
        session,
        action=vitals_action,
        actor=doctor,
        previous_state="",
        new_state="REQUESTED",
        notes="High-frequency vitals requested.",
        timestamp=rao_base + timedelta(minutes=3),
    )
    _add_event(
        session,
        action=vitals_action,
        actor=nurse,
        previous_state="REQUESTED",
        new_state="RECORDED",
        notes="Vitals updated: BP 92/58, pulse 112, SpO2 95%.",
        timestamp=rao_base + timedelta(minutes=18),
    )

    initial_med = _create_action(
        session,
        patient_id=mr_rao.id,
        created_by=doctor,
        action_type=ActionType.MEDICATION,
        priority=Priority.CRITICAL,
        title="Aspirin 325mg + Nitroglycerin 0.4mg SL",
        notes="Initial chest pain medication order.",
        current_state="DISPENSED",
        department="Pharmacy",
        created_at=rao_base + timedelta(minutes=4),
        updated_at=rao_base + timedelta(minutes=21),
        sla_deadline=now + timedelta(minutes=10),
    )
    _add_event(
        session,
        action=initial_med,
        actor=doctor,
        previous_state="",
        new_state="PRESCRIBED",
        notes="Medication prescribed immediately after triage.",
        timestamp=rao_base + timedelta(minutes=4),
    )
    _add_event(
        session,
        action=initial_med,
        actor=pharmacist,
        previous_state="PRESCRIBED",
        new_state="DISPENSED",
        notes="Dose prepared and dispatched to emergency bay.",
        timestamp=rao_base + timedelta(minutes=21),
    )

    revised_med = _create_action(
        session,
        patient_id=mr_rao.id,
        created_by=doctor,
        action_type=ActionType.MEDICATION,
        priority=Priority.CRITICAL,
        title="Nitroglycerin revised dose 0.2mg SL",
        notes="Dose reduced after BP trend; pending pharmacy acknowledgment.",
        current_state="PRESCRIBED",
        department="Pharmacy",
        created_at=rao_base + timedelta(minutes=31),
        updated_at=rao_base + timedelta(minutes=31),
        sla_deadline=now + timedelta(minutes=6),
    )
    _add_event(
        session,
        action=revised_med,
        actor=doctor,
        previous_state="",
        new_state="PRESCRIBED",
        notes="Dosage modification entered after vitals update.",
        timestamp=rao_base + timedelta(minutes=31),
    )

    _add_note(
        session,
        patient=mr_rao,
        author=lab,
        note_type="laboratory",
        content="Cardiac enzyme panel is complete and report is ready; no physician acknowledgment yet.",
        created_at=rao_base + timedelta(minutes=25),
    )
    _add_note(
        session,
        patient=mr_rao,
        author=nurse,
        note_type="nursing",
        content="Vitals were updated, but revised medication order is not reflected in nursing workflow yet.",
        created_at=rao_base + timedelta(minutes=32),
    )
    _add_note(
        session,
        patient=mr_rao,
        author=pharmacist,
        note_type="pharmacy",
        content="Initial medication prepared. Awaiting confirmation for revised nitroglycerin dosage.",
        created_at=rao_base + timedelta(minutes=33),
    )

    _add_attachment(
        session,
        patient=mr_rao,
        action=blood_panel,
        created_by=lab,
        filename="cardiac-enzyme-panel.txt",
        stored_name="demo-rao-cardiac-enzyme-panel.txt",
        content="Troponin-I elevated. CK-MB elevated. Report flagged for urgent physician review.",
        created_at=rao_base + timedelta(minutes=24),
    )
    _add_attachment(
        session,
        patient=mr_rao,
        action=ecg_action,
        created_by=lab,
        filename="ecg-preliminary-tracing.txt",
        stored_name="demo-rao-ecg-preliminary.txt",
        content="Preliminary ECG: sinus tachycardia with ST-segment depression in lateral leads.",
        created_at=rao_base + timedelta(minutes=30),
    )

    print("  Added chest-pain coordination workflow for Mr. Rao (lab, nursing, and pharmacy handoff gaps).")
    return mr_rao


def _seed_action_with_timeline(
    session: Session,
    *,
    patient: Patient,
    created_by: User,
    priority: Priority,
    title: str,
    notes: str,
    department: str,
    base_time: datetime,
    sla_deadline: datetime,
    timeline: list[tuple[User, str, str, int]],
    action_type: ActionType | None = None,
    custom_type: CustomActionType | None = None,
) -> ClinicalAction:
    if not timeline:
        raise RuntimeError(f"Timeline is required for seeded action '{title}'")

    created_at = base_time + timedelta(minutes=timeline[0][3])
    updated_at = base_time + timedelta(minutes=timeline[-1][3])
    action = _create_action(
        session,
        patient_id=patient.id,
        created_by=created_by,
        action_type=action_type,
        custom_type=custom_type,
        priority=priority,
        title=title,
        notes=notes,
        current_state=timeline[-1][1],
        department=department,
        created_at=created_at,
        updated_at=updated_at,
        sla_deadline=sla_deadline,
    )

    previous_state = ""
    for actor, new_state, event_notes, offset_minutes in timeline:
        _add_event(
            session,
            action=action,
            actor=actor,
            previous_state=previous_state,
            new_state=new_state,
            notes=event_notes,
            timestamp=base_time + timedelta(minutes=offset_minutes),
        )
        previous_state = new_state

    return action


def _seed_realistic_general_demo_workflows(
    session: Session,
    users_by_email: dict[str, User],
    patient_by_name: dict[str, Patient],
    *,
    now: datetime,
):
    doctor = users_by_email["doctor@clavis.local"]
    nurse = users_by_email["nurse@clavis.local"]
    pharmacist = users_by_email["pharmacy@clavis.local"]
    lab = users_by_email["lab@clavis.local"]
    radiology = users_by_email["radiology@clavis.local"]

    aarav = patient_by_name["Aarav Mehta"]
    aarav_base = aarav.admission_date or (now - timedelta(hours=5))
    _seed_action_with_timeline(
        session,
        patient=aarav,
        created_by=doctor,
        action_type=ActionType.VITALS_REQUEST,
        priority=Priority.URGENT,
        title="Post-op Vitals Monitoring (q4h)",
        notes="Monitor HR, BP, temperature, and pain score after appendectomy.",
        department="Nursing",
        base_time=aarav_base,
        sla_deadline=now + timedelta(minutes=80),
        timeline=[
            (doctor, "REQUESTED", "Post-op monitoring protocol started.", 20),
            (nurse, "RECORDED", "Latest vitals stable and within expected recovery range.", 58),
        ],
    )
    _seed_action_with_timeline(
        session,
        patient=aarav,
        created_by=doctor,
        action_type=ActionType.MEDICATION,
        priority=Priority.ROUTINE,
        title="IV Ceftriaxone 1g",
        notes="Continue prophylactic antibiotic coverage for 24 hours.",
        department="Pharmacy",
        base_time=aarav_base,
        sla_deadline=now + timedelta(minutes=120),
        timeline=[
            (doctor, "PRESCRIBED", "Antibiotic order entered in post-op plan.", 25),
            (pharmacist, "DISPENSED", "Prepared and released to nursing station.", 43),
            (nurse, "ADMINISTERED", "Dose administered without complications.", 70),
        ],
    )
    _seed_action_with_timeline(
        session,
        patient=aarav,
        created_by=doctor,
        action_type=ActionType.CARE_INSTRUCTION,
        priority=Priority.ROUTINE,
        title="Early Ambulation Protocol",
        notes="Sit out of bed and supervised walking twice daily.",
        department="Nursing",
        base_time=aarav_base,
        sla_deadline=now + timedelta(minutes=180),
        timeline=[
            (doctor, "ISSUED", "Early mobilization advised.", 28),
            (nurse, "ACKNOWLEDGED", "Protocol discussed with patient.", 47),
            (nurse, "IN_PROGRESS", "Completed first assisted walk in corridor.", 92),
        ],
    )
    _add_note(
        session,
        patient=aarav,
        author=nurse,
        note_type="progress",
        content="Post-op recovery is smooth. Pain controlled and oral intake resumed.",
        created_at=aarav_base + timedelta(minutes=94),
    )

    nisha = patient_by_name["Nisha Verma"]
    nisha_base = nisha.admission_date or (now - timedelta(hours=6))
    nisha_troponin = _seed_action_with_timeline(
        session,
        patient=nisha,
        created_by=doctor,
        action_type=ActionType.DIAGNOSTIC,
        priority=Priority.CRITICAL,
        title="Repeat Troponin Panel",
        notes="Rule out ongoing myocardial injury.",
        department="Laboratory",
        base_time=nisha_base,
        sla_deadline=now + timedelta(minutes=14),
        timeline=[
            (doctor, "REQUESTED", "Repeat panel requested after chest discomfort recurrence.", 16),
            (nurse, "SAMPLE_COLLECTED", "Second blood sample sent to lab.", 36),
            (lab, "PROCESSING", "Sample queued in urgent analyzer lane.", 70),
        ],
    )
    _seed_action_with_timeline(
        session,
        patient=nisha,
        created_by=doctor,
        action_type=ActionType.MEDICATION,
        priority=Priority.URGENT,
        title="Clopidogrel Loading Dose",
        notes="Start antiplatelet therapy while labs are pending.",
        department="Pharmacy",
        base_time=nisha_base,
        sla_deadline=now + timedelta(minutes=45),
        timeline=[
            (doctor, "PRESCRIBED", "Loading dose ordered by cardiology team.", 20),
            (pharmacist, "DISPENSED", "Medication issued to bedside nursing team.", 52),
        ],
    )
    _seed_action_with_timeline(
        session,
        patient=nisha,
        created_by=doctor,
        action_type=ActionType.REFERRAL,
        priority=Priority.URGENT,
        title="Cardiology Consultant Review",
        notes="Senior cardiology opinion for telemetry abnormalities.",
        department="Referral",
        base_time=nisha_base,
        sla_deadline=now + timedelta(minutes=35),
        timeline=[
            (doctor, "INITIATED", "Consult raised from medicine unit.", 24),
            (doctor, "ACKNOWLEDGED", "Cardiology registrar accepted case.", 66),
        ],
    )
    _add_note(
        session,
        patient=nisha,
        author=doctor,
        note_type="assessment",
        content="Persistent mild chest pain; awaiting repeat troponin and consultant recommendation.",
        created_at=nisha_base + timedelta(minutes=74),
    )
    _add_attachment(
        session,
        patient=nisha,
        action=nisha_troponin,
        created_by=lab,
        filename="troponin-trend.txt",
        stored_name="demo-nisha-troponin-trend.txt",
        content="Initial troponin mildly elevated; repeat sample currently processing.",
        created_at=nisha_base + timedelta(minutes=70),
    )

    rahul = patient_by_name["Rahul Kapoor"]
    rahul_base = rahul.admission_date or (now - timedelta(hours=6))
    _seed_action_with_timeline(
        session,
        patient=rahul,
        created_by=doctor,
        action_type=ActionType.DIAGNOSTIC,
        priority=Priority.CRITICAL,
        title="Blood Culture Set x2",
        notes="Sepsis workup in view of persistent fever and hypotension.",
        department="Laboratory",
        base_time=rahul_base,
        sla_deadline=now - timedelta(minutes=28),
        timeline=[
            (doctor, "REQUESTED", "Cultures requested before broad-spectrum antibiotics.", 12),
            (nurse, "SAMPLE_COLLECTED", "Peripheral and central samples collected.", 30),
            (lab, "PROCESSING", "Cultures incubating; Gram stain pending.", 92),
        ],
    )
    _seed_action_with_timeline(
        session,
        patient=rahul,
        created_by=doctor,
        action_type=ActionType.VITALS_REQUEST,
        priority=Priority.CRITICAL,
        title="Sepsis Vitals Cycle (q30min)",
        notes="Continuous trend capture for BP, pulse, and urine output.",
        department="Nursing",
        base_time=rahul_base,
        sla_deadline=now - timedelta(minutes=10),
        timeline=[
            (doctor, "REQUESTED", "Escalated monitoring initiated.", 14),
        ],
    )
    _seed_action_with_timeline(
        session,
        patient=rahul,
        created_by=doctor,
        action_type=ActionType.MEDICATION,
        priority=Priority.CRITICAL,
        title="Piperacillin-Tazobactam 4.5g IV",
        notes="Empiric coverage pending culture finalization.",
        department="Pharmacy",
        base_time=rahul_base,
        sla_deadline=now + timedelta(minutes=12),
        timeline=[
            (doctor, "PRESCRIBED", "STAT antibiotic order entered.", 18),
        ],
    )
    _add_note(
        session,
        patient=rahul,
        author=nurse,
        note_type="nursing",
        content="Borderline blood pressure continues. Fluids running, awaiting first antibiotic dose.",
        created_at=rahul_base + timedelta(minutes=94),
    )

    kavya = patient_by_name["Kavya Nair"]
    kavya_base = kavya.admission_date or (now - timedelta(hours=6))
    _seed_action_with_timeline(
        session,
        patient=kavya,
        created_by=doctor,
        action_type=ActionType.DIAGNOSTIC,
        priority=Priority.URGENT,
        title="Arterial Blood Gas",
        notes="Assess respiratory status after acute wheeze episode.",
        department="Laboratory",
        base_time=kavya_base,
        sla_deadline=now + timedelta(minutes=25),
        timeline=[
            (doctor, "REQUESTED", "ABG ordered after desaturation episode.", 10),
            (nurse, "SAMPLE_COLLECTED", "Radial sample collected at bedside.", 18),
            (lab, "PROCESSING", "ABG sample under analysis.", 26),
            (lab, "COMPLETED", "Gas values improved from admission baseline.", 35),
        ],
    )
    _seed_action_with_timeline(
        session,
        patient=kavya,
        created_by=doctor,
        action_type=ActionType.MEDICATION,
        priority=Priority.ROUTINE,
        title="Nebulized Salbutamol",
        notes="Continue bronchodilator treatment every 6 hours.",
        department="Pharmacy",
        base_time=kavya_base,
        sla_deadline=now + timedelta(minutes=70),
        timeline=[
            (doctor, "PRESCRIBED", "Bronchodilator protocol initiated.", 12),
            (pharmacist, "DISPENSED", "Nebule pack handed over to ward.", 20),
            (nurse, "ADMINISTERED", "Latest dose administered successfully.", 28),
        ],
    )
    _seed_action_with_timeline(
        session,
        patient=kavya,
        created_by=doctor,
        action_type=ActionType.CARE_INSTRUCTION,
        priority=Priority.ROUTINE,
        title="Incentive Spirometry Coaching",
        notes="Breathing exercise sessions every nursing shift.",
        department="Nursing",
        base_time=kavya_base,
        sla_deadline=now + timedelta(minutes=90),
        timeline=[
            (doctor, "ISSUED", "Respiratory exercises instructed.", 14),
            (nurse, "ACKNOWLEDGED", "Technique demonstrated to patient.", 23),
            (nurse, "IN_PROGRESS", "Morning session completed.", 34),
            (nurse, "COMPLETED", "Target repetitions met for current cycle.", 48),
        ],
    )
    _add_note(
        session,
        patient=kavya,
        author=doctor,
        note_type="progress",
        content="Symptoms improving. Candidate for discharge review in next 24 hours if stable.",
        created_at=kavya_base + timedelta(minutes=52),
    )

    sandeep = patient_by_name["Sandeep Kulkarni"]
    sandeep_base = sandeep.admission_date or (now - timedelta(hours=6))
    sandeep_ct = _seed_action_with_timeline(
        session,
        patient=sandeep,
        created_by=doctor,
        action_type=ActionType.DIAGNOSTIC,
        priority=Priority.URGENT,
        title="Chest CT Screening",
        notes="Evaluate worsening COPD symptoms and possible consolidation.",
        department="Radiology",
        base_time=sandeep_base,
        sla_deadline=now + timedelta(minutes=30),
        timeline=[
            (doctor, "REQUESTED", "Urgent CT requested from pulmonology unit.", 17),
            (nurse, "SAMPLE_COLLECTED", "Patient prepared and moved for scan slot.", 42),
        ],
    )
    _seed_action_with_timeline(
        session,
        patient=sandeep,
        created_by=doctor,
        action_type=ActionType.REFERRAL,
        priority=Priority.ROUTINE,
        title="Pulmonology Senior Round",
        notes="Need bedside review for NIV planning.",
        department="Referral",
        base_time=sandeep_base,
        sla_deadline=now + timedelta(minutes=120),
        timeline=[
            (doctor, "INITIATED", "Senior consult requested.", 22),
        ],
    )
    _seed_action_with_timeline(
        session,
        patient=sandeep,
        created_by=doctor,
        action_type=ActionType.VITALS_REQUEST,
        priority=Priority.URGENT,
        title="Oxygen Saturation Trending",
        notes="Track SpO2 and respiratory rate while on bronchodilator therapy.",
        department="Nursing",
        base_time=sandeep_base,
        sla_deadline=now + timedelta(minutes=50),
        timeline=[
            (doctor, "REQUESTED", "Continuous respiratory vitals requested.", 21),
            (nurse, "RECORDED", "SpO2 improved to 93% on controlled oxygen.", 54),
        ],
    )
    _add_note(
        session,
        patient=sandeep,
        author=nurse,
        note_type="nursing",
        content="Mild dyspnea persists on exertion. Awaiting radiology availability for chest CT.",
        created_at=sandeep_base + timedelta(minutes=58),
    )
    _add_attachment(
        session,
        patient=sandeep,
        action=sandeep_ct,
        created_by=radiology,
        filename="ct-slot-confirmation.txt",
        stored_name="demo-sandeep-ct-slot.txt",
        content="Radiology slot tentatively assigned for evening session; transport requested.",
        created_at=sandeep_base + timedelta(minutes=44),
    )

    pooja = patient_by_name["Pooja Menon"]
    pooja_base = pooja.admission_date or (now - timedelta(hours=6))
    _seed_action_with_timeline(
        session,
        patient=pooja,
        created_by=doctor,
        action_type=ActionType.MEDICATION,
        priority=Priority.CRITICAL,
        title="Insulin Infusion Titration",
        notes="Titrate infusion based on hourly glucose values.",
        department="Pharmacy",
        base_time=pooja_base,
        sla_deadline=now + timedelta(minutes=35),
        timeline=[
            (doctor, "PRESCRIBED", "Insulin infusion started for severe hyperglycemia.", 14),
            (pharmacist, "DISPENSED", "Infusion bag prepared and delivered.", 30),
        ],
    )
    _seed_action_with_timeline(
        session,
        patient=pooja,
        created_by=doctor,
        action_type=ActionType.DIAGNOSTIC,
        priority=Priority.ROUTINE,
        title="HbA1c + Metabolic Panel",
        notes="Baseline diabetic control and electrolyte status.",
        department="Laboratory",
        base_time=pooja_base,
        sla_deadline=now + timedelta(minutes=95),
        timeline=[
            (doctor, "REQUESTED", "Baseline diabetic labs ordered.", 18),
        ],
    )
    _seed_action_with_timeline(
        session,
        patient=pooja,
        created_by=doctor,
        action_type=ActionType.CARE_INSTRUCTION,
        priority=Priority.ROUTINE,
        title="Diabetic Diet Counseling",
        notes="Reinforce meal timing and carbohydrate distribution.",
        department="Nursing",
        base_time=pooja_base,
        sla_deadline=now + timedelta(minutes=120),
        timeline=[
            (doctor, "ISSUED", "Diet counseling task created.", 20),
            (nurse, "ACKNOWLEDGED", "Counseling session completed with family present.", 49),
        ],
    )
    _add_note(
        session,
        patient=pooja,
        author=nurse,
        note_type="progress",
        content="Capillary glucose trend is improving; infusion adjustments ongoing.",
        created_at=pooja_base + timedelta(minutes=52),
    )

    vivek = patient_by_name["Vivek Sharma"]
    vivek_base = vivek.admission_date or (now - timedelta(hours=6))
    _seed_action_with_timeline(
        session,
        patient=vivek,
        created_by=doctor,
        action_type=ActionType.REFERRAL,
        priority=Priority.URGENT,
        title="Physiotherapy Rehabilitation Consult",
        notes="Early mobilization and gait training plan.",
        department="Referral",
        base_time=vivek_base,
        sla_deadline=now + timedelta(minutes=65),
        timeline=[
            (doctor, "INITIATED", "Rehab consult requested.", 13),
            (doctor, "ACKNOWLEDGED", "Physiotherapy team accepted referral.", 28),
            (doctor, "REVIEWED", "Initial assessment documented by rehab team.", 63),
        ],
    )
    _seed_action_with_timeline(
        session,
        patient=vivek,
        created_by=doctor,
        action_type=ActionType.CARE_INSTRUCTION,
        priority=Priority.ROUTINE,
        title="Swallow Safety Protocol",
        notes="Aspiration precautions and supervised oral intake plan.",
        department="Nursing",
        base_time=vivek_base,
        sla_deadline=now + timedelta(minutes=100),
        timeline=[
            (doctor, "ISSUED", "Swallow safety protocol ordered.", 17),
            (nurse, "ACKNOWLEDGED", "Precaution chart updated.", 31),
            (nurse, "IN_PROGRESS", "Meal supervision initiated.", 58),
        ],
    )
    _seed_action_with_timeline(
        session,
        patient=vivek,
        created_by=doctor,
        action_type=ActionType.MEDICATION,
        priority=Priority.URGENT,
        title="Aspirin 150mg OD",
        notes="Secondary stroke prevention regimen.",
        department="Pharmacy",
        base_time=vivek_base,
        sla_deadline=now + timedelta(minutes=85),
        timeline=[
            (doctor, "PRESCRIBED", "Antiplatelet started post imaging review.", 15),
            (pharmacist, "DISPENSED", "Dose supplied to ward.", 37),
            (nurse, "ADMINISTERED", "Morning dose administered.", 59),
        ],
    )
    _add_note(
        session,
        patient=vivek,
        author=doctor,
        note_type="assessment",
        content="Neurologic deficits improving. Rehab pathway active and swallowing precautions in place.",
        created_at=vivek_base + timedelta(minutes=66),
    )

    neha = patient_by_name["Neha Joshi"]
    neha_base = neha.admission_date or (now - timedelta(hours=6))
    failed_culture = _seed_action_with_timeline(
        session,
        patient=neha,
        created_by=doctor,
        action_type=ActionType.DIAGNOSTIC,
        priority=Priority.URGENT,
        title="Urine Culture",
        notes="UTI workup started from emergency triage.",
        department="Laboratory",
        base_time=neha_base,
        sla_deadline=now + timedelta(minutes=40),
        timeline=[
            (doctor, "REQUESTED", "Initial urine culture requested.", 11),
            (nurse, "SAMPLE_COLLECTED", "Sample delivered to lab.", 19),
            (lab, "PROCESSING", "Culture processing started.", 34),
            (lab, "FAILED", "Sample contamination detected; repeat required.", 53),
        ],
    )
    _seed_action_with_timeline(
        session,
        patient=neha,
        created_by=doctor,
        action_type=ActionType.DIAGNOSTIC,
        priority=Priority.URGENT,
        title="Repeat Urine Culture",
        notes="Second sample requested after contamination in first run.",
        department="Laboratory",
        base_time=neha_base,
        sla_deadline=now + timedelta(minutes=70),
        timeline=[
            (doctor, "REQUESTED", "Repeat sample order placed.", 60),
        ],
    )
    _seed_action_with_timeline(
        session,
        patient=neha,
        created_by=doctor,
        action_type=ActionType.MEDICATION,
        priority=Priority.ROUTINE,
        title="Empiric Nitrofurantoin",
        notes="Start empiric oral antibiotic while repeat culture is pending.",
        department="Pharmacy",
        base_time=neha_base,
        sla_deadline=now + timedelta(minutes=95),
        timeline=[
            (doctor, "PRESCRIBED", "Empiric therapy started pending microbiology.", 66),
        ],
    )
    _add_note(
        session,
        patient=neha,
        author=lab,
        note_type="laboratory",
        content="First urine culture rejected due to contamination; repeat sample requested urgently.",
        created_at=neha_base + timedelta(minutes=54),
    )
    _add_attachment(
        session,
        patient=neha,
        action=failed_culture,
        created_by=lab,
        filename="urine-culture-rejection.txt",
        stored_name="demo-neha-culture-rejection.txt",
        content="Specimen integrity issue noted. Re-collection advised before antimicrobial narrowing.",
        created_at=neha_base + timedelta(minutes=53),
    )

    print("  Added realistic staged workflows across all general demo patients.")


def _seed_story_patients(
    session: Session,
    users_by_email: dict[str, User],
    include_actions: bool,
):
    doctor = users_by_email["doctor@clavis.local"]
    nurse = users_by_email["nurse@clavis.local"]
    pharmacist = users_by_email["pharmacy@clavis.local"]
    lab = users_by_email["lab@clavis.local"]
    radiology = users_by_email["radiology@clavis.local"]

    now = datetime.utcnow()
    mri_base = now - timedelta(hours=2, minutes=10)

    _seed_mr_rao_story(
        session,
        users_by_email,
        include_actions=include_actions,
        now=now,
    )
    ms_iyer = Patient(
        name="Ms. Ananya Iyer",
        age=46,
        gender="Female",
        blood_group="A+",
        allergies=DEMO_PATIENT_PROFILES["Ms. Ananya Iyer"]["allergies"],
        past_medical_history=DEMO_PATIENT_PROFILES["Ms. Ananya Iyer"]["past_medical_history"],
        chronic_conditions=DEMO_PATIENT_PROFILES["Ms. Ananya Iyer"]["chronic_conditions"],
        current_medications=DEMO_PATIENT_PROFILES["Ms. Ananya Iyer"]["current_medications"],
        surgical_history=DEMO_PATIENT_PROFILES["Ms. Ananya Iyer"]["surgical_history"],
        family_history=DEMO_PATIENT_PROFILES["Ms. Ananya Iyer"]["family_history"],
        social_history=DEMO_PATIENT_PROFILES["Ms. Ananya Iyer"]["social_history"],
        immunization_history=DEMO_PATIENT_PROFILES["Ms. Ananya Iyer"]["immunization_history"],
        ward="Neurology Ward 4",
        primary_doctor_id=doctor.id,
        admission_date=mri_base,
        created_at=mri_base,
    )
    session.add(ms_iyer)
    session.flush()
    print(f"Created patient: {ms_iyer.name} (id={ms_iyer.id})")

    general_patients: dict[str, Patient] = {}
    for index, spec in enumerate(DEMO_PATIENT_SPECS, start=1):
        created_at = now - timedelta(hours=5, minutes=index * 13)
        profile = DEMO_PATIENT_PROFILES.get(spec["name"], {})
        patient = Patient(
            name=spec["name"],
            age=spec["age"],
            gender=spec["gender"],
            blood_group=spec["blood_group"],
            allergies=profile.get("allergies"),
            past_medical_history=profile.get("past_medical_history"),
            chronic_conditions=profile.get("chronic_conditions"),
            current_medications=profile.get("current_medications"),
            surgical_history=profile.get("surgical_history"),
            family_history=profile.get("family_history"),
            social_history=profile.get("social_history"),
            immunization_history=profile.get("immunization_history"),
            ward=spec["ward"],
            primary_doctor_id=doctor.id,
            admission_date=created_at,
            created_at=created_at,
        )
        session.add(patient)
        session.flush()
        general_patients[patient.name] = patient
        print(f"Created patient: {patient.name} (id={patient.id})")

    if not include_actions:
        return

    mri_workflow = CustomActionType(
        name=MRI_WORKFLOW_NAME,
        department="Radiology",
        terminal_state="CLOSED",
        sla_routine_minutes=360,
        sla_urgent_minutes=120,
        sla_critical_minutes=45,
        created_at=mri_base,
    )
    mri_workflow.states = [
        "REQUESTED",
        "ACCEPTED",
        "SCHEDULED",
        "SCANNING",
        "REPORT_READY",
        "CLOSED",
    ]
    session.add(mri_workflow)
    session.flush()

    # Patient 2: Ms. Ananya Iyer - MRI request with explicit acceptance/scheduling/report tracking.
    mri_scan = _create_action(
        session,
        patient_id=ms_iyer.id,
        created_by=doctor,
        custom_type=mri_workflow,
        priority=Priority.URGENT,
        title="Brain MRI with Contrast",
        notes="Assess possible acute ischemic changes.",
        current_state="REPORT_READY",
        department="Radiology",
        created_at=mri_base + timedelta(minutes=1),
        updated_at=mri_base + timedelta(minutes=85),
        sla_deadline=now + timedelta(minutes=40),
    )
    _add_event(
        session,
        action=mri_scan,
        actor=doctor,
        previous_state="",
        new_state="REQUESTED",
        notes="MRI ordered by attending physician.",
        timestamp=mri_base + timedelta(minutes=1),
    )
    _add_event(
        session,
        action=mri_scan,
        actor=radiology,
        previous_state="REQUESTED",
        new_state="ACCEPTED",
        notes="Request accepted by Radiology.",
        timestamp=mri_base + timedelta(minutes=10),
    )
    _add_event(
        session,
        action=mri_scan,
        actor=radiology,
        previous_state="ACCEPTED",
        new_state="SCHEDULED",
        notes="MRI slot scheduled and confirmed.",
        timestamp=mri_base + timedelta(minutes=20),
    )
    _add_event(
        session,
        action=mri_scan,
        actor=radiology,
        previous_state="SCHEDULED",
        new_state="SCANNING",
        notes="Patient moved to scanner and imaging started.",
        timestamp=mri_base + timedelta(minutes=55),
    )
    _add_event(
        session,
        action=mri_scan,
        actor=radiology,
        previous_state="SCANNING",
        new_state="REPORT_READY",
        notes="MRI report uploaded and ready for physician review.",
        timestamp=mri_base + timedelta(minutes=85),
    )

    mri_renal = _create_action(
        session,
        patient_id=ms_iyer.id,
        created_by=doctor,
        action_type=ActionType.DIAGNOSTIC,
        priority=Priority.ROUTINE,
        title="Renal Function Panel (Pre-Contrast)",
        notes="Ensure contrast safety.",
        current_state="COMPLETED",
        department="Laboratory",
        created_at=mri_base + timedelta(minutes=2),
        updated_at=mri_base + timedelta(minutes=27),
        sla_deadline=mri_base + timedelta(minutes=122),
    )
    _add_event(
        session,
        action=mri_renal,
        actor=doctor,
        previous_state="",
        new_state="REQUESTED",
        notes="Pre-contrast bloodwork ordered.",
        timestamp=mri_base + timedelta(minutes=2),
    )
    _add_event(
        session,
        action=mri_renal,
        actor=nurse,
        previous_state="REQUESTED",
        new_state="SAMPLE_COLLECTED",
        notes="Sample collected in neurology ward.",
        timestamp=mri_base + timedelta(minutes=8),
    )
    _add_event(
        session,
        action=mri_renal,
        actor=lab,
        previous_state="SAMPLE_COLLECTED",
        new_state="PROCESSING",
        notes="Laboratory processing initiated.",
        timestamp=mri_base + timedelta(minutes=18),
    )
    _add_event(
        session,
        action=mri_renal,
        actor=lab,
        previous_state="PROCESSING",
        new_state="COMPLETED",
        notes="Renal panel complete; contrast cleared.",
        timestamp=mri_base + timedelta(minutes=27),
    )

    mri_premed = _create_action(
        session,
        patient_id=ms_iyer.id,
        created_by=doctor,
        action_type=ActionType.MEDICATION,
        priority=Priority.URGENT,
        title="Contrast Premedication (Hydrocortisone)",
        notes="Premedication before MRI contrast.",
        current_state="DISPENSED",
        department="Pharmacy",
        created_at=mri_base + timedelta(minutes=5),
        updated_at=mri_base + timedelta(minutes=14),
        sla_deadline=now + timedelta(minutes=25),
    )
    _add_event(
        session,
        action=mri_premed,
        actor=doctor,
        previous_state="",
        new_state="PRESCRIBED",
        notes="Premedication prescribed before scan.",
        timestamp=mri_base + timedelta(minutes=5),
    )
    _add_event(
        session,
        action=mri_premed,
        actor=pharmacist,
        previous_state="PRESCRIBED",
        new_state="DISPENSED",
        notes="Dose prepared and sent to ward.",
        timestamp=mri_base + timedelta(minutes=14),
    )

    mri_referral = _create_action(
        session,
        patient_id=ms_iyer.id,
        created_by=doctor,
        action_type=ActionType.REFERRAL,
        priority=Priority.URGENT,
        title="Neurology Specialist Review",
        notes="Awaiting post-MRI consult.",
        current_state="INITIATED",
        department="Referral",
        created_at=mri_base + timedelta(minutes=30),
        updated_at=mri_base + timedelta(minutes=30),
        sla_deadline=now - timedelta(minutes=15),
    )
    _add_event(
        session,
        action=mri_referral,
        actor=doctor,
        previous_state="",
        new_state="INITIATED",
        notes="Consult requested and pending specialist acceptance.",
        timestamp=mri_base + timedelta(minutes=30),
    )

    mri_instruction = _create_action(
        session,
        patient_id=ms_iyer.id,
        created_by=doctor,
        action_type=ActionType.CARE_INSTRUCTION,
        priority=Priority.ROUTINE,
        title="Pre-Scan Hydration + Fasting Protocol",
        notes="Maintain hydration while fasting until scan.",
        current_state="COMPLETED",
        department="Nursing",
        created_at=mri_base + timedelta(minutes=6),
        updated_at=mri_base + timedelta(minutes=24),
        sla_deadline=mri_base + timedelta(minutes=126),
    )
    _add_event(
        session,
        action=mri_instruction,
        actor=doctor,
        previous_state="",
        new_state="ISSUED",
        notes="Instruction issued for imaging prep.",
        timestamp=mri_base + timedelta(minutes=6),
    )
    _add_event(
        session,
        action=mri_instruction,
        actor=nurse,
        previous_state="ISSUED",
        new_state="ACKNOWLEDGED",
        notes="Nursing acknowledged prep protocol.",
        timestamp=mri_base + timedelta(minutes=12),
    )
    _add_event(
        session,
        action=mri_instruction,
        actor=nurse,
        previous_state="ACKNOWLEDGED",
        new_state="IN_PROGRESS",
        notes="Protocol in progress.",
        timestamp=mri_base + timedelta(minutes=16),
    )
    _add_event(
        session,
        action=mri_instruction,
        actor=nurse,
        previous_state="IN_PROGRESS",
        new_state="COMPLETED",
        notes="Pre-scan protocol completed.",
        timestamp=mri_base + timedelta(minutes=24),
    )

    _add_note(
        session,
        patient=ms_iyer,
        author=radiology,
        note_type="radiology",
        content="MRI accepted and scheduled; patient called in for slot.",
        created_at=mri_base + timedelta(minutes=21),
    )
    _add_note(
        session,
        patient=ms_iyer,
        author=doctor,
        note_type="assessment",
        content="MRI report received; pending neurology consult for final interpretation.",
        created_at=mri_base + timedelta(minutes=86),
    )

    _add_attachment(
        session,
        patient=ms_iyer,
        action=mri_scan,
        created_by=radiology,
        filename="mri-report-prelim.txt",
        stored_name="demo-iyer-mri-report-prelim.txt",
        content="MRI preliminary report: no acute hemorrhage, correlate clinically.",
        created_at=mri_base + timedelta(minutes=85),
    )
    _add_attachment(
        session,
        patient=ms_iyer,
        action=mri_renal,
        created_by=lab,
        filename="renal-panel.txt",
        stored_name="demo-iyer-renal-panel.txt",
        content="Creatinine within normal range. Cleared for contrast administration.",
        created_at=mri_base + timedelta(minutes=27),
    )

    _seed_realistic_general_demo_workflows(
        session,
        users_by_email,
        general_patients,
        now=now,
    )

    print("  Created scripted MRI workflow with notes and attachments.")


def replace_mr_rao_for_demo(include_actions: bool = True):
    create_db()
    _validate_demo_seed_config()

    with Session(engine) as session:
        try:
            users_by_email = _ensure_demo_users(session)
            removed = _remove_existing_patient_by_name(session, "Mr. Rao")
            now = datetime.utcnow()
            patient = _seed_mr_rao_story(
                session,
                users_by_email,
                include_actions=include_actions,
                now=now,
            )
            session.commit()
        except Exception:
            session.rollback()
            raise
        print(
            f"Replaced Mr. Rao demo patient (removed={removed}, new_id={patient.id}, actions={'on' if include_actions else 'off'})."
        )


def run_seed(seed_actions: bool = True, seed_patient: bool = True):
    create_db()
    _validate_demo_seed_config()

    with Session(engine) as session:
        try:
            users_by_email = _ensure_demo_users(session)

            if seed_patient or seed_actions:
                _replace_demo_patients(
                    session,
                    users_by_email,
                    include_actions=seed_actions,
                )
            else:
                print("No default patient/actions seeded (clean slate).")

            session.commit()
        except Exception:
            session.rollback()
            raise

        print("Demo credentials:")
        for spec in DEMO_USERS:
            print(f"  {spec['email']} / {spec['password']}")
        print("Seed complete.")


if __name__ == "__main__":
    run_seed(
        seed_actions=os.getenv("CLAVIS_SEED_ACTIONS", "1") == "1",
        seed_patient=os.getenv("CLAVIS_SEED_PATIENT", "1") == "1",
    )
