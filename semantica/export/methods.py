"""
Export Methods Module

This module provides all export methods as simple, reusable functions for
exporting knowledge graphs, entities, relationships, and data to various formats.
It supports multiple export approaches and integrates with the method registry
for extensibility.

Supported Methods:

RDF Export:
    - "turtle": Turtle format export
    - "rdfxml": RDF/XML format export
    - "jsonld": JSON-LD format export
    - "ntriples": N-Triples format export
    - "n3": N3 format export

JSON Export:
    - "json": Standard JSON format export
    - "json-ld": JSON-LD format export

CSV Export:
    - "csv": CSV format export with configurable delimiter

Graph Export:
    - "graphml": GraphML format export
    - "gexf": GEXF format export
    - "dot": DOT format export
    - "json": JSON graph format export

YAML Export:
    - "yaml": YAML format export
    - "semantic_network": Semantic network YAML export
    - "schema": Schema YAML export

OWL Export:
    - "owl-xml": OWL/XML format export
    - "turtle": OWL in Turtle format

Vector Export:
    - "json": JSON vector format
    - "numpy": NumPy format
    - "binary": Binary format
    - "faiss": FAISS format

LPG Export:
    - "cypher": Cypher query format for Neo4j/Memgraph
    - "lpg": Labeled Property Graph format

Neo4j Bulk CSV Export:
    - "neo4j_csv": CSV files for ``neo4j-admin database import``

Report Generation:
    - "html": HTML report format
    - "markdown": Markdown report format
    - "json": JSON report format
    - "text": Plain text report format

Algorithms Used:

RDF Export:
    - RDF Serialization: Multiple format serialization
      (Turtle, RDF/XML, JSON-LD, N-Triples, N3)
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
    - Node Label Assignment: Entity type to node label mapping
    - Relationship Type Mapping: Relationship type to edge label conversion
    - Property Serialization: Entity and relationship properties to LPG property format
    - Cypher Query Generation: Cypher CREATE statements for graph database import
    - Batch Node/Relationship Export: Efficient batch processing for large graphs
    - Index Generation: Index and constraint generation for graph databases

JSON/JSON-LD Export:
    - JSON Serialization: Standard JSON serialization with configurable indentation
    - JSON-LD Context Management: @context generation and management
    - Knowledge Graph Serialization: Graph structure to JSON/JSON-LD conversion
    - Metadata Embedding: Provenance and metadata serialization in JSON structure
    - Pretty Printing: Formatted JSON output with indentation

CSV Export:
    - Tabular Serialization: Entity and relationship to CSV row conversion
    - Field Extraction: Dynamic field name extraction from data structures
    - Delimiter Handling: Configurable delimiter support (comma, tab, semicolon)
    - Header Generation: Automatic CSV header row generation
    - Metadata Serialization: JSON string serialization for complex metadata
      fields
    - Multi-file Export: Knowledge graph split into multiple CSV files
      (entities, relationships)

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
    - OWL 2.0 Feature Support: Advanced OWL features (cardinality, restrictions, etc.)
    - Ontology Validation: OWL syntax and semantic validation

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
    - Multiple export format methods
    - Knowledge graph export with format dispatch
    - Method dispatchers with registry support
    - Custom method registration capability
    - Consistent interface across all methods

Main Functions:
    - export_rdf: RDF export wrapper
    - export_json: JSON/JSON-LD export wrapper
    - export_csv: CSV export wrapper
    - export_graph: Graph format export wrapper
    - export_yaml: YAML export wrapper
    - export_owl: OWL export wrapper
    - export_vector: Vector export wrapper
    - export_lpg: LPG export wrapper
    - generate_report: Report generation wrapper
    - get_export_method: Get export method by name
    - list_available_methods: List registered methods

Example Usage:
    >>> from semantica.export.methods import export_rdf, export_json, export_lpg
    >>> kg = {"entities": [...], "relationships": [...]}
    >>> export_json(kg, "output.json", format="json")
    >>> export_rdf(kg, "output.ttl", format="turtle")
    >>> export_lpg(kg, "output.cypher", method="cypher")
"""

