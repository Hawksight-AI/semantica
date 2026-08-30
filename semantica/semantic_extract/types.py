"""
Shared semantic extraction data types.

These lightweight dataclasses live outside the extractor implementations so
method dispatchers and extractors can share result models without import cycles.
"""

from dataclasses import dataclass, field
from typing import Any, Dict, Optional


@dataclass
class Entity:
    """Entity representation.

    ``confidence`` is ``None`` when no confidence measurement is available
    (e.g. the extraction backend does not expose per-entity probabilities).
    ``None`` is distinct from any numeric score: it means "unknown", not
    "certain". Producers should record where a score came from in
    ``metadata["confidence_source"]`` (e.g. ``"model"``, ``"heuristic"``,
    ``"unavailable"``).
    """

    text: str
    label: str
    start_char: int
    end_char: int
    confidence: Optional[float] = None
    metadata: Dict[str, Any] = field(default_factory=dict)


def meets_confidence_threshold(
    confidence: Optional[float], threshold: float
) -> bool:
    """Return True if a confidence value passes a minimum threshold.

    Unknown confidence (``None``) passes: absence of a measurement is not
    evidence of low confidence, and entities must not be silently dropped
    just because their backend exposes no probabilities.
    """
    return confidence is None or confidence >= threshold


@dataclass
class Relation:
    """Relation representation."""

    subject: Entity
    predicate: str
    object: Entity
    confidence: float = 1.0
    context: str = ""
    metadata: Dict[str, Any] = field(default_factory=dict)


@dataclass
class Triplet:
    """RDF triplet representation."""

    subject: str
    predicate: str
    object: str
    confidence: float = 1.0
    metadata: Dict[str, Any] = field(default_factory=dict)

    def get(self, key: str, default: Any = None) -> Any:
        """Get attribute value like a dictionary."""
        return getattr(self, key, default)

    def __getitem__(self, key: str) -> Any:
        """Get item like a dictionary."""
        return getattr(self, key)
