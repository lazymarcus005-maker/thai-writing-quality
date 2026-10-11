"""Thai spelling analyzer (T-006).

Two distinct operations (architecture boundary):
1. **Tokenization** — PyThaiNLP ``word_tokenize``/``Tokenizer`` with
   ``engine='newmm'`` and a read-only custom Trie seeded from the glossary;
   runs over the masked analysis view so protected spans are invisible.
2. **Spelling** — (a) curated canonical misspelling rules (exact spans,
   outside protected regions) and (b) a dictionary check that flags
   unknown Thai tokens with PyThaiNLP spell candidates.

Every output is a suggestion; nothing is ever auto-applied. Suggestions
carry ``{text, confidence, source}`` with ``confidence=None`` — P0
confidence values are not calibrated, and the contract allows null.
Unknown/ambiguous contexts abstain via ``requires_review=true``.
"""

from __future__ import annotations

import json
from importlib import resources

from pythainlp.corpus import thai_words
from pythainlp.spell import spell
from pythainlp.tokenize import Tokenizer

from thai_writing_mcp.config.glossary import GlossaryView
from thai_writing_mcp.core.issues import make_issue
from thai_writing_mcp.core.offsets import MASK_CONT, MASK_HEAD
from thai_writing_mcp.schemas.models import Issue

_MISSPELLINGS_RESOURCE = resources.files("thai_writing_mcp.config").joinpath(
    "data/thai_misspellings.json"
)

#: Profiles that review unknown tokens (FR-008: profiles change behavior).
_TOKEN_REVIEW_PROFILES = frozenset({"formal", "technical"})
_MAX_SUGGESTIONS = 3


def _builtin_misspellings() -> dict[str, str]:
    payload = json.loads(_MISSPELLINGS_RESOURCE.read_text())
    return {k: v for k, v in payload["misspellings"].items()}


def _is_mask_fragment(token: str) -> bool:
    return MASK_HEAD in token or MASK_CONT in token


def _is_thai_token(token: str) -> bool:
    return any("\u0e00" <= ch <= "\u0e7f" for ch in token)


