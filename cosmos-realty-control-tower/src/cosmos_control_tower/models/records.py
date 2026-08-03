from datetime import datetime
from typing import Any

from pydantic import BaseModel, Field


class SourceRecord(BaseModel):
    entity_type: str
    source_id: str
    assigned_to_id: str | None = None
    assigned_at: datetime | None = None
    assignee_active: bool | None = None
    department_id: str | None = None
    stage_id: str | None = None
    created_at: datetime | None = None
    updated_at: datetime | None = None
    stage_changed_at: datetime | None = None
    last_activity_at: datetime | None = None
    next_activity_at: datetime | None = None
    has_open_activity: bool | None = None
    next_task_at: datetime | None = None
    has_open_task: bool | None = None
    task_data_complete: bool = False
    has_first_call: bool | None = None
    activity_data_complete: bool = True
    source_channel_id: str | None = None
    category_id: str | None = None
    is_closed: bool = False
    is_won: bool = False
    lost_reason: str | None = None
    card_url: str | None = None
    required_fields: dict[str, Any] = Field(default_factory=dict)


class Violation(BaseModel):
    rule_id: str
    status: str
    entity_type: str
    source_id: str
    assigned_to_id: str | None = None
    department_id: str | None = None
    card_url: str | None = None
    evidence: dict[str, Any] = Field(default_factory=dict)


class DryRunAction(BaseModel):
    action_id: str
    rule_id: str
    target_role: str
    target_id: str | None = None
    entity_type: str
    source_id: str
    card_url: str | None = None
    reason: str
    proposed_action: str
    execute_after: datetime | None = None
    dry_run: bool = True


class CalibratedRecord(BaseModel):
    record: SourceRecord
    work_scope: str
    reason_code: str
    rule_status: str = "PROPOSED"
