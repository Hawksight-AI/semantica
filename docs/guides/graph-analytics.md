---
title: "Graph Analytics"
description: "How to find the most important nodes in your knowledge graph, discover hidden communities, measure structural similarity, and predict missing connections — with real-world examples."
icon: "chart-network"
---

`ContextGraph` analytics — centrality, community detection, Node2Vec embeddings, link prediction, and structural similarity — answer what your graph *means*, not just what it contains. Enable them once with `advanced_analytics=True` and use them to rank the most structurally important nodes, surface hidden operational clusters, and flag implied connections before they are formally observed.

<Info>
  All analytics require `advanced_analytics=True` at construction time. Without it, every method in this guide raises `RuntimeError: advanced_analytics not enabled`. The flag lazy-initializes five sub-components: `CentralityCalculator`, `CommunityDetector`, `NodeEmbedder`, `LinkPredictor`, and `SimilarityCalculator`.
</Info>

## Setting Up the Analytical Graph

```python
from semantica.context import ContextGraph

graph = ContextGraph(
    advanced_analytics  = True,
    community_detection = True,
    node_embeddings     = True,
)
```

If you're loading an existing graph from storage, pass the same flags — the sub-components initialize from the loaded graph state, not from a fresh empty graph.

## The One-Call Snapshot

Before diving into individual analyses, get the lay of the land first. `analyze_graph_with_kg()` runs every analytics pass in sequence and returns a single unified report:

```python
report = graph.analyze_graph_with_kg()

print(f"Nodes:       {report['graph_metrics']['node_count']}")
print(f"Edges:       {report['graph_metrics']['edge_count']}")
print(f"Density:     {report['graph_metrics']['density']:.4f}")
print(f"Communities: {len(report['community_analysis'])}")
```

For a graph with 2,400 nodes and 8,700 edges, a density of 0.003 is completely normal — knowledge graphs are sparse by nature; most nodes connect to a small neighborhood, not to everything. If you see density above 0.1, you likely have over-connected hub nodes pulling everything together, which can distort centrality scores.

Run this at the end of each ingestion batch. The result gives you a baseline to compare against the next run — if community count drops from 12 to 4 between ingestion cycles, something in the new data is bridging clusters that were previously separate. That's a signal worth investigating before the next analyst briefing.

The full report structure:

```text
report
├── "graph_metrics"         → node_count, edge_count, density
├── "centrality_analysis"   → all five measures + per-node rankings
├── "community_analysis"    → detected communities + modularity score
├── "connectivity_analysis" → connected components, diameter, avg path length
├── "node_embeddings"       → node_id → List[float] (Node2Vec vectors)
└── "timestamp"             → ISO datetime of this analysis run
```

## Finding the Kingpins — Centrality Analysis

Not all nodes are equal. Centrality analysis gives each node five different scores, each measuring a different kind of importance.

The key intuition: a node can have low *degree* (few direct connections) but extreme *betweenness* (everything passes through it). That's a **broker** — the node that, if removed, would fragment the graph into disconnected pieces. In threat intelligence, brokers are often infrastructure nodes: bulletproof hosting providers, shared C2 frameworks, or intermediary loaders that every campaign routes through.

### Scoring a Single Node

When you suspect a particular entity is significant, start with a direct score:

```python
scores = graph.get_node_centrality("APT29")

# degree      → 0.0420  (4.2% of nodes are direct neighbors)
# betweenness → 0.1837  (APT29 sits on 18% of all shortest paths)
# closeness   → 0.6123  (average 1.6 hops to any other node)
# eigenvector → 0.8941  (most of APT29's neighbors are themselves well-connected)
# pagerank    → 0.0089  (0.89% of random-walk probability mass lands here)

for measure, score in scores.items():
    print(f"{measure:12s}: {score:.4f}")
```

The betweenness score of 0.18 here is striking — it means APT29 acts as a broker for nearly a fifth of all information flows in the graph. If an analyst wants to understand "what connects our observed TTPs to known infrastructure," they have to pass through APT29. That's not just fame; that's structural power.

