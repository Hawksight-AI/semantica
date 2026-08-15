"""Atlas → Semantica ingestion adapter + insight queries — MULTI-TENANT (atlas #618).

Tenant model
------------
The tenant boundary in Atlas is the **workspace**. This adapter is namespace-per-workspace: every
call is scoped to one ``workspace_id``, each workspace gets its **own named graph**
(``ns = f"ws_{workspace_id}"``) in FalkorDB / its own vector namespace, and node ids are also
workspace-prefixed so two tenants can never share a node even if graphs are co-located. Isolation is
enforced twice: (1) here, by only ever reading/writing one workspace's namespace, and (2) upstream, by
Atlas's own workspace auth / FGA when it calls this — never expose a cross-tenant graph API to users.

What it does
------------
1. EXTRACT the workspace's spine from Atlas Postgres (read-only), seeded from explicit FKs (a
   trustworthy skeleton; NLP-extracted edges would be layered on later, confidence-scored).
2. BUILD a Semantica ContextGraph (+ optional FalkorDB persistence, one named graph per workspace).
3. ANSWER: blast-radius / "if we remove X", coverage gaps, risk hotspots (betweenness),
   "which requirements rest on unvalidated assumptions".

Run (as a Semantica worker, Atlas DATABASE_URL injected read-only)::

    ATLAS_DATABASE_URL=postgres://…  python -m integrations.atlas.atlas_adapter --all
    ATLAS_DATABASE_URL=postgres://…  python -m integrations.atlas.atlas_adapter --workspace <uuid>

Grounded in the verified Atlas schema and the Semantica ContextGraph / CentralityCalculator APIs.
"""
from __future__ import annotations

import os
import sys
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Tuple

import psycopg2

# ── Node / edge taxonomy ─────────────────────────────────────────────────────────────────────────
# Structural edges we ingest from Atlas FKs. Directionality matters for impact traversal: DOWNSTREAM
# edges are the ones a change propagates along (parent → child / thing → its dependents).
DOWNSTREAM_EDGES = {"HAS_SECTION", "HAS_AC", "VERIFIED_BY", "LINKED_TO", "RESTS_ON"}
# AFFECTS is emitted by a ChangeEvent onto what it touches (incoming to the touched node).

DEFAULT_NAMESPACE_PREFIX = "ws_"


@dataclass
class WorkspaceGraph:
    """One tenant's graph: the namespace + node/edge lists + a lazily-built Semantica ContextGraph."""
    workspace_id: str
    namespace: str
    nodes: List[dict] = field(default_factory=list)
    edges: List[dict] = field(default_factory=list)
    _cg: Any = None
    _status: Dict[str, str] = field(default_factory=dict)   # node_id -> assumption status

    # ---- Semantica ContextGraph (in-memory algorithm layer) ----
    def context_graph(self):
        if self._cg is None:
            from semantica.context import ContextGraph
            cg = ContextGraph()
            cg.add_nodes(self.nodes)
            cg.add_edges(self.edges)
            self._cg = cg
        return self._cg

    # ---- Insight queries (all scoped to THIS workspace's graph) ----
    def if_removed(self, node_id: str, max_depth: int = 8) -> Dict[str, List[str]]:
        """"If we remove <node_id>, what's affected?" — directional downstream reachability + any
        ChangeEvents that AFFECT the impacted set. Returns impacted node labels grouped by type."""
        nid = self._scope(node_id)
        out: Dict[str, List[dict]] = {}
        for e in self.edges:
            out.setdefault(e["source"], []).append(e)
        seen, frontier = {nid}, [nid]
        for _ in range(max_depth):
            nxt = []
            for u in frontier:
                for e in out.get(u, []):
                    if e["type"] in DOWNSTREAM_EDGES and e["target"] not in seen:
                        seen.add(e["target"]); nxt.append(e["target"])
            frontier = nxt
            if not frontier:
                break
        for e in self.edges:                                  # pull in change events touching the set
            if e["type"] == "AFFECTS" and e["target"] in seen:
                seen.add(e["source"])
        seen.discard(nid)
        grouped: Dict[str, List[str]] = {}
        for n in self.nodes:
            if n["id"] in seen:
                grouped.setdefault(n["type"], []).append(n["label"])
        return grouped

    def unvalidated_assumptions(self) -> List[Tuple[str, str, str]]:
        """"Which requirements rest on unvalidated assumptions?" — every RESTS_ON edge whose target
        Assumption node's status != 'validated'. Returns (requirement_label, assumption_label, status)."""
        lbl = {n["id"]: n["label"] for n in self.nodes}
        rows = []
        for e in self.edges:
            if e["type"] != "RESTS_ON":
                continue
            status = self._status.get(e["target"], "unknown")
            if status != "validated":
                rows.append((lbl.get(e["source"], e["source"]), lbl.get(e["target"], e["target"]), status))
        return rows

    def coverage_gaps(self) -> Dict[str, List[str]]:
        """Structural accountability gaps, from the edge set."""
        lbl = {n["id"]: n["label"] for n in self.nodes}
        typ = {n["id"]: n["type"] for n in self.nodes}
        has_out = lambda i, t: any(e["source"] == i and e["type"] == t for e in self.edges)
        has_in = lambda i, t, st=None: any(
            e["target"] == i and e["type"] == t and (st is None or typ.get(e["source"]) == st) for e in self.edges)
        gaps = {
            "acs_without_test": [lbl[i] for i in typ if typ[i] == "AC" and not has_out(i, "VERIFIED_BY")],
            "sections_without_ac": [lbl[i] for i in typ if typ[i] == "Section" and not has_out(i, "HAS_AC")],
            "issues_without_pr": [lbl[i] for i in typ if typ[i] == "Issue" and not has_in(i, "LINKED_TO", "PR")],
            "decisions_without_run": [lbl[i] for i in typ if typ[i] == "Decision" and not has_out(i, "FROM_RUN")],
        }
        return gaps

    def risk_hotspots(self, top_n: int = 10) -> List[Tuple[str, float]]:
        """Most load-bearing nodes by betweenness centrality (Semantica's CentralityCalculator)."""
        from semantica.kg.centrality_calculator import CentralityCalculator
        graph = {"nodes": [n["id"] for n in self.nodes],
                 "edges": [(e["source"], e["target"]) for e in self.edges]}
        bc = CentralityCalculator().calculate_betweenness_centrality(graph)
        scores = bc.get("centrality", bc) if isinstance(bc, dict) else bc
        lbl = {n["id"]: f'{n["type"]}: {n["label"]}' for n in self.nodes}
        ranked = sorted(((lbl.get(k, k), float(v)) for k, v in scores.items() if isinstance(v, (int, float))),
                        key=lambda x: -x[1])
        return ranked[:top_n]

    def _scope(self, raw_id: str) -> str:
        rid = str(raw_id)
        return rid if rid.startswith(self.namespace + ":") else f"{self.namespace}:{rid}"


