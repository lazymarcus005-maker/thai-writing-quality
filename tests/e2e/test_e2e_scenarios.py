"""T-012: end-to-end mixed-language scenarios through a real MCP client.

Each scenario is a realistic document fragment combining several difficulty
axes; assertions cover the full pipeline behavior a host would observe.
"""

import sys

import pytest
from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client

import os

SCENARIO_RELEASE_NOTE = """# บันทึกประจำรุ่น 2.4.0

ขออนุญาติแจ้งการอัปเดตระบบครับ ทีมงานได้แก้ไข bug เรื่อง respones ที่ช้าผิดปกติ
endpoint /cxgateway/v1/payment-xapi ตอนนี้ตอบภายใน 120ms (ลดจาก 850ms)
ดูรายละเอียดได้ที่ https://docs.internal.example/release/2.4.0 ตั้งแต่วันที่ 2026-10-11
"""

SCENARIO_INCIDENT = """รายงานเหตุขัดข้อง: เรียก /cxutility/api/v2/orders แล้วได้ HTTP 500
log แสดงข้อความ `Connection refused (os error 111)` ซ้ำ 42 ครั้ง
ฐานข้อมูล Redis หลักล่มชั่วคราวในช่วง 03:00-03:15 น. ระบบ backup ทำงานปกติ
"""


def server_params() -> StdioServerParameters:
    return StdioServerParameters(
        command=sys.executable,
        args=["-m", "thai_writing_mcp.server"],
        env=os.environ | {"TWQ_LOG_LEVEL": "ERROR"},
    )


async def _call(session: ClientSession, tool: str, args: dict):
    return await session.call_tool(tool, args)


@pytest.mark.asyncio
async def test_e2e_release_note_scenario() -> None:
    async with stdio_client(server_params()) as (r, w):
        async with ClientSession(r, w) as s:
            await s.initialize()
            analysis = (await _call(s, "thai_analyze", {"text": SCENARIO_RELEASE_NOTE})).structured_content
            originals = [i["original"] for i in analysis["issues"]]
            assert "อนุญาติ" in originals
            assert "respones" in originals
            # Everything protected survives analysis untouched.
            for lit in ("/cxgateway/v1/payment-xapi", "120ms", "850ms",
                        "https://docs.internal.example/release/2.4.0", "2026-10-11"):
                assert lit in analysis["original"]

            correction = (await _call(s, "thai_correct", {"text": SCENARIO_RELEASE_NOTE})).structured_content
            assert correction["corrected"].replace("อนุญาติ", "อนุญาต").replace("respones", "response") == correction["corrected"]
            assert correction["validation"]["ok"] is True

            verdict = (await _call(s, "thai_validate", {"text": SCENARIO_RELEASE_NOTE})).structured_content
            assert verdict["status"] == "WARN"  # typos found, nothing deterministic-fail


@pytest.mark.asyncio
async def test_e2e_incident_scenario_no_protected_damage() -> None:
    async with stdio_client(server_params()) as (r, w):
        async with ClientSession(r, w) as s:
            await s.initialize()
            safe = (await _call(s, "thai_correct", {
                "text": SCENARIO_INCIDENT, "mode": "safe_apply"
            })).structured_content
            # Protected literals byte-identical in output.
            for lit in ("/cxutility/api/v2/orders", "HTTP 500", "`Connection refused (os error 111)`",
                        "42", "Redis", "03:00-03:15"):
                assert lit in safe["corrected"], f"protected literal damaged: {lit}"
            assert safe["validation"]["ok"] is True
            # A WARN (not FAIL): no deterministic structural anomaly present.
            verdict = (await _call(s, "thai_validate", {"text": SCENARIO_INCIDENT})).structured_content
            assert verdict["status"] in ("PASS", "WARN")


@pytest.mark.asyncio
async def test_e2e_invocation_burst_respects_cap() -> None:
    env = os.environ | {"TWQ_LOG_LEVEL": "ERROR", "TWQ_MAX_INVOCATIONS": "5"}
    params = StdioServerParameters(
        command=sys.executable, args=["-m", "thai_writing_mcp.server"], env=env
    )
    async with stdio_client(params) as (r, w):
        async with ClientSession(r, w) as s:
            await s.initialize()
            codes = []
            for i in range(8):
                res = await _call(s, "thai_validate", {"text": f"ทดสอบระบบครั้งที่ {i}"})
                err = res.structured_content.get("error")
                codes.append(err["code"] if err else "OK")
            assert codes[:5] == ["OK"] * 5
            assert codes[5:] == ["RULE_FAILURE"] * 3  # FR-012: abuse refused, server stayed up
