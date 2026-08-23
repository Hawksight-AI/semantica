---
title: "Context Graphs"
description: "How Semantica stores, links, searches, and traverses knowledge as a thread-safe in-memory property graph — with temporal validity, cross-graph navigation, proximity-blended retrieval, and conversation-to-graph construction."
icon: "diagram-project"
---

`ContextGraph` is a thread-safe, in-memory property graph with temporal validity windows on every node and edge, built-in Breadth-First Search (BFS) traversal, a FAISS vector index for semantic search, and proximity-blended retrieval through `AgentContext`. Use it when multiple agents or threads write to a shared knowledge base while analysts query it in real time.

## What Is a Context Graph?

A context graph is a property graph that stores entities as **nodes** and relationships as **edges**, enriched with metadata and temporal validity.

**Nodes** represent entities in your domain — threat actors, vulnerabilities, companies, people, or any concept you want to track. Each node has an ID, a type, optional content text, and metadata properties.

**Edges** represent relationships between entities — "APT29 uses SUNBURST", "Alice works_for Acme Corp", or "CVE-2024-3400 affects SolarWinds". Each edge has a type, weight, and optional metadata.

**Metadata** stores additional properties on nodes and edges as key-value pairs — geographic origin, confidence scores, timestamps, or any domain-specific attributes.

**Property graphs** like ContextGraph differ from simple networks by supporting rich metadata on both nodes and edges, making them suitable for complex real-world domains where relationships need context and attributes.

## Why Use a Context Graph?

**Relationship analysis.** Graph structure reveals how entities connect — who targets whom, what exploits what, which decisions led to which outcomes. Relationships that aren't obvious from individual documents become clear when connected.

**Multi-hop reasoning.** Answer questions like "what can APT29 reach within 3 steps?" or "which vulnerabilities affect our critical systems?" by traversing the graph rather than keyword matching.

**Context preservation.** Unlike vector search alone, graphs preserve the relationships between entities. When you find a relevant threat actor, you can immediately see their tools, targets, and infrastructure.

**Temporal state tracking.** Track when relationships were valid, when infrastructure was active, or when decisions were made. Query historical states or filter to current information only.

## When To Use / When Not To Use

**Use context graphs for:**
- Complex domains with rich relationships between entities
- Multi-hop reasoning and traversal queries
- Temporal tracking of entity relationships and states
- Integration with structured data that has clear entity relationships
- Collaborative environments where multiple sources contribute connected data

**Simple vector search may be sufficient for:**
- Pure document retrieval where relationships don't matter
- Single-hop similarity searches
- Exploratory research where structure isn't well-defined
- Read-only analysis of unstructured text without entity relationships

**Graphs may be unnecessary for:**
- Simple keyword or semantic search tasks
- Static document collections without evolving relationships
- Single-user, short-term analysis projects
- Cases where setup complexity exceeds the relationship complexity

<Info>
  ContextGraph is an **in-memory data structure**. All nodes, edges, and metadata are stored in Python dictionaries and lists. For standalone graphs, persist state with `save_to_file()`. When using `AgentContext`, call `AgentContext.save()` instead — it saves the graph, the FAISS vector index, and memory in one step. For analytical operations on top of a populated graph — centrality rankings, community detection, node embeddings, link prediction — see the [Graph Analytics guide](graph-analytics). For recording and querying decisions stored as nodes, see the [Decision Intelligence guide](decision-intelligence).
</Info>

## Constructing the Graph

You can construct a ContextGraph in two ways:

**Manual construction** — Add nodes and edges programmatically using `add_node()` and `add_edge()`. This gives you complete control over the graph structure and is ideal when you have structured data or want to build specific relationship patterns.

**Automated extraction workflows** — Pass a list of documents to `AgentContext.store()` with `extract_entities=True` or `extract_relationships=True`. This requires `knowledge_graph=` to be set in the `AgentContext` constructor; the extraction process then creates nodes for detected entities and edges for discovered relationships. Single strings passed to `store()` are stored as memory items only and do not trigger graph construction.

