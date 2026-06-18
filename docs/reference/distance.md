---
title: "Distance Intelligence"
description: "Semantic neighborhoods, N×N distance matrices, ego-mode exploration, proximity-blended retrieval, and embedding cache optimization."
icon: "radar"
---

Distance Intelligence gives every node in your knowledge graph a **semantic neighborhood** — making it possible to answer not just "is A connected to B?" but "how semantically close is A to B, and what lies in between?"

Introduced in **v0.5.0**, Distance Intelligence operates across three layers:

<div style={{display:"flex",flexWrap:"wrap",gap:"1.5rem",margin:"1.5rem 0"}}>
  <div style={{flex:"1 1 200px",padding:"1.25rem 1.5rem",borderRadius:"10px",border:"1px solid rgba(16,185,129,0.25)",background:"rgba(16,185,129,0.04)"}}>
    <div style={{fontSize:"1.1rem",fontWeight:700,color:"#10B981",marginBottom:"6px"}}>Distance Matrices</div>
    <div style={{fontSize:"0.82rem",color:"rgba(255,255,255,0.6)",lineHeight:1.5}}>N×N upper-triangle semantic distance between any node set</div>
  </div>
  <div style={{flex:"1 1 200px",padding:"1.25rem 1.5rem",borderRadius:"10px",border:"1px solid rgba(16,185,129,0.25)",background:"rgba(16,185,129,0.04)"}}>
    <div style={{fontSize:"1.1rem",fontWeight:700,color:"#10B981",marginBottom:"6px"}}>Semantic Neighborhoods</div>
    <div style={{fontSize:"0.82rem",color:"rgba(255,255,255,0.6)",lineHeight:1.5}}>BFS ego-graphs with confidence decay and distance band classification</div>
  </div>
  <div style={{flex:"1 1 200px",padding:"1.25rem 1.5rem",borderRadius:"10px",border:"1px solid rgba(16,185,129,0.25)",background:"rgba(16,185,129,0.04)"}}>
    <div style={{fontSize:"1.1rem",fontWeight:700,color:"#10B981",marginBottom:"6px"}}>Proximity Blending</div>
    <div style={{fontSize:"0.82rem",color:"rgba(255,255,255,0.6)",lineHeight:1.5}}>Combine semantic similarity with graph proximity in retrieval</div>
  </div>
  <div style={{flex:"1 1 200px",padding:"1.25rem 1.5rem",borderRadius:"10px",border:"1px solid rgba(16,185,129,0.25)",background:"rgba(16,185,129,0.04)"}}>
    <div style={{fontSize:"1.1rem",fontWeight:700,color:"#10B981",marginBottom:"6px"}}>10× Cache</div>
    <div style={{fontSize:"0.82rem",color:"rgba(255,255,255,0.6)",lineHeight:1.5}}>Graph revision–based embedding cache avoids redundant re-computation</div>
  </div>
</div>


## Distance Bands

Every neighbor result is classified into one of four distance bands based on hop count and semantic similarity:

| Band | Hop count | Meaning | Explorer color |
| :---- | :-------- | :------- | :------------- |
| `direct` | 1 | Immediate neighbor — strong semantic overlap | Green |
| `near` | 2 | One-hop away — closely related concept | Teal |
| `mid-range` | 3–4 | Conceptually related but some separation | Yellow |
| `distant` | 5+ | Weak structural connection | Red |

Distance bands flow through the entire system: retrieval results, path responses, API endpoints, and the Explorer Ego Mode visualization all use the same four-tier classification.


## Quick Start

