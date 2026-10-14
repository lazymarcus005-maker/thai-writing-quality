"""Minimal patch generator (T-008).

Patches are sorted, non-overlapping, bounded, and precondition-checked:
``original[start:end] == patch.original`` is enforced before anything is
applied. Unchanged sections stay byte-identical because application is a
pure splice over the original string (FR-007, NFR-008).
"""

from __future__ import annotations

from thai_writing_mcp.schemas.errors import RULE_FAILURE, EngineError
from thai_writing_mcp.schemas.models import Issue, Patch, ProtectedSpan

#: Total edit budget: edited characters / total characters (FR-007 bound).
DEFAULT_MAX_EDIT_RATIO = 0.3

#: Above this product, a patch counts as full-length (bounds the DP).
_LEV_CAP = 40_000


def _bounded_levenshtein(a: str, b: str) -> int:
    """Edit distance with a size cap so pathological patches stay linear."""
    if len(a) * len(b) > _LEV_CAP:
        return max(len(a), len(b))
    if a == b:
        return 0
    prev = list(range(len(b) + 1))
    for i, ca in enumerate(a, 1):
        cur = [i]
        for j, cb in enumerate(b, 1):
            cur.append(min(prev[j] + 1, cur[j - 1] + 1, prev[j - 1] + (ca != cb)))
        prev = cur
    return prev[-1]


def patch_diff(patch: Patch) -> str:
    """Rendered before/after line for one patch (LLM- and human-readable)."""

    return f"- {patch.original}\n+ {patch.replacement}"


def apply_patches(
    text: str, patches: list[Patch], *, max_edit_ratio: float = DEFAULT_MAX_EDIT_RATIO
) -> str:
    """Splice `patches` into `text` after checking every precondition."""
    _check_patch_invariants(text, patches, max_edit_ratio)
    out: list[str] = []
    cursor = 0
    for p in sorted(patches, key=lambda x: (x.start, x.end)):
        out.append(text[cursor : p.start])
        out.append(p.replacement)
        cursor = p.end
    out.append(text[cursor:])
    return "".join(out)


def _check_patch_invariants(text: str, patches: list[Patch], max_edit_ratio: float) -> None:
    ordered = sorted(patches, key=lambda x: (x.start, x.end))
    prev: Patch | None = None
    changed = 0
    for p in ordered:
        if p.start < 0 or p.end > len(text) or p.start >= p.end:
            raise EngineError(
                RULE_FAILURE,
                "patch out of bounds",
                details={"start": p.start, "end": p.end, "length": len(text)},
            )
        if text[p.start : p.end] != p.original:
            raise EngineError(
                RULE_FAILURE,
                f"patch precondition failed at {p.start}:{p.end}",
                details={"expected": p.original, "actual": text[p.start : p.end]},
            )
        if prev is not None and p.start < prev.end:
            raise EngineError(RULE_FAILURE, "overlapping patches", details={"at": p.start})
        changed += _bounded_levenshtein(p.original, p.replacement)
        prev = p
    if text and changed / len(text) > max_edit_ratio:
        raise EngineError(
            RULE_FAILURE,
            "max edit ratio exceeded",
            details={"changed": changed, "total": len(text), "ratio": max_edit_ratio},
        )


class PatchPlanner:
    """Turns issues into minimal, non-overlapping patches."""

    def __init__(self, max_edit_ratio: float = DEFAULT_MAX_EDIT_RATIO) -> None:
        self.max_edit_ratio = max_edit_ratio

    def plan(
        self,
        text: str,
        issues: list[Issue],
        max_changes: int,
        protected_spans: list[ProtectedSpan] | None = None,
    ) -> list[Patch]:
        protected = protected_spans or []
        candidates: list[Patch] = []
        for issue in issues:
            if not issue.suggestions:
                continue  # review-only issue: no patch
            fix = issue.suggestions[0].text
            patch = Patch(
                start=issue.start,
                end=issue.end,
                original=issue.original,
                replacement=fix,
                applied=False,
                reason=issue.rule_id,
            )
            if any(sp.start <= patch.start < sp.end for sp in protected):
                continue  # defensive: never plan inside a protected span
            candidates.append(patch)
        candidates.sort(key=lambda p: (p.start, p.end))

        picked: list[Patch] = []
        for patch in candidates:
            if len(picked) >= max_changes:
                break
            if picked and patch.start < picked[-1].end:
                continue  # overlap: earlier patch wins
            if patch.original != text[patch.start : patch.end]:
                continue  # stale issue: skip rather than fail the batch
            picked.append(patch)
        return picked

    def apply_safe(self, text: str, patches: list[Patch], issues: list[Issue]) -> str:
        """safe_apply gate: only patches whose issue is review-free apply.

        Matching is positional (a patch inherits the review flag of the issue
        at its exact span) — rule ids alone are not precise enough.
        """
        review_positions = {(i.start, i.end) for i in issues if i.requires_review}
        applicable = [p for p in patches if (p.start, p.end) not in review_positions]
        return apply_patches(text, applicable, max_edit_ratio=self.max_edit_ratio)
