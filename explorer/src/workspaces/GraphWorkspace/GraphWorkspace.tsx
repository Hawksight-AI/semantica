import { useCallback, useEffect, useMemo, useRef, useState, type ComponentType, type ReactNode } from "react";
import {
  Activity,
  Clock3,
  Eye,
  Focus,
  GitBranch,
  Layers3,
  Maximize2,
  Pause,
  Play,
  RefreshCw,
  Search,
  Users,
  ZoomIn,
  ZoomOut,
} from "lucide-react";

import type Graph from "graphology";
import { batchMergeEdges, batchMergeNodes, graph } from "../../store/graphStore";
import { logEvent } from "../../store/registryStore";
import type { EdgeAttributes, NodeAttributes } from "../../store/graphStore";
import { curveGroupForPair } from "../../store/edgePairKeys.js";
import { InspectorPanel, MetricChip, SurfaceCard } from "../../ui/primitives";
import { lazy, Suspense } from "react";
import { SigmaSceneAdapter } from "./SigmaSceneAdapter";
import { useLoadGraph, useReloadGraph } from "./useLoadGraph";
import { GraphLoadingOverlay } from "./GraphLoadingOverlay";
import { createGraphLoadProgress, getGraphLoadTitle } from "./graphLoading";
import { GRAPH_THEME, withAlpha } from "./graphTheme";
import type { GraphEntityShapeVariant } from "./graphTheme";
import { buildHeatmapRenderSnapshot, buildStructuralDistanceSnapshot, checkGroupedViewAvailability, getDistanceBandColor, resolveDisplayGraph, resolveDisplayStateSnapshot, resolveGroupedDisplayNodeId, resolveGroupedDisplayStateSnapshot, summarizeDistanceBuckets } from "./graphSceneState";
import {
  type GraphPlugin,
  type GraphPluginActionRequest,
  type GraphPluginContext,
  type GraphPluginOverlayDescriptor,
  type GraphPluginPanelDescriptor,
  type GraphPluginToolbarItem,
} from "./plugins";
import type { LinkPrediction, PathResponse } from "./GraphInspectorPanel";
import type { GraphSceneHandle, GraphSceneRuntime } from "./scene";
import type {
  GraphAnalyticsSnapshot,
  GraphDistanceVisualMode,
  GraphDistanceVisualState,
  GraphDisplayStateSnapshot,
  GraphDiagnosticsSnapshot,
  GraphEffectToggle,
  GraphEffectsState,
  GraphInteractionState,
  GraphLoadProgress,
  GraphLoadSummary,
  GraphRuntimeDiagnosticsSnapshot,
  GraphSelectedEdgeState,
  GraphSelectedNodeKind,
  GraphSelectedNodeState,
  GraphTemporalState,
  GraphViewMode,
} from "./types";

type SearchResult = {
  node: {
    id: string;
    type: string;
    content: string;
    properties: Record<string, unknown>;
  };
  score: number;
};

type TemporalBounds = {
  min?: string | null;
  max?: string | null;
};

type ExploreLayoutState = {
  showInspector: boolean;
  showPluginDock: boolean;
};

type ToolbarIconComponent = ComponentType<{
  size?: number;
  strokeWidth?: number;
  "aria-hidden"?: boolean;
}>;

type GraphToolbarItem = {
  id: string;
  label: string;
  title?: string;
  active?: boolean;
  disabled?: boolean;
  tone?: "primary" | "secondary";
  icon?: ToolbarIconComponent;
  ariaLabel?: string;
  compact?: boolean;
  onClick: () => void;
};

type GraphToolbarGroup = {
  id: string;
  label?: string;
  variant?: "cluster" | "segmented";
  items: GraphToolbarItem[];
};

type SemanticNeighborhoodResponse = {
  anchor_node: string;
  total: number;
  neighbors: Array<{
    id: string;
    type: string;
    content: string;
    similarity: number;
    hop_distance?: number | null;
  }>;
};

type LazyPluginRegistryEntry = {
  id: string;
  panelId: string;
  label: string;
  title: string;
  order: number;
  load: () => Promise<GraphPlugin>;
  shouldLoad: (context: {
    panelState: Record<string, boolean>;
    temporalState: GraphTemporalState | null;
  }) => boolean;
};

const PROVENANCE_KEYS = ["source", "source_url", "pmid", "pmids", "evidence", "provenance", "confidence"] as const;
const EMPTY_DISTANCE_RECORD: Record<string, number> = {};
const STRUCTURAL_DISTANCE_MAX_HOPS = 6;
const HEATMAP_DISTANCE_MAX_HOPS = 3;
const DEFAULT_EFFECTS_STATE: GraphEffectsState = {
  pathPulseEnabled: false,
  pathFlowEnabled: false,
  lensEnabled: false,
  temporalEmphasisEnabled: false,
  semanticRegionsEnabled: false,
  contoursEnabled: false,
  pathfindingEnabled: false,
  communitiesEnabled: false,
  centralityEnabled: false,
  legendEnabled: false,
  diagnosticsEnabled: false,
  lensMode: "neighborhood",
  effectQuality: "bounded",
};
const LazyTimelinePanel = lazy(() => import("./TimelinePanel").then((module) => ({ default: module.TimelinePanel })));
const LazyGraphInspectorPanel = lazy(() => import("./GraphInspectorPanel").then((module) => ({ default: module.GraphInspectorPanel })));

const loadExplorationEffectsPlugin = () => import("./plugins/explorationEffectsPluginPhaseC").then((module) => module.explorationEffectsPluginPhaseC);
const loadNeighborhoodPanelPlugin = () => import("./plugins/neighborhoodPanelPlugin").then((module) => module.neighborhoodPanelPlugin);
const loadTemporalOverlayPlugin = () => import("./plugins/temporalOverlayPlugin").then((module) => module.temporalOverlayPlugin);
const EMPTY_PATH: string[] = [];
const COMPACT_TOOLBAR_CLUSTER_IDS = new Set(["camera", "utility"]);
const ENTITY_VISUAL_KEY: Array<{ shape: GraphEntityShapeVariant; label: string }> = [
  { shape: "biomolecule", label: "Biomolecule" },
  { shape: "condition", label: "Condition" },
  { shape: "compound", label: "Compound" },
  { shape: "process", label: "Process" },
  { shape: "community", label: "Community" },
  { shape: "entity", label: "Other" },
];
const DEBUG_GRAPH_WORKSPACE = import.meta.env.DEV;

function debugGraphWorkspace(message: string, payload?: Record<string, unknown>) {
  if (!DEBUG_GRAPH_WORKSPACE) {
    return;
  }
  console.debug(`[GraphWorkspace] ${message}`, payload ?? {});
}

function getGraphSummarySignature(summary: GraphLoadSummary): string {
  return [
    summary.nodeCount,
    summary.edgeCount,
    summary.layoutSource ?? "unknown",
    summary.layoutReady ? "ready" : "runtime",
    summary.loadTimeMs,
  ].join(":");
}

function useDebounce<T>(value: T, delay: number): T {
  const [debouncedValue, setDebouncedValue] = useState<T>(value);
  useEffect(() => {
    const timeout = setTimeout(() => setDebouncedValue(value), delay);
    return () => clearTimeout(timeout);
  }, [delay, value]);
  return debouncedValue;
}

function iconForPluginToolbarItem(item: GraphPluginToolbarItem): ToolbarIconComponent {
  const normalized = `${item.id} ${item.label}`.toLowerCase();
  if (normalized.includes("neighbor")) {
    return Users;
  }
  if (normalized.includes("temporal") || normalized.includes("time")) {
    return Clock3;
  }
  return Activity;
}

function ToolbarIcon({ icon: Icon, size = 15 }: { icon?: ToolbarIconComponent; size?: number }) {
  if (!Icon) {
    return null;
  }

  return <Icon size={size} strokeWidth={2.15} aria-hidden />;
}

function ToolbarButton({
  item,
  compact = false,
  className = "",
}: {
  item: GraphToolbarItem;
  compact?: boolean;
  className?: string;
}) {
  const isCompact = compact || item.compact;
  return (
    <button
      type="button"
      className={`explore-tool-button ${item.tone === "primary" ? "explore-tool-button-primary" : ""} ${className}`}
      data-active={item.active ? "true" : "false"}
      data-compact={isCompact ? "true" : "false"}
      onClick={item.onClick}
      title={item.title}
      aria-label={item.ariaLabel ?? item.label}
      disabled={item.disabled}
    >
      <ToolbarIcon icon={item.icon} size={isCompact ? 14 : 15} />
      <span className="explore-tool-button-label">{item.label}</span>
    </button>
  );
}

function ToolbarCluster({
  label,
  items,
  compact = false,
  children,
}: {
  label: string;
  items?: GraphToolbarItem[];
  compact?: boolean;
  children?: ReactNode;
}) {
  if ((!items || items.length === 0) && !children) {
    return null;
  }

  return (
    <div className="explore-tool-cluster" aria-label={label}>
      <div className="explore-tool-cluster-label">{label}</div>
      <div className="explore-tool-cluster-items">
        {children}
        {items?.map((item) => (
          <ToolbarButton key={item.id} item={item} compact={compact} />
        ))}
      </div>
    </div>
  );
}

function SegmentedModeControl({ items }: { items: GraphToolbarItem[] }) {
  if (!items.length) {
    return null;
  }

  return (
    <div className="explore-mode-control" role="group" aria-label="Graph view mode">
      {items.map((item) => (
        <ToolbarButton key={item.id} item={item} className="explore-mode-segment" />
      ))}
    </div>
  );
}

function SearchCommandBar({
  value,
  disabled,
  onChange,
  onSubmit,
}: {
  value: string;
  disabled: boolean;
  onChange: (value: string) => void;
  onSubmit: () => void;
}) {
  return (
    <form
      className="explore-search-command"
      onSubmit={(event) => {
        event.preventDefault();
        if (!disabled) {
          onSubmit();
        }
      }}
    >
      <Search size={17} strokeWidth={2.15} aria-hidden />
      <input
        value={value}
        onChange={(event) => onChange(event.target.value)}
        placeholder="Search command, node, or concept"
        aria-label="Search graph nodes"
      />
      <button type="submit" disabled={disabled} aria-label="Search for the current query">
        Search
      </button>
    </form>
  );
}

function EntityVisualKey() {
  return (
    <div className="explore-entity-key" aria-label="Node visual key">
      {ENTITY_VISUAL_KEY.map((item) => (
        <div key={item.shape} className="explore-entity-key-item">
          <span className="explore-entity-key-mark" data-shape={item.shape} />
          <span>{item.label}</span>
        </div>
      ))}
    </div>
  );
}

