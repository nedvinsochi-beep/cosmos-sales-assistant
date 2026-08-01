from __future__ import annotations

from collections import defaultdict
from collections.abc import AsyncIterator
from datetime import UTC, datetime
from typing import Any
from urllib.parse import urlsplit

from cosmos_control_tower.audit.rules import AuditRules, evaluate_record
from cosmos_control_tower.bitrix.client import BitrixClient
from cosmos_control_tower.models.records import SourceRecord, Violation

LEAD_FIELDS = [
    "ID",
    "STATUS_ID",
    "STATUS_SEMANTIC_ID",
    "SOURCE_ID",
    "ASSIGNED_BY_ID",
    "DATE_CREATE",
    "DATE_MODIFY",
    "UTM_SOURCE",
    "UTM_MEDIUM",
    "UTM_CAMPAIGN",
]

DEAL_FIELDS = [
    "ID",
    "CATEGORY_ID",
    "STAGE_ID",
    "STAGE_SEMANTIC_ID",
    "SOURCE_ID",
    "ASSIGNED_BY_ID",
    "DATE_CREATE",
    "DATE_MODIFY",
    "CLOSEDATE",
    "CLOSED",
    "UTM_SOURCE",
    "UTM_MEDIUM",
    "UTM_CAMPAIGN",
]

ACTIVITY_FIELDS = [
    "ID",
    "OWNER_TYPE_ID",
    "OWNER_ID",
    "TYPE_ID",
    "PROVIDER_ID",
    "RESPONSIBLE_ID",
    "COMPLETED",
    "DEADLINE",
    "CREATED",
    "LAST_UPDATED",
]


def _as_datetime(value: Any) -> datetime | None:
    if not value or not isinstance(value, str):
        return None
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None
    if parsed.tzinfo is None:
        return parsed.replace(tzinfo=UTC)
    return parsed


def _portal_origin(webhook_url: str) -> str:
    parsed = urlsplit(webhook_url)
    return f"{parsed.scheme}://{parsed.netloc}"


async def _bounded(
    rows: AsyncIterator[dict[str, Any]], limit: int | None
) -> list[dict[str, Any]]:
    result: list[dict[str, Any]] = []
    async for row in rows:
        result.append(row)
        if limit and len(result) >= limit:
            break
    return result


