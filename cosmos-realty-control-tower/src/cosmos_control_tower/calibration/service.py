from __future__ import annotations

import hashlib
from collections import Counter
from collections.abc import Callable
from datetime import UTC, datetime, timedelta
from typing import Any

from pydantic import BaseModel, Field

from cosmos_control_tower.models.records import CalibratedRecord, SourceRecord, Violation


class CalibrationRules(BaseModel):
    rule_status: str = "PROPOSED_REQUIRES_APPROVAL"
    operational_recent_days: int = Field(default=7, gt=0)
    warm_future_days: int = Field(default=7, gt=0)
    warm_stage_ids: set[str] = Field(default_factory=lambda: {"PROCESSED", "2", "UC_ZL59WW"})
    excluded_stage_ids: set[str] = Field(default_factory=lambda: {"UC_OWVT1B"})
    technical_category_ids: set[str] = Field(default_factory=lambda: {"10", "12"})


def classify_records(
    records: list[SourceRecord],
    rules: CalibrationRules,
    *,
    now: datetime | None = None,
) -> list[CalibratedRecord]:
    now = now or datetime.now(UTC)
    return [_classify(record, rules, now) for record in records]


def _classify(
    record: SourceRecord, rules: CalibrationRules, now: datetime
) -> CalibratedRecord:
    if record.is_closed:
        return _result(record, "archive", "closed_record", rules)
    if record.assignee_active is False:
        return _result(record, "archive", "inactive_employee", rules)
    if record.assignee_active is None:
        return _result(record, "archive", "employee_status_unknown", rules)
    if record.category_id in rules.technical_category_ids:
        return _result(record, "archive", "technical_or_training_pipeline", rules)
    if record.stage_id in rules.excluded_stage_ids:
        return _result(record, "archive", "non_client_or_excluded_status", rules)
    if record.stage_id in rules.warm_stage_ids:
        return _result(record, "warm", "warm_or_deferred_stage", rules)
    if record.next_activity_at and record.next_activity_at > now + timedelta(
        days=rules.warm_future_days
    ):
        return _result(record, "warm", "future_contact_beyond_operational_window", rules)

    recent_after = now - timedelta(days=rules.operational_recent_days)
    if any(
        value is not None and value >= recent_after
        for value in (record.created_at, record.last_activity_at, record.next_activity_at)
    ):
        return _result(record, "operational", "recent_or_scheduled_work", rules)
    return _result(record, "archive", "historical_without_recent_work_candidate", rules)


def _result(
    record: SourceRecord, scope: str, reason: str, rules: CalibrationRules
) -> CalibratedRecord:
    return CalibratedRecord(
        record=record,
        work_scope=scope,
        reason_code=reason,
        rule_status=rules.rule_status,
    )


def calibration_summary(
    calibrated: list[CalibratedRecord], violations: list[Violation]
) -> dict[str, Any]:
    by_scope = Counter(item.work_scope for item in calibrated)
    by_reason = Counter(item.reason_code for item in calibrated)
    scope_by_key = {
        (item.record.entity_type, item.record.source_id): item.work_scope
        for item in calibrated
    }
    actual = [item for item in violations if item.status == "VIOLATION"]
    operational = [
        item
        for item in actual
        if scope_by_key.get((item.entity_type, item.source_id)) == "operational"
    ]
    unique_original = {(item.entity_type, item.source_id) for item in actual}
    unique_operational = {(item.entity_type, item.source_id) for item in operational}
    records = [item.record for item in calibrated]
    return {
        "total_records": len(calibrated),
        "scope_counts": dict(sorted(by_scope.items())),
        "reason_counts": dict(by_reason.most_common()),
        "original_violation_events": len(actual),
        "original_violating_cards": len(unique_original),
        "operational_violation_events": len(operational),
        "operational_violating_cards": len(unique_operational),
        "excluded_violation_events": len(actual) - len(operational),
        "rule_counts_original": dict(Counter(item.rule_id for item in actual)),
        "rule_counts_operational": dict(Counter(item.rule_id for item in operational)),
        "distributions": {
            "entity_type": _count(records, lambda item: item.entity_type),
            "category_id": _count(records, lambda item: item.category_id or "NO_CATEGORY"),
            "stage_id": _count(records, lambda item: item.stage_id or "NO_STAGE"),
            "department_id": _count(
                records, lambda item: item.department_id or "NO_DEPARTMENT"
            ),
            "assignee_status": _count(
                records,
                lambda item: "active"
                if item.assignee_active is True
                else "inactive"
                if item.assignee_active is False
                else "unknown",
            ),
            "created_age": _count(records, lambda item: _age_bucket(item.created_at)),
            "last_activity_age": _count(
                records, lambda item: _age_bucket(item.last_activity_at)
            ),
            "source": _count(
                records, lambda item: item.source_channel_id or "NO_SOURCE"
            ),
            "closed_state": _count(
                records, lambda item: "closed" if item.is_closed else "open"
            ),
            "next_activity": _count(
                records,
                lambda item: "has_open_activity"
                if item.has_open_activity
                else "no_open_activity",
            ),
        },
    }