from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Union

from ..utils.exceptions import ProcessingError
from ..utils.logging import get_logger
from .arango_aql_exporter import ArangoAQLExporter
from .arrow_exporter import ArrowExporter
from .config import export_config
from .csv_exporter import CSVExporter
from .graph_exporter import GraphExporter
from .json_exporter import JSONExporter
from .lpg_exporter import LPGExporter
from .neo4j_csv_exporter import Neo4jCSVExporter
from .owl_exporter import OWLExporter

try:
    from .parquet_exporter import ParquetExporter

    PARQUET_AVAILABLE = True
except ImportError:
    PARQUET_AVAILABLE = False
from .rdf_exporter import RDFExporter
from .registry import method_registry
from .report_generator import ReportGenerator
from .vector_exporter import VectorExporter
from .yaml_exporter import SemanticNetworkYAMLExporter, YAMLSchemaExporter

logger = get_logger("export_methods")


def export_rdf(
    data: Union[Dict[str, Any], List[Dict[str, Any]]],
    file_path: Union[str, Path],
    format: str = "turtle",
    method: str = "default",
    **kwargs,
) -> None:
    """
    Export data to RDF format (convenience function).

    This is a user-friendly wrapper that exports data to RDF using the specified format.

    Args:
        data: Data to export (knowledge graph, entities, relationships, or triplets)
        file_path: Output RDF file path
        format: RDF format (default: "turtle")
            - "turtle": Turtle format
            - "rdfxml": RDF/XML format
            - "jsonld": JSON-LD format
            - "ntriples": N-Triples format
            - "n3": N3 format
        method: Export method (default: "default")
        **kwargs: Additional options passed to RDFExporter

    Examples:
        >>> from semantica.export.methods import export_rdf
        >>> export_rdf(kg, "output.ttl", format="turtle")
        >>> export_rdf(entities, "output.rdf", format="rdfxml")
    """
    # Check for custom method in registry
    custom_method = method_registry.get("rdf", method)
    if custom_method and custom_method is not export_rdf:
        try:
            return custom_method(data, file_path, format=format, **kwargs)
        except Exception as e:
            logger.warning(
                f"Custom method {method} failed: {e}, falling back to default"
            )

    try:
        # Get config
        config = export_config.get_method_config("rdf")
        config.update(kwargs)

        exporter = RDFExporter(**config)
        exporter.export(data, file_path, format=format, **kwargs)

    except Exception as e:
        logger.error(f"Failed to export RDF: {e}")
        raise


def export_json(
    data: Union[Dict[str, Any], List[Dict[str, Any]]],
    file_path: Union[str, Path],
    format: str = "json",
    method: str = "default",
    **kwargs,
) -> None:
    """
    Export data to JSON/JSON-LD format (convenience function).

    This is a user-friendly wrapper that exports data to JSON or JSON-LD format.

    Args:
        data: Data to export (knowledge graph, entities, relationships)
        file_path: Output JSON file path
        format: Export format (default: "json")
            - "json": Standard JSON format
            - "json-ld": JSON-LD format
        method: Export method (default: "default")
        **kwargs: Additional options passed to JSONExporter

    Examples:
        >>> from semantica.export.methods import export_json
        >>> export_json(kg, "output.json", format="json")
        >>> export_json(kg, "output.jsonld", format="json-ld")
    """
    # Check for custom method in registry
    custom_method = method_registry.get("json", method)
    if custom_method and custom_method is not export_json:
        try:
            return custom_method(data, file_path, format=format, **kwargs)
        except Exception as e:
            logger.warning(
                f"Custom method {method} failed: {e}, falling back to default"
            )

    try:
        # Get config
        config = export_config.get_method_config("json")
        config.update(kwargs)
        config["format"] = format

        exporter = JSONExporter(**config)
        exporter.export(data, file_path, format=format, **kwargs)

    except Exception as e:
        logger.error(f"Failed to export JSON: {e}")
        raise


