---
title: "Core Concepts"
description: "The fundamental ideas behind Semantica: knowledge graphs, reasoning, provenance, and temporal intelligence explained."
icon: "book-open"
---

<Info>
  New here? Start with [Getting Started](getting-started) for hands-on examples, then return here for deeper understanding.
</Info>

Semantica transforms unstructured data: documents, web pages, reports, databases: into **knowledge graphs**: structured representations that AI systems can query, reason about, and trace back to sources.

At its core, Semantica adds a **context and accountability layer** on top of your existing AI stack. It doesn't replace LangChain, LlamaIndex, or your LLM provider: it makes their outputs **grounded**, **traceable**, and **auditable**.

<CardGroup cols={3}>
  <Card title="Context Layer" icon="diagram-project">
    Knowledge graphs, GraphRAG retrieval, semantic embeddings, and temporal intelligence ground every LLM response in structured, queryable facts.
  </Card>
  <Card title="Accountability Layer" icon="shield-check">
    Provenance tracking, decision intelligence, conflict detection, and W3C PROV-O compliance make every claim in your AI stack auditable and explainable.
  </Card>
  <Card title="Extension Layer" icon="plug">
    `PluginRegistry` and `MethodRegistry` let you replace or augment any component: ingestors, extractors, reasoning engines, backends: without changing framework code.
  </Card>
</CardGroup>


## Knowledge Graphs

<img src="/assets/img/diagrams/kg-structure.svg" alt="Knowledge graph node and edge structure showing entities (Person, Organization, Location, Date) and their typed relations" style={{ width: '100%', borderRadius: '12px', margin: '0 0 20px' }} />

The foundation of everything in Semantica. A knowledge graph stores information as three building blocks:

- **Nodes (entities)**: people, companies, locations, events, concepts
- **Edges (relationships)**: `works_for`, `located_in`, `founded_by`
- **Properties**: name, date, confidence score, source URL

This structure makes knowledge **searchable**, **connectable**, **queryable**, and: critically: **explainable**: every answer can be traced back to the facts and relationships that produced it.


## Entity Extraction (NER)

Scanning text to find and classify real-world entities:

```python
# Input: "Apple Inc. was founded by Steve Jobs in 1976 in Cupertino."
{
    "entities": [
        {"text": "Apple Inc.",  "type": "ORGANIZATION", "confidence": 0.98},
        {"text": "Steve Jobs",  "type": "PERSON",       "confidence": 0.99},
        {"text": "1976",        "type": "DATE",         "confidence": 0.95},
        {"text": "Cupertino",   "type": "LOCATION",     "confidence": 0.97}
    ]
}
```

Each entity gets a type, confidence score, and a link to its source document. Three extraction methods are available:

| Method | Speed | Accuracy | Requirements |
| :------ | :----- | :-------- | :------------ |
| `"pattern"` | ⚡ Very fast | Moderate | No API key: regex-based |
| `"ml"` | Fast | High | Local ML model |
| `"llm"` | Medium | Highest | LLM provider: all 9 supported |

## Relationship Extraction

Finding how entities connect to each other:

```python
{
    "relationships": [
        {"subject": "Steve Jobs", "predicate": "founded",    "object": "Apple Inc.", "confidence": 0.92},
        {"subject": "Apple Inc.", "predicate": "located_in", "object": "Cupertino",  "confidence": 0.89}
    ]
}
```

Relationships can be extracted via rule-based methods, ML models, or LLMs: each producing typed triplets with confidence scores and source attribution.


## Knowledge Graph vs. Vector Store

Both store information for AI retrieval: but they're built for different jobs.

