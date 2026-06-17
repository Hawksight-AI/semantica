---
title: "Vector Store Module"
description: "Unified interface for FAISS, Pinecone, Weaviate, Qdrant, Milvus, and PgVector with hybrid search."
icon: "database"
---

`semantica.vector_store` provides a unified API for storing and searching vector embeddings across all major backends:

- Swap backends with a one-line change — no application code changes needed
- `HybridSearch` fuses dense vector similarity with metadata filtering via RRF or weighted average
- `NamespaceManager` for multi-tenant structural isolation
- `FAISSStore` with flat, ivf, hnsw, and pq index types
- Batch embed and store with parallel workers; metadata update without re-embedding


## Exported Classes

| Class | Role |
| :--- | :--- |
| `VectorStore` | Unified interface: `store_vectors`, `search_vectors`, `update_vectors`, `delete_vectors` |
| `HybridSearch` | Fuses dense vector similarity with metadata filtering via RRF or weighted average |
| `MetadataFilter` | Chainable filter builder: `.eq("type", "person").gt("year", 2020).in_list("tag", [...])` |
| `NamespaceManager` | Multi-tenant isolation — separate index namespaces per project or user |
| `FAISSStore` | Local disk or in-memory — flat, ivf, hnsw, and pq index types |
| `WeaviateStore` | Cloud or self-hosted, schema-aware |
| `QdrantStore` | Cloud or self-hosted with payload-based filtering |
| `PineconeStore` | Managed cloud vector database with serverless and pod modes |
| `MilvusStore` | Scalable self-hosted vector database |
| `PgVectorStore` | PostgreSQL with `pgvector` extension — no extra infrastructure |
| `MetadataStore` | Standalone metadata indexing and querying |
| `SearchRanker` | RRF and weighted-average result fusion |

## What You Get

<CardGroup cols={2}>
  <Card title="VectorStore" icon="database">
    - Unified interface across FAISS, Pinecone, Weaviate, Qdrant, Milvus, PgVector
    - One-line backend swap — no application code changes
    - `add_documents()` auto-embeds; `store_vectors()` for pre-computed embeddings
  </Card>
  <Card title="HybridSearch" icon="magnifying-glass">
    - Dense vector similarity with metadata filtering
    - RRF or weighted-average fusion strategies
    - Multi-source fusion across separate collections
  </Card>
  <Card title="MetadataStore" icon="table">
    - Rich metadata indexing by field values
    - Update metadata fields without re-embedding
    - OR and AND query operators
  </Card>
  <Card title="NamespaceManager" icon="folder-tree">
    - Structural per-tenant namespace isolation
    - Faster queries (smaller search space per tenant)
    - Safer than metadata-filter-only separation
  </Card>
  <Card title="Batch Operations" icon="layer-group">
    - Bulk add, delete, and metadata updates
    - Parallel embedding with configurable `batch_size` and `workers`
    - In-place vector updates without full re-indexing
  </Card>
  <Card title="FAISS Index Types" icon="chart-scatter">
    - flat, ivf, hnsw, and pq index types
    - Full configuration control via `FAISSStore.create_index()`
    - `save()` / `load()` for disk persistence
  </Card>
</CardGroup>


## Getting Started

**`VectorStore`** is the main entry point. Use `"inmemory"` for development and `"faiss"` for **local production**:

```python
from semantica.vector_store import VectorStore

# In-memory (development / testing — no persistence)
store = VectorStore(backend="inmemory", dimension=384)

# FAISS (local, persists to disk via save/load)
store = VectorStore(backend="faiss", dimension=384)

# Add plain text documents (auto-embedded)
ids = store.add_documents(
    documents=["Apple was founded by Steve Jobs.", "Microsoft was co-founded by Bill Gates."],
    metadata=[{"source": "wiki"}, {"source": "wiki"}]
)

# Search by text query (auto-embedded)
results = store.search("technology company founders", limit=5)
for r in results:
    print(f"{r['id']} — score: {r['score']:.3f}")
```

## Quick Start

