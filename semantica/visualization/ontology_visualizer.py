"""
Ontology Visualizer Module

This module provides comprehensive visualization capabilities for ontologies in the
Semantica framework, including class hierarchy trees, property graphs, ontology structure
networks, class-property matrices, and ontology metrics dashboards.

Key Features:
    - Class hierarchy tree visualizations
    - Property graphs with domain/range relationships
    - Ontology structure network visualizations
    - Class-property relationship matrices
    - Ontology metrics dashboards
    - Support for multiple input formats (dict, SemanticNetwork, OntologyGenerator result)
    - Graphviz integration for hierarchy visualization
    - Interactive and static output formats

Main Classes:
    - OntologyVisualizer: Main ontology visualizer coordinator

Example Usage:
    >>> from semantica.visualization import OntologyVisualizer
    >>> viz = OntologyVisualizer(color_scheme="default")
    >>> fig = viz.visualize_hierarchy(ontology, output="interactive")
    >>> viz.visualize_properties(ontology, file_path="properties.html")
    >>> viz.visualize_structure(ontology, output="interactive")
    >>> viz.visualize_class_property_matrix(ontology, file_path="matrix.png")
    >>> viz.visualize_metrics(ontology, output="interactive")
    >>> viz.visualize_semantic_model(semantic_model, file_path="model.html")

Author: Semantica Contributors
License: MIT
"""

from pathlib import Path
from typing import Any, Dict, List, Optional, Union

import matplotlib.patches as mpatches
import matplotlib.pyplot as plt

try:
    import plotly.express as px
    import plotly.graph_objects as go
    from plotly.subplots import make_subplots
except (ImportError, OSError):
    px = None
    go = None
    make_subplots = None

from matplotlib.patches import FancyBboxPatch

try:
    import graphviz
except (ImportError, OSError):
    graphviz = None

from ..utils.exceptions import ProcessingError
from ..utils.logging import get_logger
from ..utils.progress_tracker import get_progress_tracker
from .utils.color_schemes import ColorPalette, ColorScheme
from .utils.export_formats import (
    export_matplotlib_figure,
    export_plotly_figure,
    save_html,
)
from .utils.layout_algorithms import HierarchicalLayout