class ThaiAnalyzer:
    """Finds Thai misspellings and proposes candidates — suggestions only."""

    dictionary_name = "pythainlp newmm + words_th"

    def __init__(self, glossary: GlossaryView) -> None:
        self._glossary = glossary
        # Canonical pairs where the key is the wrong form; glossary wins.
        self._misspellings: dict[str, str] = {
            **_builtin_misspellings(),
            **glossary.canonical_pairs(),
        }
        # Read-only custom Trie: BASE words union glossary/project terms (a
        # fresh Trie — pythainlp's global state is never mutated). Note
        # Tokenizer(custom_dict=...) *replaces* the dictionary, so the base
        # words must be merged in explicitly.
        self._known: frozenset[str] = frozenset(thai_words()) | frozenset(glossary.protect_terms())
        self._tokenizer = Tokenizer(custom_dict=self._known, engine="newmm")

    def analyze(self, view_text: str, spans, profile: str) -> list[Issue]:
        issues: list[Issue] = []
        canonical = self._canonical_issues(view_text, spans)
        issues.extend(canonical)
        if profile in _TOKEN_REVIEW_PROFILES:
            # A curated canonical match means we already know what is wrong
            # here: token-level residue flags around it are pure noise.
            suppress = [(i.start, i.end) for i in canonical]
            issues.extend(self._unknown_token_issues(view_text, spans, suppress))
        return sorted(issues, key=lambda i: (i.start, i.end))

    def _canonical_issues(self, view_text: str, spans) -> list[Issue]:
        issues: list[Issue] = []
        for wrong, right in self._misspellings.items():
            start = 0
            while (found := view_text.find(wrong, start)) != -1:
                start = found + len(wrong)
                if any(sp.start <= found < sp.end for sp in spans):
                    continue  # protected span: never touch
                issues.append(
                    make_issue(
                        rule_id="spelling.canonical",
                        category="spelling",
                        severity="medium",
                        start=found,
                        original=wrong,
                        suggestions=[right],
                        message=f"known misspelling; canonical form is {right!r}",
                        requires_review=False,
                        confidences=[None],
                        sources=["canonical_dictionary"],
                    )
                )
        return issues

    def _unknown_token_issues(
        self, view_text: str, spans, suppress: list[tuple[int, int]]
    ) -> list[Issue]:
        issues: list[Issue] = []
        toks = self._tokenize(view_text)
        claimed: list[tuple[int, int]] = list(suppress)

        # Cluster pass: merge an unknown token with adjacent tokens when the
        # merged form has dictionary-backed candidates (newmm often splits a
        # misspelling into a known prefix + residue, e.g. อาจารย -> อาจาร + ย).
        i = 0
        while i < len(toks):
            token, start, _end = toks[i]
            if (
                _is_thai_token(token)
                and not _is_mask_fragment(token)
                and token not in self._known
                and not any(sp.start <= start < sp.end for sp in spans)
                and not any(cs <= start < ce for cs, ce in claimed)
            ):
                cluster = self._cluster_around(toks, i)
                if cluster is not None:
                    merged, cs, ce = cluster
                    candidates = [
                        c for c in spell(merged) if c != merged and c in self._known
                    ][:_MAX_SUGGESTIONS]
                    issues.append(self._unknown_issue(merged, cs, candidates))
                    claimed.append((cs, ce))
                    i = next(j for j, (_, s, _) in enumerate(toks) if s >= ce)
                    continue
            i += 1

        # Standalone pass: unknown Thai tokens of >= 2 code points.
        for token, start, _end in toks:
            if (
                len(token) < 2
                or _is_mask_fragment(token)
                or not _is_thai_token(token)
                or token in self._known
                or any(sp.start <= start < sp.end for sp in spans)
                or any(cs <= start < ce for cs, ce in claimed)
            ):
                continue
            candidates = [c for c in spell(token) if c != token][:_MAX_SUGGESTIONS]
            issues.append(self._unknown_issue(token, start, candidates))
        return issues

    def _unknown_issue(self, original: str, start: int, candidates: list[str]) -> Issue:
        return make_issue(
            rule_id="spelling.unknown_token",
            category="spelling",
            severity="low",
            start=start,
            original=original,
            suggestions=candidates,
            message="word not in dictionary; candidates may apply — human review required",
            requires_review=True,
            confidences=[None] * len(candidates),
            sources=[self.dictionary_name] * len(candidates),
        )

    def _cluster_around(
        self, toks: list[tuple[str, int, int]], index: int
    ) -> tuple[str, int, int] | None:
        """Try small adjacent merges around an unknown token.

        Returns (merged_text, start, end) for the first merge whose text is
        itself unknown but has dictionary-backed spell candidates, or None.
        Bounded: at most three windows of at most three tokens.
        """
        windows = []
        if index >= 1:
            windows.append((index - 1, index + 1))
        if index + 1 < len(toks):
            windows.append((index, index + 2))
        if index >= 1 and index + 1 < len(toks):
            windows.append((index - 1, index + 2))
        for lo, hi in windows:
            parts = toks[lo:hi]
            merged = "".join(p[0] for p in parts)
            if _is_mask_fragment(merged) or not _is_thai_token(merged) or len(merged) > 25:
                continue
            if merged in self._known:
                continue
            if merged == parts[index - lo][0]:
                continue  # degenerate single-token window
            if any(c in self._known for c in spell(merged)):
                return merged, parts[0][1], parts[-1][2]
        return None

    def _tokenize(self, view_text: str) -> list[tuple[str, int, int]]:
        tokens = self._tokenizer.word_tokenize(view_text)
        out: list[tuple[str, int, int]] = []
        pos = 0
        for token in tokens:
            if token:
                out.append((token, pos, pos + len(token)))
                pos += len(token)
        return out
