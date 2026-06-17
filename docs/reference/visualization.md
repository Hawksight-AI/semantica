---
title: "Visualization Module"
description: "Interactive and static knowledge graph, ontology, embedding, and temporal visualization."
icon: "chart-bar"
---

**`semantica.visualization`** renders knowledge graphs, ontologies, embedding spaces, and temporal data as **interactive HTML or static images**: without launching the full Explorer server:

- `KGVisualizer`: interactive network with force, hierarchical, and circular layouts
- `EmbeddingVisualizer`: 2D/3D UMAP or t-SNE projections with cluster labels
- `TemporalVisualizer`: timeline views and graph evolution across snapshots
- `AnalyticsVisualizer`: centrality scores, community structure, degree distribution charts

Requires `plotly`: `pip install plotly`. Some exporters also need `matplotlib` or `graphviz`.


## Exported Classes

| Class | Role |
| :--- | :--- |
| `KGVisualizer` | Interactive network, community, and subgraph rendering with force/hierarchical/circular layouts |
| `OntologyVisualizer` | Class hierarchy and property relationship diagrams from any ontology |
| `EmbeddingVisualizer` | 2D/3D UMAP or t-SNE projection of embedding spaces with cluster labels |
| `SemanticNetworkVisualizer` | Weighted semantic network rendering |
| `AnalyticsVisualizer` | Centrality scores, community structure, connectivity, and degree distribution charts |
| `TemporalVisualizer` | Timeline views and graph evolution across snapshots |

## Quick Start

<Steps>
  <Step title="Render a knowledge graph">
    ```python
    from semantica.visualization import KGVisualizer

    viz = KGVisualizer(layout="force", color_scheme="default")

    # Interactive: opens in browser, supports hover and click
    viz.visualize_network(graph, output="interactive")
    ```
  </Step>
  <Step title="Apply layout and color options">
    ```python
    viz = KGVisualizer(layout="force", color_scheme="vibrant")

    viz.visualize_network(
        graph,
        output="html",
        file_path="graph.html",
        node_color_by="type",      # color nodes by entity type attribute
    )
    ```
  </Step>
  <Step title="Export to static formats">
    ```python
    # Static PNG: for reports and embedding in documents
    viz.visualize_network(graph, output="png", file_path="graph.png")

    # Vector SVG: for publications and scalable diagrams
    viz.visualize_network(graph, output="svg", file_path="graph.svg")
    ```
  </Step>
</Steps>

<Warning>
  **`plotly` is required for all visualizers.** Install before use: `pip install plotly`. All visualizer methods raise `ProcessingError` if Plotly is not installed.
</Warning>

## Visualizers

