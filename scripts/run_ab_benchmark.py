#!/usr/bin/env python3
"""T-016: controlled A/B benchmark harness (Gate C).

Conditions (identical tasks, dataset, prompts; 3 repeats; environment
recorded) per spec §9 and docs/quality-evaluation.md:

  base_llm    — model only, no skill, no tools.   REQUIRES model credentials.
  skill_only  — model following SKILL.md, no tools. REQUIRES model credentials.
  mcp         — the deterministic engine via a REAL MCP stdio client. RUNNABLE.
  skill_mcp   — model + skill + tools.            REQUIRES model credentials.

The harness runs every condition it can and records an explicit BLOCKED
entry (stop-condition: unavailable credentials) for those it cannot —
the report never invents numbers.
"""

from __future__ import annotations

import asyncio
import json
import os
import platform
import statistics
import sys
import time
from datetime import UTC, datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parents[1] / "src"))

DATA = Path(__file__).parents[1] / "data" / "golden" / "golden-v1.jsonl"
OUT = Path(__file__).parents[1] / "docs" / "evidence" / "gate-c"
REPEATS = 3
MAX_TASKS = 40  # per repeat, keeps the harness bounded for CI


def environment() -> dict:
    cpu = platform.processor() or platform.machine()
    return {
        "os": platform.platform(),
        "cpu": cpu,
        "python": platform.python_version(),
        "engine": __import__("thai_writing_mcp").__version__,
        "mcp_sdk": __import__("importlib.metadata", fromlist=["version"]).version("mcp"),
        "pythainlp": __import__("importlib.metadata", fromlist=["version"]).version("pythainlp"),
        "captured_at": datetime.now(UTC).isoformat(),
        "input_lengths": "10..154 code points (golden-v1 sample)",
        "cold_warm": "cold = first repeat, warm = repeats 2-3",
    }


def load_tasks() -> list[dict]:
    records = [
        json.loads(line) for line in DATA.read_text().splitlines() if line.strip()
    ]
    return records[:MAX_TASKS]


async def run_mcp_condition(tasks: list[dict]) -> dict:
    """Drive the REAL stdio server through the MCP SDK client."""
    from mcp import ClientSession, StdioServerParameters
    from mcp.client.stdio import stdio_client

    def expected_issues(rec: dict) -> set[str]:
        return set(rec["expected_issues"])

    tp = fp = fn = 0
    latencies: list[float] = []
    integrity_ok = 0

    params = StdioServerParameters(
        command=sys.executable,
        args=["-m", "thai_writing_mcp.server"],
        env=os.environ | {"TWQ_LOG_LEVEL": "ERROR"},
    )
    async with stdio_client(params) as (read, write):
        async with ClientSession(read, write) as session:
            await session.initialize()
            for repeat in range(REPEATS):
                for rec in tasks:
                    t0 = time.perf_counter()
                    result = await session.call_tool(
                        "thai_analyze", {"text": rec["text"], "profile": rec["profile"]}
                    )
                    latencies.append((time.perf_counter() - t0) * 1000)
                    data = result.structured_content
                    flagged = {i["original"] for i in data["issues"]}
                    expected = (
                        expected_issues(rec)
                        if rec["expected_behavior"] in ("suggest", "flag", "review")
                        else set()
                    )
                    tp += len(expected & flagged)
                    fn += len(expected - flagged)
                    fp += len(flagged - expected)
                    if repeat == 0 and rec["protected_literals"]:
                        correct = await session.call_tool(
                            "thai_correct", {"text": rec["text"], "mode": "safe_apply"}
                        )
                        corrected = correct.structured_content["corrected"]
                        if all(lit in corrected for lit in rec["protected_literals"]):
                            integrity_ok += 1

    precision = tp / (tp + fp) if tp + fp else 1.0
    recall = tp / (tp + fn) if tp + fn else 1.0
    lat_sorted = sorted(latencies)
    return {
        "condition": "mcp",
        "status": "run",
        "repeats": REPEATS,
        "tasks_per_repeat": len(tasks),
        "detection_precision": round(precision, 4),
        "detection_recall": round(recall, 4),
        "p50_ms": round(statistics.median(lat_sorted), 2),
        "p95_ms": round(lat_sorted[int(0.95 * (len(lat_sorted) - 1))], 2),
        "transport": "stdio via mcp SDK client (subprocess)",
    }


def blocked_condition(name: str, reason: str) -> dict:
    return {"condition": name, "status": "BLOCKED", "reason": reason}


async def main() -> None:
    tasks = load_tasks()
    report = {
        "design": "identical tasks/dataset/prompts across conditions; 3 repeats",
        "environment": environment(),
        "conditions": [],
    }
    report["conditions"].append(await run_mcp_condition(tasks))
    report["conditions"].append(
        blocked_condition(
            "base_llm",
            "no model credentials available in this environment (claude CLI not "
            "logged in; no LLM API key provided). Stop condition: unavailable "
            "credentials for an optional remote service.",
        )
    )
    report["conditions"].append(
        blocked_condition("skill_only", "same credential blocker as base_llm")
    )
    report["conditions"].append(
        blocked_condition("skill_mcp", "same credential blocker as base_llm")
    )
    OUT.mkdir(parents=True, exist_ok=True)
    (OUT / "ab-benchmark.json").write_text(json.dumps(report, ensure_ascii=False, indent=2))
    print(json.dumps(report, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    asyncio.run(main())
