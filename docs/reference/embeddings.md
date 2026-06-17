---
title: "Embeddings Module"
description: "Text and graph embedding generation: FastEmbed, Sentence-Transformers, OpenAI, BGE: with pooling strategies and provider-agnostic API."
icon: "vector-square"
---

**`semantica.embeddings`** converts text and graph structures into **dense vector representations**:

- Provider-agnostic API: FastEmbed (default, ONNX, no GPU), Sentence-Transformers, OpenAI, BGE
- Powers semantic search, entity resolution, GraphRAG retrieval, and deduplication
- `GraphEmbeddingManager` embeds KG nodes and edges for graph database backends
- Five pooling strategies: Mean (default), Max, CLS, Attention, Hierarchical
- `check_available_providers()` shows which backends are installed in your environment


## Why Embeddings Matter

Raw text can't be compared mathematically. Embeddings translate meaning into geometry: two semantically similar sentences produce vectors that are close together in high-dimensional space, even when they share no words.

Semantica uses embeddings for:

- **Semantic search**: find knowledge graph nodes by meaning, not just keywords
- **Entity resolution**: detect that "Apple Inc." and "Apple Computer" refer to the same entity
- **Deduplication**: `semantic_v2` strategy measures entity similarity via embedding distance
- **GraphRAG retrieval**: hybrid vector + graph traversal for grounded LLM answers
- **Semantic chunking**: detect topic shift boundaries in `TextSplitter(method="semantic_transformer")`

## Exported Classes

| Class | Role |
| :--- | :--- |
| `EmbeddingGenerator` | Provider-agnostic entry point: handles batching and provider selection |
| `TextEmbedder` | Text embedding with automatic batch processing; default uses FastEmbed |
| `GraphEmbeddingManager` | Embed KG nodes and edges for GraphRAG and graph databases |
| `VectorEmbeddingManager` | Prepare and format embeddings for vector database backends |
| `OpenAIStore` | OpenAI `text-embedding-3-small` / `text-embedding-3-large` provider |
| `BGEStore` | BAAI/bge models via `sentence-transformers` |
| `FastEmbedStore` | ONNX-accelerated local embeddings: no CUDA **required** |
| `LlamaStore` | Placeholder store: not production-ready; do not use for embeddings |
| `MeanPooling` | Default pooling strategy: best for retrieval and clustering |

## What You Get

- **EmbeddingGenerator** — Main entry point: provider-agnostic, handles batching automatically across all backends.
- **TextEmbedder** — Text-specific with automatic batching and progress tracking. Default method is FastEmbed.
- **GraphEmbeddingManager** — Node and edge embeddings for graph databases: Neo4j, NetworkX, FalkorDB.
- **VectorEmbeddingManager** — Prepare, normalize, and format embeddings for FAISS, Weaviate, Qdrant, and Milvus.
- **Provider Stores** — `OpenAIStore`, `BGEStore`, `FastEmbedStore`, and `ProviderStoreFactory`.
- **Pooling Strategies** — Mean, Max, CLS, Attention, and Hierarchical: control token-to-vector aggregation.

## Provider Setup