<Tabs>
  <Tab title="Knowledge Graph">
    Stores **structured facts** as typed nodes and labeled edges. Answers questions that require understanding relationships between entities.

    | Strength | Why it matters |
    | :-------- | :------------- |
    | **Traversal** | Multi-hop queries: "Who founded companies that Apple alumni later joined?" |
    | **Explainability** | Every answer traces back to specific nodes and edges: no black-box retrieval |
    | **Temporal reasoning** | Point-in-time queries, `valid_from`/`valid_until` windows, historical snapshots |
    | **Conflict detection** | Two sources disagreeing on the same fact is surfaced and resolvable |
    | **Schema enforcement** | SHACL validation catches constraint violations before they corrupt results |

    **Use when:** you need structured reasoning, provenance, compliance, or explainability.

    ```python
    from semantica.kg import GraphBuilder, PathFinder

    graph   = GraphBuilder(merge_entities=True).build(entities=entities, relationships=rels)
    finder  = PathFinder()
    path    = finder.dijkstra_shortest_path(graph, "Steve Jobs", "Tim Cook")
    ```
  </Tab>

  <Tab title="Vector Store">
    Stores **dense embeddings** of text chunks. Answers questions by finding semantically similar passages: useful when the structure of the answer isn't known in advance.

    | Strength | Why it matters |
    | :-------- | :------------- |
    | **Fuzzy similarity** | Finds relevant content even when exact words don't match |
    | **Speed** | Sub-millisecond approximate nearest-neighbor search at scale |
    | **Unstructured text** | Works directly on paragraphs, sentences, and raw documents |
    | **Simplicity** | No schema design required: embed and index |

    **Use when:** you need fast semantic search over large text corpora.

    ```python
    from semantica.vector_store import VectorStore

    store   = VectorStore(backend="faiss", dimension=768)
    store.add_documents(["Apple was founded in 1976.", "Google was founded in 1998."])
    results = store.search("tech company founding dates", limit=5)
    ```
  </Tab>

  <Tab title="GraphRAG (Both)">
    Semantica combines both: vector search seeds the graph traversal, and the graph provides structure and provenance the vector store cannot.

    | Step | What happens |
    | :---- | :----------- |
    | **Query embedding** | User query is embedded and used to find anchor nodes via vector similarity |
    | **Graph traversal** | Multi-hop traversal from anchor nodes retrieves related entities and relationships |
    | **Context assembly** | Facts + relationships are assembled with source attribution for each claim |
    | **LLM generation** | LLM generates an answer grounded in the retrieved structured context |

    **Result:** every claim in the response links back to a specific graph node: no hallucination from training data, full audit trail.

    ```python
    from semantica.context import AgentContext, ContextGraph
    from semantica.vector_store import VectorStore

    context = AgentContext(
        vector_store=VectorStore(backend="faiss", dimension=768),
        knowledge_graph=ContextGraph(advanced_analytics=True),
    )
    result = context.query("Who founded Apple?", mode="graphrag")
    ```
  </Tab>
</Tabs>


## Embeddings

Embeddings convert text into numerical vectors so AI systems can measure semantic similarity: finding related concepts even when the exact words differ.

Semantica uses embeddings for:

- **Semantic search**: retrieve by meaning, not just keywords
- **Entity resolution**: match the same entity across different sources
- **Precedent search**: find similar past decisions
- **GraphRAG retrieval**: hybrid vector + graph traversal
- **Distance Intelligence**: N×N semantic distance matrices between any node set

**Supported models:** Sentence-Transformers, FastEmbed, OpenAI, BGE, Ollama local embeddings.


## GraphRAG

GraphRAG (Graph-Augmented Retrieval Augmented Generation) enhances LLM responses by grounding them in a structured knowledge graph rather than raw text chunks alone.

<img src="/assets/img/diagrams/graphrag-flow.svg" alt="GraphRAG flow: User Query → Vector Search + Graph Traversal → Context Builder → LLM → Grounded Answer" style={{ width: '100%', borderRadius: '12px', margin: '16px 0 20px' }} />

<Steps>
  <Step title="User submits a query">
    The query is embedded and used to seed both vector search and graph traversal simultaneously.
  </Step>
  <Step title="Hybrid context retrieval">
    Semantica retrieves relevant graph context: entities, typed relationships, and multi-hop reasoning paths: alongside vector-similar text chunks.
  </Step>
  <Step title="Context building">
    Retrieved facts and reasoning paths are assembled into a structured prompt context, each fact tagged with its source node and confidence.
  </Step>
  <Step title="LLM generates a grounded response">
    The LLM produces an answer where every claim links back to a source node in the graph: no floating assertions, no hallucinations from training data.
  </Step>
