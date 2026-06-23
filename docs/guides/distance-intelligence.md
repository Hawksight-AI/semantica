---
title: "Distance Intelligence"
description: "Classify graph proximity into distance bands, compute confidence decay along paths, run multi-algorithm path finding, and blend semantic similarity with structural proximity in retrieval."
icon: "route"
---

`ContextGraph` distance intelligence answers the structural question that pure semantic similarity cannot: given two nodes, what is their precise relationship in terms of graph topology, path weight, and inferential confidence? Use it to annotate attribution chains with hop counts and confidence decay, rank retrieval results by structural proximity to an anchor node, and surface implied connections for analyst review.

## What Is Distance Intelligence?

Distance intelligence quantifies and analyzes the structural relationships between nodes in your knowledge graph. It provides detailed metadata about graph paths including hop counts, distance bands, confidence decay, and path analysis.

**Distance metadata** includes hop counts (number of edges between nodes), distance bands (semantic categories like "direct", "near", "distant"), confidence decay (accumulated trust along paths), and path analysis (finding optimal routes between nodes).

**Hop counts** measure the number of edges you must traverse to reach one node from another. A hop count of 1 means direct connection; 3 means you traverse through 2 intermediate nodes.

**Distance bands** convert raw hop counts into meaningful categories: "direct" (0-1 hops), "near" (2-3 hops), "mid-range" (4-6 hops), and "distant" (7+ hops). These categories help interpret the semantic meaning of graph distances.

**Confidence decay** multiplies edge weights along a path to compute accumulated trust. If each edge has weight 0.8, a 3-hop path has confidence decay of 0.8³ = 0.512, indicating moderate confidence in the connection.

**Path analysis** finds optimal routes between nodes using algorithms like Dijkstra's shortest path or Yen's k-shortest paths algorithm.

**Distance intelligence vs. graph analytics:** Analytics computes statistical measures like centrality and communities across the entire graph. Distance intelligence focuses on specific paths and relationships between particular nodes.

**Distance intelligence vs. graph traversal:** Simple traversal follows edges to find neighbors. Distance intelligence quantifies the quality and confidence of those connections using weights, paths, and decay metrics.

## Why Use Distance Intelligence?

**Confidence-aware retrieval.** Instead of treating all graph connections equally, distance intelligence weights results by path confidence, giving higher rankings to nodes connected through stronger, more direct relationships.

**Relationship discovery.** Find not just whether two entities are connected, but how they're connected, through which intermediaries, and with what level of confidence across the full path.

**Causal analysis.** Trace cause-and-effect chains through your knowledge graph with quantified confidence at each step, essential for decision tracking and audit trails.

**Precedent search.** Find similar past cases by analyzing structural similarity and path patterns, not just content similarity.

**Graph-aware ranking.** Blend semantic similarity with graph proximity to surface contextually relevant results that pure vector search would miss.

## When To Use / When Not To Use

**Use distance intelligence for:**
- Multi-hop reasoning where path quality matters
- Attribution analysis requiring confidence assessment
- Causal chain analysis and decision tracing
- Proximity-weighted retrieval from specific anchor nodes
- Finding alternative connection routes for verification
- Ranking results by both content relevance and structural proximity

**Simple graph traversal may be sufficient for:**
- Finding direct neighbors of a node
- Basic graph exploration without confidence weighting
- Cases where all edges have equal importance
- Simple reachability queries (can A reach B?)

**Distance intelligence may be unnecessary for:**
- Single-hop neighbor lookups
- Graphs where edge weights don't represent meaningful confidence
- Simple existence queries rather than quality assessment
- Scenarios where path analysis adds unnecessary complexity

<Info>
  Distance Intelligence feeds into proximity-blended retrieval (`proximity_weight` on `retrieve()`), causal chain analysis (`trace_decision_causality()`), and advanced precedent search (`find_precedents_hybrid()`). Enable it by passing `include_distance_metadata=True` on neighbor queries or `proximity_weight > 0` on retrieval calls.
</Info>

## Distance Bands: Turning Hop Counts into Meaning

The first tool in distance intelligence is `classify_path_distance` — it maps any Breadth-First Search (BFS) depth to a human-readable band that carries semantic meaning.

