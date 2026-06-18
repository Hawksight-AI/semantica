---
title: "Knowledge Graph Module"
description: "Graph construction, temporal models, analytics, similarity scoring, and structural embeddings."
icon: "diagram-project"
---

`semantica.kg` transforms extracted entities and relationships into structured, queryable knowledge graphs:

- Temporal nodes and edges with `valid_from` / `valid_until` windows and all 13 Allen interval relations
- Full graph analytics suite: centrality, community detection, path finding, link prediction
- Node2Vec structural embeddings for downstream ML and similarity scoring
- OWL-Time export and versioned snapshots via `TemporalVersionManager`
- Schema and constraint validation before persistence


## Exported Classes

| Class | Role |
| :--- | :--- |
| `KnowledgeGraph` | Core graph data structure: nodes, edges, properties, temporal validity |
| `GraphBuilder` | Construct from entities + relationships; pass `merge_entities=True` to enable deduplication |
| `GraphBuilderWithProvenance` | Wraps `GraphBuilder` with optional provenance tracking; pass `provenance=True` to enable |
| `EntityResolver` | Entity deduplication and merging during graph construction |
| `GraphAnalyzer` | Unified analytics wrapper: runs centrality, community detection, and connectivity in one call |
| `ConnectivityAnalyzer` | Connected component detection, bridge identification, density, and degree statistics |
| `TemporalGraphQuery` | Point-in-time snapshots, range queries, evolution analysis, temporal path finding |
| `TemporalPatternDetector` | Sequence and cycle pattern detection over temporal edges |
| `TemporalReasoningEngine` | All 13 Allen interval algebra relations over `TemporalInterval` objects |
| `TemporalInterval` | Frozen dataclass `(start: datetime, end: datetime \| TemporalBound, label?)` |
| `IntervalRelation` | Enum of all 13 Allen relation labels (`BEFORE`, `AFTER`, `MEETS`, …) |
| `BiTemporalFact` | Dataclass wrapping `valid_from`, `valid_until`, `recorded_at`, `superseded_at`. Factory: `BiTemporalFact.from_relationship(rel_dict)` |
| `TemporalBound` | Sentinel enum for open-ended intervals — single value: `TemporalBound.OPEN` |
| `TemporalNormalizer` | Parse NL temporal expressions to `(datetime, datetime)` tuples — zero LLM calls |
| `TemporalQueryRewriter` | Extract temporal intent from free-text queries; returns `TemporalQueryResult` |
| `TemporalQueryResult` | Dataclass output of `TemporalQueryRewriter.rewrite()` |
| `TemporalVersionManager` | Versioned snapshots with SHA-256 integrity, SQLite-backed persistent storage |
| `CentralityCalculator` | PageRank, degree, betweenness, closeness, eigenvector centrality |
| `CommunityDetector` | Louvain, Leiden, Label Propagation, and K-Clique community detection |
| `PathFinder` | Dijkstra, A*, BFS, and K-Shortest path algorithms |
| `LinkPredictor` | Preferential Attachment, Jaccard, Adamic-Adar link prediction |
| `NodeEmbedder` | Node2Vec structural embeddings for downstream ML |
| `SimilarityCalculator` | Cosine, Euclidean, Manhattan, and correlation similarity scoring |
| `GraphValidator` | Schema and constraint validation before persistence |
| `AlgorithmTrackerWithProvenance` | Algorithm execution tracking with provenance metadata |
| `AlgorithmRegistry` / `algorithm_registry` | Registry for registered algorithms; `algorithm_registry` is the shared singleton |
| `ProvenanceTracker` | W3C PROV-O provenance tracking for graph operations |
| `SeedManager` | Reproducible random seed management across algorithms |
| `KGConfig` / `kg_config` | Module-level configuration; `kg_config` is the shared singleton |


<Tip>
  For conflict detection and advanced entity resolution, use `semantica.conflicts` and `semantica.deduplication` alongside this module.
</Tip>

<img src="/assets/img/diagrams/kg-structure.svg" alt="Knowledge graph entity and relation structure: Person, Organization, Location, Date nodes with typed labeled edges" style={{ width: '100%', borderRadius: '12px', margin: '0 0 24px' }} />

## GraphBuilder

