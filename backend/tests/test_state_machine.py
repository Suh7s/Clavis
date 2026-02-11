import json

import pytest

from models import ActionType, CustomActionType
from state_machine import build_custom_transitions, validate_custom_transition, validate_transition


def test_validate_transition_valid_and_invalid():
    assert validate_transition(ActionType.MEDICATION, "PRESCRIBED", "DISPENSED") is True

    with pytest.raises(ValueError):
        validate_transition(ActionType.MEDICATION, "PRESCRIBED", "COMPLETED")


def test_custom_transition_rules():
    custom = CustomActionType(
        name="BLOOD_TRANSFUSION",
        department="Blood Bank",
        states_json=json.dumps(["ORDERED", "MATCHED", "TRANSFUSING", "COMPLETED"]),
        terminal_state="COMPLETED",
        sla_routine_minutes=120,
        sla_urgent_minutes=30,
        sla_critical_minutes=10,
    )

    transitions = build_custom_transitions(custom)
    assert transitions["ORDERED"] == ["MATCHED"]
    assert validate_custom_transition(custom, "MATCHED", "TRANSFUSING") is True

    with pytest.raises(ValueError):
        validate_custom_transition(custom, "MATCHED", "COMPLETED")
