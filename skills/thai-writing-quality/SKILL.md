---
name: thai-writing-quality
description: Review and improve Thai-English mixed technical writing via Thai Language MCP, preserving code, technical terms, numbers and meaning.
---
# Thai Writing Quality

## Trigger
Use for substantial user-facing Thai text, especially Thai mixed with English or project terminology. Do not invoke for pure code snippets or very short acknowledgements unless asked to proofread them.

## Workflow
1. Draft with the user's tone and intent. Identify all code, URLs, identifiers, numeric values, proper nouns, English technical terms, citations and quoted text as protected.
2. Call `thai_validate` or `thai_analyze` with a matching profile (`technical` default for software engineering, `formal` for business documents, `general` otherwise).
3. If errors warrant improvement, call `thai_correct(mode='suggest')`.
4. Accept minimal, reliable changes only; reject any changes to protected tokens, numbers, units, factual claims or uncertain names.
5. If revised, optionally validate once more. Max 2 passes, then return final with outstanding ambiguity disclosed.
6. Invoke `thai_rewrite` only when style rewriting is specifically requested; evaluate every suggestion.

## Rules
- Thai-English mixed prose is valid; do not translate technical terms without permission.
- Never rewrite code blocks, CLI commands, JSON field names, API paths, variable names, class names, error codes, dates or numerical values.
- Unknown English words may be valid brand names or identifiers; avoid aggressive replacements.
- Do not turn suggestions into facts. No invented citations, numeric claims or terms.
- MCP may be unavailable; when it is, perform ordinary careful editing and state limitations if material.
- A skill instruction is not a guaranteed always-on enforcement mechanism. Use a host/output hook for mandatory quality gates when supported.
