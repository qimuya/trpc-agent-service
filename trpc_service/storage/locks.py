"""Per-session asynchronous leases without a global execution lock."""

from __future__ import annotations

import asyncio
import re
from contextlib import asynccontextmanager
from collections.abc import AsyncIterator


class SessionLockManager:
    def __init__(self) -> None:
        self._locks: dict[str, asyncio.Lock] = {}
        self._guard = asyncio.Lock()

    @asynccontextmanager
    async def acquire(self, platform_session_id: str) -> AsyncIterator[None]:
        if re.fullmatch(r"sess_[0-9a-f]{64}", platform_session_id) is None:
            raise ValueError("a tenant-scoped platform session id is required")
        async with self._guard:
            lock = self._locks.setdefault(platform_session_id, asyncio.Lock())
        await lock.acquire()
        try:
            yield
        finally:
            if lock.locked():
                lock.release()
