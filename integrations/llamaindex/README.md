# Semantica × LlamaIndex

Drop Semantica into LlamaIndex graph pipelines: a `PropertyGraphStore` adapter,
a hybrid retriever, and agent tools.

## Install

```bash
pip install semantica[llamaindex]
```

## Components

### `SemanticaPropertyGraphStore`
A `PropertyGraphStore` backed by `semantica.context.ContextGraph`. Construct a
`PropertyGraphIndex` directly over a Semantica graph:

```python
from llama_index.core.indices.property_graph import PropertyGraphIndex
from integrations.llamaindex import SemanticaPropertyGraphStore
from semantica.context import ContextGraph

store = SemanticaPropertyGraphStore(ContextGraph())
index = PropertyGraphIndex.from_documents(docs, property_graph_store=store)
```

Entities/relations extracted by LlamaIndex land in a Semantica-managed graph —
with Semantica's export, analytics and reasoning available on top.

### `SemanticaRetriever`
A `BaseRetriever` combining vector similarity with multi-hop graph expansion:

```python
from llama_index.core.query_engine import RetrieverQueryEngine
from integrations.llamaindex import SemanticaRetriever

retriever = SemanticaRetriever(graph, hybrid=hybrid_search, top_k=10, hops=2)
engine = RetrieverQueryEngine.from_args(retriever)
```

### `semantica_kg_tools()`
`FunctionTool` adapters for `FunctionAgent` / `ReActAgent` — KG query and
decision recording:

```python
from llama_index.core.agent import FunctionAgent
from integrations.llamaindex import semantica_kg_tools

agent = FunctionAgent.from_tools(semantica_kg_tools(graph), llm=llm)
```

## Graceful degradation

Without `llama-index-core` installed, the module imports fine (the
`LLAMAINDEX_AVAILABLE` flag is `False`), adapters fall back to plain dicts,
and `semantica_kg_tools()` returns an empty list — no hard dependency.
