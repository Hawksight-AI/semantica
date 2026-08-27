"""Helpers for reading entity identifiers consistently across the KG pipeline."""

from typing import Any


def get_entity_id(entity: Any) -> Any:
    """Return a truthy identifier from either supported entity ID field.

    The KG pipeline treats empty and otherwise falsy identifiers as missing.
    Prefer the canonical ``id`` field when it is populated, then fall back to
    the compatible ``entity_id`` alias.
    """
    if isinstance(entity, dict):
        return entity.get("id") or entity.get("entity_id") or None

    return getattr(entity, "id", None) or getattr(entity, "entity_id", None) or None
