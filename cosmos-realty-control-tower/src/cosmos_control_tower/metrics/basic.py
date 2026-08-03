from collections import Counter
from collections.abc import Iterable
from typing import Any

from cosmos_control_tower.models.records import SourceRecord, Violation


def broker_metrics(
    records: Iterable[SourceRecord], violations: Iterable[Violation]
) -> list[dict[str, Any]]:
    record_counts = Counter(record.assigned_to_id or "UNASSIGNED" for record in records)
    violation_counts = Counter(
        violation.assigned_to_id or "UNASSIGNED"
        for violation in violations
        if violation.status == "VIOLATION"
    )
    return [
        {
            "broker_id": broker_id,
            "entity_count": count,
            "violation_count": violation_counts[broker_id],
        }
        for broker_id, count in sorted(record_counts.items())
    ]


def department_metrics(records: Iterable[SourceRecord]) -> list[dict[str, Any]]:
    counts = Counter(record.department_id or "UNASSIGNED" for record in records)
    return [
        {"department_id": department_id, "entity_count": count}
        for department_id, count in sorted(counts.items())
    ]
