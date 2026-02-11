from __future__ import annotations

from models import ActionType, ClinicalAction, UserRole


DEPARTMENT_ROLE_MAP: dict[str, set[UserRole]] = {
    "pharmacy": {UserRole.PHARMACIST},
    "nursing": {UserRole.NURSE},
    "laboratory": {UserRole.LAB_TECH},
    "radiology": {UserRole.RADIOLOGIST},
    "referral": {UserRole.DOCTOR},
    "general": {UserRole.DOCTOR},
}


def _department_key(name: str) -> str:
    return name.strip().casefold()


def allowed_roles_for_department(department: str) -> set[UserRole]:
    return set(DEPARTMENT_ROLE_MAP.get(_department_key(department), {UserRole.DOCTOR}))


def can_access_department_queue(role: UserRole, department: str) -> bool:
    if role == UserRole.ADMIN:
        return True
    return role in allowed_roles_for_department(department)


def _cancel_roles() -> set[UserRole]:
    return {UserRole.DOCTOR, UserRole.ADMIN}


def roles_allowed_for_transition(action: ClinicalAction, new_state: str) -> set[UserRole]:
    if action.custom_action_type_id is not None:
        allowed = allowed_roles_for_department(action.department)
        allowed.add(UserRole.ADMIN)
        return allowed

    if action.action_type == ActionType.DIAGNOSTIC:
        if new_state == "CANCELLED":
            return _cancel_roles()
        base = (
            {UserRole.RADIOLOGIST}
            if action.department.strip().casefold() == "radiology"
            else {UserRole.LAB_TECH}
        )
        base.add(UserRole.ADMIN)
        return base

    if action.action_type == ActionType.MEDICATION:
        if new_state == "DISPENSED":
            return {UserRole.PHARMACIST, UserRole.ADMIN}
        if new_state == "ADMINISTERED":
            return {UserRole.NURSE, UserRole.ADMIN}
        if new_state == "CANCELLED":
            return _cancel_roles()

    if action.action_type == ActionType.REFERRAL:
        return {UserRole.DOCTOR, UserRole.ADMIN}

    if action.action_type == ActionType.CARE_INSTRUCTION:
        if new_state == "CANCELLED":
            return _cancel_roles() | {UserRole.NURSE}
        return {UserRole.NURSE, UserRole.ADMIN}

    if action.action_type == ActionType.VITALS_REQUEST:
        if new_state == "CANCELLED":
            return _cancel_roles() | {UserRole.NURSE}
        return {UserRole.NURSE, UserRole.ADMIN}

    return {UserRole.ADMIN}
