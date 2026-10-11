# Test Results

Record commands, versions, environment, stdout summary, failures and trace evidence.

## 2026-10-11 — T-001 scaffold (Gate: none)

- Environment: macOS 15.6 (arm64), Python 3.12.13 (uv-managed venv `.venv`), pip 25.x
- Pinned versions: `mcp==2.3.0`, `pythainlp==5.4.0`, dev: pytest 8.4.2, pytest-asyncio 1.3.0, ruff 0.14.5, mypy 1.19.0
- API validation (before implementing, per handoff contract):
  - `mcp.server.fastmcp` **raises** in 2.x ("FastMCP was renamed to MCPServer") — confirmed by import attempt.
  - `from mcp.server.mcpserver import MCPServer` OK; `.tool()`, `.run(transport=...)`, `.streamable_http_app()` present.
  - `pythainlp.tokenize.word_tokenize(engine='newmm')` tokenized Thai/EN mix in 0.13s with **no** `~/.pythainlp-data` created (offline proof, fresh HOME).
- Commands:
  - `uv venv --python 3.12 .venv && uv pip install -p .venv/bin/python -e ".[dev]"` — OK
  - `.venv/bin/python -m pytest tests/unit/test_scaffold.py -q` — 4 passed
  - `.venv/bin/python -m ruff check src tests` — All checks passed
  - `.venv/bin/python -m mypy src/thai_writing_mcp` — no issues in 5 source files

## 2026-10-11 — T-002..T-009 (Gate A)

- `.venv/bin/python -m pytest tests -q` — 127 passed (unit + integration)
- `.venv/bin/python -m ruff check src tests scripts` — clean
- `.venv/bin/python -m mypy src/thai_writing_mcp` — no issues in 19 source files
- Real-client smoke (Gate A evidence): `scripts/capture_gate_a.py`
  - server: `python -m thai_writing_mcp.server` (stdio, mcp==2.3.0)
  - client: `mcp.ClientSession` + `stdio_client` (subprocess) — initialize, list_tools, 8 calls
  - results: analyze/correct(suggest+safe_apply)/validate(PASS+WARN+FAIL) all structured; TOO_LARGE + INVALID_INPUT returned as stable codes (see transcript JSON)
- Notable API findings (mcp 2.3.0): `CallToolResult.is_error` (not isError), `Tool.input_schema`, `InitializeResult.server_info`; argument schema validation happens server-side pre-handler (enum violations are protocol errors, not EngineError)
