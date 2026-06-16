# Semantica Knowledge Explorer

A browser-based graph workbench for the [Semantica](https://github.com/semantica-agi/semantica) platform. Pan and zoom live graphs, scrub the timeline, trace every decision's causal chain, resolve duplicates, and author your ontology visually. Built on React 19 + Sigma.js.

---

## Requirements

| Dependency | Minimum version |
| --- | --- |
| Python | 3.8+ |
| Node.js | 18.x or higher (20.x recommended) |
| npm | 9.x or higher |

```bash
python --version
node --version
npm --version
```

---

## Two ways to run the Explorer

### Option A — pip install (recommended for users)

Install the package with the explorer extras. The pre-built frontend bundle is included in the wheel so no Node.js is required.

```bash
pip install "semantica[explorer]"
```

Launch the dashboard by pointing it at any graph JSON file:

```bash
semantica-explorer --graph my_graph.json
```

The server starts at `http://127.0.0.1:8000` and opens the dashboard in your default browser automatically.

CLI flags:

| Flag | Default | Description |
| --- | --- | --- |
| `--graph` / `-g` | *(required)* | Path to a ContextGraph JSON file |
| `--port` / `-p` | `8000` | Port to bind the server to |
| `--host` | `127.0.0.1` | Host to bind (use `127.0.0.1` for local-only; see security note below) |
| `--no-browser` | off | Skip opening the browser automatically |

Examples:

```bash
# Default — opens at http://127.0.0.1:8000
semantica-explorer --graph my_graph.json

# Custom port
semantica-explorer --graph my_graph.json --port 8080

# Suppress auto-open
semantica-explorer --graph my_graph.json --no-browser

# Equivalent using python -m
python -m semantica.explorer --graph my_graph.json
```

> **Security note:** The Explorer API has no built-in authentication. The default `--host 127.0.0.1` binds to localhost only, so it is not reachable from other machines on your network. If you bind to `0.0.0.0`, all graph data is readable and writable by any host that can reach the port. The CLI will print a warning in that case.

---

### Option B — run from source (for contributors / frontend development)

This mode runs the React dev server with hot module replacement, so frontend changes appear in the browser instantly without rebuilding.

#### Step 1 — Clone the repo

```bash
git clone https://github.com/semantica-agi/semantica.git
cd semantica
```

#### Step 2 — Install the Python package

```bash
pip install -e ".[explorer]"
```

#### Step 3 — Install frontend dependencies

```bash
cd explorer
npm ci
```

#### Step 4 — Start the Python backend

Open a terminal in the repo root:

```bash
semantica-explorer --graph path/to/my_graph.json --no-browser
```

This starts the API on `http://127.0.0.1:8000`. Keep this terminal open.

#### Step 5 — Start the frontend dev server

Open a second terminal in `explorer/`:

```bash
npm run dev
```

Vite starts on **`http://localhost:5173`**. Open that URL in your browser. All `/api` and `/ws` requests are automatically proxied to the Python backend at `http://127.0.0.1:8000`.

---

## Building the production bundle

If you need to serve the UI from the Python server directly (without the Vite dev server):

```bash
cd explorer
npm ci
npm run build
```

This writes the compiled assets to `../semantica/static/`. The Python server then serves the full dashboard at `http://127.0.0.1:8000` — no separate Vite process needed.

---

## Workspaces

| Workspace | What you can do |
| --- | --- |
| **Knowledge Graph** | Live Sigma.js canvas · ForceAtlas2 layout · Ego Mode · semantic distance heatmap · path highlighting |
| **Timeline** | Temporal event scrubber — watch the graph evolve across time |
| **Decisions** | Browse causal chains behind every recorded decision with outcome badges and confidence scores |
| **Registry** | Live audit log of every graph mutation (add-node, add-edge, delete, update) |
| **Entity Resolution** | Review and merge duplicate entities with blocking + semantic dedup |
| **KG Overview** | Aggregate stats, community breakdown, centrality heatmap |
| **Ontology Hub** | SHACL Studio · visual drag-and-drop editor · cross-ontology alignments · SKOS browser |
| **Lineage** | W3C PROV-O provenance visualization for any entity |

---

## Environment variables

| Variable | Default | Description |
| --- | --- | --- |
| `EXPLORER_CORS_ORIGINS` | `http://localhost:5173,http://127.0.0.1:5173` | Comma-separated list of allowed CORS origins |
| `EXPLORER_CORS_CREDENTIALS` | `false` | Set to `true` to allow credentialed cross-origin requests (only needed behind an authenticating reverse proxy) |

---

## Available scripts

Run these from inside the `explorer/` directory:

```bash
# Start the dev server with hot module replacement
npm run dev

# Type-check and build the production bundle into ../semantica/static/
npm run build

# Preview the production build locally
npm run preview

# Run ESLint over all source files
npm run lint

# Run the graph store multi-edge unit tests
npm run test:graph-store

# Run the graph workspace display tests
npm run test:graph-workspace
```

---

## API & WebSocket proxy (dev mode only)

During development, Vite forwards requests automatically — no CORS configuration needed:

| Pattern | Forwarded to |
| --- | --- |
| `/api/*` | `http://127.0.0.1:8000/api/*` |
| `/ws/*` | `ws://127.0.0.1:8000/ws/*` |

To run the backend on a different port, update `server.proxy` in [vite.config.ts](vite.config.ts).

---

## Project structure

```text
explorer/
├── src/
│   ├── App.tsx                        # Root layout, tab routing, workspace wiring
│   ├── index.css                      # Global resets, fonts, keyframe animations
│   ├── store/
│   │   ├── graphStore.ts              # In-memory graph state
│   │   └── registryStore.ts           # Pub/sub audit registry
│   └── workspaces/
│       ├── GraphWorkspace/            # Sigma.js canvas + inspector + behaviors
│       ├── DecisionWorkspace/         # Causal flow diagram + decision list
│       ├── DiffMergeWorkspace/        # Graph diff and merge view
│       ├── EnrichWorkspace/           # Entity resolution + registry tabs
│       ├── ImportExportWorkspace/     # Import CSV/JSON, export graph
│       ├── LineageWorkspace/          # W3C PROV-O lineage diagram
│       ├── ManageWorkspace/           # KG Overview + Ontology Summary
│       ├── OntologyWorkspace/         # SHACL Studio, visual editor, SKOS browser
│       ├── SparqlWorkspace/           # In-browser SPARQL query editor
│       └── VocabularyWorkspace/       # SKOS vocabulary manager
├── index.html
├── vite.config.ts                     # Dev proxy → 127.0.0.1:8000, build → ../semantica/static
└── package.json
```

---

## Troubleshooting

### Dashboard shows a blank white page or "UI not available" message

The frontend bundle is missing from the server's static directory. Fix options:

- **If you installed via pip:** `pip install --upgrade "semantica[explorer]"` — the wheel includes the pre-built bundle.
- **If you installed from source:** run `cd explorer && npm ci && npm run build` from the repo root, then restart the server.
- **In dev mode:** use the Vite dev server at `http://localhost:5173` instead of the backend URL.

### Blank graph / no data loads in the browser

- Confirm the Python backend is running and check the terminal for errors.
- Open browser DevTools → Network tab and look for failed `/api/graph` requests.
- If the backend is on a different port, update `server.proxy` in `vite.config.ts`.

### `npm ci` fails or reports missing lockfile

The `package-lock.json` must be present. Run `npm install` once to generate it, commit it, then use `npm ci` going forward.

### `npm run dev` fails with Node version error

Vite 6 requires **Node 18 or higher**. Run `node --version` to check. If you're on Node 16, upgrade via [nvm](https://github.com/nvm-sh/nvm) or the official Node.js installer.

### Port 5173 already in use

Vite automatically tries the next available port and prints the actual URL in the terminal. Use the URL shown in the output.

### WebSocket not connecting (real-time mutations not appearing)

- Confirm the backend exposes the `/ws/graph-updates` WebSocket endpoint.
- Check DevTools → Network → WS tab for the connection status and error code.
- Ensure the backend version matches the frontend — mixing major versions can cause protocol mismatches.

---

## Tech stack

- **React 19** + TypeScript (strict mode)
- **Vite 6** with `babel-plugin-react-compiler`
- **Sigma.js 3** + **Graphology** — graph rendering and in-memory graph model
- **ForceAtlas2** — physics-based layout
- **@tanstack/react-query** — async data fetching for ontology and vocab tabs
- **vis-timeline** — temporal event visualization
- **@xyflow/react** — lineage diagram rendering
- **Monaco Editor** — in-browser SPARQL / SHACL editor
- **lucide-react** — icon set

---

## Contributing

See the root [CONTRIBUTING.md](../CONTRIBUTING.md) and open issues on the main [Semantica repository](https://github.com/semantica-agi/semantica).
