"""
Ontology Generation Module

This module handles automatic generation of ontologies from data and text using
a 6-stage pipeline that transforms raw data into structured OWL ontologies.

Key Features:
    - Automatic ontology generation (6-stage pipeline)
    - Class and property inference
    - Ontology structure optimization
    - Domain-specific ontology creation
    - Ontology quality assessment
    - Semantic network parsing
    - Hierarchy generation

Main Classes:
    - OntologyGenerator: Main ontology generation class (6-stage pipeline)
    - ClassInferencer: Class inference engine (legacy alias)
    - PropertyInferencer: Property inference engine (legacy alias)
    - OntologyOptimizer: Ontology optimization engine

Example Usage:
    >>> from semantica.ontology import OntologyGenerator
    >>> generator = OntologyGenerator(base_uri="https://example.org/ontology/")
    >>> ontology = generator.generate_ontology({"entities": [...], "relationships": [...]})
    >>> classes = generator.infer_classes(data)
    >>> properties = generator.infer_properties(data, classes)

Author: Semantica Contributors
License: MIT
"""

import re
from dataclasses import dataclass, field, replace as dataclass_replace
from datetime import datetime
from typing import Any, Dict, List, Optional
from urllib.parse import quote

from ..utils.exceptions import ProcessingError, ValidationError
from ..utils.logging import get_logger
from ..utils.progress_tracker import get_progress_tracker
from .class_inferrer import ClassInferrer
from .namespace_manager import NamespaceManager
from .naming_conventions import NamingConventions
from .property_generator import PropertyGenerator
from .ontology_validator import OntologyValidator


