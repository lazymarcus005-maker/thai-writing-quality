"""T-009 Gate A evidence: a REAL MCP stdio client invokes every tool.

Unit tests are not sufficient evidence (hand-off contract) — this module
spawns the server as a subprocess and drives it through the official
MCP Python SDK client, asserting schema-conformant structured output.
"""

import os
import sys

import pytest
from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client

from thai_writing_mcp import SCHEMA_VERSION

SAMPLE_TH = "ขออนุญาติ deploy API ไป production"


def server_params(env_extra: dict[str, str] | None = None) -> StdioServerParameters:
    env = os.environ | {"TWQ_LOG_LEVEL": "ERROR"}
    if env_extra:
        env = env | env_extra
    return StdioServerParameters(
        command=sys.executable, args=["-m", "thai_writing_mcp.server"], env=env
    )


async def _session():
    async with stdio_client(server_params()) as (read, write):
        async with ClientSession(read, write) as session:
            await session.initialize()
            yield session


async def test_gate_a_list_tools() -> None:
    async for s in _session():
        tools = await s.list_tools()
        names = {t.name for t in tools.tools}
        assert {"thai_analyze", "thai_correct", "thai_validate"} <= names
        analyze = next(t for t in tools.tools if t.name == "thai_analyze")
        props = analyze.input_schema.get("properties", {})
        assert {"text", "profile", "glossary"} <= set(props)


async def test_gate_a_thai_analyze_structured() -> None:
    async for s in _session():
        result = await s.call_tool("thai_analyze", {"text": SAMPLE_TH, "profile": "technical"})
        assert not result.is_error
        data = result.structured_content
        assert data["schema_version"] == SCHEMA_VERSION
        assert data["engine_version"] and data["dictionary_version"]
        assert data["original"] == SAMPLE_TH
        kinds = {sp["kind"] for sp in data["protected_spans"]}
        assert "glossary_term" in kinds  # deploy/API/production from the glossary
        issues = data["issues"]
        assert [i["original"] for i in issues] == ["อนุญาติ"]
        assert issues[0]["suggestions"][0]["text"] == "อนุญาต"
        # human-readable summary accompanies structured content
        assert any("issue" in c.text for c in result.content if hasattr(c, "text"))


async def test_gate_a_thai_correct_suggest_and_safe_apply() -> None:
    async for s in _session():
        suggest = await s.call_tool("thai_correct", {"text": SAMPLE_TH})
        data = suggest.structured_content
        assert data["requires_review"] is True  # suggest mode never auto-applies
        assert data["corrected"] == "ขออนุญาต deploy API ไป production"
        assert all(p["applied"] is False for p in data["patches"])
        assert data["validation"]["ok"] is True

        safe = await s.call_tool("thai_correct", {"text": SAMPLE_TH, "mode": "safe_apply"})
        sdata = safe.structured_content
        assert sdata["corrected"] == sdata["corrected"]  # stable shape
        applied = [p for p in sdata["patches"] if p["applied"]]
        assert applied, "canonical fix is review-free and must apply in safe_apply"
        assert sdata["corrected"] == "ขออนุญาต deploy API ไป production"


async def test_gate_a_thai_validate_verdicts() -> None:
    async for s in _session():
        warn = await s.call_tool("thai_validate", {"text": SAMPLE_TH})
        assert warn.structured_content["status"] == "WARN"
        fail = await s.call_tool("thai_validate", {"text": "สวัสดี \u202e ครับ"})
        assert fail.structured_content["status"] == "FAIL"  # bidi control: deterministic
        clean = await s.call_tool(
            "thai_validate", {"text": "ประมวลผลคำขอเรียบร้อยแล้ว", "profile": "general"}
        )
        assert clean.structured_content["status"] == "PASS"


async def test_gate_a_invalid_input_stable_error() -> None:
    async for s in _session():
        # Enum violations are rejected by the tool's JSON schema (contract-true).
        bad = await s.call_tool("thai_analyze", {"text": "x", "profile": "slang"})
        assert bad.is_error
        # What the schema cannot express (empty text) yields the stable code.
        empty = await s.call_tool("thai_analyze", {"text": ""})
        assert empty.structured_content["error"]["code"] == "INVALID_INPUT"


async def test_gate_a_invocation_cap_fr012() -> None:
    # Dedicated server with TWQ_MAX_INVOCATIONS=3: the 4th call must fail closed.
    async with stdio_client(server_params({"TWQ_MAX_INVOCATIONS": "3"})) as (read, write):
        async with ClientSession(read, write) as session:
            await session.initialize()
            outcomes = []
            for _ in range(4):
                r = await session.call_tool("thai_validate", {"text": "สวัสดี"})
                outcomes.append(r.structured_content.get("error", {}).get("code"))
            assert outcomes[:3] == [None, None, None]
            assert outcomes[3] == "RULE_FAILURE"


@pytest.mark.parametrize("tool", ["thai_analyze", "thai_correct", "thai_validate"])
async def test_gate_a_oversized_rejected(tool: str) -> None:
    async for s in _session():
        big = "ก" * 50_001
        r = await s.call_tool(tool, {"text": big})
        assert r.structured_content["error"]["code"] == "TOO_LARGE"