<Tabs>
  <Tab title="FastEmbed (default)">
    ONNX-accelerated local embeddings. No GPU required, no API key. Best starting point.

    ```bash
    pip install "semantica[fastembed]"
    ```

    ```python
    from semantica.embeddings import EmbeddingGenerator

    # FastEmbed is the default: no config needed
    generator = EmbeddingGenerator()
    embedding = generator.generate_embeddings("Text about AI")
    ```

    <Check>
      Default model is `BAAI/bge-small-en-v1.5`. Zero cost, zero GPU, works on any machine.
    </Check>

    <Warning>
      **FastEmbed ignores the `device` parameter.** FastEmbed uses ONNX Runtime and manages its own execution providers: passing `device="cuda"` has no effect. Switch to `method="sentence_transformers"` if you need explicit GPU control.
    </Warning>
  </Tab>
  <Tab title="Sentence-Transformers">
    Broad model selection via HuggingFace. Runs locally, no API key.

    ```bash
    pip install semantica  # sentence-transformers included
    ```

    ```python
    from semantica.embeddings import EmbeddingGenerator

    generator = EmbeddingGenerator(config={
        "text": {
            "method": "sentence_transformers",
            "model_name": "all-MiniLM-L6-v2",
        }
    })
    ```

    Popular models: `all-MiniLM-L6-v2` (fast, small), `all-mpnet-base-v2` (balanced), `BAAI/bge-large-en-v1.5` (high accuracy).

    <Warning>
      **Sequence length limits.** Most sentence-transformers models have a 512-token limit. Text beyond that is silently truncated. Use `TextSplitter(method="hierarchical")` + `HierarchicalPooling` for long documents.
    </Warning>
  </Tab>
  <Tab title="BGE">
    BAAI/bge models via sentence-transformers. State-of-the-art retrieval performance, runs locally.

    ```bash
    pip install semantica
    ```

    ```python
    from semantica.embeddings import BGEStore, EmbeddingGenerator

    store     = BGEStore(model="BAAI/bge-large-en-v1.5")
    embedding = store.embed("Text about AI")

    # Or switch model on an existing EmbeddingGenerator
    generator = EmbeddingGenerator()
    generator.set_text_model("sentence_transformers", "BAAI/bge-large-en-v1.5")
    ```
  </Tab>
  <Tab title="OpenAI">
    Cloud embeddings via OpenAI API. Highest quality, requires API key.

    ```bash
    pip install "semantica[llm-openai]"
    export OPENAI_API_KEY="sk-..."
    ```

    ```python
    import os
    from semantica.embeddings import OpenAIStore

    store = OpenAIStore(
        api_key=os.getenv("OPENAI_API_KEY"),
        model="text-embedding-3-small",   # or text-embedding-3-large
    )
    embedding = store.embed("Text about AI")
    ```

    | Model | Dimensions | Best for |
    | :---- | :--------- | :-------- |
    | `text-embedding-3-small` | 1536 | Cost-efficient retrieval |
    | `text-embedding-3-large` | 3072 | Highest accuracy workloads |
  </Tab>
</Tabs>

Check which providers are installed in your environment:

```python
from semantica.embeddings import check_available_providers

providers = check_available_providers()
# → {"sentence_transformers": True, "fastembed": True, "openai": False}
```

## Getting Started

`EmbeddingGenerator` is the fastest path to embeddings: the default method is FastEmbed (ONNX, no GPU needed):

```python
from semantica.embeddings import EmbeddingGenerator

# Default: FastEmbed with BAAI/bge-small-en-v1.5
generator = EmbeddingGenerator()

# Embed a single text
embedding = generator.generate_embeddings("Text about AI")

# Embed a batch
embeddings = generator.generate_embeddings(["Text about AI", "Machine learning concepts"])

# Compare two embeddings (cosine similarity: 0.0 to 1.0)
score = generator.compare_embeddings(embeddings[0], embeddings[1], method="cosine")
print(f"Similarity: {score:.3f}")
```

<Tip>
  **Always use the same model for indexing and querying.** Vectors from different models are not comparable: they live in different vector spaces. Switching models requires re-embedding your entire corpus.
</Tip>

To switch provider after construction:

```python
# Switch to a sentence-transformers model
generator.set_text_model("sentence_transformers", "all-MiniLM-L6-v2")

# Switch to BGE large
generator.set_text_model("sentence_transformers", "BAAI/bge-large-en-v1.5")
```

## Quick Start

