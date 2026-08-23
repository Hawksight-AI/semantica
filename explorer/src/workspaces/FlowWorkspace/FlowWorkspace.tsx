/**
 * FlowWorkspace — n8n-style visual flow canvas for bug bounty graph engineering.
 */
import { useCallback, useEffect, useMemo, useState } from "react";
import {
  Background,
  Controls,
  Handle,
  MiniMap,
  Position,
  ReactFlow,
  type Edge,
  type Node,
  type NodeProps,
  MarkerType,
} from "@xyflow/react";
import "@xyflow/react/dist/style.css";
import { Play, RefreshCw, Shield, Workflow } from "lucide-react";

type CatalogNode = {
  type: string;
  label: string;
  category: string;
  description: string;
  color: string;
  default_config?: Record<string, unknown>;
};

type FlowNodeData = {
  label: string;
  type: string;
  category: string;
  status?: string;
  description?: string;
  config?: Record<string, unknown>;
  color?: string;
  messages?: string[];
};

type FlowPayload = {
  id: string;
  name: string;
  description?: string;
  nodes: Array<{
    id: string;
    type: string;
    label: string;
    category?: string;
    description?: string;
    status?: string;
    config?: Record<string, unknown>;
    position?: { x: number; y: number };
    result?: { messages?: string[] };
    error?: string;
  }>;
  edges: Array<{
    id: string;
    source: string;
    target: string;
    label?: string;
  }>;
  metadata?: Record<string, unknown>;
};

type RunPayload = {
  id: string;
  status: string;
  error?: string;
  node_status?: Record<string, string>;
  node_results?: Record<string, { messages?: string[]; output?: Record<string, unknown>; error?: string }>;
  context?: {
    report?: { markdown?: string; findings?: unknown[] };
    exported_graph?: { nodes?: unknown[]; edges?: unknown[] };
    submission_gate?: { ready?: boolean; failed_checks?: string[] };
  };
};

const STATUS_COLOR: Record<string, string> = {
  idle: "rgba(143,168,198,0.55)",
  pending: "rgba(143,168,198,0.55)",
  running: "#f2b66d",
  success: "#4cc38a",
  failed: "#ff7b72",
  skipped: "rgba(143,168,198,0.35)",
};

