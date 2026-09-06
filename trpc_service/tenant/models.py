"""Tenant-owned configuration models and verified execution context."""

from __future__ import annotations

from datetime import datetime
from enum import StrEnum
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, field_validator

from trpc_service.channels.contracts import Channel


class ResourceStatus(StrEnum):
    ACTIVE = "active"
    DISABLED = "disabled"


class _DomainModel(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)


class _CreatedAtModel(_DomainModel):
    created_at: datetime

    @field_validator("created_at")
    @classmethod
    def require_utc(cls, value: datetime) -> datetime:
        if value.tzinfo is None or value.utcoffset() is None or value.utcoffset().total_seconds() != 0:
            raise ValueError("created_at must be UTC-aware")
        return value


Identifier = str


class Tenant(_CreatedAtModel):
    tenant_id: Identifier = Field(pattern=r"^[a-z0-9][a-z0-9-]{0,63}$")
    display_name: str = Field(min_length=1, max_length=120)
    status: ResourceStatus
    config_version: int = Field(gt=0)


class AgentApplication(_DomainModel):
    tenant_id: Identifier = Field(pattern=r"^[a-z0-9][a-z0-9-]{0,63}$")
    agent_id: Identifier = Field(pattern=r"^[a-z0-9][a-z0-9-]{0,63}$")
    agent_name: str = Field(min_length=1, max_length=120)
    status: ResourceStatus
    model_profile: Literal["deterministic-offline"]
    instruction: str = Field(min_length=1, max_length=4000)
    config_version: int = Field(gt=0)


class ChannelBinding(_CreatedAtModel):
    binding_id: Identifier = Field(pattern=r"^[a-z0-9][a-z0-9-]{0,95}$")
    tenant_id: Identifier = Field(pattern=r"^[a-z0-9][a-z0-9-]{0,63}$")
    agent_id: Identifier = Field(pattern=r"^[a-z0-9][a-z0-9-]{0,63}$")
    channel: Channel
    status: ResourceStatus
    secret_ref: str = Field(pattern=r"^[A-Z][A-Z0-9_]{0,127}$")
    signature_version: Literal["v1"]


class VerifiedTenantContext(_DomainModel):
    tenant_id: Identifier
    agent_id: Identifier
    agent_name: str
    binding_id: Identifier
    channel: Channel
    external_user_id: str
    trace_id: UUID
    config_version: int

    @classmethod
    def from_resources(
        cls,
        *,
        tenant: Tenant,
        agent: AgentApplication,
        binding: ChannelBinding,
        external_user_id: str,
        trace_id: UUID,
    ) -> VerifiedTenantContext:
        ownership_matches = (
            tenant.tenant_id == agent.tenant_id == binding.tenant_id
            and agent.agent_id == binding.agent_id
        )
        if not ownership_matches:
            raise ValueError("resource ownership mismatch")
        if any(resource.status != ResourceStatus.ACTIVE for resource in (tenant, agent, binding)):
            raise ValueError("resource is not active")
        return cls(
            tenant_id=tenant.tenant_id,
            agent_id=agent.agent_id,
            agent_name=agent.agent_name,
            binding_id=binding.binding_id,
            channel=binding.channel,
            external_user_id=external_user_id,
            trace_id=trace_id,
            config_version=max(tenant.config_version, agent.config_version),
        )
