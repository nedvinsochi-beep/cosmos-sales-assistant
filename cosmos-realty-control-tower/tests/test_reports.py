import json
from pathlib import Path

from cosmos_control_tower.models.records import Violation
from cosmos_control_tower.reports.generator import generate_reports


def test_report_generation(tmp_path: Path) -> None:
    findings = [
        Violation(
            rule_id="NO_NEXT_TASK",
            status="VIOLATION",
            entity_type="lead",
            source_id="anon-1",
        )
    ]
    generate_reports(
        tmp_path,
        findings,
        [{"broker_id": "10", "entity_count": 1, "violation_count": 0}],
        [{"department_id": "20", "entity_count": 1}],
    )
    expected = {
        "violations.csv",
        "broker_metrics.csv",
        "department_metrics.csv",
        "daily_report.html",
        "daily_report.md",
        "daily_report.json",
    }
    assert expected.issubset({path.name for path in tmp_path.iterdir()})
    summary = json.loads((tmp_path / "daily_report.json").read_text(encoding="utf-8"))
    assert summary["violations"] == 1
    assert summary["contains_personal_data"] is False
