---
title: "Visualization"
description: "Render knowledge graphs, ontology hierarchies, embedding projections, graph analytics, and temporal timelines as interactive HTML or static image files."
icon: "chart-network"
---

`KGVisualizer`, `AnalyticsVisualizer`, `TemporalVisualizer`, and `OntologyVisualizer` turn graph dicts, analytics results, and ontologies into interactive HTML dashboards or static images in a single method call. Use them to present centrality rankings, community clusters, event timelines, and before/after snapshot diffs to stakeholders without writing any rendering code.

<Info>
  All visualizers accept `output="interactive"` (Plotly/pyvis HTML, shown in Jupyter or saved to file) or `output="static"` (PNG/SVG via Matplotlib). Omit `file_path` to get the figure object back for further manipulation.
</Info>

## Rendering the Full Knowledge Graph

The first thing to put in front of stakeholders is the full network — nodes coloured by entity type, sized by degree centrality, with tooltips showing content on hover.

```python
from semantica.context import AgentContext, ContextGraph
from semantica.vector_store import VectorStore
from semantica.visualization import KGVisualizer

graph = ContextGraph(advanced_analytics=True)
ctx   = AgentContext(
    vector_store=VectorStore(backend="faiss", dimension=768),
    knowledge_graph=graph,
    graph_expansion=True,
)
ctx.store([
    "APT29 exploited CVE-2024-3400 targeting NATO defense contractors.",
    "CVE-2024-3400 is a critical vulnerability in PAN-OS by Palo Alto Networks.",
    "HAMMERTOSS is APT29's C2 backdoor operating over Twitter and GitHub.",
    "APT29 conducted the SUNBURST supply chain attack against SolarWinds in 2020.",
], extract_entities=True, extract_relationships=True)

viz = KGVisualizer()

# Interactive network — saved to HTML, opens in any browser
viz.visualize_network(
    graph         = graph.to_dict(),
    output        = "interactive",
    file_path     = "reports/threat_graph.html",
    node_color_by = "type",      # colour each node by its entity type
    node_size_by  = "degree",    # larger nodes = more connections
    hover_data    = ["type", "content"],
)
```

The resulting HTML is fully self-contained — no server required. Share it as a file attachment and it renders in any browser with pan, zoom, and hover.

For a static PNG suitable for a PDF report or a slide deck:

```python
viz.visualize_network(
    graph     = graph.to_dict(),
    output    = "static",
    file_path = "reports/threat_graph.png",
    node_color_by = "type",
)
```

To highlight a specific attribution path through the graph — for example, the chain from APT29 through SUNBURST to SolarWinds — pass the node IDs as `highlight_path`:

```python
viz.visualize_network(
    graph          = graph.to_dict(),
    output         = "static",
    file_path      = "reports/apt29_path.png",
    highlight_path = ["APT29", "SUNBURST", "SolarWinds"],
)
```

## Showing Community Structure

After community detection, you have a dict mapping community labels to node ID lists. `visualize_communities` on `KGVisualizer` overlays those clusters on the network; `AnalyticsVisualizer.visualize_community_structure` forwards to that same community graph view.

```python
from semantica.visualization import AnalyticsVisualizer

# The community dict you get from graph analytics
communities = {
    "node_assignments": {
        "apt29": 0,
        "hammertoss": 0,
        "nobelium": 0,
        "sunburst": 0,
        "cve-2024-3400": 1,
        "pan-os": 1,
        "globalprotect": 1,
        "solarwinds": 2,
        "orion-platform": 2,
        "cve-2020-10148": 2,
    },
    "num_communities": 3,
}

# Network view with community colouring
viz.visualize_communities(
    graph       = graph.to_dict(),
    communities = communities,
    output      = "interactive",
    file_path   = "reports/communities_network.html",
)

# Standalone breakdown chart — for a slide on "what are the 12 clusters?"
av = AnalyticsVisualizer()
av.visualize_community_structure(
    graph      = graph.to_dict(),
    communities = communities,
    output     = "interactive",
    file_path  = "reports/communities_breakdown.html",
)
```

## Plotting Centrality Rankings

