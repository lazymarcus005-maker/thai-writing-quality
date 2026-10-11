"""Core pipeline: protection -> analysis views -> issues -> patches -> verification.

Pure functions over the request payload; no MCP concepts here (architecture
boundary: the transport adapter knows nothing about NLP rules).
"""

from __future__ import annotations

from collections import Counter

from thai_writing_mcp.config.glossary import GlossaryConfig, GlossaryView, default_config
from thai_writing_mcp.core.issues import make_issue
from thai_writing_mcp.core.offsets import build_analysis_view
from thai_writing_mcp.core.patches import (
    DEFAULT_MAX_EDIT_RATIO,
    PatchPlanner,
    apply_patches,
)
from thai_writing_mcp.core.patches import _bounded_levenshtein as _edit_size
from thai_writing_mcp.core.protection import ProtectionEngine
from thai_writing_mcp.core.validate import InvariantVerifier
from thai_writing_mcp.engines.english import EnglishAnalyzer
from thai_writing_mcp.engines.style import StyleAnalyzer
from thai_writing_mcp.engines.thai import ThaiAnalyzer
from thai_writing_mcp.engines.unicode import UnicodeInspector
from thai_writing_mcp.schemas.errors import (
    PROTECTED_CONTENT_VIOLATION,
    RULE_FAILURE,
    EngineError,
)
from thai_writing_mcp.schemas.models import Issue, Patch, ProtectedSpan, versions_block