class OntologyGenerator:
    """
    Ontology generation handler with 6-stage pipeline.

    6-Stage Pipeline:
    1. Semantic Network Parsing → Extract domain concepts
    2. YAML-to-Definition → Transform into class definitions
    3. Definition-to-Types → Map to OWL types
    4. Hierarchy Generation → Build taxonomic structures
    5. TTL Generation → Generate OWL/Turtle syntax using rdflib, triplet generation (subject-predicate-object)
    6. Symbolic Validation → HermiT/Pellet reasoning

    • Generates ontologies from data and text
    • Infers classes and properties automatically
    • Creates domain-specific ontologies
    • Optimizes ontology structure
    • Validates ontology quality
    • Supports various ontology formats
    """

    def __init__(self, config=None, **kwargs):
        """
        Initialize ontology generator.

        Sets up the ontology generator with namespace management, naming conventions,
        and inference engines for classes and properties.

        Args:
            config: Configuration dictionary
            **kwargs: Additional configuration options:
                - base_uri: Base URI for ontology (default: "https://semantica.dev/ontology/")
                - namespace_manager: Optional namespace manager instance
                - min_occurrences: Minimum occurrences for class inference (default: 2)

        Example:
            ```python
            generator = OntologyGenerator(
                base_uri="https://example.org/ontology/",
                min_occurrences=3
            )
            ```
        """
        self.logger = get_logger("ontology_generator")
        self.config = config or {}
        self.config.update(kwargs)

        # Initialize progress tracker
        self.progress_tracker = get_progress_tracker()
        # Ensure progress tracker is enabled
        if not self.progress_tracker.enabled:
            self.progress_tracker.enabled = True

        # Initialize components
        self.namespace_manager = self.config.get(
            "namespace_manager"
        ) or NamespaceManager(**self.config)
        self.naming_conventions = NamingConventions(**self.config)
        self.class_inferrer = ClassInferrer(
            namespace_manager=self.namespace_manager, **self.config
        )
        self.property_generator = PropertyGenerator(
            namespace_manager=self.namespace_manager, **self.config
        )
        self.validator = OntologyValidator(**self.config)

        self.supported_formats = ["owl", "ttl", "rdf", "json-ld"]

    def generate_ontology(self, data: Dict[str, Any], **options) -> Dict[str, Any]:
        """
        Generate ontology from data using 5-stage pipeline.

        Executes the complete 5-stage ontology generation pipeline:
        1. Semantic Network Parsing: Extract domain concepts from entities/relationships
        2. YAML-to-Definition: Transform concepts into class definitions
        3. Definition-to-Types: Map definitions to OWL types
        4. Hierarchy Generation: Build taxonomic structures
        5. TTL Generation: (Handled by OWLGenerator)

        Args:
            data: Input data dictionary containing:
                - entities: List of entity dictionaries
                - relationships: List of relationship dictionaries
                - semantic_network: Optional pre-parsed semantic network
            **options: Generation options:
                - name: Ontology name (default: "GeneratedOntology")
                - build_hierarchy: Whether to build class hierarchy (default: True)
                - namespace_manager: Optional namespace manager instance

        Returns:
            Generated ontology dictionary containing:
                - uri: Ontology URI
                - name: Ontology name
                - version: Version string
                - classes: List of class definitions
                - properties: List of property definitions
                - metadata: Additional metadata

        Example:
            ```python
            generator = OntologyGenerator(base_uri="https://example.org/ontology/")
            ontology = generator.generate_ontology({
                "entities": [{"type": "Person", "name": "John"}],
                "relationships": [{"type": "worksFor", "source": "John", "target": "Acme"}]
            })
            ```
        """
        tracking_id = self.progress_tracker.start_tracking(
            module="ontology",
            submodule="OntologyGenerator",
            message="Generating ontology using 6-stage pipeline",
        )

        try:
            self.logger.info("Starting ontology generation pipeline")

            # Stage 1: Semantic Network Parsing
            self.progress_tracker.update_tracking(
                tracking_id, message="Stage 1: Parsing semantic network..."
            )
            semantic_network = self._stage1_parse_semantic_network(data, **options)

            # Stage 2: YAML-to-Definition
            self.progress_tracker.update_tracking(
                tracking_id, message="Stage 2: Converting to class definitions..."
            )
            definitions = self._stage2_yaml_to_definition(semantic_network, **options)

            # Stage 3: Definition-to-Types
            self.progress_tracker.update_tracking(
                tracking_id, message="Stage 3: Mapping to OWL types..."
            )
            
            # Ensure entities and relationships are available for property inference
            stage3_options = options.copy()
            # Use normalized entities and relationships from stage 1 if available
            stage3_options["entities"] = semantic_network.get("entities", data.get("entities", []))
            stage3_options["relationships"] = semantic_network.get("relationships", data.get("relationships", []))
            
            typed_definitions = self._stage3_definition_to_types(definitions, **stage3_options)

            # Stage 4: Hierarchy Generation
            self.progress_tracker.update_tracking(
                tracking_id, message="Stage 4: Building class hierarchy..."
            )
            ontology = self._stage4_hierarchy_generation(typed_definitions, **options)

            # Stage 5: TTL Generation (handled by OWLGenerator)

            # Stage 6: Symbolic Validation
            if options.get("validate", True):
                self.progress_tracker.update_tracking(
                    tracking_id, message="Stage 6: Validating ontology..."
                )
                validation_result = self.validator.validate(ontology)
                ontology["validation"] = {
                    "valid": validation_result.valid,
                    "consistent": validation_result.consistent,
                    "satisfiable": validation_result.satisfiable,
                    "errors": validation_result.errors,
                    "warnings": validation_result.warnings
                }
                if not validation_result.valid:
                    self.logger.warning(f"Ontology validation failed: {validation_result.errors}")

            self.progress_tracker.stop_tracking(
                tracking_id,
                status="completed",
                message=f"Generated ontology with {len(ontology.get('classes', []))} classes, {len(ontology.get('properties', []))} properties",
            )
            return ontology

        except Exception as e:
            self.progress_tracker.stop_tracking(
                tracking_id, status="failed", message=str(e)
            )
            raise

    def generate_from_graph(self, graph: Dict[str, Any], **options) -> Dict[str, Any]:
        """
        Generate ontology from a knowledge graph.

        Alias for generate_ontology.

        Args:
            graph: Knowledge graph dictionary (output from GraphBuilder)
            **options: Additional options

        Returns:
            Generated ontology dictionary
        """
        return self.generate_ontology(graph, **options)

    def _stage1_parse_semantic_network(
        self, data: Dict[str, Any], **options
    ) -> Dict[str, Any]:
        """
        Stage 1: Parse semantic network from data.

        Extract domain concepts from entities and relationships.
        """
        raw_entities = data.get("entities", [])
        relationships = data.get("relationships", [])

        # Normalize entities
        entities = []

        def process_entity(ent):
            """Normalize entity to dictionary."""
            if isinstance(ent, dict):
                return ent
            # Handle Entity object (from NERExtractor)
            if hasattr(ent, "label") and hasattr(ent, "text"):
                return {
                    "type": ent.label,
                    "name": ent.text,
                    "entity_type": ent.label,
                    "text": ent.text,
                    "start_char": getattr(ent, "start_char", 0),
                    "end_char": getattr(ent, "end_char", 0),
                    "confidence": getattr(ent, "confidence", 1.0),
                    "metadata": getattr(ent, "metadata", {}),
                }
            # Handle list/tuple (legacy or raw format)
            if isinstance(ent, (list, tuple)) and len(ent) >= 2:
                # Assume [text, label, ...]
                return {
                    "name": str(ent[0]),
                    "text": str(ent[0]),
                    "type": str(ent[1]),
                    "entity_type": str(ent[1]),
                }
            return None

        # Handle list of lists (batch output) or flat list
        for item in raw_entities:
            if isinstance(item, list):
                # Check if it's a list of entities (batch) or a single entity as list
                # If the first element is also a list or Entity object, it's a batch
                if len(item) > 0 and (
                    isinstance(item[0], list) or hasattr(item[0], "label")
                ):
                    for sub_item in item:
                        processed = process_entity(sub_item)
                        if processed:
                            entities.append(processed)
                else:
                    # Treat as single entity [text, label]
                    processed = process_entity(item)
                    if processed:
                        entities.append(processed)
            else:
                processed = process_entity(item)
                if processed:
                    entities.append(processed)

        # Extract concepts
        concepts = {}
        for entity in entities:
            entity_type = entity.get("type") or entity.get("entity_type", "Entity")
            if entity_type not in concepts:
                concepts[entity_type] = {"instances": [], "relationships": []}
            concepts[entity_type]["instances"].append(entity)

        entity_aliases = self._build_entity_aliases(entities)

        # Extract relationships
        normalized_relationships = []
        for rel_item in relationships:
            # Normalize relationship to dictionary
            rel = None
            if isinstance(rel_item, dict):
                rel = dict(rel_item)
            elif hasattr(rel_item, "subject") and hasattr(rel_item, "predicate") and hasattr(rel_item, "object"):
                # Handle Relation object (subject, predicate, object)
                rel = {
                    "source": getattr(rel_item, "subject"),
                    "type": getattr(rel_item, "predicate"),
                    "target": getattr(rel_item, "object"),
                    "relationship_type": getattr(rel_item, "predicate"),
                    "source_type": getattr(rel_item, "source_type", "Entity"),
                    "target_type": getattr(rel_item, "target_type", "Entity"),
                    "confidence": getattr(rel_item, "confidence", 1.0),
                    "metadata": getattr(rel_item, "metadata", {}),
                }
            elif hasattr(rel_item, "source") and hasattr(rel_item, "type") and hasattr(rel_item, "target"):
                 # Handle Relation object (source, type, target) - alternative
                rel = {
                    "source": getattr(rel_item, "source"),
                    "type": getattr(rel_item, "type"),
                    "target": getattr(rel_item, "target"),
                    "relationship_type": getattr(rel_item, "type"),
                    "source_type": getattr(rel_item, "source_type", "Entity"),
                    "target_type": getattr(rel_item, "target_type", "Entity"),
                    "confidence": getattr(rel_item, "confidence", 1.0),
                    "metadata": getattr(rel_item, "metadata", {}),
                }
            elif isinstance(rel_item, (list, tuple)) and len(rel_item) >= 3:
                # Assume [source, type, target] (RDF triplet style)
                # or [source, target, type]
                # Heuristic: if 2nd element is short and looks like a relation, assume [source, type, target]
                rel = {
                    "source": str(rel_item[0]),
                    "type": str(rel_item[1]),
                    "target": str(rel_item[2]),
                    "relationship_type": str(rel_item[1]),
                    "source_type": "Entity",
                    "target_type": "Entity",
                }
            
            if not rel:
                continue

            source_type = self._resolve_relationship_endpoint_type(
                rel, "source", entity_aliases
            )
            target_type = self._resolve_relationship_endpoint_type(
                rel, "target", entity_aliases
            )
            
            # Update rel with resolved types
            rel["source_type"] = source_type
            rel["target_type"] = target_type
            
            normalized_relationships.append(rel)

            if source_type and source_type in concepts:
                concepts[source_type]["relationships"].append(rel)

        return {
            "concepts": concepts,
            "entities": entities,
            "relationships": normalized_relationships,
        }

    @staticmethod
    def _build_entity_aliases(entities: List[Dict[str, Any]]) -> Dict[str, set]:
        """Build an unambiguous alias-to-type index for relationship endpoints."""
        aliases: Dict[str, set] = {}
        for entity in entities:
            entity_type = entity.get("type") or entity.get("entity_type")
            if not entity_type:
                continue

            for key in ("id", "entity_id", "name", "text", "label"):
                if key not in entity or entity[key] is None or entity[key] == "":
                    continue
                aliases.setdefault(str(entity[key]), set()).add(entity_type)

        return aliases

    @staticmethod
    def _get_relationship_endpoint(rel: Dict[str, Any], endpoint: str) -> Any:
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

    def _resolve_relationship_endpoint_type(
        self, rel: Dict[str, Any], endpoint: str, aliases: Dict[str, set]
    ) -> Optional[str]:
        """Resolve an endpoint type without treating missing fields as aliases."""
        explicit_type = rel.get(f"{endpoint}_type")
        if explicit_type and explicit_type != "Entity":
            return explicit_type

        endpoint_value = self._get_relationship_endpoint(rel, endpoint)
        if endpoint_value is not None:
            candidates = aliases.get(str(endpoint_value), set())
            if len(candidates) == 1:
                return next(iter(candidates))

        return explicit_type

    def _stage2_yaml_to_definition(
        self, semantic_network: Dict[str, Any], **options
    ) -> Dict[str, Any]:
        """
        Stage 2: Transform semantic network to class definitions.

        Convert concepts to structured class definitions.
        """
        concepts = semantic_network.get("concepts", {})
        entities = semantic_network.get("entities", [])

        # Infer classes from entities
        classes = self.class_inferrer.infer_classes(entities, **options)

        # Create definitions
        definitions = {
            "classes": classes,
            "properties": [],
            "metadata": {
                "generated_at": datetime.now().isoformat(),
                "concept_count": len(concepts),
            },
        }

        return definitions

    def _stage3_definition_to_types(
        self, definitions: Dict[str, Any], **options
    ) -> Dict[str, Any]:
        """
        Stage 3: Map definitions to OWL types.

        Convert class definitions to OWL-compliant types.
        """
        classes = definitions.get("classes", [])
        relationships = options.get("relationships", [])
        entities = options.get("entities", [])

        # Clean options for infer_properties to avoid multiple values for arguments
        prop_options = options.copy()
        prop_options.pop("entities", None)
        prop_options.pop("relationships", None)

        # Infer properties
        properties = self.property_generator.infer_properties(
            entities=entities, relationships=relationships, classes=classes, **prop_options
        )

        # Add types to classes.
        # ClassInferrer sets "uri": None when it was given no namespace manager,
        # so the key is present and a `not in` guard never fires: every class
        # then reached the exporters with no IRI at all (#1103).
        for cls in classes:
            cls["@type"] = "owl:Class"
            if not cls.get("uri"):
                cls["uri"] = self.namespace_manager.generate_class_iri(cls["name"])

        # Add types to properties
        for prop in properties:
            if prop["type"] == "object":
                prop["@type"] = "owl:ObjectProperty"
            else:
                prop["@type"] = "owl:DatatypeProperty"

            if not prop.get("uri"):
                prop["uri"] = self.namespace_manager.generate_property_iri(prop["name"])

        return {
            "classes": classes,
            "properties": properties,
            "metadata": definitions.get("metadata", {}),
        }

    def _stage4_hierarchy_generation(
        self, typed_definitions: Dict[str, Any], **options
    ) -> Dict[str, Any]:
        """
        Stage 4: Build taxonomic structures.

        Generate class hierarchies and property relationships.
        """
        classes = typed_definitions.get("classes", [])
        properties = typed_definitions.get("properties", [])

        # Build class hierarchy
        classes = self.class_inferrer.build_class_hierarchy(classes, **options)

        # Build ontology structure
        ontology = {
            "uri": self.namespace_manager.get_base_uri(),
            "name": options.get("name", "GeneratedOntology"),
            "version": self.namespace_manager.version,
            "classes": classes,
            "properties": properties,
            "imports": [],
            "metadata": {
                **typed_definitions.get("metadata", {}),
                "class_count": len(classes),
                "property_count": len(properties),
            },
        }

        return ontology

    def infer_classes(self, data: Dict[str, Any], **options) -> List[Dict[str, Any]]:
        """
        Infer ontology classes from data.

        Args:
            data: Input data
            **options: Additional options

        Returns:
            List of inferred classes
        """
        entities = data.get("entities", [])
        return self.class_inferrer.infer_classes(entities, **options)

    def infer_properties(
        self, data: Dict[str, Any], classes: List[Dict[str, Any]], **options
    ) -> List[Dict[str, Any]]:
        """
        Infer ontology properties from data.

        Args:
            data: Input data
            classes: List of class definitions
            **options: Additional options

        Returns:
            List of inferred properties
        """
        entities = data.get("entities", [])
        relationships = data.get("relationships", [])

        return self.property_generator.infer_properties(
            entities=entities, relationships=relationships, classes=classes, **options
        )

    def optimize_ontology(self, ontology: Dict[str, Any], **options) -> Dict[str, Any]:
        """
        Optimize ontology structure and quality.

        Args:
            ontology: Ontology dictionary
            **options: Additional options

        Returns:
            Optimized ontology
        """
        optimizer = OntologyOptimizer(**self.config)
        return optimizer.optimize_ontology(ontology, **options)


