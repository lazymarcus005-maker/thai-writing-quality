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