The centrality dict maps node IDs to scores. Two calls cover the two use cases: a network view where node size reflects centrality, and a standalone ranked bar chart for the "top 10 most connected nodes" slide.

```python
centrality = {
    "centrality": {
        "apt29": 0.14,
        "cve-2024-3400": 0.11,
        "pan-os": 0.07,
        "hammertoss": 0.06,
        "nobelium": 0.05,
    }
}

# Network coloured and sized by centrality score
viz.visualize_centrality(
    graph          = graph.to_dict(),
    centrality     = centrality,
    centrality_type= "pagerank",
    output         = "interactive",
    file_path      = "reports/centrality_network.html",
)

# Standalone ranked bar chart — most impactful nodes at a glance
av.visualize_centrality_rankings(
    centrality      = centrality,
    centrality_type = "pagerank",
    output          = "interactive",
    file_path       = "reports/centrality_rankings.html",
)
```

## Analytics Charts: Connectivity and Degree Distribution

After running graph analytics, two additional charts complete the picture. The connectivity chart shows how many disconnected components exist and how large each one is. The degree distribution shows the power-law shape of your graph — useful for confirming that your graph is scale-free (a few highly-connected hubs, many leaf nodes).

```python
# Connectivity — pass the analysis result dict directly
# Keys the visualizer reads: "is_connected", "num_components", "component_sizes"
connectivity = {
    "is_connected":    False,
    "num_components":  3,
    "component_sizes": [42, 8, 2],
}

av.visualize_connectivity(
    connectivity = connectivity,
    output       = "interactive",
    file_path    = "reports/connectivity.html",
)

# Degree distribution — pass the graph dict directly
av.visualize_degree_distribution(
    graph     = graph.to_dict(),
    output    = "interactive",
    file_path = "reports/degree_distribution.html",
)
```

<Info>
  `visualize_connectivity` takes the connectivity analysis result dict — not `graph.to_dict()`. The dict must contain `"is_connected"`, `"num_components"`, and `"component_sizes"`. Compute it from your graph analytics output and pass the result.
</Info>

## Drawing a Timeline of Events

When the story you are telling is temporal — a CVE lifecycle, an incident timeline, a campaign progression — `TemporalVisualizer.visualize_timeline` turns a list of timestamped events into a scrollable interactive chart.

```python
from semantica.visualization import TemporalVisualizer

tv = TemporalVisualizer()

# Events are passed inside a dict under the "events" key
tv.visualize_timeline(
    temporal_data = {"events": [
        {"id": "pub",   "label": "CVE-2024-3400 published",      "timestamp": "2024-03-14T00:00:00"},
        {"id": "exp",   "label": "Zero-day exploitation begins",  "timestamp": "2024-03-26T00:00:00"},
        {"id": "patch", "label": "PAN-OS hotfix released",        "timestamp": "2024-04-14T00:00:00"},
        {"id": "rem",   "label": "Contractor remediation confirmed","timestamp": "2024-04-30T00:00:00"},
    ]},
    output    = "interactive",
    file_path = "reports/cve_timeline.html",
)
```

## Comparing Two Graph Snapshots Side-by-Side

When the question is "what changed between March 14 and April 14?", `visualize_snapshot_comparison` takes two named snapshots from `TemporalVersionManager` and renders a side-by-side diff view showing nodes and edges added or removed.

```python
from semantica.change_management import TemporalVersionManager

vm    = TemporalVersionManager(storage_path="versions.db")
snap1 = vm.get_version("pre_patch_march_14")
snap2 = vm.get_version("post_patch_april_14")

# Pass snapshots as a dict mapping label → snapshot dict
tv.visualize_snapshot_comparison(
    snapshots = {
        "pre_patch_march_14":   snap1,
        "post_patch_april_14":  snap2,
    },
    output    = "interactive",
    file_path = "reports/snapshot_diff.html",
)
```

## Tracking Graph Growth Over Time

The final chart for a stakeholder review is the growth curve — how many nodes and edges has the graph accumulated over the past year? `visualize_metrics_evolution` takes a history dict and a parallel timestamps list.

