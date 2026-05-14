from __future__ import annotations

from typing import Optional

from pydantic import BaseModel, Field, field_validator


class BlocklistAdd(BaseModel):
    domains: list[str] = Field(..., min_length=1)


class ScheduleCreate(BaseModel):
    name: str = Field(..., min_length=1, max_length=80)
    days: list[int] = Field(..., min_length=1)
    start_minute: int = Field(..., ge=0, le=1439)
    end_minute: int = Field(..., ge=0, le=1439)

    @field_validator("days")
    @classmethod
    def _days_in_range(cls, v: list[int]) -> list[int]:
        if any(d < 0 or d > 6 for d in v):
            raise ValueError("days must be in 0..6 (Mon=0)")
        return v


class SessionCreate(BaseModel):
    label: str = Field("focus session", max_length=80)
    duration_minutes: int = Field(..., ge=1, le=24 * 60)
    frozen: bool = True


class StatusResponse(BaseModel):
    active: bool
    reason: str
    expires_at: Optional[float]
    frozen: bool
    sources: list[dict]
    blocked_domains: list[str]
    hosts_synced: bool
