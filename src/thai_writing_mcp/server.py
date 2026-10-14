"""MCP stdio server (T-009): thai_analyze / thai_correct / thai_validate.

Transport adapter only — no NLP rules live here. Diagnostics go to stderr
and never include raw input text (FR-013, FR-014). EngineError maps to
stable machine-readable codes; nothing ever becomes a traceback (NFR-006).
FR-012: a server-side invocation cap bounds correction loops — a total cap
for stdio (one agent session) and a rolling-window cap for long-lived HTTP
deployments so the server never permanently refuses all traffic.
"""

from __future__ import annotations

import json
import logging
import os
import sys
import time
from collections import deque
from collections.abc import Callable
from typing import Any

from mcp.server.mcpserver import MCPServer
from mcp.types import ToolAnnotations

from thai_writing_mcp import __version__
from thai_writing_mcp.config.glossary import config_from_env, default_config
from thai_writing_mcp.core.pipeline import WritingEngine
from thai_writing_mcp.engines.llm_adapter import LLMAdapter
from thai_writing_mcp.schemas.errors import RULE_FAILURE, EngineError, error_dict
from thai_writing_mcp.schemas.models import (
    AnalyzeRequest,
    CorrectRequest,
    Profile,
    RewriteRequest,
    ValidateRequest,
)
from thai_writing_mcp.schemas.validate import validate_request

#: FR-012: default cap on tool invocations per server process.
DEFAULT_INVOCATION_CAP = 1_000

#: Long-lived HTTP servers use a rolling window instead of a lifetime total.
DEFAULT_HTTP_INVOCATIONS_PER_MIN = 10_000

log = logging.getLogger("thai_writing_mcp.server")

_RO = ToolAnnotations(read_only_hint=True, destructive_hint=False, open_world_hint=False)


class _JsonFormatter(logging.Formatter):
    """One JSON object per log line (TWQ_LOG_JSON=1) for log aggregators."""

    def format(self, record: logging.LogRecord) -> str:
        return json.dumps(
            {
                "ts": self.formatTime(record),
                "name": record.name,
                "level": record.levelname,
                "msg": record.getMessage(),
                "request_id": getattr(record, "request_id", None),
            },
            ensure_ascii=False,
        )


class InvocationCap:
    """Counts tool calls; over the limit, fail closed with RULE_FAILURE.

    Without ``window_s`` the cap is a lifetime total (stdio: one agent
    session per process). With ``window_s`` only invocations inside the
    trailing window count (HTTP: a process serving many requests must not
    brick itself after N total calls — the window recovers).
    """

    def __init__(self, limit: int, *, window_s: float | None = None) -> None:
        self.limit = limit
        self.window_s = window_s
        self.count = 0
        self._recent: deque[float] = deque()

    def check(self) -> None:
        self.count += 1
        if self.window_s is not None:
            now = time.monotonic()
            self._recent.append(now)
            while self._recent and self._recent[0] <= now - self.window_s:
                self._recent.popleft()
            if len(self._recent) > self.limit:
                raise EngineError(
                    RULE_FAILURE,
                    f"invocation cap reached ({self.limit} per {self.window_s:g}s); retry shortly",
                    retryable=True,
                    details={"limit": self.limit, "window_s": self.window_s},
                )
            return
        if self.count > self.limit:
            raise EngineError(
                RULE_FAILURE,
                f"invocation cap reached ({self.limit}); refusing further calls",
                retryable=False,
                details={"limit": self.limit, "invocations": self.count},
            )


def _guarded(
    cap: InvocationCap, fn: Callable[[], dict[str, Any]], tool_name: str
) -> dict[str, Any]:
    """Cap + timing + safe error mapping. Logs never contain input text."""
    started = time.perf_counter()
    try:
        cap.check()
        result = fn()
    except EngineError as exc:
        log.error(
            "tool_error tool=%s code=%s retryable=%s", tool_name, exc.code, exc.retryable
        )
        return {"error": error_dict(exc), "summary": f"error: {exc.code}"}
    except Exception:
        # NFR-006: engine failures surface as stable codes, never tracebacks.
        log.exception("tool_unexpected_error tool=%s", tool_name)
        err = EngineError(RULE_FAILURE, "internal engine failure", retryable=False)
        return {"error": error_dict(err), "summary": "error: RULE_FAILURE"}
    elapsed_ms = int((time.perf_counter() - started) * 1000)
    log.info("tool_ok tool=%s latency_ms=%d", tool_name, elapsed_ms)
    return result