def anonymized_examples(
    calibrated: list[CalibratedRecord],
    violations: list[Violation],
    *,
    per_rule: int = 20,
) -> dict[str, list[dict[str, Any]]]:
    classification = {
        (item.record.entity_type, item.record.source_id): item for item in calibrated
    }
    result: dict[str, list[dict[str, Any]]] = {}
    for rule_id in ("UNACCEPTED_LEAD", "NO_NEXT_TASK", "INACTIVE_ENTITY"):
        candidates: list[dict[str, Any]] = []
        for violation in violations:
            if violation.rule_id != rule_id or violation.status != "VIOLATION":
                continue
            calibrated_item = classification.get((violation.entity_type, violation.source_id))
            if not calibrated_item:
                continue
            record = calibrated_item.record
            candidates.append(
                {
                    "anonymous_id": _anonymous_id(record),
                    "entity_type": record.entity_type,
                    "category_id": record.category_id,
                    "stage_id": record.stage_id,
                    "department_id": record.department_id,
                    "assignee_active": record.assignee_active,
                    "created_month": record.created_at.strftime("%Y-%m")
                    if record.created_at
                    else None,
                    "last_activity_month": record.last_activity_at.strftime("%Y-%m")
                    if record.last_activity_at
                    else None,
                    "has_open_activity": record.has_open_activity,
                    "work_scope": calibrated_item.work_scope,
                    "classification_reason": calibrated_item.reason_code,
                    "trigger_evidence": violation.evidence,
                    "trigger_explanation": _trigger_explanation(rule_id),
                }
            )
        result[rule_id] = _diverse_sample(candidates, per_rule)
    return result


def _anonymous_id(record: SourceRecord) -> str:
    raw = f"{record.entity_type}:{record.source_id}".encode()
    return hashlib.sha256(raw).hexdigest()[:12]


def _count(
    records: list[SourceRecord], key: Callable[[SourceRecord], object]
) -> dict[str, int]:
    return dict(Counter(str(key(item)) for item in records).most_common())


def _age_bucket(value: datetime | None) -> str:
    if value is None:
        return "missing"
    days = (datetime.now(UTC) - value).days
    if days <= 7:
        return "0-7d"
    if days <= 30:
        return "8-30d"
    if days <= 90:
        return "31-90d"
    if days <= 180:
        return "91-180d"
    return "180d+"


def _diverse_sample(candidates: list[dict[str, Any]], limit: int) -> list[dict[str, Any]]:
    selected: list[dict[str, Any]] = []
    seen: set[tuple[Any, ...]] = set()
    for item in candidates:
        key = (
            item["category_id"],
            item["stage_id"],
            item["department_id"],
            item["work_scope"],
        )
        if key not in seen:
            selected.append(item)
            seen.add(key)
        if len(selected) >= limit:
            return selected
    for item in candidates:
        if item not in selected:
            selected.append(item)
        if len(selected) >= limit:
            break
    return selected


def _trigger_explanation(rule_id: str) -> str:
    return {
        "UNACCEPTED_LEAD": "Статус NEW, норматив принятия истёк, активности нет",
        "NO_NEXT_TASK": "Не найдена открытая CRM-активность",
        "INACTIVE_ENTITY": "Последняя коммуникационная активность старше порога",
    }[rule_id]
