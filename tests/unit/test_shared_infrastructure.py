from __future__ import annotations

from pathlib import Path

import pytest

from trpc_service.config.settings import load_runtime_settings
from trpc_service.storage.contracts import ConfigurationUnavailable
from trpc_service.storage.models import IdempotencyKey, NodeIdentity
from trpc_service.storage.postgres.models import Base
from trpc_service.storage.redis_codec import RedisKeyCodec
from trpc_service.storage.redis_scripts.loader import RedisScriptLoader
from trpc_service.storage.shared import SharedPlatformAdapters
from trpc_service.storage.postgres.database import SUPPORTED_SCHEMA_VERSION


def test_postgres_schema_contains_authoritative_and_recovery_tables() -> None:
    assert {
        "schema_migrations",
        "tenants",
        "agent_applications",
        "channel_bindings",
        "persistent_audit_records",
        "recovery_markers",
    } <= set(Base.metadata.tables)
    sql = Path(
        "trpc_service/storage/postgres/migrations/001_shared_state.sql"
    ).read_text(encoding="utf-8")
    assert "CREATE TABLE IF NOT EXISTS" in sql
    assert "secret_value" not in sql
    migration = Path(
        "trpc_service/storage/postgres/migrations/002_audit_agent_scope.sql"
    ).read_text(encoding="utf-8")
    assert SUPPORTED_SCHEMA_VERSION == 2
    assert "ADD COLUMN IF NOT EXISTS agent_id" in migration


def test_redis_key_codec_is_scoped_and_hides_external_identifiers() -> None:
    codec = RedisKeyCodec(namespace="pytest")
    alpha = codec.idempotency(
        IdempotencyKey(
            tenant_id="tenant-alpha",
            binding_id="binding-alpha",
            external_message_id="private-message-id",
        )
    )
    beta = codec.idempotency(
        IdempotencyKey(
            tenant_id="tenant-beta",
            binding_id="binding-alpha",
            external_message_id="private-message-id",
        )
    )
    assert alpha != beta
    assert "private-message-id" not in alpha
    assert alpha.startswith("pytest:")


async def test_script_loader_recovers_from_noscript() -> None:
    class FakeRedis:
        def __init__(self) -> None:
            self.loads = 0
            self.evals = 0

        async def script_load(self, source: str) -> str:
            self.loads += 1
            assert source == "return ARGV[1]"
            return "sha"

        async def evalsha(self, sha: str, keys: int, *args: object) -> object:
            self.evals += 1
            if self.evals == 1:
                from redis.exceptions import NoScriptError

                raise NoScriptError("not exposed")
            return args[-1]

    client = FakeRedis()
    loader = RedisScriptLoader(client)
    result = await loader.execute_source("echo", "return ARGV[1]", [], ["ok"])
    assert result == "ok"
    assert client.loads == 2


async def test_shared_lifecycle_never_accepts_local_profile() -> None:
    local = load_runtime_settings({})
    with pytest.raises(ConfigurationUnavailable):
        await SharedPlatformAdapters.create(local, NodeIdentity(node_id="worker-a"))
