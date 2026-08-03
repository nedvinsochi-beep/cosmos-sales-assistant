from __future__ import annotations

from datetime import datetime
from typing import Any
from urllib.parse import urlsplit

from cosmos_control_tower.bitrix.client import BitrixClient
from cosmos_control_tower.models.records import SourceRecord

LEAD_FIELDS = [
    "ID",
    "STATUS_ID",
    "STATUS_SEMANTIC_ID",
    "ASSIGNED_BY_ID",
    "DATE_CREATE",
    "DATE_MODIFY",
    "MOVED_TIME",
]


class AcceptanceService:
    def __init__(self, client: BitrixClient, webhook_url: str) -> None:
        self.client = client
        parsed = urlsplit(webhook_url)
        self.portal_origin = f"{parsed.scheme}://{parsed.netloc}"

    async def collect(self, *, day_start: datetime) -> dict[str, Any]:
        active_payload = await self.client.call("user.get", {"FILTER[ACTIVE]": "Y"})
        inactive_payload = await self.client.call("user.get", {"FILTER[ACTIVE]": "N"})
        departments_payload = await self.client.call("department.get")
        active_users = self._rows(active_payload)
        inactive_users = self._rows(inactive_payload)
        users = active_users + inactive_users
        user_active = {
            str(item.get("ID")): item.get("ACTIVE") in {True, "Y"}
            for item in users
            if item.get("ID") is not None
        }
        user_departments = {
            str(item.get("ID")): self._first_department(item.get("UF_DEPARTMENT"))
            for item in users
            if item.get("ID") is not None
        }
        departments = self._rows(departments_payload)
        heads = {
            str(item.get("ID")): str(item.get("UF_HEAD"))
            for item in departments
            if item.get("ID") is not None and item.get("UF_HEAD")
        }

        new_rows = [
            row
            async for row in self.client.paginate(
                "crm.lead.list",
                {"filter[STATUS_ID]": "NEW", "select[]": LEAD_FIELDS},
            )
        ]
        today_rows = [
            row
            async for row in self.client.paginate(
                "crm.lead.list",
                {
                    "filter[>=DATE_CREATE]": day_start.isoformat(),
                    "select[]": LEAD_FIELDS,
                },
            )
        ]
        merged = {
            str(row.get("ID")): row for row in new_rows + today_rows if row.get("ID") is not None
        }
        records = [self._record(row, user_active, user_departments) for row in merged.values()]
        return {
            "generated_at": datetime.now(day_start.tzinfo).isoformat(),
            "mode": "live_read_only",
            "contains_personal_data": False,
            "records": [item.model_dump(mode="json") for item in records],
            "department_heads": heads,
            "source_counts": {
                "current_new": len(new_rows),
                "created_today": len(today_rows),
                "merged": len(records),
            },
            "limitations": [
                "ASSIGNED_BY_ID timestamp is unavailable",
                "MOVED_TIME is stage movement time, not assignment time",
            ],
        }

    def _record(
        self,
        row: dict[str, Any],
        user_active: dict[str, bool],
        user_departments: dict[str, str | None],
    ) -> SourceRecord:
        lead_id = str(row.get("ID", ""))
        assigned = str(row.get("ASSIGNED_BY_ID")) if row.get("ASSIGNED_BY_ID") else None
        semantic = str(row.get("STATUS_SEMANTIC_ID") or "")
        return SourceRecord(
            entity_type="lead",
            source_id=lead_id,
            assigned_to_id=assigned,
            assigned_at=None,
            assignee_active=user_active.get(assigned or ""),
            department_id=user_departments.get(assigned or ""),
            stage_id=str(row.get("STATUS_ID")) if row.get("STATUS_ID") else None,
            created_at=_as_datetime(row.get("DATE_CREATE")),
            updated_at=_as_datetime(row.get("DATE_MODIFY")),
            stage_changed_at=_as_datetime(row.get("MOVED_TIME")),
            is_closed=semantic in {"S", "F"},
            is_won=semantic == "S",
            card_url=f"{self.portal_origin}/crm/lead/details/{lead_id}/",
        )

    @staticmethod
    def _rows(payload: dict[str, Any]) -> list[dict[str, Any]]:
        result = payload.get("result", [])
        if not isinstance(result, list):
            return []
        return [item for item in result if isinstance(item, dict)]

    @staticmethod
    def _first_department(value: Any) -> str | None:
        if isinstance(value, list) and value:
            return str(value[0])
        return str(value) if value not in (None, "") else None


def _as_datetime(value: Any) -> datetime | None:
    if not isinstance(value, str) or not value:
        return None
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None
