"""
RDF Export Module

This module provides comprehensive RDF (Resource Description Framework) export
capabilities for the Semantica framework, supporting multiple RDF serialization
formats and validation.

Key Features:
    - Multiple RDF format support (Turtle, RDF/XML, JSON-LD, N-Triples, N3)
    - RDF serialization and export
    - Namespace management and conflict resolution
    - RDF validation and quality checking
    - Batch RDF export processing
    - Knowledge graph to RDF conversion

Main Classes:
    - RDFExporter: Main RDF export class
    - RDFSerializer: RDF serialization engine
    - RDFValidator: RDF validation engine
    - NamespaceManager: RDF namespace management

Example Usage:
    >>> from semantica.export import RDFExporter
    >>> exporter = RDFExporter()
    >>> exporter.export(data, "output.ttl", format="turtle")
    >>> validation = exporter.validate_rdf(data)

Author: Semantica Contributors
License: MIT
"""

import re
from pathlib import Path
from decimal import Decimal, InvalidOperation
from html import escape as xml_escape
from typing import Any, Dict, List, Optional, Set, Union
from urllib.parse import quote, urlsplit

from ..utils.exceptions import ProcessingError, ValidationError
from ..utils.helpers import ensure_directory, hash_data
from ..utils.logging import get_logger
from ..utils.progress_tracker import get_progress_tracker


SEMANTICA_NS = "https://semantica.dev/ns#"

#: Written when an entity carries no type of its own. A full IRI rather than the
#: prefixed form, because the Turtle serializer writes it inside angle brackets,
#: where `semantica:Entity` would be read as an IRI in the scheme `semantica`
#: rather than as the prefix expansion (issue #1101).
DEFAULT_ENTITY_TYPE = f"{SEMANTICA_NS}Entity"

#: Written when a relationship carries no type of its own. Same reasoning.
DEFAULT_RELATION_TYPE = f"{SEMANTICA_NS}related_to"

#: The one datatype every serializer writes confidence in.
#:
#: The four paths used to disagree: Turtle wrote the value bare, which the
#: Turtle grammar reads as xsd:decimal, N-Triples typed it xsd:float, RDF/XML
#: emitted a plain literal with no datatype, and JSON-LD emitted a native
#: number, which becomes xsd:double. Those are four distinct RDF terms for one
#: value (issue #1100).
#:
#: xsd:decimal is the choice because it is what the Turtle path already
#: produced, so the most used output is unchanged, and because it is exact:
#: xsd:float is 32 bit binary, and cannot represent 0.9 or 0.95 at all.
CONFIDENCE_DATATYPE = "http://www.w3.org/2001/XMLSchema#decimal"

#: Largest power of ten a confidence may carry. xsd:decimal has no exponent
#: notation, so a value has to be written out in full, and a compact literal
#: such as "1e100000000" would expand to a hundred million digits.
MAX_CONFIDENCE_EXPONENT = 100


def normalize_confidence(value: Any) -> Optional[str]:
    """
    Return the canonical xsd:decimal lexical form of a confidence value.

    Returns None when the value cannot be a decimal, so callers omit the triple
    rather than writing something the vocabulary contradicts. The Turtle path
    used to interpolate the raw value, so a confidence of "high" produced
    `semantica:confidence high .` and made the whole document unparseable
    (issue #1102).

    Booleans are rejected. `bool` is a subclass of `int` in Python, so True
    would otherwise silently become a confidence of 1.
    """
    if value is None or isinstance(value, bool):
        return None
    if isinstance(value, str):
        value = value.strip()
        if not value:
            return None
    if not isinstance(value, (int, float, str, Decimal)):
        return None

    try:
        decimal_value = Decimal(str(value))
    except (InvalidOperation, ValueError, TypeError):
        return None

    # NaN and the infinities are Decimal values with no xsd:decimal form.
    if not decimal_value.is_finite():
        return None

    # xsd:decimal has no exponent notation, so writing one means expanding it.
    # "1e100000000" is eleven characters that expand to a hundred million, and
    # the export path continues past validation errors, so a single malformed
    # field could exhaust memory. Nothing near this magnitude is a confidence.
    if (
        not -MAX_CONFIDENCE_EXPONENT
        <= decimal_value.adjusted()
        <= MAX_CONFIDENCE_EXPONENT
    ):
        return None

    # `str(Decimal("0.00001"))` gives "0.00001", but a float that has already
    # been through repr can arrive as "1e-05", which xsd:decimal does not allow.
    formatted = format(decimal_value, "f")
    if "." in formatted:
        formatted = formatted.rstrip("0").rstrip(".") or "0"

    # Decimal keeps the sign of zero, so 0.0 and -0.0 would serialise as two
    # distinct RDF terms and defeat the point of a canonical form.
    if formatted.lstrip("-").strip("0.") == "":
        formatted = "0"
    return formatted


def mint_entity_iri(text: str) -> str:
    """Mint a stable IRI for an entity that arrived without an id.

    Python's builtin ``hash()`` is randomised per process (PYTHONHASHSEED), so
    minting from it gave the same entity a different IRI on every run: exports
    could not be diffed, deduplicated against an earlier load, or joined to a
    provenance record written by an earlier process. SHA-256 is stable across
    runs and machines, which is what an identifier has to be.
    """
    digest = hash_data(str(text))[:16]
    return f"{SEMANTICA_NS}entity_{digest}"


def mint_relationship_iri(index: int, source: Any, target: Any) -> str:
    """Mint a stable IRI for a relationship that arrived without an id."""
    digest = hash_data(f"{source}\x00{target}")[:16]
    return f"{SEMANTICA_NS}rel_{index}_{digest}"


#: The metadata keys Semantica itself produces, and the terms they are written
#: as. GraphBuilder.build_graph writes the first five, create_snapshot writes
#: snapshot_time, and load_from_neo4j writes source / uri / database. These are
#: Semantica's own vocabulary, so they are minted in the declared namespace and
#: declared in semantica-ns.ttl.
#:
#: A key the caller supplied is a different matter. Which namespace an
#: arbitrary metadata key belongs in is issue #1146, and until that is settled
#: the exporter refuses to guess: it warns and skips, and a caller who already
#: knows the answer passes ``metadata_terms``.
#:
#: The map is key -> term rather than key -> namespace because two of the keys
#: cannot keep their own name. ``source`` on a graph loaded from Neo4j is the
#: system it came from, while sem:source is already the ObjectProperty holding
#: the subject of a reified relationship; reusing it would put a string where
#: an entity belongs.
DEFAULT_METADATA_TERMS: Dict[str, str] = {
    "num_entities": f"{SEMANTICA_NS}numEntities",
    "num_relationships": f"{SEMANTICA_NS}numRelationships",
    "temporal_enabled": f"{SEMANTICA_NS}temporalEnabled",
    "entity_resolution_applied": f"{SEMANTICA_NS}entityResolutionApplied",
    "timestamp": f"{SEMANTICA_NS}builtAt",
    "snapshot_time": f"{SEMANTICA_NS}snapshotAt",
    "source": f"{SEMANTICA_NS}sourceSystem",
    "uri": f"{SEMANTICA_NS}sourceUri",
    "database": f"{SEMANTICA_NS}sourceDatabase",
}

#: Terms whose value is a node rather than a string. Everything else stays a
#: literal: a metadata value that merely looks like a URL is not thereby a
#: reference to one.
IRI_VALUED_METADATA_TERMS: Set[str] = {f"{SEMANTICA_NS}sourceUri"}

_XSD_NS = "http://www.w3.org/2001/XMLSchema#"


def _escape_literal(value: str) -> str:
    """Escape a string for a Turtle or N-Triples quoted literal."""
    return (
        value.replace("\\", "\\\\")
        .replace('"', '\\"')
        .replace("\n", "\\n")
        .replace("\r", "\\r")
        .replace("\t", "\\t")
    )


def _escape_temporal_literal(value: Any) -> str:
    """Escape a temporal bound for a Turtle ``dateTimeStamp`` literal.

    Bounds are normally strings, but callers may hand us a ``datetime`` or
    ``None``. ``_escape_literal`` is str-only, so stringify non-str values
    first instead of calling ``.replace()`` on them; ``None`` yields an empty
    bound rather than crashing. Datetimes must use ISO 8601 so the
    ``xsd:dateTimeStamp`` ``T`` separator is preserved — ``str()`` yields a
    space ("00:00:00+00:00"), which is a lexically invalid timestamp.
    """
    if value is None:
        return ""
    if isinstance(value, str):
        return _escape_literal(value)
    if hasattr(value, "isoformat"):
        return value.isoformat()
    return str(value)