### Bulk Rankings Across the Full Graph

To rank every node across all five measures at once:

```python
from semantica.kg import CentralityCalculator

calc       = CentralityCalculator()
graph_dict = graph.to_dict()

all_measures = calc.calculate_all_centrality(graph_dict)

# Pull top 5 by betweenness — these are your brokers
betweenness_rankings = all_measures["centrality_measures"]["betweenness"]["rankings"]
print("Top brokers (betweenness):")
for entry in betweenness_rankings[:5]:
    print(f"  [{entry['score']:.4f}]  {entry['node']}")
```

If you only care about two measures, pass the subset to avoid computing all five:

```python
focused = calc.calculate_all_centrality(
    graph_dict,
    centrality_types = ["degree", "pagerank"],
)
```

### Which Measure to Trust?

| If you want to know... | Use |
| :--- | :--- |
| Who has the most direct connections? | `degree` |
| Who would most disrupt the network if removed? | `betweenness` |
| Who can reach the rest of the network fastest? | `closeness` |
| Who is influential because their neighbors are influential? | `eigenvector` |
| Who matters in a random traversal of the graph? | `pagerank` |

For attribution analysis, **eigenvector** centrality often surfaces the most meaningful nodes — high eigenvector means you're connected to other high-eigenvector nodes, which in threat intelligence tracks with "known-to-be-important" entities clustering together.

## Mapping Threat Actor Clusters — Community Detection

Centrality tells you about individual nodes. Community detection tells you about *groups* — which nodes form tightly-knit clusters with more internal connections than external ones.

Imagine your graph has twenty distinct threat actor nodes. Centrality can rank them individually, but it can't tell you that twelve of them actually share infrastructure, tooling patterns, and target sectors in a way that makes them a single operational cluster, while the remaining eight split into two separate groups. Community detection finds that automatically.

```python
from semantica.kg import CommunityDetector

detector   = CommunityDetector()
result     = detector.detect_communities(graph.to_dict(), algorithm="louvain")

communities = result["communities"]       # List[List[str]] — node groups
assignments = result["node_assignments"]  # node_id → community index
modularity  = result["modularity"]        # 0.0–1.0 — partition quality

print(f"Found {len(communities)} communities  (modularity: {modularity:.3f})")

for i, members in enumerate(communities):
    print(f"\n  Community {i} — {len(members)} members")
    print(f"  Sample: {', '.join(members[:4])}")
```

**Modularity above 0.4** is generally considered meaningful — the communities found are not random. If your graph returns 0.71, that's a strong signal that the clustering is real: your threat actors genuinely form operational clusters, not just random associations.

When you see a community that mixes what you thought were unrelated threat actors, that's a hypothesis worth investigating. Maybe `COZY BEAR`, `VENOMOUS BEAR`, and `FANCY BEAR` all appear in the same community because they share C2 infrastructure — despite being traditionally attributed to different GRU units.

Visualize immediately with:

```python
from semantica.visualization import KGVisualizer

viz = KGVisualizer()
viz.visualize_communities(
    graph       = graph,
    communities = communities,
    output      = "interactive",
    file_path   = "threat_clusters.html",
)
```

## Teaching the Graph to Measure Distance — Node2Vec Embeddings

Centrality and community detection are topological — they work with edges as binary connections. Node2Vec embeddings go deeper: they generate a dense vector for each node by simulating thousands of random walks through the graph, learning which nodes tend to appear in similar neighborhoods.

The practical result: nodes that play similar *structural roles* end up near each other in embedding space — even if they have no direct edge between them. Two C2 domains that both sit between threat actors and victim infrastructure will have similar embeddings, even if they're in completely different parts of the graph.

