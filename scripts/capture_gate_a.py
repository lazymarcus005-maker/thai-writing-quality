"""Capture Gate A evidence: real MCP stdio client request/response transcripts.

Writes docs/evidence/gate-a/*.json — one file per tool call, with the exact
arguments and the structured result the client received.
"""

from __future__ import annotations

import asyncio
import json
import sys
from datetime import UTC, datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parents[1] / "src"))

from mcp import ClientSession, StdioServerParameters  # noqa: E402
from mcp.client.stdio import stdio_client  # noqa: E402

OUT = Path(__file__).parents[1] / "docs" / "evidence" / "gate-a"

_MIXED = "ขออนุญาติ deploy API ไป production"
CALLS = [
    ("analyze_mixed", "thai_analyze", {"text": _MIXED, "profile": "technical"}),
    ("correct_suggest", "thai_correct", {"text": _MIXED}),
    ("correct_safe_apply", "thai_correct", {"text": _MIXED, "mode": "safe_apply"}),
    ("validate_warn", "thai_validate", {"text": _MIXED}),
    ("validate_fail_bidi", "thai_validate", {"text": "สวัสดี \u202e ครับ"}),
    ("validate_pass", "thai_validate", {"text": "ประมวลผลคำขอเรียบร้อยแล้ว", "profile": "general"}),
    ("error_oversized", "thai_analyze", {"text": "ก" * 50_001}),
    ("error_invalid_empty", "thai_analyze", {"text": ""}),
]


async def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    params = StdioServerParameters(
        command=sys.executable,
        args=["-m", "thai_writing_mcp.server"],
        env={"TWQ_LOG_LEVEL": "ERROR"},
    )
    async with stdio_client(params) as (read, write):
        async with ClientSession(read, write) as session:
            info = await session.initialize()
            tools = await session.list_tools()
            evidence = {
                "captured_at": datetime.now(UTC).isoformat(),
                "server_info": {"name": info.server_info.name, "version": info.server_info.version},
                "advertised_tools": sorted(t.name for t in tools.tools),
                "client": "mcp python sdk (mcp==2.3.0) over stdio",
                "calls": [],
            }
            for name, tool, arguments in CALLS:
                result = await session.call_tool(tool, arguments)
                evidence["calls"].append(
                    {
                        "label": name,
                        "tool": tool,
                        "request": arguments
                        if len(json.dumps(arguments)) < 400
                        else {"text": f"<{len(arguments['text'])} code points>"},
                        "is_error": result.is_error,
                        "structured_content": result.structured_content,
                    }
                )
            (OUT / "gate-a-transcript.json").write_text(
                json.dumps(evidence, ensure_ascii=False, indent=2)
            )
            print(f"wrote {OUT / 'gate-a-transcript.json'}")
            print("tools:", evidence["advertised_tools"])
            for c in evidence["calls"]:
                marker = "ERR" if c["is_error"] else "OK "
                print(f"  [{marker}] {c['tool']}: {c['label']}")


if __name__ == "__main__":
    asyncio.run(main())
