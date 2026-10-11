"""T-003: protected-span lexer and code-point offsets.

Seam: core.protection.ProtectionEngine.find_spans + core.offsets mask/view.
Offsets are Python code points, zero-based, half-open [start, end).
"""

import json
from pathlib import Path

from thai_writing_mcp.core.offsets import AnalysisView, build_analysis_view
from thai_writing_mcp.core.protection import KIND_PRIORITY, ProtectionEngine

FIXTURES = [
    json.loads(line)
    for line in (Path(__file__).parents[1] / "fixtures" / "golden.jsonl").read_text().splitlines()
    if line.strip()
]
BY_ID = {f["id"]: f for f in FIXTURES}


def engine(terms: list[str] | None = None) -> ProtectionEngine:
    return ProtectionEngine(protect_terms=terms or [])


def engine_terms(**kw) -> ProtectionEngine:
    return ProtectionEngine(**kw)


def spans_of(text: str, kind: str, eng: ProtectionEngine | None = None):
    e = eng or engine()
    return [s for s in e.find_spans(text) if s.kind == kind]


def find_literal(text: str, literal: str, eng: ProtectionEngine | None = None):
    e = eng or engine()
    return [s for s in e.find_spans(text) if text[s.start : s.end] == literal]


class TestCodePointOffsets:
    def test_unicode_001_emoji_and_api(self) -> None:
        f = BY_ID["unicode-001"]
        text = f["text"]  # "ทดสอบภาษาไทย🙂 และ API"
        assert len("🙂") == 1  # emoji is ONE code point
        api = find_literal(text, "API")
        assert len(api) == 1
        assert text[api[0].start : api[0].end] == "API"

    def test_combining_mark_shifts_offsets_by_exactly_one(self) -> None:
        base = "ทดสอบภาษาไทย🙂 และ API"
        marked = "ทดสอบภาษาไทยี🙂 และ API"  # one extra combining mark
        assert len(marked) == len(base) + 1
        api_base = find_literal(base, "API")[0]
        api_marked = find_literal(marked, "API")[0]
        assert api_marked.start == api_base.start + 1

    def test_thai_combining_marks_are_single_code_points(self) -> None:
        text = "ที่"  # ท + ี + ่ = 3 code points
        assert len(text) == 3


class TestGuardFixtures:
    def test_guard_001_api_route_and_status(self) -> None:
        f = BY_ID["guard-001"]
        text = f["text"]  # เรียก /cxgateway/v1/member-xapi แล้วได้ HTTP 500
        route = find_literal(text, "/cxgateway/v1/member-xapi")
        assert route and route[0].kind == "api_route"
        status = find_literal(text, "500")
        assert status and status[0].kind == "number"
        eng = engine_terms(protect_terms=["cxgateway"])
        # Byte-for-byte: every protected literal survives reconstruction
        _assert_reconstruction(text, eng)

    def test_guard_002_inline_code_and_duration(self) -> None:
        f = BY_ID["guard-002"]
        text = f["text"]  # ใช้ `HttpClient` และ timeout 2s
        inline = find_literal(text, "`HttpClient`")
        assert inline and inline[0].kind == "code_inline"
        dur = find_literal(text, "2s")
        assert dur and dur[0].kind == "number"
        _assert_reconstruction(text, engine())

    def test_guard_003_json_content(self) -> None:
        f = BY_ID["guard-003"]
        text = f["text"]  # {"BICode":"TH01","count":500}
        js = spans_of(text, "json")
        assert len(js) == 1
        payload = json.loads(text[js[0].start : js[0].end])
        assert payload == {"BICode": "TH01", "count": 500}
        # BICode / TH01 / 500 all inside the protected JSON span
        for lit in ("BICode", "TH01", "500"):
            assert text.find(lit) >= js[0].start

    def test_glossary_protect_terms_are_spans(self) -> None:
        f = BY_ID["mix-001"]
        text = f["text"]  # ขออนุญาติ deploy API ไป production
        eng = engine_terms(protect_terms=["deploy", "API", "production"])
        for lit in f["protected_literals"]:
            found = find_literal(text, lit, eng)
            assert found, f"{lit} not protected"


