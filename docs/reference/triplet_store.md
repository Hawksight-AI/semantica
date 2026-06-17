---
title: "Triplet Store Module"
description: "RDF triple storage with SPARQL queries and bulk loading: Blazegraph, Apache Jena, and RDF4J."
icon: "table"
---

`semantica.triplet_store` provides **W3C-standard RDF storage** with **SPARQL 1.1** query support. Use it when you need **semantic web compatibility**, OWL-style reasoning, SPARQL-based queries, or standards-compliant RDF serialization.

## Exported Classes

| Class | Role |
| :---- | :--- |
| `TripletStore` | Unified interface: `add_triplet`, `add_triplets`, `get_triplets`, `delete_triplet`, `execute_query` |
| `QueryEngine` | **SPARQL 1.1** execution with query optimization and result caching |
| `BulkLoader` | High-volume RDF loading with batching, retries, and progress tracking |
| `BlazegraphStore` | Blazegraph REST API: SPARQL 1.1 Update, namespace management |
| `JenaStore` | Apache Jena: rdflib-backed, SPARQL read support via remote endpoint |
| `RDF4JStore` | Eclipse RDF4J: REST API, transaction support |

## What You Get

<CardGroup cols={2}>
  <Card title="TripletStore" icon="server">
    Unified interface across Blazegraph, Apache Jena, and RDF4J: swap backends with one parameter.
  </Card>
  <Card title="SPARQL" icon="magnifying-glass">
    Full SPARQL SELECT, ASK, CONSTRUCT, and UPDATE query support via `execute_query()`.
  </Card>
  <Card title="Bulk Loading" icon="layer-group">
    `add_triplets()` batches writes with configurable batch size, retry logic, and progress tracking.
  </Card>
  <Card title="SKOS Vocabulary" icon="diagram-project">
    Built-in helpers: `add_skos_concept()` and `get_skos_concepts()` for controlled vocabulary management.
  </Card>
  <Card title="Named Graphs" icon="folder-tree">
    Blazegraph and RDF4J support named graph scoping via `graph=` on `execute_query()`.
  </Card>
  <Card title="Delta Computation" icon="code-compare">
    `compute_delta(old_graph_uri, new_graph_uri)` returns added and removed triples between two named graph snapshots.
  </Card>
</CardGroup>

## Getting Started

**`TripletStore`** wraps the backend of your choice. Construct a `Triplet` object (from `semantica.semantic_extract.types`) and call `add_triplet()`:

```python
from semantica.triplet_store import TripletStore
from semantica.semantic_extract.types import Triplet

store = TripletStore(
    backend="blazegraph",
    endpoint="http://localhost:9999/blazegraph/sparql"
)

# Create and store a single triplet
t = Triplet(
    subject="http://example.org/apple_inc",
    predicate="http://example.org/founded_by",
    object="http://example.org/steve_jobs",
)
store.add_triplet(t)

# Query with SPARQL: returns a QueryResult with a .bindings list
result = store.execute_query("""
    PREFIX ex: <http://example.org/>
    SELECT ?person ?company WHERE {
        ?person ex:founded ?company .
    }
""")

for row in result.bindings:
    person  = row.get("person",  {}).get("value")
    company = row.get("company", {}).get("value")
    print(person, company)
```

## Quick Start

<Steps>
  <Step title="Connect to a backend">
    ```python
    from semantica.triplet_store import TripletStore

    store = TripletStore(
        backend="blazegraph",
        endpoint="http://localhost:9999/blazegraph/sparql"
    )
    ```
  </Step>
  <Step title="Add triplets">
    ```python
    from semantica.semantic_extract.types import Triplet

    # Add a single triplet
    store.add_triplet(Triplet(
        subject="http://example.org/apple_inc",
        predicate="http://example.org/founded_by",
        object="http://example.org/steve_jobs",
    ))

    # Bulk-add a list of Triplet objects
    store.add_triplets(triplets, batch_size=500)
    ```
  </Step>
  <Step title="Query with SPARQL">
    ```python
    # execute_query returns a QueryResult: iterate result.bindings
    result = store.execute_query("""
        PREFIX ex: <http://example.org/>
        SELECT ?person ?company WHERE {
            ?person ex:founded ?company .
            ?company ex:located_in ex:SiliconValley .
        }
    """)

    for row in result.bindings:
        print(row.get("person",  {}).get("value"))
        print(row.get("company", {}).get("value"))
    ```
  </Step>
  <Step title="Store an entire knowledge graph">
    ```python
    # store(knowledge_graph, ontology) converts entities/relationships
    # to RDF triples and bulk-loads them in one call
    store.store(knowledge_graph=kg_dict, ontology=ontology_dict)
    ```
  </Step>
