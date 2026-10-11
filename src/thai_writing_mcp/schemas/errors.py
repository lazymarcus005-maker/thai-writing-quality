"""Stable, typed engine errors (NFR-006).

Every failure surfaces as `{code, message, retryable, details}` — never a
traceback to the client, never silently dropped.
"""

from __future__ import annotations

from typing import Any

INVALID_INPUT = "INVALID_INPUT"
TOO_LARGE = "TOO_LARGE"
RULE_FAILURE = "RULE_FAILURE"
PROTECTED_CONTENT_VIOLATION = "PROTECTED_CONTENT_VIOLATION"
LLM_UNAVAILABLE = "LLM_UNAVAILABLE"

ALL_CODES = (INVALID_INPUT, TOO_LARGE, RULE_FAILURE, PROTECTED_CONTENT_VIOLATION, LLM_UNAVAILABLE)


class EngineError(Exception):
    """A deterministic, machine-readable failure with a stable code."""

    def __init__(
        self,
        code: str,
        message: str,
        *,
        retryable: bool = False,
        details: dict[str, Any] | None = None,
    ) -> None:
        if code not in ALL_CODES:
            raise ValueError(f"unknown error code: {code}")
        super().__init__(message)
        self.code = code
        self.message = message
        self.retryable = retryable
        self.details = details or {}

    def to_dict(self) -> dict[str, Any]:
        return {
            "code": self.code,
            "message": self.message,
            "retryable": self.retryable,
            "details": self.details,
        }

    def __str__(self) -> str:  # pragma: no cover - cosmetic
        return f"{self.code}: {self.message}"


def error_dict(err: EngineError) -> dict[str, Any]:
    """Public helper so callers never depend on EngineError internals."""
    return err.to_dict()
