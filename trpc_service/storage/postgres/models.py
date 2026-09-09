"""SQLAlchemy schema for authoritative configuration, audit and recovery."""

from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from typing import Any

from sqlalchemy import (
    BigInteger,
    Boolean,
    CheckConstraint,
    DateTime,
    ForeignKey,
    ForeignKeyConstraint,
    Index,
    JSON,
    Numeric,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


class Base(DeclarativeBase):
    pass


class SchemaMigrationRow(Base):
    __tablename__ = "schema_migrations"
    __table_args__ = (CheckConstraint("version > 0"),)

    version: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(120))
    checksum: Mapped[str] = mapped_column(String(64))
    applied_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))


class TenantRow(Base):
    __tablename__ = "tenants"
    __table_args__ = (
        CheckConstraint("config_version > 0"),
        CheckConstraint("status IN ('active', 'disabled')"),
    )

    tenant_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    display_name: Mapped[str] = mapped_column(String(120))
    status: Mapped[str] = mapped_column(String(16))
    config_version: Mapped[int] = mapped_column(BigInteger)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))


class AgentApplicationRow(Base):
    __tablename__ = "agent_applications"
    __table_args__ = (
        CheckConstraint("config_version > 0"),
        CheckConstraint("status IN ('active', 'disabled')"),
    )

    tenant_id: Mapped[str] = mapped_column(
        String(64), ForeignKey("tenants.tenant_id"), primary_key=True
    )
    agent_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    agent_name: Mapped[str] = mapped_column(String(120))
    status: Mapped[str] = mapped_column(String(16))
    model_profile: Mapped[str] = mapped_column(String(64))
    instruction: Mapped[str] = mapped_column(Text)
    config_version: Mapped[int] = mapped_column(BigInteger)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))


class ChannelBindingRow(Base):
    __tablename__ = "channel_bindings"
    __table_args__ = (
        ForeignKeyConstraint(
            ["tenant_id", "agent_id"],
            ["agent_applications.tenant_id", "agent_applications.agent_id"],
        ),
        CheckConstraint("config_version > 0"),
        CheckConstraint("status IN ('active', 'disabled')"),
    )

    binding_id: Mapped[str] = mapped_column(String(96), primary_key=True)
    tenant_id: Mapped[str] = mapped_column(String(64))
    agent_id: Mapped[str] = mapped_column(String(64))
    channel: Mapped[str] = mapped_column(String(32))
    status: Mapped[str] = mapped_column(String(16))
    secret_ref: Mapped[str] = mapped_column(String(128))
    signature_version: Mapped[str] = mapped_column(String(16))
    config_version: Mapped[int] = mapped_column(BigInteger)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    provider_tenant_key: Mapped[str | None] = mapped_column(String(128))
    provider_app_or_bot_id: Mapped[str | None] = mapped_column(String(128))
    channel_identity_digest: Mapped[str | None] = mapped_column(String(64))


class PersistentAuditRecordRow(Base):
    __tablename__ = "persistent_audit_records"
    __table_args__ = (
        CheckConstraint("latency_ms >= 0"),
        CheckConstraint("cost >= 0"),
        Index("ix_audit_tenant_trace", "tenant_id", "trace_id", "created_at"),
        Index("ix_audit_tenant_session", "tenant_id", "platform_session_id", "created_at"),
        Index("ix_audit_tenant_agent", "tenant_id", "agent_id", "created_at"),
        Index("ix_audit_tenant_message", "tenant_id", "external_message_digest", "created_at"),
        UniqueConstraint(
            "tenant_id",
            "external_message_digest",
            "message_generation",
            "decision",
            "audit_kind",
            name="uq_business_terminal_generation",
        ),
    )

    audit_id: Mapped[str] = mapped_column(String(36), primary_key=True)
    audit_kind: Mapped[str] = mapped_column(String(16))
    decision: Mapped[str] = mapped_column(String(40))
    trace_id: Mapped[str] = mapped_column(String(36))
    first_claim_trace_id: Mapped[str | None] = mapped_column(String(36))
    owner_trace_id: Mapped[str | None] = mapped_column(String(36))
    execution_trace_id: Mapped[str | None] = mapped_column(String(36))
    tenant_id: Mapped[str | None] = mapped_column(String(64))
    agent_id: Mapped[str | None] = mapped_column(String(64))
    channel: Mapped[str] = mapped_column(String(32), default="local_http")
    node_id: Mapped[str] = mapped_column(String(64))
    process_instance_id: Mapped[str] = mapped_column(String(36))
    binding_id_digest: Mapped[str] = mapped_column(String(71))
    external_message_digest: Mapped[str | None] = mapped_column(String(71))
    platform_session_id: Mapped[str | None] = mapped_column(String(69))
    message_generation: Mapped[int | None] = mapped_column(BigInteger)
    session_generation: Mapped[int | None] = mapped_column(BigInteger)
    rejected_generation: Mapped[int | None] = mapped_column(BigInteger)
    current_generation: Mapped[int | None] = mapped_column(BigInteger)
    error_type: Mapped[str | None] = mapped_column(String(64))
    result_digest: Mapped[str | None] = mapped_column(String(64))
    latency_ms: Mapped[Decimal] = mapped_column(Numeric)
    cost: Mapped[Decimal] = mapped_column(Numeric)
    recovery_status: Mapped[str | None] = mapped_column(String(32))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    adapter_node_id: Mapped[str | None] = mapped_column(String(64))
    adapter_generation: Mapped[int | None] = mapped_column(BigInteger)
    channel_identity_digest: Mapped[str | None] = mapped_column(String(64))
    provider_message_digest: Mapped[str | None] = mapped_column(String(71))
    delivery_id: Mapped[str | None] = mapped_column(String(36))
    delivery_attempt_no: Mapped[int | None] = mapped_column(BigInteger)
    delivery_status: Mapped[str | None] = mapped_column(String(32))


