from __future__ import annotations

import csv
import json
from pathlib import Path
from typing import Any

from jinja2 import BaseLoader, Environment, select_autoescape

from cosmos_control_tower.acceptance.models import AcceptanceReport

HTML = """<!doctype html><html lang="ru"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>Потеряшка — dry-run</title><style>
body{font:14px/1.5 -apple-system,BlinkMacSystemFont,"Segoe UI",sans-serif;margin:0;
background:#f4f6f9;color:#172033}main{max-width:1300px;margin:auto;padding:28px}
.grid{display:grid;grid-template-columns:repeat(auto-fit,minmax(190px,1fr));gap:12px}
.card,.panel,.warning{background:white;border:1px solid #e1e5ec;border-radius:12px}
.card{padding:15px}.card b{display:block;font-size:28px}.warning{padding:14px;background:#fff4da;
border-color:#e7c675;margin:16px 0}.panel{overflow:auto;margin:14px 0}table{width:100%;
border-collapse:collapse;min-width:800px}th,td{padding:9px 11px;border-bottom:1px solid #e8ebf0;
text-align:left}th{font-size:12px;color:#667085}a{color:#2458c5}</style></head><body><main>
<h1>Робот «Потеряшка» — dry-run</h1><p>Срез {{ report.as_of }} · проверено записей:
{{ report.records_evaluated }} · изменений в Bitrix24: {{ report.writes_performed }}</p>
<div class="warning"><b>Apply заблокирован.</b> Bitrix24 не предоставляет дату назначения
ответственного. DATE_CREATE, DATE_MODIFY и MOVED_TIME не заменяют assigned_at.</div>
<div class="grid"><div class="card"><b>—</b>точно назначено сегодня</div>
<div class="card"><b>—</b>точно принято до 23:50</div>
<div class="card"><b>{{ report.created_today_assigned_proxy }}</b>
создано сегодня и сейчас назначено</div>
<div class="card"><b>{{ report.created_today_moved_from_new_proxy }}</b>
создано сегодня и сейчас уже не NEW</div>
<div class="card"><b>{{ report.eligible_to_return }}</b>точно готово к возврату</div>
<div class="card"><b>{{ report.blocked_candidates|length }}</b>
заблокировано данными/настройкой</div></div>
<h2>По брокерам</h2><div class="panel"><table><tr><th>ID брокера</th><th>Готово</th>
<th>Заблокировано</th></tr>{% for row in report.by_broker %}<tr><td>{{ row.user_id }}</td>
<td>{{ row.eligible }}</td><td>{{ row.blocked }}</td></tr>{% endfor %}</table></div>
<h2>По РОПам</h2><div class="panel"><table><tr><th>ID РОПа</th><th>Готово</th>
<th>Заблокировано</th></tr>{% for row in report.by_rop %}<tr><td>{{ row.user_id }}</td>
<td>{{ row.eligible }}</td><td>{{ row.blocked }}</td></tr>{% endfor %}</table></div>
<h2>Заблокированные кандидаты</h2><div class="panel"><table><tr><th>Лид</th>
<th>Брокер</th><th>Отдел</th><th>РОП</th><th>Причина</th></tr>
{% for row in blocked %}<tr><td>{% if row.card_url %}
<a href="{{ row.card_url }}">#{{ row.lead_id }}</a>
{% else %}#{{ row.lead_id }}{% endif %}</td><td>{{ row.assigned_user_id }}</td>
<td>{{ row.department_id }}</td><td>{{ row.rop_user_id }}</td><td>{{ row.reason }}</td></tr>
{% endfor %}</table></div><p>Показаны первые {{ blocked|length }} из
{{ report.blocked_candidates|length }}. Полный список — в CSV/JSON.</p>
</main></body></html>"""


def generate_acceptance_reports(output: Path, report: AcceptanceReport) -> None:
    output.mkdir(parents=True, exist_ok=True)
    payload = report.model_dump(mode="json")
    (output / "acceptance-report.json").write_text(
        json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    _csv(output / "acceptance-actions.csv", payload["actions"])
    _csv(output / "acceptance-blocked.csv", payload["blocked_candidates"])
    environment = Environment(loader=BaseLoader(), autoescape=select_autoescape(["html"]))
    html = environment.from_string(HTML).render(
        report=payload, blocked=payload["blocked_candidates"][:500]
    )
    (output / "acceptance-report.html").write_text(html, encoding="utf-8")


def _csv(path: Path, rows: list[dict[str, Any]]) -> None:
    columns = sorted({key for item in rows for key in item})
    with path.open("w", encoding="utf-8", newline="") as handle:
        if not columns:
            return
        writer = csv.DictWriter(handle, fieldnames=columns, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(rows)