const HUD_CSS = `
  .palantir-bg {
    background:
      ${GRAPH_THEME.ui.scene.radialGlow},
      ${GRAPH_THEME.ui.scene.background};
  }
  .palantir-grid {
    position: absolute;
    inset: 0;
    background-image:
      linear-gradient(${GRAPH_THEME.ui.scene.grid} 1px, transparent 1px),
      linear-gradient(90deg, ${GRAPH_THEME.ui.scene.grid} 1px, transparent 1px),
      linear-gradient(${GRAPH_THEME.ui.scene.gridStrong} 1px, transparent 1px),
      linear-gradient(90deg, ${GRAPH_THEME.ui.scene.gridStrong} 1px, transparent 1px);
    background-size: 48px 48px, 48px 48px, 240px 240px, 240px 240px;
    pointer-events: none;
    z-index: 1;
  }
  .palantir-vignette {
    position: absolute;
    inset: 0;
    background: ${GRAPH_THEME.ui.scene.vignette};
    pointer-events: none;
    z-index: 2;
  }
  .glass-header {
    background: ${GRAPH_THEME.ui.surface.cardSubtle};
    border-bottom: 1px solid ${GRAPH_THEME.ui.surface.panelBorder};
    backdrop-filter: blur(12px);
    -webkit-backdrop-filter: blur(12px);
  }
  .glass-hud {
    background: ${GRAPH_THEME.ui.surface.panel};
    backdrop-filter: blur(14px) saturate(1.08);
    -webkit-backdrop-filter: blur(14px) saturate(1.08);
    border-left: 1px solid ${GRAPH_THEME.ui.surface.panelBorder};
    box-shadow: ${GRAPH_THEME.ui.surface.shadow};
  }
  .hud-scrollbar::-webkit-scrollbar { width: 6px; }
  .hud-scrollbar::-webkit-scrollbar-track { background: transparent; }
  .hud-scrollbar::-webkit-scrollbar-thumb { background: rgba(215, 209, 196, 0.22); border-radius: 6px; }
  .node-panel-collapse {
    border: 1px solid ${GRAPH_THEME.ui.surface.panelBorder};
    border-radius: 12px;
    background: rgba(255, 255, 255, 0.026);
    overflow: hidden;
  }
  .node-panel-collapse + .node-panel-collapse {
    margin-top: 12px;
  }
  .node-panel-summary {
    list-style: none;
    cursor: pointer;
    display: flex;
    align-items: center;
    justify-content: space-between;
    gap: 12px;
    padding: 12px 14px;
    color: ${GRAPH_THEME.ui.text.body};
    font-size: 12px;
    font-weight: 700;
    letter-spacing: 0.04em;
    text-transform: uppercase;
  }
  .node-panel-summary::-webkit-details-marker {
    display: none;
  }
  .node-panel-summary::after {
    content: "+";
    color: ${GRAPH_THEME.ui.timeline.playhead};
    font-size: 16px;
    line-height: 1;
  }
  .node-panel-collapse[open] .node-panel-summary::after {
    content: "−";
  }
  .node-panel-body {
    padding: 0 14px 14px;
  }
  .graph-loading-overlay {
    position: absolute;
    inset: 0;
    z-index: 9;
    display: flex;
    align-items: center;
    justify-content: center;
    pointer-events: none;
  }
  .graph-loading-card {
    width: min(460px, calc(100% - 48px));
    border-radius: 20px;
    padding: 22px 22px 18px;
    background: ${GRAPH_THEME.ui.surface.cardStrong};
    border: 1px solid ${GRAPH_THEME.ui.surface.panelBorder};
    box-shadow: ${GRAPH_THEME.ui.surface.shadow};
    backdrop-filter: blur(18px);
    -webkit-backdrop-filter: blur(18px);
  }
  .graph-loading-dots {
    display: inline-flex;
    gap: 8px;
    align-items: center;
  }
  .graph-loading-dot {
    width: 10px;
    height: 10px;
    border-radius: 999px;
    background: linear-gradient(135deg, ${GRAPH_THEME.ui.timeline.playhead}, ${GRAPH_THEME.palette.accent.selected});
    box-shadow: 0 0 18px rgba(98, 226, 205, 0.28);
    animation: sem-loader-pulse 1.2s ease-in-out infinite;
  }
  .graph-loading-dot:nth-child(2) {
    animation-delay: 0.14s;
  }
  .graph-loading-dot:nth-child(3) {
    animation-delay: 0.28s;
  }
  @keyframes sem-loader-pulse {
    0%, 100% {
      transform: translateY(0) scale(0.92);
      opacity: 0.55;
    }
    50% {
      transform: translateY(-4px) scale(1.08);
      opacity: 1;
    }
  }
  .graph-loading-bar {
    width: 100%;
    height: 10px;
    border-radius: 999px;
    overflow: hidden;
    background: rgba(255, 255, 255, 0.052);
    border: 1px solid ${GRAPH_THEME.ui.surface.panelBorder};
  }
  .graph-loading-bar > span {
    display: block;
    height: 100%;
    border-radius: 999px;
    background: linear-gradient(90deg, rgba(98, 226, 205, 0.9), rgba(233, 196, 122, 0.9));
    box-shadow: 0 0 28px rgba(98, 226, 205, 0.22);
    transition: width 180ms ease;
  }
  .explore-shell {
    position: relative;
    width: 100%;
    height: 100%;
    overflow: hidden;
    padding: 12px;
    display: flex;
    flex-direction: column;
    gap: 10px;
  }
  .explore-command-deck {
    position: relative;
    z-index: 3;
  }
  .explore-command-grid {
    display: grid;
    grid-template-columns: minmax(260px, 0.9fr) minmax(0, 1.4fr);
    gap: 16px;
  }
  .explore-main-grid {
    position: relative;
    z-index: 3;
    min-height: 0;
    flex: 1;
    display: grid;
    grid-template-columns: minmax(0, 1fr) minmax(340px, 380px);
    gap: 12px;
  }
  .explore-scene-stack {
    min-height: 0;
    display: flex;
    flex-direction: column;
    gap: 14px;
  }
  .explore-scene-card {
    min-height: 0;
    flex: 1;
    display: flex;
    flex-direction: column;
    overflow: hidden;
  }
  .explore-scene-shell {
    position: relative;
    min-height: 0;
    flex: 1;
    overflow: hidden;
    border-radius: 20px 20px 0 0;
    background: ${GRAPH_THEME.ui.surface.stage};
  }
  .explore-scene-stage {
    position: relative;
    z-index: 3;
    width: 100%;
    height: 100%;
  }
  .explore-scene-footer {
    position: relative;
    z-index: 3;
    border-top: 1px solid ${GRAPH_THEME.ui.timeline.border};
    background: ${GRAPH_THEME.ui.timeline.background};
  }
  .explore-plugin-dock {
    position: relative;
    z-index: 3;
  }
  .explore-plugin-dock-tabs {
    display: flex;
    align-items: center;
    gap: 6px;
    flex-wrap: wrap;
  }
  .explore-plugin-dock-tab {
    border: 1px solid ${GRAPH_THEME.ui.control.defaultBorder};
    background: ${GRAPH_THEME.ui.control.defaultBg};
    color: ${GRAPH_THEME.ui.control.defaultText};
    border-radius: 999px;
    padding: 6px 10px;
    font-size: 11px;
    font-weight: 600;
    cursor: pointer;
  }
  .explore-plugin-dock-tab[data-active="true"] {
    color: ${GRAPH_THEME.ui.control.activeText};
    background: rgba(74, 181, 166, 0.18);
    border-color: ${GRAPH_THEME.ui.control.activeBorder};
  }
  .explore-toolbar {
    display: flex;
    flex-direction: column;
    gap: 12px;
  }
  .explore-status-strip {
    display: flex;
    align-items: center;
    gap: 7px;
    flex-wrap: wrap;
  }
  .explore-workflow-bar {
    display: grid;
    grid-template-columns: minmax(280px, 1.1fr) auto minmax(360px, 1.55fr);
    align-items: center;
    gap: 10px;
  }
  .explore-search-command {
    min-width: 0;
    height: 43px;
    display: grid;
    grid-template-columns: auto minmax(0, 1fr) auto;
    align-items: center;
    gap: 9px;
    padding: 4px 5px 4px 13px;
    border-radius: 16px;
    border: 1px solid ${GRAPH_THEME.ui.control.inputBorder};
    background:
      linear-gradient(135deg, rgba(255,255,255,0.06), rgba(255,255,255,0.018)),
      ${GRAPH_THEME.ui.control.inputBg};
    color: ${GRAPH_THEME.ui.text.muted};
    box-shadow: inset 0 1px 0 rgba(255,255,255,0.045), 0 14px 30px rgba(0,0,0,0.16);
  }
  .explore-search-command:focus-within {
    border-color: ${GRAPH_THEME.ui.control.activeBorder};
    box-shadow: inset 0 1px 0 rgba(255,255,255,0.06), 0 0 0 1px ${GRAPH_THEME.ui.control.focusRing}, 0 16px 32px rgba(0,0,0,0.18);
  }
  .explore-search-command input {
    width: 100%;
    min-width: 0;
    border: 0;
    outline: 0;
    color: ${GRAPH_THEME.ui.text.strong};
    background: transparent;
    font-size: 13px;
  }
  .explore-search-command input::placeholder {
    color: ${GRAPH_THEME.ui.text.subtle};
  }
  .explore-search-command button {
    height: 33px;
    border: 1px solid ${GRAPH_THEME.ui.control.primaryBorder};
    border-radius: 12px;
    padding: 0 13px;
    background: ${GRAPH_THEME.ui.control.primaryBg};
    color: ${GRAPH_THEME.ui.control.primaryText};
    font-size: 12px;
    font-weight: 800;
    cursor: pointer;
    box-shadow: inset 0 1px 0 rgba(255,255,255,0.08);
  }
  .explore-search-command button:disabled {
    cursor: not-allowed;
    opacity: 0.45;
  }
  .explore-mode-control {
    display: inline-grid;
    grid-template-columns: repeat(3, minmax(88px, auto));
    align-items: center;
    padding: 4px;
    border-radius: 16px;
    border: 1px solid ${GRAPH_THEME.ui.control.defaultBorder};
    background: rgba(255, 255, 255, 0.026);
    box-shadow: inset 0 1px 0 rgba(255,255,255,0.035);
  }
  .explore-mode-segment {
    min-width: 0;
    border-radius: 12px;
  }
  .explore-toolbelt {
    min-width: 0;
    display: flex;
    justify-content: flex-end;
    align-items: center;
    gap: 8px;
    flex-wrap: wrap;
  }
  .explore-tool-cluster {
    display: inline-flex;
    align-items: center;
    gap: 6px;
    min-height: 43px;
    padding: 4px;
    border-radius: 16px;
    border: 1px solid rgba(211, 205, 190, 0.075);
    background: rgba(255, 255, 255, 0.022);
  }
  .explore-tool-cluster-label {
    padding: 0 4px 0 7px;
    color: ${GRAPH_THEME.ui.text.subtle};
    font-size: 10px;
    font-weight: 800;
    letter-spacing: 0.08em;
    text-transform: uppercase;
    white-space: nowrap;
  }
  .explore-tool-cluster-items {
    display: inline-flex;
    align-items: center;
    gap: 4px;
    flex-wrap: wrap;
  }
  .explore-tool-button {
    min-height: 33px;
    display: inline-flex;
    align-items: center;
    justify-content: center;
    gap: 7px;
    border: 1px solid ${GRAPH_THEME.ui.control.defaultBorder};
    border-radius: 12px;
    padding: 7px 10px;
    background: ${GRAPH_THEME.ui.control.defaultBg};
    color: ${GRAPH_THEME.ui.control.defaultText};
    font-size: 12px;
    font-weight: 700;
    line-height: 1;
    cursor: pointer;
    white-space: nowrap;
    box-shadow: inset 0 1px 0 rgba(255,255,255,0.035);
    transition: background 140ms ease, border-color 140ms ease, color 140ms ease, transform 140ms ease;
  }
  .explore-tool-button:hover:not(:disabled) {
    background: ${GRAPH_THEME.ui.control.hoverBg};
    border-color: rgba(211, 205, 190, 0.18);
    transform: translateY(-1px);
  }
  .explore-tool-button:disabled {
    cursor: not-allowed;
    color: ${GRAPH_THEME.ui.control.disabledText};
    opacity: 0.48;
    transform: none;
  }
  .explore-tool-button[data-active="true"] {
    color: ${GRAPH_THEME.ui.control.activeText};
    background: ${GRAPH_THEME.ui.control.activeBg};
    border-color: ${GRAPH_THEME.ui.control.activeBorder};
    box-shadow: 0 0 0 1px ${GRAPH_THEME.ui.control.focusRing}, inset 0 1px 0 rgba(255,255,255,0.06);
  }
  .explore-tool-button-primary {
    color: ${GRAPH_THEME.ui.control.primaryText};
    background: ${GRAPH_THEME.ui.control.primaryBg};
    border-color: ${GRAPH_THEME.ui.control.primaryBorder};
  }
  .explore-tool-button[data-compact="true"] {
    min-width: 34px;
    padding-inline: 9px;
  }
  .explore-tool-button[data-compact="true"] .explore-tool-button-label {
    display: none;
  }
  .explore-entity-key {
    display: flex;
    align-items: center;
    gap: 10px;
    flex-wrap: wrap;
    padding: 2px 1px 0;
    color: ${GRAPH_THEME.ui.text.subtle};
    font-size: 10px;
    font-weight: 700;
    letter-spacing: 0.02em;
  }
  .explore-entity-key-item {
    display: inline-flex;
    align-items: center;
    gap: 6px;
    white-space: nowrap;
  }
  .explore-entity-key-mark {
    width: 13px;
    height: 13px;
    display: inline-block;
    border: 1px solid rgba(194, 214, 218, 0.42);
    background: rgba(73, 154, 150, 0.58);
    box-shadow: inset 0 1px 0 rgba(255,255,255,0.08);
  }
  .explore-entity-key-mark[data-shape="entity"] {
    border-radius: 999px;
  }
  .explore-entity-key-mark[data-shape="biomolecule"] {
    clip-path: polygon(50% 7%, 86% 28%, 86% 72%, 50% 93%, 14% 72%, 14% 28%);
  }
  .explore-entity-key-mark[data-shape="condition"] {
    border-radius: 5px;
    transform: rotate(45deg) scale(0.88);
  }
  .explore-entity-key-mark[data-shape="compound"] {
    width: 20px;
    border-radius: 999px;
  }
  .explore-entity-key-mark[data-shape="process"] {
    border-radius: 4px;
    clip-path: polygon(0 0, 86% 0, 100% 16%, 100% 100%, 0 100%);
  }
  .explore-entity-key-mark[data-shape="community"] {
    width: 15px;
    height: 15px;
    border-radius: 999px;
    background: rgba(96, 190, 180, 0.16);
    border-color: rgba(229, 213, 175, 0.54);
  }
  .explore-search-results {
    display: flex;
    flex-direction: column;
    gap: 8px;
    max-height: 260px;
    overflow-y: auto;
    padding-right: 4px;
  }
  .explore-inspector-shell {
    min-height: 0;
    display: flex;
    flex-direction: column;
  }
  .explore-inspector-card {
    min-height: 0;
    flex: 1;
    overflow: hidden;
  }
  .explore-inspector-scroll {
    height: 100%;
    overflow-y: auto;
  }
  @media (max-width: 1260px) {
    .explore-main-grid {
      grid-template-columns: 1fr;
    }
    .explore-workflow-bar {
      grid-template-columns: minmax(280px, 1fr) auto;
    }
    .explore-toolbelt {
      grid-column: 1 / -1;
      justify-content: flex-start;
    }
  }
  @media (max-width: 980px) {
    .explore-shell {
      padding: 10px;
      gap: 10px;
    }
    .explore-command-grid {
      grid-template-columns: 1fr;
    }
    .explore-workflow-bar {
      grid-template-columns: 1fr;
    }
    .explore-mode-control {
      width: 100%;
      grid-template-columns: repeat(3, minmax(0, 1fr));
    }
    .explore-toolbelt {
      justify-content: flex-start;
    }
    .explore-tool-cluster {
      max-width: 100%;
    }
  }
`;

function getProvenanceCount(properties: Record<string, unknown>) {
  return PROVENANCE_KEYS.reduce(
    (count, key) => (properties[key] !== undefined && properties[key] !== null ? count + 1 : count),
    0,
  );
}

function buildRealtimeNodeAttributes(payload: {
  id: string;
  type?: string;
  properties?: Record<string, unknown>;
}): NodeAttributes {
  const properties = payload.properties || {};
  const label = String(properties.content || payload.id);
  const baseColor = GRAPH_THEME.palette.accent.path;
  const hasTemporalBounds = Boolean(properties.valid_from || properties.valid_until);
  const provenanceCount = getProvenanceCount(properties);

  return {
    label,
    x: Number(properties.x ?? Math.random() * 1000 - 500),
    y: Number(properties.y ?? Math.random() * 1000 - 500),
    nodeType: payload.type || "inferred",
    content: label,
    valid_from: (properties.valid_from as string | null | undefined) ?? null,
    valid_until: (properties.valid_until as string | null | undefined) ?? null,
    properties,
    size: 8,
    baseSize: 8,
    semanticGroup: payload.type || "inferred",
    color: baseColor,
    baseColor,
    mutedColor: withAlpha(baseColor, GRAPH_THEME.nodes.mutedAlpha),
    glowColor: withAlpha(baseColor, 0.36),
    visualPriority: 0.82,
    labelPriority: 0.82,
    strokeColor: GRAPH_THEME.palette.background.nodeBorder,
    borderColor: GRAPH_THEME.palette.background.nodeBorder,
    borderSize: 0.85,
    nodeVariant: "inferred",
    nodeShapeVariant: "inferred",
    badgeKind: hasTemporalBounds ? "temporal" : provenanceCount > 0 ? "provenance" : "inferred",
    badgeCount: provenanceCount || undefined,
    ringColor: GRAPH_THEME.nodes.selectedRing.color,
    haloColor: withAlpha(baseColor, 0.42),
    labelVisibilityPolicy: "local",
  };
}

