# Implementation Tickets
Ticket IDs are stable. Each ticket requires passing tests and documented execution evidence.

| ID | Phase | Task | Acceptance | Dependencies |
|---|---|---|---|---|
| T-001 | P0 | Python package + CI + dependency pinning | `pip install -e .` and imports work; CI on fresh environment | none |
| T-002 | P0 | Input schemas/limits + errors | Invalid/massive inputs return typed errors | T-001 |
| T-003 | P0 | Protected spans lexer + offsets | Markdown, API paths, URLs, JSON, code, dates, emoji pass integrity fixtures | T-001 |
| T-004 | P0 | Unicode Thai inspector | catches known anomalies without false blanket normalization | T-002,T-003 |
| T-005 | P0 | Dictionary layers + terminology policy | priorities, protected projects, snapshots tested | T-001 |
| T-006 | P0 | Thai spelling analyzer using PyThaiNLP | concrete candidate+issue fixtures pass | T-003,T-005 |
| T-007 | P0 | Mixed-language English analyzer | preserves proper names, optional typo suggestions | T-003,T-005 |
| T-008 | P0 | Minimal patch + invariant verifier | nonoverlap, precondition, protected+number integrity tests | T-003 |
| T-009 | P0 | MCP 3 tool adapters and structured schemas | real stdio client invokes each | T-002,T-004,T-006,T-007,T-008 |
| T-010 | P0 | Skill and host instruction | SKILL.md works with one real host; no unlimited loop | T-009 |
| T-011 | P0 | Golden dataset + scoring tool | reproducible precision/recall, false corrections & latency | T-006,T-007,T-008 |
| T-012 | P0 | Security / negative / end-to-end tests | docs/security.md checklist and no network by default | T-009,T-011 |
| T-013 | P1 | Optional contextual LLM adapter | opt-in only; offline fallback; schema validity | T-009,T-012 |
| T-014 | P1 | `thai_rewrite`, profiles + semantic gate | never silent change to numbers/protected content | T-013 |
| T-015 | P1 | Streamable HTTP / Docker / auth | local bind by default, auth, rate limits | T-009,T-012 |
| T-016 | P1 | A/B experiment and benchmark report | base vs skill vs MCP vs combined on same gold set | T-010,T-011,T-014 |

## Gate criteria
**Gate A:** T-001..T-009 + all P0 correctness tests. **Gate B:** T-010..T-012 and real client demo. **Gate C:** optional P1 validated against A/B results. Never label Gate B 'production ready' without threat review and operational tests.
