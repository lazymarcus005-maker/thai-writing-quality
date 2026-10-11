# Evaluation and Test Protocol
## Corpus requirements
Start with included seed fixtures; expand to >=800 independently annotated examples across Thai spelling, natural correct Thai, technical mixed-language, English errors, protected code/route/JSON, dates, numbers, Unicode combining marks, adversarial and semantic-risk samples. Deduplicate by normalized sentence family, but preserve original for offset tests. Split train/dev/test by source to avoid leakage.

## Label format
JSONL records `id`, `text`, `profile`, `expected_issues`, `protected_literals`, `expected_behavior`, `notes`. Labels are human-reviewed gold, not model-generated truth. Include intentionally *no-change* examples.

## Metrics
Detection precision/recall, suggestion exact-match precision, auto-applied false-correction %, preservation violation count, issue offset exact-match, human semantic preservation adjudication, p50/p95 latency. Track per-category and protected/nonprotected slices. Compare LLM alone, Skill only, MCP only, Skill+MCP with same prompts, dataset and human ratings.

## Experiment rules
Run 3 repeats; record OS, CPU, Python/dependencies, language model/reasoning config, input length and cold/warm starts. No unsupported performance claims. P0 initial gates: protected integrity 100%, suggestion precision >=95%, detection recall >=90%, auto false corrections <=1%, p95 <=200ms for <=1k-char reference input. Report real results even if gates fail.

## Human review
At least 2 independent annotators for ambiguous grammar/semantic changes, reconcile differences. Scores should distinguish readability from actual factual/semantic correctness.