class AtlasSemanticaAdapter:
    """Reads Atlas Postgres (read-only) and produces per-workspace Semantica graphs."""

    def __init__(self, atlas_db_url: Optional[str] = None):
        self.conn = psycopg2.connect(atlas_db_url or os.environ["ATLAS_DATABASE_URL"])
        self.conn.set_session(readonly=True)

    def list_workspaces(self) -> List[Tuple[str, str, int]]:
        cur = self.conn.cursor()
        cur.execute("""
            select w.id, coalesce(w.name,'?'),
                   (select count(*) from issues i join repositories r on r.id=i.repository_id
                    where r.workspace_id=w.id) issues
            from workspaces w order by issues desc""")
        return [(str(a), b, c) for a, b, c in cur.fetchall()]

    # ── EXTRACT (workspace-scoped; seed from explicit FKs) ────────────────────────────────────────
    def extract(self, workspace_id: str) -> WorkspaceGraph:
        ns = f"{DEFAULT_NAMESPACE_PREFIX}{workspace_id}"
        wg = WorkspaceGraph(workspace_id=str(workspace_id), namespace=ns)
        seen: set = set()

        def N(raw, ntype, label, status: Optional[str] = None):
            if raw is None:
                return
            nid = f"{ns}:{raw}"
            if nid not in seen:
                seen.add(nid)
                wg.nodes.append({"id": nid, "type": ntype, "label": (label or "")[:120],
                                 "properties": {"type": ntype, "workspace_id": str(workspace_id),
                                                **({"status": status} if status else {})}})
                if status:
                    wg._status[nid] = status

        def E(s, d, t):
            if s is not None and d is not None:
                wg.edges.append({"source": f"{ns}:{s}", "target": f"{ns}:{d}", "type": t})

        cur = self.conn.cursor()
        cur.execute("select id from repositories where workspace_id=%s", (workspace_id,))
        repo_ids = [str(r[0]) for r in cur.fetchall()]  # cast for the ANY(%s::uuid[]) params below

        cur.execute("select id, title from documents where workspace_id=%s", (workspace_id,))
        for did, title in cur.fetchall():
            N(did, "Doc", title)
        cur.execute("""select s.id, s.document_id, s.title, s.linked_issue_id from spec_sections s
                       join documents d on d.id=s.document_id where d.workspace_id=%s""", (workspace_id,))
        for sid, did, title, li in cur.fetchall():
            N(sid, "Section", title); E(did, sid, "HAS_SECTION")
            if li:
                E(sid, li, "LINKED_TO")
        cur.execute("""select a.id, a.section_id, a.description, a.linked_issue_id from acceptance_criteria a
                       join spec_sections s on s.id=a.section_id join documents d on d.id=s.document_id
                       where d.workspace_id=%s""", (workspace_id,))
        for aid, sid, desc, li in cur.fetchall():
            N(aid, "AC", desc); E(sid, aid, "HAS_AC")
            if li:
                E(aid, li, "LINKED_TO")

        if repo_ids:
            cur.execute("""select id, acceptance_criterion_id from test_case_specs
                           where repository_id = ANY(%s::uuid[]) and acceptance_criterion_id is not null""", (repo_ids,))
            for tid, aid in cur.fetchall():
                N(tid, "TestSpec", "test"); E(aid, tid, "VERIFIED_BY")
            cur.execute("select id, number, title from issues where repository_id = ANY(%s::uuid[])", (repo_ids,))
            for iid, num, title in cur.fetchall():
                N(iid, "Issue", f"#{num} {title}")
            cur.execute("""select i.issue_id, i.document_id from issue_documents i
                           join issues s on s.id=i.issue_id where s.repository_id = ANY(%s::uuid[])""", (repo_ids,))
            for iid, did in cur.fetchall():
                E(iid, did, "SPECIFIED_BY")
            cur.execute("select id, issue_id from agent_runs where repository_id = ANY(%s::uuid[]) and issue_id is not null", (repo_ids,))
            for rid, iid in cur.fetchall():
                N(rid, "Run", "run"); E(rid, iid, "WORKS_ON")
            cur.execute("select id, issue_id from linked_pull_requests where repository_id = ANY(%s::uuid[]) and issue_id is not null", (repo_ids,))
            for pid, iid in cur.fetchall():
                N(pid, "PR", "pr"); E(pid, iid, "LINKED_TO")

        cur.execute("select id, header, run_id from decisions where workspace_id=%s", (workspace_id,))
        for did2, hdr, rid in cur.fetchall():
            N(did2, "Decision", hdr)
            if rid:
                E(did2, rid, "FROM_RUN")

        # Assumptions + change-events are additive node types (SpecOps #611/#610). Ingested here once
        # those tables land; the graph + queries already handle Assumption(status)/RESTS_ON + ChangeEvent/AFFECTS.
        self._extract_assumptions_if_present(cur, workspace_id, N, E)
        return wg

    def _extract_assumptions_if_present(self, cur, workspace_id, N, E):
        """Best-effort: pull assumptions/change-events if those tables exist yet (#611/#610)."""
        try:
            cur.execute("select to_regclass('public.assumptions')")
            if cur.fetchone()[0]:
                cur.execute("select id, statement, status, requirement_id from assumptions where workspace_id=%s", (workspace_id,))
                for aid, stmt, status, req in cur.fetchall():
                    N(aid, "Assumption", stmt, status=status or "unvalidated")
                    if req:
                        E(req, aid, "RESTS_ON")
        except Exception:
            self.conn.rollback()

    # ── PERSIST per-workspace (multi-tenant named graph) ─────────────────────────────────────────
    def push_to_falkordb(self, wg: WorkspaceGraph, host: Optional[str] = None, port: int = 6379) -> str:
        """Write the workspace graph to its OWN FalkorDB named graph (hard tenant isolation).
        Graph key = the workspace namespace. Returns the graph name written."""
        from falkordb import FalkorDB  # optional dep; only when persisting
        db = FalkorDB(host=host or os.environ.get("FALKORDB_HOST", "localhost"),
                      port=int(os.environ.get("FALKORDB_PORT", port)))
        g = db.select_graph(wg.namespace)          # ← per-tenant graph, isolated at the store
        g.query("MATCH (n) DETACH DELETE n")        # idempotent refresh
        for n in wg.nodes:
            g.query("CREATE (:%s {id:$id, label:$label, ws:$ws})" % _safe_label(n["type"]),
                    {"id": n["id"], "label": n["label"], "ws": wg.workspace_id})
        for e in wg.edges:
            g.query("MATCH (a {id:$s}),(b {id:$d}) CREATE (a)-[:%s]->(b)" % _safe_label(e["type"]),
                    {"s": e["source"], "d": e["target"]})
        return wg.namespace

    def ingest(self, workspace_id: str, persist: bool = False) -> WorkspaceGraph:
        wg = self.extract(workspace_id)
        if persist:
            self.push_to_falkordb(wg)
        return wg