<Tabs>
  <Tab title="KGVisualizer">
    Interactive and static knowledge graph rendering:

    ```python
    from semantica.visualization import KGVisualizer

    viz = KGVisualizer(layout="force", color_scheme="default")

    # Interactive: opens in browser
    viz.visualize_network(graph, output="interactive")

    # Save as HTML file
    viz.visualize_network(graph, output="html", file_path="graph.html")

    # Static PNG
    viz.visualize_network(graph, output="png", file_path="graph.png")

    # Community-colored graph
    viz.visualize_communities(graph, communities, file_path="communities.html")

    # Centrality-sized nodes
    viz.visualize_centrality(graph, centrality, centrality_type="degree")

    # Entity type distribution bar chart
    viz.visualize_entity_types(graph, output="interactive")

    # Relationship frequency heatmap
    viz.visualize_relationship_matrix(graph, output="interactive")
    ```

    <Warning>
      **Use `max_nodes` for large graphs.** Force-directed layouts become unreadable and slow above ~1,000 nodes. Filter to a subgraph before visualizing large graphs.
    </Warning>

    <Tip>
      **HTML output is always the best starting point.** Interactive HTML lets you zoom, pan, and hover for details. Only export to PNG/SVG/PDF when embedding in a report.
    </Tip>

    <Tip>
      **For interactive dashboards, prefer Explorer.** `KGVisualizer.visualize_network()` generates a self-contained HTML file. The Explorer CLI (`semantica-explorer`) gives a full live web app with search, filtering, path-finding, and REST API.
    </Tip>

    **Layout options (`layout=`):**

    | Layout | Description | Best For |
    | :------ | :----------- | :-------- |
    | `force` | Physics simulation: clusters emerge naturally | General graphs |
    | `hierarchical` | Top-down tree layout | Taxonomies, org charts |
    | `circular` | Nodes on a circle, edges as chords | Small dense graphs |
  </Tab>
  <Tab title="OntologyVisualizer">
    Visualize class hierarchies and property relationships:

    ```python
    from semantica.visualization import OntologyVisualizer

    viz = OntologyVisualizer()

    # Class hierarchy tree
    viz.visualize_hierarchy(ontology, output="interactive")

    # Property domain/range graph
    viz.visualize_properties(ontology, output="html", file_path="properties.html")

    # Full structure network (classes + properties)
    viz.visualize_structure(ontology, output="interactive")

    # Class-property matrix heatmap
    viz.visualize_class_property_matrix(ontology, output="html", file_path="matrix.html")

    # Ontology metrics dashboard
    viz.visualize_metrics(ontology, output="interactive")
    ```
  </Tab>
  <Tab title="EmbeddingVisualizer">
    Project high-dimensional embeddings into 2D for cluster analysis:

    ```python
    from semantica.visualization import EmbeddingVisualizer

    viz = EmbeddingVisualizer()

    viz.visualize_2d_projection(
        embeddings=embeddings,
        labels=labels,
        output="interactive",
        file_path="embeddings.html",
        method="umap",    # "umap" | "tsne" | "pca"
    )
    ```

    | Method | Speed | Preserves | Best For |
    | :------ | :----- | :--------- | :-------- |
    | `umap` | Fast | Global + local structure | Large datasets, cluster discovery |
    | `tsne` | Medium | Local structure | Tight cluster separation |
    | `pca` | Very fast | Variance | Quick overview, linear structure |

    <Tip>
      **UMAP is faster than t-SNE at scale.** For embedding spaces with >5,000 points, UMAP completes in seconds; t-SNE may take minutes. Both produce good cluster separation.
    </Tip>
  </Tab>
  <Tab title="TemporalVisualizer">
    Visualize how a knowledge graph changes over time:

    ```python
    from semantica.visualization import TemporalVisualizer

    viz = TemporalVisualizer()

    # Timeline of entity/relationship changes
    viz.visualize_timeline(temporal_data, output="interactive")

    # Animated network evolution: one frame per time step
    viz.visualize_network_evolution(temporal_kg, output="html", file_path="evolution.html")

    # Side-by-side snapshot comparison
    # snapshots: dict mapping timestamp strings to graph dicts
    snapshots = {
        "2023-01": graph_v1,
        "2024-01": graph_v2,
    }
    viz.visualize_snapshot_comparison(snapshots, output="html", file_path="diff.html")

    # Temporal patterns: pass a list of pattern dicts
    viz.visualize_temporal_patterns(patterns, output="html", file_path="patterns.html")

    # Metrics evolution over time
    viz.visualize_metrics_evolution(metrics_history, timestamps, output="interactive")
    ```
  </Tab>
  <Tab title="AnalyticsVisualizer">
    Visualize graph analytics results: centrality, communities, and degree distribution:

    ```python
    from semantica.visualization import AnalyticsVisualizer

    viz = AnalyticsVisualizer()

    # Bar chart of top-N nodes by centrality measure
    # param is centrality_type= (not metric=) and top_n= (not top_k=)
    viz.visualize_centrality_rankings(
        centrality,
        centrality_type="pagerank",
        top_n=20,
        output="html",
        file_path="centrality.html",
    )

    # Community-colored network graph
    viz.visualize_community_structure(kg, communities, output="html", file_path="communities.html")

    # Degree distribution histogram
    viz.visualize_degree_distribution(kg, output="html", file_path="degree_dist.html")

    # Connectivity analysis (connected/disconnected, component sizes)
    viz.visualize_connectivity(connectivity, output="interactive")

    # Full metrics dashboard (nodes, edges, density, diameter)
    viz.visualize_metrics_dashboard(metrics, output="interactive")

    # Compare multiple centrality measures side-by-side
    viz.visualize_centrality_comparison(centrality_results, top_n=10)
    ```
  </Tab>
</Tabs>

## Color Schemes

All visualizers accept a `color_scheme=` constructor parameter:

```python
viz = KGVisualizer(color_scheme="vibrant")
```

| Scheme | Description | Best For |
| :------ | :----------- | :-------- |
| `default` | Blue-grey palette | General use |
| `vibrant` | High-contrast, saturated colours | Presentations |
| `pastel` | Soft, muted tones | Light backgrounds |
| `dark` | Dark background with bright nodes | Dark-mode dashboards |
| `light` | White background, thin edges | Publications, print |
| `colorblind` | Okabe-Ito safe palette | Accessibility |

<Tip>
  **Use `color_scheme="colorblind"` in publications and dashboards.** The Okabe-Ito palette is readable for everyone, including the ~8% of readers who are red-green colorblind.
</Tip>

## Export Formats

| Format | Interactive | Scalable | Best For |
| :------ | :----------- | :-------- | :-------- |
| `.html` | Yes | N/A | Web dashboards, exploratory analysis |
| `.png` | No | No | Reports, Jupyter notebooks |
| `.svg` | No | Yes | Publications, slide decks |
| `.pdf` | No | Yes | Print, compliance exports |

## Convenience Functions

```python
from semantica.visualization import (
    visualize_kg, visualize_ontology, visualize_embeddings,
    visualize_semantic_network, visualize_analytics, visualize_temporal,
)

# Returns Plotly figure or None
fig = visualize_kg(graph, output="interactive", method="default")
fig = visualize_ontology(ontology, output="interactive", method="hierarchy")
fig = visualize_embeddings(embeddings, labels, output="interactive", method="2d_projection")
fig = visualize_analytics(analytics_data, output="interactive", method="centrality")
fig = visualize_temporal(temporal_data, output="interactive", method="timeline")
```

## Graph Explorer (Full Dashboard)

For a full browser-based UI with search, path finding, and the Ontology Hub, launch the Explorer CLI:

```bash
semantica-explorer --graph my_graph.json
```

See the [Explorer reference](explorer) for the full feature set and REST API.

<CardGroup cols={2}>
  <Card title="Knowledge Graph" icon="diagram-project" href="kg">
    The graph being visualized.
  </Card>
  <Card title="Ontology" icon="sitemap" href="ontology">
    Visualize ontology class structure.
  </Card>
  <Card title="Embeddings" icon="vector-square" href="embeddings">
    Generate the embeddings visualized here.
  </Card>
  <Card title="Explorer" icon="globe" href="explorer">
    Full interactive Knowledge Explorer UI.
  </Card>
</CardGroup>
