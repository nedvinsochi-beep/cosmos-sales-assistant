from __future__ import annotations

import hashlib
from collections import Counter, defaultdict
from datetime import datetime

from cosmos_control_tower.acceptance.engine import evaluate_acceptance
from cosmos_control_tower.acceptance.models import AcceptanceRule, OrganizationMap
from cosmos_control_tower.models.records import SourceRecord
from cosmos_control_tower.rules_engine.models import (
    RuleDefinition,
    RulePreview,
    RuleRunResult,
)


def missed_lead_acceptance(
    rule: RuleDefinition,
    records: list[SourceRecord],
    department_heads: dict[str, str],
    organization: OrganizationMap,
    as_of: datetime,
    processed_keys: set[str],
) -> RuleRunResult:
    started = datetime.now(as_of.tzinfo)
    acceptance = evaluate_acceptance(
        records,
        department_heads,
        organization,
        AcceptanceRule(
            rule_id=rule.rule_id,
            source_stage_id=str(rule.conditions[0].get("value", "NEW")),
            target_stage_id=str(rule.violation.get("accepted_stage_id", "IN_PROCESS")),
            check_time=str(rule.deadline.get("time", "23:50")),
            timezone=rule.timezone,
        ),
        as_of=as_of,
        processed_keys=processed_keys,
    )
    previews = [
        RulePreview(
            idempotency_key=item.idempotency_key,
            entity_type="lead",
            entity_id=item.lead_id,
            card_url=item.card_url,
            employee_id=item.original_assigned_user_id,
            rop_user_id=item.rop_user_id,
            reason="Лид остался в стадии раздачи к 23:50",
            proposed_actions=[
                {"type": "assign_to_rop", "user_id": item.rop_user_id},
                {
                    "type": "add_observer",
                    "user_id": item.original_assigned_user_id,
                },
                {"type": "add_observer", "user_id": item.poteryashka_user_id},
                {"type": "add_comment", "text": item.proposed_comment},
                {
                    "type": "record_violation",
                    "flags": item.proposed_updates["SERVICE_FLAGS_ADD"],
                },
            ],
        )
        for item in acceptance.actions
    ]
    return RuleRunResult(
        run_id=_run_id(rule.rule_id, as_of),
        rule_id=rule.rule_id,
        name=rule.name,
        mode=rule.mode,
        status="COMPLETED_DRY_RUN",
        started_at=started,
        completed_at=datetime.now(as_of.tzinfo),
        records_evaluated=acceptance.records_evaluated,
        violations_found=len(previews),
        blocked_by_data=len(acceptance.blocked_candidates),
        planned_actions=sum(len(item.proposed_actions) for item in previews),
        previews=previews,
        exclusions=acceptance.exclusions,
        kpi={
            "created_today_assigned_proxy": acceptance.created_today_assigned_proxy,
            "created_today_moved_from_new_proxy": acceptance.created_today_moved_from_new_proxy,
            "returned_by_robot": 0,
        },
        limitations=acceptance.limitations,
    )


