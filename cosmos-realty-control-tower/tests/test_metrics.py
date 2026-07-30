from cosmos_control_tower.metrics.basic import broker_metrics, department_metrics
from cosmos_control_tower.models.records import SourceRecord, Violation


def test_basic_metrics_group_by_non_personal_ids() -> None:
    records = [
        SourceRecord(entity_type="lead", source_id="1", assigned_to_id="10", department_id="20"),
        SourceRecord(entity_type="lead", source_id="2", assigned_to_id="10", department_id="20"),
    ]
    violations = [
        Violation(
            rule_id="NO_NEXT_TASK",
            status="VIOLATION",
            entity_type="lead",
            source_id="1",
            assigned_to_id="10",
        )
    ]
    assert broker_metrics(records, violations) == [
        {"broker_id": "10", "entity_count": 2, "violation_count": 1}
    ]
    assert department_metrics(records) == [{"department_id": "20", "entity_count": 2}]
