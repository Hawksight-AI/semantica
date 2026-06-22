---
title: "Context Graphs"
description: "How Semantica stores, links, searches, and traverses knowledge as a thread-safe in-memory property graph — with temporal validity, cross-graph navigation, proximity-blended retrieval, and conversation-to-graph construction."
icon: "diagram-project"
---

`ContextGraph` is a thread-safe, in-memory property graph with temporal validity windows on every node and edge, built-in BFS traversal, a FAISS vector index for semantic search, and proximity-blended retrieval through `AgentContext`. Use it when multiple agents or threads write to a shared knowledge base while analysts query it in real time.

<Info>
  For analytical operations on top of a populated graph — centrality rankings, community detection, node embeddings, link prediction — see the [Graph Analytics guide](graph-analytics). For recording and querying decisions stored as nodes, see the [Decision Intelligence guide](decision-intelligence).
</Info>

## Constructing the Graph

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

For point-to-point routing, use the shortest path finder:

```python
# shortest_path(source_id, target_id, edge_types=None) -> Optional[List[str]]
path = graph.shortest_path("APT29", "SolarWinds")
if path:
    print(" → ".join(path))
# APT29 → SUNBURST → SolarWinds
```

When you need to analyze a sub-cluster in isolation, `extract_subgraph()` gives you a new independent `ContextGraph` instance:

```python
# extract_subgraph(node_ids, include_edges=True) -> ContextGraph
campaign_nodes = ["APT29", "SUNBURST", "CVE-2020-10148", "45.142.212.100", "SolarWinds"]
subgraph = graph.extract_subgraph(campaign_nodes)

s = subgraph.stats()
print(f"Subgraph: {s['node_count']} nodes, {s['edge_count']} edges")
# Subgraph: 5 nodes, 6 edges
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

# Critical path to the backup server
path = graph.shortest_path("ws-finance-04", "srv-backup-01")
print(" → ".join(path))
# ws-finance-04 → srv-dc-01 → srv-backup-01

# Isolate incident subgraph for reporting
incident_nodes = [n["id"] for n in reachable] + ["ws-finance-04"]
subgraph = graph.extract_subgraph(incident_nodes)
print(f"Incident scope: {subgraph.stats()['node_count']} hosts")
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

# Extract stress-test subgraph
stress_nodes = ["BankA", "SPV-EUR-01", "BankB", "CCP-LME"]
subgraph = graph.extract_subgraph(stress_nodes)
print(f"Stress-test scope: {subgraph.stats()['node_count']} entities, "
      f"{subgraph.stats()['edge_count']} exposures")
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
