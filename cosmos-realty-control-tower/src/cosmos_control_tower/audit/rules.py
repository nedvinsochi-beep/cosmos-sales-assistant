from datetime import UTC, datetime, timedelta
from typing import Any

from pydantic import BaseModel, Field

from cosmos_control_tower.models.records import SourceRecord, Violation


class AuditRules(BaseModel):
    inactive_hours: int = Field(default=24, gt=0)
    stage_age_limits_hours: dict[str, int] = Field(default_factory=dict)
    required_fields_by_stage: dict[str, list[str]] = Field(default_factory=dict)
    first_call_activity_types: list[str] = Field(default_factory=list)
    lead_entity_types: list[str] = Field(default_factory=lambda: ["lead", "deal"])


def _violation(
    rule_id: str, record: SourceRecord, status: str, evidence: dict[str, Any]
) -> Violation:
    return Violation(
        rule_id=rule_id,
        status=status,
        entity_type=record.entity_type,
        source_id=record.source_id,
        assigned_to_id=record.assigned_to_id,
        department_id=record.department_id,
        evidence=evidence,
    )


def evaluate_record(
    record: SourceRecord,
    rules: AuditRules,
    *,
    now: datetime | None = None,
) -> list[Violation]:
    now = now or datetime.now(UTC)
    findings: list[Violation] = []

    if record.has_open_activity is False:
        findings.append(_violation("NO_NEXT_TASK", record, "VIOLATION", {}))
    elif record.has_open_activity is None:
        findings.append(_violation("NO_NEXT_TASK", record, "BLOCKED_BY_DATA", {}))

    if record.next_activity_at and record.next_activity_at < now:
        findings.append(
            _violation(
                "OVERDUE_TASK",
                record,
                "VIOLATION",
                {"overdue_since": record.next_activity_at.isoformat()},
            )
        )
    elif record.next_activity_at is None:
        findings.append(_violation("OVERDUE_TASK", record, "BLOCKED_BY_DATA", {}))

    if record.has_first_call is False:
        findings.append(_violation("NO_FIRST_CALL", record, "VIOLATION", {}))
    elif record.has_first_call is None:
        findings.append(_violation("NO_FIRST_CALL", record, "BLOCKED_BY_DATA", {}))

    if record.updated_at and now - record.updated_at > timedelta(hours=rules.inactive_hours):
        findings.append(
            _violation(
                "INACTIVE_ENTITY",
                record,
                "VIOLATION",
                {"inactive_hours_limit": rules.inactive_hours},
            )
        )
    elif record.updated_at is None:
        findings.append(_violation("INACTIVE_ENTITY", record, "BLOCKED_BY_DATA", {}))

    if record.stage_id and record.stage_changed_at:
        limit = rules.stage_age_limits_hours.get(record.stage_id)
        if limit is None:
            findings.append(_violation("STAGE_AGE", record, "BLOCKED_BY_DATA", {}))
        elif now - record.stage_changed_at > timedelta(hours=limit):
            findings.append(
                _violation("STAGE_AGE", record, "VIOLATION", {"stage_age_limit_hours": limit})
            )
    else:
        findings.append(_violation("STAGE_AGE", record, "BLOCKED_BY_DATA", {}))

    required = rules.required_fields_by_stage.get(record.stage_id or "")
    if required is None:
        findings.append(_violation("REQUIRED_FIELD", record, "BLOCKED_BY_DATA", {}))
    else:
        missing = [name for name in required if not record.required_fields.get(name)]
        if missing:
            findings.append(
                _violation("REQUIRED_FIELD", record, "VIOLATION", {"missing_fields": missing})
            )
    return findings
