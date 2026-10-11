# Agent Handoff — Autonomous Implementation Contract

## Mission
Implement an installable, tested Thai-English Technical Writing MCP server + `thai-writing-quality` skill. Work autonomously end-to-end, but **never claim unexecuted tests passed**. All essential product decisions are documented; default to simplest secure local-first behavior.

## Read first, in this order
1. `spec.md`: full requirements and acceptance.
2. `architecture.md`: boundaries and invariants.
3. `tickets/plan.md`: milestones and prioritized tasks.
4. `docs/tool-contracts.md`, `docs/quality-evaluation.md`, `docs/security.md`.
5. `skills/thai-writing-quality/SKILL.md`, `config/glossary.example.json`, `tests/fixtures/golden.jsonl`.

## Agent operating rules
- Choose one ticket, implement it, write tests, execute tests, document evidence, commit incrementally if repo supports Git. Continue until complete or a true external blocker exists.
- Delegate in parallel only independent units: MCP protocol/schema, NLP/glossary, protection/offsets, evaluation fixtures; one orchestrator integrates.
- No hardcoded secrets, no insecure TLS workarounds, no unapproved outbound requests. Do not store user text by default.
- P0 no LLM dependency. P1 optional adapter must not silently contact cloud.
- When source examples are ambiguous, create a failing regression fixture and default to suggestion-only / abstain.
- Preserve literal text and protected spans; meaning, identifiers, values > style.
- Do not accept model-generated semantic rewrite automatically.
- Validate actual current MCP SDK imports before implementing, even if prior examples differ by version.
- Require real MCP client/inspector smoke test; unit-only success insufficient.
- Maintain `docs/decisions.md`, `docs/progress.md`, `docs/test-results.md` with commands, outputs, version and open issues.

## Work loop
1. Read ticket acceptance criteria and dependencies.
2. Inspect files and environment; record assumptions.
3. Implement minimal vertical slice.
4. Run format/lint/type/unit/integration as configured; fix regressions.
5. Add negative and protected-text cases.
6. Record evidence and current status.
7. Proceed to next unblocked ticket, prioritizing P0.
8. On completion, produce installation commands, sample tool request/response, MCP smoke evidence, metrics and limitations.

## Agent delegation proposal
- **Subagent A — Core/protection:** Unicode offsets, protected spans, patch invariant logic, tests.
- **Subagent B — NLP/glossary:** Thai tokens, spelling candidate adapter, English and terms, test fixtures.
- **Subagent C — MCP/integration:** typed tool interfaces, stdio client, SKILL, packaging.
- **Subagent D — QA/security:** adversarial tests, metrics, false-correction reporting, CI.
Each subagent owns separate files; orchestrator integrates and resolves conflicts. Parallel work is optional and must never be required for success.

## Exact milestone order
M0 repo scaffold and documented working environment -> M1 protection/offsets -> M2 rule+NLP analyzers -> M3 MCP tools -> M4 skill + host smoke -> M5 datasets + measurement + security -> optional M6 LLM contextual P1.

## Stop conditions
Stop and state blocker only when: unavailable credentials for an optional remote service; missing host-specific config that cannot be inferred; legal/permission constraint; or an unsafe irreconcilable semantic ambiguity. Do not stop for simple decisions, formatting or test failures—fix them.

## Definition of completed handoff
Report checklist for FR-001–FR-015 with linked tests; commands and sample results; pinned dependency versions; security posture; all known residual risks; actual benchmark numbers versus targets. Do not alter product scope without an ADR.

## First command plan
- Inspect `README.md` and files.
- Create Python package and pinned `pyproject.toml` using compatible SDK and PyThaiNLP versions.
- Run a minimal P0 `thai_analyze` MCP smoke test, then implement pipeline iteratively.
- Verify entire golden fixture suite and build artifact before marking complete.

## Final response format
`IMPLEMENTED | TESTED | NOT IMPLEMENTED | BLOCKED | RISKS | HOW TO RUN | NEXT STEPS` with actual evidence for each claim.
