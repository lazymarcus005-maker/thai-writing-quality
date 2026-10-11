# Thai-English Technical Writing MCP — Product Specification
Status: Implementation-ready specification (not yet implemented)  
Version: 1.0 | 2026-10-11 | Language: TH/EN

## 1. Purpose
Build a reusable, local-first MCP service to improve Thai spelling, Unicode safety, grammar, readability and mixed Thai-English technical writing without altering intent or protected content. Agents may call MCP tools on demand; an optional host-side hook can enforce checking.

## 2. Scope
**P0 / MVP:** deterministic Unicode inspection, protected span discovery, Thai spelling suggestions, English/technical glossary support, issue locations, minimal-diff suggestions, 3 MCP tools (`thai_analyze`, `thai_correct`, `thai_validate`), structured JSON, configuration, regression tests, local stdio transport, skill. P0 shall run without an LLM.
**P1:** `thai_rewrite`, contextual grammar/meaning suggestions, LLM adapter (off by default), formal/technical/general writing profiles, HTTP deployment, benchmark harness and evaluation.
**P2:** feedback loop, project dictionaries, metrics, optional host-side enforcement hooks and user-defined terminology policies.
**Out of scope (MVP):** perfect automatic grammar correction, modifying code, full document parsing, unreviewed factual rewrites, training a new language model, bypassing client MCP limitations.

## 3. Stakeholders and users
Coding/document agents; technical writers; Thai business documents; internal document generation systems; optional hospital/medical use only with domain-specific review. First integration target: Claude Code/Hermes or any MCP host supporting the advertised transport.

## 4. Functional requirements
| ID | Requirement | Priority | Acceptance |
|---|---|---|---|
| FR-001 | Accept Unicode Thai, English and mixed text without corrupting combining marks | P0 | Unicode regression cases pass |
| FR-002 | Detect and preserve fenced/inline code, URLs, file paths, identifiers, JSON keys, API routes, dates, numbers and units | P0 | Byte-for-byte protected span comparison passes |
| FR-003 | Identify Thai spelling errors and propose candidates, not blindly auto-apply | P0 | Gold corpus precision measured |
| FR-004 | Recognize configurable technical vocabulary, acronyms, products, proper nouns and project identifiers | P0 | Dictionary tests pass |
| FR-005 | Detect English typos in prose but do not flag unknown project tokens as definite misspellings | P0 | Mixed-language fixtures pass |
| FR-006 | Return typed issues with code, category, severity, evidence, positions and suggestions | P0 | JSON schema tests pass |
| FR-007 | Return minimal patch suggestions with original and corrected text and diff | P0 | Unchanged sections remain identical |
| FR-008 | Support general, formal, technical profiles | P0 | Profile behavior tests pass |
| FR-009 | Validate proposed output against protected spans and numbers | P0 | Violations rejected, not silently repaired |
| FR-010 | Offer optional LLM contextual suggestions with explicit configuration; fail closed to deterministic mode | P1 | Offline fallback tests pass |
| FR-011 | Support Thai-English spacing and style suggestions without inventing mandatory rules | P1 | Language review corpus |
| FR-012 | No unbounded correction loop | P0 | Tool invocation cap tests |
| FR-013 | Support stdin/stdout MCP, later Streamable HTTP; diagnostics to stderr | P0/P1 | Client smoke test |
| FR-014 | No raw text persisted or sent to external API by default | P0 | Network/no-log tests |
| FR-015 | Versioned dictionaries and rules, reproducible evaluations | P0 | Version metadata returned |

## 5. Nonfunctional requirements
- NFR-001: local-first, zero outbound requests by default; config opt-in for remote LLM.
- NFR-002: for <=1,000 Unicode code points in P0 deterministic mode, target p95 <=200 ms on declared reference hardware (target, not proven).
- NFR-003: protect against oversized input (default 50k code points), excessive recursion, regex worst-case, payload abuse.
- NFR-004: no code execution from text; avoid interpolating input into shell commands.
- NFR-005: pin dependencies and run security/dependency checks.
- NFR-006: return stable JSON and structured error codes; never silently drop errors.
- NFR-007: Unicode offsets are **Python Unicode code point positions**, half-open [start,end). On JS consumers convert explicitly from UTF-16 offsets, and test emojis/combining marks.
- NFR-008: preserve original input verbatim for unchanged segments; never normalize entire text globally. NFC only for analysis if mappings remain reversible.