function buildRealtimeEdgeAttributes(payload: {
  id: string;
  familyId?: string;
  source_id: string;
  target_id: string;
  type?: string;
  weight?: number;
  properties?: Record<string, unknown>;
}): EdgeAttributes {
  const properties = payload.properties || {};
  const isInferred = Boolean(properties.inferred);
  const isBidirectional = graph.hasDirectedEdge(payload.target_id, payload.source_id);
  const baseColor = isInferred ? GRAPH_THEME.palette.accent.path : GRAPH_THEME.palette.muted.edgeStructure;

  return {
    edgeId: payload.id,
    familyId: payload.familyId || payload.id,
    sourceId: payload.source_id,
    targetId: payload.target_id,
    weight: Number(payload.weight ?? 1),
    edgeType: payload.type || "related_to",
    properties,
    size: 1,
    baseSize: 1,
    color: baseColor,
    baseColor,
    mutedColor: GRAPH_THEME.palette.muted.edgeOverview,
    visualPriority: isInferred ? 0.95 : 0.5,
    isBidirectional,
    edgeFamily: isInferred ? "path" : isBidirectional ? "bidirectional" : "line",
    curveGroup: isBidirectional ? curveGroupForPair(payload.source_id, payload.target_id) : null,
    type: "line",
    edgeVariant: isInferred ? "pathSignal" : isBidirectional ? "bidirectionalCurve" : "directional",
    arrowVisibilityPolicy: isInferred ? "always" : "contextual",
    relationshipStrength: isInferred ? 0.95 : 0.52,
    isParallelPair: false,
    parallelIndex: 0,
    parallelCount: 1,
    familySize: 1,
  };
}

function buildSelectedNodeState(
  nodeId: string,
  displayState: GraphDisplayStateSnapshot,
): GraphSelectedNodeState | null {
  if (!nodeId || !graph.hasNode(nodeId)) {
    return null;
  }

  const attributes = graph.getNodeAttributes(nodeId) as {
    label?: string;
    content?: string;
    nodeType?: string;
    color?: string;
    valid_from?: string | null;
    valid_until?: string | null;
    properties?: Record<string, unknown>;
  };

  return {
    id: nodeId,
    label: String(attributes.label ?? nodeId),
    content: String(attributes.content ?? attributes.label ?? nodeId),
    nodeType: String(attributes.nodeType ?? "Entity"),
    color: typeof attributes.color === "string" ? attributes.color : undefined,
    valid_from: attributes.valid_from ?? null,
    valid_until: attributes.valid_until ?? null,
    properties: attributes.properties ?? {},
    neighborCount: graph.neighbors(nodeId).length,
    visibleNeighborCount: displayState.selectedVisibleNeighborIds.length,
    collapsedNeighborCount: displayState.selectedCollapsedNeighborIds.length,
    isNeighborhoodCollapsed: displayState.selectedCollapsedNeighborIds.length > 0,
    canCollapseNeighborhood: graph.neighbors(nodeId).length > 8,
  };
}

type FocusResolution = {
  kind: GraphSelectedNodeKind;
  resolvedNodeId: string | null;
  reason: string | null;
};

function buildSelectedEdgeState(
  edgeId: string,
  displayGraph: typeof graph | Graph<NodeAttributes, EdgeAttributes>,
): GraphSelectedEdgeState | null {
  if (!edgeId || !displayGraph.hasEdge(edgeId)) {
    return null;
  }

  const [displaySourceId, displayTargetId] = displayGraph.extremities(edgeId);
  const attributes = displayGraph.getEdgeAttributes(edgeId) as {
    edgeType?: string;
    weight?: number;
    properties?: Record<string, unknown>;
    familyId?: string;
    rawEdgeIds?: string[];
    isAggregated?: boolean;
    aggregateCount?: number;
    bundleKind?: "parallel" | "bidirectional" | "community";
    dominantEdgeType?: string;
    representativeWeight?: number;
  };
  const rawEdgeIds = attributes.rawEdgeIds?.length ? attributes.rawEdgeIds.map((rawEdgeId) => String(rawEdgeId)) : [edgeId];
  const primaryRawEdgeId = rawEdgeIds.find((rawEdgeId) => graph.hasEdge(rawEdgeId)) ?? rawEdgeIds[0];
  let sourceId = displaySourceId;
  let targetId = displayTargetId;
  if (primaryRawEdgeId && graph.hasEdge(primaryRawEdgeId)) {
    [sourceId, targetId] = graph.extremities(primaryRawEdgeId);
  }
  const sourceAttributes = graph.hasNode(sourceId)
    ? (graph.getNodeAttributes(sourceId) as { label?: string; content?: string })
    : ({ label: displaySourceId } as { label?: string; content?: string });
  const targetAttributes = graph.hasNode(targetId)
    ? (graph.getNodeAttributes(targetId) as { label?: string; content?: string })
    : ({ label: displayTargetId } as { label?: string; content?: string });
  const properties = attributes.properties ?? {};
  const familyId = String(attributes.familyId || edgeId);
  let familySize = 0;
  let siblingCount = 0;
  rawEdgeIds.forEach((rawEdgeId) => {
    if (!graph.hasEdge(rawEdgeId)) {
      return;
    }
    const candidateAttrs = graph.getEdgeAttributes(rawEdgeId) as { familyId?: string };
    const [candidateSource, candidateTarget] = graph.extremities(rawEdgeId);
    if (String(candidateAttrs.familyId || rawEdgeId) === familyId) {
      familySize += 1;
    }
    if (candidateSource === sourceId && candidateTarget === targetId) {
      siblingCount += 1;
    }
  });

  if (attributes.isAggregated) {
    siblingCount = rawEdgeIds.filter((rawEdgeId) => graph.hasEdge(rawEdgeId)).length;
    familySize = Math.max(familySize, siblingCount);
  }

  return {
    id: edgeId,
    familyId,
    sourceId,
    sourceLabel: String(sourceAttributes.label ?? sourceAttributes.content ?? sourceId),
    targetId,
    targetLabel: String(targetAttributes.label ?? targetAttributes.content ?? targetId),
    edgeType: String(attributes.edgeType ?? "related_to"),
    weight: Number(attributes.weight ?? 1),
    properties,
    provenanceCount: getProvenanceCount(properties),
    familySize,
    siblingCount,
    isAggregated: Boolean(attributes.isAggregated),
    aggregateCount: Number(attributes.aggregateCount ?? rawEdgeIds.length),
    rawEdgeIds,
    bundleKind: attributes.bundleKind ?? null,
    dominantEdgeType: attributes.dominantEdgeType ?? null,
    representativeWeight: Number(attributes.representativeWeight ?? attributes.weight ?? 1),
  };
}

function collectPluginPanels(
  plugins: GraphPlugin[],
  context: GraphPluginContext,
): GraphPluginPanelDescriptor[] {
  const panels: GraphPluginPanelDescriptor[] = [];

  for (const plugin of plugins) {
    try {
      const result = plugin.renderPanel?.(context);
      if (!result) {
        continue;
      }
      if (Array.isArray(result)) {
        panels.push(...result);
      } else {
        panels.push(result);
      }
    } catch (error) {
      console.error(`[GraphPlugin:${plugin.id}] panel render failed`, error);
    }
  }

  return panels.sort((left, right) => (left.order ?? 0) - (right.order ?? 0));
}

function collectPluginOverlays(
  plugins: GraphPlugin[],
  context: GraphPluginContext,
): GraphPluginOverlayDescriptor[] {
  const overlays: GraphPluginOverlayDescriptor[] = [];

  for (const plugin of plugins) {
    try {
      const result = plugin.renderOverlay?.(context);
      if (!result) {
        continue;
      }
      if (Array.isArray(result)) {
        overlays.push(...result);
      } else {
        overlays.push(result);
      }
    } catch (error) {
      console.error(`[GraphPlugin:${plugin.id}] overlay render failed`, error);
    }
  }

  return overlays.sort((left, right) => {
    if ((left.layer ?? 0) !== (right.layer ?? 0)) {
      return (left.layer ?? 0) - (right.layer ?? 0);
    }
    return (left.order ?? 0) - (right.order ?? 0);
  });
}

interface GraphWorkspaceProps {
  externalFocusNodeId?: string;
  externalFocusToken?: number;
}