def export_csv(
    data: Union[List[Dict[str, Any]], Dict[str, List[Dict[str, Any]]]],
    file_path: Union[str, Path],
    method: str = "default",
    **kwargs,
) -> None:
    """
    Export data to CSV format (convenience function).

    This is a user-friendly wrapper that exports data to CSV format.

    Args:
        data: Data to export (list of dicts or dict with list values)
        file_path: Output CSV file path (or base path for multiple files)
        method: Export method (default: "default")
        **kwargs: Additional options passed to CSVExporter

    Examples:
        >>> from semantica.export.methods import export_csv
        >>> export_csv(entities, "entities.csv")
        >>> export_csv({"entities": [...], "relationships": [...]}, "output_base")
    """
    # Check for custom method in registry
    custom_method = method_registry.get("csv", method)
    if custom_method and custom_method is not export_csv:
        try:
            return custom_method(data, file_path, **kwargs)
        except Exception as e:
            logger.warning(
                f"Custom method {method} failed: {e}, falling back to default"
            )

    try:
        # Get config
        config = export_config.get_method_config("csv")
        config.update(kwargs)

        exporter = CSVExporter(**config)
        exporter.export(data, file_path, **kwargs)

    except Exception as e:
        logger.error(f"Failed to export CSV: {e}")
        raise


def export_arrow(
    data: Union[List[Dict[str, Any]], Dict[str, List[Dict[str, Any]]]],
    file_path: Union[str, Path],
    method: str = "default",
    **kwargs,
) -> None:
    """
    Export data to Apache Arrow format (convenience function).

    This is a user-friendly wrapper that exports data to Arrow IPC format.

    Args:
        data: Data to export (list of dicts or dict with list values)
        file_path: Output Arrow file path (or base path for multiple files)
        method: Export method (default: "default")
        **kwargs: Additional options passed to ArrowExporter

    Examples:
        >>> from semantica.export.methods import export_arrow
        >>> export_arrow(entities, "entities.arrow")
        >>> export_arrow({"entities": [...], "relationships": [...]}, "output_base")
    """
    # Check for custom method in registry
    custom_method = method_registry.get("arrow", method)
    if custom_method and custom_method is not export_arrow:
        try:
            return custom_method(data, file_path, **kwargs)
        except Exception as e:
            logger.warning(
                f"Custom method {method} failed: {e}, falling back to default"
            )

    try:
        # Get config
        config = export_config.get_method_config("arrow")
        config.update(kwargs)

        exporter = ArrowExporter(**config)
        exporter.export(data, file_path, **kwargs)

    except Exception as e:
        logger.error(f"Failed to export Arrow: {e}")
        raise


def export_parquet(
    data: Union[List[Dict[str, Any]], Dict[str, List[Dict[str, Any]]]],
    file_path: Union[str, Path],
    compression: str = "snappy",
    method: str = "default",
    **kwargs,
) -> None:
    """
    Export data to Apache Parquet format (convenience function).

    This is a user-friendly wrapper that exports data to Parquet columnar format,
    optimized for analytics and data warehousing workflows.

    Args:
        data: Data to export (list of dicts or dict with list values)
        file_path: Output Parquet file path (or base path for multiple files)
        compression: Compression codec (default: "snappy")
            - "snappy": Fast compression (default)
            - "gzip": Better compression ratio
            - "brotli": Best compression ratio
            - "zstd": Balanced compression and speed
            - "lz4": Very fast compression
            - "none": No compression
        method: Export method (default: "default")
        **kwargs: Additional options passed to ParquetExporter

    Examples:
        >>> from semantica.export.methods import export_parquet
        >>> export_parquet(entities, "entities.parquet", compression="snappy")
        >>> export_parquet({"entities": [...], "relationships": [...]}, "output_base")
    """
    if not PARQUET_AVAILABLE:
        raise ImportError(
            "ParquetExporter is not available. Please install pyarrow with: "
            "pip install pyarrow"
        )

    # Check for custom method in registry
    custom_method = method_registry.get("parquet", method)
    if custom_method and custom_method is not export_parquet:
        try:
            return custom_method(data, file_path, compression=compression, **kwargs)
        except Exception as e:
            logger.warning(
                f"Custom method {method} failed: {e}, falling back to default"
            )

    try:
        # Get config
        config = export_config.get_method_config("parquet")
        config.update(kwargs)

        exporter = ParquetExporter(compression=compression, **config)
        exporter.export(data, file_path, **kwargs)

    except Exception as e:
        logger.error(f"Failed to export Parquet: {e}")
        raise


