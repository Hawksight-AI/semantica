"""The vocabulary Semantica's exporters emit terms from.

Every RDF export mints terms in ``https://semantica.dev/ns#``: ``sem:text``,
``sem:confidence``, the default ``sem:Entity`` type, and the rest. Until this
file existed, nothing declared what those terms meant, so a consumer receiving
an export could not tell ``sem:text`` from a typo of it, and no closed-world
check could be run against them at all (issue #1107).

The document ships inside the package so it can be loaded without a network
round trip, and is the same file intended to be served at the namespace IRI.

    >>> from semantica.ontology.vocabulary import vocabulary_turtle
    >>> ttl = vocabulary_turtle()
"""

from __future__ import annotations

from pathlib import Path

VOCABULARY_FILENAME = "semantica-ns.ttl"

#: The namespace the vocabulary declares terms in.
NAMESPACE = "https://semantica.dev/ns#"

__all__ = ["NAMESPACE", "VOCABULARY_FILENAME", "vocabulary_path", "vocabulary_turtle"]


def vocabulary_path() -> Path:
    """Filesystem path to the vocabulary document."""
    return Path(__file__).parent / VOCABULARY_FILENAME


def vocabulary_turtle() -> str:
    """The vocabulary document as Turtle."""
    return vocabulary_path().read_text(encoding="utf-8")