export function GraphWorkspace({ externalFocusNodeId, externalFocusToken }: GraphWorkspaceProps = {}) {
  const [selectedNodeId, setSelectedNodeId] = useState("");
  const [focusedNodeId, setFocusedNodeId] = useState("");
  const [lastGroupedSelectedNodeId, setLastGroupedSelectedNodeId] = useState("");
  const [selectedEdgeId, setSelectedEdgeId] = useState("");
  const [isLayoutRunning, setIsLayoutRunning] = useState(false);
  const [graphReady, setGraphReady] = useState(false);
  const [graphVersion, setGraphVersion] = useState(0);
  const [viewMode, setViewMode] = useState<GraphViewMode>("full");
  const [aggregationEnabled] = useState(true);
  const [collapsedNeighborhoodNodeIds, setCollapsedNeighborhoodNodeIds] = useState<string[]>([]);
  const [searchQuery, setSearchQuery] = useState("");
  const [searchResults, setSearchResults] = useState<SearchResult[]>([]);
  const [searchError, setSearchError] = useState("");
  const [predictionType, setPredictionType] = useState("");
  const [isRunningPredictions, setIsRunningPredictions] = useState(false);
  const [predictions, setPredictions] = useState<LinkPrediction[]>([]);
  const [pathTargetId, setPathTargetId] = useState("");
  const [pathResult, setPathResult] = useState<PathResponse | null>(null);
  const [activeNodeCount, setActiveNodeCount] = useState<number | null>(null);
  const [temporalBounds, setTemporalBounds] = useState<TemporalBounds | null>(null);
  const [scrubberTime, setScrubberTime] = useState<Date | null>(null);
  const [loadingProgress, setLoadingProgress] = useState<GraphLoadProgress | null>(null);
  const [pluginPanelState, setPluginPanelState] = useState<Record<string, boolean>>({
    "effects-panel": false,
    "neighborhood-panel": false,
    "temporal-panel": false,
  });
  const [activeDockPanelId, setActiveDockPanelId] = useState<string | null>(null);
  const [pluginRuntimeVersion, setPluginRuntimeVersion] = useState(0);
  const [effectsState, setEffectsState] = useState<GraphEffectsState>(DEFAULT_EFFECTS_STATE);
  const [graphDiagnosticsState, setGraphDiagnosticsState] = useState<GraphRuntimeDiagnosticsSnapshot | null>(null);
  const [graphAnalyticsState, setGraphAnalyticsState] = useState<GraphAnalyticsSnapshot | null>(null);
  const [loadedPlugins, setLoadedPlugins] = useState<Record<string, GraphPlugin>>({});

  // FR-2: Egocentric depth-of-field
  const [egoModeEnabled, setEgoModeEnabled] = useState(false);
  const [egoMaxHops, setEgoMaxHops] = useState(3);
  // FR-3 frontend: Distance mode overlay
  const [distanceMode, setDistanceMode] = useState<"off" | "structural" | "semantic">("off");
  // FR-5: Distance heatmap layout
  const [heatmapEnabled, setHeatmapEnabled] = useState(false);
  const [semanticDistanceState, setSemanticDistanceState] = useState<{
    anchorNodeId: string | null;
    scores: Record<string, number>;
    count: number;
    status: GraphDistanceVisualState["status"];
    error: string | null;
  }>({
    anchorNodeId: null,
    scores: EMPTY_DISTANCE_RECORD,
    count: 0,
    status: "idle",
    error: null,
  });

  const debouncedTime = useDebounce(scrubberTime, 150);
  const prevActiveIdsRef = useRef<Set<string>>(new Set());
  const sceneRef = useRef<GraphSceneHandle>(null);
  const lastExternalFocusTokenRef = useRef<number | undefined>(undefined);
  const pluginRuntimeRef = useRef<GraphSceneRuntime | null>(null);
  const appliedGraphSummarySignatureRef = useRef<string | null>(null);
  const pluginInteractionStateRef = useRef<GraphInteractionState>({
    hoveredNodeId: null,
    selectedNodeId: "",
    selectedEdgeId: "",
    focusedNodeId: "",
    activePath: [],
    activePathEdgeIds: [],
    viewMode: "full",
    zoomTier: "overview",
    isLayoutRunning: false,
  });
  const reload = useReloadGraph();

  const handleLoadProgress = useCallback((progress: GraphLoadProgress) => {
    setLoadingProgress(progress);
    if (progress.phase !== "ready" && progress.phase !== "stabilizing_layout") {
      setGraphReady(false);
    }
  }, []);

  const applyGraphReadySummary = useCallback((graphSummary: GraphLoadSummary) => {
    const signature = getGraphSummarySignature(graphSummary);
    if (appliedGraphSummarySignatureRef.current === signature) {
      return;
    }

    appliedGraphSummarySignatureRef.current = signature;
    setGraphReady(true);
    setGraphVersion((current) => current + 1);
    setIsLayoutRunning(!graphSummary.layoutReady);

    if (graphSummary.layoutReady) {
      setLoadingProgress(null);
      return;
    }

    setLoadingProgress(createGraphLoadProgress({
      phase: "stabilizing_layout",
      progressKind: "indeterminate",
      nodesLoaded: graphSummary.nodeCount,
      nodesTotal: graphSummary.nodeCount,
      edgesLoaded: graphSummary.edgeCount,
      edgesTotal: graphSummary.edgeCount,
      message: "Settling runtime layout",
      showGraphBehind: true,
      layoutSource: graphSummary.layoutSource,
      layoutState: "bootstrapping",
    }));
  }, []);

  const { data: summary, isLoading, isFetching } = useLoadGraph({
    enabled: true,
    onGraphReady: applyGraphReadySummary,
    onProgress: handleLoadProgress,
  });

  useEffect(() => {
    if (isLayoutRunning) {
      return;
    }

    setLoadingProgress((current) => (current?.phase === "stabilizing_layout" ? null : current));
  }, [isLayoutRunning]);

  useEffect(() => {
    if (!summary || graphReady) {
      return;
    }

    applyGraphReadySummary(summary);
  }, [applyGraphReadySummary, graphReady, summary]);

  useEffect(() => {
    let cancelled = false;
    const loadBounds = async () => {
      try {
        const response = await fetch("/api/temporal/bounds");
        if (!response.ok || cancelled) return;
        const data: TemporalBounds = await response.json();
        if (!cancelled) {
          setTemporalBounds(data);
        }
      } catch {
        if (!cancelled) {
          setTemporalBounds(null);
        }
      }
    };
    loadBounds();
    return () => {
      cancelled = true;
    };
  }, [summary?.nodeCount, summary?.edgeCount]);

  useEffect(() => {
    if (!debouncedTime || isLoading) return;
    let cancelled = false;

    const applySnapshot = async () => {
      try {
        const at = debouncedTime.toISOString();
        const response = await fetch(`/api/temporal/snapshot?at=${encodeURIComponent(at)}`);
        if (!response.ok || cancelled) return;

        const data: { active_node_ids: string[]; active_node_count: number } = await response.json();
        if (cancelled) return;

        const nextActiveIds = new Set(data.active_node_ids);
        requestAnimationFrame(() => {
          if (cancelled) return;
          const previous = prevActiveIdsRef.current;
          previous.forEach((id) => {
            if (!nextActiveIds.has(id) && graph.hasNode(id)) {
              graph.setNodeAttribute(id, "hidden", true);
            }
          });
          nextActiveIds.forEach((id) => {
            if (graph.hasNode(id)) {
              graph.setNodeAttribute(id, "hidden", false);
            }
          });
          prevActiveIdsRef.current = nextActiveIds;
          setActiveNodeCount(data.active_node_count);
          setGraphVersion((current) => current + 1);
          sceneRef.current?.getRuntime()?.requestRender();
        });
      } catch (fetchError) {
        if (!cancelled) {
          console.error("[Temporal] Snapshot fetch failed", fetchError);
        }
      }
    };

    applySnapshot();
    return () => {
      cancelled = true;
    };
  }, [debouncedTime, isLoading]);

  const resolveNodeIdForFocusedMode = useCallback((
    nodeId: string,
    displayGraphCandidate?: GraphSceneRuntime["displayGraph"] | null,
  ): FocusResolution => {
    if (!nodeId) {
      return {
        kind: "none",
        resolvedNodeId: null,
        reason: "Select a node to inspect in Focused mode.",
      };
    }

    if (graph.hasNode(nodeId)) {
      return {
        kind: "base",
        resolvedNodeId: nodeId,
        reason: null,
      };
    }

    const currentDisplayGraph = displayGraphCandidate ?? pluginRuntimeRef.current?.displayGraph ?? graph;
    if (currentDisplayGraph.hasNode(nodeId)) {
      const displayAttrs = currentDisplayGraph.getNodeAttributes(nodeId) as NodeAttributes;
      const communityGroup = displayAttrs.properties?.__communityGroup as
        | {
            anchorNodeId?: string | null;
            sampleNodeIds?: string[];
          }
        | undefined;

      const anchorNodeId = communityGroup?.anchorNodeId || communityGroup?.sampleNodeIds?.[0] || "";
      if (anchorNodeId && graph.hasNode(anchorNodeId)) {
        return {
          kind: "grouped",
          resolvedNodeId: anchorNodeId,
          reason: null,
        };
      }

      return {
        kind: "grouped",
        resolvedNodeId: null,
        reason: "Focused mode is unavailable for this grouped selection.",
      };
    }

    return {
      kind: "unavailable",
      resolvedNodeId: null,
      reason: "Selected item is not available in the current graph.",
    };
  }, []);

  const focusedSelectionResolution = useMemo(
    () => resolveNodeIdForFocusedMode(selectedNodeId, pluginRuntimeRef.current?.displayGraph),
    [pluginRuntimeVersion, resolveNodeIdForFocusedMode, selectedNodeId, viewMode],
  );
  const inspectableNodeId = focusedSelectionResolution.resolvedNodeId ?? "";
  const canActivateFocusedMode = Boolean(focusedSelectionResolution.resolvedNodeId);
  const { available: groupedViewAvailable, reason: groupedViewReason } = useMemo(
    () => checkGroupedViewAvailability(),
    [graphVersion],
  );
  const groupedDisplayCandidate = useMemo(
    () => viewMode === "grouped"
      ? resolveDisplayGraph("", EMPTY_PATH, EMPTY_PATH, "grouped", {
          aggregationEnabled,
          collapsedNeighborhoodNodeIds,
        })
      : null,
    [viewMode, aggregationEnabled, collapsedNeighborhoodNodeIds, graphVersion],
  );

  const requestViewMode = useCallback((nextViewMode: GraphViewMode) => {
    if (nextViewMode === "focused") {
      const resolution = resolveNodeIdForFocusedMode(selectedNodeId, pluginRuntimeRef.current?.displayGraph);
      if (!resolution.resolvedNodeId) {
        return;
      }

      setFocusedNodeId(resolution.resolvedNodeId);
      setSelectedNodeId(resolution.resolvedNodeId);
      setViewMode("focused");
      setIsLayoutRunning(false);
      return;
    }

    if (nextViewMode === "grouped") {
      if (!groupedViewAvailable) {
        debugGraphWorkspace("grouped-view-unavailable", {
          reason: groupedViewReason,
          graphVersion,
        });
        return;
      }

      const groupedDisplayGraph = groupedDisplayCandidate?.graph
        ?? resolveDisplayGraph("", EMPTY_PATH, EMPTY_PATH, "grouped", {
          aggregationEnabled,
          collapsedNeighborhoodNodeIds,
        }).graph;
      const nextGroupedSelection = [
        lastGroupedSelectedNodeId,
        selectedNodeId,
        focusedNodeId,
      ]
        .map((candidateId) => resolveGroupedDisplayNodeId(groupedDisplayGraph, candidateId))
        .find((candidateId): candidateId is string => Boolean(candidateId))
        ?? "";

      setFocusedNodeId("");
      setSelectedNodeId(nextGroupedSelection);
      if (nextGroupedSelection) {
        setLastGroupedSelectedNodeId(nextGroupedSelection);
      }
      setViewMode("grouped");
      setIsLayoutRunning(true);
      return;
    }

    setFocusedNodeId("");
    setSelectedNodeId((currentSelectedNodeId) => (
      currentSelectedNodeId && graph.hasNode(currentSelectedNodeId) ? currentSelectedNodeId : ""
    ));
    setViewMode("full");
  }, [
    aggregationEnabled,
    collapsedNeighborhoodNodeIds,
    focusedNodeId,
    graphVersion,
    groupedDisplayCandidate,
    groupedViewAvailable,
    groupedViewReason,
    lastGroupedSelectedNodeId,
    resolveNodeIdForFocusedMode,
    selectedNodeId,
  ]);

  const focusNode = useCallback((nodeId: string) => {
    if (!nodeId) {
      setSelectedNodeId("");
      setSelectedEdgeId("");
      setPathResult(null);
      setSearchResults([]);
      setSearchError("");
      return;
    }

    const currentDisplayGraph = pluginRuntimeRef.current?.displayGraph ?? graph;
    const nextSelectedNodeId = nodeId;

    if (!graph.hasNode(nodeId) && currentDisplayGraph.hasNode(nodeId)) {
      setLastGroupedSelectedNodeId(nodeId);
    }

    setSelectedNodeId(nextSelectedNodeId);
    setSelectedEdgeId("");
    setPathResult(null);
    setSearchResults([]);
    setSearchError("");
    if (viewMode === "focused" && graph.hasNode(nextSelectedNodeId)) {
      setFocusedNodeId(nextSelectedNodeId);
      setIsLayoutRunning(false);
    }
  }, [viewMode]);  // Note: ego/heatmap/distanceMode effects re-run automatically when selectedNodeId changes

  useEffect(() => {
    if (!externalFocusNodeId || externalFocusToken == null) return;
    if (lastExternalFocusTokenRef.current === externalFocusToken) return;
    if (!graphReady || !graph.hasNode(externalFocusNodeId)) return;

    lastExternalFocusTokenRef.current = externalFocusToken;
    // Set state directly instead of going through focusNode(), which captures
    // a stale viewMode in its closure. setViewMode is called first so the node
    // is visible in the full graph before the scene pans to it.
    setViewMode("full");
    setSelectedNodeId(externalFocusNodeId);
    setSelectedEdgeId("");
    window.setTimeout(() => {
      sceneRef.current?.focusNode(externalFocusNodeId);
    }, 0);
  }, [externalFocusNodeId, externalFocusToken, graphReady]);

  const handleEdgeSelect = useCallback((edgeId: string) => {
    setSelectedEdgeId(edgeId);
  }, []);

  const handleSearch = useCallback(async () => {
    if (!searchQuery.trim()) {
      setSearchResults([]);
      return;
    }
    setSearchError("");
    try {
      const response = await fetch("/api/graph/search", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ query: searchQuery, limit: 8 }),
      });
      if (!response.ok) {
        throw new Error(`Search failed with status ${response.status}`);
      }
      const data = await response.json();
      setSearchResults(data.results || []);
    } catch (searchFetchError) {
      setSearchError(searchFetchError instanceof Error ? searchFetchError.message : "Search failed");
    }
  }, [searchQuery]);

  const handleRunPredictions = useCallback(async () => {
    if (!inspectableNodeId) return;
    setIsRunningPredictions(true);
    try {
      const response = await fetch("/api/enrich/links", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          node_id: inspectableNodeId,
          top_n: 6,
          candidate_type: predictionType || undefined,
          min_score: 0,
        }),
      });
      if (!response.ok) {
        throw new Error(`Link prediction failed with status ${response.status}`);
      }
      const data = await response.json();
      setPredictions(data.predictions || []);
    } catch (predictionError) {
      console.error("[GraphWorkspace] prediction failed", predictionError);
      setPredictions([]);
    } finally {
      setIsRunningPredictions(false);
    }
  }, [inspectableNodeId, predictionType]);

  const handleTracePath = useCallback(async () => {
    if (!inspectableNodeId || !pathTargetId.trim()) return;
    try {
      const pathParams = new URLSearchParams({
        source: inspectableNodeId,
        target: pathTargetId.trim(),
        algorithm: "dijkstra",
      });
      const response = await fetch(
        `/api/graph/path?${pathParams.toString()}`
      );
      if (!response.ok) {
        throw new Error(`Path lookup failed with status ${response.status}`);
      }
      const data: PathResponse = await response.json();
      setPathResult(data);
      if (data.path?.length) {
        const lastStep = data.path[data.path.length - 1];
        if (graph.hasNode(lastStep)) {
          sceneRef.current?.focusNode(lastStep);
        }
      }
    } catch (pathError) {
      console.error("[GraphWorkspace] path trace failed", pathError);
      setPathResult(null);
    }
  }, [inspectableNodeId, pathTargetId]);

  const handleDownloadProvenance = useCallback(async (format: "json" | "markdown") => {
    if (!inspectableNodeId) return;
    const suffix = format === "markdown" ? "markdown" : "json";
    const response = await fetch(`/api/provenance/report?node_id=${encodeURIComponent(inspectableNodeId)}&format=${suffix}`);
    if (!response.ok) {
      throw new Error(`Provenance report failed with status ${response.status}`);
    }
    const blob = await response.blob();
    const url = window.URL.createObjectURL(blob);
    const anchor = document.createElement("a");
    anchor.href = url;
    anchor.download = `${inspectableNodeId}_provenance.${format === "markdown" ? "md" : "json"}`;
    document.body.appendChild(anchor);
    anchor.click();
    window.URL.revokeObjectURL(url);
    document.body.removeChild(anchor);
  }, [inspectableNodeId]);

  useEffect(() => {
    const protocol = window.location.protocol === "https:" ? "wss:" : "ws:";
    const socket = new WebSocket(`${protocol}//${window.location.host}/ws/graph-updates`);

    socket.onmessage = (event) => {
      try {
        const message = JSON.parse(event.data);
        if (message.event === "connection_ack") {
          return;
        }
        if (message.event !== "graph_mutation") {
          return;
        }
        const eventType = message.data?.event_type;
        const payload = message.data?.payload;
        if (eventType === "ADD_NODE" && payload?.id) {
          batchMergeNodes([
            {
              id: payload.id,
              attributes: buildRealtimeNodeAttributes(payload),
            },
          ]);
          logEvent("add-node", `Added node ${payload.label ?? payload.id}${payload.nodeType ? ` (${payload.nodeType})` : ""} via realtime ws`, { nodeId: payload.id, nodeType: payload.nodeType });
          setGraphVersion((current) => current + 1);
          sceneRef.current?.getRuntime()?.requestRender();
        }
        if (eventType === "ADD_EDGE") {
          batchMergeEdges([
            {
              id: String(payload.id),
              familyId: payload.familyId ? String(payload.familyId) : String(payload.id),
              source: payload.source_id,
              target: payload.target_id,
              attributes: buildRealtimeEdgeAttributes(payload),
            },
          ]);
          logEvent("add-edge", `Added edge ${payload.edgeType ?? payload.id} (${payload.source_id} → ${payload.target_id}) via realtime ws`, { edgeId: payload.id, edgeType: payload.edgeType, source: payload.source_id, target: payload.target_id });
          setGraphVersion((current) => current + 1);
          sceneRef.current?.getRuntime()?.requestRender();
        }
      } catch (socketError) {
        console.error("[GraphWorkspace] websocket update failed", socketError);
      }
    };

    return () => {
      socket.close();
    };
  }, []);

  useEffect(() => {
    setCollapsedNeighborhoodNodeIds([]);
    setFocusedNodeId("");
    setLastGroupedSelectedNodeId("");
  }, [summary?.edgeCount, summary?.nodeCount]);

  const activeDistanceMode: GraphDistanceVisualMode = egoModeEnabled
    ? "ego"
    : heatmapEnabled
      ? "heatmap"
      : distanceMode;
  const distanceAnchorNodeId = viewMode === "full" && selectedNodeId && graph.hasNode(selectedNodeId)
    ? selectedNodeId
    : "";
  const distanceAnchorLabel = distanceAnchorNodeId
    ? String((graph.getNodeAttributes(distanceAnchorNodeId) as NodeAttributes).label || distanceAnchorNodeId)
    : null;
  const distanceMaxHops = activeDistanceMode === "ego"
    ? egoMaxHops
    : activeDistanceMode === "heatmap"
      ? HEATMAP_DISTANCE_MAX_HOPS
      : STRUCTURAL_DISTANCE_MAX_HOPS;
  const structuralDistances = useMemo(
    () => (
      distanceAnchorNodeId && activeDistanceMode !== "off"
        ? buildStructuralDistanceSnapshot(graph, distanceAnchorNodeId, distanceMaxHops)
        : EMPTY_DISTANCE_RECORD
    ),
    [activeDistanceMode, distanceAnchorNodeId, distanceMaxHops, graphVersion],
  );
  const distanceCounts = useMemo(
    () => summarizeDistanceBuckets(structuralDistances, graph.order),
    [structuralDistances, graphVersion],
  );
  const heatmapRenderSnapshot = useMemo(
    () => (
      activeDistanceMode === "heatmap" && distanceAnchorNodeId
        ? buildHeatmapRenderSnapshot(graph, distanceAnchorNodeId, structuralDistances, HEATMAP_DISTANCE_MAX_HOPS)
        : null
    ),
    [activeDistanceMode, distanceAnchorNodeId, graphVersion, structuralDistances],
  );

  useEffect(() => {
    if (viewMode === "full") {
      return;
    }
    setEgoModeEnabled(false);
    setHeatmapEnabled(false);
    setDistanceMode("off");
  }, [viewMode]);

  useEffect(() => {
    if (activeDistanceMode === "off" || !selectedNodeId || !graph.hasNode(selectedNodeId)) {
      setEgoModeEnabled(false);
      setHeatmapEnabled(false);
      setDistanceMode("off");
    }
  }, [activeDistanceMode, graphVersion, selectedNodeId]);

  useEffect(() => {
    if (distanceMode !== "semantic" || !distanceAnchorNodeId) {
      setSemanticDistanceState({
        anchorNodeId: distanceAnchorNodeId || null,
        scores: EMPTY_DISTANCE_RECORD,
        count: 0,
        status: distanceMode === "semantic" ? "unavailable" : "idle",
        error: distanceMode === "semantic" ? "Select a Full Graph node to load semantic distance." : null,
      });
      return;
    }

    let cancelled = false;
    setSemanticDistanceState({
      anchorNodeId: distanceAnchorNodeId,
      scores: EMPTY_DISTANCE_RECORD,
      count: 0,
      status: "loading",
      error: null,
    });

    const loadSemanticNeighborhood = async () => {
      try {
        const semanticParams = new URLSearchParams({
          node_id: distanceAnchorNodeId,
          top_k: "50",
        });
        const response = await fetch(
          `/api/graph/semantic-neighborhood?${semanticParams.toString()}`,
        );
        if (cancelled) {
          return;
        }
        if (!response.ok) {
          throw new Error(response.status === 503
            ? "Semantic similarity is unavailable for this graph."
            : response.status === 404
              ? "Selected node was not found by the semantic distance API."
            : `Semantic distance failed with status ${response.status}`);
        }

        const data: SemanticNeighborhoodResponse = await response.json();
        const scores = data.neighbors.reduce<Record<string, number>>((nextScores, neighbor) => {
          if (Number.isFinite(neighbor.similarity)) {
            nextScores[neighbor.id] = neighbor.similarity;
          }
          return nextScores;
        }, {});

        setSemanticDistanceState({
          anchorNodeId: distanceAnchorNodeId,
          scores,
          count: Object.keys(scores).length,
          status: Object.keys(scores).length > 0 ? "ready" : "unavailable",
          error: Object.keys(scores).length > 0 ? null : "No semantic neighbors were returned for this node.",
        });
      } catch (error) {
        if (cancelled) {
          return;
        }
        setSemanticDistanceState({
          anchorNodeId: distanceAnchorNodeId,
          scores: EMPTY_DISTANCE_RECORD,
          count: 0,
          status: "error",
          error: error instanceof Error ? error.message : "Semantic distance could not be loaded.",
        });
      }
    };

    void loadSemanticNeighborhood();
    return () => {
      cancelled = true;
    };
  }, [distanceAnchorNodeId, distanceMode]);

  const distanceVisualState = useMemo<GraphDistanceVisualState>(() => {
    if (activeDistanceMode === "off") {
      return {
        mode: "off",
        anchorNodeId: null,
        anchorLabel: null,
        maxHops: distanceMaxHops,
        structuralDistances: EMPTY_DISTANCE_RECORD,
        semanticScores: EMPTY_DISTANCE_RECORD,
        distanceCounts: undefined,
        outsideCount: 0,
        heatmapVisibleNodeIds: undefined,
        heatmapRingCounts: undefined,
        heatmapRenderedRingCounts: undefined,
        heatmapSaturationMode: undefined,
        semanticNeighborCount: 0,
        status: "idle",
        error: null,
      };
    }

    if (viewMode !== "full") {
      return {
        mode: activeDistanceMode,
        anchorNodeId: null,
        anchorLabel: null,
        maxHops: distanceMaxHops,
        structuralDistances: EMPTY_DISTANCE_RECORD,
        semanticScores: EMPTY_DISTANCE_RECORD,
        distanceCounts: undefined,
        outsideCount: graph.order,
        heatmapVisibleNodeIds: undefined,
        heatmapRingCounts: undefined,
        heatmapRenderedRingCounts: undefined,
        heatmapSaturationMode: undefined,
        semanticNeighborCount: 0,
        status: "unavailable",
        error: "Distance intelligence is available in Full Graph mode.",
      };
    }

    if (!distanceAnchorNodeId) {
      return {
        mode: activeDistanceMode,
        anchorNodeId: null,
        anchorLabel: null,
        maxHops: distanceMaxHops,
        structuralDistances: EMPTY_DISTANCE_RECORD,
        semanticScores: EMPTY_DISTANCE_RECORD,
        distanceCounts: undefined,
        outsideCount: graph.order,
        heatmapVisibleNodeIds: undefined,
        heatmapRingCounts: undefined,
        heatmapRenderedRingCounts: undefined,
        heatmapSaturationMode: undefined,
        semanticNeighborCount: 0,
        status: "unavailable",
        error: "Select a node to activate distance intelligence.",
      };
    }

    if (activeDistanceMode === "semantic") {
      return {
        mode: "semantic",
        anchorNodeId: distanceAnchorNodeId,
        anchorLabel: distanceAnchorLabel,
        maxHops: distanceMaxHops,
        structuralDistances,
        semanticScores: semanticDistanceState.anchorNodeId === distanceAnchorNodeId
          ? semanticDistanceState.scores
          : EMPTY_DISTANCE_RECORD,
        distanceCounts,
        outsideCount: distanceCounts.outside,
        heatmapVisibleNodeIds: undefined,
        heatmapRingCounts: undefined,
        heatmapRenderedRingCounts: undefined,
        heatmapSaturationMode: undefined,
        semanticNeighborCount: semanticDistanceState.anchorNodeId === distanceAnchorNodeId
          ? semanticDistanceState.count
          : 0,
        status: semanticDistanceState.anchorNodeId === distanceAnchorNodeId
          ? semanticDistanceState.status
          : "loading",
        error: semanticDistanceState.anchorNodeId === distanceAnchorNodeId
          ? semanticDistanceState.error
          : null,
      };
    }

    return {
      mode: activeDistanceMode,
      anchorNodeId: distanceAnchorNodeId,
      anchorLabel: distanceAnchorLabel,
      maxHops: distanceMaxHops,
      structuralDistances,
      semanticScores: EMPTY_DISTANCE_RECORD,
      distanceCounts,
      outsideCount: distanceCounts.outside,
      heatmapVisibleNodeIds: heatmapRenderSnapshot?.visibleNodeIds,
      heatmapRingCounts: heatmapRenderSnapshot?.ringCounts,
      heatmapRenderedRingCounts: heatmapRenderSnapshot?.renderedRingCounts,
      heatmapSaturationMode: heatmapRenderSnapshot?.saturationMode,
      semanticNeighborCount: 0,
      status: "ready",
      error: null,
    };
  }, [
    activeDistanceMode,
    distanceAnchorLabel,
    distanceAnchorNodeId,
    distanceCounts,
    distanceMaxHops,
    graph.order,
    heatmapRenderSnapshot,
    semanticDistanceState,
    structuralDistances,
    viewMode,
  ]);

  const showLoadingOverlay = !graphReady && (isLoading || isFetching || Boolean(loadingProgress));
  const showSettlingStatus = graphReady && loadingProgress?.phase === "stabilizing_layout";
  const hasGraphContent = Boolean(summary?.nodeCount);
  const activePath = pathResult?.path ?? EMPTY_PATH;
  const activePathEdgeIds = pathResult?.edge_ids ?? EMPTY_PATH;
  const structuralSelectedNodeId = useMemo(() => {
    if (viewMode === "focused") {
      return focusedNodeId && graph.hasNode(focusedNodeId) ? focusedNodeId : "";
    }
    if (!selectedNodeId || !graph.hasNode(selectedNodeId)) {
      return "";
    }
    return collapsedNeighborhoodNodeIds.includes(selectedNodeId) ? selectedNodeId : "";
  }, [collapsedNeighborhoodNodeIds, focusedNodeId, selectedNodeId, viewMode]);
  const structuralActivePath = structuralSelectedNodeId ? activePath : EMPTY_PATH;
  const structuralActivePathEdgeIds = structuralSelectedNodeId ? activePathEdgeIds : EMPTY_PATH;
  const displayResult = useMemo(
    () => (
      viewMode === "grouped"
        ? (groupedDisplayCandidate ?? resolveDisplayGraph("", EMPTY_PATH, EMPTY_PATH, "grouped", {
            aggregationEnabled,
            collapsedNeighborhoodNodeIds,
          }))
        : resolveDisplayGraph(structuralSelectedNodeId, structuralActivePath, structuralActivePathEdgeIds, viewMode, {
            aggregationEnabled,
            collapsedNeighborhoodNodeIds,
          })
    ),
    [
      aggregationEnabled,
      collapsedNeighborhoodNodeIds,
      groupedDisplayCandidate,
      structuralActivePath,
      structuralActivePathEdgeIds,
      structuralSelectedNodeId,
      viewMode,
    ],
  );
  const displayState = useMemo(
    () => (
      viewMode === "grouped"
        ? resolveGroupedDisplayStateSnapshot(displayResult.graph, selectedNodeId, {
            groupedViewAvailable,
            groupedViewReason,
            selectedNodeKind: focusedSelectionResolution.kind,
            resolvedFocusedNodeId: focusedSelectionResolution.resolvedNodeId,
            focusedUnavailableReason: focusedSelectionResolution.reason,
          })
        : resolveDisplayStateSnapshot(selectedNodeId, activePath, viewMode, {
            aggregationEnabled,
            collapsedNeighborhoodNodeIds,
            groupedViewAvailable,
            groupedViewReason,
            selectedNodeKind: focusedSelectionResolution.kind,
            resolvedFocusedNodeId: focusedSelectionResolution.resolvedNodeId,
            focusedUnavailableReason: focusedSelectionResolution.reason,
          })
    ),
    [
      activePath,
      aggregationEnabled,
      collapsedNeighborhoodNodeIds,
      displayResult.graph,
      focusedSelectionResolution.kind,
      focusedSelectionResolution.reason,
      focusedSelectionResolution.resolvedNodeId,
      groupedViewAvailable,
      groupedViewReason,
      selectedNodeId,
      viewMode,
    ],
  );
  const displayMeta = displayResult.meta;
  useEffect(() => {
    if (viewMode === "grouped" && !groupedViewAvailable) {
      debugGraphWorkspace("grouped-view-reset-to-full", {
        reason: groupedViewReason,
        graphVersion,
      });
      setViewMode("full");
      setFocusedNodeId("");
      setSelectedNodeId((currentSelectedNodeId) => (
        currentSelectedNodeId && graph.hasNode(currentSelectedNodeId) ? currentSelectedNodeId : ""
      ));
    }
  }, [graphVersion, groupedViewAvailable, groupedViewReason, viewMode]);
  useEffect(() => {
    if (viewMode === "focused" && (!focusedNodeId || !graph.hasNode(focusedNodeId))) {
      setViewMode("full");
      setFocusedNodeId("");
    }
  }, [focusedNodeId, graphVersion, viewMode]);
  const previousDisplayGraphRef = useRef(displayResult.graph);
  const previousDisplayStateRef = useRef(displayState);
  useEffect(() => {
    const graphRebuilt = previousDisplayGraphRef.current !== displayResult.graph;
    const displayStateChanged = previousDisplayStateRef.current !== displayState;
    debugGraphWorkspace("display-state-derived", {
      selectedNodeId,
      structuralSelectedNodeId,
      viewMode,
      graphRebuilt,
      displayStateChanged,
      aggregationEnabled,
      collapsedNeighborhoodActive: Boolean(structuralSelectedNodeId && collapsedNeighborhoodNodeIds.includes(structuralSelectedNodeId)),
    });
    previousDisplayGraphRef.current = displayResult.graph;
    previousDisplayStateRef.current = displayState;
  }, [
    aggregationEnabled,
    collapsedNeighborhoodNodeIds,
    displayResult.graph,
    displayState,
    selectedNodeId,
    structuralSelectedNodeId,
    viewMode,
  ]);
  const focusedSummary = useMemo(() => {
    if (!selectedNodeId || !graph.hasNode(selectedNodeId)) {
      if (viewMode === "grouped") {
        return displayState.groupedViewAvailable
          ? "Communities compressed into grouped structure view"
          : (displayState.groupedViewReason ?? "Grouped view is unavailable for the current graph");
      }
      return null;
    }

    const localNeighborCount = graph.neighbors(selectedNodeId).length;
    if (viewMode === "focused") {
      const visibleNeighbors = displayState.selectedVisibleNeighborIds.length || Math.min(localNeighborCount, 16);
      return `${visibleNeighbors + 1} nodes in focused view`;
    }

    if (viewMode === "grouped") {
      return "Grouped structure view with direct community drill-in";
    }

    if (displayState.selectedCollapsedNeighborIds.length > 0) {
      return `${displayState.selectedVisibleNeighborIds.length} visible neighbors, ${displayState.selectedCollapsedNeighborIds.length} collapsed`;
    }

    return `${localNeighborCount} direct neighbors highlighted`;
  }, [displayState, selectedNodeId, viewMode]);
  const graphSummary = summary as GraphLoadSummary | null;
  const selectedNodeState = useMemo(
    () => buildSelectedNodeState(selectedNodeId, displayState),
    [displayState, selectedNodeId, summary?.nodeCount, summary?.edgeCount],
  );
  const selectedEdgeState = useMemo(
    () => buildSelectedEdgeState(selectedEdgeId, displayResult.graph),
    [displayResult.graph, selectedEdgeId, summary?.nodeCount, summary?.edgeCount],
  );
  const temporalState = useMemo(
    () => ({
      currentTime: scrubberTime,
      activeNodeCount,
      minDate: temporalBounds?.min ?? undefined,
      maxDate: temporalBounds?.max ?? undefined,
    }),
    [activeNodeCount, scrubberTime, temporalBounds?.max, temporalBounds?.min],
  );

  const pluginRegistry = useMemo<LazyPluginRegistryEntry[]>(
    () => [
      {
        id: "exploration-effects",
        panelId: "effects-panel",
        label: "Effects",
        title: "Open exploration effects controls",
        order: 18,
        load: loadExplorationEffectsPlugin,
        shouldLoad: ({ panelState }) => Boolean(panelState["effects-panel"]),
      },
      {
        id: "neighborhood-panel",
        panelId: "neighborhood-panel",
        label: "Neighbors",
        title: "Toggle neighborhood panel",
        order: 30,
        load: loadNeighborhoodPanelPlugin,
        shouldLoad: ({ panelState }) => Boolean(panelState["neighborhood-panel"]),
      },
      {
        id: "temporal-overlay",
        panelId: "temporal-panel",
        label: "Temporal",
        title: "Toggle temporal context panel",
        order: 40,
        load: loadTemporalOverlayPlugin,
        shouldLoad: ({ panelState, temporalState }) => Boolean(panelState["temporal-panel"] || temporalState?.currentTime),
      },
    ],
    [],
  );
  const activePlugins = useMemo(
    () => pluginRegistry.map((entry) => loadedPlugins[entry.id]).filter((plugin): plugin is GraphPlugin => Boolean(plugin)),
    [loadedPlugins, pluginRegistry],
  );

  useEffect(() => {
    let cancelled = false;

    pluginRegistry.forEach((entry) => {
      if (loadedPlugins[entry.id]) {
        return;
      }

      if (!entry.shouldLoad({ panelState: pluginPanelState, temporalState })) {
        return;
      }

      void entry.load()
        .then((plugin) => {
          if (cancelled) {
            return;
          }
          setLoadedPlugins((current) => (current[entry.id] ? current : { ...current, [entry.id]: plugin }));
        })
        .catch((error) => {
          console.error(`[GraphPlugin:${entry.id}] lazy load failed`, error);
        });
    });

    return () => {
      cancelled = true;
    };
  }, [loadedPlugins, pluginPanelState, pluginRegistry, temporalState]);

  const setEffectToggle = useCallback((effect: GraphEffectToggle, enabled: boolean | ((current: boolean) => boolean)) => {
    setEffectsState((current) => {
      const nextValue = typeof enabled === "function" ? enabled(current[effect]) : enabled;
      if (effect === "diagnosticsEnabled" && !GRAPH_THEME.effects.diagnostics.enabledInDev) {
        return current;
      }
      if (current[effect] === nextValue) {
        return current;
      }
      return {
        ...current,
        [effect]: nextValue,
      };
    });
  }, []);

  const handlePluginAction = useCallback((action: GraphPluginActionRequest) => {
    switch (action.type) {
      case "fitView":
        sceneRef.current?.fitView();
        return;
      case "focusNode":
        sceneRef.current?.focusNode(action.nodeId);
        return;
      case "selectNode":
        focusNode(action.nodeId);
        return;
      case "setViewMode":
        requestViewMode(action.viewMode);
        return;
      case "collapseNeighborhood":
        if (!selectedNodeId) {
          return;
        }
        setCollapsedNeighborhoodNodeIds((current) => (
          current.includes(selectedNodeId) ? current : [...current, selectedNodeId]
        ));
        return;
      case "expandNeighborhood":
        if (!selectedNodeId) {
          return;
        }
        setCollapsedNeighborhoodNodeIds((current) => current.filter((nodeId) => nodeId !== selectedNodeId));
        return;
      case "toggleEffect":
        setEffectToggle(action.effect, (current) => !current);
        return;
      case "setEffect":
        setEffectToggle(action.effect, action.enabled);
        return;
      case "togglePanel":
        setPluginPanelState((current) => {
          const nextOpen = !current[action.panelId];
          setActiveDockPanelId((previous) => {
            if (nextOpen) {
              return action.panelId;
            }
            return previous === action.panelId ? null : previous;
          });
          return {
            ...current,
            [action.panelId]: nextOpen,
          };
        });
        return;
      case "openPanel":
        setActiveDockPanelId(action.panelId);
        setPluginPanelState((current) => ({
          ...current,
          [action.panelId]: true,
        }));
        return;
      case "closePanel":
        setPluginPanelState((current) => ({
          ...current,
          [action.panelId]: false,
        }));
        setActiveDockPanelId((previous) => (previous === action.panelId ? null : previous));
        return;
    }
  }, [focusNode, requestViewMode, selectedNodeId, setEffectToggle]);

  const diagnosticsSnapshot = useMemo<GraphDiagnosticsSnapshot | null>(() => {
    if (!GRAPH_THEME.effects.diagnostics.enabledInDev || !graphDiagnosticsState) {
      return null;
    }

    return {
      interactionState: pluginInteractionStateRef.current,
      activePluginIds: activePlugins.map((plugin) => plugin.id),
      openPanelIds: Object.entries(pluginPanelState)
        .filter(([, isOpen]) => isOpen)
        .map(([panelId]) => panelId),
      effectsState,
      edgeClasses: graphDiagnosticsState.edgeClasses,
      distanceVisual: graphDiagnosticsState.distanceVisual,
      effectAvailability: graphDiagnosticsState.effectAvailability,
    };
  }, [activePlugins, effectsState, graphDiagnosticsState, pluginPanelState]);

  const pluginContext = useMemo<GraphPluginContext>(() => ({
    get scene() {
      return pluginRuntimeRef.current;
    },
    get graph() {
      return graph;
    },
    get displayGraph() {
      return pluginRuntimeRef.current?.displayGraph ?? graph;
    },
    theme: GRAPH_THEME,
    getInteractionState: () => pluginInteractionStateRef.current,
    getSelectedNodeState: () => selectedNodeState,
    getInspectorState: () => ({
      selectedNodeId: selectedNodeId || null,
      ownsSelectionDetails: true,
    }),
    getGraphSummary: () => graphSummary,
    getTemporalState: () => temporalState,
    getEffectsState: () => effectsState,
    getDiagnosticsSnapshot: () => diagnosticsSnapshot,
    getAnalyticsSnapshot: () => graphAnalyticsState,
    getDisplayState: () => displayState,
    isPanelOpen: (panelId: string) => Boolean(pluginPanelState[panelId]),
    dispatchAction: handlePluginAction,
  }), [
    displayState,
    graphAnalyticsState,
    diagnosticsSnapshot,
    effectsState,
    graphSummary,
    handlePluginAction,
    pluginPanelState,
    selectedNodeId,
    selectedNodeState,
    temporalState,
  ]);

  const handleSceneRuntimeChange = useCallback((runtime: GraphSceneRuntime | null) => {
    pluginRuntimeRef.current = runtime;
    if (!runtime) {
      setGraphAnalyticsState(null);
    }
    setPluginRuntimeVersion((version) => version + 1);
  }, []);

  const handleInteractionStateChange = useCallback((interactionState: GraphInteractionState) => {
    pluginInteractionStateRef.current = interactionState;
    for (const plugin of activePlugins) {
      try {
        plugin.onStateChange(pluginContext, interactionState);
      } catch (error) {
        console.error(`[GraphPlugin:${plugin.id}] state update failed`, error);
      }
    }
  }, [activePlugins, pluginContext]);

  const handleDiagnosticsChange = useCallback((diagnostics: GraphRuntimeDiagnosticsSnapshot) => {
    if (!GRAPH_THEME.effects.diagnostics.enabledInDev) {
      return;
    }
    setGraphDiagnosticsState(diagnostics);
  }, []);

  const handleAnalyticsChange = useCallback((analytics: GraphAnalyticsSnapshot | null) => {
    setGraphAnalyticsState(analytics);
  }, []);

  useEffect(() => {
    if (!pluginRuntimeRef.current) {
      return;
    }

    const mountedPlugins: GraphPlugin[] = [];
    for (const plugin of activePlugins) {
      try {
        plugin.mount(pluginContext);
        mountedPlugins.push(plugin);
      } catch (error) {
        console.error(`[GraphPlugin:${plugin.id}] mount failed`, error);
      }
    }

    return () => {
      for (const plugin of mountedPlugins.reverse()) {
        try {
          plugin.unmount(pluginContext);
        } catch (error) {
          console.error(`[GraphPlugin:${plugin.id}] unmount failed`, error);
        }
      }
    };
  }, [activePlugins, pluginContext, pluginRuntimeVersion]);

  const pluginToolbarItems = useMemo<GraphPluginToolbarItem[]>(
    () => pluginRegistry.map((entry) => ({
      id: `${entry.id}-toggle`,
      label: entry.label,
      title: entry.title,
      active: pluginContext.isPanelOpen(entry.panelId),
      order: entry.order,
      onClick: () => pluginContext.dispatchAction({ type: "togglePanel", panelId: entry.panelId }),
    })),
    [pluginContext, pluginRegistry],
  );
  const pluginPanels = useMemo(
    () => collectPluginPanels(activePlugins, pluginContext),
    [activePlugins, pluginContext],
  );
  const pluginOverlays = useMemo(
    () => collectPluginOverlays(activePlugins, pluginContext),
    [activePlugins, pluginContext],
  );
  const pendingDockPanels = useMemo<GraphPluginPanelDescriptor[]>(
    () => pluginRegistry
      .filter((entry) => pluginPanelState[entry.panelId] && !loadedPlugins[entry.id])
      .map((entry) => ({
        id: entry.panelId,
        title: entry.label,
        placement: "bottom" as const,
        order: entry.order,
        content: <div style={pluginLoadingStyle}>Loading {entry.label.toLowerCase()}…</div>,
      })),
    [loadedPlugins, pluginPanelState, pluginRegistry],
  );
  const dockPanels = [...pluginPanels, ...pendingDockPanels]
    .filter((panel) => panel.placement === "bottom" || panel.placement === "side")
    .sort((left, right) => (left.order ?? 0) - (right.order ?? 0));
  const openDockPanels = dockPanels.filter((panel) => pluginPanelState[panel.id]);
  const activeDockPanel =
    openDockPanels.find((panel) => panel.id === activeDockPanelId)
    ?? openDockPanels[0]
    ?? null;
  const layoutState: ExploreLayoutState = {
    showInspector: Boolean(selectedNodeId),
    showPluginDock: openDockPanels.length > 0,
  };

  useEffect(() => {
    if (!openDockPanels.length) {
      setActiveDockPanelId(null);
      return;
    }

    if (!activeDockPanelId || !openDockPanels.some((panel) => panel.id === activeDockPanelId)) {
      setActiveDockPanelId(openDockPanels[0].id);
    }
  }, [activeDockPanelId, openDockPanels]);

  const viewModeItems = useMemo<GraphToolbarItem[]>(() => {
    if (!hasGraphContent) {
      return [];
    }

    return [
      {
        id: "view-full",
        label: "Full Graph",
        title: "Return to the full graph context",
        icon: Layers3,
        active: viewMode === "full",
        onClick: () => requestViewMode("full"),
      },
      {
        id: "view-grouped",
        label: "Grouped View",
        title: displayState.groupedViewAvailable
          ? "Compress dense structure into detected communities"
          : (displayState.groupedViewReason ?? "Grouped view is unavailable until communities can be detected"),
        icon: GitBranch,
        active: viewMode === "grouped",
        disabled: !displayState.groupedViewAvailable,
        onClick: () => requestViewMode("grouped"),
      },
      {
        id: "view-focused",
        label: "Focused",
        title: canActivateFocusedMode
          ? "Inspect the selected node in a focused local graph"
          : (focusedSelectionResolution.reason ?? "Focused mode is unavailable for the current selection"),
        icon: Focus,
        active: viewMode === "focused",
        disabled: viewMode !== "focused" && !canActivateFocusedMode,
        onClick: () => requestViewMode("focused"),
      },
    ];
  }, [
    canActivateFocusedMode,
    displayState.groupedViewAvailable,
    displayState.groupedViewReason,
    focusedSelectionResolution.reason,
    hasGraphContent,
    requestViewMode,
    viewMode,
  ]);

  const cameraToolbarItems = useMemo<GraphToolbarItem[]>(() => [
    {
      id: "zoom-in",
      label: "Zoom In",
      title: "Zoom in (or scroll up on the canvas)",
      ariaLabel: "Zoom in",
      icon: ZoomIn,
      compact: true,
      onClick: () => sceneRef.current?.zoomIn(),
    },
    {
      id: "zoom-out",
      label: "Zoom Out",
      title: "Zoom out (or scroll down on the canvas)",
      ariaLabel: "Zoom out",
      icon: ZoomOut,
      compact: true,
      onClick: () => sceneRef.current?.zoomOut(),
    },
    {
      id: "fit-view",
      label: "Fit",
      title: "Reset the camera to fit the whole graph",
      ariaLabel: "Fit view",
      icon: Maximize2,
      compact: true,
      onClick: () => sceneRef.current?.fitView(),
    },
  ], []);

  const layoutToolbarItems = useMemo<GraphToolbarItem[]>(() => [
    {
      id: "layout-toggle",
      label: isLayoutRunning ? "Pause" : "Run",
      title: "Toggle the layout worker",
      icon: isLayoutRunning ? Pause : Play,
      active: isLayoutRunning,
      disabled: showLoadingOverlay,
      onClick: () => setIsLayoutRunning((value) => !value),
    },
  ], [isLayoutRunning, showLoadingOverlay]);

  const localToolbarItems = useMemo<GraphToolbarItem[]>(() => {
    if (!selectedNodeState) {
      return [];
    }

    return [
      {
        id: "collapse-neighborhood",
        label: "Collapse",
        title: "Hide lower-priority fanout around the selected node",
        icon: Eye,
        disabled: !selectedNodeState.canCollapseNeighborhood || selectedNodeState.isNeighborhoodCollapsed,
        onClick: () => handlePluginAction({ type: "collapseNeighborhood" }),
      },
      {
        id: "expand-neighborhood",
        label: "Expand",
        title: "Restore the collapsed local neighborhood",
        icon: Users,
        disabled: !selectedNodeState.isNeighborhoodCollapsed,
        onClick: () => handlePluginAction({ type: "expandNeighborhood" }),
      },
    ];
  }, [handlePluginAction, selectedNodeState]);

  const analysisToolbarItems = useMemo<GraphToolbarItem[]>(
    () => pluginToolbarItems.map((item) => ({
      id: item.id,
      label: item.label,
      title: item.title,
      icon: iconForPluginToolbarItem(item),
      active: item.active,
      onClick: item.onClick,
    })),
    [pluginToolbarItems],
  );

  const utilityToolbarItems = useMemo<GraphToolbarItem[]>(() => [
    {
      id: "reload",
      label: "Reload",
      title: "Reload the graph data",
      ariaLabel: "Reload graph data",
      icon: RefreshCw,
      compact: true,
      disabled: showLoadingOverlay,
      onClick: reload,
    },
  ], [reload, showLoadingOverlay]);

  const searchDisabled = showLoadingOverlay || !searchQuery.trim();

  const distanceToolbarItems = useMemo<GraphToolbarItem[]>(() => {
    if (!hasGraphContent || viewMode !== "full" || !selectedNodeId || !graph.hasNode(selectedNodeId)) {
      return [];
    }

    return [
      {
        id: "ego-mode",
        label: egoModeEnabled ? `Ego (${egoMaxHops}h)` : "Ego Mode",
        title: egoModeEnabled
          ? `Egocentric view: ${egoMaxHops} hops depth (click to toggle off)`
          : "Show depth-of-field fading around the selected node",
        active: egoModeEnabled,
        onClick: () => {
          setEgoModeEnabled((v) => !v);
          setHeatmapEnabled(false);
          setDistanceMode("off");
        },
      },
      {
        id: "heatmap",
        label: "Heatmap",
        title: heatmapEnabled
          ? "Distance heatmap active (click to toggle off)"
          : "Color nodes by hop distance from selected node",
        active: heatmapEnabled,
        onClick: () => {
          setHeatmapEnabled((v) => !v);
          setEgoModeEnabled(false);
          setDistanceMode("off");
        },
      },
      {
        id: "dist-structural",
        label: "Structural",
        title: "Color edges by structural (hop) distance",
        active: distanceMode === "structural",
        onClick: () => {
          setEgoModeEnabled(false);
          setHeatmapEnabled(false);
          setDistanceMode((m) => (m === "structural" ? "off" : "structural"));
        },
      },
      {
        id: "dist-semantic",
        label: "Semantic",
        title: "Color edges by semantic similarity to selected node",
        active: distanceMode === "semantic",
        onClick: () => {
          setEgoModeEnabled(false);
          setHeatmapEnabled(false);
          setDistanceMode((m) => (m === "semantic" ? "off" : "semantic"));
        },
      },
    ];
  }, [distanceMode, egoMaxHops, egoModeEnabled, hasGraphContent, heatmapEnabled, selectedNodeId, viewMode]);

  const toolbarClusters = useMemo<GraphToolbarGroup[]>(() => [
    {
      id: "camera",
      label: "Camera",
      items: cameraToolbarItems,
    },
    {
      id: "layout",
      label: "Layout",
      items: layoutToolbarItems,
    },
    {
      id: "local-structure",
      label: "Local",
      items: localToolbarItems,
    },
    {
      id: "distance",
      label: "Distance",
      items: distanceToolbarItems,
    },
    {
      id: "analysis",
      label: "Analysis",
      items: analysisToolbarItems,
    },
    {
      id: "utility",
      label: "Utility",
      items: utilityToolbarItems,
    },
  ].filter((group) => group.items.length > 0), [
    analysisToolbarItems,
    cameraToolbarItems,
    distanceToolbarItems,
    layoutToolbarItems,
    localToolbarItems,
    utilityToolbarItems,
  ]);

  const sceneAdapterProps = {
    onNodeSelect: focusNode,
    onEdgeSelect: handleEdgeSelect,
    graphVersion,
    graphReady,
    displayGraph: displayResult.graph,
    displayMeta,
    displayState,
    selectedNodeId,
    focusedNodeId,
    selectedEdgeId,
    activePath,
    activePathEdgeIds,
    distanceVisualState,
    effectsState,
    temporalState,
    isLayoutRunning,
    layoutSource: graphSummary?.layoutSource,
    viewMode,
    showFitViewButton: false,
    pluginOverlays: pluginOverlays.map((overlay) => overlay.element),
    onRuntimeChange: handleSceneRuntimeChange,
    onInteractionStateChange: handleInteractionStateChange,
    onDiagnosticsChange: handleDiagnosticsChange,
    onAnalyticsChange: handleAnalyticsChange,
  } as const;
  const showDistanceStatus = distanceVisualState.mode !== "off";
  const distanceReachableCount = Object.keys(distanceVisualState.structuralDistances).length;
  const visibleDistanceCounts = distanceVisualState.distanceCounts;
  const renderedHeatmapCounts = distanceVisualState.heatmapRenderedRingCounts;
  const formatRenderedCount = (truth: number, rendered: number | undefined) => {
    if (rendered == null || rendered >= truth) {
      return truth.toLocaleString();
    }
    return `${truth.toLocaleString()} (${rendered.toLocaleString()} shown)`;
  };
  const heatmapDistanceSummary = visibleDistanceCounts
    ? [
      `${visibleDistanceCounts.anchor.toLocaleString()} anchor`,
      `${formatRenderedCount(visibleDistanceCounts.oneHop, renderedHeatmapCounts?.oneHop)} 1-hop`,
      `${formatRenderedCount(visibleDistanceCounts.twoHop, renderedHeatmapCounts?.twoHop)} 2-hop`,
      `${formatRenderedCount(visibleDistanceCounts.threeHopPlus, renderedHeatmapCounts?.threeHopPlus)} 3+ hop`,
      `${visibleDistanceCounts.outside.toLocaleString()} outside`,
      distanceVisualState.heatmapSaturationMode === "sampled" ? "Sampled for readability" : "",
    ].filter(Boolean).join(" · ")
    : `${distanceReachableCount.toLocaleString()} nodes within ${distanceVisualState.maxHops} hops`;
  const heatmapRenderedSummary = distanceVisualState.mode === "heatmap" && renderedHeatmapCounts
    ? [
      `${renderedHeatmapCounts.anchor.toLocaleString()} anchor shown`,
      `${renderedHeatmapCounts.oneHop.toLocaleString()} 1-hop shown`,
      `${renderedHeatmapCounts.twoHop.toLocaleString()} 2-hop shown`,
      `${renderedHeatmapCounts.threeHopPlus.toLocaleString()} 3+ hop shown`,
    ].join(" · ")
    : null;
  const distanceLegendItems = distanceVisualState.mode === "heatmap"
    ? [
      { label: "Anchor", color: getDistanceBandColor(0) },
      { label: "1", color: getDistanceBandColor(1) },
      { label: "2", color: getDistanceBandColor(2) },
      { label: "3", color: getDistanceBandColor(3) },
      { label: "Outside", color: withAlpha(GRAPH_THEME.palette.overview.nodeMuted, 0.38) },
    ]
    : [
      { label: "0h", color: getDistanceBandColor(0) },
      { label: "1h", color: getDistanceBandColor(1) },
      { label: "2-3h", color: getDistanceBandColor(3) },
      { label: "4-6h", color: getDistanceBandColor(6) },
    ];

  return (
    <div className="palantir-bg" style={{ position: "relative", width: "100%", height: "100%", overflow: "hidden" }}>
      <style>{HUD_CSS}</style>
      <div className="palantir-grid" />
      <div className="palantir-vignette" />

      <div className="explore-shell">
        <section className="explore-command-deck">
          <SurfaceCard tone="subtle">
            <div style={{ display: "flex", flexDirection: "column", gap: 12 }}>
              <div className="explore-toolbar">
                <div className="explore-status-strip">
                  {(showLoadingOverlay || showSettlingStatus) && loadingProgress ? (
                    <MetricChip>{getGraphLoadTitle(loadingProgress.phase)}</MetricChip>
                  ) : null}
                  {summary ? (
                    <MetricChip>{summary.nodeCount.toLocaleString()} nodes · {summary.edgeCount.toLocaleString()} edges</MetricChip>
                  ) : null}
                  {activeNodeCount !== null ? (
                    <MetricChip tone="success">{activeNodeCount.toLocaleString()} active</MetricChip>
                  ) : null}
                  {focusedSummary ? <MetricChip tone="warm">{focusedSummary}</MetricChip> : null}
                </div>
                <div className="explore-workflow-bar">
                  <SearchCommandBar
                    value={searchQuery}
                    disabled={searchDisabled}
                    onChange={setSearchQuery}
                    onSubmit={() => void handleSearch()}
                  />
                  <SegmentedModeControl items={viewModeItems} />
                  <div className="explore-toolbelt">
                    {toolbarClusters.map((group) => (
                      <ToolbarCluster
                        key={group.id}
                        label={group.label ?? group.id}
                        items={group.items}
                        compact={COMPACT_TOOLBAR_CLUSTER_IDS.has(group.id)}
                      />
                    ))}
                  </div>
                </div>
                <EntityVisualKey />
              </div>

              {egoModeEnabled && (
                <div style={{ display: "flex", alignItems: "center", gap: 10, fontSize: 12, color: "#a0b4cc" }}>
                  <span style={{ fontWeight: 600, color: "#79c0ff" }}>Ego depth:</span>
                  <input
                    type="range"
                    min={1}
                    max={8}
                    value={egoMaxHops}
                    onChange={(e) => setEgoMaxHops(Number(e.target.value))}
                    style={{ width: 90, accentColor: "#79c0ff" }}
                    title={`Ego depth: ${egoMaxHops} hops`}
                  />
                  <span style={{ fontFamily: "monospace", color: "#e6f2ff" }}>{egoMaxHops} hop{egoMaxHops !== 1 ? "s" : ""}</span>
                </div>
              )}

              {showDistanceStatus ? (
                <div style={distanceStatusStripStyle}>
                  <div style={distanceStatusTitleStyle}>
                    <Activity size={14} aria-hidden />
                    <span>Distance Intelligence</span>
                    <span style={distanceModeBadgeStyle}>{distanceVisualState.mode}</span>
                  </div>
                  <div style={distanceStatusMetaStyle}>
                    {distanceVisualState.anchorLabel ? (
                      <span>Anchor: <strong>{distanceVisualState.anchorLabel}</strong></span>
                    ) : null}
                    {distanceVisualState.mode === "semantic" ? (
                      <span>
                        {distanceVisualState.status === "loading"
                          ? "Loading semantic neighborhood..."
                          : `${distanceVisualState.semanticNeighborCount ?? 0} semantic neighbors`}
                      </span>
                    ) : distanceVisualState.mode === "heatmap" ? (
                      <span>{heatmapDistanceSummary}</span>
                    ) : (
                      <span>{distanceReachableCount.toLocaleString()} nodes within {distanceVisualState.maxHops} hops</span>
                    )}
                    {distanceVisualState.status === "unavailable" || distanceVisualState.status === "error" ? (
                      <span style={{ color: GRAPH_THEME.ui.control.dangerText }}>{distanceVisualState.error}</span>
                    ) : null}
                    {heatmapRenderedSummary ? (
                      <span style={{ color: GRAPH_THEME.ui.text.muted }}>{heatmapRenderedSummary}</span>
                    ) : null}
                  </div>
                  <div style={distanceLegendStyle}>
                    {distanceLegendItems.map((item) => (
                      <span key={item.label} style={distanceLegendItemStyle}>
                        <span style={{ ...distanceLegendSwatchStyle, background: item.color }} />
                        {item.label}
                      </span>
                    ))}
                  </div>
                </div>
              ) : null}

              {searchError ? <div style={{ color: "#ff7b72", fontSize: 12 }}>{searchError}</div> : null}

              {searchResults.length ? (
                <div className="explore-search-results hud-scrollbar" style={searchResultsStripStyle}>
                  {searchResults.map((result) => (
                    <button key={result.node.id} style={predictionCardStyle} onClick={() => focusNode(result.node.id)}>
                      <div style={{ display: "flex", justifyContent: "space-between", gap: 12 }}>
                        <div style={{ minWidth: 0 }}>
                          <div style={{ color: "#fff", fontWeight: 600 }}>{result.node.content || result.node.id}</div>
                          <div style={{ color: "#8b949e", fontSize: 12 }}>{result.node.type}</div>
                        </div>
                        <div style={{ color: "#58a6ff", fontSize: 12, whiteSpace: "nowrap" }}>
                          {result.score.toFixed(3)}
                        </div>
                      </div>
                    </button>
                  ))}
                </div>
              ) : null}

              {selectedEdgeState ? (
                <div style={selectedEdgeCardStyle}>
                  <div style={{ display: "flex", justifyContent: "space-between", gap: 12, alignItems: "flex-start" }}>
                    <div style={{ minWidth: 0 }}>
                      <div style={{ color: "rgba(127, 208, 255, 0.76)", fontSize: 11, fontWeight: 700, letterSpacing: "0.08em", textTransform: "uppercase" }}>
                        Relationship
                      </div>
                      <div style={{ color: "#f4f8ff", fontSize: 15, fontWeight: 700, marginTop: 6 }}>
                        {selectedEdgeState.edgeType}
                      </div>
                    </div>
                    <button
                      onClick={() => setSelectedEdgeId("")}
                      style={{ ...secondaryActionButtonStyle, minHeight: 30, padding: "6px 10px" }}
                    >
                      Close
                    </button>
                  </div>

                  <div style={{ display: "flex", alignItems: "center", gap: 10, flexWrap: "wrap" }}>
                    <button style={selectedEdgeNodeChipStyle} onClick={() => focusNode(selectedEdgeState.sourceId)}>
                      {selectedEdgeState.sourceLabel}
                    </button>
                    <span style={{ color: "#7fa7ce", fontSize: 12 }}>→</span>
                    <button style={selectedEdgeNodeChipStyle} onClick={() => focusNode(selectedEdgeState.targetId)}>
                      {selectedEdgeState.targetLabel}
                    </button>
                  </div>

                  <div style={{ display: "flex", gap: 8, flexWrap: "wrap" }}>
                    <MetricChip tone="warm">weight {selectedEdgeState.weight.toFixed(2)}</MetricChip>
                    {selectedEdgeState.isAggregated ? (
                      <MetricChip tone="success">
                        {selectedEdgeState.aggregateCount} bundled edge{selectedEdgeState.aggregateCount === 1 ? "" : "s"}
                      </MetricChip>
                    ) : (
                      <MetricChip>{selectedEdgeState.siblingCount} parallel lane{selectedEdgeState.siblingCount === 1 ? "" : "s"}</MetricChip>
                    )}
                    <MetricChip>{selectedEdgeState.familySize} family member{selectedEdgeState.familySize === 1 ? "" : "s"}</MetricChip>
                    {selectedEdgeState.bundleKind ? (
                      <MetricChip>{selectedEdgeState.bundleKind} bundle</MetricChip>
                    ) : null}
                    {selectedEdgeState.dominantEdgeType ? (
                      <MetricChip>{selectedEdgeState.dominantEdgeType}</MetricChip>
                    ) : null}
                    {selectedEdgeState.provenanceCount > 0 ? (
                      <MetricChip>{selectedEdgeState.provenanceCount} provenance fields</MetricChip>
                    ) : null}
                  </div>

                  {Object.keys(selectedEdgeState.properties).length ? (
                    <div style={selectedEdgePropertyGridStyle}>
                      {Object.entries(selectedEdgeState.properties).slice(0, 4).map(([key, value]) => (
                        <div key={key} style={selectedEdgePropertyCardStyle}>
                          <div style={{ color: "rgba(127, 208, 255, 0.68)", fontSize: 10, letterSpacing: "0.06em", textTransform: "uppercase" }}>
                            {key}
                          </div>
                          <div style={{ color: "#dce7f4", fontSize: 12, marginTop: 4, wordBreak: "break-word" }}>
                            {typeof value === "object" ? JSON.stringify(value) : String(value)}
                          </div>
                        </div>
                      ))}
                    </div>
                  ) : null}
                </div>
              ) : null}
            </div>
          </SurfaceCard>
        </section>

        <div
          className="explore-main-grid"
          style={{
            gridTemplateColumns: layoutState.showInspector ? "minmax(0, 1fr) minmax(320px, 360px)" : "minmax(0, 1fr)",
          }}
        >
          <div className="explore-scene-stack">
            <SurfaceCard padding="none" className="explore-scene-card">
              <div className="explore-scene-shell">
                <div className="palantir-grid" />
                <div className="palantir-vignette" />
                <div className="explore-scene-stage">
                  <SigmaSceneAdapter
                    ref={sceneRef}
                    {...sceneAdapterProps}
                  />
                  <GraphLoadingOverlay
                    progress={loadingProgress}
                    visible={showLoadingOverlay}
                    showGraphBehind={hasGraphContent || Boolean(loadingProgress?.showGraphBehind)}
                  />
                </div>
              </div>

              {layoutState.showPluginDock ? (
                <div className="explore-plugin-dock">
                  <SurfaceCard tone="subtle" style={{ borderRadius: 0, borderLeft: "none", borderRight: "none", borderBottom: "none" }}>
                    <div style={{ display: "flex", flexDirection: "column", gap: 10 }}>
                      <div style={{ display: "flex", justifyContent: "space-between", gap: 12, alignItems: "center" }}>
                        <div className="explore-plugin-dock-tabs">
                          {openDockPanels.map((panel) => (
                            <button
                              key={panel.id}
                              className="explore-plugin-dock-tab"
                              data-active={activeDockPanel?.id === panel.id}
                              onClick={() => setActiveDockPanelId(panel.id)}
                            >
                              {panel.title}
                            </button>
                          ))}
                          {activeDockPanel ? (
                            <button
                              className="explore-plugin-dock-tab"
                              onClick={() => handlePluginAction({ type: "closePanel", panelId: activeDockPanel.id })}
                            >
                              ×
                            </button>
                          ) : null}
                        </div>
                      </div>
                      {activeDockPanel ? (
                        <div style={pluginDockContentStyle}>{activeDockPanel.content}</div>
                      ) : null}
                    </div>
                  </SurfaceCard>
                </div>
              ) : null}

              <div className="explore-scene-footer">
                <Suspense fallback={<div style={timelineFallbackStyle}>Loading timeline…</div>}>
                  <LazyTimelinePanel
                    onTimeChange={setScrubberTime}
                    minDate={temporalBounds?.min ?? undefined}
                    maxDate={temporalBounds?.max ?? undefined}
                  />
                </Suspense>
              </div>
            </SurfaceCard>
          </div>

          {layoutState.showInspector ? (
            <div className="explore-inspector-shell">
              <InspectorPanel open={layoutState.showInspector} className="explore-inspector-card">
                <div className="explore-inspector-scroll hud-scrollbar">
                  <Suspense fallback={<div style={inspectorFallbackStyle}>Loading inspector…</div>}>
                    <LazyGraphInspectorPanel
                      nodeId={selectedNodeId}
                      inspectableNodeId={inspectableNodeId || null}
                      selectedNodeKind={displayState.selectedNodeKind}
                      canActivateFocused={canActivateFocusedMode}
                      focusedUnavailableReason={displayState.focusedUnavailableReason}
                      predictions={predictions}
                      predictionType={predictionType}
                      onPredictionTypeChange={setPredictionType}
                      onRunPredictions={() => void handleRunPredictions()}
                      isRunningPredictions={isRunningPredictions}
                      pathTargetId={pathTargetId}
                      onPathTargetChange={setPathTargetId}
                      onTracePath={() => void handleTracePath()}
                      pathResult={pathResult}
                      onDownloadProvenance={(format) => void handleDownloadProvenance(format)}
                      onFocusNode={focusNode}
                    />
                  </Suspense>
                </div>
              </InspectorPanel>
            </div>
          ) : null}
        </div>
      </div>
    </div>
  );
}

