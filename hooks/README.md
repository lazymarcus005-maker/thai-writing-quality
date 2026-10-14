# Enforcing the quality gate (host-side hooks)

The skill alone does not guarantee anything: Gate C measured that a host
with both skill and MCP tools attached still answered from its own
judgment (0.73 detection vs the engine's 1.0). A hook that the host cannot
skip is the reliable enforcement path. All of the below wrap the same
deterministic engine as the MCP tools.

## Exit-code contract (`thai-writing-check`)

| exit | meaning | gate behavior |
|---|---|---|
| 0 | PASS (or no Thai content — skipped) | allow |
| 1 | WARN — review-worthy findings | allow (reported) |
| 2 | FAIL — deterministic high-severity evidence | **block** |
| 3 | engine/input error | allow + stderr warning |

FAIL requires deterministic evidence (bidi controls, confusable
look-alikes), so blocking on it is safe; WARN never blocks to avoid a
noisy gate. Files without Thai characters are skipped (fast, quiet).

## Claude Code (PreToolUse)

```bash
pip install -e .          # or: uv pip install -e .
mkdir -p .claude && cp hooks/claude-code-settings.json .claude/settings.json
# then edit the command path to this repo's venv interpreter
```

On Write/Edit/MultiEdit/NotebookEdit the hook validates the incoming
content; on FAIL it blocks the edit with the findings as the reason.

## pre-commit (any git workflow)

Consume the exported hook from this repo (see `.pre-commit-hooks.yaml`),
or call the CLI directly:

```yaml
- repo: https://github.com/lazymarcus005-maker/thai-writing-quality
  rev: <tag>
  hooks:
    - id: thai-writing-check
```

## CI

```yaml
- run: thai-writing-check docs/ *.md   # fail the build on exit 2
```

## opencode and other hosts

opencode does not expose a Claude-Code-compatible hook registry; until it
does, enforce via git (pre-commit above) or CI, and keep the MCP server +
skill attached for interactive use (`.opencode.json` / project
`opencode.json`, see docs/claude-code-integration.md).

## Persistent glossary

Set `TWQ_GLOSSARY_FILE=/repo/.thai-glossary.json` (shape:
`docs/config/glossary.example.json`) so protected project terms apply to
every check — CLI, hooks and server all read it.