```python
# Build from TemporalVersionManager snapshots
versions = vm.list_versions()
versions.sort(key=lambda v: v["timestamp"])

timestamps      = [v["timestamp"][:10] for v in versions]
metrics_history = {
    "node_count": [len(v.get("nodes", [])) for v in versions],
    "edge_count": [len(v.get("edges", [])) for v in versions],
}

tv.visualize_metrics_evolution(
    metrics_history = metrics_history,
    timestamps      = timestamps,
    output          = "interactive",
    file_path       = "reports/graph_growth.html",
)
```

Or populate the history dict directly from known quarterly milestones:

```python
tv.visualize_metrics_evolution(
    metrics_history = {
        "node_count": [50, 142, 309, 481],
        "edge_count": [88, 387, 821, 1340],
    },
    timestamps = ["2025-01-01", "2025-04-01", "2025-07-01", "2025-10-01"],
    output     = "interactive",
    file_path  = "reports/graph_growth.html",
)
```

## Domain Examples

<Tabs>

<Tab title="Defense — CTI/Threat">

A full analyst briefing package: interactive threat network, community breakdown, CVE timeline, and graph growth curve — all generated from a live CTI graph before the morning standup.

```python
from semantica.context import AgentContext, ContextGraph
from semantica.vector_store import VectorStore
from semantica.visualization import KGVisualizer, AnalyticsVisualizer, TemporalVisualizer
import os

graph = ContextGraph(advanced_analytics=True)
ctx   = AgentContext(
    vector_store=VectorStore(backend="faiss", dimension=768),
    knowledge_graph=graph,
    graph_expansion=True,
)
ctx.store([
    "APT29 used HAMMERTOSS for C2 via Twitter and GitHub in 2020.",
    "APT29 infrastructure cluster: 185.220.101.0/24, AS200651.",
    "SolarWinds supply chain compromise attributed to APT29, campaign SUNBURST.",
    "APT29 leveraged OAuth token theft against cloud workloads in 2023.",
], extract_entities=True, extract_relationships=True)

os.makedirs("reports", exist_ok=True)

kg_viz = KGVisualizer()

# Full network — interactive for the analyst portal
kg_viz.visualize_network(
    graph         = graph.to_dict(),
    output        = "interactive",
    file_path     = "reports/cti_network.html",
    node_color_by = "type",
    node_size_by  = "degree",
    hover_data    = ["type", "content"],
)

# Attribution path PNG for the slide deck
kg_viz.visualize_network(
    graph          = graph.to_dict(),
    output         = "static",
    file_path      = "reports/apt29_sunburst_path.png",
    highlight_path = ["APT29", "SUNBURST", "SolarWinds"],
)

# Connectivity overview
av = AnalyticsVisualizer()
av.visualize_connectivity(
    connectivity = {"is_connected": True, "num_components": 1, "component_sizes": [24]},
    output       = "interactive",
    file_path    = "reports/connectivity.html",
)

# CVE-2024-3400 incident timeline
tv = TemporalVisualizer()
tv.visualize_timeline(
    temporal_data = {"events": [
        {"id": "pub",   "label": "CVE-2024-3400 published",     "timestamp": "2024-03-14"},
        {"id": "exp",   "label": "Zero-day exploitation",        "timestamp": "2024-03-26"},
        {"id": "patch", "label": "PAN-OS hotfix released",       "timestamp": "2024-04-14"},
        {"id": "rem",   "label": "Remediation confirmed",        "timestamp": "2024-04-30"},
    ]},
    output    = "interactive",
    file_path = "reports/cve_timeline.html",
)
```

</Tab>

<Tab title="Security — SOC/Incident">

During an active incident, the SOC generates a lateral movement network with the attack path highlighted, a centrality ranking to identify which hosts are most pivotal, and a relationship matrix to show who connects to what.