const actionButtonStyle: React.CSSProperties = {
  background: GRAPH_THEME.ui.control.primaryBg,
  color: GRAPH_THEME.ui.control.primaryText,
  border: `1px solid ${GRAPH_THEME.ui.control.primaryBorder}`,
  borderRadius: 12,
  padding: "9px 12px",
  cursor: "pointer",
  fontWeight: 700,
  fontSize: 12,
  display: "inline-flex",
  alignItems: "center",
  justifyContent: "center",
  boxShadow: "inset 0 1px 0 rgba(255,255,255,0.07), 0 10px 24px rgba(0,0,0,0.18)",
};

const secondaryActionButtonStyle: React.CSSProperties = {
  ...actionButtonStyle,
  background: GRAPH_THEME.ui.control.defaultBg,
  border: `1px solid ${GRAPH_THEME.ui.control.defaultBorder}`,
  color: GRAPH_THEME.ui.control.defaultText,
  fontWeight: 600,
};

const predictionCardStyle: React.CSSProperties = {
  textAlign: "left",
  padding: 12,
  background: "rgba(255, 255, 255, 0.035)",
  border: `1px solid ${GRAPH_THEME.ui.surface.panelBorder}`,
  borderRadius: 10,
  cursor: "pointer",
};

const selectedEdgeCardStyle: React.CSSProperties = {
  display: "flex",
  flexDirection: "column",
  gap: 12,
  padding: 14,
  background: "linear-gradient(135deg, rgba(98, 226, 205, 0.1), rgba(233, 196, 122, 0.045))",
  border: `1px solid ${GRAPH_THEME.ui.surface.panelBorder}`,
  borderRadius: 14,
  boxShadow: "inset 0 1px 0 rgba(255,255,255,0.03)",
};

