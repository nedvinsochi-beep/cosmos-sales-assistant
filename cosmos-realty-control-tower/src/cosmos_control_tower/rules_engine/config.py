import json
from pathlib import Path

from pydantic import TypeAdapter

from cosmos_control_tower.rules_engine.models import RuleDefinition


def load_rules(path: Path) -> list[RuleDefinition]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    return TypeAdapter(list[RuleDefinition]).validate_python(payload.get("rules", []))
