import json
from datetime import datetime
from enum import Enum
from typing import Optional

from sqlmodel import SQLModel, Field


class ActionType(str, Enum):
    DIAGNOSTIC = "DIAGNOSTIC"
    MEDICATION = "MEDICATION"
    REFERRAL = "REFERRAL"
    CARE_INSTRUCTION = "CARE_INSTRUCTION"
    VITALS_REQUEST = "VITALS_REQUEST"


class Priority(str, Enum):
    ROUTINE = "ROUTINE"
    URGENT = "URGENT"
    CRITICAL = "CRITICAL"


class UserRole(str, Enum):
    DOCTOR = "doctor"
    NURSE = "nurse"
    PHARMACIST = "pharmacist"
    LAB_TECH = "lab_tech"
    RADIOLOGIST = "radiologist"
    ADMIN = "admin"


class AdmissionStatus(str, Enum):
    ADMITTED = "ADMITTED"
    DISCHARGED = "DISCHARGED"
    TRANSFERRED = "TRANSFERRED"


class User(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    name: str
    email: str = Field(unique=True, index=True)
    password_hash: str
    role: UserRole
    department: str = ""
    is_active: bool = True
    created_at: datetime = Field(default_factory=datetime.utcnow)


class Patient(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    name: str
    age: int
    gender: str
    blood_group: Optional[str] = None
    admission_date: Optional[datetime] = Field(default_factory=datetime.utcnow)
    ward: Optional[str] = None
    primary_doctor_id: Optional[int] = Field(default=None, foreign_key="user.id")
    is_active: bool = True
    admission_status: AdmissionStatus = AdmissionStatus.ADMITTED
    discharge_date: Optional[datetime] = None
    discharge_notes: Optional[str] = None
    created_at: datetime = Field(default_factory=datetime.utcnow)


class CustomActionType(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    name: str = Field(unique=True)
    department: str
    states_json: str = Field(default="[]")
    terminal_state: str
    sla_routine_minutes: int = 120
    sla_urgent_minutes: int = 30
    sla_critical_minutes: int = 10
    created_at: datetime = Field(default_factory=datetime.utcnow)

    @property
    def states(self) -> list[str]:
        return json.loads(self.states_json)

    @states.setter
    def states(self, val: list[str]):
        self.states_json = json.dumps(val)


class ClinicalAction(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    patient_id: int = Field(foreign_key="patient.id")
    created_by: Optional[int] = Field(default=None, foreign_key="user.id")
    assigned_to: Optional[int] = Field(default=None, foreign_key="user.id")
    action_type: Optional[ActionType] = None
    custom_action_type_id: Optional[int] = Field(default=None, foreign_key="customactiontype.id")
    title: str = ""
    notes: str = ""
    current_state: str
    priority: Priority
    department: str
    sla_deadline: Optional[datetime] = None
    created_at: datetime = Field(default_factory=datetime.utcnow)
    updated_at: Optional[datetime] = Field(default_factory=datetime.utcnow)


class ActionEvent(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    action_id: int = Field(foreign_key="clinicalaction.id")
    actor_id: Optional[int] = Field(default=None, foreign_key="user.id")
    actor_role: Optional[UserRole] = None
    previous_state: str
    new_state: str
    notes: str = ""
    timestamp: datetime = Field(default_factory=datetime.utcnow)


class PatientNote(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    patient_id: int = Field(foreign_key="patient.id")
    author_id: int = Field(foreign_key="user.id")
    note_type: str = "general"
    content: str
    created_at: datetime = Field(default_factory=datetime.utcnow)


class PatientTransfer(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    patient_id: int = Field(foreign_key="patient.id")
    from_doctor_id: Optional[int] = Field(default=None, foreign_key="user.id")
    to_doctor_id: Optional[int] = Field(default=None, foreign_key="user.id")
    from_ward: Optional[str] = None
    to_ward: Optional[str] = None
    reason: str = ""
    transferred_by: int = Field(foreign_key="user.id")
    created_at: datetime = Field(default_factory=datetime.utcnow)


class Attachment(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    patient_id: int = Field(foreign_key="patient.id")
    action_id: Optional[int] = Field(default=None, foreign_key="clinicalaction.id")
    filename: str
    file_type: str = ""
    file_size: int = 0
    stored_path: str
    created_by: int = Field(foreign_key="user.id")
    created_at: datetime = Field(default_factory=datetime.utcnow)
