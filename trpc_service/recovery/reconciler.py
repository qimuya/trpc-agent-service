"""Terminal-only reconciliation. This module deliberately cannot execute Agents."""

from __future__ import annotations

from typing import Any
from trpc_service.storage.contracts import ConditionalWriteFailed


class RecoveryReconciler:
    def __init__(self, durable_repository: Any, terminal_repository: Any) -> None:
        self.durable_repository = durable_repository
        self.terminal_repository = terminal_repository

    async def run_once(self, tenant_scope: Any, limit: int = 100) -> int:
        markers = await self.durable_repository.get_pending(tenant_scope, limit)
        completed = 0
        for marker in markers:
            marker_id = marker.get("id") if isinstance(marker, dict) else marker.recovery_id
            digest = marker.get("result_digest", "saved") if isinstance(marker, dict) else marker.result_digest
            try:
                await self.terminal_repository.complete_from_recovery(marker)
                await self.durable_repository.mark_reconciled(tenant_scope, marker_id, digest)
                completed += 1
            except ConditionalWriteFailed:
                await self.durable_repository.mark_conflict_review(
                    tenant_scope, marker_id, "terminal_cas_conflict"
                )
        return completed