```python
from semantica.context import ContextGraph
from semantica.visualization import KGVisualizer, AnalyticsVisualizer

graph = ContextGraph(advanced_analytics=True)

for node_id, ntype, content in [
    ("wkstn-047",  "Host",   "Compromised workstation WKSTN-047"),
    ("dc01",       "Host",   "Domain controller DC01"),
    ("jsmith",     "User",   "Compromised user jsmith"),
    ("psexec",     "Tool",   "PsExec lateral movement tool"),
    ("t1021",      "MITRE",  "T1021.002 SMB/Admin Shares"),
]:
    graph.add_node(node_id, ntype, content)

graph.add_edge("wkstn-047", "dc01",    "lateral_movement", weight=1.0)
graph.add_edge("jsmith",    "wkstn-047","session_on",      weight=0.9)
graph.add_edge("psexec",    "wkstn-047","executed_on",     weight=1.0)
graph.add_edge("psexec",    "t1021",   "implements",       weight=0.95)

viz = KGVisualizer()

# Incident network with lateral movement path highlighted
viz.visualize_network(
    graph          = graph.to_dict(),
    output         = "interactive",
    file_path      = "soc/incident_graph.html",
    node_color_by  = "type",
    highlight_path = ["wkstn-047", "dc01"],
    hover_data     = ["type", "content"],
)

# Relationship matrix — who connects to what
viz.visualize_relationship_matrix(
    graph     = graph.to_dict(),
    output    = "interactive",
    file_path = "soc/rel_matrix.html",
)

# Centrality rankings — which host is most pivotal?
av = AnalyticsVisualizer()
av.visualize_centrality_rankings(
    centrality      = {"wkstn-047": 0.35, "dc01": 0.28, "psexec": 0.22, "jsmith": 0.15},
    centrality_type = "degree",
    output          = "interactive",
    file_path       = "soc/centrality.html",
)
```

</Tab>

<Tab title="Life Science — Clinical/Pharma">

A drug repurposing exploration: interactive drug-target-disease network, OWL class hierarchy, UMAP embedding projection, and a similarity heatmap to spot structurally equivalent compounds.

```python
from semantica.context import AgentContext, ContextGraph
from semantica.vector_store import VectorStore
from semantica.visualization import KGVisualizer, EmbeddingVisualizer, OntologyVisualizer
from semantica.ontology import OntologyGenerator

graph = ContextGraph(advanced_analytics=True)
ctx   = AgentContext(
    vector_store=VectorStore(backend="faiss", dimension=768),
    knowledge_graph=graph,
    graph_expansion=True,
)
ctx.store([
    "Metformin activates AMPK and reduces hepatic glucose production in Type 2 Diabetes.",
    "Dapagliflozin inhibits SGLT2 and reduces cardiovascular mortality in HFrEF.",
    "Semaglutide agonises GLP-1R and reduces HbA1c in obesity and Type 2 Diabetes.",
], extract_entities=True, extract_relationships=True)

kg_viz = KGVisualizer()
kg_viz.visualize_network(
    graph         = graph.to_dict(),
    output        = "interactive",
    file_path     = "drug_kg.html",
    node_color_by = "type",
    node_size_by  = "degree",
)

# OWL class hierarchy
ontology = OntologyGenerator(
    base_uri="https://purl.obolibrary.org/obo/DRUG_",
    min_occurrences=1,
).generate_from_graph(graph.to_dict())

ov = OntologyVisualizer()
ov.visualize_hierarchy(ontology, output="interactive", file_path="drug_hierarchy.html")
ov.visualize_structure(ontology, output="interactive", file_path="drug_ontology.html")

# UMAP projection and similarity heatmap for drug embeddings
embeddings = [[0.1, 0.2, 0.3], [0.15, 0.22, 0.31], [0.8, 0.7, 0.6]]
labels     = ["Metformin", "Dapagliflozin", "Semaglutide"]

ev = EmbeddingVisualizer()
ev.visualize_2d_projection(
    embeddings, labels, method="umap",
    output="interactive", file_path="drug_embeddings.html",
)
ev.visualize_similarity_heatmap(
    embeddings, labels,
    output="interactive", file_path="drug_similarity.html",
)
```

</Tab>

<Tab title="Banking — Risk/Compliance">

