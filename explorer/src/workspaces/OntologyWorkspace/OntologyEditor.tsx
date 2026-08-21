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
} from "@xyflow/react";
import type { Connection, Edge, Node } from "@xyflow/react";
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
import { useI18n } from "../../i18n";

type OntologyNodeData = {
  label?: string;
  type?: string;
};

type OntologyNode = Node<OntologyNodeData>;
type OntologyEdge = Edge<Record<string, unknown>>;

const nodeTypes = {
  classNode: ({ data }: { data: OntologyNodeData }) => (
    <div style={classNodeStyle}>
      <div style={classNodeHeader}>{data.label}</div>
      <div style={classNodeSub}>{data.type}</div>
    </div>
  ),
};

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

interface RegistryEntry {
  uri: string;
  name: string;
}

export function OntologyEditor() {
  const { t } = useI18n();
  const [nodes, setNodes, onNodesChange] = useNodesState<OntologyNode>([]);
  const [edges, setEdges, onEdgesChange] = useEdgesState<OntologyEdge>([]);
  const [selectedElement, setSelectedElement] = useState<OntologyNode | OntologyEdge | null>(null);
  const [registry, setRegistry] = useState<RegistryEntry[]>([]);
  const [ontologyUri, setOntologyUri] = useState<string>("");
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
  const [showDraft, setShowDraft] = useState<boolean>(false);

  const pendingCount =
    draftDiff.added_classes.length +
    draftDiff.removed_classes.length +
    Object.keys(draftDiff.modified_classes).length +
    draftDiff.added_properties.length +
    draftDiff.removed_properties.length +
    Object.keys(draftDiff.modified_properties).length +
    draftDiff.added_restrictions.length +
    draftDiff.removed_restrictions.length +
    draftDiff.added_axioms.length +
    draftDiff.removed_axioms.length +
    Object.keys(draftDiff.annotation_changes).length;

  const updateAddedRestriction = useCallback(
    (index: number, patch: Record<string, any>) => {
      setDraftDiff((prev) => {
        const next = [...prev.added_restrictions];
        next[index] = { ...next[index], ...patch };
        return { ...prev, added_restrictions: next };
      });
    },
    []
  );

  const removeAddedRestriction = useCallback((index: number) => {
    setDraftDiff((prev) => ({
      ...prev,
      added_restrictions: prev.added_restrictions.filter((_, i) => i !== index),
    }));
  }, []);

  const updateAddedAxiom = useCallback(
    (index: number, patch: Record<string, any>) => {
      setDraftDiff((prev) => {
        const next = [...prev.added_axioms];
        next[index] = { ...next[index], ...patch };
        return { ...prev, added_axioms: next };
      });
    },
    []
  );

  const removeAddedAxiom = useCallback((index: number) => {
    setDraftDiff((prev) => ({
      ...prev,
      added_axioms: prev.added_axioms.filter((_, i) => i !== index),
    }));
  }, []);

  useEffect(() => {
    let cancelled = false;
    fetch("/api/ontology/registry")
      .then((response) => (response.ok ? response.json() : []))
      .then((entries: RegistryEntry[]) => {
        if (cancelled) return;
        setRegistry(entries);
        setOntologyUri((current) => current || entries[0]?.uri || "");
      })
      .catch((error) => {
        console.error("Failed to load ontology registry:", error);
      });
    return () => {
      cancelled = true;
    };
  }, []);

  // Load the selected ontology's existing graph structure (classes/properties/
  // edges) as the editable canvas — works for MCP/import-created ontologies
  // (implicit, graph-derived) as well as explicitly registered ones.
  useEffect(() => {
    if (!ontologyUri) return;
    let cancelled = false;
    setNodes([]);
    setEdges([]);
    fetch(`/api/ontology/${encodeURIComponent(ontologyUri)}/structure`)
      .then((response) => (response.ok ? response.json() : null))
      .then((data) => {
        if (cancelled || !data) return;
        const members: OntologyNode[] = [
          ...(data.classes ?? []),
          ...(data.properties ?? []),
        ].map((member, index) => ({
          id: member.id,
          type: "classNode" as const,
          position: { x: (index % 4) * 220 + 40, y: Math.floor(index / 4) * 140 + 40 },
          data: { label: member.label, type: member.type || "owl:Class" },
        }));
        const memberIds = new Set(members.map((n) => n.id));
        const layoutEdges: OntologyEdge[] = (data.edges ?? [])
          .filter((edge: { source: string; target: string }) =>
            memberIds.has(edge.source) && memberIds.has(edge.target)
          )
          .map((edge: { id: string; source: string; target: string; type?: string }) => ({
            id: edge.id,
            source: edge.source,
            target: edge.target,
            label: edge.type,
            type: "smoothstep" as const,
            animated: false,
          }));
        setNodes(members);
        setEdges(layoutEdges);
      })
      .catch((error) => {
        console.error("Failed to load ontology structure:", error);
      });
    return () => {
      cancelled = true;
    };
  }, [ontologyUri, setNodes, setEdges]);

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
      data: { label: "NewClass", type: "owl:Class" },
    };
    setNodes((nds) => [...nds, newNode]);
    setDraftDiff((prev) => ({
      ...prev,
      added_classes: [...prev.added_classes, newId],
    }));
  }, [setNodes]);

  const addProperty = useCallback(() => {
    if (nodes.length < 2) {
      alert(t('onto.alertNeedClasses'));
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
      data: { label: "NewIndividual", type: "owl:NamedIndividual" },
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
    const layoutNodes = nodes.map((node, index) => ({
      ...node,
      position: { x: (index % 4) * 200, y: Math.floor(index / 4) * 150 },
    }));
    setNodes(layoutNodes);
  }, [nodes, setNodes]);

  const saveDraft = useCallback(async () => {
    if (!ontologyUri) {
      alert(t('onto.alertSelectOntology'));
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
        alert(t('onto.draftSaved', { id: data.draft_id }));
      }
    } catch (error) {
      console.error("Failed to save draft:", error);
      alert(t('onto.draftFailed'));
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
      } else {
        setNodes((nds) => nds.filter((n) => n.id !== target.id));
        setDraftDiff((prev) => ({
          ...prev,
          removed_classes: [...prev.removed_classes, target.id],
        }));
      }
      setSelectedElement(null);
    }
    setShowContext(null);
  }, [selectedElement, setNodes, setEdges, showContext]);

  const renameSelected = useCallback(() => {
    const target = showContext?.element ?? selectedElement;
    if (target && !("source" in target)) {
      const newLabel = prompt(t('onto.renamePrompt'), String(target.data.label ?? ""));
      if (newLabel) {
        setNodes((nds) =>
          nds.map((n) => (n.id === target.id ? { ...n, data: { ...n.data, label: newLabel } } : n))
        );
        setDraftDiff((prev) => ({
          ...prev,
          modified_classes: { ...prev.modified_classes, [target.id]: { label: newLabel } },
        }));
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
    position: "absolute",
    right: 0,
    top: 0,
    bottom: 0,
    width: "320px",
    background: "rgba(9, 19, 34, 0.95)",
    borderLeft: "1px solid rgba(140, 192, 255, 0.12)",
    padding: "20px",
    overflow: "auto",
    backdropFilter: "blur(18px)",
  };

  const draftPanelStyle: React.CSSProperties = {
    position: "absolute",
    right: "16px",
    bottom: "16px",
    width: "360px",
    maxHeight: "55vh",
    background: "rgba(9, 19, 34, 0.95)",
    border: "1px solid rgba(127, 208, 255, 0.25)",
    borderRadius: "10px",
    boxShadow: "0 10px 30px rgba(0, 0, 0, 0.5)",
    backdropFilter: "blur(18px)",
    display: "flex",
    flexDirection: "column",
    zIndex: 50,
  };

  const draftPanelHeaderStyle: React.CSSProperties = {
    display: "flex",
    alignItems: "center",
    padding: "12px 14px",
    borderBottom: "1px solid rgba(127, 208, 255, 0.15)",
  };

  const draftPanelCloseStyle: React.CSSProperties = {
    marginLeft: "auto",
    background: "transparent",
    border: "none",
    color: "#8fa8c6",
    fontSize: "20px",
    lineHeight: 1,
    cursor: "pointer",
    padding: "0 6px",
  };

  const draftPanelBodyStyle: React.CSSProperties = {
    padding: "12px 14px",
    overflowY: "auto",
  };

  const draftSectionTitleStyle: React.CSSProperties = {
    color: "#7fdcff",
    fontSize: "12px",
    fontWeight: 700,
    margin: "0 0 8px 0",
    textTransform: "uppercase",
    letterSpacing: "0.05em",
  };

  const draftItemRowStyle: React.CSSProperties = {
    display: "flex",
    alignItems: "center",
    gap: "6px",
    marginBottom: "6px",
  };

  const draftSelectStyle: React.CSSProperties = {
    flex: "0 0 140px",
    padding: "4px 6px",
    borderRadius: "6px",
    border: "1px solid rgba(127, 208, 255, 0.18)",
    background: "rgba(3, 9, 18, 0.85)",
    color: "#ebf3ff",
    fontSize: "11px",
  };

  const draftInputStyle: React.CSSProperties = {
    flex: 1,
    padding: "4px 6px",
    borderRadius: "6px",
    border: "1px solid rgba(127, 208, 255, 0.18)",
    background: "rgba(3, 9, 18, 0.85)",
    color: "#ebf3ff",
    fontSize: "11px",
    minWidth: 0,
  };

  const draftRemoveStyle: React.CSSProperties = {
    flex: "0 0 24px",
    display: "inline-flex",
    alignItems: "center",
    justifyContent: "center",
    padding: "4px",
    borderRadius: "6px",
    border: "1px solid rgba(255, 120, 120, 0.3)",
    background: "rgba(255, 120, 120, 0.08)",
    color: "#ff9a9a",
    cursor: "pointer",
  };

  return (
    <div style={{ display: "flex", flexDirection: "column", height: "100%", background: "#07111f" }}>
      <div style={toolbarStyle}>
        <select
          aria-label={t('onto.ariaOntology')}
          value={ontologyUri}
          onChange={(event) => setOntologyUri(event.target.value)}
          style={selectStyle}
        >
          <option value="">{t('onto.selectOntology')}</option>
          {registry.map((entry) => (
            <option key={entry.uri} value={entry.uri}>
              {entry.name || entry.uri}
            </option>
          ))}
        </select>
        <button style={toolbarButtonStyle} onClick={addClass}>
          <Plus size={14} />
          {t('onto.addClass')}
        </button>
        <button
          style={toolbarButtonStyle}
          onClick={addProperty}
          disabled={nodes.length < 2}
          title={t('onto.alertNeedClasses')}
        >
          <GitBranch size={14} />
          {t('onto.addProperty')}
        </button>
        <button style={toolbarButtonStyle} onClick={addIndividual}>
          <User size={14} />
          {t('onto.addIndividual')}
        </button>
        <button
          style={toolbarButtonStyle}
          onClick={addRestriction}
          title={t('onto.addRestrictionHint')}
        >
          <Shield size={14} />
          {t('onto.addRestriction')}
        </button>
        <button
          style={toolbarButtonStyle}
          onClick={addAxiom}
          title={t('onto.addAxiomHint')}
        >
          <FileText size={14} />
          {t('onto.addAxiom')}
        </button>
        <button style={toolbarButtonStyle} onClick={autoLayout}>
          <Layout size={14} />
          {t('onto.autoLayout')}
        </button>
        <div style={{ flex: 1 }} />
        <button
          style={{
            ...toolbarButtonStyle,
            background: showDraft
              ? "rgba(127, 208, 255, 0.25)"
              : toolbarButtonStyle.background,
          }}
          onClick={() => setShowDraft((s) => !s)}
          title={t('onto.pendingDraft')}
        >
          <FileText size={14} />
          {t('onto.pendingDraft')}
          {pendingCount > 0 && (
            <span
              style={{
                marginLeft: "4px",
                padding: "0 6px",
                borderRadius: "999px",
                background: "rgba(127, 208, 255, 0.35)",
                color: "#ebf3ff",
                fontSize: "11px",
              }}
            >
              {pendingCount}
            </span>
          )}
        </button>
        <button style={toolbarButtonStyle} onClick={saveDraft} disabled={isSaving}>
          <Send size={14} />
          {isSaving ? t('onto.saving') : t('onto.propose')}
        </button>
      </div>

      <div style={{ flex: 1, position: "relative" }}>
        <ReactFlow
          nodes={nodes}
          edges={edges}
          onNodesChange={onNodesChange}
          onEdgesChange={onEdgesChange}
          onConnect={onConnect}
          onNodeClick={(_, node) => setSelectedElement(node)}
          onEdgeClick={(_, edge) => setSelectedElement(edge)}
          onNodeContextMenu={handleNodeContextMenu}
          onEdgeContextMenu={handleEdgeContextMenu}
          nodeTypes={nodeTypes}
          fitView
          style={{ background: "#07111f" }}
        >
          <Background color="#1a2d3d" gap={20} />
          <Controls />
          <MiniMap nodeColor="#4aa3ff" maskColor="rgba(0,0,0,0.6)" />
        </ReactFlow>

        {showContext && (
          <div style={{ ...contextMenuStyle, left: showContext.x, top: showContext.y }}>
            <div style={contextItemStyle} onClick={renameSelected}>
              <Pencil size={14} />
              {t('onto.rename')}
            </div>
            <div style={contextItemStyle} onClick={deleteSelected}>
              <Trash2 size={14} />
              {t('onto.delete')}
            </div>
          </div>
        )}

        {showDraft && (
          <div style={draftPanelStyle}>
            <div style={draftPanelHeaderStyle}>
              <strong style={{ color: "#ebf3ff", fontSize: "14px" }}>
                {t('onto.pendingDraft')}
              </strong>
              <span style={{ color: "#8fa8c6", fontSize: "12px", marginLeft: "8px" }}>
                {t('onto.pendingItemsCount', { count: pendingCount })}
              </span>
              <button
                onClick={() => setShowDraft(false)}
                style={draftPanelCloseStyle}
                aria-label="Close pending draft"
              >
                ×
              </button>
            </div>

            {pendingCount === 0 ? (
              <p style={{ color: "#8fa8c6", fontSize: "12px", padding: "12px 4px", margin: 0 }}>
                {t('onto.noPendingItems')}
              </p>
            ) : (
              <div style={draftPanelBodyStyle}>
                {(draftDiff.added_classes.length +
                  draftDiff.removed_classes.length +
                  Object.keys(draftDiff.modified_classes).length +
                  draftDiff.added_properties.length +
                  draftDiff.removed_properties.length +
                  Object.keys(draftDiff.modified_properties).length) > 0 && (
                  <div style={{ marginBottom: "12px", color: "#8fa8c6", fontSize: "12px" }}>
                    Classes +{draftDiff.added_classes.length} −
                    {draftDiff.removed_classes.length} ~{Object.keys(draftDiff.modified_classes).length}
                    {" · "}
                    Properties +{draftDiff.added_properties.length} −
                    {draftDiff.removed_properties.length} ~{Object.keys(draftDiff.modified_properties).length}
                  </div>
                )}

                {draftDiff.added_restrictions.length > 0 && (
                  <div style={{ marginBottom: "14px" }}>
                    <h4 style={draftSectionTitleStyle}>
                      {t('onto.restrictionType')} ({draftDiff.added_restrictions.length})
                    </h4>
                    {draftDiff.added_restrictions.map((r, i) => (
                      <div key={`r-${i}`} style={draftItemRowStyle}>
                        <select
                          value={String(r.type ?? "someValuesFrom")}
                          onChange={(e) => updateAddedRestriction(i, { type: e.target.value })}
                          style={draftSelectStyle}
                        >
                          <option value="someValuesFrom">someValuesFrom</option>
                          <option value="allValuesFrom">allValuesFrom</option>
                          <option value="hasValue">hasValue</option>
                          <option value="minCardinality">minCardinality</option>
                          <option value="maxCardinality">maxCardinality</option>
                          <option value="exactCardinality">exactCardinality</option>
                        </select>
                        <input
                          type="text"
                          value={String(r.value ?? "")}
                          placeholder={t('onto.targetClass')}
                          onChange={(e) => updateAddedRestriction(i, { value: e.target.value })}
                          style={draftInputStyle}
                        />
                        <button
                          onClick={() => removeAddedRestriction(i)}
                          style={draftRemoveStyle}
                          aria-label={t('onto.removeItem')}
                          title={t('onto.removeItem')}
                        >
                          <Trash2 size={12} />
                        </button>
                      </div>
                    ))}
                  </div>
                )}

                {draftDiff.added_axioms.length > 0 && (
                  <div style={{ marginBottom: "14px" }}>
                    <h4 style={draftSectionTitleStyle}>
                      {t('onto.axiomType')} ({draftDiff.added_axioms.length})
                    </h4>
                    {draftDiff.added_axioms.map((a, i) => (
                      <div key={`a-${i}`} style={draftItemRowStyle}>
                        <select
                          value={String(a.type ?? "subClassOf")}
                          onChange={(e) => updateAddedAxiom(i, { type: e.target.value })}
                          style={draftSelectStyle}
                        >
                          <option value="subClassOf">subClassOf</option>
                          <option value="equivalentClass">equivalentClass</option>
                          <option value="disjointWith">disjointWith</option>
                        </select>
                        <input
                          type="text"
                          value={String(a.value ?? "")}
                          placeholder={t('onto.targetClass')}
                          onChange={(e) => updateAddedAxiom(i, { value: e.target.value })}
                          style={draftInputStyle}
                        />
                        <button
                          onClick={() => removeAddedAxiom(i)}
                          style={draftRemoveStyle}
                          aria-label={t('onto.removeItem')}
                          title={t('onto.removeItem')}
                        >
                          <Trash2 size={12} />
                        </button>
                      </div>
                    ))}
                  </div>
                )}

                {draftDiff.added_restrictions.length === 0 &&
                  draftDiff.added_axioms.length === 0 && (
                    <p style={{ color: "#8fa8c6", fontSize: "12px", margin: 0 }}>
                      {t('onto.noPendingItems')}
                    </p>
                  )}
              </div>
            )}
          </div>
        )}

        {selectedElement && (
          <div style={detailPanelStyle}>
            <h3 style={{ margin: "0 0 16px", color: "#ebf3ff", fontSize: "16px" }}>
              {"source" in selectedElement ? t('onto.propertyDetails') : t('onto.classDetails')}
            </h3>
            <div style={{ marginBottom: "12px" }}>
              <label style={{ display: "block", color: "#8fa8c6", fontSize: "12px", marginBottom: "4px" }}>
                {t('onto.id')}
              </label>
              <div style={{ color: "#ebf3ff", fontSize: "13px", wordBreak: "break-all" }}>
                {selectedElement.id}
              </div>
            </div>
            {!("source" in selectedElement) && (
              <>
                <div style={{ marginBottom: "12px" }}>
                  <label style={{ display: "block", color: "#8fa8c6", fontSize: "12px", marginBottom: "4px" }}>
                    {t('onto.label')}
                  </label>
                  <input
                    type="text"
                    value={String(selectedElement.data.label ?? "")}
                    onChange={(e) => {
                      setNodes((nds) =>
                        nds.map((n) =>
                          n.id === selectedElement.id
                            ? { ...n, data: { ...n.data, label: e.target.value } }
                            : n
                        )
                      );
                      setDraftDiff((prev) => ({
                        ...prev,
                        modified_classes: {
                          ...prev.modified_classes,
                          [selectedElement.id]: { label: e.target.value },
                        },
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
                    {t('onto.type')}
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