The simplest possible graph needs no arguments:

```python
from semantica.context import ContextGraph

graph = ContextGraph()
```

For a threat intelligence workload that will also run analytics, enable the sub-components at construction time — they initialize lazily but must be declared upfront:

```python
graph = ContextGraph(
    advanced_analytics  = True,
    centrality_analysis = True,
    community_detection = True,
    node_embeddings     = True,
)
```

The graph is backed entirely by Python dicts and a re-entrant lock (`threading.RLock`). No external service, no database connection, no network call. You can stand up a fully functional intelligence graph in a unit test with a single import.

## Adding Your First Entities

Every entity goes in as a node with a type, optional content string, and any number of metadata kwargs:

```python
# add_node(node_id, node_type, content=None, **properties) -> None
# All extra kwargs land in ContextNode.metadata

graph.add_node(
    "APT29",
    "ThreatActor",
    "Russian state-sponsored group, also known as COZY BEAR",
    origin="Russia",
    motivation="espionage",
    first_seen="2008",
)

graph.add_node(
    "SUNBURST",
    "Malware",
    "Supply-chain backdoor embedded in SolarWinds Orion updates",
    family="backdoor",
    first_seen="2019-10",
    platforms=["Windows"],
)

graph.add_node(
    "CVE-2020-10148",
    "Vulnerability",
    "SolarWinds Orion API authentication bypass",
    cvss=10.0,
    affected_product="SolarWinds Orion",
)

graph.add_node(
    "45.142.212.100",
    "C2Domain",
    "Command-and-control server observed in SUNBURST campaign",
    asn="AS29550",
    country="Netherlands",
)

graph.add_node(
    "SolarWinds",
    "Victim",
    "SolarWinds Corporation — software supply chain victim",
    sector="Technology",
)
```

<Info>
  There is no `properties={}` parameter. Pass all metadata fields as direct keyword arguments. Calling `add_node("x", "t", properties={"k": "v"})` would store the dict under a key literally named `properties` in metadata — not what you want.
</Info>

Now connect them with typed, weighted edges:

```python
# add_edge(source_id, target_id, edge_type="related_to", weight=1.0, **properties) -> None

graph.add_edge("APT29",          "SUNBURST",         "uses",       weight=1.0)
graph.add_edge("SUNBURST",       "CVE-2020-10148",   "exploits",   weight=0.95)
graph.add_edge("SUNBURST",       "SolarWinds",       "targets",    weight=1.0)
graph.add_edge("APT29",          "45.142.212.100",   "operates",   weight=0.9)
graph.add_edge("SUNBURST",       "45.142.212.100",   "beacons_to", weight=0.85)
graph.add_edge("CVE-2020-10148", "SolarWinds",       "affects",    weight=1.0)
```

Check what you have:

```python
s = graph.stats()
print(f"Nodes: {s['node_count']}, Edges: {s['edge_count']}, Density: {s['density']:.4f}")
# Nodes: 5, Edges: 6, Density: 0.3000

print("Node types:", s["node_types"])   # {"ThreatActor": 1, "Malware": 1, ...}
print("Edge types:", s["edge_types"])   # {"uses": 1, "exploits": 1, ...}
```

## Temporal Validity — Intel Has an Expiry Date

Use `valid_from` and `valid_until` to mark nodes and edges with activity windows so temporal queries exclude stale data:

