"""
Export and Reporting Module

This module provides comprehensive export and reporting capabilities for the
Semantica framework, supporting multiple formats and use cases including RDF,
JSON, CSV, Graph, YAML, OWL, Vector, LPG (Labeled Property Graph), and
ArangoDB AQL formats.

Algorithms Used:

RDF Export:
    - RDF Serialization: Multiple format serialization (Turtle,
      RDF/XML, JSON-LD, N-Triples, N3)
    - RDF Serialization: Multiple format serialization (Turtle, RDF/XML,
      JSON-LD, N-Triples, N3)
    - Namespace Management: Namespace registration, conflict resolution,
      declaration generation
    - RDF Validation: RDF syntax validation, triplet validation,
      namespace validation
    - URI Generation: Hash-based and text-based URI assignment for RDF resources
    - Triplet Extraction: Entity and relationship to RDF triplet conversion
    - Format Conversion: Cross-format RDF conversion algorithms

LPG (Labeled Property Graph) Export:
    - LPG Serialization: Labeled Property Graph format for Neo4j,
      Memgraph, and similar databases
    - LPG Serialization: Labeled Property Graph format for Neo4j, Memgraph,
      and similar databases
    - Node Label Assignment: Entity type to node label mapping
    - Relationship Type Mapping: Relationship type to edge label conversion
    - Property Serialization: Entity and relationship properties to LPG property format
    - Cypher Query Generation: Cypher CREATE statements for graph database import
    - Batch Node/Relationship Export: Efficient batch processing for large graphs
    - Index Generation: Index and constraint generation for graph databases

ArangoDB AQL Export:
    - AQL Serialization: AQL INSERT statements for ArangoDB multi-model databases
    - Vertex Collection Export: Entity to vertex collection conversion
    - Edge Collection Export: Relationship to edge collection conversion
    - Key Sanitization: Automatic sanitization of keys for ArangoDB compliance
    - Batch Insert Generation: Efficient batch INSERT operations for large graphs
    - Configurable Collections: Support for custom vertex and edge collection names
    - Property Preservation: Full preservation of entity and relationship properties

JSON/JSON-LD Export:
    - JSON Serialization: Standard JSON serialization with configurable indentation
    - JSON-LD Context Management: @context generation and management
    - Knowledge Graph Serialization: Graph structure to JSON/JSON-LD conversion
    - Metadata Embedding: Provenance and metadata serialization in JSON
      structure
    - Pretty Printing: Formatted JSON output with indentation

CSV Export:
    - Tabular Serialization: Entity and relationship to CSV row conversion
    - Field Extraction: Dynamic field name extraction from data structures
    - Delimiter Handling: Configurable delimiter support (comma, tab, semicolon)
    - Header Generation: Automatic CSV header row generation
    - Metadata Serialization: JSON string serialization for complex metadata fields
    - Metadata Serialization: JSON string serialization for complex
      metadata fields
    - Multi-file Export: Knowledge graph split into multiple CSV files
      (entities, relationships)

Neo4j Bulk CSV Export:
    - Neo4j Admin Import CSV: Deterministic nodes.csv and relationships.csv
      files compatible with neo4j-admin database import
    - Stable Node IDs: Reuse existing graph IDs or derive deterministic IDs
      from node contents
    - Label and Property Mapping: Multi-label :LABEL values and sorted
      property columns

Graph Export:
    - GraphML Serialization: GraphML format generation for graph visualization tools
    - GEXF Serialization: GEXF format generation for Gephi and similar tools
    - DOT Serialization: Graphviz DOT format generation
    - Node/Edge Attribute Mapping: Property to graph attribute conversion
    - Graph Structure Conversion: Knowledge graph to graph format transformation

YAML Export:
    - YAML Serialization: Human-readable YAML format generation
    - Semantic Network Export: Entity-relationship network to YAML conversion
    - Schema Export: Ontology schema to YAML for human editing
    - Pipeline Integration: Stage-specific YAML export for ontology generation pipeline

OWL Export:
    - OWL-XML Serialization: OWL/XML format generation
    - Turtle Serialization: OWL in Turtle format
    - Class Hierarchy Export: Class definition and hierarchy serialization
    - Property Export: Object and data property definition export
    - OWL 2.0 Feature Support: Advanced OWL features (cardinality,
      restrictions, etc.)
    - Ontology Validation: OWL syntax and semantic validation

Parquet Export:
    - Parquet Serialization: Columnar storage format for analytics
    - Schema Definition: Explicit Arrow schema for entities and
      relationships
    - Compression: Configurable compression (snappy, gzip, brotli,
      zstd, lz4)
    - Metadata Handling: Structured metadata as Parquet structs
    - Analytics Integration: Compatible with pandas, Spark, Snowflake,
      BigQuery, Databricks
    - Batch Export: Efficient batch processing for large graphs

Vector Export:
    - Vector Serialization: Multiple format support (JSON, NumPy, Binary, FAISS)
    - Vector Store Integration: Format conversion for Weaviate, Qdrant, FAISS
    - Metadata Association: Vector-to-metadata mapping and serialization
    - Batch Export: Efficient batch vector export processing
    - Multi-dimensional Support: Variable dimension vector handling

Report Generation:
    - Template Rendering: Template-based report generation (HTML, Markdown, JSON, Text)
    - Quality Metrics Aggregation: Statistical aggregation of quality metrics
    - Chart Generation: Visualization and chart generation (if enabled)
    - Format Conversion: Cross-format report conversion
    - Section Organization: Hierarchical report section organization

Key Features:
    - Multiple export formats (RDF, JSON, CSV, Graph, YAML, OWL, Vector, LPG, Parquet)
    - Multiple export formats (RDF, JSON, CSV, Graph, YAML, OWL, Vector,
      LPG, ArangoDB AQL)
    - Knowledge graph export with format auto-detection
    - Report generation (HTML, Markdown, JSON, Text)
    - Vector store integration
    - Batch export processing
    - Metadata and provenance tracking
    - Method registry for extensibility
    - Configuration management with environment variables and config files

Main Classes:
    - RDFExporter: RDF format export (Turtle, RDF/XML, JSON-LD)
    - JSONExporter: JSON and JSON-LD format export
    - CSVExporter: CSV format export for tabular data
    - Neo4jCSVExporter: Neo4j bulk import CSV export
    - ParquetExporter: Parquet format export for analytics and data warehousing
    - GraphExporter: Graph format export (GraphML, GEXF, DOT)
    - YAMLExporter: YAML format export for semantic networks
    - OWLExporter: OWL format export for ontologies
    - VectorExporter: Vector embedding export for vector stores
    - LPGExporter: LPG format export for Neo4j, Memgraph, and similar
      databases
    - ArangoAQLExporter: ArangoDB AQL format export for multi-model
      databases
    - ReportGenerator: Report generation (HTML, Markdown, JSON, Text)
    - MethodRegistry: Registry for custom export methods
    - ExportConfig: Configuration manager for export module

Convenience Functions:
    - export_rdf: RDF export wrapper
    - export_json: JSON/JSON-LD export wrapper
    - export_parquet: Parquet export wrapper
    - export_csv: CSV export wrapper
    - export_graph: Graph format export wrapper
    - export_yaml: YAML export wrapper
    - export_owl: OWL export wrapper
    - export_vector: Vector export wrapper
    - export_lpg: LPG export wrapper
    - generate_report: Report generation wrapper

Example Usage:
    >>> # Using convenience function
    >>> export_lpg(kg, "output.cypher", method="cypher")
    >>> export_parquet(entities, "output.parquet", compression="snappy")
    >>> # Using classes directly
    >>> json_exporter = JSONExporter()
    >>> json_exporter.export_knowledge_graph(kg, "output.json")

Author: Semantica Contributors
License: MIT
"""