class ClassInferencer:
    """
    Class inference engine (legacy compatibility).

    • Infers ontology classes from data
    • Handles class hierarchies
    • Manages class relationships
    • Processes class constraints
    """

    def __init__(self, **config):
        """Initialize class inferencer."""
        self.class_inferrer = ClassInferrer(**config)

    def infer_classes(self, data, **options):
        """Infer classes from data."""
        entities = data.get("entities", []) if isinstance(data, dict) else data
        return self.class_inferrer.infer_classes(entities, **options)

    def build_class_hierarchy(self, classes, **options):
        """Build class hierarchy."""
        return self.class_inferrer.build_class_hierarchy(classes, **options)

    def validate_classes(self, classes, **criteria):
        """Validate classes."""
        return self.class_inferrer.validate_classes(classes, **criteria)


class PropertyInferencer:
    """
    Property inference engine (legacy compatibility).

    • Infers ontology properties from data
    • Handles property domains and ranges
    • Manages property relationships
    • Processes property constraints
    """

    def __init__(self, **config):
        """Initialize property inferencer."""
        self.property_generator = PropertyGenerator(**config)

    def infer_properties(self, data, classes, **options):
        """Infer properties from data and classes."""
        entities = data.get("entities", []) if isinstance(data, dict) else []
        relationships = data.get("relationships", []) if isinstance(data, dict) else []

        return self.property_generator.infer_properties(
            entities=entities, relationships=relationships, classes=classes, **options
        )

    def infer_domains_and_ranges(self, properties, classes):
        """Infer domains and ranges."""
        return self.property_generator.infer_domains_and_ranges(properties, classes)

    def validate_properties(self, properties, **criteria):
        """Validate properties."""
        return self.property_generator.validate_properties(properties, **criteria)


