from __future__ import annotations

import hashlib
from collections import Counter
from datetime import datetime
from zoneinfo import ZoneInfo

from cosmos_control_tower.acceptance.models import (
    AcceptanceAction,
    AcceptanceReport,
    AcceptanceRule,
    BlockedCandidate,
    OrganizationMap,
)
from cosmos_control_tower.models.records import SourceRecord


def evaluate_acceptance(
    records: list[SourceRecord],
    department_heads: dict[str, str],
    organization: OrganizationMap,
    rule: AcceptanceRule,
    *,
    as_of: datetime,
    processed_keys: set[str] | None = None,
) -> AcceptanceReport:
    zone = ZoneInfo(rule.timezone)
    local_as_of = as_of.astimezone(zone)
    processed_keys = processed_keys or set()
    run_id = hashlib.sha256(local_as_of.isoformat().encode()).hexdigest()[:16]
    rop_ids = set(department_heads.values())
    excluded_ids = (
        organization.owner_user_ids
        | organization.service_user_ids
        | organization.technical_user_ids
        | organization.test_user_ids
        | rop_ids
    )
    exclusions: Counter[str] = Counter()
    blocked: list[BlockedCandidate] = []
    actions: list[AcceptanceAction] = []
    created_today_assigned = 0
    created_today_moved = 0

    for record in records:
        if record.entity_type != "lead":
            continue
        assigned_id = record.assigned_to_id
        created_today = bool(
            record.created_at and record.created_at.astimezone(zone).date() == local_as_of.date()
        )
        if created_today and assigned_id:
            created_today_assigned += 1
            if record.stage_id != rule.source_stage_id:
                created_today_moved += 1
        if record.stage_id != rule.source_stage_id:
            exclusions["not_in_distribution_stage"] += 1
            continue
        if record.is_closed:
            exclusions["closed"] += 1
            continue
        if not assigned_id:
            exclusions["unassigned_pool"] += 1
            continue
        if record.assignee_active is not True:
            exclusions["inactive_or_unknown_employee"] += 1
            continue
        if assigned_id in excluded_ids:
            exclusions["owner_rop_service_technical_or_test"] += 1
            continue
        rop_id = department_heads.get(record.department_id or "")
        if not rop_id:
            exclusions["rop_not_mapped"] += 1
            continue
        if record.assigned_at is None:
            blocked.append(
                BlockedCandidate(
                    lead_id=record.source_id,
                    card_url=record.card_url,
                    assigned_user_id=assigned_id,
                    department_id=record.department_id,
                    rop_user_id=rop_id,
                    reason="assignment_timestamp_unavailable",
                    created_at=record.created_at,
                )
            )
            continue
        if record.assigned_at.astimezone(zone).date() != local_as_of.date():
            exclusions["assigned_on_another_day"] += 1
            continue
        key = _idempotency_key(rule.rule_id, record.source_id, assigned_id, record.assigned_at)
        if key in processed_keys:
            exclusions["already_processed"] += 1
            continue
        if not organization.poteryashka_user_id:
            blocked.append(
                BlockedCandidate(
                    lead_id=record.source_id,
                    card_url=record.card_url,
                    assigned_user_id=assigned_id,
                    department_id=record.department_id,
                    rop_user_id=rop_id,
                    reason="poteryashka_user_id_not_configured",
                    created_at=record.created_at,
                )
            )
            continue
        actions.append(
            _action(
                record,
                assigned_id,
                rop_id,
                organization.poteryashka_user_id,
                rule,
                local_as_of,
                run_id,
                key,
            )
        )

    return AcceptanceReport(
        generated_at=datetime.now(zone),
        as_of=local_as_of,
        timezone=rule.timezone,
        records_evaluated=len(records),
        exact_assigned_today=None,
        exact_accepted_today=None,
        created_today_assigned_proxy=created_today_assigned,
        created_today_moved_from_new_proxy=created_today_moved,
        eligible_to_return=len(actions),
        blocked_candidates=blocked,
        actions=actions,
        exclusions=dict(exclusions),
        by_broker=_group(actions, blocked, "broker"),
        by_rop=_group(actions, blocked, "rop"),
        limitations=[
            "ASSIGNED_BY_ID change timestamp is not exposed by the audited fields",
            "DATE_CREATE, DATE_MODIFY and MOVED_TIME are not assignment timestamps",
            "Exact assigned/accepted-today KPI is blocked until assigned_at is recorded",
            "Service, technical and test user IDs require explicit organization-map approval",
        ],
    )


def _idempotency_key(rule_id: str, lead_id: str, assignee: str, assigned_at: datetime) -> str:
    raw = f"{rule_id}|{lead_id}|{assignee}|{assigned_at.isoformat()}".encode()
    return hashlib.sha256(raw).hexdigest()


def _action(
    record: SourceRecord,
    assigned_id: str,
    rop_id: str,
    poteryashka_id: str,
    rule: AcceptanceRule,
    as_of: datetime,
    run_id: str,
    key: str,
) -> AcceptanceAction:
    assigned_at = record.assigned_at
    assert assigned_at is not None
    comment = (
        "Автоматический контроль принятия лида.\n\n"
        f"Лид был назначен сотруднику: {assigned_id}\n\n"
        f"Дата и время назначения: {assigned_at.isoformat()}\n\n"
        "До 23:50 текущего дня лид не был переведён в стадию "
        "«Взял / касание».\n\n"
        f"Лид автоматически передан руководителю отдела: {rop_id}\n\n"
        "Прежний ответственный добавлен наблюдателем.\n"
        "Технический наблюдатель «Потеряшка» добавлен в карточку.\n\n"
        "Нарушение зафиксировано системой контроля."
    )
    return AcceptanceAction(
        idempotency_key=key,
        lead_id=record.source_id,
        card_url=record.card_url,
        original_assigned_user_id=assigned_id,
        assigned_at=assigned_at,
        violation_date=as_of.date().isoformat(),
        violation_detected_at=as_of,
        rop_user_id=rop_id,
        poteryashka_user_id=poteryashka_id,
        robot_rule_id=rule.rule_id,
        robot_run_id=run_id,
        source_stage_id=rule.source_stage_id,
        target_stage_id=rule.target_stage_id,
        proposed_updates={
            "ASSIGNED_BY_ID": rop_id,
            "OBSERVER_IDS_ADD": [assigned_id, poteryashka_id],
            "SERVICE_FLAGS_ADD": ["MISSED_ACCEPTANCE_SLA", "AUTO_RETURNED_TO_ROP"],
        },
        proposed_comment=comment,
    )


def _group(
    actions: list[AcceptanceAction], blocked: list[BlockedCandidate], dimension: str
) -> list[dict[str, object]]:
    action_counts: Counter[str] = Counter()
    blocked_counts: Counter[str] = Counter()
    for item in actions:
        key = item.original_assigned_user_id if dimension == "broker" else item.rop_user_id
        action_counts[key] += 1
    for blocked_item in blocked:
        blocked_key = (
            blocked_item.assigned_user_id if dimension == "broker" else blocked_item.rop_user_id
        )
        blocked_counts[blocked_key or "UNMAPPED"] += 1
    return [
        {"user_id": key, "eligible": action_counts[key], "blocked": blocked_counts[key]}
        for key in sorted(set(action_counts) | set(blocked_counts))
    ]
