"""Core pipeline: protection -> analysis views -> issues -> patches -> verification.

Pure functions over the request payload; no MCP concepts here (architecture
boundary: the transport adapter knows nothing about NLP rules).
"""

from __future__ import annotations

from collections import Counter

from thai_writing_mcp.config.glossary import GlossaryConfig, GlossaryView, default_config
from thai_writing_mcp.core.issues import make_issue
from thai_writing_mcp.core.offsets import build_analysis_view
from thai_writing_mcp.core.patches import DEFAULT_MAX_EDIT_RATIO, PatchPlanner, apply_patches
from thai_writing_mcp.core.protection import ProtectionEngine
from thai_writing_mcp.core.validate import InvariantVerifier
from thai_writing_mcp.engines.english import EnglishAnalyzer
from thai_writing_mcp.engines.thai import ThaiAnalyzer
from thai_writing_mcp.engines.unicode import UnicodeInspector
from thai_writing_mcp.schemas.errors import RULE_FAILURE, EngineError
from thai_writing_mcp.schemas.models import Issue, ProtectedSpan, versions_block


class WritingEngine:
    """The deterministic P0 engine behind all MCP tools."""

    def __init__(self, config: GlossaryConfig | None = None) -> None:
        self._config = config or default_config()
        # Analyzer bundles are expensive (62k-word Trie) — build once per
        # distinct request-glossary, not per call. Shared read-only across
        # threads (benign race: worst case one duplicate build).
        self._bundles: dict[
            tuple, tuple[GlossaryView, ProtectionEngine, ThaiAnalyzer, EnglishAnalyzer]
        ] = {}

    # -- shared context -----------------------------------------------------
    def _context(
        self, profile: str, glossary: list[str] | None
    ) -> tuple[GlossaryView, ProtectionEngine, ThaiAnalyzer, EnglishAnalyzer]:
        key = tuple(sorted(glossary or []))
        if key not in self._bundles:
            view = GlossaryView(self._config, request_terms=glossary)
            protection = ProtectionEngine(protect_terms=view.protect_terms())
            self._bundles[key] = (view, protection, ThaiAnalyzer(view), EnglishAnalyzer(view))
        return self._bundles[key]

    def _issues(
        self,
        text: str,
        analyzers: tuple[GlossaryView, ProtectionEngine, ThaiAnalyzer, EnglishAnalyzer],
        spans: list[ProtectedSpan],
        profile: str,
    ) -> list[Issue]:
        analysis_view = build_analysis_view(text, spans)
        _view, _protection, thai, english = analyzers
        issues: list[Issue] = []
        issues.extend(UnicodeInspector().inspect(analysis_view.text, spans))
        issues.extend(thai.analyze(analysis_view.text, spans, profile))
        issues.extend(english.analyze(analysis_view.text, spans, profile))
        unique: dict[str, Issue] = {}
        for issue in sorted(issues, key=lambda i: (i.start, i.end, i.rule_id)):
            unique.setdefault(issue.id, issue)
        return list(unique.values())

    # -- tools ---------------------------------------------------------------
    def analyze(
        self, text: str, *, profile: str = "technical", glossary: list[str] | None = None
    ) -> dict:
        glossary_view, protection, _thai, _english = self._context(profile, glossary)
        spans = protection.find_spans(text)
        issues = self._issues(text, self._context(profile, glossary), spans, profile)
        by_category = dict(Counter(i.category for i in issues))
        return {
            **versions_block(glossary_view.dictionary_version()),
            "original": text,
            "protected_spans": [sp.model_dump() for sp in spans],
            "issues": [i.model_dump() for i in issues],
            "summary": {"count": len(issues), "by_category": by_category},
        }

    def correct(
        self,
        text: str,
        *,
        profile: str = "technical",
        mode: str = "suggest",
        max_changes: int = 10,
        glossary: list[str] | None = None,
    ) -> dict:
        glossary_view, protection, _thai, _english = self._context(profile, glossary)
        spans = protection.find_spans(text)
        issues = self._issues(text, self._context(profile, glossary), spans, profile)
        planner = PatchPlanner()
        patches = planner.plan(text, issues, max_changes, protected_spans=spans)

        if mode == "safe_apply":
            corrected = planner.apply_safe(text, patches, issues)
        elif mode == "suggest":
            # Preview only: nothing is committed, so the edit-ratio gate is
            # not enforced here (it guards auto-application, not proposals).
            corrected = apply_patches(text, patches, max_edit_ratio=1.0)
        else:  # pragma: no cover - schema layer rejects other modes
            raise EngineError(RULE_FAILURE, f"unknown mode {mode!r}")

        applied_rules = set()
        if mode == "safe_apply":
            review_positions = {(i.start, i.end) for i in issues if i.requires_review}
            for p in patches:
                p.applied = (p.start, p.end) not in review_positions
                if p.applied:
                    applied_rules.add(p.reason)

        verifier = InvariantVerifier()
        validation = verifier.verify(text, corrected, spans, patches, numbers_authorized=False)
        requires_review = any(i.requires_review for i in issues) or (
            mode == "suggest" and bool(patches)
        )
        applied_count = sum(1 for p in patches if p.applied)
        summary = (
            f"{applied_count}/{len(patches)} patch(es) applied; "
            f"{len(issues)} issue(s) found."
            if mode == "safe_apply"
            else (
                f"{len(patches)} patch(es) suggested; {len(issues)} issue(s) found. "
                "Review before applying."
            )
        )
        return {
            **versions_block(glossary_view.dictionary_version()),
            "original": text,
            "corrected": corrected,
            "patches": [p.model_dump() for p in patches],
            "issues": [i.model_dump() for i in issues],
            "requires_review": requires_review,
            "validation": {
                "ok": validation.ok,
                "violations": validation.violations,
                "protected_spans_checked": len(spans),
            },
            "summary": summary,
        }

    def validate(
        self, text: str, *, profile: str = "technical", glossary: list[str] | None = None
    ) -> dict:
        result = self.analyze(text, profile=profile, glossary=glossary)
        issues = result["issues"]
        # FAIL needs deterministic evidence (spec): high-severity structural
        # findings (bidi controls, confusables). Everything else is WARN.
        deterministic_fail = any(
            i["severity"] == "high" and not i["requires_review"] for i in issues
        )
        status = "FAIL" if deterministic_fail else ("WARN" if issues else "PASS")
        return {
            **{k: v for k, v in result.items() if k.startswith(("schema", "engine", "dictionary"))},
            "status": status,
            "issues": issues,
            "protected_integrity": True,
            "summary": {
                "count": len(issues),
                "by_category": result["summary"]["by_category"],
            },
        }


def make_issue_public() -> None:  # pragma: no cover - re-export helper for typing
    _ = make_issue


_ = DEFAULT_MAX_EDIT_RATIO  # re-exported for adapters
