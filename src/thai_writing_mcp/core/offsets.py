"""Analysis views over protected spans (T-003).

Masking replaces protected spans in the analysis view so analyzers can never
see (and never propose edits inside) protected content. With same-length
masks the view offsets are identical to the original offsets; the mapping
machinery additionally supports length-changing masks and maps view indices
back to original code-point positions.
"""

from __future__ import annotations

from dataclasses import dataclass

from thai_writing_mcp.schemas.models import ProtectedSpan

#: Leading code point of a mask run; second char marks continuation.
MASK_HEAD = "\ue000"
MASK_CONT = "\ue001"


@dataclass(frozen=True)
class Mask:
    """A masked region: view[start:end) stands for original[orig_start:orig_end)."""

    view_start: int
    view_end: int
    orig_start: int
    orig_end: int


class AnalysisView:
    """The text as analyzers see it, with protected spans masked out."""

    def __init__(
        self,
        text: str,
        original: str,
        protected: list[tuple[int, int, int]] | list[tuple[int, int, int, int]],
    ) -> None:
        """`protected` holds (view_start, view_end, orig_start[, orig_end])."""
        self.text = text
        self.original = original
        masks: list[Mask] = []
        for t in protected:
            vs, ve, os_ = t[0], t[1], t[2]
            oe = t[3] if len(t) == 4 else os_ + (ve - vs)
            masks.append(Mask(vs, ve, os_, oe))
        self.masks = sorted(masks, key=lambda m: m.view_start)

    @property
    def protected_spans(self) -> list[ProtectedSpan]:
        return [
            ProtectedSpan(start=m.view_start, end=m.view_end, kind="masked") for m in self.masks
        ]

    def _shift_before(self, index: int) -> int:
        shift = 0
        for m in self.masks:
            if m.view_end <= index:
                shift += (m.orig_end - m.orig_start) - (m.view_end - m.view_start)
        return shift

    def map_to_original(self, index: int) -> int:
        """Map a view index (0..len(view)) to an original code-point index."""
        for m in self.masks:
            if m.view_start <= index < m.view_end:
                return m.orig_start + (index - m.view_start)
        mapped = index + self._shift_before(index)
        return max(0, min(mapped, len(self.original)))

    def reconstruct(self) -> str:
        """Rebuild the original text byte-for-byte from the view + masks."""
        out: list[str] = []
        cursor = 0
        for m in self.masks:
            out.append(self.text[cursor : m.view_start])
            out.append(self.original[m.orig_start : m.orig_end])
            cursor = m.view_end
        out.append(self.text[cursor:])
        return "".join(out)


def build_analysis_view(text: str, spans: list[ProtectedSpan]) -> AnalysisView:
    """Mask every protected span with a same-length PUA run.

    Same-length masking keeps view offsets identical to original offsets, so
    analyzers report issues directly in original coordinates (NFR-007) and
    emoji / Thai combining marks cannot shift anything (they are single code
    points and stay outside masks).
    """
    chars = list(text)
    for span in spans:
        if span.end <= span.start or span.start < 0 or span.end > len(text):
            continue
        for i in range(span.start, span.end):
            chars[i] = MASK_HEAD if i == span.start else MASK_CONT
    protected = [(s.start, s.end, s.start) for s in spans]
    return AnalysisView(text="".join(chars), original=text, protected=protected)
