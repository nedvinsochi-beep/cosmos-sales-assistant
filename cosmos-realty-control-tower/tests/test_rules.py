from datetime import UTC, datetime, timedelta

from cosmos_control_tower.audit.rules import AuditRules, evaluate_record
from cosmos_control_tower.models.records import SourceRecord


def test_rules_report_violations_and_blocked_data() -> None:
    now = datetime(2026, 1, 2, tzinfo=UTC)
    record = SourceRecord(
        entity_type="lead",
        source_id="demo",
        stage_id="unknown-stage",
        updated_at=now - timedelta(hours=25),
        next_activity_at=now - timedelta(minutes=1),
        has_open_activity=False,
        has_first_call=False,
    )
    findings = evaluate_record(record, AuditRules(inactive_hours=24), now=now)
    statuses = {(item.rule_id, item.status) for item in findings}
    assert ("NO_NEXT_TASK", "VIOLATION") in statuses
    assert ("OVERDUE_TASK", "VIOLATION") in statuses
    assert ("NO_FIRST_CALL", "VIOLATION") in statuses
    assert ("INACTIVE_ENTITY", "VIOLATION") in statuses
    assert ("STAGE_AGE", "BLOCKED_BY_DATA") in statuses
    assert ("REQUIRED_FIELD", "BLOCKED_BY_DATA") in statuses


def test_required_fields_use_configured_names_only() -> None:
    now = datetime(2026, 1, 2, tzinfo=UTC)
    rules = AuditRules(required_fields_by_stage={"known-stage": ["configured_field"]})
    record = SourceRecord(
        entity_type="deal",
        source_id="demo",
        stage_id="known-stage",
        required_fields={"configured_field": ""},
    )
    findings = evaluate_record(record, rules, now=now)
    finding = next(item for item in findings if item.rule_id == "REQUIRED_FIELD")
    assert finding.status == "VIOLATION"
    assert finding.evidence["missing_fields"] == ["configured_field"]
