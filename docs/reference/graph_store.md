---
title: "Graph Store Module"
description: "Unified interface for Neo4j, FalkorDB, Apache AGE, and Amazon Neptune graph databases."
icon: "server"
---

**`semantica.graph_store`** provides a **single unified API** for persisting and querying knowledge graphs in production graph databases:

- Swap backends with a one-line change: Neo4j, FalkorDB, Apache AGE, Amazon Neptune
- Parameterized Cypher execution with optional result caching via `QueryEngine`
- Batch node and edge loading: faster than individual writes
- `GraphAnalytics` for degree centrality, connected components, shortest path, neighbor traversal
- Context manager support: `with GraphStore(...) as store:` closes connection automatically


## Exported Classes

| Class | Role |
| :--- | :--- |
| `GraphStore` | Unified interface: `create_node`, `create_relationship`, `query`, `get_neighbors`, `shortest_path` |
| `QueryEngine` | Parameterized Cypher execution with result caching |
| `GraphAnalytics` | `degree_centrality`, `connected_components`, `shortest_path`, `get_neighbors` |
| `Neo4jStore` | Production workloads via Bolt: supports APOC and GDS plugins |
| `ApacheAgeStore` | PostgreSQL + AGE extension: no separate graph server needed |
| `AmazonNeptuneStore` | AWS Neptune: OpenCypher via Bolt protocol |
| `FalkorDBStore` | Redis-based: sub-millisecond latency for real-time applications |


## What You Get

<CardGroup cols={2}>
  <Card title="GraphStore" icon="server">
    - Unified API across Neo4j, FalkorDB, Apache AGE, Amazon Neptune
    - Context manager support for automatic connection cleanup
    - `create_nodes()` for bulk loading: faster than individual calls
  </Card>
  <Card title="QueryEngine" icon="magnifying-glass">
    - Parameterized Cypher construction prevents injection attacks
    - Optional in-process result caching with `use_cache=True`
    - `clear_cache()` on writes, toggle with `enable_cache()` / `disable_cache()`
  </Card>
  <Card title="GraphAnalytics" icon="chart-line">
    - Degree centrality ordered by degree DESC
    - Connected component assignment
    - Shortest path between nodes, neighbor traversal up to N hops
  </Card>
  <Card title="Bulk Operations" icon="layer-group">
    - `create_nodes(list)`: one round-trip for many nodes
    - `create_relationship()` with typed properties
    - `delete_node(detach=True)` removes all connected relationships
  </Card>
  <Card title="Schema Management" icon="table">
    - `create_index(label, property_name=)`: makes MATCH queries orders-of-magnitude faster
    - `get_stats()`: node counts, edge counts, type breakdown
    - Create indexes before bulk loading for best performance
  </Card>
  <Card title="Path Traversal" icon="route">
    - `shortest_path()` returns `length`, `nodes`, `relationships`
    - `get_neighbors()` with direction and depth control
    - Cross-backend path traversal via the unified API
  </Card>
</CardGroup>


## Getting Started

`GraphStore` wraps the backend of your choice behind a single API. Call `connect()` (or use it as a context manager) before running any queries:

```python
from semantica.graph_store import GraphStore

store = GraphStore(
    backend="neo4j",
    uri="bolt://localhost:7687",
    user="neo4j",
    password="password",
)
store.connect()

# Create a node
node = store.create_node(
    labels=["Person"],
    properties={"name": "Alice", "role": "Engineer"},
)
print(node["id"])   # Neo4j internal integer ID

# Create a relationship
store.create_relationship(
    start_node_id=node1_id,
    end_node_id=node2_id,
    rel_type="WORKS_FOR",
    properties={"since": 2022},
)

# Execute a Cypher query
results = store.query(
    "MATCH (p:Person)-[:WORKS_FOR]->(o:Organization) WHERE o.name = $org RETURN p",
    parameters={"org": "Acme Corp"},
)

store.close()
```

Use as a context manager to close the connection automatically:

```python
with GraphStore(backend="neo4j", uri="bolt://localhost:7687", user="neo4j", password="password") as store:
    store.create_node(labels=["Person"], properties={"name": "Bob"})
```

<Warning>
  **Call `connect()` before any operations.** `GraphStore` does not connect automatically on construction. Either call `store.connect()` explicitly or use the context manager form `with GraphStore(...) as store:`.
</Warning>

## Quick Start