def no_next_step(
    rule: RuleDefinition,
    records: list[SourceRecord],
    department_heads: dict[str, str],
    organization: OrganizationMap,
    as_of: datetime,
    processed_keys: set[str],
) -> RuleRunResult:
    started = datetime.now(as_of.tzinfo)
    excluded_users = (
        organization.owner_user_ids
        | organization.service_user_ids
        | organization.technical_user_ids
        | organization.test_user_ids
        | set(department_heads.values())
    )
    exclusions: Counter[str] = Counter()
    previews: list[RulePreview] = []
    active_by_broker: Counter[str] = Counter()
    next_step_by_broker: Counter[str] = Counter()
    missing_by_broker: Counter[str] = Counter()
    blocked_by_broker: Counter[str] = Counter()
    operational_stage_ids = {str(item) for item in rule.scope.get("stage_ids", [])}
    waiting_stage_ids = {str(item) for item in rule.exclusions[0].get("stage_ids", [])}
    for record in records:
        if record.entity_type not in set(rule.scope.get("entity_types", ["lead", "deal"])):
            continue
        if record.is_closed:
            exclusions["closed_or_archive"] += 1
            continue
        if record.stage_id in waiting_stage_ids:
            exclusions["approved_waiting_or_warm"] += 1
            continue
        if operational_stage_ids and record.stage_id not in operational_stage_ids:
            exclusions["outside_approved_operational_stages"] += 1
            continue
        employee = record.assigned_to_id
        if not employee:
            exclusions["unassigned_pool"] += 1
            continue
        if record.assignee_active is not True:
            exclusions["inactive_or_unknown_employee"] += 1
            continue
        if employee in excluded_users:
            exclusions["owner_rop_service_technical_or_test"] += 1
            continue
        rop = department_heads.get(record.department_id or "")
        if not rop:
            exclusions["rop_not_mapped"] += 1
            continue
        active_by_broker[employee] += 1
        has_future_activity = bool(
            record.has_open_activity
            and record.next_activity_at
            and record.next_activity_at > as_of
        )
        if has_future_activity:
            next_step_by_broker[employee] += 1
            continue
        evidence = "CONFIRMED" if record.task_data_complete else "BLOCKED_BY_DATA"
        key = _key(rule.rule_id, record, as_of)
        if key in processed_keys:
            exclusions["already_processed_in_window"] += 1
            continue
        if evidence == "CONFIRMED":
            missing_by_broker[employee] += 1
        else:
            blocked_by_broker[employee] += 1
        previews.append(
            RulePreview(
                idempotency_key=key,
                entity_type=record.entity_type,
                entity_id=record.source_id,
                card_url=record.card_url,
                employee_id=employee,
                department_id=record.department_id,
                rop_user_id=rop,
                reason="Нет подтверждённого будущего действия с датой и ответственным",
                evidence_status=evidence,
                proposed_actions=[
                    {"level": 1, "action": "preview_broker_notification"},
                    {"level": 2, "action": "preview_rop_escalation_after_deadline"},
                    {"level": 3, "action": "include_in_rop_kpi_if_repeated"},
                ],
            )
        )
    confirmed = [item for item in previews if item.evidence_status == "CONFIRMED"]
    blocked = [item for item in previews if item.evidence_status == "BLOCKED_BY_DATA"]
    broker_kpi = []
    for employee in sorted(active_by_broker):
        active = active_by_broker[employee]
        missing = missing_by_broker[employee]
        broker_kpi.append(
            {
                "employee_id": employee,
                "active_cards": active,
                "with_next_step": next_step_by_broker[employee],
                "without_next_step": missing,
                "without_next_step_pct": round(missing / active * 100, 1) if active else 0,
                "blocked_candidates": blocked_by_broker[employee],
                "average_resolution_time": None,
                "repeat_violations": None,
                "week": None,
                "month": None,
            }
        )
    return RuleRunResult(
        run_id=_run_id(rule.rule_id, as_of),
        rule_id=rule.rule_id,
        name=rule.name,
        mode=rule.mode,
        status="COMPLETED_DRY_RUN",
        started_at=started,
        completed_at=datetime.now(as_of.tzinfo),
        records_evaluated=len(records),
        violations_found=len(confirmed),
        blocked_by_data=len(blocked),
        planned_actions=len(confirmed) * 3,
        previews=previews,
        exclusions=dict(exclusions),
        kpi={
            "brokers": broker_kpi,
            "department_violations": _department_counts(confirmed),
            "resolved": None,
            "overdue": None,
            "average_reaction_time": None,
            "trend": None,
        },
        limitations=[
            "CRM activities are checked from the structural snapshot",
            "Linked Bitrix tasks are not proven by the current snapshot",
            "Blocked candidates are not counted as confirmed violations",
            "Resolution time and trends require a persisted multi-run ledger",
        ],
    )


def _key(rule_id: str, record: SourceRecord, as_of: datetime) -> str:
    window = as_of.date().isoformat()
    value = f"{rule_id}|{record.entity_type}|{record.source_id}|{window}"
    return hashlib.sha256(value.encode()).hexdigest()


def _run_id(rule_id: str, as_of: datetime) -> str:
    return hashlib.sha256(f"{rule_id}|{as_of.isoformat()}".encode()).hexdigest()[:16]


def _department_counts(previews: list[RulePreview]) -> dict[str, int]:
    counts: defaultdict[str, int] = defaultdict(int)
    for item in previews:
        counts[item.department_id or "UNMAPPED"] += 1
    return dict(counts)
