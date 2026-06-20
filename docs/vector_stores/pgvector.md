---
title: "pgvector Store"
description: "PostgreSQL with pgvector extension: cosine, L2, and inner product similarity search with IVFFlat and HNSW indexing."
icon: "database"
---

**`PgVectorStore`** adds PostgreSQL-native vector storage and similarity search to Semantica: no dedicated vector database required.


## Overview

**`PgVectorStore`** provides native PostgreSQL vector storage using the [pgvector](https://github.com/pgvector/pgvector) extension. It supports **multiple distance metrics** (cosine similarity, L2/Euclidean, inner product), index types (IVFFlat, HNSW), and JSONB metadata storage with filtering.

## Features

<Check>Distance metrics: cosine, L2 (Euclidean), inner product</Check>
<Check>Index types: IVFFlat and HNSW for approximate nearest-neighbor search</Check>
<Check>JSONB metadata storage with filtering support</Check>
<Check>Connection pooling via psycopg3/psycopg2</Check>
<Check>Batch insert, update, and delete</Check>
<Check>Idempotent index creation: safe to call multiple times</Check>


## Setup

### Prerequisites

1. PostgreSQL 13+ with pgvector extension installed
2. Python dependencies: `psycopg3` (preferred) or `psycopg2-binary`, `pgvector`

### Installing Dependencies

```bash
# Install with pgvector support
pip install semantica[vectorstore-pgvector]

# Or install manually
pip install psycopg[binary] pgvector
# Or for psycopg2
pip install psycopg2-binary pgvector
```

### PostgreSQL Setup

<Steps>
  <Step title="Install the pgvector extension">
    ```sql
    -- Debian/Ubuntu
    sudo apt-get install postgresql-16-pgvector

    -- macOS (Homebrew)
    brew install pgvector

    -- Or build from source: https://github.com/pgvector/pgvector
    ```
  </Step>
  <Step title="Create the extension in your database">
    ```sql
    CREATE EXTENSION vector;
    ```
  </Step>
  <Step title="Verify installation">
    ```sql
    SELECT * FROM pg_extension WHERE extname = 'vector';
    ```
  </Step>
</Steps>

### Docker Quickstart

```bash
docker run -d \
    --name pgvector \
    -e POSTGRES_PASSWORD=postgres \
    -p 5432:5432 \
    ankane/pgvector:latest
```


## Connection String Format

Standard PostgreSQL connection string:

```
postgresql://user:password@host:port/database
```

Examples:

```python
# Local development
"postgresql://postgres:postgres@localhost:5432/semantica"

# With SSL
"postgresql://user:pass@host/db?sslmode=require"

# Connection parameters
"postgresql://user:pass@localhost/db?connect_timeout=10&application_name=semantica"
```


## Usage

### Basic Usage

```python
from semantica.vector_store import PgVectorStore
import numpy as np

# Initialize store
store = PgVectorStore(
    connection_string="postgresql://postgres:postgres@localhost:5432/semantica",
    table_name="document_vectors",
    dimension=768,
    distance_metric="cosine",
    pool_size=10
)

# Add vectors
vectors = [np.random.rand(768).astype(np.float32) for _ in range(100)]
metadata = [{"doc_id": i, "category": "article"} for i in range(100)]
ids = store.add(vectors, metadata)

# Search
query = np.random.rand(768).astype(np.float32)
results = store.search(query, top_k=10)

# Results format: [{"id": "...", "score": 0.95, "metadata": {...}}, ...]
for result in results:
    print(f"ID: {result['id']}, Score: {result['score']:.4f}")

# Close store
store.close()
```

### Context Manager

```python
with PgVectorStore(
    connection_string="postgresql://...",
    table_name="vectors",
    dimension=768,
    distance_metric="cosine"
) as store:
    vectors = [np.random.rand(768).astype(np.float32)]
    ids = store.add(vectors, [{"source": "test"}])
    # Store automatically closed on exit
```

### Metadata Filtering

```python
# Search with metadata filter
results = store.search(
    query_vector,
    top_k=10,
    filter={"category": "science", "published": True}
)
```

### Update and Delete

```python
# Update vectors and metadata
new_vectors = [np.random.rand(768).astype(np.float32)]
new_metadata = [{"updated": True}]
store.update(["vec_0"], new_vectors, new_metadata)

# Update metadata only
store.update(["vec_0"], metadata=[{"tag": "updated"}])

# Delete vectors
store.delete(["vec_0", "vec_1"])
```

### Retrieve by ID

```python
results = store.get(["vec_0", "vec_1"])
# Returns: [{"id": "vec_0", "vector": np.array(...), "metadata": {...}}, ...]
```

### Index Creation

```python
# Create HNSW index for approximate nearest neighbor search
store.create_index(
    index_type="hnsw",
    params={"m": 16, "ef_construction": 64}
)

# Create IVFFlat index
store.create_index(
    index_type="ivfflat",
    params={"lists": 100}
)
```

Index creation is idempotent: calling multiple times is safe.

### Statistics

```python
stats = store.get_stats()
# Returns: {
#     "table_name": "document_vectors",
#     "dimension": 768,
#     "distance_metric": "cosine",
#     "vector_count": 1000,
#     "indexes": [...],
#     "psycopg_version": "3"
# }
```

## Distance Metrics

| Metric | Operator | Description | Use Case |
| :-------- | :---------- | :------------- | :---------- |
| `cosine` | `<=>` | Cosine distance (1 - cosine similarity) | Semantic similarity, text embeddings |
| `l2` | `<->` | Euclidean distance | Geometric distance, clustering |
| `inner_product` | `<#>` | Negative inner product | Maximum inner product search |

**Note**: Scores returned by `search()` are normalized to similarity (higher = better) regardless of metric.

## Index Types

<Tabs>
  <Tab title="HNSW">
    **Hierarchical Navigable Small World**: best for high-dimensional vectors with high recall requirements.

    | | |
    | :-- | :-- |
    | **Pros** | Fast search, good recall, incremental build |
    | **Cons** | Higher memory usage, slower build time |

    ```python
    store.create_index(index_type="hnsw", params={
        "m": 16,               # connections per layer (default: 16)
        "ef_construction": 64  # build-time accuracy/speed tradeoff (default: 64)
    })
    ```
  </Tab>
  <Tab title="IVFFlat">
    **Inverted File with Flat Index**: best for large datasets in memory-constrained environments.

    | | |
    | :-- | :-- |
    | **Pros** | Lower memory usage, tunable speed/accuracy |
    | **Cons** | Requires training data, slower incremental updates |

    ```python
    store.create_index(index_type="ivfflat", params={
        "lists": 100  # number of inverted lists (default: 100)
    })
    ```

    <Note>IVFFlat requires at least as many vectors as `lists` before training can run.</Note>
  </Tab>
</Tabs>

## Schema

The vector table schema:

```sql
CREATE TABLE IF NOT EXISTS {table_name} (
    id TEXT PRIMARY KEY,
    vector VECTOR({dimension}),
    metadata JSONB DEFAULT '{}',
    created_at TIMESTAMP DEFAULT NOW()
);
```

## Migration Notes

### From Other Vector Stores

```python
# Export from existing store
from semantica.vector_store import FAISSStore

faiss_store = FAISSStore(dimension=768)
# ... load existing index

# Migrate to PgVectorStore
pg_store = PgVectorStore(
    connection_string="postgresql://...",
    table_name="migrated_vectors",
    dimension=768,
    distance_metric="cosine"
)

# Get all vectors from source
all_ids = list(faiss_store.index.vector_ids)
all_vectors = [...]  # Get vectors from source
all_metadata = [faiss_store.index.metadata.get(id, {}) for id in all_ids]

# Batch insert
pg_store.add(all_vectors, all_metadata, all_ids)
```

### Backup and Restore

Use PostgreSQL native backup tools:

```bash
# Backup
pg_dump -h localhost -U postgres -d semantica -t document_vectors > vectors_backup.sql

# Restore
psql -h localhost -U postgres -d semantica < vectors_backup.sql
```

## Configuration

### Connection Pool Settings

```python
store = PgVectorStore(
    connection_string="postgresql://...",
    table_name="vectors",
    dimension=768,
    distance_metric="cosine",
    pool_size=10,        # Max connections in pool
    max_overflow=10      # Extra connections beyond pool_size
)
```

### Environment Variables

```bash
# Connection string via environment
export SEMANTICA_PGVECTOR_URL="postgresql://user:pass@host/db"
```

```python
import os

store = PgVectorStore(
    connection_string=os.getenv("SEMANTICA_PGVECTOR_URL"),
    table_name="vectors",
    dimension=768,
    distance_metric="cosine"
)
```

## Error Handling

Common errors and solutions:

| Error | Cause | Solution |
| :------- | :------- | :---------- |
| `ProcessingError: pgvector extension is not installed` | pgvector not in PostgreSQL | Run `CREATE EXTENSION vector;` |
| `ValidationError: Unsupported distance metric` | Invalid metric | Use: `cosine`, `l2`, `inner_product` |
| `ValidationError: dimension mismatch` | Vector dim != store dim | Ensure consistent dimensions |
| `ProcessingError: Failed to initialize connection pool` | Connection issue | Check connection string, network |

## Performance Tuning

1. **Use indexes for large datasets** (>10k vectors)
2. **Tune HNSW parameters**: Higher `m` and `ef_construction` = better recall, slower build
3. **Connection pool size**: Set based on concurrent workload
4. **Batch operations**: Use `add()` with lists instead of individual inserts

## Testing

Tests require a running PostgreSQL with pgvector:

```bash
# Start PostgreSQL with Docker
docker run -d \
    --name pgvector-test \
    -e POSTGRES_PASSWORD=postgres \
    -p 5432:5432 \
    ankane/pgvector:latest

# Run tests
pytest tests/vector_store/test_pgvector_store.py -v

# Or with specific connection string
TEST_PGVECTOR_URL="postgresql://postgres:postgres@localhost:5432/test" \
    pytest tests/vector_store/test_pgvector_store.py -v
```

## See Also

- [pgvector Documentation](https://github.com/pgvector/pgvector)
- [PgVector Python Client](https://github.com/pgvector/pgvector-python)
- [psycopg Documentation](https://www.psycopg.org/)
- [Vector Store Module](../reference/vector_store)
