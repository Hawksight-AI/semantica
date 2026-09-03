---
title: "Semantica"
description: "The Context and Semantic Layer for AI in High-Stakes Domains: Context Graphs · Decision Intelligence · Full Provenance"
---

```bash
pip install semantica
```

Most AI agents store embeddings, not meaning. They can't say why a fact was recalled, where it came from, or what led to a decision. In healthcare, finance, legal, and government, that lack of a traceable record blocks production deployment.

Semantica is the context and semantic layer for AI in high-stakes domains, sitting beneath your existing agent framework. It doesn't replace LangChain or LlamaIndex; it makes their outputs traceable.


## What Most AI Stacks Are Missing

**No memory structure.** Agents store embeddings, not meaning.
- No way to ask *why* a fact was recalled
- No link from a recalled fact back to its source document
- Context is a black box that resets on every run

**No decision trail.** Agents act continuously but record nothing.
- No history to hand to a regulator or auditor
- No way to replay or reproduce a past decision
- Debugging means re-running, not reviewing

**No provenance.** Outputs can't be traced to source facts.
- A hard compliance blocker in healthcare, finance, and legal
- No lineage from inference back to the original document
- No way to demonstrate what the agent actually relied on

**No reasoning transparency.** Black-box answers with no explanation.
- No way to validate the reasoning path
- No way to contest a specific conclusion
- No basis for improving or correcting future behavior

**No conflict detection.** Contradictory facts silently coexist in vector stores.
- No detection when two sources disagree
- Outputs become inconsistent and unpredictable over time
- Silent failures compound as the knowledge base grows


## What Semantica Adds to Your Stack

Semantica gives every agent the infrastructure it needs to be accountable, and it drops into an existing setup in minutes.

**Context Graphs.** A structured, queryable graph of everything your agent knows, decides, and reasons about.
- Persistent across agent runs, with no context loss between sessions
- Queryable with SPARQL and full graph algorithms
- Temporal model with `valid_from` / `valid_until` on nodes and edges
- Point-in-time snapshots of the full knowledge state

**Decision Intelligence.** Every decision is a first-class object in your system.
- `record_decision()` captures full lifecycle and causal chain
- Hybrid precedent search over past decisions for consistency
- `analyze_decision_impact()` shows downstream consequences
- Causal chain visualization from trigger to outcome

**Full Provenance.** Every fact links to its source document and ingestion event.
- W3C PROV-O compliant lineage across all modules
- Full traceability from raw input to final inference
- `recorded_at` stamping with OWL-Time export
- Audit-ready for HIPAA, SOX, GDPR, FDA 21 CFR Part 11

**Reasoning Engines.** Explainable reasoning paths, not black boxes.
- Forward chaining, Rete, deductive, abductive
- SPARQL query-based inference over RDF graphs
- Datalog with recursive Horn clause rules
- Every conclusion backed by a traceable derivation path

**Temporal Intelligence.** Your graph knows not just *what*, but *when*.
- Allen interval algebra covering all 13 temporal relations
- Point-in-time queries over historical graph states
- Temporal provenance stamping on every fact
- OWL-Time export for standards-compliant archiving

**Ontology Hub.** Full ontology lifecycle in the browser.
- Visual editor for schema design and editing
- SHACL Studio for constraint authoring and validation
- Alignment authoring across multiple ontologies
- Health dashboard and version control built in

<Tip>
  Works alongside any LLM provider and any agent framework. Add it to an existing stack without changing your architecture.
</Tip>

<img src="/assets/img/diagrams/architecture-overview.svg" alt="Semantica four-layer architecture: Ingestion → Processing → Intelligence → Application" style={{ width: '100%', borderRadius: '12px', margin: '24px 0' }} />


## See It In Action

One pip install. A few lines to connect your agent. Everything else becomes traceable.

```bash
pip install semantica
```

<CodeGroup>