class OntologyVisualizer:
    """
    Ontology visualizer.

    Provides visualization methods for ontologies including:
    - Class hierarchy trees
    - Property graphs
    - Ontology structure networks
    - Class-property matrices
    """

    def __init__(self, **config):
        """
        Initialize ontology visualizer.

        Args:
            **config: Configuration options:
                - color_scheme: Color scheme name
                - node_size: Base node size
        """
        self.logger = get_logger("ontology_visualizer")
        self.config = config
        self.progress_tracker = get_progress_tracker()
        # Ensure progress tracker is enabled
        if not self.progress_tracker.enabled:
            self.progress_tracker.enabled = True

        color_scheme_name = config.get("color_scheme", "default")
        try:
            self.color_scheme = ColorScheme[color_scheme_name.upper()]
        except (KeyError, AttributeError):
            self.color_scheme = ColorScheme.DEFAULT
        self.node_size = config.get("node_size", 15)

    def _check_dependencies(self, require_graphviz: bool = False):
        """Check if dependencies are available."""
        if require_graphviz:
            if graphviz is None:
                raise ProcessingError(
                    "Graphviz is required for DOT export. "
                    "Install with: pip install graphviz"
                )
        else:
            if px is None or go is None:
                raise ProcessingError(
                    "Plotly is required for ontology visualization. "
                    "Install with: pip install plotly"
                )

    def visualize_hierarchy(
        self,
        ontology: Dict[str, Any],
        output: str = "interactive",
        file_path: Optional[Union[str, Path]] = None,
        node_color_by: str = "level",
        node_size_by: str = "instances",
        hover_data: Optional[List[str]] = None,
        **options,
    ) -> Optional[Any]:
        """
        Visualize class hierarchy as tree.

        Implements the 5-step visualization process:
        1. Problem setting: Implicit in ontology selection
        2. Data analysis: Logs ontology statistics
        3. Layout: Hierarchical tree layout
        4. Styling: Configurable node color (e.g. by level) and size (e.g. by instances)
        5. Interaction: Rich hover data

        Args:
            ontology: Ontology dictionary with classes, or SemanticNetwork object,
                     or ontology generator result
            output: Output type ("interactive", "html", "png", "svg", "dot")
            file_path: Output file path
            node_color_by: Property to map to node color (default: "level")
            node_size_by: Property to map to node size (default: "instances")
            hover_data: List of properties to show in hover tooltip
            **options: Additional options

        Returns:
            Visualization figure or None
        """
        # Check dependencies
        if output == "dot":
            self._check_dependencies(require_graphviz=True)
        else:
            self._check_dependencies()

        tracking_id = self.progress_tracker.start_tracking(
            module="visualization",
            submodule="OntologyVisualizer",
            message="Visualizing ontology class hierarchy",
        )

        try:
            self.logger.info("Visualizing ontology class hierarchy")

            # Handle different input formats
            self.progress_tracker.update_tracking(
                tracking_id, message="Extracting classes from ontology..."
            )
            if hasattr(ontology, "classes"):
                # OntologyGenerator result object
                classes = ontology.classes if hasattr(ontology, "classes") else []
            elif isinstance(ontology, dict):
                classes = ontology.get("classes", ontology.get("class_definitions", []))
            else:
                classes = []

            # If no classes, try to extract from semantic network
            if not classes and isinstance(ontology, dict):
                # Check if it's a semantic model or semantic network
                semantic_network = ontology.get(
                    "semantic_network", ontology.get("network")
                )
                if semantic_network:
                    classes = self._extract_classes_from_semantic_network(
                        semantic_network
                    )

            if not classes:
                self.progress_tracker.stop_tracking(
                    tracking_id, status="failed", message="No classes found in ontology"
                )
                raise ProcessingError(
                    "No classes found in ontology. Please provide classes or a semantic network."
                )

            # Step 2: Data Analysis
            num_classes = len(classes)
            max_depth = 0
            for cls in classes:
                depth = self._calculate_class_depth(cls, classes)
                max_depth = max(max_depth, depth)
            
            self.logger.info(f"Ontology Analysis: {num_classes} classes, max depth {max_depth}")

            # If output is dot and graphviz is available, use it
            if output == "dot" and graphviz is not None and file_path:
                self.progress_tracker.update_tracking(
                    tracking_id, message="Generating Graphviz visualization..."
                )
                result = self._visualize_hierarchy_graphviz(
                    classes, file_path, **options
                )
                self.progress_tracker.stop_tracking(
                    tracking_id,
                    status="completed",
                    message=f"Hierarchy visualized: {len(classes)} classes",
                )
                return result

            # Build hierarchy tree
            self.progress_tracker.update_tracking(
                tracking_id, message="Building hierarchy tree..."
            )
            hierarchy = self._build_hierarchy_tree(classes)

            self.progress_tracker.update_tracking(
                tracking_id, message="Generating visualization..."
            )
            result = self._visualize_hierarchy_plotly(
                hierarchy, 
                classes, 
                output, 
                file_path, 
                node_color_by=node_color_by,
                node_size_by=node_size_by,
                hover_data=hover_data,
                **options
            )

            self.progress_tracker.stop_tracking(
                tracking_id,
                status="completed",
                message=f"Hierarchy visualized: {len(classes)} classes",
            )
            return result
        except Exception as e:
            self.progress_tracker.stop_tracking(
                tracking_id, status="failed", message=str(e)
            )
            raise

    def visualize_properties(
        self,
        ontology: Dict[str, Any],
        output: str = "interactive",
        file_path: Optional[Union[str, Path]] = None,
        **options,
    ) -> Optional[Any]:
        """
        Visualize property graph showing properties and their domains/ranges.

        Args:
            ontology: Ontology dictionary, SemanticNetwork, or ontology generator result
            output: Output type
            file_path: Output file path
            **options: Additional options

        Returns:
            Visualization figure or None
        """
        self._check_dependencies()
        self.logger.info("Visualizing ontology properties")

        # Handle different input formats
        if hasattr(ontology, "properties"):
            properties = ontology.properties if hasattr(ontology, "properties") else []
            classes = ontology.classes if hasattr(ontology, "classes") else []
        elif isinstance(ontology, dict):
            properties = ontology.get(
                "properties", ontology.get("property_definitions", [])
            )
            classes = ontology.get("classes", ontology.get("class_definitions", []))
        else:
            properties = []
            classes = []

        # If no properties, try to extract from semantic network
        if not properties and isinstance(ontology, dict):
            semantic_network = ontology.get("semantic_network", ontology.get("network"))
            if semantic_network:
                properties = self._extract_properties_from_semantic_network(
                    semantic_network
                )

        if not properties:
            raise ProcessingError("No properties found in ontology")

        return self._visualize_properties_plotly(
            properties, classes, output, file_path, **options
        )

    def visualize_structure(
        self,
        ontology: Dict[str, Any],
        output: str = "interactive",
        file_path: Optional[Union[str, Path]] = None,
        **options,
    ) -> Optional[Any]:
        """
        Visualize ontology structure as network.

        Args:
            ontology: Ontology dictionary
            output: Output type
            file_path: Output file path
            **options: Additional options

        Returns:
            Visualization figure or None
        """
        self._check_dependencies()
        self.logger.info("Visualizing ontology structure")

        classes = ontology.get("classes", [])
        properties = ontology.get("properties", [])

        # Build nodes and edges
        nodes = []
        edges = []

        # Add class nodes
        for cls in classes:
            nodes.append(
                {
                    "id": cls.get("name") or cls.get("uri", ""),
                    "label": cls.get("label") or cls.get("name", ""),
                    "type": "class",
                }
            )

            # Add hierarchy edges
            parent = cls.get("parent") or cls.get("subClassOf")
            if parent:
                edges.append(
                    {
                        "source": cls.get("name") or cls.get("uri", ""),
                        "target": parent,
                        "type": "subClassOf",
                    }
                )

        # Add property nodes
        for prop in properties:
            prop_name = prop.get("name") or prop.get("uri", "")
            nodes.append(
                {
                    "id": prop_name,
                    "label": prop.get("label") or prop.get("name", ""),
                    "type": "property",
                }
            )

            # Add domain edges
            domain = prop.get("domain")
            if domain:
                if isinstance(domain, list):
                    for d in domain:
                        edges.append({"source": prop_name, "target": d, "type": "domain"})
                else:
                    edges.append({"source": prop_name, "target": domain, "type": "domain"})

            # Add range edges
            range_val = prop.get("range")
            if range_val:
                if isinstance(range_val, list):
                    for r in range_val:
                        edges.append({"source": prop_name, "target": r, "type": "range"})
                else:
                    edges.append(
                        {"source": prop_name, "target": range_val, "type": "range"}
                    )

        return self._visualize_structure_plotly(
            nodes, edges, output, file_path, **options
        )

    def visualize_class_property_matrix(
        self,
        ontology: Dict[str, Any],
        output: str = "interactive",
        file_path: Optional[Union[str, Path]] = None,
        **options,
    ) -> Optional[Any]:
        """
        Visualize class-property matrix showing which properties belong to which classes.

        Args:
            ontology: Ontology dictionary
            output: Output type
            file_path: Output file path
            **options: Additional options

        Returns:
            Visualization figure or None
        """
        self._check_dependencies()
        self.logger.info("Visualizing class-property matrix")

        classes = ontology.get("classes", [])
        properties = ontology.get("properties", [])

        # Build matrix
        class_names = [cls.get("name") or cls.get("label", "") for cls in classes]
        property_names = [
            prop.get("name") or prop.get("label", "") for prop in properties
        ]

        matrix = []
        for cls in classes:
            row = []
            cls_props = cls.get("properties", [])
            for prop in properties:
                prop_name = prop.get("name") or prop.get("uri", "")
                # Check if property belongs to class (via domain or direct property list)
                domain = prop.get("domain")
                domains = (
                    domain if isinstance(domain, list) else [domain] if domain else []
                )
                has_prop = prop_name in cls_props or cls.get("name") in domains
                row.append(1 if has_prop else 0)
            matrix.append(row)

        fig = go.Figure(
            data=go.Heatmap(
                z=matrix,
                x=property_names,
                y=class_names,
                colorscale="Blues",
                text=matrix,
                texttemplate="%{text}",
                textfont={"size": 8},
            )
        )
        fig.update_layout(
            title="Class-Property Matrix",
            xaxis_title="Properties",
            yaxis_title="Classes",
            width=800,
            height=600,
        )

        if output == "interactive":
            return fig
        elif file_path:
            export_plotly_figure(
                fig, file_path, format=output if output != "interactive" else "html"
            )
            return None

    def visualize_metrics(
        self,
        ontology: Dict[str, Any],
        output: str = "interactive",
        file_path: Optional[Union[str, Path]] = None,
        **options,
    ) -> Optional[Any]:
        """
        Visualize ontology metrics dashboard.

        Args:
            ontology: Ontology dictionary
            output: Output type
            file_path: Output file path
            **options: Additional options

        Returns:
            Visualization figure or None
        """
        self._check_dependencies()
        self.logger.info("Visualizing ontology metrics")

        classes = ontology.get("classes", [])
        properties = ontology.get("properties", [])

        # Calculate metrics
        num_classes = len(classes)
        num_properties = len(properties)

        # Calculate hierarchy depth
        max_depth = 0
        for cls in classes:
            depth = self._calculate_class_depth(cls, classes)
            max_depth = max(max_depth, depth)

        fig = make_subplots(
            rows=1,
            cols=3,
            subplot_titles=("Class Count", "Property Count", "Max Depth"),
            specs=[
                [{"type": "indicator"}, {"type": "indicator"}, {"type": "indicator"}]
            ],
        )

        fig.add_trace(
            go.Indicator(
                mode="number",
                value=num_classes,
                title={"text": "Classes"},
                domain={"x": [0, 0.33], "y": [0, 1]},
            ),
            row=1,
            col=1,
        )

        fig.add_trace(
            go.Indicator(
                mode="number",
                value=num_properties,
                title={"text": "Properties"},
                domain={"x": [0.33, 0.66], "y": [0, 1]},
            ),
            row=1,
            col=2,
        )

        fig.add_trace(
            go.Indicator(
                mode="number",
                value=max_depth,
                title={"text": "Max Depth"},
                domain={"x": [0.66, 1], "y": [0, 1]},
            ),
            row=1,
            col=3,
        )

        fig.update_layout(title="Ontology Metrics Dashboard")

        if output == "interactive":
            return fig
        elif file_path:
            export_plotly_figure(
                fig, file_path, format=output if output != "interactive" else "html"
            )
            return None

    def _build_hierarchy_tree(
        self, classes: List[Dict[str, Any]]
    ) -> Dict[str, List[str]]:
        """Build hierarchy tree structure."""
        tree = {}
        root_classes = []

        for cls in classes:
            cls_name = cls.get("name") or cls.get("uri", "")
            parent = cls.get("parent") or cls.get("subClassOf")

            if parent:
                if parent not in tree:
                    tree[parent] = []
                tree[parent].append(cls_name)
            else:
                root_classes.append(cls_name)

            if cls_name not in tree:
                tree[cls_name] = []

        return tree

    def _calculate_class_depth(
        self, cls: Dict[str, Any], all_classes: List[Dict[str, Any]]
    ) -> int:
        """Calculate depth of class in hierarchy."""
        parent = cls.get("parent") or cls.get("subClassOf") or cls.get("superClassOf")
        if not parent:
            return 1

        # Find parent class
        for p_cls in all_classes:
            cls_name = p_cls.get("name") or p_cls.get("uri") or p_cls.get("label", "")
            if cls_name == parent:
                return 1 + self._calculate_class_depth(p_cls, all_classes)

        return 1

    def _extract_classes_from_semantic_network(
        self, semantic_network: Any
    ) -> List[Dict[str, Any]]:
        """Extract class definitions from semantic network."""
        classes = []

        # Handle SemanticNetwork dataclass
        if hasattr(semantic_network, "nodes"):
            # Group nodes by type to form classes
            type_groups = {}
            for node in semantic_network.nodes:
                node_type = node.type if hasattr(node, "type") else "Unknown"
                if node_type not in type_groups:
                    type_groups[node_type] = []
                type_groups[node_type].append(node)

            # Create class definitions
            for node_type, nodes in type_groups.items():
                classes.append(
                    {
                        "name": node_type,
                        "label": node_type,
                        "uri": f"#{node_type}",
                        "instances": len(nodes),
                        "properties": list(
                            set(
                                prop
                                for node in nodes
                                for prop in (
                                    node.properties.keys()
                                    if hasattr(node, "properties")
                                    else []
                                )
                            )
                        ),
                    }
                )

        # Handle dictionary format
        elif isinstance(semantic_network, dict):
            nodes = semantic_network.get("nodes", [])
            type_groups = {}
            for node in nodes:
                node_type = (
                    node.get("type")
                    if isinstance(node, dict)
                    else (node.type if hasattr(node, "type") else "Unknown")
                )
                if node_type not in type_groups:
                    type_groups[node_type] = []
                type_groups[node_type].append(node)

            for node_type, nodes in type_groups.items():
                classes.append(
                    {
                        "name": node_type,
                        "label": node_type,
                        "uri": f"#{node_type}",
                        "instances": len(nodes),
                    }
                )

        return classes

    def visualize_semantic_model(
        self,
        semantic_model: Any,
        output: str = "interactive",
        file_path: Optional[Union[str, Path]] = None,
        **options,
    ) -> Optional[Any]:
        """
        Visualize semantic model from ontology generator.

        This method extracts and visualizes both the ontology structure
        and the underlying semantic network that generated it.

        Args:
            semantic_model: Semantic model from OntologyGenerator or semantic network
            output: Output type
            file_path: Output file path
            **options: Additional options

        Returns:
            Visualization figure or None
        """
        self._check_dependencies()
        self.logger.info("Visualizing semantic model")

        # Handle OntologyGenerator result
        if hasattr(semantic_model, "semantic_network"):
            # Visualize the semantic network
            from .semantic_network_visualizer import SemanticNetworkVisualizer

            sem_net_viz = SemanticNetworkVisualizer(**self.config)
            return sem_net_viz.visualize_network(
                semantic_model.semantic_network,
                output=output,
                file_path=file_path,
                **options,
            )

        # Handle dictionary format with semantic_network
        elif isinstance(semantic_model, dict):
            if "semantic_network" in semantic_model:
                from .semantic_network_visualizer import SemanticNetworkVisualizer

                sem_net_viz = SemanticNetworkVisualizer(**self.config)
                return sem_net_viz.visualize_network(
                    semantic_model["semantic_network"],
                    output=output,
                    file_path=file_path,
                    **options,
                )
            # Otherwise treat as ontology
            else:
                return self.visualize_structure(
                    semantic_model, output, file_path, **options
                )

        # Handle direct semantic network
        else:
            from .semantic_network_visualizer import SemanticNetworkVisualizer

            sem_net_viz = SemanticNetworkVisualizer(**self.config)
            return sem_net_viz.visualize_network(
                semantic_model, output=output, file_path=file_path, **options
            )

    def _visualize_hierarchy_plotly(
        self,
        hierarchy: Dict[str, List[str]],
        classes: List[Dict[str, Any]],
        output: str,
        file_path: Optional[Path],
        node_color_by: str = "level",
        node_size_by: str = "instances",
        hover_data: Optional[List[str]] = None,
        **options,
    ) -> Optional[Any]:
        """Create Plotly hierarchy visualization."""
        # Build tree structure for plotly
        # This is a simplified tree visualization
        # For full tree, would need more complex layout

        # Get root classes
        all_class_names = {
            cls.get("name") or cls.get("uri", ""): cls for cls in classes
        }
        root_classes = [
            name
            for name in all_class_names.keys()
            if name not in [c for children in hierarchy.values() for c in children]
        ]

        if not root_classes:
            root_classes = list(all_class_names.keys())[:1] if all_class_names else []

        # Build node and edge lists for tree
        nodes = []
        edges = []

        def add_node_and_children(cls_name, level=0, x_offset=0):
            # Find class data
            cls_data = all_class_names.get(cls_name, {})
            
            nodes.append({
                "name": cls_name, 
                "level": level, 
                "x": x_offset, 
                "y": -level,
                "data": cls_data
            })

            children = hierarchy.get(cls_name, [])
            child_width = 1.0 / max(len(children), 1)
            for i, child in enumerate(children):
                child_x = x_offset - 0.5 + (i + 0.5) * child_width
                edges.append({"source": cls_name, "target": child})
                add_node_and_children(child, level + 1, child_x)

        # Start from root
        root_x = 0.5
        root_width = 1.0 / max(len(root_classes), 1)
        for i, root in enumerate(root_classes):
            root_x = (i + 0.5) * root_width
            add_node_and_children(root, 0, root_x)

        # Step 4: Styling - Node Colors
        # Default to coloring by level
        node_colors = []
        if node_color_by == "level":
             node_colors = [n["level"] for n in nodes]
        else:
            # Map custom property
            values = []
            for n in nodes:
                val = str(n["data"].get(node_color_by, "Unknown"))
                values.append(val)
            
            unique_vals = sorted(list(set(values)))
            colors = ColorPalette.get_colors(self.color_scheme, len(unique_vals))
            val_map = dict(zip(unique_vals, colors))
            node_colors = [val_map.get(str(n["data"].get(node_color_by, "Unknown")), "#888") for n in nodes]

        # Step 4: Styling - Node Sizes
        # Default to sizing by instances (if available) or fixed size
        node_sizes = []
        if node_size_by:
            raw_sizes = []
            for n in nodes:
                val = n["data"].get(node_size_by, 0)
                try:
                    s = float(val)
                except (ValueError, TypeError):
                    s = 0
                raw_sizes.append(s)
            
            if raw_sizes and max(raw_sizes) > min(raw_sizes):
                min_s, max_s = min(raw_sizes), max(raw_sizes)
                # Scale between 10 and 40
                node_sizes = [10 + 30 * ((s - min_s) / (max_s - min_s)) for s in raw_sizes]
            else:
                node_sizes = [self.node_size] * len(nodes)
        else:
             node_sizes = [self.node_size] * len(nodes)

        # Step 5: Interaction - Rich Hover
        node_text = []
        for n in nodes:
            cls_data = n["data"]
            text = f"<b>{n['name']}</b><br>Level: {n['level']}"
            
            # Add instances if available
            if "instances" in cls_data:
                text += f"<br>Instances: {cls_data['instances']}"
            
            # Additional hover data
            if hover_data:
                for field in hover_data:
                    val = cls_data.get(field, "N/A")
                    text += f"<br>{field}: {val}"
            
            node_text.append(text)

        # Create visualization
        edge_x = []
        edge_y = []
        node_positions = {n["name"]: (n["x"], n["y"]) for n in nodes}

        for edge in edges:
            source_pos = node_positions.get(edge["source"])
            target_pos = node_positions.get(edge["target"])
            if source_pos and target_pos:
                edge_x.extend([source_pos[0], target_pos[0], None])
                edge_y.extend([source_pos[1], target_pos[1], None])

        edge_trace = go.Scatter(
            x=edge_x,
            y=edge_y,
            line=dict(width=2, color="#888"),
            hoverinfo="none",
            mode="lines",
        )

        node_x = [n["x"] for n in nodes]
        node_y = [n["y"] for n in nodes]

        node_trace = go.Scatter(
            x=node_x,
            y=node_y,
            mode="markers+text",
            text=[n["name"] for n in nodes], # Keep label on node simple
            hovertext=node_text,             # Rich hover text
            hoverinfo="text",
            textposition="top center",
            marker=dict(
                size=node_sizes,
                color=node_colors,
                colorscale="Viridis" if node_color_by == "level" else None,
                line=dict(width=2, color="white"),
                showscale=True if node_color_by == "level" else False
            ),
        )

        fig = go.Figure(
            data=[edge_trace, node_trace],
            layout=go.Layout(
                title="Ontology Class Hierarchy",
                showlegend=False,
                hovermode="closest",
                margin=dict(b=20, l=5, r=5, t=40),
                xaxis=dict(showgrid=False, zeroline=False, showticklabels=False),
                yaxis=dict(showgrid=False, zeroline=False, showticklabels=False),
            ),
        )

        if output == "interactive":
            return fig
        elif file_path:
            export_plotly_figure(
                fig, file_path, format=output if output != "interactive" else "html"
            )
            return None

    def _visualize_hierarchy_graphviz(
        self, classes: List[Dict[str, Any]], file_path: Path, **options
    ) -> None:
        """Create Graphviz hierarchy visualization."""
        if graphviz is None:
            raise ProcessingError(
                "Graphviz not available. Install with: pip install graphviz"
            )

        dot = graphviz.Digraph(comment="Ontology Hierarchy")

        # Add nodes
        for cls in classes:
            cls_name = cls.get("name") or cls.get("label", "")
            dot.node(cls_name, cls_name)

        # Add edges
        for cls in classes:
            cls_name = cls.get("name") or cls.get("label", "")
            parent = cls.get("parent") or cls.get("subClassOf")
            if parent:
                dot.edge(parent, cls_name)

        dot.render(str(file_path), format="svg", cleanup=True)
        self.logger.info(f"Saved Graphviz hierarchy to {file_path}")

    def _visualize_properties_plotly(
        self,
        properties: List[Dict[str, Any]],
        classes: List[Dict[str, Any]],
        output: str,
        file_path: Optional[Path],
        **options,
    ) -> Optional[Any]:
        """Create Plotly property visualization."""
        # Build property graph
        nodes = []
        edges = []

        # Add class nodes
        for cls in classes:
            cls_name = cls.get("name") or cls.get("uri", "")
            nodes.append(
                {"id": cls_name, "label": cls.get("label") or cls_name, "type": "class"}
            )

        # Add property nodes and edges
        for prop in properties:
            prop_name = prop.get("name") or prop.get("uri", "")
            nodes.append(
                {
                    "id": prop_name,
                    "label": prop.get("label") or prop_name,
                    "type": "property",
                }
            )

            domain = prop.get("domain")
            if domain:
                domains = domain if isinstance(domain, list) else [domain]
                edges.extend(
                    {"source": prop_name, "target": value, "type": "domain"}
                    for value in domains
                )

            range_val = prop.get("range")
            if range_val:
                ranges = range_val if isinstance(range_val, list) else [range_val]
                edges.extend(
                    {"source": prop_name, "target": value, "type": "range"}
                    for value in ranges
                )

        # Use similar approach as KG visualizer
        from .kg_visualizer import KGVisualizer

        kg_viz = KGVisualizer(**self.config)
        return kg_viz._visualize_network_plotly(
            nodes, edges, output, file_path, **options
        )

    def _extract_properties_from_semantic_network(
        self, semantic_network: Any
    ) -> List[Dict[str, Any]]:
        """Extract property definitions from semantic network."""
        properties = []

        # Handle SemanticNetwork dataclass
        if hasattr(semantic_network, "edges"):
            # Extract unique edge labels as properties
            property_types = set()
            for edge in semantic_network.edges:
                edge_label = edge.label if hasattr(edge, "label") else ""
                if edge_label and edge_label not in property_types:
                    property_types.add(edge_label)
                    properties.append(
                        {
                            "name": edge_label,
                            "label": edge_label,
                            "uri": f"#{edge_label}",
                            "domain": "Thing",  # Default domain
                            "range": "Thing",  # Default range
                        }
                    )

        # Handle dictionary format
        elif isinstance(semantic_network, dict):
            edges = semantic_network.get(
                "edges", semantic_network.get("relationships", [])
            )
            property_types = set()
            for edge in edges:
                edge_label = (
                    edge.get("label")
                    if isinstance(edge, dict)
                    else (edge.label if hasattr(edge, "label") else "")
                )
                if edge_label and edge_label not in property_types:
                    property_types.add(edge_label)
                    properties.append(
                        {
                            "name": edge_label,
                            "label": edge_label,
                            "uri": f"#{edge_label}",
                            "domain": edge.get("domain", "Thing")
                            if isinstance(edge, dict)
                            else "Thing",
                            "range": edge.get("range", "Thing")
                            if isinstance(edge, dict)
                            else "Thing",
                        }
                    )

        return properties

    def _visualize_structure_plotly(
        self,
        nodes: List[Dict[str, Any]],
        edges: List[Dict[str, Any]],
        output: str,
        file_path: Optional[Path],
        **options,
    ) -> Optional[Any]:
        """Create Plotly structure visualization."""
        from .kg_visualizer import KGVisualizer

        kg_viz = KGVisualizer(**self.config)
        return kg_viz._visualize_network_plotly(
            nodes, edges, output, file_path, **options
        )
