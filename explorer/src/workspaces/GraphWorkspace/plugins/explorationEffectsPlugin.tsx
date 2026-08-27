import type { CSSProperties } from "react";

import type {
  GraphDiagnosticsSnapshot,
  GraphEffectAvailability,
  GraphEffectToggle,
} from "../types";
import type { GraphPlugin } from "./types";

const EFFECTS_PANEL_ID = "effects-panel";

type EffectRowConfig = {
  key: GraphEffectToggle;
  label: string;
  description: string;
};

const EFFECT_ROWS: EffectRowConfig[] = [
  {
    key: "pathPulseEnabled",
    label: "Path Pulse",
    description: "Animated pulse on the active selected path.",
  },
  {
    key: "pathFlowEnabled",
    label: "Path Flow",
    description: "Directional flow accents along the active selected path.",
  },
  {
    key: "lensEnabled",
    label: "Neighborhood Lens",
    description: "Local emphasis around the hovered or selected node.",
  },
  {
    key: "edgeLabelsEnabled",
    label: "Edge Labels",
    description: "Draw the relationship type on graph edges. Off restores label-free edges on dense graphs.",
  },
  {
    key: "legendEnabled",
    label: "Semantic Legend",
    description: "Compact semantic group legend for graph orientation.",
  },
];

// Maps the effect toggle keys rendered by this plugin to their corresponding
// availability keys in GraphDiagnosticsSnapshot["effectAvailability"]. Kept
// local because this plugin only renders a subset of all effects.
const EFFECT_AVAILABILITY_KEYS: Partial<Record<GraphEffectToggle, keyof GraphDiagnosticsSnapshot["effectAvailability"]>> = {
  pathPulseEnabled: "pathPulse",
  pathFlowEnabled: "pathFlow",
  lensEnabled: "lens",
  edgeLabelsEnabled: "edgeLabels",
  legendEnabled: "legend",
};

function renderAvailabilityText(availability: GraphEffectAvailability) {
  if (availability.available) {
    if (typeof availability.visibleSegments === "number" && typeof availability.segmentCap === "number") {
      return `${availability.reason} · ${availability.visibleSegments}/${availability.segmentCap} segments`;
    }
    return availability.reason;
  }

  return availability.detail ? `${availability.reason} · ${availability.detail}` : availability.reason;
}

function collectLegendItems(context: Parameters<NonNullable<GraphPlugin["renderPanel"]>>[0]) {
  const groups = new Map<string, { count: number; color: string }>();
  context.graph.forEachNode((_nodeId, attrs) => {
    const semanticGroup = String(attrs.semanticGroup || attrs.nodeType || "entity");
    const color = String(attrs.baseColor || context.theme.palette.semantic[0]);
    const current = groups.get(semanticGroup);
    groups.set(semanticGroup, {
      count: (current?.count ?? 0) + 1,
      color,
    });
  });

  return [...groups.entries()]
    .map(([group, data]) => ({ group, ...data }))
    .sort((left, right) => right.count - left.count)
    .slice(0, context.theme.effects.legend.maxGroups);
}

function EffectToggleRow({
  label,
  description,
  checked,
  availability,
  onToggle,
}: {
  label: string;
  description: string;
  checked: boolean;
  availability: GraphEffectAvailability;
  onToggle: () => void;
}) {
  return (
    <div style={toggleRowStyle}>
      <div style={{ minWidth: 0, flex: 1 }}>
        <div style={rowTitleStyle}>{label}</div>
        <div style={rowDescriptionStyle}>{description}</div>
        <div style={rowMetaStyle}>{renderAvailabilityText(availability)}</div>
      </div>
      <button type="button" onClick={onToggle} style={checked ? toggleButtonActiveStyle : toggleButtonStyle}>
        {checked ? "On" : "Off"}
      </button>
    </div>
  );
}

