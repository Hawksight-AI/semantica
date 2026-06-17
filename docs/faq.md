---
title: "FAQ"
description: "Common questions about Semantica: installation, features, integrations, and troubleshooting."
icon: "circle-question"
---

<Info>
  Use **Ctrl+F** / **Cmd+F** to search this page. Common jumps: [Installation](#installation) · [Data & Features](#data--features) · [Troubleshooting](#troubleshooting)
</Info>

## Quick Answers

| Question | Answer |
| :-------- | :------ |
| License? | MIT: free forever, no paywalled features |
| Python version? | 3.8+ (3.11+ recommended) |
| API key required? | Optional: pattern extraction works with no keys |
| Works with LangChain / LlamaIndex? | Yes: Semantica is a layer on top, not a replacement |
| Production-ready? | Yes: 1,000+ tests, v0.5.0 ships with 12 security fixes |
| Latest version? | **v0.5.0** (May 2026) |
| Local LLMs? | Yes: Ollama via LiteLLM, HuggingFaceLLM for air-gapped |


## General

<AccordionGroup>

<Accordion title="What is Semantica?" icon="info-circle">

Semantica is an open-source framework for building context graphs and decision intelligence layers for AI. It transforms unstructured data: documents, APIs, databases: into structured knowledge graphs with full provenance tracking, making AI systems explainable and auditable.

It's not a replacement for LangChain or LlamaIndex. It's the **accountability layer** that goes on top: recording decisions, tracing facts to sources, and making reasoning transparent.

</Accordion>

<Accordion title="What can I build with Semantica?" icon="hammer">

- Knowledge graphs from documents and multi-source data
- GraphRAG systems with graph-grounded retrieval and source attribution
- AI agents with structured decision history and semantic memory
- Compliance-ready pipelines with W3C PROV-O lineage (HIPAA, SOX, GDPR, FDA 21 CFR Part 11)
- Temporal graphs that track how facts change over time
- Ontology-driven knowledge bases with SHACL validation

</Accordion>

<Accordion title="What makes Semantica different from LangChain or LlamaIndex?" icon="scale-balanced">

Most frameworks stop at retrieval or generation. Semantica adds an **accountability layer**: every decision is recorded, every fact links to a source, and every reasoning step is explainable. It's designed for environments where you need to audit *why* an AI reached a conclusion: not just what it said.

Semantica works alongside these frameworks, not against them.

</Accordion>

<Accordion title="Is Semantica free?" icon="tag">

Yes: MIT licensed, no vendor lock-in, no paywalled features. Some capabilities require third-party API keys (e.g., OpenAI embeddings, Groq inference), but Semantica itself is always free and open source.

</Accordion>

<Accordion title="What's the latest version?" icon="star">

**v0.5.0**: released May 2026.

Highlights: Ontology Hub, Distance Intelligence, Parquet/XML ingestion, 12 security fixes, Graph Explorer redesign, NER gateway fix.

```bash
pip install --upgrade semantica
```

</Accordion>

</AccordionGroup>


## Installation

<AccordionGroup>

<Accordion title="How do I install Semantica?" icon="download">

```bash
pip install semantica
```

See [Installation](installation) for virtual environment setup, optional extras (`[gpu]`, `[all]`, provider-specific), and platform-specific troubleshooting.

</Accordion>

<Accordion title="What Python version do I need?" icon="python">

Python **3.8 or higher**. Python 3.11+ is recommended for best performance and compatibility.

</Accordion>

<Accordion title="The [all] extra fails on Windows" icon="windows">

This was a known bug: fixed in **v0.5.0**. Upgrade:

```bash
pip install --upgrade semantica
```

If you're on an older version, install extras individually: `pip install "semantica[core]"`, then add `[llm-openai]`, `[gpu]`, etc.

</Accordion>

<Accordion title="What are the system requirements?" icon="server">

| Requirement | Minimum | Recommended |
| :----------- | :------- | :----------- |
| Python | 3.8 | 3.11+ |
| RAM | 4 GB | 16 GB+ |
| Storage | 2 GB | 20 GB+ |
| GPU | Optional | CUDA for embeddings and ML models |

</Accordion>

</AccordionGroup>


## Data & Features

<AccordionGroup>

<Accordion title="What data sources does Semantica support?" icon="database">

| Category | Sources |
| :-------- | :------- |
| **Files** | PDF, DOCX, HTML, JSON, CSV, Excel, PPTX, Parquet (v0.5.0), XML (v0.5.0), archives |
| **Web** | `WebIngestor` crawl, RSS feeds, sitemaps |
| **Databases** | PostgreSQL, MySQL, Snowflake via `DBIngestor` / `SnowflakeIngestor` |
| **NoSQL** | MongoDB via `MongoIngestor`, DuckDB via `DuckDBIngestor` |
| **Streams** | Kafka, real-time ingestion via `StreamIngestor` |
| **Protocols** | MCP (Model Context Protocol) via `MCPIngestor` |
| **Cloud** | Google Drive via `GDriveIngestor`, HuggingFace datasets |

</Accordion>

<Accordion title="Can I use my own models?" icon="robot">

Yes. Semantica supports:

- **Custom NER and extraction models**: register via `method_registry`
- **Custom embedding models**: any model with a `.encode()` interface
- **Custom LLM providers**: via LiteLLM (100+ models) or direct provider integration
- **Custom pipeline processors**: register via `PluginRegistry`

</Accordion>

<Accordion title="Does Semantica support GPUs?" icon="bolt">

Yes. When available, GPUs are used automatically for embedding generation, ML model inference, and vector operations. Install GPU support:

```bash
pip install "semantica[gpu]"
```

This includes PyTorch with CUDA, FAISS GPU, and CuPy.

</Accordion>

<Accordion title="How does Semantica handle large datasets?" icon="layer-group">

- **Batching**: process documents in configurable chunks to control memory usage
- **Parallel processing**: `Pipeline(workers=N)` runs extraction steps concurrently
- **Delta processing**: update graphs incrementally without full recompute on new data
- **Persistent backends**: swap in-memory NetworkX for Neo4j, FalkorDB, or Apache AGE for large-scale production graphs

</Accordion>

<Accordion title="What is Temporal Intelligence?" icon="clock">

`TemporalKnowledgeGraph` attaches `valid_from` / `valid_until` windows to nodes and edges, enabling point-in-time queries and historical analysis. Supports all 13 Allen interval algebra relations and OWL-Time export.

```python
from semantica.kg import TemporalKnowledgeGraph

tkg = TemporalKnowledgeGraph()
tkg.add_temporal_triple("A", "caused", "B", valid_from="2024-01", valid_until="2024-06")
snapshot = tkg.query_at_time("2024-03")
```

Available since v0.4.0.

</Accordion>

<Accordion title="What is the Ontology Hub?" icon="sitemap">

A visual browser UI for the full ontology lifecycle: launched via `semantica.explorer`. Includes:

- **Visual editor**: create and edit classes, properties, and relationships
- **SHACL Studio**: author, validate, and export SHACL shapes
- **Alignment authoring**: map concepts across ontologies
- **Health dashboard**: coverage, consistency, and constraint violation metrics
- **Version control**: diff and history for ontology changes

Available since v0.5.0.

</Accordion>

<Accordion title="What is Distance Intelligence?" icon="compass">

Semantic neighborhood exploration for any entity in the graph. Returns structured proximity data with distance band classification.

- N×N distance matrices across a set of entities
- Ego-mode visualization centered on a single node
- Distance bands: `near` / `mid` / `far` based on embedding thresholds
- Embedding cache optimization for repeated queries

Available since v0.5.0.

</Accordion>

<Accordion title="My NER extractor silently falls back to pattern mode on a custom gateway" icon="triangle-exclamation">

Fixed in **v0.5.0**. The `response_format=json_object` parameter is now conditionally omitted for incompatible gateways, with a plain `generate()` plus JSON parsing fallback applied automatically. Upgrade to fix:

```bash
pip install --upgrade semantica
```

</Accordion>

</AccordionGroup>


## Technical

<AccordionGroup>

<Accordion title="What graph databases are supported?" icon="diagram-project">

- **Neo4j**: industry standard, Cypher query language
- **FalkorDB**: Redis-protocol, ultra-low latency
- **Apache AGE**: PostgreSQL extension, OpenCypher
- **Amazon Neptune**: managed AWS, SPARQL and Gremlin
- **NetworkX**: in-memory, for development and small graphs

</Accordion>

<Accordion title="What export formats are available?" icon="file-export">

RDF (Turtle, JSON-LD, N-Triples, XML), Apache Parquet, ArangoDB AQL, Apache Arrow, LPG, CSV, YAML, OWL ontologies, and distance matrices.

</Accordion>

<Accordion title="What vector stores are supported?" icon="server">

FAISS, Pinecone, Weaviate, Qdrant, Milvus, PgVector, and in-memory. All backends share the same `VectorStore` API: swap with one line change.

</Accordion>

<Accordion title="What LLM providers are supported?" icon="microchip">

Groq, OpenAI, Anthropic, Google Gemini, Ollama (fully local), DeepSeek, Novita AI, LiteLLM (100+ models via a single interface), and any OpenAI-compatible gateway.

</Accordion>

<Accordion title="Is Semantica production-ready?" icon="shield-check">

Yes. v0.5.0 ships with:

- 1,000+ passing tests across Python 3.8–3.12
- `PipelineValidator` and `FailureHandler` with exponential backoff and configurable retry policies
- W3C PROV-O provenance tracking across all modules
- Change management with SHA-256 checksums and full audit trails
- 12 security vulnerability fixes: eval injection, pickle deserialization, SQL injection, XXE, SSRF, ReDoS, path traversal, and more

</Accordion>

</AccordionGroup>


## Troubleshooting

<AccordionGroup>

<Accordion title="ModuleNotFoundError: No module named 'semantica'" icon="xmark-circle">

Ensure the correct Python environment is active:

```bash
pip list | grep semantica
pip install --upgrade semantica
```

</Accordion>

<Accordion title="Installation fails with dependency errors" icon="xmark-circle">

```bash
pip install --upgrade pip wheel
pip install semantica
```

If `[all]` fails on Windows, install extras individually instead.

</Accordion>

<Accordion title="Memory errors during processing" icon="memory">

Reduce batch sizes, enable streaming ingestion, or switch to a persistent graph backend:

```python
from semantica.graph_store import FalkorDBStore
store   = FalkorDBStore(host="localhost", port=6379)
builder = GraphBuilder(merge_entities=True, graph_store=store)
```

</Accordion>

<Accordion title="Slow embedding or inference" icon="gauge-high">

Install GPU support and confirm CUDA is available:

```bash
pip install "semantica[gpu]"
nvidia-smi  # confirm GPU is visible
```

</Accordion>

<Accordion title="Unicode / cp1252 crash on Windows" icon="windows">

Fixed in **v0.5.0**. Upgrade, or set the encoding environment variable for older versions:

```bash
pip install --upgrade semantica
# or for older versions:
set PYTHONIOENCODING=utf-8
```

</Accordion>

</AccordionGroup>


## Support

- [Discord](https://discord.gg/sV34vps5hH) — Community chat and live support.
- [GitHub Issues](https://github.com/semantica-agi/semantica/issues) — Bug reports and feature requests.
- [Contributing](contributing-guide) — Help improve Semantica.
