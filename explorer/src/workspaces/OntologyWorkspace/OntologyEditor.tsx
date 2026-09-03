import { useCallback, useEffect, useState } from "react";
import {
  ReactFlow,
  Background,
  Controls,
  MiniMap,
  addEdge,
  useNodesState,
  useEdgesState,
  MarkerType,
  Handle,
  Position,
} from "@xyflow/react";
import type { Connection, Edge, Node, ReactFlowInstance } from "@xyflow/react";
import "@xyflow/react/dist/style.css";
import {
  Plus,
  GitBranch,
  User,
  Shield,
  FileText,
  Layout,
  Send,
  Pencil,
  Trash2,
} from "lucide-react";
import { loadOntologyEntityOwner, loadOntologyGraph } from "./api";
import type { OntologyGraphEdge, OntologyGraphNode } from "./api";
import {
  classifyNodeType,
  isEditableEntityType,
  ONTOLOGY_MINIMAP_THEME,
  resolveEditorOntology,
} from "./ontologyEditorModel";
import type { EditorEntityType, RegistryEntry } from "./ontologyEditorModel";

type OntologyNodeData = {
  label?: string;
  type?: string;
  entityType?: EditorEntityType;
};

type OntologyNode = Node<OntologyNodeData>;
type OntologyEdge = Edge<Record<string, unknown>>;

const nodeTypes = {
  classNode: ({ data }: { data: OntologyNodeData }) => (
    <div style={classNodeStyle}>
      <Handle type="target" position={Position.Left} style={handleStyle} />
      <div style={classNodeHeader}>{data.label}</div>
      <div style={classNodeSub}>{data.type}</div>
      <Handle type="source" position={Position.Right} style={handleStyle} />
    </div>
  ),
};

const handleStyle: React.CSSProperties = {
  width: 8,
  height: 8,
  border: "1px solid rgba(235, 243, 255, 0.8)",
  background: "#4aa3ff",
};

const ontologyFlowThemeCss = `
  .ontology-editor-flow .react-flow__controls {
    overflow: hidden;
    border: 1px solid rgba(127, 208, 255, 0.2);
    border-radius: 9px;
    background: rgba(6, 13, 26, 0.96);
    box-shadow: 0 8px 24px rgba(0, 0, 0, 0.38);
  }

  .ontology-editor-flow .react-flow__controls-button {
    width: 30px;
    height: 30px;
    background: transparent;
    border-bottom-color: rgba(127, 208, 255, 0.14);
    color: #8fa8c6;
    transition: color 140ms ease, background 140ms ease;
  }

  .ontology-editor-flow .react-flow__controls-button:hover {
    background: rgba(74, 163, 255, 0.14);
    color: #ebf3ff;
  }

  .ontology-editor-flow .react-flow__controls-button:focus-visible {
    position: relative;
    z-index: 1;
    outline: 2px solid #7fd0ff;
    outline-offset: -2px;
  }

  .ontology-editor-flow .react-flow__controls-button:disabled {
    background: rgba(3, 9, 18, 0.32);
    color: #40566f;
  }
`;

const classNodeStyle: React.CSSProperties = {
  padding: "12px 16px",
  borderRadius: "8px",
  background: "linear-gradient(135deg, rgba(74, 163, 255, 0.15), rgba(74, 163, 255, 0.05))",
  border: "1px solid rgba(127, 208, 255, 0.3)",
  color: "#ebf3ff",
  fontSize: "13px",
  fontWeight: "600",
  minWidth: "140px",
  textAlign: "center",
  boxShadow: "0 4px 12px rgba(0, 0, 0, 0.2)",
};

const classNodeHeader: React.CSSProperties = {
  fontSize: "14px",
  fontWeight: "700",
  marginBottom: "4px",
};

const classNodeSub: React.CSSProperties = {
  fontSize: "11px",
  color: "#8fa8c6",
  fontWeight: "500",
};

interface DraftDiff {
  added_classes: string[];
  removed_classes: string[];
  modified_classes: Record<string, Record<string, any>>;
  added_properties: string[];
  removed_properties: string[];
  modified_properties: Record<string, Record<string, any>>;
  added_restrictions: Record<string, any>[];
  removed_restrictions: Record<string, any>[];
  added_axioms: Record<string, any>[];
  removed_axioms: Record<string, any>[];
  annotation_changes: Record<string, Record<string, any>>;
}

