"""MCP stdio server (T-009): thai_analyze / thai_correct / thai_validate.

Transport adapter only — no NLP rules live here. Diagnostics go to stderr
and never include raw input text (FR-013, FR-014). EngineError maps to
stable machine-readable codes; nothing ever becomes a traceback (NFR-006).
FR-012: a server-side invocation cap bounds correction loops.
"""

from __future__ import annotations

import logging
import os
import sys
import time
from collections.abc import Callable
from typing import Any

from mcp.server.mcpserver import MCPServer

from thai_writing_mcp import __version__
from thai_writing_mcp.core.pipeline import WritingEngine
from thai_writing_mcp.schemas.errors import RULE_FAILURE, EngineError, error_dict
from thai_writing_mcp.schemas.models import (
    AnalyzeRequest,
    CorrectRequest,
    Profile,
    ValidateRequest,
)
from thai_writing_mcp.schemas.validate import validate_request

#: FR-012: default cap on tool invocations per server process.
DEFAULT_INVOCATION_CAP = 1_000

log = logging.getLogger("thai_writing_mcp.server")


class InvocationCap:
    """Counts tool calls; over the limit, fail closed with RULE_FAILURE."""

    def __init__(self, limit: int) -> None:
        self.limit = limit
        self.count = 0

    def check(self) -> None:
        self.count += 1
        if self.count > self.limit:
            raise EngineError(
                RULE_FAILURE,
                f"invocation cap reached ({self.limit}); refusing further calls",
                retryable=False,
                details={"limit": self.limit, "invocations": self.count},
            )


def _guarded(cap: InvocationCap, fn: Callable[[], dict[str, Any]]) -> dict[str, Any]:
    """Cap + timing + safe error mapping. Logs never contain input text."""
    started = time.perf_counter()
    try:
        cap.check()
        result = fn()
    except EngineError as exc:
        log.error("tool_error code=%s retryable=%s", exc.code, exc.retryable)
        return {"error": error_dict(exc), "summary": f"error: {exc.code}"}
    except Exception:
        # NFR-006: engine failures surface as stable codes, never tracebacks.
        log.exception("tool_unexpected_error")
        err = EngineError(RULE_FAILURE, "internal engine failure", retryable=False)
        return {"error": error_dict(err), "summary": "error: RULE_FAILURE"}
    elapsed_ms = int((time.perf_counter() - started) * 1000)
    log.info("tool_ok latency_ms=%d", elapsed_ms)
    return result


def build_server(
    engine: WritingEngine | None = None,
    *,
    invocation_cap: int | None = None,
) -> MCPServer:
    engine = engine or WritingEngine()
    cap_limit = invocation_cap or int(
        os.environ.get("TWQ_MAX_INVOCATIONS", str(DEFAULT_INVOCATION_CAP))
    )
    cap = InvocationCap(cap_limit)

    server = MCPServer(
        "thai-writing-quality",
        instructions=(
            "Deterministic Thai-English writing quality checks. Offsets are "
            "Python code points (half-open). thai_correct defaults to suggest; "
            "safe_apply applies only review-free deterministic patches. Never "
            "call in an unbounded loop (FR-012)."
        ),
        version=__version__,
    )

    @server.tool()
    def thai_analyze(
        text: str, profile: Profile = "technical", glossary: list[str] | None = None
    ) -> dict[str, Any]:
        """Diagnose Thai/English mixed text: issues + protected spans. Never edits."""
        def work() -> dict[str, Any]:
            req = validate_request(
                AnalyzeRequest, {"text": text, "profile": profile, "glossary": glossary}
            )
            return engine.analyze(req.text, profile=req.profile, glossary=req.glossary)

        return _guarded(cap, work)

    @server.tool()
    def thai_correct(
        text: str,
        profile: Profile = "technical",
        mode: str = "suggest",
        max_changes: int = 10,
        glossary: list[str] | None = None,
    ) -> dict[str, Any]:
        """Suggest minimal patches (default) or apply review-free ones (safe_apply)."""
        def work() -> dict[str, Any]:
            req = validate_request(
                CorrectRequest,
                {
                    "text": text,
                    "profile": profile,
                    "mode": mode,
                    "max_changes": max_changes,
                    "glossary": glossary,
                },
            )
            return engine.correct(
                req.text,
                profile=req.profile,
                mode=req.mode,
                max_changes=req.max_changes,
                glossary=req.glossary,
            )

        return _guarded(cap, work)

    @server.tool()
    def thai_validate(
        text: str, profile: Profile = "technical", glossary: list[str] | None = None
    ) -> dict[str, Any]:
        """Preflight verdict: PASS / WARN / FAIL. FAIL needs deterministic evidence."""
        def work() -> dict[str, Any]:
            req = validate_request(
                ValidateRequest, {"text": text, "profile": profile, "glossary": glossary}
            )
            return engine.validate(req.text, profile=req.profile, glossary=req.glossary)

        return _guarded(cap, work)

    return server


def main() -> None:
    # stderr is the diagnostics channel; stdout carries only MCP frames.
    logging.basicConfig(
        stream=sys.stderr,
        level=os.environ.get("TWQ_LOG_LEVEL", "INFO"),
        format="%(asctime)s %(name)s %(levelname)s %(message)s",
    )
    build_server().run(transport="stdio")


if __name__ == "__main__":
    main()
