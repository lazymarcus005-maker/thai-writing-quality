"""Thai-English spacing/style suggestions (FR-011, T-014).

Conservative, Royal-Institute-aligned style hints only — never presented as
mandatory rules. Each suggestion carries ``requires_review=true``:
- Mai yamok (ๆ) must be preceded by a space, and never doubled ("ๆๆ").
Nothing else is "corrected"; inventing rules is explicitly out of scope.
"""

from __future__ import annotations

import re

from thai_writing_mcp.core.issues import make_issue
from thai_writing_mcp.core.offsets import MASK_CONT, MASK_HEAD
from thai_writing_mcp.schemas.models import Issue

#: Profiles that receive style hints (FR-008: profiles change behavior).
STYLE_PROFILES = frozenset({"formal", "technical"})

_RE_GLUED_YAMOK = re.compile(r"(?<=[\u0e00-\u0e7e])(\u0e46)")  # ๆ glued to a word
_RE_DOUBLE_YAMOK = re.compile(r"\u0e46\s*\u0e46")


class StyleAnalyzer:
    """FR-011: spacing/style suggestions without invented mandatory rules."""

    dictionary_name = "thai_style_royal_institute_spacing"

    def analyze(self, view_text: str, spans, profile: str) -> list[Issue]:
        if profile not in STYLE_PROFILES:
            return []
        issues: list[Issue] = []
        for m in _RE_DOUBLE_YAMOK.finditer(view_text):
            if MASK_HEAD in m.group():
                continue
            if any(sp.start <= m.start() < sp.end for sp in spans):
                continue
            issues.append(
                make_issue(
                    rule_id="style.double_maiyamok",
                    category="style",
                    severity="low",
                    start=m.start(),
                    original=m.group(),
                    suggestions=["\u0e46"],
                    message="duplicated mai yamok; a single ๆ (with a preceding space) is standard",
                    requires_review=True,
                    confidences=[None],
                    sources=[self.dictionary_name],
                )
            )
        for m in _RE_GLUED_YAMOK.finditer(view_text):
            if MASK_HEAD in m.group() or MASK_CONT in m.group():
                continue
            if any(sp.start <= m.start() < sp.end for sp in spans):
                continue
            # Skip positions already covered by the double-yamok rule.
            if any(i.start <= m.start() < i.end for i in issues):
                continue
            issues.append(
                make_issue(
                    rule_id="style.maiyamok_spacing",
                    category="style",
                    severity="info",
                    start=m.start(),
                    original=m.group(),
                    suggestions=[" \u0e46"],
                    message=(
                        "mai yamok is conventionally preceded by a space "
                        "(style suggestion, not a rule)"
                    ),
                    requires_review=True,
                    confidences=[None],
                    sources=[self.dictionary_name],
                )
            )
        return sorted(issues, key=lambda i: (i.start, i.end))
