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
from trpc_service.config.settings import load_settings
from trpc_service.gateway.service import GatewayService
from trpc_service.metrics.inmemory import InMemoryMetricsRecorder
from trpc_service.storage.inmemory import EnvironmentSecretResolver, InMemoryPlatformAdapters
from trpc_service.storage.session_backend import SessionBackendFactory
from trpc_service.storage.locks import SessionLockManager
from trpc_service.worker.service import AgentExecutor


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