#: Turtle/N-Triples IRIREF grammar excludes these unescaped between `<` and
#: `>`: control characters, space, and <>"{}|^`\. An IRI-valued metadata
#: value (currently only sem:sourceUri, from the caller-controlled "uri"
#: metadata key) is written as `<{value}>` with no other quoting, so a value
#: containing one of these characters — a ">" followed by a full triple, for
#: instance — closes the IRIREF early and lets the rest of the string be
#: parsed as further RDF statements. This is the same shape of defect the
#: entity/relationship IRIs were hardened against; that hardening resolves
#: prefixes as well, which a metadata value never needs, so this stays a
#: narrower, dedicated guard rather than reusing _as_turtle_iri.
_IRI_REF_UNSAFE_RE = re.compile(r'[\x00-\x20<>"{}|^`\\]')


def _safe_iri_ref(value: str) -> str:
    """Percent-encode the characters an IRIREF may not contain unescaped."""
    return _IRI_REF_UNSAFE_RE.sub(lambda m: quote(m.group(0), safe=""), value)


def _escape_xml(value: str) -> str:
    """Escape a string for either XML element text or an attribute value.

    The quotes matter. This helper feeds `rdf:about`, `rdf:resource` and
    `xmlns:` attribute values, which are delimited by double quotes, so a value
    carrying one would close the attribute early and produce a document that
    does not parse. Escaping them in element text as well is harmless and
    means one helper cannot be used in the wrong place.
    """
    return (
        value.replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
        .replace('"', "&quot;")
        .replace("'", "&apos;")
    )


def _is_ncname(value: str) -> bool:
    """Whether a string can be an XML NCName, which is what RDF/XML requires.

    Checked over the ASCII range rather than the full XML production: the
    grammar also admits combining characters and extenders, so this is
    deliberately conservative. It refuses names it could have accepted, and it
    never accepts one that would produce a document a parser rejects. The
    earlier check tested only that the first character was not a digit, which
    let through every other way a local name can fail to be a name.
    """
    if not value:
        return False
    if not (value[0].isascii() and (value[0].isalpha() or value[0] == "_")):
        return False
    return all(c.isascii() and (c.isalnum() or c in "._-") for c in value[1:])


def _split_iri(iri: str) -> Optional[tuple]:
    """Split an IRI into (namespace, local name) for RDF/XML's QName syntax.

    Returns None when no split yields a usable local name. RDF/XML is the only
    serialization here that cannot write an arbitrary predicate IRI, so this is
    the one place a term can be unrepresentable, and the caller reports it
    rather than dropping it quietly.
    """
    for sep in ("#", "/"):
        index = iri.rfind(sep)
        if index != -1 and index + 1 < len(iri):
            local = iri[index + 1 :]
            if _is_ncname(local):
                return iri[: index + 1], local
    return None


def _metadata_statements(
    metadata: Any,
    terms: Dict[str, str],
    logger: Any,
) -> List[tuple]:
    """Resolve a metadata mapping to a list of (term IRI, value) pairs.

    A key with no term is skipped and reported. Silence is the defect this
    fixes, so an unmapped key must be louder than a mapped one, not quieter.
    """
    if not isinstance(metadata, dict):
        return []

    statements: List[tuple] = []
    for key, value in metadata.items():
        term = terms.get(key)
        if term is None:
            logger.warning(
                "Metadata key %r has no term and was not exported. Which "
                "namespace a caller-supplied key belongs in is issue #1146; "
                "pass metadata_terms={%r: '<iri>'} to export it now.",
                key,
                key,
            )
            continue
        if value is None:
            continue
        if isinstance(value, (dict, list, tuple, set)):
            logger.warning(
                "Metadata key %r holds a %s, which has no modelled RDF shape "
                "yet, and was not exported.",
                key,
                type(value).__name__,
            )
            continue
        statements.append((term, value))
    return statements


def _resolve_metadata_terms(overrides: Optional[Dict[str, str]]) -> Dict[str, str]:
    if not overrides:
        return DEFAULT_METADATA_TERMS
    return {**DEFAULT_METADATA_TERMS, **overrides}


def _typed_literal_parts(term: str, value: Any) -> tuple:
    """Return (kind, lexical, datatype) for one metadata value.

    kind is "iri" or "literal". The lexical form and datatype are chosen once,
    here, so that the four serializers cannot disagree about them the way they
    disagreed about confidence in #1100.
    """
    if term in IRI_VALUED_METADATA_TERMS and isinstance(value, str):
        return "iri", value, None
    if isinstance(value, bool):
        return "literal", "true" if value else "false", f"{_XSD_NS}boolean"
    if isinstance(value, int):
        return "literal", str(value), f"{_XSD_NS}integer"
    if isinstance(value, float):
        # xsd:double, not xsd:decimal. `repr(1e-05)` is "1e-05" and
        # `repr(float("nan"))` is "nan", and xsd:decimal admits neither the
        # exponent form nor the special values, so typing a float as decimal
        # produced lexicals a strict parser rejects. A Python float is an IEEE
        # 754 double; xsd:double has legal lexicals for all of them, and it is
        # also the honest claim, since nothing that arrived as a float was ever
        # exact. `normalize_confidence` keeps xsd:decimal for confidence
        # deliberately: that is a bounded score where exactness is meaningful
        # and NaN is not a confidence at all.
        if value != value:
            lexical = "NaN"
        elif value == float("inf"):
            lexical = "INF"
        elif value == float("-inf"):
            lexical = "-INF"
        else:
            lexical = repr(value)
        return "literal", lexical, f"{_XSD_NS}double"
    return "literal", str(value), None


def _turtle_object(term: str, value: Any) -> str:
    kind, lexical, datatype = _typed_literal_parts(term, value)
    if kind == "iri":
        return f"<{_safe_iri_ref(lexical)}>"
    if datatype is None:
        return f'"{_escape_literal(lexical)}"'
    return f'"{lexical}"^^<{datatype}>'


def _turtle_metadata_clauses(statements: List[tuple]) -> List[str]:
    return [f"<{term}> {_turtle_object(term, value)}" for term, value in statements]


def _ntriples_metadata_lines(subject: str, statements: List[tuple]) -> List[str]:
    return [
        f"<{subject}> <{term}> {_turtle_object(term, value)} ."
        for term, value in statements
    ]


def _rdfxml_metadata_lines(
    statements: List[tuple], indent: str, logger: Any = None
) -> List[str]:
    """RDF/XML needs a QName, so an unprefixed term declares its own prefix.

    A term with no QName form has no RDF/XML representation at all, and this is
    the only serialization with that restriction. Skipping it quietly would
    reintroduce, in one format, exactly the silent metadata loss this module
    was changed to stop, so it is reported and the other three formats still
    carry the statement in full.
    """
    lines: List[str] = []
    for position, (term, value) in enumerate(statements):
        split = _split_iri(term)
        if split is None:
            if logger is not None:
                logger.warning(
                    "Term %r has no QName form, so it cannot be written in "
                    "RDF/XML and was omitted from that serialization only. "
                    "Turtle, N-Triples and JSON-LD carry it in full.",
                    term,
                )
            continue
        namespace, local = split
        kind, lexical, datatype = _typed_literal_parts(term, value)
        prefix = f"md{position}"
        opening = f'{indent}<{prefix}:{local} xmlns:{prefix}="{_escape_xml(namespace)}"'
        if kind == "iri":
            lines.append(f'{opening} rdf:resource="{_escape_xml(lexical)}"/>')
            continue
        if datatype is not None:
            opening += f' rdf:datatype="{_escape_xml(datatype)}"'
        lines.append(f"{opening}>{_escape_xml(lexical)}</{prefix}:{local}>")
    return lines


def _jsonld_metadata_entries(statements: List[tuple]) -> Dict[str, Any]:
    """Absolute IRIs as keys, and explicit @value/@type rather than JSON's own
    types: JSON's number is xsd:double, which would make the JSON-LD export
    disagree with the other three about the datatype of an integer."""
    entries: Dict[str, Any] = {}
    for term, value in statements:
        kind, lexical, datatype = _typed_literal_parts(term, value)
        if kind == "iri":
            entries[term] = {"@id": lexical}
        elif datatype is None:
            entries[term] = lexical
        else:
            entries[term] = {"@value": lexical, "@type": datatype}
    return entries


