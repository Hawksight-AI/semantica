---
title: "Context Module"
description: "Agent context graphs, decision tracking, causal chains, precedent search, policy enforcement, and multi-hop GraphRAG."
icon: "brain"
---

`semantica.context` is the memory and decision layer for AI agents:

- Stores facts with provenance and embedding-backed retrieval
- Records decisions as first-class graph objects with full causal chains
- Lets agents search their own history to stay consistent across runs
- Answers complex queries via multi-hop GraphRAG traversal
- Enforces versioned policies and tracks compliance exceptions


## Exported Classes

| Class | Role |
| :--- | :--- |
| `AgentContext` | Primary entry point: memory, retrieval, decisions, graph traversal, checkpoints |
| `ContextGraph` | In-memory knowledge graph with centrality, community detection, and decision tracking |
| `AgentMemory` | Vector-backed persistent memory: `store(text)`, `retrieve(query, max_results)` |
| `EntityLinker` | Link entity mentions to URIs; create typed edges between entity IDs |
| `ContextRetriever` | Hybrid vector + graph retrieval with min-score and graph expansion options |
| `DecisionRecorder` | Record decisions with embeddings, causal chains, and metadata |
| `PolicyEngine` | Policy management: `add_policy()`, `check_compliance()`, `get_applicable_policies()` |
| `CausalChainAnalyzer` | Trace how decisions influenced each other: `get_causal_chain(decision_id)` |


## What You Get

- **AgentContext** — Memory, decision tracking, and graph-backed retrieval behind one API
  - Conversation history and checkpoint diffing
  - Persist and restore full context state to disk
- **ContextGraph** — Thread-safe in-memory knowledge graph
  - PageRank, centrality, community detection, temporal validity
  - Cross-graph navigation and link traversal
- **AgentMemory** — Embedding-backed memory with retention policy
  - LRU eviction at configurable `max_memory_size`
  - Per-conversation history isolation
- **DecisionRecorder** — Records decisions with causal chains and confidence scores
  - Temporal validity windows (`valid_from` / `valid_until`)
  - Cross-system context capture on every decision
- **PolicyEngine** — Versioned policy storage in the knowledge graph
  - Compliance checking against recorded decisions
  - Policy exception tracking with approver audit trail
- **EntityLinker** — Maps entity text to stable URIs
  - Creates typed links between entity IDs
  - Prevents "Apple", "Apple Inc.", "AAPL" becoming separate nodes
- **ContextRetriever** — Fuses vector similarity, graph traversal, and agent memory
  - Richer context than pure vector search
  - Configurable `hybrid_alpha` and expansion hops
- **CausalChainAnalyzer** — Traces upstream causes and downstream effects of any decision
  - Explainability paths with relationship types
  - Configurable depth and direction


## Quick Start

<Steps>
  <Step title="Initialize the agent context">
    ```python
    from semantica.context import AgentContext, ContextGraph
    from semantica.vector_store import VectorStore

    context = AgentContext(
        vector_store=VectorStore(backend="faiss", dimension=768),
        knowledge_graph=ContextGraph(advanced_analytics=True),
        decision_tracking=True,
        retention_days=90,
        max_memories=50000,
    )
    ```
  </Step>
  <Step title="Store facts and retrieve by semantic similarity">
    ```python
    memory_id = context.store(
        "GPT-4 outperforms GPT-3.5 on reasoning benchmarks by 40%",
        metadata={"source": "openai_blog", "date": "2024-01"}
    )

    results = context.retrieve("LLM benchmark comparisons", max_results=5)
    for r in results:
        print("{} (score: {:.3f})".format(r["content"], r["score"]))
    ```
  </Step>
  <Step title="Record decisions with full provenance">
    ```python
    decision_id = context.record_decision(
        category="model_selection",
        scenario="Choose LLM for production reasoning pipeline",
        reasoning="GPT-4 benchmark advantage justifies 3x cost increase",
        outcome="selected_gpt4",
        confidence=0.91,
        entities=["gpt-4", "gpt-3.5"],
        decision_maker="pipeline_agent",
    )
    ```
  </Step>
  <Step title="Find precedents and trace causal chains">
    ```python
    # Search past decisions: prevents contradictory choices across runs
    precedents = context.find_precedents("model selection reasoning", limit=5)
    for p in precedents:
        print("[{}] {}  (confidence: {:.2f})".format(p.category, p.outcome, p.confidence))
        print("  Reasoning: {}".format(p.reasoning))

    # Trace downstream decisions influenced by this one
    chain = context.get_causal_chain(decision_id, direction="downstream", max_depth=5)
    print("Downstream decisions: {}".format(len(chain)))

    # Full explainability
    explanation = context.trace_decision_explainability(decision_id)
    print("Total connections: {}".format(explanation["total_connections"]))
    ```
  </Step>
