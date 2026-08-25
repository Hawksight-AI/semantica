"""
Ontology Management Module

This module provides comprehensive ontology management and generation capabilities,
following semantic modeling best practices and guidelines for building effective ontologies.

Algorithms Used:

Ontology Generation (6-Stage Pipeline):
    - Stage 1 - Semantic Network Parsing: Extract domain concepts from entities/relationships, entity type analysis (Counter), relationship pattern extraction, concept grouping
    - Stage 2 - YAML-to-Definition: Transform concepts into class definitions, YAML parsing, definition structure creation, class inference (ClassInferrer.infer_classes)
    - Stage 3 - Definition-to-Types: Map definitions to OWL types, type inference, OWL class/property mapping (@type assignment: owl:Class, owl:ObjectProperty, owl:DatatypeProperty), property inference (PropertyGenerator.infer_properties)
    - Stage 4 - Hierarchy Generation: Build taxonomic structures, parent-child relationship inference, hierarchy validation, circular dependency detection (DFS), transitive closure calculation
    - Stage 5 - TTL Generation: Generate OWL/Turtle syntax using rdflib, namespace prefix handling, RDF serialization (rdflib.serialize format="turtle"), triplet generation (subject-predicate-object)
    - Stage 6 - Symbolic Validation: HermiT/Pellet reasoning, consistency checking, satisfiability checking, structural validation

Class Inference:
    - Pattern-Based Inference: Entity type frequency analysis (Counter), minimum occurrence threshold filtering, similarity-based class merging (threshold matching), entity grouping by type
    - Hierarchy Building: Parent-child relationship inference, transitive closure calculation, hierarchy depth analysis, circular dependency detection (DFS), parent class assignment
    - Class Validation: Naming convention enforcement (PascalCase), IRI generation (namespace_manager.generate_class_iri), namespace validation, class name normalization

Property Inference:
    - Object Property Inference: Relationship type analysis, domain/range inference from entity types, property cardinality detection, relationship-to-property mapping
    - Data Property Inference: Entity attribute analysis, XSD type detection (string, integer, float, boolean, date), property domain inference, attribute frequency analysis
    - Property Validation: Domain/range validation, property hierarchy management, naming convention enforcement (camelCase), property IRI generation

OWL/RDF Generation:
    - RDF Graph Construction: rdflib.Graph creation, namespace binding, triplet generation (subject-predicate-object), namespace prefix declaration
    - Serialization: Turtle format (rdflib.serialize format="turtle"), RDF/XML format, JSON-LD format, N3 format, format selection and conversion
    - Namespace Management: Prefix declaration, IRI resolution, namespace prefix mapping, standard namespace registration (RDF, RDFS, OWL, XSD, SKOS, DC)

Ontology Evaluation:
    - Competency Question Validation: Question parsing, ontology query generation, answer coverage analysis, question-to-ontology element tracing
    - Coverage Metrics: Class coverage calculation, property coverage calculation, relationship coverage calculation, answerable question ratio
    - Completeness Metrics: Required class detection, missing property identification, gap analysis, completeness score calculation
    - Granularity Evaluation: Class granularity assessment, generalization/specialization analysis, granularity score calculation

Requirements Specification:
    - Competency Question Management: Question storage, categorization (general, organizational, temporal), validation, priority assignment (1=high, 2=medium, 3=low)
    - Scope Definition: Domain boundary definition, entity type scoping, relationship scoping, purpose documentation
    - Traceability: Requirements-to-ontology mapping, coverage tracking, trace-to-elements assignment

Ontology Reuse:
    - Ontology Research: Known ontology catalog lookup (FOAF, Dublin Core, Schema.org), URI resolution, metadata extraction, ontology information retrieval
    - Alignment Evaluation: Concept alignment scoring, compatibility assessment, interoperability analysis, alignment score calculation
    - Import Management: External ontology import, namespace merging, conflict resolution, import decision tracking (reuse/partial/reject)

Version Management:
    - Version-Aware IRI Generation: Version in ontology IRI (not element IRIs), version-less element IRIs, logical version-less IRIs, versioned IRI construction (urljoin)
    - Version Comparison: Diff generation, change detection, migration path identification, version diff analysis
    - Multi-Version Coexistence: Version isolation, import closure resolution, version record management

Namespace Management:
    - IRI Generation: Base URI + local name construction (urljoin), namespace prefix mapping, IRI validation, speaking IRI support (human-readable)
    - Prefix Handling: Prefix declaration, namespace binding, prefix resolution, standard namespace registration

Associative Class Creation:
    - Complex Relationship Modeling: N-ary relationship handling, relationship properties, intermediate class creation, multi-entity connection
    - Pattern Detection: Relationship pattern analysis, associative class inference, temporal association detection

Key Features:
    - Automatic ontology generation from data (6-stage pipeline)
    - Class and property inference from entities and relationships
    - OWL/RDF generation and serialization
    - Ontology quality evaluation and assessment
    - Requirements specification and competency questions
    - Ontology reuse and integration management
    - Version management with best practices
    - Namespace and IRI management
    - Naming convention enforcement
    - Modular ontology development
    - Pre-built domain ontologies
    - Comprehensive documentation management
    - Associative class creation for complex relationships
    - Method registry for extensibility
    - Configuration management with environment variables and config files

Main Classes:
    - OntologyGenerator: Main ontology generation class (6-stage pipeline)
    - ClassInferrer: Class discovery and hierarchy building
    - PropertyGenerator: Property inference and data types
    - OntologyEvaluator: Ontology quality evaluation
    - OWLGenerator: OWL/RDF generation using rdflib
    - RequirementsSpecManager: Requirements specification and competency questions
    - CompetencyQuestionsManager: Competency question management
    - ReuseManager: Ontology reuse management
    - VersionManager: Ontology versioning
    - NamespaceManager: Namespace and IRI management
    - NamingConventions: Naming convention enforcement
    - ModuleManager: Ontology module management
    - DomainOntologies: Pre-built domain ontologies
    - OntologyDocumentationManager: Documentation management
    - AssociativeClassBuilder: Associative class creation
    - MethodRegistry: Registry for custom ontology methods
    - OntologyConfig: Configuration manager for ontology module

Convenience Functions:
    - generate_ontology: Ontology generation wrapper (6-stage pipeline)
    - infer_classes: Class inference wrapper
    - infer_properties: Property inference wrapper
    - generate_owl: OWL/RDF generation wrapper
    - evaluate_ontology: Ontology evaluation wrapper
    - create_requirements_spec: Requirements specification wrapper
    - add_competency_question: Competency question management wrapper
    - research_ontology: Ontology research wrapper
    - import_external_ontology: External ontology import wrapper
    - create_version: Version creation wrapper
    - manage_namespace: Namespace management wrapper
    - create_associative_class: Associative class creation wrapper
    - get_ontology_method: Get ontology method by name
    - list_available_methods: List registered methods
    - ingest_ontology: Ingest ontology from file or directory

Example Usage:
    >>> from semantica.ontology import generate_ontology, infer_classes, OntologyGenerator, ingest_ontology
    >>> # Using convenience functions
    >>> ontology = generate_ontology({"entities": [...], "relationships": [...]}, method="default")
    >>> classes = infer_classes(entities, method="default")
    >>> data = ingest_ontology("ontology.ttl")
    >>> # Using classes directly
    >>> from semantica.ontology import OntologyGenerator, ClassInferrer, PropertyGenerator
    >>> generator = OntologyGenerator(base_uri="https://example.org/ontology/")
    >>> ontology = generator.generate_ontology({"entities": [...], "relationships": [...]})
    >>> inferrer = ClassInferrer()
    >>> classes = inferrer.infer_classes(entities)
    >>> prop_gen = PropertyGenerator()
    >>> properties = prop_gen.infer_properties(entities, relationships, classes)

Author: Semantica Contributors
License: MIT
"""