function requestedEntityUri(): string {
  try {
    return new URLSearchParams(window.location.search).get("ontologyEntity") || "";
  } catch {
    return "";
  }
}

function nodeLabel(node: OntologyGraphNode): string {
  const explicit = String(node.content || node.properties?.["rdfs:label"] || "").trim();
  if (explicit && explicit !== node.id) {
    return explicit;
  }
  const trimmed = node.id.replace(/[/#]+$/, "");
  return trimmed.split("#").pop() || trimmed.split("/").pop() || node.id;
}

function classifyEditorNode(node: OntologyGraphNode): OntologyNodeData["entityType"] {
  return classifyNodeType(node.type);
}

function layoutEditorNodes(inputNodes: OntologyNode[]): OntologyNode[] {
  const properties = inputNodes.filter((node) => node.data.entityType === "property");
  const targets = inputNodes.filter((node) => (
    node.data.entityType === "class" || node.data.entityType === "external"
  ));
  const context = inputNodes.filter((node) => (
    node.data.entityType !== "property"
    && node.data.entityType !== "class"
    && node.data.entityType !== "external"
  ));
  const height = Math.max(360, Math.max(properties.length, targets.length) * 180);
  const positions = new Map<string, { x: number; y: number }>();

  properties.forEach((node, index) => {
    positions.set(node.id, { x: 0, y: ((index + 1) * height) / (properties.length + 1) });
  });
  targets.forEach((node, index) => {
    positions.set(node.id, { x: 600, y: ((index + 1) * height) / (targets.length + 1) });
  });
  context.forEach((node, index) => {
    positions.set(node.id, { x: 300 + index * 220, y: height + 120 });
  });

  return inputNodes.map((node) => ({
    ...node,
    position: positions.get(node.id) || node.position,
  }));
}

function buildEditorElements(apiNodes: OntologyGraphNode[], apiEdges: OntologyGraphEdge[]) {
  const sortedNodes = [...apiNodes].sort((left, right) => {
    const typeDelta = left.type.localeCompare(right.type);
    return typeDelta || left.id.localeCompare(right.id);
  });
  const nodes = layoutEditorNodes(sortedNodes.map((node) => ({
    id: node.id,
    type: "classNode",
    position: { x: 0, y: 0 },
    data: {
      label: nodeLabel(node),
      type: node.type,
      entityType: classifyEditorNode(node),
    },
  })));
  const edges: OntologyEdge[] = apiEdges.map((edge, index) => ({
    id: edge.id || `${edge.source}:${edge.type}:${edge.target}:${index}`,
    source: edge.source,
    target: edge.target,
    label: edge.type,
    type: "default",
    markerEnd: { type: MarkerType.ArrowClosed },
    style: { stroke: "rgba(127, 208, 255, 0.72)", strokeWidth: 1.5 },
    labelStyle: { fill: "#c8dcf5", fontSize: 11, fontWeight: 600 },
    labelBgStyle: { fill: "#07111f", fillOpacity: 0.9 },
  }));
  return { nodes, edges };
}

export function OntologyEditor() {
  const [nodes, setNodes, onNodesChange] = useNodesState<OntologyNode>([]);
  const [edges, setEdges, onEdgesChange] = useEdgesState<OntologyEdge>([]);
  const [selectedElement, setSelectedElement] = useState<OntologyNode | OntologyEdge | null>(null);
  const hasDetailPanel = selectedElement !== null;
  const [registry, setRegistry] = useState<RegistryEntry[]>([]);
  const [ontologyUri, setOntologyUri] = useState<string>("");
  const [flowInstance, setFlowInstance] = useState<ReactFlowInstance<OntologyNode, OntologyEdge> | null>(null);
  const [isLoadingGraph, setIsLoadingGraph] = useState(false);
  const [graphError, setGraphError] = useState("");
  const [draftDiff, setDraftDiff] = useState<DraftDiff>({
    added_classes: [],
    removed_classes: [],
    modified_classes: {},
    added_properties: [],
    removed_properties: [],
    modified_properties: {},
    added_restrictions: [],
    removed_restrictions: [],
    added_axioms: [],
    removed_axioms: [],
    annotation_changes: {},
  });
  const [isSaving, setIsSaving] = useState(false);
  const [showContext, setShowContext] = useState<{ x: number; y: number; type: string; element: OntologyNode | OntologyEdge } | null>(null);

  useEffect(() => {
    let cancelled = false;
    const requested = requestedEntityUri();
    Promise.all([
      fetch("/api/ontology/registry").then((response) => (response.ok ? response.json() : [])),
      requested
        ? loadOntologyEntityOwner(requested).catch(() => undefined)
        : Promise.resolve(undefined),
    ])
      .then(([entries, ownerVerdict]: [RegistryEntry[], string | null | undefined]) => {
        if (cancelled) return;
        setRegistry(entries);
        const resolvedOntology = resolveEditorOntology(entries, requested, ownerVerdict);
        setOntologyUri((current) => current || resolvedOntology || entries[0]?.uri || "");
      })
      .catch((error) => {
        console.error("Failed to load ontology registry:", error);
      });
    return () => {
      cancelled = true;
    };
  }, []);

  useEffect(() => {
    if (!ontologyUri) {
      setNodes([]);
      setEdges([]);
      setSelectedElement(null);
      return;
    }

    const controller = new AbortController();
    setIsLoadingGraph(true);
    setGraphError("");
    loadOntologyGraph(ontologyUri, controller.signal)
      .then((payload) => {
        const elements = buildEditorElements(payload.nodes, payload.edges);
        setNodes(elements.nodes);
        setEdges(elements.edges);
        const requested = requestedEntityUri();
        setSelectedElement(elements.nodes.find((node) => node.id === requested) || null);
      })
      .catch((error) => {
        if (controller.signal.aborted) return;
        setNodes([]);
        setEdges([]);
        setSelectedElement(null);
        setGraphError(error instanceof Error ? error.message : "Failed to load ontology graph");
      })
      .finally(() => {
        if (!controller.signal.aborted) setIsLoadingGraph(false);
      });

    return () => controller.abort();
  }, [ontologyUri, setEdges, setNodes]);

  useEffect(() => {
    if (!flowInstance || nodes.length === 0) return;
    const frame = window.requestAnimationFrame(() => {
      void flowInstance.fitView({ padding: 0.22, duration: 320, maxZoom: 1.25 });
    });
    return () => window.cancelAnimationFrame(frame);
  }, [flowInstance, hasDetailPanel, nodes.length, ontologyUri]);

  const onConnect = useCallback(
    (params: Connection) => setEdges((eds) => addEdge({ ...params, markerEnd: { type: MarkerType.ArrowClosed } }, eds)),
    [setEdges]
  );

  const addClass = useCallback(() => {
    const newId = `class_${Date.now()}`;
    const newNode: OntologyNode = {
      id: newId,
      type: "classNode",
      position: { x: Math.random() * 400, y: Math.random() * 300 },
      data: { label: "NewClass", type: "owl:Class", entityType: "class" },
    };
    setNodes((nds) => [...nds, newNode]);
    setDraftDiff((prev) => ({
      ...prev,
      added_classes: [...prev.added_classes, newId],
    }));
  }, [setNodes]);

  const addProperty = useCallback(() => {
    if (nodes.length < 2) {
      alert("Add at least two classes before creating a property edge.");
      return;
    }
    const newId = `prop_${Date.now()}`;
    const newEdge: OntologyEdge = {
      id: newId,
      source: nodes[0].id,
      target: nodes[1].id,
      label: "hasProperty",
      type: "smoothstep",
      animated: true,
    };
    setEdges((eds) => [...eds, newEdge]);
    setDraftDiff((prev) => ({
      ...prev,
      added_properties: [...prev.added_properties, newId],
    }));
  }, [nodes, setEdges]);

  const addIndividual = useCallback(() => {
    const newId = `ind_${Date.now()}`;
    const newNode: OntologyNode = {
      id: newId,
      type: "classNode",
      position: { x: Math.random() * 400, y: Math.random() * 300 },
      data: { label: "NewIndividual", type: "owl:NamedIndividual", entityType: "external" },
    };
    setNodes((nds) => [...nds, newNode]);
  }, [setNodes]);

  const addRestriction = useCallback(() => {
    setDraftDiff((prev) => ({
      ...prev,
      added_restrictions: [...prev.added_restrictions, { type: "someValuesFrom", value: "" }],
    }));
  }, []);

  const addAxiom = useCallback(() => {
    setDraftDiff((prev) => ({
      ...prev,
      added_axioms: [...prev.added_axioms, { type: "subClassOf", value: "" }],
    }));
  }, []);

  const autoLayout = useCallback(() => {
    setNodes(layoutEditorNodes(nodes));
  }, [nodes, setNodes]);

  const selectNode = useCallback((node: OntologyNode) => {
    setSelectedElement(node);
    try {
      const params = new URLSearchParams(window.location.search);
      params.set("ontologyTab", "editor");
      params.set("ontologyEntity", node.id);
      window.history.replaceState(null, "", `?${params.toString()}`);
    } catch {
      // URL state is optional; the editor selection still works without it.
    }
  }, []);

  const saveDraft = useCallback(async () => {
    if (!ontologyUri) {
      alert("Please select an ontology first");
      return;
    }
    setIsSaving(true);
    try {
      const response = await fetch("/api/ontology/draft", {
        method: "PATCH",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          ontology_uri: ontologyUri,
          diff: draftDiff,
          author: "user",
          summary: "Visual editor changes",
        }),
      });
      if (response.ok) {
        const data = await response.json();
        alert(`Draft saved: ${data.draft_id}`);
      }
    } catch (error) {
      console.error("Failed to save draft:", error);
      alert("Failed to save draft");
    } finally {
      setIsSaving(false);
    }
  }, [ontologyUri, draftDiff]);

  const handleNodeContextMenu = useCallback((event: React.MouseEvent, node: OntologyNode) => {
    event.preventDefault();
    setSelectedElement(node);
    setShowContext({ x: event.clientX, y: event.clientY, type: "node", element: node });
  }, []);

  const handleEdgeContextMenu = useCallback((event: React.MouseEvent, edge: OntologyEdge) => {
    event.preventDefault();
    setSelectedElement(edge);
    setShowContext({ x: event.clientX, y: event.clientY, type: "edge", element: edge });
  }, []);

  const deleteSelected = useCallback(() => {
    const target = showContext?.element ?? selectedElement;
    if (target) {
      if ("source" in target) {
        setEdges((eds) => eds.filter((e) => e.id !== target.id));
        setDraftDiff((prev) => ({
          ...prev,
          removed_properties: [...prev.removed_properties, target.id],
        }));
      } else if (isEditableEntityType(target.data.entityType)) {
        setNodes((nds) => nds.filter((n) => n.id !== target.id));
        setDraftDiff((prev) => target.data.entityType === "property"
          ? { ...prev, removed_properties: [...prev.removed_properties, target.id] }
          : { ...prev, removed_classes: [...prev.removed_classes, target.id] });
      }
      setSelectedElement(null);
    }
    setShowContext(null);
  }, [selectedElement, setNodes, setEdges, showContext]);

  const renameSelected = useCallback(() => {
    const target = showContext?.element ?? selectedElement;
    if (target && !("source" in target) && isEditableEntityType(target.data.entityType)) {
      const newLabel = prompt("Enter new name:", String(target.data.label ?? ""));
      if (newLabel) {
        setNodes((nds) =>
          nds.map((n) => (n.id === target.id ? { ...n, data: { ...n.data, label: newLabel } } : n))
        );
        setDraftDiff((prev) => target.data.entityType === "property"
          ? {
              ...prev,
              modified_properties: { ...prev.modified_properties, [target.id]: { label: newLabel } },
            }
          : {
              ...prev,
              modified_classes: { ...prev.modified_classes, [target.id]: { label: newLabel } },
            });
      }
    }
    setShowContext(null);
  }, [selectedElement, setNodes, showContext]);

  useEffect(() => {
    const handleClick = () => setShowContext(null);
    window.addEventListener("click", handleClick);
    return () => window.removeEventListener("click", handleClick);
  }, []);

  const toolbarStyle: React.CSSProperties = {
    display: "flex",
    gap: "8px",
    padding: "12px 16px",
    background: "rgba(3, 9, 18, 0.92)",
    borderBottom: "1px solid rgba(140, 192, 255, 0.12)",
    flexWrap: "wrap",
  };

  const toolbarButtonStyle: React.CSSProperties = {
    display: "inline-flex",
    alignItems: "center",
    gap: "6px",
    padding: "8px 12px",
    borderRadius: "8px",
    border: "1px solid rgba(127, 208, 255, 0.18)",
    background: "rgba(74, 163, 255, 0.08)",
    color: "#ebf3ff",
    fontSize: "12px",
    fontWeight: "600",
    cursor: "pointer",
    transition: "160ms ease",
  };

  const selectStyle: React.CSSProperties = {
    padding: "8px 12px",
    borderRadius: "8px",
    border: "1px solid rgba(127, 208, 255, 0.18)",
    background: "rgba(3, 9, 18, 0.88)",
    color: "#ebf3ff",
    fontSize: "12px",
    minWidth: "260px",
  };

  const contextMenuStyle: React.CSSProperties = {
    position: "fixed",
    background: "rgba(9, 19, 34, 0.95)",
    border: "1px solid rgba(127, 208, 255, 0.3)",
    borderRadius: "8px",
    padding: "8px 0",
    minWidth: "180px",
    boxShadow: "0 8px 24px rgba(0, 0, 0, 0.4)",
    zIndex: 1000,
  };

  const contextItemStyle: React.CSSProperties = {
    padding: "8px 16px",
    display: "flex",
    alignItems: "center",
    gap: "10px",
    color: "#ebf3ff",
    fontSize: "13px",
    cursor: "pointer",
    transition: "160ms ease",
  };

  const detailPanelStyle: React.CSSProperties = {
    flex: "0 0 320px",
    width: "320px",
    minWidth: "320px",
    boxSizing: "border-box",
    background: "rgba(9, 19, 34, 0.95)",
    borderLeft: "1px solid rgba(140, 192, 255, 0.12)",
    padding: "20px",
    overflow: "auto",
    backdropFilter: "blur(18px)",
  };

  return (
    <div style={{ display: "flex", flexDirection: "column", height: "100%", background: "#07111f" }}>
      <style>{ontologyFlowThemeCss}</style>
      <div style={toolbarStyle}>
        <select
          aria-label="Active ontology"
          value={ontologyUri}
          onChange={(event) => {
            setOntologyUri(event.target.value);
            setSelectedElement(null);
            try {
              // Drop the previous ontology's entity from the URL, or a reload
              // would resolve the stale ID and jump back to that ontology.
              const params = new URLSearchParams(window.location.search);
              params.delete("ontologyEntity");
              window.history.replaceState(null, "", `?${params.toString()}`);
            } catch {
              // URL state is optional; switching ontologies still works.
            }
          }}
          style={selectStyle}
        >
          <option value="">Select ontology...</option>
          {registry.map((entry) => (
            <option key={entry.uri} value={entry.uri}>
              {entry.name || entry.uri}
            </option>
          ))}
        </select>
        <button style={toolbarButtonStyle} onClick={addClass}>
          <Plus size={14} />
          Add Class
        </button>
        <button style={toolbarButtonStyle} onClick={addProperty} disabled={nodes.length < 2}>
          <GitBranch size={14} />
          Add Property
        </button>
        <button style={toolbarButtonStyle} onClick={addIndividual}>
          <User size={14} />
          Add Individual
        </button>
        <button style={toolbarButtonStyle} onClick={addRestriction}>
          <Shield size={14} />
          Add Restriction
        </button>
        <button style={toolbarButtonStyle} onClick={addAxiom}>
          <FileText size={14} />
          Add Axiom
        </button>
        <button style={toolbarButtonStyle} onClick={autoLayout}>
          <Layout size={14} />
          Auto Layout
        </button>
        <div style={{ flex: 1 }} />
        <button style={toolbarButtonStyle} onClick={saveDraft} disabled={isSaving}>
          <Send size={14} />
          {isSaving ? "Saving..." : "Propose"}
        </button>
      </div>

      <div style={{ display: "flex", flex: 1, minHeight: 0, minWidth: 0 }}>
        <div style={{ flex: 1, minHeight: 0, minWidth: 0, position: "relative" }}>
          <ReactFlow
            className="ontology-editor-flow"
            nodes={nodes}
            edges={edges}
            onNodesChange={onNodesChange}
            onEdgesChange={onEdgesChange}
            onConnect={onConnect}
            onInit={setFlowInstance}
            onNodeClick={(_, node) => selectNode(node)}
            onEdgeClick={(_, edge) => setSelectedElement(edge)}
            onNodeContextMenu={handleNodeContextMenu}
            onEdgeContextMenu={handleEdgeContextMenu}
            nodeTypes={nodeTypes}
            fitView
            style={{ background: "#07111f" }}
          >
            <Background color="#1a2d3d" gap={20} />
            <Controls />
            <MiniMap {...ONTOLOGY_MINIMAP_THEME} />
          </ReactFlow>

          {isLoadingGraph && (
            <div style={canvasMessageStyle}>Loading ontology structure…</div>
          )}
          {!isLoadingGraph && graphError && (
            <div style={{ ...canvasMessageStyle, color: "#ff9a8d" }}>{graphError}</div>
          )}
          {!isLoadingGraph && !graphError && ontologyUri && nodes.length === 0 && (
            <div style={canvasMessageStyle}>This ontology has no editable classes or properties.</div>
          )}

          {showContext && (
            <div style={{ ...contextMenuStyle, left: showContext.x, top: showContext.y }}>
              {"source" in showContext.element || isEditableEntityType(showContext.element.data.entityType) ? (
                <>
                  {!("source" in showContext.element) && (
                    <div style={contextItemStyle} onClick={renameSelected}>
                      <Pencil size={14} />
                      Rename
                    </div>
                  )}
                  <div style={contextItemStyle} onClick={deleteSelected}>
                    <Trash2 size={14} />
                    Delete
                  </div>
                </>
              ) : (
                <div style={{ ...contextItemStyle, cursor: "default", color: "#8fa8c6" }}>
                  This term is read-only
                </div>
              )}
            </div>
          )}
        </div>

        {selectedElement && (
          <div style={detailPanelStyle}>
            <h3 style={{ margin: "0 0 16px", color: "#ebf3ff", fontSize: "16px" }}>
              {"source" in selectedElement
                ? "Relationship Details"
                : selectedElement.data.entityType === "property"
                  ? "Property Details"
                  : selectedElement.data.entityType === "ontology"
                    ? "Ontology Details"
                    : selectedElement.data.entityType === "external"
                      ? "External Term Details"
                      : "Class Details"}
            </h3>
            <div style={{ marginBottom: "12px" }}>
              <label style={{ display: "block", color: "#8fa8c6", fontSize: "12px", marginBottom: "4px" }}>
                ID
              </label>
              <div style={{ color: "#ebf3ff", fontSize: "13px", wordBreak: "break-all" }}>
                {selectedElement.id}
              </div>
            </div>
            {!("source" in selectedElement) && (
              <>
                <div style={{ marginBottom: "12px" }}>
                  <label style={{ display: "block", color: "#8fa8c6", fontSize: "12px", marginBottom: "4px" }}>
                    Label
                  </label>
                  <input
                    type="text"
                    value={String(selectedElement.data.label ?? "")}
                    readOnly={!isEditableEntityType(selectedElement.data.entityType)}
                    onChange={(e) => {
                      if (!isEditableEntityType(selectedElement.data.entityType)) return;
                      setNodes((nds) =>
                        nds.map((n) =>
                          n.id === selectedElement.id
                            ? { ...n, data: { ...n.data, label: e.target.value } }
                            : n
                        )
                      );
                      setDraftDiff((prev) => ({
                        ...prev,
                        ...(selectedElement.data.entityType === "property"
                          ? {
                              modified_properties: {
                                ...prev.modified_properties,
                                [selectedElement.id]: { label: e.target.value },
                              },
                            }
                          : {
                              modified_classes: {
                                ...prev.modified_classes,
                                [selectedElement.id]: { label: e.target.value },
                              },
                            }),
                      }));
                    }}
                    style={{
                      width: "100%",
                      padding: "8px",
                      borderRadius: "6px",
                      border: "1px solid rgba(127, 208, 255, 0.2)",
                      background: "rgba(3, 9, 18, 0.8)",
                      color: "#ebf3ff",
                      fontSize: "13px",
                    }}
                  />
                </div>
                <div style={{ marginBottom: "12px" }}>
                  <label style={{ display: "block", color: "#8fa8c6", fontSize: "12px", marginBottom: "4px" }}>
                    Type
                  </label>
                  <div style={{ color: "#ebf3ff", fontSize: "13px" }}>
                    {selectedElement.data.type || "owl:Class"}
                  </div>
                </div>
              </>
            )}
          </div>
        )}
      </div>
    </div>
  );
}

const canvasMessageStyle: React.CSSProperties = {
  position: "absolute",
  left: "50%",
  top: "50%",
  transform: "translate(-50%, -50%)",
  padding: "10px 14px",
  borderRadius: "8px",
  border: "1px solid rgba(127, 208, 255, 0.18)",
  background: "rgba(3, 9, 18, 0.9)",
  color: "#8fa8c6",
  fontSize: "13px",
  pointerEvents: "none",
};
