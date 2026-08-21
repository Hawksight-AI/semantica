#!/bin/sh
# Semantica MCP entrypoint.
#
# Connects the MCP server to the Semantica platform:
#   - joins the same Docker network (compose)
#   - optionally pulls the current platform graph snapshot from the
#     explorer API (POST /api/export) into /data/kg.json and loads it
#     via SEMANTICA_KG_PATH, so MCP tools operate on platform data.
#
# Set SEMANTICA_SYNC_PLATFORM=false to skip the graph sync.

set -e

if [ "${SEMANTICA_SYNC_PLATFORM:-true}" = "true" ]; then
  echo "[semantica-mcp] syncing graph from platform explorer..."
  python - <<'PY'
import json
import os
import urllib.request

try:
    req = urllib.request.Request(
        "http://explorer:8000/api/export",
        data=json.dumps({"format": "json"}).encode(),
        headers={"Content-Type": "application/json"},
    )
    with urllib.request.urlopen(req, timeout=20) as resp:
        graph = json.loads(resp.read().decode("utf-8"))
    # Prefer the shared volume (/shared — mounted by compose on both the
    # Explorer and the MCP server), falling back to /data and /tmp when
    # unwritable (the container runs as the non-root `semantica` user).
    candidates = ["/shared/kg.json", "/data/kg.json", "/tmp/kg.json"]
    path = None
    for candidate in candidates:
        try:
            os.makedirs(os.path.dirname(candidate), exist_ok=True)
            with open(candidate, "w", encoding="utf-8") as f:
                json.dump(graph, f, ensure_ascii=False)
            path = candidate
            break
        except OSError:
            continue
    if path is None:
        raise RuntimeError("no writable path for kg.json")
    entities = len(graph.get("entities", []))
    relationships = len(graph.get("relationships", []))
    print(f"[semantica-mcp] graph synced: {entities} entities, {relationships} relationships -> {path}")
except Exception as exc:  # noqa: BLE001
    print(f"[semantica-mcp] graph sync skipped: {exc}")
PY
  export SEMANTICA_KG_PATH="${SEMANTICA_KG_PATH:-/shared/kg.json}"
fi

echo "[semantica-mcp] starting bridge: $*"
exec "$@"