<Steps>
  <Step title="Connect to a graph database">
    ```python
    from semantica.graph_store import GraphStore

    store = GraphStore(
        backend="neo4j",
        uri="bolt://localhost:7687",
        user="neo4j",
        password="password",
    )
    store.connect()
    ```
  </Step>
  <Step title="Create indexes before loading data">
    ```python
    store.create_index(label="Person",       property_name="name")
    store.create_index(label="Organization", property_name="name")
    ```
  </Step>
  <Step title="Load nodes and relationships">
    ```python
    # Batch creation: list of dicts with "labels" and "properties" keys
    store.create_nodes([
        {"labels": ["Person"],       "properties": {"name": "Alice"}},
        {"labels": ["Organization"], "properties": {"name": "Acme Corp"}},
    ])
    ```
  </Step>
  <Step title="Query the graph">
    ```python
    results = store.query(
        "MATCH (p:Person)-[:WORKS_FOR]->(o:Organization) WHERE o.name = $org RETURN p",
        parameters={"org": "Acme Corp"},
    )
    ```
  </Step>
</Steps>


## GraphStore Methods

| Method | Returns | Description |
| :------ | :------- | :----------- |
| `create_node(labels, properties)` | `dict` | Create a single node, returns node dict with `"id"` |
| `create_nodes(nodes)` | `List[dict]` | Batch-create nodes from list of `{"labels", "properties"}` dicts |
| `get_node(node_id)` | `dict \| None` | Retrieve a node by its backend ID |
| `get_nodes(labels, properties, limit)` | `List[dict]` | Query nodes matching label/property criteria |
| `update_node(node_id, properties, merge)` | `dict` | Update node properties; `merge=True` (default) merges, `merge=False` replaces |
| `delete_node(node_id, detach)` | `bool` | Delete node; `detach=True` (default) removes relationships too |
| `create_relationship(start_node_id, end_node_id, rel_type, properties)` | `dict` | Create a directed relationship |
| `get_relationships(node_id, rel_type, direction, limit)` | `List[dict]` | Get relationships for a node |
| `delete_relationship(rel_id)` | `bool` | Delete a relationship by ID |
| `execute_query(query, parameters)` | `dict` | Execute raw Cypher, returns `{"success", "records", "keys", "metadata"}` |
| `query(query, parameters)` | `List[dict]` | Execute Cypher and return records list directly |
| `create_index(label, property_name)` | `bool` | Create an index for faster lookups |
| `get_neighbors(node_id, rel_type, direction, depth)` | `List[dict]` | Get neighboring nodes |
| `shortest_path(start_node_id, end_node_id, rel_type, max_depth)` | `dict \| None` | Find shortest path between two nodes |
| `get_stats()` | `dict` | Get graph statistics from the backend |


## Backends

<Tabs>
  <Tab title="Neo4j (recommended)">
    ```bash
    pip install neo4j
    ```

    ```python
    from semantica.graph_store import GraphStore

    store = GraphStore(
        backend="neo4j",
        uri="bolt://localhost:7687",
        user="neo4j",
        password="password",
        database="neo4j",    # optional: targets default database
    )
    store.connect()
    ```

    **Best for:** production workloads, complex Cypher queries, Bloom visualization.
  </Tab>
  <Tab title="FalkorDB">
    ```bash
    pip install falkordb
    ```

    ```python
    store = GraphStore(
        backend="falkordb",
        host="localhost",
        port=6379,
        graph_name="semantica",
    )
    store.connect()
    ```

    **Best for:** ultra-low latency queries over Redis protocol, edge deployments.
  </Tab>
  <Tab title="Apache AGE">
    ```bash
    pip install psycopg2-binary
    ```

    ```python
    store = GraphStore(
        backend="age",   # or "apache_age"
        connection_string="host=localhost dbname=agedb user=postgres password=secret",
        graph_name="semantica",
    )
    store.connect()
    ```

    **Best for:** teams already running PostgreSQL who want graph queries without a separate service.

    <Warning>
      **Apache AGE requires the PostgreSQL extension installed.** `backend="age"` calls the AGE extension functions. If AGE is not installed in your PostgreSQL instance, you'll get a `ProgrammingError`. See the [Apache AGE docs](https://age.apache.org/age-manual/master/intro/setup.html) for setup.
    </Warning>
  </Tab>
  <Tab title="Amazon Neptune">
    ```bash
    pip install neo4j boto3
    ```

    ```python
    store = GraphStore(
        backend="neptune",   # or "amazon_neptune"
        endpoint="your-cluster.cluster-xxxx.us-east-1.neptune.amazonaws.com",
        port=8182,
        region="us-east-1",
        iam_auth=True,    # uses boto3 default credential chain
    )
    store.connect()

    # OpenCypher queries via Bolt protocol
    results = store.query(
        "MATCH (p:Person)-[:WORKS_FOR]->(o:Organization) RETURN p, o"
    )
    ```

    **Best for:** managed AWS deployments. Neptune uses the Bolt protocol for OpenCypher queries: the same query API used for Neo4j.

    <Warning>
      **Amazon Neptune uses `iam_auth=`, not `use_iam_auth=`.** The `AmazonNeptuneStore` and the `GraphStore` Neptune backend both use `iam_auth: bool = True` as the parameter name.
    </Warning>
  </Tab>
  <Tab title="Backend Comparison">

    | Backend | Query Language | Deployment | IAM Auth | Best For |
    | :------- | :-------------- | :---------- | :-------- | :-------- |
    | Neo4j | Cypher | Self-hosted / Aura | No | Production, complex traversals, Bloom UI |
    | FalkorDB | OpenCypher | Redis-based | No | Ultra-low latency, edge deployments |
    | Apache AGE | OpenCypher | PostgreSQL extension | No | Teams already on Postgres |
    | Amazon Neptune | OpenCypher | AWS managed | Yes | Cloud-native, managed, compliance |

  </Tab>