class TestStructuralDetection:
    def test_fenced_code_block_multiline(self) -> None:
        text = "ดูโค้ดนี้:\n```python\nx = 1\nprint(x)\n```\nเสร็จแล้ว"
        fence = spans_of(text, "code_fence")
        assert len(fence) == 1
        assert text[fence[0].start : fence[0].end].startswith("```python")

    def test_url(self) -> None:
        text = "เปิด https://example.com/a/b?x=1 ดูข้อมูล"
        url = find_literal(text, "https://example.com/a/b?x=1")
        assert url and url[0].kind == "url"

    def test_file_path(self) -> None:
        text = "แก้ไข้ไฟล์ src/config/app.yaml ก่อน"
        p = find_literal(text, "src/config/app.yaml")
        assert p and p[0].kind == "path"

    def test_iso_date(self) -> None:
        text = "ประกาศเมื่อ 2026-10-11 โดยทีมงาน"
        d = find_literal(text, "2026-10-11")
        assert d and d[0].kind == "date"

    def test_identifier_p95(self) -> None:
        text = "latency p95 คือ 200ms"
        ident = find_literal(text, "p95")
        assert ident and ident[0].kind == "identifier"
        dur = find_literal(text, "200ms")
        assert dur and dur[0].kind == "number"

    def test_plain_thai_text_has_no_spans(self) -> None:
        text = "ประมวลผลคำขอเรียบร้อยแล้ว"
        assert engine().find_spans(text) == []


class TestPriorityAndOverlap:
    def test_output_is_sorted_nonoverlapping(self) -> None:
        text = "ดู `https://x.io/api` และ /v1/users ปี 2026-10-11"
        spans = engine().find_spans(text)
        for a, b in zip(spans, spans[1:], strict=False):
            assert a.end <= b.start, f"overlap: {a} {b}"
        assert all(s.kind in KIND_PRIORITY for s in spans)

    def test_inline_code_wins_over_inner_url(self) -> None:
        text = "```python\nrequests.get('http://in.fence')\n```"
        spans = engine().find_spans(text)
        kinds = {s.kind for s in spans}
        assert kinds == {"code_fence"}  # fence swallows everything inside

    def test_priority_order_is_documented(self) -> None:
        assert KIND_PRIORITY[0] == "code_fence"
        assert "code_inline" in KIND_PRIORITY[:3]


class TestMasking:
    def test_mask_same_length_offsets_identity(self) -> None:
        text = "เรียก /cxgateway/v1/member-xapi ได้ 500"
        eng = engine()
        view = build_analysis_view(text, eng.find_spans(text))
        assert len(view.text) == len(text)  # offsets are identity
        for span in view.protected_spans:
            assert view.text[span.start : span.end] != text[span.start : span.end]

    def test_reconstruction_is_byte_identical(self) -> None:
        text = "ใช้ `HttpClient` และ timeout 2s กับ https://x.io ปี 2026-10-11"
        eng = engine()
        view = build_analysis_view(text, eng.find_spans(text))
        assert view.reconstruct() == text

    def test_map_back(self) -> None:
        text = "เรียก /cxgateway/v1/member-xapi แล้ว ได้ 500"
        eng = engine()
        view = build_analysis_view(text, eng.find_spans(text))
        # Identity mapping: every view index equals original index
        for i in range(len(text)):
            assert view.map_to_original(i) == i

    def test_view_supports_non_identity_mapping(self) -> None:
        # A view that masks with different-length placeholders must still map back.
        view = AnalysisView(
            text="a@@b",
            original="aXXXXb",
            protected=[(1, 3, 1, 5)],  # view[1:3) == orig[1:5): length-changing mask
        )
        assert view.map_to_original(1) == 1
        assert view.map_to_original(3) == 5
        assert view.map_to_original(4) == 6  # shifted region; len(original) == 6


def _assert_reconstruction(text: str, eng: ProtectionEngine) -> None:
    view = build_analysis_view(text, eng.find_spans(text))
    assert view.reconstruct() == text