<Steps>
  <Step title="Get neighbors with distance metadata">
    The simplest entry point: call `get_neighbors()` with `include_distance_metadata=True`:

    ```python
    from semantica.context import ContextGraph

    graph = ContextGraph(advanced_analytics=True)

    graph.add_node("python",   "language",   properties={"paradigm": "multi"})
    graph.add_node("fastapi",  "framework",  properties={"language": "Python"})
    graph.add_node("django",   "framework",  properties={"language": "Python"})
    graph.add_node("sqlmodel", "library",    properties={"orm": True})

    graph.add_edge("python",   "fastapi",  "enables")
    graph.add_edge("python",   "django",   "enables")
    graph.add_edge("fastapi",  "sqlmodel", "uses")

    neighbors = graph.get_neighbors(
        "python",
        hops=3,
        include_distance_metadata=True,
    )

    for n in neighbors:
        print(f"{n['node_id']:12s}  band={n['distance_band']:10s}  "
              f"decay={n['confidence_decay']:.3f}  "
              f"path={n['path_to_anchor']}")
    ```
    ```
    fastapi       band=direct     decay=1.000  path=['python', 'fastapi']
    django        band=direct     decay=1.000  path=['python', 'django']
    sqlmodel      band=near       decay=0.750  path=['python', 'fastapi', 'sqlmodel']
    ```
  </Step>
  <Step title="Compute a semantic distance matrix">
    ```python
    from semantica.kg import SimilarityCalculator, NodeEmbedder

    # Generate structural embeddings first
    embedder   = NodeEmbedder(method="node2vec", embedding_dimension=128)
    embeddings = embedder.compute_embeddings(kg, ["language", "framework", "library"], ["enables", "uses"])

    # N×N upper-triangle distance matrix
    calc   = SimilarityCalculator()
    matrix = calc.compute_distance_matrix(embeddings)

    # matrix["distances"] is an upper-triangle dict: {(node_a, node_b): distance}
    for (a, b), dist in sorted(matrix["distances"].items(), key=lambda x: x[1]):
        print(f"{a:15s} ↔ {b:15s}  distance={dist:.4f}")
    ```
  </Step>
  <Step title="Blend proximity into retrieval">
    Set `proximity_weight` on `AgentContext` to blend graph proximity into every semantic retrieval call:

    ```python
    from semantica.context import AgentContext, ContextGraph
    from semantica.vector_store import VectorStore

    context = AgentContext(
        vector_store=VectorStore(backend="faiss", dimension=768),
        knowledge_graph=ContextGraph(advanced_analytics=True),
        decision_tracking=True,
        proximity_weight=0.3,   # combined = 0.7×semantic + 0.3×proximity
    )

    # retrieve() and find_precedents() both use the blended score
    results = context.retrieve("web API frameworks", max_results=10)
    for r in results:
        print(f"[{r['combined_score']:.3f}]  semantic={r['semantic_score']:.3f}  "
              f"proximity={r['proximity_score']:.3f}  {r['content'][:60]}")
    ```
  </Step>
</Steps>


## ContextGraph Distance API

### `get_neighbors()`

Returns BFS neighbors enriched with distance metadata when `include_distance_metadata=True`:

```python
neighbors = graph.get_neighbors(
    node_id="python",
    hops=4,
    include_distance_metadata=True,
    min_weight=0.3,               # exclude low-confidence edges
)
```

| Field | Type | Description |
| :---- | :---- | :----------- |
| `node_id` | `str` | Node identifier |
| `node_type` | `str` | Node type label |
| `properties` | `Dict` | Node property dict |
| `hop_count` | `int` | BFS hops from anchor |
| `distance_band` | `str` | `"direct"` / `"near"` / `"mid-range"` / `"distant"` |
| `confidence_decay` | `float` | Confidence score after hop-based decay: `weight^hop_count` |
| `path_to_anchor` | `List[str]` | Shortest path from anchor to this node |
| `edge_weight` | `float` | Weight of the direct edge (if hop=1) |

### `get_neighbor_distances()`

Returns a sorted list of neighbors ranked by combined confidence-decay distance score:

```python
distances = graph.get_neighbor_distances("fastapi", hops=3)

for d in distances:
    print(f"{d['node_id']:15s}  score={d['combined_distance_score']:.4f}  "
          f"band={d['distance_band']}")
```


## SimilarityCalculator — Pairwise Similarity

`SimilarityCalculator` computes similarity between node embeddings using four metrics.

```python
from semantica.kg import SimilarityCalculator

calc = SimilarityCalculator(method="cosine", normalize=True)
# method: "cosine" | "euclidean" | "manhattan" | "correlation"
```

### Constructor

| Parameter | Type | Default | Description |
| :--------- | :---- | :------- | :----------- |
| `method` | `str` | `"cosine"` | Default metric: `"cosine"`, `"euclidean"`, `"manhattan"`, `"correlation"` |
| `normalize` | `bool` | `True` | Normalize vectors before calculation |

### Methods

