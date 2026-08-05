import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from cosmos_control_tower.audit.service import AuditService
from cosmos_control_tower.bitrix.client import BitrixClient


def _rows(payload: dict[str, Any]) -> list[dict[str, Any]]:
    result = payload.get("result", [])
    if isinstance(result, dict):
        result = result.get("items", result.get("tasks", []))
    return [row for row in result if isinstance(row, dict)] if isinstance(result, list) else []


def _only(rows: list[dict[str, Any]], keys: set[str]) -> list[dict[str, Any]]:
    return [{key: row[key] for key in keys if key in row} for row in rows]


class PortalAuditService:
    """Configuration-only portal inventory with no CRM entity writes or PII export."""

    def __init__(self, client: BitrixClient, output_dir: Path) -> None:
        self.client = client
        self.output_dir = output_dir

    async def _safe_call(self, method: str, params: dict[str, Any] | None = None) -> dict[str, Any]:
        try:
            return await self.client.call(method, params)
        except Exception as exc:  # noqa: BLE001 - partial audit is an expected outcome
            return {"status": "unavailable", "error_type": type(exc).__name__}

    def _write(self, name: str, payload: Any) -> None:
        (self.output_dir / name).write_text(
            json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
        )

    async def run(self) -> dict[str, Any]:
        self.output_dir.mkdir(parents=True, exist_ok=True)
        baseline = await AuditService(self.client, self.output_dir).run()
        methods = set(baseline.get("connection", {}).get("methods", {}).get("result", []))

        fields = dict(baseline.get("fields", {}))
        for method in ("crm.contact.fields", "crm.company.fields"):
            payload = await self._safe_call(method) if method in methods else {"status": "method_not_available"}
            fields[method] = AuditService._sanitize_field_definitions(payload)

        async def available(method: str, params: dict[str, Any] | None = None) -> dict[str, Any]:
            if method not in methods:
                return {"status": "method_not_available"}
            return await self._safe_call(method, params)

        groups_raw = await available("sonet_group.get", {"ORDER[ID]": "ASC"})
        groups = _only(_rows(groups_raw), {"ID", "NAME", "ACTIVE", "CLOSED", "PROJECT", "OWNER_ID"})
        task_fields_raw = await available("task.item.userfield.getlist")
        task_fields = _only(_rows(task_fields_raw), {"ID", "FIELD_NAME", "USER_TYPE_ID", "MULTIPLE", "MANDATORY"})

        automations: dict[str, Any] = {}
        for method in (
            "crm.automation.trigger.list",
            "bizproc.workflow.template.list",
            "bizproc.workflow.instance.list",
            "bizproc.robot.list",
            "bizproc.task.list",
        ):
            payload = await available(method)
            automations[method] = {
                "status": payload.get("status", "available"),
                "count": len(_rows(payload)),
                "items": _only(_rows(payload), {"ID", "NAME", "MODULE_ID", "ENTITY", "DOCUMENT_TYPE", "WORKFLOW_STATUS", "STATUS"}),
            }

        telephony: dict[str, Any] = {}
        for method in ("voximplant.line.get", "voximplant.sip.get"):
            payload = await available(method)
            telephony[method] = {
                "status": payload.get("status", "available"),
                "count": len(_rows(payload)),
                "items": _only(_rows(payload), {"ID", "TYPE", "STATUS", "ACTIVE", "LINE_NAME"}),
            }

        storage_raw = await available("disk.storage.getlist")
        sites_raw = await available("landing.site.getlist", {"filter[TYPE]": "KNOWLEDGE"})
        knowledge = {
            "disk_storages": _only(_rows(storage_raw), {"ID", "ENTITY_TYPE", "MODULE_ID"}),
            "knowledge_sites": _only(_rows(sites_raw), {"ID", "TYPE", "ACTIVE", "DELETED"}),
            "content_exported": False,
        }

        smart_methods = sorted(name for name in methods if name.startswith(("crm.type.", "crm.item.")))
        smart_inventory_available = "crm.type.list" in methods
        smart_processes = {
            "status": "available" if smart_inventory_available else "method_not_available",
            "available_methods": smart_methods,
            "items": [],
            "note": "No smart-process records were requested when universal CRM type methods were unavailable.",
        }

        metadata = baseline.get("metadata", {})
        users_departments = {
            "personal_data_removed": True,
            "users": metadata.get("user.get", {}),
            "departments": metadata.get("department.get", {}),
        }
        pipelines = {
            "categories": metadata.get("crm.dealcategory.list", {}),
            "stages": baseline.get("category_stages", {}),
            "statuses_and_sources": metadata.get("crm.status.list", {}),
        }
        self._write("users-departments.json", users_departments)
        self._write("crm-pipelines.json", pipelines)
        self._write("crm-fields.json", fields)
        self._write("smart-processes.json", smart_processes)
        self._write("automations.json", automations)
        self._write("telephony.json", telephony)
        self._write("knowledge-bases.json", knowledge)
        self._write("tasks-groups.json", {"groups": groups, "task_user_fields": task_fields, "task_templates": {"status": "method_not_available"}})

        summary = {
            "checked_at_utc": datetime.now(UTC).isoformat(),
            "scope_count": len(baseline.get("connection", {}).get("scopes", {}).get("result", [])),
            "method_count": len(methods),
            "department_count": metadata.get("department.get", {}).get("count", 0),
            "active_user_count": metadata.get("user.get", {}).get("count", 0),
            "pipeline_count": metadata.get("crm.dealcategory.list", {}).get("count", 0),
            "group_count": len(groups),
            "capabilities": baseline.get("capabilities", {}),
            "writes_performed": 0,
        }
        self._write("audit-summary.json", summary)
        return summary
