# thai-writing-quality

Local-first MCP server that improves **Thai–English mixed technical writing** — Thai spelling, Unicode safety, protected-span handling, minimal-diff suggestions — **without altering intent, code, numbers, or protected terms**.

Status: under active implementation against [docs/spec.md](docs/spec.md). See [docs/progress.md](docs/progress.md) and [docs/test-results.md](docs/test-results.md) for measured evidence.

## Install

Requires Python >= 3.11.

```bash
pip install -e ".[dev]"
pytest                # run the test suite
```

## Run the MCP server (stdio)

```bash
thai-writing-mcp          # serves thai_analyze / thai_correct / thai_validate over stdio
```

## Install the agent skill

```bash
cp -r skills/thai-writing-quality ~/.claude/skills/   # Claude Code (user scope)
```

See [docs/claude-code-integration.md](docs/claude-code-integration.md) for
the full host integration (`.mcp.json`, headless smoke, degradation rules).

## Tools (v1 contracts)

| Tool | Purpose |
|---|---|
| `thai_analyze` | Issue list + protected spans; never edits |
| `thai_correct` | Suggested minimal patches (default `suggest`; explicit `safe_apply` gated by invariants) |
| `thai_validate` | PASS / WARN / FAIL preflight verdict |
| `thai_rewrite` | (P1) Reviewed rewriting proposals; `requires_review=true` always |

Contracts: [docs/tool-contracts.md](docs/tool-contracts.md). Spec: [docs/spec.md](docs/spec.md). Security posture: [docs/security.md](docs/security.md).

## Design invariants

- Offsets are **Python Unicode code points**, zero-based, half-open `[start, end)`, into the original string.
- Protected content (code, URLs, paths, JSON, identifiers, numbers, dates, glossary-protected terms) is verified intact with markers/diff — violations are **rejected, never silently repaired**.
- Default mode is **suggest-only**; deterministic safe patches apply only in explicit `safe_apply`.
- **Zero outbound network requests** by default; the optional LLM adapter is off unless explicitly enabled.
- Diagnostics go to stderr; tool responses are structured JSON plus a human summary.

## Known limitations (honest status)

- The golden dataset is **agent-curated** (139 records); the spec's >=800
  independently human-annotated examples target is **not yet met**, so the
  measured precision/recall numbers are optimistic bounds — see
  [docs/benchmark-report.md](docs/benchmark-report.md).
- The A/B comparison has now run on all four conditions via opencode
  (deepseek-v4-flash): the MCP engine beat the model on detection
  (1.0 vs 0.67-0.73) at ~5,000x lower latency; notably, skill+MCP did not
  lift the model — hosts don't reliably call attached tools without
  enforcement. LLM numbers are one model on a 10-task subset.
- Gate B and Gate C are explicitly **not "production ready"**: no
  independent threat review and no operational (load/restart/multi-tenant)
  tests have been performed.
- The full agent-side skill workflow is verified on a real host
  (opencode + deepseek-v4-flash): it followed read → analyze → correct
  and reported both planted typos with protected tokens intact.

## Repository layout

```
src/thai_writing_mcp/   package (schemas, core pipeline, engines, MCP server)
tests/                  unit + integration tests, golden fixtures
skills/                 thai-writing-quality agent skill
docs/                   spec, architecture, contracts, threat model, evidence logs
```
