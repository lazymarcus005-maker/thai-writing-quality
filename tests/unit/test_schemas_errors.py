"""T-002: typed input schemas, size limits, structured errors.

Seam: schemas.errors / schemas.models — every tool entry point validates here
before any work happens. Negative tests cover every stable error code.
"""

import pytest

from thai_writing_mcp.schemas.errors import (
    INVALID_INPUT,
    TOO_LARGE,
    EngineError,
    error_dict,
)
from thai_writing_mcp.schemas.models import AnalyzeRequest, CorrectRequest, ValidateRequest
from thai_writing_mcp.schemas.validate import validate_request

MAX = 50_000


class TestErrorShape:
    def test_error_has_stable_shape(self) -> None:
        err = EngineError(INVALID_INPUT, "bad text", retryable=False, details={"field": "text"})
        d = error_dict(err)
        assert set(d) == {"code", "message", "retryable", "details"}
        assert d["code"] == "INVALID_INPUT"
        assert d["retryable"] is False

    def test_stable_codes_exist(self) -> None:
        from thai_writing_mcp.schemas.errors import (
            LLM_UNAVAILABLE,
            PROTECTED_CONTENT_VIOLATION,
            RULE_FAILURE,
        )

        assert {
            INVALID_INPUT,
            TOO_LARGE,
            RULE_FAILURE,
            PROTECTED_CONTENT_VIOLATION,
            LLM_UNAVAILABLE,
        } == {
            "INVALID_INPUT",
            "TOO_LARGE",
            "RULE_FAILURE",
            "PROTECTED_CONTENT_VIOLATION",
            "LLM_UNAVAILABLE",
        }


class TestAnalyzeRequest:
    def test_valid_defaults(self) -> None:
        req = validate_request(AnalyzeRequest, {"text": "สวัสดี"})
        assert req.text == "สวัสดี"
        assert req.profile == "technical"  # spec default

    def test_all_profiles_accepted_end_to_end(self) -> None:
        for profile in ("general", "formal", "technical"):
            req = validate_request(AnalyzeRequest, {"text": "x", "profile": profile})
            assert req.profile == profile

    @pytest.mark.parametrize("bad", [None, 123, ["x"], {"t": 1}])
    def test_text_must_be_string(self, bad) -> None:
        with pytest.raises(EngineError) as ei:
            validate_request(AnalyzeRequest, {"text": bad})
        assert ei.value.code == INVALID_INPUT

    def test_oversized_text_returns_too_large(self) -> None:
        with pytest.raises(EngineError) as ei:
            validate_request(AnalyzeRequest, {"text": "ก" * (MAX + 1)})
        assert ei.value.code == TOO_LARGE
        assert ei.value.details["limit"] == MAX
        assert ei.value.details["actual"] == MAX + 1

    @pytest.mark.parametrize("bad", ["General", "informal", "", None, 1])
    def test_invalid_profile(self, bad) -> None:
        with pytest.raises(EngineError) as ei:
            validate_request(AnalyzeRequest, {"text": "x", "profile": bad})
        assert ei.value.code == INVALID_INPUT

    def test_glossary_must_be_string_list(self) -> None:
        req = validate_request(AnalyzeRequest, {"text": "x", "glossary": ["projA", "Redis"]})
        assert req.glossary == ["projA", "Redis"]
        with pytest.raises(EngineError) as ei:
            validate_request(AnalyzeRequest, {"text": "x", "glossary": ["ok", 42]})
        assert ei.value.code == INVALID_INPUT


class TestCorrectRequest:
    def test_defaults_to_suggest(self) -> None:
        req = validate_request(CorrectRequest, {"text": "x"})
        assert req.mode == "suggest"  # FR-007: suggest is the default
        assert req.max_changes == 10

    def test_safe_apply_is_explicit(self) -> None:
        req = validate_request(CorrectRequest, {"text": "x", "mode": "safe_apply"})
        assert req.mode == "safe_apply"

    def test_invalid_mode(self) -> None:
        with pytest.raises(EngineError) as ei:
            validate_request(CorrectRequest, {"text": "x", "mode": "auto"})
        assert ei.value.code == INVALID_INPUT

    @pytest.mark.parametrize("bad", [0, -1, "ten", 1.5, 100_000])
    def test_invalid_max_changes(self, bad) -> None:
        with pytest.raises(EngineError) as ei:
            validate_request(CorrectRequest, {"text": "x", "max_changes": bad})
        assert ei.value.code == INVALID_INPUT


class TestValidateRequest:
    def test_valid(self) -> None:
        req = validate_request(ValidateRequest, {"text": "สวัสดี", "profile": "formal"})
        assert req.profile == "formal"


class TestUnknownFields:
    def test_unknown_fields_rejected(self) -> None:
        with pytest.raises(EngineError) as ei:
            validate_request(AnalyzeRequest, {"text": "x", "evil": True})
        assert ei.value.code == INVALID_INPUT
