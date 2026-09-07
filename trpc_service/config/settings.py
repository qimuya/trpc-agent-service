"""Non-sensitive demo configuration for two isolated tenants."""

from __future__ import annotations

from datetime import datetime, timezone
from enum import StrEnum
from os import environ as process_environ
from typing import Mapping

from pydantic import BaseModel, ConfigDict, Field, SecretStr, ValidationError, model_validator

from trpc_service.storage.models import NodeIdentity
from trpc_service.tenant.models import AgentApplication, ChannelBinding, ResourceStatus, Tenant


class ConfigurationError(RuntimeError):
    pass


class RuntimeProfile(StrEnum):
    LOCAL = "local"
    SHARED = "shared"


class LeaseSettings(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    lease_ms: int = Field(default=10_000, gt=0, le=300_000)
    heartbeat_ms: int = Field(default=3_000, gt=0)
    acquire_wait_ms: int = Field(default=2_000, ge=0, le=60_000)

    @model_validator(mode="after")
    def heartbeat_precedes_expiry(self) -> "LeaseSettings":
        if self.heartbeat_ms >= self.lease_ms:
            raise ValueError("heartbeat must be shorter than the lease")
        return self


class RuntimeSettings(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    profile: RuntimeProfile
    node: NodeIdentity
    redis_url: SecretStr | None = None
    database_url: SecretStr | None = None
    lease: LeaseSettings = Field(default_factory=LeaseSettings)
    agent_timeout_seconds: float = Field(default=30, gt=0, le=300)

    @model_validator(mode="after")
    def shared_requires_external_state(self) -> "RuntimeSettings":
        if self.profile == RuntimeProfile.SHARED and (
            self.redis_url is None or self.database_url is None
        ):
            raise ValueError("shared runtime dependencies are required")
        return self


def load_runtime_settings(
    environ: Mapping[str, str] | None = None,
) -> RuntimeSettings:
    source = process_environ if environ is None else environ
    profile_value = source.get("TRPC_RUNTIME_PROFILE", RuntimeProfile.LOCAL.value)
    values: dict[str, object] = {
        "profile": profile_value,
        "node": {
            "node_id": source.get(
                "TRPC_NODE_ID",
                "local-worker" if profile_value == RuntimeProfile.LOCAL else "",
            )
        },
        "agent_timeout_seconds": source.get("TRPC_AGENT_TIMEOUT_SECONDS", "30"),
        "lease": {
            "lease_ms": source.get("TRPC_LEASE_MS", "10000"),
            "heartbeat_ms": source.get("TRPC_LEASE_HEARTBEAT_MS", "3000"),
            "acquire_wait_ms": source.get("TRPC_LEASE_ACQUIRE_WAIT_MS", "2000"),
        },
    }
    if profile_value == RuntimeProfile.SHARED:
        values["redis_url"] = source.get("TRPC_SHARED_REDIS_URL") or None
        values["database_url"] = source.get("TRPC_SHARED_DATABASE_URL") or None
    try:
        return RuntimeSettings.model_validate(values)
    except ValidationError:
        raise ConfigurationError("Runtime configuration is invalid.") from None


class PlatformSettings(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    tenants: tuple[Tenant, ...]
    agents: tuple[AgentApplication, ...]
    bindings: tuple[ChannelBinding, ...]
    model_credentials_required: bool = False


def build_demo_settings() -> PlatformSettings:
    created_at = datetime(2026, 1, 1, tzinfo=timezone.utc)
    tenant_specs = (
        ("tenant-alpha", "Alpha Tenant", "agent-alpha", "Alpha Agent", "binding-alpha", "TRPC_DEMO_ALPHA_SECRET"),
        ("tenant-beta", "Beta Tenant", "agent-beta", "Beta Agent", "binding-beta", "TRPC_DEMO_BETA_SECRET"),
    )
    tenants = tuple(
        Tenant(
            tenant_id=tenant_id,
            display_name=display_name,
            status=ResourceStatus.ACTIVE,
            created_at=created_at,
            config_version=1,
        )
        for tenant_id, display_name, *_ in tenant_specs
    )
    agents = tuple(
        AgentApplication(
            tenant_id=tenant_id,
            agent_id=agent_id,
            agent_name=agent_name,
            status=ResourceStatus.ACTIVE,
            model_profile="deterministic-offline",
            instruction="Run the deterministic validation conversation.",
            config_version=1,
        )
        for tenant_id, _, agent_id, agent_name, _, _ in tenant_specs
    )
    bindings = tuple(
        ChannelBinding(
            binding_id=binding_id,
            tenant_id=tenant_id,
            agent_id=agent_id,
            channel="local_http",
            status=ResourceStatus.ACTIVE,
            secret_ref=secret_ref,
            signature_version="v1",
            created_at=created_at,
        )
        for tenant_id, _, agent_id, _, binding_id, secret_ref in tenant_specs
    )
    return PlatformSettings(tenants=tenants, agents=agents, bindings=bindings)


def load_settings(environ: Mapping[str, str] | None = None) -> PlatformSettings:
    source = process_environ if environ is None else environ
    settings = build_demo_settings()
    if any(not source.get(binding.secret_ref, "").strip() for binding in settings.bindings):
        raise ConfigurationError("Required binding secret is unavailable.")
    return settings
