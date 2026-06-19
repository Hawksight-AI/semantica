---
title: "Choose the Right Module"
description: "Map your goal to the right Semantica module in under 30 seconds."
icon: "compass"
---

<Info>
  Every module works independently — import only what you need. This page maps developer goals to starting points. The [Module Reference](modules) covers every module in depth.
</Info>

## Quick Reference

Find your goal below. The **Module** column is your import path; **Key class** is what you instantiate first.

| I want to... | Module | Key class |
| :------------ | :------ | :--------- |
| Load a PDF, DOCX, HTML, CSV, or archive | `ingest` | `FileIngestor` |
| Crawl a website | `ingest` | `WebIngestor` |
| Load Parquet files or partitioned datasets | `ingest` | `ParquetIngestor` |
| Ingest XML with schema validation | `ingest` | `XMLIngestor` |
| Ingest from SQL, Snowflake, Kafka, or email | `ingest` | `DBIngestor`, `SnowflakeIngestor`, `StreamIngestor` |
| Extract clean text and tables from a document | `parse` | `DocumentParser` |
| Parse complex PDFs with OCR or multi-column layout | `parse` | `DoclingParser` |
| Chunk text for embedding or RAG | `split` | `TextSplitter` |
| Normalize text, dates, entities, or encodings | `normalize` | `TextNormalizer`, `EntityNormalizer` |
| Find named entities (people, orgs, locations) in text | `semantic_extract` | `NERExtractor` |
| Extract typed relationships from text | `semantic_extract` | `RelationExtractor` |
| Extract RDF subject–predicate–object triplets | `semantic_extract` | `TripletExtractor` |
| Build a queryable knowledge graph | `kg` | `GraphBuilder` |
| Add time-validity (`valid_from` / `valid_until`) to facts | `kg` | `TemporalGraphQuery` |
| Run graph algorithms (centrality, communities, paths) | `kg` | `GraphAnalyzer`, `CentralityCalculator` |
| Generate vector embeddings | `embeddings` | `EmbeddingGenerator` |
| Store and search vectors | `vector_store` | `VectorStore` |
| Persist a graph in Neo4j or FalkorDB | `graph_store` | `Neo4jStore`, `FalkorDBStore` |
| Store RDF triples and query with SPARQL | `triplet_store` | `TripletStore` |
| Deduplicate entities across sources | `deduplication` | `DuplicateDetector`, `EntityMerger` |
| Detect and resolve contradictory facts | `conflicts` | `ConflictDetector`, `ConflictResolver` |
| Give an AI agent persistent memory | `context` | `AgentContext` |
| Ground LLM responses in a knowledge graph (GraphRAG) | `context` | `AgentContext.query_with_reasoning()` |
| Record AI decisions with a full audit trail | `context` | `AgentContext.record_decision()` |
| Search past decisions before making a new one | `context` | `AgentContext.find_precedents()` |
| Trace the causal chain of a decision | `context` | `AgentContext.get_causal_chain()` |
| Track where every fact came from (W3C PROV-O) | `provenance` | `ProvenanceManager` |
| Version a graph with checksums and rollback | `change_management` | `TemporalVersionManager` |
| Auto-generate an OWL schema from a graph | `ontology` | `OntologyGenerator` |
| Validate a graph against SHACL constraints | `ontology` | `SHACLGenerator`, `OntologyValidator` |
| Derive new facts from existing knowledge | `reasoning` | `Reasoner`, `GraphReasoner` |
| Export to RDF Turtle, JSON-LD, or N-Triples | `export` | `RDFExporter` |
| Export to Parquet for Spark / BigQuery | `export` | `ParquetExporter` |
| Export for ArangoDB | `export` | `ArangoAQLExporter` |
| Export to Neo4j or Memgraph via Cypher | `export` | `LPGExporter` |
| Visualize a knowledge graph interactively | `visualization` | `KGVisualizer` |
| Run a reproducible multi-step pipeline | `pipeline` | `PipelineBuilder` |
| Use Semantica from Claude Desktop or Cursor | `mcp_server` | `semantica-mcp` |
| Bootstrap a graph from verified seed data | `seed` | `SeedDataManager` |
| Extend Semantica with a custom component | `core` | `PluginRegistry` |


## Goal-by-Goal Starting Points

Pick your goal to see the minimum imports and a working skeleton.