```python
from semantica.utils.helpers import classify_path_distance

print(classify_path_distance(0))   # "direct"  — same node
print(classify_path_distance(1))   # "direct"  — single edge
print(classify_path_distance(2))   # "near"    — two-hop neighbourhood
print(classify_path_distance(3))   # "near"
print(classify_path_distance(5))   # "mid-range"
print(classify_path_distance(9))   # "distant" — treat with caution
```

| Band | Hop Range | What it means in practice |
| :--- | :-------- | :------------------------ |
| `"direct"` | 0–1 | Direct relationship — high confidence inferences |
| `"near"` | 2–3 | Two-hop neighbourhood — closely related, reliable |
| `"mid-range"` | 4–6 | Reachable but semantically separated |
| `"distant"` | 7+ | Weakly coupled — treat inferences with caution |

These bands appear automatically on every result that uses `include_distance_metadata=True`, `proximity_weight > 0`, or `trace_decision_causality()`. You do not compute them manually — they are attached to the result.

## Confidence Decay: How Trust Erodes Along a Path

Each hop along a path multiplies the accumulated confidence by the edge weight. The product — `confidence_decay` — is the single most useful signal for deciding whether a multi-hop inference is trustworthy.

<Info>
  **Confidence Decay and Edge Weights:** Confidence decay depends directly on edge weights in your graph. Weights should represent confidence, trust, relevance, or similar domain-specific signals where higher values indicate stronger relationships. Unweighted graphs (all edges weight 1.0) produce no meaningful decay analysis.
</Info>

<Info>
  **Dense Graph Warning:** Very dense graphs can make path analysis computationally expensive and results harder to interpret. Dense connectivity creates many possible paths with similar weights, making distance-based rankings less discriminating.
</Info>

```python
from semantica.context import ContextGraph

graph = ContextGraph()
graph.add_node("apt29",       "ThreatActor",   "APT29 / NOBELIUM")
graph.add_node("hammertoss",  "Malware",       "HAMMERTOSS C2 tool")
graph.add_node("twitter_c2",  "Infrastructure","APT29 Twitter C2 channel")
graph.add_node("nato_target", "Target",        "NATO defense contractor")

graph.add_edge("apt29",      "hammertoss",  "deploys", weight=0.95)
graph.add_edge("hammertoss", "twitter_c2",  "uses",    weight=0.88)
graph.add_edge("twitter_c2", "nato_target", "reaches", weight=0.80)

# Request neighbors with full distance metadata attached
neighbors = graph.get_neighbors(
    "apt29",
    hops=3,
    include_distance_metadata=True,
)

for n in neighbors:
    print("{:20s}  band={:10s}  decay={:.3f}  hop={}".format(
        n["id"],
        n["distance_band"],
        n["confidence_decay"],
        n["hop"],
    ))
```

Output:

```text
hammertoss            band=direct     decay=0.950  hop=1
twitter_c2            band=near       decay=0.836  hop=2
nato_target           band=near       decay=0.669  hop=3
```

The `nato_target` node is reachable — but with only 0.669 confidence decay. That means any inference drawn from the connection between APT29 and the NATO contractor carries a 33% uncertainty budget accumulated across three hops. At "near" band, the inference is still usable; at "distant" band with similar decay, you would flag it for human review.

## Getting All Neighbors with Distance Metadata

`get_neighbor_distances` returns every reachable node up to a given hop depth, filtered by a minimum confidence threshold, ordered by nearest hops first and strongest decay first within each hop.

```python
neighbors = graph.get_neighbor_distances(
    "apt29",
    hops=4,
    relationship_types=["deploys", "uses", "reaches"],
    min_confidence=0.60,   # drop nodes where confidence_decay < 0.60
)

# Each result dict contains:
# "id", "type", "content"    — node identity
# "relationship"             — edge type of the last hop
# "weight"                   — edge weight of the last hop
# "hop"                      — BFS depth from anchor
# "distance_band"            — "direct" / "near" / "mid-range" / "distant"
# "confidence_decay"         — product of all edge weights along the path
# "path_to_anchor"           — full node ID list from anchor to this node

for n in neighbors:
    print("[{:10s}] {:20s}  decay={:.3f}  path={}".format(
        n["distance_band"],
        n["id"],
        n["confidence_decay"],
        " → ".join(n["path_to_anchor"]),
    ))
```

## Finding the Shortest Path Between Two Nodes

`PathFinder` exposes five path algorithms. The right one depends on whether you need the single cheapest path, multiple alternative paths, or all paths from a source.