</Steps>

<Tip>
  **GraphRAG eliminates the hallucination and traceability problems of standard RAG.** Standard RAG retrieves text chunks; GraphRAG retrieves structured facts with typed relationships. The LLM cannot confabulate structure that was never in the graph.
</Tip>


## Ontology

An ontology defines the schema and rules for your knowledge: what entity types exist, which relationships are valid, and what constraints apply.

```python
ontology = {
    "classes": ["Person", "Organization", "Location"],
    "relationships": ["works_for", "located_in", "founded_by"],
    "rules": {
        "Person":       ["must_have_name"],
        "Organization": ["must_have_name", "can_have_founding_date"]
    }
}
```

Semantica can auto-generate ontologies from your knowledge graph or import existing OWL/RDF/Turtle ontologies. The **Ontology Hub** (v0.5.0) adds a visual editor, SHACL Studio, alignment authoring, and a live health dashboard. See the [Ontology reference](reference/ontology) for the full 6-stage generation pipeline.


## Reasoning & Inference

Semantica includes multiple reasoning engines to derive new knowledge from existing facts.

```text
Known:    Steve Jobs founded Apple Inc.
Known:    Apple Inc. is headquartered in Cupertino
Inferred: Steve Jobs has a connection to Cupertino
```

<Tabs>
  <Tab title="Forward Chaining">
    Applies IF/THEN rules repeatedly until no new facts can be derived. Best for alert systems, compliance checks, and trigger-based workflows.

    ```python
    from semantica.reasoning import Reasoner, Rule, Fact, RuleType

    engine = Reasoner()
    engine.add_fact(Fact(subject="Alice", predicate="is_a", obj="Manager"))
    engine.add_rule(Rule(
        rule_type=RuleType.FORWARD_CHAIN,
        conditions=[{"subject": "?x", "predicate": "is_a", "object": "Manager"}],
        conclusion={"subject": "?x", "predicate": "has_authority", "object": "true"}
    ))
    result = engine.infer()
    ```
  </Tab>
  <Tab title="Rete Network">
    Efficient pattern matching for large rule sets: the Rete algorithm avoids re-evaluating rules whose preconditions haven't changed. Best for thousands of rules over millions of facts.

    ```python
    from semantica.reasoning import ReteEngine

    engine = ReteEngine()
    engine.load_rules("rules/domain_rules.json")
    results = engine.run(kg)
    ```
  </Tab>
  <Tab title="Deductive & Abductive">
    **Deductive**: classical syllogistic reasoning from premises to guaranteed conclusions.

    **Abductive**: infers the most likely explanation for observed evidence. Best for diagnostic and investigative use cases.

    ```python
    from semantica.reasoning import GraphReasoner

    graph_reasoner = GraphReasoner(kg)
    graph_reasoner.add_rule({"if": [{"subject": "?a", "predicate": "parent_of", "object": "?b"}], "then": {"subject": "?a", "predicate": "ancestor_of", "object": "?b"}})
    inferences = graph_reasoner.infer(kg)
    ```
  </Tab>
  <Tab title="Datalog (v0.4.0)">
    Recursive Horn clause rules with fixpoint semantics: handles transitive closure and recursive relationships that forward chaining cannot express.

    ```python
    from semantica.reasoning import DatalogReasoner, DatalogFact, DatalogRule

    reasoner = DatalogReasoner()
    reasoner.add_fact(DatalogFact("parent", ("alice", "bob")))
    reasoner.add_rule(DatalogRule("ancestor(?X, ?Y) :- parent(?X, ?Y)."))
    reasoner.evaluate()
    results = reasoner.query("ancestor(alice, ?Z)")
    ```
  </Tab>
  <Tab title="Engine Comparison">

    | Engine | Description | Best For |
    | :------ | :----------- | :-------- |
    | Forward chaining | Applies rules until fixpoint | Alert systems, compliance checks |
    | Rete network | Efficient pattern matching | Large rule sets, high fact throughput |
    | Deductive | Classical syllogistic reasoning | Mathematical and logical inference |
    | Abductive | Most likely explanation | Diagnostics, investigation |
    | SPARQL | Query-based inference over RDF | Semantic web, ontology reasoning |
    | Datalog (v0.4.0) | Recursive Horn clause rules | Transitive closure, graph reachability |

  </Tab>