</Tabs>

## Graph Operations

```python
# Create a single node
node = store.create_node(
    labels=["Organization"],
    properties={"name": "Apple Inc.", "founded": 1976},
)

# Create a directed relationship (both node IDs required)
rel = store.create_relationship(
    start_node_id=jobs_id,
    end_node_id=node["id"],
    rel_type="FOUNDED",
    properties={"year": 1976},
)

# Batch-create nodes
store.create_nodes([
    {"labels": ["Person"],       "properties": {"name": "Steve Jobs"}},
    {"labels": ["Organization"], "properties": {"name": "NeXT"}},
])

# Update node properties (merge=True merges, merge=False replaces)
store.update_node(node["id"], {"employees": 164000}, merge=True)

# Delete (detach=True also removes connected relationships)
store.delete_node(node["id"], detach=True)
store.delete_relationship(rel["id"])

# Get neighbors
neighbors = store.get_neighbors(
    node["id"],
    rel_type="HAS_EMPLOYEE",
    direction="in",    # "in" | "out" | "both"
    depth=1,
)

# Shortest path: returns {"length", "nodes", "relationships"} or None
path = store.shortest_path(
    start_node_id=jobs_id,
    end_node_id=cook_id,
    rel_type="WORKS_WITH",
    max_depth=5,
)
if path:
    print(f"Hops: {path['length']}")
```

<Tip>
  **Use `create_nodes()` for bulk loading.** Individual `create_node()` calls issue one network round-trip each. `create_nodes(list)` is faster for initial graph population.
</Tip>

## QueryEngine

`QueryEngine` handles query execution and optional caching. Access it via `store.query_engine`:

```python
from semantica.graph_store import GraphStore

store  = GraphStore(backend="neo4j", uri="bolt://localhost:7687", user="neo4j", password="password")
store.connect()

# Get the query engine from the store
engine = store.query_engine

# Execute a parameterized query
result = engine.execute(
    "MATCH (p:Person) WHERE p.department = $dept RETURN p",
    parameters={"dept": "Engineering"},
)
# result is {"success": True, "records": [...], "keys": [...], "metadata": {...}}

# Execute with caching: repeated identical calls return cached result
result = engine.execute(
    "MATCH (p:Person) RETURN count(p) as total",
    use_cache=True,
)

# Clear cached results
engine.clear_cache()

# Toggle caching
engine.disable_cache()
engine.enable_cache()
```

### QueryEngine Methods

| Method | Returns | Description |
| :------ | :------- | :----------- |
| `execute(query, parameters, use_cache)` | `dict` | Execute Cypher, returns `{success, records, keys, metadata}` |
| `clear_cache()` | `None` | Flush all cached query results |
| `enable_cache()` | `None` | Turn on caching (on by default) |
| `disable_cache()` | `None` | Turn off caching |

<Tip>
  **Use `QueryEngine` caching for read-heavy workloads.** Access the engine via `store.query_engine`. Call `engine.execute(query, use_cache=True)` to cache identical queries in-process. Call `engine.clear_cache()` after writes that invalidate results.
</Tip>

<Warning>
  **Use parameterized queries, never string interpolation.** `store.query("WHERE n.name = $name", parameters={"name": user_input})` prevents Cypher injection attacks. Never use `f"WHERE n.name = '{user_input}'"`.
</Warning>


## GraphAnalytics

Access analytics via `store._manager.analytics` or construct directly with the backend store instance:

