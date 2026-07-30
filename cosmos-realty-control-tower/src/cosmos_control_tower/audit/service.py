import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from cosmos_control_tower.audit.redaction import redact_record
from cosmos_control_tower.audit.rules import AuditRules
from cosmos_control_tower.bitrix.client import READ_ONLY_METHODS, BitrixClient


class AuditService:
    def __init__(self, client: BitrixClient, output_dir: Path) -> None:
        self.client = client
        self.output_dir = output_dir

    async def run(self) -> dict[str, Any]:
        self.output_dir.mkdir(parents=True, exist_ok=True)
        discovered: dict[str, Any] = {"checked_at_utc": datetime.now(UTC).isoformat()}

        for method, key in (("app.info", "app"), ("scope", "scopes"), ("methods", "methods")):
            try:
                discovered[key] = redact_record(await self.client.call(method))
            except Exception as exc:  # noqa: BLE001 - audit must report partial access
                discovered[key] = {"status": "unavailable", "error_type": type(exc).__name__}

        available = set(discovered.get("methods", {}).get("result", []))
        fields: dict[str, Any] = {}
        for method in ("crm.lead.fields", "crm.deal.fields", "crm.activity.fields"):
            if not available or method in available:
                try:
                    fields[method] = redact_record(await self.client.call(method))
                except Exception as exc:  # noqa: BLE001
                    fields[method] = {"status": "unavailable", "error_type": type(exc).__name__}

        snapshot = {
            "metadata_only": True,
            "personal_data_removed": True,
            "approved_read_methods": sorted(READ_ONLY_METHODS),
            "connection": discovered,
            "fields": fields,
        }
        (self.output_dir / "technical-audit.json").write_text(
            json.dumps(snapshot, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
        )
        return snapshot


def load_rules(path: Path) -> AuditRules:
    return AuditRules.model_validate_json(path.read_text(encoding="utf-8"))
