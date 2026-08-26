"""
Shared SPARQL literal-escaping and URI-validation primitives.

This module centralizes string-escaping, datatype-IRI resolution, and URI
allowlist validation logic that was previously duplicated (or would have
been duplicated) between ``BlazegraphStore`` and the CONSTRUCT template
renderer. ``BlazegraphStore._escape_literal`` and
``BlazegraphStore._resolve_datatype_iri`` delegate to ``escape_literal`` and
``resolve_datatype_iri`` here without any change in behavior; ``validate_uri``
is new and is used by ``render_construct_template`` for both ``"uri"``-typed
parameters and ``target_graph`` values.

Author: Semantica Contributors
License: MIT
"""

import re
from typing import FrozenSet
from urllib.parse import urlparse

from ..utils.exceptions import ValidationError

# Allowed URI schemes for validate_uri's allowlist (Requirement 3.2/4.4).
_ALLOWED_URI_SCHEMES: FrozenSet[str] = frozenset({"http", "https", "urn"})

# Known prefix expansions for XSD and common RDF vocabularies.
# Identical table to BlazegraphStore._KNOWN_PREFIXES.
KNOWN_PREFIXES: dict = {
    "xsd": "http://www.w3.org/2001/XMLSchema#",
    "rdf": "http://www.w3.org/1999/02/22-rdf-syntax-ns#",
    "rdfs": "http://www.w3.org/2000/01/rdf-schema#",
    "owl": "http://www.w3.org/2002/07/owl#",
    "skos": "http://www.w3.org/2004/02/skos/core#",
}

# RFC 5646 language tag: primary subtag optionally followed by '-' + subtags.
# Identical pattern to BlazegraphStore._LANG_TAG_RE.
LANG_TAG_RE = re.compile(r"^[a-zA-Z]{1,8}(-[a-zA-Z0-9]{1,8})*$")

# Disallowed-character check shared by validate_uri and resolve_datatype_iri,
# identical to the character class used throughout BlazegraphStore.
_DISALLOWED_URI_CHARS_RE = re.compile(r"[\s<>\"{}|\\^`]")

# Matches CONSTRUCT only as the actual SPARQL query-form keyword: anchored
# from the start of the string, optionally preceded by PREFIX/BASE
# declarations, then requires CONSTRUCT as the first non-whitespace keyword.
# This prevents false-positives from SELECT/ASK queries that merely contain
# the word "CONSTRUCT" inside a string literal or comment (e.g. a literal
# value of '"please CONSTRUCT this"' or a comment line).
#
# Shared by BlazegraphStore and RDF4JStore so the detection logic has one
# canonical implementation rather than being duplicated per-backend.
#
# The comment alternative must consume the whole comment up to a line
# terminator. Written as a bare `\#[^\n]*`, the trailing `*` backtracks: for
# "# CONSTRUCT ...\nSELECT ...", the engine gives back everything after the
# '#', letting the CONSTRUCT *inside the comment* satisfy the query-form
# keyword and misreporting a SELECT as a CONSTRUCT. Requiring a terminator
# ([\n\r], or end of input for a trailing comment) makes that backtracking
# impossible: if the character class gives a character back, the next
# character is by definition not a terminator, so the group cannot match.
# Both LF and CR are treated as terminators because the SPARQL grammar ends
# a comment at either.
CONSTRUCT_QUERY_RE = re.compile(
    r"""
    \A                       # anchor to start of string
    (?:                      # skip zero or more of:
        \s+                  # whitespace
      | \#[^\n\r]*(?:[\n\r]|\Z)  # comment, to end of line or end of input
      | PREFIX\s+[\w\-]*:\s*<[^>]*>  # PREFIX declaration
      | BASE\s+<[^>]*>       # BASE declaration
    )*
    \s*                      # any remaining whitespace before the query form
    CONSTRUCT                # the actual query-form keyword
    \b                       # must be followed by a non-word character
    """,
    re.IGNORECASE | re.VERBOSE,
)


