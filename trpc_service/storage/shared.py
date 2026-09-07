"""Lifecycle boundary for Redis/PostgreSQL shared-state adapters."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from redis.asyncio import Redis

from trpc_service.config.settings import RuntimeProfile, RuntimeSettings
from trpc_service.storage.contracts import ConfigurationUnavailable
from trpc_service.storage.models import NodeIdentity
from trpc_service.storage.postgres.database import PostgresDatabase
from trpc_service.storage.postgres.repositories import PostgresAuditRepository, PostgresConfigurationRepository
from trpc_service.storage.redis_scripts.loader import RedisScriptLoader
from trpc_service.storage.redis_idempotency import RedisIdempotencyRepository


@dataclass(slots=True)
class SharedPlatformAdapters:
    settings: RuntimeSettings
    node: NodeIdentity
    redis: Any
    database: PostgresDatabase
    scripts: RedisScriptLoader
    configuration: PostgresConfigurationRepository
    audit: PostgresAuditRepository
    idempotency: RedisIdempotencyRepository
    closed: bool = False

    @classmethod
    async def create(
        cls, settings: RuntimeSettings, node: NodeIdentity
    ) -> "SharedPlatformAdapters":
        if settings.profile != RuntimeProfile.SHARED:
            raise ConfigurationUnavailable()
        assert settings.redis_url is not None
        assert settings.database_url is not None
        redis = Redis.from_url(
            settings.redis_url.get_secret_value(),
            decode_responses=True,
        )
        database = PostgresDatabase(settings.database_url.get_secret_value())
        try:
            await redis.ping()
            await database.verify_schema()
        except Exception:
            await redis.aclose()
            await database.close()
            raise ConfigurationUnavailable() from None
        return cls(
            settings, node, redis, database, RedisScriptLoader(redis),
            PostgresConfigurationRepository(database),
            PostgresAuditRepository(database, node_id=node.node_id),
            RedisIdempotencyRepository(redis, node_id=node.node_id),
        )

    async def get_auth_material(self, binding_id: str, channel: Any) -> Any:
        return await self.configuration.get_auth_material(binding_id, channel)

    async def resolve_active_context(self, scope: Any, *, external_user_id: str, trace_id: Any) -> Any:
        return await self.configuration.resolve_active_context(
            scope, external_user_id=external_user_id, trace_id=trace_id
        )

    async def readiness(self) -> bool:
        if self.closed:
            return False
        try:
            await self.redis.ping()
            await self.database.verify_schema()
        except Exception:
            return False
        return True

    async def close(self) -> None:
        if self.closed:
            return
        self.closed = True
        await self.redis.aclose()
        await self.database.close()