from .arango_aql_exporter import ArangoAQLExporter
from .config import ExportConfig, export_config
from .distance_exporter import DistanceExporter

try:
    from .arrow_exporter import ArrowExporter
except ImportError:
    # ArrowExporter is not available in CI environment - dummy class
    class ArrowExporter:
        def __init__(self, *args, **kwargs):
            pass

        def __getattr__(self, name):
            return lambda *args, **kwargs: f"Mock ArrowExporter.{name}"


from .csv_exporter import CSVExporter
from .graph_exporter import GraphExporter
from .json_exporter import JSONExporter
from .lpg_exporter import LPGExporter
from .methods import (
    export_arango,
    export_arrow,
    export_csv,
    export_graph,
    export_json,
    export_lpg,
    export_neo4j_csv,
    export_owl,
    export_parquet,
    export_rdf,
    export_vector,
    export_yaml,
    generate_report,
    get_export_method,
    list_available_methods,
)
from .neo4j_csv_exporter import Neo4jCSVExporter
from .owl_exporter import OWLExporter

try:
    from .parquet_exporter import ParquetExporter
except ImportError:
    # ParquetExporter is not available in CI environment - create a dummy class
    class ParquetExporter:
        def __init__(self, *args, **kwargs):
            pass

        def __getattr__(self, name):
            return lambda *args, **kwargs: f"Mock ParquetExporter.{name}"


from .rdf_exporter import NamespaceManager, RDFExporter, RDFSerializer, RDFValidator
from .registry import MethodRegistry, method_registry
from .report_generator import ReportGenerator
from .vector_exporter import VectorExporter
from .yaml_exporter import SemanticNetworkYAMLExporter, YAMLSchemaExporter

__all__ = [
    # Core Exporters
    "ArrowExporter",
    "ArangoAQLExporter",
    "DistanceExporter",
    "RDFExporter",
    "RDFSerializer",
    "RDFValidator",
    "NamespaceManager",
    "JSONExporter",
    "CSVExporter",
    "Neo4jCSVExporter",
    "ParquetExporter",
    "GraphExporter",
    "SemanticNetworkYAMLExporter",
    "YAMLSchemaExporter",
    "ReportGenerator",
    "OWLExporter",
    "VectorExporter",
    "LPGExporter",
    # Registry and Methods
    "MethodRegistry",
    "method_registry",
    "export_rdf",
    "export_json",
    "export_csv",
    "export_arrow",
    "export_parquet",
    "export_graph",
    "export_yaml",
    "export_owl",
    "export_vector",
    "export_lpg",
    "export_neo4j_csv",
    "export_arango",
    "generate_report",
    "get_export_method",
    "list_available_methods",
    # Configuration
    "ExportConfig",
    "export_config",
]
