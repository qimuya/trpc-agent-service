"""Safe PostgreSQL engine lifecycle and schema gate."""

from __future__ import annotations

from datetime import datetime, timezone
from hashlib import sha256
from pathlib import Path

from sqlalchemy import func, select, text
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncEngine, create_async_engine

from trpc_service.storage.contracts import ConfigurationUnavailable
from trpc_service.storage.postgres.models import Base, SchemaMigrationRow


SUPPORTED_SCHEMA_VERSION = 4
_MIGRATION_DIR = Path(__file__).with_name("migrations")


class PostgresDatabase:
    def __init__(self, url: str) -> None:
        self.engine: AsyncEngine = create_async_engine(
            url, pool_pre_ping=True, hide_parameters=True
        )

    async def initialize_schema(self) -> None:
        async with self.engine.begin() as connection:
            await connection.run_sync(Base.metadata.create_all)
            applied_versions = set(
                (await connection.scalars(select(SchemaMigrationRow.version))).all()
            )
            current_version = max(applied_versions, default=None)
            if current_version is not None and current_version > SUPPORTED_SCHEMA_VERSION:
                raise ConfigurationUnavailable()
            await connection.execute(
                insert(SchemaMigrationRow).values(
                    version=1, name="001_shared_state",
                    checksum=sha256(b"001_shared_state:sqlalchemy-metadata-v1").hexdigest(),
                    applied_at=datetime.now(timezone.utc),
                ).on_conflict_do_nothing(index_elements=["version"])
            )
            if 2 not in applied_versions:
                source = (_MIGRATION_DIR / "002_audit_agent_scope.sql").read_text(encoding="utf-8")
                for statement in (part.strip() for part in source.split(";")):
                    if statement:
                        await connection.execute(text(statement))
                await connection.execute(
                    insert(SchemaMigrationRow).values(
                        version=2, name="002_audit_agent_scope",
                        checksum=sha256(source.encode("utf-8")).hexdigest(),
                        applied_at=datetime.now(timezone.utc),
                    ).on_conflict_do_nothing(index_elements=["version"])
                )
            if 3 not in applied_versions:
                source = (_MIGRATION_DIR / "003_dual_im.sql").read_text(encoding="utf-8")
                for statement in (part.strip() for part in source.split(";")):
                    if statement:
                        await connection.execute(text(statement))
                await connection.execute(
                    insert(SchemaMigrationRow).values(
                        version=3, name="003_dual_im",
                        checksum=sha256(source.encode("utf-8")).hexdigest(),
                        applied_at=datetime.now(timezone.utc),
                    ).on_conflict_do_nothing(index_elements=["version"])
                )
            if 4 not in applied_versions:
                source = (_MIGRATION_DIR / "004_preauth_audit_channel.sql").read_text(encoding="utf-8")
                for statement in (part.strip() for part in source.split(";")):
                    if statement:
                        await connection.execute(text(statement))
                await connection.execute(
                    insert(SchemaMigrationRow).values(
                        version=4, name="004_preauth_audit_channel",
                        checksum=sha256(source.encode("utf-8")).hexdigest(),
                        applied_at=datetime.now(timezone.utc),
                    ).on_conflict_do_nothing(index_elements=["version"])
                )

    async def verify_schema(self) -> int:
        try:
            async with self.engine.connect() as connection:
                version = await connection.scalar(
                    select(func.max(SchemaMigrationRow.version))
                )
        except Exception:
            raise ConfigurationUnavailable() from None
        if version != SUPPORTED_SCHEMA_VERSION:
            raise ConfigurationUnavailable()
        return int(version)

    async def ping(self) -> None:
        await self.verify_schema()

    async def close(self) -> None:
        await self.engine.dispose()
