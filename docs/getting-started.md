---
title: "Getting Started"
description: "The context and intelligence layer for AI: turning raw data into explainable, auditable knowledge graphs."
icon: "rocket"
---

<Tip>
  Already installed? Jump straight to [Quickstart](quickstart). Need setup help first? See [Installation](installation).
</Tip>

## What You Can Build

- **GraphRAG Systems** — Ground LLM responses in traceable, structured knowledge. Every claim links back to a source node.
- **Accountable AI Agents** — Agents with structured decision history, causal chains, and precedent search. Every choice is recorded and auditable.
- **Production Knowledge Graphs** — Build, validate, and maintain enterprise-grade semantic knowledge bases from multi-source data.
- **Compliance-Ready AI** — W3C PROV-O provenance on every fact. HIPAA, SOX, GDPR, FDA 21 CFR Part 11 infrastructure built in.


## Setup in 3 Steps

<Steps>
  <Step title="Install Semantica">
    <CodeGroup>

    ```bash pip (recommended)
    pip install semantica
    ```

    ```bash With all extras
    pip install semantica[all]
    ```

    ```bash From source
    git clone https://github.com/semantica-agi/semantica.git
    cd semantica
    pip install -e ".[dev]"
    ```

    </CodeGroup>

    <Check>
      Verify installation:
      ```python
      import semantica
      print(semantica.__version__)  # 0.5.0
      ```
    </Check>
  </Step>

  <Step title="Choose your path">
    Pick the track that matches what you're building: each starts with a focused 5-minute example.

    | Track | You want to... | Start with |
    | :----- | :-------------- | :--------- |
    | **Knowledge Graph** | Turn documents into structured, queryable graphs | [Quickstart → Step 1](quickstart) |
    | **Agent Context** | Give your AI agent persistent memory and decision tracking | [Context reference](reference/context) |
    | **GraphRAG** | Ground LLM answers in structured knowledge | [Concepts → GraphRAG](concepts#graphrag) |
    | **MCP Integration** | Use Semantica from Claude Desktop or VS Code | [MCP Server](reference/mcp_server) |

  </Step>

  <Step title="Run the pipeline">
    The full 6-step pipeline: ingest, parse, extract, build, visualize, export: is in the [Quickstart](quickstart). Takes under 5 minutes with pattern-based extraction (no API key required).

    <Note>
      An LLM API key is **optional** for the quickstart. Pattern-based extraction works out of the box: upgrade to LLM extraction for higher accuracy when you're ready.
    </Note>
  </Step>
</Steps>


## Choose Your Path

<Tabs>
  <Tab title="Knowledge Graph">
    Build a structured knowledge graph from any document or data source.

    ```python
    from semantica.ingest import FileIngestor
    from semantica.parse import DocumentParser
    from semantica.semantic_extract import NERExtractor, RelationExtractor
    from semantica.kg import GraphBuilder

    # 1. Ingest
    sources = FileIngestor().ingest("data/report.pdf")

    # 2. Parse
    parsed = DocumentParser().parse(sources[0])

    # 3. Extract
    ner           = NERExtractor(method="pattern")  # no API key needed
    entities      = ner.extract(parsed)
    relationships = RelationExtractor().extract(parsed, entities=entities)

    # 4. Build
    graph = GraphBuilder(merge_entities=True).build(
        entities=entities, relationships=relationships
    )
    print(f"{len(graph['nodes'])} nodes, {len(graph['relationships'])} edges")
    ```

    **Next:** [Full pipeline walkthrough →](quickstart)
  </Tab>

  <Tab title="Agent Context">
    Give your agent persistent memory, decision tracking, and precedent search.

    ```python
    from semantica.context import AgentContext, ContextGraph
    from semantica.vector_store import VectorStore

    context = AgentContext(
        vector_store=VectorStore(backend="faiss", dimension=768),
        knowledge_graph=ContextGraph(advanced_analytics=True),
        decision_tracking=True,
    )

    # Store a fact with provenance
    context.store("GPT-4 outperforms GPT-3.5 on reasoning by 40%")

    # Record a decision with full causal chain
    decision_id = context.record_decision(
        category="model_selection",
        scenario="Choose LLM for production pipeline",
        reasoning="GPT-4 benchmark advantage justifies cost",
        outcome="selected_gpt4",
        confidence=0.91,
    )

    # Search past decisions before making a new one
    precedents = context.find_precedents("model selection", limit=5)
    ```

    **Next:** [Context module reference →](reference/context)
  </Tab>

  <Tab title="GraphRAG">
    Ground every LLM response in your knowledge graph: no floating assertions.

    ```python
    from semantica.context import AgentContext, ContextGraph
    from semantica.vector_store import VectorStore

    context = AgentContext(
        vector_store=VectorStore(backend="faiss", dimension=768),
        knowledge_graph=ContextGraph(advanced_analytics=True),
    )

    # Load your knowledge graph
    context.load_graph("company_kg.json")

    # Multi-hop GraphRAG query
    result = context.query(
        "What companies were founded by people who worked at Apple?",
        mode="graphrag",
        reasoning=True,
    )

    # Every claim links back to a source node
    for claim in result.claims:
        print(f"{claim.text}  →  source: {claim.source_node}")
    ```

    **Next:** [GraphRAG concepts →](concepts#graphrag)
  </Tab>

  <Tab title="MCP Integration">
    Use Semantica from Claude Desktop, VS Code, Cursor, or any MCP client: no Python code required after setup.

    ```bash
    pip install semantica
    ```

    Add to your MCP client config:

    ```json
    {
      "mcpServers": {
        "semantica": {
          "command": "semantica-mcp"
        }
      }
    }
    ```

    12 tools available instantly: extract entities, query graph, record decisions, run reasoning, export results.

    **Next:** [MCP Server reference →](reference/mcp_server)
  </Tab>
</Tabs>


## Core Architecture

Semantica uses a modular, layered architecture: import only what you need.

- **[Input Layer](reference/ingest)** — Load and prepare data from any source. Modules: `ingest`, `parse`, `split`, `normalize`
- **[Semantic Layer](reference/semantic_extract)** — Extract meaning from raw text. Modules: `semantic_extract`, `kg`, `ontology`, `reasoning`
- **[Storage Layer](reference/vector_store)** — Persist knowledge for retrieval. Modules: `embeddings`, `vector_store`, `graph_store`, `triplet_store`
- **[Quality Layer](reference/deduplication)** — Validate and deduplicate. Modules: `deduplication`, `conflicts`
- **[Context Layer](reference/context)** — Track decisions and lineage. Modules: `context`, `provenance`, `change_management`
- **[Output Layer](reference/export)** — Deliver results downstream. Modules: `export`, `visualization`, `pipeline`, `explorer`


## "Which module do I need?" Quick Reference

| I want to... | Module | Key class |
| :------------ | :------ | :--------- |
| Load a PDF / web page / database | `ingest` | `FileIngestor`, `WebIngestor` |
| Extract text and tables from a PDF | `parse` | `DocumentParser`, `DoclingParser` |
| Find entities in text | `semantic_extract` | `NERExtractor` |
| Build a knowledge graph | `kg` | `GraphBuilder` |
| Store and search vectors | `vector_store` | `VectorStore` |
| Give my agent persistent memory | `context` | `AgentContext` |
| Record AI decisions with audit trail | `context` | `AgentContext.record_decision()` |
| Query my graph with natural language | `reasoning` | `GraphReasoner` |
| Export to RDF / Neo4j / Parquet | `export` | `RDFExporter`, `LPGExporter` |
| Visualize a knowledge graph | `visualization` | `KGVisualizer` |
| Run a reproducible pipeline | `pipeline` | `PipelineBuilder` |
| Use Semantica from Claude Desktop | `mcp_server` | `semantica-mcp` |


## Next Steps

- [Core Concepts](concepts) — Knowledge graphs, ontologies, and reasoning explained in depth.
- [Quickstart Tutorial](quickstart) — Full 6-step pipeline walkthrough with working code.
- [Module Reference](modules) — Every module, class, and common chain explained.
- [API Reference](reference/context) — Complete module documentation for every class and method.


## Help

- [Discord](https://discord.gg/sV34vps5hH) — Ask questions, share projects, get community support.
- [GitHub Issues](https://github.com/semantica-agi/semantica/issues) — Report bugs or request features.
- [FAQ](faq) — Common questions answered.
