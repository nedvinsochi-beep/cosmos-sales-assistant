from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import BaseModel, Field


class OrganizationMap(BaseModel):
    owner_user_ids: set[str] = Field(default_factory=lambda: {"1"})
    service_user_ids: set[str] = Field(default_factory=set)
    technical_user_ids: set[str] = Field(default_factory=set)
    test_user_ids: set[str] = Field(default_factory=set)
    poteryashka_user_id: str | None = None


class AcceptanceRule(BaseModel):
    rule_id: str = "MISSED_ACCEPTANCE_SLA"
    source_stage_id: str = "NEW"
    target_stage_id: str = "IN_PROCESS"
    check_time: str = "23:50"
    timezone: str = "Europe/Moscow"


class AcceptanceAction(BaseModel):
    idempotency_key: str
    lead_id: str
    card_url: str | None = None
    original_assigned_user_id: str
    assigned_at: datetime
    violation_date: str
    violation_detected_at: datetime
    rop_user_id: str
    poteryashka_user_id: str
    robot_rule_id: str
    robot_run_id: str
    source_stage_id: str
    target_stage_id: str
    proposed_updates: dict[str, Any]
    proposed_comment: str
    dry_run: bool = True


class BlockedCandidate(BaseModel):
    lead_id: str
    card_url: str | None = None
    assigned_user_id: str | None = None
    department_id: str | None = None
    rop_user_id: str | None = None
    reason: str
    created_at: datetime | None = None


class AcceptanceReport(BaseModel):
    generated_at: datetime
    as_of: datetime
    timezone: str
    dry_run: bool = True
    writes_performed: int = 0
    records_evaluated: int
    exact_assigned_today: int | None = None
    exact_accepted_today: int | None = None
    created_today_assigned_proxy: int
    created_today_moved_from_new_proxy: int
    eligible_to_return: int
    blocked_candidates: list[BlockedCandidate]
    actions: list[AcceptanceAction]
    exclusions: dict[str, int]
    by_broker: list[dict[str, Any]]
    by_rop: list[dict[str, Any]]
    limitations: list[str]
