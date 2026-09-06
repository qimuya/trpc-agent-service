"""Application orchestration for authenticated local messages."""

from __future__ import annotations

import asyncio
from datetime import datetime, timezone
from decimal import Decimal
from hashlib import sha256
from time import monotonic
from uuid import UUID, uuid4

from trpc_service.audit.models import AuditDecision, AuditRecord, TenantScope
from trpc_service.channels.contracts import DeliveryAction, ErrorDetail, InboundMessage, OutboundReply, ReplyStatus, VerifiedBindingScope
from trpc_service.metrics.contracts import MetricsRecorder, MetricsUnavailable
from trpc_service.storage.locks import SessionLockManager
from trpc_service.storage.models import ClaimDisposition, ExecutionResult, ExecutionStatus, IdempotencyKey, content_fingerprint
from trpc_service.tenant.session_identity import derive_session_identity
from trpc_service.storage.contracts import AgentExecutionFailed, AgentExecutorPort, AgentPreparationFailed, AuditUnavailable, ConditionalWriteFailed, OutcomeUnknown, PlatformAdapters, SessionLockManager as SessionLockPort


def _digest(value: str) -> str:
    return "sha256:" + sha256(value.encode("utf-8")).hexdigest()


def _scoped_digest(scope: str, value: str) -> str:
    digest = sha256()
    for part in (scope, value):
        encoded = part.encode("utf-8")
        digest.update(len(encoded).to_bytes(8, "big"))
        digest.update(encoded)
    return "sha256:" + digest.hexdigest()