const selectedEdgeNodeChipStyle: React.CSSProperties = {
  ...secondaryActionButtonStyle,
  minHeight: 32,
  padding: "7px 12px",
  whiteSpace: "nowrap",
};

const distanceStatusStripStyle: React.CSSProperties = {
  display: "flex",
  alignItems: "center",
  gap: 12,
  flexWrap: "wrap",
  border: `1px solid ${GRAPH_THEME.ui.control.activeBorder}`,
  background: "linear-gradient(135deg, rgba(98, 226, 205, 0.09), rgba(227, 179, 65, 0.045))",
  borderRadius: 16,
  padding: "9px 12px",
  boxShadow: "inset 0 1px 0 rgba(255,255,255,0.045)",
};

const distanceStatusTitleStyle: React.CSSProperties = {
  display: "flex",
  alignItems: "center",
  gap: 7,
  color: GRAPH_THEME.ui.text.strong,
  fontSize: 12,
  fontWeight: 800,
  letterSpacing: "0.04em",
  textTransform: "uppercase",
};

const distanceModeBadgeStyle: React.CSSProperties = {
  padding: "2px 7px",
  borderRadius: 999,
  border: `1px solid ${GRAPH_THEME.ui.surface.panelBorder}`,
  color: GRAPH_THEME.palette.accent.path,
  background: "rgba(215, 144, 86, 0.1)",
  fontSize: 10,
};

