"""Shared Issue factory: stable ids, contract-shaped issues."""

from __future__ import annotations

from thai_writing_mcp.schemas.models import Issue, Suggestion


def make_issue(
    *,
    rule_id: str,
    category: str,
    severity: str,
    start: int,
    original: str,
    suggestions: list[str],
    message: str,
    requires_review: bool,
    protected: bool = False,
    confidences: list[float | None] | None = None,
    sources: list[str] | None = None,
) -> Issue:
    """Build a contract-conformant Issue; id is stable per rule+position."""
    sugg: list[Suggestion] = []
    for j, text in enumerate(suggestions):
        confidence = confidences[j] if confidences and j < len(confidences) else None
        source = sources[j] if sources and j < len(sources) else rule_id
        sugg.append(Suggestion(text=text, confidence=confidence, source=source))
    return Issue(
        id=f"{rule_id}@{start}",
        rule_id=rule_id,
        category=category,
        severity=severity,  # type: ignore[arg-type]
        start=start,
        end=start + len(original),
        original=original,
        suggestions=sugg,
        message=message,
        protected=protected,
        requires_review=requires_review,
    )
