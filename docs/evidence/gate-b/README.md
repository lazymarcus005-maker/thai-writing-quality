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

## Full agent-side workflow — VERIFIED via opencode (2026-10-11)

`opencode-host-smoke.json` records a complete real-host execution of the
skill workflow: opencode CLI 1.18.34 (model `deepseek-v4-flash-vision-exp`)
with the skill installed as project instructions and the MCP server
attached via `opencode.json`. The host followed the workflow exactly —
read → `thai_analyze` → `thai_correct` (2 tool passes, per the skill's
max-passes rule) — and reported both typos (อนุญาติ, respones) with
protected tokens byte-identical in the suggested corrected text.

The Claude Code transcript above remains as an additional real-host
connectivity artifact; the agent-side workflow requirement (Definition of
Done: "one real host integration documented") is satisfied by the opencode
evidence. Re-running `scripts/capture_gate_b_host_smoke.sh` after
`claude /login` would add a second host for redundancy.