def escape_literal(value: str) -> str:
    """
    Escape a string literal for safe inclusion inside SPARQL double quotes.

    This is a byte-for-byte copy of BlazegraphStore._escape_literal's
    transformation:
        \\ -> \\\\ , " -> \\" , \\n -> \\n , \\r -> \\r , \\t -> \\t

    Args:
        value: Raw literal value (converted via str() first, matching the
            original method's behavior of accepting non-str inputs).

    Returns:
        Escaped string safe to place inside a SPARQL/Turtle double-quoted
        literal.
    """
    return (
        str(value)
        .replace("\\", "\\\\")
        .replace("\"", "\\\"")
        .replace("\n", "\\n")
        .replace("\r", "\\r")
        .replace("\t", "\\t")
    )


def resolve_datatype_iri(datatype: str) -> str:
    """
    Expand a datatype string to a validated SPARQL IRI token.

    This is a byte-for-byte copy of BlazegraphStore._resolve_datatype_iri's
    logic and exception behavior (raises ValueError, not ValidationError, to
    match the original method's existing contract).

    Accepts:
    - Already-wrapped IRIs: ``<http://...>``
    - Full IRIs:            ``http://...`` / ``https://...`` / ``urn:...``
    - Known prefixed names: ``xsd:integer``, ``rdf:langString``, etc.

    Raises:
        ValueError: for anything else, or for malformed/unsafe IRIs.

    Returns:
        An angle-bracketed IRI token, e.g. ``<http://www.w3.org/2001/XMLSchema#integer>``.
    """
    datatype = str(datatype)

    # Already angle-bracketed — validate the inner IRI contains no whitespace
    if datatype.startswith("<") and datatype.endswith(">"):
        inner = datatype[1:-1]
        if not inner or _DISALLOWED_URI_CHARS_RE.search(inner):
            raise ValueError(f"Invalid datatype IRI: {datatype!r}")
        return datatype

    # Full absolute IRI without brackets
    parsed = urlparse(datatype)
    if parsed.scheme in {"http", "https", "urn"} and not _DISALLOWED_URI_CHARS_RE.search(datatype):
        return f"<{datatype}>"

    # Prefixed form — expand known prefixes only
    if ":" in datatype:
        prefix, local = datatype.split(":", 1)
        if prefix in KNOWN_PREFIXES and re.match(r"^[A-Za-z0-9_\-\.]+$", local):
            return f"<{KNOWN_PREFIXES[prefix]}{local}>"

    raise ValueError(
        f"Unsupported datatype {datatype!r}: use a full IRI (http/https/urn), "
        f"an angle-bracketed IRI, or a known prefix (xsd/rdf/rdfs/owl/skos)."
    )


def validate_uri(
    value: str,
    *,
    allowed_schemes: FrozenSet[str] = _ALLOWED_URI_SCHEMES,
) -> str:
    """
    Validate that `value` is a safe absolute IRI using urllib.parse, and
    return it unchanged (no bracket-wrapping — callers wrap with <...> at
    render time).

    Uses urllib.parse.urlparse(value):
      - scheme must be in allowed_schemes (default {"http", "https", "urn"})
      - the value must not contain whitespace or any of
        < > " { } | \\ ^ ` characters (same disallowed-character set used by
        resolve_datatype_iri / BlazegraphStore's existing IRI checks)

    Args:
        value: Candidate URI/IRI string.
        allowed_schemes: Set of permitted URI schemes.

    Returns:
        The validated `value`, unchanged.

    Raises:
        ValidationError: if value is empty, not a string, has a scheme not in
            allowed_schemes, or contains a disallowed character.
    """
    if not isinstance(value, str) or not value:
        raise ValidationError(f"Invalid URI: value must be a non-empty string, got {value!r}")

    if _DISALLOWED_URI_CHARS_RE.search(value):
        raise ValidationError(
            f"Invalid URI {value!r}: contains disallowed character(s) "
            f"(whitespace or one of < > \" {{ }} | \\ ^ `)"
        )

    parsed = urlparse(value)
    if parsed.scheme not in allowed_schemes:
        raise ValidationError(
            f"Invalid URI {value!r}: scheme {parsed.scheme!r} is not allowed "
            f"(allowed: {sorted(allowed_schemes)})"
        )

    return value