def export_graph(
    graph_data: Dict[str, Any],
    file_path: Union[str, Path],
    format: str = "json",
    method: str = "default",
    **kwargs,
) -> None:
    """
    Export graph data to graph format (convenience function).

    This is a user-friendly wrapper that exports graph data to various graph formats.

    Args:
        graph_data: Graph data dictionary with nodes and edges
        file_path: Output graph file path
        format: Graph format (default: "json")
            - "graphml": GraphML format
            - "gexf": GEXF format
            - "dot": DOT format
            - "json": JSON graph format
        method: Export method (default: "default")
        **kwargs: Additional options passed to GraphExporter

    Examples:
        >>> from semantica.export.methods import export_graph
        >>> export_graph(graph_data, "graph.graphml", format="graphml")
        >>> export_graph(graph_data, "graph.gexf", format="gexf")
    """
    # Check for custom method in registry
    custom_method = method_registry.get("graph", method)
    if custom_method and custom_method is not export_graph:
        try:
            return custom_method(graph_data, file_path, format=format, **kwargs)
        except Exception as e:
            logger.warning(
                f"Custom method {method} failed: {e}, falling back to default"
            )

    try:
        # Get config
        config = export_config.get_method_config("graph")
        config.update(kwargs)
        config["format"] = format

        exporter = GraphExporter(**config)
        exporter.export(graph_data, file_path, format=format, **kwargs)

    except Exception as e:
        logger.error(f"Failed to export graph: {e}")
        raise


def export_yaml(
    data: Union[Dict[str, Any], List[Dict[str, Any]]],
    file_path: Union[str, Path],
    method: str = "semantic_network",
    **kwargs,
) -> None:
    """
    Export data to YAML format (convenience function).

    This is a user-friendly wrapper that exports data to YAML format.

    Args:
        data: Data to export (semantic network, entities, relationships)
        file_path: Output YAML file path
        method: Export method (default: "semantic_network")
            - "semantic_network": Semantic network YAML export
            - "schema": Schema YAML export
        **kwargs: Additional options passed to YAML exporters

    Examples:
        >>> from semantica.export.methods import export_yaml
        >>> export_yaml(semantic_network, "network.yaml", method="semantic_network")
        >>> export_yaml(schema, "schema.yaml", method="schema")
    """
    # Check for custom method in registry
    custom_method = method_registry.get("yaml", method)
    if custom_method and custom_method is not export_yaml:
        try:
            return custom_method(data, file_path, **kwargs)
        except Exception as e:
            logger.warning(
                f"Custom method {method} failed: {e}, falling back to default"
            )

    try:
        # Get config
        config = export_config.get_method_config("yaml")
        config.update(kwargs)

        if method == "semantic_network":
            exporter = SemanticNetworkYAMLExporter(**config)
            exporter.export(data, file_path, **kwargs)
        elif method == "schema":
            exporter = YAMLSchemaExporter(**config)
            yaml_content = exporter.export_ontology_schema(data, **kwargs)
            with open(file_path, "w", encoding="utf-8") as f:
                f.write(yaml_content)
        else:
            raise ProcessingError(f"Unknown YAML export method: {method}")

    except Exception as e:
        logger.error(f"Failed to export YAML: {e}")
        raise


