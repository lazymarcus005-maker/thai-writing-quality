"""T-005: layered glossary and terminology policy.

Seam: config.glossary (GlossaryConfig + GlossaryView).
Layers: global -> domain -> project -> request; protection is a union,
canonical/suggest merge with deeper layers taking precedence, and protection
always overrides automatic correction unless editing is explicitly authorized.
"""

import json

import pytest

from thai_writing_mcp.config.glossary import EXAMPLE_GLOSSARY_PATH, GlossaryConfig, GlossaryView
from thai_writing_mcp.schemas.errors import INVALID_INPUT, EngineError

EXAMPLE = json.loads(EXAMPLE_GLOSSARY_PATH.read_text())


def view_with(request_terms: list[str] | None = None) -> GlossaryView:
    return GlossaryView(GlossaryConfig.from_dict(EXAMPLE), request_terms=request_terms)


class TestExampleGlossary:
    def test_protect_rules_from_example(self) -> None:
        v = view_with()
        terms = v.protect_terms()
        for term in [
            "API",
            "Redis",
            "Kubernetes",
            "Docker",
            "HttpClient",
            "p95",
            "cxgateway",
            "BICode",
        ]:
            assert term in terms, f"missing protect term: {term}"

    def test_canonical_rule_anuyat(self) -> None:
        v = view_with()
        assert v.canonical_pairs().get("อนุญาติ") == "อนุญาต"

    def test_dictionary_version_exposed_and_stable(self) -> None:
        v1 = view_with()
        v2 = view_with()
        assert v1.dictionary_version()
        assert v1.dictionary_version() == v2.dictionary_version()  # FR-015 reproducibility

    def test_request_terms_are_protected(self) -> None:
        v = view_with(request_terms=["myProjectToken"])
        assert "myProjectToken" in v.protect_terms()


class TestPriority:
    def test_protection_overrides_canonical_by_default(self) -> None:
        cfg = {
            "version": "1.0",
            "global": {"protect": ["Gateway"], "canonical": {"gateway": "Gateway"}},
            "project": {"protect": ["gateway"]},
        }
        v = GlossaryView(GlossaryConfig.from_dict(cfg))
        # "gateway" is protected at project level: no automatic canonical rewrite...
        assert "gateway" not in v.canonical_pairs()
        # ...unless the request explicitly authorizes editing that term.
        assert "gateway" in v.canonical_pairs(authorize_edit=True)

    def test_deeper_layer_canonical_wins(self) -> None:
        cfg = {
            "version": "2.0",
            "global": {"canonical": {" respons": "response"}},
            "domain": {"software": {"canonical": {" respons": "respond"}}},
        }
        v = GlossaryView(GlossaryConfig.from_dict(cfg))
        assert v.canonical_pairs()[" respons"] == "respond"

    def test_suggest_pairs(self) -> None:
        cfg = {
            "version": "1.0",
            "global": {"suggest": {"รัน": "เรียกใช้"}},
        }
        v = GlossaryView(GlossaryConfig.from_dict(cfg))
        assert v.suggest_pairs()["รัน"] == "เรียกใช้"


class TestSnapshotRoundTrip:
    def test_round_trip_preserves_config(self) -> None:
        cfg = GlossaryConfig.from_dict(EXAMPLE)
        restored = GlossaryConfig.from_dict(cfg.to_dict())
        assert restored.to_dict() == cfg.to_dict()

    def test_snapshot_is_json_serializable_and_sorted(self) -> None:
        cfg = GlossaryConfig.from_dict(EXAMPLE)
        snap = cfg.snapshot()
        twice = json.loads(json.dumps(snap, sort_keys=True))
        assert twice == json.loads(json.dumps(cfg.snapshot(), sort_keys=True))


class TestMalformedConfig:
    @pytest.mark.parametrize(
        "payload",
        [
            {"version": "1.0"},  # no layers
            {"layers": {}},  # missing version
            {"version": 3, "global": {}},  # version not a string
            {"version": "1.0", "global": {"protect": "API"}},  # protect not a list
            {"version": "1.0", "global": {"protect": [42]}},  # non-string term
            {"version": "1.0", "global": {"canonical": {"a": 1}}},  # canonical value not str
            {"version": "1.0", "bogus": {}},  # unknown layer
            {"version": "1.0", "domain": {"sw": {"typo": []}}},  # unknown layer key
        ],
    )
    def test_malformed_rejected_atomically(self, payload) -> None:
        with pytest.raises(EngineError) as ei:
            GlossaryConfig.from_dict(payload)
        assert ei.value.code == INVALID_INPUT

    def test_error_details_name_the_field(self) -> None:
        with pytest.raises(EngineError) as ei:
            GlossaryConfig.from_dict({"version": "1.0", "global": {"protect": [42]}})
        assert "global.protect" in json.dumps(ei.value.details)
