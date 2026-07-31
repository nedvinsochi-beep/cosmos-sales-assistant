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
from cosmos_control_tower.models.records import SourceRecord
from cosmos_control_tower.reports.generator import generate_reports

app = typer.Typer(help="Cosmos Realty Control Tower read-only tools")


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


if __name__ == "__main__":
    app()
