"""T-004: Unicode anomaly inspector for Thai.

Seam: engines.unicode.UnicodeInspector.inspect(view, spans) -> list[Issue].

Scans the (same-length) analysis view so offsets pass straight through to
original code-point positions, and skips masked (protected) regions
entirely. Valid Thai combining marks are NEVER flagged for being combining
marks (spec correction policy step 2); only genuine structural anomalies
are: bidi controls, confusable look-alikes, orphan/duplicate/wrong-script
combining marks, and invisible characters.
"""

import unicodedata

from thai_writing_mcp.core.issues import make_issue
from thai_writing_mcp.core.offsets import MASK_CONT, MASK_HEAD
from thai_writing_mcp.schemas.models import Issue, ProtectedSpan

# Directional formatting that can silently reorder rendered text (high risk).
_BIDI_CONTROLS = {
    "\u202a": "LRE",
    "\u202b": "RLE",
    "\u202c": "PDF",
    "\u202d": "LRO",
    "\u202e": "RLO",
    "\u2066": "LRI",
    "\u2067": "RLI",
    "\u2068": "FSI",
    "\u2069": "PDI",
    "\u061c": "ALM",
}
# Directional marks: legitimate in some bidi text, unexpected in Thai/EN docs.
_BIDI_MARKS = {"\u200e": "LRM", "\u200f": "RLM"}

# Invisible characters with no Thai/EN technical-writing purpose.
_INVISIBLE = {
    "\u200b": "ZWSP",
    "\u00ad": "SOFT HYPHEN",
    "\ufeff": "BOM/ZWNBSP",
    "\u2060": "WORD JOINER",
    "\u180e": "MONGOLIAN VOWEL SEPARATOR",
}
_ZWJ, _ZWNJ = "\u200d", "\u200c"

# Curated homoglyph map (Cyrillic/Greek look-alikes -> ASCII). Extended by
# NFKC for fullwidth and other compatibility forms.
_HOMOGLYPHS = {
    "а": "a",
    "е": "e",
    "о": "o",
    "р": "p",
    "с": "c",
    "х": "x",
    "у": "y",
    "і": "i",
    "А": "A",
    "В": "B",
    "Е": "E",
    "К": "K",
    "М": "M",
    "Н": "H",
    "О": "O",
    "Р": "P",
    "С": "C",
    "Т": "T",
    "Х": "X",
    "І": "I",
    "ο": "o",
    "ν": "v",
    "α": "a",
    "ε": "e",
    "ι": "i",
    "κ": "k",
    "ρ": "p",
    "τ": "t",
    "υ": "u",
    "σ": "s",
    "χ": "x",
    "Ο": "O",
    "Α": "A",
    "Ε": "E",
    "Τ": "T",
    "Ρ": "P",
    "‑": "-",
    "–": "-",
    "—": "-",
    "−": "-",
}

_RE_THAI_CONSONANT_RANGE = ("\u0e01", "\u0e2e")  # ก..ฮ


def _ascii_skeleton(ch: str) -> str | None:
    if ch in _HOMOGLYPHS:
        return _HOMOGLYPHS[ch]
    try:
        folded = unicodedata.normalize("NFKC", ch)
    except ValueError:  # pragma: no cover - surrogates
        return None
    if folded != ch and len(folded) >= 1 and all(ord(c) < 128 for c in folded):
        return folded
    return None


def _mark_has_no_valid_base(prev: str | None) -> bool:
    """True when a combining mark cannot legitimately attach to `prev`.

    Valid Thai bases: consonants (ก-ฮ) and any Thai vowel/mark already
    stacked on the base (e.g. ี + ่). Note Thai marks all have canonical
    combining class 0, so the Unicode ccc cannot decide this — script
    membership does.
    """
    if prev is None or prev in " \t\n\r":
        return True
    if _is_thai_consonant(prev) or _is_thai_mark(prev):
        return False
    return True


def _is_masked(view: str, index: int) -> bool:
    ch = view[index]
    return ch == MASK_HEAD or ch == MASK_CONT


def _is_thai_consonant(ch: str) -> bool:
    return _RE_THAI_CONSONANT_RANGE[0] <= ch <= _RE_THAI_CONSONANT_RANGE[1]


def _is_thai_mark(ch: str) -> bool:
    return "\u0e00" <= ch <= "\u0e7f" and unicodedata.category(ch) in ("Mn", "Mc")


def _is_combining(ch: str) -> bool:
    return unicodedata.category(ch) == "Mn"


def _is_emojiish(ch: str) -> bool:
    return (
        "\U0001f000" <= ch <= "\U0001faff" or "\u2600" <= ch <= "\u27bf" or ch in ("\ufe0f", _ZWJ)
    )