```python
from semantica.kg import PathFinder

pf = PathFinder()
```

**Dijkstra — weighted shortest path.** Use this as the default. It finds the path where the sum of edge weights is minimised.

```python
path = pf.dijkstra_shortest_path(
    graph  = graph,
    source = "apt29",
    target = "nato_target",
)
length = pf.path_length(graph, path)
print("Shortest path:", " → ".join(path))
print("Path length  :", round(length, 3))
```

**BFS — unweighted shortest path.** Use when you want fewest hops regardless of edge weights.

```python
path = pf.bfs_shortest_path(graph, "apt29", "nato_target")
print("Hop count:", len(path) - 1)
```

**K-shortest paths — Yen's algorithm.** Yen's algorithm finds multiple alternative paths between two nodes, ranked by total path cost. Use when you need alternative attribution chains, redundancy analysis, or corroboration routes. Finding the three shortest paths and showing they all converge on the same target is stronger evidence than a single path.

```python
k_paths = pf.find_k_shortest_paths(graph, "apt29", "nato_target", k=3)

for i, path in enumerate(k_paths, 1):
    length = pf.path_length(graph, path)
    band   = classify_path_distance(len(path) - 1)
    print("Path {} [{}] length={:.3f}: {}".format(
        i, band, length, " → ".join(path)
    ))
```

**All shortest paths from a source.** Use when you want to map everything reachable from an anchor node and understand the structural layout.

```python
all_paths = pf.all_shortest_paths(graph, source="apt29")

for target, paths in all_paths.items():
    path = paths[0]
    print("{:20s}  hops={}  path={}".format(
        target, len(path) - 1, " → ".join(path)
    ))
```

## Proximity-Blended Retrieval

Standard semantic retrieval ranks results by text similarity to the query. Proximity-blended retrieval adds a second signal: how structurally close is each result to an anchor node in the graph? The `proximity_weight` parameter controls the blend.

```python
from semantica.context import AgentContext, ContextGraph
from semantica.vector_store import VectorStore

graph   = ContextGraph(advanced_analytics=True)
context = AgentContext(
    vector_store=VectorStore(backend="faiss", dimension=768),
    knowledge_graph=graph,
    hybrid_alpha=0.5,
)

context.store([
    "APT29 exploited CVE-2024-3400 in PAN-OS targeting NATO governments.",
    "HAMMERTOSS is APT29's C2 tool using Twitter as a covert channel.",
    "SUNBURST was a supply chain implant targeting SolarWinds Orion.",
], extract_entities=True, extract_relationships=True)

# 70% semantic + 30% graph proximity, anchored at APT29
results = context.retrieve(
    "nation-state C2 infrastructure",
    max_results      = 8,
    use_graph        = True,
    anchor_node      = "APT29",
    max_hops         = 3,
    proximity_weight = 0.30,
    min_score        = 0.20,
)

for r in results:
    print("[{:.3f}]  band={:10s}  hop={}  decay={:.3f}  {}".format(
        r.get("combined_score", r["score"]),
        r.get("distance_band",   "-"),
        r.get("hop_distance",    "-"),
        r.get("confidence_decay", 0),
        r["content"][:70],
    ))
```

When `proximity_weight > 0`, each result gains `proximity_score`, `combined_score`, `hop_distance`, `distance_band`, `confidence_decay`, and `path_to_anchor` — giving you a complete picture of why each result ranked where it did.

## Finding Structurally Similar Nodes

When you want to know which other nodes in the graph behave like a given node — same connectivity pattern or similar text — `find_similar_nodes` exposes the modes implemented on `ContextGraph` today.

```python
# Content similarity — text overlap on node content fields
content_similar = graph.find_similar_nodes(
    "CVE-2024-3400",
    similarity_type = "content",
    top_k           = 5,
)

# Structural similarity — nodes with similar neighbourhood topology
struct_similar = graph.find_similar_nodes(
    "CVE-2024-3400",
    similarity_type = "structural",
    top_k           = 5,
)

for n in content_similar:
    print("[{:.3f}] {}  {}".format(n["score"], n["type"], n["id"]))
```

`similarity_type="content"` compares node text/content, while `similarity_type="structural"` compares neighbourhood topology. Other values currently fall back to content similarity, so reserve `"embedding"` for lower-level KG APIs rather than `ContextGraph.find_similar_nodes()`.

