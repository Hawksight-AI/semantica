---
title: "LangChain Integration"
description: "Drop Semantica into LangChain / LangGraph pipelines via a GraphRAG retriever, VectorStore adapter, and agent tools."
icon: "link"
---

> Three drop-in adapters that bring Semantica's context graph and hybrid search into LangChain chains and LangGraph agents.

## Installation

```bash
pip install "semantica[langchain]"
```

Requires `langchain-core >= 0.3`. If langchain-core is not installed, the integration still imports — every class carries the full Semantica API and degrades gracefully (`build()` returns `None`; branch on `LANGCHAIN_AVAILABLE`).

## Components at a Glance

- **SemanticaRetriever** — `BaseRetriever`: hybrid-search seeds retrieval, then graph edges are walked `hops` steps (default 2) for GraphRAG-style results.
- **SemanticaVectorStore** — `VectorStore`: `add_texts` / `similarity_search` / `similarity_search_with_score` / `from_texts` over `HybridSearch`.
- **SemanticaKGTool** / **SemanticaDecisionTool** — `BaseTool` subclasses: `semantica_query_graph` and `semantica_query_decisions` for LangGraph / tool-calling agents.

## Component Details

<Tabs>
  <Tab title="SemanticaRetriever">
    Hybrid search seeds retrieval; then graph edges are walked `hops` steps so results go beyond flat vector similarity. If hybrid search is omitted or fails, the retriever falls back to a `ContextGraph.query` keyword scan.

    ```python
    from integrations.langchain import SemanticaRetriever
    from semantica.context import ContextGraph
    from semantica.vector_store import HybridSearch

    graph = ContextGraph()
    hybrid = HybridSearch()

    retriever = SemanticaRetriever(graph=graph, hybrid=hybrid, hops=2, top_k=10)

    from langchain.chains import RetrievalQA

    qa = RetrievalQA.from_chain_type(llm=llm, retriever=retriever)
    ```
  </Tab>
  <Tab title="SemanticaVectorStore">
    Drop-in `VectorStore` for RetrievalQA / LCEL chains. `from_texts` requires a pre-configured `hybrid` instance.

    ```python
    from integrations.langchain import SemanticaVectorStore

    store = SemanticaVectorStore(hybrid=hybrid)
    store.add_texts(
        ["document one", "document two"],
        metadatas=[{"source": "a"}, {"source": "b"}],
    )
    docs = store.similarity_search("document", k=2)
    docs, scores = store.similarity_search_with_score("document", k=2)
    ```

    `add_texts` delegates to a Semantica vector store with `add_documents` (pass `vector_store=` to `HybridSearch` or to `SemanticaVectorStore`).
  </Tab>
  <Tab title="Agent tools">
    Instances are LangChain `BaseTool`s and can be passed to an agent directly.
    `.build()` returns the tool, or `None` when langchain-core is absent.

    ```python
    from integrations.langchain import SemanticaKGTool, SemanticaDecisionTool
    from langgraph.prebuilt import create_react_agent

    tools = [
        SemanticaKGTool(graph),
        SemanticaDecisionTool(graph),
    ]
    agent = create_react_agent(model, tools)
    ```

    | Tool | Description |
    | :------ | :------------- |
    | `semantica_query_graph` | Keyword / NL query over the shared context graph |
    | `semantica_query_decisions` | Search the recorded decision log |
  </Tab>
</Tabs>