</Steps>


## Usage Patterns

<Tabs>
  <Tab title="Vector Memory Only">
    Fastest setup: no knowledge graph. Best for agents that need semantic search over facts without graph traversal overhead.

    ```python
    from semantica.context import AgentContext
    from semantica.vector_store import VectorStore

    # Zero-graph setup: vector memory only
    context = AgentContext(
        vector_store=VectorStore(backend="faiss", dimension=768),
    )

    context.store("User prefers concise responses with code examples")
    context.store("Project uses Python 3.11 with FastAPI and PostgreSQL")

    results = context.retrieve("user coding preferences", max_results=5)
    for r in results:
        print("{:.3f}  {}".format(r["score"], r["content"]))
    ```

    <Check>
      Swap `backend="faiss"` to `backend="inmemory"` for zero-dependency local development.
    </Check>
  </Tab>
  <Tab title="Full Agent Context">
    Production setup: graph + decisions + analytics. Use when you need explainability and contradiction-free decision history.

    ```python
    from semantica.context import AgentContext, ContextGraph
    from semantica.vector_store import VectorStore

    context = AgentContext(
        vector_store=VectorStore(backend="faiss", dimension=768),
        knowledge_graph=ContextGraph(
            advanced_analytics=True,  # PageRank, centrality, community detection
            kg_algorithms=True,       # path-finding, link prediction
        ),
        decision_tracking=True,       # requires knowledge_graph
        retention_days=90,
        max_memories=50000,
    )

    decision_id = context.record_decision(
        category="model_selection",
        scenario="Choose LLM for production reasoning pipeline",
        reasoning="GPT-4 benchmark advantage justifies 3x cost",
        outcome="selected_gpt4",
        confidence=0.91,
        entities=["gpt-4", "gpt-3.5"],
    )

    # Prevent contradictions across runs
    precedents = context.find_precedents("model selection", limit=5)
    ```

  </Tab>
  <Tab title="GraphRAG Query">
    Load a pre-built knowledge graph and answer complex questions with multi-hop graph traversal.

    ```python
    from semantica.context import AgentContext, ContextGraph
    from semantica.vector_store import VectorStore

    context = AgentContext(
        vector_store=VectorStore(backend="faiss", dimension=768),
        knowledge_graph=ContextGraph(advanced_analytics=True),
        hybrid_alpha=0.4,        # 0.0 = pure vector  →  1.0 = pure graph
        max_expansion_hops=3,
    )

    # Load a pre-built knowledge graph
    context.load_graph("company_kg.json")

    # Multi-hop GraphRAG retrieval
    results = context.retrieve(
        "companies founded by Apple alumni",
        use_graph=True,
        max_results=10,
    )
    for r in results:
        print("[{:.3f}] {}".format(r["score"], r["content"]))
    ```

    <Tip>
      Increase `max_expansion_hops` for deeper traversal at the cost of latency. Start at 2 and tune upward.
    </Tip>
  </Tab>
  <Tab title="Policy Enforcement">
    Add versioned compliance policies and gate every decision against them before recording.

    ```python
    from semantica.context import AgentContext, ContextGraph, PolicyEngine
    from semantica.vector_store import VectorStore

    context = AgentContext(
        vector_store=VectorStore(backend="faiss", dimension=768),
        knowledge_graph=ContextGraph(),
        decision_tracking=True,
    )

    engine = PolicyEngine(knowledge_graph=context.knowledge_graph)

    engine.add_policy(
        name="data_privacy",
        description="No PII stored without user consent flag",
        version="1.2",
        effective_date="2024-01-01",
        category="privacy",
        rules={"requires_consent": True, "max_retention_days": 90},
    )

    decision_data = {"action": "store_user_email", "user_consent": True}
    result = engine.check_compliance(decision_data, policy_names=["data_privacy"])

    if result["compliant"]:
        context.record_decision(
            category="data_storage",
            scenario="Store user profile",
            outcome="stored",
            confidence=1.0,
        )
    else:
        print("Blocked by policy:", result["violations"])
    ```
  </Tab>
