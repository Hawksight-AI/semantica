"""
Namespace and IRI Manager Module

This module manages ontology namespaces and generates consistent, human-readable
IRIs following best practices (speaking IRIs, version management). It provides
PascalCase for classes, camelCase for properties, and supports version-aware IRI
generation.

Key Features:
    - Define stable host namespaces
    - Generate consistent IRI conventions
    - PascalCase for classes
    - camelCase for properties and relations
    - Version-aware IRI management
    - Resolvable IRI generation
    - Speaking IRI support (human-readable)
    - Standard namespace registration (RDF, RDFS, OWL, XSD, SKOS, DC)

Main Classes:
    - NamespaceManager: Manager for namespaces and IRI generation

Example Usage:
    >>> from semantica.ontology import NamespaceManager
    >>> manager = NamespaceManager(base_uri="https://example.org/ontology/", version="1.0")
    >>> class_iri = manager.generate_class_iri("Person")
    >>> prop_iri = manager.generate_property_iri("hasName")
    >>> manager.register_namespace("ex", "https://example.org/")

Author: Semantica Contributors
License: MIT
"""

import re
from typing import Any, Dict, List, Optional
from urllib.parse import urljoin

from ..utils.exceptions import ProcessingError, ValidationError
from ..utils.logging import get_logger
from ..utils.progress_tracker import get_progress_tracker