```python
# The C2 domain was only active during the campaign window
graph.add_node(
    "45.142.212.100",
    "C2Domain",
    "SUNBURST C2 — active during campaign",
    asn="AS29550",
    valid_from="2019-10-01T00:00:00",
    valid_until="2020-12-17T00:00:00",   # DarkHalo C2 shutdown date
)

# A detection rule with a limited effectiveness window
graph.add_node(
    "SIGMA-SUNBURST-001",
    "DetectionRule",
    "Sigma rule: SUNBURST beacon pattern",
    rule_type="sigma",
    valid_from="2020-12-13T00:00:00",
    valid_until="2021-06-30T23:59:59",   # deprecated after updated TTPs observed
)

# Temporal edges work the same way
graph.add_edge(
    "APT29", "45.142.212.100", "operates",
    weight=0.9,
    valid_from="2019-10-01T00:00:00",
    valid_until="2020-12-17T00:00:00",
)
```

Now ask: which nodes were active on December 1, 2020 (during the campaign)?

```python
from datetime import datetime

# at_time must be a datetime object — not an ISO string
active = graph.find_active_nodes(
    node_type="C2Domain",
    at_time=datetime(2020, 12, 1, 0, 0, 0),
)
print(f"Active C2 domains on 2020-12-01: {len(active)}")
# Active C2 domains on 2020-12-01: 1  (45.142.212.100 is still in its window)

# Compare to today — the C2 is expired
active_now = graph.find_active_nodes(node_type="C2Domain")  # defaults to datetime.now()
print(f"Active C2 domains today: {len(active_now)}")
# Active C2 domains today: 0

# Full temporal snapshot — only nodes and edges valid at a given moment
snapshot = graph.state_at(datetime(2020, 12, 1, 0, 0, 0))
print(f"Active nodes: {len(snapshot['nodes'])}")
print(f"Active edges: {len(snapshot['edges'])}")
```

This is how you prevent a query today from returning "APT29 currently operates 45.142.212.100" — the edge is outside its validity window and won't appear in temporal queries.

## Finding Nodes

`find_node()` retrieves by ID, and `find_nodes()` filters by type or metadata:

```python
# find_node(node_id) -> Optional[Dict]
# Returns keys: "id", "type", "content", "metadata"  — NOT "node_id" or "node_type"

actor = graph.find_node("APT29")
if actor:
    print(actor["id"])       # "APT29"
    print(actor["type"])     # "ThreatActor"
    print(actor["content"])  # "Russian state-sponsored group..."
    print(actor["metadata"]) # {"origin": "Russia", "motivation": "espionage", ...}

# find_nodes(node_type=None, skip=0, limit=None) -> List[Dict]
all_actors = graph.find_nodes(node_type="ThreatActor")
all_vulns  = graph.find_nodes(node_type="Vulnerability")
```

## Traversing the Graph

BFS traversal answers reachability questions directly:

```python
# get_neighbors(node_id, hops=1, relationship_types=None,
#               min_weight=0.0, include_distance_metadata=False) -> List[Dict]
# Each result: {"id", "type", "content", "relationship", "weight", "hop"}

neighbors = graph.get_neighbors("APT29", hops=2)
for n in neighbors:
    print(f"  hop={n['hop']}  [{n['relationship']}]  {n['id']}  ({n['type']})")

# hop=1  [uses]       SUNBURST         (Malware)
# hop=1  [operates]   45.142.212.100   (C2Domain)
# hop=2  [exploits]   CVE-2020-10148   (Vulnerability)
# hop=2  [targets]    SolarWinds       (Victim)
# hop=2  [beacons_to] 45.142.212.100   (C2Domain)  — also reachable via hop-1
```

Filter to only follow specific edge types — useful when you want to trace just the exploitation chain without noise from other relationship types:

```python
exploit_chain = graph.get_neighbors(
    "APT29",
    hops=3,
    relationship_types=["uses", "exploits", "affects"],
)
```

When you need to understand how confident a connection is based on graph distance, enable distance metadata. Each result gains a `confidence_decay` multiplier — nodes further away are weighted down:

```python
neighbors = graph.get_neighbors(
    "APT29",
    hops=3,
    include_distance_metadata=True,
)
for n in neighbors:
    print(f"  {n['id']:30s}  band={n['distance_band']:8s}  decay={n['confidence_decay']:.3f}")

# APT29's direct SUNBURST edge:   band=direct   decay=1.000
# CVE reached via SUNBURST:       band=near     decay=0.850
# SolarWinds reached via CVE:     band=mid      decay=0.700
```

To trace the route from a starting node to a specific target, use `get_neighbors()` with `include_distance_metadata=True`. Each result includes a `path_to_anchor` list showing the exact sequence of node IDs from source to that neighbor:

```python
# get_neighbors with include_distance_metadata=True returns path_to_anchor
neighbors = graph.get_neighbors("APT29", hops=3, include_distance_metadata=True)
for n in neighbors:
    if n["id"] == "SolarWinds":
        print(" → ".join(n["path_to_anchor"]))
        # APT29 → SUNBURST → SolarWinds
```

## Handling Concurrent Writes

`ContextGraph` handles concurrent writes with a re-entrant lock (`threading.RLock`) that wraps every mutation — you do not need to add your own synchronization:

```python
import threading
from semantica.context import ContextGraph

graph = ContextGraph()

def misp_ingest_worker(events):
    for event in events:
        graph.add_node(event["id"], event["type"], event["value"])
        for attr in event.get("attributes", []):
            graph.add_edge(event["id"], attr["value"], "has_attribute")

def nvd_ingest_worker(cves):
    for cve in cves:
        graph.add_node(cve["id"], "Vulnerability", cve["description"], cvss=cve["cvss"])
        graph.add_edge(cve["id"], cve["product"], "affects")

# Both threads write safely to the same graph
t1 = threading.Thread(target=misp_ingest_worker, args=(misp_events,))
t2 = threading.Thread(target=nvd_ingest_worker, args=(nvd_batch,))
t1.start(); t2.start()
t1.join(); t2.join()

print(graph.stats())
```

The lock is re-entrant, so internal calls that themselves acquire the lock (for example, `add_edge()` calling `find_node()` internally) won't deadlock.

## Semantic Search via AgentContext

`AgentContext` wraps the graph with a FAISS vector index and lets you retrieve by semantic similarity, with optional blending of graph proximity:

```python
from semantica.context import AgentContext, ContextGraph
from semantica.vector_store import VectorStore

graph = ContextGraph()
# ... (populated with CTI nodes as above)

context = AgentContext(
    vector_store    = VectorStore(backend="faiss", dimension=768),
    knowledge_graph = graph,
    hybrid_alpha    = 0.5,       # 50% semantic / 50% structural weighting
    decision_tracking = True,
)

# Store intel summaries — these become searchable
context.store("APT29 operated SUNBURST backdoor via SolarWinds supply chain compromise")
context.store("45.142.212.100 is a C2 server associated with the SUNBURST campaign")
context.store("CVE-2020-10148 allows unauthenticated API access in SolarWinds Orion")

# Retrieve with graph proximity blending
# anchor_node="APT29" means nodes close to APT29 in the graph score higher
results = context.retrieve(
    "APT29 infrastructure and C2 servers",
    max_results      = 10,
    anchor_node      = "APT29",
    max_hops         = 2,
    proximity_weight = 0.3,    # 30% graph proximity, 70% semantic score
    use_graph        = True,
)

for r in results:
    # "score"          — base semantic similarity (always present)
    # "combined_score" — blended score (present when proximity_weight > 0)
    # "distance_band"  — "direct" / "near" / "mid" / "far"
    score = r.get("combined_score", r.get("score", 0))
    print(f"[{score:.3f}]  {r.get('content', '')[:70]}")
```

`proximity_weight` is a **per-call parameter** on `retrieve()`, not a constructor setting. This means different queries can use different blending ratios on the same context object — a broad semantic search uses `proximity_weight=0.0`, while a neighborhood-focused traversal uses `proximity_weight=0.5`.

