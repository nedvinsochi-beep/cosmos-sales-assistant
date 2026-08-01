from __future__ import annotations

from collections import Counter, defaultdict
from datetime import UTC, datetime
from typing import Any

from cosmos_control_tower.models.records import SourceRecord, Violation

SHOWING_SCHEDULED = {"UC_JTIRDL", "UC_UHD3S2"}
SHOWING_COMPLETED = {"UC_XRYC40", "UC_AHUAA7"}
BOOKING = {"UC_YLO039", "PREPARATION", "UC_0E5VUP"}
REGISTRATION = {"UC_WLKH6O", "PREPAYMENT_INVOICE"}
CLIENT_PAID = {"UC_WTVSOD", "EXECUTING"}
COMMISSION_INVOICED = {"FINAL_INVOICE"}
COMMISSION_RECEIVED = {"UC_ETQK40", "UC_NKAFJV"}
LOST = {"JUNK", "UC_KL0QCZ", "1", "LOSE", "UC_O76N4K"}

RULE_LABELS = {
    "UNACCEPTED_LEAD": "Новый лид не принят",
    "NO_NEXT_TASK": "Нет следующей задачи",
    "OVERDUE_TASK": "Просрочена задача",
    "NO_FIRST_CALL": "Нет подтверждённого первого звонка",
    "INACTIVE_ENTITY": "Нет активности",
    "STAGE_AGE": "Сверх норматива на стадии",
    "REQUIRED_FIELD": "Не заполнены обязательные поля",
}


def _count_stage(records: list[SourceRecord], stages: set[str]) -> int:
    return sum(record.stage_id in stages for record in records)


def _risk(violation_count: int, overdue_count: int, inactive_72_count: int) -> str:
    score = violation_count + overdue_count * 2 + inactive_72_count * 3
    if score >= 8:
        return "high"
    if score >= 3:
        return "medium"
    return "low"


def build_dashboard_data(
    records: list[SourceRecord],
    violations: list[Violation],
    *,
    generated_at: str | None = None,
    mode: str = "demo",
    limitations: list[str] | None = None,
    period_start: datetime | None = None,
) -> dict[str, Any]:
    active_records = [record for record in records if not record.is_closed]
    actual = [item for item in violations if item.status == "VIOLATION"]
    violation_counts = Counter(item.rule_id for item in actual)
    by_broker_records: defaultdict[str, list[SourceRecord]] = defaultdict(list)
    by_broker_violations: defaultdict[str, list[Violation]] = defaultdict(list)
    for record in records:
        by_broker_records[record.assigned_to_id or "UNASSIGNED"].append(record)
    for violation in actual:
        by_broker_violations[violation.assigned_to_id or "UNASSIGNED"].append(violation)

    broker_rows: list[dict[str, Any]] = []
    for broker_id, broker_records in sorted(by_broker_records.items()):
        broker_findings = by_broker_violations[broker_id]
        broker_counts = Counter(item.rule_id for item in broker_findings)
        violated_entities = {
            (item.entity_type, item.source_id) for item in broker_findings
        }
        active_broker_records = [item for item in broker_records if not item.is_closed]
        clean_count = sum(
            (item.entity_type, item.source_id) not in violated_entities
            for item in active_broker_records
        )
        inactive_72 = sum(
            item.rule_id == "INACTIVE_ENTITY"
            and int(item.evidence.get("escalation_hours", 0)) >= 72
            for item in broker_findings
        )
        broker_rows.append(
            {
                "broker_id": broker_id,
                "department_id": next(
                    (item.department_id for item in broker_records if item.department_id), None
                ),
                "load": len(active_broker_records),
                "violations": len(broker_findings),
                "overdue": broker_counts["OVERDUE_TASK"],
                "without_next_task": broker_counts["NO_NEXT_TASK"],
                "showings": _count_stage(broker_records, SHOWING_SCHEDULED | SHOWING_COMPLETED),
                "bookings": _count_stage(broker_records, BOOKING),
                "won": sum(item.is_won for item in broker_records),
                "crm_discipline_pct": round(
                    clean_count / len(active_broker_records) * 100, 1
                )
                if active_broker_records
                else 100.0,
                "risk": _risk(len(broker_findings), broker_counts["OVERDUE_TASK"], inactive_72),
            }
        )

    stage_counts = Counter(record.stage_id or "UNKNOWN" for record in records)
    stage_rows = [
        {"stage_id": stage, "count": count}
        for stage, count in stage_counts.most_common()
    ]
    control_rows = [
        {
            "priority": _priority(item),
            "rule_id": item.rule_id,
            "reason": RULE_LABELS.get(item.rule_id, item.rule_id),
            "entity_type": item.entity_type,
            "source_id": item.source_id,
            "broker_id": item.assigned_to_id,
            "department_id": item.department_id,
            "card_url": item.card_url,
            "recommended_action": _recommended_action(item),
            "reaction_due": _reaction_due(item),
        }
        for item in sorted(actual, key=_priority, reverse=True)
    ]
    summary = {
        "new_leads": sum(
            record.entity_type == "lead"
            and (
                period_start is None
                or (record.created_at or datetime.min.replace(tzinfo=UTC)) >= period_start
            )
            for record in records
        ),
        "unaccepted_leads": violation_counts["UNACCEPTED_LEAD"],
        "without_first_call": violation_counts["NO_FIRST_CALL"],
        "without_next_task": violation_counts["NO_NEXT_TASK"],
        "overdue_tasks": violation_counts["OVERDUE_TASK"],
        "inactive_24": _inactive_count(actual, 24),
        "inactive_48": _inactive_count(actual, 48),
        "inactive_72": _inactive_count(actual, 72),
        "stuck_deals": sum(
            item.rule_id == "STAGE_AGE" and item.entity_type == "deal" for item in actual
        ),
        "showings_scheduled": _count_stage(records, SHOWING_SCHEDULED),
        "showings_completed": _count_stage(records, SHOWING_COMPLETED),
        "bookings": _count_stage(records, BOOKING),
        "registrations": _count_stage(records, REGISTRATION),
        "client_paid": _count_stage(records, CLIENT_PAID),
        "commission_invoiced": _count_stage(records, COMMISSION_INVOICED),
        "commission_received": _count_stage(records, COMMISSION_RECEIVED),
        "lost": _count_stage(records, LOST),
        "active_records": len(active_records),
        "violations": len(actual),
    }
    return {
        "generated_at": generated_at or datetime.now(UTC).isoformat(),
        "mode": mode,
        "contains_personal_data": False,
        "summary": summary,
        "brokers": broker_rows,
        "stages": stage_rows,
        "control": control_rows,
        "conversion": {
            "status": "BLOCKED_BY_DATA",
            "reason": "История переходов стадий недоступна текущему webhook",
        },
        "loss_reasons": {
            "status": "BLOCKED_BY_DATA",
            "reason": "Единое поле причины потери не подтверждено",
        },
        "plan_fact": {
            "status": "BLOCKED_BY_DATA",
            "reason": "Источник плана продаж не подключён",
        },
        "forecast": {
            "status": "BLOCKED_BY_DATA",
            "reason": "Нет истории стадий и подтверждённых сумм комиссии",
        },
        "recommendations": _recommendations(violation_counts),
        "limitations": limitations or [],
    }


