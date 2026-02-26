"""Shared Copilot API types."""

from __future__ import annotations

from typing import Any, Dict, Generic, List, Optional, TypeVar

from pydantic import BaseModel, Field

T = TypeVar("T")


class ApiMessage(BaseModel):
    message: str


class ApiError(BaseModel):
    detail: str


class PaginatedResponse(BaseModel, Generic[T]):
    items: List[T]
    total: int


class HealthResponse(BaseModel):
    ok: bool = True
    section: str


class CopilotModelItem(BaseModel):
    code: str
    display_name: str
    provider: str
    capability: str
    cost_per_1m_input: float = 0.0
    cost_per_1m_output: float = 0.0
    enabled: bool = True


class CopilotBudgetAllocation(BaseModel):
    scope_type: str = Field(description="ACCOUNT|ORG|TEAM|USER")
    scope_id: str
    scope_name: str
    allocated_credits: float
    used_credits: float = 0.0
    overflow_cap: Optional[float] = None


class CopilotBudgetPlan(BaseModel):
    plan_id: str
    account_id: str
    cycle: str = Field(description="monthly|weekly|daily")
    credits_factor: float
    account_allocated_credits: float
    unallocated_credits: float
    allocations: List[CopilotBudgetAllocation]


class CopilotAuditEvent(BaseModel):
    event_id: str
    timestamp: str
    account_id: str
    event_type: str
    actor: str
    data: Dict[str, Any] = Field(default_factory=dict)
