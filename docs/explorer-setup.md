---
title: "Explorer Setup"
description: "Install the Explorer extras, save a ContextGraph to JSON, and launch the interactive browser dashboard."
icon: "map"
---

**`semantica-explorer`** is an **interactive browser dashboard** for knowledge graph exploration. You give it a graph file, it starts a local server, and opens a browser tab where you can search nodes, find paths, inspect provenance, and run analytics — no code required after launch.

This page covers everything needed to go from zero to a running Explorer. For the full REST API reference and endpoint catalogue, see [Explorer Reference](reference/explorer).


## Prerequisites

The Explorer depends on FastAPI and uvicorn, which are not included in the base install:

```bash
pip install semantica[explorer]
```

<Note>
  `pip install semantica` alone is not sufficient. Running `semantica-explorer` without the `[explorer]` extra immediately prints an error and exits with code 1.
</Note>

Verify:

```bash
semantica-explorer --help
```

You should see the usage message with the four available flags. If you see `command not found`, activate your virtual environment first. See [CLI Setup](cli-setup#troubleshooting) for PATH help.


## Minimal End-to-End Example

The following four steps are everything needed to get Explorer running:

```python
from semantica.context import ContextGraph

# 1. Create a graph
graph = ContextGraph()

# 2. Add a node
graph.add_node("python", "language", content="Python programming language")

# 3. Save to disk
graph.save_to_file("my_graph.json")
```

```bash
# 4. Launch Explorer
semantica-explorer --graph my_graph.json
```

The browser opens at `http://127.0.0.1:8000`. The health endpoint confirms the server is up:

```bash
curl http://127.0.0.1:8000/api/health
# {"status": "healthy"}
```


## Step 1 — Build and Save a ContextGraph

Explorer loads a graph from a JSON file on disk. You need to create that file first.

<Steps>
  <Step title="Build a graph">
    ```python
    from semantica.context import ContextGraph

    graph = ContextGraph()

    # add_node(node_id, node_type, content=None, **properties)
    graph.add_node("python",  "language",  content="Python programming language")
    graph.add_node("fastapi", "framework", content="FastAPI web framework")
    graph.add_node("guido",   "person",    content="Guido van Rossum")

    # add_edge(source_id, target_id, edge_type="related_to", weight=1.0, **properties)
    graph.add_edge("python",  "fastapi", "enables")
    graph.add_edge("guido",   "python",  "created")
    ```
  </Step>
  <Step title="Save to a JSON file">
    ```python
    graph.save_to_file("my_graph.json")
    ```

    `save_to_file` writes a JSON object with `graph_id`, `nodes`, `edges`, and `links` to the specified path.
  </Step>
  <Step title="Verify the file loads (optional sanity check)">
    ```python
    from semantica.context import ContextGraph

    check = ContextGraph()
    check.load_from_file("my_graph.json")
    print(check.stats())
    # {
    #   "node_count": 3,
    #   "edge_count": 2,
    #   "node_types": {"language": 1, "framework": 1, "person": 1},
    #   "edge_types": {"enables": 1, "created": 1},
    #   "density": ...
    # }
    ```

    If this runs without error, Explorer will load the file successfully.
  </Step>
</Steps>

<Tip>
  Already have a graph from a pipeline run? Skip straight to Step 2. The only requirement is that the file was saved with `ContextGraph.save_to_file()`.
</Tip>


## Step 2 — Launch Explorer

```bash
semantica-explorer --graph my_graph.json
```

The startup sequence prints:

```
✓ Graph loaded — 3 nodes, 2 edges
╭─ Semantica Explorer · http://127.0.0.1:8000 ─╮
│  API docs  http://127.0.0.1:8000/docs         │
│  Health    http://127.0.0.1:8000/api/health   │
╰───────────────────────────────────────────────╯
```

The browser opens automatically at `http://127.0.0.1:8000` shortly after the server starts.


## CLI Flags

`semantica-explorer` accepts exactly four flags:

| Flag | Short | Default | Description |
| :---- | :----- | :------- | :----------- |
| `--graph` | `-g` | *(**required**)* | Path to a ContextGraph JSON file |
| `--port` | `-p` | `8000` | Port to bind the server |
| `--host` | — | `127.0.0.1` | Host to bind the server |
| `--no-browser` | — | off | Do not open a browser tab automatically |

There are no flags for authentication, log level, or TLS. Those are not implemented in the CLI.

### Examples

```bash
# Minimal — local only, port 8000, browser opens automatically
semantica-explorer --graph my_graph.json

# Short flags
semantica-explorer -g my_graph.json -p 8080

# Expose on the network so other machines can connect
semantica-explorer --graph my_graph.json --host 0.0.0.0 --port 8080

# Headless — skip the auto-open and navigate manually
semantica-explorer --graph my_graph.json --no-browser
```

<Warning>
  `--host 0.0.0.0` makes Explorer reachable on every network interface. The server has no built-in authentication. Only use this on a trusted private network.
</Warning>


## Browser Access

Once the server is running:

| URL | What you get |
| :--- | :------------ |
| `http://127.0.0.1:8000` | Interactive dashboard |
| `http://127.0.0.1:8000/docs` | Swagger UI — every REST endpoint, interactive |
| `http://127.0.0.1:8000/api/health` | Health check — `{"status": "healthy"}` |

The browser tab opens shortly after startup. If it does not open, navigate to the URL manually or pass `--no-browser` and open it yourself.


## Running as a Python Module

If `semantica-explorer` is not on `PATH`, use the module form:

```bash
python -m semantica.explorer --graph my_graph.json --port 8080
```


## Common Startup Errors

**`Error: graph file not found: my_graph.json`**

The path passed to `--graph` must point to an existing file. The CLI checks with `os.path.isfile()` before attempting to load anything.

```bash
# Confirm the file exists
ls my_graph.json           # Linux / Mac
dir my_graph.json          # Windows

# Use the full path if needed
semantica-explorer --graph /absolute/path/to/my_graph.json
```

**`Error: uvicorn is required`**

The `[explorer]` extra was not installed:

```bash
pip install semantica[explorer]
```

**Explorer launches but shows zero nodes**

The file loaded but contains no nodes. Verify with Python:

```python
from semantica.context import ContextGraph
g = ContextGraph()
g.load_from_file("my_graph.json")
print(g.stats())  # check node_count
```

A `node_count` of `0` means the file was saved empty or the nodes key is absent. Make sure you called `add_node` before `save_to_file`.

**`Connection refused` from another machine**

The default `--host 127.0.0.1` only accepts connections from the same machine. To allow remote access:

```bash
semantica-explorer --graph my_graph.json --host 0.0.0.0
```

**Browser tab does not open**

This is expected in headless, SSH, and container environments. Add `--no-browser` to suppress the warning and open `http://127.0.0.1:8000` in a browser that has network access to the server.


## What Explorer Gives You

Once running, Explorer exposes a REST API and dashboard for:

- **Node and edge search** — indexed search across all nodes by ID, type, and content
- **Neighborhood expansion** — inspect neighbors up to configurable hop depth
- **Path finding** — BFS shortest path between any two nodes
- **Graph analytics** — centrality, community detection, connectivity
- **Decisions and provenance** — query recorded decisions and their causal chains
- **Import / export** — upload JSON or CSV to extend the graph; download the current state

The full endpoint catalogue is documented in the Swagger UI at `/docs` and in the reference page below.

<CardGroup cols={2}>
  <Card title="Explorer Reference" icon="book-open" href="reference/explorer">
    Every REST endpoint, WebSocket events, analytics, and all supported flags.
  </Card>
  <Card title="CLI Setup" icon="terminal" href="cli-setup">
    All five Semantica executables and when to use each one.
  </Card>
  <Card title="Context Module" icon="brain" href="reference/context">
    Full documentation for ContextGraph — build, query, save, and load.
  </Card>
  <Card title="Quickstart" icon="rocket" href="quickstart">
    End-to-end pipeline: ingest → extract → build graph → export.
  </Card>
</CardGroup>
