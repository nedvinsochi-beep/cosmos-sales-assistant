from datetime import UTC, datetime, timedelta

from cosmos_control_tower.calibration.service import (
    CalibrationRules,
    anonymized_examples,
    calibration_summary,
    classify_records,
)
from cosmos_control_tower.models.records import SourceRecord, Violation


def test_calibration_separates_work_without_claiming_approval() -> None:
    now = datetime(2026, 8, 1, tzinfo=UTC)
    records = [
        SourceRecord(
            entity_type="lead",
            source_id="1",
            stage_id="NEW",
            assignee_active=True,
            created_at=now - timedelta(days=1),
        ),
        SourceRecord(
            entity_type="lead",
            source_id="2",
            stage_id="PROCESSED",
            assignee_active=True,
            created_at=now - timedelta(days=20),
        ),
        SourceRecord(
            entity_type="lead",
            source_id="3",
            stage_id="NEW",
            assignee_active=False,
            created_at=now - timedelta(days=1),
        ),
        SourceRecord(
            entity_type="lead",
            source_id="4",
            stage_id="NEW",
            assignee_active=True,
            created_at=now - timedelta(days=200),
        ),
    ]
    calibrated = classify_records(records, CalibrationRules(), now=now)
    assert [item.work_scope for item in calibrated] == [
        "operational",
        "warm",
        "archive",
        "archive",
    ]
    assert all(item.rule_status == "PROPOSED_REQUIRES_APPROVAL" for item in calibrated)


def test_calibration_counts_and_examples_are_anonymized() -> None:
    record = SourceRecord(
        entity_type="lead",
        source_id="real-id-must-not-leak",
        stage_id="NEW",
        assignee_active=True,
        created_at=datetime.now(UTC),
    )
    violation = Violation(
        rule_id="UNACCEPTED_LEAD",
        status="VIOLATION",
        entity_type="lead",
        source_id=record.source_id,
    )
    calibrated = classify_records([record], CalibrationRules())
    summary = calibration_summary(calibrated, [violation])
    examples = anonymized_examples(calibrated, [violation])
    assert summary["operational_violating_cards"] == 1
    assert examples["UNACCEPTED_LEAD"][0]["anonymous_id"] != record.source_id
    assert record.source_id not in str(examples)
