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

## Repository layout

```
src/thai_writing_mcp/   package (schemas, core pipeline, engines, MCP server)
tests/                  unit + integration tests, golden fixtures
skills/                 thai-writing-quality agent skill
docs/                   spec, architecture, contracts, threat model, evidence logs
```