## Cross-Graph Navigation

`link_graph()` connects two separate graphs, and `cross_graph_path()` finds paths that span the boundary:

```python
from semantica.context import ContextGraph

actor_graph  = ContextGraph()
victim_graph = ContextGraph()

actor_graph.add_node("APT29",    "ThreatActor", "APT29")
actor_graph.add_node("SUNBURST", "Malware",     "SUNBURST backdoor")
actor_graph.add_edge("APT29", "SUNBURST", "uses")

victim_graph.add_node("SolarWinds", "Victim", "SolarWinds Corporation")
victim_graph.add_node("Treasury",   "Victim", "US Department of Treasury")
victim_graph.add_edge("SolarWinds", "Treasury", "supply_chain_compromised")

link_id = actor_graph.link_graph(
    victim_graph,
    "APT29",
    "SolarWinds",
    link_type="targets",
)

other_graph, target_node_id = actor_graph.navigate_to(link_id)

sw = other_graph.find_node(target_node_id)
if sw:
    print("Reached:", sw["id"])

result = actor_graph.cross_graph_path(
    "APT29",
    victim_graph,
    "Treasury",
)

if result.get("reachable"):
    print(f"Reached in {result['hop_count']} hops")
# APT29 → SUNBURST → SolarWinds → Treasury
```

## Serialization and Persistence

After each ingest cycle, save the graph to disk. On restart, restore it — the entire node and edge set is preserved:

```python
# Save
graph.save_to_file("cti_graph.json")

# Restore
restored = ContextGraph(advanced_analytics=True)
restored.load_from_file("cti_graph.json")

print(restored.stats())

# to_dict() gives you the raw serializable dict
d = graph.to_dict()
# d["nodes"]      → list of node dicts
# d["edges"]      → list of edge dicts
# d["statistics"] → {"node_count": int, "edge_count": int}
```

For a human-editable, version-control-friendly representation, save a Markdown
directory instead:

```python
graph.save_to_file("context_graph/", format="markdown")

restored = ContextGraph(advanced_analytics=True)
restored.load_from_file("context_graph/", format="markdown")
```

The directory contains a versioned `graph.md` manifest for graph identity,
relationships, and cross-graph link descriptors, plus one file per node under
`nodes/`. A node's content is its Markdown body; its ID, type, properties,
metadata, and temporal validity are YAML frontmatter. Node, edge, family, graph,
and cross-graph link IDs are preserved across round trips.

Markdown loading uses replacement semantics, like `from_dict()`: it parses and
validates the complete directory before replacing the current graph. Invalid YAML,
duplicate IDs, unsupported versions, and unsafe filesystem links fail without
partially mutating the graph. As with JSON loading, an edge endpoint without a node
file creates an `entity` stub node. Symlinks, Windows directory junctions, and other
Windows reparse points are rejected.

Re-exporting to an existing managed directory atomically replaces it, removing stale
node files. Before replacement, Semantica validates the complete canonical export
layout, not just the manifest header. Untracked files, assets, extra directories, or
renamed node files therefore cause the export to fail closed instead of being deleted.
Keep attachments and hand-written indexes outside the managed export directory.

If the graph had cross-graph links created with `link_graph()`, call `resolve_links()` after loading to restore live navigation — object references cannot be serialized, so they must be reconnected manually:

```python
g1b, g2b = ContextGraph(), ContextGraph()
g1b.load_from_file("actor_graph.json")
g2b.load_from_file("victim_graph.json")
g1b.resolve_links({g2b.graph_id: g2b})
```

For full session persistence (graph + FAISS vector index + memory), use `AgentContext.save()` / `AgentContext.load()`:

```python
context.save("agent_state/")

# Later, on restart:
context2 = AgentContext(
    vector_store    = VectorStore(backend="faiss", dimension=768),
    knowledge_graph = ContextGraph(),
)
context2.load("agent_state/")
```