```python OpenAI
from semantica.context import AgentContext, ContextGraph
from semantica.vector_store import VectorStore
from semantica.llms import OpenAI

context = AgentContext(
    vector_store=VectorStore(backend="faiss", dimension=1536),
    knowledge_graph=ContextGraph(advanced_analytics=True),
    decision_tracking=True,
    llm=OpenAI(model="gpt-4o"),
)

context.store("GPT-4 outperforms GPT-3.5 on reasoning benchmarks by 40%")

decision_id = context.record_decision(
    category="model_selection",
    scenario="Choose LLM for production reasoning pipeline",
    reasoning="GPT-4 benchmark advantage justifies 3x cost increase",
    outcome="selected_gpt4",
    confidence=0.91,
)

precedents = context.find_precedents("model selection reasoning", limit=5)
influence  = context.analyze_decision_influence(decision_id)
```

```python Anthropic
from semantica.context import AgentContext, ContextGraph
from semantica.vector_store import VectorStore
from semantica.llms import LiteLLM
import os

context = AgentContext(
    vector_store=VectorStore(backend="faiss", dimension=1024),
    knowledge_graph=ContextGraph(advanced_analytics=True),
    decision_tracking=True,
    llm=LiteLLM(model="anthropic/claude-opus-4-7", api_key=os.getenv("ANTHROPIC_API_KEY")),
)

context.store("Claude excels at long-context reasoning and code generation")

decision_id = context.record_decision(
    category="model_selection",
    scenario="Choose LLM for document analysis pipeline",
    reasoning="Claude's 200k context window eliminates chunking overhead",
    outcome="selected_claude",
    confidence=0.94,
)

precedents = context.find_precedents("document analysis model", limit=5)
```

```python Ollama (Local)
from semantica.context import AgentContext, ContextGraph
from semantica.vector_store import VectorStore
from semantica.llms import LiteLLM

context = AgentContext(
    vector_store=VectorStore(backend="faiss", dimension=768),
    knowledge_graph=ContextGraph(advanced_analytics=True),
    decision_tracking=True,
    llm=LiteLLM(model="ollama/llama3.2", base_url="http://localhost:11434"),
)

# Fully local: no data leaves your infrastructure
context.store("Local LLMs enable air-gapped compliance deployments")

decision_id = context.record_decision(
    category="deployment_model",
    scenario="Choose inference strategy for on-prem environment",
    reasoning="Air-gap requirement eliminates cloud API options",
    outcome="local_inference",
    confidence=0.99,
)
```

</CodeGroup>

