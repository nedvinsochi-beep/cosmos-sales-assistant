from __future__ import annotations

import csv
import json
from pathlib import Path
from typing import Any

from jinja2 import BaseLoader, Environment, select_autoescape

from cosmos_control_tower.rules_engine.models import RulesRunReport

HTML = """<!doctype html><html lang="ru"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>Cosmos Control Tower — правила контроля</title><style>
body{font:14px/1.5 -apple-system,BlinkMacSystemFont,"Segoe UI",sans-serif;margin:0;
background:#f3f5f8;color:#172033}main{max-width:1400px;margin:auto;padding:28px}header{background:#172033;
color:white;padding:25px 28px}.grid{display:grid;
grid-template-columns:repeat(auto-fit,minmax(210px,1fr));
gap:12px}.card,.panel,.notice{background:white;border:1px solid #e1e6ef;border-radius:12px}
.card{padding:15px}.card b{display:block;font-size:25px}.panel{overflow:auto;margin:14px 0}
.notice{padding:13px;background:#fff8e8;margin:14px 0}table{width:100%;border-collapse:collapse;
min-width:900px}th,td{padding:10px 12px;border-bottom:1px solid #e6e9ef;text-align:left}
th{font-size:12px;color:#657085}.ok{color:#087c59}.blocked{color:#b56c08}a{color:#2458c5}</style>
</head><body><header><h1>Правила контроля</h1><p>{{ report.mode }} · {{ report.generated_at }}</p>
</header><main><div class="notice"><b>Bitrix24 writes: {{ report.writes_performed }}.</b>
Все действия — preview. ACTIVE и apply заблокированы.</div>
{% for result in report.results %}<h2>{{ result.name }} <small>({{ result.rule_id }})</small></h2>
<div class="grid"><div class="card"><b>{{ result.mode }}</b>режим</div>
<div class="card"><b>{{ result.status }}</b>статус</div>
<div class="card"><b>{{ result.records_evaluated }}</b>проверено</div>
<div class="card"><b>{{ result.violations_found }}</b>подтверждено</div>
<div class="card"><b>{{ result.blocked_by_data }}</b>заблокировано данными</div>
<div class="card"><b>{{ result.planned_actions }}</b>будущих действий</div></div>
<p>Последнее выполнение: {{ result.completed_at }}. Исключения: {{ result.exclusions }}.
Ошибки: {{ result.errors|length }}.</p>
<div class="panel"><table><thead><tr><th>Карточка</th><th>Сотрудник</th><th>РОП</th>
<th>Причина</th><th>Доказательство</th><th>Preview</th></tr></thead><tbody>
{% for row in result.previews[:500] %}<tr><td>{% if row.card_url %}<a href="{{ row.card_url }}">
{{ row.entity_type }} #{{ row.entity_id }}</a>{% else %}{{ row.entity_type }} #{{ row.entity_id }}
{% endif %}</td><td>{{ row.employee_id or '—' }}</td><td>{{ row.rop_user_id or '—' }}</td>
<td>{{ row.reason }}</td>
<td class="{{ 'ok' if row.evidence_status == 'CONFIRMED' else 'blocked' }}">
{{ row.evidence_status }}</td><td>НЕ ВЫПОЛНЕНО</td></tr>{% endfor %}</tbody></table></div>
{% endfor %}</main></body></html>"""


def generate_rules_report(output: Path, report: RulesRunReport) -> None:
    output.mkdir(parents=True, exist_ok=True)
    payload = report.model_dump(mode="json")
    (output / "rules-report.json").write_text(
        json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    rows = [
        {"rule_id": result["rule_id"], **preview}
        for result in payload["results"]
        for preview in result["previews"]
    ]
    _csv(output / "rules-preview.csv", rows)
    environment = Environment(loader=BaseLoader(), autoescape=select_autoescape(["html"]))
    rendered = environment.from_string(HTML).render(report=payload)
    (output / "rules-dashboard.html").write_text(rendered, encoding="utf-8")


def _csv(path: Path, rows: list[dict[str, Any]]) -> None:
    columns = sorted({key for row in rows for key in row})
    with path.open("w", encoding="utf-8", newline="") as handle:
        if not columns:
            return
        writer = csv.DictWriter(handle, fieldnames=columns, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(rows)