const FLOW_CSS = `
  .flow-workspace {
    display: flex;
    width: 100%;
    height: 100%;
    min-height: 0;
    background: var(--ws-bg, #060d1a);
    color: var(--ws-text, #ddeeff);
  }
  .flow-sidebar {
    width: 280px;
    flex-shrink: 0;
    border-right: 1px solid var(--ws-border, rgba(74,163,255,0.13));
    display: flex;
    flex-direction: column;
    background: rgba(7, 17, 31, 0.92);
  }
  .flow-sidebar-header {
    padding: 16px 16px 10px;
    border-bottom: 1px solid var(--ws-border, rgba(74,163,255,0.13));
  }
  .flow-sidebar-kicker {
    font-size: 11px;
    letter-spacing: 0.08em;
    text-transform: uppercase;
    color: var(--ws-text-muted, #5a7a9a);
    margin-bottom: 4px;
  }
  .flow-sidebar-title {
    font-size: 15px;
    font-weight: 600;
  }
  .flow-sidebar-body {
    flex: 1;
    overflow-y: auto;
    padding: 12px;
    display: flex;
    flex-direction: column;
    gap: 8px;
  }
  .flow-catalog-item {
    text-align: left;
    border: 1px solid var(--ws-border, rgba(74,163,255,0.13));
    background: rgba(255,255,255,0.02);
    border-radius: 10px;
    padding: 10px 12px;
    color: inherit;
    cursor: grab;
  }
  .flow-catalog-item:hover {
    background: var(--ws-surface-hover, rgba(74,163,255,0.07));
    border-color: var(--ws-border-strong, rgba(74,163,255,0.26));
  }
  .flow-catalog-label {
    font-size: 13px;
    font-weight: 600;
    display: flex;
    align-items: center;
    gap: 8px;
  }
  .flow-catalog-dot {
    width: 8px;
    height: 8px;
    border-radius: 50%;
    flex-shrink: 0;
  }
  .flow-catalog-desc {
    margin-top: 4px;
    font-size: 11px;
    color: var(--ws-text-muted, #5a7a9a);
    line-height: 1.35;
  }
  .flow-main {
    flex: 1;
    min-width: 0;
    display: flex;
    flex-direction: column;
  }
  .flow-toolbar {
    display: flex;
    align-items: center;
    gap: 10px;
    padding: 10px 14px;
    border-bottom: 1px solid var(--ws-border, rgba(74,163,255,0.13));
    background: rgba(7, 17, 31, 0.88);
  }
  .flow-toolbar-title {
    font-size: 14px;
    font-weight: 600;
    margin-right: auto;
  }
  .flow-toolbar button {
    display: inline-flex;
    align-items: center;
    gap: 6px;
    border-radius: 8px;
    border: 1px solid var(--ws-border, rgba(74,163,255,0.13));
    background: rgba(255,255,255,0.03);
    color: var(--ws-text, #ddeeff);
    padding: 7px 12px;
    font-size: 12px;
    cursor: pointer;
  }
  .flow-toolbar button.primary {
    background: rgba(76,195,138,0.16);
    border-color: rgba(76,195,138,0.35);
    color: #9aebc4;
  }
  .flow-toolbar button:disabled {
    opacity: 0.5;
    cursor: not-allowed;
  }
  .flow-canvas {
    flex: 1;
    min-height: 0;
  }
  .flow-inspector {
    width: 320px;
    flex-shrink: 0;
    border-left: 1px solid var(--ws-border, rgba(74,163,255,0.13));
    background: rgba(7, 17, 31, 0.92);
    display: flex;
    flex-direction: column;
    min-height: 0;
  }
  .flow-inspector-header {
    padding: 14px 16px;
    border-bottom: 1px solid var(--ws-border, rgba(74,163,255,0.13));
    font-size: 13px;
    font-weight: 600;
  }
  .flow-inspector-body {
    flex: 1;
    overflow: auto;
    padding: 14px 16px;
    font-size: 12px;
    color: var(--ws-text-muted, #5a7a9a);
    white-space: pre-wrap;
    line-height: 1.45;
  }
  .flow-banner {
    padding: 8px 14px;
    font-size: 12px;
    border-bottom: 1px solid var(--ws-border, rgba(74,163,255,0.13));
    display: flex;
    align-items: center;
    gap: 8px;
    color: var(--ws-text-muted, #5a7a9a);
  }
  .flow-banner strong {
    color: var(--ws-text, #ddeeff);
    font-weight: 600;
  }
  .react-flow { background: transparent; }
  .react-flow__controls {
    background: rgba(6,13,26,0.9);
    border: 1px solid rgba(74,163,255,0.18);
    border-radius: 10px;
  }
  .react-flow__controls-button {
    background: transparent;
    border-color: rgba(74,163,255,0.15);
    color: var(--ws-text-muted, #5a7a9a);
  }
  .react-flow__minimap {
    background: rgba(6,13,26,0.92) !important;
    border: 1px solid rgba(74,163,255,0.18) !important;
    border-radius: 10px;
  }
  .bb-flow-node {
    min-width: 180px;
    max-width: 220px;
    border-radius: 12px;
    border: 1px solid rgba(74,163,255,0.28);
    background: rgba(6,13,26,0.94);
    box-shadow: 0 8px 24px rgba(0,0,0,0.35);
    padding: 10px 12px 12px;
  }
  .bb-flow-node__stripe {
    height: 3px;
    border-radius: 999px;
    margin-bottom: 8px;
  }
  .bb-flow-node__type {
    font-size: 10px;
    letter-spacing: 0.06em;
    text-transform: uppercase;
    color: var(--ws-text-muted, #5a7a9a);
    margin-bottom: 2px;
  }
  .bb-flow-node__label {
    font-size: 13px;
    font-weight: 600;
    color: var(--ws-text, #ddeeff);
  }
  .bb-flow-node__status {
    margin-top: 8px;
    font-size: 11px;
    display: inline-flex;
    align-items: center;
    gap: 6px;
  }
  .bb-flow-node__status-dot {
    width: 7px;
    height: 7px;
    border-radius: 50%;
  }
`;