</Tabs>

All engines produce **explainable inference paths**: not black-box conclusions. Every derived fact includes the rules and premises that produced it.


## Temporal Intelligence

Knowledge changes over time. Temporal graphs attach `valid_from` / `valid_until` windows to nodes and edges, enabling point-in-time queries and historical analysis.

```python
from semantica.kg import TemporalGraphQuery
from datetime import datetime

query_engine = TemporalGraphQuery(enable_temporal_reasoning=True)

# Query the graph as it existed on a specific date
snapshot = query_engine.query_at_time(kg, query="", at_time=datetime(2021, 6, 15))
```

**Supported features:** Allen interval algebra (all 13 temporal relations), OWL-Time export, `recorded_at` stamping, temporal provenance.

**Common uses:** tracking company leadership changes, policy evolution, research timelines, financial instrument histories, regulatory compliance windows.


## Distance Intelligence

Explore the semantic neighborhood of any entity in your graph: useful for understanding what's conceptually close, detecting clusters, and visualizing knowledge topology.

```python
from semantica.kg import SimilarityCalculator

calc   = SimilarityCalculator()
scores = calc.calculate_similarity(entity_a, entity_b)
```

**Features:** N×N semantic distance matrices, ego-mode visualization, distance band classification (`near` / `mid` / `far`), embedding cache optimization for large graphs.

The [Visualization module](reference/visualization) renders distance matrices as interactive heatmaps and ego-mode neighborhood graphs. The [Explorer](reference/explorer) embeds distance intelligence directly in the browser dashboard.


## Deduplication & Entity Resolution

Real-world data contains the same entity under many names: "Apple", "Apple Inc.", "Apple Computer Inc." Semantica's deduplication pipeline detects these, merges attributes, resolves conflicts, and preserves the original source provenance.

<Tabs>
  <Tab title="Strategies">

    | Strategy | Algorithm | Best For |
    | :-------- | :--------- | :-------- |
    | `v1` | Jaro-Winkler string similarity | Small datasets, fast baseline |
    | `blocking_v2` | Candidate blocking + similarity | Large corpora: reduces O(n²) comparisons |
    | `hybrid_v2` | Blocking + semantic embedding match | Mixed structured/unstructured entity names |
    | `semantic_v2` | Pure embedding-based resolution | Up to 7× faster than v1; handles abbreviations and aliases |

  </Tab>
  <Tab title="Configuration">
    ```python
    from semantica.deduplication import DuplicateDetector, EntityMerger

    detector = DuplicateDetector(similarity_threshold=0.85)
    duplicates = detector.detect_duplicates(entities)

    merger = EntityMerger()
    deduplicated_entities = merger.merge_duplicates(entities)
    ```
  </Tab>
</Tabs>


## Provenance & Auditability

Every fact in Semantica links back to:

- The **source document** it came from
- The **extraction method** used (pattern / ML / LLM)
- The **ontology rules** applied during graph construction
- The **reasoning steps** that produced any inferred fact

<Note>
  This is W3C PROV-O compliant lineage: suitable for regulated industries that require audit trails (HIPAA, SOX, GDPR, FDA 21 CFR Part 11). Use `RDFExporter(include_provenance=True)` to embed provenance inline in any RDF export.
</Note>

```python
from semantica.provenance import ProvenanceManager

prov    = ProvenanceManager()
lineage = prov.get_entity_lineage("apple_inc")

print(f"Source:    {lineage.source_document}")
print(f"Method:    {lineage.extraction_method}")
print(f"Extracted: {lineage.timestamp}")
print(f"Checksum:  {lineage.checksum}")
```