```python
from semantica.kg import NodeEmbedder
import numpy as np

embedder   = NodeEmbedder()     # requires: pip install semantica[embeddings]
embeddings = embedder.compute_embeddings(
    graph_store        = graph,   # ContextGraph instance — not a dict
    node_labels        = None,    # None = embed all node types
    relationship_types = None,    # None = traverse all edge types
)
# Returns: Dict[str, List[float]] — node_id → embedding vector

for node_id, vec in list(embeddings.items())[:3]:
    print(f"{node_id}: dim={len(vec)}, norm={np.linalg.norm(vec):.4f}")
```

These vectors become first-class citizens in Semantica — they're stored on `Decision` nodes as `node2vec_embedding` and used automatically by `find_precedents_by_scenario()` as the structural similarity component.

## What Does This Attack Pattern Remind Me Of?

Once you have embeddings, you can ask: "which nodes in my graph are structurally most similar to APT29?" This isn't about shared edges — it's about shared *role*. Which other nodes play the same position in the graph that APT29 plays?

```python
from semantica.kg import SimilarityCalculator

calc = SimilarityCalculator()

top5 = calc.find_most_similar(
    embeddings      = embeddings,
    query_embedding = embeddings["APT29"],
    top_k           = 5,
)

print("Nodes most similar to APT29 (by structural role):")
for node_id, score in top5:
    print(f"  [{score:.4f}]  {node_id}")
```

If `LAZARUS` and `APT38` both appear at the top with similarity > 0.85, that's worth noting in your analyst report: these groups are playing structurally identical roles in the graph, which may warrant a unified tracking hypothesis even if traditional attribution keeps them separate.

To compare two nodes directly:

```python
score = calc.cosine_similarity(embeddings["APT29"], embeddings["LAZARUS"])
print(f"Structural similarity APT29 ↔ LAZARUS: {score:.4f}")
```

For a quicker path that doesn't require pre-computing all embeddings:

```python
similar = graph.find_similar_nodes(
    "APT29",
    similarity_type = "structural",
    top_k           = 5,
)
for r in similar:
    print(f"  [{r['score']:.4f}]  {r['type']:20s}  {r['id']}")
```

## Anticipating the Next Move — Link Prediction

Link prediction answers a different question: not "which nodes are similar" but "which edges are *missing*?" The graph may lack a direct connection between two nodes not because the connection doesn't exist, but because you haven't observed it yet.

In practice: you have `APT29 → uses → SUNBURST` and `SUNBURST → targets → Windows Server 2019`. Link prediction might surface `APT29 → targets → Windows Server 2019` with a high score — the connection is implied by transitivity but hasn't been explicitly drawn.

```python
from semantica.kg import LinkPredictor

predictor   = LinkPredictor()
predictions = predictor.predict_links(graph.to_dict(), top_k=10)

print("Predicted missing links:")
for node1, node2, score in predictions:
    print(f"  [{score:.4f}]  {node1}  →  {node2}")
```

A score above 0.8 is worth analyst review — these aren't random; they're edges the topology of the existing graph strongly implies. Scores below 0.5 are noise. The sweet spot for human review is 0.6–0.8: plausible but not yet confirmed.

<Info>
  Link prediction is also available on `Decision` nodes through `DecisionQuery.predict_decision_relationships(decision_id, top_k)`. See the [Decision Intelligence guide](decision-intelligence) for how to surface causal relationships between past decisions.
</Info>

## Understanding Your Decision History

When decisions are stored as nodes in the graph, `get_decision_insights()` gives you an analytical view across all of them:

```python
insights = graph.get_decision_insights()

print(f"Total decisions: {insights['total_decisions']}")
print(f"Mean confidence: {insights['confidence_stats']['mean']:.2f}")

print("\nBy category:")
for category, count in sorted(insights["categories"].items(), key=lambda x: -x[1]):
    print(f"  {category:<30} {count}")

print("\nBy outcome:")
for outcome, count in sorted(insights["outcomes"].items(), key=lambda x: -x[1]):
    print(f"  {outcome:<20} {count}")
```

The confidence stats are the tell: if mean confidence is 0.91 but minimum is 0.34, someone is making low-confidence decisions that still got recorded as final. That gap is worth flagging in a governance review.

