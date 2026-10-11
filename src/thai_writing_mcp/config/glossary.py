"""Layered glossary and terminology policy (T-005).

Layers merge in order global -> domain -> project -> request:

- ``protect`` terms are a union across layers. A protected term is never
  rewritten automatically; its canonical/suggest rules are suppressed unless
  the caller explicitly authorizes editing (FR-004).
- ``canonical`` / ``suggest`` maps merge per-key with the deeper layer winning.

The config is validated atomically: any malformed shape raises one typed
``EngineError(INVALID_INPUT)`` — never a partial load (NFR-006).
``dictionary_version`` is a deterministic content hash so evaluations are
reproducible (FR-015).
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from importlib import resources
from pathlib import Path
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, ValidationError, model_validator

from thai_writing_mcp.schemas.errors import INVALID_INPUT, EngineError

EXAMPLE_GLOSSARY_PATH = resources.files("thai_writing_mcp.config").joinpath(
    "data/glossary.default.json"
)


class Layer(BaseModel):
    model_config = ConfigDict(extra="forbid")
    protect: list[str] = Field(default_factory=list)
    canonical: dict[str, str] = Field(default_factory=dict)
    suggest: dict[str, str] = Field(default_factory=dict)


class _DomainLayer(Layer):
    pass


class _ConfigShape(BaseModel):
    """Pydantic shape used only to validate the raw dict atomically."""

    model_config = ConfigDict(extra="forbid")
    version: str
    global_: Layer | None = Field(default=None, alias="global")
    domain: dict[str, _DomainLayer] = Field(default_factory=dict)
    project: Layer | None = None

    @model_validator(mode="after")
    def _at_least_one_layer(self) -> _ConfigShape:
        if self.global_ is None and not self.domain and self.project is None:
            raise ValueError("glossary must define at least one layer (global, domain, project)")
        return self


@dataclass(frozen=True)
class GlossaryConfig:
    version: str
    global_layer: Layer
    domains: dict[str, Layer]
    project_layer: Layer | None

    @classmethod
    def from_dict(cls, payload: Any) -> GlossaryConfig:
        try:
            shape = _ConfigShape.model_validate(payload)
        except ValidationError as exc:
            details = [
                {
                    "field": ".".join(str(p) for p in err["loc"]),
                    "type": err["type"],
                    "message": err["msg"],
                }
                for err in exc.errors()
            ]
            raise EngineError(
                INVALID_INPUT,
                "glossary config failed validation",
                details={"errors": details},
            ) from None
        return cls(
            version=shape.version,
            global_layer=shape.global_ or Layer(),
            domains=dict(shape.domain),
            project_layer=shape.project,
        )

    @classmethod
    def from_json_file(cls, path: str) -> GlossaryConfig:
        try:
            payload = json.loads(Path(path).read_text())
        except (OSError, ValueError) as exc:
            raise EngineError(INVALID_INPUT, f"cannot read glossary file: {exc}") from None
        return cls.from_dict(payload)

    def to_dict(self) -> dict[str, Any]:
        out: dict[str, Any] = {"version": self.version}
        if self.global_layer.model_dump(exclude_defaults=True):
            out["global"] = self.global_layer.model_dump(exclude_defaults=True)
        if self.domains:
            out["domain"] = {
                k: v.model_dump(exclude_defaults=True) for k, v in self.domains.items()
            }
        if self.project_layer and self.project_layer.model_dump(exclude_defaults=True):
            out["project"] = self.project_layer.model_dump(exclude_defaults=True)
        return out

    def snapshot(self) -> str:
        """Deterministic JSON string for evidence logs and reproducibility."""
        return json.dumps(self.to_dict(), sort_keys=True, ensure_ascii=False)

    def layers_in_priority(self) -> list[Layer]:
        layers = [self.global_layer, *self.domains.values()]
        if self.project_layer:
            layers.append(self.project_layer)
        return layers


class GlossaryView:
    """The merged, request-scoped terminology policy that engines consume."""

    def __init__(self, config: GlossaryConfig, request_terms: list[str] | None = None) -> None:
        self.config = config
        self.request_terms = list(request_terms or [])

    def protect_terms(self) -> list[str]:
        terms: set[str] = set(self.request_terms)
        for layer in self.config.layers_in_priority():
            terms.update(layer.protect)
        return sorted(terms)

    def canonical_pairs(self, *, authorize_edit: bool = False) -> dict[str, str]:
        """Canonical rewrites; keys protected by any layer are suppressed
        unless ``authorize_edit`` is set (project protection beats automatic
        suggestions unless the request explicitly authorizes editing)."""
        merged: dict[str, str] = {}
        for layer in self.config.layers_in_priority():
            merged.update(layer.canonical)
        if not authorize_edit:
            protected = set(self.protect_terms())
            merged = {k: v for k, v in merged.items() if k not in protected}
        return dict(merged)

    def suggest_pairs(self) -> dict[str, str]:
        merged: dict[str, str] = {}
        for layer in self.config.layers_in_priority():
            merged.update(layer.suggest)
        protected = set(self.protect_terms())
        return {k: v for k, v in merged.items() if k not in protected}

    def dictionary_version(self) -> str:
        material = json.dumps(
            {
                "version": self.config.version,
                "protect": self.protect_terms(),
                "canonical": self.config_snapshot_canonical(),
                "suggest": self.suggest_pairs(),
                "request": sorted(self.request_terms),
            },
            sort_keys=True,
            ensure_ascii=False,
        )
        digest = hashlib.sha256(material.encode("utf-8")).hexdigest()[:12]
        return f"{self.config.version}+{digest}"

    def config_snapshot_canonical(self) -> dict[str, str]:
        merged: dict[str, str] = {}
        for layer in self.config.layers_in_priority():
            merged.update(layer.canonical)
        return merged


def default_config() -> GlossaryConfig:
    """The bundled example glossary (global + software domain + demo project)."""
    return GlossaryConfig.from_json_file(str(EXAMPLE_GLOSSARY_PATH))
