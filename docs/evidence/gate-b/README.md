# Gate B — Real-host smoke evidence (T-010)

Date: 2026-10-11 · Hosts tried: Claude Code CLI v2.1.251, MCP Inspector CLI

## What was captured

| File | Content |
|---|---|
| `host-transcript.jsonl` | Claude Code headless session: **server connected, tools discovered** (`mcp__thai-writing-quality__thai_analyze/_correct/_validate` in the init event). Model turns could not run: the CLI is not authenticated (`Not logged in · Please run /login`; `claude auth status` → `loggedIn: false`). Credential blocker recorded per the hand-off stop conditions. |
| `inspector-tools-list.json` | MCP Inspector (official host, CLI mode) `tools/list` — all three tools with input schemas. |
| `inspector-thai_analyze.json` | Real `tools/call` — `ขออนุญาติ deploy API ไป production` → issues `["อนุญาติ"]`, glossary terms protected. |
| `inspector-thai_correct.json` | Real `tools/call` suggest mode → `corrected: "ขออนุญาต deploy API ไป production"`, `requires_review: true`. |
| `inspector-thai_validate.json` | Real `tools/call` on clean text → `status: "PASS"`. |

## Reproduce

```bash
scripts/capture_gate_b_host_smoke.sh     # Claude Code attempt + summary
npx @modelcontextprotocol/inspector --cli scripts/run_server_stdio.sh --method tools/list
npx @modelcontextprotocol/inspector --cli scripts/run_server_stdio.sh \
  --method tools/call --tool-name thai_analyze \
  --tool-arg "text=ขออนุญาติ deploy API ไป production"
```

Honest scope note: the Inspector proves the **server side** of the host
integration end-to-end (connect, schema negotiation, tool invocation,
structured output). The **agent-side skill workflow** (validate → correct →
max 2 passes) is fully specified in `skills/thai-writing-quality/SKILL.md`
and integration-tested at the protocol level, but a logged-in Claude Code
transcript executing the skill end-to-end is still outstanding until the
CLI is authenticated — run `scripts/capture_gate_b_host_smoke.sh` again
after `claude /login` to replace this caveat with a full transcript.
