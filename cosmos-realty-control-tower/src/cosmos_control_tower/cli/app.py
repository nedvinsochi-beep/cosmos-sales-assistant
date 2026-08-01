import asyncio
import json
import logging
from datetime import UTC, datetime, timedelta
from pathlib import Path

import typer

from cosmos_control_tower.audit.rules import AuditRules, evaluate_record
from cosmos_control_tower.audit.service import AuditService
from cosmos_control_tower.bitrix.client import BitrixClient
from cosmos_control_tower.config import Settings
from cosmos_control_tower.metrics.basic import broker_metrics, department_metrics
from cosmos_control_tower.metrics.operational import build_dashboard_data
from cosmos_control_tower.models.records import SourceRecord, Violation
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


@app.command()
def report(
    department: str | None = typer.Option(None, help="ID отдела"),
    broker: str | None = typer.Option(None, help="ID брокера"),
    rop: str | None = typer.Option(None, help="ID РОПа"),
    source: str | None = typer.Option(None, help="ID источника"),
    stage: str | None = typer.Option(None, help="ID стадии или статуса"),
    period: str = typer.Option("week", help="today, week или month"),
    output: Path = typer.Option(DEFAULT_ROP_OUTPUT, help="Каталог отчёта"),  # noqa: B008
    demo_mode: bool = typer.Option(False, "--demo", help="Без подключения к Bitrix24"),
    snapshot_file: Path | None = typer.Option(  # noqa: B008
        None, "--snapshot", help="Повторно построить отчёт из локального снимка"
    ),
    limit: int = typer.Option(0, min=0, help="Лимит сущностей для безопасной проверки"),
) -> None:
    """Create a ROP report and dashboard. Bitrix24 is always read-only."""
    _configure_logging()
    if period not in {"today", "week", "month"}:
        raise typer.BadParameter("period должен быть today, week или month")
    if sum(value is not None for value in (department, broker, rop, source, stage)) > 1:
        raise typer.BadParameter(
            "Выберите один фильтр: department, broker, rop, source или stage"
        )

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
    records, violations, scope = _apply_scope(
        records,
        violations,
        snapshot.get("department_heads", {}),
        department=department,
        broker=broker,
        rop=rop,
        source=source,
        stage=stage,
        period=period,
    )
    dashboard = build_dashboard_data(
        records,
        violations,
        generated_at=str(snapshot.get("generated_at", "")),
        mode=str(snapshot.get("mode", "unknown")),
        limitations=[str(item) for item in snapshot.get("limitations", [])],
        period_start=_period_start(period),
    )
    actions = preview_actions(violations)
    generate_operational_reports(output, dashboard, actions, scope=scope)
    typer.echo(f"ROP dashboard created: {output / 'rop-dashboard.html'}")
    typer.echo(f"Dry-run actions: {len(actions)}; Bitrix24 writes: 0")


def _load_rules(path: Path) -> AuditRules:
    if not path.exists():
        return AuditRules()
    return AuditRules.model_validate_json(path.read_text(encoding="utf-8"))


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
    period: str,
) -> tuple[list[SourceRecord], list[Violation], str]:
    selected_departments = [department] if department else []
    if rop and isinstance(department_heads, dict):
        selected_departments = [
            str(key) for key, value in department_heads.items() if str(value) == rop
        ]
        if not selected_departments:
            raise typer.BadParameter("Для этого РОПа не найден отдел")
    if broker:
        records = [item for item in records if item.assigned_to_id == broker]
        scope = f"брокер {broker}, период {period}"
    elif selected_departments:
        records = [item for item in records if item.department_id in selected_departments]
        label = f"РОП {rop}" if rop else f"отдел {selected_departments[0]}"
        scope = f"{label}, период {period}"
    elif source:
        records = [item for item in records if item.source_channel_id == source]
        scope = f"источник {source}, период {period}"
    elif stage:
        records = [item for item in records if item.stage_id == stage]
        scope = f"стадия {stage}, период {period}"
    else:
        scope = f"все отделы, период {period}"
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


if __name__ == "__main__":
    app()