<Steps>
  <Step title="Create a vector store">
    ```python
    from semantica.vector_store import VectorStore

    # In-memory (development)
    store = VectorStore(backend="inmemory", dimension=384)

    # FAISS (local production)
    store = VectorStore(backend="faiss", dimension=384)
    ```
  </Step>
  <Step title="Add vectors">
    ```python
    # Add text documents (auto-embedded in batches)
    ids = store.add_documents(
        documents=["text one", "text two"],
        metadata=[{"title": "Document 1"}, {"title": "Document 2"}]
    )

    # Add pre-computed vectors directly
    ids = store.store_vectors(
        vectors=[embedding1, embedding2],
        metadata=[{"title": "Document 1"}, {"title": "Document 2"}]
    )
    ```
  </Step>
  <Step title="Search by semantic similarity">
    ```python
    # Search by text query (auto-embeds the query)
    results = store.search("machine learning", limit=10)

    # Search by pre-computed vector
    results = store.search_vectors(query_vector, k=10)

    for r in results:
        print(f"{r['id']} — score: {r['score']:.3f}")
    ```
  </Step>
  <Step title="Filter results by metadata">
    ```python
    from semantica.vector_store import HybridSearch, MetadataFilter

    mf = MetadataFilter().eq("category", "research").gt("year", 2022)

    # Pass vector_store to the constructor — search() resolves vectors automatically
    search  = HybridSearch(vector_store=store)
    results = search.search(query=query_vector, k=10, metadata_filter=mf)
    ```
  </Step>
</Steps>

## Backends

<Tabs>
  <Tab title="In-memory / FAISS">

```python
# In-memory — no persistence, for development and testing
store = VectorStore(backend="inmemory", dimension=384)

# FAISS — local disk persistence via save() / load()
store = VectorStore(backend="faiss", dimension=384)
store.save("./my_store")   # save to directory
store.load("./my_store")   # restore from directory
```

No installation or API key required. FAISS requires `pip install faiss-cpu`.

  </Tab>
  <Tab title="Pinecone">

```bash
pip install "semantica[pinecone]"
```

```python
import os
store = VectorStore(
    backend="pinecone",
    dimension=768,
    api_key=os.getenv("PINECONE_API_KEY"),
    index_name="semantica-index",
    environment="us-east-1-aws"
)
```

  </Tab>
  <Tab title="Weaviate">

```bash
pip install "semantica[weaviate]"
```

```python
store = VectorStore(
    backend="weaviate",
    dimension=768,
    url="http://localhost:8080",
    class_name="Document"
)
```

  </Tab>
  <Tab title="Qdrant">

```bash
pip install "semantica[qdrant]"
```

```python
store = VectorStore(
    backend="qdrant",
    dimension=768,
    url="http://localhost:6333",
    collection_name="semantica"
)
```

  </Tab>
  <Tab title="PgVector">

```bash
pip install "semantica[pgvector]"
```

```python
store = VectorStore(
    backend="pgvector",
    dimension=768,
    connection_string="postgresql://user:pass@localhost/db",
    table_name="embeddings"
)
```

`connection_string` is required — the store raises `ValueError` at construction if it is absent.

  </Tab>
  <Tab title="Milvus">

```bash
pip install pymilvus
```

```python
store = VectorStore(
    backend="milvus",
    dimension=768,
    host="localhost",
    port=19530,
    collection_name="semantica"
)
```

  </Tab>
</Tabs>

## Backend Selection Guide

| Backend | Deployment | API Key | Persistence | Best For |
| :------- | :---------- | :------- | :----------- | :-------- |
| `inmemory` | Process | No | No | Development, unit tests |
| `faiss` | Local | No | Via `save()`/`load()` | On-premise, offline production |
| `pinecone` | Cloud | Yes | Managed | Managed cloud, serverless |
| `weaviate` | Self-hosted / Cloud | Optional | Managed | Rich metadata filtering |
| `qdrant` | Self-hosted / Cloud | Optional | Managed | High-performance filtering |
| `milvus` | Self-hosted | No | Managed | Large-scale production |
| `pgvector` | PostgreSQL | No | Managed | Postgres-native integration |

## HybridSearch

`HybridSearch` combines vector similarity with metadata filtering. Pass `vector_store` at construction to avoid supplying raw vectors on every call:

```python
from semantica.vector_store import HybridSearch, MetadataFilter

# With vector_store — search() pulls vectors from the store automatically
search = HybridSearch(vector_store=store)
mf     = MetadataFilter().eq("category", "research").gt("year", 2022)

results = search.search(
    query=query_vector,   # np.ndarray or query string (auto-embedded)
    k=10,
    metadata_filter=mf
)

for r in results:
    print(f"{r['id']} — score: {r['score']:.3f}  metadata: {r['metadata']}")
```

Without a `vector_store`, pass vectors explicitly:

```python
search = HybridSearch()
results = search.search(
    query=query_vector,
    vectors=my_vectors,
    metadata=my_metadata,
    vector_ids=my_ids,
    k=10,
    metadata_filter=mf,
)
```

Multi-source fusion across separate collections:

```python
sources = [
    {"vectors": v1, "metadata": m1, "ids": ids1},
    {"vectors": v2, "metadata": m2, "ids": ids2},
]
fused = search.multi_source_search(query_vector, sources, k=10)
```

## Metadata Filtering

`MetadataFilter` supports chained conditions — all conditions are ANDed:

```python
from semantica.vector_store import MetadataFilter

mf = MetadataFilter().eq("author", "John Smith")          # equality
mf = MetadataFilter().ne("status", "archived")            # not equal
mf = MetadataFilter().gt("year", 2022).lte("year", 2024)  # range
mf = MetadataFilter().in_list("tag", ["ai", "ml"])        # set membership
mf = MetadataFilter().contains("title", "neural")         # substring / list contains

# Multiple conditions — all must match (AND)
mf = (
    MetadataFilter()
    .eq("category", "research")
    .gt("year", 2022)
    .contains("title", "language model")
)
```

### MetadataFilter Methods

| Method | Operator | Description |
| :------ | :-------- | :----------- |
| `.eq(field, value)` | `==` | Exact equality |
| `.ne(field, value)` | `!=` | Not equal |
| `.gt(field, value)` | `>` | Greater than |
| `.gte(field, value)` | `>=` | Greater than or equal |
| `.lt(field, value)` | `<` | Less than |
| `.lte(field, value)` | `<=` | Less than or equal |
| `.in_list(field, values)` | `in` | Field value is in list |
| `.contains(field, value)` | substring | String contains or list contains |

## SearchRanker

`SearchRanker` fuses results from multiple ranked lists:

```python
from semantica.vector_store import SearchRanker

# Reciprocal Rank Fusion — robust to score scale differences
ranker  = SearchRanker(strategy="reciprocal_rank_fusion")
fused   = ranker.rank([results_list_1, results_list_2])

# Weighted average — requires normalised scores on the same scale
ranker  = SearchRanker(strategy="weighted_average")
fused   = ranker.rank([results_list_1, results_list_2], weights=[0.7, 0.3])
```

| Fusion strategy | Description |
| :--------------- | :----------- |
| `reciprocal_rank_fusion` | Rank-based combination via RRF — robust to score scale differences (default) |
| `weighted_average` | Weighted sum of scores — pass `weights=[...]` to `rank()` |

## Namespace Isolation

Use `NamespaceManager` to assign vectors to named namespaces for multi-tenant isolation:

```python
from semantica.vector_store import NamespaceManager, VectorStore

store      = VectorStore(backend="inmemory", dimension=384)
ns_manager = NamespaceManager()

ns_manager.create_namespace("tenant_a", description="Customer A data")
ns_manager.create_namespace("tenant_b", description="Customer B data")

# Store vectors, then assign them to a namespace
ids_a = store.store_vectors(embeddings_a, metadata=metadata_a)
for vid in ids_a:
    ns_manager.add_vector_to_namespace(vid, "tenant_a")

# List all namespace names
for name in ns_manager.list_namespaces():     # returns List[str]
    print(name)

# Get all vectors in a namespace
vectors_in_a = ns_manager.get_namespace_vectors("tenant_a")

# Look up which namespace a vector belongs to
ns = ns_manager.get_vector_namespace("vec_0")

ns_manager.delete_namespace("tenant_a")
```

## Batch Operations

