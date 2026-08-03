from datetime import datetime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

from typer.testing import CliRunner

from cosmos_control_tower.acceptance.engine import evaluate_acceptance
from cosmos_control_tower.acceptance.models import AcceptanceRule, OrganizationMap
from cosmos_control_tower.cli.app import app
from cosmos_control_tower.models.records import SourceRecord

ZONE = ZoneInfo("Europe/Moscow")
AS_OF = datetime(2026, 8, 3, 23, 50, tzinfo=ZONE)


def _lead(**updates: object) -> SourceRecord:
    values: dict[str, object] = {
        "entity_type": "lead",
        "source_id": "100",
        "assigned_to_id": "10",
        "assigned_at": AS_OF.replace(hour=18),
        "assignee_active": True,
        "department_id": "2",
        "stage_id": "NEW",
        "created_at": AS_OF.replace(hour=17),
    }
    values.update(updates)
    return SourceRecord.model_validate(values)


def _evaluate(records: list[SourceRecord], processed: set[str] | None = None):
    return evaluate_acceptance(
        records,
        {"2": "20"},
        OrganizationMap(poteryashka_user_id="99"),
        AcceptanceRule(),
        as_of=AS_OF,
        processed_keys=processed,
    )


def test_acceptance_preview_contains_safe_future_action() -> None:
    report = _evaluate([_lead()])

    assert report.eligible_to_return == 1
    assert report.writes_performed == 0
    action = report.actions[0]
    assert action.original_assigned_user_id == "10"
    assert action.rop_user_id == "20"
    assert action.proposed_updates["OBSERVER_IDS_ADD"] == ["10", "99"]
    assert "MISSED_ACCEPTANCE_SLA" in action.proposed_updates["SERVICE_FLAGS_ADD"]


def test_acceptance_exclusions_and_missing_assignment_time() -> None:
    records = [
        _lead(source_id="accepted", stage_id="IN_PROCESS"),
        _lead(source_id="pool", assigned_to_id=None),
        _lead(source_id="inactive", assignee_active=False),
        _lead(source_id="old", assigned_at=AS_OF - timedelta(days=1)),
        _lead(source_id="unknown-time", assigned_at=None),
    ]
    report = _evaluate(records)

    assert report.eligible_to_return == 0
    assert len(report.blocked_candidates) == 1
    assert report.blocked_candidates[0].reason == "assignment_timestamp_unavailable"
    assert report.exclusions == {
        "not_in_distribution_stage": 1,
        "unassigned_pool": 1,
        "inactive_or_unknown_employee": 1,
        "assigned_on_another_day": 1,
    }


def test_acceptance_preview_is_idempotent_against_ledger() -> None:
    first = _evaluate([_lead()])
    second = _evaluate([_lead()], {first.actions[0].idempotency_key})

    assert second.eligible_to_return == 0
    assert second.exclusions["already_processed"] == 1


def test_acceptance_cli_demo_and_apply_gate(tmp_path: Path) -> None:
    runner = CliRunner()
    demo = runner.invoke(
        app,
        [
            "acceptance-control",
            "--dry-run",
            "--as-of",
            "23:50",
            "--demo",
            "--output",
            str(tmp_path),
        ],
    )
    assert demo.exit_code == 0, demo.output
    assert "Eligible actions: 1" in demo.output
    assert "Bitrix24 writes: 0" in demo.output
    assert (tmp_path / "acceptance-report.html").exists()

    apply = runner.invoke(app, ["acceptance-control", "--apply"])
    assert apply.exit_code == 2
    assert "APPLY заблокирован" in apply.output
