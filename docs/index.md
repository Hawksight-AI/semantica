---
title: "Welcome to Semantica"
description: "The Context and Semantic Layer for AI in High-Stakes Domains: Context Graphs · Decision Intelligence · Full Provenance"
---

```bash
pip install semantica
```

Most AI agents run on embeddings, not meaning. A similarity score has no structure, no relationships, and no way to explain why a result came back.

Semantica is the semantic and context layer underneath your LLM, vector store, and agent framework: deterministic infrastructure, not a model. Graph construction, reasoning, and provenance all run without an LLM in the loop. It turns fragmented enterprise data into a structured, queryable context graph and knowledge graph, governed by ontologies, taxonomies, and controlled vocabularies (OWL, SHACL, SKOS), so your data's meaning is explicit rather than approximated by an embedding.

Provenance and audit trails aren't a bolt-on. They fall out naturally once your data has that structure, so the same graph that powers retrieval and reasoning also gives you a straight answer when a regulator asks why.

## What you get

- **[Context graphs](/guides/context-graphs)**: a persistent, queryable graph of everything your agent knows, decides, and reasons about
- **Decision intelligence**: `record_decision()` captures the full lifecycle and causal chain of every decision
- **[Full provenance](/guides/provenance)**: every fact links back to its source, W3C PROV-O compliant and audit-ready for HIPAA, SOX, and GDPR
- **[Explainable reasoning](/guides/reasoning)**: forward chaining, Datalog, and SPARQL, each with a derivation path you can inspect
- **Temporal intelligence**: Allen interval algebra and point-in-time snapshots, so the graph knows not just *what* but *when*

<Tip>
  Works alongside any LLM provider and any agent framework, and ingests directly from enterprise data platforms like Databricks, SAP, Salesforce, and Snowflake. Add it to an existing stack without changing your architecture.
</Tip>

## Try it

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

## Start here

<Steps>
  <Step title="Install">
    ```bash
    pip install semantica
    ```
    Optional extras: `[all]`, `[neo4j]`, `[pinecone]`. See [Installation](/installation).
  </Step>
  <Step title="Build a pipeline">
    Follow the [Quickstart](/quickstart) to ingest documents, extract entities, build a graph, and record a decision in 5 minutes.
  </Step>
  <Step title="Learn the model">
    [Core Concepts](/concepts) covers knowledge graphs vs. vector stores, GraphRAG, and how provenance and decisions fit together.
  </Step>
  <Step title="Go deep">
    Every module has a [reference page](/reference/context) with full API docs and runnable examples.
  </Step>
</Steps>

More: the [Cookbook](/cookbook) for real-world notebooks, [Discord](https://discord.gg/sV34vps5hH) for help.

<Accordion title="Full module list">
  `semantica.ingest`, `semantica.parse`, `semantica.split`, `semantica.normalize`, `semantica.semantic_extract`, `semantica.kg`, `semantica.ontology`, `semantica.reasoning`, `semantica.embeddings`, `semantica.vector_store`, `semantica.graph_store`, `semantica.triplet_store`, `semantica.context`, `semantica.provenance`, `semantica.change_management`, `semantica.deduplication`, `semantica.conflicts`, `semantica.export`, `semantica.visualization`, `semantica.pipeline`, `semantica.seed`, `semantica.llms`, `semantica.mcp_server`, `semantica.explorer`, `semantica.evals`, `semantica.utils`, `semantica.core`. See the [API Reference](/reference/context) for full docs on each.
</Accordion>