The `"advanced_analytics"` key inside `insights` contains the full `analyze_graph_with_kg()` result — so calling `get_decision_insights()` gives you the complete analytical picture without an extra call.

## Domain Examples

<Tabs>

<Tab title="Defense — CTI Threat Network">

Your SOC just merged three threat intel feeds into a single CTI graph. Before this week's analyst briefing, you need to rank the most dangerous actors, identify hidden operational clusters, and flag implied connections that haven't been formally tracked.

```python
from semantica.context import ContextGraph
from semantica.kg import CentralityCalculator, CommunityDetector, LinkPredictor
from semantica.visualization import AnalyticsVisualizer

graph = ContextGraph(
    advanced_analytics  = True,
    community_detection = True,
    node_embeddings     = True,
)
# (Populated from MISP/OTX/OSINT ingest)

# Full snapshot
report = graph.analyze_graph_with_kg()
print(f"Graph: {report['graph_metrics']['node_count']} nodes, "
      f"{report['graph_metrics']['edge_count']} edges")

# Rank brokers — who, if taken down, fragments the network?
calc     = CentralityCalculator()
measures = calc.calculate_all_centrality(graph.to_dict())
brokers  = measures["centrality_measures"]["betweenness"]["rankings"][:5]

print("\nTop 5 broker nodes (betweenness):")
for entry in brokers:
    print(f"  [{entry['score']:.4f}]  {entry['node']}")

# Find operational clusters
detector = CommunityDetector()
result   = detector.detect_communities(graph.to_dict(), algorithm="louvain")
print(f"\n{len(result['communities'])} clusters  "
      f"(modularity {result['modularity']:.3f})")

# Flag implied connections
predictor   = LinkPredictor()
predictions = predictor.predict_links(graph.to_dict(), top_k=5)
print("\nHigh-confidence implied connections:")
for n1, n2, score in predictions:
    if score > 0.7:
        print(f"  [{score:.3f}]  {n1}  →  {n2}")
```

</Tab>

<Tab title="Security — Active Incident">

During an active incident, your graph has grown to include alert nodes, affected hosts, lateral movement edges, and identified malware. You need to understand the blast radius: which hosts are structural brokers in the lateral movement chain, and which connections haven't been formally documented yet?

```python
from semantica.context import ContextGraph
from semantica.kg import CentralityCalculator, LinkPredictor

graph = ContextGraph(advanced_analytics=True)
# (Populated from SIEM alert correlation and EDR telemetry)

calc     = CentralityCalculator()
measures = calc.calculate_all_centrality(graph.to_dict())

# Betweenness finds the pivot hosts — the ones lateral movement flows through
pivot_hosts = measures["centrality_measures"]["betweenness"]["rankings"][:5]
print("Pivot hosts (lateral movement brokers):")
for entry in pivot_hosts:
    print(f"  [{entry['score']:.4f}]  {entry['node']}")

# Identify the attacker's likely next targets
predictor   = LinkPredictor()
predictions = predictor.predict_links(graph.to_dict(), top_k=10)

print("\nLikely next lateral moves (predicted):")
for src, dst, score in predictions:
    if score > 0.65:
        print(f"  [{score:.3f}]  {src}  →  {dst}")

# Score a specific high-value target
dc_scores = graph.get_node_centrality("DC-PROD-01")
print(f"\nDomain Controller centrality:")
print(f"  Betweenness: {dc_scores['betweenness']:.4f}")
print(f"  PageRank:    {dc_scores['pagerank']:.4f}")
# High betweenness + high pagerank on a DC = confirmed pivot point
```

</Tab>

<Tab title="Life Science — Clinical Trial Graph">

Your clinical trial platform maintains a graph of drugs, biomarkers, patient populations, adverse event types, and regulatory decisions. At the end of each trial phase, you need to understand whether the drug cluster for metabolic syndrome is truly isolated from the cardiovascular cluster — that separation matters for co-administration risk assessment.

