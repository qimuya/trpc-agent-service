"""Composition root for the process-local validation service."""

from __future__ import annotations

from dataclasses import dataclass
from contextlib import asynccontextmanager
from datetime import datetime, timezone
from typing import Callable, Mapping

from starlette.applications import Starlette
from starlette.responses import JSONResponse
from starlette.routing import Route

from trpc_service.audit.models import TenantScope
from trpc_service.channels.local_http import LocalHttpChannelAdapter
from trpc_service.config.settings import load_settings, load_runtime_settings
from trpc_service.gateway.service import GatewayService
from trpc_service.metrics.inmemory import InMemoryMetricsRecorder
from trpc_service.storage.inmemory import EnvironmentSecretResolver, InMemoryPlatformAdapters
from trpc_service.storage.session_backend import SessionBackendFactory
from trpc_service.storage.locks import SessionLockManager
from trpc_service.worker.service import AgentExecutor
from trpc_service.storage.models import NodeIdentity
from trpc_service.storage.redis_session import SharedSessionBackendFactory
from trpc_service.storage.shared import SharedPlatformAdapters
from trpc_service.storage.redis_leases import RedisSessionLeaseManager
from trpc_service.storage.redis_adapter_leases import RedisAdapterOwnershipRepository
from trpc_service.metrics.shared import SharedMetricsRecorder
from trpc_service.recovery.reconciler import RecoveryReconciler
from trpc_service.storage.contracts import AuditUnavailable, StateBackendUnavailable
import asyncio


def adapter_readiness_payload(state: object) -> dict[str, object]:
    """Render ownership state without echoing the channel identity digest."""

    return {
        "readiness": state.phase.value,
        "owner_node_id": state.owner_node_id,
        "generation": state.generation,
        "expires_in_ms": state.expires_in_ms,
    }


@dataclass(slots=True)
class LocalRuntime:
    adapters: InMemoryPlatformAdapters
    metrics: InMemoryMetricsRecorder
    secrets: EnvironmentSecretResolver
    worker: AgentExecutor
    gateway: GatewayService
    now: Callable[[], datetime]

    def tenant_scope(self, tenant_id: str) -> TenantScope:
        return TenantScope(tenant_id=tenant_id)

    async def close(self) -> None:
        await self.worker.close()


def build_runtime(environ: Mapping[str, str], *, now: Callable[[], datetime] | None = None) -> LocalRuntime:
    clock = now or (lambda: datetime.now(timezone.utc))
    settings = load_settings(environ)
    adapters = InMemoryPlatformAdapters(settings)
    metrics = InMemoryMetricsRecorder()
    secrets = EnvironmentSecretResolver(environ)
    worker = AgentExecutor(SessionBackendFactory())
    gateway = GatewayService(adapters, metrics, worker, SessionLockManager(), now=clock)
    return LocalRuntime(adapters, metrics, secrets, worker, gateway, clock)


def create_app(environ: Mapping[str, str], *, now: Callable[[], datetime] | None = None) -> Starlette:
    runtime = build_runtime(environ, now=now)
    adapter = LocalHttpChannelAdapter(runtime)

    @asynccontextmanager
    async def lifespan(_app: Starlette):
        try:
            yield
        finally:
            await runtime.close()

    async def health(_request: object) -> JSONResponse:
        return JSONResponse({"status": "ok"})

    app = Starlette(lifespan=lifespan, routes=[Route("/healthz", health), Route("/v1/local/messages", adapter.handle, methods=["POST"])])
    app.state.runtime = runtime
    return app


