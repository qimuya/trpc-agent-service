"""Command-line entry points for the local validation service."""

from __future__ import annotations

import argparse
import json
import os
import time
from dataclasses import dataclass, field
from urllib.parse import urlsplit
from uuid import uuid4

import httpx
import uvicorn

from trpc_service.channels.hmac_auth import body_sha256, canonical_string, sign_request
from trpc_service.config.settings import RuntimeProfile, load_runtime_settings
from trpc_service.storage.postgres.database import PostgresDatabase
from trpc_service.web.app import create_app, create_shared_app
from trpc_service.config.settings import build_demo_settings
from trpc_service.storage.postgres.repositories import PostgresConfigurationRepository


def build_serve_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="trpc-agent-local-serve")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8000)
    return parser


def serve_main(argv: list[str] | None = None) -> int:
    args = build_serve_parser().parse_args(argv)
    if args.host not in {"127.0.0.1", "localhost", "::1"}:
        raise SystemExit("The local validation service may only listen on loopback.")
    app = create_app(os.environ)
    uvicorn.run(app, host=args.host, port=args.port)
    return 0


def build_shared_serve_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="trpc-agent-shared-serve")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, required=True)
    parser.add_argument("--node-id", required=True)
    return parser


def shared_serve_main(argv: list[str] | None = None) -> int:
    args = build_shared_serve_parser().parse_args(argv)
    if args.host not in {"127.0.0.1", "localhost", "::1"}:
        raise SystemExit("The shared validation service may only listen on loopback.")
    runtime_environ = dict(os.environ)
    runtime_environ["TRPC_RUNTIME_PROFILE"] = "shared"
    runtime_environ["TRPC_NODE_ID"] = args.node_id
    app = create_shared_app(runtime_environ)
    uvicorn.run(app, host=args.host, port=args.port)
    return 0


async def _initialize_shared() -> None:
    settings = load_runtime_settings(os.environ)
    if settings.profile != RuntimeProfile.SHARED or settings.database_url is None:
        raise SystemExit("Shared runtime configuration is required.")
    database = PostgresDatabase(settings.database_url.get_secret_value())
    try:
        await database.initialize_schema()
        await PostgresConfigurationRepository(database).seed(build_demo_settings())
    finally:
        await database.close()


def shared_init_main(argv: list[str] | None = None) -> int:
    argparse.ArgumentParser(prog="trpc-agent-shared-init").parse_args(argv)
    import asyncio

    asyncio.run(_initialize_shared())
    return 0


@dataclass(frozen=True, slots=True)
class SignedRequest:
    url: str
    content: bytes = field(repr=False)
    headers: dict[str, str] = field(repr=False)


def build_signed_request(args: object, environ: object, *, timestamp: int | None = None) -> SignedRequest:
    secret_name = getattr(args, "secret_env")
    secret = environ.get(secret_name, "")
    if not secret:
        raise SystemExit("Runtime secret is unavailable.")
    parsed_url = urlsplit(getattr(args, "url"))
    if parsed_url.scheme != "http" or parsed_url.hostname not in {"127.0.0.1", "localhost", "::1"} or parsed_url.username or parsed_url.password:
        raise SystemExit("The local sender may only connect to a loopback HTTP URL.")
    payload = {
        "channel": "local_http",
        "external_message_id": getattr(args, "external_message_id"),
        "external_user_id": getattr(args, "external_user_id"),
        "conversation_type": getattr(args, "conversation_type"),
        "external_conversation_id": getattr(args, "external_conversation_id"),
        "text": getattr(args, "text"),
    }
    raw = json.dumps(payload, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
    stamp = str(timestamp if timestamp is not None else int(time.time()))
    binding_id = getattr(args, "binding_id")
    signature = sign_request(
        secret.encode("utf-8"),
        canonical_string(stamp, binding_id, payload["external_message_id"], body_sha256(raw)),
    )
    base_url = getattr(args, "url").rstrip("/")
    return SignedRequest(
        url=base_url + "/v1/local/messages",
        content=raw,
        headers={
            "content-type": "application/json",
            "x-channel-binding": binding_id,
            "x-request-timestamp": stamp,
            "x-signature": signature,
            "x-trace-id": getattr(args, "trace_id", None) or str(uuid4()),
        },
    )


def build_send_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="trpc-agent-local-send")
    parser.add_argument("--url", default="http://127.0.0.1:8000")
    parser.add_argument("--binding-id", required=True)
    parser.add_argument("--secret-env", required=True)
    parser.add_argument("--external-message-id", required=True)
    parser.add_argument("--external-user-id", required=True)
    parser.add_argument("--conversation-type", choices=("direct", "group"), required=True)
    parser.add_argument("--external-conversation-id", required=True)
    parser.add_argument("--text", required=True)
    parser.add_argument("--trace-id")
    return parser


def _post_local(request: SignedRequest) -> httpx.Response:
    with httpx.Client(trust_env=False) as client:
        return client.post(request.url, content=request.content, headers=request.headers, timeout=35)


def send_main(argv: list[str] | None = None) -> int:
    args = build_send_parser().parse_args(argv)
    request = build_signed_request(args, os.environ)
    try:
        response = _post_local(request)
    except httpx.HTTPError:
        print(json.dumps({"status": "failed", "error": {"code": "transport_error", "message": "Local service request failed."}}))
        return 2
    try:
        payload = response.json()
    except (ValueError, json.JSONDecodeError):
        print(json.dumps({"status": "failed", "error": {"code": "invalid_response", "message": "Local service returned an invalid response."}}))
        return 2
    print(json.dumps(payload, ensure_ascii=False, separators=(",", ":")))
    return 0 if response.status_code < 400 else 1
