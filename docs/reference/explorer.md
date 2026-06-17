---
title: "Explorer"
description: "Interactive FastAPI dashboard for knowledge graph exploration, ontology management, and graph analytics."
icon: "map"
---

**`semantica.explorer`** is a **browser-based dashboard** for exploring knowledge graphs, managing ontologies, and running visual analyses:

- Indexed search: 0.004ms on 118k nodes: no full scans
- Ontology Hub: visual editor, SHACL Studio, alignment authoring, and health dashboard
- Bidirectional path finding between any two nodes
- WebSocket progress streaming for live pipeline monitoring
- No code required after launch: full graph exploration in the browser


## Getting Started

Install, export your graph to JSON, and launch:

```bash
pip install "semantica[explorer]"
```

```python
# 1. Export your graph to a JSON file
import json
from semantica.context import ContextGraph

graph = ContextGraph()
graph.add_node("Python",  "language",  properties={"paradigm": "multi-paradigm"})
graph.add_node("FastAPI", "framework", properties={"language": "Python"})
graph.add_edge("Python", "FastAPI", "enables")
graph.save_to_file("my_graph.json")
```

```bash
# 2. Launch the Explorer
semantica-explorer --graph my_graph.json
# → Loading graph...
# → Graph loaded: 2 nodes, 1 edges
# → Semantica Explorer · http://127.0.0.1:8000
#     API docs  http://127.0.0.1:8000/docs
#     Health    http://127.0.0.1:8000/api/health
```

The browser opens automatically at `http://127.0.0.1:8000`. The interactive API docs are at `/docs`.

<Tip>
  `semantica.explorer` is a **server process**, not an importable Python library. Use the CLI or `python -m semantica.explorer` to launch. The `app.py` module exposes a module-level `app` instance for use with uvicorn or Docker.
</Tip>

## Launch

<Steps>
  <Step title="Save your graph and launch Explorer">
    ```python
    from semantica.context import ContextGraph

    graph = ContextGraph()
    graph.load_from_file("my_graph.json")   # verify graph loads
    ```

    ```bash
    semantica-explorer --graph my_graph.json
    # Serves at http://127.0.0.1:8000
    ```
  </Step>
  <Step title="Custom host and port">
    ```bash
    # Expose on the network
    semantica-explorer --graph my_graph.json --host 0.0.0.0 --port 8080

    # Skip auto-opening the browser
    semantica-explorer --graph my_graph.json --no-browser
    ```
  </Step>
  <Step title="Import new data without restarting">
    ```bash
    # Import a JSON or CSV file into the running session
    curl -X POST http://localhost:8000/api/import \
      -F "file=@updated_graph.json"
    ```
  </Step>
  <Step title="Use via Python module">
    ```bash
    python -m semantica.explorer --graph my_graph.json --port 8080
    ```
  </Step>
</Steps>

## CLI Reference

The `semantica-explorer` command accepts exactly four flags:

| Flag | Short | Default | Description |
| :---- | :----- | :------- | :----------- |
| `--graph` | `-g` | *(**required**)* | Path to a ContextGraph JSON file to load |
| `--port` | `-p` | `8000` | Port to bind the server |
| `--host` |: | `127.0.0.1` | Host to bind the server: use `0.0.0.0` to expose on the network |
| `--no-browser` |: | off | Skip auto-opening the browser tab |

<Note>
  There are no flags for authentication, CORS, or log level in the CLI. CORS allowed origins are configured via the `EXPLORER_CORS_ORIGINS` environment variable (comma-separated, default: `http://localhost:5173,http://127.0.0.1:5173`).
</Note>

```bash
# Full example
EXPLORER_CORS_ORIGINS="http://myapp.example.com" \
  semantica-explorer --graph my_graph.json --host 0.0.0.0 --port 8080 --no-browser
```

## What You Get

<CardGroup cols={2}>
  <Card title="Graph Explorer" icon="diagram-project">
    Interactive node/edge search, path finding, and neighborhood expansion. Indexed search at 0.004ms on 118k-node graphs.
  </Card>
  <Card title="Ontology Hub" icon="sitemap">
    SKOS vocabulary management, SHACL shape generation and validation, ontology alignment, health dashboard, and versioning.
  </Card>
  <Card title="Analytics" icon="chart-line">
    Degree centrality, community detection, connectivity analysis, graph validation, and distance matrices.
  </Card>
  <Card title="REST API" icon="code">
    All features available as a REST API: fully documented at `/docs`.
  </Card>
  <Card title="WebSocket Updates" icon="bolt">
    Real-time graph mutation events streamed over WebSocket at `/ws/graph-updates`.
  </Card>
  <Card title="CLI Launcher" icon="terminal">
    `semantica-explorer --graph my_graph.json` for instant local startup.
  </Card>