| Method | Returns | Description |
| :------ | :------- | :----------- |
| `cosine_similarity(vector1, vector2)` | `float` | Cosine similarity `[-1, 1]` between two vectors |
| `euclidean_distance(embedding1, embedding2)` | `float` | L2 distance (non-negative) between two vectors |
| `manhattan_distance(embedding1, embedding2)` | `float` | L1 distance (non-negative) between two vectors |
| `correlation_similarity(embedding1, embedding2)` | `float` | Pearson correlation `[-1, 1]` between two vectors |
| `batch_similarity(embeddings, query_embedding, method=None, top_k=None, chunk_size=1000)` | `Dict[str, float]` | Similarity of all nodes against a query vector. Returns `{node_id: score}` |
| `pairwise_similarity(embeddings, method=None)` | `Dict[Tuple[str,str], float]` | Upper-triangle N×N pairwise similarity matrix for all node pairs |
| `find_most_similar(embeddings, query_embedding, top_k=10, method=None)` | `List[Tuple[str, float]]` | Top-k `(node_id, score)` pairs sorted by similarity |

### Pairwise Similarity Matrix

`pairwise_similarity()` returns the upper triangle of the N×N matrix — each key is a `(node_id_a, node_id_b)` tuple:

```python
from semantica.kg import NodeEmbedder, SimilarityCalculator

embedder   = NodeEmbedder(method="node2vec", embedding_dimension=128)
embeddings = embedder.compute_embeddings(kg, ["language", "framework"], ["enables", "uses"])

calc = SimilarityCalculator(method="cosine")

# N×N upper-triangle: Dict[(node_a, node_b), similarity_score]
matrix = calc.pairwise_similarity(embeddings)

# Sort by similarity (most similar first)
for (a, b), score in sorted(matrix.items(), key=lambda x: x[1], reverse=True)[:5]:
    print(f"{a:15s} ↔ {b:15s}  similarity={score:.4f}")

# Find most similar pair
best_pair = max(matrix.items(), key=lambda x: x[1])
print(f"Most similar: {best_pair[0]}  score={best_pair[1]:.4f}")

# Find most dissimilar pair
worst_pair = min(matrix.items(), key=lambda x: x[1])
print(f"Most distant:  {worst_pair[0]}  score={worst_pair[1]:.4f}")
```

<Note>
  The matrix is upper-triangle only — `(a, b)` is stored but `(b, a)` is not. To look up either direction: `matrix.get((a, b)) or matrix.get((b, a))`.
</Note>

### Batch Similarity

Efficiently compare a query vector against all nodes using chunked vectorized ops:

```python
# Query vector against all nodes
scores = calc.batch_similarity(
    embeddings,
    query_embedding=my_query_vec,
    method="cosine",    # override default
    top_k=10,           # return only top 10 (None = all)
    chunk_size=1000,    # chunk size for memory efficiency
)

for node_id, score in sorted(scores.items(), key=lambda x: x[1], reverse=True):
    print(f"{node_id:15s}  {score:.4f}")
```

### Find Most Similar

```python
# Top-k (node_id, score) tuples sorted descending
similar = calc.find_most_similar(
    embeddings,
    query_embedding=embeddings["python"],
    top_k=5,
    method="cosine",
)

for node_id, score in similar:
    print(f"{node_id:15s}  similarity={score:.4f}")
```

### Individual Metrics

```python
vec_a = embeddings["fastapi"]
vec_b = embeddings["django"]

cosine  = calc.cosine_similarity(vec_a, vec_b)
l2      = calc.euclidean_distance(vec_a, vec_b)
l1      = calc.manhattan_distance(vec_a, vec_b)
pearson = calc.correlation_similarity(vec_a, vec_b)

print(f"Cosine:      {cosine:.4f}")
print(f"Euclidean:   {l2:.4f}")
print(f"Manhattan:   {l1:.4f}")
print(f"Correlation: {pearson:.4f}")
```


## Proximity-Blended Retrieval

`AgentContext.retrieve()` and `find_precedents()` both support a `proximity_weight` parameter that blends graph proximity into the semantic similarity score:

```
combined_score = (1 − proximity_weight) × semantic_score
              + proximity_weight × proximity_score
```

Where `proximity_score` is derived from hop count and edge weights from the query anchor node.

