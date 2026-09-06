"""Validated metrics snapshots with explicit tenant or pre-auth scope."""

from __future__ import annotations

from decimal import Decimal
from typing import Literal, Self

from pydantic import BaseModel, ConfigDict, Field, model_validator

from trpc_service.audit.models import PreAuthScope, TenantScope


class MetricSnapshot(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    scope: TenantScope | PreAuthScope
    request_count: int = Field(default=0, ge=0)
    error_count: int = Field(default=0, ge=0)
    stage_latency_ms: dict[str, float] = Field(default_factory=dict)
    agent_latency_ms: float = Field(default=0, ge=0)
    state_backend_latency_ms: float = Field(default=0, ge=0)
    channel_delivery_count: int = Field(default=0, ge=0)
    token_count: int = Field(default=0, ge=0)
    tenant_cost: Decimal = Field(default=Decimal("0"), ge=0)
    model_metric_status: Literal["not_applicable"] = "not_applicable"
    tool_metric_status: Literal["not_applicable"] = "not_applicable"
    im_metric_status: Literal["not_applicable"] = "not_applicable"

    @model_validator(mode="after")
    def validate_counts_and_latencies(self) -> Self:
        if self.error_count > self.request_count:
            raise ValueError("error_count cannot exceed request_count")
        if any(value < 0 for value in self.stage_latency_ms.values()):
            raise ValueError("stage latency cannot be negative")
        return self