class OntologyOptimizer:
    """
    Ontology optimization engine.

    • Optimizes ontology structure
    • Removes redundant elements
    • Improves ontology coherence
    • Manages optimization metrics
    """

    def __init__(self, **config):
        """
        Initialize ontology optimizer.

        Args:
            **config: Configuration options
        """
        self.logger = get_logger("ontology_optimizer")
        self.config = config

    def optimize_ontology(self, ontology: Dict[str, Any], **options) -> Dict[str, Any]:
        """
        Optimize ontology structure.

        Args:
            ontology: Ontology dictionary
            **options: Additional options

        Returns:
            Optimized ontology
        """
        optimized = dict(ontology)

        # Remove redundancy
        if options.get("remove_redundancy", True):
            optimized = self.remove_redundancy(optimized)

        # Improve coherence
        if options.get("improve_coherence", True):
            optimized = self.improve_coherence(optimized)

        return optimized

    def remove_redundancy(self, ontology: Dict[str, Any]) -> Dict[str, Any]:
        """
        Remove redundant elements from ontology.

        Args:
            ontology: Ontology dictionary

        Returns:
            Cleaned ontology
        """
        # Remove duplicate classes
        classes = ontology.get("classes", [])
        seen_names = set()
        unique_classes = []

        for cls in classes:
            class_name = cls.get("name")
            if class_name and class_name not in seen_names:
                seen_names.add(class_name)
                unique_classes.append(cls)

        ontology["classes"] = unique_classes

        # Remove duplicate properties
        properties = ontology.get("properties", [])
        seen_prop_names = set()
        unique_properties = []

        for prop in properties:
            prop_name = prop.get("name")
            if prop_name and prop_name not in seen_prop_names:
                seen_prop_names.add(prop_name)
                unique_properties.append(prop)

        ontology["properties"] = unique_properties

        return ontology

    def improve_coherence(self, ontology: Dict[str, Any]) -> Dict[str, Any]:
        """
        Improve ontology coherence.

        Args:
            ontology: Ontology dictionary

        Returns:
            Improved ontology
        """
        # Ensure all classes have required fields. Both guards used `not in`,
        # which misses a key that is present and None, and the URI fallback
        # assigned a bare class name where an absolute IRI is required (#1103).
        #
        # The base comes from the ontology being optimized. OntologyOptimizer
        # holds no namespace manager, so reaching for one here would raise
        # AttributeError on every ontology carrying a class with no URI.
        base_uri = ontology.get("uri") or DEFAULT_ONTOLOGY_BASE_URI
        classes = ontology.get("classes", [])
        for cls in classes:
            if not cls.get("uri"):
                cls["uri"] = _mint_term_iri(base_uri, cls.get("name", "Entity"))
            if not cls.get("label"):
                cls["label"] = cls.get("name", "Entity")

        # Ensure all properties have domains and ranges
        properties = ontology.get("properties", [])
        for prop in properties:
            if prop.get("type") == "object":
                if "domain" not in prop or not prop["domain"]:
                    prop["domain"] = ["owl:Thing"]
                if "range" not in prop or not prop["range"]:
                    prop["range"] = ["owl:Thing"]

        return ontology


# ─────────────────────────────────────────────────────────────────────────────
# SHACL Shape Generation
# ─────────────────────────────────────────────────────────────────────────────


@dataclass
class PropertyShape:
    """Internal model for a SHACL sh:PropertyShape."""
    path: str
    name: Optional[str] = None
    description: Optional[str] = None
    datatype: Optional[str] = None       # sh:datatype
    class_: Optional[str] = None         # sh:class
    min_count: Optional[int] = None
    max_count: Optional[int] = None
    in_values: Optional[List[str]] = None
    has_value: Optional[str] = None
    pattern: Optional[str] = None
    severity: str = "Violation"


@dataclass
class NodeShape:
    """Internal model for a SHACL sh:NodeShape."""
    target_class: str
    name: Optional[str] = None
    description: Optional[str] = None
    property_shapes: List[PropertyShape] = field(default_factory=list)
    closed: bool = False
    severity: str = "Violation"


#: Used when an ontology carries no URI of its own.
DEFAULT_ONTOLOGY_BASE_URI = "https://semantica.dev/ontology/"


