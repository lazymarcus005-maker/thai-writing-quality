"""English/technical-word analyzer (T-007).

Scope and limits:
- **Known typos**: a curated, unambiguous typo dictionary proposes
  corrections — suggestions only, outside protected spans.
- **Unknown tokens** are never definite misspellings (FR-005). In the
  ``formal`` profile they surface as review flags with no candidates
  (abstention); ``technical`` and ``general`` assume jargon and stay quiet.
- **No blanket language classification**: analysis is token-level over the
  masked view; nothing here decides "this segment is English" for the rest
  of the pipeline.
"""

from __future__ import annotations

import json
import re
from importlib import resources

from thai_writing_mcp.config.glossary import GlossaryView
from thai_writing_mcp.core.issues import make_issue
from thai_writing_mcp.core.offsets import MASK_CONT, MASK_HEAD
from thai_writing_mcp.schemas.models import Issue

_TYPOS_RESOURCE = resources.files("thai_writing_mcp.config").joinpath("data/english_typos.json")
_COMMON_RESOURCE = resources.files("thai_writing_mcp.config").joinpath("data/english_common.csv")

_RE_WORD = re.compile(r"[A-Za-z][A-Za-z'’-]*")
#: Profiles that surface unknown English tokens for review (FR-005).
_REVIEW_PROFILES = frozenset({"formal"})
_MIN_TOKEN_LEN = 3


def _load_typos() -> dict[str, str]:
    payload = json.loads(_TYPOS_RESOURCE.read_text())
    return {k.lower(): v for k, v in payload.items()}


def _load_common() -> frozenset[str]:
    words = _COMMON_RESOURCE.read_text().replace("\n", ",").split(",")
    return frozenset(w.strip().lower() for w in words if w.strip())


class EnglishAnalyzer:
    """Proposes fixes for known English typos; abstains on unknown tokens."""

    dictionary_name = "english_typo_dictionary"

    def __init__(self, glossary: GlossaryView) -> None:
        self._typos = _load_typos()
        self._common = _load_common() | {t.lower() for t in glossary.protect_terms()}

    def analyze(self, view_text: str, spans, profile: str) -> list[Issue]:
        issues: list[Issue] = []
        issues.extend(self._typo_issues(view_text, spans))
        if profile in _REVIEW_PROFILES:
            issues.extend(self._unknown_token_issues(view_text, spans))
        return sorted(issues, key=lambda i: (i.start, i.end))

    def _typo_issues(self, view_text: str, spans) -> list[Issue]:
        issues: list[Issue] = []
        for m in _RE_WORD.finditer(view_text):
            token = m.group()
            lowered = token.lower()
            if lowered not in self._typos:
                continue
            if MASK_HEAD in token or MASK_CONT in token:
                continue
            if any(sp.start <= m.start() < sp.end for sp in spans):
                continue  # protected span: never touch
            fix = self._typos[lowered]
            if token[0].isupper():
                fix = fix.capitalize()
            issues.append(
                make_issue(
                    rule_id="english.typo",
                    category="spelling",
                    severity="medium",
                    start=m.start(),
                    original=token,
                    suggestions=[fix],
                    message=f"known English typo; did you mean {fix!r}?",
                    requires_review=False,
                    confidences=[None],
                    sources=[self.dictionary_name],
                )
            )
        return issues

    def _unknown_token_issues(self, view_text: str, spans) -> list[Issue]:
        issues: list[Issue] = []
        for m in _RE_WORD.finditer(view_text):
            token = m.group()
            if (
                len(token) < _MIN_TOKEN_LEN
                or MASK_HEAD in token
                or MASK_CONT in token
                or token.lower() in self._common
                or token.lower() in self._typos  # typo rule already covers it
            ):
                continue
            if any(sp.start <= m.start() < sp.end for sp in spans):
                continue
            issues.append(
                make_issue(
                    rule_id="english.unknown_token",
                    category="terminology",
                    severity="info",
                    start=m.start(),
                    original=token,
                    suggestions=[],
                    message="unknown English token — may be a brand or project identifier; review",
                    requires_review=True,
                )
            )
        return issues