</CardGroup>

## Features

<Tabs>
  <Tab title="Graph Explorer">
    Core dashboard for navigating knowledge graphs:

    - **Indexed search**: POST to `/api/graph/search` with a query; 0.004ms on 118k-node graphs
    - **Path finding**: BFS or Dijkstra between any two nodes via `GET /api/graph/path?source=&target=`
    - **Neighbor expansion**: `GET /api/graph/node/{id}/neighbors?depth=2`
    - **Filter by entity type**: `GET /api/graph/nodes?type=Person`
    - **Semantic neighborhood**: `GET /api/graph/semantic-neighborhood?node_id=&top_k=20`
    - **Distance matrix**: `POST /api/graph/distance-matrix`
  </Tab>
  <Tab title="Ontology Hub">
    Ontology lifecycle management in the browser:

    - **Registry**: `GET /api/ontology/registry`: list loaded ontologies
    - **SKOS vocabularies**: `GET /api/ontology/skos/schemes`, `GET /api/ontology/skos/concept/{uri}`
    - **SHACL**: `POST /api/ontology/shacl/generate`, `POST /api/ontology/shacl/validate`
    - **Alignments**: `GET/POST /api/ontology/alignments`, `POST /api/ontology/suggest-alignments`
    - **Proposals & versioning**: `POST /api/ontology/propose`, `GET /api/ontology/versions/{uri}`
    - **Health**: `GET /api/ontology/health`
  </Tab>
  <Tab title="Analytics">
    Graph metrics running against the loaded graph:

    - **Combined metrics**: `GET /api/analytics?metrics=centrality,community,connectivity`
    - **Graph validation**: `GET /api/analytics/validation`
    - **Enrich: link prediction**: `POST /api/enrich/links`
    - **Enrich: deduplication**: `POST /api/enrich/dedup`
    - **Enrich: entity extraction**: `POST /api/enrich/extract`
    - **Temporal**: `GET /api/temporal/snapshot`, `GET /api/temporal/diff`, `GET /api/temporal/bounds`
  </Tab>
  <Tab title="Decisions & Provenance">
    Decision tracking and provenance queries:

    - **Decisions**: `GET /api/decisions`, `GET /api/decisions/{id}`, `GET /api/decisions/{id}/chain`
    - **Precedents**: `GET /api/decisions/{id}/precedents`
    - **Causal distance**: `GET /api/decisions/causal-distance?source=&target=`
    - **Compliance**: `GET /api/decisions/{id}/compliance`
    - **Provenance**: `GET /api/provenance?node_id=`, `GET /api/provenance/report?node_id=`
    - **Annotations**: `GET/POST /api/annotations`, `DELETE /api/annotations/{id}`
  </Tab>
</Tabs>

## API Endpoints

Full interactive docs at `http://localhost:8000/docs`. All endpoints accept and return JSON.