def export_owl(
    ontology: Dict[str, Any],
    file_path: Union[str, Path],
    format: str = "owl-xml",
    method: str = "default",
    **kwargs,
) -> None:
    """
    Export ontology to OWL format (convenience function).

    This is a user-friendly wrapper that exports ontologies to OWL format.

    Args:
        ontology: Ontology data dictionary
        file_path: Output OWL file path
        format: OWL format (default: "owl-xml")
            - "owl-xml": OWL/XML format
            - "turtle": OWL in Turtle format
        method: Export method (default: "default")
        **kwargs: Additional options passed to OWLExporter

    Examples:
        >>> from semantica.export.methods import export_owl
        >>> export_owl(ontology, "ontology.owl", format="owl-xml")
        >>> export_owl(ontology, "ontology.ttl", format="turtle")
    """
    # Check for custom method in registry
    custom_method = method_registry.get("owl", method)
    if custom_method and custom_method is not export_owl:
        try:
            return custom_method(ontology, file_path, format=format, **kwargs)
        except Exception as e:
            logger.warning(
                f"Custom method {method} failed: {e}, falling back to default"
            )

    try:
        # Get config
        config = export_config.get_method_config("owl")
        config.update(kwargs)
        config["format"] = format

        exporter = OWLExporter(**config)
        exporter.export(ontology, file_path, format=format, **kwargs)

    except Exception as e:
        logger.error(f"Failed to export OWL: {e}")
        raise


def export_vector(
    vectors: Union[List, Dict[str, Any]],
    file_path: Union[str, Path],
    format: str = "json",
    method: str = "default",
    **kwargs,
) -> None:
    """
    Export vectors to vector format (convenience function).

    This is a user-friendly wrapper that exports vectors to various vector formats.

    Args:
        vectors: Vector data (list of vectors or dict with vector data)
        file_path: Output vector file path
        format: Vector format (default: "json")
            - "json": JSON vector format
            - "numpy": NumPy format
            - "binary": Binary format
            - "faiss": FAISS format
        method: Export method (default: "default")
        **kwargs: Additional options passed to VectorExporter

    Examples:
        >>> from semantica.export.methods import export_vector
        >>> export_vector(vectors, "vectors.json", format="json")
        >>> export_vector(vectors, "vectors.npy", format="numpy")
    """
    # Check for custom method in registry
    custom_method = method_registry.get("vector", method)
    if custom_method and custom_method is not export_vector:
        try:
            return custom_method(vectors, file_path, format=format, **kwargs)
        except Exception as e:
            logger.warning(
                f"Custom method {method} failed: {e}, falling back to default"
            )

    try:
        # Get config
        config = export_config.get_method_config("vector")
        config.update(kwargs)
        config["format"] = format

        exporter = VectorExporter(**config)
        exporter.export(vectors, file_path, format=format, **kwargs)

    except Exception as e:
        logger.error(f"Failed to export vector: {e}")
        raise


def export_lpg(
    knowledge_graph: Dict[str, Any],
    file_path: Union[str, Path],
    method: str = "cypher",
    **kwargs,
) -> None:
    """
    Export knowledge graph to LPG format (convenience function).

    This is a user-friendly wrapper that exports knowledge graphs to LPG format
    (Cypher queries for Neo4j, Memgraph, etc.).

    Args:
        knowledge_graph: Knowledge graph dictionary with entities and relationships
        file_path: Output Cypher file path
        method: Export method (default: "cypher")
            - "cypher": Cypher query format
            - "lpg": Labeled Property Graph format
        **kwargs: Additional options passed to LPGExporter

    Examples:
        >>> from semantica.export.methods import export_lpg
        >>> export_lpg(kg, "graph.cypher", method="cypher")
    """
    # Check for custom method in registry
    custom_method = method_registry.get("lpg", method)
    if custom_method and custom_method is not export_lpg:
        try:
            return custom_method(knowledge_graph, file_path, **kwargs)
        except Exception as e:
            logger.warning(
                f"Custom method {method} failed: {e}, falling back to default"
            )

    try:
        # Get config
        config = export_config.get_method_config("lpg")
        config.update(kwargs)

        exporter = LPGExporter(**config)
        exporter.export_knowledge_graph(knowledge_graph, file_path, **kwargs)

    except Exception as e:
        logger.error(f"Failed to export LPG: {e}")
        raise


