"""Scheduled ingest worker — refresh every Atlas workspace's Semantica graph (atlas #618).

Multi-tenant: each workspace is written to its OWN FalkorDB named graph (``ws_<workspace_id>``), so
tenants never share a graph. Run on a schedule (Railway cron / ``semantica-worker``) with a READ-ONLY
Atlas DB URL + the FalkorDB coordinates::

    ATLAS_DATABASE_URL=postgres://…  FALKORDB_HOST=…  FALKORDB_PORT=6379 \
        python -m integrations.atlas.worker            # all non-empty workspaces
    …  python -m integrations.atlas.worker --workspace <uuid>

Incremental mode (only workspaces whose issues/docs/decisions changed since the last run) is a TODO
hook — pass ``--since <iso8601>`` once wired; today it does a full per-workspace refresh (idempotent:
``push_to_falkordb`` clears+rewrites each tenant graph).
"""
from __future__ import annotations

import sys

from .atlas_adapter import AtlasSemanticaAdapter


def main(argv=None) -> int:
    argv = list(sys.argv[1:] if argv is None else argv)
    adapter = AtlasSemanticaAdapter()
    if "--workspace" in argv:
        targets = [(argv[argv.index("--workspace") + 1], None, 1)]
    else:
        targets = [w for w in adapter.list_workspaces() if w[2] > 0]

    total = 0
    for wid, name, _ in targets:
        wg = adapter.ingest(wid, persist=True)
        total += 1
        print(f"[atlas→semantica] {name or wid}: {len(wg.nodes)} nodes / {len(wg.edges)} edges "
              f"→ graph {wg.namespace}")
    print(f"[atlas→semantica] refreshed {total} workspace graph(s)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
