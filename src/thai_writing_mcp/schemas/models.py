"""Typed models for tool contracts v1 (docs/tool-contracts.md).

Offsets are Python Unicode code points, zero-based, half-open [start, end),
into the original string. Original text is immutable.
"""

from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field

Profile = Literal["general", "formal", "technical"]

#: NFR-003: default input cap in Unicode code points.
MAX_INPUT_CODEPOINTS = 50_000

#: Upper bound for max_changes (FR-012: no unbounded correction loops).
MAX_CHANGES_CAP = 1000


class StrictModel(BaseModel):
    """Reject unknown fields: malformed or hostile payloads fail closed."""

    model_config = ConfigDict(extra="forbid", str_strip_whitespace=False)


class AnalyzeRequest(StrictModel):
    text: str
    profile: Profile = "technical"
    glossary: list[str] | None = None


class CorrectRequest(StrictModel):
    text: str
    profile: Profile = "technical"
    mode: Literal["suggest", "safe_apply"] = "suggest"
    max_changes: int = Field(default=10, ge=1, le=MAX_CHANGES_CAP)
    glossary: list[str] | None = None


class ValidateRequest(StrictModel):
    text: str
    profile: Profile = "technical"
    glossary: list[str] | None = None


class RewriteRequest(StrictModel):
    text: str
    profile: Profile = "technical"
    preserve_meaning: bool = True
    glossary: list[str] | None = None


class Suggestion(BaseModel):
    text: str
    confidence: float | None = None  # not calibrated; null allowed (spec §6)
    source: str


class Issue(BaseModel):
    id: str
    rule_id: str
    category: str
    severity: Literal["info", "low", "medium", "high"]
    start: int
    end: int
    original: str
    suggestions: list[Suggestion] = Field(default_factory=list)
    message: str
    protected: bool
    requires_review: bool


class ProtectedSpan(BaseModel):
    start: int
    end: int
    kind: str


class Patch(BaseModel):
    start: int
    end: int
    original: str
    replacement: str
    applied: bool = False
    reason: str


class ValidationReport(BaseModel):
    ok: bool
    violations: list[str] = Field(default_factory=list)
    protected_spans_checked: int = 0


class Versions(BaseModel):
    schema_version: str
    engine_version: str
    dictionary_version: str


def versions_block(dictionary_version: str) -> dict[str, Any]:
    """FR-015: every tool output carries all three versions."""
    from thai_writing_mcp import SCHEMA_VERSION, __version__

    return {
        "schema_version": SCHEMA_VERSION,
        "engine_version": __version__,
        "dictionary_version": dictionary_version,
    }