def _mint_term_iri(base_uri: str, name: str) -> str:
    """
    Mint an absolute IRI for a term from a base and a name.

    The name is percent-encoded: names are free text, and "Customer Account"
    pasted onto a base gives an IRI with a space in it, which strict parsers
    reject outright.
    """
    local = quote(str(name).strip(), safe="~._-!$&'()*+,;=:@")
    if not local:
        local = "Entity"
    separator = "" if base_uri.endswith(("#", "/", ":")) else "#"
    return f"{base_uri}{separator}{local}"


@dataclass
class SHACLGraph:
    """Internal model representing the complete SHACL shapes graph."""
    base_uri: str
    shapes_uri: str
    node_shapes: List[NodeShape] = field(default_factory=list)
    prefixes: Dict[str, str] = field(default_factory=dict)
    # Bare names mapped to the absolute IRI the data uses for them. Shapes are
    # indexed internally by name; this is what those names expand to at
    # serialisation time (#1104). Classes and properties are kept apart because
    # a property may legitimately share a class's name, and a single map would
    # silently give it the class's IRI.
    class_iris: Dict[str, str] = field(default_factory=dict)
    property_iris: Dict[str, str] = field(default_factory=dict)


class SHACLGenerator:
    """
    Generates SHACL shapes from Semantica OWL ontology dicts.

    6-stage internal pipeline:
        1. _build_class_index()       — {class_name: class_dict} for O(1) lookup
        2. _generate_node_shapes()    — one NodeShape per OWL class
        3. _attach_property_shapes()  — map properties to their domain node shapes
        4. _propagate_inheritance()   — copy parent shapes to children (iterative, cycle-safe)
        5. _apply_quality_tier()      — strict tier: set closed=True on all shapes
        6. serialize()                — Turtle / JSON-LD / N-Triples
    """

    _XSD_ALIASES: Dict[str, str] = {
        "string": "xsd:string", "str": "xsd:string",
        "int": "xsd:integer", "integer": "xsd:integer",
        "float": "xsd:decimal", "decimal": "xsd:decimal",
        "boolean": "xsd:boolean", "bool": "xsd:boolean",
        "date": "xsd:date",
        "datetime": "xsd:dateTime",
        "uri": "xsd:anyURI", "anyuri": "xsd:anyURI",
    }

    def __init__(
        self,
        base_uri: str = "https://semantica.dev/shapes/",
        shapes_uri: Optional[str] = None,
        include_inherited: bool = True,
        severity: str = "Violation",
        quality_tier: str = "standard",
        target_namespace: Optional[str] = None,
        attach_domainless_properties: bool = False,
        config: Optional[Dict[str, Any]] = None,
    ):
        """
        Args:
            base_uri: Namespace the shape resources themselves live in.
            target_namespace: Namespace the terms being validated live in, used
                to expand sh:targetClass and sh:path when the ontology does not
                supply absolute IRIs. This is deliberately separate from
                base_uri: shapes that target their own namespace match nothing,
                and pySHACL reports that as conforming (#1104).
            attach_domainless_properties: When True, a property with no declared
                domain is attached to every node shape, which is the pre-0.6.6
                behaviour. It invents a constraint the ontology never stated, so
                it is off by default (#1105).
        """
        self.logger = get_logger("ontology_shacl")
        self.progress_tracker = get_progress_tracker()
        # Preserve an RDF namespace that already ends in `#` (the common
        # convention for vocabularies): `...manufacturing#` must not become
        # `...manufacturing#/`, or every generated URI lands in the wrong
        # namespace and SHACL validation silently targets nothing. Matches
        # the `#`-aware normalization in `generate()`. Slash-terminated
        # bases are collapsed to a single trailing `/` so redundant runs
        # (`.../ns////`) cannot leak a different namespace into emitted IRIs.
        self.base_uri = (
            base_uri if base_uri.endswith("#") else base_uri.rstrip("/") + "/"
        )
        self.shapes_uri = shapes_uri or (self.base_uri + "shapes")
        self.include_inherited = include_inherited
        self.severity = severity
        self.quality_tier = quality_tier
        self.target_namespace = target_namespace
        self.attach_domainless_properties = attach_domainless_properties
        self.config = config or {}

    # ── Public API ────────────────────────────────────────────────────────────

    def generate(self, ontology: Dict[str, Any], **options) -> SHACLGraph:
        """Generate a SHACLGraph from a Semantica ontology dict."""
        if not isinstance(ontology, dict):
            raise ValueError("ontology must be a dict")
        if "classes" not in ontology and "properties" not in ontology:
            raise ValueError(
                "ontology must contain at least a 'classes' or 'properties' key"
            )

        tracking_id = self.progress_tracker.start_tracking(
            module="ontology", submodule="SHACLGenerator", message="Building SHACL index"
        )
        try:
            classes = ontology.get("classes", [])
            properties = ontology.get("properties", [])

            # Resolve base_uri from ontology namespace if present
            ns = ontology.get("namespace", {})
            base_uri = (
                ns.get("base_uri", self.base_uri) if isinstance(ns, dict) else self.base_uri
            )
            if not base_uri.endswith("/") and not base_uri.endswith("#"):
                base_uri += "/"

            prefixes = {
                "sh": "http://www.w3.org/ns/shacl#",
                "xsd": "http://www.w3.org/2001/XMLSchema#",
                "owl": "http://www.w3.org/2002/07/owl#",
                "rdf": "http://www.w3.org/1999/02/22-rdf-syntax-ns#",
                "rdfs": "http://www.w3.org/2000/01/rdf-schema#",
                "ex": base_uri,
            }

            target_ns = self._resolve_target_namespace(ontology, base_uri)
            prefixes["ex"] = target_ns

            graph = SHACLGraph(
                base_uri=base_uri,
                shapes_uri=self.shapes_uri,
                prefixes=prefixes,
                class_iris=self._build_term_index(classes, target_ns),
                property_iris=self._build_term_index(properties, target_ns),
            )

            self.progress_tracker.update_tracking(tracking_id, message="Generating node shapes")
            class_index = self._build_class_index(classes)
            self._generate_node_shapes(graph, classes)

            self.progress_tracker.update_tracking(tracking_id, message="Attaching property shapes")
            self._attach_property_shapes(graph, properties)

            if self.include_inherited:
                self.progress_tracker.update_tracking(tracking_id, message="Propagating inheritance")
                self._propagate_inheritance(graph, class_index)

            self._apply_quality_tier(graph)

            self.progress_tracker.stop_tracking(
                tracking_id, status="completed", message="SHACL graph built"
            )
            return graph

        except (ValueError, TypeError):
            self.progress_tracker.stop_tracking(
                tracking_id, status="failed", message="Generation failed"
            )
            raise
        except Exception as exc:
            self.progress_tracker.stop_tracking(
                tracking_id, status="failed", message=str(exc)
            )
            from ..utils.exceptions import ProcessingError
            raise ProcessingError(f"SHACL generation failed: {exc}") from exc

    def serialize(self, graph: SHACLGraph, format: str = "turtle") -> str:
        """Serialize a SHACLGraph to a string in the requested format."""
        tracking_id = self.progress_tracker.start_tracking(
            module="ontology", submodule="SHACLGenerator", message="Serializing SHACL graph"
        )
        try:
            fmt = format.lower().strip()
            if fmt in ("turtle", "ttl"):
                result = self._serialize_turtle(graph)
            elif fmt in ("json-ld", "jsonld", "json_ld"):
                result = self._serialize_jsonld(graph)
            elif fmt in ("n-triples", "ntriples", "nt"):
                result = self._serialize_ntriples(graph)
            else:
                raise ValueError(
                    f"Unsupported SHACL serialization format: '{format}'. "
                    "Supported formats: 'turtle', 'json-ld', 'n-triples'"
                )
            self.progress_tracker.stop_tracking(
                tracking_id, status="completed", message="Serialized"
            )
            return result
        except ValueError:
            self.progress_tracker.stop_tracking(
                tracking_id, status="failed", message="Unsupported format"
            )
            raise
        except Exception as exc:
            self.progress_tracker.stop_tracking(
                tracking_id, status="failed", message=str(exc)
            )
            from ..utils.exceptions import ProcessingError
            raise ProcessingError(f"SHACL serialization failed: {exc}") from exc

    # ── Internal pipeline stages ──────────────────────────────────────────────

    _DEFAULT_TARGET_NAMESPACE = "https://semantica.dev/ns#"

    @staticmethod
    def _is_absolute_iri(value: Any) -> bool:
        return isinstance(value, str) and bool(
            re.match(r"^[A-Za-z][A-Za-z0-9+.\-]*:", value.strip())
        )

    @staticmethod
    def _join_iri(base: str, local: str) -> str:
        separator = "" if base.endswith(("#", "/", ":")) else "#"
        return f"{base}{separator}{local}"

    def _resolve_target_namespace(self, ontology: Dict[str, Any], base_uri: str) -> str:
        """
        Decide which namespace sh:targetClass and sh:path are expanded in.

        base_uri says where the shapes live. It is only the right answer here
        when the ontology declared it, meaning shapes and terms deliberately
        share a namespace. Falling back to the shapes namespace produces shapes
        that target terms no data graph uses.
        """
        if self.target_namespace:
            return self.target_namespace

        namespace = ontology.get("namespace")
        if isinstance(namespace, dict) and namespace.get("base_uri"):
            return str(namespace["base_uri"])

        # An IRI already carried by a term is the most reliable evidence of
        # where the data lives, so prefer it over any configured default.
        for terms in (ontology.get("classes"), ontology.get("properties")):
            for term in terms or []:
                if not isinstance(term, dict):
                    continue
                for key in ("uri", "iri", "id"):
                    value = term.get(key)
                    if self._is_absolute_iri(value):
                        value = value.strip()
                        cut = max(value.rfind("#"), value.rfind("/"))
                        if cut != -1:
                            return value[: cut + 1]

        if ontology.get("uri") and self._is_absolute_iri(ontology["uri"]):
            return str(ontology["uri"])

        if base_uri != self.base_uri:
            return base_uri

        return self._DEFAULT_TARGET_NAMESPACE

    def _build_term_index(
        self, terms: List[Dict[str, Any]], target_ns: str
    ) -> Dict[str, str]:
        """Map each term's name to the absolute IRI it expands to."""
        index: Dict[str, str] = {}
        for term in terms or []:
            if not isinstance(term, dict):
                continue
            name = term.get("name")
            if not isinstance(name, str) or not name.strip():
                continue
            name = name.strip()

            iri = ""
            for key in ("uri", "iri", "id"):
                value = term.get(key)
                if isinstance(value, str) and value.strip():
                    value = value.strip()
                    iri = value if self._is_absolute_iri(value) else self._join_iri(target_ns, value)
                    break
            index.setdefault(name, iri or self._join_iri(target_ns, name))
        return index

    def _build_class_index(
        self, classes: List[Dict[str, Any]]
    ) -> Dict[str, Dict[str, Any]]:
        return {c["name"]: c for c in classes if c.get("name")}

    def _generate_node_shapes(
        self, graph: SHACLGraph, classes: List[Dict[str, Any]]
    ) -> None:
        for cls in classes:
            name = cls.get("name")
            if not name:
                continue
            shape = NodeShape(
                target_class=name,
                name=cls.get("label") or cls.get("name"),
                description=cls.get("description") or cls.get("comment"),
                severity=self.severity,
            )
            graph.node_shapes.append(shape)

    def _attach_property_shapes(
        self, graph: SHACLGraph, properties: List[Dict[str, Any]]
    ) -> None:
        shape_by_class = {ns.target_class: ns for ns in graph.node_shapes}

        for prop in properties:
            pname = prop.get("name")
            if not pname:
                continue

            domain = prop.get("domain")
            if isinstance(domain, list):
                domains = [d for d in domain if d]
            elif isinstance(domain, str) and domain:
                domains = [domain]
            else:
                domains = []

            if domains:
                for d in domains:
                    if d in shape_by_class:
                        shape_by_class[d].property_shapes.append(
                            self._build_property_shape(prop)
                        )
                    else:
                        self.logger.debug(
                            f"Property '{pname}' domain '{d}' has no matching node shape — skipped"
                        )
            elif self.attach_domainless_properties:
                self.logger.warning(
                    f"Property '{pname}' declares no domain and is being attached "
                    "to every node shape because attach_domainless_properties is "
                    "set. This states a constraint the ontology does not."
                )
                for node_shape in graph.node_shapes:
                    node_shape.property_shapes.append(self._build_property_shape(prop))
            else:
                # Attaching here would state a constraint the ontology does not.
                # With minCount 1 that invalidates every instance of every
                # class, so the property is left unattached (#1105).
                self.logger.warning(
                    f"Property '{pname}' declares no domain, so it is not attached "
                    "to any node shape. Declare a domain, or pass "
                    "attach_domainless_properties=True to restore the old behaviour."
                )

    def _build_property_shape(self, prop: Dict[str, Any]) -> PropertyShape:
        ptype = prop.get("type", "")
        range_ = prop.get("range", "")
        if isinstance(range_, list):
            range_ = range_[0] if range_ else ""

        cardinality = prop.get("cardinality") or {}
        min_count = cardinality.get("min") if isinstance(cardinality, dict) else None
        max_count = cardinality.get("max") if isinstance(cardinality, dict) else None

        if prop.get("required") and min_count is None:
            min_count = 1

        datatype = None
        class_ = None
        if ptype in ("datatype", "data", "DatatypeProperty"):
            datatype = self._resolve_xsd(range_) if range_ else None
        elif ptype in ("object", "ObjectProperty"):
            class_ = range_ if range_ else None

        in_values = (
            prop.get("one_of") or prop.get("enum") or prop.get("allowed_values")
        )
        if in_values and self.quality_tier in ("standard", "strict"):
            in_values = list(in_values)
        else:
            in_values = None

        pattern = prop.get("pattern") if self.quality_tier in ("standard", "strict") else None

        return PropertyShape(
            path=prop.get("name", ""),
            name=prop.get("label") or prop.get("name"),
            description=prop.get("description") or prop.get("comment"),
            datatype=datatype,
            class_=class_,
            min_count=min_count,
            max_count=max_count,
            in_values=in_values,
            has_value=prop.get("has_value"),
            pattern=pattern,
            severity=self.severity,
        )

    def _propagate_inheritance(
        self, graph: SHACLGraph, class_index: Dict[str, Dict[str, Any]]
    ) -> None:
        shape_by_class = {ns.target_class: ns for ns in graph.node_shapes}

        for _ in range(20):  # max 20 passes; stops early when stable
            changed = False
            for node_shape in graph.node_shapes:
                cls_data = class_index.get(node_shape.target_class, {})
                parent_name = cls_data.get("parent") or cls_data.get("parent_class")
                if not parent_name or parent_name not in shape_by_class:
                    continue
                parent_shape = shape_by_class[parent_name]
                existing_paths = {ps.path for ps in node_shape.property_shapes}
                for pps in parent_shape.property_shapes:
                    if pps.path not in existing_paths:
                        node_shape.property_shapes.append(dataclass_replace(pps))
                        existing_paths.add(pps.path)
                        changed = True
            if not changed:
                break

    def _apply_quality_tier(self, graph: SHACLGraph) -> None:
        if self.quality_tier == "strict":
            for node_shape in graph.node_shapes:
                # Only close shapes that declare at least one property
                if node_shape.property_shapes:
                    node_shape.closed = True

    # ── Serializers ───────────────────────────────────────────────────────────

    def _prefix_decls(self, graph: SHACLGraph) -> str:
        return "\n".join(f"@prefix {p}: <{u}> ." for p, u in sorted(graph.prefixes.items()))

    def _term_iri(self, graph: SHACLGraph, local: str, kind: str = "class") -> str:
        """
        Resolve a class or property name to the absolute IRI the data uses.

        Every serializer goes through here. Turtle alone was corrected at first,
        which left JSON-LD and N-Triples still pasting names onto the shapes
        namespace, so the shapes they produced went on matching nothing (#1104).

        `kind` selects the index: a property may share a class's name, and the
        two can carry different IRIs.
        """
        if local.startswith("http://") or local.startswith("https://"):
            return local
        index = graph.property_iris if kind == "property" else graph.class_iris
        resolved = index.get(local)
        if resolved:
            return resolved
        # Fall back to the other index before giving up: sh:class names a class,
        # but a caller may pass a term only registered on the other side.
        other = graph.class_iris if kind == "property" else graph.property_iris
        resolved = other.get(local)
        if resolved:
            return resolved
        if ":" in local:
            return local
        separator = "" if graph.base_uri.endswith(("#", "/", ":")) else "#"
        return f"{graph.base_uri}{separator}{local}"

    def _uri(self, graph: SHACLGraph, local: str, kind: str = "class") -> str:
        """Turtle-facing wrapper: the resolved IRI, in angle brackets."""
        resolved = self._term_iri(graph, local, kind)
        if resolved.startswith(("http://", "https://", "urn:")):
            return f"<{resolved}>"
        return resolved

    def _serialize_turtle(self, graph: SHACLGraph) -> str:
        lines = [self._prefix_decls(graph), ""]
        lines.append(f"<{graph.shapes_uri}> a owl:Ontology .")
        lines.append("")

        for node_shape in graph.node_shapes:
            shape_uri = f"{graph.base_uri}{node_shape.target_class}Shape"
            block = [f"<{shape_uri}>"]
            block.append("    a sh:NodeShape ;")
            block.append(
                f"    sh:targetClass {self._uri(graph, node_shape.target_class)} ;"
            )
            if node_shape.name:
                block.append(f'    sh:name "{node_shape.name}" ;')
            if node_shape.description:
                escaped = node_shape.description.replace('"', '\\"')
                block.append(f'    sh:description "{escaped}" ;')
            if node_shape.closed:
                block.append("    sh:closed true ;")
                block.append("    sh:ignoredProperties ( <http://www.w3.org/1999/02/22-rdf-syntax-ns#type> ) ;")

            for i, ps in enumerate(node_shape.property_shapes):
                is_last = i == len(node_shape.property_shapes) - 1
                terminator = " ." if is_last else " ;"
                parts = ["    sh:property ["]
                parts.append(f'        sh:path {self._uri(graph, ps.path, "property")} ;')
                if ps.datatype:
                    parts.append(f"        sh:datatype {ps.datatype} ;")
                if ps.class_:
                    parts.append(f'        sh:class {self._uri(graph, ps.class_, "class")} ;')
                if ps.min_count is not None:
                    parts.append(f"        sh:minCount {ps.min_count} ;")
                if ps.max_count is not None:
                    parts.append(f"        sh:maxCount {ps.max_count} ;")
                if ps.in_values is not None:
                    vals = " ".join(f'"{v}"' for v in ps.in_values)
                    parts.append(f"        sh:in ( {vals} ) ;")
                if ps.has_value is not None:
                    parts.append(f"        sh:hasValue {self._uri(graph, ps.has_value)} ;")
                if ps.pattern:
                    escaped_p = ps.pattern.replace('"', '\\"')
                    parts.append(f'        sh:pattern "{escaped_p}" ;')
                parts.append(f"        sh:severity sh:{ps.severity}")
                parts.append("    ]" + terminator)
                block.extend(parts)

            if not node_shape.property_shapes:
                # Close the declaration when there are no property shapes
                block[-1] = block[-1].rstrip(" ;") + " ."

            lines.append("\n".join(block))
            lines.append("")

        return "\n".join(lines)

    def _serialize_jsonld(self, graph: SHACLGraph) -> str:
        import json

        context: Dict[str, Any] = dict(graph.prefixes)
        context["sh"] = "http://www.w3.org/ns/shacl#"
        context["@vocab"] = graph.base_uri

        graph_list: List[Dict[str, Any]] = [
            {"@id": graph.shapes_uri, "@type": "owl:Ontology"}
        ]
        for node_shape in graph.node_shapes:
            shape_id = f"{graph.base_uri}{node_shape.target_class}Shape"
            node: Dict[str, Any] = {
                "@id": shape_id,
                "@type": "sh:NodeShape",
                "sh:targetClass": {"@id": self._term_iri(graph, node_shape.target_class, "class")},
            }
            if node_shape.name:
                node["sh:name"] = node_shape.name
            if node_shape.description:
                node["sh:description"] = node_shape.description
            if node_shape.closed:
                node["sh:closed"] = True
                node["sh:ignoredProperties"] = [{"@id": "rdf:type"}]
            if node_shape.property_shapes:
                props = []
                for ps in node_shape.property_shapes:
                    p: Dict[str, Any] = {
                        "sh:path": {"@id": self._term_iri(graph, ps.path, "property")}
                    }
                    if ps.datatype:
                        dt = ps.datatype.replace(
                            "xsd:", "http://www.w3.org/2001/XMLSchema#"
                        )
                        p["sh:datatype"] = {"@id": dt}
                    if ps.class_:
                        p["sh:class"] = {"@id": self._term_iri(graph, ps.class_, "class")}
                    if ps.min_count is not None:
                        p["sh:minCount"] = ps.min_count
                    if ps.max_count is not None:
                        p["sh:maxCount"] = ps.max_count
                    if ps.in_values:
                        p["sh:in"] = {"@list": ps.in_values}
                    if ps.has_value is not None:
                        p["sh:hasValue"] = ps.has_value
                    if ps.pattern:
                        p["sh:pattern"] = ps.pattern
                    p["sh:severity"] = {"@id": f"sh:{ps.severity}"}
                    props.append(p)
                node["sh:property"] = props
            graph_list.append(node)

        return json.dumps({"@context": context, "@graph": graph_list}, indent=2)

    def _serialize_ntriples(self, graph: SHACLGraph) -> str:
        SHACL = "http://www.w3.org/ns/shacl#"
        OWL = "http://www.w3.org/2002/07/owl#"
        RDF = "http://www.w3.org/1999/02/22-rdf-syntax-ns#"
        XSD = "http://www.w3.org/2001/XMLSchema#"

        lines: List[str] = []

        def t(s: str, p: str, o: str) -> None:
            lines.append(f"{s} {p} {o} .")

        t(f"<{graph.shapes_uri}>", f"<{RDF}type>", f"<{OWL}Ontology>")

        for i, node_shape in enumerate(graph.node_shapes):
            shape_uri = f"<{graph.base_uri}{node_shape.target_class}Shape>"
            class_uri = f'<{self._term_iri(graph, node_shape.target_class, "class")}>'
            t(shape_uri, f"<{RDF}type>", f"<{SHACL}NodeShape>")
            t(shape_uri, f"<{SHACL}targetClass>", class_uri)
            if node_shape.name:
                t(shape_uri, f"<{SHACL}name>", f'"{node_shape.name}"')
            if node_shape.closed:
                t(
                    shape_uri,
                    f"<{SHACL}closed>",
                    f'"true"^^<{XSD}boolean>',
                )

            for j, ps in enumerate(node_shape.property_shapes):
                bnode = f"_:ps{i}_{j}"
                t(shape_uri, f"<{SHACL}property>", bnode)
                prop_uri = f'<{self._term_iri(graph, ps.path, "property")}>'
                t(bnode, f"<{SHACL}path>", prop_uri)
                if ps.datatype:
                    dt_uri = ps.datatype.replace("xsd:", XSD)
                    t(bnode, f"<{SHACL}datatype>", f"<{dt_uri}>")
                if ps.class_:
                    t(bnode, f"<{SHACL}class>", f'<{self._term_iri(graph, ps.class_, "class")}>')
                if ps.min_count is not None:
                    t(bnode, f"<{SHACL}minCount>", f'"{ps.min_count}"^^<{XSD}integer>')
                if ps.max_count is not None:
                    t(bnode, f"<{SHACL}maxCount>", f'"{ps.max_count}"^^<{XSD}integer>')
                t(bnode, f"<{SHACL}severity>", f"<{SHACL}{ps.severity}>")

        return "\n".join(lines)

    # ── Helper ────────────────────────────────────────────────────────────────

    def _resolve_xsd(self, range_str: str) -> str:
        """Map ontology range strings to xsd:-prefixed datatypes."""
        key = range_str.lower().strip()
        return self._XSD_ALIASES.get(key, f"xsd:{range_str}")
