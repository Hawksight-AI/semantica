/**
 * src/workspaces/ManageWorkspace/KGOverviewTab.tsx
 *
 * Quick-view dashboard for the Knowledge Graph: node/edge counts,
 * type distributions, and top connected nodes.
 */
import { useState, useEffect, useCallback } from "react";
import { Network, RefreshCw, Loader2 } from "lucide-react";
import { useI18n } from "../../i18n";
import { translateEdgeType } from "../GraphWorkspace/plugins/types";

interface KGStats {
  node_count: number;
  edge_count: number;
  node_types?: Record<string, number>;
  edge_types?: Record<string, number>;
  [key: string]: unknown;
}

interface NodeItem {
  id: string;
  type: string;
  content: string;
  properties?: Record<string, unknown>;
}

interface NodeListResponse {
  nodes: NodeItem[];
  total: number;
}

function TypeBar({ label, count, total, color }: { label: string; count: number; total: number; color: string }) {
  const pct = total > 0 ? Math.round((count / total) * 100) : 0;
  return (
    <div style={{ display: "flex", alignItems: "center", gap: 10, padding: "5px 0" }}>
      <div style={{ width: 120, flexShrink: 0, color: "#c6d4e3", fontSize: 12, overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }} title={label}>
        {label}
      </div>
      <div style={{ flex: 1, height: 6, borderRadius: 999, background: "rgba(255,255,255,0.06)", overflow: "hidden" }}>
        <div
          style={{
            width: `${pct}%`,
            height: "100%",
            borderRadius: 999,
            background: color,
            transition: "width 400ms ease",
          }}
        />
      </div>
      <div style={{ width: 52, textAlign: "right", flexShrink: 0, display: "flex", gap: 6, justifyContent: "flex-end" }}>
        <span style={{ color: "#8b949e", fontSize: 11 }}>{count.toLocaleString()}</span>
        <span style={{ color: "#6a7f97", fontSize: 11 }}>{pct}%</span>
      </div>
    </div>
  );
}

const NODE_COLORS = ["#3E79F2", "#149287", "#2F9F61", "#555FD6", "#8A56D8", "#B65473", "#C9922E", "#4aa3ff", "#f2b66d"];
const EDGE_COLORS = ["#4cc38a", "#79c0ff", "#d2a8ff", "#f2b66d", "#ff7b72", "#58a6ff", "#4aa3ff", "#8A56D8"];

function buildTypeMap(nodes: NodeItem[], key: keyof NodeItem): Record<string, number> {
  const map: Record<string, number> = {};
  for (const node of nodes) {
    const val = String(node[key] ?? "unknown");
    map[val] = (map[val] ?? 0) + 1;
  }
  return map;
}

