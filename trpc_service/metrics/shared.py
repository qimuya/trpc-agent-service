"""Bounded, pseudonymous shared-profile metric dimensions."""

from __future__ import annotations

from hashlib import sha256

from trpc_service.audit.models import TenantScope
from trpc_service.metrics.inmemory import InMemoryMetricsRecorder


def _anonymous(value: str) -> str:
    return "sha256:" + sha256(value.encode("utf-8")).hexdigest()[:16]


class SharedMetricsRecorder(InMemoryMetricsRecorder):
    def __init__(self, *, node_id: str) -> None:
        super().__init__()
        self.node_id = node_id
        self.events: list[dict[str, object]] = []

    def observe_lease(self, scope: TenantScope, *, backend: str, session_id: str,
                      outcome: str, wait_ms: float) -> None:
        self.events.append({
            "node_id": self.node_id, "tenant": _anonymous(scope.tenant_id),
            "backend": backend, "session": _anonymous(session_id),
            "outcome": outcome, "wait_ms": wait_ms,
        })

    def observe_trace(self, scope: TenantScope, *, backend: str, outcome: str,
                      first_trace: str | None, owner_trace: str | None,
                      execution_trace: str | None, generation: int | None) -> None:
        self.events.append({
            "node_id": self.node_id, "tenant": _anonymous(scope.tenant_id),
            "backend": backend, "outcome": outcome,
            "first_trace": first_trace, "owner_trace": owner_trace,
            "execution_trace": execution_trace, "generation": generation,
        })
