from datetime import UTC, datetime, timedelta
from pathlib import Path

import httpx
import pytest

from cosmos_control_tower.audit.rules import AuditRules, evaluate_record
from cosmos_control_tower.bitrix.client import BitrixClient
from cosmos_control_tower.metrics.operational import build_dashboard_data
from cosmos_control_tower.models.records import SourceRecord
from cosmos_control_tower.operational.service import OperationalService
from cosmos_control_tower.reports.operational import generate_operational_reports
from cosmos_control_tower.robots.dry_run import preview_actions


def test_dashboard_and_dry_run_do_not_claim_blocked_conversions(tmp_path: Path) -> None:
    now = datetime(2026, 1, 5, tzinfo=UTC)
    record = SourceRecord(
        entity_type="lead",
        source_id="safe-1",
        assigned_to_id="10",
        department_id="2",
        stage_id="NEW",
        created_at=now - timedelta(hours=80),
        has_open_activity=False,
        has_first_call=False,
    )
    findings = evaluate_record(record, AuditRules(), now=now)
    dashboard = build_dashboard_data([record], findings, generated_at=now.isoformat())
    actions = preview_actions(findings)
    generate_operational_reports(tmp_path, dashboard, actions, scope="отдел 2")

    assert dashboard["conversion"]["status"] == "BLOCKED_BY_DATA"
    assert dashboard["summary"]["inactive_72"] == 1
    assert actions
    assert all(action.dry_run for action in actions)
    assert (tmp_path / "rop-dashboard.html").exists()
    assert (tmp_path / "rop-report.md").exists()
    assert "НЕ ВЫПОЛНЕНО" in (tmp_path / "rop-dashboard.html").read_text()


def test_closed_records_do_not_require_current_control() -> None:
    record = SourceRecord(
        entity_type="deal",
        source_id="closed",
        stage_id="WON",
        is_closed=True,
        is_won=True,
        has_open_activity=False,
        has_first_call=True,
    )
    dashboard = build_dashboard_data([record], [])
    assert dashboard["summary"]["active_records"] == 0
    assert dashboard["summary"]["violations"] == 0


@pytest.mark.asyncio
async def test_live_collector_reads_only_structural_fields_and_masks_webhook() -> None:
    seen_methods: list[str] = []

    async def handler(request: httpx.Request) -> httpx.Response:
        method = request.url.path.rsplit("/", 1)[-1].removesuffix(".json")
        seen_methods.append(method)
        responses = {
            "user.get": {
                "result": [{"ID": "10", "ACTIVE": True, "UF_DEPARTMENT": ["2"]}]
            },
            "department.get": {"result": [{"ID": "2", "UF_HEAD": "20"}]},
            "crm.lead.list": {
                "result": [
                    {
                        "ID": "1",
                        "STATUS_ID": "NEW",
                        "ASSIGNED_BY_ID": "10",
                        "DATE_CREATE": "2026-01-01T10:00:00+03:00",
                    }
                ]
            },
            "crm.deal.list": {"result": []},
            "crm.activity.list": {"result": []},
        }
        return httpx.Response(200, json=responses[method])

    webhook = "https://portal.example/rest/1/fake/"
    client = BitrixClient(webhook, rate_limit_per_second=10, transport=httpx.MockTransport(handler))
    snapshot = await OperationalService(client, webhook, AuditRules()).collect(limit=1)
    await client.close()

    serialized = str(snapshot)
    assert "/rest/1/fake" not in serialized
    assert snapshot["records"][0]["card_url"] == "https://portal.example/crm/lead/details/1/"
    assert snapshot["records"][0]["activity_data_complete"] is False
    assert all(item["status"] == "BLOCKED_BY_DATA" for item in snapshot["violations"])
    assert set(seen_methods) == {
        "user.get",
        "department.get",
        "crm.lead.list",
        "crm.deal.list",
        "crm.activity.list",
    }
    assert snapshot["contains_personal_data"] is False
