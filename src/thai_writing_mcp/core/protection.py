"""Protected-span lexer (T-003): everything that must never be edited.

Detects fenced/inline code, URLs, JSON literals, API routes, file paths,
dates, numbers (+units), code identifiers, emoji, and caller-supplied
protect terms — all as exact code-point spans into the original string.

Overlap resolution (documented priority, highest first):
    code_fence > code_inline > url > json > api_route > path
    > date > number > identifier > emoji > glossary_term
A candidate overlapping an already-accepted (higher-priority) span is
dropped entirely, so accepted spans are always sorted and non-overlapping.

All patterns are ASCII-bounded and quantifier-simple: Thai characters never
match inside these patterns, and pathological input cannot trigger
catastrophic backtracking (NFR-003). No text normalization happens here —
the input is scanned verbatim (NFR-008).
"""

from __future__ import annotations

import json
import re
import unicodedata

from thai_writing_mcp.schemas.models import ProtectedSpan

#: Resolution priority: lower index wins an overlap.
KIND_PRIORITY: list[str] = [
    "code_fence",
    "code_inline",
    "url",
    "json",
    "api_route",
    "path",
    "date",
    "number",
    "identifier",
    "emoji",
    "glossary_term",
]
_PRIORITY = {kind: i for i, kind in enumerate(KIND_PRIORITY)}

#: Safety bounds for pathological inputs (NFR-003).
_MAX_JSON_CANDIDATES = 500
_MAX_JSON_SPAN = 20_000
_MAX_CANDIDATES = 5_000

# ASCII guards: (?<![A-Za-z0-9_]) / (?![A-Za-z0-9_]) keep patterns from
# matching inside larger ASCII tokens. Thai text never matches these classes.
_LB = r"(?<![A-Za-z0-9_])"
_RB = r"(?![A-Za-z0-9_])"

_RE_FENCE = re.compile(r"```[\s\S]*?```|~~~[\s\S]*?~~~")
_RE_INLINE = re.compile(r"`[^`\n]+`")
_RE_URL = re.compile(r"(?:https?://|www\.)[^\s<>\"'`]+", re.IGNORECASE)
_RE_TRAIL_PUNCT = ".,;:!?)>]}',\"”»"

_RE_ROUTE = re.compile(_LB + r"/[A-Za-z0-9._~-]+(?:/[A-Za-z0-9._~-]+)+/?" + r"(?![A-Za-z0-9_.~-])")
_RE_VERSIONY = re.compile(r"(?:^|/)(?:v\d+(?:[._]\d+)?|api|gateway|endpoint)(?:/|$)", re.IGNORECASE)
_RE_EXT = re.compile(r"\.[A-Za-z0-9]{1,8}$")
_RE_PATH = re.compile(
    _LB
    + r"(?:\./|\.\./|~/)?[A-Za-z0-9._-]+(?:/[A-Za-z0-9._-]+)+"
    + r"(?![A-Za-z0-9_.-])"
)
_RE_WINPATH = re.compile(_LB + r"[A-Za-z]:\\[^\s]+")
_RE_DATE_ISO = re.compile(
    _LB + r"\d{4}-\d{2}-\d{2}(?:[T ]\d{2}:\d{2}(?::\d{2})?(?:Z|[+-]\d{2}:?\d{2})?)?"
)
_RE_DATE_SLASH = re.compile(_LB + r"\d{1,2}/\d{1,2}/\d{2,4}" + r"(?![0-9/])")

_UNITS = (
    r"(?:kib|mib|gib|tib|kb|mb|gb|tb|bps|ms|us|ns|sec|sp|min|h|km|cm|mm|kg|mg|lb|oz|px|pt|"
    r"g|s|฿|บาท|วินาที|นาที|ชั่วโมง|วัน|ปี|ลิตร|กม\.|กก\.|%)"
)
_RE_NUMBER = re.compile(
    _LB + r"\d[\d,]*(?:\.\d+)?" + r"(?:" + _UNITS + r")?" + r"(?![0-9A-Za-z_.])"
)

_RE_IDENT = re.compile(
    _LB
    + r"(?:"
    r"[A-Za-z_][A-Za-z0-9_]*_[A-Za-z0-9_]*"  # snake_case / SCREAMING_SNAKE
    r"|[a-z]+(?:[A-Z][a-z0-9]+)+[A-Za-z0-9]*"  # camelCase
    r"|[A-Z][a-z0-9]+(?:[A-Z][a-z0-9]+)+[A-Za-z0-9]*"  # PascalCase
    r"|[A-Z][A-Z0-9]{1,}"  # ACRONYM
    r"|[A-Za-z][A-Za-z0-9]*\d+[A-Za-z0-9]*"  # p95, v1, x86
    r"|[A-Za-z_][A-Za-z0-9_]*(?:\.[A-Za-z_][A-Za-z0-9_]*)+"  # dotted.name
    r")"
    + _RB
)
_RE_EMOJI = re.compile(
    "["
    "\U0001f000-\U0001faff"  # pictographs, emoji
    "\u2600-\u27bf"  # misc symbols/dingbats
    "\u2190-\u21ff\u2300-\u23ff"  # arrows, misc technical
    "]\ufe0f?\u200d?"
)
_RE_THAI = re.compile(r"[\u0e00-\u0e7f]")


