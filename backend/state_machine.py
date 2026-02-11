from models import ActionType, CustomActionType

VALID_TRANSITIONS: dict[str, dict[str, list[str]]] = {
    ActionType.DIAGNOSTIC: {
        "REQUESTED": ["SAMPLE_COLLECTED"],
        "SAMPLE_COLLECTED": ["PROCESSING"],
        "PROCESSING": ["COMPLETED"],
    },
    ActionType.MEDICATION: {
        "PRESCRIBED": ["DISPENSED"],
        "DISPENSED": ["ADMINISTERED"],
    },
    ActionType.REFERRAL: {
        "INITIATED": ["ACKNOWLEDGED"],
        "ACKNOWLEDGED": ["REVIEWED"],
        "REVIEWED": ["CLOSED"],
    },
    ActionType.CARE_INSTRUCTION: {
        "ISSUED": ["ACKNOWLEDGED"],
        "ACKNOWLEDGED": ["IN_PROGRESS"],
        "IN_PROGRESS": ["COMPLETED"],
    },
}

INITIAL_STATES: dict[str, str] = {
    ActionType.DIAGNOSTIC: "REQUESTED",
    ActionType.MEDICATION: "PRESCRIBED",
    ActionType.REFERRAL: "INITIATED",
    ActionType.CARE_INSTRUCTION: "ISSUED",
}

TERMINAL_STATES: set[str] = {"COMPLETED", "ADMINISTERED", "CLOSED"}


def validate_transition(action_type: str, current_state: str, new_state: str) -> bool:
    """Validate and return True if transition is allowed, raise ValueError otherwise."""
    transitions = VALID_TRANSITIONS.get(action_type)
    if transitions is None:
        raise ValueError(f"Unknown action type: {action_type}")

    allowed = transitions.get(current_state)
    if allowed is None:
        raise ValueError(
            f"No transitions from state '{current_state}' for action type '{action_type}'"
        )

    if new_state not in allowed:
        raise ValueError(
            f"Invalid transition: {action_type} cannot go from '{current_state}' to '{new_state}'. "
            f"Allowed: {allowed}"
        )

    return True


def build_custom_transitions(cat: CustomActionType) -> dict[str, list[str]]:
    """Build a transition map from an ordered states list: each state can go to the next."""
    states = cat.states
    transitions: dict[str, list[str]] = {}
    for i in range(len(states) - 1):
        transitions[states[i]] = [states[i + 1]]
    return transitions


def validate_custom_transition(cat: CustomActionType, current_state: str, new_state: str) -> bool:
    transitions = build_custom_transitions(cat)
    allowed = transitions.get(current_state)
    if allowed is None:
        raise ValueError(
            f"No transitions from state '{current_state}' for custom type '{cat.name}'"
        )
    if new_state not in allowed:
        raise ValueError(
            f"Invalid transition: '{cat.name}' cannot go from '{current_state}' to '{new_state}'. "
            f"Allowed: {allowed}"
        )
    return True
