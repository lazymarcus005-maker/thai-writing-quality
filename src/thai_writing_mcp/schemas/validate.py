"""Request validation: the single gate every tool call passes first (T-002).

Bad or oversized requests get a stable typed error — never a traceback,
never a silent drop.
"""

from __future__ import annotations

from typing import Any, TypeVar

from pydantic import BaseModel, ValidationError

from thai_writing_mcp.schemas.errors import INVALID_INPUT, TOO_LARGE, EngineError
from thai_writing_mcp.schemas.models import MAX_INPUT_CODEPOINTS

T = TypeVar("T", bound=BaseModel)


def validate_request(
    model_cls: type[T], payload: Any, *, max_codepoints: int = MAX_INPUT_CODEPOINTS
) -> T:
    """Validate a raw request payload against a tool request model.

    Raises EngineError(INVALID_INPUT) for schema violations and
    EngineError(TOO_LARGE) when `text` exceeds `max_codepoints`.
    """
    if not isinstance(payload, dict):
        raise EngineError(
            INVALID_INPUT, "request must be a JSON object", details={"got": type(payload).__name__}
        )
    try:
        req = model_cls.model_validate(payload)
    except ValidationError as exc:
        raise _invalid_input(exc) from None

    text = getattr(req, "text", None)
    if isinstance(text, str):
        # Count Python code points, not bytes or UTF-16 units (NFR-007).
        if len(text) > max_codepoints:
            raise EngineError(
                TOO_LARGE,
                f"text exceeds the {max_codepoints} code point limit",
                retryable=False,
                details={"limit": max_codepoints, "actual": len(text)},
            )
        if len(text) == 0:
            raise EngineError(
                INVALID_INPUT,
                "text must be a non-empty string",
                details={"field": "text"},
            )
    return req


def _invalid_input(exc: ValidationError) -> EngineError:
    fields: list[dict[str, Any]] = []
    for err in exc.errors():
        fields.append(
            {
                "field": ".".join(str(p) for p in err["loc"]),
                "type": err["type"],
                "message": err["msg"],
            }
        )
    return EngineError(
        INVALID_INPUT,
        "request failed schema validation",
        details={"errors": fields},
    )