## Domain Examples

<Tabs>

<Tab title="Defense — CTI/Threat">

Finding the primary attribution path from a C2 IP to a threat actor, then finding all alternative corroboration paths to strengthen the attribution case before it goes into an intelligence product.

```python
from semantica.context import ContextGraph
from semantica.kg import PathFinder
from semantica.utils.helpers import classify_path_distance

graph = ContextGraph(advanced_analytics=True)

for node_id, ntype, content in [
    ("apt29",       "ThreatActor",   "APT29 / NOBELIUM / Cozy Bear"),
    ("hammertoss",  "Malware",       "HAMMERTOSS C2 backdoor"),
    ("twitter_c2",  "Infrastructure","APT29 Twitter C2 (steganography)"),
    ("github_c2",   "Infrastructure","APT29 GitHub dead-drop resolver"),
    ("as200651",    "Network",       "APT29 hosting cluster AS200651"),
    ("nato_gov",    "Target",        "NATO government agency"),
]:
    graph.add_node(node_id, ntype, content)

graph.add_edge("apt29",     "hammertoss",  "deploys",   weight=0.95)
graph.add_edge("hammertoss","twitter_c2",  "c2_via",    weight=0.88)
graph.add_edge("hammertoss","github_c2",   "c2_via",    weight=0.82)
graph.add_edge("twitter_c2","as200651",    "hosted_on", weight=0.90)
graph.add_edge("github_c2", "as200651",    "resolves",  weight=0.76)
graph.add_edge("as200651",  "nato_gov",    "targets",   weight=0.85)

pf = PathFinder()

# Primary attribution path
primary = pf.dijkstra_shortest_path(graph, "apt29", "nato_gov")
length  = pf.path_length(graph, primary)
band    = classify_path_distance(len(primary) - 1)
print("Primary [{}] length={:.3f}: {}".format(band, length, " → ".join(primary)))

# Three corroboration paths
k_paths = pf.find_k_shortest_paths(graph, "apt29", "nato_gov", k=3)
for i, path in enumerate(k_paths, 1):
    l = pf.path_length(graph, path)
    b = classify_path_distance(len(path) - 1)
    print("Alt {}: {} [{}, length={:.3f}]".format(i, " → ".join(path), b, l))

# All reachable from APT29 with confidence >= 60%
neighbors = graph.get_neighbor_distances("apt29", hops=4, min_confidence=0.60)
print("\nReachable from APT29 (confidence >= 60%):")
for n in neighbors:
    print("  [{:10s}]  decay={:.3f}  {}".format(
        n["distance_band"], n["confidence_decay"], n["id"]
    ))
```

</Tab>

<Tab title="Security — SOC/Incident">

Mapping the lateral movement attack graph, finding all alternative routes an attacker could take to the domain controller, and scoring each route by confidence decay to prioritise which paths to block first.

```python
from semantica.context import ContextGraph
from semantica.kg import PathFinder

graph = ContextGraph()

for node_id, ntype, content in [
    ("attacker_ip", "ExternalHost", "Attacker 185.220.101.47"),
    ("wkstn047",    "Host",         "Compromised workstation WKSTN-047"),
    ("svc_backup",  "Account",      "Stolen service account SVC-BACKUP"),
    ("jump_server", "Host",         "Jump server JUMP-01"),
    ("dc01",        "Host",         "Domain controller DC01"),
    ("ad_forest",   "Asset",        "Active Directory forest root"),
]:
    graph.add_node(node_id, ntype, content)

graph.add_edge("attacker_ip","wkstn047",    "initial_access",   weight=0.90)
graph.add_edge("wkstn047",   "svc_backup",  "credential_theft", weight=0.85)
graph.add_edge("svc_backup", "jump_server", "lateral_move",     weight=0.78)
graph.add_edge("jump_server","dc01",        "lateral_move",     weight=0.88)
graph.add_edge("wkstn047",   "dc01",        "direct_smb",       weight=0.60)
graph.add_edge("dc01",       "ad_forest",   "controls",         weight=0.98)

pf = PathFinder()

# All routes to DC01 — which to block first?
routes = pf.find_k_shortest_paths(graph, "attacker_ip", "dc01", k=3)
for i, route in enumerate(routes, 1):
    length = pf.path_length(graph, route)
    print("Route {} (length={:.3f}): {}".format(i, length, " → ".join(route)))

# What is exposed if DC01 is compromised?
exposed = graph.get_neighbor_distances("dc01", hops=2, min_confidence=0.70)
for n in exposed:
    print("Exposed: {:15s}  [{:8s}]  decay={:.3f}".format(
        n["id"], n["distance_band"], n["confidence_decay"]
    ))
```