## Common Pitfalls

**Duplicate entities.** Adding "APT-29", "APT29", and "Cozy Bear" as separate nodes fragments the graph when they should be one entity. Use consistent naming conventions upfront, or use `detect_duplicates()` and `EntityMerger` from the [Deduplication](deduplication) guide to merge them after ingestion.

**Inconsistent naming conventions.** Mixing "ThreatActor", "threat_actor", and "Threat-Actor" as node types breaks queries that filter by type. Pick one convention and enforce it across all data sources.

**Over-connecting nodes.** Creating edges between every entity mentioned in the same document adds noise. Focus on meaningful relationships — direct causation, membership, or functional dependencies rather than co-occurrence.

**Storing unnecessary information.** Adding every field from source data as metadata bloats memory usage. Include only properties needed for queries, filtering, or downstream analysis.

**Failing to persist important graph state.** Since ContextGraph is in-memory, shutting down your application loses all nodes and edges unless you call `save_to_file()` or `AgentContext.save()`. Persist regularly during long-running ingestion processes.

## Relationship Between Graph Structure and Vector Search

ContextGraph structure and vector search serve complementary purposes:

- **Graph structure** captures explicit relationships and enables traversal, reachability analysis, and multi-hop reasoning
- **Vector search** enables semantic similarity queries and fuzzy matching based on content

When used together via `AgentContext`, you can blend both approaches — find semantically similar content while boosting results that are structurally close to your starting point in the graph.

## Domain Examples

<Tabs>
  <Tab title="Defense — CTI/Threat">
    Three separate ingest workers write to a shared `ContextGraph` simultaneously (MISP, NVD, classified STIX). Temporal validity prevents stale campaign data from appearing in current-threat queries.

```python
from semantica.context import ContextGraph, AgentContext
from semantica.vector_store import VectorStore
from datetime import datetime

graph = ContextGraph(advanced_analytics=True, community_detection=True)

# Core CTI entities
graph.add_node("APT29", "ThreatActor", "Russian GRU unit, COZY BEAR",
               origin="Russia", motivation="espionage")
graph.add_node("SUNBURST", "Malware", "SolarWinds supply chain backdoor",
               family="backdoor", platforms=["Windows"])
graph.add_node("CVE-2020-10148", "Vulnerability",
               "SolarWinds Orion API auth bypass", cvss=10.0)

# Time-bound C2 infrastructure
graph.add_node("avsvmcloud.com", "C2Domain",
               "SUNBURST DNS C2 domain",
               valid_from="2019-10-01T00:00:00",
               valid_until="2020-12-18T00:00:00")

graph.add_edge("APT29",    "SUNBURST",        "deploys",    weight=1.0)
graph.add_edge("SUNBURST", "CVE-2020-10148",  "exploits",   weight=0.95)
graph.add_edge("SUNBURST", "avsvmcloud.com",  "beacons_to", weight=0.9,
               valid_from="2019-10-01T00:00:00",
               valid_until="2020-12-18T00:00:00")

# What C2 infrastructure is active right NOW?
active_c2 = graph.find_active_nodes(node_type="C2Domain")
print(f"Currently active C2 domains: {len(active_c2)}")
# Currently active C2 domains: 0  — avsvmcloud.com expired in 2020

# Historical query: what was active during the campaign?
campaign_c2 = graph.find_active_nodes(
    node_type="C2Domain",
    at_time=datetime(2020, 6, 1),
)
print(f"C2 domains active June 2020: {len(campaign_c2)}")
# C2 domains active June 2020: 1  — avsvmcloud.com was active

# Traversal: full blast radius from APT29
blast_radius = graph.get_neighbors("APT29", hops=3,
                                   include_distance_metadata=True)
for n in blast_radius:
    print(f"  hop={n['hop']}  decay={n['confidence_decay']:.2f}  {n['id']}")
```

  </Tab>

  <Tab title="Security — SOC/Incident">
    During an active incident, hosts are nodes and observed lateral connections are edges. The graph answers which hosts are on the critical path and what the attacker's reachable network looks like from the initial foothold.

