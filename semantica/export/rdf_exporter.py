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

from pathlib import Path
from typing import Any, Dict, List, Optional, Set, Union

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
                    # Use ID part as label if no name/text
                    norm_entity["label"] = str(norm_entity["id"]).split(":")[-1]

            rdf_data["entities"].append(norm_entity)

        return rdf_data

    # OWL-Time namespace URI
    _OWL_TIME_NS = "http://www.w3.org/2006/time#"

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
            confidence = entity.get("confidence", 1.0)

            lines.append(f"<{entity_id}> a <{entity_type}> ;")
            lines.append(f'    semantica:text "{text}" ;')
            lines.append(f"    semantica:confidence {confidence} .")
            lines.append("")

        # Convert relationships to RDF triplets
        relationships = rdf_data.get("relationships", [])
        for idx, rel in enumerate(relationships):
            source_id = rel.get("source_id") or rel.get("source")
            target_id = rel.get("target_id") or rel.get("target")
            rel_type = rel.get("type", DEFAULT_RELATION_TYPE)

            lines.append(f"<{source_id}> <{rel_type}> <{target_id}> .")

            if include_temporal:
                owl_lines = self._owl_time_triples_for_rel(rel, idx, time_axis)
                if owl_lines:
                    lines.extend(owl_lines)

        return "\n".join(lines)

    def _owl_time_triples_for_rel(
        self, rel: Dict[str, Any], idx: int, time_axis: str
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
            if hasattr(v, "value"):          # TemporalBound enum
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
        rel_base_id = rel.get("id") or mint_relationship_iri(idx, source_id, target_id)

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
                lines.append(
                    '    semantica:openEndedInterval "true"^^xsd:boolean .'
                )
            elif until_val is not None:
                end_id = f"{rel_base_id}__{axis_name}_end"
                lines.append(f"    time:hasEnd <{end_id}> .")
                lines.append(f"<{end_id}> a time:Instant ;")
                lines.append(
                    f'    time:inXSDDateTimeStamp "{until_val}"^^xsd:dateTimeStamp .'
                )
            else:
                lines[-1] = lines[-1].rstrip(" ;") + " ."  # close interval without hasEnd

            lines.append(f"<{begin_id}> a time:Instant ;")
            lines.append(
                f'    time:inXSDDateTimeStamp "{from_val}"^^xsd:dateTimeStamp .'
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
        lines = ['<?xml version="1.0" encoding="UTF-8"?>']
        lines.append('<rdf:RDF xmlns:rdf="http://www.w3.org/1999/02/22-rdf-syntax-ns#"')
        lines.append('         xmlns:rdfs="http://www.w3.org/2000/01/rdf-schema#"')
        lines.append('         xmlns:semantica="https://semantica.dev/ns#">')
        lines.append("")

        # Convert entities to RDF/XML
        entities = rdf_data.get("entities", [])
        for entity in entities:
            # Generate entity ID if not provided
            entity_id = entity.get("id")
            if not entity_id:
                entity_text = entity.get("text", "")
                entity_id = mint_entity_iri(entity_text)

            entity_type = entity.get("type", DEFAULT_ENTITY_TYPE)
            text = entity.get("text") or entity.get("label", "")
            confidence = entity.get("confidence", 1.0)

            # RDF/XML syntax: rdf:Description with rdf:about
            lines.append(f'  <rdf:Description rdf:about="{entity_id}">')
            lines.append(f'    <rdf:type rdf:resource="{entity_type}"/>')
            lines.append(f"    <semantica:text>{text}</semantica:text>")
            lines.append(
                f"    <semantica:confidence>{confidence}</semantica:confidence>"
            )
            lines.append("  </rdf:Description>")
            lines.append("")

        # Convert relationships to RDF/XML
        relationships = rdf_data.get("relationships", [])
        for rel in relationships:
            source_id = rel.get("source_id") or rel.get("source")
            target_id = rel.get("target_id") or rel.get("target")
            rel_type = rel.get("type", "semantica:related_to")

            # Relationship as property on source entity
            lines.append(f'  <rdf:Description rdf:about="{source_id}">')
            lines.append(f'    <{rel_type} rdf:resource="{target_id}"/>')
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

            jsonld["@graph"].append(
                {
                    "@id": entity_id,
                    "@type": entity.get("type", "semantica:Entity"),
                    "semantica:text": entity.get("text") or entity.get("label", ""),
                    "semantica:confidence": entity.get("confidence", 1.0),
                }
            )

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
        lines = []

        def expand_uri(uri: str) -> str:
            if not uri:
                return ""
            if uri.startswith("http"):
                return f"<{uri}>"
            if uri.startswith("semantica:"):
                return f"<https://semantica.dev/ns#{uri.split(':', 1)[1]}>"
            if uri.startswith("rdf:"):
                return f"<http://www.w3.org/1999/02/22-rdf-syntax-ns#{uri.split(':', 1)[1]}>"
            if uri.startswith("rdfs:"):
                return f"<http://www.w3.org/2000/01/rdf-schema#{uri.split(':', 1)[1]}>"
            if ":" in uri:
                return f"<{uri}>"
            return f"<https://semantica.dev/ns#{uri}>"

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
            entity_type = entity.get("type", "semantica:Entity")
            lines.append(
                f"{subject} <http://www.w3.org/1999/02/22-rdf-syntax-ns#type> {expand_uri(entity_type)} ."
            )

            # Text property
            text = entity.get("text") or entity.get("label", "")
            if text:
                safe_text = text.replace('"', '\\"').replace("\n", "\\n")
                lines.append(
                    f'{subject} {expand_uri("semantica:text")} "{safe_text}" .'
                )

            # Confidence property
            confidence = entity.get("confidence")
            if confidence is not None:
                lines.append(
                    f'{subject} {expand_uri("semantica:confidence")} "{confidence}"^^<http://www.w3.org/2001/XMLSchema#float> .'
                )

        # Convert relationships
        relationships = rdf_data.get("relationships", [])
        for rel in relationships:
            source_id = rel.get("source_id") or rel.get("source")
            target_id = rel.get("target_id") or rel.get("target")
            rel_type = rel.get("type", "semantica:related_to")

            if source_id and target_id:
                lines.append(
                    f"{expand_uri(source_id)} {expand_uri(rel_type)} {expand_uri(target_id)} ."
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