## Decision Intelligence

Every agent decision is a first-class object in Semantica: recorded, causally linked, and searchable by precedent. This is the **accountability layer** for AI pipelines: decisions are no longer ephemeral log messages, they are queryable knowledge graph nodes.

```python
decision_id = context.record_decision(
    category="model_selection",
    scenario="Choose LLM for production pipeline",
    reasoning="GPT-4 benchmark advantage justifies 3x cost increase",
    outcome="selected_gpt4",
    confidence=0.91,
)

# Find similar past decisions before making a new one
precedents = context.find_precedents("model selection reasoning", limit=5)

# Trace downstream impact of a past decision
influence  = context.analyze_decision_influence(decision_id)
```

<Tip>
  **Use `find_precedents()` before every high-stakes decision.** Hybrid similarity search over all recorded decisions surfaces past reasoning that may apply: reducing inconsistency across agent runs and enabling genuine organisational learning from AI decision history.
</Tip>


## Conflict Detection

When multiple sources disagree on the same fact, Semantica flags and resolves the conflict rather than silently picking one value.

**Resolution strategies:**

- **Recency**: prefer the most recent source
- **Source credibility**: prefer the most reliable source (configurable credibility scores)
- **Majority vote**: aggregate across all sources with ≥ 2 agreeing
- **Manual review**: flag for human arbitration; continue pipeline without blocking

See the [Conflicts reference](reference/conflicts) for `ConflictResolver`, `SourceTracker`, and `InvestigationGuideGenerator`.


## Custom Plugin Development

Semantica is designed for extension. Any component: ingestor, extractor, graph builder, reasoning engine: can be replaced or augmented with a custom implementation registered at runtime.

<AccordionGroup>
  <Accordion title="PluginRegistry: replace any component by name">

    `PluginRegistry` provides dynamic plugin discovery, registration, and loading across all modules. Register your own class under a string key; Semantica will use it wherever that key is referenced in config or pipeline steps.

    ```python
    from semantica.core import PluginRegistry

    registry = PluginRegistry()

    # Register a custom ingestor
    registry.register_plugin(
        "my_sql_ingestor", MySQLIngestor,
        version="1.0.0",
        description="PostgreSQL ingestor for internal warehouse",
        capabilities=["ingest"],
    )

    # Load and use
    plugin = registry.load_plugin("my_sql_ingestor", connection_string="postgresql://...")
    result = plugin.execute("SELECT * FROM documents")

    # Reference by name in pipeline YAML: no code changes needed
    ```

    ```yaml
    steps:
      - name: ingest
        plugin: my_sql_ingestor
        config:
          connection_string: "${DB_URL}"
    ```

    **Extension points available:** ingestors, parsers, normalizers, extractors, reasoning engines, export formats, vector store backends, graph store backends, visualization renderers.

  </Accordion>
  <Accordion title="MethodRegistry: add domain-specific graph operations">

    `MethodRegistry` lets you register custom methods on knowledge graph objects by name: useful for adding domain-specific graph operations without subclassing.

    ```python
    from semantica.kg import MethodRegistry

    registry = MethodRegistry()

    def find_supply_chain_hops(graph, source_node, max_hops=3):
        """Custom BFS traversal for supply chain graphs."""
        ...

    # Register under a string key
    registry.register("supply_chain_hops", find_supply_chain_hops)

    # Call by name on any graph object
    result = registry.call("supply_chain_hops", kg, source_node="Supplier_A", max_hops=5)

    # List all registered methods
    print(registry.list_methods())   # ["supply_chain_hops", ...]
    ```

  </Accordion>
</AccordionGroup>

<CardGroup cols={2}>
  <Card title="Quickstart Tutorial" icon="play" href="quickstart">
    Build a full pipeline with code.
  </Card>
  <Card title="Modules Guide" icon="puzzle-piece" href="modules">
    Every module explained with examples.
  </Card>
  <Card title="API Reference" icon="code" href="reference/context">
    Complete technical reference.
  </Card>
</CardGroup>