**`GraphBuilder`** constructs knowledge graphs from extracted entities and relationships. `merge_entities` defaults to `False`: pass **`True`** to enable entity deduplication during construction:

```python
from semantica.kg import GraphBuilder

# Pass a dict with "entities" and "relationships" keys
builder = GraphBuilder(merge_entities=True)
kg = builder.build({"entities": entities, "relationships": relationships})
```

| Method | Returns | Description |
| :------ | :------- | :----------- |
| `build(sources)` | `dict` | Build graph from a dict, list of dicts, or list of entity/relation objects |
| `build_single_source(data)` | `dict` | Build graph from a single data source dict |


## Temporal Knowledge Graphs (v0.4.0+)

<Info>
  Full temporal reference including `BiTemporalFact`, `TemporalReasoningEngine`, Allen interval algebra, and `TemporalNormalizer` is covered in the dedicated [Temporal Intelligence](temporal) page. This section documents the KG-layer temporal API.
</Info>

The temporal stack — see the [Temporal Intelligence](temporal) page for the full reference.

### Building a Temporal Graph

```python
from semantica.kg import GraphBuilder, TemporalGraphQuery, TemporalVersionManager

builder = GraphBuilder()
kg = builder.build(sources=[
    {
        "entities": [
            {"id": "alice",     "type": "Person"},
            {"id": "acme_corp", "type": "Organization"},
            {"id": "beta_ltd",  "type": "Organization"},
        ],
        "relationships": [
            {
                "source": "alice", "target": "acme_corp", "type": "ceo_of",
                "valid_from":  "2018-01-01",
                "valid_until": "2022-06-01",
            },
            {
                "source": "alice", "target": "beta_ltd", "type": "ceo_of",
                "valid_from":  "2022-06-01",
                # No valid_until → open-ended (TemporalBound.OPEN)
            },
        ],
    }
])
```

### Point-in-Time Queries

`TemporalGraphQuery` accepts optional constructor args; pass the graph into each query call:

```python
from semantica.kg import TemporalGraphQuery

query = TemporalGraphQuery(
    temporal_granularity="day",        # second|minute|hour|day|week|month|year
    enable_temporal_reasoning=True,
)

# Primary API: query_at_time returns counts + filtered data
result_2020 = query.query_at_time(kg, "", at_time="2020-06-15")
result_2023 = query.query_at_time(kg, "", at_time="2023-01-01")
print(f"Rels in 2020: {result_2020['num_relationships']}")

# Low-level: reconstruct_at_time returns a deep-copied subgraph dict
snapshot = query.reconstruct_at_time(kg, "2020-06-15")

# Range query: all relationships active during any part of 2021
range_result = query.query_time_range(kg, "", "2021-01-01", "2021-12-31")

# Compare two snapshots: use TemporalVersionManager.compare_versions()
# (temporal_diff() does not exist — see TemporalVersionManager below)
```

### Bi-Temporal Facts

`BiTemporalFact` is a **dataclass** — use the `from_relationship()` factory, not a positional constructor:

```python
from semantica.kg import BiTemporalFact, TemporalBound

rel = {
    "source": "alice", "target": "acme_corp", "type": "ceo_of",
    "valid_from":    "2018-01-01",
    "valid_until":   "2022-06-01",
    "recorded_at":   "2018-01-05T09:32:00Z",
    "superseded_at": None,   # None → TemporalBound.OPEN (still current)
}
fact = BiTemporalFact.from_relationship(rel)

print(fact.valid_from)      # datetime(2018, 1, 1, tzinfo=utc)
print(fact.valid_until)     # datetime(2022, 6, 1, tzinfo=utc)
print(fact.superseded_at)   # TemporalBound.OPEN

# Open-ended fact (no valid_until → TemporalBound.OPEN)
open_rel = {"source": "alice", "target": "beta_ltd", "type": "ceo_of",
            "valid_from": "2022-06-01"}
open_fact = BiTemporalFact.from_relationship(open_rel)
print(open_fact.valid_until)   # TemporalBound.OPEN

# Serialize back to dict fields for storage
fields = fact.to_relationship_fields()
```

### Allen Interval Algebra

`TemporalReasoningEngine` implements **all 13 Allen relations** deterministically — no LLM, no probability. It operates on `TemporalInterval` objects (not plain dicts):