<Tabs>
  <Tab title="Build a Knowledge Graph">
    Turn documents, web pages, or databases into a structured, queryable graph.

    **Pipeline:** `ingest` → `parse` → `semantic_extract` → `kg`

    ```python
    from semantica.ingest import FileIngestor
    from semantica.parse import DocumentParser
    from semantica.semantic_extract import NERExtractor, RelationExtractor
    from semantica.kg import GraphBuilder

    sources       = FileIngestor().ingest("report.pdf")
    parsed        = DocumentParser().parse_document("report.pdf")

    # No API key required — pattern-based extraction
    entities      = NERExtractor(method="pattern").extract(parsed)
    relationships = RelationExtractor(method="rule").extract(parsed, entities=entities)

    graph = GraphBuilder(merge_entities=True).build(
        sources=[{"entities": entities, "relationships": relationships}]
    )
    print(f"{len(graph.nodes)} nodes, {len(graph.edges)} edges")
    ```

    <Tip>
      Pass `method="pattern"` to `NERExtractor` for zero-cost, zero-API-key extraction. Switch to `method="llm"` with any of the supported providers for higher recall.
    </Tip>

    **Next:** [Quickstart →](quickstart) — full pipeline with visualization and export.
  </Tab>

  <Tab title="Build GraphRAG">
    Ground every LLM response in a structured knowledge graph. Every claim links back to a source node.

    **Module:** `context`

    ```python
    from semantica.context import AgentContext, ContextGraph
    from semantica.vector_store import VectorStore
    from semantica.llms import Groq

    llm = Groq(model="llama-3.3-70b-versatile")

    context = AgentContext(
        vector_store=VectorStore(backend="faiss", dimension=768),
        knowledge_graph=ContextGraph(advanced_analytics=True),
    )

    # Store facts — retrieval uses both vectors and graph structure
    context.store("Apple Inc. was co-founded by Steve Jobs in 1976 in Cupertino.")

    # GraphRAG query with multi-hop reasoning trace
    result = context.query_with_reasoning(
        "Who co-founded Apple?",
        llm_provider=llm,
        max_hops=2,
    )
    print(result["response"])        # grounded answer
    print(result["reasoning_path"])  # multi-hop trace
    ```

    **Next:** [Context module reference →](reference/context)
  </Tab>

  <Tab title="Add Agent Memory">
    Give an AI agent persistent memory, decision tracking, and precedent search across sessions.

    **Module:** `context`

    ```python
    from semantica.context import AgentContext, ContextGraph
    from semantica.vector_store import VectorStore

    context = AgentContext(
        vector_store=VectorStore(backend="faiss", dimension=768),
        knowledge_graph=ContextGraph(advanced_analytics=True),
        decision_tracking=True,   # required to use record_decision()
    )

    # Store a memory
    context.store("GPT-4 outperforms GPT-3.5 on reasoning benchmarks by 40%.")

    # Record a decision with full causal context
    decision_id = context.record_decision(
        category="model_selection",
        scenario="Choose LLM for production reasoning pipeline",
        reasoning="GPT-4 benchmark advantage justifies cost increase",
        outcome="selected_gpt4",
        confidence=0.91,
    )

    # Search past decisions before making a new one
    precedents = context.find_precedents("model selection", limit=5)

    # Trace what happened downstream from this decision
    chain = context.get_causal_chain(decision_id, direction="downstream")
    ```

    <Note>
      `decision_tracking=True` is required. Without it, `record_decision()` raises `RuntimeError`.
    </Note>

    **Next:** [Context module reference →](reference/context)
  </Tab>

  <Tab title="Track Provenance">
    W3C PROV-O lineage on every fact: source document, extraction method, timestamp, and checksum.

    **Modules:** `provenance`, `change_management`

    ```python
    from semantica.provenance import ProvenanceManager

    prov = ProvenanceManager()

    # Track an entity with full source details
    prov.track_entity(
        entity_id="entity_1",
        source="DOI:10.1371/journal.pone.0023601",
        source_location="Figure 2",
        confidence=0.92,
    )

    # Retrieve the complete lineage for this entity
    lineage = prov.get_lineage("entity_1")

    # Version-control the graph with SHA-256 checksums
    from semantica.change_management import TemporalVersionManager

    manager  = TemporalVersionManager()
    snapshot = manager.create_snapshot(kg, "v1.0", "user@example.com", "Initial build")
    diff     = manager.diff("v1.0", "v1.1")
    ```

    **Next:** [Provenance reference →](reference/provenance) · [Change Management reference →](reference/change_management)
  </Tab>

  <Tab title="Export">
    Serialize your knowledge graph for the semantic web, analytics platforms, or graph databases.

    **Module:** `export`

    ```python
    from semantica.export import RDFExporter, ParquetExporter, LPGExporter, ArangoAQLExporter

    # RDF — multiple serialization formats
    RDFExporter().export(graph, "graph.ttl",    format="turtle")
    RDFExporter().export(graph, "graph.jsonld", format="jsonld")

    # Parquet — for Spark, BigQuery, Databricks, Snowflake
    ParquetExporter().export(graph, "output/graph.parquet")

    # Neo4j / Memgraph via Cypher
    LPGExporter().export(graph, "graph.cypher")

    # ArangoDB AQL inserts
    ArangoAQLExporter().export(graph, "graph.aql")
    ```

    **Formats:** Turtle · JSON-LD · N-Triples · RDF/XML · Parquet · Cypher · Arrow · OWL · CSV · ArangoDB AQL

    **Next:** [Export module reference →](reference/export)
  </Tab>

  <Tab title="MCP — Claude / Cursor">
    Use Semantica from Claude Desktop, Cursor, VS Code, or any MCP-aware tool — no Python code required after setup. 12 tools available instantly.

    **Step 1 — Install:**
    ```bash
    pip install semantica
    ```

    **Step 2 — Add to your MCP client config:**

    <CodeGroup>

    ```json Claude Desktop / Windsurf / Cline
    {
      "mcpServers": {
        "semantica": {
          "command": "semantica-mcp"
        }
      }
    }
    ```

    ```json Cursor / VS Code / Continue
    {
      "mcpServers": {
        "semantica": {
          "command": "semantica-mcp",
          "env": {
            "SEMANTICA_KG_PATH": "/path/to/my_graph.json"
          }
        }
      }
    }
    ```

    </CodeGroup>

    **Available tools:** `extract_entities` · `extract_relations` · `add_entity` · `add_relationship` · `record_decision` · `query_decisions` · `find_precedents` · `get_causal_chain` · `run_reasoning` · `get_graph_analytics` · `export_graph` · `get_graph_summary`

    <Warning>
      Set `SEMANTICA_KG_PATH` to persist your graph across restarts. Without it, all data is lost when the server process exits.
    </Warning>

    **Next:** [MCP Server reference →](reference/mcp_server)
  </Tab>
