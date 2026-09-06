"""Safe structured operational logging helpers.

Only already-classified identifiers and outcomes are accepted here. Request bodies,
signatures, credentials and external user identifiers deliberately have no parameters.
"""

from __future__ import annotations

import json
import logging
from uuid import UUID

_LOGGER = logging.getLogger("trpc_service")


def log_delivery(*, trace_id: UUID, outcome: str, status_code: int) -> None:
    _LOGGER.info(
        json.dumps(
            {"event": "local_message_delivery", "trace_id": str(trace_id), "outcome": outcome, "status_code": status_code},
            separators=(",", ":"),
        )
    )


__all__ = ["log_delivery"]