const distanceStatusMetaStyle: React.CSSProperties = {
  display: "flex",
  alignItems: "center",
  gap: 10,
  flexWrap: "wrap",
  color: GRAPH_THEME.ui.text.body,
  fontSize: 12,
};

const distanceLegendStyle: React.CSSProperties = {
  display: "flex",
  alignItems: "center",
  gap: 8,
  marginLeft: "auto",
  color: GRAPH_THEME.ui.text.muted,
  fontSize: 11,
};

const distanceLegendItemStyle: React.CSSProperties = {
  display: "inline-flex",
  alignItems: "center",
  gap: 4,
};

const distanceLegendSwatchStyle: React.CSSProperties = {
  width: 8,
  height: 8,
  borderRadius: 999,
};

const selectedEdgePropertyGridStyle: React.CSSProperties = {
  display: "grid",
  gridTemplateColumns: "repeat(auto-fit, minmax(160px, 1fr))",
  gap: 8,
};

const selectedEdgePropertyCardStyle: React.CSSProperties = {
  borderRadius: 10,
  padding: 10,
  background: "rgba(255, 255, 255, 0.03)",
  border: `1px solid ${GRAPH_THEME.ui.surface.panelBorder}`,
};

const pluginDockContentStyle: React.CSSProperties = {
  borderRadius: 16,
  border: `1px solid ${GRAPH_THEME.ui.surface.panelBorder}`,
  background: "rgba(255, 255, 255, 0.02)",
  padding: 14,
};

const pluginLoadingStyle: React.CSSProperties = {
  color: GRAPH_THEME.ui.text.muted,
  fontSize: 12,
  padding: 10,
};

const searchResultsStripStyle: React.CSSProperties = {
  display: "grid",
  gridTemplateColumns: "repeat(auto-fit, minmax(220px, 1fr))",
  gap: 10,
  maxHeight: 186,
  overflowY: "auto",
};

const inspectorFallbackStyle: React.CSSProperties = {
  padding: 24,
  color: GRAPH_THEME.ui.text.muted,
  fontSize: 12,
};

const timelineFallbackStyle: React.CSSProperties = {
  height: "90px",
  display: "flex",
  alignItems: "center",
  padding: "0 18px",
  color: GRAPH_THEME.ui.text.muted,
  fontSize: 12,
  borderTop: `1px solid ${GRAPH_THEME.ui.timeline.border}`,
  background: GRAPH_THEME.ui.timeline.background,
};
