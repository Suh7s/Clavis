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


class Priority(str, Enum):
    ROUTINE = "ROUTINE"
    URGENT = "URGENT"
    CRITICAL = "CRITICAL"


class Patient(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    name: str
    age: int
    gender: str
    created_at: datetime = Field(default_factory=datetime.utcnow)


class CustomActionType(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    name: str = Field(unique=True)
    department: str
    states_json: str = Field(default="[]")  # JSON list of ordered states
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
    action_type: Optional[ActionType] = None
    custom_action_type_id: Optional[int] = Field(default=None, foreign_key="customactiontype.id")
    current_state: str
    priority: Priority
    department: str
    sla_deadline: Optional[datetime] = None
    created_at: datetime = Field(default_factory=datetime.utcnow)


class ActionEvent(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    action_id: int = Field(foreign_key="clinicalaction.id")
    previous_state: str
    new_state: str
    timestamp: datetime = Field(default_factory=datetime.utcnow)
