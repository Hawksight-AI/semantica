"""
OWL Exporter Module

This module provides comprehensive OWL (Web Ontology Language) export capabilities
for the Semantica framework, enabling ontology export for semantic modeling.

Key Features:
    - OWL/OWL-XML format export
    - Turtle format export
    - Class definition and hierarchy export
    - Object and data property export
    - OWL 2.0 feature support
    - Ontology validation

Example Usage:
    >>> from semantica.export import OWLExporter
    >>> exporter = OWLExporter(ontology_uri="http://example.org/ontology#")
    >>> exporter.export(ontology, "ontology.owl", format="owl-xml")
    >>> exporter.export_classes(classes, "classes.owl")

Author: Semantica Contributors
License: MIT
"""

import re
from datetime import datetime
from pathlib import Path
from urllib.parse import quote
from typing import Any, Dict, List, Optional, Union

from ..utils.exceptions import ProcessingError, ValidationError
from ..utils.helpers import ensure_directory
from ..utils.logging import get_logger
from ..utils.progress_tracker import get_progress_tracker

# Issue #825, Part B Tier 3 — exporter interlinking. Reuses the same default
# namespace as ProvenanceManager.export_prov() and RDFExporter's
# NamespaceManager "semantica" entry, so ontology URIs, KG instance URIs, and
# PROV-exported URIs co-resolve under one shared namespace by default.
from ..provenance.manager import DEFAULT_BASE_URI

#: Module-level logger, for the classmethod helpers that have no instance.
logger = get_logger("owl_exporter")


