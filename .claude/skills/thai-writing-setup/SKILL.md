---
name: thai-writing-setup
description: Set up this repo end-to-end on a fresh clone — Python env, editable install, green test suite, MCP server wiring into the host (Claude Code .mcp.json / opencode.json), and a REAL client round-trip. Use when the repo was just cloned, when the user asks to set up / install / wire the thai-writing-quality MCP server, when MCP tools (thai_analyze, thai_correct, thai_validate, thai_rewrite) are missing or failing, or before claiming the server is "ready to use".
---

# Thai Writing Quality — one-shot setup

Goal: when this skill completes, the host can call `thai_analyze`,
`thai_correct`, `thai_validate`, `thai_rewrite` and the test suite is green.
Everything is idempotent — safe to re-run on an already-set-up machine.

## Step 1 — Run the deterministic setup script

```bash
bash scripts/setup_local.sh
```

It handles, in order: finds a Python >= 3.11 (installs one via `uv` if
none exists), creates/reuses `.venv`, `pip install -e ".[dev]"`, runs the
full test suite, writes `.mcp.json` (Claude Code, project scope) and
`opencode.json` (opencode) with absolute paths, and finishes with a REAL
MCP client round-trip (`scripts/verify_install.py`: initialize → list
tools → call `thai_validate`).

Rules:
- Exit code 0 + `== READY ==` banner = proceed to Step 2.
- If pytest fails or verify_install prints FAIL: **stop and report the
  actual output**. Do not patch tests, do not skip steps, do not claim
  success. The failure is the finding.
- Do not hand-edit the generated wiring files; re-run the script instead.

## Step 2 — Install the skill into the host

The repo ships an agent skill at `skills/thai-writing-quality/SKILL.md`
(workflow rules for USING the tools correctly). Wire it for the host in
use:

- **Claude Code (user scope — survives across projects):**
  ```bash
  mkdir -p ~/.claude/skills && cp -r skills/thai-writing-quality ~/.claude/skills/
  ```
- **Claude Code (project scope):** `mkdir -p .claude/skills && cp -r skills/thai-writing-quality .claude/skills/`
- **opencode:** tools are already exposed via the generated `opencode.json`;
  skill behavior comes from the project `AGENTS.md` if one is added.

## Step 3 — Make the host pick the server up

- Claude Code reads `.mcp.json` at session start: the user must **restart
  or reload the session** (or run `claude --mcp-config .mcp.json`). Verify
  with `/mcp` in the interactive session — all four tools should list.
- opencode reloads project config per run; verify with a one-shot:
  `opencode run "call the thai_validate tool on สวัสดี and print the raw result"`.

## Step 4 — Report

Report exactly: Python + package versions (`pip show thai-writing-mcp`),
test count, the four tool names confirmed by the round-trip, where the
wiring files are, and one usage example per tool (contracts:
`docs/tool-contracts.md`). If anything is degraded, say so plainly —
never mark setup complete on partial evidence.

## Troubleshooting

- **`python3` is 3.9** (common on macOS): the script auto-falls back to
  newer interpreters, then to `uv python install`. Do not install global
  packages with the system Python.
- **First tool call is slow**: dictionaries load once per process (~0.3 s
  import + ~0.2 s first analyze); this is normal, warm calls are ~0.1 ms.
- **Network must stay silent**: the engine makes ZERO outbound requests
  (tested with sockets raised). If you see any outbound attempt, that is a
  bug — report it, do not configure around it.
- **Optional HTTP mode**: `thai-writing-http` requires `TWQ_HTTP_API_KEY`
  (env/secret only) and binds 127.0.0.1 by default; without a key it
  refuses every request by design.
- **Offline machines**: everything works offline except the optional LLM
  adapter (off unless `TWQ_LLM_ENABLED=1` + base URL + key + model).