<AccordionGroup>
  <Accordion title="Graph endpoints">

    | Endpoint | Method | Description |
    | :-------- | :------ | :----------- |
    | `/api/graph/stats` | `GET` | Node count, edge count, entity type distribution |
    | `/api/graph/nodes` | `GET` | List nodes: `?type=&search=&skip=&limit=&cursor=&bbox=` |
    | `/api/graph/node/{id}` | `GET` | Fetch a single node with all properties |
    | `/api/graph/node/{id}/neighbors` | `GET` | Neighbors of a node: `?depth=1` (1–5) |
    | `/api/graph/edges` | `GET` | List edges: `?type=&source=&target=&skip=&limit=&cursor=` |
    | `/api/graph/path` | `GET` | Shortest path: `?source=&target=&algorithm=bfs&directed=true` |
    | `/api/graph/search` | `POST` | Indexed search: body: `{query, limit, filters, anchor_node}` |
    | `/api/graph/distance-matrix` | `POST` | Pairwise distances: body: `{node_ids, metric}` (max 50 nodes) |
    | `/api/graph/semantic-neighborhood` | `GET` | Semantic neighbors: `?node_id=&top_k=20&min_similarity=0.0` |

  </Accordion>
  <Accordion title="Analytics, Enrich & Temporal">

    **Analytics:**

    | Endpoint | Method | Description |
    | :-------- | :------ | :----------- |
    | `/api/analytics` | `GET` | Graph metrics: `?metrics=centrality,community,connectivity` |
    | `/api/analytics/validation` | `GET` | Graph validation report |

    **Enrich:**

    | Endpoint | Method | Description |
    | :-------- | :------ | :----------- |
    | `/api/enrich/extract` | `POST` | Entity extraction from text |
    | `/api/enrich/links` | `POST` | Link prediction for nodes |
    | `/api/enrich/dedup` | `POST` | Duplicate detection |
    | `/api/enrich/merge` | `POST` | Merge duplicate nodes |
    | `/api/reason` | `POST` | Run reasoning over graph |

    **Temporal:**

    | Endpoint | Method | Description |
    | :-------- | :------ | :----------- |
    | `/api/temporal/snapshot` | `GET` | Graph snapshot at `?at=ISO8601` (defaults to now) |
    | `/api/temporal/diff` | `GET` | Diff between two times: `?from_time=&to_time=` |
    | `/api/temporal/patterns` | `GET` | Temporal activity patterns |
    | `/api/temporal/bounds` | `GET` | Earliest and latest temporal bounds in graph |
    | `/api/temporal/distance-history` | `GET` | Distance history: `?source=&target=` |

  </Accordion>
  <Accordion title="Ontology, Vocabulary & SPARQL">

    **Ontology:**

    | Endpoint | Method | Description |
    | :-------- | :------ | :----------- |
    | `/api/ontology/registry` | `GET` | List loaded ontologies |
    | `/api/ontology/load` | `POST` | Load an ontology from URL or content |
    | `/api/ontology/create` | `POST` | Create a new ontology |
    | `/api/ontology/search` | `GET` | Search ontology entities: `?q=term` |
    | `/api/ontology/health` | `GET` | Ontology health and coverage metrics |
    | `/api/ontology/alignments` | `GET/POST` | List or create ontology alignments |
    | `/api/ontology/suggest-alignments` | `POST` | AI-suggested alignments |
    | `/api/ontology/shacl/generate` | `POST` | Generate SHACL shapes |
    | `/api/ontology/shacl/validate` | `POST` | Validate RDF against SHACL |
    | `/api/ontology/skos/schemes` | `GET` | List SKOS concept schemes |
    | `/api/ontology/skos/concept/{uri}` | `GET` | Get a SKOS concept |
    | `/api/ontology/proposals` | `GET/POST` | Manage ontology change proposals |
    | `/api/ontology/versions/{uri}` | `GET` | Version history |

    **Vocabulary:**

    | Endpoint | Method | Description |
    | :-------- | :------ | :----------- |
    | `/api/vocabulary/schemes` | `GET` | SKOS schemes via TripletStore |
    | `/api/vocabulary/concepts` | `GET` | Concepts in a scheme: `?scheme=URI` |
    | `/api/vocabulary/hierarchy` | `GET` | Concept hierarchy tree |
    | `/api/vocabulary/import` | `POST` | Import SKOS/RDF vocabulary file |

    **SPARQL:**

    | Endpoint | Method | Description |
    | :-------- | :------ | :----------- |
    | `/api/sparql` | `POST` | Execute a SPARQL SELECT or ASK query |

  </Accordion>
  <Accordion title="Decisions, Provenance, Annotations & Export">

    **Decisions:**

    | Endpoint | Method | Description |
    | :-------- | :------ | :----------- |
    | `/api/decisions` | `GET` | Paginated list of recorded decisions |
    | `/api/decisions/{id}` | `GET` | Single decision details |
    | `/api/decisions/{id}/chain` | `GET` | Causal chain for a decision |
    | `/api/decisions/{id}/precedents` | `GET` | Similar past decisions |
    | `/api/decisions/{id}/compliance` | `GET` | Policy compliance check |
    | `/api/decisions/causal-distance` | `GET` | Causal distance: `?source=&target=` |

    **Provenance:**

    | Endpoint | Method | Description |
    | :-------- | :------ | :----------- |
    | `/api/provenance` | `GET` | Entity provenance lineage: `?node_id=` |
    | `/api/provenance/report` | `GET` | Provenance export report: `?node_id=` |

    **Annotations:**

    | Endpoint | Method | Description |
    | :-------- | :------ | :----------- |
    | `/api/annotations` | `GET` | List annotations: `?node_id=` (optional) |
    | `/api/annotations` | `POST` | Create annotation (returns 201) |
    | `/api/annotations/{id}` | `DELETE` | Delete annotation (returns 204) |

    **Export / Import:**

    | Endpoint | Method | Description |
    | :-------- | :------ | :----------- |
    | `/api/export` | `POST` | Export graph as JSON or CSV: body: `{format, node_ids}` |
    | `/api/export/distance-enriched` | `POST` | Export pairwise distances as CSV or JSONL |
    | `/api/import` | `POST` | Import nodes/edges from `.json` or `.csv` file (max 50 MB) |

  </Accordion>
  <Accordion title="Health & Info">

    | Endpoint | Method | Description |
    | :-------- | :------ | :----------- |
    | `/api/health` | `GET` | Returns `{"status": "healthy"}` |
    | `/api/info` | `GET` | Server name, version, status |
    | `/docs` | `GET` | Interactive Swagger UI: all endpoints |

  </Accordion>