</Steps>

## Backends

<Tabs>
  <Tab title="Blazegraph">
    ```bash
    pip install requests
    ```

    ```python
    from semantica.triplet_store import TripletStore

    store = TripletStore(
        backend="blazegraph",
        endpoint="http://localhost:9999/blazegraph/sparql",
        namespace="kb",      # default: "kb"
        timeout=30,          # request timeout in seconds
    )
    ```

    **Best for:** Wikidata-style workloads, high triple counts, named graph support, SPARQL 1.1 Update.
  </Tab>
  <Tab title="Apache Jena">
    ```bash
    pip install rdflib
    ```

    ```python
    store = TripletStore(
        backend="jena",
        endpoint="http://localhost:3030/ds",   # SPARQL read endpoint for rdflib SPARQLStore
    )
    ```

    **Best for:** local development with rdflib, SPARQL read queries against a Fuseki endpoint.

    <Warning>
      **`backend="jena"` OWL inference is a placeholder.** `enable_inference=True` is accepted but the inference call returns 0 inferred triples. For production OWL reasoning, use Jena Fuseki directly with its built-in reasoner configuration.
    </Warning>
  </Tab>
  <Tab title="RDF4J">
    ```bash
    pip install requests
    ```

    ```python
    store = TripletStore(
        backend="rdf4j",
        endpoint="http://localhost:8080/rdf4j-server",
        repository_id="semantica",   # passed through **config
    )
    ```

    **Best for:** Eclipse Foundation deployments, transaction-based loading via REST API.
  </Tab>
  <Tab title="Backend Comparison">

    | Backend | License | Named Graphs | Write via | Best For |
    | :------- | :------- | :------------ | :--------- | :-------- |
    | Blazegraph | Open source | Yes | SPARQL Update REST | High triple count, SPARQL 1.1 |
    | Apache Jena | Apache 2.0 | No (rdflib backend) | rdflib in-process | Local dev, read queries |
    | RDF4J | Eclipse 1.0 | Yes | REST API N-Triples | Enterprise Java, transactions |

  </Tab>
</Tabs>

<Tip>
  **Use Apache Jena for development, Blazegraph for production.** Jena initializes with rdflib in-memory: no server required for local testing. Switch to Blazegraph for high-throughput persistent workloads by changing `backend=`.
</Tip>

## Triplet Object

All store operations use the `Triplet` dataclass from `semantica.semantic_extract.types`:

```python
from semantica.semantic_extract.types import Triplet

t = Triplet(
    subject="http://example.org/apple_inc",     # required: full URI string
    predicate="http://example.org/founded_by",  # required: full URI string
    object="http://example.org/steve_jobs",     # required: URI or literal string
    confidence=0.95,                            # optional: float 0.0–1.0, default 1.0
    metadata={"source": "wikipedia"},           # optional: dict
)
```

| Field | Type | Default | Description |
| :----- | :---- | :------- | :----------- |
| `subject` | `str` | **required** | Subject URI |
| `predicate` | `str` | **required** | Predicate URI |
| `object` | `str` | **required** | Object URI or literal |
| `confidence` | `float` | `1.0` | Confidence score (0–1) |
| `metadata` | `dict` | `{}` | Arbitrary metadata |

<Warning>
  **`add_triplet()` takes a `Triplet` object, not keyword arguments.** Use `Triplet(subject=..., predicate=..., object=...)` from `semantica.semantic_extract.types` and pass the object: not `subject=`, `predicate=`, `obj=` to `add_triplet`.
</Warning>

## TripletStore Methods

| Method | Returns | Description |
| :------ | :------- | :----------- |
| `add_triplet(triplet)` | `dict` | Add a single `Triplet` object |
| `add_triplets(triplets, batch_size)` | `dict` | Bulk-add a list of `Triplet` objects; returns `{"success", "total", "processed", "failed", "batches"}` |
| `get_triplets(subject, predicate, object)` | `List[Triplet]` | Retrieve triplets matching subject/predicate/object filters |
| `delete_triplet(triplet)` | `dict` | Delete a `Triplet` from the store |
| `update_triplet(old_triplet, new_triplet)` | `dict` | Atomic delete + add |
| `execute_query(query, parameters, graph, graphs)` | `QueryResult` | Execute a SPARQL query: returns `QueryResult` with `.bindings`, `.variables`, `.execution_time` |
| `store(knowledge_graph, ontology)` | `dict` | Convert a KG + ontology dict to RDF triples and bulk-load them |
| `add_skos_concept(concept_uri, scheme_uri, pref_label, ...)` | `dict` | Add a SKOS concept with optional alt labels, broader/narrower/related |
| `get_skos_concepts(scheme_uri)` | `List[dict]` | Retrieve all SKOS concepts, optionally filtered by scheme URI |
| `compute_delta(old_graph_uri, new_graph_uri)` | `dict` | Return `{"added_triples", "removed_triples", "added_count", "removed_count"}` between two named graph snapshots |
| `get_stats()` | `dict` | Get backend statistics |