def export_neo4j_csv(
    knowledge_graph: Any,
    output_dir: Union[str, Path],
    method: str = "default",
    **kwargs,
) -> Dict[str, Path]:
    """
    Export knowledge graph to Neo4j bulk-import CSV files.

    This wrapper writes deterministic ``nodes.csv`` and ``relationships.csv``
    files that can be imported with ``neo4j-admin database import``.

    Args:
        knowledge_graph: Knowledge graph dictionary or object with graph attributes.
        output_dir: Output directory for Neo4j CSV files.
        method: Export method (default: "default").
        **kwargs: Additional options passed to ``Neo4jCSVExporter``.

    Returns:
        Mapping with ``"nodes"`` and ``"relationships"`` output paths.
    """
    custom_method = method_registry.get("neo4j_csv", method)
    if custom_method and custom_method is not export_neo4j_csv:
        try:
            return custom_method(knowledge_graph, output_dir, **kwargs)
        except Exception as e:
            logger.warning(
                f"Custom method {method} failed: {e}, falling back to default"
            )

    try:
        config = export_config.get_method_config("neo4j_csv")

        # Split kwargs: constructor-level settings vs per-call export() options.
        # Passing all kwargs to both the constructor AND export_knowledge_graph
        # causes dialect params like delimiter to reach csv.writer twice.
        _init_params = frozenset({
            "node_file_name",
            "relationship_file_name",
            "encoding",
            "delimiter",
            "label_separator",
            "strict",
            "config",
        })
        init_kwargs = {k: v for k, v in kwargs.items() if k in _init_params}
        call_kwargs = {k: v for k, v in kwargs.items() if k not in _init_params}

        config.update(init_kwargs)
        exporter = Neo4jCSVExporter(**config)
        return exporter.export_knowledge_graph(knowledge_graph, output_dir, **call_kwargs)

    except Exception as e:
        logger.error(f"Failed to export Neo4j CSV: {e}")
        raise


def export_arango(
    knowledge_graph: Dict[str, Any],
    file_path: Union[str, Path],
    method: str = "default",
    **kwargs,
) -> None:
    """
    Export knowledge graph to ArangoDB AQL format (convenience function).

    This is a user-friendly wrapper that exports knowledge graphs to ArangoDB
    multi-model databases via AQL INSERT statements.

    Args:
        knowledge_graph: Knowledge graph dictionary with entities and relationships
        file_path: Output AQL file path
        method: Export method (default: "default")
        **kwargs: Additional options passed to ArangoAQLExporter:
            - vertex_collection: Override default vertex collection name
            - edge_collection: Override default edge collection name
            - batch_size: Batch size for INSERT operations
            - include_collection_creation: Whether to include collection
              creation statements

    Examples:
        >>> from semantica.export.methods import export_arango
        >>> export_arango(kg, "output.aql")
        >>> export_arango(
        ...     kg,
        ...     "graph.aql",
        ...     vertex_collection="nodes",
        ...     edge_collection="links",
        ... )
    """
    # Check for custom method in registry
    custom_method = method_registry.get("arango", method)
    if custom_method and custom_method is not export_arango:
        try:
            return custom_method(knowledge_graph, file_path, **kwargs)
        except Exception as e:
            logger.warning(
                f"Custom method {method} failed: {e}, falling back to default"
            )

    try:
        # Get config
        config = export_config.get_method_config("arango")
        config.update(kwargs)

        exporter = ArangoAQLExporter(**config)
        exporter.export_knowledge_graph(knowledge_graph, file_path, **kwargs)

    except Exception as e:
        logger.error(f"Failed to export ArangoDB AQL: {e}")
        raise