```python
from semantica.kg import (
    TemporalReasoningEngine, TemporalInterval, IntervalRelation
)
from datetime import datetime, timezone

def dt(y, m, d): return datetime(y, m, d, tzinfo=timezone.utc)

engine = TemporalReasoningEngine()

h1_2020 = TemporalInterval(start=dt(2020, 1, 1), end=dt(2020, 6, 30))
q2_q4   = TemporalInterval(start=dt(2020, 4, 1), end=dt(2020, 12, 31))

relation = engine.relation(h1_2020, q2_q4)   # primary method
print(relation)          # IntervalRelation.OVERLAPS
print(relation.value)    # "overlaps"

print(engine.overlaps(h1_2020, q2_q4))  # True
print(engine.contains(q2_q4, h1_2020))  # False
print(engine.active_at(h1_2020, dt(2020, 3, 15)))  # True
```

| `IntervalRelation` | `.value` | Description |
| :--- | :--- | :--- |
| `BEFORE` | `"before"` | A ends strictly before B starts |
| `MEETS` | `"meets"` | A ends exactly when B starts |
| `OVERLAPS` | `"overlaps"` | A and B share a period; A starts and ends first |
| `STARTS` | `"starts"` | Same start; A ends before B |
| `DURING` | `"during"` | A is entirely within B |
| `FINISHES` | `"finishes"` | Same end; B started earlier |
| `EQUALS` | `"equals"` | Identical interval |
| `AFTER`, `MET_BY`, `OVERLAPPED_BY`, `STARTED_BY`, `CONTAINS`, `FINISHED_BY` | *(inverses)* | Mirror relations |

### Natural Language Temporal Parsing

```python
from semantica.kg import TemporalNormalizer, TemporalQueryRewriter
from datetime import datetime, timezone

# reference_date set at construction time (required for relative phrases)
norm = TemporalNormalizer(reference_date=datetime(2024, 6, 15, tzinfo=timezone.utc))

# Returns Optional[Tuple[datetime, datetime]] — not a dict
result = norm.normalize("last quarter")
start, end = result
print(start)   # datetime(2024, 1, 1, tzinfo=utc)
print(end)     # datetime(2024, 3, 31, tzinfo=utc)

result = norm.normalize("2022")
# (datetime(2022, 1, 1, tzinfo=utc), datetime(2022, 12, 31, tzinfo=utc))

result = norm.normalize("unparseable phrase")
print(result)  # None

# TemporalQueryRewriter: primary method is rewrite(), returns TemporalQueryResult
rewriter = TemporalQueryRewriter()
result = rewriter.rewrite("Who was CEO before the 2022 restructuring?")
print(result.temporal_intent)    # "before"
print(result.at_time.year)       # 2022
print(result.rewritten_query)    # "Who was CEO"
print(result.confidence)         # 0.85
print(result.has_temporal_context())  # True
```

### Versioned Snapshots

```python
from semantica.kg import TemporalVersionManager

# In-memory (default); pass storage_path="versions.db" for SQLite persistence
versioner = TemporalVersionManager()

# author and description are required for create_snapshot
versioner.create_snapshot(kg, version_label="2024-Q1",
                          author="user@example.com",
                          description="Q1 2024 baseline")

# List versions (not list_snapshots)
for v in versioner.list_versions():
    print(f"{v['label']:12s}  {v['author']}")

# Compare two versions (not diff_versions)
diff = versioner.compare_versions("2023-Q4", "2024-Q1")
print(f"Entities added:      {diff['summary']['entities_added']}")
print(f"Relationships added: {diff['summary']['relationships_added']}")

# Retrieve a version (not restore_snapshot)
past_kg = versioner.get_version("2023-Q4")

# SHA-256 integrity check
versioner.verify_checksum(past_kg)
```

<Tip>
  See the [Temporal Intelligence](temporal) reference for the full class API, domain examples (personnel changes, policy evolution, financial timelines), and configuration options.
</Tip>


## Similarity Scoring

`SimilarityCalculator` computes cosine, Euclidean, Manhattan, and correlation similarity between node embeddings:

