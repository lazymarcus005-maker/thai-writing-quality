# Claude Code integration — thai-writing-quality

## 1. Install the MCP server

Add to the project's `.mcp.json` (or `~/.claude.json` for user scope):

```json
{
  "mcpServers": {
    "thai-writing-quality": {
      "command": "/absolute/path/to/.venv/bin/python",
      "args": ["-m", "thai_writing_mcp.server"],
      "env": { "TWQ_LOG_LEVEL": "ERROR", "TWQ_GLOSSARY_FILE": "/repo/.thai-glossary.json" }
    }
  }
}
```

(Editable install also provides a `thai-writing-mcp` console script:
`"command": "thai-writing-mcp", "args": []`.)

`TWQ_GLOSSARY_FILE` is optional; when set, its project terms protect every
call without passing `glossary` each time (shape:
`docs/config/glossary.example.json`). A broken file aborts the server at
startup instead of silently losing terms.

## 2. Install the skill

```bash
cp -r skills/thai-writing-quality ~/.claude/skills/     # user scope
# or project scope:
mkdir -p .claude/skills && cp -r skills/thai-writing-quality .claude/skills/
```

The skill instructs the agent to: validate/analyze first, use
`thai_correct` in **suggest** mode, accept minimal reliable changes only,
and stop after **max 2 tool passes** (FR-012 discipline on the client side;
the server enforces its own invocation cap regardless).

## 3. Enforce the gate (PreToolUse hook) — recommended

Gate C measured that the host does not reliably call attached tools
(skill+MCP scored at the bare-model level). A hook the host cannot skip is
the enforced path:

```bash
mkdir -p .claude
cp hooks/claude-code-settings.json .claude/settings.json
# edit the command path to the venv interpreter that has thai-writing-mcp installed
```

On Write/Edit/MultiEdit/NotebookEdit the hook validates the incoming
content through the same engine and blocks the edit on FAIL (deterministic
Unicode evidence only). WARN never blocks. See [hooks/README.md](../hooks/README.md)
for pre-commit and CI wiring of the same gate.

## 4. Headless smoke test

```bash
claude -p "Review thai-sample.md with the thai-writing-quality skill" \
  --mcp-config .mcp.json --strict-mcp-config \
  --allowedTools "mcp__thai-writing-quality"
```

## 5. Server unavailable = graceful degradation

Per the skill's rules: when the MCP server is unreachable, the agent edits
carefully by ordinary means and states the limitation if material. The
server is never a hard dependency for editing. The CLI gate
(`thai-writing-check`) keeps working regardless — it does not need the
MCP server, only the installed package.
