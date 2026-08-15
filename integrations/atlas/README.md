# Atlas → Semantica integration

Index an [Atlas](https://getsemantica.ai) workspace's artifact spine into a Semantica graph and answer
**impact / coverage / risk / assumption-provenance** questions over it — multi-tenant, one namespace
per workspace.

## Why

Atlas already links specs → sections → acceptance-criteria → issues → runs → PRs → tests → decisions
via foreign keys. Loading that into a graph turns it into interactive answers:

- *"If we remove Enterprise SSO, what's affected?"* → directional blast radius
- *"Which requirements rest on unvalidated assumptions?"* → `RESTS_ON` edges to `status != validated`
- *"Where are the accountability gaps?"* → ACs w/o test, issues w/o PR, decisions w/o run
- *"Which specs/decisions are most load-bearing?"* → betweenness centrality

## Multi-tenancy

The tenant boundary is the **workspace** (`repositories.workspace_id`). Every call is scoped to one
`workspace_id`; each workspace is written to its **own FalkorDB named graph** `ws_<workspace_id>`, and
node ids are workspace-prefixed. Isolation is enforced here (one namespace per call) **and** must be
enforced upstream by the caller's workspace auth — never expose a cross-tenant graph API to end users.

## Usage

```bash
# one-off, from the Semantica worker (read-only Atlas DB)
ATLAS_DATABASE_URL=postgres://…ro  python -m integrations.atlas.atlas_adapter --workspace <uuid>
ATLAS_DATABASE_URL=postgres://…ro  python -m integrations.atlas.atlas_adapter --all

# scheduled refresh → per-workspace FalkorDB graphs
ATLAS_DATABASE_URL=…  FALKORDB_HOST=…  python -m integrations.atlas.worker
```

```python
from integrations.atlas import AtlasSemanticaAdapter
wg = AtlasSemanticaAdapter("postgres://…ro").extract(workspace_id)   # scoped to one tenant
wg.if_removed(node_id)             # impact
wg.coverage_gaps()                 # accountability gaps
wg.unvalidated_assumptions()       # requirements on unvalidated assumptions (#611/#610)
wg.risk_hotspots(top_n=10)         # betweenness centrality
```

MCP: `mcp/tools/atlas_impact.py` exposes the four as workspace-scoped MCP tools (`atlas_if_removed`,
`atlas_coverage_gaps`, `atlas_unvalidated_assumptions`, `atlas_risk_hotspots`).

## Notes

- **Seed from explicit FKs first** (trustworthy skeleton); NLP-extracted edges layer on later,
  confidence-scored/suggested until a human verifies them.
- `assumptions` / `change_events` are additive node types (`Assumption(status)` + `RESTS_ON`,
  `ChangeEvent` + `AFFECTS`) — handled already, populated once those tables exist.
- Validated on real data: `hvogue` 2342 nodes / 1734 edges (633/889 ACs w/o test, 617/622 issues w/o
  PR); a second tenant 34 / 13; 0 cross-tenant node bleed.
