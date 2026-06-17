---
title: "MCP Server"
description: "Model Context Protocol server: expose Semantica's full capability set to Claude Desktop, VS Code, Cursor, and any MCP-aware tool."
icon: "plug"
---

**`semantica.mcp_server`** exposes Semantica's knowledge graph, decision intelligence, semantic extraction, and reasoning capabilities as an [MCP (Model Context Protocol)](https://modelcontextprotocol.io) **server over stdio**:

- 12 MCP tools exposed: extract entities, query graph, record decisions, run reasoning, export results
- No Python code required after launch: configure once, use from any MCP-aware client
- Compatible with Claude Desktop, Windsurf, Cline, Continue, VS Code, Roo Code, Cursor

## Server Interface

```json
// Configure in your MCP client (Claude Desktop, Windsurf, Cursor, VS Code, etc.)
{
  "mcpServers": {
    "semantica": {
      "command": "semantica-mcp"
    }
  }
}
```

```bash
# Or run directly
semantica-mcp
# or
python -m semantica.mcp_server
```

<Tip>
  `semantica.mcp_server` is a **stdio server process**, not a Python library. It exposes no importable classes: all interaction happens through MCP tool calls from a connected AI client.
</Tip>

<Warning>
  **The server communicates over stdio: don't add logging to stdout.** Any `print()` or logger output directed to stdout will corrupt the JSON-RPC message stream. All logging is written to `stderr` only. Configure log verbosity with the `SEMANTICA_LOG_LEVEL` environment variable.
</Warning>

## What You Get

<CardGroup cols={2}>
  <Card title="12 MCP Tools" icon="wrench">
    Extract entities, extract relations, record decisions, query decisions, find precedents, trace causal chains, add entities, add relationships, run analytics, summarise graph, run reasoning, export graph.
  </Card>
  <Card title="3 Readable Resources" icon="book-open">
    Live graph JSON (`semantica://graph/summary`), decision list, and schema/version info: readable by any MCP client.
  </Card>
  <Card title="Zero Infrastructure" icon="bolt">
    Runs over stdio: no server, no port, no Docker required. One config block to activate in any MCP client.
  </Card>
  <Card title="Persistent Graphs" icon="database">
    Point `SEMANTICA_KG_PATH` at a saved graph file to reload it automatically on every server startup.
  </Card>
  <Card title="Decision Intelligence" icon="brain">
    Record decisions, find precedents via hybrid similarity search, and trace causal chains across agent runs.
  </Card>
  <Card title="REST Alternative" icon="globe">
    The [Explorer](explorer) module offers a full HTTP API and browser dashboard if you prefer programmatic access.
  </Card>
</CardGroup>

## Installation

```bash
pip install semantica
```

The MCP server is included in the base install: no extras required.

## Configuration

<Steps>
  <Step title="Find your MCP client's settings file">

    | Client | Settings file |
    | :------ | :------------- |
    | Claude Desktop (macOS) | `~/Library/Application Support/Claude/claude_desktop_config.json` |
    | Claude Desktop (Windows) | `%APPDATA%\Claude\claude_desktop_config.json` |
    | Cursor | `.cursor/mcp.json` in your project, or `~/.cursor/mcp.json` globally |
    | VS Code / Continue | `.vscode/mcp.json` or user settings |
    | Windsurf / Cline / Roo Code | App-specific settings → MCP Servers |

  </Step>
  <Step title="Add the Semantica MCP server config">

    <CodeGroup>

    ```json Claude Desktop / Windsurf / Cline
    {
      "mcpServers": {
        "semantica": {
          "command": "semantica-mcp"
        }
      }
    }
    ```

    ```json Cursor
    {
      "mcpServers": {
        "semantica": {
          "command": "semantica-mcp",
          "env": {
            "SEMANTICA_KG_PATH": "/path/to/my_graph.json"
          }
        }
      }
    }
    ```

    ```json VS Code / Continue / Roo Code
    {
      "mcpServers": {
        "semantica": {
          "command": "python",
          "args": ["-m", "semantica.mcp_server"]
        }
      }
    }
    ```

    ```json With persistent graph
    {
      "mcpServers": {
        "semantica": {
          "command": "semantica-mcp",
          "env": {
            "SEMANTICA_KG_PATH": "/path/to/my_graph.json",
            "SEMANTICA_LOG_LEVEL": "INFO"
          }
        }
      }
    }
    ```

    </CodeGroup>

    <Warning>
      **Configure your MCP client's `command` field exactly.** The `command` field must point to the exact executable path (use `which semantica-mcp` on macOS/Linux to find it). A wrong path fails silently: the server just doesn't appear in the tools list. Test with the raw `echo | semantica-mcp` command first to confirm the binary works.
    </Warning>

  </Step>
  <Step title="Test locally before configuring your client">
    ```bash
    # Run the server directly (reads from stdin, writes to stdout)
    semantica-mcp

    # Or via Python module
    python -m semantica.mcp_server

    # Send a JSON-RPC initialize message to confirm it's working
    echo '{"jsonrpc":"2.0","id":1,"method":"initialize","params":{"protocolVersion":"2024-11-05","capabilities":{},"clientInfo":{"name":"test","version":"1.0"}}}' | semantica-mcp
    ```
  </Step>