</Tabs>


## AgentContext

**`AgentContext`** is the main entry point. Wraps memory, graph, and decision tracking behind a **single unified API**.

### Constructor Parameters

| Parameter | Type | Default | Description |
| :--------- | :---- | :------- | :----------- |
| `vector_store` | `VectorStore` | **required** | Backend for embedding-based memory retrieval |
| `knowledge_graph` | `ContextGraph` | `None` | Enables graph-backed relationships and GraphRAG |
| `decision_tracking` | `bool` | `False` | Activates `DecisionRecorder`: requires `knowledge_graph` to also be set |
| `retention_days` | `Optional[int]` | `30` | Auto-expire memories older than N days; `None` = keep forever |
| `max_memories` | `int` | `10000` | Hard cap before LRU eviction |
| `graph_expansion` | `bool` | `True` | Auto-expands graph from stored memories |
| `max_expansion_hops` | `int` | `2` | Max hops for graph expansion during retrieval |
| `hybrid_alpha` | `float` | `0.5` | Balance between vector (`0.0`) and graph (`1.0`) retrieval |
| `advanced_analytics` | `bool` | `True` | Enables PageRank, centrality, and community analysis |
| `kg_algorithms` | `bool` | `True` | Adds path-finding and link prediction |

<Tip>
  **Set `retention_days` to avoid memory bloat.** The default of `30` prunes automatically. Compliance-critical agents may need `retention_days=None` with explicit archival via `export()`.
</Tip>