class OWLExporter:
    """
    OWL exporter for semantic modeling and ontology representation.

    This class provides comprehensive OWL export functionality for ontologies,
    including class definitions, hierarchies, and property definitions.

    Features:
        - OWL/OWL-XML format export
        - Turtle format export
        - Class definition and hierarchy export
        - Object and data property export
        - OWL 2.0 feature support
        - Ontology validation

    Example Usage:
        >>> exporter = OWLExporter(
        ...     ontology_uri="http://example.org/ontology#",
        ...     version="1.0",
        ...     format="owl-xml"
        ... )
        >>> exporter.export(ontology, "ontology.owl")
    """

    def __init__(
        self,
        ontology_uri: str = DEFAULT_BASE_URI,
        version: str = "1.0",
        format: str = "owl-xml",
        config: Optional[Dict[str, Any]] = None,
        **kwargs,
    ):
        """
        Initialize OWL exporter.

        Sets up the exporter with ontology URI, version, and format configuration.

        Args:
            ontology_uri: Base URI for the ontology (default: ProvenanceManager.DEFAULT_BASE_URI,
                shared with RDFExporter's NamespaceManager and export_prov() so URIs co-resolve)
            version: Ontology version string (default: "1.0")
            format: Default export format - 'owl-xml' or 'turtle' (default: 'owl-xml')
            config: Optional configuration dictionary (merged with kwargs)
            **kwargs: Additional configuration options
        """
        self.logger = get_logger("owl_exporter")
        self.config = config or {}
        self.config.update(kwargs)

        # OWL configuration
        self.ontology_uri = ontology_uri
        self.version = version
        self.format = format

        # Initialize progress tracker
        self.progress_tracker = get_progress_tracker()

        self.logger.debug(
            f"OWL exporter initialized: uri={ontology_uri}, "
            f"version={version}, format={format}"
        )

    def export(
        self,
        ontology: Dict[str, Any],
        file_path: Union[str, Path],
        format: Optional[str] = None,
        encoding: str = "utf-8",
        **options,
    ) -> None:
        """
        Export ontology to OWL format file.

        This method exports a complete ontology (classes, properties, etc.) to
        OWL format in either OWL-XML or Turtle serialization.

        Supported Formats:
            - "owl-xml": OWL-XML format (RDF/XML-based)
            - "turtle": Turtle format (human-readable)

        Args:
            ontology: Ontology dictionary containing:
                - uri: Ontology URI (optional, uses self.ontology_uri if not provided)
                - name: Ontology name
                - description: Ontology description (optional)
                - version: Ontology version (optional)
                - classes: List of class definitions
                - object_properties: List of object property definitions
                - data_properties: List of data property definitions
            file_path: Output OWL file path
            format: Export format - 'owl-xml' or 'turtle' (default: self.format)
            encoding: File encoding (default: 'utf-8')
            **options: Additional export options

        Raises:
            ValidationError: If format is unsupported

        Example:
            >>> ontology = {
            ...     "name": "MyOntology",
            ...     "classes": [...],
            ...     "object_properties": [...]
            ... }
            >>> exporter.export(ontology, "ontology.owl", format="owl-xml")
        """
        # Track OWL export
        tracking_id = self.progress_tracker.start_tracking(
            file=str(file_path),
            module="export",
            submodule="OWLExporter",
            message=f"Exporting ontology to {format or self.format}: {file_path}",
        )

        try:
            file_path = Path(file_path)
            ensure_directory(file_path.parent)

            export_format = format or self.format

            self.logger.debug(
                f"Exporting ontology to {export_format}: {file_path}, "
                f"classes={len(ontology.get('classes', []))}, "
                f"object_properties={len(ontology.get('object_properties', []))}, "
                f"data_properties={len(ontology.get('data_properties', []))}"
            )

            self.progress_tracker.update_tracking(
                tracking_id, message=f"Converting ontology to {export_format}..."
            )
            # Generate OWL content based on format
            if export_format == "owl-xml":
                owl_content = self._export_owl_xml(ontology, **options)
            elif export_format == "turtle":
                owl_content = self._export_owl_turtle(ontology, **options)
            else:
                raise ValidationError(
                    f"Unsupported OWL format: {export_format}. "
                    "Supported formats: owl-xml, turtle"
                )

            self.progress_tracker.update_tracking(
                tracking_id, message="Writing OWL file..."
            )
            # Write OWL file
            with open(file_path, "w", encoding=encoding) as f:
                f.write(owl_content)

            self.logger.info(f"Exported OWL ({export_format}) to: {file_path}")
            self.progress_tracker.stop_tracking(
                tracking_id,
                status="completed",
                message=f"Exported OWL ({export_format}) to: {file_path}",
            )

        except Exception as e:
            self.progress_tracker.stop_tracking(
                tracking_id, status="failed", message=str(e)
            )
            raise

    def export_ontology(
        self, ontology: Dict[str, Any], file_path: Union[str, Path], **options
    ) -> None:
        """
        Export complete ontology to OWL.

        Args:
            ontology: Ontology dictionary
            file_path: Output file path
            **options: Additional options
        """
        self.export(ontology, file_path, **options)

    def _export_owl_xml(self, ontology: Dict[str, Any], **options) -> str:
        """
        Export ontology to OWL-XML format.

        OWL-XML is the RDF/XML-based serialization of OWL ontologies. This method
        generates OWL-XML syntax with proper RDF/XML structure.

        Args:
            ontology: Ontology dictionary with classes, properties, etc.
            **options: Additional export options (unused)

        Returns:
            String containing OWL-XML serialization
        """
        esc_xml = self._escape_xml
        ontology_uri = ontology.get("uri") or self.ontology_uri
        ontology_name = ontology.get("name", "SemanticaOntology")
        version = ontology.get("version") or self.version

        lines = ['<?xml version="1.0"?>']
        lines.append('<rdf:RDF xmlns:rdf="http://www.w3.org/1999/02/22-rdf-syntax-ns#"')
        lines.append('         xmlns:owl="http://www.w3.org/2002/07/owl#"')
        lines.append('         xmlns:rdfs="http://www.w3.org/2000/01/rdf-schema#"')
        lines.append('         xmlns:xsd="http://www.w3.org/2001/XMLSchema#">')
        lines.append("")

        # Ontology declaration
        lines.append(f'  <owl:Ontology rdf:about="{esc_xml(ontology_uri)}">')
        lines.append(f"    <rdfs:label>{esc_xml(ontology_name)}</rdfs:label>")
        lines.append(f"    <owl:versionInfo>{esc_xml(version)}</owl:versionInfo>")
        if ontology.get("description"):
            lines.append(
                f'    <rdfs:comment>{esc_xml(ontology.get("description"))}</rdfs:comment>'
            )
        lines.append("  </owl:Ontology>")
        lines.append("")

        class_index = self._class_iri_index(ontology, ontology_uri)
        object_properties, data_properties = self._split_properties(ontology)

        def _as_list(value):
            if value is None:
                return []
            return value if isinstance(value, list) else [value]

        # Classes
        for cls in ontology.get("classes", []) or []:
            if not isinstance(cls, dict):
                continue
            class_uri = self._term_iri(cls, ontology_uri)
            if not class_uri:
                self.logger.warning(
                    "Skipping a class with no name, uri or id: it would serialise "
                    "as an empty rdf:about"
                )
                continue
            class_name = cls.get("name") or cls.get("label", "")

            lines.append(f'  <owl:Class rdf:about="{esc_xml(class_uri)}">')
            lines.append(f"    <rdfs:label>{esc_xml(class_name)}</rdfs:label>")

            comment = cls.get("comment") or cls.get("description")
            if comment:
                lines.append(f"    <rdfs:comment>{esc_xml(comment)}</rdfs:comment>")

            # Subclass relationships
            for parent in _as_list(cls.get("subClassOf") or cls.get("parent")):
                parent_iri = self._resolve_class_ref(parent, ontology_uri, class_index)
                if parent_iri:
                    lines.append(
                        f'    <rdfs:subClassOf rdf:resource="{esc_xml(parent_iri)}"/>'
                    )

            # Equivalent classes
            for equiv in _as_list(cls.get("equivalentClass")):
                equiv_iri = self._resolve_class_ref(equiv, ontology_uri, class_index)
                if equiv_iri:
                    lines.append(
                        f'    <owl:equivalentClass rdf:resource="{esc_xml(equiv_iri)}"/>'
                    )

            lines.append("  </owl:Class>")
            lines.append("")

        # Object properties
        for prop in object_properties:
            prop_uri = self._term_iri(prop, ontology_uri)
            if not prop_uri:
                self.logger.warning(
                    "Skipping an object property with no name, uri or id"
                )
                continue
            prop_name = prop.get("name") or prop.get("label", "")

            lines.append(f'  <owl:ObjectProperty rdf:about="{esc_xml(prop_uri)}">')
            lines.append(f"    <rdfs:label>{esc_xml(prop_name)}</rdfs:label>")

            comment = prop.get("comment") or prop.get("description")
            if comment:
                lines.append(f"    <rdfs:comment>{esc_xml(comment)}</rdfs:comment>")

            for domain in _as_list(prop.get("domain")):
                domain_iri = self._resolve_class_ref(domain, ontology_uri, class_index)
                if domain_iri:
                    lines.append(
                        f'    <rdfs:domain rdf:resource="{esc_xml(domain_iri)}"/>'
                    )

            for range_val in _as_list(prop.get("range")):
                range_iri = self._resolve_class_ref(range_val, ontology_uri, class_index)
                if range_iri:
                    lines.append(
                        f'    <rdfs:range rdf:resource="{esc_xml(range_iri)}"/>'
                    )

            lines.append("  </owl:ObjectProperty>")
            lines.append("")

        # Data properties
        for prop in data_properties:
            prop_uri = self._term_iri(prop, ontology_uri)
            if not prop_uri:
                self.logger.warning("Skipping a data property with no name, uri or id")
                continue
            prop_name = prop.get("name") or prop.get("label", "")

            lines.append(f'  <owl:DatatypeProperty rdf:about="{esc_xml(prop_uri)}">')
            lines.append(f"    <rdfs:label>{esc_xml(prop_name)}</rdfs:label>")

            comment = prop.get("comment") or prop.get("description")
            if comment:
                lines.append(f"    <rdfs:comment>{esc_xml(comment)}</rdfs:comment>")

            for domain in _as_list(prop.get("domain")):
                domain_iri = self._resolve_class_ref(domain, ontology_uri, class_index)
                if domain_iri:
                    lines.append(
                        f'    <rdfs:domain rdf:resource="{esc_xml(domain_iri)}"/>'
                    )

            for range_val in _as_list(prop.get("range")):
                range_iri = self._resolve_datatype_iri(range_val)
                if range_iri:
                    lines.append(
                        f'    <rdfs:range rdf:resource="{esc_xml(range_iri)}"/>'
                    )

            lines.append("  </owl:DatatypeProperty>")
            lines.append("")

        lines.append("</rdf:RDF>")
        return "\n".join(lines)

    # ── Ontology-dict normalisation ───────────────────────────────────────────
    #
    # OntologyGenerator emits a single `properties` list tagged with
    # type/@type, while hand-authored ontologies use `object_properties` and
    # `data_properties`. Both shapes are accepted; everything below works from
    # the normalised view so the two cannot drift apart again (#1103).

    _XSD_NS = "http://www.w3.org/2001/XMLSchema#"

    #: Prefixes the generator and hand-authored ontologies actually use. A
    #: prefixed name is not an absolute IRI: `owl:Thing` matches the generic
    #: scheme grammar, so treating it as one produced <owl:Thing> as a domain,
    #: which is a different term from http://www.w3.org/2002/07/owl#Thing.
    _KNOWN_PREFIXES = {
        "owl": "http://www.w3.org/2002/07/owl#",
        "rdf": "http://www.w3.org/1999/02/22-rdf-syntax-ns#",
        "rdfs": "http://www.w3.org/2000/01/rdf-schema#",
        "xsd": _XSD_NS,
        "skos": "http://www.w3.org/2004/02/skos/core#",
        "dc": "http://purl.org/dc/elements/1.1/",
        "dcterms": "http://purl.org/dc/terms/",
        "foaf": "http://xmlns.com/foaf/0.1/",
        "sem": "https://semantica.dev/ns#",
        "semantica": "https://semantica.dev/ns#",
    }

    #: Schemes that really do introduce an absolute IRI without `//`.
    _ABSOLUTE_SCHEMES = ("urn:", "doi:", "mailto:", "tag:", "uuid:")

    @classmethod
    def _is_absolute_iri(cls, value: str) -> bool:
        if not isinstance(value, str):
            return False
        value = value.strip()
        if "://" in value:
            return bool(re.match(r"^[A-Za-z][A-Za-z0-9+.\-]*://", value))
        return value.lower().startswith(cls._ABSOLUTE_SCHEMES)

    @classmethod
    def _expand_prefixed_name(cls, value: str) -> str:
        """Expand a known prefixed name, or return "" when it cannot be expanded."""
        prefix, _, local = value.partition(":")
        namespace = cls._KNOWN_PREFIXES.get(prefix)
        return f"{namespace}{local}" if namespace and local else ""

    @staticmethod
    def _iri_safe(local: str) -> str:
        """
        Percent-encode a local name so it can sit inside <>.

        A name is free text. "Customer Account" pasted onto a base gives an IRI
        with a space in it, which rdflib only warns about and Oxigraph rejects
        with "Invalid IRI code point".
        """
        return quote(local.strip(), safe="~._-!$&'()*+,;=:@/?")

    @classmethod
    def _join_iri(cls, base: str, local: str) -> str:
        """Append a local name to a base IRI, respecting hash and slash bases."""
        if not base:
            return ""
        local = cls._iri_safe(local)
        if not local:
            return ""
        separator = "" if base.endswith(("#", "/", ":")) else "#"
        return f"{base}{separator}{local}"

    @classmethod
    def _term_iri(cls, term: Dict[str, Any], base: str) -> str:
        """
        Resolve the IRI of a class or property.

        Returns "" when the term carries nothing usable, so the caller can skip
        it. Interpolating an empty string into <> silently resolves against the
        parser's base — under rdflib that is the current working directory — and
        collapses every such term onto one subject.
        """
        for key in ("uri", "iri", "id"):
            value = term.get(key)
            if isinstance(value, str) and value.strip():
                value = value.strip()
                return value if cls._is_absolute_iri(value) else cls._join_iri(base, value)

        name = term.get("name") or term.get("label")
        if isinstance(name, str) and name.strip():
            return cls._join_iri(base, name.strip())
        return ""

    @classmethod
    def _class_iri_index(cls, ontology: Dict[str, Any], base: str) -> Dict[str, str]:
        """Map class name and label to the IRI that class is actually exported under."""
        index: Dict[str, str] = {}
        for class_def in ontology.get("classes", []) or []:
            if not isinstance(class_def, dict):
                continue
            iri = cls._term_iri(class_def, base)
            if not iri:
                continue
            for key in (class_def.get("name"), class_def.get("label")):
                if isinstance(key, str) and key.strip():
                    index.setdefault(key.strip(), iri)
        return index

    @classmethod
    def _resolve_class_ref(cls, value: Any, base: str, index: Dict[str, str]) -> str:
        """
        Resolve a domain/range reference to an absolute IRI.

        The generator writes bare class names here. Looking the name up in the
        class index first means a reference always lands on the IRI that class
        was exported under, rather than on a re-derived guess.
        """
        if not isinstance(value, str) or not value.strip():
            return ""
        value = value.strip()
        if cls._is_absolute_iri(value):
            return value
        if value in index:
            return index[value]
        if ":" in value:
            return cls._expand_prefixed_name(value)
        return cls._join_iri(base, value)

    @classmethod
    def _resolve_datatype_iri(cls, value: Any) -> str:
        """
        Resolve a data property range to an absolute datatype IRI.

        Accepts "string", "xsd:string" and a full IRI alike. The previous
        `xsd:{range}` interpolation doubled the prefix whenever the generator
        had already written "xsd:string".
        """
        if not isinstance(value, str) or not value.strip():
            return ""
        value = value.strip()
        if value.startswith(("xsd:", "XSD:")):
            return cls._XSD_NS + value.split(":", 1)[1]
        if cls._is_absolute_iri(value):
            return value
        return cls._XSD_NS + value

    @classmethod
    def _ttl_datatype_ref(cls, value: Any) -> str:
        """
        Render a data property range for Turtle.

        XSD datatypes are written with the xsd: prefix the header already
        declares; anything else is written as a full IRI. Both are the same
        term, this only keeps the compact style the module was written in.
        """
        iri = cls._resolve_datatype_iri(value)
        if not iri:
            return ""
        if iri.startswith(cls._XSD_NS):
            return f"xsd:{iri[len(cls._XSD_NS):]}"
        return f"<{iri}>"

    @classmethod
    def _split_properties(
        cls, ontology: Dict[str, Any]
    ) -> "tuple[List[Dict[str, Any]], List[Dict[str, Any]]]":
        """
        Return (object_properties, data_properties) across both dict shapes.

        A property listed under an explicit key keeps that key's kind. A
        property from the generator's combined `properties` list is classified
        by its own type/@type, defaulting to a data property.
        """
        object_props: List[Dict[str, Any]] = []
        data_props: List[Dict[str, Any]] = []

        for prop in ontology.get("object_properties", []) or []:
            if isinstance(prop, dict):
                object_props.append(prop)
        for prop in ontology.get("data_properties", []) or []:
            if isinstance(prop, dict):
                data_props.append(prop)

        skipped = 0
        untyped = []
        for prop in ontology.get("properties", []) or []:
            if not isinstance(prop, dict):
                skipped += 1
                continue
            kind = str(prop.get("type") or "").strip().lower()
            owl_type = str(prop.get("@type") or "").strip().lower()
            if kind in ("object", "objectproperty") or owl_type.endswith("objectproperty"):
                object_props.append(prop)
            else:
                if not kind and not owl_type:
                    untyped.append(prop.get("name") or prop.get("uri") or "<unnamed>")
                data_props.append(prop)

        if skipped:
            logger.warning(
                f"Skipped {skipped} entr(y/ies) in 'properties' that are not "
                "dictionaries and cannot be exported"
            )
        if untyped:
            logger.warning(
                "Exported as data properties because they declare no type or "
                f"@type: {', '.join(str(name) for name in untyped)}"
            )

        return object_props, data_props

    @staticmethod
    def _escape_xml(value: Any) -> str:
        """Escape a value for safe embedding in XML text or an attribute value."""
        return (
            str(value)
            .replace("&", "&amp;")
            .replace("<", "&lt;")
            .replace(">", "&gt;")
            .replace('"', "&quot;")
        )

    @staticmethod
    def _escape_ttl_str(value: str) -> str:
        """Escape a string value for safe embedding in a Turtle string literal."""
        return value.replace("\\", "\\\\").replace('"', '\\"').replace("\n", "\\n").replace("\r", "\\r").replace("\t", "\\t")

    def _ttl_block(self, subject_uri: str, rdf_type: str, predicates: List[str]) -> str:
        """Build a valid Turtle subject block from accumulated predicate strings."""
        stmt = f"<{subject_uri}> a {rdf_type}"
        for pred in predicates:
            stmt += f" ;\n    {pred}"
        return stmt + " ."

    def _export_owl_turtle(self, ontology: Dict[str, Any], **options) -> str:
        """
        Export ontology to OWL Turtle format.

        Turtle is a human-readable RDF serialization format. This method generates
        OWL ontology in Turtle syntax with namespace declarations and OWL constructs.

        Args:
            ontology: Ontology dictionary with classes, properties, etc.
            **options: Additional export options (unused)

        Returns:
            String containing OWL Turtle serialization
        """
        esc = self._escape_ttl_str
        ontology_uri = ontology.get("uri") or self.ontology_uri
        ontology_name = ontology.get("name", "SemanticaOntology")
        version = ontology.get("version") or self.version

        lines = []

        # Namespace declarations
        lines.append("@prefix rdf: <http://www.w3.org/1999/02/22-rdf-syntax-ns#> .")
        lines.append("@prefix rdfs: <http://www.w3.org/2000/01/rdf-schema#> .")
        lines.append("@prefix owl: <http://www.w3.org/2002/07/owl#> .")
        lines.append("@prefix xsd: <http://www.w3.org/2001/XMLSchema#> .")
        lines.append(f"@prefix ont: <{ontology_uri}> .")
        lines.append("")

        # Ontology declaration
        onto_predicates = [
            f'rdfs:label "{esc(ontology_name)}"',
            f'owl:versionInfo "{esc(version)}"',
        ]
        description = ontology.get("description")
        if description:
            onto_predicates.append(f'rdfs:comment "{esc(description)}"')
        lines.append(self._ttl_block(ontology_uri, "owl:Ontology", onto_predicates))
        lines.append("")

        class_index = self._class_iri_index(ontology, ontology_uri)
        object_properties, data_properties = self._split_properties(ontology)

        def _as_list(value):
            if value is None:
                return []
            return value if isinstance(value, list) else [value]

        # Classes
        for cls in ontology.get("classes", []) or []:
            if not isinstance(cls, dict):
                continue
            class_uri = self._term_iri(cls, ontology_uri)
            if not class_uri:
                self.logger.warning(
                    "Skipping a class with no name, uri or id: it would serialise as <>"
                )
                continue
            class_name = cls.get("name") or cls.get("label", "")
            predicates = [f'rdfs:label "{esc(class_name)}"']
            comment = cls.get("comment") or cls.get("description")
            if comment:
                predicates.append(f'rdfs:comment "{esc(comment)}"')
            for parent in _as_list(cls.get("subClassOf") or cls.get("parent")):
                parent_iri = self._resolve_class_ref(parent, ontology_uri, class_index)
                if parent_iri:
                    predicates.append(f"rdfs:subClassOf <{parent_iri}>")
            for equiv in _as_list(cls.get("equivalentClass")):
                equiv_iri = self._resolve_class_ref(equiv, ontology_uri, class_index)
                if equiv_iri:
                    predicates.append(f"owl:equivalentClass <{equiv_iri}>")
            lines.append(self._ttl_block(class_uri, "owl:Class", predicates))
            lines.append("")

        # Object properties
        for prop in object_properties:
            prop_uri = self._term_iri(prop, ontology_uri)
            if not prop_uri:
                self.logger.warning(
                    "Skipping an object property with no name, uri or id"
                )
                continue
            prop_name = prop.get("name") or prop.get("label", "")
            predicates = [f'rdfs:label "{esc(prop_name)}"']
            comment = prop.get("comment") or prop.get("description")
            if comment:
                predicates.append(f'rdfs:comment "{esc(comment)}"')
            for domain in _as_list(prop.get("domain")):
                domain_iri = self._resolve_class_ref(domain, ontology_uri, class_index)
                if domain_iri:
                    predicates.append(f"rdfs:domain <{domain_iri}>")
            for range_val in _as_list(prop.get("range")):
                range_iri = self._resolve_class_ref(range_val, ontology_uri, class_index)
                if range_iri:
                    predicates.append(f"rdfs:range <{range_iri}>")
            lines.append(self._ttl_block(prop_uri, "owl:ObjectProperty", predicates))
            lines.append("")

        # Data properties
        for prop in data_properties:
            prop_uri = self._term_iri(prop, ontology_uri)
            if not prop_uri:
                self.logger.warning("Skipping a data property with no name, uri or id")
                continue
            prop_name = prop.get("name") or prop.get("label", "")
            predicates = [f'rdfs:label "{esc(prop_name)}"']
            comment = prop.get("comment") or prop.get("description")
            if comment:
                predicates.append(f'rdfs:comment "{esc(comment)}"')
            for domain in _as_list(prop.get("domain")):
                domain_iri = self._resolve_class_ref(domain, ontology_uri, class_index)
                if domain_iri:
                    predicates.append(f"rdfs:domain <{domain_iri}>")
            for range_val in _as_list(prop.get("range")):
                range_ref = self._ttl_datatype_ref(range_val)
                if range_ref:
                    predicates.append(f"rdfs:range {range_ref}")
            lines.append(self._ttl_block(prop_uri, "owl:DatatypeProperty", predicates))
            lines.append("")

        return "\n".join(lines)

    def export_classes(
        self,
        classes: List[Dict[str, Any]],
        file_path: Union[str, Path],
        ontology_uri: Optional[str] = None,
        ontology_name: str = "SemanticaOntology",
        **options,
    ) -> None:
        """
        Export class definitions to OWL format.

        This method exports a list of class definitions to OWL format, creating
        a minimal ontology containing only the classes.

        Args:
            classes: List of class definition dictionaries with fields:
                - uri/id: Class URI/identifier
                - name/label: Class name/label
                - comment: Class description (optional)
                - subClassOf: Parent class URI (optional)
                - equivalentClass: Equivalent class URI (optional)
            file_path: Output OWL file path
            ontology_uri: Ontology URI (default: self.ontology_uri)
            ontology_name: Ontology name (default: "SemanticaOntology")
            **options: Additional options passed to export()

        Example:
            >>> classes = [
            ...     {"uri": "http://example.org/Person", "name": "Person"},
            ...     {"uri": "http://example.org/Organization", "name": "Organization"}
            ... ]
            >>> exporter.export_classes(classes, "classes.owl")
        """
        ontology = {
            "classes": classes,
            "uri": ontology_uri or self.ontology_uri,
            "name": ontology_name,
        }
        self.export(ontology, file_path, **options)

    def export_properties(
        self,
        properties: List[Dict[str, Any]],
        file_path: Union[str, Path],
        property_type: str = "object",
        ontology_uri: Optional[str] = None,
        ontology_name: str = "SemanticaOntology",
        **options,
    ) -> None:
        """
        Export property definitions to OWL format.

        This method exports a list of property definitions (object or data properties)
        to OWL format, creating a minimal ontology containing only the properties.

        Args:
            properties: List of property definition dictionaries with fields:
                - uri/id: Property URI/identifier
                - name/label: Property name/label
                - comment: Property description (optional)
                - domain: Domain class URI(s) (optional)
                - range: Range class URI or datatype (optional)
            file_path: Output OWL file path
            property_type: Property type - 'object' or 'data' (default: 'object')
            ontology_uri: Ontology URI (default: self.ontology_uri)
            ontology_name: Ontology name (default: "SemanticaOntology")
            **options: Additional options passed to export()

        Raises:
            ValidationError: If property_type is invalid

        Example:
            >>> properties = [
            ...     {
            ...         "uri": "http://example.org/hasName",
            ...         "name": "hasName",
            ...         "domain": "http://example.org/Person",
            ...         "range": "http://www.w3.org/2001/XMLSchema#string"
            ...     }
            ... ]
            >>> exporter.export_properties(properties, "properties.owl", property_type="data")
        """
        if property_type not in ["object", "data"]:
            raise ValidationError(
                f"Invalid property_type: {property_type}. "
                "Must be 'object' or 'data'."
            )

        ontology = {"uri": ontology_uri or self.ontology_uri, "name": ontology_name}

        # Add properties based on type
        if property_type == "object":
            ontology["object_properties"] = properties
        else:
            ontology["data_properties"] = properties

        self.export(ontology, file_path, **options)
