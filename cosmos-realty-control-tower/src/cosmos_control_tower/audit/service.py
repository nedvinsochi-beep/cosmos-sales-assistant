import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from cosmos_control_tower.audit.redaction import redact_record
from cosmos_control_tower.audit.rules import AuditRules
from cosmos_control_tower.bitrix.client import READ_ONLY_METHODS, BitrixClient

SAMPLE_LIMIT = 5

SAMPLE_QUERIES: dict[str, tuple[str, list[str]]] = {
    "leads": (
        "crm.lead.list",
        [
            "ID",
            "STATUS_ID",
            "SOURCE_ID",
            "ASSIGNED_BY_ID",
            "DATE_CREATE",
            "DATE_MODIFY",
            "HAS_PHONE",
            "HAS_EMAIL",
            "UTM_SOURCE",
            "UTM_MEDIUM",
            "UTM_CAMPAIGN",
        ],
    ),
    "deals": (
        "crm.deal.list",
        [
            "ID",
            "CATEGORY_ID",
            "STAGE_ID",
            "SOURCE_ID",
            "ASSIGNED_BY_ID",
            "DATE_CREATE",
            "DATE_MODIFY",
            "CLOSEDATE",
            "UTM_SOURCE",
            "UTM_MEDIUM",
            "UTM_CAMPAIGN",
        ],
    ),
    "tasks": (
        "task.item.list",
        [
            "ID",
            "STATUS",
            "RESPONSIBLE_ID",
            "GROUP_ID",
            "CREATED_DATE",
            "DEADLINE",
            "CLOSED_DATE",
        ],
    ),
    "activities": (
        "crm.activity.list",
        [
            "ID",
            "OWNER_TYPE_ID",
            "OWNER_ID",
            "TYPE_ID",
            "PROVIDER_ID",
            "RESPONSIBLE_ID",
            "DIRECTION",
            "COMPLETED",
            "DEADLINE",
            "LAST_UPDATED",
        ],
    ),
}


