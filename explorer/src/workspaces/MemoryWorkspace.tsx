import { useCallback, useEffect, useRef, useState, type CSSProperties } from "react";
import { Brain, RefreshCw } from "lucide-react";

import { MarkdownContentViewer } from "./GraphWorkspace/MarkdownContentViewer";
import {
  readMarkdownResource,
  type MarkdownApplyResult,
} from "./GraphWorkspace/markdownResourceClient";
import { GRAPH_THEME } from "./GraphWorkspace/graphTheme";

interface MemorySummary {
  id: string;
  type: string;
  excerpt: string;
  updated_at: string | null;
}

interface MemoryListResponse {
  items: MemorySummary[];
  total: number;
}
interface MemoryWorkspaceProps {
  onDirtyChange?: (dirty: boolean) => void;
}


function responseMessage(payload: unknown, fallback: string): string {
  if (!payload || typeof payload !== "object" || !("detail" in payload)) {
    return fallback;
  }
  return typeof payload.detail === "string" ? payload.detail : fallback;
}


async function fetchMemoryList(): Promise<MemoryListResponse> {
  const response = await fetch("/api/memories?skip=0&limit=100");
  if (!response.ok) {
    const payload = await response.json().catch(() => null);
    throw new Error(responseMessage(payload, `Memory list failed (${response.status}).`));
  }
  return response.json() as Promise<MemoryListResponse>;
}

