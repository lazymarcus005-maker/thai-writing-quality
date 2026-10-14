"""Production-hardening regression tests (v0.2.0).

Covers the fixes from the production review:
- windowed invocation cap (no self-DoS on long-lived servers)
- bounded analyzer-bundle cache (memory exhaustion vector)
- LLM adapter payload hardening (max_tokens, opt-in JSON mode, size cap)
- persistent TWQ_GLOSSARY_FILE glossary
- preview/diff enrichment of tool outputs
"""

from __future__ import annotations

import json
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer

import pytest

from thai_writing_mcp.config.glossary import config_from_env
from thai_writing_mcp.core.pipeline import WritingEngine
from thai_writing_mcp.engines.llm_adapter import LLMAdapter
from thai_writing_mcp.schemas.errors import LLM_UNAVAILABLE, EngineError
from thai_writing_mcp.server import InvocationCap

OPT_IN = {
    "TWQ_LLM_ENABLED": "1",
    "TWQ_LLM_BASE_URL": "http://127.0.0.1:9/v1",
    "TWQ_LLM_API_KEY": "test-key-not-a-secret",
    "TWQ_LLM_MODEL": "test-model",
}


class TestInvocationCapWindow:
    def test_windowed_cap_recovers_instead_of_bricking(self) -> None:
        cap = InvocationCap(2, window_s=0.05)
        for _ in range(2):
            cap.check()
        with pytest.raises(EngineError) as exc:
            cap.check()
        assert exc.value.retryable is True  # retryable, unlike the stdio total cap
        import time

        time.sleep(0.06)  # old invocations leave the window
        cap.check()  # server serves traffic again

    def test_lifetime_cap_still_fails_closed_for_stdio(self) -> None:
        cap = InvocationCap(1)
        cap.check()
        with pytest.raises(EngineError) as exc:
            cap.check()
        assert exc.value.retryable is False


class TestBoundedBundleCache:
    def test_cycling_glossaries_cannot_grow_memory(self) -> None:
        engine = WritingEngine()
        for i in range(40):
            engine.analyze("ขออนุญาติ deploy", glossary=[f"term{i}"])
        assert len(engine._bundles) <= 16  # bounded LRU, not unbounded dict

    def test_repeated_glossary_hits_cached_bundle(self) -> None:
        engine = WritingEngine()
        engine.analyze("ขออนุญาติ", glossary=["a"])
        before = len(engine._bundles)
        engine.analyze("ขออนุญาติ", glossary=["a"])
        assert len(engine._bundles) == before


class TestOutputEnrichment:
    def test_analyze_issues_carry_preview(self) -> None:
        text = "ขออนุญาติ deploy API ไป production"
        result = WritingEngine().analyze(text)
        issue = next(i for i in result["issues"] if i["original"] == "อนุญาติ")
        assert "⟦อนุญาติ⟧" in issue["preview"]
        assert "ขอ" in issue["preview"]  # left context visible

    def test_correct_patches_carry_diff(self) -> None:
        result = WritingEngine().correct("ขออนุญาติ deploy API ไป production")
        patch = next(p for p in result["patches"] if p["original"] == "อนุญาติ")
        assert patch["diff"] == "- อนุญาติ\n+ อนุญาต"


class TestGlossaryFromEnv:
    def test_unset_returns_none(self) -> None:
        assert config_from_env({}) is None

    def test_broken_file_raises_typed_error(self, tmp_path) -> None:
        bad = tmp_path / "bad.json"
        bad.write_text("{not json")
        with pytest.raises(EngineError):
            config_from_env({"TWQ_GLOSSARY_FILE": str(bad)})

    def test_loaded_config_changes_dictionary_version(self, tmp_path) -> None:
        good = tmp_path / "g.json"
        good.write_text(json.dumps({"version": "9", "global": {"protect": ["Zyxq"]}}))
        cfg = config_from_env({"TWQ_GLOSSARY_FILE": str(good)})
        assert cfg is not None and cfg.version == "9"


class TestLLMAdapterHardening:
    def _capturing_transport(self, capture: dict):
        def transport(method, url, headers, body_bytes, timeout):
            capture["payload"] = json.loads(body_bytes)
            body = json.dumps(
                {"choices": [{"message": {"content": json.dumps({"suggestions": []})}}]}
            )
            return 200, body.encode()

        return transport

    def test_payload_has_max_tokens(self) -> None:
        capture: dict = {}
        adapter = LLMAdapter(env=OPT_IN, transport=self._capturing_transport(capture))
        adapter.propose("ขออนุญาติ")
        assert capture["payload"]["max_tokens"] == 2_000
        assert "response_format" not in capture["payload"]  # opt-in only

    def test_json_mode_opt_in(self) -> None:
        capture: dict = {}
        adapter = LLMAdapter(
            env=OPT_IN | {"TWQ_LLM_JSON_MODE": "1"},
            transport=self._capturing_transport(capture),
        )
        adapter.propose("ขออนุญาติ")
        assert capture["payload"]["response_format"] == {"type": "json_object"}

    def test_oversized_provider_response_discarded(self) -> None:
        class Handler(BaseHTTPRequestHandler):
            def do_POST(self) -> None:
                self.send_response(200)
                self.send_header("Content-Type", "application/json")
                self.end_headers()
                self.wfile.write(b"x" * 2_000_000)

        server = HTTPServer(("127.0.0.1", 0), Handler)
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        try:
            adapter = LLMAdapter(
                env=OPT_IN
                | {"TWQ_LLM_BASE_URL": f"http://127.0.0.1:{server.server_port}/v1"}
            )
            with pytest.raises(EngineError) as exc:
                adapter.propose("ขออนุญาติ")
            assert exc.value.code == LLM_UNAVAILABLE
            assert "size cap" in exc.value.message
        finally:
            server.shutdown()
