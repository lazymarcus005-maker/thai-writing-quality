#!/usr/bin/env python3
"""Verify a thai-writing-quality installation end-to-end.

Spawns the stdio MCP server, initializes a real client session, lists the
tools, and calls thai_validate on a clean Thai sentence. Exit 0 only if the
full round-trip succeeds with a schema-conformant structured answer.
"""

from __future__ import annotations

import asyncio
import json
import os
import sys

REQUIRED_TOOLS = {"thai_analyze", "thai_correct", "thai_validate", "thai_rewrite"}


async def main() -> int:
    from mcp import ClientSession, StdioServerParameters
    from mcp.client.stdio import stdio_client

    env = os.environ | {"TWQ_LOG_LEVEL": "ERROR"}
    params = StdioServerParameters(
        command=sys.executable, args=["-m", "thai_writing_mcp.server"], env=env
    )
    async with stdio_client(params) as (read, write):
        async with ClientSession(read, write) as session:
            info = await session.initialize()
            tools = {t.name for t in (await session.list_tools()).tools}
            missing = REQUIRED_TOOLS - tools
            if missing:
                print(f"FAIL: missing tools: {sorted(missing)}")
                return 1
            result = await session.call_tool(
                "thai_validate", {"text": "ประมวลผลคำขอเรียบร้อยแล้ว", "profile": "general"}
            )
            data = result.structured_content or {}
            if data.get("status") != "PASS":
                print(f"FAIL: unexpected validation result: {data}")
                return 1
            print(
                json.dumps(
                    {
                        "ok": True,
                        "server": f"{info.server_info.name} {info.server_info.version}",
                        "tools": sorted(tools),
                        "sample_call": {"tool": "thai_validate", "status": data["status"]},
                        "dictionary_version": data.get("dictionary_version"),
                    },
                    ensure_ascii=False,
                )
            )
            return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
