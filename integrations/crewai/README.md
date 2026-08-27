# Semantica × CrewAI

First-class integration between Semantica and [CrewAI](https://github.com/crewAIInc/crewAI) — give your crews a shared semantic knowledge graph, decision intelligence, and graph-based retrieval.

## Installation

```bash
pip install semantica[crewai]
```

Requires `crewai >= 0.80.0`. If `crewai` is not installed, the integration still imports (classes degrade gracefully), but you can't pass the objects to a `Crew`.

> **⚠️ Security note:** crewai hard-requires `chromadb~=1.1.0`, which is currently affected by the unpatched pre-authentication code-injection advisory **CVE-2026-45829** (no fixed release — even the latest chromadb 1.5.9 is affected). Installing `semantica[crewai]` pulls that dependency into your environment. The `crewai` extra is intentionally **not** part of `semantica[all]` for this reason — only install it where you actually use CrewAI, and follow chromadb for a patched release.

## 1. SemanticaKGTool

A `BaseTool` that lets agents **build and query** a shared `ContextGraph` mid-reasoning:

- `extract_entities` — extract named entities from `text`
- `extract_relations` — extract relationships from `text`
- `add_to_graph` — extract entities/relations from `text` and add them to the shared graph
- `query_graph` — keyword-search the graph using `query`
- `find_related` — find concepts related to `entity` within `hops`

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
    tasks=[Task(description="Extract and link key entities from the brief", expected_output="JSON", agent=analyst)],
)
result = crew.kickoff()
```

All actions return JSON, so agents get parseable results.

## 2. SemanticaDecisionTool

A `BaseTool` that wraps `AgentContext` and exposes decision intelligence:

- `record_decision` — record a decision with reasoning and outcome
- `find_precedents` — retrieve past decisions similar to a scenario
- `trace_causal_chain` — trace the causal chain from a decision
- `analyze_impact` — assess downstream influence using graph centrality
- `check_policy` — validate a proposed decision against rule-based policies

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

When no `AgentContext` is passed, one is created in-memory with `decision_tracking=True`.

## 3. SemanticaKnowledgeSource

A `BaseKnowledgeSource` that serializes the current state of a `ContextGraph` (nodes, edges, metadata) into CrewAI's knowledge storage, giving **every agent in the crew** retrieval access to the graph:

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

> **Embedder required:** storing chunks goes through CrewAI's knowledge pipeline, which needs an embedder. Set `Crew(embedder=...)` (or provide CrewAI's default credentials, e.g. `OPENAI_API_KEY`). Without a working embedder, storage fails, an ERROR is logged, and agents retrieve nothing — the crew still runs with empty knowledge queries.

### Compatibility note

CrewAI's `BaseKnowledgeSource` contract changed between `0.80.x` and current releases (`load_content()` → `validate_content()`/`aadd()`). `SemanticaKnowledgeSource` implements both the legacy and current methods, so it works across `crewai>=0.80.0`.

### Sharing state & checkpoints

- Each tool/source holds whatever `graph`/`context` you pass it. When omitted, a fresh in-memory object is created and a warning is logged — instances that auto-create their own state do **not** share knowledge, so pass the same object to every agent that must share.
- Live state (`ContextGraph`, `AgentContext`, extractors) is excluded from CrewAI's JSON serialization. After restoring from a checkpoint, re-attach the live graph/context to the restored objects.