## SPARQL Queries

`execute_query()` is the single entry point for all SPARQL operations. It returns a `QueryResult`: access results via `.bindings`:

```python
from semantica.triplet_store import TripletStore

store = TripletStore(backend="blazegraph", endpoint="http://localhost:9999/blazegraph/sparql")

# SELECT: iterate result.bindings
result = store.execute_query("""
    PREFIX ex: <http://example.org/>
    SELECT ?person ?company WHERE {
        ?person ex:founded ?company .
    }
""")

for row in result.bindings:
    print(row.get("person",  {}).get("value"))
    print(row.get("company", {}).get("value"))

# ASK, CONSTRUCT, UPDATE: same method, different SPARQL form
result = store.execute_query("""
    PREFIX ex: <http://example.org/>
    ASK { ex:apple_inc ex:founded_by ex:steve_jobs . }
""")
print(result.bindings)   # ASK returns boolean result in bindings

# SPARQL UPDATE (INSERT/DELETE)
store.execute_query("""
    PREFIX ex: <http://example.org/>
    INSERT DATA {
        ex:apple_inc ex:listed_on ex:NASDAQ .
    }
""")
```

### QueryResult fields

| Field | Type | Description |
| :----- | :---- | :----------- |
| `bindings` | `List[dict]` | Each dict maps variable name → `{"value": ..., "type": ...}` |
| `variables` | `List[str]` | SPARQL result variable names |
| `execution_time` | `float` | Seconds elapsed |
| `metadata` | `dict` | Query, graph scope, cache hit flag |

<Warning>
  **`execute_query()` returns `QueryResult`, not a list.** Iterate `result.bindings`, not `result` directly. Each binding is a dict mapping variable name → `{"value": ..., "type": ...}`.
</Warning>

## SPARQL Result Pagination

For large result sets, paginate with LIMIT and OFFSET:

```python
page_size = 1000
offset    = 0

while True:
    result = store.execute_query(f"""
        SELECT ?s ?p ?o WHERE {{
            ?s ?p ?o .
        }}
        ORDER BY ?s
        LIMIT {page_size} OFFSET {offset}
    """)
    if not result.bindings:
        break
    process_batch(result.bindings)
    offset += page_size
```

<Warning>
  **Paginate large SPARQL result sets.** A `SELECT * WHERE { ?s ?p ?o }` against a large store returns all triples. Always include `LIMIT` and `OFFSET` in exploratory queries. `QueryEngine` adds `LIMIT 1000` automatically unless you specify one.
</Warning>

## Named Graph Scoping

Blazegraph and RDF4J support named graphs. Scope `execute_query()` to a named graph with the `graph=` parameter:

```python
# Add a triplet: named graph stored in metadata or backend-specific API
from semantica.semantic_extract.types import Triplet

t = Triplet(
    subject="http://example.org/a",
    predicate="http://example.org/p",
    object="http://example.org/b",
)
store.add_triplet(t)   # named graph targeting requires backend-specific API

# Query a named graph via FROM clause in SPARQL
result = store.execute_query("""
    SELECT ?s ?p ?o WHERE {
        ?s ?p ?o .
    }
""", graph="http://example.org/graph1")   # injects FROM <graph> before WHERE

# Or scope inline using FROM in the query string
result = store.execute_query("""
    SELECT ?s ?p ?o FROM <http://example.org/graph1> WHERE {
        ?s ?p ?o .
    }
""")
```

<Note>
  Named graph support is only available for Blazegraph and RDF4J backends. The `graph=` parameter is silently ignored for the Jena backend.
</Note>

<Tip>
  **Use named graphs to isolate sources.** Pass `graph="http://example.org/source_A"` to `execute_query()` to scope a query to a specific named graph. Blazegraph and RDF4J support named graphs; Jena (rdflib backend) does not.
</Tip>

## Bulk Loading

`add_triplets()` batches writes via the internal `BulkLoader`. Access `store.bulk_loader` to configure it:

```python
from semantica.triplet_store import TripletStore
from semantica.semantic_extract.types import Triplet

store = TripletStore(backend="blazegraph", endpoint="http://localhost:9999/blazegraph/sparql")

# Default: batch_size=1000, max_retries=3
result = store.add_triplets(triplets)
# Returns: {"success": True, "total": N, "processed": N, "failed": 0, "batches": B}

# Custom batch size for this call
result = store.add_triplets(triplets, batch_size=500)

# Validate before loading
validation = store.bulk_loader.validate_before_load(triplets)
if not validation["valid"]:
    print(validation["errors"])
```

`BulkLoader` can also be used directly with a `progress_callback`:

```python
from semantica.triplet_store import BulkLoader

loader = BulkLoader(batch_size=2000, max_retries=5, retry_delay=2.0)

def on_progress(p):
    print(f"{p.progress_percentage:.1f}%  ({p.loaded_triplets}/{p.total_triplets})")

progress = loader.load_triplets(triplets, store._store_backend, progress_callback=on_progress)
print(f"Loaded {progress.loaded_triplets} in {progress.elapsed_time:.2f}s")
```

## Storing a Knowledge Graph

`store(knowledge_graph, ontology)` converts a KG+ontology dict structure to RDF and bulk-loads everything in one call:

```python
kg = {
    "entities": [
        {"id": "apple_inc",  "type": "Organization", "properties": {"name": "Apple Inc."}},
        {"id": "steve_jobs", "type": "Person",        "properties": {"name": "Steve Jobs"}},
    ],
    "relationships": [
        {"source": "steve_jobs", "target": "apple_inc", "type": "founded"}
    ],
}
ontology = {
    "uri": "https://example.org/ontology/",
    "classes": [
        {"name": "Organization"},
        {"name": "Person"},
    ],
    "properties": [
        {"name": "founded", "type": "object", "domain": ["Person"], "range": ["Organization"]},
    ],
}

result = store.store(knowledge_graph=kg, ontology=ontology)
# Returns add_triplets result dict
```

## SKOS Vocabulary Management

```python
store.add_skos_concept(
    concept_uri="http://example.org/skos/MachineLearning",
    scheme_uri="http://example.org/skos/AIScheme",
    pref_label="Machine Learning",
    alt_labels=["ML", "Statistical Learning"],
    broader=["http://example.org/skos/AI"],
    definition="A field of artificial intelligence...",
)

# Retrieve all concepts in a scheme
concepts = store.get_skos_concepts(scheme_uri="http://example.org/skos/AIScheme")
for c in concepts:
    print(c["uri"], c["pref_label"], c["alt_labels"])
```

## Delta Computation

```python
# Compare two named graph snapshots and return added/removed triples
delta = store.compute_delta(
    old_graph_uri="http://example.org/graph/v1",
    new_graph_uri="http://example.org/graph/v2",
)

print(f"Added:   {delta['added_count']} triples")
print(f"Removed: {delta['removed_count']} triples")

for t in delta["added_triples"]:
    print(f"+  {t.subject}  {t.predicate}  {t.object}")
for t in delta["removed_triples"]:
    print(f"-  {t.subject}  {t.predicate}  {t.object}")
```

## Integration with Export Module

The Export module writes RDF that the triplet store can then receive via `add_triplets()`:

```python
from semantica.export import RDFExporter
from semantica.triplet_store import TripletStore
from semantica.semantic_extract.types import Triplet

# Export KG to Turtle
exporter = RDFExporter()
exporter.export_to_file(kg, "output.ttl", format="turtle")

# Parse the file and load triplets into the store
# (TripletStore does not have a built-in import_file() method —
#  parse with rdflib and convert to Triplet objects)
import rdflib
g = rdflib.Graph()
g.parse("output.ttl", format="turtle")

store = TripletStore(backend="jena", endpoint="http://localhost:3030/ds")
triplets = [
    Triplet(subject=str(s), predicate=str(p), object=str(o))
    for s, p, o in g
]
store.add_triplets(triplets)

# Query with SPARQL
result = store.execute_query("SELECT * WHERE { ?s ?p ?o } LIMIT 10")
for row in result.bindings:
    print(row)
```

<CardGroup cols={2}>
  <Card title="Export" icon="file-export" href="export">
    Export knowledge graphs to RDF formats.
  </Card>
  <Card title="Ontology" icon="sitemap" href="ontology">
    Load OWL ontologies and store as RDF triples.
  </Card>
  <Card title="Reasoning" icon="microchip" href="reasoning">
    SPARQL-based property chain inference.
  </Card>
  <Card title="Graph Store" icon="server" href="graph_store">
    Property graph alternative for Cypher queries.
  </Card>
</CardGroup>