```python
from semantica.kg import SimilarityCalculator, NodeEmbedder

# First compute structural embeddings
embedder   = NodeEmbedder(method="node2vec", embedding_dimension=128)
embeddings = embedder.compute_embeddings(kg, ["Person", "Organization"], ["RELATED_TO"])

# Then compare nodes by embedding similarity
calc  = SimilarityCalculator()
score = calc.cosine_similarity(embeddings["Apple Inc."], embeddings["Google"])
print(f"Apple–Google structural similarity: {score:.3f}")

# Find structurally similar nodes: returns List[str] of node IDs
similar = embedder.find_similar_nodes(kg, "Apple Inc.", top_k=5)
for node_id in similar:
    print(node_id)
```


## Graph Analytics

<Tabs>
  <Tab title="Centrality">
    Measure node importance across five algorithms. Use `calculate_all_centrality()` to run them all at once.

    ```python
    from semantica.kg import CentralityCalculator

    calculator = CentralityCalculator()

    # Run all centrality measures at once
    all_metrics = calculator.calculate_all_centrality(graph)

    # Or run individually
    pagerank    = calculator.calculate_pagerank(graph, damping_factor=0.85)
    betweenness = calculator.calculate_betweenness_centrality(graph)
    closeness   = calculator.calculate_closeness_centrality(graph)

    # Get the top 10 most important nodes
    top_nodes = calculator.get_top_nodes(pagerank, top_k=10)
    ```

    | Method | Best for |
    | :------ | :-------- |
    | `calculate_degree_centrality()` | Most-connected nodes |
    | `calculate_pagerank()` | Link-based influence (like Google PageRank) |
    | `calculate_betweenness_centrality()` | Bottleneck / bridge nodes |
    | `calculate_closeness_centrality()` | Nodes closest to all others |
    | `calculate_eigenvector_centrality()` | Nodes connected to other high-influence nodes |
  </Tab>
  <Tab title="Community Detection">
    Discover clusters and communities within the graph. Louvain is the fastest; Leiden produces higher-quality partitions.

    ```python
    from semantica.kg import CommunityDetector

    detector = CommunityDetector()

    # Louvain: fast, high quality (default)
    communities = detector.detect_communities(graph, algorithm="louvain")

    # Leiden: higher quality, slower
    communities = detector.detect_communities_leiden(graph, resolution=1.2)

    # Evaluate community quality
    metrics = detector.calculate_community_metrics(graph, communities)
    print(f"Modularity: {metrics['modularity']:.3f}")
    print(f"Communities found: {metrics['num_communities']}")
    ```

    | Algorithm | Strength |
    | :--------- | :-------- |
    | Louvain | Fast, good modularity: use for large graphs |
    | Leiden | Best modularity: use when quality matters more than speed |
    | Label Propagation | Near-linear time: use for very large graphs |
    | K-Clique | Overlapping communities: nodes can belong to multiple groups |
  </Tab>
  <Tab title="Path Finding">
    Find shortest paths and route alternatives between any two nodes.

    ```python
    from semantica.kg import PathFinder

    finder = PathFinder()

    # Dijkstra shortest path
    path = finder.dijkstra_shortest_path(graph, "Alice", "Bob")
    print(" → ".join(path["path"]))

    # All shortest paths between two nodes
    paths = finder.all_shortest_paths(graph, "source", "target")

    # K-Shortest paths (alternative routes)
    k_paths = finder.find_k_shortest_paths(graph, "source", "target", k=3)
    ```

    | Algorithm | Use case |
    | :--------- | :-------- |
    | Dijkstra | Weighted shortest path: standard routing |
    | A\* | Heuristic-guided search: faster on large sparse graphs |
    | BFS | Unweighted shortest path: hop count only |
    | K-Shortest | Multiple alternative routes |
  </Tab>
  <Tab title="Link Prediction">
    Predict missing or future edges. Use to complete knowledge graphs or find implicit relationships.

    ```python
    from semantica.kg import LinkPredictor

    predictor = LinkPredictor(method="preferential_attachment")

    # Predict the top 20 most likely missing edges
    predicted = predictor.predict_links(graph, top_k=20)
    for link in predicted:
        print(f"{link['source']} → {link['target']}  (score: {link['score']:.3f})")

    # Score a specific pair
    score = predictor.score_link(graph, "Alice", "CompanyX")
    ```

    | Algorithm | Best for |
    | :--------- | :-------- |
    | Preferential Attachment | High-degree node connection prediction |
    | Common Neighbors | Nodes with shared connections |
    | Jaccard | Normalized common-neighbor overlap |
    | Adamic-Adar | Weighted common neighbors (penalizes hubs) |
    | Resource Allocation | Conservative: ignores high-degree intermediaries |
  </Tab>
  <Tab title="Node Embeddings">
    Compute structural embeddings with Node2Vec, then find similar nodes or feed into downstream ML.

    ```python
    from semantica.kg import NodeEmbedder, SimilarityCalculator

    # Compute Node2Vec embeddings
    embedder = NodeEmbedder(method="node2vec", embedding_dimension=128)
    embeddings = embedder.compute_embeddings(
        graph, ["Person", "Organization"], ["RELATED_TO"]
    )

    # Find structurally similar nodes
    similar = embedder.find_similar_nodes(graph, "Apple Inc.", top_k=5)
    for node_id in similar:
        print(node_id)

    # Compare two specific nodes by embedding similarity
    calc  = SimilarityCalculator()
    score = calc.cosine_similarity(embeddings["Apple Inc."], embeddings["Google"])
    print(f"Structural similarity: {score:.3f}")
    ```

    <Note>
      `find_similar_nodes` returns `List[str]`: a list of node IDs, not node objects. Look up full node data via `graph["nodes"]`.
    </Note>
  </Tab>
