"""Non-sensitive demo configuration for two isolated tenants."""

from __future__ import annotations

from datetime import datetime, timezone
from os import environ as process_environ
from typing import Mapping

from pydantic import BaseModel, ConfigDict

from trpc_service.tenant.models import AgentApplication, ChannelBinding, ResourceStatus, Tenant


class ConfigurationError(RuntimeError):
    pass


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