<Steps>
  <Step title="Install and initialize a provider">
    ```python
    from semantica.embeddings import EmbeddingGenerator

    # Default: FastEmbed, free, runs locally with no GPU
    generator = EmbeddingGenerator()

    # Use sentence-transformers instead
    generator = EmbeddingGenerator(config={"text": {"method": "sentence_transformers", "model_name": "all-MiniLM-L6-v2"}})
    ```
  </Step>
  <Step title="Generate embeddings">
    ```python
    # Single text → 1D array
    embedding = generator.generate_embeddings("Text about AI")

    # Batch → 2D array (n_texts, dim)
    embeddings = generator.generate_embeddings(["Text about AI", "Machine learning concepts"])
    ```
  </Step>
  <Step title="Compute similarity">
    ```python
    # Cosine similarity: 0.0 (unrelated) to 1.0 (identical meaning)
    score = generator.compare_embeddings(embeddings[0], embeddings[1], method="cosine")
    print(f"Similarity: {score:.3f}")
    ```
  </Step>
  <Step title="Prepare for a vector database">
    ```python
    from semantica.embeddings import VectorEmbeddingManager
    import numpy as np

    manager = VectorEmbeddingManager()

    embeddings = np.array([...], dtype=np.float32)
    metadata   = [{"text": "doc 1"}, {"text": "doc 2"}]

    result = manager.prepare_for_vector_db(embeddings, metadata=metadata, backend="faiss")
    # result["vectors"]  → normalized float32 array
    # result["ids"]      → ["vec_0", "vec_1", ...]
    # result["metadata"] → formatted metadata list
    ```
  </Step>
</Steps>

## Supported Models

| Provider | Model | Dimension | Speed | Best For |
| :-------- | :----- | :--------- | :----- | :-------- |
| `fastembed` | `BAAI/bge-small-en-v1.5` | 384 | Very fast | **Default**: CPU-optimised, no GPU **required** |
| `sentence_transformers` | `all-MiniLM-L6-v2` | 384 | Fast | Good balance of speed and quality |
| `sentence_transformers` | `all-mpnet-base-v2` | 768 | Medium | Higher retrieval quality |
| `sentence_transformers` | `BAAI/bge-large-en-v1.5` | 1024 | Medium | State-of-the-art retrieval accuracy |
| `openai` | `text-embedding-3-small` | 1536 | API | Cost-effective OpenAI embedding |
| `openai` | `text-embedding-3-large` | 3072 | API | Highest quality via OpenAI API |

## EmbeddingGenerator

<Tabs>
  <Tab title="FastEmbed (default)">
    ```python
    from semantica.embeddings import EmbeddingGenerator

    # Default: FastEmbed with BAAI/bge-small-en-v1.5
    generator = EmbeddingGenerator()
    embeddings = generator.generate_embeddings(texts)
    similarity = generator.compare_embeddings(embeddings[0], embeddings[1])
    ```

    **Best for:** CPU-only production, lowest latency without GPU. Default: works out of the box.
  </Tab>
  <Tab title="Sentence-Transformers">
    ```python
    from semantica.embeddings import EmbeddingGenerator

    generator = EmbeddingGenerator()
    generator.set_text_model("sentence_transformers", "all-MiniLM-L6-v2")
    embeddings = generator.generate_embeddings(texts)
    ```

    **Best for:** higher-quality retrieval when GPU is available, or when fine-tuned models are needed.
  </Tab>
  <Tab title="OpenAI">
    ```python
    from semantica.embeddings import OpenAIStore
    import os

    store     = OpenAIStore(api_key=os.getenv("OPENAI_API_KEY"), model="text-embedding-3-small")
    embedding = store.embed("Hello world")
    ```

    **Best for:** highest quality (`text-embedding-3-large`), or matching an existing OpenAI pipeline.
  </Tab>
  <Tab title="GPU acceleration">
    ```python
    from semantica.embeddings import EmbeddingGenerator

    # Use CUDA via sentence-transformers
    generator = EmbeddingGenerator(config={"text": {"method": "sentence_transformers", "device": "cuda"}})

    # Apple Silicon (M1/M2/M3)
    generator = EmbeddingGenerator(config={"text": {"method": "sentence_transformers", "device": "mps"}})
    ```

    GPU is only applicable with sentence-transformers. FastEmbed uses ONNX and does not use `device`.
  </Tab>
</Tabs>

### Constructor Parameters

