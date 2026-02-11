from __future__ import annotations

from models import ActionType, ClinicalAction
from services.sla import is_terminal_state

RADIOLOGY_KEYWORDS = (
    "xray",
    "x-ray",
    "ct",
    "mri",
    "ultrasound",
    "scan",
    "radiology",
)


def _norm(value: str) -> str:
    return value.strip().casefold()


def default_department_for_action(
    action_type: ActionType | None,
    title: str = "",
    department_target: str | None = None,
) -> str:
    if department_target and department_target.strip():
        return department_target.strip()

    if action_type == ActionType.DIAGNOSTIC:
        title_norm = _norm(title)
        if any(word in title_norm for word in RADIOLOGY_KEYWORDS):
            return "Radiology"
        return "Laboratory"
    if action_type == ActionType.MEDICATION:
        return "Pharmacy"
    if action_type == ActionType.REFERRAL:
        return "Referral"
    if action_type in {ActionType.CARE_INSTRUCTION, ActionType.VITALS_REQUEST}:
        return "Nursing"
    return "General"


def queue_departments_for_action(action: ClinicalAction, custom_terminal: str | None = None) -> list[str]:
    if is_terminal_state(action.action_type, action.current_state, custom_terminal):
        return []

    if action.custom_action_type_id is not None:
        return [action.department]

    if action.action_type == ActionType.MEDICATION:
        if action.current_state == "PRESCRIBED":
            return ["Pharmacy"]
        if action.current_state == "DISPENSED":
            return ["Nursing"]
        return []

    if action.action_type in {
        ActionType.CARE_INSTRUCTION,
        ActionType.VITALS_REQUEST,
    }:
        return ["Nursing"]

    if action.action_type == ActionType.REFERRAL:
        return [action.department or "Referral"]

    if action.action_type == ActionType.DIAGNOSTIC:
        return [action.department or "Laboratory"]

    return [action.department]


def department_matches(department: str, candidates: list[str]) -> bool:
    dept = _norm(department)
    return any(_norm(c) == dept for c in candidates)


def primary_queue_department(action: ClinicalAction, custom_terminal: str | None = None) -> str:
    queue = queue_departments_for_action(action, custom_terminal)
    if queue:
        return queue[0]
    return action.department
