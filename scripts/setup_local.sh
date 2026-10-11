#!/usr/bin/env bash
# One-shot local setup for thai-writing-quality (idempotent).
#
# Creates/reuses .venv (Python >=3.11), installs the package editable with
# dev tools, runs the test suite, generates host wiring files (.mcp.json,
# opencode.json) with absolute paths, and verifies the server through a
# REAL MCP client round-trip. Exit 0 means everything is ready to use.
set -euo pipefail
REPO="$(cd "$(dirname "$0")/.." && pwd)"
cd "$REPO"

echo "== thai-writing-quality setup =="

# 1. Python >= 3.11 (prefer an existing one, then uv, then python3)
PY=""
for candidate in .venv/bin/python python3.13 python3.12 python3.11 python3; do
  if command -v "$candidate" >/dev/null 2>&1 || [ -x "$candidate" ]; then
    if "$candidate" -c 'import sys; assert sys.version_info >= (3, 11)' 2>/dev/null; then
      PY="$(command -v "$candidate" || echo "$candidate")"
      break
    fi
  fi
done
if [ -z "$PY" ]; then
  if command -v uv >/dev/null 2>&1; then
    echo "no Python >=3.11 found; installing via uv"
    uv python install 3.12
    PY="$(uv python find 3.12)"
  else
    echo "ERROR: Python >=3.11 required (and uv not available to install one)" >&2
    exit 1
  fi
fi
echo "python: $PY ($("$PY" --version))"

# 2. Virtualenv + editable install (reused if it already exists)
if [ ! -x .venv/bin/python ]; then
  if command -v uv >/dev/null 2>&1; then
    uv venv --python "$PY" .venv
  else
    "$PY" -m venv .venv
  fi
fi
echo "installing package (editable) + dev tools..."
if command -v uv >/dev/null 2>&1; then
  uv pip install --quiet -p .venv/bin/python -e ".[dev]"
else
  .venv/bin/python -m ensurepip --upgrade >/dev/null 2>&1 || true
  .venv/bin/python -m pip install --quiet --upgrade pip
  .venv/bin/python -m pip install --quiet -e ".[dev]"
fi

# 3. Test suite must be green — never paper over failures.
echo "running tests..."
.venv/bin/python -m pytest tests -q

# 4. Host wiring files with ABSOLUTE paths (machine-specific -> gitignored).
"$PY" - <<PYEOF
import json, pathlib
mcp = {
    "mcpServers": {
        "thai-writing-quality": {
            "command": "$REPO/.venv/bin/python",
            "args": ["-m", "thai_writing_mcp.server"],
            "env": {"TWQ_LOG_LEVEL": "ERROR"},
        }
    }
}
pathlib.Path(".mcp.json").write_text(json.dumps(mcp, indent=2))
oc = {
    "\$schema": "https://opencode.ai/config.json",
    "mcp": {
        "thai-writing-quality": {
            "type": "local",
            "command": ["$REPO/.venv/bin/python", "-m", "thai_writing_mcp.server"],
            "environment": {"TWQ_LOG_LEVEL": "ERROR"},
            "enabled": True,
        }
    },
}
pathlib.Path("opencode.json").write_text(json.dumps(oc, indent=2))
print("wrote .mcp.json and opencode.json")
PYEOF

# 5. Real-client verification round-trip.
echo "verifying server via real MCP client..."
.venv/bin/python scripts/verify_install.py

cat <<'SUMMARY'

== READY ==
- stdio server : .venv/bin/python -m thai_writing_mcp.server  (or: thai-writing-mcp)
- http server  : thai-writing-http   (needs TWQ_HTTP_API_KEY; binds 127.0.0.1)
- host wiring  : .mcp.json (Claude Code project scope) + opencode.json (opencode)
  -> restart/reload the host session so it picks the server up
- skill        : skills/thai-writing-quality (copy to ~/.claude/skills/ for user scope)
- tools        : thai_analyze / thai_correct / thai_validate / thai_rewrite
SUMMARY
