"""
Graph Exporter Module

This module provides comprehensive graph format export capabilities for the
Semantica framework, enabling knowledge graph export to various graph formats
for visualization and analysis tools.

Key Features:
    - Multiple graph format support (GraphML, GEXF, DOT, JSON)
    - Knowledge graph to graph format conversion
    - Node and edge attribute support
    - Graph visualization export
    - Configurable attribute inclusion

Example Usage:
    >>> from semantica.export import GraphExporter
    >>> exporter = GraphExporter(format="graphml", include_attributes=True)
    >>> exporter.export_knowledge_graph(kg, "graph.graphml")
    >>> exporter.export(graph_data, "graph.gexf", format="gexf")

Author: Semantica Contributors
License: MIT
"""

import json
from pathlib import Path
from typing import Any, Dict, List, Optional, Union

from ..utils.exceptions import ProcessingError, ValidationError
from ..utils.helpers import ensure_directory
from ..utils.logging import get_logger
from ..utils.progress_tracker import get_progress_tracker


class GraphExporter:
    """
    Graph exporter for knowledge graphs and network data.

    This class provides comprehensive graph format export functionality for
    knowledge graphs, supporting multiple graph formats for visualization
    and analysis tools.

    Features:
        - Multiple graph format support (GraphML, GEXF, DOT, JSON)
        - Knowledge graph to graph format conversion
        - Node and edge attribute support
        - Graph visualization export
        - Configurable attribute inclusion

    Example Usage:
        >>> exporter = GraphExporter(
        ...     format="graphml",
        ...     include_attributes=True
        ... )
        >>> exporter.export_knowledge_graph(kg, "graph.graphml")
    """

    def __init__(
        self,
        format: str = "json",
        include_attributes: bool = True,
        config: Optional[Dict[str, Any]] = None,
        **kwargs,
    ):
        """
        Initialize graph exporter.

        Sets up the exporter with specified graph format and attribute options.

        Args:
            format: Default export format - 'graphml', 'gexf', 'json', or 'dot'
                   (default: 'json')
            include_attributes: Whether to include node/edge attributes in export
                              (default: True)
            config: Optional configuration dictionary (merged with kwargs)
            **kwargs: Additional configuration options
        """
        self.logger = get_logger("graph_exporter")
        self.config = config or {}
        self.config.update(kwargs)

        # Graph export configuration
        self.format = format
        self.include_attributes = include_attributes

        # Initialize progress tracker
        self.progress_tracker = get_progress_tracker()
        # Ensure progress tracker is enabled
        if not self.progress_tracker.enabled:
            self.progress_tracker.enabled = True

        self.logger.debug(
            f"Graph exporter initialized: format={format}, "
            f"include_attributes={include_attributes}"
        )

    def export(
        self,
        graph_data: Dict[str, Any],
        file_path: Optional[Union[str, Path]] = None,
        format: Optional[str] = None,
        **options,
    ) -> None:
        """
        Export graph data to file in specified format.

        This method exports graph data (nodes and edges) to various graph formats
        supported by visualization and analysis tools.

        Supported Formats:
            - "json": JSON format (default)
            - "graphml": GraphML format (XML-based, for Cytoscape, yEd, etc.)
            - "gexf": GEXF format (for Gephi)
            - "dot": DOT format (for Graphviz)

        Args:
            graph_data: Graph data dictionary containing:
                - nodes: List of node dictionaries with id, label, type, attributes
                - edges: List of edge dictionaries with source, target, type, attributes
                - metadata: Metadata dictionary (optional)
            file_path: Output file path (or use output_path in options)
            format: Export format - 'graphml', 'gexf', 'json', or 'dot'
                   (default: self.format)
            **options: Additional format-specific options

        Raises:
            ValidationError: If format is unsupported
            ValueError: If file_path is not provided

        Example:
            >>> graph_data = {
            ...     "nodes": [{"id": "n1", "label": "Node 1"}],
            ...     "edges": [{"source": "n1", "target": "n2", "type": "RELATED"}]
            ... }
            >>> exporter.export(graph_data, "graph.graphml", format="graphml")
        """
        # Handle file_path from options if not provided
        if file_path is None:
            file_path = options.get("output_path")
            
        if file_path is None:
            raise ValueError("file_path argument is required")

        # Track graph export
        tracking_id = self.progress_tracker.start_tracking(
            file=str(file_path),
            module="export",
            submodule="GraphExporter",
            message=f"Exporting graph to {format or self.format}: {file_path}",
        )

        try:
            file_path = Path(file_path)
            ensure_directory(file_path.parent)

            export_format = format or self.format

            self.logger.debug(
                f"Exporting graph to {export_format}: {file_path}, "
                f"nodes={len(graph_data.get('nodes', []))}, "
                f"edges={len(graph_data.get('edges', []))}"
            )

            self.progress_tracker.update_tracking(
                tracking_id, message=f"Exporting in {export_format} format..."
            )
            # Export based on format
            if export_format == "json":
                self._export_json(graph_data, file_path, **options)
            elif export_format == "graphml":
                self._export_graphml(graph_data, file_path, **options)
            elif export_format == "gexf":
                self._export_gexf(graph_data, file_path, **options)
            elif export_format == "dot":
                self._export_dot(graph_data, file_path, **options)
            else:
                raise ValidationError(
                    f"Unsupported graph format: {export_format}. "
                    f"Supported formats: json, graphml, gexf, dot"
                )

            self.logger.info(f"Exported graph ({export_format}) to: {file_path}")
            self.progress_tracker.stop_tracking(
                tracking_id,
                status="completed",
                message=f"Exported graph ({export_format}) to: {file_path}",
            )

        except Exception as e:
            self.progress_tracker.stop_tracking(
                tracking_id, status="failed", message=str(e)
            )
            raise

    def export_knowledge_graph(
        self,
        knowledge_graph: Dict[str, Any],
        file_path: Optional[Union[str, Path]] = None,
        format: Optional[str] = None,
        **options,
    ) -> None:
        """
        Export knowledge graph to graph format.

        Args:
            knowledge_graph: Knowledge graph dictionary
            file_path: Output file path (or use output_path in options)
            format: Export format
            **options: Additional options
        """
        # Handle file_path from options if not provided
        if file_path is None:
            file_path = options.get("output_path")
            
        if file_path is None:
            raise ValueError("file_path argument is required")

        # Convert knowledge graph to graph format
        graph_data = self._convert_kg_to_graph(knowledge_graph)
        self.export(graph_data, file_path, format=format, **options)

    def _convert_kg_to_graph(self, kg: Dict[str, Any]) -> Dict[str, Any]:
        """
        Convert knowledge graph to graph format.

        This method converts a knowledge graph (entities and relationships) to
        a graph structure (nodes and edges) suitable for graph format export.

        Conversion:
            - Entities -> Nodes (with id, label, type, attributes)
            - Relationships -> Edges (with source, target, type, attributes)

        Args:
            kg: Knowledge graph dictionary containing:
                - entities: List of entity dictionaries
                - relationships: List of relationship dictionaries
                - metadata: Metadata dictionary (optional)

        Returns:
            Dictionary with nodes, edges, and metadata in graph format
        """
        nodes = []
        edges = []

        # Convert entities to nodes
        entities = kg.get("entities", [])
        for entity in entities:
            node = {
                "id": entity.get("id") or entity.get("entity_id"),
                "label": (
                    entity.get("text")
                    or entity.get("label")
                    or entity.get("name")
                    or ""
                ),
                "type": entity.get("type") or entity.get("entity_type", "entity"),
            }

            # Add attributes if requested
            if self.include_attributes:
                node["attributes"] = {
                    "confidence": entity.get("confidence", 1.0),
                    **entity.get("metadata", {}),
                }

            nodes.append(node)

        # Convert relationships to edges
        relationships = kg.get("relationships", [])
        for rel in relationships:
            edge = {
                "source": rel.get("source_id") or rel.get("source"),
                "target": rel.get("target_id") or rel.get("target"),
                "type": rel.get("type") or rel.get("relationship_type", "related_to"),
            }

            # Add attributes if requested
            if self.include_attributes:
                edge["attributes"] = {
                    "confidence": rel.get("confidence", 1.0),
                    **rel.get("metadata", {}),
                }

            edges.append(edge)

        self.logger.debug(
            f"Converted knowledge graph: {len(nodes)} node(s), {len(edges)} edge(s)"
        )

        return {"nodes": nodes, "edges": edges, "metadata": kg.get("metadata", {})}

    def _export_json(
        self, graph_data: Dict[str, Any], file_path: Path, **options
    ) -> None:
        """
        Export graph to JSON format.

        This method exports graph data to JSON format using the helper function.

        Args:
            graph_data: Graph data dictionary with nodes and edges
            file_path: Output JSON file path
            **options: Additional options (unused)
        """
        from ..utils.helpers import write_json_file

        write_json_file(graph_data, file_path, indent=2)

    def _export_graphml(
        self, graph_data: Dict[str, Any], file_path: Path, **options
    ) -> None:
        """
        Export graph to GraphML format.

        GraphML is an XML-based format for graph data, widely supported by
        graph visualization tools like Cytoscape, yEd, and Gephi.

        Args:
            graph_data: Graph data dictionary with nodes and edges
            file_path: Output GraphML file path
            **options: Additional options (unused)
        """
        lines = ['<?xml version="1.0" encoding="UTF-8"?>']
        lines.append('<graphml xmlns="http://graphml.graphdrawing.org/xmlns"')
        lines.append('         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"')
        lines.append(
            '         xsi:schemaLocation="http://graphml.graphdrawing.org/xmlns'
        )
        lines.append('         http://graphml.graphdrawing.org/xmlns/1.0/graphml.xsd">')
        lines.append("")

        # Define attribute keys.
        # GraphML requires every key id referenced by a <data> element to be
        # declared here with a matching <key> element.
        #
        # for="all"  — key is valid on both nodes and edges
        # for="node" — key is valid on nodes only
        # for="edge" — key is valid on edges only
        #
        # label    : used on <node> (human-readable label) and <edge> (type).
        #            Declared for="all" so both uses are schema-valid.
        # type     : node entity type; only written on nodes.
        # confidence: written on both nodes and edges when include_attributes
        #             is True; declared for="all" so edge confidence is valid.
        lines.append(
            '  <key id="label" for="all" attr.name="label" attr.type="string"/>'
        )
        lines.append(
            '  <key id="type" for="node" attr.name="type" attr.type="string"/>'
        )
        lines.append(
            '  <key id="confidence" for="all" attr.name="confidence" attr.type="double"/>'
        )
        lines.append("")

        # Graph declaration (directed graph)
        lines.append('  <graph id="G" edgedefault="directed">')
        lines.append("")

        # xml.sax.saxutils helpers:
        #   escape(v)     – escapes & < > in text node content
        #   quoteattr(v)  – escapes & < > " ' and wraps in the
        #                   appropriate quote character for use as an
        #                   XML attribute value (including the quotes)
        from xml.sax.saxutils import escape, quoteattr

        # Export nodes
        nodes = graph_data.get("nodes", [])
        for node in nodes:
            node_id = str(node.get("id") or "")
            label = str(node.get("label") or "")
            node_type = str(node.get("type") or "")

            # quoteattr produces the surrounding quotes; do NOT add extra "…"
            lines.append(f"    <node id={quoteattr(node_id)}>")
            lines.append(f"      <data key=\"label\">{escape(label)}</data>")
            lines.append(f"      <data key=\"type\">{escape(node_type)}</data>")

            # Add attributes if requested
            if self.include_attributes and "attributes" in node:
                attrs = node["attributes"]
                if "confidence" in attrs:
                    lines.append(
                        f"      <data key=\"confidence\">{escape(str(attrs['confidence']))}</data>"
                    )

            lines.append("    </node>")

        lines.append("")

        # Export edges
        edges = graph_data.get("edges", [])
        for edge in edges:
            source = str(edge.get("source") or "")
            target = str(edge.get("target") or "")
            edge_type = str(edge.get("type") or "")

            lines.append(f"    <edge source={quoteattr(source)} target={quoteattr(target)}>")
            lines.append(f"      <data key=\"label\">{escape(edge_type)}</data>")

            # Add attributes if requested
            if self.include_attributes and "attributes" in edge:
                attrs = edge["attributes"]
                if "confidence" in attrs:
                    lines.append(
                        f"      <data key=\"confidence\">{escape(str(attrs['confidence']))}</data>"
                    )

            lines.append("    </edge>")

        lines.append("  </graph>")
        lines.append("</graphml>")

        # Write GraphML file
        with open(file_path, "w", encoding="utf-8") as f:
            f.write("\n".join(lines))

        self.logger.debug(
            f"Exported GraphML: {len(nodes)} node(s), {len(edges)} edge(s)"
        )

    def _export_gexf(
        self, graph_data: Dict[str, Any], file_path: Path, **options
    ) -> None:
        """
        Export graph to GEXF format.

        GEXF (Graph Exchange XML Format) is an XML-based format primarily used
        by Gephi for graph visualization and analysis.

        Args:
            graph_data: Graph data dictionary with nodes and edges
            file_path: Output GEXF file path
            **options: Additional options (unused)
        """
        lines = ['<?xml version="1.0" encoding="UTF-8"?>']
        lines.append('<gexf xmlns="http://www.gexf.net/1.2draft" version="1.2">')
        lines.append('  <graph mode="static" defaultedgetype="directed">')
        lines.append("    <nodes>")

        # Export nodes
        nodes = graph_data.get("nodes", [])
        for node in nodes:
            node_id = node.get("id", "")
            label = node.get("label", "")

            lines.append(f'      <node id="{node_id}" label="{label}">')

            # Add attributes if requested
            if self.include_attributes and "attributes" in node:
                lines.append("        <attvalues>")
                attrs = node["attributes"]
                for key, value in attrs.items():
                    lines.append(f'          <attvalue for="{key}" value="{value}"/>')
                lines.append("        </attvalues>")

            lines.append("      </node>")

        lines.append("    </nodes>")
        lines.append("    <edges>")

        # Export edges
        edges = graph_data.get("edges", [])
        for i, edge in enumerate(edges):
            source = edge.get("source", "")
            target = edge.get("target", "")
            edge_type = edge.get("type", "")

            lines.append(
                f'      <edge id="{i}" source="{source}" target="{target}" label="{edge_type}">'
            )

            # Add attributes if requested
            if self.include_attributes and "attributes" in edge:
                lines.append("        <attvalues>")
                attrs = edge["attributes"]
                for key, value in attrs.items():
                    lines.append(f'          <attvalue for="{key}" value="{value}"/>')
                lines.append("        </attvalues>")

            lines.append("      </edge>")

        lines.append("    </edges>")
        lines.append("  </graph>")
        lines.append("</gexf>")

        # Write GEXF file
        with open(file_path, "w", encoding="utf-8") as f:
            f.write("\n".join(lines))

        self.logger.debug(f"Exported GEXF: {len(nodes)} node(s), {len(edges)} edge(s)")

    def _export_dot(
        self, graph_data: Dict[str, Any], file_path: Path, **options
    ) -> None:
        """
        Export graph to DOT format (Graphviz).

        DOT is a graph description language used by Graphviz for graph
        visualization. This format is human-readable and widely supported.

        Args:
            graph_data: Graph data dictionary with nodes and edges
            file_path: Output DOT file path
            **options: Additional options (unused)
        """
        lines = ["digraph G {"]  # Directed graph
        lines.append("  rankdir=LR;")  # Left-to-right layout
        lines.append("")

        # Export nodes
        nodes = graph_data.get("nodes", [])
        for node in nodes:
            # Escape quotes in IDs and labels
            node_id = node.get("id", "").replace('"', '\\"')
            label = node.get("label", "").replace('"', '\\"')
            node_type = node.get("type", "")

            # Build node attributes
            attributes = [f'label="{label}"']
            if node_type:
                attributes.append(f'type="{node_type}"')

            attrs_str = ", ".join(attributes)
            lines.append(f'  "{node_id}" [{attrs_str}];')

        lines.append("")

        # Export edges
        edges = graph_data.get("edges", [])
        for edge in edges:
            # Escape quotes in source, target, and type
            source = edge.get("source", "").replace('"', '\\"')
            target = edge.get("target", "").replace('"', '\\"')
            edge_type = edge.get("type", "").replace('"', '\\"')

            # Build edge attributes
            attributes = [f'label="{edge_type}"']
            attrs_str = ", ".join(attributes)
            lines.append(f'  "{source}" -> "{target}" [{attrs_str}];')

        lines.append("}")

        # Write DOT file
        with open(file_path, "w", encoding="utf-8") as f:
            f.write("\n".join(lines))

        self.logger.debug(f"Exported DOT: {len(nodes)} node(s), {len(edges)} edge(s)")
