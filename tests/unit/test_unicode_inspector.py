"""T-004: Unicode anomaly inspector.

Anti-blanket rule (spec correction policy step 2): valid Thai combining
marks are never flagged for being combining marks.
"""

from thai_writing_mcp.core.offsets import build_analysis_view
from thai_writing_mcp.core.protection import ProtectionEngine
from thai_writing_mcp.engines.unicode import UnicodeInspector

INSPECTOR = UnicodeInspector()


def issues_for(text: str, protect: list[str] | None = None):
    eng = ProtectionEngine(protect_terms=protect or [])
    spans = eng.find_spans(text)
    view = build_analysis_view(text, spans)
    return INSPECTOR.inspect(view.text, spans)


class TestBidi:
    def test_rlo_override_flagged_high_with_removal(self) -> None:
        text = "สวัสดี \u202efile.txt\u202c ครับ"
        found = [i for i in issues_for(text) if i.rule_id == "unicode.bidi_control"]
        assert len(found) == 2  # RLO and PDF
        assert all(i.severity == "high" for i in found)
        first = found[0]
        assert text[first.start] == "\u202e"
        assert first.suggestions[0].text == ""

    def test_lrm_is_low_and_review(self) -> None:
        found = [i for i in issues_for("a\u200eb") if i.rule_id == "unicode.bidi_mark"]
        assert len(found) == 1
        assert found[0].severity == "low"
        assert found[0].requires_review is True


class TestConfusables:
    def test_cyrillic_in_ascii_word(self) -> None:
        text = "login аdmin"  # Cyrillic а
        found = [i for i in issues_for(text) if i.rule_id == "unicode.confusable"]
        assert len(found) == 1
        # The suggestion folds only the flagged run (the homoglyph itself).
        assert found[0].suggestions[0].text == "a"
        assert text[found[0].start : found[0].end] == "а"

    def test_fullwidth_latin(self) -> None:
        text = "โค้ด ＡＰＩ ครับ"
        found = [i for i in issues_for(text) if i.rule_id == "unicode.confusable"]
        assert len(found) == 1
        assert found[0].suggestions[0].text == "API"

    def test_thai_text_never_confusable(self) -> None:
        assert issues_for("ประมวลผลคำขอเรียบร้อยแล้ว ำๆ") == []


class TestCombiningMarks:
    def test_valid_thai_clusters_not_flagged(self) -> None:
        # ที่ เรื่อง อยู่ ปัน — dense valid combining usage
        assert issues_for("ที่อยู่เรื่องปันใจใส่ใจกัน") == []

    def test_duplicate_tone_mark(self) -> None:
        sara_ii = "\u0e35"
        text = "คำท" + sara_ii + sara_ii + "ผิด"  # two sara ii stacked
        found = [i for i in issues_for(text) if i.rule_id == "unicode.duplicate_mark"]
        assert len(found) == 1
        assert found[0].requires_review is True

    def test_orphan_mark_after_space(self) -> None:
        text = "ทดสอบ ่ ระบบ"
        found = [i for i in issues_for(text) if i.rule_id == "unicode.orphan_mark"]
        assert len(found) == 1
        assert text[found[0].start] == "\u0e48"

    def test_mark_on_latin_letter(self) -> None:
        text = "user ครั้ง o\u0e48 ผิด"
        found = [i for i in issues_for(text) if i.rule_id == "unicode.wrong_script_mark"]
        assert len(found) == 1


class TestInvisible:
    def test_zwsp(self) -> None:
        text = "สวัสดี\u200bครับ"
        found = [i for i in issues_for(text) if i.rule_id == "unicode.invisible_char"]
        assert len(found) == 1
        assert found[0].start == len("สวัสดี")
        assert found[0].suggestions[0].text == ""

    def test_zwj_inside_emoji_sequence_ok(self) -> None:
        # Family emoji: ZWJ between pictographs is legitimate.
        text = "ครอบครัว 👨\u200d👩\u200d👧 ดี"
        found = [i for i in issues_for(text) if i.rule_id == "unicode.invisible_char"]
        assert found == []


class TestProtectionExclusion:
    def test_no_flags_inside_protected_spans(self) -> None:
        text = "ดู `a\u202eb` แล้ว"
        assert issues_for(text) == []  # bidi inside inline code is protected

    def test_offsets_are_original_code_points(self) -> None:
        text = "ที่อยู่\u200bครับ"  # combining marks before the ZWSP
        found = [i for i in issues_for(text) if i.rule_id == "unicode.invisible_char"]
        assert found[0].start == len("ที่อยู่")