class GatewayService:
    def __init__(
        self,
        adapters: PlatformAdapters,
        metrics: MetricsRecorder,
        worker: AgentExecutorPort,
        locks: SessionLockPort | None = None,
        *,
        now: object | None = None,
    ) -> None:
        self.adapters = adapters
        self.metrics = metrics
        self.worker = worker
        self.locks = locks or SessionLockManager()
        self._now = now or (lambda: datetime.now(timezone.utc))

    def _record_metrics(
        self,
        scope: TenantScope,
        message: InboundMessage,
        started: float,
        *,
        outcome: str,
        agent: bool = False,
        delivered: bool = False,
    ) -> None:
        duration_ms = (monotonic() - started) * 1000
        try:
            self.metrics.record(scope, trace_id=message.trace_id, stage="request", outcome=outcome, duration_ms=duration_ms)
            self.metrics.record(scope, trace_id=message.trace_id, stage="state_backend", outcome=outcome, duration_ms=0)
            if agent:
                self.metrics.record(scope, trace_id=message.trace_id, stage="agent", outcome=outcome, duration_ms=duration_ms)
            if delivered:
                self.metrics.record(scope, trace_id=message.trace_id, stage="delivery", outcome="success", duration_ms=0)
        except MetricsUnavailable:
            pass

    def _audit(
        self,
        scope: TenantScope,
        message: InboundMessage,
        context: object,
        decision: AuditDecision,
        *,
        session_id: str | None = None,
        error_type: str | None = None,
        original_trace_id: UUID | None = None,
    ) -> AuditRecord:
        record = AuditRecord(
            audit_id=uuid4(),
            trace_id=message.trace_id,
            original_trace_id=original_trace_id,
            tenant_id=scope.tenant_id,
            channel=message.channel,
            binding_id_digest=_digest(message.binding_id),
            user_id=_scoped_digest(scope.tenant_id, message.external_user_id),
            session_id=session_id,
            agent_name=getattr(context, "agent_name", None),
            decision=decision,
            latency_ms=0,
            error_type=error_type,
            cost=Decimal("0"),
            external_message_digest=_digest(message.external_message_id),
            created_at=self._now(),
        )
        return self.adapters.audit.append(scope, record)

    @staticmethod
    def _failed_reply(
        message: InboundMessage,
        *,
        tenant_id: str,
        session_id: str,
        code: str,
        safe_message: str,
        retryable: bool,
        execution_started: bool,
        original_trace_id: UUID | None = None,
        delivery_action: DeliveryAction = DeliveryAction.NONE,
    ) -> OutboundReply:
        return OutboundReply(
            status=ReplyStatus.FAILED,
            trace_id=message.trace_id,
            original_trace_id=original_trace_id,
            tenant_id=tenant_id,
            platform_session_id=session_id,
            external_message_id=message.external_message_id,
            delivery_action=delivery_action,
            error=ErrorDetail(
                code=code,
                message=safe_message,
                retryable=retryable,
                execution_started=execution_started,
            ),
        )

    async def handle_verified_message(
        self,
        verified_scope: VerifiedBindingScope,
        message: InboundMessage,
    ) -> OutboundReply:
        started = monotonic()
        context = self.adapters.resolve_active_context(
            verified_scope,
            external_user_id=message.external_user_id,
            trace_id=message.trace_id,
        )
        scope = TenantScope.from_context(context)
        identity = derive_session_identity(context, message.conversation_type, message.external_conversation_id)
        key = IdempotencyKey(tenant_id=context.tenant_id, binding_id=context.binding_id, external_message_id=message.external_message_id)
        claim = self.adapters.idempotency.claim(key, content_fingerprint(message), message.trace_id, self._now())
        if claim.disposition == ClaimDisposition.CONFLICT:
            self._audit(scope, message, context, AuditDecision.IDEMPOTENCY_CONFLICT, session_id=identity.platform_session_id)
            self._record_metrics(scope, message, started, outcome="error")
            return OutboundReply(
                status=ReplyStatus.CONFLICT,
                trace_id=message.trace_id,
                tenant_id=context.tenant_id,
                platform_session_id=identity.platform_session_id,
                external_message_id=message.external_message_id,
                delivery_action=DeliveryAction.NONE,
                error=ErrorDetail(code="idempotency_conflict", message="The message identifier was already used for different content.", retryable=False, execution_started=False),
            )
        if claim.disposition == ClaimDisposition.PROCESSING:
            self._audit(scope, message, context, AuditDecision.PROCESSING, session_id=identity.platform_session_id, original_trace_id=claim.original_trace_id)
            self._record_metrics(scope, message, started, outcome="success")
            return OutboundReply(
                status=ReplyStatus.PROCESSING,
                trace_id=message.trace_id,
                original_trace_id=claim.original_trace_id,
                tenant_id=context.tenant_id,
                platform_session_id=identity.platform_session_id,
                external_message_id=message.external_message_id,
                delivery_action=DeliveryAction.NONE,
            )
        if claim.disposition == ClaimDisposition.COMPLETED:
            result = claim.result
            if result is None:
                raise RuntimeError("terminal idempotency result is missing")
            decision = AuditDecision.DUPLICATE
            self._audit(scope, message, context, decision, session_id=identity.platform_session_id, original_trace_id=result.original_trace_id)
            if result.status == ExecutionStatus.SUCCEEDED:
                self._record_metrics(scope, message, started, outcome="success")
                return OutboundReply(
                    status=ReplyStatus.DUPLICATE,
                    trace_id=message.trace_id,
                    original_trace_id=result.original_trace_id,
                    tenant_id=context.tenant_id,
                    platform_session_id=result.platform_session_id,
                    external_message_id=message.external_message_id,
                    text=result.response_text,
                    delivery_action=DeliveryAction.SUPPRESS,
                )
            self._record_metrics(scope, message, started, outcome="error")
            return OutboundReply(
                status=ReplyStatus.FAILED,
                trace_id=message.trace_id,
                original_trace_id=result.original_trace_id,
                tenant_id=context.tenant_id,
                platform_session_id=result.platform_session_id,
                external_message_id=message.external_message_id,
                delivery_action=DeliveryAction.SUPPRESS,
                error=ErrorDetail(code=result.error_code or "outcome_unknown", message=result.error_message or "Agent outcome is unknown.", retryable=False, execution_started=True),
            )
        owner_token = claim.owner_token
        if owner_token is None:
            raise RuntimeError("acquired claim has no owner token")
        async with self.locks.acquire(identity.platform_session_id):
            try:
                self._audit(scope, message, context, AuditDecision.AUTHORIZED, session_id=identity.platform_session_id)
            except AuditUnavailable:
                self.adapters.idempotency.mark_pre_start_failed(key, owner_token, "audit_unavailable", self._now())
                self._record_metrics(scope, message, started, outcome="error")
                return self._failed_reply(
                    message,
                    tenant_id=context.tenant_id,
                    session_id=identity.platform_session_id,
                    code="audit_unavailable",
                    safe_message="Audit service is unavailable.",
                    retryable=True,
                    execution_started=False,
                )
            try:
                prepared = await self.worker.prepare(context, identity, message.text)
            except asyncio.CancelledError:
                self.adapters.idempotency.mark_pre_start_failed(key, owner_token, "cancelled", self._now())
                self._record_metrics(scope, message, started, outcome="error")
                raise
            except (AgentPreparationFailed, Exception) as exc:
                if isinstance(exc, (KeyboardInterrupt, SystemExit)):
                    raise
                self.adapters.idempotency.mark_pre_start_failed(key, owner_token, "agent_unavailable", self._now())
                self._record_metrics(scope, message, started, outcome="error")
                return self._failed_reply(
                    message,
                    tenant_id=context.tenant_id,
                    session_id=identity.platform_session_id,
                    code="agent_unavailable",
                    safe_message="Agent is unavailable.",
                    retryable=True,
                    execution_started=False,
                )
            try:
                self._audit(scope, message, context, AuditDecision.EXECUTION_STARTED, session_id=identity.platform_session_id)
            except AuditUnavailable:
                self.adapters.idempotency.mark_pre_start_failed(key, owner_token, "audit_unavailable", self._now())
                self._record_metrics(scope, message, started, outcome="error")
                return self._failed_reply(
                    message, tenant_id=context.tenant_id,
                    session_id=identity.platform_session_id,
                    code="audit_unavailable", safe_message="Audit service is unavailable.",
                    retryable=True, execution_started=False,
                )
            self.adapters.idempotency.mark_running(key, owner_token, message.trace_id, self._now())
            started_at = self._now()
            try:
                execution = await prepared.execute(timeout_seconds=30)
                decision = AuditDecision.SUCCEEDED
                result = ExecutionResult(
                    status=ExecutionStatus.SUCCEEDED,
                    response_text=execution.final_text,
                    original_trace_id=message.trace_id,
                    platform_session_id=identity.platform_session_id,
                    started_at=started_at,
                    finished_at=self._now(),
                    agent_event_count=execution.event_count,
                    final_response_count=execution.final_response_count,
                    delivery_action=DeliveryAction.DELIVER,
                )
            except (OutcomeUnknown, asyncio.CancelledError, TimeoutError):
                decision = AuditDecision.OUTCOME_UNKNOWN
                result = ExecutionResult(
                    status=ExecutionStatus.OUTCOME_UNKNOWN,
                    error_code="outcome_unknown",
                    error_message="Agent outcome is unknown.",
                    original_trace_id=message.trace_id,
                    platform_session_id=identity.platform_session_id,
                    started_at=started_at,
                    finished_at=self._now(),
                    agent_event_count=0,
                    final_response_count=0,
                    delivery_action=DeliveryAction.NONE,
                )
            except AgentExecutionFailed:
                decision = AuditDecision.AGENT_FAILED
                result = ExecutionResult(
                    status=ExecutionStatus.FAILED_POST_START,
                    error_code="agent_failed",
                    error_message="Agent execution failed.",
                    original_trace_id=message.trace_id,
                    platform_session_id=identity.platform_session_id,
                    started_at=started_at,
                    finished_at=self._now(),
                    agent_event_count=0,
                    final_response_count=0,
                    delivery_action=DeliveryAction.NONE,
                )
            try:
                self._audit(scope, message, context, decision, session_id=identity.platform_session_id, error_type=result.error_code)
            except AuditUnavailable:
                result = ExecutionResult(
                    status=ExecutionStatus.FAILED_POST_START,
                    error_code="audit_incomplete",
                    error_message="Audit completion failed.",
                    original_trace_id=message.trace_id,
                    platform_session_id=identity.platform_session_id,
                    started_at=started_at,
                    finished_at=self._now(),
                    agent_event_count=0,
                    final_response_count=0,
                    delivery_action=DeliveryAction.NONE,
                )
            try:
                self.adapters.idempotency.complete(key, owner_token, result, self._now())
            except ConditionalWriteFailed:
                result = ExecutionResult(
                    status=ExecutionStatus.OUTCOME_UNKNOWN,
                    error_code="outcome_unknown",
                    error_message="Agent outcome is unknown.",
                    original_trace_id=message.trace_id,
                    platform_session_id=identity.platform_session_id,
                    started_at=started_at,
                    finished_at=self._now(),
                    agent_event_count=0,
                    final_response_count=0,
                    delivery_action=DeliveryAction.NONE,
                )
                self.adapters.idempotency.mark_outcome_unknown(key, owner_token, result, self._now())
        self._record_metrics(
            scope,
            message,
            started,
            outcome="success" if result.status == ExecutionStatus.SUCCEEDED else "error",
            agent=True,
            delivered=result.status == ExecutionStatus.SUCCEEDED,
        )
        if result.status != ExecutionStatus.SUCCEEDED:
            return self._failed_reply(
                message,
                tenant_id=context.tenant_id,
                session_id=identity.platform_session_id,
                code=result.error_code or "outcome_unknown",
                safe_message=result.error_message or "Agent outcome is unknown.",
                retryable=False,
                execution_started=True,
                original_trace_id=result.original_trace_id,
            )
        return OutboundReply(
            status=ReplyStatus.SUCCEEDED,
            trace_id=message.trace_id,
            tenant_id=context.tenant_id,
            platform_session_id=identity.platform_session_id,
            external_message_id=message.external_message_id,
            text=execution.final_text,
            delivery_action=DeliveryAction.DELIVER,
        )

    async def handle_verified_message_for_test(self, message: InboundMessage) -> OutboundReply:
        scope = VerifiedBindingScope._issue(binding_id=message.binding_id, channel=message.channel)
        return await self.handle_verified_message(scope, message)