</Tab>

<Tab title="Life Science — Clinical/Pharma">

Mapping drug-enzyme inhibition chains, computing confidence decay for multi-step metabolic pathways, and using proximity-blended retrieval to surface the most structurally relevant drug interaction evidence.

```python
from semantica.context import AgentContext, ContextGraph
from semantica.vector_store import VectorStore
from semantica.kg import PathFinder

graph   = ContextGraph(advanced_analytics=True)
context = AgentContext(
    vector_store=VectorStore(backend="faiss", dimension=768),
    knowledge_graph=graph,
    graph_expansion=True,
)

for node_id, ntype, content in [
    ("warfarin",    "Drug",   "Warfarin — anticoagulant, narrow therapeutic window"),
    ("amiodarone",  "Drug",   "Amiodarone — antiarrhythmic"),
    ("cyp2c9",      "Enzyme", "CYP2C9 — hepatic cytochrome P450"),
    ("bleeding",    "ADE",    "Major bleeding adverse event"),
    ("cyp3a4",      "Enzyme", "CYP3A4 — major metabolising enzyme"),
    ("simvastatin", "Drug",   "Simvastatin — HMG-CoA reductase inhibitor"),
]:
    graph.add_node(node_id, ntype, content)

graph.add_edge("amiodarone", "cyp2c9",     "inhibits",    weight=0.92)
graph.add_edge("cyp2c9",     "warfarin",   "metabolises", weight=0.95)
graph.add_edge("warfarin",   "bleeding",   "risk_of",     weight=0.88)
graph.add_edge("amiodarone", "cyp3a4",     "inhibits",    weight=0.80)
graph.add_edge("cyp3a4",     "simvastatin","metabolises", weight=0.90)

pf = PathFinder()

# Interaction chain: amiodarone → bleeding (3 hops, decay = 0.92 × 0.95 × 0.88 = 0.769)
path   = pf.dijkstra_shortest_path(graph, "amiodarone", "bleeding")
length = pf.path_length(graph, path)
print("Interaction chain: {} (length: {:.3f})".format(" → ".join(path), length))

# All paths from amiodarone — what does it reach?
all_paths = pf.all_shortest_paths(graph, "amiodarone")
for target, paths in all_paths.items():
    p = paths[0]
    print("  {:15s}  hops={} path={}".format(target, len(p)-1, " → ".join(p)))

# Proximity-blended retrieval anchored at amiodarone
context.store([
    "CYP2C9 inhibition by amiodarone reduces warfarin metabolism, raising INR.",
    "Patients on warfarin and amiodarone have 4-fold increased major bleeding risk.",
], extract_entities=True, extract_relationships=True)

results = context.retrieve(
    "anticoagulant enzyme inhibition",
    anchor_node      = "amiodarone",
    max_hops         = 3,
    proximity_weight = 0.35,
    max_results      = 5,
)
for r in results:
    print("[{:.3f}]  {:10s}  {}".format(
        r.get("combined_score", r["score"]),
        r.get("distance_band", "-"),
        r["content"][:80],
    ))
```

</Tab>

<Tab title="Banking — Risk/Compliance">

Scoring causal distance from a macroeconomic shock to specific loan portfolios, finding all exposure routes, and recording a stress-test decision with full causal chain annotation.

