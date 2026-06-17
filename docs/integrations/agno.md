---
title: "Agno Integration"
description: "Wire Semantica's semantic intelligence stack into Agno multi-agent teams via five focused components."
icon: "robot"
---

> Five drop-in components that bring Semantica's KG, vector memory, and decision intelligence into any Agno agent or team.


## Installation

```bash
# Core integration
pip install "semantica[agno]"

# With a graph store backend
pip install "semantica[agno,graph-neo4j]"
pip install "semantica[agno,graph-falkordb]"

# Full stack
pip install "semantica[agno,graph-neo4j,vectorstore-pgvector]"
```


## Components at a Glance

<CardGroup cols={2}>
  <Card title="AgnoContextStore" icon="database">
    `AgentMemory(db=…)` — Replaces Agno's flat storage with hybrid vector + context graph memory. Adds decision tracking and precedent search to any agent.
  </Card>
  <Card title="AgnoKnowledgeGraph" icon="diagram-project">
    `Agent(knowledge=…)` — Documents flow through the full Semantica extraction pipeline into a queryable `ContextGraph` with multi-hop GraphRAG.
  </Card>
  <Card title="AgnoDecisionKit" icon="list-check">
    `Agent(tools=[…])` — 6 decision intelligence tools: record decisions, find precedents, trace causal chains, analyze impact, check policies, summarize history.
  </Card>
  <Card title="AgnoKGToolkit" icon="wrench">
    `Agent(tools=[…])` — 7 KG construction tools: extract entities, extract relations, add to graph, query graph, find related, infer facts, export subgraph.
  </Card>
  <Card title="AgnoSharedContext" icon="users">
    Team-level — A single `ContextGraph` shared across all agents. Each agent gets a role-scoped view via `bind_agent()`. Writes are tagged by role.
  </Card>
</CardGroup>


## Component Details

