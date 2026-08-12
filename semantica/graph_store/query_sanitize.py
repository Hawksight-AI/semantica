"""
Shared identifier validation for Cypher/SPARQL query builders.

Node labels, relationship types, and property keys can't be bound as query
parameters the way values can, so any such identifier that reaches a query
string unvalidated is a direct injection point (GHSA-482h-hw99-h62p).
`age_store.py` already validates its labels/relationship types this way;
this module generalizes that pattern for reuse across the other graph
store backends without introducing an import cycle with `graph_store.py`
or `methods.py`.
"""

import re

from ..utils.exceptions import ValidationError

_IDENTIFIER_RE = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")


def sanitize_identifier(name: str, kind: str = "identifier") -> str:
    """Validate a Cypher/SPARQL label, relationship type, or property key.

    Only alphanumeric/underscore identifiers starting with a letter or
    underscore are allowed.
    """
    if not isinstance(name, str) or not _IDENTIFIER_RE.match(name):
        raise ValidationError(
            f"Invalid {kind}: {name!r}. Must start with a letter or "
            "underscore and contain only alphanumeric characters and "
            "underscores."
        )
    return name