class OperationalService:
    """Build a structural, PII-free snapshot without changing Bitrix24."""

    def __init__(
        self,
        client: BitrixClient,
        webhook_url: str,
        rules: AuditRules,
        *,
        first_call_provider_ids: set[str] | None = None,
    ) -> None:
        self.client = client
        self.portal_origin = _portal_origin(webhook_url)
        self.rules = rules
        self.first_call_provider_ids = first_call_provider_ids or set()

    async def collect(self, *, limit: int | None = None) -> dict[str, Any]:
        active_users_payload = await self.client.call("user.get", {"FILTER[ACTIVE]": "Y"})
        inactive_users_payload = await self.client.call("user.get", {"FILTER[ACTIVE]": "N"})
        departments_payload = await self.client.call("department.get")
        active_users = self._rows(active_users_payload)
        inactive_users = self._rows(inactive_users_payload)
        users = active_users + inactive_users
        departments = self._rows(departments_payload)
        user_active = {
            str(user.get("ID")): user.get("ACTIVE") in {True, "Y"}
            for user in users
            if user.get("ID") is not None
        }
        user_departments = {
            str(user.get("ID")): self._first_department(user.get("UF_DEPARTMENT"))
            for user in users
            if user.get("ID") is not None
        }
        department_heads = {
            str(row.get("ID")): str(row.get("UF_HEAD"))
            for row in departments
            if row.get("ID") is not None and row.get("UF_HEAD")
        }

        leads = await _bounded(
            self.client.paginate("crm.lead.list", {"select[]": LEAD_FIELDS}), limit
        )
        deals = await _bounded(
            self.client.paginate("crm.deal.list", {"select[]": DEAL_FIELDS}), limit
        )
        activities = await _bounded(
            self.client.paginate("crm.activity.list", {"select[]": ACTIVITY_FIELDS}), limit
        )
        activity_index = self._activity_index(activities)

        records = [
            self._record(
                "lead",
                row,
                user_departments,
                user_active,
                activity_index,
                activity_data_complete=limit is None,
            )
            for row in leads
        ] + [
            self._record(
                "deal",
                row,
                user_departments,
                user_active,
                activity_index,
                activity_data_complete=limit is None,
            )
            for row in deals
        ]
        findings = [
            item
            for record in records
            if not record.is_closed
            for item in evaluate_record(record, self.rules)
        ]
        return {
            "generated_at": datetime.now(UTC).isoformat(),
            "mode": "live_read_only",
            "contains_personal_data": False,
            "portal_origin": self.portal_origin,
            "records": [record.model_dump(mode="json") for record in records],
            "violations": [finding.model_dump(mode="json") for finding in findings],
            "departments": sorted(set(filter(None, user_departments.values()))),
            "department_heads": department_heads,
            "employee_status_counts": {
                "active": len(active_users),
                "inactive": len(inactive_users),
            },
            "source_counts": {
                "leads": len(leads),
                "deals_main_pipeline": sum(
                    str(row.get("CATEGORY_ID", "0")) == "0" for row in deals
                ),
                "activities": len(activities),
            },
            "limitations": self._limitations(limited=limit is not None),
        }

    def _record(
        self,
        entity_type: str,
        row: dict[str, Any],
        user_departments: dict[str, str | None],
        user_active: dict[str, bool],
        activity_index: dict[tuple[str, str], list[dict[str, Any]]],
        *,
        activity_data_complete: bool,
    ) -> SourceRecord:
        source_id = str(row.get("ID", ""))
        owner_type = "1" if entity_type == "lead" else "2"
        activities = activity_index.get((owner_type, source_id), [])
        open_activities = [item for item in activities if item.get("COMPLETED") != "Y"]
        next_dates = [
            value
            for item in open_activities
            if (value := _as_datetime(item.get("DEADLINE"))) is not None
        ]
        activity_dates = [
            value
            for item in activities
            if (
                value := _as_datetime(item.get("LAST_UPDATED"))
                or _as_datetime(item.get("CREATED"))
            )
            is not None
        ]
        call_state: bool | None = None
        if self.first_call_provider_ids:
            call_state = any(
                str(item.get("PROVIDER_ID")) in self.first_call_provider_ids
                for item in activities
            )
        assignee = str(row.get("ASSIGNED_BY_ID")) if row.get("ASSIGNED_BY_ID") else None
        stage_id = str(row.get("STATUS_ID") or row.get("STAGE_ID") or "") or None
        semantic = str(row.get("STATUS_SEMANTIC_ID") or row.get("STAGE_SEMANTIC_ID") or "")
        is_won = semantic == "S" or stage_id in {"CONVERTED", "WON"}
        is_closed = semantic in {"S", "F"} or row.get("CLOSED") == "Y"
        return SourceRecord(
            entity_type=entity_type,
            source_id=source_id,
            assigned_to_id=assignee,
            assignee_active=user_active.get(assignee or ""),
            department_id=user_departments.get(assignee or ""),
            stage_id=stage_id,
            category_id=str(row.get("CATEGORY_ID")) if row.get("CATEGORY_ID") is not None else None,
            source_channel_id=str(row.get("SOURCE_ID")) if row.get("SOURCE_ID") else None,
            created_at=_as_datetime(row.get("DATE_CREATE")),
            updated_at=_as_datetime(row.get("DATE_MODIFY")),
            last_activity_at=max(activity_dates) if activity_dates else None,
            next_activity_at=min(next_dates) if next_dates else None,
            has_open_activity=bool(open_activities),
            has_first_call=call_state,
            activity_data_complete=activity_data_complete,
            is_closed=is_closed,
            is_won=is_won,
            card_url=f"{self.portal_origin}/crm/{entity_type}/details/{source_id}/",
        )

    @staticmethod
    def _rows(payload: dict[str, Any]) -> list[dict[str, Any]]:
        result = payload.get("result", [])
        if isinstance(result, dict):
            result = result.get("items", [])
        return [row for row in result if isinstance(row, dict)] if isinstance(result, list) else []

    @staticmethod
    def _first_department(value: Any) -> str | None:
        if isinstance(value, list) and value:
            return str(value[0])
        if value not in (None, ""):
            return str(value)
        return None

    @staticmethod
    def _activity_index(
        activities: list[dict[str, Any]],
    ) -> dict[tuple[str, str], list[dict[str, Any]]]:
        index: defaultdict[tuple[str, str], list[dict[str, Any]]] = defaultdict(list)
        for item in activities:
            owner_type = item.get("OWNER_TYPE_ID")
            owner_id = item.get("OWNER_ID")
            if owner_type is not None and owner_id is not None:
                index[(str(owner_type), str(owner_id))].append(item)
        return dict(index)

    def _limitations(self, *, limited: bool) -> list[str]:
        limitations = [
            "stage_history_unavailable",
            "commission_amount_unconfirmed",
            "meeting_outcome_unconfirmed",
            "loss_reason_field_unconfirmed",
        ]
        if not self.first_call_provider_ids:
            limitations.append("first_call_provider_unconfirmed")
        if limited:
            limitations.append("limited_sample_activity_rules_blocked")
        return limitations


def records_from_snapshot(snapshot: dict[str, Any]) -> list[SourceRecord]:
    rows = snapshot.get("records", [])
    if not isinstance(rows, list):
        return []
    return [SourceRecord.model_validate(row) for row in rows if isinstance(row, dict)]


def violations_from_snapshot(snapshot: dict[str, Any]) -> list[Violation]:
    rows = snapshot.get("violations", [])
    if not isinstance(rows, list):
        return []
    return [Violation.model_validate(row) for row in rows if isinstance(row, dict)]
