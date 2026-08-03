from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

import pytest
from typer.testing import CliRunner

from cosmos_control_tower.acceptance.models import OrganizationMap
from cosmos_control_tower.cli.app import app
from cosmos_control_tower.models.records import SourceRecord
from cosmos_control_tower.rules_engine.config import load_rules
from cosmos_control_tower.rules_engine.engine import RulesEngine
from cosmos_control_tower.rules_engine.models import RuleMode

AS_OF = datetime(2026, 8, 3, 23, 50, tzinfo=ZoneInfo("Europe/Moscow"))
CONFIG = Path("config/rules.example.json")


def _rule(rule_id: str):
    return next(item for item in load_rules(CONFIG) if item.rule_id == rule_id)


def test_config_contains_two_safe_rules() -> None:
    rules = load_rules(CONFIG)

    assert [item.rule_id for item in rules] == ["MISSED_LEAD_ACCEPTANCE", "NO_NEXT_STEP"]
    assert all(item.mode in {RuleMode.OFF, RuleMode.DRY_RUN} for item in rules)


def test_no_next_step_is_blocked_when_task_evidence_is_missing() -> None:
    record = SourceRecord(
        entity_type="lead",
        source_id="10",
        assigned_to_id="100",
        assignee_active=True,
        department_id="2",
        stage_id="IN_PROCESS",
        has_open_activity=False,
        task_data_complete=False,
    )
    result = RulesEngine().run(
        _rule("NO_NEXT_STEP"),
        [record],
        {"2": "200"},
        OrganizationMap(),
        as_of=AS_OF,
    )

    assert result.violations_found == 0
    assert result.blocked_by_data == 1
    assert result.previews[0].evidence_status == "BLOCKED_BY_DATA"
    assert result.kpi["brokers"][0]["without_next_step"] == 0
    assert result.kpi["brokers"][0]["blocked_candidates"] == 1
    assert result.writes_performed == 0


def test_no_next_step_confirmed_and_idempotent_with_complete_evidence() -> None:
    record = SourceRecord(
        entity_type="lead",
        source_id="10",
        assigned_to_id="100",
        assignee_active=True,
        department_id="2",
        stage_id="IN_PROCESS",
        has_open_activity=False,
        task_data_complete=True,
    )
    engine = RulesEngine()
    first = engine.run(
        _rule("NO_NEXT_STEP"),
        [record],
        {"2": "200"},
        OrganizationMap(),
        as_of=AS_OF,
    )
    second = engine.run(
        _rule("NO_NEXT_STEP"),
        [record],
        {"2": "200"},
        OrganizationMap(),
        as_of=AS_OF,
        processed_keys={first.previews[0].idempotency_key},
    )

    assert first.violations_found == 1
    assert first.planned_actions == 3
    assert second.violations_found == 0
    assert second.exclusions["already_processed_in_window"] == 1


def test_active_mode_and_apply_are_blocked(tmp_path: Path) -> None:
    active = _rule("NO_NEXT_STEP").model_copy(update={"mode": RuleMode.ACTIVE})
    with pytest.raises(PermissionError, match="ACTIVE mode is blocked"):
        RulesEngine().run(active, [], {}, OrganizationMap(), as_of=AS_OF)

    result = CliRunner().invoke(app, ["rules", "run-all", "--apply"])
    assert result.exit_code == 2
    assert "APPLY заблокирован" in result.output
    one_rule = CliRunner().invoke(app, ["rules", "apply", "NO_NEXT_STEP"])
    assert one_rule.exit_code == 2
    assert "APPLY заблокирован" in one_rule.output


def test_rules_cli_demo_generates_unified_dashboard(tmp_path: Path) -> None:
    runner = CliRunner()
    listed = runner.invoke(app, ["rules", "list"])
    assert listed.exit_code == 0
    assert "MISSED_LEAD_ACCEPTANCE" in listed.output
    assert "NO_NEXT_STEP" in listed.output

    result = runner.invoke(
        app,
        ["rules", "run-all", "--dry-run", "--demo", "--output", str(tmp_path)],
    )
    assert result.exit_code == 0, result.output
    assert "Bitrix24 writes: 0" in result.output
    assert (tmp_path / "rules-dashboard.html").exists()
    assert (tmp_path / "rules-report.json").exists()
