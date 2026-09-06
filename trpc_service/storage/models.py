"""Immutable idempotency state machine and content identity models."""

from __future__ import annotations

from datetime import datetime
from enum import StrEnum
from hashlib import sha256
from typing import Self
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, model_validator

from trpc_service.channels.contracts import DeliveryAction, InboundMessage


class IdempotencyState(StrEnum):
    PENDING = "pending"
    RUNNING = "running"
    SUCCEEDED = "succeeded"
    FAILED_PRE_START = "failed_pre_start"
    FAILED_POST_START = "failed_post_start"
    OUTCOME_UNKNOWN = "outcome_unknown"


class ClaimDisposition(StrEnum):
    ACQUIRED = "acquired"
    PROCESSING = "processing"
    COMPLETED = "completed"
    CONFLICT = "conflict"


class ExecutionStatus(StrEnum):
    SUCCEEDED = "succeeded"
    FAILED_POST_START = "failed_post_start"
    OUTCOME_UNKNOWN = "outcome_unknown"


class _Frozen(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)


class IdempotencyKey(_Frozen):
    tenant_id: str
    binding_id: str
    external_message_id: str


class ExecutionResult(_Frozen):
    status: ExecutionStatus
    response_text: str | None = Field(default=None, min_length=1, max_length=4000)
    error_code: str | None = None
    error_message: str | None = None
    original_trace_id: UUID
    platform_session_id: str
    started_at: datetime
    finished_at: datetime
    agent_event_count: int = Field(ge=0)
    final_response_count: int = Field(ge=0)
    delivery_action: DeliveryAction

    @model_validator(mode="after")
    def validate_result(self) -> Self:
        if self.status == ExecutionStatus.SUCCEEDED:
            if self.response_text is None or self.final_response_count != 1:
                raise ValueError("successful execution requires exactly one final response")
        elif self.error_code is None or self.response_text is not None:
            raise ValueError("failed execution requires a safe error")
        return self


class IdempotencyRecord(_Frozen):
    key: IdempotencyKey
    content_fingerprint: str = Field(pattern=r"^[0-9a-f]{64}$")
    state: IdempotencyState
    attempt: int = Field(ge=1)
    owner_token: str | None
    first_claim_trace_id: UUID
    owner_trace_id: UUID | None
    execution_trace_id: UUID | None = None
    result: ExecutionResult | None = None
    created_at: datetime
    updated_at: datetime
    pre_start_error: str | None = None

    @classmethod
    def pending(cls, *, key: IdempotencyKey, content_fingerprint: str, owner_token: str, trace_id: UUID, now: datetime) -> IdempotencyRecord:
        return cls(
            key=key,
            content_fingerprint=content_fingerprint,
            state=IdempotencyState.PENDING,
            attempt=1,
            owner_token=owner_token,
            first_claim_trace_id=trace_id,
            owner_trace_id=trace_id,
            created_at=now,
            updated_at=now,
        )

    def _require(self, state: IdempotencyState, owner_token: str) -> None:
        if self.state != state or self.owner_token != owner_token:
            raise ValueError("invalid idempotency transition")

    def mark_running(self, owner_token: str, execution_trace_id: UUID, now: datetime) -> IdempotencyRecord:
        self._require(IdempotencyState.PENDING, owner_token)
        return self.model_copy(update={"state": IdempotencyState.RUNNING, "execution_trace_id": execution_trace_id, "updated_at": now})

    def mark_pre_start_failed(self, owner_token: str, safe_error: str, now: datetime) -> IdempotencyRecord:
        self._require(IdempotencyState.PENDING, owner_token)
        return self.model_copy(update={"state": IdempotencyState.FAILED_PRE_START, "owner_token": None, "owner_trace_id": None, "pre_start_error": safe_error, "updated_at": now})

    def reclaim(self, owner_token: str, trace_id: UUID, now: datetime) -> IdempotencyRecord:
        if self.state != IdempotencyState.FAILED_PRE_START:
            raise ValueError("invalid idempotency transition")
        return self.model_copy(update={"state": IdempotencyState.PENDING, "attempt": self.attempt + 1, "owner_token": owner_token, "owner_trace_id": trace_id, "execution_trace_id": None, "result": None, "updated_at": now})

    def complete(self, owner_token: str, result: ExecutionResult, now: datetime) -> IdempotencyRecord:
        self._require(IdempotencyState.RUNNING, owner_token)
        terminal = IdempotencyState(result.status.value)
        return self.model_copy(update={"state": terminal, "owner_token": None, "owner_trace_id": None, "result": result, "updated_at": now})


class ClaimResult(_Frozen):
    disposition: ClaimDisposition
    owner_token: str | None = None
    attempt: int | None = None
    original_trace_id: UUID | None = None
    result: ExecutionResult | None = None


def _digest_parts(*parts: str) -> str:
    digest = sha256()
    for part in parts:
        encoded = part.encode("utf-8")
        digest.update(len(encoded).to_bytes(8, "big"))
        digest.update(encoded)
    return digest.hexdigest()


def content_fingerprint(message: InboundMessage) -> str:
    return _digest_parts(
        message.channel.value,
        message.external_user_id,
        message.conversation_type.value,
        message.external_conversation_id,
        message.text,
    )