export const explorationEffectsPlugin: GraphPlugin = {
  id: "exploration-effects",
  mount: () => {},
  unmount: () => {},
  onStateChange: () => {},
  toolbarItems: (context) => [
    {
      id: "effects-toggle",
      label: "Effects",
      title: "Open exploration effects controls",
      active: context.isPanelOpen(EFFECTS_PANEL_ID),
      order: 18,
      onClick: () => context.dispatchAction({ type: "togglePanel", panelId: EFFECTS_PANEL_ID }),
    },
  ],
  renderPanel: (context) => {
    if (!context.isPanelOpen(EFFECTS_PANEL_ID)) {
      return null;
    }

    const effectsState = context.getEffectsState();
    const diagnosticsSnapshot = context.getDiagnosticsSnapshot();
    const availability = diagnosticsSnapshot?.effectAvailability;
    const legendItems = effectsState.legendEnabled ? collectLegendItems(context) : [];

    return {
      id: EFFECTS_PANEL_ID,
      title: "Effects",
      placement: "bottom",
      order: 8,
      defaultOpen: false,
      preferredWidth: 420,
      preferredHeight: 320,
      content: (
        <div style={panelBodyStyle}>
          <div style={panelEyebrowStyle}>Exploration effects</div>

          <div style={sectionStyle}>
            <div style={sectionTitleStyle}>Path and focus</div>
            {EFFECT_ROWS.map((row) => (
              <EffectToggleRow
                key={row.key}
                label={row.label}
                description={row.description}
                checked={effectsState[row.key]}
                availability={
                  (EFFECT_AVAILABILITY_KEYS[row.key] !== undefined
                    ? availability?.[EFFECT_AVAILABILITY_KEYS[row.key]!]
                    : undefined) ?? {
                    enabled: effectsState[row.key],
                    available: false,
                    reason: "Waiting for graph runtime",
                  }
                }
                onToggle={() => context.dispatchAction({ type: "toggleEffect", effect: row.key })}
              />
            ))}
          </div>

          {effectsState.legendEnabled ? (
            <div style={sectionStyle}>
              <div style={sectionTitleStyle}>Semantic legend</div>
              {legendItems.length ? (
                <div style={{ display: "flex", flexDirection: "column", gap: 8 }}>
                  {legendItems.map((item) => (
                    <div key={item.group} style={legendRowStyle}>
                      <span
                        style={{
                          ...legendSwatchStyle,
                          background: item.color,
                          boxShadow: `0 0 0 1px rgba(255,255,255,0.06), 0 0 14px ${item.color}40`,
                        }}
                      />
                      <div style={{ minWidth: 0, flex: 1 }}>
                        <div style={rowTitleStyle}>{item.group}</div>
                        <div style={rowMetaStyle}>{item.count.toLocaleString()} nodes</div>
                      </div>
                    </div>
                  ))}
                </div>
              ) : (
                <div style={emptyTextStyle}>Legend data will populate when graph metadata is available.</div>
              )}
            </div>
          ) : null}

          {import.meta.env.DEV ? (
            <div style={sectionStyle}>
              <div style={sectionTitleStyle}>Diagnostics</div>
              <EffectToggleRow
                label="Dev Diagnostics"
                description="Inspect plugin, interaction, and effect gating state."
                checked={effectsState.diagnosticsEnabled}
                availability={
                  availability?.diagnostics ?? {
                    enabled: effectsState.diagnosticsEnabled,
                    available: false,
                    reason: "Waiting for graph runtime",
                  }
                }
                onToggle={() => context.dispatchAction({ type: "toggleEffect", effect: "diagnosticsEnabled" })}
              />
              {effectsState.diagnosticsEnabled && diagnosticsSnapshot ? (
                <details style={detailsStyle}>
                  <summary style={summaryStyle}>Runtime snapshot</summary>
                  <pre style={diagnosticsPreStyle}>
                    {JSON.stringify(diagnosticsSnapshot, null, 2)}
                  </pre>
                </details>
              ) : null}
            </div>
          ) : null}
        </div>
      ),
    };
  },
};

const panelBodyStyle: CSSProperties = {
  display: "flex",
  flexDirection: "column",
  gap: 12,
};

const panelEyebrowStyle: CSSProperties = {
  color: "#8ea4be",
  fontSize: 11,
  fontWeight: 700,
  letterSpacing: "0.08em",
  textTransform: "uppercase",
};

const sectionStyle: CSSProperties = {
  display: "flex",
  flexDirection: "column",
  gap: 8,
  padding: "10px 12px",
  borderRadius: 14,
  border: "1px solid rgba(255,255,255,0.06)",
  background: "rgba(255,255,255,0.025)",
};

const sectionTitleStyle: CSSProperties = {
  color: "#dce9f8",
  fontSize: 12,
  fontWeight: 700,
};

const toggleRowStyle: CSSProperties = {
  display: "flex",
  alignItems: "center",
  gap: 12,
  padding: "8px 0",
};

const rowTitleStyle: CSSProperties = {
  color: "#f3f7fd",
  fontSize: 13,
  fontWeight: 600,
};

const rowDescriptionStyle: CSSProperties = {
  color: "#a1b7cf",
  fontSize: 12,
  lineHeight: 1.45,
};

const rowMetaStyle: CSSProperties = {
  color: "#7fc6ff",
  fontSize: 11,
  lineHeight: 1.45,
};

const toggleButtonStyle: CSSProperties = {
  minWidth: 52,
  padding: "8px 10px",
  borderRadius: 999,
  border: "1px solid rgba(255,255,255,0.08)",
  background: "rgba(255,255,255,0.03)",
  color: "#cfe0f4",
  fontSize: 12,
  fontWeight: 700,
  cursor: "pointer",
};

const toggleButtonActiveStyle: CSSProperties = {
  ...toggleButtonStyle,
  background: "rgba(31, 111, 235, 0.24)",
  border: "1px solid rgba(127, 208, 255, 0.28)",
  color: "#eef6ff",
};

const legendRowStyle: CSSProperties = {
  display: "flex",
  alignItems: "center",
  gap: 10,
  padding: "8px 10px",
  borderRadius: 12,
  border: "1px solid rgba(255,255,255,0.06)",
  background: "rgba(255,255,255,0.025)",
};

const legendSwatchStyle: CSSProperties = {
  width: 10,
  height: 10,
  borderRadius: 999,
  flexShrink: 0,
};

const detailsStyle: CSSProperties = {
  borderRadius: 12,
  border: "1px solid rgba(255,255,255,0.05)",
  background: "rgba(0,0,0,0.14)",
  overflow: "hidden",
};

const summaryStyle: CSSProperties = {
  cursor: "pointer",
  padding: "10px 12px",
  color: "#c6d4e3",
  fontSize: 12,
  fontWeight: 700,
  letterSpacing: "0.04em",
  textTransform: "uppercase",
};

const diagnosticsPreStyle: CSSProperties = {
  margin: 0,
  padding: "0 12px 12px",
  color: "#dce9f8",
  fontSize: 11,
  lineHeight: 1.55,
  whiteSpace: "pre-wrap",
  wordBreak: "break-word",
};

const emptyTextStyle: CSSProperties = {
  color: "#8ea4be",
  fontSize: 12,
  lineHeight: 1.5,
};
