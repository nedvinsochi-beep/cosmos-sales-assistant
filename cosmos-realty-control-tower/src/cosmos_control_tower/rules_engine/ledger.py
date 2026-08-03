from __future__ import annotations

import json
from pathlib import Path
from typing import Any


def load_processed_keys(path: Path) -> set[str]:
    if not path.exists():
        return set()
    payload = json.loads(path.read_text(encoding="utf-8"))
    entries = payload.get("entries", []) if isinstance(payload, dict) else []
    return {
        str(item["idempotency_key"])
        for item in entries
        if isinstance(item, dict) and item.get("idempotency_key")
    }


def empty_ledger() -> dict[str, Any]:
    """Ledger shape for future apply; dry-run never writes it."""
    return {"version": 1, "entries": []}