- [Full Quickstart](/quickstart): step-by-step pipeline walkthrough
- [Cookbook](/cookbook): 40+ real-world Jupyter notebooks
- [Join Discord](https://discord.gg/sV34vps5hH): community chat and support


## Industry Use Cases

Semantica is used in domains where every decision must be explainable and every fact must be traceable.

<Warning>
  **This is system-level explainability, not foundation-model explainability.** Semantica does not expose, reconstruct, or explain what happens *inside* the LLM/foundation model. Its internal reasoning or chain-of-thought stays opaque, as it does for any external system. What Semantica explains is *outside* the model: the context and data fed in, the decision produced, its provenance, the relevant relationships, the policies applied, and the full execution trail. See [Core Concepts](/concepts) for the full scope note.
</Warning>

**Healthcare & Life Sciences**
- Clinical decision support with full audit trails
- Drug interaction and contraindication graphs
- Patient safety event tracking and root-cause analysis
- HIPAA-compliant provenance chains out of the box

**Finance & Risk**
- Fraud detection knowledge graphs
- Risk assessment trails built to survive an audit
- SOX, GDPR, and MiFID II compliance infrastructure
- Model decision lineage for regulatory reporting

**Legal & Compliance**
- Evidence-backed research with every cited fact provenance-linked
- Contract analysis with traceable clause extraction
- Regulatory change tracking across jurisdictions
- Full reasoning paths ready for court-admissible documentation

**Cybersecurity**
- Threat attribution graphs linking actors, TTPs, and indicators
- Incident response timelines with full event provenance
- Security audit trails across the complete kill chain
- MITRE ATT&CK-aligned knowledge graph integration

**Government & Defense**
- Policy decision trails from brief to outcome
- Classified information handling with provenance chains
- Chain-of-custody scrutiny for intelligence reporting
- Air-gapped deployment with local LLM support

**Critical Infrastructure**
- Power grid state tracking with temporal intelligence
- Transportation safety event graphs
- Emergency response coordination with decision audit trails
- Consequence modeling for high-stakes operational decisions


## Start Here

<Steps>
  <Step title="Install Semantica">
    ```bash
    pip install semantica
    ```
    See [Installation](/installation) for optional extras (`[all]`, `[neo4j]`, `[pinecone]`) and environment setup.
  </Step>
  <Step title="Run the Quickstart">
    Build a complete knowledge graph pipeline in [5 minutes](/quickstart):
    - Ingest documents from any source
    - Extract entities and relationships
    - Build and query the graph
    - Record and trace a decision
  </Step>
  <Step title="Learn the mental model">
    [Core Concepts](/concepts) covers:
    - Knowledge graphs vs. vector stores: when to use each
    - What GraphRAG is and how Semantica implements it
    - How provenance and decision tracking work together
    - The context and semantic layer architecture
  </Step>
  <Step title="Go deep on any module">
    Every module has a dedicated [reference page](/reference/context) with:
    - Full class and method documentation
    - Parameter tables with types and defaults
    - Runnable code examples for each feature
  </Step>
</Steps>

- [Installation](/installation): get Semantica installed in under a minute
- [Quickstart](/quickstart): build a complete knowledge graph pipeline in 5 minutes
- [Core Concepts](/concepts): the mental model behind the API
- [API Reference](/reference/context): exact module, class, and method details
- [Cookbook](/cookbook): domain notebooks for real-world use cases
- [Changelog](https://github.com/semantica-agi/semantica/releases): release history


## Full Capabilities

<AccordionGroup>

<Accordion title="Context & Decision Intelligence" icon="brain">

### Context Graphs

- Structured, persistent graph of entities, relationships, and decisions
- Temporal model with `valid_from` / `valid_until` on every node and edge
- Point-in-time queries across historical graph states
- Distance Intelligence: semantic neighborhoods and N×N distance matrices

### Decision Tracking

- `record_decision()` with full lifecycle management and causal chains
- Hybrid similarity search over past decisions for consistency enforcement
- `analyze_decision_impact()` and `analyze_decision_influence()` for consequence modeling
- Ego-mode exploration for targeted neighborhood investigation

</Accordion>

<Accordion title="Knowledge Engineering" icon="diagram-project">

### Entity & Relation Extraction

- Named entity recognition: pattern, ML, or LLM methods
- Typed triplet extraction via LLM or rule-based pipelines
- Event extraction with temporal and causal linking

### Ontology & Schema

- Ontology Hub: visual editor, SHACL Studio, alignments, health dashboard
- Deduplication v2: `blocking_v2`, `hybrid_v2`, `semantic_v2`: up to 7x faster
- Datalog reasoning: recursive Horn clause rules with fixpoint semantics
- SPARQL reasoning: query-based inference over RDF graphs

</Accordion>

<Accordion title="Provenance & Auditability" icon="shield-check">

### Lineage Tracking

- W3C PROV-O lineage across all modules: every fact has a source
- `recorded_at` stamping with full OWL-Time export
- Change management with SHA-256 checksums and version control
- Full audit trails from ingestion event to final inference

### Compliance Infrastructure

- HIPAA: patient data handling with audit-ready provenance chains
- SOX / MiFID II: financial decision records with full traceability
- GDPR: data lineage for subject access and right-to-erasure workflows
- FDA 21 CFR Part 11: electronic records and signature compliance

</Accordion>

<Accordion title="Data Ingestion & Export" icon="database">

### Ingestion Formats

- Documents: PDF, DOCX, HTML, PPTX, Docling layout analysis
- Structured data: JSON, CSV, Excel, Parquet, XML
- Sources: web crawl, SQL, Snowflake, feeds, email, code repositories, MCP

### Vector Stores

- FAISS, Pinecone, Weaviate, Qdrant, Milvus, PgVector, in-memory

### Graph Stores

- Neo4j, FalkorDB, Apache AGE, Amazon Neptune

### Export Formats

- RDF: Turtle, JSON-LD, N-Triples, RDF/XML
- Tabular: Parquet, CSV, Arrow
- Graph: GraphML, GEXF, DOT, ArangoDB AQL
- Ontology: OWL, SKOS, SHACL

</Accordion>

</AccordionGroup>


## Module Reference

| Module | What it provides |
| :-------- | :----------------- |
| `semantica.context` | Context graphs, agent memory, decision tracking, causal analysis, precedent search |
| `semantica.kg` | KG construction, graph algorithms, temporal model, Allen interval algebra |
| `semantica.semantic_extract` | NER, relation extraction, event extraction, triplet generation |
| `semantica.reasoning` | Forward chaining, Rete, deductive, abductive, SPARQL, Datalog |
| `semantica.ontology` | SHACL, SKOS, alignments, diff/migration, auto-generation, OWL/RDF |
| `semantica.explorer` | FastAPI Knowledge Explorer, Ontology Hub, Distance Intelligence, SHACL Studio |
| `semantica.mcp_server` | MCP stdio server: 15 tools for Claude Desktop, VS Code, Cursor, Windsurf, Cline |
| `semantica.vector_store` | FAISS, Pinecone, Weaviate, Qdrant, Milvus, PgVector |
| `semantica.graph_store` | Neo4j, FalkorDB, Apache AGE, Amazon Neptune |
| `semantica.triplet_store` | In-memory and persistent RDF triple store with SPARQL |
| `semantica.ingest` | Files, web, feeds, databases, Snowflake, Parquet, XML, MCP |
| `semantica.parse` | Document parsing: PDF, DOCX, HTML, PPTX, Docling layout analysis |
| `semantica.split` | Text chunking: sentence, paragraph, token, semantic boundary strategies |
| `semantica.normalize` | Text normalization, entity canonicalization, whitespace and encoding cleanup |
| `semantica.embeddings` | Sentence-Transformers, FastEmbed, OpenAI, BGE, Ollama local embeddings |
| `semantica.pipeline` | Pipeline DSL, parallel workers, retry policies, failure handling |
| `semantica.export` | RDF, Parquet, ArangoDB AQL, CSV, OWL, Arrow, GraphML, GEXF, DOT |
| `semantica.visualization` | Programmatic graph rendering: force, hierarchical, circular, spring layouts |
| `semantica.deduplication` | Entity deduplication v1/v2, similarity scoring, blocking, merging |
| `semantica.conflicts` | Conflict detection and resolution across overlapping knowledge sources |
| `semantica.provenance` | W3C PROV-O lineage tracking, source attribution, audit trails |
| `semantica.change_management` | Version control with SHA-256 checksums, diff, rollback |
| `semantica.llms` | Groq, OpenAI, Anthropic, Gemini, Ollama, DeepSeek, Novita AI, LiteLLM, HuggingFace |
| `semantica.seed` | Foundation graph seeding from CSV, JSON, SQL, API, and RDF sources |
| `semantica.evals` | Evaluation harness: KG quality, extraction F1, pipeline benchmarking, regression tracking |
| `semantica.core` | Orchestration, ConfigManager, LifecycleManager, PluginRegistry, MethodRegistry |
| `semantica.utils` | Logging, validation, progress tracking, hash utilities, nested dict helpers |


## Why Semantica?

**Open Source, MIT.** No vendor lock-in, no paywalled features.
- Full source available on GitHub
- Every line auditable by your security team
- Fork, extend, and self-host with no restrictions
- No telemetry, no usage reporting

**Production Ready.** Built for teams that can't afford surprises.
- 1,000+ passing tests with full regression coverage
- `PipelineValidator` catches configuration errors at startup
- `FailureHandler` with exponential backoff and dead-letter queues
- Ongoing security hardening, with fixes shipped in every release ([CHANGELOG](https://github.com/semantica-agi/semantica/blob/main/CHANGELOG.md))

**Modular by Design.** Import only what you need.
- Use `NERExtractor` without a graph store
- Use `ContextGraph` without vector storage
- Every component independently swappable and testable
- No framework lock-in, and works with any agent stack