Regulatory knowledge graph for model governance: entity network, OWL class hierarchy for documentation, and a graph growth curve across quarterly Basel III updates — all in static PNG for the model governance committee pack.

```python
from semantica.context import ContextGraph
from semantica.change_management import TemporalVersionManager
from semantica.visualization import KGVisualizer, TemporalVisualizer, OntologyVisualizer
from semantica.ontology import OntologyGenerator

graph = ContextGraph(advanced_analytics=True)
vm    = TemporalVersionManager(storage_path="regulatory_versions.db")

for node, ntype, content in [
    ("bcbs-cre20",  "Regulation", "Basel III CRE20 — CRE capital requirements"),
    ("metric-ltv",  "Metric",     "Loan-to-Value Ratio"),
    ("metric-dscr", "Metric",     "Debt Service Coverage Ratio"),
    ("metric-pd",   "Metric",     "Probability of Default"),
    ("metric-lgd",  "Metric",     "Loss Given Default"),
]:
    graph.add_node(node, ntype, content)

graph.add_edge("bcbs-cre20", "metric-ltv",  "requires", weight=1.0)
graph.add_edge("bcbs-cre20", "metric-dscr", "requires", weight=1.0)
graph.add_edge("bcbs-cre20", "metric-pd",   "requires", weight=0.9)
graph.add_edge("bcbs-cre20", "metric-lgd",  "requires", weight=0.9)

kg_viz = KGVisualizer()
kg_viz.visualize_network(
    graph         = graph.to_dict(),
    output        = "static",
    file_path     = "regulatory/regulatory_kg.png",
    node_color_by = "type",
    node_size_by  = "degree",
)

# OWL hierarchy — static PNG for the documentation appendix
ontology = OntologyGenerator(
    base_uri="https://basel.eba.eu/ontology/",
    min_occurrences=1,
).generate_from_graph(graph.to_dict())

ov = OntologyVisualizer()
ov.visualize_hierarchy(ontology, output="static", file_path="regulatory/class_hierarchy.png")

# Graph growth curve across quarterly snapshots
tv = TemporalVisualizer()
tv.visualize_metrics_evolution(
    metrics_history = {
        "node_count": [12, 18, 25, 31],
        "edge_count": [8,  15, 24, 32],
    },
    timestamps = ["2025-01-01", "2025-04-01", "2025-07-01", "2025-10-01"],
    output     = "interactive",
    file_path  = "regulatory/graph_growth.html",
)

# Snapshot comparison — what changed between Q2 and Q3 Basel update?
snap1 = vm.get_version("basel_q2_2025")
snap2 = vm.get_version("basel_q3_2025")
if snap1 and snap2:
    tv.visualize_snapshot_comparison(
        snapshots = {"basel_q2_2025": snap1, "basel_q3_2025": snap2},
        output    = "interactive",
        file_path = "regulatory/snapshot_diff.html",
    )
```

</Tab>

</Tabs>

## Output Modes

Every visualizer method accepts the same two output modes:

| `output` value | Format | Best for |
| :------------- | :----- | :------- |
| `"interactive"` | Self-contained HTML (Plotly / pyvis) | Jupyter notebooks, analyst portals, email attachments |
| `"static"` | PNG / SVG (Matplotlib) | PDF reports, slide decks, regulatory submissions |

To get the figure object instead of writing to disk, omit `file_path`:

```python
fig = viz.visualize_network(graph.to_dict(), output="interactive")
fig.show()              # renders inline in Jupyter
fig.write_html("out.html")   # manual export
```

## Related Guides

- [Context Graphs](context-graphs) — `graph.to_dict()` is the primary input for `KGVisualizer`
- [Ontology Management](ontology) — `OntologyVisualizer` renders ontologies produced by `OntologyGenerator`
- [Change Management](change-management) — `TemporalVersionManager` snapshots feed `visualize_metrics_evolution()` and `visualize_snapshot_comparison()`
- [Graph Analytics](graph-analytics) — centrality scores, community dicts, and connectivity results that feed the `AnalyticsVisualizer`
- [Export & Serialization](export) — export the same graph to GraphML, GEXF, or DOT for Gephi and Graphviz