class RecoveryMarkerRow(Base):
    __tablename__ = "recovery_markers"
    __table_args__ = (
        CheckConstraint("message_generation > 0"),
        CheckConstraint("session_generation > 0"),
        CheckConstraint("replay_allowed = false"),
        UniqueConstraint(
            "tenant_id",
            "binding_id_digest",
            "external_message_digest",
            "execution_trace_id",
            name="uq_recovery_identity",
        ),
    )

    recovery_id: Mapped[str] = mapped_column(String(36), primary_key=True)
    tenant_id: Mapped[str] = mapped_column(String(64))
    binding_id_digest: Mapped[str] = mapped_column(String(71))
    external_message_digest: Mapped[str] = mapped_column(String(71))
    platform_session_id: Mapped[str] = mapped_column(String(69))
    idempotency_key_digest: Mapped[str] = mapped_column(String(64))
    message_generation: Mapped[int] = mapped_column(BigInteger)
    session_generation: Mapped[int] = mapped_column(BigInteger)
    execution_trace_id: Mapped[str] = mapped_column(String(36))
    state: Mapped[str] = mapped_column(String(32))
    result_status: Mapped[str] = mapped_column(String(32))
    result_payload: Mapped[dict[str, Any]] = mapped_column(JSON)
    result_digest: Mapped[str] = mapped_column(String(64))
    replay_allowed: Mapped[bool] = mapped_column(Boolean, default=False)
    failure_stage: Mapped[str | None] = mapped_column(String(64))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    reconciled_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class DeliveryRecordRow(Base):
    __tablename__ = "delivery_records"
    __table_args__ = (
        CheckConstraint(
            "status IN ('pending', 'sending', 'retry_wait', 'delivered', "
            "'delivery_failed', 'delivery_unknown')"
        ),
        CheckConstraint("adapter_generation > 0"),
        UniqueConstraint(
            "tenant_id",
            "idempotency_key_digest",
            "channel",
            "binding_id",
            name="uq_delivery_execution_scope",
        ),
        Index("ix_delivery_due", "tenant_id", "status", "next_attempt_at"),
        Index("ix_delivery_execution_trace", "tenant_id", "execution_trace_id"),
    )

    delivery_id: Mapped[str] = mapped_column(String(36), primary_key=True)
    tenant_id: Mapped[str] = mapped_column(String(64), ForeignKey("tenants.tenant_id"))
    binding_id: Mapped[str] = mapped_column(
        String(96), ForeignKey("channel_bindings.binding_id")
    )
    channel: Mapped[str] = mapped_column(String(32))
    idempotency_key_digest: Mapped[str] = mapped_column(String(64))
    execution_trace_id: Mapped[str] = mapped_column(String(36))
    reply_context: Mapped[dict[str, Any]] = mapped_column(JSON)
    result_digest: Mapped[str] = mapped_column(String(64))
    status: Mapped[str] = mapped_column(String(32))
    adapter_generation: Mapped[int] = mapped_column(BigInteger)
    next_attempt_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))


class DeliveryAttemptRow(Base):
    __tablename__ = "delivery_attempts"
    __table_args__ = (
        CheckConstraint("attempt_no BETWEEN 1 AND 4"),
        CheckConstraint("adapter_generation > 0"),
        CheckConstraint("retry_delay_seconds IS NULL OR retry_delay_seconds IN (1, 2, 4)"),
        UniqueConstraint(
            "delivery_id", "attempt_no", name="uq_delivery_attempt_number"
        ),
    )

    attempt_id: Mapped[str] = mapped_column(String(36), primary_key=True)
    delivery_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("delivery_records.delivery_id")
    )
    attempt_no: Mapped[int] = mapped_column(BigInteger)
    trace_id: Mapped[str] = mapped_column(String(36))
    adapter_node_id: Mapped[str] = mapped_column(String(64))
    adapter_generation: Mapped[int] = mapped_column(BigInteger)
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    outcome: Mapped[str | None] = mapped_column(String(32))
    safe_error_code: Mapped[str | None] = mapped_column(String(64))
    retry_delay_seconds: Mapped[int | None] = mapped_column(BigInteger)
