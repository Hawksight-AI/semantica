---
title: "CrewAI Integration"
description: "Give CrewAI crews a shared semantic knowledge graph, decision intelligence, and graph-based retrieval via three drop-in components."
icon: "users"
---

> Three drop-in components that bring Semantica's knowledge graph and decision intelligence into any CrewAI crew.

## Installation

```bash
pip install "semantica[crewai]"
```

Requires `crewai >= 0.80.0`. If `crewai` is not installed, the integration still imports — every class carries the full Semantica API and degrades gracefully, but cannot be passed to a `Crew`.

## Components at a Glance

- **SemanticaKGTool** — `Agent(tools=[…])`: 5 KG construction/query actions: extract entities, extract relations, add to graph, query graph, find related.
- **SemanticaDecisionTool** — `Agent(tools=[…])`: 5 decision intelligence actions: record decisions, find precedents, trace causal chains, analyze impact, check policies.
- **SemanticaKnowledgeSource** — `Crew(knowledge_sources=[…])`: Serializes a `ContextGraph` into CrewAI knowledge storage so every agent gets retrieval access to the graph.

## Component Details

<Tabs>
  <Tab title="SemanticaKGTool">
    Lets agents actively **build and query** a shared `ContextGraph` mid-reasoning.

    ```python
    from crewai import Agent, Crew, Task
    from semantica.context import ContextGraph
    from integrations.crewai import SemanticaKGTool

    graph = ContextGraph()

    analyst = Agent(
        role="Knowledge Analyst",
        goal="Build and explore a knowledge graph from documents",
        backstory="You map entities and relationships into a shared graph.",
        tools=[SemanticaKGTool(graph=graph)],
    )

    crew = Crew(
        agents=[analyst],
        tasks=[Task(
            description="Extract and link key entities from the brief",
            expected_output="JSON",
            agent=analyst,
        )],
    )
    crew.kickoff()
    ```

    | Tool | Description |
    | :------ | :------------- |
    | `extract_entities` | Extract named entities from `text` |
    | `extract_relations` | Extract relationships between entities in `text` |
    | `add_to_graph` | Extract entities/relations from `text` and add them to the shared graph |
    | `query_graph` | Keyword-search the graph by node id, type, and content using `query` |
    | `find_related` | Find concepts related to `entity` within `hops` hops |

    All actions return JSON so agents get parseable results.

    **Sharing a graph:** the tool reads/writes whatever `graph` you pass in. When no `graph` is given, a fresh in-memory `ContextGraph()` is created (and a warning is logged) — two tool instances that each auto-create their own graph do **not** share knowledge. Pass the same `ContextGraph` to every agent that must share state.
  </Tab>
  <Tab title="SemanticaDecisionTool">
    Exposes Semantica's decision intelligence as a native CrewAI tool, backed by `AgentContext`.

    ```python
    from crewai import Agent, Crew, Task
    from integrations.crewai import SemanticaDecisionTool

    planner = Agent(
        role="Decision Planner",
        goal="Make grounded, precedented decisions",
        backstory="You record decisions and validate them against policy.",
        tools=[SemanticaDecisionTool()],
    )

    crew = Crew(agents=[planner], tasks=[...])
    ```

    When no `AgentContext` is passed, one is created in-memory with `decision_tracking=True` and its own `ContextGraph`, so decision actions work out of the box (a warning is logged — pass the same `AgentContext` to every agent that must share decision state). Missing optional fields in `record_decision` fall back to `category="general"`, `reasoning="agent decision"`, and `outcome="recorded"`. `find_precedents` returns up to `max_precedents` results. If a knowledge graph cannot trace causality, `trace_causal_chain` returns an explicit error rather than substituting similarity-based results.

    | Tool | Description |
    | :------ | :------------- |
    | `record_decision` | Record a decision with reasoning, outcome, and confidence |
    | `find_precedents` | Search for similar past decisions |
    | `trace_causal_chain` | Trace the causal chain from a decision |
    | `analyze_impact` | Assess downstream influence of a decision |
    | `check_policy` | Validate a proposed decision against policy rules |
  </Tab>
  <Tab title="SemanticaKnowledgeSource">
    Gives **every agent in the crew** retrieval access to a `ContextGraph`.

    ```python
    from crewai import Agent, Crew, Task
    from semantica.context import ContextGraph
    from integrations.crewai import SemanticaKnowledgeSource

    graph = ContextGraph()
    graph.add_node(node_id="privacy", node_type="policy", content="...")

    researcher = Agent(
        role="Policy Researcher",
        goal="Answer questions from the knowledge base",
        backstory="You retrieve from graph knowledge to answer accurately.",
    )

    crew = Crew(
        agents=[researcher],
        tasks=[...],
        knowledge_sources=[SemanticaKnowledgeSource(graph=graph)],
    )
    ```

    On kickoff the graph's nodes and edges are serialized, chunked, and stored through CrewAI's knowledge pipeline.

    > **Embedder required:** storing chunks goes through CrewAI's knowledge pipeline, which needs an embedder to be configured. Set `Crew(embedder=...)` (or provide the default credentials CrewAI falls back to, e.g. `OPENAI_API_KEY`). If no working embedder is configured, storage fails, an ERROR is logged, and agents will retrieve **nothing** — the crew still runs, but its knowledge queries return empty.

    **Compatibility:** CrewAI's `BaseKnowledgeSource` contract changed between `0.80.x` and current releases (`load_content()` → `validate_content()`/`aadd()`). `SemanticaKnowledgeSource` implements both legacy and current methods, so it works across `crewai>=0.80.0`.
  </Tab>
</Tabs>

## Checkpoints & Serialization

CrewAI serializes tools and knowledge sources to JSON for checkpointing/resume. Live Semantica state (`ContextGraph`, `AgentContext`, extractors) is **excluded from that serialization** — a restored tool/source comes back with a fresh in-memory `ContextGraph` and logs a warning. Until you re-attach the live graph/context, the restored objects answer queries against an **empty** graph, so re-wire them after resuming (e.g. `restored_tool.graph = live_graph`) before agents continue.

## API Reference

```python
from integrations.crewai import (
    SemanticaKGTool,          # BaseTool: KG construction/query actions
    SemanticaDecisionTool,    # BaseTool: decision intelligence actions
    SemanticaKnowledgeSource, # BaseKnowledgeSource: graph → crew knowledge
    CREWAI_AVAILABLE,         # bool: True if crewai is installed
)
```

All three classes are usable without `crewai` installed: they carry the full Semantica API and degrade gracefully.

## See Also

- [Context Module](../reference/context) — AgentContext and ContextGraph backing the integration.
- [Semantic Extraction](../reference/semantic_extract) — NERExtractor / RelationExtractor used by SemanticaKGTool.
- [LLMs](../reference/llms) — Configure LLM providers for your crew's agents.
- [Vector Store](../reference/vector_store) — Vector backend used by SemanticaDecisionTool.