</Tabs>


## Still Unsure?

<AccordionGroup>
  <Accordion title="Knowledge graph vs. vector store — which do I need?" icon="scale-balanced">
    Use a **knowledge graph** (`kg`) when you need structured reasoning, multi-hop traversal, provenance, or compliance audit trails.

    Use a **vector store** (`vector_store`) when you need fast fuzzy similarity search over large text corpora and relationships between items don't matter.

    Use **both together** via `AgentContext` (GraphRAG) to get grounded LLM responses where every claim traces back to a source node.

    See also: [Core Concepts](concepts)
  </Accordion>

  <Accordion title="I just want to run something quickly." icon="rocket">
    Start with the [Quickstart](quickstart). It builds a complete pipeline (ingest → parse → extract → graph → visualize → export) with no API key required.
  </Accordion>

  <Accordion title="I'm adding Semantica to an existing agent — what's the minimum?" icon="plug">
    Add `AgentContext`. It wraps your existing agent with memory, decision tracking, and precedent search — no changes to your LLM provider or agent framework needed.

    ```python
    from semantica.context import AgentContext, ContextGraph
    from semantica.vector_store import VectorStore

    context = AgentContext(
        vector_store=VectorStore(backend="faiss", dimension=768),
        knowledge_graph=ContextGraph(advanced_analytics=True),
        decision_tracking=True,
    )
    ```

    [Context module reference →](reference/context)
  </Accordion>

  <Accordion title="I need a compliance-ready pipeline — what's the minimum stack?" icon="shield-check">
    | Layer | Module | Key class |
    | :---- | :------ | :--------- |
    | Ingestion | `ingest` | `FileIngestor` |
    | Extraction | `semantic_extract` | `NERExtractor` |
    | Graph | `kg` | `GraphBuilder` |
    | Lineage | `provenance` | `ProvenanceManager` |
    | Versioning | `change_management` | `TemporalVersionManager` |
    | Audit export | `export` | `RDFExporter` |
    Supports HIPAA, SOX, GDPR, and FDA 21 CFR Part 11 audit requirements.
  </Accordion>
</AccordionGroup>

---

- [Quickstart](quickstart) — Full pipeline in 5 minutes.
- [Module Reference](modules) — Every module with examples and common chains.
- [API Reference](reference/context) — Complete class and method documentation.