```python
from semantica.context import ContextGraph

graph = ContextGraph(advanced_analytics=True)

# Affected hosts
for host in ["ws-finance-04", "srv-dc-01", "srv-file-02",
             "ws-hr-11", "srv-backup-01"]:
    graph.add_node(host, "Host", f"Windows host: {host}")

# Implants observed
graph.add_node("COBALT-STRIKE-BEACON-01", "Implant",
               "Cobalt Strike beacon, staged from ws-finance-04")
graph.add_node("MIMIKATZ-DUMP-01", "Tool",
               "Credential dump observed on srv-dc-01")

# Lateral movement edges
graph.add_edge("ws-finance-04", "srv-dc-01",               "lateral_move", weight=0.9)
graph.add_edge("srv-dc-01",     "srv-file-02",             "lateral_move", weight=0.85)
graph.add_edge("srv-dc-01",     "srv-backup-01",           "lateral_move", weight=0.8)
graph.add_edge("ws-finance-04", "COBALT-STRIKE-BEACON-01", "hosts",        weight=1.0)
graph.add_edge("srv-dc-01",     "MIMIKATZ-DUMP-01",        "executes",     weight=1.0)

# Blast radius from initial foothold
reachable = graph.get_neighbors("ws-finance-04", hops=3,
                                 relationship_types=["lateral_move"])
print("Reachable via lateral movement:")
for n in reachable:
    print(f"  hop={n['hop']}  {n['id']}")

# Path from initial foothold to the backup server via path_to_anchor
all_paths = graph.get_neighbors("ws-finance-04", hops=3,
                                relationship_types=["lateral_move"],
                                include_distance_metadata=True)
for n in all_paths:
    if n["id"] == "srv-backup-01":
        print(" → ".join(n["path_to_anchor"]))
        # ws-finance-04 → srv-dc-01 → srv-backup-01
```

  </Tab>

  <Tab title="Life Science — Clinical/Pharma">
    A clinical trial knowledge graph tracks drugs, biomarkers, patient populations, adverse events, and regulatory milestones. Each regulatory milestone has a validity window — queries must respect those windows to prevent stale efficacy data from being cited alongside current safety findings.

```python
from semantica.context import ContextGraph
from datetime import datetime

graph = ContextGraph(advanced_analytics=True)

# Entities
graph.add_node("dapagliflozin",     "Drug",        "SGLT2 inhibitor, AstraZeneca")
graph.add_node("HbA1c-reduction",   "Biomarker",   "Primary endpoint: HbA1c change from baseline")
graph.add_node("T2D-adults-65plus", "Population",  "Type 2 diabetes, adults 65+, DECLARE-TIMI 58")
graph.add_node("DKA",               "AdverseEvent","Diabetic ketoacidosis, known SGLT2 risk")

# Phase III data node — valid once submission accepted
graph.add_node("DECLARE-TIMI58-results", "ClinicalData",
               "Phase III CVOT results: dapagliflozin vs placebo",
               phase="III",
               primary_endpoint_met=True,
               valid_from="2019-01-11T00:00:00")   # NEJM publication date

graph.add_edge("dapagliflozin",          "HbA1c-reduction",    "primary_endpoint", weight=1.0)
graph.add_edge("dapagliflozin",          "T2D-adults-65plus",  "studied_in",       weight=1.0)
graph.add_edge("dapagliflozin",          "DKA",                "risk_of",          weight=0.7)
graph.add_edge("DECLARE-TIMI58-results", "dapagliflozin",      "evaluates",        weight=1.0)

# Only retrieve trial data available as of a given regulatory review date
active_data = graph.find_active_nodes(
    node_type="ClinicalData",
    at_time=datetime(2019, 6, 1),
)
print(f"Published trial data available June 2019: {len(active_data)}")
# Published trial data available June 2019: 1

# Traverse: what is known about dapagliflozin within 2 hops?
drug_neighbors = graph.get_neighbors("dapagliflozin", hops=2)
for n in drug_neighbors:
    print(f"  [{n['relationship']}]  {n['id']}  ({n['type']})")
```

  </Tab>

  <Tab title="Banking — Risk/Compliance">
    A counterparty risk graph connects banks, SPVs, exposure instruments, guarantors, and regulatory entities. Entities have reporting-period validity — a counterparty's CDS exposure node is valid only for the quarter it was reported.

