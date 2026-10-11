"""T-007: English and technical-word analyzer.

Seam: engines.english.EnglishAnalyzer.analyze.
Known English typos propose corrections outside protected spans; unknown
tokens (brands, project ids) are never definite misspellings (FR-005).
No blanket ASCII-based language classification: analysis is token-level
inside mixed prose, never a whole-text language decision.
"""

from thai_writing_mcp.config.glossary import GlossaryView, default_config
from thai_writing_mcp.core.offsets import build_analysis_view
from thai_writing_mcp.core.protection import ProtectionEngine
from thai_writing_mcp.engines.english import EnglishAnalyzer


def issues_for(text: str, profile: str = "technical", request_terms: list[str] | None = None):
    gv = GlossaryView(default_config(), request_terms=request_terms)
    eng = ProtectionEngine(protect_terms=gv.protect_terms())
    spans = eng.find_spans(text)
    view = build_analysis_view(text, spans)
    return EnglishAnalyzer(gv).analyze(view.text, spans, profile)


class TestKnownTypos:
    def test_mix_002_respones(self) -> None:
        issues = issues_for("ตรวจสอบ respones จาก API", profile="technical")
        assert [i.original for i in issues] == ["respones"]
        i = issues[0]
        assert i.suggestions[0].text == "response"
        assert i.suggestions[0].source == "english_typo_dictionary"
        assert i.requires_review is False  # curated, unambiguous pair
        assert text_offset_ok(i)

    def test_respones_inside_code_not_flagged(self) -> None:
        text = "จะเจอคำว่า `respones` ใน log"
        assert issues_for(text, profile="technical") == []

    def test_recieve(self) -> None:
        issues = issues_for("ผมได้ recieve email แล้ว", profile="general")
        assert [i.suggestions[0].text for i in issues] == ["receive"]

    def test_teh(self) -> None:
        issues = issues_for("fix teh bug ครับ", profile="technical")
        assert [i.suggestions[0].text for i in issues] == ["the"]


class TestUnknownTokens:
    def test_unknown_token_not_definite_in_technical(self) -> None:
        issues = issues_for("ใช้ Zyxpan ทำงานร่วมกับระบบ", profile="technical")
        definite = [i for i in issues if not i.requires_review]
        assert definite == []  # FR-005: never a definite misspelling

    def test_unknown_token_defaults_to_review_in_formal(self) -> None:
        issues = issues_for("ใช้ Zyxpan ทำงานร่วมกับระบบ", profile="formal")
        review = [i for i in issues if i.requires_review]
        assert len(review) == 1
        assert review[0].original == "Zyxpan"
        assert review[0].suggestions == []  # abstain: no candidates

    def test_common_words_not_flagged_in_formal(self) -> None:
        assert issues_for("check the server response ให้หน่อย", profile="formal") == []


class TestProfiles:
    def test_profile_changes_behavior(self) -> None:
        text = "ใช้ Zyxpan ทำงานร่วมกับระบบ"
        technical = issues_for(text, "technical")
        formal = issues_for(text, "formal")
        general = issues_for(text, "general")
        assert len(formal) > len(technical) == len(general) == 0


class TestCleanAndMixed:
    def test_clean_001_no_issues(self) -> None:
        assert issues_for("ฐานข้อมูล Redis ทำงานช้า", profile="technical") == []

    def test_clean_002_no_issues(self) -> None:
        assert issues_for("ประมวลผลคำขอเรียบร้อยแล้ว", profile="general") == []

    def test_spec_example_no_forced_translation(self) -> None:
        # ฐานข้อมูล Redis ทำงานช้า -> no forced translation of Redis
        issues = issues_for("ฐานข้อมูล Redis ทำงานช้า", profile="formal")
        assert all(i.original != "Redis" for i in issues)

    def test_no_blanket_classification(self) -> None:
        # Routes/identifiers are the protection engine's job; the English
        # analyzer must not re-classify whole segments by ASCII share.
        text = "endpoint /cxgateway/v1/member-xapi มี status 500"
        gv = GlossaryView(default_config(), request_terms=["cxgateway"])
        eng = ProtectionEngine(protect_terms=gv.protect_terms())
        spans = eng.find_spans(text)
        view = build_analysis_view(text, spans)
        issues = EnglishAnalyzer(gv).analyze(view.text, spans, "technical")
        assert issues == []


def text_offset_ok(issue) -> bool:
    return issue.end - issue.start == len(issue.original)