class NamespaceManager:
    """
    RDF namespace management engine.

    This class manages RDF namespaces, handles namespace declarations, resolves
    conflicts, and generates namespace declarations for various RDF formats.

    Features:
        - Namespace registration and management
        - Namespace declaration generation
        - Namespace conflict resolution
        - Format-specific namespace formatting

    Example Usage:
        >>> manager = NamespaceManager()
        >>> declarations = manager.generate_namespace_declarations(
        ...     {"ex": "http://example.org/ns#"},
        ...     format="turtle"
        ... )
    """

    def __init__(self, **config):
        """
        Initialize namespace manager.

        Sets up the namespace manager with standard RDF namespaces and
        configuration options.

        Args:
            **config: Configuration options (currently unused)
        """
        self.logger = get_logger("namespace_manager")

        # Standard RDF namespaces. "semantica" reuses ProvenanceManager's
        # DEFAULT_BASE_URI (issue #825, Part B Tier 3 — exporter
        # interlinking) so KG-exported and PROV-exported URIs for the same
        # entity_id co-resolve to the same namespace instead of two
        # independently-hardcoded placeholder domains.
        from ..provenance.manager import DEFAULT_BASE_URI

        self.namespaces: Dict[str, str] = {
            "rdf": "http://www.w3.org/1999/02/22-rdf-syntax-ns#",
            "rdfs": "http://www.w3.org/2000/01/rdf-schema#",
            "owl": "http://www.w3.org/2002/07/owl#",
            "xsd": "http://www.w3.org/2001/XMLSchema#",
            "semantica": DEFAULT_BASE_URI,
        }
        self.config = config or {}

        self.logger.debug(
            f"Namespace manager initialized with {len(self.namespaces)} namespace(s)"
        )

    def extract_namespaces(self, rdf_data: Dict[str, Any]) -> Dict[str, str]:
        """
        Extract namespaces from RDF data.

        This method identifies and extracts namespace declarations from RDF data,
        particularly from JSON-LD @context or other namespace declarations.

        Args:
            rdf_data: RDF data dictionary that may contain namespace information

        Returns:
            Dictionary mapping namespace prefixes to URIs

        Example:
            >>> rdf_data = {
            ...     "@context": {
            ...         "ex": "http://example.org/ns#",
            ...         "rdf": "http://www.w3.org/1999/02/22-rdf-syntax-ns#"
            ...     }
            ... }
            >>> namespaces = manager.extract_namespaces(rdf_data)
        """
        extracted = {}

        # Check for @context in JSON-LD
        if "@context" in rdf_data:
            context = rdf_data["@context"]
            if isinstance(context, dict):
                for prefix, uri in context.items():
                    # Skip JSON-LD keywords (starting with @)
                    if not prefix.startswith("@"):
                        extracted[prefix] = uri
                        self.logger.debug(f"Extracted namespace: {prefix} -> {uri}")

        return extracted

    def generate_namespace_declarations(
        self, namespaces: Dict[str, str], format: str = "turtle"
    ) -> str:
        """
        Generate namespace declarations for specified RDF format.

        This method creates namespace declarations in the appropriate syntax
        for the specified RDF format.

        Supported Formats:
            - "turtle": Turtle format (@prefix prefix: <uri> .)
            - "rdfxml": RDF/XML format (xmlns:prefix="uri")
            - "jsonld": JSON-LD format (returns empty, handled via @context)

        Args:
            namespaces: Dictionary mapping namespace prefixes to URIs
            format: RDF format - 'turtle', 'rdfxml', or 'jsonld' (default: 'turtle')

        Returns:
            String containing namespace declarations in format-specific syntax

        Example:
            >>> namespaces = {"ex": "http://example.org/ns#"}
            >>> decls = manager.generate_namespace_declarations(namespaces, "turtle")
            >>> # Returns: "@prefix ex: <http://example.org/ns#> ."
        """
        declarations = []

        if format == "turtle":
            # Turtle format: @prefix prefix: <uri> .
            for prefix, uri in namespaces.items():
                declarations.append(f"@prefix {prefix}: <{uri}> .")
        elif format == "rdfxml":
            # RDF/XML format: xmlns:prefix="uri"
            for prefix, uri in namespaces.items():
                declarations.append(f'xmlns:{prefix}="{uri}"')
        elif format == "jsonld":
            # JSON-LD uses @context, not separate declarations
            return ""  # Handled separately in JSON-LD serialization

        return "\n".join(declarations)

    def resolve_namespace_conflicts(self, namespaces: Dict[str, str]) -> Dict[str, str]:
        """
        Resolve namespace conflicts.

        This method identifies namespace conflicts where multiple prefixes map
        to the same URI, or the same prefix maps to multiple URIs. Logs warnings
        for conflicts but allows them (first prefix wins).

        Args:
            namespaces: Dictionary mapping namespace prefixes to URIs

        Returns:
            Dictionary with resolved namespaces (conflicts logged but preserved)

        Example:
            >>> namespaces = {
            ...     "ex": "http://example.org/ns#",
            ...     "ex2": "http://example.org/ns#"  # Same URI, different prefix
            ... }
            >>> resolved = manager.resolve_namespace_conflicts(namespaces)
            >>> # Logs warning about conflict, returns both mappings
        """
        resolved = {}
        seen_uris = {}  # Track which prefix was first for each URI

        for prefix, uri in namespaces.items():
            if uri in seen_uris:
                # Conflict: same URI, different prefix
                existing_prefix = seen_uris[uri]
                resolved[prefix] = uri
                if prefix != existing_prefix:
                    self.logger.warning(
                        f"Namespace conflict: prefixes '{prefix}' and "
                        f"'{existing_prefix}' both map to URI '{uri}'. "
                        "Using first prefix."
                    )
            else:
                resolved[prefix] = uri
                seen_uris[uri] = prefix

        return resolved


