/**
 * src/workspaces/EnrichWorkspace/RegistryTab.tsx
 *
 * Document Registry — a live, filterable chronological audit log of every
 * KG / Ontology mutation that occurred in this session.
 */
import { useState } from "react";
import { ClipboardList, Filter, Trash2, ChevronDown, ChevronRight } from "lucide-react";
import { useRegistry, clearRegistry, type RegistryEntryOp } from "../../store/registryStore";

const OP_META: Record<
  RegistryEntryOp,
  { label: string; color: string; bg: string; border: string }
> = {
  import:       { label: "IMPORT",       color: "#4aa3ff", bg: "rgba(74,163,255,0.12)",  border: "rgba(74,163,255,0.28)" },
  export:       { label: "EXPORT",       color: "#8fa8c6", bg: "rgba(143,168,198,0.08)", border: "rgba(143,168,198,0.18)" },
  merge:        { label: "MERGE",        color: "#f2b66d", bg: "rgba(242,182,109,0.12)", border: "rgba(242,182,109,0.28)" },
  "add-node":   { label: "ADD NODE",     color: "#4cc38a", bg: "rgba(76,195,138,0.12)",  border: "rgba(76,195,138,0.28)" },
  "update-node": { label: "UPDATE NODE",  color: "#79c0ff", bg: "rgba(121,192,255,0.10)", border: "rgba(121,192,255,0.24)" },
  "add-edge":   { label: "ADD EDGE",     color: "#4cc38a", bg: "rgba(76,195,138,0.10)",  border: "rgba(76,195,138,0.22)" },
  delete:       { label: "DELETE",       color: "#ff7b72", bg: "rgba(255,123,114,0.12)", border: "rgba(255,123,114,0.28)" },
  infer:        { label: "INFER",        color: "#d2a8ff", bg: "rgba(210,168,255,0.12)", border: "rgba(210,168,255,0.28)" },
  "vocab-import": { label: "VOCAB",      color: "#79c0ff", bg: "rgba(121,192,255,0.12)", border: "rgba(121,192,255,0.28)" },
};

const ALL_OPS: (RegistryEntryOp | "all")[] = [
  "all", "import", "export", "merge", "add-node", "update-node", "add-edge", "infer", "delete", "vocab-import",
];

function formatTimestamp(date: Date): string {
  return date.toLocaleTimeString(undefined, { hour: "2-digit", minute: "2-digit", second: "2-digit" });
}

function formatDate(date: Date): string {
  return date.toLocaleDateString(undefined, { month: "short", day: "numeric" });
}

function EntryRow({ entry }: { entry: ReturnType<typeof useRegistry>[number] }) {
  const [expanded, setExpanded] = useState(false);
  const meta = OP_META[entry.op];
  const hasDetail = entry.detail && Object.keys(entry.detail).length > 0;

  return (
    <div style={entryCardStyle}>
      <div style={{ display: "flex", alignItems: "flex-start", gap: 12 }}>
        {/* Op Badge */}
        <span
          style={{
            flexShrink: 0,
            display: "inline-block",
            padding: "3px 8px",
            borderRadius: 999,
            fontSize: 10,
            fontWeight: 800,
            letterSpacing: "0.07em",
            color: meta.color,
            background: meta.bg,
            border: `1px solid ${meta.border}`,
            marginTop: 1,
          }}
        >
          {meta.label}
        </span>

        {/* Content */}
        <div style={{ flex: 1, minWidth: 0 }}>
          <div style={{ color: "#e6edf3", fontSize: 13, fontWeight: 500, wordBreak: "break-word" }}>
            {entry.summary}
          </div>
          <div style={{ color: "#8b949e", fontSize: 11, marginTop: 3 }}>
            {formatDate(entry.timestamp)} · {formatTimestamp(entry.timestamp)}
          </div>
        </div>

        {/* Expand toggle */}
        {hasDetail ? (
          <button
            onClick={() => setExpanded((v) => !v)}
            title={expanded ? "Collapse details" : "Expand details"}
            style={expandBtnStyle}
          >
            {expanded ? <ChevronDown size={14} /> : <ChevronRight size={14} />}
          </button>
        ) : null}
      </div>

      {/* Expanded detail */}
      {expanded && hasDetail ? (
        <pre style={detailPreStyle}>
          {JSON.stringify(entry.detail, null, 2)}
        </pre>
      ) : null}
    </div>
  );
}

