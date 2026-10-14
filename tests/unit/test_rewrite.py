"""T-014: thai_rewrite, writing profiles, semantic gate.

Acceptance under test:
- output ALWAYS carries requires_review=true; never auto-published
- preserve_meaning is a request, not a proof: guardrails + abstention
- general/formal/technical profiles measurably differ (FR-008, FR-011)
- protected spans and numbers intact in proposed output (validated)
- max-edit-ratio and meaning-risk guardrails enforced
"""

import sys

import pytest

from thai_writing_mcp import SCHEMA_VERSION
from thai_writing_mcp.core.pipeline import WritingEngine
from thai_writing_mcp.engines.llm_adapter import LLMAdapter
from thai_writing_mcp.schemas.errors import LLM_UNAVAILABLE

OPT_IN = {
    "TWQ_LLM_ENABLED": "1",
    "TWQ_LLM_BASE_URL": "http://127.0.0.1:9/v1",
    "TWQ_LLM_API_KEY": "k",
    "TWQ_LLM_MODEL": "m",
}


def rewrite(text: str, profile: str = "formal", **kw):
    return WritingEngine().rewrite(text, profile=profile, **kw)


class TestContract:
    def test_requires_review_is_always_true(self) -> None:
        assert rewrite("ขออนุญาติ deploy")["requires_review"] is True
        assert rewrite("ประมวลผลคำขอเรียบร้อยแล้ว", profile="general")["requires_review"] is True

    def test_contract_fields_present(self) -> None:
        out = rewrite("ขออนุญาติ deploy", profile="technical")
        for field in ("original", "proposed", "patches", "issues", "requires_review", "validation"):
            assert field in out
        assert out["schema_version"] == SCHEMA_VERSION

    def test_llm_disabled_by_default_no_network_path(self) -> None:
        out = rewrite("respones ช้า", profile="technical")
        assert out["llm_status"] == "disabled"  # deterministic-only


class TestProfilesFR008FR011:
    def test_maiyamok_spacing_suggested_formal_technical_not_general(self) -> None:
        text = "ทำงานเสร็จๆ แล้ว"
        for profile in ("formal", "technical"):
            rules = [i["rule_id"] for i in rewrite(text, profile)["issues"]]
            assert "style.maiyamok_spacing" in rules, profile
        general_rules = [i["rule_id"] for i in rewrite(text, "general")["issues"]]
        assert "style.maiyamok_spacing" not in general_rules

    def test_double_maiyamok_flagged(self) -> None:
        rules = [i["rule_id"] for i in rewrite("ดี\u0e46\u0e46 มาก", profile="formal")["issues"]]
        assert "style.double_maiyamok" in rules

    def test_style_suggestions_never_mandatory(self) -> None:
        out = rewrite("ทำงานเสร็จๆ แล้ว", profile="formal")
        issue = next(i for i in out["issues"] if i["rule_id"] == "style.maiyamok_spacing")
        assert issue["requires_review"] is True  # style is a hint, never a rule
        assert issue["severity"] in ("info", "low")

    def test_profiles_measurably_differ(self) -> None:
        text = "ใช้ Zyxpan ทำงานเสร็จๆ"
        counts = {p: len(rewrite(text, p)["issues"]) for p in ("general", "formal", "technical")}
        assert counts["formal"] > counts["general"]  # style + unknown-token review
        assert counts["technical"] >= counts["general"]


class TestSemanticGate:
    def test_protected_spans_intact_validated_not_assumed(self) -> None:
        text = "ตรวจสอบ respones ที่ /cxgateway/v1/payment-xapi ได้ 120ms"
        out = rewrite(text, profile="technical")
        for lit in ("/cxgateway/v1/payment-xapi", "120ms"):
            assert lit in out["proposed"]
        assert out["validation"]["ok"] is True
        assert out["validation"]["protected_spans_checked"] > 0

    def test_numbers_unchanged(self) -> None:
        text = "ลดจาก 850ms เหลือ 120ms แล้ว respones ก็ปกติ"
        out = rewrite(text, profile="technical")
        assert "850ms" in out["proposed"] and "120ms" in out["proposed"]

    def test_hijacked_llm_cannot_damage_proposed_output(self) -> None:
        # Provider "proposes" deleting a protected route: the merge gate
        # must decline; proposed output keeps the route byte-identical.
        def hijacked(method, url, headers, body, timeout):
            import json

            content = json.dumps(
                {
                    "suggestions": [
                        {
                            "start": 6,
                            "end": 31,
                            "original": "/cxgateway/v1/member-xapi",
                            "replacement": "",
                            "reason": "style",
                        }
                    ]
                }
            )
            return 200, json.dumps({"choices": [{"message": {"content": content}}]}).encode()

        adapter = LLMAdapter(env=OPT_IN, transport=hijacked)
        text = "เรียก /cxgateway/v1/member-xapi แล้ว 500"
        out = WritingEngine().rewrite(text, profile="technical", llm_adapter=adapter)
        assert "/cxgateway/v1/member-xapi" in out["proposed"]
        assert "500" in out["proposed"]
        assert out["requires_review"] is True

    def test_llm_unavailable_fails_closed_to_deterministic(self) -> None:
        adapter = LLMAdapter(env=OPT_IN, timeout_s=0.2)
        text = "respones ช้า"
        out = rewrite(text, profile="technical", llm_adapter=adapter)
        assert out["llm_status"] == "unavailable"
        assert out["proposed"] == "response ช้า"  # deterministic edits still proposed
        from thai_writing_mcp.schemas.errors import EngineError as _EngineError

        with pytest.raises(_EngineError) as ei:
            adapter.propose(text)
        assert ei.value.code == LLM_UNAVAILABLE


