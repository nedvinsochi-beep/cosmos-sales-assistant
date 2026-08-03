import csv
import json
from collections.abc import Iterable
from pathlib import Path
from typing import Any

from jinja2 import BaseLoader, Environment, select_autoescape

from cosmos_control_tower.models.records import Violation

HTML_TEMPLATE = """<!doctype html>
<html lang="ru"><head><meta charset="utf-8"><title>CRM audit</title></head>
<body><h1>Cosmos Realty — CRM audit</h1>
<p>Нарушений: {{ violations }}. Непроверяемых правил: {{ blocked }}.</p>
<p>Отчет не содержит персональных данных клиентов.</p></body></html>
"""


def _write_csv(path: Path, rows: list[dict[str, Any]], columns: list[str]) -> None:
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=columns)
        writer.writeheader()
        writer.writerows(rows)


def generate_reports(
    output_dir: Path,
    violations: Iterable[Violation],
    broker_rows: list[dict[str, Any]],
    department_rows: list[dict[str, Any]],
) -> None:
    output_dir.mkdir(parents=True, exist_ok=True)
    findings = list(violations)
    violation_rows = [
        {
            "rule_id": item.rule_id,
            "status": item.status,
            "entity_type": item.entity_type,
            "source_id": item.source_id,
            "evidence": json.dumps(item.evidence, ensure_ascii=False, sort_keys=True),
        }
        for item in findings
    ]
    _write_csv(
        output_dir / "violations.csv",
        violation_rows,
        ["rule_id", "status", "entity_type", "source_id", "evidence"],
    )
    _write_csv(
        output_dir / "broker_metrics.csv",
        broker_rows,
        ["broker_id", "entity_count", "violation_count"],
    )
    _write_csv(
        output_dir / "department_metrics.csv",
        department_rows,
        ["department_id", "entity_count"],
    )

    summary = {
        "violations": sum(item.status == "VIOLATION" for item in findings),
        "blocked_by_data": sum(item.status == "BLOCKED_BY_DATA" for item in findings),
        "contains_personal_data": False,
    }
    (output_dir / "daily_report.json").write_text(
        json.dumps(summary, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    (output_dir / "daily_report.md").write_text(
        "# Cosmos Realty — CRM audit\n\n"
        f"- Нарушений: {summary['violations']}\n"
        f"- Непроверяемых правил: {summary['blocked_by_data']}\n"
        "- Персональные данные клиентов: отсутствуют\n",
        encoding="utf-8",
    )
    environment = Environment(loader=BaseLoader(), autoescape=select_autoescape(["html"]))
    html = environment.from_string(HTML_TEMPLATE).render(
        violations=summary["violations"], blocked=summary["blocked_by_data"]
    )
    (output_dir / "daily_report.html").write_text(html, encoding="utf-8")