export function MemoryWorkspace({ onDirtyChange }: MemoryWorkspaceProps = {}) {
  const [items, setItems] = useState<MemorySummary[]>([]);
  const [selectedId, setSelectedId] = useState("");
  const [selectedBody, setSelectedBody] = useState("");
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [dirty, setDirty] = useState(false);
  const [reloadToken, setReloadToken] = useState(0);
  const listGenerationRef = useRef(0);
  const selectionGenerationRef = useRef(0);
  const handleDirtyChange = useCallback((nextDirty: boolean) => {
    setDirty(nextDirty);
    onDirtyChange?.(nextDirty);
  }, [onDirtyChange]);


  useEffect(() => {
    let cancelled = false;
    const listGeneration = ++listGenerationRef.current;
    const selectionGeneration = ++selectionGenerationRef.current;
    const isCurrent = () => (
      !cancelled
      && listGeneration === listGenerationRef.current
      && selectionGeneration === selectionGenerationRef.current
    );
    const load = async () => {
      setLoading(true);
      setError("");
      try {
        const payload = await fetchMemoryList();
        if (!isCurrent()) return;
        setItems(payload.items);
        const first = payload.items[0];
        if (!first) {
          setSelectedId("");
          setSelectedBody("");
          return;
        }
        const document = await readMarkdownResource({
          kind: "agent-memory",
          id: first.id,
        });
        if (!isCurrent()) return;
        setSelectedId(first.id);
        setSelectedBody(document.body);
      } catch (failure) {
        if (isCurrent()) {
          setError(failure instanceof Error ? failure.message : "Memories could not be loaded.");
        }
      } finally {
        if (isCurrent()) setLoading(false);
      }
    };
    void load();
    return () => {
      cancelled = true;
      listGenerationRef.current += 1;
      selectionGenerationRef.current += 1;
    };
  }, [reloadToken]);

  const selectMemory = async (memoryId: string) => {
    if (memoryId === selectedId) return;
    if (dirty && !window.confirm("Discard the unapplied Markdown draft and open another memory?")) return;
    const selectionGeneration = ++selectionGenerationRef.current;
    handleDirtyChange(false);
    setLoading(true);
    setError("");
    try {
      const document = await readMarkdownResource({
        kind: "agent-memory",
        id: memoryId,
      });
      if (selectionGeneration !== selectionGenerationRef.current) return;
      setSelectedId(memoryId);
      setSelectedBody(document.body);
    } catch (failure) {
      if (selectionGeneration === selectionGenerationRef.current) {
        setError(failure instanceof Error ? failure.message : "The memory could not be loaded.");
      }
    } finally {
      if (selectionGeneration === selectionGenerationRef.current) {
        setLoading(false);
      }
    }
  };

  const refreshMemorySummaries = useCallback(async () => {
    const listGeneration = ++listGenerationRef.current;
    try {
      const payload = await fetchMemoryList();
      if (listGeneration !== listGenerationRef.current) return;
      setItems(payload.items);
    } catch {
      if (listGeneration === listGenerationRef.current) {
        setError("Memory was applied, but its summary could not be refreshed.");
      }
    }
  }, []);

  const applyMemory = useCallback((result: MarkdownApplyResult) => {
    setSelectedBody(result.body);
    handleDirtyChange(false);
    setItems((current) => current.map((item) => (
      item.id === result.resource.id
        ? { ...item, excerpt: result.body.replace(/\s+/g, " ").slice(0, 160) }
        : item
    )));
    void refreshMemorySummaries();
  }, [handleDirtyChange, refreshMemorySummaries]);

  return (
    <div style={workspaceStyle}>
      <aside style={listPanelStyle} aria-label="Agent memories">
        <div style={listHeaderStyle}>
          <div>
            <div style={listTitleStyle}>AgentMemory</div>
            <div style={listCountStyle}>{items.length} loaded</div>
          </div>
          <button
            type="button"
            aria-label="Refresh memories"
            onClick={() => setReloadToken((value) => value + 1)}
            disabled={loading || dirty}
            title={dirty ? "Apply or cancel the current draft before refreshing" : "Refresh memories"}
            style={{ ...iconButtonStyle, opacity: loading || dirty ? 0.55 : 1 }}
          >
            <RefreshCw size={14} aria-hidden="true" />
          </button>
        </div>
        <div style={memoryListStyle}>
          {items.map((item) => (
            <button
              type="button"
              key={item.id}
              onClick={() => void selectMemory(item.id)}
              aria-current={item.id === selectedId ? "true" : undefined}
              style={{
                ...memoryButtonStyle,
                ...(item.id === selectedId ? selectedMemoryButtonStyle : {}),
              }}
            >
              <span style={memoryTypeStyle}>{item.type}</span>
              <span style={memoryIdStyle}>{item.id}</span>
              <span style={memoryExcerptStyle}>{item.excerpt || "Empty memory"}</span>
            </button>
          ))}
          {!loading && items.length === 0 ? (
            <div style={emptyStyle}>
              <Brain size={22} aria-hidden="true" />
              <span>No AgentMemory items are available.</span>
              <button type="button" onClick={() => setReloadToken((value) => value + 1)} style={retryButtonStyle}>
                Refresh
              </button>
            </div>
          ) : null}
        </div>
      </aside>

      <main style={editorPanelStyle}>
        {error ? <div role="alert" style={alertStyle}>{error}</div> : null}
        {loading ? (
          <div role="status" style={emptyStyle}>Loading memories…</div>
        ) : selectedId ? (
          <>
            <div style={selectionHeaderStyle}>
              <span style={selectionLabelStyle}>Selected memory</span>
              <strong style={selectionIdStyle}>{selectedId}</strong>
            </div>
            <MarkdownContentViewer
              content={selectedBody}
              resource={{ kind: "agent-memory", id: selectedId }}
              onApplied={applyMemory}
              onDirtyChange={handleDirtyChange}
            />
          </>
        ) : null}
      </main>
    </div>
  );
}

const workspaceStyle: CSSProperties = {
  display: "grid",
  gridTemplateColumns: "minmax(220px, 300px) minmax(0, 1fr)",
  height: "100%",
  minHeight: 0,
  background: GRAPH_THEME.ui.surface.stage,
};

const listPanelStyle: CSSProperties = {
  display: "flex",
  flexDirection: "column",
  minHeight: 0,
  borderRight: `1px solid ${GRAPH_THEME.ui.surface.panelBorder}`,
  background: GRAPH_THEME.ui.surface.panel,
};

const listHeaderStyle: CSSProperties = {
  display: "flex",
  alignItems: "center",
  justifyContent: "space-between",
  gap: 12,
  padding: 16,
  borderBottom: `1px solid ${GRAPH_THEME.ui.surface.panelBorder}`,
};