def _recommendations(counts: Counter[str]) -> list[str]:
    ranked = [
        (counts[rule_id], RULE_LABELS[rule_id])
        for rule_id in RULE_LABELS
        if counts[rule_id]
    ]
    return [
        f"Приоритет: {label.lower()} — {count}"
        for count, label in sorted(ranked, reverse=True)[:5]
    ]


def _inactive_count(violations: list[Violation], hours: int) -> int:
    return sum(
        item.rule_id == "INACTIVE_ENTITY"
        and int(item.evidence.get("escalation_hours", 0)) >= hours
        for item in violations
    )


def _priority(item: Violation) -> int:
    if item.rule_id == "INACTIVE_ENTITY":
        return int(item.evidence.get("escalation_hours", 24))
    return {
        "UNACCEPTED_LEAD": 90,
        "OVERDUE_TASK": 80,
        "NO_FIRST_CALL": 70,
        "NO_NEXT_TASK": 60,
        "STAGE_AGE": 50,
        "REQUIRED_FIELD": 40,
    }.get(item.rule_id, 10)


def _recommended_action(item: Violation) -> str:
    return {
        "UNACCEPTED_LEAD": "Связаться с брокером и принять лид",
        "NO_FIRST_CALL": "Проверить первый контакт",
        "NO_NEXT_TASK": "Назначить следующий шаг",
        "OVERDUE_TASK": "Закрыть или перенести задачу с причиной",
        "INACTIVE_ENTITY": "Проверить карточку и восстановить контакт",
        "STAGE_AGE": "Проверить соответствие стадии фактической работе",
        "REQUIRED_FIELD": "Заполнить обязательные поля",
    }.get(item.rule_id, "Проверить карточку")


def _reaction_due(item: Violation) -> str:
    if item.rule_id in {"UNACCEPTED_LEAD", "OVERDUE_TASK"}:
        return "сейчас"
    if item.rule_id == "INACTIVE_ENTITY" and int(
        item.evidence.get("escalation_hours", 0)
    ) >= 72:
        return "сейчас"
    return "сегодня"
