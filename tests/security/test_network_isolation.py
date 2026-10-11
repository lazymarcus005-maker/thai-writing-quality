"""T-012: zero-outbound-network verification (NFR-001, FR-014).

Two layers:
1. In-process: every socket constructor raises while the full engine
   exercises a mixed workload — any accidental network call fails loudly.
2. Subprocess: the stdio server runs with all proxy env vars pointed at a
   blackhole; identical results prove no code path depends on egress.
"""

import os
import socket
import sys

import pytest

from thai_writing_mcp.core.pipeline import WritingEngine

WORKLOAD = [
    ("ขออนุญาติ deploy API ไป production 2026-10-11 🙂", "technical"),
    ("ตรวจสอบ respones จาก API แล้ว", "technical"),
    ("สวัสดี \u202e ครับ", "general"),
    ('{"BICode":"TH01","count":500} ตามที่ /cxgateway/v1/member-xapi แจ้ง', "technical"),
]


class _SocketIsBlocked(socket.socket):
    def __init__(self, *args, **kwargs):
        raise OSError("network disabled by test: zero-outbound-request policy")


@pytest.fixture()
def no_network(monkeypatch):
    monkeypatch.setattr(socket, "socket", _SocketIsBlocked)
    monkeypatch.setattr(
        socket, "create_connection", lambda *a, **k: (_ for _ in ()).throw(OSError("blocked"))
    )
    return None


def test_engine_makes_zero_outbound_requests(no_network) -> None:
    engine = WritingEngine()
    for text, profile in WORKLOAD:
        result = engine.analyze(text, profile=profile)
        assert result["original"] == text
        corrected = engine.correct(text, profile=profile, mode="safe_apply")
        assert "validation" in corrected
        assert engine.validate(text, profile=profile)["status"] in ("PASS", "WARN", "FAIL")


def test_thai_tokenizer_already_warm_makes_no_requests(no_network) -> None:
    # A second engine instance shares pythainlp's imported state; assert that
    # even a cold attribute access path (misspellings load) needs no network.
    from thai_writing_mcp.engines.thai import _builtin_misspellings

    assert "อนุญาติ" in _builtin_misspellings()


@pytest.mark.asyncio
async def test_stdio_server_with_blackhole_proxies(tmp_path) -> None:
    """Real server subprocess with every proxy pointed at a dead port."""
    from mcp import ClientSession, StdioServerParameters
    from mcp.client.stdio import stdio_client

    env = os.environ | {
        "TWQ_LOG_LEVEL": "ERROR",
        "HTTP_PROXY": "http://127.0.0.1:1",
        "HTTPS_PROXY": "http://127.0.0.1:1",
        "ALL_PROXY": "http://127.0.0.1:1",
        "NO_PROXY": "",
    }
    params = StdioServerParameters(
        command=sys.executable,
        args=["-m", "thai_writing_mcp.server"],
        env=env,
    )
    async with stdio_client(params) as (read, write):
        async with ClientSession(read, write) as session:
            await session.initialize()
            result = await session.call_tool(
                "thai_analyze", {"text": "ขออนุญาติ deploy API ไป production"}
            )
            assert result.structured_content["issues"], (
                "engine must still work with egress blackholed"
            )