```python
from semantica.context import ContextGraph
from semantica.kg import CommunityDetector, NodeEmbedder, SimilarityCalculator

graph = ContextGraph(
    advanced_analytics  = True,
    community_detection = True,
    node_embeddings     = True,
)
# (Populated from trial records, PubMed, and FDA adverse event database)

# Find drug-disease clusters
detector = CommunityDetector()
result   = detector.detect_communities(graph.to_dict(), algorithm="louvain")
print(f"Clinical clusters: {len(result['communities'])}  "
      f"(modularity {result['modularity']:.3f})")

# Inspect the cluster containing dapagliflozin
drug_cluster_idx = result["node_assignments"].get("dapagliflozin")
if drug_cluster_idx is not None:
    cluster_members = result["communities"][drug_cluster_idx]
    print(f"\nCluster containing dapagliflozin ({len(cluster_members)} members):")
    for m in cluster_members[:8]:
        print(f"  {m}")

# Find drugs that play the same structural role as dapagliflozin
embedder   = NodeEmbedder()
embeddings = embedder.compute_embeddings(graph_store=graph)
calc       = SimilarityCalculator()

similar_drugs = calc.find_most_similar(
    embeddings      = embeddings,
    query_embedding = embeddings["dapagliflozin"],
    top_k           = 5,
)
print("\nStructurally similar to dapagliflozin:")
for drug, score in similar_drugs:
    print(f"  [{score:.4f}]  {drug}")
```

</Tab>

<Tab title="Banking — Counterparty Risk">

Your risk management team models counterparty relationships as a graph: banks, SPVs, exposure instruments, and regulatory entities connected by exposure, guarantees, and ownership edges. Before the quarterly stress test, you need to identify which entities are systemic — whose failure would cascade most broadly.

```python
from semantica.context import ContextGraph
from semantica.kg import CentralityCalculator, CommunityDetector

graph = ContextGraph(advanced_analytics=True, community_detection=True)
# (Populated from regulatory filings, trade repositories, and internal exposure data)

calc     = CentralityCalculator()
measures = calc.calculate_all_centrality(graph.to_dict())

# Eigenvector finds "too connected to fail" — entities connected to other
# high-centrality entities
systemic = measures["centrality_measures"]["eigenvector"]["rankings"][:5]
print("Systemically connected entities:")
for entry in systemic:
    print(f"  [{entry['score']:.4f}]  {entry['node']}")

# Betweenness finds contagion brokers — entities that, if they defaulted,
# would disconnect otherwise-separate parts of the exposure graph
brokers = measures["centrality_measures"]["betweenness"]["rankings"][:5]
print("\nContagion brokers:")
for entry in brokers:
    print(f"  [{entry['score']:.4f}]  {entry['node']}")

# Find exposure clusters — groups with dense mutual exposure
detector = CommunityDetector()
result   = detector.detect_communities(graph.to_dict(), algorithm="louvain")
print(f"\n{len(result['communities'])} exposure clusters  "
      f"(modularity {result['modularity']:.3f})")
```

</Tab>

</Tabs>

## What the Numbers Mean

| Score | What it tells you |
| :--- | :--- |
| Betweenness > 0.15 | Critical broker — investigate this node first in any attribution or root-cause analysis |
| Modularity > 0.4 | Communities are real, not statistical noise — trust the clustering |
| Modularity < 0.2 | Graph is too dense for meaningful community structure at this level |
| Embedding cosine similarity > 0.85 | Two nodes are structurally near-identical — strong hypothesis for unified tracking |
| Link prediction score > 0.7 | This edge almost certainly exists — queue for analyst confirmation |
| Link prediction score 0.5–0.7 | Plausible but uncertain — treat as a hypothesis, not a fact |

## Related Guides

- [Context Graphs](context-graphs) — building and querying the underlying `ContextGraph`
- [Visualization](visualization) — render centrality rankings and community clusters as interactive dashboards
- [Decision Intelligence](decision-intelligence) — link prediction and structural similarity applied to decision nodes
- [GraphRAG](graphrag) — using analytics results to ground LLM generation in the most contextually relevant subgraph
