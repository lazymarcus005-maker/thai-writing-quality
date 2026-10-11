"""Streamable HTTP transport with hardening (T-015, FR-013).

Layered on the SDK's native Streamable HTTP app (which already enforces a
request-body cap and session idle timeout), this module adds:

- **Authentication**: every request must carry ``Authorization: Bearer
  <TWQ_HTTP_API_KEY>``. The key comes from the environment / secret manager
  only. Without a configured key the app refuses ALL requests (fail closed);
  anonymous mode exists solely for explicit loopback development.
- **Loopback default**: binds 127.0.0.1 unless TWQ_HTTP_HOST says otherwise.
- **Rate limiting**: per-token token bucket (429 when exhausted).
- **Tenant scoping**: ``X-Tenant`` must name a tenant from
  ``TWQ_TENANT_GLOSSARIES`` (JSON map tenant -> glossary path, "" = bundled
  default). Unknown tenants are rejected; glossary selection never crosses
  tenants.

Run: ``thai-writing-http`` (console script) or
``python -m thai_writing_mcp.http_server``.
"""

from __future__ import annotations

import hmac
import json
import os
import time
from collections import defaultdict

from starlette.requests import Request
from starlette.responses import JSONResponse

DEFAULT_PORT = 8000
DEFAULT_RATE_LIMIT_PER_MIN = 60
DEFAULT_MAX_BODY_BYTES = 1_000_000


class _TokenBucket:
    def __init__(self, capacity: int, refill_per_min: int) -> None:
        self.capacity = float(capacity)
        self.tokens = float(capacity)
        self.refill_per_sec = refill_per_min / 60.0
        self.updated = time.monotonic()

    def take(self) -> bool:
        now = time.monotonic()
        self.tokens = min(self.capacity, self.tokens + (now - self.updated) * self.refill_per_sec)
        self.updated = now
        if self.tokens >= 1:
            self.tokens -= 1
            return True
        return False


class HardeningMiddleware:
    """ASGI middleware: auth, rate limit, tenant scoping, body cap."""

    def __init__(self, app, config: HTTPConfig) -> None:
        self.app = app
        self.config = config
        self._buckets: dict[str, _TokenBucket] = defaultdict(
            lambda: _TokenBucket(
                capacity=config.rate_limit_per_min, refill_per_min=config.rate_limit_per_min
            )
        )

    async def __call__(self, scope, receive, send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return
        request = Request(scope)
        # 1. Authentication (constant-time compare).
        if self.config.api_key is None:
            await JSONResponse(
                {
                    "error": "server_not_configured",
                    "message": "TWQ_HTTP_API_KEY not set; refusing all requests",
                },
                status_code=503,
            )(scope, receive, send)
            return
        auth = request.headers.get("authorization", "")
        presented = auth[7:] if auth.lower().startswith("bearer ") else ""
        if not presented or not hmac.compare_digest(presented, self.config.api_key):
            await JSONResponse(
                {"error": "unauthorized", "message": "missing or invalid bearer token"},
                status_code=401,
            )(scope, receive, send)
            return
        # 2. Tenant scoping.
        tenant = request.headers.get("x-tenant", "default")
        if tenant not in self.config.tenants:
            await JSONResponse(
                {"error": "unknown_tenant", "message": f"tenant {tenant!r} is not configured"},
                status_code=403,
            )(scope, receive, send)
            return
        # 3. Request size cap.
        length = request.headers.get("content-length")
        if length and int(length) > self.config.max_body_bytes:
            await JSONResponse(
                {"error": "payload_too_large", "message": "request body exceeds limit"},
                status_code=413,
            )(scope, receive, send)
            return
        # 4. Rate limit per token.
        if not self._buckets[presented[:16]].take():
            await JSONResponse(
                {"error": "rate_limited", "message": "token bucket exhausted; slow down"},
                status_code=429,
                headers={"Retry-After": "5"},
            )(scope, receive, send)
            return
        await self.app(scope, receive, send)


class HTTPConfig:
    def __init__(self, env: dict[str, str] | None = None) -> None:
        merged = os.environ | (env or {})
        self.api_key: str | None = merged.get("TWQ_HTTP_API_KEY") or None
        allow_anonymous = merged.get("TWQ_HTTP_ALLOW_ANONYMOUS") == "1"
        host = merged.get("TWQ_HTTP_HOST", "127.0.0.1")
        self.host = host
        self.port = int(merged.get("TWQ_HTTP_PORT", str(DEFAULT_PORT)))
        self.rate_limit_per_min = int(
            merged.get("TWQ_HTTP_RATE_LIMIT_PER_MIN", str(DEFAULT_RATE_LIMIT_PER_MIN))
        )
        self.max_body_bytes = int(
            merged.get("TWQ_HTTP_MAX_BODY_BYTES", str(DEFAULT_MAX_BODY_BYTES))
        )
        tenant_map = merged.get("TWQ_TENANT_GLOSSARIES", "")
        try:
            self.tenants: dict[str, str] = json.loads(tenant_map) if tenant_map else {"default": ""}
        except ValueError:
            self.tenants = {"default": ""}
        # Anonymous requests only ever allowed on explicit loopback dev.
        if self.api_key is None:
            self.api_key = (
                "loopback-dev-key"
                if (allow_anonymous and host in ("127.0.0.1", "::1", "localhost"))
                else None
            )


def build_http_app(env: dict[str, str] | None = None, mcp_server=None):
    """Build the hardened Streamable HTTP ASGI app (does not run a server)."""

    from thai_writing_mcp.server import build_server

    config = HTTPConfig(env)
    mcp = mcp_server or build_server()
    inner = mcp.streamable_http_app(
        stateless_http=True,
        json_response=True,
        max_request_body_size=config.max_body_bytes,  # NFR-003
        session_idle_timeout=600,
    )
    return HardeningMiddleware(inner, config), config


def main() -> None:
    import uvicorn

    app, config = build_http_app()
    if config.api_key is None:
        raise SystemExit(
            "TWQ_HTTP_API_KEY is required (or TWQ_HTTP_ALLOW_ANONYMOUS=1 on loopback only)"
        )
    uvicorn.run(
        app,
        host=config.host,  # loopback by default
        port=config.port,
        timeout_keep_alive=5,
        timeout_graceful_shutdown=10,
        log_level="info",
    )


if __name__ == "__main__":
    main()
