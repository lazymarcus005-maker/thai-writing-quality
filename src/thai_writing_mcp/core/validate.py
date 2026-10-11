"""Invariant verifier (T-008, FR-009).

Verifies proposed output against the original using an **ordered marker
scan** — protected spans must reappear in output in order, with at least
their original multiplicity — which is strictly stronger than naive
substring containment. Numbers/dates/units are protected unless explicitly
authorized. The output must be exactly expressible as the declared patches
over the original, which keeps every unchanged section byte-identical.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

from thai_writing_mcp.core.patches import apply_patches
from thai_writing_mcp.schemas.errors import (
    PROTECTED_CONTENT_VIOLATION,
    RULE_FAILURE,
    EngineError,
)
from thai_writing_mcp.schemas.models import Patch, ProtectedSpan

_RE_ANY_NUMBER = re.compile(r"\d[\d,]*(?:\.\d+)?")
_RE_ANY_DATE = re.compile(r"\d{4}-\d{2}-\d{2}|\d{1,2}/\d{1,2}/\d{2,4}")


@dataclass
class VerificationResult:
    ok: bool
    violations: list[str]


class InvariantVerifier:
    """Rejects violations — never silently repairs (FR-009)."""

    def verify(
        self,
        original: str,
        output: str,
        protected_spans: list[ProtectedSpan],
        patches: list[Patch],
        *,
        numbers_authorized: bool = False,
    ) -> VerificationResult:
        violations: list[str] = []
        literals = [original[sp.start : sp.end] for sp in protected_spans]
        violations.extend(self._protected_integrity(output, literals))
        if not numbers_authorized:
            violations.extend(self._numeric_integrity(original, output, protected_spans))
        try:
            expected = apply_patches(original, patches)
        except EngineError as exc:
            violations.append(f"patch_invariant: {exc}")
        else:
            if output != expected:
                violations.append(
                    "output_mismatch: output is not the declared patches over the original"
                )
        return VerificationResult(ok=not violations, violations=violations)

    def verify_or_raise(
        self,
        original: str,
        output: str,
        protected_spans: list[ProtectedSpan],
        patches: list[Patch],
        *,
        numbers_authorized: bool = False,
    ) -> VerificationResult:
        result = self.verify(
            original,
            output,
            protected_spans,
            patches,
            numbers_authorized=numbers_authorized,
        )
        if not result.ok:
            protected = [v for v in result.violations if v.startswith(("protected", "numeric"))]
            code = PROTECTED_CONTENT_VIOLATION if protected else RULE_FAILURE
            raise EngineError(
                code,
                "invariant verification failed; output rejected, not repaired",
                details={"violations": result.violations},
            )
        return result

    def _protected_integrity(self, output: str, literals: list[str]) -> list[str]:
        violations: list[str] = []
        position = 0
        for i, literal in enumerate(literals):
            found = output.find(literal, position)
            if found == -1:
                violations.append(
                    f"protected_span_missing: index {i} ({literal[:20]!r} out of order or absent)"
                )
                continue
            position = found + len(literal)
        return violations

    def _numeric_integrity(
        self, original: str, output: str, protected_spans: list[ProtectedSpan]
    ) -> list[str]:
        violations: list[str] = []

        def free_numbers(text: str) -> list[str]:
            spans = [(sp.start, sp.end) for sp in protected_spans]
            found: list[str] = []
            for pattern in (_RE_ANY_DATE, _RE_ANY_NUMBER):
                for m in pattern.finditer(text):
                    if any(s <= m.start() < e for s, e in spans):
                        continue
                    found.append(m.group())
            return found

        expected = free_numbers(original)
        position = 0
        for i, literal in enumerate(expected):
            found = output.find(literal, position)
            if found == -1:
                violations.append(
                    f"numeric_changed: occurrence {i} of {literal!r} missing or moved"
                )
                position = 0  # rescan from the start for the next literal
            else:
                position = found + len(literal)
        return violations
