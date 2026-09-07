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