def generate_report(
    data: Dict[str, Any],
    file_path: Union[str, Path],
    format: str = "markdown",
    method: str = "default",
    **kwargs,
) -> None:
    """
    Generate report (convenience function).

    This is a user-friendly wrapper that generates reports in various formats.

    Args:
        data: Report data dictionary
        file_path: Output report file path
        format: Report format (default: "markdown")
            - "html": HTML report format
            - "markdown": Markdown report format
            - "json": JSON report format
            - "text": Plain text report format
        method: Report generation method (default: "default")
        **kwargs: Additional options passed to ReportGenerator

    Examples:
        >>> from semantica.export.methods import generate_report
        >>> generate_report(metrics, "report.html", format="html")
        >>> generate_report(analysis, "report.md", format="markdown")
    """
    # Check for custom method in registry
    custom_method = method_registry.get("report", method)
    if custom_method and custom_method is not generate_report:
        try:
            return custom_method(data, file_path, format=format, **kwargs)
        except Exception as e:
            logger.warning(
                f"Custom method {method} failed: {e}, falling back to default"
            )

    try:
        # Get config
        config = export_config.get_method_config("report")
        config.update(kwargs)
        config["format"] = format

        generator = ReportGenerator(**config)
        generator.generate_report(data, file_path, format=format, **kwargs)

    except Exception as e:
        logger.error(f"Failed to generate report: {e}")
        raise


def export_knowledge_graph(
    knowledge_graph: Dict[str, Any],
    file_path: Union[str, Path],
    format: str = "json",
    method: Optional[str] = None,
    **kwargs,
) -> None:
    """
    Export knowledge graph to specified format (unified convenience function).

    This is a user-friendly wrapper that automatically routes to the appropriate
    exporter based on the file extension or format parameter.

    Args:
        knowledge_graph: Knowledge graph dictionary with entities and
            relationships
        file_path: Output file path (format auto-detected from extension
            if format not specified)
        format: Export format (auto-detected from file extension if not
            specified)
            - "json", "json-ld": JSONExporter
            - "csv": CSVExporter
            - "ttl", "turtle": RDFExporter (turtle)
            - "rdf", "rdfxml": RDFExporter (rdfxml)
            - "graphml": GraphExporter (graphml)
            - "gexf": GraphExporter (gexf)
            - "dot": GraphExporter (dot)
            - "yaml", "yml": YAML exporters
            - "owl": OWLExporter
            - "cypher": LPGExporter
            - "aql": ArangoAQLExporter
        method: Optional specific export method
        **kwargs: Additional options passed to exporter

    Examples:
        >>> from semantica.export.methods import export_knowledge_graph
        >>> export_knowledge_graph(kg, "output.json", format="json")
        >>> export_knowledge_graph(kg, "output.ttl", format="turtle")
        >>> export_knowledge_graph(kg, "output.cypher", format="cypher")
    """
    # Auto-detect format from file extension if not specified
    if not format:
        file_path_obj = Path(file_path)
        ext = file_path_obj.suffix.lower()
        format_map = {
            ".json": "json",
            ".jsonld": "json-ld",
            ".csv": "csv",
            ".ttl": "turtle",
            ".rdf": "rdfxml",
            ".graphml": "graphml",
            ".gexf": "gexf",
            ".dot": "dot",
            ".yaml": "yaml",
            ".yml": "yaml",
            ".owl": "owl-xml",
            ".cypher": "cypher",
            ".aql": "aql",
            ".parquet": "parquet",
        }
        format = format_map.get(ext, "json")

    # Route to appropriate exporter
    if format in ["json", "json-ld"]:
        export_json(knowledge_graph, file_path, format=format, method=method, **kwargs)
    elif format == "csv":
        export_csv(knowledge_graph, file_path, method=method, **kwargs)
    elif format in ["turtle", "rdfxml", "jsonld", "ntriples", "n3"]:
        export_rdf(knowledge_graph, file_path, format=format, method=method, **kwargs)
    elif format in ["graphml", "gexf", "dot"]:
        export_graph(knowledge_graph, file_path, format=format, method=method, **kwargs)
    elif format in ["yaml", "yml"]:
        export_yaml(knowledge_graph, file_path, method=method, **kwargs)
    elif format in ["owl-xml", "owl"]:
        export_owl(knowledge_graph, file_path, format=format, method=method, **kwargs)
    elif format == "cypher":
        export_lpg(knowledge_graph, file_path, method=method, **kwargs)
    elif format in ["neo4j_csv", "neo4j-csv"]:
        # file_path is treated as the output directory; nodes.csv and
        # relationships.csv are written inside it.
        export_neo4j_csv(knowledge_graph, file_path, method=method, **kwargs)
    elif format == "aql":
        export_arango(knowledge_graph, file_path, method=method, **kwargs)
    elif format == "parquet":
        export_parquet(knowledge_graph, file_path, method=method, **kwargs)
    else:
        raise ProcessingError(f"Unknown export format: {format}")