from typing import Any, Dict, List, Optional, Union

from .associative_class import AssociativeClass, AssociativeClassBuilder
from .class_inferrer import ClassInferrer
from .competency_questions import CompetencyQuestion, CompetencyQuestionsManager
from .config import OntologyConfig, ontology_config
from .domain_ontologies import DomainOntologies
from .llm_generator import LLMOntologyGenerator
from .engine import OntologyEngine
from .module_manager import ModuleManager, OntologyModule
from .namespace_manager import NamespaceManager
from .naming_conventions import NamingConventions
from .ontology_documentation import OntologyDocumentation, OntologyDocumentationManager
from .ontology_evaluator import EvaluationResult, OntologyEvaluator
from .ontology_generator import (
    ClassInferencer,
    NodeShape,
    OntologyGenerator,
    OntologyOptimizer,
    PropertyInferencer,
    PropertyShape,
    SHACLGenerator,
    SHACLGraph,
)
from .ontology_validator import (
    OntologyValidator,
    SHACLValidationReport,
    SHACLViolation,
    ValidationResult,
    run_shacl_validation,
    validate_ontology,
)
from .owl_generator import OWLGenerator
from .property_generator import PropertyGenerator
from .registry import MethodRegistry, method_registry
from .requirements_spec import RequirementsSpec, RequirementsSpecManager
from .reuse_manager import ReuseDecision, ReuseManager
# VersionManager and OntologyVersion moved to change_management module
# Import them directly from there: from semantica.change_management import VersionManager, OntologyVersion
from semantica.ingest import OntologyData, OntologyIngestor
from .methods import ingest_ontology

__all__ = [
    # Main generators
    "OntologyGenerator",
    "ClassInferrer",
    "ClassInferencer",  # Legacy alias
    "PropertyGenerator",
    "PropertyInferencer",  # Legacy alias
    "OntologyOptimizer",
    # Validation and evaluation
    "OntologyValidator",
    "ValidationResult",
    "validate_ontology",
    "OntologyEvaluator",
    "EvaluationResult",
    # SHACL generation and validation
    "SHACLGenerator",
    "SHACLGraph",
    "NodeShape",
    "PropertyShape",
    "SHACLValidationReport",
    "SHACLViolation",
    "run_shacl_validation",
    # OWL/RDF generation
    "OWLGenerator",
    # Requirements and competency questions
    "RequirementsSpecManager",
    "RequirementsSpec",
    "CompetencyQuestionsManager",
    "CompetencyQuestion",
    # Management
    "ReuseManager",
    "ReuseDecision",
    # VersionManager and OntologyVersion moved to change_management module
    "NamespaceManager",
    "NamingConventions",
    "ModuleManager",
    "OntologyModule",
    "DomainOntologies",
    "OntologyDocumentationManager",
    "OntologyDocumentation",
    # Special classes
    "AssociativeClassBuilder",
    "AssociativeClass",
    # Registry and Methods
    "MethodRegistry",
    "method_registry",
    "LLMOntologyGenerator",
    "OntologyEngine",
    # Configuration
    "OntologyConfig",
    "ontology_config",
    "ingest_ontology",
    "OntologyData",
    "OntologyIngestor",
]
