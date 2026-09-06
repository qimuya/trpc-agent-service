"""Replaceable repository and adapter ports for the local message flow."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Any, Protocol, runtime_checkable
from uuid import UUID

from trpc_service.channels.contracts import Channel, VerifiedBindingScope
from trpc_service.tenant.models import ResourceStatus, VerifiedTenantContext


class PlatformPortError(RuntimeError):
    """Stable base error translated at the gateway boundary."""


class InvalidRequest(PlatformPortError):
    pass


class Unauthorized(PlatformPortError):
    pass


class AccessDenied(PlatformPortError):
    pass


class NotFound(PlatformPortError):
    pass


class SecretUnavailable(PlatformPortError):
    pass


class IdempotencyConflict(PlatformPortError):
    pass


class Processing(PlatformPortError):
    pass


class AgentPreparationFailed(PlatformPortError):
    pass


class AgentExecutionFailed(PlatformPortError):
    pass


class OutcomeUnknown(PlatformPortError):
    pass


class AuditUnavailable(PlatformPortError):
    pass


class AuditIncomplete(PlatformPortError):
    pass


class ConditionalWriteFailed(PlatformPortError):
    pass


@dataclass(frozen=True, slots=True)
class BindingAuthMaterial:
    binding_id: str
    secret_ref: str
    signature_version: str
    status: ResourceStatus


class SecretBytes:
    """Short-lived secret wrapper that cannot be serialized or printed."""

    __slots__ = ("__value",)

    def __init__(self, value: bytes) -> None:
        if not value:
            raise ValueError("secret must not be empty")
        self.__value = bytes(value)

    def reveal(self) -> bytes:
        return self.__value

    def __repr__(self) -> str:
        return "SecretBytes(<redacted>)"

    def __reduce__(self) -> object:
        raise TypeError("SecretBytes cannot be serialized")


@runtime_checkable
class BindingAuthRegistry(Protocol):
    def get_auth_material(self, binding_id: str, channel: Channel) -> BindingAuthMaterial: ...


@runtime_checkable
class SecretResolver(Protocol):
    def resolve(self, secret_ref: str) -> SecretBytes: ...


@runtime_checkable
class TenantDirectory(Protocol):
    def resolve_active_context(
        self,
        scope: VerifiedBindingScope,
        *,
        external_user_id: str,
        trace_id: Any,
    ) -> VerifiedTenantContext: ...


@runtime_checkable
class IdempotencyRepository(Protocol):
    def claim(self, key: Any, fingerprint: str, trace_id: UUID, now: datetime) -> Any: ...
    def mark_running(self, key: Any, owner_token: str, execution_trace_id: UUID, now: datetime) -> Any: ...
    def mark_pre_start_failed(self, key: Any, owner_token: str, safe_error: str, now: datetime) -> Any: ...
    def complete(self, key: Any, owner_token: str, result: Any, now: datetime) -> Any: ...
    def mark_post_start_failed(self, key: Any, owner_token: str, result: Any, now: datetime) -> Any: ...
    def mark_outcome_unknown(self, key: Any, owner_token: str, result: Any, now: datetime) -> Any: ...
    def get(self, key: Any) -> Any: ...
    def reset(self) -> None: ...


@runtime_checkable
class SessionLockManager(Protocol):
    def acquire(self, platform_session_id: str) -> Any: ...


@runtime_checkable
class SessionBackendFactory(Protocol):
    def get_backend(self, tenant_id: str, agent_id: str) -> Any: ...
    async def close(self) -> None: ...


@runtime_checkable
class AuditRepository(Protocol):
    def append(self, scope: Any, record: Any) -> Any: ...
    def update_final(self, scope: Any, audit_id: UUID, trace_id: UUID, decision: Any, **fields: object) -> Any: ...
    def list_by_trace(self, scope: Any, trace_id: UUID) -> list[Any]: ...
    def list_by_session(self, scope: Any, platform_session_id: str) -> list[Any]: ...
    def list_by_tenant(self, scope: Any) -> list[Any]: ...
    def list_preauth(self, scope: Any) -> list[Any]: ...
    def reset(self) -> None: ...


@runtime_checkable
class PlatformAdapters(BindingAuthRegistry, TenantDirectory, Protocol):
    audit: AuditRepository
    idempotency: IdempotencyRepository


@runtime_checkable
class AgentExecutorPort(Protocol):
    async def prepare(self, context: VerifiedTenantContext, identity: Any, text: str) -> Any: ...
    async def close(self) -> None: ...


__all__ = [name for name in globals() if not name.startswith("_")]
