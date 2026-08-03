from __future__ import annotations

from collections.abc import Callable
from datetime import datetime

from cosmos_control_tower.acceptance.models import OrganizationMap
from cosmos_control_tower.models.records import SourceRecord
from cosmos_control_tower.rules_engine.evaluators import (
    missed_lead_acceptance,
    no_next_step,
)
from cosmos_control_tower.rules_engine.models import RuleDefinition, RuleMode, RuleRunResult

Evaluator = Callable[
    [
        RuleDefinition,
        list[SourceRecord],
        dict[str, str],
        OrganizationMap,
        datetime,
        set[str],
    ],
    RuleRunResult,
]


class RulesEngine:
    def __init__(self) -> None:
        self._evaluators: dict[str, Evaluator] = {
            "missed_lead_acceptance": missed_lead_acceptance,
            "no_next_step": no_next_step,
        }

    def run(
        self,
        rule: RuleDefinition,
        records: list[SourceRecord],
        department_heads: dict[str, str],
        organization: OrganizationMap,
        *,
        as_of: datetime,
        processed_keys: set[str] | None = None,
    ) -> RuleRunResult:
        if not rule.enabled or rule.mode == RuleMode.OFF:
            now = datetime.now(as_of.tzinfo)
            return RuleRunResult(
                run_id="not-run",
                rule_id=rule.rule_id,
                name=rule.name,
                mode=rule.mode,
                status="OFF",
                started_at=now,
                completed_at=now,
                records_evaluated=0,
                violations_found=0,
                blocked_by_data=0,
                planned_actions=0,
            )
        if rule.mode == RuleMode.ACTIVE:
            raise PermissionError("ACTIVE mode is blocked until explicit approval")
        evaluator = self._evaluators.get(rule.evaluator)
        if evaluator is None:
            raise ValueError(f"Unknown rule evaluator: {rule.evaluator}")
        return evaluator(
            rule,
            records,
            department_heads,
            organization,
            as_of,
            processed_keys or set(),
        )
