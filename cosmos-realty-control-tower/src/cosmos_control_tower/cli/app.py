import asyncio
import json
import logging
from datetime import UTC, datetime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

import typer

from cosmos_control_tower.acceptance.demo import acceptance_demo_snapshot
from cosmos_control_tower.acceptance.engine import evaluate_acceptance
from cosmos_control_tower.acceptance.models import AcceptanceRule, OrganizationMap
from cosmos_control_tower.acceptance.report import generate_acceptance_reports
from cosmos_control_tower.acceptance.service import AcceptanceService
from cosmos_control_tower.audit.rules import AuditRules, evaluate_record
from cosmos_control_tower.audit.service import AuditService
from cosmos_control_tower.bitrix.client import BitrixClient
from cosmos_control_tower.calibration.report import generate_calibration_reports
from cosmos_control_tower.calibration.service import (
    CalibrationRules,
    anonymized_examples,
    calibration_summary,
    classify_records,
)
from cosmos_control_tower.config import Settings
from cosmos_control_tower.metrics.basic import broker_metrics, department_metrics
from cosmos_control_tower.metrics.operational import build_dashboard_data
from cosmos_control_tower.models.records import CalibratedRecord, SourceRecord, Violation
from cosmos_control_tower.operational.demo import demo_snapshot
from cosmos_control_tower.operational.service import (
    OperationalService,
    records_from_snapshot,
    violations_from_snapshot,
)
from cosmos_control_tower.reports.generator import generate_reports
from cosmos_control_tower.reports.operational import generate_operational_reports
from cosmos_control_tower.robots.dry_run import preview_actions

app = typer.Typer(help="Cosmos Realty Control Tower read-only tools")
DEFAULT_ROP_OUTPUT = Path("output/rop")
DEFAULT_CALIBRATION_OUTPUT = Path("output")
DEFAULT_CALIBRATION_RULES = Path("config/calibration-rules.example.json")
DEFAULT_ACCEPTANCE_OUTPUT = Path("output/acceptance-control")
DEFAULT_ACCEPTANCE_RULE = Path("config/acceptance-rule.json")
DEFAULT_ORGANIZATION_MAP = Path("config/organization-map.example.json")


def _configure_logging() -> None:
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s %(message)s")
    logging.getLogger("httpx").setLevel(logging.WARNING)


@app.command("audit-bitrix")
def audit_bitrix(output: Path = Path("output")) -> None:
    """Read metadata from Bitrix24 and create a redacted technical audit."""
    _configure_logging()
    settings = Settings()  # type: ignore[call-arg]  # Values come from environment.

    async def run() -> None:
        async with BitrixClient(
            settings.webhook_secret.get_secret_value(),
            timeout=settings.bitrix_timeout_seconds,
            rate_limit_per_second=settings.bitrix_rate_limit_per_second,
            max_retries=settings.bitrix_max_retries,
        ) as client:
            await AuditService(client, output).run()

    asyncio.run(run())
    typer.echo(f"Read-only audit completed: {output}")


@app.command()
def demo(output: Path = Path("output")) -> None:
    """Generate sanitized report templates without connecting to Bitrix24."""
    now = datetime.now(UTC)
    records = [
        SourceRecord(
            entity_type="lead",
            source_id="demo-001",
            assigned_to_id="broker-demo",
            department_id="department-demo",
            stage_id="stage-demo",
            created_at=now - timedelta(days=2),
            updated_at=now - timedelta(days=2),
            stage_changed_at=now - timedelta(days=2),
            next_activity_at=now - timedelta(hours=1),
            has_open_activity=False,
            has_first_call=False,
            required_fields={},
        )
    ]
    rules = AuditRules(inactive_hours=24)
    findings = [item for record in records for item in evaluate_record(record, rules, now=now)]
    generate_reports(
        output,
        findings,
        broker_metrics(records, findings),
        department_metrics(records),
    )
    (output / "demo-snapshot.json").write_text(
        json.dumps([record.model_dump(mode="json") for record in records], indent=2) + "\n",
        encoding="utf-8",
    )
    typer.echo(f"Sanitized demo reports created: {output}")


