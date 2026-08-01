from __future__ import annotations

import csv
import json
from pathlib import Path
from typing import Any

from jinja2 import BaseLoader, Environment, select_autoescape

from cosmos_control_tower.models.records import DryRunAction

DASHBOARD_TEMPLATE = """<!doctype html>
<html lang="ru">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>Cosmos Realty — контроль РОПа</title>
  <style>
    :root { --ink:#172033; --muted:#677085; --bg:#f3f5f8; --card:#fff;
      --line:#e3e7ee; --accent:#275fe8; --danger:#c83246; --warn:#d98614;
      --ok:#15805d; }
    * { box-sizing:border-box; }
    body { margin:0; font:14px/1.45 -apple-system,BlinkMacSystemFont,"Segoe UI",sans-serif;
      color:var(--ink); background:var(--bg); }
    header { padding:28px 32px 22px; color:white;
      background:linear-gradient(120deg,#172033,#203b71 68%,#275fe8); }
    h1 { margin:0 0 6px; font-size:28px; } h2 { margin:30px 0 14px; }
    header p { margin:0; color:#d8e3ff; }
    main { max-width:1440px; margin:auto; padding:24px 28px 50px; }
    .notice { padding:12px 15px; border:1px solid #f0d59b; background:#fff8e8;
      border-radius:10px; margin-bottom:18px; }
    .grid { display:grid; grid-template-columns:repeat(auto-fit,minmax(160px,1fr)); gap:12px; }
    .card,.panel { background:var(--card); border:1px solid var(--line); border-radius:12px;
      box-shadow:0 3px 12px rgba(25,35,55,.04); }
    .card { padding:15px; min-height:100px; } .card b { display:block; font-size:27px; }
    .card span { color:var(--muted); } .danger b { color:var(--danger); }
    .warn b { color:var(--warn); } .ok b { color:var(--ok); }
    .panel { overflow:auto; } table { width:100%; border-collapse:collapse; min-width:780px; }
    th,td { padding:11px 12px; border-bottom:1px solid var(--line); text-align:left; }
    th { color:var(--muted); font-size:12px; text-transform:uppercase; letter-spacing:.03em; }
    tr:last-child td { border:0; } a { color:var(--accent); text-decoration:none; }
    .risk-high,.priority { color:var(--danger); font-weight:700; }
    .risk-medium { color:var(--warn); font-weight:700; } .risk-low { color:var(--ok); }
    .tabs { margin:0 0 16px; display:flex; flex-wrap:wrap; gap:7px; }
    .tabs a { padding:8px 11px; background:#e7edfb; border-radius:8px; }
    .barrow { display:grid; grid-template-columns:minmax(150px,240px) 1fr 55px; gap:12px;
      align-items:center; padding:8px 14px; }
    .bar { height:10px; background:#e8edf7; border-radius:10px; overflow:hidden; }
    .bar i { display:block; height:100%; background:var(--accent); border-radius:10px; }
    footer { color:var(--muted); margin-top:28px; }
    @media(max-width:680px) { header,main { padding-left:16px; padding-right:16px; }
      h1{font-size:23px;} }
  </style>
</head>
<body>
<header><h1>Cosmos Realty — контроль РОПа</h1>
<p>{{ scope }} · {{ mode }} · снимок {{ generated_at }}</p></header>
<main>
  <nav class="tabs">{% for label,href in scope_links %}
    <a href="{{ href }}">{{ label }}</a>{% endfor %}</nav>
  <div class="notice"><b>Безопасный режим:</b> данные только прочитаны. Ни одна задача,
    стадия, карточка или уведомление в Bitrix24 не изменены.</div>
  <h2>Сегодня — требует внимания</h2>
  <section class="grid">
    {% for item in cards %}<div class="card {{ item.tone }}">
      <b>{{ item.value }}</b><span>{{ item.label }}</span>
    </div>{% endfor %}
  </section>
  <h2>Брокеры</h2>
  <div class="panel"><table><thead><tr><th>ID брокера</th><th>Отдел</th><th>Нагрузка</th>
    <th>Нарушения</th><th>Просрочки</th><th>Без задачи</th><th>Показы</th><th>Брони</th>
    <th>Сделки</th><th>CRM-дисциплина</th><th>Риск</th></tr></thead><tbody>
    {% for row in brokers %}<tr><td>{{ row.broker_id }}</td><td>{{ row.department_id or '—' }}</td>
    <td>{{ row.load }}</td><td>{{ row.violations }}</td><td>{{ row.overdue }}</td>
    <td>{{ row.without_next_task }}</td><td>{{ row.showings }}</td><td>{{ row.bookings }}</td>
    <td>{{ row.won }}</td><td>{{ row.crm_discipline_pct }}%</td>
    <td class="risk-{{ row.risk }}">{{ row.risk }}</td></tr>{% endfor %}
  </tbody></table></div>
  <h2>Воронка — текущий срез</h2>
  <div class="panel">{% for row in stages %}<div class="barrow"><span>{{ row.stage_id }}</span>
    <div class="bar"><i style="width:{{ row.share }}%"></i></div><b>{{ row.count }}</b>
    </div>{% endfor %}</div>
  <div class="notice" style="margin-top:12px">Конверсии между этапами пока не показываются:
    история переходов недоступна текущему webhook. Текущий срез не выдаётся за конверсию.</div>
  <h2>Контроль — кого проверить</h2>
  <p>Показаны первые {{ control_shown }} из {{ control_total }} нарушений.
    Полный список находится в CSV и JSON.</p>
  <div class="panel"><table><thead><tr><th>Приоритет</th><th>Причина</th><th>Карточка</th>
    <th>Брокер</th><th>Отдел</th><th>Действие</th><th>Срок</th></tr></thead><tbody>
    {% for row in control %}<tr><td class="priority">{{ row.priority }}</td>
    <td>{{ row.reason }}</td><td>{% if row.card_url %}
      <a href="{{ row.card_url }}" target="_blank" rel="noopener">
        {{ row.entity_type }} #{{ row.source_id }}</a>
      {% else %}{{ row.entity_type }} #{{ row.source_id }}{% endif %}</td>
    <td>{{ row.broker_id or '—' }}</td><td>{{ row.department_id or '—' }}</td>
    <td>{{ row.recommended_action }}</td><td>{{ row.reaction_due }}</td></tr>{% endfor %}
  </tbody></table></div>
  <h2>Dry-run роботов</h2>
  <p>Показаны первые {{ actions_shown }} из {{ actions_total }} будущих действий.
    Ни одно действие не выполнено.</p>
  <div class="panel"><table><thead><tr><th>Кому</th><th>Причина</th>
    <th>Будущее действие</th><th>Факт</th></tr></thead><tbody>
    {% for row in actions %}<tr><td>{{ row.target_role }} {{ row.target_id or '' }}</td>
    <td>{{ row.reason }}</td><td>{{ row.proposed_action }}</td>
    <td>НЕ ВЫПОЛНЕНО</td></tr>{% endfor %}
  </tbody></table></div>
  <h2>Прогноз и рекомендации</h2>
  <div class="notice">План-факт: {{ plan_fact.reason }}. Прогноз: {{ forecast.reason }}.
    Система не выдумывает прогноз без истории стадий и сумм комиссии.</div>
  <div class="panel"><ul>{% for item in recommendations %}<li>{{ item }}</li>{% endfor %}</ul></div>
  <footer>Источник: структурные поля Bitrix24 без ФИО и контактов клиентов. Данные — снимок,
    обновляются повторным запуском команды report.</footer>
</main></body></html>"""