| Parameter | Type | Default | Description |
| :--------- | :---- | :------- | :----------- |
| `config` | `dict` | `None` | Config dict; `config["text"]` is passed to `TextEmbedder` |
| `**kwargs` | | | Additional key/value config merged into `config` |

Use `generator.set_text_model(method, model_name)` to switch the embedding model after construction.

## TextEmbedder

Direct text embedding with batch processing:

```python
from semantica.embeddings import TextEmbedder

# Default: FastEmbed with BAAI/bge-small-en-v1.5
embedder = TextEmbedder()

# Single text → 1D array
embedding = embedder.embed_text("A knowledge graph connects entities with typed relationships.")

# Batch → 2D array (n_texts, dim)
embeddings = embedder.embed_batch(["First text", "Second text", "Third text"])

# Per-sentence embeddings
sentence_embeddings = embedder.embed_sentences("First sentence. Second sentence.")

# Get embedding dimension
dim = embedder.get_embedding_dimension()
```

### TextEmbedder Constructor Parameters

| Parameter | Type | Default | Description |
| :--------- | :---- | :------- | :----------- |
| `model_name` | `str` | `"BAAI/bge-small-en-v1.5"` | Model name to load |
| `method` | `str` | `"fastembed"` | Embedding method: `"fastembed"` or `"sentence_transformers"` |
| `device` | `str` | `"cpu"` | Device for sentence-transformers: `"cpu"`, `"cuda"`, `"mps"`. Ignored for FastEmbed. |
| `normalize` | `bool` | `True` | L2-normalize output vectors |

**Key behaviours:**
- If FastEmbed or sentence-transformers is unavailable, falls back to a 128-dimensional hash-based embedding. Hash embeddings are deterministic but not semantic: do not use in production.
- Large batches are chunked internally by the underlying library to avoid OOM.

<Warning>
  **Dimension mismatch.** The dimension you pass to your vector store must exactly match your embedding model's output. `BAAI/bge-small-en-v1.5` → 384, `all-MiniLM-L6-v2` → 384, `all-mpnet-base-v2` → 768, `BAAI/bge-large-en-v1.5` → 1024. Check with `embedder.get_embedding_dimension()` before creating the store.
</Warning>

<Tip>
  **Fallback embeddings are not semantic.** If neither FastEmbed nor sentence-transformers loads successfully, TextEmbedder silently falls back to 128-dimensional SHA-256 hash embeddings. These are deterministic but carry no semantic meaning. Check `embedder.get_method()`: if it returns `"fallback"`, install your intended provider.
</Tip>

## Provider Stores

Use provider stores directly when you need fine-grained control over a single backend:

```python
from semantica.embeddings import (
    OpenAIStore, BGEStore, FastEmbedStore,
    ProviderStoreFactory,
)
import os

# OpenAI
store     = OpenAIStore(api_key=os.getenv("OPENAI_API_KEY"), model="text-embedding-3-small")
embedding = store.embed("Hello world")

# BGE (Sentence-Transformers wrapper): pass model_name= not model=
store     = BGEStore(model_name="BAAI/bge-large-en-v1.5")
embedding = store.embed("Hello world")

# FastEmbed: ONNX runtime, no CUDA required
store     = FastEmbedStore(model_name="BAAI/bge-small-en-v1.5")
embedding = store.embed("Hello world")
# FastEmbedStore also has an efficient batch method
embeddings = store.embed_batch(["text1", "text2", "text3"])

# Auto-select from a name string: useful in config-driven pipelines
# Supported providers: "openai", "bge", "fastembed"
store = ProviderStoreFactory.create(provider="bge", model_name="BAAI/bge-large-en-v1.5")
```

<Note>
  `LlamaStore` exists in the module but is a placeholder: it does not connect to Ollama and always raises `ProcessingError` at embed time. Do not use it in production.
</Note>

<Warning>
  **LlamaStore is not functional.** `LlamaStore` exists in the module but does not connect to Ollama. It always raises `ProcessingError` at embed time. Use `FastEmbedStore` for local ONNX-based embeddings or `BGEStore` for sentence-transformers-based local embeddings instead.
