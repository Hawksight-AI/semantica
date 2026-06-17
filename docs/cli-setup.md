---
title: "CLI Setup"
description: "The five Semantica executables: what each one does, when to use it, and how to confirm it is working."
icon: "terminal"
---

Installing the base package registers five executables on your `PATH`. Each serves a distinct purpose. This page explains what they are, how to verify they are available, and which one to reach for in each situation.


## Installed Commands

```bash
pip install semantica
```

After installation the following commands are available:

| Command | Entry point | What it does |
| :------- | :----------- | :------------ |
| `semantica` | `semantica.cli:main` | General-purpose CLI for pipeline runs, extraction, and graph operations |
| `semantica-server` | `semantica.server:main` | FastAPI/uvicorn REST API server bound to `0.0.0.0:8000` |
| `semantica-worker` | `semantica.worker:main` | Background worker process entry point for Semantica deployments |
| `semantica-explorer` | `semantica.explorer:main` | Interactive browser dashboard for knowledge graph exploration |
| `semantica-mcp` | `semantica.mcp_server:main` | MCP server (stdio) for Claude Desktop, Cursor, Windsurf, and other MCP clients |

<Note>
  `semantica-explorer` requires `pip install semantica[explorer]`. Running it without that extra will immediately print an error and exit. See [Explorer Setup](explorer-setup) for the full walkthrough.
</Note>


## Verify the Installation

Confirm each command is reachable and prints its usage:

```bash
semantica --help
semantica-server --help
semantica-worker --help
semantica-explorer --help
semantica-mcp --help
```

Confirm the package version:

```bash
python -c "import semantica; print(semantica.__version__)"
```


## When to Use Each Command

- **semantica** — The general-purpose CLI. Use it for one-off pipeline runs, entity extraction, and graph operations from a shell script or CI job.
- **semantica-server** — Starts the REST API server. Binds to `0.0.0.0:8000`. Use this when another service or application needs programmatic access to Semantica over HTTP.
- **semantica-worker** — Background task processor. Run alongside `semantica-server` when you need async pipeline execution outside the request cycle. Start the server first, then start one or more workers pointing at the same backend.
- **semantica-explorer** — Launches the browser dashboard. Requires `pip install semantica[explorer]`. Use this to explore a saved knowledge graph interactively. See [Explorer Setup](explorer-setup).
- **semantica-mcp** — Runs the MCP server over stdio. Configure it in your MCP client's settings file to expose all 12 tools and 3 resources to Claude Desktop, Cursor, Windsurf, or any MCP-aware client. See [MCP Server](reference/mcp_server).


## Usage Examples

<Tabs>
  <Tab title="REST server">
    ```bash
    # Starts FastAPI + uvicorn on 0.0.0.0:8000
    semantica-server
    ```

    Once running, check it with:

    ```bash
    curl http://localhost:8000/health
    # {"status": "healthy"}

    curl http://localhost:8000/api/info
    # {"name": "Semantica API", "version": "...", "status": "active"}
    ```

    The interactive API docs are at `http://localhost:8000/docs`.
  </Tab>
  <Tab title="Worker">
    ```bash
    semantica-worker
    ```

    The worker exits cleanly on `SIGINT` (Ctrl-C) or `SIGTERM`.
  </Tab>
  <Tab title="MCP client config">
    Add to your MCP client's settings file:

    ```json
    {
      "mcpServers": {
        "semantica": {
          "command": "semantica-mcp"
        }
      }
    }
    ```

    Or use the Python module form if the command is not on `PATH`:

    ```json
    {
      "mcpServers": {
        "semantica": {
          "command": "python",
          "args": ["-m", "semantica.mcp_server"]
        }
      }
    }
    ```

    Test it directly before configuring your client:

    ```bash
    echo '{"jsonrpc":"2.0","id":1,"method":"initialize","params":{"protocolVersion":"2024-11-05","capabilities":{},"clientInfo":{"name":"test","version":"1.0"}}}' | semantica-mcp
    ```

    You should receive a JSON-RPC response. See [MCP Server](reference/mcp_server) for the full list of tools and resources.
  </Tab>
  <Tab title="Explorer">
    ```bash
    pip install semantica[explorer]
    semantica-explorer --graph my_graph.json
    ```

    See [Explorer Setup](explorer-setup) for the full walkthrough including how to build and save a graph file.
  </Tab>
  <Tab title="Python module form">
    Every command also runs as a Python module: useful when the script directory is not on `PATH`:

    ```bash
    python -m semantica.mcp_server
    python -m semantica.explorer --graph my_graph.json
    ```
  </Tab>
</Tabs>


## Environment Variables

`semantica-mcp` reads two environment variables:

| Variable | Default | Description |
| :-------- | :------- | :----------- |
| `SEMANTICA_KG_PATH` | *(none)* | Path to a saved graph file to load on startup |
| `SEMANTICA_LOG_LEVEL` | `WARNING` | Log verbosity: `DEBUG`, `INFO`, `WARNING` |

`semantica-server` reads one:

| Variable | Default | Description |
| :-------- | :------- | :----------- |
| `SEMANTICA_CORS_ORIGINS` | `http://localhost:5173,http://127.0.0.1:5173` | Comma-separated list of allowed CORS origins |

No other environment variables are read by these commands.


## Troubleshooting

<AccordionGroup>

<Accordion title="command not found" icon="terminal">

The executables land in `bin/` (Linux/Mac) or `Scripts/` (Windows) of the active Python environment. If the command is not found, that directory is likely not on `PATH`.

Activate your virtual environment first:

```bash
source venv/bin/activate   # Linux / Mac
venv\Scripts\activate      # Windows
semantica --help
```

Find where pip placed the scripts:

```bash
python -m site --user-scripts   # user-level install
pip show -f semantica           # shows all installed files
```

</Accordion>

<Accordion title="Command found but crashes on import" icon="triangle-exclamation">

```bash
pip install --upgrade semantica
python -c "import semantica; print(semantica.__version__)"
```

If you have multiple Python environments, install into the one the shell resolves:

```bash
python -m pip install semantica
```

</Accordion>

<Accordion title="semantica-explorer: uvicorn is required" icon="map">

The Explorer extras are not included in the base install:

```bash
pip install semantica[explorer]
```

</Accordion>

<Accordion title="semantica-mcp silent failure inside a MCP client" icon="plug">

The MCP server communicates over stdio. Test it directly from the shell first:

```bash
echo '{"jsonrpc":"2.0","id":1,"method":"ping","params":{}}' | semantica-mcp
```

A response of `{"jsonrpc":"2.0","id":1,"result":{}}` confirms the server is working. If you see nothing, check that the command is on `PATH` and the base package is installed.

</Accordion>

<Accordion title="Windows: DLL errors on startup" icon="windows">

Install the [Microsoft Visual C++ Redistributable](https://aka.ms/vs/17/release/vc_redist.x64.exe). This is a Windows system dependency required by PyTorch and related packages, not a Semantica bug.

</Accordion>

</AccordionGroup>


## Next Steps

- [Explorer Setup](explorer-setup) — Build a graph, save it, and launch the browser dashboard.
- [MCP Server](reference/mcp_server) — All 12 tools and 3 resources exposed over the MCP protocol.
- [Installation](installation) — Virtual environments, optional extras, and platform-specific notes.
- [Quickstart](quickstart) — End-to-end pipeline walkthrough with working code.
