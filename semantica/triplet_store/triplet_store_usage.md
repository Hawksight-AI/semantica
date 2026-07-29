# Triplet Store Module Usage Guide

This comprehensive guide demonstrates how to use the triplet store module for RDF data storage and querying, supporting multiple triplet store backends (Blazegraph, Jena, RDF4J) with unified interfaces, SPARQL query execution, bulk loading, and query optimization.

## Table of Contents

1. [Basic Usage](#basic-usage)
2. [Store Registration](#store-registration)
3. [CRUD Operations](#crud-operations)
4. [SPARQL Query Execution](#sparql-query-execution)
5. [Query Optimization](#query-optimization)
6. [Bulk Loading](#bulk-loading)
7. [Store Backends](#store-backends)
8. [Configuration](#configuration)

## Basic Usage

### Using TripletStore Class

```python
from semantica.triplet_store import TripletStore
from semantica.semantic_extract.triplet_extractor import Triplet

# Initialize store (Blazegraph default)
store = TripletStore(
    backend="blazegraph",
    endpoint="http://localhost:9999/blazegraph"
)

# Add a triplet
triplet = Triplet(
    subject="http://example.org/entity1",
    predicate="http://example.org/hasName",
    object="John Doe",
    confidence=0.9
)
result = store.add_triplet(triplet)

print(f"Triplet added: {result['success']}")
```

### Using Convenience Functions

```python
from semantica.triplet_store import register_store, add_triplet

# Register a store
store = register_store("main", "blazegraph", "http://localhost:9999/blazegraph")

# Add a triplet
result = add_triplet(
    Triplet("http://s", "http://p", "http://o"),
    store_id="main"
)
```

## CRUD Operations

### Adding Triplets

```python
from semantica.triplet_store import TripletStore
from semantica.semantic_extract.triplet_extractor import Triplet

store = TripletStore(backend="blazegraph", endpoint="http://localhost:9999/blazegraph")

# Add single triplet
triplet = Triplet(
    subject="http://example.org/entity1",
    predicate="http://example.org/hasName",
    object="John Doe"
)
result = store.add_triplet(triplet)

# Add multiple triplets (Bulk)
triplets = [
    Triplet("http://example.org/entity1", "http://example.org/hasAge", "30"),
    Triplet("http://example.org/entity1", "http://example.org/hasCity", "New York")
]
result = store.add_triplets(triplets, batch_size=1000)
print(f"Added {result['total']} triplets")
```

### Retrieving Triplets

```python
# Get all triplets for a subject
triplets = store.get_triplets(subject="http://example.org/entity1")

# Get triplets matching predicate
triplets = store.get_triplets(predicate="http://example.org/hasName")

# Get specific triplet
triplets = store.get_triplets(
    subject="http://example.org/entity1",
    predicate="http://example.org/hasName",
    object="John Doe"
)
```

### Deleting Triplets

```python
# Delete triplet
triplet = Triplet(
    subject="http://example.org/entity1",
    predicate="http://example.org/hasName",
    object="John Doe"
)
result = store.delete_triplet(triplet)
```

## SPARQL Query Execution

```python
query = """
SELECT ?s ?p ?o
WHERE {
    ?s ?p ?o .
    ?s <http://example.org/hasName> ?o .
}
LIMIT 10
"""
result = store.execute_query(query)

print(f"Variables: {result.variables}")
print(f"Results: {len(result.bindings)}")
for binding in result.bindings:
    print(binding)
```

## Bulk Loading

The module supports high-performance bulk loading with progress tracking.

```python
from semantica.triplet_store import BulkLoader

loader = BulkLoader()
triplets = [...] # List of 10,000 triplets

# Load triplets
progress = loader.load_triplets(triplets, store._store_backend)

print(f"Loaded: {progress.loaded_triplets}/{progress.total_triplets}")
print(f"Failed: {progress.failed_triplets}")
```

## Store Backends

### Blazegraph
High-performance graph database supporting RDF/SPARQL.
```python
store = TripletStore(backend="blazegraph", endpoint="http://localhost:9999/blazegraph")
```

### Jena
Apache Jena Fuseki support.
```python
store = TripletStore(backend="jena", endpoint="http://localhost:3030/ds")
```

### RDF4J
Eclipse RDF4J support.
```python
store = TripletStore(backend="rdf4j", endpoint="http://localhost:8080/rdf4j-server")
```

### Anzo
Altair Anzo (Altair Graph Studio) support. Unlike Blazegraph's namespace or
RDF4J's repository ID, Anzo addresses data by a dataset/graphmart **URI**
rather than a short name, so `dataset_uri` is required and is
percent-encoded into the endpoint path
(`<endpoint>/sparql/<store_type>/<url-encoded_dataset_uri>`).
```python
store = TripletStore(
    backend="anzo",
    endpoint="http://localhost:8080",
    dataset_uri="http://cambridgesemantics.com/Graphmart/abc123",
    store_type="graphmart",  # or "dataset"
    username="user",
    password="pass",
)
```

## Configuration

Configuration is managed via `config.yaml` or environment variables.

```yaml
triplet_store:
  default_backend: blazegraph
  blazegraph_endpoint: http://localhost:9999/blazegraph
  jena_endpoint: http://localhost:3030/ds
  rdf4j_endpoint: http://localhost:8080/rdf4j-server
  anzo_endpoint: http://localhost:8080
```