function FlowNodeCard({ data }: NodeProps) {
  const nodeData = data as FlowNodeData;
  const status = nodeData.status || "idle";
  return (
    <div className="bb-flow-node">
      <Handle type="target" position={Position.Left} style={{ background: "#4aa3ff" }} />
      <div className="bb-flow-node__stripe" style={{ background: nodeData.color || "#4aa3ff" }} />
      <div className="bb-flow-node__type">{nodeData.type}</div>
      <div className="bb-flow-node__label">{nodeData.label}</div>
      <div className="bb-flow-node__status">
        <span className="bb-flow-node__status-dot" style={{ background: STATUS_COLOR[status] || STATUS_COLOR.idle }} />
        {status}
      </div>
      <Handle type="source" position={Position.Right} style={{ background: "#4aa3ff" }} />
    </div>
  );
}

const nodeTypes = { flowNode: FlowNodeCard };

function toReactFlow(flow: FlowPayload, catalog: CatalogNode[]): { nodes: Node[]; edges: Edge[] } {
  const colorByType = Object.fromEntries(catalog.map((c) => [c.type, c.color]));
  const nodes: Node[] = flow.nodes.map((n) => ({
    id: n.id,
    type: "flowNode",
    position: n.position || { x: 0, y: 0 },
    data: {
      label: n.label,
      type: n.type,
      category: n.category || "general",
      status: n.status || "idle",
      description: n.description,
      config: n.config,
      color: colorByType[n.type] || "#4aa3ff",
      messages: n.result?.messages,
    } satisfies FlowNodeData,
  }));
  const edges: Edge[] = flow.edges.map((e) => ({
    id: e.id,
    source: e.source,
    target: e.target,
    label: e.label,
    animated: true,
    style: { stroke: "rgba(74,163,255,0.55)" },
    markerEnd: { type: MarkerType.ArrowClosed, color: "rgba(74,163,255,0.8)" },
  }));
  return { nodes, edges };
}

function fromReactFlow(flow: FlowPayload, nodes: Node[], edges: Edge[]): FlowPayload {
  const byId = Object.fromEntries(flow.nodes.map((n) => [n.id, n]));
  return {
    ...flow,
    nodes: nodes.map((n) => {
      const prev = byId[n.id];
      const data = n.data as FlowNodeData;
      return {
        id: n.id,
        type: data.type || prev?.type || "trigger",
        label: data.label || prev?.label || n.id,
        category: data.category || prev?.category || "general",
        description: data.description || prev?.description || "",
        status: data.status || prev?.status || "idle",
        config: data.config || prev?.config || {},
        position: { x: n.position.x, y: n.position.y },
      };
    }),
    edges: edges.map((e) => ({
      id: e.id,
      source: e.source,
      target: e.target,
      label: typeof e.label === "string" ? e.label : "",
    })),
  };
}