const listTitleStyle: CSSProperties = {
  color: GRAPH_THEME.ui.text.strong,
  fontSize: 14,
  fontWeight: 700,
};

const listCountStyle: CSSProperties = {
  color: GRAPH_THEME.ui.text.muted,
  fontSize: 11,
  marginTop: 3,
};

const iconButtonStyle: CSSProperties = {
  display: "inline-grid",
  placeItems: "center",
  width: 30,
  height: 30,
  borderRadius: 8,
  border: `1px solid ${GRAPH_THEME.ui.surface.panelBorder}`,
  background: "rgba(255, 255, 255, 0.04)",
  color: GRAPH_THEME.ui.text.body,
  cursor: "pointer",
};

const memoryListStyle: CSSProperties = {
  display: "flex",
  flexDirection: "column",
  gap: 6,
  minHeight: 0,
  padding: 10,
  overflowY: "auto",
};

const memoryButtonStyle: CSSProperties = {
  display: "flex",
  flexDirection: "column",
  alignItems: "flex-start",
  gap: 5,
  padding: 10,
  borderRadius: 9,
  border: "1px solid transparent",
  background: "transparent",
  color: GRAPH_THEME.ui.text.body,
  textAlign: "left",
  cursor: "pointer",
};

const selectedMemoryButtonStyle: CSSProperties = {
  border: `1px solid ${GRAPH_THEME.ui.control.activeBorder}`,
  background: GRAPH_THEME.ui.timeline.playheadSoft,
};

const memoryTypeStyle: CSSProperties = {
  color: GRAPH_THEME.ui.timeline.playhead,
  fontSize: 10,
  fontWeight: 700,
  textTransform: "uppercase",
};

const memoryIdStyle: CSSProperties = {
  maxWidth: "100%",
  overflow: "hidden",
  color: GRAPH_THEME.ui.text.strong,
  fontFamily: "monospace",
  fontSize: 12,
  textOverflow: "ellipsis",
  whiteSpace: "nowrap",
};

const memoryExcerptStyle: CSSProperties = {
  display: "-webkit-box",
  overflow: "hidden",
  color: GRAPH_THEME.ui.text.muted,
  fontSize: 11,
  lineHeight: 1.45,
  WebkitBoxOrient: "vertical",
  WebkitLineClamp: 2,
};

const editorPanelStyle: CSSProperties = {
  minWidth: 0,
  minHeight: 0,
  padding: 20,
  overflowY: "auto",
};

const selectionHeaderStyle: CSSProperties = {
  display: "flex",
  flexDirection: "column",
  gap: 4,
  marginBottom: 12,
};

const selectionLabelStyle: CSSProperties = {
  color: GRAPH_THEME.ui.text.muted,
  fontSize: 11,
};

const selectionIdStyle: CSSProperties = {
  color: GRAPH_THEME.ui.text.strong,
  fontFamily: "monospace",
  fontSize: 14,
  wordBreak: "break-all",
};

const emptyStyle: CSSProperties = {
  display: "flex",
  flexDirection: "column",
  alignItems: "center",
  justifyContent: "center",
  gap: 10,
  minHeight: 160,
  padding: 20,
  color: GRAPH_THEME.ui.text.muted,
  fontSize: 12,
  textAlign: "center",
};

const retryButtonStyle: CSSProperties = {
  padding: "6px 10px",
  borderRadius: 7,
  border: `1px solid ${GRAPH_THEME.ui.control.activeBorder}`,
  background: GRAPH_THEME.ui.timeline.playheadSoft,
  color: GRAPH_THEME.ui.timeline.playhead,
  cursor: "pointer",
};

const alertStyle: CSSProperties = {
  marginBottom: 12,
  padding: "10px 12px",
  borderRadius: 8,
  border: "1px solid rgba(248, 81, 73, 0.28)",
  background: "rgba(248, 81, 73, 0.1)",
  color: "#ffb4ad",
  fontSize: 12,
};