</Warning>

## Pooling Strategies

Pooling aggregates a set of embeddings into a single vector: useful when you have multiple chunk embeddings to combine:

<Tabs>
  <Tab title="MeanPooling (default)">
    ```python
    from semantica.embeddings import MeanPooling

    pooler = MeanPooling()
    pooled = pooler.pool(token_embeddings)   # shape: (hidden_dim,)
    ```

    **Best for:** retrieval, semantic search, and clustering: averages all contributions.
  </Tab>
  <Tab title="MaxPooling">
    ```python
    from semantica.embeddings import MaxPooling

    pooler = MaxPooling()
    pooled = pooler.pool(token_embeddings)
    ```

    **Best for:** capturing the presence of any feature: takes the max activation per dimension.
  </Tab>
  <Tab title="CLSPooling">
    ```python
    from semantica.embeddings import CLSPooling

    pooler = CLSPooling()
    pooled = pooler.pool(token_embeddings)
    ```

    **Best for:** classification-style tasks; models explicitly trained with CLS pooling (BERT).
  </Tab>
  <Tab title="HierarchicalPooling">
    ```python
    from semantica.embeddings import HierarchicalPooling

    pooler = HierarchicalPooling()
    # chunk_size is passed at pool time, not at construction
    pooled = pooler.pool(token_embeddings, chunk_size=10)
    ```

    **Best for:** long documents: chunk-level mean pooling, then global mean pooling across chunks.
  </Tab>
  <Tab title="Strategy Comparison">

    | Strategy | When to Use |
    | :-------- | :----------- |
    | `mean` | Default for retrieval, semantic search, and clustering |
    | `max` | When you want to capture the presence of any feature, not average presence |
    | `cls` | Classification-style tasks; models explicitly trained with CLS pooling (BERT) |
    | `attention` | When token importance varies significantly; slower but more accurate |
    | `hierarchical` | Long documents with many chunks; combines chunk-level then global pooling |

    ```python
    from semantica.embeddings import PoolingStrategyFactory

    pooler = PoolingStrategyFactory.create(strategy="mean")
    ```

  </Tab>
</Tabs>

## GraphEmbeddingManager

Embed graph nodes and edges for storage in graph databases:

```python
from semantica.embeddings import GraphEmbeddingManager

manager = GraphEmbeddingManager()

entities = [
    {"id": "e1", "text": "Apple Inc.", "type": "Organization"},
    {"id": "e2", "text": "Tim Cook",   "type": "Person"},
]
relationships = [
    {"source": "e2", "target": "e1", "type": "CEO_OF"}
]

# Embed entities → dict of {id: np.ndarray}
node_embeddings = manager.embed_entities(entities)

# Embed relationships → dict of {id: np.ndarray}
edge_embeddings = manager.embed_relationships(relationships)

# Or prepare everything at once for a graph DB backend
result = manager.prepare_for_graph_db(entities, relationships, backend="neo4j")
# result["node_embeddings"] → {id: np.ndarray}
# result["edge_embeddings"] → {id: np.ndarray}
# result["nodes"]           → entities with "embedding" field added
# result["edges"]           → relationships with "embedding" field added
```

**Supported backends:** `"neo4j"`, `"networkx"`, `"falkordb"`

## VectorEmbeddingManager

Prepare and validate embeddings for vector database storage:

```python
from semantica.embeddings import VectorEmbeddingManager
import numpy as np

manager    = VectorEmbeddingManager()
embeddings = np.random.rand(5, 384).astype(np.float32)
metadata   = [{"text": f"doc_{i}", "category": "science"} for i in range(5)]

# Prepare for FAISS
result = manager.prepare_for_vector_db(embeddings, metadata=metadata, backend="faiss")
# result["vectors"]  → L2-normalized float32 array
# result["ids"]      → ["vec_0", "vec_1", ...]
# result["metadata"] → formatted metadata list

# Validate dimensions before insertion
is_valid = manager.validate_dimensions(embeddings, backend="milvus")

# Prepare multiple batches at once
combined = manager.batch_prepare([embeddings_a, embeddings_b], backend="qdrant")
```