## 6. API contracts
- `thai_analyze(text, profile='technical', glossary=None)`: issue list, protected spans, metadata. No edit.
- `thai_correct(text, profile='technical', mode='suggest', glossary=None, max_changes=10)`: suggested corrected text, accepted/declined patches, issue list and reasons. **P0 defaults to suggest only**; only deterministic safe patches may auto-apply in a separate explicit mode.
- `thai_validate(text, profile='technical')`: verdict PASS/WARN/FAIL, issue counts; fail only for reliably determinable errors or protection violations.
- `thai_rewrite(text, profile, preserve_meaning=True)`: P1; contextual suggestions, not guaranteed preservation; must undergo independent semantic and protected-span checks.

### Issue schema
`{id,rule_id,category,severity,start,end,original,suggestions:[{text,confidence,source}],message,protected,requires_review}`.
Confidence is **not** calibrated probability until empirically validated. Null is allowed.
Error schema `{code,message,retryable,details}`. All tool outputs include `schema_version`, `engine_version`, `dictionary_version`.

## 7. Correction policy
1. Mask protected spans before segment-level analysis (retain reversible offsets).
2. Scan Unicode structural anomalies; never assume combining marks are invalid solely for being combining marks.
3. Tokenize Thai using PyThaiNLP + custom dictionary; compute candidate suggestions.
4. Analyze English prose via allowlist/optional dictionary but exempt unknown technical tokens from auto-correction.
5. Generate non-overlapping minimal patches; order by source offset; validate original text match before patching.
6. Verify invariants: protected spans, digits/units, JSON/code, named entities when identified.
7. For risky edits, return suggestion with requires_review=true rather than applying.
8. On ambiguous context, abstain. Minimal editing beats aggressive rewriting.

## 8. Example cases (expected)
- `ขออนุญาติ deploy API ไป production` -> suggest `อนุญาต`; preserve `deploy API production`.
- `ตรวจสอบ respones จาก API` -> propose `response` only if known-English typo outside protected spans.
- `endpoint /cxgateway/v1/member-xapi มี status 500` -> protect route and `500`.
- `` `HttpClient` มี timeout 2s `` -> protect identifier and value.
- `ฐานข้อมูล Redis ทำงานช้า` -> no forced translation.
- `รัน unit test บน Kubernetes` -> terminology preserved.
- Existing correct text -> no change.

## 9. Success metrics and gates
Gold set target >=800 labeled examples: Thai typo, English typo, mixed prose, ambiguous proper names, Unicode anomalies, code/Markdown/JSON, numbers/dates and no-error controls. Report per-class precision/recall, suggestion acceptance, false-correction rate, protected-span integrity, meaning change rate (human adjudication), latency p50/p95 and CPU/memory. Initial targets: spelling suggestion precision >=95%, detection recall >=90%, false correction <=1%, protected integrity 100%; targets must be revisited with real measurements. Quality gate: no regressions on protected spans, all tests pass, and documented benchmark methodology before release. Explicit comparison: base LLM vs skill only vs MCP only vs skill+MCP (with identical tasks).

## 10. Security and privacy
Reject secrets in logs; redact or hash telemetry. Never copy input to an external LLM unless explicitly enabled. Disable prompt-following from input text (data not instructions). Test malicious Markdown/HTML, confusables, bidi marks, prompt injection and secrets. Optional HTTP: authenticate, rate-limit, bind localhost by default, validate input size. Do not hardcode API keys.

## 11. Definition of Done
- All 3 P0 tools callable from real MCP client, with structured outputs matching schemas.
- End-to-end mixed-language examples pass.
- Tests explicitly include clean text and protected tokens.
- Skill installed and one real host integration documented.
- CI runs unit, integration, lint, typing and benchmark smoke checks.
- README, runbook, threat model, known limitations and reproducible benchmark report exist.