class UnicodeInspector:
    """Finds structural Unicode anomalies; never touches valid Thai script."""

    def inspect(self, view: str, spans: list[ProtectedSpan]) -> list[Issue]:
        issues: list[Issue] = []
        issues.extend(self._bidi(view))
        issues.extend(self._confusables(view))
        issues.extend(self._combining(view))
        issues.extend(self._invisible(view))
        return [i for i in issues if not self._in_span(i, spans)]

    def _in_span(self, issue: Issue, spans: list[ProtectedSpan]) -> bool:
        return any(s.start <= issue.start < s.end for s in spans)

    def _bidi(self, view: str) -> list[Issue]:
        issues: list[Issue] = []
        for i, ch in enumerate(view):
            if _is_masked(view, i):
                continue
            name = _BIDI_CONTROLS.get(ch)
            if name:
                issues.append(
                    make_issue(
                        rule_id="unicode.bidi_control",
                        category="unicode",
                        severity="high",
                        start=i,
                        original=ch,
                        suggestions=[""],
                        message=(
                            f"directional formatting character {name} can silently "
                            "reorder displayed text"
                        ),
                        requires_review=False,
                    )
                )
                continue
            name = _BIDI_MARKS.get(ch)
            if name:
                issues.append(
                    make_issue(
                        rule_id="unicode.bidi_mark",
                        category="unicode",
                        severity="low",
                        start=i,
                        original=ch,
                        suggestions=[""],
                        message=f"directional mark {name} is unexpected in Thai/English text",
                        requires_review=True,
                    )
                )
        return issues

    def _confusables(self, view: str) -> list[Issue]:
        issues: list[Issue] = []
        run_start = -1
        run: list[str] = []
        for i, ch in enumerate(view + "\0"):  # sentinel flushes the run
            if i < len(view) and not _is_masked(view, i) and (mapped := _ascii_skeleton(ch)):
                if run_start < 0:
                    run_start = i
                run.append(mapped)
                continue
            if run:
                issues.append(
                    make_issue(
                        rule_id="unicode.confusable",
                        category="unicode",
                        severity="high",
                        start=run_start,
                        original="".join(view[run_start:i]),
                        suggestions=["".join(run)],
                        message="look-alike characters may not be what they appear (spoofing risk)",
                        requires_review=False,
                    )
                )
                run_start, run = -1, []
        return issues

    def _combining(self, view: str) -> list[Issue]:
        issues: list[Issue] = []
        prev: str | None = None
        for i, ch in enumerate(view):
            if _is_masked(view, i):
                prev = None
                continue
            if _is_combining(ch):
                if not ("\u0e00" <= ch <= "\u0e7f"):
                    prev = ch
                    continue  # non-Thai combining marks (e.g. NFD Latin) out of scope
                # Duplicate identical mark directly on the same base.
                if prev == ch:
                    issues.append(
                        make_issue(
                            rule_id="unicode.duplicate_mark",
                            category="unicode",
                            severity="medium",
                            start=i,
                            original=ch,
                            suggestions=[""],
                            message=(
                                f"duplicate combining mark U+{ord(ch):04X} stacked on the same base"
                            ),
                            requires_review=True,
                        )
                    )
                elif _mark_has_no_valid_base(prev):
                    base = view[i - 1] if i > 0 else ""
                    if base and base.isascii() and base.isalnum():
                        issues.append(
                            make_issue(
                                rule_id="unicode.wrong_script_mark",
                                category="unicode",
                                severity="medium",
                                start=i,
                                original=ch,
                                suggestions=[],
                                message=(
                                    f"combining mark U+{ord(ch):04X} attached "
                                    "to a non-Thai base character"
                                ),
                                requires_review=True,
                            )
                        )
                    else:
                        issues.append(
                            make_issue(
                                rule_id="unicode.orphan_mark",
                                category="unicode",
                                severity="medium",
                                start=i,
                                original=ch,
                                suggestions=[],
                                message=(
                                    f"combining mark U+{ord(ch):04X} has no "
                                    "base character to attach to"
                                ),
                                requires_review=True,
                            )
                        )
                prev = ch
                continue
            prev = ch
        return issues

    def _invisible(self, view: str) -> list[Issue]:
        issues: list[Issue] = []
        for i, ch in enumerate(view):
            if _is_masked(view, i):
                continue
            name = _INVISIBLE.get(ch)
            if name:
                issues.append(
                    make_issue(
                        rule_id="unicode.invisible_char",
                        category="unicode",
                        severity="low",
                        start=i,
                        original=ch,
                        suggestions=[""],
                        message=(
                            f"invisible character {name} (U+{ord(ch):04X}) may "
                            "change copy/paste behavior"
                        ),
                        requires_review=True,
                    )
                )
                continue
            if ch in (_ZWJ, _ZWNJ):
                # Legitimate inside emoji sequences; flag only bare usage.
                prev_ch = view[i - 1] if i > 0 else ""
                next_ch = view[i + 1] if i + 1 < len(view) else ""
                if _is_emojiish(prev_ch) or _is_emojiish(next_ch):
                    continue
                issues.append(
                    make_issue(
                        rule_id="unicode.invisible_char",
                        category="unicode",
                        severity="low",
                        start=i,
                        original=ch,
                        suggestions=[""],
                        message=(
                            f"zero-width {'joiner' if ch == _ZWJ else 'non-joiner'} "
                            f"(U+{ord(ch):04X}) outside an emoji sequence"
                        ),
                        requires_review=True,
                    )
                )
        return issues