**Supported backends:** `"faiss"`, `"weaviate"`, `"qdrant"`, `"milvus"`

## Common Workflows

<Tabs>
  <Tab title="Batch Text Embedding">
    ```python
    from semantica.embeddings import TextEmbedder

    embedder = TextEmbedder()   # default: FastEmbed

    texts = [
        "Apple Inc. was founded by Steve Jobs.",
        "Microsoft was co-founded by Bill Gates.",
        "Amazon was started by Jeff Bezos.",
    ]

    # All at once: more efficient than calling embed_text() per item
    embeddings = embedder.embed_batch(texts)
    print(f"Shape: {embeddings.shape}")   # (3, 384)
    ```
  </Tab>
  <Tab title="Provider Comparison">
    ```python
    from semantica.embeddings import check_available_providers, EmbeddingGenerator

    # Check what's installed
    available = check_available_providers()
    # → {"sentence_transformers": True, "fastembed": True, "openai": False}

    # Use the fastest available provider
    generator = EmbeddingGenerator()
    if available["fastembed"]:
        generator.set_text_model("fastembed", "BAAI/bge-small-en-v1.5")
    elif available["sentence_transformers"]:
        generator.set_text_model("sentence_transformers", "all-MiniLM-L6-v2")

    embeddings = generator.generate_embeddings(texts)
    ```
  </Tab>
  <Tab title="Graph Node Embedding">
    ```python
    from semantica.embeddings import GraphEmbeddingManager

    manager  = GraphEmbeddingManager()
    entities = [{"id": "n1", "text": "Python"}, {"id": "n2", "text": "Django"}]

    node_embeddings = manager.embed_entities(entities)
    # {"n1": array([...]), "n2": array([...])}
    ```
  </Tab>
  <Tab title="Similarity Search">
    ```python
    from semantica.embeddings import EmbeddingGenerator, calculate_similarity
    import numpy as np

    generator = EmbeddingGenerator()
    query     = generator.generate_embeddings("knowledge graph databases")
    corpus    = generator.generate_embeddings([
        "graph databases store relationships",
        "relational databases use tables",
        "knowledge graphs model entity relationships",
    ])

    scores = [calculate_similarity(query, doc, method="cosine") for doc in corpus]
    ranked = sorted(zip(scores, range(len(scores))), reverse=True)

    for score, idx in ranked:
        print(f"{score:.3f}  {['graph databases store...', 'relational databases...', 'knowledge graphs...'][idx]}")
    ```
  </Tab>
</Tabs>

## Similarity Computation

```python
from semantica.embeddings import calculate_similarity

# Cosine similarity: direction only, not magnitude; most common for text
score = calculate_similarity(embedding_a, embedding_b, method="cosine")
# → 0.0 (orthogonal / unrelated) to 1.0 (identical direction)

# Euclidean distance converted to similarity
score = calculate_similarity(embedding_a, embedding_b, method="euclidean")
```

## Convenience Functions

```python
from semantica.embeddings import (
    embed_text, generate_embeddings, calculate_similarity,
    pool_embeddings, check_available_providers,
)

# Single text: fastest path
emb = embed_text("Hello world", method="sentence_transformers")

# Batch
embs = generate_embeddings(["text1", "text2"], method="default")

# Pool multiple embeddings into one
pooled = pool_embeddings(embs, method="mean")

# Check which providers are installed
providers = check_available_providers()
# → {"sentence_transformers": True, "fastembed": True, "openai": False}
```

- [Vector Store](vector_store) — Store and search the generated embeddings.
- [Split](split) — Chunk text before embedding for better retrieval quality.
- [KG Module](kg) — Distance Intelligence uses graph embeddings for semantic neighbourhoods.
- [Deduplication](deduplication) — Semantic deduplication uses embedding distance for entity resolution.