```python
from semantica.context import AgentContext, ContextGraph
from semantica.vector_store import VectorStore

context = AgentContext(
    vector_store=VectorStore(backend="faiss", dimension=768),
    knowledge_graph=ContextGraph(advanced_analytics=True),
    proximity_weight=0.3,
)

# Standard retrieval — proximity blended automatically
results = context.retrieve("model deployment strategies", max_results=10)

# Override weight per-call
results = context.retrieve(
    "model deployment strategies",
    max_results=10,
    proximity_weight=0.5,   # stronger proximity weight for this query
)

# find_precedents also blends proximity
precedents = context.find_precedents(
    "infrastructure scaling decisions",
    proximity_weight=0.4,
    limit=5,
)

for p in precedents:
    print(f"[{p.combined_score:.3f}]  {p.outcome}  (confidence: {p.confidence:.2f})")
```


## Embedding Cache

The embedding cache avoids re-computing embeddings for nodes that haven't changed since the last call — delivering up to **10× throughput improvement** on large graphs.

### How It Works

Each `GraphSession` tracks a **graph revision hash** derived from the current node and edge state. When a distance matrix or neighborhood request arrives:

1. The revision hash is compared to the cached hash
2. If unchanged: the cached embeddings are returned directly
3. If changed (nodes/edges added or modified): the cache is invalidated and embeddings are recomputed

```python
from semantica.explorer import GraphSession

session = GraphSession(graph=kg)

# First call: computes embeddings, stores in cache
embeddings = session.get_cached_embeddings()

# Second call (graph unchanged): returns cache instantly
embeddings = session.get_cached_embeddings()

# After graph modification: cache is automatically invalidated
session.graph.add_node("new_node", "concept", properties={})
embeddings = session.get_cached_embeddings()  # recomputes
```

| Parameter | Type | Default | Description |
| :--------- | :---- | :------- | :----------- |
| `force_refresh` | `bool` | `False` | Force cache invalidation even if the graph is unchanged |
| Cache invalidation | Automatic | — | Triggered by `add_nodes()`, `add_edges()`, or any mutation |
| Cache scope | Per-session | — | Each `GraphSession` maintains its own independent cache |

<Tip>
  The cache is most effective in Explorer deployments where the same graph is queried repeatedly for distance matrices and ego-mode neighborhoods. In batch pipeline contexts, set `force_refresh=True` to ensure the latest graph state is always used.
</Tip>


## REST API Endpoints

Five new endpoints were added in v0.5.0 for programmatic distance intelligence access:

### `POST /api/graph/distance-matrix`

Compute N×N semantic distance matrix for a set of node IDs:

```bash
curl -X POST http://localhost:8000/api/graph/distance-matrix \
  -H "Content-Type: application/json" \
  -d '{
    "node_ids": ["alice", "bob", "acme_corp", "beta_ltd"],
    "embedding_model": "all-MiniLM-L6-v2",
    "include_band_classification": true
  }'
```

```json
{
  "matrix": {
    "alice,bob": 0.312,
    "alice,acme_corp": 0.087,
    "alice,beta_ltd": 0.154,
    "bob,acme_corp": 0.401,
    "bob,beta_ltd": 0.233,
    "acme_corp,beta_ltd": 0.198
  },
  "most_similar": ["alice", "acme_corp"],
  "most_distant": ["bob", "acme_corp"],
  "mean_distance": 0.231
}
```

### `GET /api/graph/node/{id}/semantic-neighborhood`

Retrieve the ego-graph (BFS neighborhood) of a node with distance metadata:

```bash
curl "http://localhost:8000/api/graph/node/alice/semantic-neighborhood?depth=3&include_distance_metadata=true"
```

```json
{
  "anchor_node": "alice",
  "neighbors": [
    {"node_id": "acme_corp", "distance_band": "direct",   "confidence_decay": 1.0,  "hop_count": 1},
    {"node_id": "ceo_role",  "distance_band": "direct",   "confidence_decay": 1.0,  "hop_count": 1},
    {"node_id": "beta_ltd",  "distance_band": "near",     "confidence_decay": 0.75, "hop_count": 2},
    {"node_id": "london_hq", "distance_band": "mid-range","confidence_decay": 0.56, "hop_count": 3}
  ],
  "total_neighbors": 4,
  "depth": 3
}
```