export function KGOverviewTab() {
  const { t } = useI18n();
  const [stats, setStats] = useState<KGStats | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");
  const [topNodes, setTopNodes] = useState<{ node: NodeItem; neighborCount: number }[]>([]);
  const [nodeTypeMap, setNodeTypeMap] = useState<Record<string, number>>({});

  const fetchOverview = useCallback(async () => {
    setLoading(true);
    setError("");
    try {
      const [statsRes, nodesRes] = await Promise.all([
        fetch("/api/graph/stats"),
        fetch("/api/graph/nodes?limit=500"),
      ]);

      if (!statsRes.ok) throw new Error(t('manage.kg.statsFetchFailed', { status: statsRes.status }));
      if (!nodesRes.ok) throw new Error(t('manage.kg.nodesFetchFailed', { status: nodesRes.status }));

      const statsData: KGStats = await statsRes.json();
      setStats(statsData);
          if (statsRes.status === 207) {
            setError((statsData as any).message || t('manage.kg.partialStats'));
          }

      const nodesData: NodeListResponse = await nodesRes.json();
      const nodes = nodesData.nodes ?? [];
      setNodeTypeMap(buildTypeMap(nodes, "type"));
      if (nodesRes.status === 207) {
        const nodesMessage = (nodesData as any).message || "Warning: Partial success loading nodes.";
        setError((prev) => (prev ? `${prev} ${nodesMessage}` : nodesMessage));
      }

      // Simulate neighbor counts via edges fetch for top-N
      const edgesRes = await fetch("/api/graph/edges?limit=2000");
      if (edgesRes.ok) {
        const edgesData = await edgesRes.json();
        const edges: { source: string; target: string }[] = edgesData.edges ?? [];
        const degreeMap: Record<string, number> = {};
        for (const edge of edges) {
          degreeMap[edge.source] = (degreeMap[edge.source] ?? 0) + 1;
          degreeMap[edge.target] = (degreeMap[edge.target] ?? 0) + 1;
        }
        const sorted = nodes
          .map((n) => ({ node: n, neighborCount: degreeMap[n.id] ?? 0 }))
          .sort((a, b) => b.neighborCount - a.neighborCount)
          .slice(0, 10);
        setTopNodes(sorted);
      }
    } catch (err) {
      setError(err instanceof Error ? err.message : t('manage.kg.loadFailed'));
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    let ignore = false;
    async function fetchInitial() {
      if (!ignore) {
        setLoading(true);
        setError("");
      }
      try {
        const [statsRes, nodesRes] = await Promise.all([
          fetch("/api/graph/stats"),
          fetch("/api/graph/nodes?limit=500"),
        ]);

        if (!statsRes.ok) throw new Error(`Stats fetch failed (${statsRes.status})`);
        if (!nodesRes.ok) throw new Error(`Nodes fetch failed (${nodesRes.status})`);

        const statsData: KGStats = await statsRes.json();
        if (!ignore) {
          setStats(statsData);
          if (statsRes.status === 207) {
            setError((statsData as { message?: string }).message || t('manage.kg.partialStats'));
          }
        }

        const nodesData: NodeListResponse = await nodesRes.json();
        const nodes = nodesData.nodes ?? [];
        if (!ignore) {
          setNodeTypeMap(buildTypeMap(nodes, "type"));
          if (nodesRes.status === 207) {
            const nodesMessage = (nodesData as { message?: string }).message || t('manage.kg.partialNodes');
            setError((prev) => (prev ? `${prev} ${nodesMessage}` : nodesMessage));
          }
        }

        // Simulate neighbor counts via edges fetch for top-N
        const edgesRes = await fetch("/api/graph/edges?limit=2000");
        if (edgesRes.ok) {
          const edgesData = await edgesRes.json();
          const edges: { source: string; target: string }[] = edgesData.edges ?? [];
          const degreeMap: Record<string, number> = {};
          for (const edge of edges) {
            degreeMap[edge.source] = (degreeMap[edge.source] ?? 0) + 1;
            degreeMap[edge.target] = (degreeMap[edge.target] ?? 0) + 1;
          }
          const sorted = nodes
            .map((n) => ({ node: n, neighborCount: degreeMap[n.id] ?? 0 }))
            .sort((a, b) => b.neighborCount - a.neighborCount)
            .slice(0, 10);
          if (!ignore) setTopNodes(sorted);
        }
      } catch (err) {
        if (!ignore) setError(err instanceof Error ? err.message : t('manage.kg.loadFailed'));
      } finally {
        if (!ignore) setLoading(false);
      }
    }
    void fetchInitial();
    return () => { ignore = true; };
  }, []);

  const nodeTypeEntries = Object.entries(nodeTypeMap).sort((a, b) => b[1] - a[1]);
  const edgeTypeEntries = stats?.edge_types
    ? Object.entries(stats.edge_types).sort((a, b) => b[1] - a[1])
    : [];

  const totalNodes = stats?.node_count ?? 0;
  const totalEdges = stats?.edge_count ?? 0;

  const statCards = [
    { label: t('manage.kg.statNodes'),   value: totalNodes.toLocaleString(), color: "var(--ws-accent)",  sub: t('manage.kg.nodeTypes', { count: nodeTypeEntries.length }) },
    { label: t('manage.kg.statEdges'),   value: totalEdges.toLocaleString(), color: "var(--ws-green)",   sub: t('manage.kg.edgeTypes', { count: edgeTypeEntries.length }) },
    { label: t('manage.kg.statDensity'), value: totalNodes > 1 ? ((totalEdges / (totalNodes * (totalNodes - 1))) * 100).toFixed(3) + "%" : "—", color: "var(--ws-purple)", sub: t('manage.kg.graphDensity') },
  ];

  return (
    <div className="ws-page">
      {error ? (
        <div style={{ margin: "16px 22px 0 22px", padding: 12, borderRadius: 14, color: "#ffb4c2", background: "rgba(255,157,175,0.1)", border: "1px solid rgba(255,157,175,0.18)" }}>
          {error}
        </div>
      ) : null}

      {/* Header */}
      <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", padding: "16px 22px", borderBottom: "1px solid var(--ws-border)", flexShrink: 0 }}>
        <div style={{ display: "flex", alignItems: "center", gap: 10 }}>
          <div style={{ width: 32, height: 32, borderRadius: 9, background: "var(--ws-accent-soft)", border: "1px solid var(--ws-border-strong)", display: "grid", placeItems: "center", color: "var(--ws-accent)" }}>
            <Network size={16} />
          </div>
          <div>
            <div style={{ color: "var(--ws-text)", fontSize: 15, fontWeight: 700, lineHeight: 1 }}>{t('manage.kg.title')}</div>
            <div className="ws-body" style={{ fontSize: 11, marginTop: 2 }}>{t('manage.kg.subtitle')}</div>
          </div>
        </div>
        <button className="ws-btn ws-btn--ghost" onClick={() => void fetchOverview()} disabled={loading} style={{ padding: "6px 12px" }}>
          {loading ? <Loader2 size={13} className="ws-spin" /> : <RefreshCw size={13} />}
          {t('manage.kg.refresh')}
        </button>
      </div>



      <div className="ws-scroll" style={{ flex: 1, padding: "18px 22px", display: "flex", flexDirection: "column", gap: 16 }}>
        {/* Stat cards */}
        <div className="ws-stat-grid ws-stat-grid--3">
          {statCards.map(({ label, value, color, sub }) => (
            <div key={label} className="ws-stat-card">
              <div className="ws-eyebrow" style={{ marginBottom: 6 }}>{label}</div>
              <div className="ws-stat-value" style={{ color }}>{loading ? "—" : value}</div>
              <div className="ws-stat-label">{sub}</div>
            </div>
          ))}
        </div>

        {/* Type breakdowns */}
        <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 14 }}>
          <div className="ws-card" style={{ padding: "16px 18px", gap: 8, display: "flex", flexDirection: "column" }}>
            <div className="ws-eyebrow" style={{ marginBottom: 4 }}>{t('manage.kg.nodeBreakdown')}</div>
            {loading ? (
              <div style={{ display: "flex", flexDirection: "column", gap: 8 }}>
                {[80, 65, 45, 35, 25].map((w, i) => <div key={i} className="ws-skeleton" style={{ height: 10, width: `${w}%` }} />)}
              </div>
            ) : nodeTypeEntries.length === 0 ? (
              <div className="ws-body" style={{ fontSize: 12 }}>{t('manage.kg.noData')}</div>
            ) : (
              nodeTypeEntries.slice(0, 8).map(([type, count], i) => (
                <TypeBar key={type} label={type} count={count} total={totalNodes || 1} color={NODE_COLORS[i % NODE_COLORS.length]} />
              ))
            )}
          </div>

          <div className="ws-card" style={{ padding: "16px 18px", gap: 8, display: "flex", flexDirection: "column" }}>
            <div className="ws-eyebrow" style={{ marginBottom: 4 }}>{t('manage.kg.edgeBreakdown')}</div>
            {loading ? (
              <div style={{ display: "flex", flexDirection: "column", gap: 8 }}>
                {[70, 55, 48, 30, 20].map((w, i) => <div key={i} className="ws-skeleton" style={{ height: 10, width: `${w}%` }} />)}
              </div>
            ) : edgeTypeEntries.length === 0 ? (
              <div className="ws-body" style={{ fontSize: 12 }}>{t('manage.kg.edgeBreakdownHint')}</div>
            ) : (
              edgeTypeEntries.slice(0, 8).map(([type, count], i) => (
                <TypeBar key={type} label={translateEdgeType(t, type)} count={count} total={totalEdges || 1} color={EDGE_COLORS[i % EDGE_COLORS.length]} />
              ))
            )}
          </div>
        </div>

        {/* Top connected nodes */}
        {topNodes.length > 0 && (
          <div className="ws-card" style={{ padding: "16px 18px" }}>
            <div className="ws-eyebrow" style={{ marginBottom: 12 }}>{t('manage.kg.topConnected')}</div>
            <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fill, minmax(260px, 1fr))", gap: 8 }}>
              {topNodes.map(({ node, neighborCount }, rank) => (
                <div key={node.id} style={{ display: "flex", alignItems: "center", gap: 10, padding: "9px 12px", borderRadius: "var(--ws-radius-sm)", background: "rgba(0,0,0,0.18)", border: "1px solid var(--ws-border)" }}>
                  <div style={{ color: "var(--ws-text-dim)", fontSize: 11, fontWeight: 700, minWidth: 22 }}>#{rank + 1}</div>
                  <div style={{ flex: 1, minWidth: 0 }}>
                    <div style={{ color: "var(--ws-text)", fontSize: 12, fontWeight: 600, overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>{node.content || node.id}</div>
                    <div className="ws-eyebrow" style={{ marginTop: 2, fontSize: 9 }}>{node.type}</div>
                  </div>
                  <span className="ws-pill ws-pill--accent" style={{ fontSize: 10 }}>{neighborCount}</span>
                </div>
              ))}
            </div>
          </div>
        )}
      </div>
    </div>
  );
}