<Tabs>
  <Tab title="AgnoContextStore">
    Replaces Agno's flat conversation storage with a hybrid **vector + context graph** memory store. Implements `agno.memory.db.base.MemoryDb`.

    ```python
    from agno.agent import Agent
    from agno.memory import AgentMemory
    from agno.models.openai import OpenAIChat
    from semantica.context import ContextGraph
    from semantica.vector_store import VectorStore
    from integrations.agno import AgnoContextStore

    store = AgnoContextStore(
        vector_store=VectorStore(backend="faiss"),
        knowledge_graph=ContextGraph(advanced_analytics=True),
        decision_tracking=True,
        graph_expansion=True,
        session_id="user_session_42",
    )

    agent = Agent(
        model=OpenAIChat(id="gpt-4o"),
        memory=AgentMemory(db=store),
        description="A financially aware assistant with persistent decision intelligence.",
    )
    ```

    | Method | Description |
    | :-------- | :------------- |
    | `upsert_memory()` | Store text in `AgentContext` (vector index + graph node) |
    | `read_memories()` | Hybrid retrieval: vector similarity + graph hop expansion |
    | `record_decision()` | Record a structured decision with reasoning and outcome |
    | `find_precedents()` | Return semantically similar historical decisions |
  </Tab>
  <Tab title="AgnoKnowledgeGraph">
    Gives Agno agents a queryable `ContextGraph` instead of a flat document store. Ingested documents pass through the full Semantica extraction pipeline.

    ```python
    from agno.agent import Agent
    from agno.models.openai import OpenAIChat
    from semantica.kg import GraphBuilder
    from semantica.semantic_extract import NERExtractor, RelationExtractor
    from integrations.agno import AgnoKnowledgeGraph

    kg = AgnoKnowledgeGraph(
        graph_builder=GraphBuilder(),
        ner_extractor=NERExtractor(),
        relation_extractor=RelationExtractor(),
    )

    kg.load("regulatory_docs/", recursive=True)
    kg.load(texts=["Basel IV capital requirements apply from January 2026."])

    agent = Agent(model=OpenAIChat(id="gpt-4o"), knowledge=kg, search_knowledge=True)
    ```

    **Ingestion:** `parse → NER → relation extract → graph build → vector index`

    **Search:** `vector retrieval → entity lookup → graph hop expansion → context injection`

    ```python
    ctx = kg.get_graph_context("Basel IV")
    # Returns a text summary of the entity's immediate neighbourhood
    ```
  </Tab>
  <Tab title="AgnoDecisionKit">
    Exposes Semantica's decision intelligence as native Agno tools.

    ```python
    from agno.agent import Agent
    from agno.models.openai import OpenAIChat
    from semantica.context import AgentContext
    from integrations.agno import AgnoDecisionKit

    ctx   = AgentContext(decision_tracking=True)
    agent = Agent(
        model=OpenAIChat(id="gpt-4o"),
        tools=[AgnoDecisionKit(context=ctx)],
        show_tool_calls=True,
    )
    agent.print_response("Should we approve this mortgage application?")
    ```

    | Tool | Description |
    | :------ | :------------- |
    | `record_decision` | Record a decision with reasoning, outcome, and confidence |
    | `find_precedents` | Search for similar past decisions |
    | `trace_causal_chain` | Trace causal chain of a decision |
    | `analyze_impact` | Assess downstream influence of a decision |
    | `check_policy` | Validate decision against policy rules |
    | `get_decision_summary` | Summarise decision history by category |
  </Tab>
  <Tab title="AgnoKGToolkit">
    Lets agents actively build and query the context graph during reasoning.

    ```python
    from agno.agent import Agent
    from agno.models.openai import OpenAIChat
    from integrations.agno import AgnoKGToolkit

    agent = Agent(
        model=OpenAIChat(id="gpt-4o"),
        tools=[AgnoKGToolkit()],
        show_tool_calls=True,
    )
    ```

    | Tool | Description |
    | :------ | :------------- |
    | `extract_entities` | Extract named entities from text |
    | `extract_relations` | Extract relationships between entities |
    | `add_to_graph` | Add entities / relations to the context graph |
    | `query_graph` | Query the graph (natural-language or Cypher) |
    | `find_related` | Find concepts related to a given entity |
    | `infer_facts` | Apply rules to infer new facts from the graph |
    | `export_subgraph` | Export a subgraph as RDF / JSON-LD |
  </Tab>
  <Tab title="AgnoSharedContext">
    A single `ContextGraph` shared across an Agno `Team`. Each agent gets a role-scoped view via `bind_agent()`. Writes are tagged by role.

    ```python
    from agno.agent import Agent
    from agno.team import Team
    from agno.models.openai import OpenAIChat
    from semantica.context import ContextGraph
    from semantica.vector_store import VectorStore
    from integrations.agno import AgnoSharedContext, AgnoDecisionKit, AgnoKGToolkit

    shared = AgnoSharedContext(
        vector_store=VectorStore(backend="faiss"),
        knowledge_graph=ContextGraph(advanced_analytics=True),
        decision_tracking=True,
    )

    research_agent = Agent(
        name="Researcher",
        model=OpenAIChat(id="gpt-4o"),
        memory=shared.bind_agent("researcher"),
        tools=[AgnoKGToolkit(context=shared)],
    )
    decision_agent = Agent(
        name="Analyst",
        model=OpenAIChat(id="gpt-4o"),
        memory=shared.bind_agent("analyst"),
        tools=[AgnoDecisionKit(context=shared)],
    )

    team = Team(
        name="Research & Decision Team",
        agents=[research_agent, decision_agent],
        mode="coordinate",
    )
    ```

    ```python
    decision_id = shared.record_decision(
        category="strategy",
        scenario="Expand to EU market",
        reasoning="Strong demand signals from Q1 survey",
        outcome="approved",
        confidence=0.87,
        agent_role="cfo",
    )
    precedents = shared.find_precedents("market expansion")
    insights   = shared.get_shared_insights()
    ```
  </Tab>
</Tabs>


## API Reference

```python
from integrations.agno import (
    AgnoContextStore,    # MemoryDb implementation
    AgnoKnowledgeGraph,  # AgentKnowledge implementation
    AgnoDecisionKit,     # Decision intelligence Toolkit
    AgnoKGToolkit,       # Knowledge graph Toolkit
    AgnoSharedContext,   # Team-level shared context
    AGNO_AVAILABLE,      # bool — True if agno is installed
)
```

All five classes are usable without `agno` installed — they carry the full Semantica API and degrade gracefully.


## See Also

<CardGroup cols={2}>
  <Card title="Context Module" icon="brain" href="../reference/context">
    AgentContext and ContextGraph backing the integration.
  </Card>
  <Card title="Knowledge Graph" icon="diagram-project" href="../reference/kg">
    KG construction used by AgnoKnowledgeGraph.
  </Card>
  <Card title="LLMs" icon="microchip" href="../reference/llms">
    Configure LLM providers for Agno agents.
  </Card>
  <Card title="Vector Store" icon="vector-square" href="../reference/vector_store">
    Vector backend for AgnoContextStore.
  </Card>
</CardGroup>
