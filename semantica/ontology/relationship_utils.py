"""Shared helpers for resolving ontology relationship endpoints."""

from typing import Any, Dict, List, Optional, Set


def build_entity_aliases(entities: List[Dict[str, Any]]) -> Dict[str, Set[str]]:
    """Build an alias-to-type index for relationship endpoints."""
    aliases: Dict[str, Set[str]] = {}
    for entity in entities:
        entity_type = entity.get("type") or entity.get("entity_type")
        if not entity_type:
            continue

        for key in ("id", "entity_id", "name", "text", "label"):
            if key not in entity or entity[key] is None or entity[key] == "":
                continue
            aliases.setdefault(str(entity[key]), set()).add(str(entity_type))

    return aliases


def get_relationship_endpoint(rel: Dict[str, Any], endpoint: str) -> Any:
    """Return an endpoint value from either ID or legacy relationship fields."""
    for key in (f"{endpoint}_id", endpoint):
        if key not in rel:
            continue

        value = rel[key]
        if value is None or value == "":
            continue
        if isinstance(value, dict):
            for alias_key in ("id", "entity_id", "name", "text", "label"):
                if alias_key not in value:
                    continue
                alias_value = value[alias_key]
                if alias_value is not None and alias_value != "":
                    return alias_value
            continue
        return value

    return None


def resolve_relationship_endpoint_type(
    rel: Dict[str, Any], endpoint: str, aliases: Dict[str, Set[str]]
) -> Optional[str]:
    """Resolve an endpoint type without treating missing fields as aliases."""
    explicit_type = rel.get(f"{endpoint}_type")
    if explicit_type and explicit_type != "Entity":
        return str(explicit_type)

    endpoint_value = get_relationship_endpoint(rel, endpoint)
    if endpoint_value is not None:
        candidates = aliases.get(str(endpoint_value), set())
        if len(candidates) == 1:
            return next(iter(candidates))

    return str(explicit_type) if explicit_type else None
