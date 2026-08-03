from __future__ import annotations

from datetime import datetime
from enum import StrEnum
from typing import Any

from pydantic import BaseModel, Field


class RuleMode(StrEnum):
    OFF = "OFF"
    DRY_RUN = "DRY_RUN"
    APPROVAL_REQUIRED = "APPROVAL_REQUIRED"
    ACTIVE = "ACTIVE"


class RuleDefinition(BaseModel):
    rule_id: str
    name: str
    description: str
    enabled: bool = False
    mode: RuleMode = RuleMode.OFF
    schedule: str
    timezone: str = "Europe/Moscow"
    entity_type: str
    scope: dict[str, Any] = Field(default_factory=dict)
    conditions: list[dict[str, Any]] = Field(default_factory=list)
    exclusions: list[dict[str, Any]] = Field(default_factory=list)
    deadline: dict[str, Any] = Field(default_factory=dict)
    violation: dict[str, Any] = Field(default_factory=dict)
    actions: list[dict[str, Any]] = Field(default_factory=list)
    escalation: list[dict[str, Any]] = Field(default_factory=list)
    kpi: list[str] = Field(default_factory=list)
    idempotency_key: str
    owner: str
    version: str
    evaluator: str = "simple_conditions"


class RulePreview(BaseModel):
    idempotency_key: str
    entity_type: str
    entity_id: str
    card_url: str | None = None
    employee_id: str | None = None
    department_id: str | None = None
    rop_user_id: str | None = None
    reason: str
    evidence_status: str = "CONFIRMED"
    escalation_level: int = 1
    proposed_actions: list[dict[str, Any]] = Field(default_factory=list)
    dry_run: bool = True


class RuleRunResult(BaseModel):
    run_id: str
    rule_id: str
    name: str
    mode: RuleMode
    status: str
    started_at: datetime
    completed_at: datetime
    records_evaluated: int
    violations_found: int
    blocked_by_data: int
    planned_actions: int
    writes_performed: int = 0
    previews: list[RulePreview] = Field(default_factory=list)
    exclusions: dict[str, int] = Field(default_factory=dict)
    kpi: dict[str, Any] = Field(default_factory=dict)
    errors: list[str] = Field(default_factory=list)
    limitations: list[str] = Field(default_factory=list)


class RulesRunReport(BaseModel):
    generated_at: datetime
    mode: str = "DRY_RUN"
    writes_performed: int = 0
    results: list[RuleRunResult]