class TestGuardrails:
    def test_accepted_llm_patches_are_review_only_not_spliced(self) -> None:
        # A *legitimate* LLM proposal must not be auto-spliced either; and the
        # returned `patches` must express exactly `proposed` (deterministic).
        import json

        def provider(method, url, headers, body, timeout):
            content = json.dumps(
                {
                    "suggestions": [
                        {
                            "start": 0,
                            "end": 8,
                            "original": "respones",
                            "replacement": "response",
                            "reason": "typo",
                        }
                    ]
                }
            )
            return 200, json.dumps({"choices": [{"message": {"content": content}}]}).encode()

        adapter = LLMAdapter(env=OPT_IN, transport=provider)
        text = "respones จากระบบ"
        out = rewrite(text, profile="technical", llm_adapter=adapter)
        assert out["llm_status"] == "ok"
        assert out["requires_review"] is True
        assert out["llm_proposals"] == {"accepted": 1, "spliced": 0}
        # No llm patches leak into `patches`; patches still express `proposed`.
        assert not [p for p in out["patches"] if p["reason"].startswith("llm:")]
        spliced = text
        for p in sorted(out["patches"], key=lambda x: x["start"]):
            assert spliced[p["start"] : p["end"]] == p["original"]
            spliced = spliced[: p["start"]] + p["replacement"] + spliced[p["end"] :]
        assert spliced == out["proposed"]

    def test_max_edit_ratio_abstains(self) -> None:
        # Many long patches on a short text push the total ratio past 0.3:
        # the rewrite must abstain and return the original as `proposed`.
        text = "respones respones respones"  # 3 typos, 26 chars
        out = rewrite(text, profile="technical")
        # 3 x (lev 2) = 6/26 = 23% -> applies; sanity-check the boundary logic:
        assert out["validation"]["ok"] is True
        # Now a text engineered to exceed the bound: 1 typo in a tiny text is fine,
        # so drive the ratio with a large replacement via the merge gate instead.
        engine = WritingEngine()
        merged = engine.merge_external_proposals(
            "respones",
            [(0, 8, "respones", "X" * 30, "llm-test")],
        )
        assert merged["accepted"] == []  # edit-ratio bound refuses
        assert merged["corrected"] == "respones"

    def test_preserve_meaning_false_relaxes_but_still_reviews(self) -> None:
        text = "ทำงานเสร็จๆ แล้ว"
        strict = rewrite(text, "formal", preserve_meaning=True)
        relaxed = rewrite(text, "formal", preserve_meaning=False)
        assert strict["validation"]["preserve_meaning"] is True
        assert relaxed["validation"]["preserve_meaning"] is False
        assert relaxed["requires_review"] is True  # never auto-published either way


@pytest.mark.asyncio
async def test_rewrite_through_real_client() -> None:
    import os

    from mcp import ClientSession, StdioServerParameters
    from mcp.client.stdio import stdio_client

    params = StdioServerParameters(
        command=sys.executable,
        args=["-m", "thai_writing_mcp.server"],
        env=os.environ | {"TWQ_LOG_LEVEL": "ERROR"},
    )
    async with stdio_client(params) as (r, w):
        async with ClientSession(r, w) as s:
            await s.initialize()
            result = await s.call_tool(
                "thai_rewrite",
                {"text": "ขออนุญาติ deploy API ไป production", "profile": "technical"},
            )
            data = result.structured_content
            assert data["requires_review"] is True
            assert "อนุญาต" in data["proposed"] and "อนุญาติ" not in data["proposed"]
            assert data["llm_status"] == "disabled"
