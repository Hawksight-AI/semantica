<div align="center">

<img src="Semantica Logo.png" alt="Semantica" width="420"/>

### Graph-Native Infrastructure for Context and Accountable AI Systems

#### *The Open Source Palantir for AI Agents*

> Ingest your enterprise data, extract what matters, build a Context Graph and knowledge graph (KG), and run graph analytics and causal reasoning over all of it, with full decision provenance baked in. Explainable, traceable, and trustworthy by design.

**Decision Intelligence &nbsp;·&nbsp; Context Management &nbsp;·&nbsp; Deterministic Reasoning &nbsp;·&nbsp; Ontology Management &nbsp;·&nbsp; SKOS Vocabularies &nbsp;·&nbsp; Traceability**

**Open Source &nbsp;·&nbsp; Auditable &nbsp;·&nbsp; Governed &nbsp;·&nbsp; Self-Hostable &nbsp;·&nbsp; Zero Vendor Lock-In**

#### Built for High-Stakes, Regulated Domains

*Finance &nbsp;·&nbsp; Healthcare &nbsp;·&nbsp; Legal &nbsp;·&nbsp; Government &nbsp;·&nbsp; Defense &nbsp;&nbsp;([details ↓](#built-for-high-stakes-domains))*

[![GitHub Stars](https://img.shields.io/github/stars/semantica-agi/semantica?style=flat-square&color=FFD700&logo=github&logoColor=white&label=Stars)](https://github.com/semantica-agi/semantica) [![GitHub Forks](https://img.shields.io/github/forks/semantica-agi/semantica?style=flat-square&color=6E40C9&logo=github&logoColor=white&label=Forks)](https://github.com/semantica-agi/semantica/network/members) [![Contributors](https://img.shields.io/github/contributors/semantica-agi/semantica?style=flat-square&color=2EA043&logo=github&logoColor=white)](https://github.com/semantica-agi/semantica/graphs/contributors) [![PyPI](https://img.shields.io/pypi/v/semantica.svg?style=flat-square&color=0066CC&logo=pypi&logoColor=white)](https://pypi.org/project/semantica/) [![Total Downloads](https://static.pepy.tech/badge/semantica?style=flat-square)](https://pepy.tech/project/semantica) [![Python 3.8+](https://img.shields.io/badge/python-3.8+-3776AB?style=flat-square&logo=python&logoColor=white)](https://www.python.org/) [![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg?style=flat-square)](https://opensource.org/licenses/MIT) [![CI](https://img.shields.io/github/actions/workflow/status/semantica-agi/semantica/ci.yml?style=flat-square&label=CI)](https://github.com/semantica-agi/semantica/actions) [![Ask DeepWiki](https://deepwiki.com/badge.svg)](https://deepwiki.com/semantica-agi/semantica)

[![Website](https://img.shields.io/badge/Website-getsemantica.ai-000000?style=flat-square&logo=googlechrome&logoColor=white)](https://getsemantica.ai/) [![Docs](https://img.shields.io/badge/Docs-docs.getsemantica.ai-0099FF?style=flat-square&logo=readthedocs&logoColor=white)](https://docs.getsemantica.ai/) [![Discord](https://img.shields.io/badge/Discord-Join%20Community-5865F2?style=flat-square&logo=discord&logoColor=white)](https://discord.gg/sV34vps5hH) [![Twitter/X](https://img.shields.io/badge/Follow-%40BuildSemantica-000000?style=flat-square&logo=x&logoColor=white)](https://x.com/BuildSemantica) [![YouTube](https://img.shields.io/badge/YouTube-Watch%20Demos-FF0000?style=flat-square&logo=youtube&logoColor=white)](https://www.youtube.com/watch?v=QfnNZg4-dZA) [![Changelog](https://img.shields.io/badge/Changelog-View-6E40C9?style=flat-square&logo=keepachangelog&logoColor=white)](CHANGELOG.md)

</div>

---

<div align="center">

<a href="https://www.youtube.com/watch?v=QfnNZg4-dZA" target="_blank">
<img
  src="docs/assets/img/semantica-knowledge-explorer-demo.gif"
  alt="Semantica Knowledge Explorer: live graph, decisions, entity resolution, ontology hub"
  width="900"
/>
</a>

*Knowledge Explorer · Context Graphs · Reasoning Engine · Decision Intelligence · Ontology Hub*

**[▶ Watch the full platform walkthrough](https://www.youtube.com/watch?v=QfnNZg4-dZA)**

</div>

---

Most AI agents act without a trail. They store embeddings, not meaning: context that can't be explained, decisions that can't be audited. In lending, that gap is a compliance exposure, not an inconvenience: an underwriting agent's approval has to survive a regulator's "why" months later.

Semantica sits underneath your LLM, vector store, and agent framework as a deterministic infrastructure layer: no LLM required for graph construction, reasoning, or provenance.

**Who it's for:**

- **AI/ML platform teams** shipping agents that make consequential decisions and need structured, queryable context built from fragmented raw data, not just a vector index
- **Compliance, risk, and audit teams** who need a straight answer to "why did the AI do that?" in a format a regulator will actually accept
- **Regulated enterprises** (finance, healthcare, legal, government, defense) that can't ship a black box, and can't send their data to someone else's SaaS to get one
- **Platform and infra engineers** who want the KG, reasoning, and provenance stack self-hosted and swappable, not locked to one vendor's backend
- **Data and knowledge engineers** building a KG from messy, multi-source data: entities and relationships get extracted, conflicting or contradictory facts are flagged instead of silently overwritten, and duplicates are merged before they turn into noise

**[Quick Start](#quick-start)** &nbsp;·&nbsp; **[Architecture](#architecture)** &nbsp;·&nbsp; **[What You Get](#what-semantica-gives-you)** &nbsp;·&nbsp; **[Why Semantica](#why-semantica)** &nbsp;·&nbsp; **[Decision Intelligence](#decision-intelligence)** &nbsp;·&nbsp; **[Context Graphs](#context-graphs)** &nbsp;·&nbsp; **[Recipe: Audit Trail](#recipe-audit-trail-for-a-regulated-decision)** &nbsp;·&nbsp; **[Platform Reference](PLATFORM_REFERENCE.md)** &nbsp;·&nbsp; **[CLI](#cli)** &nbsp;·&nbsp; **[Performance](#performance)** &nbsp;·&nbsp; **[Install](#installation)**

---

## What Semantica Gives You

- **Context Graphs:** A structured, queryable graph of everything your agent knows, decides, and reasons about
- **Decision Intelligence:** Every decision is a first-class object: traceable, searchable by precedent, and causally linked
- **AI Governance & Ontology:** SHACL constraints, conflict detection, compliance rules, OWL generation, and SKOS vocabulary management with a visual editor
- **Full Auditability:** W3C PROV-O provenance on every fact, with audit trails exportable to JSON, CSV, or RDF
- **Deterministic Reasoning:** Forward chaining, Rete network, Datalog, and SPARQL with fully explainable paths, not black boxes
- **Knowledge Pipeline:** Multi-source ingestion, entity-aware chunking, NER/relation/event extraction, and knowledge graph construction, with semantic deduplication and provenance-preserving merges throughout
- **Graph Analytics:** Centrality, community detection, link prediction, and shortest-path queries over the graph you just built
- **Polyglot Graph Storage:** Native RDF (Blazegraph, Apache Jena, Eclipse RDF4J via SPARQL) and Labeled Property Graphs (Neo4j, FalkorDB, Apache AGE, AWS Neptune via Cypher), plus vector stores, all swappable without touching your code
- **Visualization:** Explore any graph, ontology, or timeline in an interactive browser workbench
- **Drop-in Integrations:** Native Agno support, a full-featured MCP server, a comprehensive CLI, a REST API, and plugins across major editors

---

## Why Semantica

| | Vector DB + RAG | Plain LLM Memory | **Semantica** |
| --- | --- | --- | --- |
| **Recall method** | Embedding similarity | Token window | Graph traversal + semantic search |
| **Decision history** | Not stored | Not stored | First-class queryable objects |
| **Provenance** | None | None | W3C PROV-O, source-linked |
| **Reasoning** | None | Black box | Forward chain, Rete, Datalog, SPARQL |
| **Conflict detection** | Silent overwrite | Silent overwrite | Detected, flagged, resolved |
| **Time travel** | No | No | Point-in-time graph snapshots |
| **Compliance export** | None | None | PROV-O, SHACL, OWL, RDF |
| **Policy enforcement** | None | None | Built-in rule engine + SHACL |
| **Entity resolution** | No | No | Blocking + semantic deduplication |
| **Multi-agent context** | Separate per agent | Separate per agent | Single shared intelligence layer |

Semantica complements your existing stack rather than replacing it. Keep your LLM, vector store, and agent framework exactly as they are; Semantica adds the decision records, causal reasoning, provenance, ontology governance, conflict detection, and audit trails on top. The reasoning engines, KG construction, and provenance layer are fully deterministic; no LLM is required to use them.

---

## Quick Start

```bash
pip install semantica
```

```python
from semantica.context import ContextGraph

graph = ContextGraph(advanced_analytics=True)

# Every agent decision becomes a queryable, auditable knowledge node
decision_id = graph.record_decision(
    category="vendor_selection",
    scenario="Choose cloud provider for HIPAA workload",
    reasoning="AWS offers BAA, mature HIPAA tooling, and existing team expertise",
    outcome="selected_aws",
    confidence=0.93,
)

# Ask "why did this happen?" and get a real, structured answer
chain     = graph.trace_decision_chain(decision_id)       # full causal ancestry
similar   = graph.find_similar_decisions("cloud vendor", max_results=5)  # precedents
impact    = graph.analyze_decision_impact(decision_id)    # downstream influence map
compliant = graph.check_decision_rules({"category": "vendor_selection"})  # policy gate
```

**Verify your install in 5 seconds:**

```bash
semantica doctor
# Python 3.11.9         pass
# semantica 0.5.1       pass
# faiss vector store    pass
# Config file           pass    ~/.semantica/config.yaml
```

<div align="center">

If Semantica solves a real problem for you, a star helps others find it.

**[⭐ Star on GitHub](https://github.com/semantica-agi/semantica)** &nbsp;·&nbsp; **[Join Discord](https://discord.gg/sV34vps5hH)**

</div>

---

## Architecture

Semantica is a real end-to-end pipeline, not a single library with a marketing name. Every stage below is a shipping module, independently importable:

```
Sources → Ingest → Parse → Normalize → Split → Extract → Conflict Detection → Deduplication
   → Knowledge Graph → [ Ontology · Reasoning · Provenance · Decisions ] → Enriched KG
   → Vector Store + Polyglot Graph Store (RDF & LPG) → Export / Visualize / REST · MCP · CLI
```

- **Ingest:** files, web, databases, enterprise data platforms (Databricks, Snowflake), cloud (Drive, Elasticsearch), streams (Kafka, Kinesis), Git, email, MCP
- **Parse → Normalize → Split:** document parsing, text/entity/date normalization, GraphRAG-native entity-aware chunking
- **Extract → Conflict Detection → Deduplication:** NER, relations, events, triplets; conflicting facts flagged and resolved before they merge
- **Knowledge Graph:** `GraphBuilder` constructs the graph; bi-temporal facts and full graph analytics (centrality, communities, link prediction) run on top of it
- **Ontology · Reasoning · Provenance · Decisions:** the intelligence layer sitting on the KG, with SHACL/OWL governance, Rete/Datalog/SPARQL inference, W3C PROV-O lineage, and first-class decision records
- **Storage:** polyglot by design, with RDF triple stores (Blazegraph, Apache Jena, Eclipse RDF4J), Labeled Property Graphs (Neo4j, FalkorDB, Apache AGE, AWS Neptune), and vector stores, all swappable without touching your code
- **Outputs:** export (RDF, OWL, Parquet, Cypher, JSON-LD), interactive visualization, and access via REST API, MCP server, or CLI

**→ [Full Mermaid diagrams for the pipeline and the decision intelligence lifecycle](ARCHITECTURE.md)**

---

## Decision Intelligence

Decision Intelligence turns every AI choice from an ephemeral inference into a permanent, auditable, queryable record. It answers *"what did your AI decide, why, and what happened next?"*: the question regulators and enterprise risk teams ask with increasing urgency.

In Semantica, a decision is not a log line. It is a first-class graph node with a full lifecycle. In regulated domains, every AI decision must be traceable to a source and defensible to an auditor: `record_decision()` creates a permanent, structured record exportable as W3C PROV-O, the format most compliance frameworks accept for regulator submission.

```
record_decision()             → stored as a graph node with full structured context
add_causal_relationship()     → linked to upstream causes and downstream effects
find_similar_decisions()      → semantic precedent search across all past decisions
trace_decision_chain()        → full causal ancestry back to root causes
analyze_decision_impact()     → downstream influence map - everything this decision affected
check_decision_rules()        → policy compliance gate against configurable rule sets
export / audit trail          → W3C PROV-O, CSV, or JSON for regulator submission
```

```python
from semantica.context import ContextGraph

graph = ContextGraph(advanced_analytics=True)

# Record decisions with full structured context
app_id = graph.record_decision(
    category="credit_application",
    scenario="Personal loan, $85k income, 31% DTI, 3yr employment",
    reasoning="Income meets threshold; employment stable; no adverse credit events",
    outcome="proceed_to_underwriting",
    confidence=0.88,
    metadata={"applicant_id": "A-7291"},
)
uw_id = graph.record_decision(
    category="loan_underwriting",
    scenario="Underwriting review for A-7291",
    reasoning="DTI within policy; clean 36-month credit history",
    outcome="approved",
    confidence=0.94,
)
rate_id = graph.record_decision(
    category="interest_rate",
    scenario="Rate assignment for approved loan A-7291",
    outcome="rate_set_8.9pct",
    reasoning="Prime + 2.4% based on risk tier B2",
    confidence=0.99,
)

# Build the auditable causal chain
graph.add_causal_relationship(app_id, uw_id,   relationship_type="triggers")
graph.add_causal_relationship(uw_id,  rate_id, relationship_type="enables")

# Query the intelligence
chain     = graph.trace_decision_chain(rate_id)
similar   = graph.find_similar_decisions("personal loan approval, 31% DTI", max_results=5)
impact    = graph.analyze_decision_impact(uw_id)
compliant = graph.check_decision_rules({"category": "loan_underwriting", "confidence": 0.94})
insights  = graph.get_decision_insights()
```

---

## Context Graphs

A Context Graph is the structured memory layer that traditional RAG is missing. Instead of flat embeddings that answer *"what is similar?"*, a Context Graph answers *"what is connected, why, and how?"* Every entity, relationship, decision, and fact is a first-class node, queryable by graph traversal. Entities link to source documents, decisions link to evidence and consequences, facts carry full provenance, and conflicts are detected, not silently overwritten.

```python
from semantica.context import ContextGraph, AgentContext
from semantica.vector_store import VectorStore

graph = ContextGraph(advanced_analytics=True)

# Add nodes with typed properties
graph.add_node("acme_corp",    "Organization", name="Acme Corp", industry="SaaS")
graph.add_node("alice_chen",   "Person",       name="Alice Chen", role="CTO")
graph.add_node("contract_001", "Contract",     value=2_400_000, currency="USD")

# Add typed, weighted edges (extra kwargs become edge metadata)
graph.add_edge("alice_chen", "acme_corp",    edge_type="works_for",  since="2019-03-01")
graph.add_edge("acme_corp",  "contract_001", edge_type="party_to",   signed="2024-01-15")

# BFS traversal - hop through the graph from any node
neighbors = graph.get_neighbors("acme_corp", hops=2)

# Point-in-time snapshot - the graph as it existed on any past date
snapshot  = graph.state_at("2024-01-01")

# AgentContext - high-level API for agent memory workflows
vs  = VectorStore(backend="faiss")
ctx = AgentContext(vector_store=vs, knowledge_graph=graph)
ctx.store("Alice approved the Acme renewal in Q1 2024", conversation_id="conv_001")
retrieved = ctx.retrieve("who approved the Acme contract?")
```

**Why graph over embeddings:** traversal finds connections embeddings miss (a person 3 hops from a contract); every node carries provenance so you can always ask *"where did this come from?"*; conflicts are flagged before they corrupt your knowledge base; point-in-time snapshots let you replay history without reprocessing.

---

## Recipe: Audit Trail for a Regulated Decision

The flagship pattern: record a causally-linked decision chain, attach provenance to every entity, and export a regulator-ready audit trail.

```python
from semantica.context import ContextGraph
from semantica.provenance import ProvenanceManager
from semantica.export import RDFExporter

graph = ContextGraph(advanced_analytics=True)
prov  = ProvenanceManager(storage_path="./audit.db")

# Record the decision chain
d1 = graph.record_decision(
    category="loan_application", scenario="A-7291, $85k income",
    reasoning="Income threshold met", outcome="proceed", confidence=0.88,
)
d2 = graph.record_decision(
    category="loan_underwriting", scenario="Underwriting A-7291",
    reasoning="Clean credit history", outcome="approved", confidence=0.94,
)
graph.add_causal_relationship(d1, d2, relationship_type="triggers")

# Track provenance for every entity
prov.track_entity("applicant_A7291", source="loan_application_form.pdf",
                  metadata={"page": 1, "extractor": "NamedEntityRecognizer"})

# Export W3C PROV-O for regulator submission
kg = graph.export_graph()
RDFExporter().export(kg, "audit_trail.ttl", format="turtle")
```

More recipes (GraphRAG pipelines, an AML rules engine, ontology-to-KG in one pass) are in **[PLATFORM_REFERENCE.md](PLATFORM_REFERENCE.md#more-recipes)**.

---

## Explore the Platform

Every module below is independently importable, with working code samples; use one or all of them.

| Module | What it does |
| --- | --- |
| [`semantica.ingest`](PLATFORM_REFERENCE.md#semanticaingest-multi-source-ingestion) | Files, web, databases, APIs, streams, email, Git, Parquet, Snowflake, MCP |
| [`semantica.semantic_extract`](PLATFORM_REFERENCE.md#semanticasemantic_extract-ner-relations-events-triplets) | NER, relation extraction, event detection, triplet generation |
| [`semantica.kg`](PLATFORM_REFERENCE.md#semanticakg-knowledge-graph-construction--analysis) | Graph construction, centrality, communities, link prediction |
| [`semantica.reasoning`](PLATFORM_REFERENCE.md#semanticareasoning-forward-chaining-rete-datalog-sparql) | Forward chaining, Rete, Datalog, SPARQL, fully explainable |
| [`semantica.vector_store`](PLATFORM_REFERENCE.md#semanticavector_store-hybrid--filtered-semantic-search) | FAISS, Qdrant, Weaviate, Milvus, Pinecone, PgVector, hybrid search |
| [`semantica.split`](PLATFORM_REFERENCE.md#semanticasplit-graphrag-native-document-chunking) | Entity-aware, relation-aware, ontology-aware chunking for GraphRAG |
| [`semantica.provenance`](PLATFORM_REFERENCE.md#semanticaprovenance-w3c-prov-o-lineage) | W3C PROV-O lineage on every fact |
| [`semantica.ontology`](PLATFORM_REFERENCE.md#semanticaontology-owl-generation-shacl-validation) | OWL generation, SHACL validation, SKOS vocabularies |
| [`semantica.conflicts`](PLATFORM_REFERENCE.md#semanticaconflicts-conflict-detection--resolution) | Detect and resolve conflicting facts across sources |
| [`semantica.deduplication`](PLATFORM_REFERENCE.md#semanticadeduplication-entity-resolution-at-scale) | Entity resolution at scale, 6.98× faster than baseline |
| [`semantica.export`](PLATFORM_REFERENCE.md#semanticaexport-rdf-owl-parquet-cypher-json-ld) | RDF, OWL, Parquet, Cypher, JSON-LD |
| [`semantica.visualization`](PLATFORM_REFERENCE.md#semanticavisualization-interactive-graph-workbench) | Force-directed graphs, ontology hierarchies, temporal dashboards |
| [Temporal Intelligence](PLATFORM_REFERENCE.md#temporal-intelligence-bi-temporal-graphs--time-travel) | Bi-temporal facts, Allen interval algebra, time travel |
| [Multi-Agent (Agno)](PLATFORM_REFERENCE.md#multi-agent-shared-context-with-agno) | One shared context graph across every agent on a team |

**→ [Full Platform Reference](PLATFORM_REFERENCE.md)**: every module, more recipes, the full integrations matrix, MCP tool list, and REST endpoints.

---

## Performance

Benchmarks from v0.5.0 on a 118,000-node production graph:

| Operation | Before | After | Improvement |
| --- | --- | --- | --- |
| Node search (118k nodes) | 24 ms | 0.004 ms | **6,000×** faster |
| Embedding cache hit | cold load | revision-based cache | **10×** throughput |
| Semantic deduplication | baseline | optimized candidate gen | **6.98×** faster |
| Candidate generation | baseline | blocking strategy | **63.6%** faster |

*Measured on a 118,000-node production graph (AMD EPYC, 64 GB RAM). Results vary by hardware, dataset topology, and backend selection. Run `pytest tests/vector_store/test_performance_benchmarks.py -s` to measure your own data.*

---

## CLI

Every capability is available from the terminal. The CLI ships with the package, no separate install required.

```bash
pip install semantica
semantica        # startup dashboard
semantica doctor # health check
semantica --help # full grouped command reference
```

Start with `semantica`, verify with `doctor`, build a graph, and explore the command groups from one terminal.

**Command groups:** `ingest` · `parse` · `extract` · `kg` · `reason` · `decision` · `temporal` · `provenance` · `ontology` · `embed` · `deduplicate` · `validate` · `export` · `visualize` · `pipeline` · `server` · `explorer` · `mcp` · `doctor` · `shell` · `init` · `watch`

→ [Full CLI reference](https://docs.getsemantica.ai/)

---

## Integrations

Native plugin bundles for Claude Code, Cursor, Codex, Windsurf, Cline, Continue, VS Code, and OpenClaw; a full-featured MCP server for any MCP-compatible client; a comprehensive REST API; and first-class Agno support for multi-agent shared context. Every major LLM provider is already supported via `semantica.llms` and LiteLLM: OpenAI, Anthropic, Gemini, Mistral, Llama, Groq, Cohere, Azure, Bedrock, Ollama, DeepSeek, HuggingFace, and more.

MCP setup in 30 seconds:

```bash
python -m semantica.mcp_server
# or: semantica-mcp
```

```json
{
  "mcpServers": {
    "semantica": { "command": "python", "args": ["-m", "semantica.mcp_server"] }
  }
}
```

**→ [Full integrations matrix, MCP tool list, and REST endpoints](PLATFORM_REFERENCE.md#integrations)**

---

## Knowledge Explorer

A browser-based graph workbench. Pan and zoom live graphs, scrub the timeline, review every decision's causal chain, resolve duplicates, and author your ontology visually. Built on React 19 + Sigma.js.

| Workspace | What you can do |
| --- | --- |
| **Knowledge Graph** | Live Sigma.js canvas with ForceAtlas2 layout, Ego Mode, semantic distance heatmap |
| **Timeline** | Scrub through temporal events and watch the graph evolve |
| **Decisions** | Browse the causal chain behind every recorded decision |
| **Registry** | Live audit log of every graph mutation |
| **Entity Resolution** | Review and merge duplicates |
| **Ontology Hub** | SHACL Studio, visual editor, cross-ontology alignments, SKOS browser |
| **Lineage** | W3C PROV-O provenance visualization for any entity |

Quickest way to start (no Node.js required):

```bash
pip install "semantica[explorer]"
semantica-explorer --graph my_graph.json
# Dashboard opens at http://127.0.0.1:8000
```

For contributor / dev-server setup: **[explorer/README.md: Local Setup Guide](explorer/README.md)**

---

## What's New in v0.5.1

- **Apache Arrow & Feather Ingestion:** Read `.arrow`, `.feather`, and `.ipc` files via `ArrowIngestor`; selective column reads, row limits, batch-aware iteration; auto-detected by extension and IPC magic bytes. Install with `pip install semantica[ingest-arrow]`
- **Knowledge Explorer Deployment Templates:** Ready-to-use `deploy/` configs for major cloud platforms; fixed Dockerfile, full-stack Compose, `/api/health` endpoint, env-var wired `FALKORDB_HOST`/`ALLOWED_ORIGINS`

  [![Docker](https://img.shields.io/badge/Docker-Compose-2496ED?style=flat-square&logo=docker&logoColor=white)](deploy/docker-compose.yml)
  [![Railway](https://img.shields.io/badge/Railway-Deploy-0B0D0E?style=flat-square&logo=railway&logoColor=white)](deploy/railway/railway.toml)
  [![Render](https://img.shields.io/badge/Render-Deploy-46E3B7?style=flat-square&logo=render&logoColor=black)](deploy/render/render.yaml)
  [![Fly.io](https://img.shields.io/badge/Fly.io-Deploy-7B3FE4?style=flat-square&logo=flydotio&logoColor=white)](deploy/fly/fly.toml)
  [![GCP Cloud Run](https://img.shields.io/badge/GCP-Cloud%20Run-4285F4?style=flat-square&logo=googlecloud&logoColor=white)](deploy/gcp/cloudrun-service.yaml)
  [![Azure](https://img.shields.io/badge/Azure-Container%20Apps-0078D4?style=flat-square&logo=microsoftazure&logoColor=white)](deploy/azure/main.bicep)
  [![Kubernetes](https://img.shields.io/badge/Kubernetes-Manifests-326CE5?style=flat-square&logo=kubernetes&logoColor=white)](deploy/kubernetes/)
  [![Helm](https://img.shields.io/badge/Helm-Chart-0F1689?style=flat-square&logo=helm&logoColor=white)](deploy/helm/knowledge-explorer/)
- **Neo4j Bulk CSV Export:** `Neo4jCSVExporter` for `neo4j-admin database import`; deterministic output, SHA-256 stable node IDs, multi-label support, `dry_run()` validation

→ [Full release notes](RELEASE_NOTES.md) · [Changelog](CHANGELOG.md)

---

## Built for High-Stakes Domains

Semantica is designed for environments where AI outputs must be explainable, auditable, and defensible, and where the data itself can't leave your infrastructure. Self-hostable with zero vendor lock-in, it's built as much for organizations handling confidential or classified data as for regulated industries chasing an audit trail:

- **Finance:** Loan underwriting audit trails, fraud detection, AML compliance, regulatory risk knowledge graphs
- **Healthcare:** Clinical decision support, drug interaction graphs, and patient safety audit trails
- **Legal:** Evidence-backed research, contract analysis, case law reasoning, and privilege tracking
- **Government & Defense:** Policy decision records, classified information governance, and regulatory reporting, fully self-hosted with no data leaving your perimeter
- **Law Enforcement:** Case linkage, evidence provenance chains, and investigative knowledge graphs that hold up under legal scrutiny
- **Cybersecurity:** Threat attribution, incident response timelines, and IOC provenance tracking
- **Autonomous Systems:** Decision logs, safety validation, and explainable AI for certification

---

## Installation

```bash
pip install semantica           # core
pip install semantica[all]      # everything
```

```bash
pip install semantica[agno]                 # Agno multi-agent integration
pip install semantica[llm-litellm]          # OpenAI, Anthropic, Gemini, Mistral, Llama, Groq, Cohere, Bedrock, Ollama, DeepSeek, and more
pip install semantica[graph-neo4j]          # Neo4j graph store (LPG)
pip install semantica[graph-falkordb]       # FalkorDB graph store (LPG)
pip install semantica[graph-apache-age]     # Apache AGE graph store (LPG)
pip install semantica[graph-amazon-neptune] # AWS Neptune graph store (LPG)
# RDF triple stores (Blazegraph, Apache Jena, Eclipse RDF4J) need no extra:
# semantica.triplet_store talks SPARQL over HTTP using the core `requests` dependency
pip install semantica[vectorstore-qdrant]   # Qdrant vector store
pip install semantica[vectorstore-pinecone] # Pinecone vector store
pip install semantica[db-snowflake]         # Snowflake
pip install semantica[db-databricks]        # Databricks (SDK + SQL connector)
pip install semantica[ingest-parquet]       # Parquet / PyArrow
pip install semantica[ingest-arrow]        # Apache Arrow, Feather, IPC
pip install semantica[viz]                  # HTML interactive visualization
pip install semantica[watch]                # Directory file watcher
```

For production deployments, use Docker or Kubernetes rather than a local `pip install`. Set `SEMANTICA_SECRET_KEY`, configure a persistent LPG graph store (Neo4j / FalkorDB / Apache AGE / AWS Neptune) and/or RDF triple store (Blazegraph / Apache Jena / Eclipse RDF4J), and point the vector store at a hosted backend (Qdrant / Pinecone). See [ARCHITECTURE.md](ARCHITECTURE.md) for the full deployment topology.

```bash
# From source
git clone https://github.com/semantica-agi/semantica.git
cd semantica && pip install -e ".[dev]" && pytest tests/
```

---

## Enterprise

On-premises deployment · Private cloud · Custom domain implementations · SLA-backed support · Professional services for regulated industries (finance, healthcare, legal, government).

**[getsemantica.ai](https://getsemantica.ai/)** for enterprise solutions and pricing.

---

## Community & Support

| | |
| --- | --- |
| **Discord** | [discord.gg/sV34vps5hH](https://discord.gg/sV34vps5hH): real-time help, showcases, and announcements |
| **GitHub Discussions** | [Q&A and feature requests](https://github.com/semantica-agi/semantica/discussions) |
| **GitHub Issues** | [Bug reports](https://github.com/semantica-agi/semantica/issues) |
| **Documentation** | [docs.getsemantica.ai](https://docs.getsemantica.ai/) |
| **Cookbook** | [Runnable Jupyter notebooks](https://github.com/semantica-agi/semantica/tree/main/cookbook) |
| **Changelog** | [CHANGELOG.md](CHANGELOG.md) · [Release Notes](RELEASE_NOTES.md) |

---

## Star History

<a href="https://www.star-history.com/?repos=semantica-agi%2Fsemantica&type=date&legend=top-left">
 <picture>
   <source media="(prefers-color-scheme: dark)" srcset="https://api.star-history.com/chart?repos=semantica-agi/semantica&type=date&theme=dark&legend=top-left" />
   <source media="(prefers-color-scheme: light)" srcset="https://api.star-history.com/chart?repos=semantica-agi/semantica&type=date&legend=top-left" />
   <img alt="Star History Chart" src="https://api.star-history.com/chart?repos=semantica-agi/semantica&type=date&legend=top-left" />
 </picture>
</a>

---

## Contributors

<div align="center">

[![Contributors](https://contrib.rocks/image?repo=semantica-agi/semantica&max=500)](https://github.com/semantica-agi/semantica/graphs/contributors)

</div>

---

## Contributing

All contributions are welcome: bug fixes, features, tests, and documentation.

1. Fork the repo and create a branch
2. `pip install -e ".[dev]"`
3. Write tests alongside your changes (`pytest tests/`)
4. Open a PR and tag `@KaifAhmad1` for review

See [CONTRIBUTING.md](CONTRIBUTING.md) for full guidelines.

---

<div align="center">

MIT License · Built by [Semantica](https://github.com/semantica-agi)

[GitHub](https://github.com/semantica-agi/semantica) &nbsp;·&nbsp;
[Discord](https://discord.gg/sV34vps5hH) &nbsp;·&nbsp;
[Twitter/X](https://x.com/BuildSemantica) &nbsp;·&nbsp;
[Website](https://getsemantica.ai/) &nbsp;·&nbsp;
[Docs](https://docs.getsemantica.ai/) &nbsp;·&nbsp;
[PyPI](https://pypi.org/project/semantica/)

If this project helps you build better AI, a star means a lot.

**[⭐ Star on GitHub →](https://github.com/semantica-agi/semantica)**

[English](https://readme-i18n.com/semantica-agi/semantica?lang=en) · [Deutsch](https://readme-i18n.com/semantica-agi/semantica?lang=de) · [Français](https://readme-i18n.com/semantica-agi/semantica?lang=fr) · [Español](https://readme-i18n.com/semantica-agi/semantica?lang=es) · [Italiano](https://readme-i18n.com/semantica-agi/semantica?lang=it) · [Português](https://readme-i18n.com/semantica-agi/semantica?lang=pt) · [العربية](https://readme-i18n.com/semantica-agi/semantica?lang=ar) · [اردو](https://readme-i18n.com/semantica-agi/semantica?lang=ur) · [हिन्दी](https://readme-i18n.com/semantica-agi/semantica?lang=hi) · [中文](https://readme-i18n.com/semantica-agi/semantica?lang=zh) · [日本語](https://readme-i18n.com/semantica-agi/semantica?lang=ja) · [한국어](https://readme-i18n.com/semantica-agi/semantica?lang=ko)

</div>