class RDFSerializer:
    """
    RDF serialization engine.

    This class provides RDF serialization to various formats including Turtle,
    RDF/XML, and JSON-LD. Handles format-specific syntax and encoding.

    Features:
        - Multiple RDF format serialization
        - Format-specific syntax handling
        - Namespace management integration
        - Entity and relationship conversion

    Example Usage:
        >>> serializer = RDFSerializer()
        >>> turtle = serializer.serialize_to_turtle(rdf_data)
        >>> jsonld = serializer.serialize_to_jsonld(rdf_data)
    """

    def __init__(self, **config):
        """
        Initialize RDF serializer.

        Sets up the serializer with namespace management and configuration.

        Args:
            **config: Configuration options (currently unused)
        """
        self.logger = get_logger("rdf_serializer")
        self.config = config or {}
        self.namespace_manager = NamespaceManager()

        self.logger.debug("RDF serializer initialized")

    @staticmethod
    def _local_name_from_id(identifier: str) -> str:
        """Derive a human-readable local name from an entity identifier.

        Handles HTTP(S)/IRI identifiers (path segments and fragments, tolerating
        trailing slashes) as well as compact/CURIE and URN-style identifiers.
        """
        raw = str(identifier).strip()
        if not raw:
            return ""

        # Prefer a fragment if present (e.g. http://ex.org/onto#acme -> acme).
        if "#" in raw:
            candidate = raw.rsplit("#", 1)[-1]
            if candidate:
                return candidate

        # For IRIs/paths, take the last non-empty path segment.
        if "/" in raw:
            segment = raw.rstrip("/").rsplit("/", 1)[-1]
            if segment:
                return segment

        # Fall back to the tail of a CURIE/URN (e.g. urn:x:acme, semantica:acme).
        if ":" in raw:
            candidate = raw.rsplit(":", 1)[-1]
            if candidate:
                return candidate

        return raw

    def convert_kg_to_rdf(self, knowledge_graph: Dict[str, Any]) -> Dict[str, Any]:
        """
        Convert knowledge graph to RDF data structure.

        This method prepares a knowledge graph for RDF serialization by ensuring
        it has the expected structure and normalizing fields (e.g., mapping 'name'
        to 'label' or 'text').

        Args:
            knowledge_graph: Knowledge graph dictionary from GraphBuilder

        Returns:
            Dictionary containing RDF-ready data:
                - entities: List of normalized entity dictionaries
                - relationships: List of relationship dictionaries
        """
        import copy

        # Create a shallow copy of the graph structure to avoid modifying original
        rdf_data = {
            "entities": [],
            "relationships": knowledge_graph.get("relationships", []),
            "metadata": knowledge_graph.get("metadata", {}),
        }

        # Copy @context if present
        if "@context" in knowledge_graph:
            rdf_data["@context"] = knowledge_graph["@context"]

        # Normalize entities
        for entity in knowledge_graph.get("entities", []):
            # Create copy of entity
            norm_entity = entity.copy()

            # Ensure 'text' or 'label' exists
            if "text" not in norm_entity and "label" not in norm_entity:
                if "name" in norm_entity:
                    norm_entity["label"] = norm_entity["name"]
                elif "id" in norm_entity:
                    # Derive a readable label from the identifier's local name
                    # (fragment/last path segment/CURIE tail). See #1097.
                    local_name = self._local_name_from_id(norm_entity["id"])
                    if local_name:
                        norm_entity["label"] = local_name

            rdf_data["entities"].append(norm_entity)

        return rdf_data

    # OWL-Time namespace URI
    _OWL_TIME_NS = "http://www.w3.org/2006/time#"
    _SEMANTICA_NS = "https://semantica.dev/ns#"

    # Matches an already-valid percent-escape so it can be passed through
    # unchanged instead of being re-encoded into e.g. %2520.
    _PERCENT_ESCAPE_RE = re.compile(r"%[0-9A-Fa-f]{2}")

    @classmethod
    def _quote_preserving_escapes(cls, value: str, safe: str) -> str:
        """quote() that leaves existing valid %XX escapes untouched.

        Blanket-quoting an absolute IRI double-encodes any percent-escape it
        already carries (%20 -> %2520), which changes the identity of every
        previously-valid IRI containing one. Only the spans between existing
        valid escapes are quoted; a bare '%' that isn't part of a valid
        escape (e.g. "%zz") still gets encoded to %25, keeping the malformed
        case handled.
        """
        parts = []
        pos = 0
        for match in cls._PERCENT_ESCAPE_RE.finditer(value):
            parts.append(quote(value[pos : match.start()], safe=safe))
            parts.append(match.group(0))
            pos = match.end()
        parts.append(quote(value[pos:], safe=safe))
        return "".join(parts)

    def _as_turtle_iri(
        self, value: Any, namespaces: Optional[Dict[str, str]] = None
    ) -> str:
        """Return an absolute, safely encoded IRI for a Turtle resource."""
        value = str(value)
        try:
            parsed = urlsplit(value)
        except ValueError:
            parsed = urlsplit("")
        if parsed.scheme:
            prefix, separator, local_name = value.partition(":")
            # Built-in namespaces (semantica:, rdf:, rdfs:, owl:, ...) must
            # always be resolvable, not only when the caller passes no
            # namespaces of its own — otherwise a value like "semantica:Foo"
            # resolves fine with no @context but stops resolving the moment
            # any @context is present, since callers pass extract_namespaces()
            # (context-only) here without merging in the built-ins.
            effective_namespaces = {
                **self.namespace_manager.namespaces,
                **(namespaces or {}),
            }
            namespace = effective_namespaces.get(prefix)
            if namespace and separator:
                return self._quote_preserving_escapes(
                    namespace + local_name, safe=":/?#[]@!$&'()*+,;="
                )
            # A scheme with at least two characters is an absolute IRI,
            # including opaque forms such as mailto:foo and isbn:0451450523.
            # Keep one-character schemes as the existing Windows drive-path case.
            if len(prefix) >= 2:
                return self._quote_preserving_escapes(
                    value, safe=":/?#[]@!$&'()*+,;="
                )
        return self._SEMANTICA_NS + quote(value, safe="")

    # Design decision — TemporalBound.OPEN in RDF:
    # OWL-Time has no standard predicate for "no known end date." We use
    # semantica:openEndedInterval "true"^^xsd:boolean on the time:Interval
    # node to signal that valid_until is OPEN/unbounded. This keeps the
    # interval well-formed while remaining human- and machine-readable.

    def serialize_to_turtle(self, rdf_data: Dict[str, Any], **options) -> str:
        """
        Serialize RDF to Turtle format.

        Turtle is a compact, human-readable RDF serialization format. This method
        converts RDF data (entities and relationships) to Turtle syntax with
        namespace declarations and RDF triplets.

        Args:
            rdf_data: RDF data dictionary containing:
                - entities: List of entity dictionaries
                - relationships: List of relationship dictionaries
                - @context: Optional JSON-LD context for namespaces
            **options: Additional serialization options.
                include_temporal (bool): When True, emit OWL-Time triples for
                    relationships that carry valid_from / valid_until metadata.
                    Default: False.
                time_axis (str): Which temporal axis to export — "valid",
                    "transaction", or "both". Default: "valid".

        Returns:
            String containing Turtle-format RDF serialization

        Example:
            >>> rdf_data = {
            ...     "entities": [{"id": "e1", "text": "Entity 1", "type": "Person"}],
            ...     "relationships": [{"source_id": "e1", "target_id": "e2", "type": "knows"}]
            ... }
            >>> turtle = serializer.serialize_to_turtle(rdf_data)
        """
        include_temporal: bool = options.pop("include_temporal", False)
        time_axis: str = options.pop("time_axis", "valid")
        metadata_terms = _resolve_metadata_terms(options.pop("metadata_terms", None))
        graph_uri: Optional[str] = options.pop("graph_uri", None)

        lines = []

        # Namespace declarations — always emit core prefixes; add OWL-Time when needed
        base_namespaces = {
            "rdf": "http://www.w3.org/1999/02/22-rdf-syntax-ns#",
            "xsd": "http://www.w3.org/2001/XMLSchema#",
            "semantica": "https://semantica.dev/ns#",
        }
        if include_temporal:
            base_namespaces["time"] = self._OWL_TIME_NS

        extracted = self.namespace_manager.extract_namespaces(rdf_data)
        merged_namespaces = {**base_namespaces, **extracted}

        ns_declarations = self.namespace_manager.generate_namespace_declarations(
            merged_namespaces, "turtle"
        )
        lines.append(ns_declarations)
        lines.append("")

        # Convert entities to RDF triplets
        entities = rdf_data.get("entities", [])
        for entity in entities:
            entity_id = entity.get("id")
            if not entity_id:
                entity_text = entity.get("text", "")
                entity_id = mint_entity_iri(entity_text)

            entity_type = entity.get("type", DEFAULT_ENTITY_TYPE)
            text = entity.get("text") or entity.get("label", "")
            confidence = normalize_confidence(entity.get("confidence", 1.0))

            clauses = [
                f"a <{self._as_turtle_iri(entity_type, merged_namespaces)}>",
                f'semantica:text "{_escape_literal(text)}"',
            ]
            if confidence is None:
                self.logger.warning(
                    f"Entity {entity_id} has a confidence that is not a number "
                    f"({entity.get('confidence')!r}), so no confidence is written"
                )
            else:
                clauses.append(
                    f'semantica:confidence "{confidence}"^^<{CONFIDENCE_DATATYPE}>'
                )
            clauses.extend(
                _turtle_metadata_clauses(
                    _metadata_statements(
                        entity.get("metadata"), metadata_terms, self.logger
                    )
                )
            )

            entity_iri = self._as_turtle_iri(entity_id, merged_namespaces)
            lines.append(f"<{entity_iri}> {clauses[0]} ;")
            for clause in clauses[1:-1]:
                lines.append(f"    {clause} ;")
            lines.append(f"    {clauses[-1]} .")
            lines.append("")

        # Convert relationships to RDF triplets
        relationships = rdf_data.get("relationships", [])
        for idx, rel in enumerate(relationships):
            source_id = rel.get("source_id") or rel.get("source")
            target_id = rel.get("target_id") or rel.get("target")
            rel_type = rel.get("type", DEFAULT_RELATION_TYPE)

            lines.append(
                f"<{self._as_turtle_iri(source_id, merged_namespaces)}> "
                f"<{self._as_turtle_iri(rel_type, merged_namespaces)}> "
                f"<{self._as_turtle_iri(target_id, merged_namespaces)}> ."
            )

            if include_temporal:
                owl_lines = self._owl_time_triples_for_rel(
                    rel, idx, time_axis, merged_namespaces
                )
                if owl_lines:
                    # The interval hangs off the relationship's own IRI, and a
                    # relationship written as a single triple has no such node
                    # in the graph. Without this the timestamps are well formed
                    # and unreachable: no query can get from the edge to its
                    # validity interval (#1106). The shape matches the JSON-LD
                    # export, and every term is declared in the vocabulary.
                    lines.extend(
                        self._reified_relationship_triples(
                            rel, idx, source_id, target_id, rel_type, merged_namespaces
                        )
                    )
                    lines.extend(owl_lines)

        # Graph-level metadata needs a subject, and this serializer has never
        # minted a document node. Rather than invent one here, it is written
        # only when the caller names the graph; issue #1147 is where the
        # default subject comes from once that lands.
        graph_clauses = (
            _turtle_metadata_clauses(
                _metadata_statements(
                    rdf_data.get("metadata"), metadata_terms, self.logger
                )
            )
            if graph_uri
            else []
        )
        if graph_clauses:
            graph_iri = self._as_turtle_iri(graph_uri, merged_namespaces)
            lines.append("")
            lines.append(
                f"<{graph_iri}> {graph_clauses[0]} "
                + (";" if len(graph_clauses) > 1 else ".")
            )
            for clause in graph_clauses[1:-1]:
                lines.append(f"    {clause} ;")
            if len(graph_clauses) > 1:
                lines.append(f"    {graph_clauses[-1]} .")

        return "\n".join(lines)

    def _reified_relationship_triples(
        self,
        rel: Dict[str, Any],
        idx: int,
        source_id: str,
        target_id: str,
        rel_type: str,
        namespaces: Optional[Dict[str, str]] = None,
    ) -> List[str]:
        """
        Emit the reified relationship node that OWL-Time triples hang off.

        The direct triple stays. This adds a subject the interval can attach
        to, using the same sem:Relationship shape the JSON-LD export already
        writes, so the two serializations describe relationships the same way.
        """
        rel_id = self._as_turtle_iri(
            rel.get("id")
            or mint_relationship_iri(idx, source_id or "", target_id or ""),
            namespaces,
        )

        # The full predicate, not its local name. Truncating to the fragment
        # made https://a.example/ns#employs and https://b.example/ns#employs the
        # same literal, so the temporal node no longer said which predicate it
        # described, and it disagreed with the direct triple beside it.
        escaped = (
            str(rel_type)
            .replace("\\", "\\\\")
            .replace('"', '\\"')
            .replace("\n", "\\n")
            .replace("\r", "\\r")
        )

        predicates = ["a semantica:Relationship"]
        if source_id:
            predicates.append(
                f"semantica:source <{self._as_turtle_iri(source_id, namespaces)}>"
            )
        if target_id:
            predicates.append(
                f"semantica:target <{self._as_turtle_iri(target_id, namespaces)}>"
            )
        predicates.append(f'semantica:type "{escaped}"')

        return ["", f"<{rel_id}> " + " ;\n    ".join(predicates) + " ."]

    def _owl_time_triples_for_rel(
        self,
        rel: Dict[str, Any],
        idx: int,
        time_axis: str,
        namespaces: Optional[Dict[str, str]] = None,
    ) -> List[str]:
        """
        Emit OWL-Time Turtle triples for a relationship that carries temporal metadata.

        For TemporalBound.OPEN valid_until values we use:
            semantica:openEndedInterval "true"^^xsd:boolean
        instead of time:hasEnd, because OWL-Time has no standard predicate for
        "no known end date."
        """
        _OPEN_SENTINEL = "OPEN"

        def _is_open(v: Any) -> bool:
            if v is None:
                return False
            if hasattr(v, "value"):  # TemporalBound enum
                return v.value == _OPEN_SENTINEL
            return str(v).strip().upper() == _OPEN_SENTINEL

        axes: List[tuple] = []
        if time_axis in ("valid", "both"):
            axes.append(("valid", rel.get("valid_from"), rel.get("valid_until")))
        if time_axis in ("transaction", "both"):
            axes.append(("tx", rel.get("recorded_at"), rel.get("superseded_at")))

        # Resolve endpoints the same way serialize_to_turtle does: both
        # representations are accepted upstream, and minting from source_id
        # alone hashes empty strings for every relationship that uses source,
        # so unrelated relationships at the same index would collide on a
        # deterministic IRI.
        source_id = rel.get("source_id") or rel.get("source") or ""
        target_id = rel.get("target_id") or rel.get("target") or ""
        rel_base_id = self._as_turtle_iri(
            rel.get("id") or mint_relationship_iri(idx, source_id, target_id),
            namespaces,
        )

        lines = [""]  # blank separator
        for axis_name, from_val, until_val in axes:
            if from_val is None and (until_val is None or _is_open(until_val)):
                continue  # no temporal data on this axis — skip

            interval_id = f"{rel_base_id}__{axis_name}_interval"
            begin_id = f"{rel_base_id}__{axis_name}_begin"

            lines.append(f"<{rel_base_id}> time:hasTime <{interval_id}> .")
            lines.append(f"<{interval_id}> a time:Interval ;")
            lines.append(f"    time:hasBeginning <{begin_id}> ;")

            if _is_open(until_val):
                lines.append('    semantica:openEndedInterval "true"^^xsd:boolean .')
            elif until_val is not None:
                end_id = f"{rel_base_id}__{axis_name}_end"
                lines.append(f"    time:hasEnd <{end_id}> .")
                lines.append(f"<{end_id}> a time:Instant ;")
                lines.append(
                    f'    time:inXSDDateTimeStamp "{_escape_temporal_literal(until_val)}"^^xsd:dateTimeStamp .'
                )
            else:
                lines[-1] = (
                    lines[-1].rstrip(" ;") + " ."
                )  # close interval without hasEnd

            lines.append(f"<{begin_id}> a time:Instant ;")
            lines.append(
                f'    time:inXSDDateTimeStamp "{_escape_temporal_literal(from_val)}"^^xsd:dateTimeStamp .'
            )
            lines.append("")

        return lines if len(lines) > 1 else []

    def serialize_to_rdfxml(self, rdf_data: Dict[str, Any], **options) -> str:
        """
        Serialize RDF to RDF/XML format.

        RDF/XML is the XML-based RDF serialization format, standardized by W3C.
        This method converts RDF data to RDF/XML syntax with proper XML structure.

        Args:
            rdf_data: RDF data dictionary containing:
                - entities: List of entity dictionaries
                - relationships: List of relationship dictionaries
            **options: Additional serialization options (unused)

        Returns:
            String containing RDF/XML-format RDF serialization

        Example:
            >>> rdf_data = {
            ...     "entities": [{"id": "e1", "text": "Entity 1"}],
            ...     "relationships": [{"source_id": "e1", "target_id": "e2"}]
            ... }
            >>> rdfxml = serializer.serialize_to_rdfxml(rdf_data)
        """
        metadata_terms = _resolve_metadata_terms(options.pop("metadata_terms", None))
        graph_uri: Optional[str] = options.pop("graph_uri", None)

        lines = ['<?xml version="1.0" encoding="UTF-8"?>']
        lines.append('<rdf:RDF xmlns:rdf="http://www.w3.org/1999/02/22-rdf-syntax-ns#"')
        lines.append('         xmlns:rdfs="http://www.w3.org/2000/01/rdf-schema#"')
        lines.append('         xmlns:semantica="https://semantica.dev/ns#">')
        lines.append("")

        namespaces = self.namespace_manager.extract_namespaces(rdf_data)

        # Convert entities to RDF/XML
        entities = rdf_data.get("entities", [])
        for entity in entities:
            # Generate entity ID if not provided
            entity_id = entity.get("id")
            if not entity_id:
                entity_text = entity.get("text", "")
                entity_id = mint_entity_iri(entity_text)

            entity_type = entity.get("type") or DEFAULT_ENTITY_TYPE
            text = entity.get("text") or entity.get("label", "")
            confidence = normalize_confidence(entity.get("confidence", 1.0))

            # RDF/XML syntax: rdf:Description with rdf:about
            # Attribute values are delimited by quotes, and both of these
            # are caller input. Element text (semantica:text) is caller input
            # too, so it needs the same escaping to avoid injecting markup
            # or breaking out of the element (#1097 / #1113).
            entity_iri = xml_escape(
                self._as_turtle_iri(entity_id, namespaces), quote=True
            )
            entity_type_iri = xml_escape(
                self._as_turtle_iri(entity_type, namespaces), quote=True
            )
            lines.append(f'  <rdf:Description rdf:about="{entity_iri}">')
            lines.append(f'    <rdf:type rdf:resource="{entity_type_iri}"/>')
            lines.append(
                f"    <semantica:text>{xml_escape(text)}</semantica:text>"
            )
            if confidence is None:
                self.logger.warning(
                    f"Entity {entity_id} has a confidence that is not a number "
                    f"({entity.get('confidence')!r}), so no confidence is written"
                )
            else:
                lines.append(
                    f'    <semantica:confidence rdf:datatype="{CONFIDENCE_DATATYPE}">'
                    f"{confidence}</semantica:confidence>"
                )
            lines.extend(
                _rdfxml_metadata_lines(
                    _metadata_statements(
                        entity.get("metadata"), metadata_terms, self.logger
                    ),
                    "    ",
                    self.logger,
                )
            )
            lines.append("  </rdf:Description>")
            lines.append("")

        # Convert relationships to RDF/XML
        relationships = rdf_data.get("relationships", [])
        for rel in relationships:
            source_id = rel.get("source_id") or rel.get("source")
            target_id = rel.get("target_id") or rel.get("target")
            # RDF/XML predicates are emitted as QNames, unlike resource
            # attributes which use the shared absolute-IRI normalizer.
            rel_type = rel.get("type") or "semantica:related_to"

            # Relationship as property on source entity
            source_iri = xml_escape(
                self._as_turtle_iri(source_id, namespaces), quote=True
            )
            target_iri = xml_escape(
                self._as_turtle_iri(target_id, namespaces), quote=True
            )
            lines.append(f'  <rdf:Description rdf:about="{source_iri}">')
            lines.append(f'    <{rel_type} rdf:resource="{target_iri}"/>')
            lines.append("  </rdf:Description>")
            lines.append("")

        graph_lines = (
            _rdfxml_metadata_lines(
                _metadata_statements(
                    rdf_data.get("metadata"), metadata_terms, self.logger
                ),
                "    ",
                self.logger,
            )
            if graph_uri
            else []
        )
        if graph_lines:
            graph_iri = xml_escape(
                self._as_turtle_iri(graph_uri, namespaces), quote=True
            )
            lines.append(f'  <rdf:Description rdf:about="{graph_iri}">')
            lines.extend(graph_lines)
            lines.append("  </rdf:Description>")
            lines.append("")

        lines.append("</rdf:RDF>")
        return "\n".join(lines)

    def serialize_to_jsonld(self, rdf_data: Dict[str, Any], **options) -> str:
        """
        Serialize RDF to JSON-LD format.

        JSON-LD is a JSON-based RDF serialization format that uses @context for
        namespace management and @graph for RDF data. This method converts RDF
        data to JSON-LD syntax.

        Args:
            rdf_data: RDF data dictionary containing:
                - entities: List of entity dictionaries
                - relationships: List of relationship dictionaries
                - @context: Optional existing context (merged)
            **options: Additional serialization options (unused)

        Returns:
            String containing JSON-LD-format RDF serialization (pretty-printed JSON)

        Example:
            >>> rdf_data = {
            ...     "entities": [{"id": "e1", "text": "Entity 1"}],
            ...     "relationships": [{"source_id": "e1", "target_id": "e2"}]
            ... }
            >>> jsonld = serializer.serialize_to_jsonld(rdf_data)
        """
        import json

        metadata_terms = _resolve_metadata_terms(options.pop("metadata_terms", None))
        graph_uri: Optional[str] = options.pop("graph_uri", None)

        # Initialize JSON-LD structure with context
        jsonld = {
            "@context": {
                "@vocab": "https://semantica.dev/vocab/",
                "semantica": "https://semantica.dev/ns#",
                "rdf": "http://www.w3.org/1999/02/22-rdf-syntax-ns#",
                "rdfs": "http://www.w3.org/2000/01/rdf-schema#",
            },
            "@graph": [],
        }

        # Merge existing context if present
        if "@context" in rdf_data:
            jsonld["@context"].update(rdf_data["@context"])

        # Convert entities to JSON-LD
        entities = rdf_data.get("entities", [])
        for entity in entities:
            # Generate @id if not provided. Minted the same way the Turtle and
            # N-Triples paths mint it (#1101), so one knowledge graph carries
            # the same node identity whichever serializer wrote it. The former
            # f"semantica:entity/{text}" interpolated the raw text into an IRI:
            # any entity whose text contained a space produced an invalid IRI
            # and was dropped in full by a JSON-LD parser, silently.
            entity_id = entity.get("id") or mint_entity_iri(entity.get("text", ""))

            node = {
                "@id": entity_id,
                "@type": entity.get("type", "semantica:Entity"),
                "semantica:text": entity.get("text") or entity.get("label", ""),
            }
            confidence = normalize_confidence(entity.get("confidence", 1.0))
            if confidence is None:
                self.logger.warning(
                    f"Entity {entity_id} has a confidence that is not a number "
                    f"({entity.get('confidence')!r}), so no confidence is written"
                )
            else:
                # A native JSON number becomes xsd:double once expanded, so the
                # value is written as a typed literal instead.
                node["semantica:confidence"] = {
                    "@value": confidence,
                    "@type": CONFIDENCE_DATATYPE,
                }
            node.update(
                _jsonld_metadata_entries(
                    _metadata_statements(
                        entity.get("metadata"), metadata_terms, self.logger
                    )
                )
            )
            jsonld["@graph"].append(node)

        # Convert relationships to JSON-LD
        relationships = rdf_data.get("relationships", [])
        for index, rel in enumerate(relationships):
            # Endpoints are resolved both ways, as serialize_to_turtle resolves
            # them: a relationship carrying source/target rather than
            # source_id/target_id used to hash into f"semantica:rel/_", so every
            # such relationship in an export collapsed onto one node and their
            # types and endpoints merged.
            source = rel.get("source_id") or rel.get("source", "")
            target = rel.get("target_id") or rel.get("target", "")
            rel_id = rel.get("id") or mint_relationship_iri(index, source, target)

            jsonld["@graph"].append(
                {
                    "@id": rel_id,
                    "@type": "semantica:Relationship",
                    "semantica:source": {"@id": source},
                    "semantica:target": {"@id": target},
                    "semantica:type": rel.get("type", "related_to"),
                }
            )

        graph_entries = (
            _jsonld_metadata_entries(
                _metadata_statements(
                    rdf_data.get("metadata"), metadata_terms, self.logger
                )
            )
            if graph_uri
            else {}
        )
        if graph_entries:
            jsonld["@graph"].append({"@id": graph_uri, **graph_entries})

        return json.dumps(jsonld, indent=2, ensure_ascii=False)

    def serialize_to_ntriples(self, rdf_data: Dict[str, Any], **options) -> str:
        """
        Serialize RDF to N-Triples format.

        N-Triples is a line-based, plain text format for encoding an RDF graph.
        Each line represents a triple: subject predicate object .

        Args:
            rdf_data: RDF data dictionary
            **options: Additional options

        Returns:
            String containing N-Triples serialization
        """
        metadata_terms = _resolve_metadata_terms(options.pop("metadata_terms", None))
        graph_uri: Optional[str] = options.pop("graph_uri", None)

        lines = []

        namespaces = self.namespace_manager.extract_namespaces(rdf_data)

        def expand_uri(uri: str) -> str:
            if not uri:
                return ""
            return f"<{self._as_turtle_iri(uri, namespaces)}>"

        # Convert entities
        entities = rdf_data.get("entities", [])
        for entity in entities:
            # Generate entity ID if not provided
            entity_id = entity.get("id")
            if not entity_id:
                entity_text = entity.get("text", "")
                entity_id = mint_entity_iri(entity_text)

            subject = expand_uri(entity_id)

            # Type triple
            entity_type = entity.get("type") or DEFAULT_ENTITY_TYPE
            lines.append(
                f"{subject} <http://www.w3.org/1999/02/22-rdf-syntax-ns#type> {expand_uri(entity_type)} ."
            )

            # Text property
            text = entity.get("text") or entity.get("label", "")
            if text:
                safe_text = _escape_literal(text)
                lines.append(
                    f'{subject} {expand_uri("semantica:text")} "{safe_text}" .'
                )

            # Confidence property. The default matches the other serializers,
            # which have always written one; omitting it here was half of why
            # Turtle and N-Triples of one KG were different graphs (#1100).
            raw_confidence = entity.get("confidence", 1.0)
            confidence = normalize_confidence(raw_confidence)
            if confidence is None:
                self.logger.warning(
                    f"Entity {entity.get('id')} has a confidence that is not a "
                    f"number ({raw_confidence!r}), so no confidence is written"
                )
            else:
                lines.append(
                    f'{subject} {expand_uri("semantica:confidence")} '
                    f'"{confidence}"^^<{CONFIDENCE_DATATYPE}> .'
                )

            lines.extend(
                _ntriples_metadata_lines(
                    subject.strip("<>"),
                    _metadata_statements(
                        entity.get("metadata"), metadata_terms, self.logger
                    ),
                )
            )

        # Convert relationships
        relationships = rdf_data.get("relationships", [])
        for rel in relationships:
            source_id = rel.get("source_id") or rel.get("source")
            target_id = rel.get("target_id") or rel.get("target")
            rel_type = rel.get("type") or DEFAULT_RELATION_TYPE

            if source_id and target_id:
                lines.append(
                    f"{expand_uri(source_id)} {expand_uri(rel_type)} {expand_uri(target_id)} ."
                )

        if graph_uri:
            lines.extend(
                _ntriples_metadata_lines(
                    graph_uri,
                    _metadata_statements(
                        rdf_data.get("metadata"), metadata_terms, self.logger
                    ),
                )
            )

        return "\n".join(lines)


