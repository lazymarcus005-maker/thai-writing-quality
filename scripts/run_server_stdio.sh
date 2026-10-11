#!/usr/bin/env bash
# Launch the thai-writing-quality MCP server over stdio (for MCP Inspector).
REPO="$(cd "$(dirname "$0")/.." && pwd)"
export PYTHONPATH="$REPO/src${PYTHONPATH:+:$PYTHONPATH}"
exec "$REPO/.venv/bin/python" -m thai_writing_mcp.server