</Steps>

## Environment Variables

| Variable | Default | Description |
| :-------- | :------- | :----------- |
| `SEMANTICA_KG_PATH` | *(none: in-memory graph)* | Path to a persisted graph file to load on startup |
| `SEMANTICA_LOG_LEVEL` | `WARNING` | Log verbosity: `DEBUG`, `INFO`, `WARNING` |

<Warning>
  **The graph starts empty unless you set `SEMANTICA_KG_PATH`.** The MCP server creates a fresh in-memory `ContextGraph` on first use. Set `SEMANTICA_KG_PATH` to a previously saved graph file to restore state across server restarts. Without it, all data is lost when the process exits.
</Warning>

<Tip>
  **Enable debug logging for troubleshooting.** Set `SEMANTICA_LOG_LEVEL=DEBUG` in your MCP client's `env` block, or run `python -m semantica.mcp_server` directly and inspect stderr output.
</Tip>

## Tools

The MCP server exposes 12 tools that any connected AI assistant can call:

| Tool | Category | Description |
| :---- | :-------- | :----------- |
| `extract_entities` | Extraction | NER: find people, places, organisations, concepts |
| `extract_relations` | Extraction | Typed relation and triplet extraction |
| `record_decision` | Decision Intelligence | Save a decision with reasoning and outcome |
| `query_decisions` | Decision Intelligence | Search recorded decisions by natural language or category |
| `find_precedents` | Decision Intelligence | Hybrid similarity search over past decisions |
| `get_causal_chain` | Decision Intelligence | Trace upstream / downstream causal chains |
| `add_entity` | Graph Operations | Add a node to the live graph |
| `add_relationship` | Graph Operations | Add a directed edge between two nodes |
| `get_graph_summary` | Graph Operations | Node count, decision count, graph status |
| `get_graph_analytics` | Graph Operations | PageRank centrality and community detection |
| `run_reasoning` | Reasoning | Forward-chain IF/THEN rules over facts |
| `export_graph` | Reasoning & Export | Serialise the graph (`turtle`/`ttl`: RDF Turtle aliases, `nt`, `xml`, `json-ld`, `json`) |

### Knowledge Extraction

<AccordionGroup>

<Accordion title="extract_entities" icon="tag">

Extract named entities (people, places, organisations, concepts) from text using Semantica NER.

**Input:**

```json
{ "text": "Apple Inc. was founded by Steve Jobs in Cupertino in 1976." }
```

**Output:**

```json
{
  "entities": [
    { "label": "Apple Inc.", "type": "ORGANIZATION", "start": 0,  "end": 10,  "confidence": 0.98 },
    { "label": "Steve Jobs", "type": "PERSON",       "start": 26, "end": 36,  "confidence": 0.99 },
    { "label": "Cupertino",  "type": "LOCATION",     "start": 40, "end": 49,  "confidence": 0.97 },
    { "label": "1976",       "type": "DATE",          "start": 53, "end": 57,  "confidence": 0.95 }
  ],
  "count": 4
}
```

</Accordion>

<Accordion title="extract_relations" icon="arrows-left-right">

Extract typed relations and `(subject, predicate, object)` triplets from text.

**Input:**

```json
{ "text": "Steve Jobs founded Apple Inc. and led it until 2011." }
```

**Output:**

```json
{
  "relations": [
    { "source": "Steve Jobs", "type": "founded", "target": "Apple Inc.", "confidence": 0.96 }
  ],
  "triplets": [
    { "subject": "Steve Jobs", "predicate": "founded", "object": "Apple Inc." }
  ],
  "relation_count": 1,
  "triplet_count": 1
}
```

</Accordion>

</AccordionGroup>

### Decision Intelligence

<AccordionGroup>

<Accordion title="record_decision" icon="check-circle">

Record a decision with full context, reasoning, and metadata into the knowledge graph.

**Input:**

```json
{
  "category": "model_selection",
  "scenario": "Choose LLM for production reasoning pipeline",
  "reasoning": "GPT-4 benchmark advantage justifies 3x cost increase",
  "outcome": "selected_gpt4",
  "confidence": 0.91,
  "decision_maker": "product_team",
  "valid_from": "2024-01-01",
  "valid_until": "2024-12-31"
}
```

