from datetime import datetime
from typing import Any

from pydantic import BaseModel, Field


class SourceRecord(BaseModel):
    entity_type: str
    source_id: str
    assigned_to_id: str | None = None
    department_id: str | None = None
    stage_id: str | None = None
    created_at: datetime | None = None
    updated_at: datetime | None = None
    stage_changed_at: datetime | None = None
    next_activity_at: datetime | None = None
    has_open_activity: bool | None = None
    has_first_call: bool | None = None
    required_fields: dict[str, Any] = Field(default_factory=dict)


class Violation(BaseModel):
    rule_id: str
    status: str
    entity_type: str
    source_id: str
    assigned_to_id: str | None = None
    department_id: str | None = None
    evidence: dict[str, Any] = Field(default_factory=dict)
