"""T-006: Thai spelling analyzer.

Seam: engines.thai.ThaiAnalyzer.analyze.
Suggestions only — never auto-applied. Tokenization (newmm) and spelling
are distinct operations. Profile measurably changes behavior (FR-008).
"""

from thai_writing_mcp.config.glossary import GlossaryView, default_config
from thai_writing_mcp.core.offsets import build_analysis_view
from thai_writing_mcp.core.protection import ProtectionEngine
from thai_writing_mcp.engines.thai import ThaiAnalyzer


def issues_for(text: str, profile: str = "technical", request_terms: list[str] | None = None):
    gv = GlossaryView(default_config(), request_terms=request_terms)
    eng = ProtectionEngine(protect_terms=gv.protect_terms())
    spans = eng.find_spans(text)
    view = build_analysis_view(text, spans)
    return ThaiAnalyzer(gv).analyze(view.text, spans, profile)


class TestSpecExamples:
    def test_th_spell_001_anuyat(self) -> None:
        f_issues = issues_for("ขออนุญาติแจ้งผลการดำเนินงาน", profile="formal")
        assert [i.original for i in f_issues] == ["อนุญาติ"]
        i = f_issues[0]
        assert i.category == "spelling"
        assert i.suggestions[0].text == "อนุญาต"
        assert i.suggestions[0].confidence is None  # never a calibrated probability
        assert i.suggestions[0].source
        # Offsets exact, contract invariants hold
        assert i.end - i.start == len("อนุญาติ")

    def test_mix_001_preserves_english_terms(self) -> None:
        issues = issues_for("ขออนุญาติ deploy API ไป production", profile="technical")
        spell_issues = [i for i in issues if i.category == "spelling"]
        assert [i.original for i in spell_issues] == ["อนุญาติ"]
        # deploy / API / production are protected -> never inside an issue
        for i in spell_issues:
            assert "deploy" not in i.original and i.original != "API"


class TestSuggestionsNeverAutoApplied:
    def test_canonical_issue_is_reviewable_output_only(self) -> None:
        issues = issues_for("อีเมล์ของฉันคืออะไร", profile="technical")
        assert any(i.suggestions[0].text == "อีเมล" for i in issues)
        # The analyzer only returns issues; applying is the patch layer's job (T-008).


class TestDictionaryBasedDetection:
    def test_missing_saral_flagged_with_candidates(self) -> None:
        issues = issues_for("คุยกับอาจารยก่อนนะ", profile="formal")
        unknown = [i for i in issues if i.rule_id == "spelling.unknown_token"]
        assert len(unknown) == 1
        assert unknown[0].original == "อาจารย"
        assert any(s.text == "อาจารย์" for s in unknown[0].suggestions)
        assert unknown[0].requires_review is True
        assert all(s.confidence is None for s in unknown[0].suggestions)  # not calibrated

    def test_known_words_not_flagged(self) -> None:
        assert issues_for("ประชุมวันจันทร์เช้านี้", profile="formal") == []


class TestProfiles:
    def test_general_profile_skips_token_review(self) -> None:
        # Canonical rules still fire...
        assert [i.original for i in issues_for("ขออนุญาติครับ", profile="general")] == ["อนุญาติ"]
        # ...but unknown-token review is off in general.
        assert issues_for("คุยกับอาจารยก่อนนะ", profile="general") == []

    def test_technical_and_formal_differ_from_general(self) -> None:
        text = "คุยกับอาจารยก่อนนะ"
        assert len(issues_for(text, "technical")) > len(issues_for(text, "general"))
        assert len(issues_for(text, "formal")) > len(issues_for(text, "general"))


class TestProtectionInteraction:
    def test_no_flags_inside_protected_spans(self) -> None:
        # อนุญาติ sits inside inline code -> masked -> not flagged
        text = "ระบบส่งคำว่า `ขออนุญาติ` กลับมา"
        assert issues_for(text, profile="formal") == []

    def test_glossary_terms_are_not_unknown_tokens(self) -> None:
        text = "ระบบ cxgateway ทำงานปกติ"
        issues = issues_for(text, profile="technical", request_terms=["cxgateway"])
        assert issues == []


class TestTokenizerContract:
    def test_tokenization_and_spelling_are_distinct(self) -> None:
        from pythainlp.tokenize import word_tokenize

        toks = word_tokenize("ขออนุญาติ deploy", engine="newmm")
        assert "deploy" in toks  # tokenization runs regardless of spelling state
        analyzer = ThaiAnalyzer(GlossaryView(default_config()))
        assert analyzer.dictionary_name == "pythainlp newmm + words_th"