class RDFValidator:
    """
    RDF validation engine.

    This class provides RDF data validation including syntax checking, structure
    validation, namespace usage validation, and consistency checking.

    Features:
        - RDF syntax validation
        - Structure and format validation
        - Namespace usage validation
        - Consistency checking (entity references, etc.)

    Example Usage:
        >>> validator = RDFValidator()
        >>> result = validator.validate_rdf_syntax(rdf_data, format="turtle")
        >>> consistency = validator.check_rdf_consistency(rdf_data)
    """

    def __init__(self, **config):
        """
        Initialize RDF validator.

        Sets up the validator with configuration options.

        Args:
            **config: Configuration options (currently unused)
        """
        self.logger = get_logger("rdf_validator")
        self.config = config or {}

        self.logger.debug("RDF validator initialized")

    def validate_rdf_syntax(
        self, rdf_data: Dict[str, Any], format: str = "turtle"
    ) -> Dict[str, Any]:
        """
        Validate RDF syntax for specified format.

        This method performs syntax and structure validation on RDF data,
        checking for required fields, correct data types, and format-specific
        requirements.

        Args:
            rdf_data: RDF data dictionary to validate
            format: RDF format being validated (default: "turtle")
                   (currently unused, but reserved for format-specific checks)

        Returns:
            Dictionary containing:
                - valid: Boolean indicating if validation passed
                - errors: List of error messages
                - warnings: List of warning messages

        Example:
            >>> result = validator.validate_rdf_syntax(rdf_data, format="turtle")
            >>> if result["valid"]:
            ...     print("RDF syntax is valid")
            ... else:
            ...     print(f"Errors: {result['errors']}")
        """
        errors = []
        warnings = []

        # Basic structure validation
        if not isinstance(rdf_data, dict):
            errors.append("RDF data must be a dictionary")
            return {"valid": False, "errors": errors, "warnings": warnings}

        # Check for required fields
        if "entities" not in rdf_data and "relationships" not in rdf_data:
            warnings.append(
                "No entities or relationships found in RDF data. "
                "RDF data may be empty."
            )

        # Validate entities
        entities = rdf_data.get("entities", [])
        for i, entity in enumerate(entities):
            if not isinstance(entity, dict):
                errors.append(f"Entity {i} is not a dictionary (type: {type(entity)})")
                continue

            # Check for required fields (at least id or text)
            if "id" not in entity and "text" not in entity:
                warnings.append(
                    f"Entity {i} missing both 'id' and 'text' fields. "
                    "Entity may not be properly identifiable."
                )

        # Validate relationships
        relationships = rdf_data.get("relationships", [])
        for i, rel in enumerate(relationships):
            if not isinstance(rel, dict):
                errors.append(
                    f"Relationship {i} is not a dictionary (type: {type(rel)})"
                )
                continue

            # Check for required fields
            if "source_id" not in rel and "source" not in rel:
                errors.append(f"Relationship {i} missing 'source_id' or 'source' field")
            if "target_id" not in rel and "target" not in rel:
                errors.append(f"Relationship {i} missing 'target_id' or 'target' field")

        is_valid = len(errors) == 0

        if is_valid:
            self.logger.debug(
                f"RDF syntax validation passed: {len(entities)} entity(ies), "
                f"{len(relationships)} relationship(s)"
            )
        else:
            self.logger.warning(
                f"RDF syntax validation failed: {len(errors)} error(s), "
                f"{len(warnings)} warning(s)"
            )

        return {"valid": is_valid, "errors": errors, "warnings": warnings}

    def validate_namespace_usage(self, rdf_data: Dict[str, Any]) -> Dict[str, Any]:
        """
        Validate RDF namespace usage.

        This method validates namespace declarations and usage in RDF data,
        particularly for JSON-LD format which uses @context.

        Args:
            rdf_data: RDF data dictionary to validate

        Returns:
            Dictionary containing:
                - valid: Boolean indicating if namespace usage is valid
                - issues: List of namespace-related issues

        Example:
            >>> result = validator.validate_namespace_usage(rdf_data)
            >>> if not result["valid"]:
            ...     print(f"Namespace issues: {result['issues']}")
        """
        issues = []

        # Check for @context in JSON-LD
        if "@context" in rdf_data:
            context = rdf_data["@context"]
            if not isinstance(context, dict):
                issues.append("@context must be a dictionary, got: {type(context)}")
            else:
                # Validate context entries
                for prefix, uri in context.items():
                    if not isinstance(prefix, str):
                        issues.append(f"Context prefix must be string: {prefix}")
                    if not isinstance(uri, str):
                        issues.append(f"Context URI must be string: {uri}")

        is_valid = len(issues) == 0

        if is_valid:
            self.logger.debug("Namespace usage validation passed")
        else:
            self.logger.warning(
                f"Namespace usage validation found {len(issues)} issue(s)"
            )

        return {"valid": is_valid, "issues": issues}

    def check_rdf_consistency(self, rdf_data: Dict[str, Any]) -> Dict[str, Any]:
        """
        Check RDF consistency and coherence.

        This method performs consistency checks on RDF data, including validation
        of relationship references to ensure they point to existing entities.

        Args:
            rdf_data: RDF data dictionary to check

        Returns:
            Dictionary containing:
                - consistent: Boolean indicating if data is consistent
                - issues: List of consistency issues found

        Example:
            >>> result = validator.check_rdf_consistency(rdf_data)
            >>> if not result["consistent"]:
            ...     print(f"Consistency issues: {result['issues']}")
        """
        issues = []

        # Build set of entity IDs for reference checking
        entities = rdf_data.get("entities", [])
        entity_ids = {e.get("id") for e in entities if e.get("id")}

        # Check relationship references
        relationships = rdf_data.get("relationships", [])
        for i, rel in enumerate(relationships):
            source_id = rel.get("source_id") or rel.get("source")
            target_id = rel.get("target_id") or rel.get("target")

            # Check if source entity exists
            if source_id and source_id not in entity_ids:
                issues.append(
                    f"Relationship {i} references non-existent source entity: {source_id}"
                )

            # Check if target entity exists
            if target_id and target_id not in entity_ids:
                issues.append(
                    f"Relationship {i} references non-existent target entity: {target_id}"
                )

        is_consistent = len(issues) == 0

        if is_consistent:
            self.logger.debug(
                f"RDF consistency check passed: {len(entities)} entity(ies), "
                f"{len(relationships)} relationship(s)"
            )
        else:
            self.logger.warning(f"RDF consistency check found {len(issues)} issue(s)")

        return {"consistent": is_consistent, "issues": issues}