export function RegistryTab() {
  const entries = useRegistry();
  const [activeFilter, setActiveFilter] = useState<RegistryEntryOp | "all">("all");

  const filtered = activeFilter === "all"
    ? entries
    : entries.filter((e) => e.op === activeFilter);

  return (
    <div style={shellStyle}>
      {/* Header */}
      <div style={headerStyle}>
        <div style={{ display: "flex", alignItems: "center", gap: 10 }}>
          <ClipboardList size={18} color="#4aa3ff" />
          <div>
            <div style={{ color: "#ebf3ff", fontSize: 16, fontWeight: 700 }}>Document Registry</div>
            <div style={{ color: "#8b949e", fontSize: 12 }}>
              Audit log of all KG and Ontology mutations this session
            </div>
          </div>
        </div>
        <div style={{ display: "flex", alignItems: "center", gap: 8 }}>
          <span style={{ color: "#8fa8c6", fontSize: 12 }}>
            {entries.length} event{entries.length !== 1 ? "s" : ""}
          </span>
          {entries.length > 0 ? (
            <button
              onClick={clearRegistry}
              title="Clear all events"
              style={clearBtnStyle}
            >
              <Trash2 size={13} />
              <span>Clear</span>
            </button>
          ) : null}
        </div>
      </div>

      {/* Filter pills */}
      <div style={filterBarStyle}>
        <Filter size={13} color="#8fa8c6" />
        <div style={{ display: "flex", gap: 6, flexWrap: "wrap" }}>
          {ALL_OPS.map((op) => {
            const isActive = op === activeFilter;
            const meta = op === "all" ? null : OP_META[op as RegistryEntryOp];
            return (
              <button
                key={op}
                onClick={() => setActiveFilter(op as typeof activeFilter)}
                style={{
                  padding: "4px 10px",
                  borderRadius: 999,
                  fontSize: 11,
                  fontWeight: 600,
                  cursor: "pointer",
                  border: isActive
                    ? `1px solid ${meta?.border ?? "rgba(127,208,255,0.35)"}`
                    : "1px solid rgba(255,255,255,0.06)",
                  background: isActive
                    ? (meta?.bg ?? "rgba(74,163,255,0.14)")
                    : "transparent",
                  color: isActive
                    ? (meta?.color ?? "#8ed3ff")
                    : "#8b949e",
                  transition: "all 140ms ease",
                }}
              >
                {op === "all" ? "All" : (meta?.label ?? op)}
              </button>
            );
          })}
        </div>
      </div>

      {/* Feed */}
      <div style={feedStyle}>
        {filtered.length === 0 ? (
          <div style={emptyStateStyle}>
            <ClipboardList size={36} color="rgba(127,208,255,0.15)" />
            <div style={{ color: "#8b949e", fontSize: 14, marginTop: 12, fontWeight: 500 }}>
              No events recorded yet
            </div>
            <div style={{ color: "#6a7f97", fontSize: 12, marginTop: 4, textAlign: "center", maxWidth: 300 }}>
              Import a file, run reasoning, or merge entities to see activity appear here.
            </div>
          </div>
        ) : (
          filtered.map((entry) => <EntryRow key={entry.id} entry={entry} />)
        )}
      </div>
    </div>
  );
}

/* ─── styles ─────────────────────────────────────────────────────── */

const shellStyle: React.CSSProperties = {
  display: "flex",
  flexDirection: "column",
  width: "100%",
  height: "100%",
  background: "#0d1117",
  overflow: "hidden",
};

const headerStyle: React.CSSProperties = {
  display: "flex",
  alignItems: "center",
  justifyContent: "space-between",
  padding: "20px 24px 16px",
  borderBottom: "1px solid rgba(88,166,255,0.1)",
  flexShrink: 0,
};

const filterBarStyle: React.CSSProperties = {
  display: "flex",
  alignItems: "center",
  gap: 10,
  padding: "12px 24px",
  borderBottom: "1px solid rgba(255,255,255,0.05)",
  flexShrink: 0,
};

const feedStyle: React.CSSProperties = {
  flex: 1,
  overflowY: "auto",
  padding: "16px 24px",
  display: "flex",
  flexDirection: "column",
  gap: 8,
};

const entryCardStyle: React.CSSProperties = {
  padding: "12px 14px",
  borderRadius: 12,
  background: "linear-gradient(135deg, rgba(13,17,23,0.6), rgba(22,27,34,0.4))",
  border: "1px solid rgba(255,255,255,0.06)",
  boxShadow: "inset 0 1px 0 rgba(255,255,255,0.03)",
};

const expandBtnStyle: React.CSSProperties = {
  flexShrink: 0,
  background: "transparent",
  border: "none",
  color: "#8b949e",
  cursor: "pointer",
  padding: 4,
  borderRadius: 6,
  display: "flex",
  alignItems: "center",
};

const detailPreStyle: React.CSSProperties = {
  marginTop: 10,
  padding: "10px 12px",
  borderRadius: 8,
  background: "rgba(0,0,0,0.28)",
  border: "1px solid rgba(255,255,255,0.06)",
  color: "#79c0ff",
  fontSize: 11,
  fontFamily: "'JetBrains Mono', monospace",
  overflowX: "auto",
  whiteSpace: "pre-wrap",
  wordBreak: "break-all",
};

const clearBtnStyle: React.CSSProperties = {
  display: "inline-flex",
  alignItems: "center",
  gap: 5,
  padding: "5px 10px",
  borderRadius: 8,
  border: "1px solid rgba(255,123,114,0.22)",
  background: "rgba(255,123,114,0.06)",
  color: "#ff7b72",
  fontSize: 12,
  fontWeight: 600,
  cursor: "pointer",
};

const emptyStateStyle: React.CSSProperties = {
  flex: 1,
  display: "flex",
  flexDirection: "column",
  alignItems: "center",
  justifyContent: "center",
  padding: 40,
  minHeight: 280,
};