</Tabs>


## Algorithm Summary

| Category | Algorithms | Use Cases |
| :-------- | :---------- | :--------- |
| Node Embeddings | Node2Vec | Structural similarity, node representation |
| Similarity | Cosine, Euclidean, Manhattan, Correlation | Node matching, recommendation |
| Path Finding | Dijkstra, A\*, BFS, K-Shortest | Route planning, network analysis |
| Link Prediction | Preferential Attachment, Jaccard, Adamic-Adar | Network completion |
| Centrality | Degree, Betweenness, Closeness, PageRank | Influence analysis |
| Community Detection | Louvain, Leiden, Label Propagation | Social clustering |
| Connectivity | Components, Bridges, Density | Network robustness |


## GraphValidator

Validates graph structure: checks required fields, duplicate IDs, dangling edges, and optionally detects cycles and orphan nodes:

```python
from semantica.kg import GraphValidator

validator = GraphValidator()
result    = validator.validate(kg)   # accepts the dict returned by GraphBuilder.build()

if result.is_valid:
    print("Graph is valid")
else:
    for issue in result.issues:
        print(f"{issue.severity.value}: {issue.message}")
```

Pass `strict=True` to treat warnings as errors. Pass a `schema` dict with `"entity_types"` and `"relationship_types"` keys to validate against a known type vocabulary.

## Configuration

```yaml
kg:
  resolution:
    threshold: 0.9
    strategy: semantic

  temporal:
    enabled: true
    default_validity: infinite
```

- [Graph Store](graph_store) — Persist graphs in Neo4j, FalkorDB, or Apache AGE.
- [Semantic Extract](semantic_extract) — Source of entities and relationships fed to GraphBuilder.
- [Visualization](visualization) — Visualize knowledge graphs interactively.
- [Conflicts](conflicts) — Conflict detection and resolution.

### Cookbooks

- [Building Knowledge Graphs](https://github.com/semantica-agi/semantica/blob/main/cookbook/introduction/07_Building_Knowledge_Graphs.ipynb): fundamentals of KG construction · Beginner
- [Your First Knowledge Graph](https://github.com/semantica-agi/semantica/blob/main/cookbook/introduction/08_Your_First_Knowledge_Graph.ipynb): entity extraction to visualization · Beginner
- [Graph Analytics](https://github.com/semantica-agi/semantica/blob/main/cookbook/introduction/10_Graph_Analytics.ipynb): centrality and community detection · Intermediate
- [Advanced Graph Analytics](https://github.com/semantica-agi/semantica/blob/main/cookbook/advanced/02_Advanced_Graph_Analytics.ipynb): PageRank, Louvain, shortest path · Advanced
- [Temporal Knowledge Graphs](https://github.com/semantica-agi/semantica/blob/main/cookbook/advanced/10_Temporal_Knowledge_Graphs.ipynb): temporal logic and graph evolution · Advanced