@app.command("acceptance-control")
def acceptance_control(
    dry_run: bool = typer.Option(False, "--dry-run", help="Только preview"),
    apply: bool = typer.Option(False, "--apply", help="Применение, закрыто safety-gate"),
    as_of: str = typer.Option("23:50", help="HH:MM или ISO datetime"),
    output: Path = typer.Option(DEFAULT_ACCEPTANCE_OUTPUT),  # noqa: B008
    demo_mode: bool = typer.Option(False, "--demo"),
    snapshot_file: Path | None = typer.Option(None, "--snapshot"),  # noqa: B008
    rule_config: Path = typer.Option(DEFAULT_ACCEPTANCE_RULE),  # noqa: B008
    organization_map: Path = typer.Option(DEFAULT_ORGANIZATION_MAP),  # noqa: B008
    ledger: Path = typer.Option(Path("output/acceptance-control/ledger.json")),  # noqa: B008
) -> None:
    """Preview the approved 23:50 lead acceptance rule without CRM writes."""
    _configure_logging()
    if dry_run == apply:
        raise typer.BadParameter("Укажите ровно один режим: --dry-run или --apply")
    if apply:
        typer.echo(
            "APPLY заблокирован: требуется отдельное разрешение Михаила, заполненный "
            "organization-map и подтверждённый источник assigned_at."
        )
        raise typer.Exit(code=2)
    rule = AcceptanceRule.model_validate_json(rule_config.read_text(encoding="utf-8"))
    organization = OrganizationMap.model_validate_json(organization_map.read_text(encoding="utf-8"))
    check_at = _acceptance_as_of(as_of, rule.timezone)
    if demo_mode and snapshot_file:
        raise typer.BadParameter("Нельзя одновременно использовать --demo и --snapshot")
    if demo_mode:
        snapshot = acceptance_demo_snapshot(check_at)
        if organization.poteryashka_user_id is None:
            organization.poteryashka_user_id = "999"
    elif snapshot_file:
        snapshot = json.loads(snapshot_file.read_text(encoding="utf-8"))
    else:
        settings = Settings()  # type: ignore[call-arg]

        async def collect_acceptance() -> dict[str, object]:
            webhook = settings.webhook_secret.get_secret_value()
            async with BitrixClient(
                webhook,
                timeout=settings.bitrix_timeout_seconds,
                rate_limit_per_second=settings.bitrix_rate_limit_per_second,
                max_retries=settings.bitrix_max_retries,
            ) as client:
                return await AcceptanceService(client, webhook).collect(
                    day_start=check_at.replace(hour=0, minute=0, second=0, microsecond=0)
                )

        snapshot = asyncio.run(collect_acceptance())
        output.mkdir(parents=True, exist_ok=True)
        (output / "acceptance-snapshot.json").write_text(
            json.dumps(snapshot, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
        )
    records = records_from_snapshot(snapshot)
    raw_heads = snapshot.get("department_heads", {})
    heads = (
        {str(key): str(value) for key, value in raw_heads.items()}
        if isinstance(raw_heads, dict)
        else {}
    )
    report_data = evaluate_acceptance(
        records,
        heads,
        organization,
        rule,
        as_of=check_at,
        processed_keys=_load_processed_keys(ledger),
    )
    generate_acceptance_reports(output, report_data)
    typer.echo(f"Acceptance dry-run: {output / 'acceptance-report.html'}")
    typer.echo(f"Eligible actions: {report_data.eligible_to_return}")
    typer.echo(f"Blocked candidates: {len(report_data.blocked_candidates)}")
    typer.echo("Bitrix24 writes: 0")


@app.command()
def report(
    department: str | None = typer.Option(None, help="ID отдела"),
    broker: str | None = typer.Option(None, help="ID брокера"),
    rop: str | None = typer.Option(None, help="ID РОПа"),
    source: str | None = typer.Option(None, help="ID источника"),
    stage: str | None = typer.Option(None, help="ID стадии или статуса"),
    category: str | None = typer.Option(None, help="ID воронки"),
    work_scope: str = typer.Option("operational", help="operational, warm, archive или all"),
    active_employees_only: bool = typer.Option(
        True, "--active-employees-only/--include-inactive-employees"
    ),
    created_after: str | None = typer.Option(None, help="Дата создания от YYYY-MM-DD"),
    last_activity_after: str | None = typer.Option(None, help="Последняя активность от YYYY-MM-DD"),
    period: str = typer.Option("week", help="today, week или month"),
    output: Path = typer.Option(DEFAULT_ROP_OUTPUT, help="Каталог отчёта"),  # noqa: B008
    demo_mode: bool = typer.Option(False, "--demo", help="Без подключения к Bitrix24"),
    snapshot_file: Path | None = typer.Option(  # noqa: B008
        None, "--snapshot", help="Повторно построить отчёт из локального снимка"
    ),
    calibration_output: Path = typer.Option(  # noqa: B008
        DEFAULT_CALIBRATION_OUTPUT, help="Каталог отчёта калибровки"
    ),
    calibration_rules: Path = typer.Option(  # noqa: B008
        DEFAULT_CALIBRATION_RULES, help="Предлагаемые правила периметра"
    ),
    limit: int = typer.Option(0, min=0, help="Лимит сущностей для безопасной проверки"),
) -> None:
    """Create a ROP report and dashboard. Bitrix24 is always read-only."""
    _configure_logging()
    if period not in {"today", "week", "month"}:
        raise typer.BadParameter("period должен быть today, week или month")
    if sum(value is not None for value in (department, broker, rop)) > 1:
        raise typer.BadParameter("Выберите один фильтр: department, broker или rop")
    if work_scope not in {"operational", "warm", "archive", "all"}:
        raise typer.BadParameter("work-scope должен быть operational, warm, archive или all")

    if demo_mode and snapshot_file:
        raise typer.BadParameter("Нельзя одновременно использовать --demo и --snapshot")
    if demo_mode:
        snapshot = demo_snapshot()
    elif snapshot_file:
        snapshot = json.loads(snapshot_file.read_text(encoding="utf-8"))
    else:
        settings = Settings()  # type: ignore[call-arg]
        rules = _load_rules(settings.bitrix_rules_config)

        async def collect() -> dict[str, object]:
            webhook = settings.webhook_secret.get_secret_value()
            async with BitrixClient(
                webhook,
                timeout=settings.bitrix_timeout_seconds,
                rate_limit_per_second=settings.bitrix_rate_limit_per_second,
                max_retries=settings.bitrix_max_retries,
            ) as client:
                service = OperationalService(
                    client,
                    webhook,
                    rules,
                    first_call_provider_ids=set(rules.first_call_activity_types),
                )
                return await service.collect(limit=limit or None)

        snapshot = asyncio.run(collect())
        output.mkdir(parents=True, exist_ok=True)
        (output / "operational-snapshot.json").write_text(
            json.dumps(snapshot, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
        )

    records = records_from_snapshot(snapshot)
    violations = violations_from_snapshot(snapshot)
    calibration_config = _load_calibration_rules(calibration_rules)
    calibrated = classify_records(
        records,
        calibration_config,
        now=_snapshot_time(snapshot),
    )
    calibration = calibration_summary(calibrated, violations)
    examples = anonymized_examples(calibrated, violations)
    generate_calibration_reports(calibration_output, calibrated, calibration, examples)

    selected_records = _records_for_work_scope(calibrated, work_scope)
    selected_records, selected_violations, scope = _apply_scope(
        selected_records,
        violations,
        snapshot.get("department_heads", {}),
        department=department,
        broker=broker,
        rop=rop,
        source=source,
        stage=stage,
        category=category,
        active_employees_only=active_employees_only,
        created_after=created_after,
        last_activity_after=last_activity_after,
        period=period,
    )
    dashboard = build_dashboard_data(
        selected_records,
        selected_violations,
        generated_at=str(snapshot.get("generated_at", "")),
        mode=str(snapshot.get("mode", "unknown")),
        limitations=[str(item) for item in snapshot.get("limitations", [])],
        period_start=_period_start(period),
    )
    actions = preview_actions(selected_violations)
    acceptance_summary = _load_optional_json(DEFAULT_ACCEPTANCE_OUTPUT / "acceptance-report.json")
    generate_operational_reports(
        output,
        dashboard,
        actions,
        scope=f"{scope}; группа {work_scope}",
        scope_links=_main_scope_links(),
        acceptance_summary=acceptance_summary,
    )
    for candidate_scope in ("operational", "warm", "archive", "all"):
        scope_records = _records_for_work_scope(calibrated, candidate_scope)
        scope_records, scope_violations, scope_label = _apply_scope(
            scope_records,
            violations,
            snapshot.get("department_heads", {}),
            department=department,
            broker=broker,
            rop=rop,
            source=source,
            stage=stage,
            category=category,
            active_employees_only=False,
            created_after=created_after,
            last_activity_after=last_activity_after,
            period=period,
        )
        scope_dashboard = build_dashboard_data(
            scope_records,
            scope_violations,
            generated_at=str(snapshot.get("generated_at", "")),
            mode=str(snapshot.get("mode", "unknown")),
            limitations=[str(item) for item in snapshot.get("limitations", [])],
            period_start=_period_start(period),
        )
        scope_actions = preview_actions(scope_violations)
        generate_operational_reports(
            output / "scopes" / candidate_scope,
            scope_dashboard,
            scope_actions,
            scope=f"{scope_label}; группа {candidate_scope}",
            scope_links=_nested_scope_links(),
            acceptance_summary=acceptance_summary,
        )
    typer.echo(f"ROP dashboard created: {output / 'rop-dashboard.html'}")
    typer.echo(f"Dry-run actions: {len(actions)}; Bitrix24 writes: 0")
    typer.echo(
        "Calibration: "
        f"operational={calibration['scope_counts'].get('operational', 0)}, "
        f"warm={calibration['scope_counts'].get('warm', 0)}, "
        f"archive={calibration['scope_counts'].get('archive', 0)}"
    )


def _load_optional_json(path: Path) -> dict[str, object]:
    if not path.exists():
        return {}
    payload = json.loads(path.read_text(encoding="utf-8"))
    return payload if isinstance(payload, dict) else {}


def _load_rules(path: Path) -> AuditRules:
    if not path.exists():
        return AuditRules()
    return AuditRules.model_validate_json(path.read_text(encoding="utf-8"))


def _load_calibration_rules(path: Path) -> CalibrationRules:
    if not path.exists():
        return CalibrationRules()
    return CalibrationRules.model_validate_json(path.read_text(encoding="utf-8"))


def _snapshot_time(snapshot: dict[str, object]) -> datetime:
    value = snapshot.get("generated_at")
    if isinstance(value, str):
        return datetime.fromisoformat(value)
    return datetime.now(UTC)


def _records_for_work_scope(
    calibrated: list[CalibratedRecord], work_scope: str
) -> list[SourceRecord]:
    return [
        item.record for item in calibrated if work_scope == "all" or item.work_scope == work_scope
    ]


def _apply_scope(
    records: list[SourceRecord],
    violations: list[Violation],
    department_heads: object,
    *,
    department: str | None,
    broker: str | None,
    rop: str | None,
    source: str | None,
    stage: str | None,
    category: str | None,
    active_employees_only: bool,
    created_after: str | None,
    last_activity_after: str | None,
    period: str,
) -> tuple[list[SourceRecord], list[Violation], str]:
    selected_departments = [department] if department else []
    if rop and isinstance(department_heads, dict):
        selected_departments = [
            str(key) for key, value in department_heads.items() if str(value) == rop
        ]
        if not selected_departments:
            raise typer.BadParameter("Для этого РОПа не найден отдел")
    labels: list[str] = []
    if broker:
        records = [item for item in records if item.assigned_to_id == broker]
        labels.append(f"брокер {broker}")
    elif selected_departments:
        records = [item for item in records if item.department_id in selected_departments]
        label = f"РОП {rop}" if rop else f"отдел {selected_departments[0]}"
        labels.append(label)
    if source:
        records = [item for item in records if item.source_channel_id == source]
        labels.append(f"источник {source}")
    if stage:
        records = [item for item in records if item.stage_id == stage]
        labels.append(f"стадия {stage}")
    if category:
        records = [item for item in records if item.category_id == category]
        labels.append(f"воронка {category}")
    if active_employees_only:
        records = [item for item in records if item.assignee_active is True]
        labels.append("только действующие сотрудники")
    if created_after:
        created_cutoff = _parse_date_filter(created_after, "created-after")
        records = [
            item for item in records if item.created_at and item.created_at >= created_cutoff
        ]
        labels.append(f"созданы с {created_after}")
    if last_activity_after:
        activity_cutoff = _parse_date_filter(last_activity_after, "last-activity-after")
        records = [
            item
            for item in records
            if item.last_activity_at and item.last_activity_at >= activity_cutoff
        ]
        labels.append(f"активность с {last_activity_after}")
    scope = ", ".join(labels or ["все отделы"]) + f", период {period}"
    record_keys = {(item.entity_type, item.source_id) for item in records}
    filtered_violations = [
        item
        for item in violations
        if (getattr(item, "entity_type", None), getattr(item, "source_id", None)) in record_keys
    ]
    return records, filtered_violations, scope


def _period_start(period: str) -> datetime:
    now = datetime.now(UTC)
    if period == "today":
        return now.replace(hour=0, minute=0, second=0, microsecond=0)
    if period == "week":
        return now - timedelta(days=7)
    return now - timedelta(days=30)


def _parse_date_filter(value: str, option: str) -> datetime:
    try:
        return datetime.fromisoformat(value).replace(tzinfo=UTC)
    except ValueError as exc:
        raise typer.BadParameter(f"{option}: используйте YYYY-MM-DD") from exc


def _main_scope_links() -> list[tuple[str, str]]:
    return [
        ("Оперативная работа", "scopes/operational/rop-dashboard.html"),
        ("Прогрев", "scopes/warm/rop-dashboard.html"),
        ("Архив", "scopes/archive/rop-dashboard.html"),
        ("Вся база", "scopes/all/rop-dashboard.html"),
    ]


def _nested_scope_links() -> list[tuple[str, str]]:
    return [
        ("Оперативная работа", "../operational/rop-dashboard.html"),
        ("Прогрев", "../warm/rop-dashboard.html"),
        ("Архив", "../archive/rop-dashboard.html"),
        ("Вся база", "../all/rop-dashboard.html"),
    ]


def _acceptance_as_of(value: str, timezone: str) -> datetime:
    zone = ZoneInfo(timezone)
    if len(value) == 5 and value[2] == ":":
        try:
            hour, minute = (int(part) for part in value.split(":"))
            return datetime.now(zone).replace(hour=hour, minute=minute, second=0, microsecond=0)
        except ValueError as exc:
            raise typer.BadParameter("as-of: используйте HH:MM или ISO datetime") from exc
    try:
        parsed = datetime.fromisoformat(value)
    except ValueError as exc:
        raise typer.BadParameter("as-of: используйте HH:MM или ISO datetime") from exc
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=zone)
    return parsed.astimezone(zone)


def _load_processed_keys(path: Path) -> set[str]:
    if not path.exists():
        return set()
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, list):
        raise typer.BadParameter("ledger должен содержать JSON-массив")
    return {
        str(item["idempotency_key"])
        for item in payload
        if isinstance(item, dict) and item.get("idempotency_key")
    }


if __name__ == "__main__":
    app()