<Tip>
  **Persist your context between runs.** `VectorStore` does not auto-persist — passing `index_path=` to its constructor is a no-op. Call `context.save("agent_state/")` to write memory, the vector index, and the graph to disk, and `context.load("agent_state/")` on the next process to restore them. See the "Persist & Restore" tab under [Real-World Patterns](#real-world-patterns) below.
</Tip>

### Memory Methods

| Method | Returns | Description |
| :------ | :------- | :----------- |
| `store(content, metadata, conversation_id, user_id)` | `str` or `Dict` | Store a fact (str → memory ID) or list of documents (list → stats dict) |
| `batch_store(items)` | `List[str]` | Store multiple items at once: returns list of memory IDs |
| `retrieve(query, max_results, min_score, use_graph, conversation_id)` | `List[Dict]` | Semantic retrieval; auto-selects GraphRAG if `knowledge_graph` is set |
| `forget(memory_id, conversation_id, days_old)` | `int` | Delete memories by ID, conversation, or age |
| `update(memory_id, content, metadata)` | `bool` | Update content or metadata of a stored memory |
| `get_memory(memory_id)` | `Optional[Dict]` | Fetch a specific memory by ID |
| `stats()` | `Dict` | Memory counts, vector store status, graph stats |
| `health()` | `Dict` | System health: all backends, status flags |
| `save(path)` | `None` | Persist full context state (memory + graph) to disk |
| `load(path)` | `None` | Restore context state from disk |
| `export(conversation_id, format)` | `str \| Dict` | Export memories as JSON or dict |
| `import_data(data, format)` | `int` | Import memories from JSON or dict |

<Tip>
  **`retrieve()` uses `max_results=`, not `top_k=`.** The parameter is `max_results` (default `5`). Pass `use_graph=True` to force GraphRAG or `use_graph=False` to force vector-only retrieval regardless of whether a `knowledge_graph` is configured.
</Tip>

### Conversation Methods

```python
# Store turns in a conversation thread
context.store("User asked about deployment options", conversation_id="conv_001")
context.store("Agent recommended Docker + Kubernetes", conversation_id="conv_001")

# Retrieve full conversation history
history = context.conversation("conv_001", max_items=50)
for turn in history:
    print("[{}] {}".format(turn["timestamp"], turn["content"]))

# Retrieve across all conversations with a query
results = context.retrieve(
    "deployment recommendations",
    conversation_id="conv_001",
    max_results=10,
)
```

### Multi-Hop GraphRAG

**Requires `knowledge_graph`** to be set at construction: enables `query_with_reasoning()` for LLM-grounded multi-hop traversal:

```python
import os
from semantica.llms import Groq

llm    = Groq(model="llama-3.3-70b-versatile", api_key=os.getenv("GROQ_API_KEY"))
result = context.query_with_reasoning(
    query="What technologies have we chosen and why?",
    llm_provider=llm,
    max_hops=2,
    max_results=10,
)

print(result["response"])
print("Confidence: {:.2f}".format(result["confidence"]))
print("Sources used: {}".format(result["num_sources"]))
```

### Decision Methods

| Method | Returns | Description |
| :------ | :------- | :----------- |
| `record_decision(category, scenario, reasoning, outcome, confidence, entities, decision_maker, valid_from, valid_until)` | `str` | Record a decision; raises `RuntimeError` if `decision_tracking=False` or no `knowledge_graph` |
| `find_precedents(scenario, category, limit, use_hybrid_search, max_hops, as_of)` | `List[Decision]` | Find similar past decisions by semantic + structural similarity |
| `query_decisions(query, max_hops, use_hybrid_search)` | `List[Decision]` | Broad context-aware decision search |
| `get_causal_chain(decision_id, direction, max_depth)` | `List[Decision]` | Trace `"upstream"` causes or `"downstream"` effects |
| `trace_decision_explainability(decision_id)` | `Dict` | Full explainability: causes, effects, relationship paths |
| `get_policy_engine()` | `PolicyEngine` | Access the active `PolicyEngine` instance |

<Warning>
  `decision_tracking=True` requires `knowledge_graph` to also be set. Without it, `record_decision()` raises `RuntimeError`.
</Warning>

<Tip>
  **Use `find_precedents()` before every significant decision.** This is how the context module prevents agents from making contradictory choices across runs. Surface precedents to the LLM as context: "we chose X for similar reasons before."
</Tip>

### Checkpoint Methods

**Ideal for auditing reasoning loops**: take a snapshot before and after a pass to see exactly what changed:

```python
# Take a named snapshot of the current graph state
context.checkpoint("before_inference")

# ... run reasoning, record decisions ...

context.checkpoint("after_inference")

# See exactly what was added/removed
diff = context.diff_checkpoints("before_inference", "after_inference")
print("Decisions added: {}".format(len(diff["decisions_added"])))
print("Relationships added: {}".format(len(diff["relationships_added"])))

# Persist a checkpoint to disk via TemporalVersionManager
context.flush_checkpoint("after_inference")
```


## ContextGraph

**`ContextGraph`** is the knowledge graph backing `AgentContext`. Can also be used **standalone** for relationship modelling without the full context layer.

```python
from semantica.context import ContextGraph

graph = ContextGraph(advanced_analytics=True)

# Build the graph
graph.add_node("Python",  "language",  properties={"paradigm": "multi-paradigm"})
graph.add_node("FastAPI", "framework", properties={"language": "Python"})
graph.add_edge("Python", "FastAPI", "enables")

# Record and query decisions directly on the graph
decision_id = graph.record_decision(
    category="technology_choice",
    scenario="Web API framework selection",
    reasoning="FastAPI's async support and auto-docs match our requirements",
    outcome="selected_fastapi",
    confidence=0.92,
    entities=["Python", "FastAPI"],
)

similar = graph.find_precedents_by_scenario("web framework", limit=3)
stats   = graph.stats()
print("Nodes: {}, Edges: {}".format(stats["node_count"], stats["edge_count"]))
```

### Constructor Options

| Parameter | Type | Default | Description |
| :--------- | :---- | :------- | :----------- |
| `advanced_analytics` | `bool` | `True` | PageRank, betweenness centrality |
| `centrality_analysis` | `bool` | `True` | Full centrality suite |
| `community_detection` | `bool` | `True` | Louvain community clustering |
| `node_embeddings` | `bool` | `True` | Node2Vec embeddings for structural similarity |

### ContextGraph: Full Method Reference

| Method | Returns | Description |
| :------ | :------- | :----------- |
| `add_node(node_id, node_type, properties, valid_from, valid_until)` | `None` | Add a node; supports temporal validity windows |
| `add_edge(source_id, target_id, edge_type, weight, properties)` | `None` | Add a directed edge with optional weight |
| `add_nodes(nodes)` | `int` | Bulk-add from a list of dicts; returns count added |
| `add_edges(edges)` | `int` | Bulk-add edges; returns count added |
| `get_neighbors(node_id, hops)` | `List[Dict]` | BFS neighbors up to given depth |
| `get_neighbor_distances(node_id, hops)` | `List[Dict]` | Neighbors with confidence-decay scoring |
| `find_node(node_id)` | `Optional[Dict]` | Look up a single node by ID |
| `find_nodes(node_type, skip, limit)` | `List[Dict]` | Filter nodes by type with pagination |
| `find_active_nodes(node_type, at_time)` | `List[Dict]` | Nodes that are valid at a given timestamp |
| `find_edges(edge_type, skip, limit)` | `List[Dict]` | Filter edges by type with pagination |
| `record_decision(category, scenario, reasoning, outcome, confidence, entities, decision_maker)` | `str` | Add decision node with causal edges |
| `find_precedents_by_scenario(scenario, category, limit, use_semantic_search, as_of)` | `List[Dict]` | Semantically similar past scenarios |
| `query(query, skip, limit)` | `List[Dict]` | Full-text search over node content |
| `stats()` | `Dict` | Node/edge counts, type breakdowns, graph density |
| `density()` | `float` | Graph density score |
| `save_to_file(path)` | `None` | Persist graph to JSON |
| `load_from_file(path)` | `None` | Load graph from JSON |
| `build_from_conversations(conversations, link_entities)` | `Dict` | Build graph from conversation data |
| `link_graph(other_graph, source_node_id, target_node_id, link_type)` | `str` | Create cross-graph navigation link; returns `link_id` |
| `navigate_to(link_id)` | `Tuple` | Follow a cross-graph link to `(target_graph, target_node_id)` |
| `cross_graph_path(source_node_id, target_graph, target_node_id, max_hops)` | `Dict` | Shortest path across linked graphs |
| `clear()` | `None` | Reset graph state and all indexes |

### Distance Intelligence (v0.5.0)

`ContextGraph` exposes a full Distance Intelligence API for exploring semantic neighborhoods and blending proximity into retrieval.

<Info>
  Full Distance Intelligence reference — distance matrices, API endpoints, embedding cache, Explorer UI — is covered in the dedicated [Distance Intelligence](distance) page. This section documents the context-layer API.
</Info>

### Neighbors with Distance Metadata

Pass `include_distance_metadata=True` to `get_neighbors()` to receive distance band, confidence decay, and path information alongside every neighbor:

```python
graph = ContextGraph(advanced_analytics=True)

# ... populate graph ...

neighbors = graph.get_neighbors(
    "python",
    hops=3,
    include_distance_metadata=True,
    min_weight=0.3,   # exclude low-confidence edges
)

for n in neighbors:
    print(
        f"{n['node_id']:15s}  "
        f"band={n['distance_band']:10s}  "
        f"decay={n['confidence_decay']:.3f}  "
        f"hops={n['hop_count']}"
    )
```

| Added field | Type | Description |
| :---------- | :---- | :----------- |
| `distance_band` | `str` | `"direct"` (1 hop) / `"near"` (2) / `"mid-range"` (3–4) / `"distant"` (5+) |
| `confidence_decay` | `float` | `edge_weight ^ hop_count` — decays with each hop |
| `path_to_anchor` | `List[str]` | Shortest path from anchor node to this neighbor |
| `hop_count` | `int` | BFS depth from anchor |

### Proximity-Blended Retrieval

Set `proximity_weight` on `AgentContext` to blend graph proximity into every `retrieve()` and `find_precedents()` call:

```python
context = AgentContext(
    vector_store=VectorStore(backend="faiss", dimension=768),
    knowledge_graph=ContextGraph(advanced_analytics=True),
    proximity_weight=0.3,   # 0.7×semantic + 0.3×proximity
)

# combined_score is returned alongside semantic_score and proximity_score
results = context.retrieve("web API frameworks", max_results=10)
for r in results:
    print(
        f"[{r['combined_score']:.3f}]  "
        f"semantic={r['semantic_score']:.3f}  "
        f"proximity={r['proximity_score']:.3f}  "
        f"{r['content'][:60]}"
    )

# Override weight per-call
precedents = context.find_precedents(
    "infrastructure scaling decisions",
    proximity_weight=0.5,
    limit=5,
)
```

<Tip>
  `proximity_weight=0.0` disables proximity blending entirely (pure semantic). `proximity_weight=1.0` returns results ranked purely by graph proximity to the query anchor. Values between `0.2`–`0.4` work well for most production use cases.
</Tip>


## Cross-Graph Navigation

Link multiple independent `ContextGraph` instances so agents can traverse across problem spaces:

```python
domain_graph    = ContextGraph()
decision_graph  = ContextGraph()

domain_graph.add_node("microservices", "architecture", properties={"style": "distributed"})
decision_graph.add_node("deploy_k8s",  "decision",     properties={"outcome": "approved"})

link_id = domain_graph.link_graph(
    other_graph=decision_graph,
    source_node_id="microservices",
    target_node_id="deploy_k8s",
    link_type="INFORMED_BY",
)

# Follow the link at traversal time
target_graph, entry_node = domain_graph.navigate_to(link_id)

# Cross-graph pathfinding
path = domain_graph.cross_graph_path(
    source_node_id="microservices",
    target_graph=decision_graph,
    target_node_id="deploy_k8s",
    max_hops=5,
)
print("Reachable: {}, hops: {}".format(path["reachable"], path["hop_count"]))
```


## AgentMemory

For fine-grained control over memory storage and retrieval:

```python
from semantica.context import AgentMemory
from semantica.vector_store import VectorStore

memory = AgentMemory(
    vector_store=VectorStore(backend="faiss", dimension=768),
    max_memory_size=10000,
    retention_policy="90_days",   # or "unlimited"
)

memory_id = memory.store(
    "Critical compliance rule: all trades must be pre-approved",
    metadata={"type": "compliance"},
)

results = memory.retrieve(
    query="trade approval requirements",
    max_results=5,
    min_score=0.0,
)

memory.delete_memory(memory_id)
memory.clear_memory(conversation_id="conv_001")

history = memory.get_conversation_history(conversation_id="conv_001", max_items=100)
```

| Parameter | Type | Default | Description |
| :--------- | :---- | :------- | :----------- |
| `vector_store` | `VectorStore` | **required** | Embedding backend for semantic retrieval |
| `max_memory_size` | `int` | `10000` | Max items before LRU eviction |
| `retention_policy` | `str` | `"unlimited"` | `"N_days"` (e.g. `"30_days"`) or `"unlimited"` |


## PolicyEngine

`PolicyEngine` manages versioned policies stored in the knowledge graph. Policies are stored as nodes and can be linked to decisions:

```python
from semantica.context import PolicyEngine
from semantica.context import ContextGraph
from semantica.context.decision_models import Policy, Decision
from datetime import datetime

graph  = ContextGraph()
policy = PolicyEngine(graph_store=graph)

# Create and store a policy
p = Policy(
    policy_id="policy_001",
    name="Confidence Threshold Policy",
    description="All decisions must have confidence >= 0.7",
    rules={"min_confidence": 0.7, "requires_reasoning": True},
    category="decision_quality",
    version="1.0",
    created_at=datetime.now(),
    updated_at=datetime.now(),
)
policy.add_policy(p)

# Check compliance of a specific decision
decision = Decision(
    decision_id="dec_001",
    category="loan_approval",
    scenario="First-time homebuyer",
    reasoning="Good credit score and stable employment",
    outcome="approved",
    confidence=0.94,
    timestamp=datetime.now(),
    decision_maker="loan_agent",
)
compliant = policy.check_compliance(decision, "policy_001")
print("Compliant:", compliant)

# Get applicable policies for a category
policies = policy.get_applicable_policies(category="decision_quality")
for p in policies:
    print("{} v{}".format(p.name, p.version))
```


## EntityLinker

Maps entity text to URIs and creates typed links between entity IDs:

```python
from semantica.context import EntityLinker

linker = EntityLinker(similarity_threshold=0.8)

# Assign a URI to an entity
uri = linker.assign_uri("apple_inc", "Apple Inc.", "ORGANIZATION")
print(uri)  # "https://semantica.dev/entity/apple_inc.#organization"

# Link entities from extracted text
entities = [
    {"id": "e1", "text": "Apple Inc.", "type": "ORGANIZATION"},
    {"id": "e2", "text": "Apple",      "type": "ORGANIZATION"},
]
linked = linker.link(text="Apple Inc. was founded by Steve Jobs.", entities=entities)
for e in linked:
    print("{} → {}  (confidence: {:.2f})".format(e.text, e.uri, e.confidence))

# Explicitly link two entity IDs (not a list: takes two IDs)
linker.link_entities(
    entity1_id="apple_inc",
    entity2_id="aapl",
    link_type="same_as",
    confidence=0.99,
)

# Build the full entity web
web = linker.build_entity_web()
print("Entities:", web["statistics"]["total_entities"])
print("Links:   ", web["statistics"]["total_links"])
```

<Warning>
  **`EntityLinker.link_entities()` links two entity IDs, not a list.** Call `link_entities(entity1_id, entity2_id, link_type)` to create a typed edge between two known IDs. For linking entities extracted from text, use `link(text, entities=[...])` instead.
</Warning>

`LinkedEntity` fields returned by `link()`:

| Field | Type | Description |
| :----- | :---- | :----------- |
| `entity_id` | `str` | Entity identifier |
| `uri` | `str` | Generated URI (e.g. `"https://semantica.dev/entity/apple_inc."`) |
| `text` | `str` | Surface form text |
| `type` | `str` | Entity type |
| `linked_entities` | `List[EntityLink]` | Related entity links with `source_entity_id`, `target_entity_id`, `link_type`, `confidence` |
| `context` | `Dict` | Entity metadata |
| `confidence` | `float` | Overall confidence score |


## ContextRetriever

Hybrid retrieval combining vector similarity, graph traversal, and memory:

```python
from semantica.context import ContextRetriever

retriever = ContextRetriever(
    memory_store=memory,
    knowledge_graph=context_graph,
    vector_store=vector_store,
    use_graph_expansion=True,
    max_expansion_hops=2,
    hybrid_alpha=0.5,
)

results = retriever.retrieve(
    query="What decisions were made about cloud infrastructure?",
    max_results=10,
    use_graph_expansion=True,
    min_relevance_score=0.3,
)

for r in results:
    print("[{}] score={:.3f}: {}".format(r.source, r.score, r.content[:80]))
```


## Data Structures

<AccordionGroup>
  <Accordion title="Decision">

```python
@dataclass
class Decision:
    decision_id:          str
    category:             str
    scenario:             str
    reasoning:            str
    outcome:              str
    confidence:           float               # 0.0 - 1.0
    timestamp:            datetime
    decision_maker:       str
    reasoning_embedding:  Optional[List[float]]  # generated embedding
    node2vec_embedding:   Optional[List[float]]  # structural embedding
    valid_from:           Optional[str]       # ISO datetime
    valid_until:          Optional[str]       # ISO datetime
    metadata:             Dict[str, Any]
```

  </Accordion>
  <Accordion title="Precedent">

```python
@dataclass
class Precedent:
    precedent_id:        str
    source_decision_id:  str
    similarity_score:    float               # 0-1 match score
    relationship_type:   str                 # "similar_scenario" | "same_policy" | "exception_precedent"
    metadata:            Dict[str, Any]
```

  </Accordion>
  <Accordion title="Policy">

```python
@dataclass
class Policy:
    policy_id:    str
    name:         str
    description:  str
    rules:        Dict[str, Any]    # rule definitions
    category:     str
    version:      str               # e.g. "1.0", "2.1"
    created_at:   datetime
    updated_at:   datetime
    metadata:     Dict[str, Any]
```

  </Accordion>
  <Accordion title="PolicyException">

```python
@dataclass
class PolicyException:
    exception_id:        str
    decision_id:         str
    policy_id:           str
    reason:              str
    approver:            str
    approval_timestamp:  datetime
    justification:       str
    metadata:            Dict[str, Any]
```

  </Accordion>
  <Accordion title="ApprovalChain">

```python
@dataclass
class ApprovalChain:
    approval_id:       str
    decision_id:       str
    approver:          str
    approval_method:   str          # "slack_dm" | "zoom_call" | "email" | "system"
    approval_context:  str
    timestamp:         datetime
    metadata:          Dict[str, Any]
```

  </Accordion>
  <Accordion title="LinkedEntity">

```python
@dataclass
class LinkedEntity:
    entity_id:       str
    uri:             str
    text:            str
    type:            str
    linked_entities: List[EntityLink]
    context:         Dict[str, Any]
    confidence:      float

@dataclass
class EntityLink:
    source_entity_id:  str
    target_entity_id:  str
    link_type:         str          # "same_as" | "related_to" | "part_of"
    confidence:        float
    source:            Optional[str]
    metadata:          Dict[str, Any]
```

  </Accordion>
</AccordionGroup>


## Real-World Patterns

<Tabs>
  <Tab title="Healthcare: Treatment Decisions">
    ```python
    from semantica.context import AgentContext, ContextGraph
    from semantica.vector_store import VectorStore

    health_agent = AgentContext(
        vector_store=VectorStore(backend="faiss", dimension=768),
        knowledge_graph=ContextGraph(),
        decision_tracking=True,
    )

    health_agent.store("Patient has hypertension, type 2 diabetes")
    health_agent.store("Patient allergic to penicillin: verified 2024-01")

    decision_id = health_agent.record_decision(
        category="treatment_plan",
        scenario="Hypertension with comorbid diabetes",
        reasoning="ACE inhibitors are renoprotective in diabetic patients",
        outcome="prescribed_lisinopril",
        confidence=0.91,
    )

    precedents = health_agent.find_precedents("hypertension diabetes", limit=5)
    for p in precedents:
        print("Past: {}  (confidence: {:.2f})".format(p.outcome, p.confidence))

    chain = health_agent.get_causal_chain(decision_id, direction="downstream")
    print("Follow-up decisions triggered: {}".format(len(chain)))
    ```
  </Tab>
  <Tab title="Finance: Loan Decisions">
    ```python
    from semantica.context import AgentContext, ContextGraph, PolicyEngine
    from semantica.context.decision_models import Policy, Decision
    from semantica.vector_store import VectorStore
    from datetime import datetime

    graph  = ContextGraph()
    policy = PolicyEngine(graph_store=graph)

    # Add compliance policy
    p = Policy(
        policy_id="lending_policy",
        name="Lending Policy",
        description="Min confidence 0.8 for loan decisions",
        rules={"min_confidence": 0.8},
        category="loan_approval",
        version="1.0",
        created_at=datetime.now(),
        updated_at=datetime.now(),
    )
    policy.add_policy(p)

    loan_agent = AgentContext(
        vector_store=VectorStore(backend="faiss", dimension=768),
        knowledge_graph=graph,
        decision_tracking=True,
    )
    loan_agent.store("Applicant: credit score 750, DTI 28%, stable employment 4yr")

    # Check compliance before recording
    d = Decision(
        decision_id="dec_loan_001",
        category="loan_approval",
        scenario="First-time homebuyer: 30yr fixed, 20% down",
        reasoning="Credit score above threshold, DTI within limits",
        outcome="approved_300k",
        confidence=0.94,
        timestamp=datetime.now(),
        decision_maker="loan_agent",
    )
    compliant = policy.check_compliance(d, "lending_policy")
    if compliant:
        loan_agent.record_decision(
            category=d.category,
            scenario=d.scenario,
            reasoning=d.reasoning,
            outcome=d.outcome,
            confidence=d.confidence,
        )
    ```
  </Tab>
  <Tab title="Persist & Restore">
    ```python
    from semantica.context import AgentContext, ContextGraph
    from semantica.vector_store import VectorStore

    context = AgentContext(
        vector_store=VectorStore(backend="faiss", dimension=768),
        knowledge_graph=ContextGraph(),
        decision_tracking=True,
    )

    context.store("Important fact learned during session")
    context.record_decision(
        category="ops", scenario="Scale up", reasoning="Load > 80%",
        outcome="scaled_to_10_replicas", confidence=0.97,
    )

    # Persist everything
    context.save("agent_state/")

    # Later: restore and continue
    restored = AgentContext(
        vector_store=VectorStore(backend="faiss", dimension=768),
        knowledge_graph=ContextGraph(),
        decision_tracking=True,
    )
    restored.load("agent_state/")

    results = restored.retrieve("load scaling decisions", max_results=3)
    ```
  </Tab>
</Tabs>

- [Vector Store](vector_store) — Embedding storage backend for memory retrieval.
- [Knowledge Graph](kg) — Graph algorithms and analytics used inside ContextGraph.
- [Reasoning](reasoning) — Logical inference layered on top of context.
- [Provenance](provenance) — W3C PROV-O lineage for every stored fact.

- [Context Module](https://github.com/semantica-agi/semantica/blob/main/cookbook/introduction/19_Context_Module.ipynb) — Memory and decision tracking · Intermediate
- [Advanced Context Engineering](https://github.com/semantica-agi/semantica/blob/main/cookbook/advanced/11_Advanced_Context_Engineering.ipynb) — Production FAISS + Neo4j setup · Advanced