class RDFExporter:
    """
    RDF export and serialization handler.

    This class provides comprehensive RDF export functionality, combining
    serialization, validation, and namespace management for multiple RDF formats.

    Features:
        - Multiple RDF format export (Turtle, RDF/XML, JSON-LD, N-Triples, N3)
        - RDF serialization and validation
        - Namespace management
        - Knowledge graph to RDF conversion
        - Batch export processing

    Example Usage:
        >>> exporter = RDFExporter()
        >>> exporter.export(data, "output.ttl", format="turtle")
        >>> validation = exporter.validate_rdf(data)
    """

    def __init__(self, config: Optional[Dict[str, Any]] = None, **kwargs):
        """
        Initialize RDF exporter.

        Sets up the exporter with serialization, validation, and namespace
        management components.

        Args:
            config: Optional configuration dictionary (merged with kwargs)
            **kwargs: Additional configuration options
        """
        self.logger = get_logger("rdf_exporter")
        self.config = config or {}
        self.config.update(kwargs)

        # Initialize components
        self.serializer = RDFSerializer()
        self.validator = RDFValidator()
        self.namespace_manager = NamespaceManager()

        # Supported RDF formats
        self.supported_formats = ["turtle", "rdfxml", "jsonld", "ntriples", "n3"]

        # Format aliases (common extensions/shorthands → canonical names)
        self._format_aliases = {
            "ttl": "turtle",
            "nt": "ntriples",
            "xml": "rdfxml",
            "rdf": "rdfxml",
            "json-ld": "jsonld",
        }

        # Initialize progress tracker
        self.progress_tracker = get_progress_tracker()

        self.logger.debug(
            f"RDF exporter initialized with {len(self.supported_formats)} format(s)"
        )

    def export_to_rdf(
        self,
        data: Dict[str, Any],
        format: str = "turtle",
        include_temporal: bool = False,
        time_axis: str = "valid",
        **options,
    ) -> str:
        """
        Export data to RDF format string.

        This method converts RDF data to a string in the specified RDF format.
        Performs validation before serialization and handles format-specific
        serialization.

        Args:
            data: RDF data dictionary containing entities and relationships
            format: RDF format - 'turtle', 'rdfxml', or 'jsonld' (default: 'turtle')
            **options: Additional serialization options

        Returns:
            String containing RDF serialization in specified format

        Raises:
            ValidationError: If format is unsupported or not implemented

        Example:
            >>> rdf_string = exporter.export_to_rdf(data, format="turtle")
            >>> print(rdf_string)
        """
        # Track RDF export
        tracking_id = self.progress_tracker.start_tracking(
            file=None,
            module="export",
            submodule="RDFExporter",
            message=f"Exporting data to RDF format: {format}",
        )

        try:
            if not isinstance(format, str):
                raise ValidationError(
                    f"RDF format must be a string, got: {type(format).__name__}"
                )
            fmt = format.strip().lower()
            format = self._format_aliases.get(fmt, fmt)
            if format not in self.supported_formats:
                raise ValidationError(
                    f"Unsupported RDF format: {format}. "
                    f"Supported formats: {', '.join(self.supported_formats)}"
                )

            self.logger.debug(f"Exporting to RDF format: {format}")

            # Normalize the graph before serialization so every format benefits
            # from field normalization (e.g. mapping 'name' -> 'label'/'text').
            # Without this, graphs produced by GraphBuilder (which emit 'name')
            # export with an empty semantica:text on all RDF paths. See #1097.
            data = self.serializer.convert_kg_to_rdf(data)

            self.progress_tracker.update_tracking(
                tracking_id, message="Validating RDF data..."
            )
            # Validate input data
            validation = self.validator.validate_rdf_syntax(data, format)
            if not validation["valid"]:
                self.logger.warning(
                    f"RDF validation issues found: {validation['errors']}. "
                    "Continuing with export, but data may be invalid."
                )
            if validation["warnings"]:
                self.logger.debug(f"RDF validation warnings: {validation['warnings']}")

            self.progress_tracker.update_tracking(
                tracking_id, message=f"Serializing to {format} format..."
            )
            # Serialize based on format
            if format == "turtle":
                result = self.serializer.serialize_to_turtle(
                    data,
                    include_temporal=include_temporal,
                    time_axis=time_axis,
                    **options,
                )
            elif format == "rdfxml":
                result = self.serializer.serialize_to_rdfxml(data, **options)
            elif format == "jsonld":
                result = self.serializer.serialize_to_jsonld(data, **options)
            elif format == "ntriples":
                result = self.serializer.serialize_to_ntriples(data, **options)
            else:
                raise ValidationError(
                    f"Format '{format}' not yet implemented. "
                    f"Implemented formats: turtle, rdfxml, jsonld"
                )

            self.progress_tracker.stop_tracking(
                tracking_id,
                status="completed",
                message=f"Exported to RDF format: {format}",
            )
            return result

        except Exception as e:
            self.progress_tracker.stop_tracking(
                tracking_id, status="failed", message=str(e)
            )
            raise

    def export(
        self,
        data: Dict[str, Any],
        file_path: Union[str, Path],
        format: str = "turtle",
        encoding: str = "utf-8",
        **options,
    ) -> None:
        """
        Export data to RDF file.

        This method exports RDF data to a file in the specified format, handling
        directory creation and file writing.

        Args:
            data: RDF data dictionary to export
            file_path: Output RDF file path
            format: RDF format - 'turtle', 'rdfxml', or 'jsonld' (default: 'turtle')
            encoding: File encoding (default: 'utf-8')
            **options: Additional options passed to export_to_rdf()

        Example:
            >>> exporter.export(rdf_data, "output.ttl", format="turtle")
            >>> exporter.export(rdf_data, "output.rdf", format="rdfxml")
        """
        file_path = Path(file_path)
        ensure_directory(file_path.parent)

        self.logger.debug(f"Exporting RDF to file: {file_path}, format={format}")

        # Generate RDF content
        rdf_content = self.export_to_rdf(data, format=format, **options)

        # Write to file
        with open(file_path, "w", encoding=encoding) as f:
            f.write(rdf_content)

        self.logger.info(f"Exported RDF ({format}) to: {file_path}")

    def export_knowledge_graph(
        self,
        graph: Dict[str, Any],
        file_path: Union[str, Path],
        format: str = "turtle",
        encoding: str = "utf-8",
        **options,
    ) -> None:
        """
        Export knowledge graph to RDF file.

        Alias for export.

        Args:
            graph: Knowledge graph dictionary
            file_path: Output file path
            format: RDF format
            encoding: File encoding
            **options: Additional options
        """
        self.export(graph, file_path, format=format, encoding=encoding, **options)

    def serialize_rdf(
        self, rdf_data: Dict[str, Any], format: str = "turtle", **options
    ) -> str:
        """
        Serialize RDF data to specified format.

        • Convert RDF to serialized format
        • Apply format-specific rules
        • Handle encoding and formatting
        • Return serialized RDF
        """
        return self.export_to_rdf(rdf_data, format=format, **options)

    def validate_rdf(self, rdf_data: Dict[str, Any], **options) -> Dict[str, Any]:
        """
        Validate RDF data quality and structure.

        This method performs comprehensive validation of RDF data including
        syntax validation, namespace usage validation, and consistency checking.

        Args:
            rdf_data: RDF data dictionary to validate
            **options: Additional validation options (unused)

        Returns:
            Dictionary containing validation results:
                - syntax: Syntax validation results
                - namespaces: Namespace validation results
                - consistency: Consistency check results
                - overall_valid: Boolean indicating if all validations passed

        Example:
            >>> result = exporter.validate_rdf(rdf_data)
            >>> if result["overall_valid"]:
            ...     print("RDF data is valid")
            ... else:
            ...     print(f"Syntax errors: {result['syntax']['errors']}")
        """
        # Perform all validation checks
        syntax_validation = self.validator.validate_rdf_syntax(rdf_data)
        namespace_validation = self.validator.validate_namespace_usage(rdf_data)
        consistency_check = self.validator.check_rdf_consistency(rdf_data)

        # Determine overall validity
        overall_valid = (
            syntax_validation["valid"]
            and namespace_validation["valid"]
            and consistency_check["consistent"]
        )

        if overall_valid:
            self.logger.info("RDF validation passed all checks")
        else:
            self.logger.warning(
                f"RDF validation failed: "
                f"syntax={syntax_validation['valid']}, "
                f"namespaces={namespace_validation['valid']}, "
                f"consistency={consistency_check['consistent']}"
            )

        return {
            "syntax": syntax_validation,
            "namespaces": namespace_validation,
            "consistency": consistency_check,
            "overall_valid": overall_valid,
        }

    def manage_namespaces(
        self, rdf_data: Dict[str, Any], **namespaces: str
    ) -> Dict[str, Any]:
        """
        Manage RDF namespaces and declarations.

        This method extracts namespaces from RDF data, merges with provided
        namespaces, resolves conflicts, and generates namespace declarations.

        Args:
            rdf_data: RDF data dictionary that may contain namespace information
            **namespaces: Additional namespaces to add (prefix=uri format)

        Returns:
            Dictionary containing:
                - namespaces: Resolved namespace dictionary (prefix -> URI)
                - declarations: Namespace declarations string (Turtle format)

        Example:
            >>> result = exporter.manage_namespaces(
            ...     rdf_data,
            ...     ex="http://example.org/ns#"
            ... )
            >>> print(result["declarations"])
        """
        # Extract existing namespaces from data
        extracted = self.namespace_manager.extract_namespaces(rdf_data)

        # Merge with provided namespaces
        all_namespaces = {**extracted, **namespaces}

        # Resolve conflicts
        resolved = self.namespace_manager.resolve_namespace_conflicts(all_namespaces)

        # Generate declarations
        declarations = self.namespace_manager.generate_namespace_declarations(
            resolved, "turtle"
        )

        self.logger.debug(
            f"Managed {len(resolved)} namespace(s): {list(resolved.keys())}"
        )

        return {"namespaces": resolved, "declarations": declarations}

    def export_shacl(
        self,
        shacl_string: str,
        file_path: Union[str, Path],
        format: str = "turtle",
        encoding: str = "utf-8",
    ) -> None:
        """
        Write a SHACL shapes string produced by SHACLGenerator to a file.

        Args:
            shacl_string: Serialized SHACL content (Turtle, JSON-LD, or N-Triples).
            file_path: Output path. Allowed extensions: .ttl, .jsonld, .nt, .shacl.
            format: Format hint used for logging — "turtle", "json-ld", "n-triples".
            encoding: File encoding (default "utf-8").

        Raises:
            ValidationError: If the file extension is not in the allowed set.
        """
        allowed_extensions = {".ttl", ".jsonld", ".nt", ".shacl"}
        path = Path(file_path)
        if path.suffix.lower() not in allowed_extensions:
            raise ValidationError(
                f"Unsupported SHACL file extension '{path.suffix}'. "
                f"Allowed: {sorted(allowed_extensions)}"
            )
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(shacl_string, encoding=encoding)
        self.logger.info(
            f"SHACL shapes ({format}) exported to {file_path} "
            f"({len(shacl_string)} chars)"
        )
