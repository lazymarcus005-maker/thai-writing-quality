# Benchmark Report (golden-v1)

- Generated: 2026-10-11 12:20 +07
- Engine: `0.1.0` · schema `1.0` · dictionary `1.0+31b0fcea6edb`
- Python 3.12.13 · macOS-26.6.2-arm64-arm-64bit
- Dataset: 139 records, 5321 code points total
  - provenance: agent-curated families + construction-derived templates + seed fixtures
  - **NOT YET MET: the spec's >=800 *independently human-annotated* examples target.**
    Current labels were authored by the implementing agent, not independent annotators,
    so absolute precision/recall numbers below are optimistic bounds, not certified
    measurements. Splitting is by source family (no family straddles train/test).

## Gates (initial targets, spec §9)

| gate | measured | target | verdict |
|---|---|---|---|
| protected integrity | 1.0000 | 1.0 | PASS ✅ |
| suggestion precision | 1.0000 | 0.95 | PASS ✅ |
| detection recall | 1.0000 | 0.9 | PASS ✅ |
| false-correction rate | 0.0000 | 0.01 | PASS ✅ |
| p95 latency (ms) | 0.1133 | 200 | PASS ✅ |

## Detection detail

- TP 57 · FP 0 · FN 0
- detection precision: **1.0000**
- offset exact-match (vs str.find oracle): **1.0000**
- latency p50 **0.08 ms** / p95 **0.11 ms**
over 139 warm calls

## Per-family slice

| family | n | TP | FP | FN |
|---|---|---|---|---|
| clean-mixed | 6 | 0 | 0 | 0 |
| clean-thai | 10 | 0 | 0 | 0 |
| en-typo | 8 | 8 | 0 | 0 |
| en-typo-template | 3 | 3 | 0 | 0 |
| guard-code | 3 | 0 | 0 | 0 |
| guard-idents | 3 | 0 | 0 | 0 |
| guard-json | 3 | 0 | 0 | 0 |
| guard-paths | 3 | 0 | 0 | 0 |
| guard-routes | 3 | 0 | 0 | 0 |
| guard-urls | 3 | 0 | 0 | 0 |
| mixed | 6 | 1 | 0 | 0 |
| numbers-dates | 4 | 0 | 0 | 0 |
| review-unknown | 3 | 3 | 0 | 0 |
| seed | 10 | 3 | 0 | 0 |
| semantic-risk | 4 | 0 | 0 | 0 |
| template-bidi | 5 | 5 | 0 | 0 |
| template-canonical | 9 | 9 | 0 | 0 |
| template-code | 6 | 0 | 0 | 0 |
| template-dates | 6 | 0 | 0 | 0 |
| template-routes | 8 | 0 | 0 | 0 |
| template-typos | 9 | 9 | 0 | 0 |
| template-units | 8 | 0 | 0 | 0 |
| th-canonical | 6 | 6 | 0 | 0 |
| th-canonical-template | 4 | 4 | 0 | 0 |
| unicode-anomaly | 3 | 3 | 0 | 0 |
| unicode-anomaly-template | 3 | 3 | 0 | 0 |

## Determinism (FR-015)

Two consecutive runs over the pinned engine + dictionary `1.0+31b0fcea6edb`:
all metrics identical ✅

## Known limitations

1. **Annotation**: labels are agent-authored (see provenance note above). Independent
   dual-annotator review with reconciliation is required before publishing these as
   certified quality numbers (quality-evaluation protocol).
2. **Coverage**: 139 records << 800 target; template families dominate several slices.
3. **Latency**: measured in-process, warm, Apple Silicon; NFR-002 declares targets
   relative to reference hardware — numbers here are environment-specific.