class NamespaceManager:
    """
    Namespace and IRI management for ontologies.

    • Define stable host namespaces
    • Generate consistent IRI conventions
    • PascalCase for classes
    • camelCase for properties and relations
    • Version-aware IRI management
    • Resolvable IRI generation
    • Speaking IRI support (human-readable)
    """

    def __init__(self, config: Optional[Dict[str, Any]] = None, **kwargs):
        """
        Initialize namespace manager.

        Args:
            config: Configuration dictionary
            **kwargs: Additional configuration options:
                - base_uri: Base URI for the ontology
                - version: Ontology version
                - use_speaking_iris: Use human-readable IRIs (default: True)
        """
        self.logger = get_logger("namespace_manager")
        self.config = config or {}
        self.config.update(kwargs)

        # Initialize progress tracker
        self.progress_tracker = get_progress_tracker()
        # Ensure progress tracker is enabled
        if not self.progress_tracker.enabled:
            self.progress_tracker.enabled = True

        self.base_uri = self.config.get("base_uri", "https://semantica.dev/ontology/")
        self.version = self.config.get("version", "1.0")
        self.use_speaking_iris = self.config.get("use_speaking_iris", True)

        # Standard namespaces
        self.namespaces = {
            "rdf": "http://www.w3.org/1999/02/22-rdf-syntax-ns#",
            "rdfs": "http://www.w3.org/2000/01/rdf-schema#",
            "owl": "http://www.w3.org/2002/07/owl#",
            "xsd": "http://www.w3.org/2001/XMLSchema#",
            "skos": "http://www.w3.org/2004/02/skos/core#",
            "dc": "http://purl.org/dc/elements/1.1/",
            "dcterms": "http://purl.org/dc/terms/",
        }

    def get_base_uri(self) -> str:
        """
        Get base URI for ontology.

        Returns:
            Base URI string
        """
        if self.version and self.version != "1.0":
            return urljoin(self.base_uri.rstrip("/") + "/", f"v{self.version}/")
        return self.base_uri

    def generate_class_iri(self, class_name: str, **options) -> str:
        """
        Generate IRI for class (PascalCase).

        Args:
            class_name: Class name
            **options: Additional options

        Returns:
            Class IRI
        """
        # Convert to PascalCase
        class_name = self._to_pascal_case(class_name)

        # Generate speaking IRI if enabled
        if self.use_speaking_iris:
            iri = urljoin(self.get_base_uri(), class_name)
        else:
            # Use hash-based IRI
            import hashlib

            hash_id = hashlib.md5(class_name.encode()).hexdigest()[:8]  # nosec B324 - deterministic IRI suffix, not security-sensitive
            iri = urljoin(self.get_base_uri(), f"class/{hash_id}")

        return iri

    def generate_property_iri(self, property_name: str, **options) -> str:
        """
        Generate IRI for property (camelCase).

        Args:
            property_name: Property name
            **options: Additional options

        Returns:
            Property IRI
        """
        # Convert to camelCase
        property_name = self._to_camel_case(property_name)

        # Generate speaking IRI if enabled
        if self.use_speaking_iris:
            iri = urljoin(self.get_base_uri(), property_name)
        else:
            # Use hash-based IRI
            import hashlib

            hash_id = hashlib.md5(property_name.encode()).hexdigest()[:8]  # nosec B324 - deterministic IRI suffix, not security-sensitive
            iri = urljoin(self.get_base_uri(), f"property/{hash_id}")

        return iri

    def generate_individual_iri(self, individual_name: str, **options) -> str:
        """
        Generate IRI for individual instance.

        Args:
            individual_name: Individual name
            **options: Additional options

        Returns:
            Individual IRI
        """
        # Clean and normalize name
        individual_name = re.sub(r"[^a-zA-Z0-9]", "", individual_name)

        if self.use_speaking_iris:
            iri = urljoin(self.get_base_uri(), f"individual/{individual_name}")
        else:
            import hashlib

            hash_id = hashlib.md5(individual_name.encode()).hexdigest()[:8]  # nosec B324 - deterministic IRI suffix, not security-sensitive
            iri = urljoin(self.get_base_uri(), f"individual/{hash_id}")

        return iri

    def register_namespace(self, prefix: str, uri: str) -> None:
        """
        Register a namespace.

        Args:
            prefix: Namespace prefix
            uri: Namespace URI
        """
        self.namespaces[prefix] = uri
        self.logger.debug(f"Registered namespace: {prefix} -> {uri}")

    def get_namespace(self, prefix: str) -> Optional[str]:
        """
        Get namespace URI by prefix.

        Args:
            prefix: Namespace prefix

        Returns:
            Namespace URI or None
        """
        return self.namespaces.get(prefix)

    def get_all_namespaces(self) -> Dict[str, str]:
        """
        Get all registered namespaces.

        Returns:
            Dictionary of prefix -> URI mappings
        """
        return dict(self.namespaces)
    
    def get_skos_uri(self, local_name: str) -> str:
        """
        Build a full SKOS URI from a local name.

        Args:
            local_name: SKOS local term (e.g. ``"Concept"``, ``"prefLabel"``)

        Returns:
            Full SKOS URI string
        """
        skos_ns = self.namespaces["skos"]
        return f"{skos_ns}{local_name}"

    def build_concept_scheme_uri(self, name: str) -> str:
        """
        Build a ConceptScheme URI anchored at the current base URI.

        The scheme name is slugified (spaces → hyphens, lower-cased) so that
        ``"My Vocabulary"`` becomes ``<base>/vocab/my-vocabulary>``.

        Args:
            name: Human-readable vocabulary name

        Returns:
            ConceptScheme URI string
        """
        slug = re.sub(r"[^a-zA-Z0-9]+", "-", name).strip("-").lower()
        return urljoin(self.get_base_uri(), f"vocab/{slug}")

    def get_alignment_predicates(self) -> Dict[str, str]:
        """
        Get standard alignment predicates for ontology mapping.
        
        Returns:
            Dictionary mapping common alignment types to their full URIs.
        """
        owl_ns = self.get_namespace("owl")
        skos_ns = self.get_namespace("skos")
        
        return {
            #OWL alignments
            "equivalentClass": f"{owl_ns}equivalentClass",
            "equivalentProperty": f"{owl_ns}equivalentProperty",
            "sameAs": f"{owl_ns}sameAs",
            #SKOS alignments
            "exactMatch": f"{skos_ns}exactMatch",
            "closeMatch": f"{skos_ns}closeMatch",
            "broadMatch": f"{skos_ns}broadMatch",
            "narrowMatch": f"{skos_ns}narrowMatch",
            "relatedMatch": f"{skos_ns}relatedMatch",
            
        }
        

    def _to_pascal_case(self, name: str) -> str:
        """Convert name to PascalCase."""
        # Remove special characters and split
        words = re.findall(r"[a-zA-Z0-9]+", name)
        if not words:
            return "Entity"

        # Capitalize first letter of each word
        return "".join(word.capitalize() for word in words)

    def _to_camel_case(self, name: str) -> str:
        """Convert name to camelCase."""
        # Check if already likely camelCase (starts with lower, has upper, single word)
        if name and name[0].islower() and any(c.isupper() for c in name) and ' ' not in name and '_' not in name:
            return name

        # Remove special characters and split
        words = re.findall(r"[a-zA-Z0-9]+", name)
        if not words:
            return "hasProperty"

        # First word lowercase, rest capitalized
        return words[0].lower() + "".join(word.capitalize() for word in words[1:])

    def validate_iri(self, iri: str) -> bool:
        """
        Validate IRI format.

        Args:
            iri: IRI to validate

        Returns:
            True if valid
        """
        tracking_id = self.progress_tracker.start_tracking(
            module="ontology",
            submodule="NamespaceManager",
            message=f"Validating IRI: {iri[:50]}...",
        )

        try:
            # Basic IRI validation
            from urllib.parse import urlparse

            parsed = urlparse(iri)
            is_valid = bool(parsed.scheme and parsed.netloc)

            self.progress_tracker.stop_tracking(
                tracking_id,
                status="completed",
                message=f"IRI validation: {'Valid' if is_valid else 'Invalid'}",
            )
            return is_valid

        except Exception as e:
            self.progress_tracker.stop_tracking(
                tracking_id, status="failed", message=str(e)
            )
            return False
