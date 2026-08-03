from __future__ import annotations

from cosmos_control_tower.models.records import DryRunAction, Violation


def preview_actions(violations: list[Violation]) -> list[DryRunAction]:
    """Translate violations into proposed actions without executing anything."""
    actions: list[DryRunAction] = []
    for item in violations:
        if item.status != "VIOLATION":
            continue
        target_role, action = _routing(item)
        actions.append(
            DryRunAction(
                action_id=f"{item.rule_id}:{item.entity_type}:{item.source_id}",
                rule_id=item.rule_id,
                target_role=target_role,
                target_id=item.assigned_to_id if target_role == "broker" else item.department_id,
                entity_type=item.entity_type,
                source_id=item.source_id,
                card_url=item.card_url,
                reason=_reason(item),
                proposed_action=action,
                dry_run=True,
            )
        )
    return actions


def _routing(item: Violation) -> tuple[str, str]:
    if item.rule_id == "INACTIVE_ENTITY":
        hours = int(item.evidence.get("escalation_hours", 24))
        if hours >= 72:
            return "owner", "Добавить системное нарушение в отчёт собственника"
        if hours >= 48:
            return "rop", "Эскалировать РОПу для проверки брокера"
        return "broker", "Напомнить брокеру восстановить активность"
    if item.rule_id == "STAGE_AGE":
        return "rop", "Уведомить РОПа о зависшей сделке"
    if item.rule_id == "REQUIRED_FIELD":
        return "broker", "Предупредить о незаполненных обязательных полях"
    if item.rule_id == "OVERDUE_TASK":
        return "broker", "Напомнить о просроченной задаче"
    if item.rule_id == "UNACCEPTED_LEAD":
        return "broker", "Напомнить принять новый лид"
    if item.rule_id == "NO_FIRST_CALL":
        return "broker", "Напомнить выполнить первый звонок"
    return "broker", "Напомнить назначить следующий шаг"


def _reason(item: Violation) -> str:
    details = ", ".join(f"{key}={value}" for key, value in sorted(item.evidence.items()))
    return f"{item.rule_id}" + (f": {details}" if details else "")
