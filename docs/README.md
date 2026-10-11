# Thai-English Technical Writing MCP — Agent Starter Bundle

This ZIP is an **implementation specification and agent handoff bundle**, not a finished MCP runtime. Start from `agents-hand-off.md`, then `spec.md`, `architecture.md` and `tickets/plan.md`. The agent is instructed to implement, test, measure and document a usable runtime.

## Contains
- `spec.md` — FR/NFR, API scope and acceptance criteria
- `architecture.md` — components, boundaries, data flow, security
- `agents-hand-off.md` — continuous autonomous implementation instructions
- `tickets/plan.md` — T-001 through T-016 and milestones
- `docs/` — tool contracts, evaluation, threat model, decisions, evidence logs
- `skills/thai-writing-quality/SKILL.md` — agent behavior and tool-use instructions
- `config/glossary.example.json` — layered terminology policy example
- `tests/fixtures/golden.jsonl` — seed tests, not a complete gold standard

## Recommended implementation
Python 3.11+; official MCP Python SDK (`https://py.sdk.modelcontextprotocol.io/`), PyThaiNLP (`https://pythainlp.org/dev-docs/api/tokenize.html`); default stdio, no network or cloud model. Implementer must validate and pin tested SDK versions. Optional LLM contextual correction comes later.

## Quick agent entry prompt
"Read `agents-hand-off.md` and execute tickets in `tickets/plan.md` in dependency order. Implement an actual installable Thai-English Technical Writing MCP server and skill. Run all available tests, perform real MCP smoke testing, record evidence and continue autonomously through P0. Do not claim untested functionality or compromise protected-term safety."

## Important
The initial 10 fixtures are **illustrative seeds**, not proof of quality. Every claimed metric must follow `docs/quality-evaluation.md` and be measured on an expanded human-labeled dataset.