def _trim_url(match: re.Match[str]) -> tuple[int, int]:
    start, end = match.span()
    while end > start and match.group()[end - start - 1] in _RE_TRAIL_PUNCT:
        end -= 1
    return start, end


def _json_spans(text: str) -> list[tuple[int, int]]:
    spans: list[tuple[int, int]] = []
    openings = [i for i, ch in enumerate(text) if ch in "{[" ][:_MAX_JSON_CANDIDATES]
    for start in openings:
        close_char = "}" if text[start] == "{" else "]"
        depth = 0
        in_string = False
        escaped = False
        end = -1
        for i in range(start, min(len(text), start + _MAX_JSON_SPAN)):
            ch = text[i]
            if in_string:
                if escaped:
                    escaped = False
                elif ch == "\\":
                    escaped = True
                elif ch == '"':
                    in_string = False
                continue
            if ch == '"':
                in_string = True
            elif ch in "{[":
                depth += 1
            elif ch in "}]":
                depth -= 1
                if depth == 0:
                    end = i + 1
                    break
                if depth < 0:
                    break
        if end > start and close_char in "}]":
            candidate = text[start:end]
            if candidate[-1] == close_char:
                try:
                    json.loads(candidate)
                except (ValueError, RecursionError):
                    continue
                spans.append((start, end))
    return spans


def _is_route(match_text: str) -> bool:
    if _RE_VERSIONY.search(match_text):
        return True
    segments = [s for s in match_text.split("/") if s]
    return len(segments) >= 3 and not _RE_EXT.search(segments[-1])


def _term_pattern(term: str) -> re.Pattern[str]:
    escaped = re.escape(term)
    if re.fullmatch(r"[A-Za-z0-9_ .-]+", term):
        return re.compile(_LB + escaped + _RB)
    # Non-ASCII (Thai) terms: no word-boundary concept; require that the
    # neighbours are not Thai combining marks gluing the term to another word.
    return re.compile("(?<![\\u0e31\\u0e33-\\u0e3a\\u0e47-\\u0e4e])" + escaped)


class ProtectionEngine:
    """Finds spans that must never be edited, in original code-point offsets."""

    def __init__(self, protect_terms: list[str] | None = None) -> None:
        terms = sorted({t for t in (protect_terms or []) if t}, key=len, reverse=True)
        self._term_patterns = [(term, _term_pattern(term)) for term in terms]

    def find_spans(self, text: str) -> list[ProtectedSpan]:
        candidates: list[ProtectedSpan] = []

        def add(kind: str, start: int, end: int) -> None:
            if end > start:
                candidates.append(ProtectedSpan(start=start, end=end, kind=kind))

        for m in _RE_FENCE.finditer(text):
            add("code_fence", m.start(), m.end())
        for m in _RE_INLINE.finditer(text):
            add("code_inline", m.start(), m.end())
        for m in _RE_URL.finditer(text):
            s, e = _trim_url(m)
            add("url", s, e)
        for s, e in _json_spans(text):
            add("json", s, e)
        for m in _RE_ROUTE.finditer(text):
            kind = "api_route" if _is_route(m.group()) else "path"
            add(kind, m.start(), m.end())
        for m in _RE_WINPATH.finditer(text):
            add("path", m.start(), m.end())
        for m in _RE_PATH.finditer(text):
            if not _is_route(m.group()):
                add("path", m.start(), m.end())
        for m in _RE_DATE_ISO.finditer(text):
            add("date", m.start(), m.end())
        for m in _RE_DATE_SLASH.finditer(text):
            add("date", m.start(), m.end())
        for m in _RE_NUMBER.finditer(text):
            add("number", m.start(), m.end())
        for m in _RE_IDENT.finditer(text):
            add("identifier", m.start(), m.end())
        for m in _RE_EMOJI.finditer(text):
            add("emoji", m.start(), m.end())
        for _term, pattern in self._term_patterns:
            for m in pattern.finditer(text):
                add("glossary_term", m.start(), m.end())

        return self._resolve(candidates)

    def is_protected_index(self, spans: list[ProtectedSpan], index: int) -> bool:
        return any(s.start <= index < s.end for s in spans)

    def _resolve(self, candidates: list[ProtectedSpan]) -> list[ProtectedSpan]:
        if len(candidates) > _MAX_CANDIDATES:
            candidates = candidates[:_MAX_CANDIDATES]
        ranked = sorted(
            candidates,
            key=lambda s: (_PRIORITY[s.kind], s.start, -(s.end - s.start)),
        )
        accepted: list[ProtectedSpan] = []
        ranges: list[tuple[int, int]] = []
        for c in ranked:
            if any(c.start < e and s < c.end for s, e in ranges):
                continue
            accepted.append(c)
            ranges.append((c.start, c.end))
        return sorted(accepted, key=lambda s: (s.start, s.end))


def is_thai_char(ch: str) -> bool:
    if _RE_THAI.match(ch):
        return True
    return "\u0e00" <= ch <= "\u0e7f" and unicodedata.category(ch) in ("Mn", "Mc")