class WritingEngine:
    """The deterministic P0 engine behind all MCP tools."""

    def __init__(self, config: GlossaryConfig | None = None) -> None:
        self._config = config or default_config()
        # Analyzer bundles are expensive (62k-word Trie) — build once per
        # distinct request-glossary, not per call. Shared read-only across
        # threads (benign race: worst case one duplicate build).
        self._bundles: dict[
            tuple,
            tuple[GlossaryView, ProtectionEngine, ThaiAnalyzer, EnglishAnalyzer, StyleAnalyzer],
        ] = {}

    # -- shared context -----------------------------------------------------
    def _context(
        self, profile: str, glossary: list[str] | None
    ) -> tuple[GlossaryView, ProtectionEngine, ThaiAnalyzer, EnglishAnalyzer, StyleAnalyzer]:
        key = tuple(sorted(glossary or []))
        if key not in self._bundles:
            view = GlossaryView(self._config, request_terms=glossary)
            protection = ProtectionEngine(protect_terms=view.protect_terms())
            self._bundles[key] = (
                view,
                protection,
                ThaiAnalyzer(view),
                EnglishAnalyzer(view),
                StyleAnalyzer(),
            )
        return self._bundles[key]

    def _issues(
        self,
        text: str,
        analyzers: tuple[
            GlossaryView, ProtectionEngine, ThaiAnalyzer, EnglishAnalyzer, StyleAnalyzer
        ],
        spans: list[ProtectedSpan],
        profile: str,
    ) -> list[Issue]:
        analysis_view = build_analysis_view(text, spans)
        _view, _protection, thai, english, style = analyzers
        issues: list[Issue] = []
        issues.extend(UnicodeInspector().inspect(analysis_view.text, spans))
        issues.extend(thai.analyze(analysis_view.text, spans, profile))
        issues.extend(english.analyze(analysis_view.text, spans, profile))
        issues.extend(style.analyze(analysis_view.text, spans, profile))
        unique: dict[str, Issue] = {}
        for issue in sorted(issues, key=lambda i: (i.start, i.end, i.rule_id)):
            unique.setdefault(issue.id, issue)
        return list(unique.values())

    # -- tools ---------------------------------------------------------------
    def analyze(
        self, text: str, *, profile: str = "technical", glossary: list[str] | None = None
    ) -> dict:
        context = self._context(profile, glossary)
        glossary_view, protection = context[0], context[1]
        spans = protection.find_spans(text)
        issues = self._issues(text, context, spans, profile)
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
        context = self._context(profile, glossary)
        glossary_view, protection = context[0], context[1]
        spans = protection.find_spans(text)
        issues = self._issues(text, context, spans, profile)
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
            f"{applied_count}/{len(patches)} patch(es) applied; {len(issues)} issue(s) found."
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

    def merge_external_proposals(
        self,
        text: str,
        proposals: list[tuple[int, int, str, str, str]],
        *,
        profile: str = "technical",
        glossary: list[str] | None = None,
    ) -> dict:
        """Route LLM (or any external) proposals through the deterministic gate.

        Proposals never apply directly (security.md): each becomes a patch
        that must pass preconditions, protected-span integrity, numeric
        integrity, and the edit-ratio bound. Violating proposals are
        declined loudly, never repaired.
        """
        context = self._context(profile, glossary)
        spans = context[1].find_spans(text)
        candidates: list[Patch] = []
        for start, end, original, replacement, reason in proposals:
            patch = Patch(
                start=start,
                end=end,
                original=original,
                replacement=replacement,
                applied=False,
                reason=f"llm:{reason}" if not reason.startswith("llm:") else reason,
            )
            if any(sp.start <= patch.start < sp.end for sp in spans):
                continue  # inside a protected span: dropped outright
            candidates.append(patch)
        candidates.sort(key=lambda p: (p.start, p.end))
        accepted: list[Patch] = []
        declined: list[dict] = []
        for patch in candidates:
            if accepted and patch.start < accepted[-1].end:
                declined.append({"patch": patch.model_dump(), "violation": "overlap"})
                continue
            if (
                patch.start < 0
                or patch.end > len(text)
                or patch.original != text[patch.start : patch.end]
            ):
                declined.append({"patch": patch.model_dump(), "violation": "precondition"})
                continue
            accepted.append(patch)
        try:
            corrected = apply_patches(text, accepted)
            verifier = InvariantVerifier().verify(
                text, corrected, spans, accepted, numbers_authorized=False
            )
            violations = verifier.violations
            if violations:
                raise EngineError(
                    PROTECTED_CONTENT_VIOLATION,
                    "proposals violate invariants",
                    details={"violations": violations},
                )
        except EngineError as exc:
            # Fail closed: decline the whole batch rather than repair silently.
            return {
                "accepted": [],
                "declined": declined + [{"batch": True, "violation": str(exc)}],
                "corrected": text,
                "requires_review": True,
                "protected_spans_checked": len(spans),
            }
        return {
            "accepted": [p.model_dump() for p in accepted],
            "declined": declined,
            "corrected": corrected,
            "requires_review": True,  # external proposals ALWAYS require review
            "protected_spans_checked": len(spans),
        }

    def rewrite(
        self,
        text: str,
        *,
        profile: str = "technical",
        preserve_meaning: bool = True,
        glossary: list[str] | None = None,
        llm_adapter=None,
    ) -> dict:
        """thai_rewrite (T-014): reviewed proposals, never auto-published.

        ``preserve_meaning`` is a REQUEST, not a proof (spec §6): the
        deterministic semantic gate bounds every patch (per-patch
        meaning-risk ratio, total edit ratio, protected spans, numbers)
        and abstains when a change is too large to vouch for. The output
        always carries ``requires_review: true``.
        """
        context = self._context(profile, glossary)
        spans = context[1].find_spans(text)
        issues = self._issues(text, context, spans, profile)
        planner = PatchPlanner()
        patches = planner.plan(text, issues, max_changes=25, protected_spans=spans)

        llm_status = "disabled"
        llm_merged: dict | None = None
        if llm_adapter is not None and llm_adapter.enabled:
            try:
                proposals = llm_adapter.propose(text, profile=profile)
                llm_status = "ok"
                llm_merged = self.merge_external_proposals(
                    text,
                    [(p.start, p.end, p.original, p.replacement, p.reason) for p in proposals],
                    profile=profile,
                    glossary=glossary,
                )
            except EngineError:
                llm_status = "unavailable"  # fail closed to deterministic mode

        max_ratio = 2.0 if preserve_meaning else 3.0
        risky = [
            p
            for p in patches
            if p.original
            and (len(p.replacement) / len(p.original) > max_ratio or not p.replacement)
        ]
        risky_spans = {(p.start, p.end) for p in risky}
        safe = [p for p in patches if (p.start, p.end) not in risky_spans]

        violations: list[str] = []
        changed = sum(_edit_size(p.original, p.replacement) for p in safe)
        if text and changed / len(text) > 0.3:
            violations.append("max_edit_ratio_exceeded: rewrite abstained, returning original")
            safe = []
        if llm_merged and llm_merged["declined"]:
            violations.append(f"llm_proposals_declined: {len(llm_merged['declined'])}")

        try:
            proposed = apply_patches(text, safe, max_edit_ratio=1.0)
        except EngineError as exc:
            violations.append(str(exc))
            proposed = text

        verification = InvariantVerifier().verify(
            text, proposed, spans, safe, numbers_authorized=False
        )
        violations.extend(verification.violations)
        if not verification.ok:
            proposed = text  # never publish an unverified proposal

        if preserve_meaning and llm_merged and llm_merged["accepted"]:
            # Accepted LLM patches are proposals only; surface them as
            # additional patches (never auto-spliced into `proposed`).
            for ap in llm_merged["accepted"]:
                patches.append(Patch(**ap))

        summary = (
            f"{len(safe)} patch(es) proposed, {len(risky)} withheld as meaning-risk; "
            f"review required. llm: {llm_status}."
        )
        return {
            **versions_block(context[0].dictionary_version()),
            "original": text,
            "proposed": proposed,
            "patches": [p.model_dump() for p in patches],
            "issues": [i.model_dump() for i in issues],
            "requires_review": True,
            "validation": {
                "ok": not violations,
                "violations": violations,
                "protected_spans_checked": len(spans),
                "preserve_meaning": preserve_meaning,
            },
            "llm_status": llm_status,
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
