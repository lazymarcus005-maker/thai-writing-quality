# LLM Adapter — Data Handling & Trust Policy (T-013, FR-010)

## Default state: OFF

With no configuration the adapter is disabled and **makes zero network
calls** (regression-tested with sockets raised). It exists only as an
optional proposal source; every P0 behavior works without it.

## Opt-in (all four required; anything missing = disabled)

| Variable | Meaning |
|---|---|
| `TWQ_LLM_ENABLED=1` | explicit opt-in switch |
| `TWQ_LLM_BASE_URL` | OpenAI-compatible chat-completions base URL |
| `TWQ_LLM_API_KEY` | credential — **environment / secret manager only** |
| `TWQ_LLM_MODEL` | model identifier |

No keys are hardcoded, logged, or echoed. One POST per request, single
attempt, hard timeout (`DEFAULT_TIMEOUT_S = 10`).

## What is sent

Only the request text, wrapped in `<DATA>` markers with the profile, plus
a system prompt. No other user data, no telemetry.

## What is trusted: nothing

- Provider unreachable, HTTP error, timeout, or malformed output →
  `EngineError(LLM_UNAVAILABLE)`; the deterministic result stands.
- Proposals are plain `(start, end, original, replacement, reason)` data.
  They become patches that must pass the **same invariant verifier** as
  deterministic edits: precondition match, protected-span integrity
  (ordered marker scan), numeric/date integrity, overlap and edit-ratio
  bounds. Violating batches are declined whole — never repaired silently.
- Every output containing an accepted LLM patch carries
  `requires_review: true`. There is no auto-publish path.

## Prompt-injection posture

The system prompt marks the DATA block as untrusted content and demands
strict JSON. Structurally, even a fully hijacked model cannot cause harm:
its suggestions are inert data until the invariant gate accepts them, and
the gate only accepts edits consistent with the original text's protected
spans and numbers. Tests: `tests/unit/test_llm_adapter.py::TestProposalGate`.
