"""Cross-suite fixtures that never contain committed credentials."""

from __future__ import annotations

import secrets
import socket
from collections.abc import Iterator
from datetime import datetime

import pytest

from tests.support import FIXED_UTC


@pytest.fixture
def fixed_utc() -> datetime:
    return FIXED_UTC


@pytest.fixture
def runtime_secret_env(monkeypatch: pytest.MonkeyPatch) -> dict[str, str]:
    values = {
        "TRPC_DEMO_ALPHA_SECRET": secrets.token_urlsafe(32),
        "TRPC_DEMO_BETA_SECRET": secrets.token_urlsafe(32),
    }
    for name, value in values.items():
        monkeypatch.setenv(name, value)
    return values


@pytest.fixture
def block_external_network(monkeypatch: pytest.MonkeyPatch) -> Iterator[None]:
    original_connect = socket.socket.connect

    def guarded_connect(sock: socket.socket, address: object) -> object:
        host = address[0] if isinstance(address, tuple) and address else ""
        if host not in {"127.0.0.1", "::1", "localhost"}:
            raise AssertionError("external network access is forbidden in offline tests")
        return original_connect(sock, address)  # type: ignore[arg-type]

    monkeypatch.setattr(socket.socket, "connect", guarded_connect)
    yield