### `GET /api/decisions/causal-distance`

Return causal distance (hop count through causal edges) between two decision nodes:

```bash
curl "http://localhost:8000/api/decisions/causal-distance?source=dec_001&target=dec_005"
```

```json
{
  "source": "dec_001",
  "target": "dec_005",
  "causal_hops": 3,
  "causal_path": ["dec_001", "dec_002", "dec_004", "dec_005"],
  "distance_band": "near"
}
```

### `GET /api/temporal/distance-history`

Track how the semantic distance between two nodes has evolved over time:

```bash
curl "http://localhost:8000/api/temporal/distance-history?node_a=alice&node_b=acme_corp&snapshots=2021-01-01,2022-01-01,2023-01-01"
```

```json
{
  "node_a": "alice",
  "node_b": "acme_corp",
  "history": [
    {"timestamp": "2021-01-01", "distance": 0.08, "band": "direct"},
    {"timestamp": "2022-01-01", "distance": 0.09, "band": "direct"},
    {"timestamp": "2023-01-01", "distance": 0.54, "band": "mid-range"}
  ]
}
```

### `POST /api/export/distance-enriched`

Export graph data enriched with distance metadata (CSV or JSONL, capped at 200 nodes):

```bash
curl -X POST http://localhost:8000/api/export/distance-enriched \
  -H "Content-Type: application/json" \
  -d '{"anchor_node": "alice", "depth": 4, "format": "csv"}'
```


## Explorer Distance Intelligence UI

The Knowledge Explorer embeds Distance Intelligence directly in the browser dashboard:

<AccordionGroup>

<Accordion title="Ego Mode" icon="circle-nodes">
  Ego Mode centers the visualization on a selected node and renders its semantic neighborhood with **BFS depth-of-field fading** — nodes further from the anchor become progressively dimmer, revealing the "shape" of conceptual proximity.

  - **Depth slider (1–8)**: controls the BFS radius of the neighborhood
  - **Confidence decay visualization**: edge opacity maps to `confidence_decay` score
  - **Distance band color coding**: green (direct) → teal (near) → yellow (mid-range) → red (distant)
  - **Bottleneck highlighting**: bridge nodes that connect otherwise separate clusters are highlighted in the path inspector

  Activate via the Explorer toolbar: **View → Ego Mode**, then click any node to set it as anchor.
</Accordion>

<Accordion title="Distance Heatmap" icon="table-cells">
  The heatmap renders an N×N distance matrix as a color-coded grid — instantly revealing which clusters of nodes are semantically cohesive and which are isolated.

  - **Color scale**: green (near, distance → 0) through yellow to red (distant, distance → 1)
  - **Hover**: shows exact distance value and distance band for each cell
  - **Sort options**: sort rows/columns by node type, community membership, or alphabetical

  Access via **View → Distance Heatmap** in the Explorer sidebar.
</Accordion>

<Accordion title="Semantic Overlay" icon="layer-group">
  Overlay semantic similarity on the standard force-directed graph layout without switching modes:

  - **Semantic overlay**: edge thickness scaled by semantic similarity score
  - **Structural overlay**: edge thickness scaled by graph centrality
  - Both overlays can be toggled independently

  Access via the **Overlay** toggle in the Explorer toolbar.
</Accordion>

<Accordion title="Path Inspector" icon="route">
  Click any two nodes to inspect the shortest path between them. The Path Inspector shows:

  - **Distance band chip**: classifies the overall path as direct / near / mid-range / distant
  - **Metric cards**: hop count, mean edge weight, path confidence decay
  - **Bottleneck node highlight**: the single node whose removal would disconnect the path
  - **Distance history**: timeline of how the distance between the two nodes has changed across graph snapshots

  Access via **right-click → Inspect Path** on any two selected nodes.
</Accordion>

</AccordionGroup>


## Real-World Patterns

