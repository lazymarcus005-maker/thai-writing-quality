"""T-008: minimal patch generator and invariant verifier.

Seams: core.patches (plan_patches / apply_patches) and
core.validate.InvariantVerifier.
"""

import pytest

from thai_writing_mcp.core.issues import make_issue
from thai_writing_mcp.core.patches import PatchPlanner, apply_patches
from thai_writing_mcp.core.protection import ProtectionEngine
from thai_writing_mcp.core.validate import InvariantVerifier
from thai_writing_mcp.schemas.errors import (
    PROTECTED_CONTENT_VIOLATION,
    RULE_FAILURE,
    EngineError,
)
from thai_writing_mcp.schemas.models import Patch, ProtectedSpan


def issue(
    start: int,
    original: str,
    suggestion: str,
    *,
    review: bool = False,
    rule: str = "spelling.canonical",
):
    return make_issue(
        rule_id=rule,
        category="spelling",
        severity="medium",
        start=start,
        original=original,
        suggestions=[suggestion],
        message="test",
        requires_review=review,
    )


class TestPlanPatches:
    def test_sorted_by_offset_nonoverlapping_bounded(self) -> None:
        text = "ขออนุญาติ x และอนุญาติ y"
        issues = [issue(3, "อนุญาติ", "อนุญาต"), issue(36, "อนุญาติ", "อนุญาต")]
        patches = PatchPlanner().plan(text, issues, max_changes=10)
        assert [p.start for p in patches] == sorted(p.start for p in patches)
        assert all(a.end <= b.start for a, b in zip(patches, patches[1:], strict=True))
        assert all(p.original == text[p.start : p.end] for p in patches)

    def test_overlapping_issues_first_wins(self) -> None:
        text = "respones text"
        issues = [issue(0, "respones", "response"), issue(0, "respones r", "response r")]
        patches = PatchPlanner().plan(text, issues, max_changes=10)
        assert len(patches) == 1
        assert patches[0].original == "respones"

    def test_max_changes_bounds(self) -> None:
        text = "aa bb cc"
        issues = [issue(0, "aa", "ab"), issue(3, "bb", "bc"), issue(6, "cc", "cd")]
        patches = PatchPlanner().plan(text, issues, max_changes=2)
        assert len(patches) == 2

    def test_review_patches_planned_but_marked_via_issue(self) -> None:
        # Planner emits patches for review issues too; the safe_apply gate
        # (T-009) decides by cross-referencing issue.requires_review.
        text = "respones"
        issues = [issue(0, "respones", "response", review=True)]
        patches = PatchPlanner().plan(text, issues, max_changes=10)
        assert len(patches) == 1
        assert patches[0].applied is False

    def test_patch_never_inside_protected_span(self) -> None:
        text = "respones"
        eng = ProtectionEngine(protect_terms=["respones"])  # hostile config, but must hold
        spans = eng.find_spans(text)
        planner = PatchPlanner()
        patches = planner.plan(text, [issue(0, "respones", "response")], 10, protected_spans=spans)
        assert patches == []


class TestApplyPatches:
    def test_apply_and_unchanged_bytes_identical(self) -> None:
        text = "ขออนุญาติ deploy 🙂 ไป production ที่ีนี่"
        start = text.index("อนุญาติ")
        patch = Patch(start=start, end=start + len("อนุญาติ"), original="อนุญาติ", replacement="อนุญาต")
        out = apply_patches(text, [patch])
        assert out == "ขออนุญาต deploy 🙂 ไป production ที่ีนี่"
        # Byte-identical outside the patch (incl. combining marks + emoji).
        assert out[:start] == text[:start]
        assert out[start + len("อนุญาต") :] == text[start + len("อนุญาติ") :]

    def test_precondition_original_mismatch(self) -> None:
        with pytest.raises(EngineError) as ei:
            apply_patches("abc", [Patch(start=0, end=3, original="xyz", replacement="q")])
        assert ei.value.code == RULE_FAILURE

    def test_overlap_rejected(self) -> None:
        patches = [
            Patch(start=0, end=4, original="aaaa", replacement="b"),
            Patch(start=2, end=6, original="cc", replacement="d"),
        ]
        with pytest.raises(EngineError) as ei:
            apply_patches("aaaaaa", patches)
        assert ei.value.code == RULE_FAILURE

    def test_edit_ratio_exceeded(self) -> None:
        patches = [Patch(start=0, end=2, original="ab", replacement="X" * 50)]
        with pytest.raises(EngineError) as ei:
            apply_patches("ab", patches)
        assert ei.value.code == RULE_FAILURE

    def test_empty_patches_returns_original(self) -> None:
        assert apply_patches("ที่อยู่🙂", []) == "ที่อยู่🙂"


