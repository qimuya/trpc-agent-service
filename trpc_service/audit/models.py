"""Pseudonymous audit records with explicit authorization scope."""

from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from enum import StrEnum
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, field_validator

from trpc_service.channels.contracts import Channel
from trpc_service.tenant.models import VerifiedTenantContext


class _AuditModel(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)


class TenantScope(_AuditModel):
    tenant_id: str = Field(pattern=r"^[a-z0-9][a-z0-9-]{0,63}$")

    @classmethod
    def from_context(cls, context: VerifiedTenantContext) -> TenantScope:
        return cls(tenant_id=context.tenant_id)


class PreAuthScope(_AuditModel):
    """Scope for observations made before a tenant has been authenticated."""


class AuditDecision(StrEnum):
    RECEIVED = "received"
    UNAUTHORIZED = "unauthorized"
    ACCESS_DENIED = "access_denied"
    INVALID_REQUEST = "invalid_request"
    AUTHORIZED = "authorized"
    DUPLICATE = "duplicate"
    PROCESSING = "processing"
    IDEMPOTENCY_CONFLICT = "idempotency_conflict"
    EXECUTION_STARTED = "execution_started"
    SUCCEEDED = "succeeded"
    AGENT_FAILED = "agent_failed"
    OUTCOME_UNKNOWN = "outcome_unknown"
    AUDIT_INCOMPLETE = "audit_incomplete"


class AuditRecord(_AuditModel):
    audit_id: UUID
    trace_id: UUID
    original_trace_id: UUID | None = None
    first_claim_trace_id: UUID | None = None
    owner_trace_id: UUID | None = None
    execution_trace_id: UUID | None = None
    generation: int | None = Field(default=None, gt=0)
    node_id: str | None = Field(default=None, max_length=64)
    audit_kind: str = Field(default="business", pattern=r"^(business|diagnostic)$")
    rejected_generation: int | None = Field(default=None, gt=0)
    current_generation: int | None = Field(default=None, gt=0)
    tenant_id: str | None = Field(default=None, pattern=r"^[a-z0-9][a-z0-9-]{0,63}$")
    channel: Channel
    binding_id_digest: str = Field(pattern=r"^sha256:[0-9a-f]{64}$")
    user_id: str | None = Field(default=None, pattern=r"^sha256:[0-9a-f]{64}$")
    session_id: str | None = Field(default=None, pattern=r"^sess_[0-9a-f]{64}$")
    agent_id: str | None = Field(default=None, pattern=r"^[a-z0-9][a-z0-9-]{0,63}$")
    agent_name: str | None = Field(default=None, max_length=120)
    tool_name: str | None = Field(default=None, max_length=120)
    decision: AuditDecision
    latency_ms: float = Field(ge=0)
    error_type: str | None = Field(default=None, pattern=r"^[a-z][a-z0-9_]*$")
    cost: Decimal = Field(default=Decimal("0"), ge=0)
    external_message_digest: str | None = Field(default=None, pattern=r"^sha256:[0-9a-f]{64}$")
    created_at: datetime

    @field_validator("created_at")
    @classmethod
    def require_utc(cls, value: datetime) -> datetime:
        if value.tzinfo is None or value.utcoffset() is None or value.utcoffset().total_seconds() != 0:
            raise ValueError("created_at must be UTC-aware")
        return value
