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


class ConfigurationUnavailable(PlatformPortError):
    def __init__(self, message: str = "Configuration is unavailable.") -> None:
        super().__init__(message)


class StateBackendUnavailable(PlatformPortError):
    def __init__(self, message: str = "Shared state is unavailable.") -> None:
        super().__init__(message)


class SessionBusy(PlatformPortError):
    pass


class SessionQuarantined(PlatformPortError):
    pass


class LeaseLost(PlatformPortError):
    pass


class StaleFence(PlatformPortError):
    pass


class RecoveryConflict(PlatformPortError):
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
    async def get_auth_material(self, binding_id: str, channel: Channel) -> BindingAuthMaterial: ...


@runtime_checkable
class SecretResolver(Protocol):
    def resolve(self, secret_ref: str) -> SecretBytes: ...


@runtime_checkable
class TenantDirectory(Protocol):
    async def resolve_active_context(
        self,
        scope: VerifiedBindingScope,
        *,
        external_user_id: str,
        trace_id: Any,
    ) -> VerifiedTenantContext: ...


@runtime_checkable
class IdempotencyRepository(Protocol):
    async def claim(self, key: Any, fingerprint: str, trace_id: UUID, now: datetime) -> Any: ...
    async def mark_running(self, key: Any, owner_token: str, execution_trace_id: UUID, now: datetime) -> Any: ...
    async def mark_pre_start_failed(self, key: Any, owner_token: str, safe_error: str, now: datetime) -> Any: ...
    async def complete(self, key: Any, owner_token: str, result: Any, now: datetime) -> Any: ...
    async def mark_post_start_failed(self, key: Any, owner_token: str, result: Any, now: datetime) -> Any: ...
    async def mark_outcome_unknown(self, key: Any, owner_token: str, result: Any, now: datetime) -> Any: ...
    async def get(self, key: Any) -> Any: ...
    async def reset(self) -> None: ...


@runtime_checkable
class SessionLockManager(Protocol):
    def acquire(self, platform_session_id: str) -> Any: ...


@runtime_checkable
class SessionBackendFactory(Protocol):
    def get_backend(self, tenant_id: str, agent_id: str) -> Any: ...
    async def close(self) -> None: ...


@runtime_checkable
class AuditRepository(Protocol):
    async def append(self, scope: Any, record: Any, fence_proof: Any | None = None) -> Any: ...
    async def append_diagnostic(self, scope: Any, record: Any) -> Any: ...
    async def update_final(self, scope: Any, audit_id: UUID, trace_id: UUID, decision: Any, **fields: object) -> Any: ...
    async def list_by_trace(self, scope: Any, trace_id: UUID) -> list[Any]: ...
    async def list_by_session(self, scope: Any, platform_session_id: str) -> list[Any]: ...
    async def list_by_tenant(self, scope: Any) -> list[Any]: ...
    async def list_preauth(self, scope: Any) -> list[Any]: ...
    async def reset(self) -> None: ...


@runtime_checkable
class SessionLeaseManager(Protocol):
    async def acquire(
        self,
        tenant_scope: Any,
        agent_id: str,
        platform_session_id: str,
        message_key_digest: str,
        node_identity: Any,
        lease_ms: int,
        wait_ms: int,
    ) -> Any: ...


@runtime_checkable
class SharedSessionRepository(Protocol):
    async def get_session(self, session_identity: Any, session_fence: Any) -> Any: ...
    async def create_session(self, session_identity: Any, initial_state: Any, session_fence: Any) -> Any: ...
    async def append_event(self, session_identity: Any, event: Any, message_fence: Any, session_fence: Any) -> Any: ...
    async def update_session(self, session_identity: Any, expected_version: int, state_delta: Any, message_fence: Any, session_fence: Any) -> Any: ...


@runtime_checkable
class RecoveryRepository(Protocol):
    async def find_blocking(self, tenant_scope: Any, idempotency_key_digest: str) -> Any: ...
    async def get_pending(self, tenant_scope: Any, limit: int) -> list[Any]: ...
    async def mark_reconciled(self, tenant_scope: Any, recovery_id: UUID, expected_result_digest: str) -> Any: ...
    async def mark_conflict_review(self, tenant_scope: Any, recovery_id: UUID, safe_reason: str) -> Any: ...


@runtime_checkable
class PlatformAdapters(BindingAuthRegistry, TenantDirectory, Protocol):
    audit: AuditRepository
    idempotency: IdempotencyRepository


@runtime_checkable
class AgentExecutorPort(Protocol):
    async def prepare(self, context: VerifiedTenantContext, identity: Any, text: str) -> Any: ...
    async def close(self) -> None: ...


__all__ = [name for name in globals() if not name.startswith("_")]