class AuditService:
    def __init__(self, client: BitrixClient, output_dir: Path) -> None:
        self.client = client
        self.output_dir = output_dir

    async def run(self) -> dict[str, Any]:
        self.output_dir.mkdir(parents=True, exist_ok=True)
        discovered: dict[str, Any] = {"checked_at_utc": datetime.now(UTC).isoformat()}

        for method, key in (
            ("app.info", "app"),
            ("profile", "profile"),
            ("scope", "scopes"),
            ("methods", "methods"),
            ("server.time", "server_time"),
        ):
            try:
                discovered[key] = redact_record(await self.client.call(method))
            except Exception as exc:  # noqa: BLE001 - audit must report partial access
                discovered[key] = {"status": "unavailable", "error_type": type(exc).__name__}

        available = set(discovered.get("methods", {}).get("result", []))
        fields: dict[str, Any] = {}
        for method in ("crm.lead.fields", "crm.deal.fields", "crm.activity.fields"):
            if not available or method in available:
                try:
                    fields[method] = self._sanitize_field_definitions(
                        await self.client.call(method)
                    )
                except Exception as exc:  # noqa: BLE001
                    fields[method] = {"status": "unavailable", "error_type": type(exc).__name__}

        metadata: dict[str, Any] = {}
        metadata_calls: tuple[tuple[str, dict[str, Any]], ...] = (
            ("department.get", {}),
            ("user.get", {"FILTER[ACTIVE]": "Y"}),
            ("crm.dealcategory.list", {}),
            ("crm.dealcategory.default.get", {}),
            ("crm.status.entity.types", {}),
            ("crm.status.list", {}),
            ("crm.activity.type.list", {}),
        )
        for method, params in metadata_calls:
            if available and method not in available:
                metadata[method] = {"status": "method_not_available"}
                continue
            try:
                payload = await self.client.call(method, params)
                metadata[method] = self._sanitize_metadata(method, payload)
            except Exception as exc:  # noqa: BLE001
                metadata[method] = {"status": "unavailable", "error_type": type(exc).__name__}

        categories = metadata.get("crm.dealcategory.list", {}).get("result", [])
        default_category = metadata.get("crm.dealcategory.default.get", {}).get("result")
        category_ids = {
            str(category["ID"])
            for category in categories
            if isinstance(category, dict) and "ID" in category
        }
        if isinstance(default_category, dict) and "ID" in default_category:
            category_ids.add(str(default_category["ID"]))
        elif isinstance(default_category, (str, int)):
            category_ids.add(str(default_category))
        category_stages: dict[str, Any] = {}
        can_read_stages = not available or "crm.dealcategory.stage.list" in available
        if can_read_stages:
            for category_id in sorted(category_ids):
                try:
                    payload = await self.client.call(
                        "crm.dealcategory.stage.list", {"id": category_id}
                    )
                    category_stages[category_id] = self._sanitize_metadata(
                        "crm.dealcategory.stage.list", payload
                    )
                except Exception as exc:  # noqa: BLE001
                    category_stages[category_id] = {
                        "status": "unavailable",
                        "error_type": type(exc).__name__,
                    }

        samples: dict[str, Any] = {}
        for name, (method, select_fields) in SAMPLE_QUERIES.items():
            if available and method not in available:
                samples[name] = {"status": "method_not_available", "records": []}
                continue
            try:
                sample_params: dict[str, Any]
                if method == "task.item.list":
                    sample_params = {
                        "ORDER[ID]": "DESC",
                        "FILTER[ID]": ">0",
                        "PARAMS[NAV_PARAMS][nPageSize]": SAMPLE_LIMIT,
                    }
                else:
                    sample_params = {"select[]": select_fields, "start": 0}
                payload = await self.client.call(
                    method,
                    sample_params,
                )
                samples[name] = {
                    "status": "ok",
                    "limit": SAMPLE_LIMIT,
                    "records": self._safe_sample(method, payload),
                }
            except Exception as exc:  # noqa: BLE001
                samples[name] = {
                    "status": "unavailable",
                    "error_type": type(exc).__name__,
                    "records": [],
                }

        method_names = sorted(available)
        capabilities = {
            "tasks": any(name.startswith(("task.", "tasks.")) for name in method_names),
            "telephony": any(
                name.startswith(("telephony.", "voximplant.")) for name in method_names
            ),
            "stage_history": any("stagehistory" in name.lower() for name in method_names),
            "utm_fields": self._has_field_prefix(fields, "UTM_"),
            "sources": self._has_status_entity(metadata, "SOURCE"),
        }

        snapshot = {
            "metadata_only": True,
            "personal_data_removed": True,
            "approved_read_methods": sorted(READ_ONLY_METHODS),
            "connection": discovered,
            "fields": fields,
            "metadata": metadata,
            "category_stages": category_stages,
            "capabilities": capabilities,
            "samples": samples,
        }
        (self.output_dir / "technical-audit.json").write_text(
            json.dumps(snapshot, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
        )
        return snapshot

    @staticmethod
    def _result_rows(payload: dict[str, Any]) -> list[dict[str, Any]]:
        result = payload.get("result", [])
        if isinstance(result, dict) and isinstance(result.get("items"), list):
            result = result["items"]
        if not isinstance(result, list):
            return []
        return [row for row in result if isinstance(row, dict)]

    @classmethod
    def _safe_sample(cls, method: str, payload: dict[str, Any]) -> list[dict[str, Any]]:
        allowed = {
            field
            for candidate_method, fields in SAMPLE_QUERIES.values()
            if candidate_method == method
            for field in fields
        }
        return [
            {key: redact_record({key: value})[key] for key, value in row.items() if key in allowed}
            for row in cls._result_rows(payload)[:SAMPLE_LIMIT]
        ]

    @classmethod
    def _sanitize_metadata(cls, method: str, payload: dict[str, Any]) -> dict[str, Any]:
        if method == "crm.dealcategory.default.get":
            result = payload.get("result", {})
            allowed = {"ID", "NAME", "SORT", "IS_DEFAULT"}
            if isinstance(result, dict):
                return {"result": {key: value for key, value in result.items() if key in allowed}}
            return {"result": result}
        rows = cls._result_rows(payload)
        if method == "user.get":
            safe = [
                {
                    key: value
                    for key, value in row.items()
                    if key in {"ID", "ACTIVE", "ADMIN", "USER_TYPE", "UF_DEPARTMENT"}
                }
                for row in rows
            ]
            return {"result": safe, "count": len(safe)}
        if method == "department.get":
            safe = [
                {
                    key: value
                    for key, value in row.items()
                    if key in {"ID", "NAME", "SORT", "PARENT", "UF_HEAD"}
                }
                for row in rows
            ]
            return {"result": safe, "count": len(safe)}
        metadata_keys = {
            "crm.dealcategory.list": {"ID", "NAME", "SORT", "IS_DEFAULT"},
            "crm.dealcategory.stage.list": {
                "ID",
                "STATUS_ID",
                "NAME",
                "SORT",
                "SYSTEM",
            },
            "crm.status.entity.types": {"ID", "ENTITY_ID", "NAME"},
            "crm.status.list": {
                "ID",
                "ENTITY_ID",
                "STATUS_ID",
                "NAME",
                "SORT",
                "SYSTEM",
            },
            "crm.activity.type.list": {"ID", "NAME"},
        }
        if method in metadata_keys:
            allowed = metadata_keys[method]
            safe = [{key: value for key, value in row.items() if key in allowed} for row in rows]
            return {"result": safe, "count": len(safe)}
        return redact_record(payload)

    @staticmethod
    def _sanitize_field_definitions(payload: dict[str, Any]) -> dict[str, Any]:
        result = payload.get("result", {})
        if not isinstance(result, dict):
            return {"result": {}}
        allowed = {
            "type",
            "isRequired",
            "isReadOnly",
            "isImmutable",
            "isMultiple",
            "isDynamic",
            "title",
            "listLabel",
            "formLabel",
            "filterLabel",
            "settings",
        }
        return {
            "result": {
                field_name: {
                    key: value for key, value in definition.items() if key in allowed
                }
                for field_name, definition in result.items()
                if isinstance(definition, dict)
            }
        }

    @staticmethod
    def _has_field_prefix(fields: dict[str, Any], prefix: str) -> bool:
        for payload in fields.values():
            result = payload.get("result", {}) if isinstance(payload, dict) else {}
            if isinstance(result, dict) and any(str(name).startswith(prefix) for name in result):
                return True
        return False

    @staticmethod
    def _has_status_entity(metadata: dict[str, Any], entity_id: str) -> bool:
        payload = metadata.get("crm.status.entity.types", {})
        return entity_id in json.dumps(payload, ensure_ascii=False)


def load_rules(path: Path) -> AuditRules:
    return AuditRules.model_validate_json(path.read_text(encoding="utf-8"))