Required fields: `category`, `scenario`, `reasoning`, `outcome`, `confidence`.
Optional: `decision_maker` (defaults to `"mcp_client"`), `valid_from`, `valid_until`.

**Output:**

```json
{ "decision_id": "dec_a1b2c3", "status": "recorded" }
```

</Accordion>

<Accordion title="query_decisions" icon="magnifying-glass">

Query recorded decisions by natural language or category filter.

**Input:**

```json
{ "query": "model selection", "category": "model_selection", "limit": 5 }
```

All fields are optional. `limit` defaults to `10`. When `query` is provided, similarity search is used. When omitted, `category` filter applies.

</Accordion>

<Accordion title="find_precedents" icon="clock-rotate-left">

Find past decisions similar to a given scenario using hybrid similarity search.

**Input:**

```json
{ "scenario": "Choose cloud provider for HIPAA workload", "max_results": 5 }
```

`max_results` defaults to `5`, maximum `50`.

<Tip>
  **Use `find_precedents` before high-stakes decisions.** The tool performs hybrid similarity search across all recorded decisions. Call it at the start of any significant decision path: it surfaces past reasoning that may be directly applicable, reducing redundant work and improving consistency across agent runs.
</Tip>

</Accordion>

<Accordion title="get_causal_chain" icon="diagram-project">

Trace the causal chain upstream or downstream from a decision.

**Input:**

```json
{ "decision_id": "dec_a1b2c3", "direction": "downstream", "max_depth": 5 }
```

`direction` accepts `"upstream"` or `"downstream"` (default: `"downstream"`).
`max_depth` defaults to `5`, maximum `20`.

</Accordion>

</AccordionGroup>

### Graph Operations

<AccordionGroup>

<Accordion title="add_entity" icon="circle-plus">

Add a node/entity to the live knowledge graph.

**Input:**

```json
{
  "id": "apple_inc",
  "label": "Apple Inc.",
  "type": "Organization",
  "metadata": { "founded": 1976, "hq": "Cupertino" }
}
```

Only `id` is required. `label` defaults to the `id` value. `type` defaults to `"Entity"`.

</Accordion>

<Accordion title="add_relationship" icon="arrow-right">

Add a directed relationship (edge) between two existing entities.

**Input:**

```json
{
  "source": "steve_jobs",
  "target": "apple_inc",
  "type": "FOUNDED",
  "metadata": { "year": 1976 }
}
```

`source` and `target` are required. `type` defaults to `"RELATED_TO"`.

</Accordion>

<Accordion title="get_graph_summary" icon="info-circle">

Return a high-level summary of the current knowledge graph.

**Output:**

```json
{
  "node_count": 42,
  "decision_count": 5,
  "graph_ready": true
}
```

Takes no input parameters.

</Accordion>

<Accordion title="get_graph_analytics" icon="chart-bar">

Compute PageRank centrality and community detection over the current graph. Returns top nodes by PageRank, community count, and overall node/edge counts.

Takes no input parameters.

</Accordion>

</AccordionGroup>

### Reasoning

<AccordionGroup>

<Accordion title="run_reasoning" icon="brain">

Run forward-chaining IF/THEN rules over a set of facts to derive new facts.

**Input:**

```json
{
  "facts": ["Employee(John)", "Manager(John)"],
  "rules": ["IF Manager(?x) THEN HasAuthority(?x)"]
}
```

**Output:**

```json
{ "derived_facts": ["HasAuthority(John)"] }
```

</Accordion>

</AccordionGroup>

### Export

<AccordionGroup>

<Accordion title="export_graph" icon="file-export">

Export the current knowledge graph to a serialisation format.

**Input:**

```json
{ "format": "json-ld" }
```

Supported formats: `turtle`, `ttl`, `nt`, `xml`, `json-ld`, `json`. Default is `json-ld`.

</Accordion>

</AccordionGroup>

## Resources

The MCP server exposes three readable resources:

| URI | Description |
| :--- | :----------- |
| `semantica://graph/summary` | High-level graph statistics |
| `semantica://decisions/list` | All recorded decisions (up to 50) |
| `semantica://schema/info` | Server version and available tools |

<CardGroup cols={2}>
  <Card title="Context" icon="brain" href="context">
    The ContextGraph that the MCP server operates on.
  </Card>
  <Card title="Semantic Extract" icon="magnifying-glass" href="semantic_extract">
    NER and relation extraction powering the MCP tools.
  </Card>
  <Card title="Reasoning" icon="microchip" href="reasoning">
    Forward-chaining engine behind run_reasoning.
  </Card>
  <Card title="Agno Integration" icon="robot" href="../integrations/agno">
    Use Semantica inside Agno multi-agent teams.
  </Card>
</CardGroup>