export function FlowWorkspace() {
  const [catalog, setCatalog] = useState<CatalogNode[]>([]);
  const [flow, setFlow] = useState<FlowPayload | null>(null);
  const [nodes, setNodes] = useState<Node[]>([]);
  const [edges, setEdges] = useState<Edge[]>([]);
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const [run, setRun] = useState<RunPayload | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");

  const selected = useMemo(
    () => nodes.find((n) => n.id === selectedId) || null,
    [nodes, selectedId],
  );

  const load = useCallback(async () => {
    setError("");
    try {
      const [catalogRes, flowsRes] = await Promise.all([
        fetch("/api/flows/catalog"),
        fetch("/api/flows"),
      ]);
      if (!catalogRes.ok) throw new Error(`Catalog failed (${catalogRes.status})`);
      if (!flowsRes.ok) throw new Error(`Flows failed (${flowsRes.status})`);
      const catalogData = await catalogRes.json();
      const flowsData = await flowsRes.json();
      const nextCatalog: CatalogNode[] = catalogData.nodes || [];
      setCatalog(nextCatalog);
      const first: FlowPayload | undefined = (flowsData.flows || [])[0];
      if (!first) {
        const seeded = await fetch("/api/flows/templates/bug_bounty_hunting", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({}),
        });
        if (!seeded.ok) throw new Error(`Seed template failed (${seeded.status})`);
        const seededFlow: FlowPayload = await seeded.json();
        setFlow(seededFlow);
        const mapped = toReactFlow(seededFlow, nextCatalog);
        setNodes(mapped.nodes);
        setEdges(mapped.edges);
        return;
      }
      setFlow(first);
      const mapped = toReactFlow(first, nextCatalog);
      setNodes(mapped.nodes);
      setEdges(mapped.edges);
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
    }
  }, []);

  useEffect(() => {
    void load();
  }, [load]);

  const onNodesChange = useCallback((changes: any) => {
    setNodes((prev) => {
      // Minimal position/selection handling without importing applyNodeChanges dependency surface issues
      let next = [...prev];
      for (const change of changes) {
        if (change.type === "position" && change.position) {
          next = next.map((n) => (n.id === change.id ? { ...n, position: change.position } : n));
        } else if (change.type === "select") {
          next = next.map((n) => (n.id === change.id ? { ...n, selected: change.selected } : n));
        } else if (change.type === "remove") {
          next = next.filter((n) => n.id !== change.id);
        }
      }
      return next;
    });
  }, []);

  const onEdgesChange = useCallback((changes: any) => {
    setEdges((prev) => {
      let next = [...prev];
      for (const change of changes) {
        if (change.type === "remove") {
          next = next.filter((e) => e.id !== change.id);
        } else if (change.type === "select") {
          next = next.map((e) => (e.id === change.id ? { ...e, selected: change.selected } : e));
        }
      }
      return next;
    });
  }, []);

  const onConnect = useCallback((connection: any) => {
    if (!connection.source || !connection.target) return;
    setEdges((prev) => [
      ...prev,
      {
        id: `e_${connection.source}_${connection.target}_${prev.length}`,
        source: connection.source,
        target: connection.target,
        animated: true,
        style: { stroke: "rgba(74,163,255,0.55)" },
        markerEnd: { type: MarkerType.ArrowClosed, color: "rgba(74,163,255,0.8)" },
      },
    ]);
  }, []);

  const addCatalogNode = (item: CatalogNode) => {
    const id = `n_${item.type}_${Math.random().toString(36).slice(2, 8)}`;
    setNodes((prev) => [
      ...prev,
      {
        id,
        type: "flowNode",
        position: { x: 120 + (prev.length % 5) * 40, y: 120 + prev.length * 24 },
        data: {
          label: item.label,
          type: item.type,
          category: item.category,
          status: "idle",
          description: item.description,
          config: item.default_config || {},
          color: item.color,
        } satisfies FlowNodeData,
      },
    ]);
  };

  const saveFlow = async () => {
    if (!flow) return;
    setBusy(true);
    setError("");
    try {
      const payload = fromReactFlow(flow, nodes, edges);
      const res = await fetch("/api/flows", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ flow: payload }),
      });
      if (!res.ok) throw new Error(`Save failed (${res.status})`);
      const saved: FlowPayload = await res.json();
      setFlow(saved);
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
    } finally {
      setBusy(false);
    }
  };

  const runFlow = async () => {
    if (!flow) return;
    setBusy(true);
    setError("");
    try {
      await saveFlow();
      const res = await fetch(`/api/flows/${encodeURIComponent(flow.id)}/execute`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ context: {}, dry_run: false }),
      });
      if (!res.ok) {
        const text = await res.text();
        throw new Error(`Execute failed (${res.status}): ${text.slice(0, 180)}`);
      }
      const result: RunPayload = await res.json();
      setRun(result);
      setNodes((prev) =>
        prev.map((n) => {
          const status = result.node_status?.[n.id] || (n.data as FlowNodeData).status;
          const messages = result.node_results?.[n.id]?.messages;
          return {
            ...n,
            data: {
              ...(n.data as FlowNodeData),
              status,
              messages,
            },
          };
        }),
      );
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
    } finally {
      setBusy(false);
    }
  };

  const resetTemplate = async () => {
    setBusy(true);
    setError("");
    try {
      const res = await fetch("/api/flows/templates/bug_bounty_hunting", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({}),
      });
      if (!res.ok) throw new Error(`Template reset failed (${res.status})`);
      const next: FlowPayload = await res.json();
      setFlow(next);
      setRun(null);
      const mapped = toReactFlow(next, catalog);
      setNodes(mapped.nodes);
      setEdges(mapped.edges);
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
    } finally {
      setBusy(false);
    }
  };

  const inspectorText = (() => {
    if (run?.context?.report?.markdown) {
      return run.context.report.markdown;
    }
    if (selected) {
      const data = selected.data as FlowNodeData;
      return JSON.stringify(
        {
          id: selected.id,
          type: data.type,
          label: data.label,
          status: data.status,
          config: data.config,
          messages: data.messages,
        },
        null,
        2,
      );
    }
    if (run) {
      return JSON.stringify(
        {
          run_id: run.id,
          status: run.status,
          error: run.error,
          submission_gate: run.context?.submission_gate,
          graph: {
            nodes: run.context?.exported_graph?.nodes?.length ?? 0,
            edges: run.context?.exported_graph?.edges?.length ?? 0,
          },
        },
        null,
        2,
      );
    }
    return "Select a node or run the flow to inspect outputs.";
  })();

  return (
    <div className="flow-workspace">
      <style>{FLOW_CSS}</style>
      <aside className="flow-sidebar">
        <div className="flow-sidebar-header">
          <div className="flow-sidebar-kicker">Logic blocks</div>
          <div className="flow-sidebar-title">AIP Logic</div>
        </div>
        <div className="flow-sidebar-body">
          {catalog.map((item) => (
            <button key={item.type} type="button" className="flow-catalog-item" onClick={() => addCatalogNode(item)}>
              <div className="flow-catalog-label">
                <span className="flow-catalog-dot" style={{ background: item.color }} />
                {item.label}
              </div>
              <div className="flow-catalog-desc">{item.description}</div>
            </button>
          ))}
        </div>
      </aside>

      <section className="flow-main">
        <div className="flow-banner">
          <Shield size={14} />
          <span>
            Authorized AIP Logic function — Ontology scope gates, evidence provenance, triage actions, report compose.
            <strong> No exploit execution.</strong>
          </span>
        </div>
        <div className="flow-toolbar">
          <Workflow size={16} />
          <div className="flow-toolbar-title">{flow?.name || "Bug Bounty Hunting Logic"}</div>
          <button type="button" onClick={() => void load()} disabled={busy}>
            <RefreshCw size={14} /> Reload
          </button>
          <button type="button" onClick={() => void resetTemplate()} disabled={busy}>
            Reset template
          </button>
          <button type="button" onClick={() => void saveFlow()} disabled={busy || !flow}>
            Save
          </button>
          <button type="button" className="primary" onClick={() => void runFlow()} disabled={busy || !flow}>
            <Play size={14} /> Run flow
          </button>
        </div>
        {error ? (
          <div className="flow-banner" style={{ color: "#ff9daf" }}>
            {error}
          </div>
        ) : null}
        {run ? (
          <div className="flow-banner">
            Last run <strong>{run.status}</strong>
            {run.id ? <> · {run.id.slice(0, 8)}</> : null}
            {run.error ? <> · {run.error}</> : null}
          </div>
        ) : null}
        <div className="flow-canvas">
          <ReactFlow
            nodes={nodes}
            edges={edges}
            nodeTypes={nodeTypes}
            onNodesChange={onNodesChange}
            onEdgesChange={onEdgesChange}
            onConnect={onConnect}
            onNodeClick={(_, node) => setSelectedId(node.id)}
            fitView
            minZoom={0.2}
            maxZoom={1.6}
          >
            <Background gap={22} size={1} color="rgba(74,163,255,0.08)" />
            <Controls />
            <MiniMap
              nodeColor={(n) => ((n.data as FlowNodeData)?.color as string) || "#4aa3ff"}
              maskColor="rgba(6,13,26,0.7)"
            />
          </ReactFlow>
        </div>
      </section>

      <aside className="flow-inspector">
        <div className="flow-inspector-header">
          {run?.context?.report ? "Report draft" : selected ? "Node inspector" : "Run inspector"}
        </div>
        <div className="flow-inspector-body">{inspectorText}</div>
      </aside>
    </div>
  );
}

export default FlowWorkspace;
