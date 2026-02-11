from datetime import datetime, timedelta

from models import ActionType, Priority, ClinicalAction, CustomActionType

SLA_DELTAS = {
    Priority.ROUTINE: timedelta(hours=2),
    Priority.URGENT: timedelta(minutes=30),
    Priority.CRITICAL: timedelta(minutes=10),
}

TERMINAL_STATES = {
    ActionType.DIAGNOSTIC: "COMPLETED",
    ActionType.MEDICATION: "ADMINISTERED",
    ActionType.REFERRAL: "CLOSED",
    ActionType.CARE_INSTRUCTION: "COMPLETED",
}


def compute_sla_deadline(priority: Priority) -> datetime:
    return datetime.utcnow() + SLA_DELTAS[priority]


def compute_custom_sla_deadline(priority: Priority, cat: CustomActionType) -> datetime:
    minutes = {
        Priority.ROUTINE: cat.sla_routine_minutes,
        Priority.URGENT: cat.sla_urgent_minutes,
        Priority.CRITICAL: cat.sla_critical_minutes,
    }[priority]
    return datetime.utcnow() + timedelta(minutes=minutes)


def is_terminal_state(action_type: str | None, state: str, custom_terminal: str | None = None) -> bool:
    if custom_terminal is not None:
        return state == custom_terminal
    if action_type is None:
        return False
    return TERMINAL_STATES.get(action_type) == state


def is_action_overdue(action: ClinicalAction, custom_terminal: str | None = None) -> bool:
    if is_terminal_state(action.action_type, action.current_state, custom_terminal):
        return False
    if action.sla_deadline is None:
        return False
    return datetime.utcnow() > action.sla_deadline
