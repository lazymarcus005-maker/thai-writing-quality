"""T-015: Streamable HTTP transport, auth, rate limits, tenant scoping.

A real MCP streamable-http client exercises a live uvicorn server. The
SDK's transport already enforces body caps + session idle timeouts; the
hardening middleware adds auth / rate limiting / tenant checks.
"""

import json
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


async def test_healthz_unauthenticated_liveness(http_server) -> None:
    import httpx2 as httpx

    async with httpx.AsyncClient(timeout=5) as client:
        res = await client.get(f"http://127.0.0.1:{http_server['port']}/healthz")
        assert res.status_code == 200
        assert res.json()["status"] == "ok"
        assert res.json()["service"] == "thai-writing-quality"


async def test_responses_carry_request_id(http_server) -> None:
    import httpx2 as httpx

    async with httpx.AsyncClient(timeout=5) as client:
        res = await client.post(
            f"http://127.0.0.1:{http_server['port']}/mcp",
            json={"jsonrpc": "2.0", "method": "initialize", "id": 1},
            headers={"Authorization": f"Bearer {http_server['key']}"},
        )
        assert res.headers.get("x-request-id")


async def test_tenant_glossary_isolation(tmp_path) -> None:
    """The documented promise, now wired: each tenant's engine uses that
    tenant's glossary — terminology never crosses tenants."""
    import threading

    import anyio
    import httpx2
    import uvicorn
    from mcp import ClientSession
    from mcp.client.streamable_http import streamable_http_client

    from thai_writing_mcp.http_server import build_http_app

    a = tmp_path / "tenant-a.json"
    b = tmp_path / "tenant-b.json"
    a.write_text(
        json.dumps({"version": "tenant-a", "global": {"protect": ["Zyxwvu"]}})
    )
    b.write_text(
        json.dumps(
            {
                "version": "tenant-b",
                "global": {"canonical": {"อนุญาติ": "อนุมัติ"}},
            }
        )
    )
    port = free_port()
    tenants = json.dumps({"a": str(a), "b": str(b)})
    app, _config = build_http_app(
        {
            "TWQ_HTTP_API_KEY": "tk",
            "TWQ_HTTP_PORT": str(port),
            "TWQ_TENANT_GLOSSARIES": tenants,
        }
    )
    server = uvicorn.Server(uvicorn.Config(app, host="127.0.0.1", port=port, log_level="error"))
    threading.Thread(target=server.run, daemon=True).start()
    for _ in range(100):
        await anyio.sleep(0.05)
        if server.started:
            break

    async def analyze_for(tenant: str) -> dict:
        http_client = httpx2.AsyncClient(
            headers={"Authorization": "Bearer tk", "X-Tenant": tenant}, timeout=10
        )
        async with streamable_http_client(
            f"http://127.0.0.1:{port}/mcp", http_client=http_client
        ) as (read, write):
            async with ClientSession(read, write) as session:
                await session.initialize()
                result = await session.call_tool("thai_analyze", {"text": "ขออนุญาติ Zyxwvu"})
                return result.structured_content

    try:
        out_a = await analyze_for("a")
        out_b = await analyze_for("b")
        # tenant a: Zyxwvu protected, default canonical อนุญาติ -> อนุญาต
        kinds_a = {sp["kind"] for sp in out_a["protected_spans"]}
        assert "glossary_term" in kinds_a
        assert out_a["dictionary_version"].startswith("tenant-a")
        assert any(i["original"] == "อนุญาติ" for i in out_a["issues"])
        # tenant b: canonical map overridden, no Zyxwvu protection
        assert out_b["dictionary_version"].startswith("tenant-b")
        assert not any(sp for sp in out_b["protected_spans"] if sp["kind"] == "glossary_term")
        fix_b = next(i for i in out_b["issues"] if i["original"] == "อนุญาติ")
        assert fix_b["suggestions"][0]["text"] == "อนุมัติ"
    finally:
        server.should_exit = True


def test_broken_tenant_glossary_fails_at_startup(tmp_path) -> None:
    import pytest

    from thai_writing_mcp.http_server import build_http_app
    from thai_writing_mcp.schemas.errors import EngineError

    bad = tmp_path / "bad.json"
    bad.write_text("{not json")
    with pytest.raises(EngineError):
        build_http_app(
            {
                "TWQ_HTTP_API_KEY": "k",
                "TWQ_TENANT_GLOSSARIES": json.dumps({"t": str(bad)}),
            }
        )