def get_export_method(task: str, name: str) -> Optional[Callable]:
    """
    Get a registered export method.

    Args:
        task: Task type ("rdf", "json", "csv", "graph", "yaml", "owl",
            "vector", "lpg", "report", "export")
        name: Method name

    Returns:
        Registered method or None if not found

    Examples:
        >>> from semantica.export.methods import get_export_method
        >>> method = get_export_method("json", "custom_method")
        >>> if method:
        ...     result = method(data, "output.json")
    """
    return method_registry.get(task, name)


def list_available_methods(task: Optional[str] = None) -> Dict[str, List[str]]:
    """
    List all available export methods.

    Args:
        task: Optional task type filter

    Returns:
        Dictionary mapping task types to method names

    Examples:
        >>> from semantica.export.methods import list_available_methods
        >>> all_methods = list_available_methods()
        >>> json_methods = list_available_methods("json")
    """
    return method_registry.list_all(task)


# Register default methods
method_registry.register("rdf", "default", export_rdf)
method_registry.register("rdf", "turtle", export_rdf)
method_registry.register("rdf", "rdfxml", export_rdf)
method_registry.register("rdf", "jsonld", export_rdf)
method_registry.register("json", "default", export_json)
method_registry.register("json", "json", export_json)
method_registry.register("json", "json-ld", export_json)
method_registry.register("csv", "default", export_csv)
method_registry.register("csv", "csv", export_csv)
method_registry.register("graph", "default", export_graph)
method_registry.register("graph", "graphml", export_graph)
method_registry.register("graph", "gexf", export_graph)
method_registry.register("graph", "dot", export_graph)
method_registry.register("yaml", "default", export_yaml)
method_registry.register("yaml", "semantic_network", export_yaml)
method_registry.register("yaml", "schema", export_yaml)
method_registry.register("owl", "default", export_owl)
method_registry.register("owl", "owl-xml", export_owl)
method_registry.register("owl", "turtle", export_owl)
method_registry.register("vector", "default", export_vector)
method_registry.register("vector", "json", export_vector)
method_registry.register("vector", "numpy", export_vector)
method_registry.register("lpg", "default", export_lpg)
method_registry.register("lpg", "cypher", export_lpg)
method_registry.register("neo4j_csv", "default", export_neo4j_csv)
method_registry.register("neo4j_csv", "neo4j_csv", export_neo4j_csv)
method_registry.register("neo4j_csv", "neo4j-csv", export_neo4j_csv)
method_registry.register("arango", "default", export_arango)
method_registry.register("arango", "aql", export_arango)
method_registry.register("report", "default", generate_report)
method_registry.register("report", "html", generate_report)
method_registry.register("report", "markdown", generate_report)
method_registry.register("export", "default", export_knowledge_graph)
method_registry.register("export", "knowledge_graph", export_knowledge_graph)
