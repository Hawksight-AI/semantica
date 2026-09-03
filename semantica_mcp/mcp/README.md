# Semantica MCP Server

A fully modular [Model Context Protocol](https://modelcontextprotocol.io/) server for the Semantica knowledge graph.  
Connects Claude Code, Cursor, Windsurf, Cline, Continue, VS Code (GitHub Copilot), and any other MCP-compatible AI tool directly to your Semantica graph.

---

## Quick start

```bash
# From the repo root — no extra install flag needed; the root mcp/ package is
# part of the repository and does not require an external MCP SDK.
pip install -e .

# Test the server (type a JSON-RPC request, press Enter)
python -m mcp
```

Or point your AI tool at it (see per-tool configs below).

---

## Transport

**stdio** — the server reads newline-delimited JSON-RPC 2.0 from `stdin` and writes responses to `stdout`.  
Log/debug output goes to `stderr` only.

```
python -m mcp [--debug]
```

---

## Tools (17 total)

### Extraction

| Tool | Description |
|---|---|
| `extract_entities` | Named entity recognition (NER) — people, places, orgs, concepts |
| `extract_relations` | Relation extraction + (subject, predicate, object) triplets |
| `extract_all` | Full pipeline: NER + coreference + relations + events + triplets |

### Decision Intelligence

| Tool | Description |
|---|---|
| `record_decision` | Record a decision with context, confidence, causal links |
| `query_decisions` | Query decisions by natural language or structured filters |
| `find_precedents` | Find past decisions similar to a scenario (hybrid similarity) |
| `get_causal_chain` | Trace upstream/downstream causal chain from a decision |
| `analyze_decision_impact` | Analyse downstream influence of a decision |

### Knowledge Graph

| Tool | Description |
|---|---|
| `add_entity` | Add a node/entity to the graph |
| `add_relationship` | Add a directed edge between two entities |
| `search_graph` | Search nodes by label or ID substring |
| `get_graph_summary` | Node/edge counts, decision count, type breakdown |
| `get_graph_analytics` | PageRank, betweenness, degree centrality, community detection |

### Reasoning

| Tool | Description |
|---|---|
| `run_reasoning` | Forward-chaining IF/THEN rules over facts |
| `abductive_reasoning` | Generate plausible hypotheses for observations |

### Export & Provenance

| Tool | Description |
|---|---|
| `export_graph` | Export graph to JSON, CSV, GraphML, Parquet, Turtle, N-Triples, RDF/XML, JSON-LD |
| `get_provenance` | Audit history and source lineage for a node |

---

## Resources (4 total)

| URI | Description |
|---|---|
| `semantica://graph/summary` | Live node/edge counts and type breakdown |
| `semantica://decisions/list` | Most recent 50 decisions |
| `semantica://schema/info` | Schema version, node/edge types, tool names |
| `semantica://ontology/schema` | Full ontology schema |

---

## Per-tool configuration

### Claude Code (`~/.claude.json` or `.mcp.json`)

Claude Code supports two MCP configuration scopes:

- **User scope** — `~/.claude.json` applies across all projects for your user account.
- **Project scope** — `.mcp.json` in your project root applies only to that project.

Both files use the same `mcpServers` structure:

```json
{
  "mcpServers": {
    "semantica": {
      "command": "python",
      "args": ["-m", "mcp"],
      "env": {
        "PYTHONPATH": "/path/to/semantica"
      }
    }
  }
}
```

> **Why `PYTHONPATH`?**  The root `mcp/` package is intentionally not included in
> the installed wheel, so `python -m mcp` only works when the repository is on
> Python's import path.  Setting `PYTHONPATH` here ensures this works regardless
> of the working directory Claude uses when it launches the server.

Or add it via the CLI (user scope):

```bash
claude mcp add --scope user semantica \
  -e PYTHONPATH=/path/to/semantica \
  -- python -m mcp
```

Or for project scope (omit `--scope user`):

```bash
claude mcp add semantica \
  -e PYTHONPATH=/path/to/semantica \
  -- python -m mcp
```

---

### Cursor (`~/.cursor/mcp.json`)

```json
{
  "mcpServers": {
    "semantica": {
      "command": "python",
      "args": ["-m", "mcp"],
      "cwd": "/path/to/semantica"
    }
  }
}
```

---

### Windsurf (`~/.codeium/windsurf/mcp_config.json`)

```json
{
  "mcpServers": {
    "semantica": {
      "command": "python",
      "args": ["-m", "mcp"],
      "cwd": "/path/to/semantica"
    }
  }
}
```

---

### Cline (VS Code extension settings)

In your VS Code `settings.json`:

```json
{
  "cline.mcpServers": {
    "semantica": {
      "command": "python",
      "args": ["-m", "mcp"],
      "cwd": "/path/to/semantica"
    }
  }
}
```

---

### Continue (`~/.continue/config.json`)

```json
{
  "mcpServers": [
    {
      "name": "semantica",
      "command": "python",
      "args": ["-m", "mcp"],
      "cwd": "/path/to/semantica"
    }
  ]
}
```

---

### VS Code (GitHub Copilot) — `.vscode/mcp.json`

```json
{
  "servers": {
    "semantica": {
      "type": "stdio",
      "command": "python",
      "args": ["-m", "mcp"],
      "cwd": "${workspaceFolder}"
    }
  }
}
```

---

### Amazon Q Developer

Add to your Q Developer MCP config:

```json
{
  "mcpServers": {
    "semantica": {
      "command": "python",
      "args": ["-m", "mcp"],
      "cwd": "/path/to/semantica"
    }
  }
}
```

---

## Environment variables

| Variable | Default | Description |
|---|---|---|
| `SEMANTICA_KG_PATH` | *(in-memory only)* | Path to a JSON file used to **load** the graph on startup and **persist** mutations (record decisions, add entities/relationships) back to disk after each change. When unset the graph lives in memory only and is lost when the server exits. |

---

## Package structure

```
mcp/
├── __init__.py          # Package entry, re-exports SemanticaMCPServer + main
├── __main__.py          # python -m mcp entry point
├── server.py            # SemanticaMCPServer class + stdio event loop
├── session.py           # Lazy ContextGraph singleton (get_graph / reset_graph)
├── schemas.py           # JSON Schema definitions for all tool inputs
├── tools/
│   ├── __init__.py      # Assembles TOOL_DEFINITIONS list
│   ├── extraction.py    # NER, relation extraction, full pipeline
│   ├── decisions.py     # Record, query, precedents, causal chain, impact
│   ├── graph.py         # Add entity/relationship, search, summary, analytics
│   ├── reasoning.py     # Forward-chaining rules, abductive hypotheses
│   └── export.py        # Graph export (multi-format) + provenance
└── resources/
    ├── __init__.py      # Re-exports RESOURCE_DEFINITIONS + handle_resource_read
    └── registry.py      # URI → handler map for the 4 semantica:// resources
```