def generate_operational_reports(
    output_dir: Path,
    dashboard: dict[str, Any],
    actions: list[DryRunAction],
    *,
    scope: str,
    scope_links: list[tuple[str, str]] | None = None,
) -> None:
    output_dir.mkdir(parents=True, exist_ok=True)
    action_rows = [item.model_dump(mode="json") for item in actions]
    payload = {"scope": scope, "dashboard": dashboard, "dry_run_actions": action_rows}
    (output_dir / "rop-report.json").write_text(
        json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    _write_csv(output_dir / "rop-control.csv", dashboard["control"])
    _write_csv(output_dir / "rop-brokers.csv", dashboard["brokers"])
    _write_csv(output_dir / "dry-run-actions.csv", action_rows)
    (output_dir / "rop-report.md").write_text(
        _markdown(dashboard, actions, scope=scope), encoding="utf-8"
    )

    stages = list(dashboard["stages"])
    maximum = max((int(row["count"]) for row in stages), default=1)
    for row in stages:
        row["share"] = round(int(row["count"]) / maximum * 100, 1)
    environment = Environment(loader=BaseLoader(), autoescape=select_autoescape(["html"]))
    html = environment.from_string(DASHBOARD_TEMPLATE).render(
        generated_at=dashboard["generated_at"],
        mode=dashboard["mode"],
        scope=scope,
        cards=_cards(dashboard["summary"]),
        brokers=dashboard["brokers"],
        stages=stages,
        control=dashboard["control"][:500],
        control_shown=min(len(dashboard["control"]), 500),
        control_total=len(dashboard["control"]),
        actions=action_rows[:500],
        actions_shown=min(len(action_rows), 500),
        actions_total=len(action_rows),
        plan_fact=dashboard["plan_fact"],
        forecast=dashboard["forecast"],
        recommendations=dashboard["recommendations"],
        scope_links=scope_links or [],
    )
    (output_dir / "rop-dashboard.html").write_text(html, encoding="utf-8")


def _write_csv(path: Path, rows: list[dict[str, Any]]) -> None:
    columns = sorted({key for row in rows for key in row})
    with path.open("w", encoding="utf-8", newline="") as handle:
        if not columns:
            handle.write("")
            return
        writer = csv.DictWriter(handle, fieldnames=columns, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(rows)


def _cards(summary: dict[str, Any]) -> list[dict[str, Any]]:
    definitions = [
        ("unaccepted_leads", "Непринятые лиды", "danger"),
        ("without_first_call", "Без подтверждённого звонка", "warn"),
        ("without_next_task", "Без следующей задачи", "danger"),
        ("overdue_tasks", "Просроченные задачи", "danger"),
        ("inactive_24", "Без активности 24+ часа", "warn"),
        ("inactive_72", "Без активности 72+ часа", "danger"),
        ("showings_scheduled", "Показы назначены", ""),
        ("showings_completed", "Показы проведены", "ok"),
        ("bookings", "Брони", "ok"),
        ("commission_received", "Комиссии получены", "ok"),
    ]
    return [
        {"value": summary[key], "label": label, "tone": tone}
        for key, label, tone in definitions
    ]


def _markdown(
    dashboard: dict[str, Any], actions: list[DryRunAction], *, scope: str
) -> str:
    summary = dashboard["summary"]
    lines = [
        "# Cosmos Realty — отчёт РОПа",
        "",
        f"Область: {scope}. Режим: {dashboard['mode']}.",
        "",
        "## Главное",
        "",
        f"- Непринятые лиды: {summary['unaccepted_leads']}",
        f"- Без следующей задачи: {summary['without_next_task']}",
        f"- Просроченные задачи: {summary['overdue_tasks']}",
        f"- Без активности 24/48/72 часа: {summary['inactive_24']}/"
        f"{summary['inactive_48']}/{summary['inactive_72']}",
        f"- Показы назначены/проведены: {summary['showings_scheduled']}/"
        f"{summary['showings_completed']}",
        f"- Брони: {summary['bookings']}",
        f"- Комиссии получены: {summary['commission_received']} (количество, не сумма)",
        "",
        "## Контроль",
        "",
    ]
    for row in dashboard["control"][:50]:
        lines.append(
            f"- {row['reason']}: {row['entity_type']} #{row['source_id']} — "
            f"{row['recommended_action']} ({row['reaction_due']})"
        )
    lines.extend(
        [
            "",
            "## Dry-run роботов",
            "",
            f"Подготовлено действий: {len(actions)}. Выполнено в Bitrix24: 0.",
            "",
            "## Ограничения",
            "",
            "- Конверсии и время этапов заблокированы до появления истории стадий.",
            "- Сумма комиссии не считается: подтверждено только состояние.",
            "- Персональные данные клиентов в отчёт не включены.",
            "- План-факт заблокирован: источник плана не подключён.",
            "- Прогноз заблокирован: нет истории стадий и сумм комиссии.",
        ]
    )
    return "\n".join(lines) + "\n"
