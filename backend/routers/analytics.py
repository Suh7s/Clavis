from collections import defaultdict
from datetime import datetime, timedelta

from fastapi import APIRouter, Depends
from sqlmodel import Session, select

from database import get_session
from models import ActionEvent, ClinicalAction, CustomActionType, User, UserRole
from services.auth import require_roles
from services.sla import is_action_overdue, is_terminal_state
from services.workflow import primary_queue_department

router = APIRouter(tags=["analytics"])


@router.get("/analytics")
def get_analytics(
    session: Session = Depends(get_session),
    _current_user: User = Depends(require_roles(UserRole.ADMIN, UserRole.DOCTOR)),
):
    actions = session.exec(select(ClinicalAction)).all()
    events = session.exec(
        select(ActionEvent).order_by(ActionEvent.timestamp.asc())  # type: ignore[union-attr]
    ).all()
    custom_types = session.exec(select(CustomActionType)).all()

    events_by_action: dict[int, list[ActionEvent]] = {}
    for event in events:
        events_by_action.setdefault(event.action_id, []).append(event)

    custom_map = {item.id: item for item in custom_types if item.id is not None}

    now = datetime.utcnow()

    duration_by_type: dict[str, list[float]] = defaultdict(list)
    sla_overall_total = 0
    sla_overall_compliant = 0
    sla_priority_stats: dict[str, dict[str, int]] = defaultdict(lambda: {"compliant": 0, "total": 0})
    throughput: dict[str, dict[str, int]] = defaultdict(
        lambda: {"last_24h": 0, "last_7d": 0, "last_30d": 0}
    )
    bottlenecks: dict[str, int] = defaultdict(int)

    for action in actions:
        custom_type = custom_map.get(action.custom_action_type_id)
        custom_terminal = custom_type.terminal_state if custom_type else None
        action_events = events_by_action.get(action.id, [])

        if is_terminal_state(action.action_type, action.current_state, custom_terminal):
            if action_events:
                started_at = action_events[0].timestamp
                completed_at = action_events[-1].timestamp
            else:
                started_at = action.created_at
                completed_at = action.updated_at or action.created_at

            duration_minutes = max((completed_at - started_at).total_seconds() / 60, 0)
            action_label = custom_type.name if custom_type else (action.action_type.value if action.action_type else "UNKNOWN")
            duration_by_type[action_label].append(duration_minutes)

            if action.sla_deadline is not None:
                sla_overall_total += 1
                priority_key = action.priority.value if hasattr(action.priority, "value") else str(action.priority)
                sla_priority_stats[priority_key]["total"] += 1
                if completed_at <= action.sla_deadline:
                    sla_overall_compliant += 1
                    sla_priority_stats[priority_key]["compliant"] += 1

            dept = action.department or "Unknown"
            if completed_at >= now - timedelta(hours=24):
                throughput[dept]["last_24h"] += 1
            if completed_at >= now - timedelta(days=7):
                throughput[dept]["last_7d"] += 1
            if completed_at >= now - timedelta(days=30):
                throughput[dept]["last_30d"] += 1
        else:
            if is_action_overdue(action, custom_terminal):
                dept = primary_queue_department(action, custom_terminal) or "Unknown"
                bottlenecks[dept] += 1

    avg_completion = []
    for action_type, durations in sorted(duration_by_type.items()):
        avg_completion.append(
            {
                "action_type": action_type,
                "avg_minutes": round(sum(durations) / len(durations), 2),
                "count": len(durations),
            }
        )

    overall_rate = round((sla_overall_compliant / sla_overall_total) * 100, 2) if sla_overall_total else 0.0
    by_priority = []
    for priority, stats in sorted(sla_priority_stats.items()):
        total = stats["total"]
        compliant = stats["compliant"]
        rate = round((compliant / total) * 100, 2) if total else 0.0
        by_priority.append(
            {
                "priority": priority,
                "compliant": compliant,
                "total": total,
                "rate": rate,
            }
        )

    throughput_rows = []
    for dept, stats in sorted(throughput.items()):
        throughput_rows.append(
            {
                "department": dept,
                "last_24h": stats["last_24h"],
                "last_7d": stats["last_7d"],
                "last_30d": stats["last_30d"],
            }
        )

    bottleneck_rows = [
        {"department": dept, "overdue_count": count}
        for dept, count in sorted(bottlenecks.items(), key=lambda item: item[1], reverse=True)
    ]

    return {
        "generated_at": now.isoformat(),
        "avg_completion_minutes": avg_completion,
        "sla_compliance": {
            "overall": {
                "compliant": sla_overall_compliant,
                "total": sla_overall_total,
                "rate": overall_rate,
            },
            "by_priority": by_priority,
        },
        "department_throughput": throughput_rows,
        "bottlenecks": bottleneck_rows,
    }