```python
from semantica.context import ContextGraph
from datetime import datetime

graph = ContextGraph(advanced_analytics=True, community_detection=True)

# Entities
graph.add_node("BankA",      "Counterparty", "Tier-1 bank, EUR exposure 4.2B")
graph.add_node("SPV-EUR-01", "SPV",          "Structured vehicle, BankA sponsored")
graph.add_node("BankB",      "Counterparty", "Tier-2 bank, USD exposure 0.8B")
graph.add_node("CCP-LME",    "CCP",          "Central counterparty — LME metals")

# Q4 2024 exposure node — valid for the reporting quarter only
graph.add_node("BankA-BankB-CDS-Q42024", "Exposure",
               "CDS notional 400M, BankA writes protection on BankB",
               notional_eur=400_000_000,
               valid_from="2024-10-01T00:00:00",
               valid_until="2024-12-31T23:59:59")

graph.add_edge("BankA",      "SPV-EUR-01",             "sponsors",   weight=1.0)
graph.add_edge("BankA",      "BankB",                  "exposed_to", weight=0.8)
graph.add_edge("BankA",      "BankA-BankB-CDS-Q42024", "holds",      weight=1.0)
graph.add_edge("SPV-EUR-01", "CCP-LME",                "clears_via", weight=0.9)
graph.add_edge("BankB",      "CCP-LME",                "member_of",  weight=1.0)

# Contagion path: if BankA defaults, who is downstream?
downstream = graph.get_neighbors("BankA", hops=3, include_distance_metadata=True)
print("Contagion reach from BankA:")
for n in downstream:
    print(f"  hop={n['hop']}  decay={n['confidence_decay']:.2f}  {n['id']}")

# Q4 exposure picture — only include nodes valid in Q4 2024
q4_exposures = graph.find_active_nodes(
    node_type="Exposure",
    at_time=datetime(2024, 11, 15),
)
print(f"\nActive Q4 2024 exposures: {len(q4_exposures)}")

# Reachability from BankA: identifies all entities in the stress-test scope
stress_reach = graph.get_neighbors("BankA", hops=2)
print(f"Stress-test reachable entities: {len(stress_reach)}")
for n in stress_reach:
    print(f"  hop={n['hop']}  {n['id']}")
```

  </Tab>
</Tabs>

## Related Guides

- [Graph Analytics](graph-analytics) — centrality rankings, community detection, node embeddings, and link prediction on a populated `ContextGraph`
- [Decision Intelligence](decision-intelligence) — recording decisions as typed nodes, causal chain analysis, precedent search, and policy enforcement
- [Ingest](ingest) — loading data from PDFs, APIs, databases, STIX bundles, and RSS feeds into the graph
- [Deduplication](deduplication) — detecting and merging near-duplicate nodes before insertion to prevent graph fragmentation
- [Reasoning](reasoning) — temporal interval algebra (Allen relations), forward/backward chaining, and SPARQL over the knowledge graph
- [Ontology Management](ontology) — deriving formal OWL ontologies from `graph.to_dict()` for downstream reasoning engines
- [Context Module Reference](../reference/context) — full API for `AgentContext`, `ContextGraph`, `ContextNode`, `ContextEdge`