<Tabs>
  <Tab title="Knowledge Cluster Discovery">
    Find semantically cohesive topic clusters in a large knowledge graph without running community detection:

    ```python
    from semantica.kg import NodeEmbedder, SimilarityCalculator

    embedder = NodeEmbedder(method="node2vec", embedding_dimension=128)
    embeddings = embedder.compute_embeddings(kg, node_types=["Concept", "Topic"])

    calc = SimilarityCalculator()

    # Cluster nodes where pairwise distance < 0.2
    clusters = calc.cluster_by_distance(embeddings, threshold=0.2)

    for i, cluster in enumerate(clusters):
        print(f"Cluster {i+1} ({len(cluster)} nodes): {cluster[:5]}")
    ```
  </Tab>
  <Tab title="Anomaly Detection">
    Flag nodes that are unexpectedly distant from their structural neighbors — potential data quality issues or genuine anomalies:

    ```python
    from semantica.context import ContextGraph
    from semantica.kg import NodeEmbedder, SimilarityCalculator

    graph   = ContextGraph(advanced_analytics=True)
    # ... build graph ...

    embedder = NodeEmbedder(method="node2vec", embedding_dimension=128)
    embeddings = embedder.compute_embeddings(graph._graph, ["entity"], ["RELATED_TO"])

    calc = SimilarityCalculator()

    for node_id in graph._graph.nodes():
        neighbors = graph.get_neighbors(node_id, hops=1, include_distance_metadata=True)
        for n in neighbors:
            # Node connected by edge but semantically very distant → anomaly candidate
            structural_dist = 1.0 - n["edge_weight"]
            semantic_dist   = calc.euclidean_distance(
                embeddings[node_id], embeddings[n["node_id"]]
            )
            if semantic_dist > 0.7 and structural_dist < 0.3:
                print(f"Anomaly: {node_id} → {n['node_id']}  "
                      f"(structural={structural_dist:.2f}, semantic={semantic_dist:.2f})")
    ```
  </Tab>
  <Tab title="Decision Consistency Audit">
    Verify that similar decisions (low semantic distance) reached similar outcomes — flag inconsistencies for review:

    ```python
    from semantica.context import AgentContext, ContextGraph
    from semantica.vector_store import VectorStore

    context = AgentContext(
        vector_store=VectorStore(backend="faiss", dimension=768),
        knowledge_graph=ContextGraph(advanced_analytics=True),
        decision_tracking=True,
        proximity_weight=0.4,
    )

    # ... populate with historical decisions ...

    # Find pairs of semantically close decisions with different outcomes
    all_decisions = context.query_decisions("", max_hops=0)
    for i, d1 in enumerate(all_decisions):
        for d2 in all_decisions[i+1:]:
            precedents = context.find_precedents(
                d1.scenario, limit=5, proximity_weight=0.4
            )
            for p in precedents:
                if p.source_decision_id == d2.decision_id:
                    if p.similarity_score > 0.85 and d1.outcome != d2.outcome:
                        print(f"INCONSISTENCY: {d1.scenario}")
                        print(f"  Decision A: {d1.outcome}  (confidence {d1.confidence:.2f})")
                        print(f"  Decision B: {d2.outcome}  (confidence {d2.confidence:.2f})")
                        print(f"  Similarity: {p.similarity_score:.3f}")
    ```
  </Tab>
</Tabs>


## Performance

| Operation | Without cache | With cache | Improvement |
| :--------- | :------------ | :--------- | :---------- |
| Distance matrix (118k nodes) | ~48s | ~4.8s | **10×** |
| Semantic neighborhood (depth 4) | ~2.1s | ~0.21s | **10×** |
| Node search (indexed) | 24 ms | 0.004 ms | **6,000×** |
| Semantic deduplication | baseline | — | **6.98×** (v2 algorithms) |

<Note>
  The 10× cache improvement applies when the graph is unchanged between requests. In write-heavy pipelines where nodes are added continuously, cache hit rates will be lower. Use `force_refresh=False` (default) for read-heavy Explorer usage and `force_refresh=True` for batch pipeline contexts.
</Note>

- [Context Module](context) — `ContextGraph.get_neighbors()` and proximity-blended retrieval.
- [Knowledge Graph Module](kg) — `NodeEmbedder`, `SimilarityCalculator`, and graph analytics.
- [Visualization](visualization) — Programmatic distance heatmaps and ego-mode graph renders.
- [Explorer](explorer) — Knowledge Explorer with built-in Distance Intelligence dashboard.

- [Distance Intelligence](https://github.com/semantica-agi/semantica/blob/main/cookbook/advanced/12_Distance_Intelligence.ipynb) — Semantic neighborhoods and distance matrices · Advanced