```python
from semantica.graph_store import GraphStore, GraphAnalytics

store = GraphStore(backend="neo4j", uri="bolt://localhost:7687", user="neo4j", password="password")
store.connect()

# GraphAnalytics takes the backend store, not the GraphStore facade
analytics = GraphAnalytics(store._store_backend)

# Degree centrality: returns list of {"id", "degree"} dicts ordered by degree DESC
scores = analytics.degree_centrality(
    labels=["Person"],
    rel_type="KNOWS",
    direction="both",    # "in" | "out" | "both"
)
for entry in scores[:5]:
    print(f"Node {entry['id']}: degree {entry['degree']}")

# Connected components (requires GDS for Neo4j, NetworkX for in-process)
components = analytics.connected_components(labels=["Person"])

# Shortest path: returns {"length", "nodes", "relationships"} or None
path = analytics.shortest_path(
    start_node_id=alice_id,
    end_node_id=charlie_id,
    rel_type="KNOWS",
    max_depth=4,
)

# Neighbor traversal
neighbors = analytics.get_neighbors(
    node_id=alice_id,
    rel_type="KNOWS",
    direction="out",
    depth=2,
)
```

### GraphAnalytics Methods

| Method | Returns | Description |
| :------ | :------- | :----------- |
| `degree_centrality(labels, rel_type, direction)` | `List[dict]` | Degree-based node importance: records ordered by degree DESC |
| `connected_components(labels)` | `List[dict]` | Connected component assignment (requires GDS on Neo4j) |
| `shortest_path(start_node_id, end_node_id, rel_type, max_depth)` | `dict \| None` | Path with `length`, `nodes`, `relationships` or `None` |
| `get_neighbors(node_id, rel_type, direction, depth)` | `List[dict]` | Neighbor nodes up to `depth` hops |

<Note>
  `betweenness_centrality()`, `pagerank()`, `detect_communities()`, and `all_paths()` are not implemented. Use Neo4j GDS procedures directly via `store.execute_query()` for those algorithms.
</Note>


## Schema Management

```python
# Index for fast label-property lookups: use property_name= not property=
store.create_index(label="Person",       property_name="name")
store.create_index(label="Organization", property_name="id")

# Graph statistics
stats = store.get_stats()
```

<Warning>
  **Create indexes before bulk loading.** `store.create_index(label="Person", property_name="name")` makes `MATCH` queries on `name` orders of magnitude faster. Without indexes, every query does a full scan. Create indexes first, then load data.
</Warning>

<Warning>
  **`create_index` parameter is `property_name=`, not `property=`.** `store.create_index(label="Person", property_name="name")`: using `property=` will be silently ignored.
</Warning>

## Common Workflows

<Tabs>
  <Tab title="Build from KG data">
    ```python
    from semantica.graph_store import GraphStore

    store = GraphStore(backend="neo4j", uri="bolt://localhost:7687", user="neo4j", password="password")
    store.connect()

    # Create indexes first for speed
    store.create_index("Person",       property_name="name")
    store.create_index("Organization", property_name="name")

    # Load entities as nodes
    created = store.create_nodes([
        {"labels": [e["type"]], "properties": {"name": e["text"], "id": e["id"]}}
        for e in entities
    ])

    # Map entity IDs to backend node IDs
    id_map = {e["id"]: node["id"] for e, node in zip(entities, created)}

    # Load relationships
    for rel in relationships:
        if rel["source_id"] in id_map and rel["target_id"] in id_map:
            store.create_relationship(
                start_node_id=id_map[rel["source_id"]],
                end_node_id=id_map[rel["target_id"]],
                rel_type=rel["type"],
            )

    store.close()
    ```
  </Tab>
  <Tab title="Parameterized queries">
    ```python
    # Always use parameters, never string interpolation
    results = store.query(
        "MATCH (p:Person)-[:WORKS_FOR]->(o:Organization) "
        "WHERE o.name = $org AND p.role = $role RETURN p.name",
        parameters={"org": user_input_org, "role": user_input_role},
    )
    ```
  </Tab>
  <Tab title="Neighbor traversal">
    ```python
    # Walk 2 hops of KNOWS relationships
    neighbors = store.get_neighbors(
        node_id=alice_id,
        rel_type="KNOWS",
        direction="out",
        depth=2,
    )
    for n in neighbors:
        print(n["properties"]["name"])
    ```
  </Tab>
  <Tab title="Apache AGE notes">
    AGE supports one primary label per vertex. If you pass multiple labels, the first is used as the AGE label and the rest are stored in a `labels` property array. Parameterized queries use literal inlining internally (AGE does not support `$param` binding inside `cypher()` calls): the store handles escaping automatically.
  </Tab>
</Tabs>

<CardGroup cols={2}>
  <Card title="KG Module" icon="diagram-project" href="kg">
    Build the graph before persisting it.
  </Card>
  <Card title="Triplet Store" icon="table" href="triplet_store">
    RDF triple store for semantic web and SPARQL queries.
  </Card>
  <Card title="Visualization" icon="chart-bar" href="visualization">
    Visualize graphs stored in any backend.
  </Card>
  <Card title="Context" icon="brain" href="context">
    AgentContext uses GraphStore for memory retrieval.
  </Card>
</CardGroup>