```python
# Batch add text documents — parallel embedding with configurable workers
ids = store.add_documents(
    documents=large_doc_list,
    metadata=large_meta_list,
    batch_size=32,     # texts per embedding batch
    parallel=True,     # use ThreadPoolExecutor
)

# Batch add pre-computed vectors
ids = store.store_vectors(vectors=embeddings_list, metadata=meta_list)

# Delete by vector ID list
store.delete_vectors(vector_ids=["vec_0", "vec_1", "vec_2"])

# Update vectors in-place (rebuilds index for inmemory backend)
store.update_vectors(
    vector_ids=["vec_0"],
    new_vectors=[new_embedding]
)
```

## Persistence (FAISS and in-memory)

```python
store = VectorStore(backend="faiss", dimension=384)
store.add_documents(documents=docs, metadata=meta)

# Save to a directory — creates index.bin and store_data.pkl
store.save("./vector_store_backup")

# Restore in a new process
store2 = VectorStore(backend="faiss", dimension=384)
store2.load("./vector_store_backup")
```

<Note>
  Cloud backends (Pinecone, Weaviate, Qdrant, Milvus, PgVector) manage persistence themselves. `save()`/`load()` are for the in-memory and FAISS backends only.
</Note>

## MetadataStore

`MetadataStore` indexes structured metadata and lets you query by field values without a vector:

```python
from semantica.vector_store import MetadataStore

meta_store = MetadataStore()

# Store and retrieve metadata
meta_store.store_metadata("doc1", {"author": "Alice", "year": 2024, "category": "research"})
meta_store.store_metadata("doc2", {"author": "Bob",   "year": 2023, "category": "review"})

# Query — returns List[str] of matching vector IDs
ids = meta_store.query_metadata({"category": "research", "year": 2024})

# OR query
ids = meta_store.query_metadata({"category": "research"}, operator="OR")

# Get and update metadata for a specific vector
meta = meta_store.get_metadata("doc1")
meta_store.update_metadata("doc1", {"score": 0.92})

# Get all unique values for a field
years = meta_store.get_field_values("year")

# Statistics
stats = meta_store.get_stats()
# {"total_vectors": 2, "indexed_fields": 3, "field_counts": {...}}
```

## FAISS Index Type Reference

FAISS index type is configured by creating a `FAISSStore` directly and calling `create_index()`. Use lowercase type names:

```python
from semantica.vector_store import FAISSStore

store = FAISSStore(dimension=384)

# flat — brute-force exact search
store.create_index(index_type="flat", metric="L2")

# ivf — inverted file index
store.create_index(index_type="ivf", metric="L2", nlist=100)

# hnsw — hierarchical navigable small world graph
store.create_index(index_type="hnsw", metric="L2", M=32)

# pq — product quantization for memory efficiency
store.create_index(index_type="pq", metric="L2", m=8)
```

| Index | Memory | Speed | Accuracy | When to Use |
| :----- | :------ | :----- | :-------- | :----------- |
| `flat` | High | Slow | Exact (100%) | < 100K vectors, correctness critical |
| `ivf` | Medium | Fast | ~95–98% | 100K–10M vectors, good balance |
| `hnsw` | Medium-High | Very fast | ~97–99% | Low latency, production retrieval |
| `pq` | Low | Fast | ~90–95% | Millions of vectors, memory-constrained |

<Note>
  When using `VectorStore(backend="faiss")`, the underlying `FAISSStore` is initialised with a flat index by default. To use ivf/hnsw/pq, construct `FAISSStore` directly and call `create_index()` with the desired type.
</Note>

## Common Workflows