class TestInvariantVerifier:
    def test_protected_integrity_ok(self) -> None:
        original = "เรียก /cxgateway/v1 แล้วได้ 500 ที่ี"
        fixed = "เรียก /cxgateway/v1 แล้วได้ 500 ที่นี่"
        route = ProtectedSpan(
            start=original.index("/cxgateway/v1"),
            end=original.index("/cxgateway/v1") + len("/cxgateway/v1"),
            kind="api_route",
        )
        num = ProtectedSpan(
            start=original.index("500"), end=original.index("500") + 3, kind="number"
        )
        patch = Patch(
            start=original.index("ที่ี"),
            end=original.index("ที่ี") + len("ที่ี"),
            original="ที่ี",
            replacement="ที่นี่",
        )
        result = InvariantVerifier().verify(original, fixed, [route, num], patches=[patch])
        assert result.ok, result.violations  # route + 500 intact; fix declared as a patch

    def test_protected_span_missing(self) -> None:
        original = "เรียก /cxgateway/v1 แล้ว"
        output = "เรียก /other แล้ว"
        spans = [ProtectedSpan(start=6, end=19, kind="api_route")]
        with pytest.raises(EngineError) as ei:
            InvariantVerifier().verify_or_raise(original, output, spans, patches=[])
        assert ei.value.code == PROTECTED_CONTENT_VIOLATION

    def test_ordered_scan_not_naive_containment(self) -> None:
        # Both protected literals exist in output, but reordered/duplicated:
        # naive substring containment would pass; ordered scan must not.
        original = "A X1 B X2 C"
        spans = [
            ProtectedSpan(start=2, end=4, kind="identifier"),
            ProtectedSpan(start=7, end=9, kind="identifier"),
        ]
        # Both literals present (naive containment passes) but in reversed
        # order: only the ordered marker scan can reject this.
        output = "X2 B C A X1"
        with pytest.raises(EngineError) as ei:
            InvariantVerifier().verify_or_raise(original, output, spans, patches=[])
        assert ei.value.code == PROTECTED_CONTENT_VIOLATION

    def test_numbers_unchanged_unless_authorized(self) -> None:
        original = "timeout 2s และ 500"
        output = "timeout 3s และ 500"
        with pytest.raises(EngineError) as ei:
            InvariantVerifier().verify_or_raise(original, output, [], patches=[])
        assert ei.value.code == PROTECTED_CONTENT_VIOLATION
        # Authorized changes still must be declared as patches.
        patches = [Patch(start=8, end=10, original="2s", replacement="3s")]
        result = InvariantVerifier().verify(
            original, output, [], patches=patches, numbers_authorized=True
        )
        assert result.ok

    def test_output_must_equal_patched_original(self) -> None:
        # Output cannot invent edits that no patch declares.
        original = "abc def"
        patches = [Patch(start=0, end=3, original="abc", replacement="abd")]
        with pytest.raises(EngineError) as ei:
            InvariantVerifier().verify_or_raise(original, "zzz def", [], patches=patches)
        assert ei.value.code == RULE_FAILURE
        assert InvariantVerifier().verify(original, "abd def", [], patches=patches).ok

    def test_safe_apply_only_applies_non_review(self) -> None:
        text = "respones และอนุญาติ"
        issues = [
            issue(text.index("respones"), "respones", "response"),  # curated: review=False
            issue(text.index("อนุญาติ"), "อนุญาติ", "อนุญาต", review=True),
        ]
        planner = PatchPlanner()
        patches = planner.plan(text, issues, max_changes=10)
        out = planner.apply_safe(text, patches, issues)
        assert out == "response และอนุญาติ"  # review patch NOT applied


class TestSafeApplyValidationRegression:
    def test_safe_apply_with_review_and_safe_issues_validates_true(self) -> None:
        """Review-declined patches must not fabricate an output_mismatch
        (code-review finding: verifier saw all patches, not applied ones)."""
        from thai_writing_mcp.core.pipeline import WritingEngine

        engine = WritingEngine()
        text = "ตรวจสอบ respones กับอาจารยครับ"
        out = engine.correct(text, profile="formal", mode="safe_apply")
        assert out["validation"]["ok"] is True, out["validation"]["violations"]
        assert "response" in out["corrected"]  # safe patch applied
        assert "อาจารย" in out["corrected"]  # review patch correctly declined
