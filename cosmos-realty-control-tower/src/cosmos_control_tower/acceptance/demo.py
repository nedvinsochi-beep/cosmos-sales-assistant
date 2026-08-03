from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

from cosmos_control_tower.models.records import SourceRecord


def acceptance_demo_snapshot(as_of: datetime) -> dict[str, object]:
    zone = ZoneInfo("Europe/Moscow")
    local = as_of.astimezone(zone)
    records = [
        SourceRecord(
            entity_type="lead",
            source_id="demo-missed",
            assigned_to_id="101",
            assigned_at=local.replace(hour=18, minute=30),
            assignee_active=True,
            department_id="2",
            stage_id="NEW",
            created_at=local.replace(hour=18, minute=25),
        ),
        SourceRecord(
            entity_type="lead",
            source_id="demo-accepted",
            assigned_to_id="102",
            assigned_at=local.replace(hour=21, minute=10),
            assignee_active=True,
            department_id="2",
            stage_id="IN_PROCESS",
            created_at=local.replace(hour=21, minute=5),
        ),
        SourceRecord(
            entity_type="lead",
            source_id="demo-old",
            assigned_to_id="101",
            assigned_at=local - timedelta(days=1),
            assignee_active=True,
            department_id="2",
            stage_id="NEW",
            created_at=local - timedelta(days=1),
        ),
        SourceRecord(
            entity_type="lead",
            source_id="demo-unassigned",
            stage_id="NEW",
            created_at=local.replace(hour=20, minute=0),
        ),
    ]
    return {
        "generated_at": local.isoformat(),
        "mode": "demo",
        "contains_personal_data": False,
        "records": [item.model_dump(mode="json") for item in records],
        "department_heads": {"2": "201"},
    }