```python
from semantica.context import AgentContext, ContextGraph
from semantica.vector_store import VectorStore
from semantica.kg import PathFinder
from semantica.utils.helpers import classify_path_distance

graph   = ContextGraph(advanced_analytics=True)
context = AgentContext(
    vector_store=VectorStore(backend="faiss", dimension=768),
    knowledge_graph=graph,
    graph_expansion=True,
    decision_tracking=True,
)

for node_id, ntype, content in [
    ("rate_hike",      "MacroEvent", "Central bank +300bps rate cycle"),
    ("real_estate",    "Sector",     "UK residential real estate"),
    ("cre_sector",     "Sector",     "UK commercial real estate"),
    ("ltv_stress",     "RiskFactor", "LTV ratios deteriorate under higher rates"),
    ("dscr_stress",    "RiskFactor", "DSCR falls below 1.0 at +300bps"),
    ("resi_portfolio", "Portfolio",  "Retail mortgage book £4.2bn"),
    ("cre_portfolio",  "Portfolio",  "CRE lending book £1.8bn"),
    ("provision",      "Impact",     "Expected credit loss provision increase"),
]:
    graph.add_node(node_id, ntype, content)

graph.add_edge("rate_hike",    "real_estate",    "depresses", weight=0.88)
graph.add_edge("rate_hike",    "cre_sector",     "depresses", weight=0.85)
graph.add_edge("real_estate",  "ltv_stress",     "causes",    weight=0.78)
graph.add_edge("cre_sector",   "dscr_stress",    "causes",    weight=0.82)
graph.add_edge("ltv_stress",   "resi_portfolio", "exposes",   weight=0.90)
graph.add_edge("dscr_stress",  "cre_portfolio",  "exposes",   weight=0.88)
graph.add_edge("resi_portfolio","provision",      "increases", weight=0.75)
graph.add_edge("cre_portfolio", "provision",      "increases", weight=0.80)

pf = PathFinder()

# How does a rate hike reach ECL provisions?
k_routes = pf.find_k_shortest_paths(graph, "rate_hike", "provision", k=3)
for i, route in enumerate(k_routes, 1):
    length = pf.path_length(graph, route)
    hops   = len(route) - 1
    band   = classify_path_distance(hops)
    print("Route {} [{:10s}] length={:.3f}: {}".format(
        i, band, length, " → ".join(route)
    ))

# Full risk exposure map
exposed = graph.get_neighbor_distances("rate_hike", hops=5, min_confidence=0.65)
print("\nRisk exposure map from rate hike:")
for n in exposed:
    print("  [{:10s}]  decay={:.3f}  {}".format(
        n["distance_band"], n["confidence_decay"], n["id"]
    ))

# Record and trace the stress-test decision
dec_id = context.record_decision(
    category       = "stress_test",
    scenario       = "+300bps rate shock — portfolio stress test Q3 2025",
    reasoning      = "LTV deterioration on resi book within tolerance; CRE DSCR breach requires provisioning",
    outcome        = "increase_provision_cre_book",
    confidence     = 0.87,
    decision_maker = "risk_model_v3",
)

chains = graph.trace_decision_causality(dec_id, max_depth=5)
for chain in chains:
    print("\nCausal chain ({} hops, {}, decay={:.3f}):".format(
        chain["hop_count"], chain["distance_band"], chain["confidence_decay"]
    ))
    print("  Interpretation:", chain["interpretation"])
```

</Tab>

</Tabs>

## Common Pitfalls

**Treating confidence decay as statistical probability.** Confidence decay is a heuristic measure based on edge weights, not a statistical probability. A decay value of 0.6 doesn't mean "60% probability" — it means the path strength based on your domain-specific weight assignments.

**Using unweighted graphs and expecting meaningful decay.** If all edges have weight 1.0, confidence decay will always be 1.0 regardless of path length, providing no useful discrimination between paths. Assign meaningful weights that reflect relationship strength.

**Excessive path exploration on dense graphs.** Dense graphs with many interconnected nodes can generate exponentially large numbers of paths. Limit `max_hops`, use `min_confidence` thresholds, and consider whether simple neighbor lookup would be sufficient.

**Overusing distance analysis when simple neighbor lookup is enough.** If you only need direct neighbors or one-hop connections, basic graph traversal is simpler and faster than full distance intelligence analysis.

**Retrieving excessive graph neighborhoods.** Large `max_hops` values can retrieve massive subgraphs that overwhelm downstream processing. Start with 2-3 hops and increase only when needed for your specific use case.

## Related Guides

- [Context Graphs](context-graphs) — `ContextGraph` node and edge model; `add_edge(weight=...)` feeds confidence decay
- [Graph Analytics](graph-analytics) — centrality, community detection, Node2Vec embeddings, link prediction
- [Agent Memory](agent-memory) — proximity-blended retrieval (`proximity_weight`) integrates distance intelligence into memory search
- [Decision Intelligence](decision-intelligence) — `trace_decision_causality()` for causal chains with distance annotations
- [Reasoning & Rules](reasoning) — `TemporalReasoningEngine` for Allen interval algebra over time-bounded graph nodes
