# Semantica × LangChain Integration

Connect [LangChain](https://github.com/langchain-ai/langchain) — the most popular LLM application framework — to Semantica's knowledge-graph, GraphRAG, and decision-intelligence stack.

Exposes framework-native retriever, vector store, and tools that wrap Semantica's core (`ContextGraph`, `HybridSearch`, `AgentContext`) and degrade gracefully if LangChain isn't installed.

---

## Installation

```bash
pip install semantica[langchain]
```

---

## 1. SemanticaRetriever (GraphRAG)

Replace flat vector similarity retrieval with walking graph edges from top vector hits (GraphRAG-style retrieval).

```python
from integrations.langchain import SemanticaRetriever
from semantica.context import ContextGraph

# Create graph
graph = ContextGraph()
graph.add_node("Agentic AI", "Concept")
graph.add_node("Semantica", "Framework")
graph.add_edge("Semantica", "Agentic AI", "enables")

# Instantiate LangChain Retriever
retriever = SemanticaRetriever(graph=graph, hops=2, top_k=5)

# Use in any LangChain chain
docs = retriever.invoke("AI Frameworks")
for doc in docs:
    print(f"Content: {doc.page_content} | Meta: {doc.metadata}")
```

---

## 2. SemanticaVectorStore

A thin adapter over `semantica.vector_store.VectorStore` implementing LangChain's standard `VectorStore` interface, enabling drop-in usage anywhere FAISS/Chroma/Pinecone is expected.

```python
from integrations.langchain import SemanticaVectorStore
from langchain_core.embeddings import FakeEmbeddings

embeddings = FakeEmbeddings(size=768)

vector_store = SemanticaVectorStore.from_texts(
    texts=["Semantica brings accountability to AI agents.", "LangChain builds LLM chains."],
    embedding=embeddings,
    backend="faiss",
    dimension=768
)

# Search
results = vector_store.similarity_search("AI accountability", k=1)
print(results[0].page_content)
```

---

## 3. Agent Tools (KG & Decision Intelligence)

Use `SemanticaKGTool` and `SemanticaDecisionTool` directly with any LangChain/LangGraph agent.

```python
from integrations.langchain import SemanticaKGTool, SemanticaDecisionTool
from langchain.agents import create_react_agent

kg_toolkit = SemanticaKGTool()
decision_toolkit = SemanticaDecisionTool()

# Retrieve list of LangChain tools
tools = kg_toolkit.get_tools() + decision_toolkit.get_tools()

# Pass to your tool-calling agent
# agent = create_react_agent(llm, tools)
```

Exposed KG Tools:
- `extract_entities` — Named entity recognition from text
- `extract_relations` — Extraction of relationships/triplets
- `add_to_graph` — Manually add nodes/edges to the context graph
- `query_graph` — Query the graph using keyword/Cypher search
- `find_related` — Retrieve related concepts in the graph
- `infer_facts` — Derive new facts from rules
- `export_subgraph` — Export subgraph as RDF/JSON-LD

Exposed Decision Tools:
- `record_decision` — Record a decision with reasoning and confidence
- `find_precedents` — Find similar past decisions
- `trace_causal_chain` — Trace causal lineage of a decision
- `analyze_impact` — Assess downstream decision influence
- `check_policy` — Validate decisions against policy rules
- `get_decision_summary` — Summarise decision history