def build_server(
    engine: WritingEngine | None = None,
    *,
    invocation_cap: int | None = None,
    invocation_window_s: float | None = None,
    engine_resolver: Callable[[], WritingEngine] | None = None,
) -> MCPServer:
    """Build the MCP server.

    ``engine_resolver`` lets a transport pick the engine per request (the
    HTTP middleware uses it for per-tenant glossaries); by default a single
    engine is shared. ``TWQ_GLOSSARY_FILE`` seeds that default engine with a
    persistent project glossary.
    """

    if engine is None and engine_resolver is None:
        engine = WritingEngine(config_from_env() or default_config())

    def _default_resolver() -> WritingEngine:
        assert engine is not None  # set right above when no resolver is given
        return engine

    resolver: Callable[[], WritingEngine] = engine_resolver or _default_resolver
    cap_limit = invocation_cap or int(
        os.environ.get("TWQ_MAX_INVOCATIONS", str(DEFAULT_INVOCATION_CAP))
    )
    cap = InvocationCap(cap_limit, window_s=invocation_window_s)

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

    @server.tool(
        annotations=_RO,
        description=(
            "Diagnose Thai/English mixed text BEFORE publishing or sending it: "
            "returns issues (spelling, Unicode anomalies, style) with a `preview` "
            "context window and protected spans (code, URLs, numbers). Never edits. "
            "Use when the text contains Thai and you want a defect list."
        ),
    )
    def thai_analyze(
        text: str, profile: Profile = "technical", glossary: list[str] | None = None
    ) -> dict[str, Any]:
        """Diagnose Thai/English mixed text: issues + protected spans. Never edits."""

        def work() -> dict[str, Any]:
            req = validate_request(
                AnalyzeRequest, {"text": text, "profile": profile, "glossary": glossary}
            )
            return resolver().analyze(req.text, profile=req.profile, glossary=req.glossary)

        return _guarded(cap, work, "thai_analyze")

    @server.tool(
        annotations=_RO,
        description=(
            "Get minimal-diff fixes for Thai/English text issues. Default mode "
            "`suggest` returns patches with rendered `diff` lines for human/model "
            "review — nothing is applied. `safe_apply` additionally applies only "
            "review-free deterministic patches. Protected content is never edited."
        ),
    )
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
            return resolver().correct(
                req.text,
                profile=req.profile,
                mode=req.mode,
                max_changes=req.max_changes,
                glossary=req.glossary,
            )

        return _guarded(cap, work, "thai_correct")

    @server.tool(
        annotations=_RO,
        description=(
            "Style/prose rewriting PROPOSALS (review required, never auto-applied). "
            "Only call when the user explicitly asks for rewriting/improvement of "
            "tone or flow — for fixing errors prefer thai_correct."
        ),
    )
    def thai_rewrite(
        text: str,
        profile: Profile = "technical",
        preserve_meaning: bool = True,
        glossary: list[str] | None = None,
    ) -> dict[str, Any]:
        """Reviewed rewriting proposals (P1). requires_review is always
        true; never auto-published."""

        def work() -> dict[str, Any]:
            req = validate_request(
                RewriteRequest,
                {
                    "text": text,
                    "profile": profile,
                    "preserve_meaning": preserve_meaning,
                    "glossary": glossary,
                },
            )
            adapter = LLMAdapter()  # disabled unless explicitly opted in via env
            return resolver().rewrite(
                req.text,
                profile=req.profile,
                preserve_meaning=req.preserve_meaning,
                glossary=req.glossary,
                llm_adapter=adapter,
            )

        return _guarded(cap, work, "thai_rewrite")

    @server.tool(
        annotations=_RO,
        description=(
            "One-shot preflight verdict for Thai/English text: PASS (no issues), "
            "WARN (review-worthy findings), FAIL (deterministic high-severity "
            "evidence such as bidi controls or confusables). Cheapest gate before "
            "publishing; also exposed as the `thai-writing-check` CLI for "
            "host-side hooks."
        ),
    )
    def thai_validate(
        text: str, profile: Profile = "technical", glossary: list[str] | None = None
    ) -> dict[str, Any]:
        """Preflight verdict: PASS / WARN / FAIL. FAIL needs deterministic evidence."""

        def work() -> dict[str, Any]:
            req = validate_request(
                ValidateRequest, {"text": text, "profile": profile, "glossary": glossary}
            )
            return resolver().validate(req.text, profile=req.profile, glossary=req.glossary)

        return _guarded(cap, work, "thai_validate")

    return server


def _configure_logging() -> None:
    handler = logging.StreamHandler(sys.stderr)
    if os.environ.get("TWQ_LOG_JSON", "") == "1":
        handler.setFormatter(_JsonFormatter())
    else:
        handler.setFormatter(
            logging.Formatter("%(asctime)s %(name)s %(levelname)s %(message)s")
        )
    logging.root.handlers[:] = [handler]
    logging.root.setLevel(os.environ.get("TWQ_LOG_LEVEL", "INFO"))


def main() -> None:
    # stderr is the diagnostics channel; stdout carries only MCP frames.
    _configure_logging()
    try:
        server = build_server()
    except EngineError as exc:
        # Startup config errors (e.g. a broken TWQ_GLOSSARY_FILE) exit loudly
        # instead of serving with silently missing terms.
        print(f"startup failed: {exc}", file=sys.stderr)
        raise SystemExit(2) from None
    server.run(transport="stdio")


if __name__ == "__main__":
    main()