<Tabs>
  <Tab title="Semantic search pipeline">
    ```python
    from semantica.vector_store import VectorStore

    store = VectorStore(backend="faiss", dimension=384)

    # Index documents
    store.add_documents(
        documents=corpus_texts,
        metadata=[{"source": src} for src in sources],
        batch_size=64,
    )

    # Persist
    store.save("./corpus_index")

    # Query
    results = store.search("What is knowledge graph construction?", limit=5)
    for r in results:
        print(f"[{r['score']:.3f}] {r['metadata']['source']}")
    ```
  </Tab>
  <Tab title="Filtered retrieval">
    ```python
    from semantica.vector_store import VectorStore, HybridSearch, MetadataFilter

    store  = VectorStore(backend="inmemory", dimension=384)
    search = HybridSearch(vector_store=store)

    # Only return results from 2023+ with category "research"
    mf = MetadataFilter().gte("year", 2023).eq("category", "research")
    results = search.search(query=query_vector, k=10, metadata_filter=mf)
    ```
  </Tab>
  <Tab title="Multi-source fusion">
    ```python
    from semantica.vector_store import HybridSearch, SearchRanker

    search = HybridSearch()
    sources = [
        {"vectors": v1, "metadata": m1, "ids": ids1},
        {"vectors": v2, "metadata": m2, "ids": ids2},
    ]
    fused = search.multi_source_search(query_vector, sources, k=10)

    # Custom fusion weights
    ranker = SearchRanker(strategy="weighted_average")
    fused  = ranker.rank([results_a, results_b], weights=[0.7, 0.3])
    ```
  </Tab>
  <Tab title="Multi-tenant namespaces">
    ```python
    from semantica.vector_store import VectorStore, NamespaceManager

    store = VectorStore(backend="inmemory", dimension=384)
    ns    = NamespaceManager()

    ns.create_namespace("project_a")
    ns.create_namespace("project_b")

    ids = store.add_documents(docs_a, metadata=meta_a)
    for vid in ids:
        ns.add_vector_to_namespace(vid, "project_a")

    # Check ownership
    print(ns.get_vector_namespace(ids[0]))  # "project_a"
    print(ns.get_namespace_stats("project_a"))
    ```
  </Tab>
</Tabs>

## Tips and Common Pitfalls

<Warning>
  **Match vector dimension to your embedding model.** The `dimension` parameter must exactly match your embedding model's output size — `BAAI/bge-small-en-v1.5` = 384, `all-MiniLM-L6-v2` = 384, `all-mpnet-base-v2` = 768, `bge-large-en-v1.5` = 1024. A mismatch raises an error at insert time.
</Warning>

<Warning>
  **FAISS index type names are lowercase.** The `FAISSStore.create_index()` method expects `"flat"`, `"ivf"`, `"hnsw"`, `"pq"` — not `"Flat"`, `"IVF"`, `"HNSW"`, `"PQ"`. Uppercase values raise `ValidationError`.
</Warning>

<Warning>
  **inmemory and faiss backends lose data on process exit without `save()`.** Call `store.save(path)` after adding vectors. Cloud backends (Pinecone, Qdrant, Weaviate, Milvus, PgVector) persist automatically.
</Warning>

<Tip>
  **Use `HybridSearch(vector_store=store)` to avoid passing raw vectors on every call.** When `vector_store` is set, `search()` pulls vectors and metadata from the store automatically — you only need to pass the query and filter.
</Tip>

<Tip>
  **Use `add_documents()` for text, `store_vectors()` for pre-computed embeddings.** `add_documents()` auto-embeds in parallel batches. If your embeddings are already computed (e.g. from a fine-tuned model), use `store_vectors()` directly to skip re-embedding.
</Tip>

<Tip>
  **Use `NamespaceManager` for multi-tenant applications.** Storing all tenants' vectors in the same collection and filtering by metadata at query time is slow and risks data leakage if a filter is accidentally omitted. Namespace isolation is both faster (smaller search space) and safer (structural isolation).
</Tip>

<Tip>
  **Update metadata without re-embedding.** `MetadataStore.update_metadata(id, {...})` changes attached fields (status, tags, review date) without re-running the embedding model. Use this for state changes that don't affect semantic content.
</Tip>

<CardGroup cols={2}>
  <Card title="Embeddings" icon="vector-square" href="embeddings">
    Generate the vectors stored here.
  </Card>
  <Card title="Context" icon="brain" href="context">
    AgentContext uses VectorStore for memory retrieval.
  </Card>
  <Card title="Split" icon="scissors" href="split">
    Chunk documents before embedding and storing.
  </Card>
  <Card title="Ingest" icon="download" href="ingest">
    Ingest documents before embedding and storing.
  </Card>
</CardGroup>
