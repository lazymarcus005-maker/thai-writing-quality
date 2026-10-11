"""T-015: Streamable HTTP transport, auth, rate limits, tenant scoping.

A real MCP streamable-http client exercises a live uvicorn server. The
SDK's transport already enforces body caps + session idle timeouts; the
hardening middleware adds auth / rate limiting / tenant checks.
"""

import socket

import pytest
from mcp import ClientSession
from mcp.client.streamable_http import streamable_http_client


def free_port() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


@pytest.fixture()
async def http_server():
    import uvicorn

    from thai_writing_mcp.http_server import build_http_app

    port = free_port()
    env = {
        "TWQ_HTTP_API_KEY": "test-key-123",
        "TWQ_HTTP_HOST": "127.0.0.1",
        "TWQ_HTTP_PORT": str(port),
        "TWQ_HTTP_RATE_LIMIT_PER_MIN": "100000",  # default high; rate tests use own app
    }
    app, config = build_http_app(env)
    server = uvicorn.Server(uvicorn.Config(app, host="127.0.0.1", port=port, log_level="error"))
    import threading

    import anyio

    thread = threading.Thread(target=server.run, daemon=True)
    thread.start()
    for _ in range(100):
        await anyio.sleep(0.05)
        if server.started:
            break
    yield {"port": port, "key": "test-key-123", "server": server}
    server.should_exit = True
    thread.join(timeout=5)


async def test_streamable_http_real_client(http_server) -> None:
    import httpx2

    url = f"http://127.0.0.1:{http_server['port']}/mcp"
    http_client = httpx2.AsyncClient(
        headers={"Authorization": f"Bearer {http_server['key']}"}, timeout=10
    )
    async with streamable_http_client(url, http_client=http_client) as (read, write):
        async with ClientSession(read, write) as session:
            await session.initialize()
            tools = await session.list_tools()
            assert {"thai_analyze", "thai_correct", "thai_validate", "thai_rewrite"} <= {
                t.name for t in tools.tools
            }
            result = await session.call_tool(
                "thai_validate", {"text": "ขออนุญาติ deploy API ไป production"}
            )
            assert result.structured_content["status"] == "WARN"


async def test_http_requires_auth(http_server) -> None:
    import httpx2 as httpx

    url = f"http://127.0.0.1:{http_server['port']}/mcp"
    async with httpx.AsyncClient(timeout=5) as client:
        no_auth = await client.post(url, json={"jsonrpc": "2.0", "method": "initialize", "id": 1})
        assert no_auth.status_code == 401
        bad = await client.post(
            url,
            json={"jsonrpc": "2.0", "method": "initialize", "id": 1},
            headers={"Authorization": "Bearer wrong"},
        )
        assert bad.status_code == 401


async def test_http_unknown_tenant_rejected(http_server) -> None:
    import httpx2 as httpx

    url = f"http://127.0.0.1:{http_server['port']}/mcp"
    async with httpx.AsyncClient(timeout=5) as client:
        res = await client.post(
            url,
            json={"jsonrpc": "2.0", "method": "initialize", "id": 1},
            headers={
                "Authorization": f"Bearer {http_server['key']}",
                "X-Tenant": "not-configured",
            },
        )
        assert res.status_code == 403


async def test_http_oversized_body_rejected() -> None:
    import httpx2 as httpx
    import uvicorn

    from thai_writing_mcp.http_server import build_http_app

    port = free_port()
    app, _config = build_http_app({"TWQ_HTTP_API_KEY": "k2", "TWQ_HTTP_MAX_BODY_BYTES": "1000"})
    server = uvicorn.Server(uvicorn.Config(app, host="127.0.0.1", port=port, log_level="error"))
    import threading

    threading.Thread(target=server.run, daemon=True).start()
    import anyio

    for _ in range(100):
        await anyio.sleep(0.05)
        if server.started:
            break
    async with httpx.AsyncClient(timeout=5) as client:
        res = await client.post(
            f"http://127.0.0.1:{port}/mcp",
            content=b"x" * 5000,
            headers={"Authorization": "Bearer k2", "Content-Type": "application/json"},
        )
        assert res.status_code == 413
    server.should_exit = True


def test_rate_limit_enforced() -> None:
    from thai_writing_mcp.http_server import _TokenBucket

    bucket = _TokenBucket(capacity=3, refill_per_min=3)
    outcomes = [bucket.take() for _ in range(5)]
    assert outcomes == [True, True, True, False, False]  # bucket of 3 then refused


def test_middleware_rate_limits_via_asgi() -> None:
    import anyio

    from thai_writing_mcp.http_server import HardeningMiddleware, HTTPConfig

    config = HTTPConfig({"TWQ_HTTP_API_KEY": "rk", "TWQ_HTTP_RATE_LIMIT_PER_MIN": "3"})
    statuses: list[int] = []

    async def app(scope, receive, send):
        statuses.append(200)

    async def send(message):
        if message["type"] == "http.response.start":
            statuses.append(message["status"])

    async def receive():
        return {"type": "http.request", "body": b"", "more_body": False}

    middleware = HardeningMiddleware(app, config)

    async def drive():
        scope = {
            "type": "http",
            "method": "POST",
            "path": "/mcp",
            "headers": [(b"authorization", b"Bearer rk")],
            "query_string": b"",
        }
        for _ in range(5):
            await middleware(dict(scope), receive, send)

    anyio.run(drive)
    assert statuses.count(200) == 3
    assert statuses.count(429) == 2


def test_fail_closed_without_api_key() -> None:
    from thai_writing_mcp.http_server import HTTPConfig

    assert HTTPConfig({}).api_key is None  # refuses ALL requests (503)
    # Anonymous mode is refused on non-loopback hosts...
    assert HTTPConfig({"TWQ_HTTP_ALLOW_ANONYMOUS": "1", "TWQ_HTTP_HOST": "0.0.0.0"}).api_key is None
    # ...and yields a loopback-only dev key otherwise (documented dev escape hatch).
    assert (
        HTTPConfig({"TWQ_HTTP_ALLOW_ANONYMOUS": "1", "TWQ_HTTP_HOST": "127.0.0.1"}).api_key
        == "loopback-dev-key"
    )