def _safe_label(s: str) -> str:
    return "".join(ch for ch in str(s) if ch.isalnum() or ch == "_") or "Node"


def _report(wg: WorkspaceGraph):
    print(f"\n== workspace {wg.workspace_id}  (namespace {wg.namespace}) ==")
    print(f"   {len(wg.nodes)} nodes, {len(wg.edges)} edges")
    gaps = wg.coverage_gaps()
    print("   coverage gaps:", {k: len(v) for k, v in gaps.items()})
    hot = wg.risk_hotspots(5)
    if hot:
        print("   risk hotspots:", [f"{l} ({s:.2f})" for l, s in hot])
    ua = wg.unvalidated_assumptions()
    if ua:
        print("   requirements on unvalidated assumptions:", ua)


if __name__ == "__main__":
    a = AtlasSemanticaAdapter()
    if "--all" in sys.argv:
        for wid, name, n in a.list_workspaces():
            if n == 0:
                continue
            _report(a.ingest(wid, persist="--persist" in sys.argv))
    elif "--workspace" in sys.argv:
        wid = sys.argv[sys.argv.index("--workspace") + 1]
        _report(a.ingest(wid, persist="--persist" in sys.argv))
    else:
        print("workspaces:")
        for wid, name, n in a.list_workspaces():
            print(f"  {wid}  {name}  ({n} issues)")
        print("\nrun with --workspace <id> [--persist]  or  --all [--persist]")