</AccordionGroup>

## WebSocket Graph Updates

Real-time graph mutation events are streamed over WebSocket at `ws://localhost:8000/ws/graph-updates`:

```python
import asyncio
import json
import websockets

async def watch_updates():
    async with websockets.connect("ws://localhost:8000/ws/graph-updates") as ws:
        # Server sends an ack on connect
        ack = json.loads(await ws.recv())
        print("Connected:", ack)

        # Send a ping to verify the connection is alive
        await ws.send("ping")

        async for message in ws:
            event = json.loads(message)
            print("[{}] {}".format(event["event"], event.get("data")))

asyncio.run(watch_updates())
```

WebSocket message schema:

```json
{
  "event":     "graph_mutation",
  "data": {
    "event_type":  "ADD_NODE",
    "entity_id":   "node_123",
    "payload":     {}
  },
  "timestamp": "2024-01-15T10:30:00+00:00"
}
```

Event types broadcast over the WebSocket include: `connection_ack`, `pong`, and `graph_mutation` (fired when nodes or edges are added/updated/removed via import or enrichment). Send the text `"ping"` to receive a `pong` response.

## Performance

| Scenario | Latency |
| :-------- | :------- |
| Node search (118k nodes, indexed) | 0.004ms |
| Neighbor expansion (depth 2) | < 5ms |
| BFS path (118k nodes) | < 50ms |
| SPARQL SELECT (simple pattern) | < 20ms |
| Distance matrix (50 nodes, semantic) | ~2s (with embedding cache) |

The node search index is built on startup. For graphs > 500k nodes, allow extra startup time before connecting.

Distance matrix is capped at 50 node pairs per request. Semantic distance requires nodes to have embeddings stored in their properties.

## Troubleshooting

**Browser tab does not open**
The browser is launched 1.5 seconds after the server starts. Use `--no-browser` and open `http://127.0.0.1:8000` manually if the auto-open fails.

**`Error: graph file not found`**
The `--graph` path must be an existing file. Check the path and ensure the file exists before launching.

**`Error: uvicorn is required`**
Install the explorer extras: `pip install "semantica[explorer]"`.

**`Connection refused` on API calls**
The server only binds to `127.0.0.1` by default. To access Explorer from another machine or container, launch with `--host 0.0.0.0`.

**Empty graph after import**
The import endpoint (`/api/import`) only parses `.json` and `.csv` files. Other formats return HTTP 422. JSON files must contain a top-level `entities`/`nodes` array or `relationships`/`edges` array.

**`PathFinder not available` error from `/api/graph/path`**
Path finding requires the `semantica[kg]` extras. Install with `pip install "semantica[all]"`.

**Semantic neighborhood returns 503**
Semantic neighborhood requires node embeddings stored in node properties (keys `embedding`, `vector`, or `node2vec_embedding`). Graphs without embeddings return 503.

**Session state lost after restart**
Session state is in-memory only. Use `POST /api/export` to save a JSON snapshot before shutting down.

## Tips and Common Pitfalls

<Warning>
  **Filter large graphs before saving to JSON.** The CLI loads the entire JSON file into memory. For graphs > 10k nodes, filter to the relevant subgraph before exporting: the force-directed layout becomes unusable on very large graphs.
</Warning>

<Warning>
  **Session state is lost on server restart.** There is no auto-save. Call `POST /api/export` with body `{"format": "json"}` to download the current state before shutting down.
</Warning>

<Tip>
  **Use the REST API for automation, Explorer UI for exploration.** Explorer's REST endpoints are a stable programmatic API: pipe them into scripts to automate batch annotation, SPARQL querying, or exports.
</Tip>

<Tip>
  **CORS origins are configured via environment variable.** Set `EXPLORER_CORS_ORIGINS` to a comma-separated list of allowed origins before launching (e.g. `EXPLORER_CORS_ORIGINS="http://myapp.example.com"`).
</Tip>

<Tip>
  **Use `/api/analytics/validation` to check graph quality.** The validator detects orphaned nodes, missing types, and other structural issues before you expose the graph to downstream pipelines.
</Tip>

<CardGroup cols={2}>
  <Card title="Context" icon="brain" href="context">
    Build and save the ContextGraph that Explorer loads.
  </Card>
  <Card title="Ontology" icon="sitemap" href="ontology">
    Programmatic ontology management and SHACL generation.
  </Card>
  <Card title="Visualization" icon="chart-bar" href="visualization">
    Programmatic graph rendering without the Explorer server.
  </Card>
  <Card title="Export" icon="file-export" href="export">
    Export to RDF, Parquet, and other formats without launching a server.
  </Card>
</CardGroup>