@dataclass(slots=True)
class SharedRuntime:
    adapters: SharedPlatformAdapters
    metrics: InMemoryMetricsRecorder
    secrets: EnvironmentSecretResolver
    worker: AgentExecutor
    gateway: GatewayService
    now: Callable[[], datetime]
    recovery: RecoveryReconciler
    recovery_task: asyncio.Task[None] | None = None

    async def start_recovery(self) -> None:
        if self.recovery_task is None:
            self.recovery_task = asyncio.create_task(self._recovery_loop())

    async def _recovery_loop(self) -> None:
        while True:
            try:
                for tenant_id in ("tenant-alpha", "tenant-beta"):
                    await self.recovery.run_once(tenant_id)
            except (AuditUnavailable, StateBackendUnavailable):
                # A transient dependency outage must not kill the worker's
                # recovery capability. /readyz independently reports the
                # dependency state and the loop retries after the interval.
                pass
            await asyncio.sleep(0.5)

    async def close(self) -> None:
        if self.recovery_task is not None:
            self.recovery_task.cancel()
            try:
                await self.recovery_task
            except asyncio.CancelledError:
                pass
        await self.worker.close()
        await self.adapters.close()


async def build_shared_runtime(environ: Mapping[str, str], *, now: Callable[[], datetime] | None = None) -> SharedRuntime:
    clock = now or (lambda: datetime.now(timezone.utc))
    settings = load_runtime_settings(environ)
    adapters = await SharedPlatformAdapters.create(settings, settings.node)
    metrics = SharedMetricsRecorder(node_id=settings.node.node_id)
    secrets = EnvironmentSecretResolver(environ)
    worker = AgentExecutor(SharedSessionBackendFactory(adapters.redis, require_fence=True))
    locks = RedisSessionLeaseManager(
        adapters.redis, node=settings.node, lease_ms=settings.lease.lease_ms,
        heartbeat_ms=settings.lease.heartbeat_ms, wait_ms=settings.lease.acquire_wait_ms,
        metrics=metrics,
    )
    adapters.audit.fence_validator = locks.validate_fence
    gateway = GatewayService(adapters, metrics, worker, locks, now=clock)
    recovery = RecoveryReconciler(adapters.audit, adapters.idempotency)
    return SharedRuntime(adapters, metrics, secrets, worker, gateway, clock, recovery)


def create_shared_app(environ: Mapping[str, str] | None = None) -> Starlette:
    """Build one stateless Worker process over the configured shared backends."""

    source = dict(environ or {})
    # This composition root is explicitly for the shared backend. Requiring
    # every in-process caller to repeat the profile selector made otherwise
    # complete Redis/PostgreSQL settings silently load as LOCAL.
    source["TRPC_RUNTIME_PROFILE"] = "shared"

    @asynccontextmanager
    async def lifespan(app: Starlette):
        runtime = await build_shared_runtime(source)
        await runtime.start_recovery()
        app.state.runtime = runtime
        app.state.adapter = LocalHttpChannelAdapter(runtime)
        try:
            yield
        finally:
            await runtime.close()

    async def health(_request: object) -> JSONResponse:
        return JSONResponse({"status": "ok", "profile": "shared"})

    async def ready(request: object) -> JSONResponse:
        runtime = request.app.state.runtime
        available = await runtime.adapters.readiness() and (
            runtime.recovery_task is not None and not runtime.recovery_task.done()
        )
        return JSONResponse({"status": "ready" if available else "unavailable"}, status_code=200 if available else 503)

    async def messages(request: object) -> JSONResponse:
        return await request.app.state.adapter.handle(request)

    async def adapter_readiness(request: object) -> JSONResponse:
        identity_digest = request.query_params.get("identity_digest", "")
        if (
            len(identity_digest) != 64
            or any(character not in "0123456789abcdef" for character in identity_digest)
        ):
            return JSONResponse({"status": "invalid_request"}, status_code=400)
        try:
            state = await RedisAdapterOwnershipRepository(
                request.app.state.runtime.adapters.redis
            ).inspect(identity_digest)
        except StateBackendUnavailable:
            return JSONResponse({"status": "unavailable"}, status_code=503)
        return JSONResponse(adapter_readiness_payload(state))

    return Starlette(lifespan=lifespan, routes=[
        Route("/healthz", health), Route("/readyz", ready),
        Route("/v1/channels/readiness", adapter_readiness),
        Route("/v1/local/messages", messages, methods=["POST"]),
    ])
