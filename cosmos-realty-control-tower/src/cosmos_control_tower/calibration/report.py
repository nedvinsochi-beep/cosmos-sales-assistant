from __future__ import annotations

import csv
import json
from pathlib import Path
from typing import Any

from jinja2 import BaseLoader, Environment, select_autoescape

from cosmos_control_tower.models.records import CalibratedRecord

CALIBRATION_TEMPLATE = """<!doctype html><html lang="ru"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>Калибровка правил Cosmos Realty</title><style>
body{font:14px/1.5 -apple-system,BlinkMacSystemFont,"Segoe UI",sans-serif;margin:0;
background:#f4f6f9;color:#172033}main{max-width:1300px;margin:auto;padding:28px}
h1{margin:0 0 8px}.note{background:#fff6dd;border:1px solid #ecd18a;padding:12px 14px;
border-radius:10px}.grid{display:grid;grid-template-columns:repeat(auto-fit,minmax(180px,1fr));
gap:12px;margin:18px 0}.card,.panel{background:white;border:1px solid #e1e5ec;border-radius:12px}
.card{padding:15px}.card b{display:block;font-size:28px}.panel{overflow:auto;margin:12px 0}
table{border-collapse:collapse;width:100%;min-width:850px}th,td{padding:9px 11px;
border-bottom:1px solid #e8ebf0;text-align:left}th{color:#657087;font-size:12px}
.tabs a{display:inline-block;padding:9px 12px;margin:4px;background:#e9eef9;border-radius:8px;
color:#204da8;text-decoration:none}code{font-size:12px}</style></head><body><main>
<h1>Калибровка операционного периметра</h1>
<p>Правила имеют статус <b>PROPOSED_REQUIRES_APPROVAL</b> и не изменяют Bitrix24.</p>
<div class="note">Цель — отделить текущую работу РОПа от прогрева и исторической базы.
Все идентификаторы примеров обезличены.</div>
<div class="grid"><div class="card"><b>{{ summary.total_records }}</b>всего карточек</div>
<div class="card"><b>{{ summary.scope_counts.operational or 0 }}</b>оперативный периметр</div>
<div class="card"><b>{{ summary.scope_counts.warm or 0 }}</b>прогрев / отложка</div>
<div class="card"><b>{{ summary.scope_counts.archive or 0 }}</b>архив / исключения</div>
<div class="card"><b>{{ summary.original_violating_cards }}</b>карточек до фильтрации</div>
<div class="card"><b>{{ summary.operational_violating_cards }}</b>
карточек после фильтрации</div></div>
<h2>Почему карточки исключены</h2><div class="panel"><table><tr>
<th>Причина</th><th>Количество</th></tr>
{% for reason,count in summary.reason_counts.items() %}<tr>
<td>{{ reason }}</td><td>{{ count }}</td></tr>{% endfor %}
</table></div>
<h2>Срабатывания правил до и после</h2><div class="panel"><table><tr>
<th>Правило</th><th>До</th><th>Оперативный периметр</th></tr>
{% for rule,count in summary.rule_counts_original.items() %}<tr>
<td>{{ rule }}</td><td>{{ count }}</td>
<td>{{ summary.rule_counts_operational.get(rule,0) }}</td></tr>{% endfor %}</table></div>
<h2>Распределения базы</h2>
{% for dimension,values in summary.distributions.items() %}<h3>{{ dimension }}</h3>
<div class="panel"><table><tr><th>Значение</th><th>Количество</th></tr>
{% for value,count in values.items() %}<tr><td>{{ value }}</td><td>{{ count }}</td></tr>
{% endfor %}</table></div>{% endfor %}
<h2>20 обезличенных примеров</h2>
{% for rule,rows in examples.items() %}<h3>{{ rule }}</h3><div class="panel"><table><tr>
<th>ID</th><th>Сущность</th><th>Стадия</th><th>Отдел</th><th>Сотрудник активен</th>
<th>Создано</th><th>Последняя активность</th><th>Группа</th><th>Почему группа</th>
<th>Почему сработало</th></tr>
{% for row in rows %}<tr><td><code>{{ row.anonymous_id }}</code></td><td>{{ row.entity_type }}</td>
<td>{{ row.stage_id }}</td><td>{{ row.department_id or '—' }}</td><td>{{ row.assignee_active }}</td>
<td>{{ row.created_month or '—' }}</td><td>{{ row.last_activity_month or '—' }}</td>
<td>{{ row.work_scope }}</td><td>{{ row.classification_reason }}</td>
<td>{{ row.trigger_explanation }}</td></tr>{% endfor %}
</table></div>{% endfor %}
<h2>Переключатели дашборда</h2><div class="tabs">
<a href="rop/scopes/operational/rop-dashboard.html">Только оперативная работа</a>
<a href="rop/scopes/warm/rop-dashboard.html">Прогрев</a>
<a href="rop/scopes/archive/rop-dashboard.html">Архив</a>
<a href="rop/scopes/all/rop-dashboard.html">Вся база</a></div>
</main></body></html>"""


def generate_calibration_reports(
    output_dir: Path,
    calibrated: list[CalibratedRecord],
    summary: dict[str, Any],
    examples: dict[str, list[dict[str, Any]]],
) -> None:
    output_dir.mkdir(parents=True, exist_ok=True)
    rows = [
        {
            "anonymous_id": _anonymous_id(item),
            "entity_type": item.record.entity_type,
            "category_id": item.record.category_id,
            "stage_id": item.record.stage_id,
            "department_id": item.record.department_id,
            "assignee_active": item.record.assignee_active,
            "created_month": item.record.created_at.strftime("%Y-%m")
            if item.record.created_at
            else None,
            "last_activity_month": item.record.last_activity_at.strftime("%Y-%m")
            if item.record.last_activity_at
            else None,
            "has_open_activity": item.record.has_open_activity,
            "is_closed": item.record.is_closed,
            "work_scope": item.work_scope,
            "reason_code": item.reason_code,
            "rule_status": item.rule_status,
        }
        for item in calibrated
    ]
    columns = list(rows[0]) if rows else []
    with (output_dir / "calibration-summary.csv").open(
        "w", encoding="utf-8", newline=""
    ) as handle:
        writer = csv.DictWriter(handle, fieldnames=columns)
        writer.writeheader()
        writer.writerows(rows)
    (output_dir / "calibration-summary.json").write_text(
        json.dumps({"summary": summary, "examples": examples}, ensure_ascii=False, indent=2)
        + "\n",
        encoding="utf-8",
    )
    environment = Environment(loader=BaseLoader(), autoescape=select_autoescape(["html"]))
    html = environment.from_string(CALIBRATION_TEMPLATE).render(
        summary=summary, examples=examples
    )
    (output_dir / "calibration-summary.html").write_text(html, encoding="utf-8")


def _anonymous_id(item: CalibratedRecord) -> str:
    import hashlib

    raw = f"{item.record.entity_type}:{item.record.source_id}".encode()
    return hashlib.sha256(raw).hexdigest()[:12]
