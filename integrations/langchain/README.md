# Semantica × LangChain

Drop Semantica into existing LangChain / LangGraph pipelines: GraphRAG-style
retrieval, a `VectorStore` adapter, and agent tools.

## Install

```bash
pip install semantica[langchain]
# or just the core adapter dependency:
pip install langchain-core
```

## Retriever (GraphRAG)

```python
from integrations.langchain import SemanticaRetriever
from semantica.context import ContextGraph
from semantica.vector_store import HybridSearch

graph = ContextGraph()
hybrid = HybridSearch()

retriever = SemanticaRetriever(graph=graph, hybrid=hybrid, hops=2, top_k=10)

# Use with any LangChain chain that accepts a retriever:
from langchain.chains import RetrievalQA

qa = RetrievalQA.from_chain_type(llm=llm, retriever=retriever)
```

Hybrid search seeds retrieval; then graph edges are walked `hops` steps so
results go beyond flat vector similarity.

## VectorStore

```python
from integrations.langchain import SemanticaVectorStore

store = SemanticaVectorStore(hybrid=hybrid)
store.add_texts(["document one", "document two"], metadatas=[{"source": "a"}, {"source": "b"}])
docs = store.similarity_search("document", k=2)
docs, scores = store.similarity_search_with_score("document", k=2)
```

## Agent tools (LangGraph / tool-calling agents)

```python
from integrations.langchain import SemanticaKGTool, SemanticaDecisionTool
from langgraph.prebuilt import create_react_agent

tools = [
    SemanticaKGTool(graph),
    SemanticaDecisionTool(graph),
]
agent = create_react_agent(model, tools)
```

- `semantica_query_graph` — query the shared context graph (keyword / NL)
- `semantica_query_decisions` — search the recorded decision log

## Compatibility

- Requires `langchain-core >= 0.3`.
- All classes degrade gracefully when `langchain-core` is absent: they remain
  importable (carrying the full Semantica API), and `build()` returns `None`,
  so agents can branch on `LANGCHAIN_AVAILABLE`.
