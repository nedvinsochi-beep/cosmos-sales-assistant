from datetime import UTC, datetime, timedelta
from typing import Any

from cosmos_control_tower.audit.rules import AuditRules, evaluate_record
from cosmos_control_tower.models.records import SourceRecord


def demo_snapshot(now: datetime | None = None) -> dict[str, Any]:
    now = now or datetime.now(UTC)
    records = [
        SourceRecord(
            entity_type="lead",
            source_id="demo-lead-1",
            assigned_to_id="101",
            assignee_active=True,
            department_id="2",
            stage_id="NEW",
            source_channel_id="WEB",
            created_at=now - timedelta(hours=30),
            has_open_activity=False,
            has_first_call=False,
            card_url=None,
        ),
        SourceRecord(
            entity_type="lead",
            source_id="demo-lead-2",
            assigned_to_id="102",
            assignee_active=True,
            department_id="2",
            stage_id="UC_JTIRDL",
            source_channel_id="CALL",
            created_at=now - timedelta(days=4),
            last_activity_at=now - timedelta(hours=50),
            next_activity_at=now + timedelta(hours=3),
            has_open_activity=True,
            has_first_call=True,
        ),
        SourceRecord(
            entity_type="deal",
            source_id="demo-deal-1",
            assigned_to_id="101",
            assignee_active=True,
            department_id="2",
            category_id="0",
            stage_id="UC_AHUAA7",
            created_at=now - timedelta(days=12),
            last_activity_at=now - timedelta(hours=74),
            next_activity_at=now - timedelta(hours=2),
            has_open_activity=True,
            has_first_call=True,
        ),
        SourceRecord(
            entity_type="deal",
            source_id="demo-deal-2",
            assigned_to_id="103",
            assignee_active=True,
            department_id="3",
            category_id="0",
            stage_id="PREPARATION",
            created_at=now - timedelta(days=5),
            last_activity_at=now - timedelta(hours=8),
            next_activity_at=now + timedelta(days=1),
            has_open_activity=True,
            has_first_call=True,
        ),
        SourceRecord(
            entity_type="deal",
            source_id="demo-deal-3",
            assigned_to_id="103",
            assignee_active=True,
            department_id="3",
            category_id="0",
            stage_id="UC_NKAFJV",
            created_at=now - timedelta(days=20),
            last_activity_at=now - timedelta(hours=2),
            has_open_activity=False,
            has_first_call=True,
        ),
        SourceRecord(
            entity_type="deal",
            source_id="demo-deal-4",
            assigned_to_id="102",
            assignee_active=True,
            department_id="2",
            category_id="0",
            stage_id="WON",
            created_at=now - timedelta(days=25),
            last_activity_at=now - timedelta(hours=3),
            has_open_activity=False,
            has_first_call=True,
            is_closed=True,
            is_won=True,
        ),
    ]
    rules = AuditRules(
        inactive_thresholds_hours=[24, 48, 72],
        stage_age_limits_hours={},
        required_fields_by_stage={},
        first_call_activity_types=["CALL"],
    )
    violations = [item for record in records for item in evaluate_record(record, rules, now=now)]
    return {
        "generated_at": now.isoformat(),
        "mode": "demo",
        "contains_personal_data": False,
        "records": [record.model_dump(mode="json") for record in records],
        "violations": [item.model_dump(mode="json") for item in violations],
        "department_heads": {"2": "201", "3": "202"},
        "limitations": [
            "fixture_data",
            "stage_history_unavailable",
            "commission_amount_unconfirmed",
        ],
    }
