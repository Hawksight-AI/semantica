import type { ReactNode } from "react";
import type Graph from "graphology";

import { graph, type EdgeAttributes, type NodeAttributes } from "../../../store/graphStore";
import type { GraphTheme } from "../graphTheme";
import type { GraphSceneRuntime } from "../scene";
import type {
  GraphAnalyticsSnapshot,
  GraphDisplayStateSnapshot,
  GraphDiagnosticsSnapshot,
  GraphEffectsState,
  GraphEffectToggle,
  GraphInteractionState,
  GraphLoadSummary,
  GraphSelectedNodeState,
  GraphTemporalState,
  GraphViewMode,
} from "../types";

export type { GraphTemporalState } from "../types";

export type GraphTranslateFn = (key: string, vars?: Record<string, string | number>) => string;

/**
 * Maps the English `reason` strings emitted by pure graph modules
 * (graphAnalytics, graphSceneState, GraphCanvas effect availability) to i18n
 * keys. Render sites call `localizeReason(t, reason)`; unknown reasons fall
 * back to the raw English string so nothing is ever dropped.
 */
export const graphReasonKeys: Record<string, string> = {
  "Community anchor": "graph.reason.communityAnchor",
  "No visible nodes are available for overview backbone selection.": "graph.reason.overviewNoVisible",
  "Ready": "graph.reason.ready",
  "No overview backbone edges met the current visibility thresholds.": "graph.reason.overviewNoEdges",
  "Trace a path to compare it against local strict directed shortest pathfinding.": "graph.reason.tracePathHint",
  "Active path endpoints are not available in the current graph view.": "graph.reason.activePathEndpointsUnavailable",
  "No strict directed shortest path found in the current graph view.": "graph.reason.noStrictPath",
  "Directed pathfinding failed for the current graph snapshot.": "graph.reason.directedPathfindingFailed",
  "No visible communities in the current graph context.": "graph.reason.noVisibleCommunities",
  "Community detection has not produced summaries yet.": "graph.reason.communityNotReady",
  "Ready (degree-biased while betweenness is bounded for large graphs).": "graph.reason.readyDegreeBiased",
  "Centrality ranking is waiting for graph data.": "graph.reason.centralityWaiting",
  "No semantic regions are visible in the current graph context.": "graph.reason.noSemanticRegions",
  "Selected item is not available in the current graph.": "graph.reason.itemUnavailable",
  "Grouped view is unavailable until communities can be detected.": "graph.reason.groupedUnavailableCommunities",
  "Grouped view is unavailable because no community nodes could be created.": "graph.reason.groupedUnavailableNoNodes",
  "Layout is still settling": "graph.effect.layoutSettling",
  "Disabled by toggle": "graph.effect.disabledByToggle",
  "No active path": "graph.effect.noActivePath",
  "Disabled by zoom tier": "graph.effect.disabledByZoomTier",
  "Path is off-screen": "graph.effect.pathOffScreen",
  "Disabled by path size cap": "graph.effect.disabledByPathSizeCap",
  "No focal node": "graph.effect.noFocalNode",
  "No temporal focus time": "graph.effect.noTemporalFocus",
  "Waiting for semantic region summaries": "graph.effect.waitingSemanticRegions",
  "Waiting for centrality ranking": "graph.effect.waitingCentrality",
  "Waiting for a traced path": "graph.effect.waitingTracedPath",
  "Waiting for community summaries": "graph.effect.waitingCommunitySummaries",
  "Panel enabled": "graph.effect.panelEnabled",
  "Disabled in production": "graph.effect.disabledInProduction",
  "Waiting for graph runtime": "graph.plugins.waitingRuntime",
};

export function localizeReason(t: GraphTranslateFn, reason: string | null | undefined): string | null {
  if (!reason) {
    return null;
  }
  const key = graphReasonKeys[reason];
  return key ? t(key) : reason;
}

/**
 * Well-known relationship (edge type) names -> i18n dictionary keys.
 *
 * Keys are matched case-insensitively; unknown types fall back to their raw
 * string so existing graphs render unchanged until a translation is added.
 */
const EDGE_TYPE_KEYS: Record<string, string> = {
  related_to: "graph.edgeTypes.relatedTo",
  related: "graph.edgeTypes.related",
  belongs_to: "graph.edgeTypes.belongsTo",
  involves: "graph.edgeTypes.involves",
  made_by: "graph.edgeTypes.madeBy",
  caused_by: "graph.edgeTypes.causedBy",
  causes: "graph.edgeTypes.causes",
  influences: "graph.edgeTypes.influences",
  influence: "graph.edgeTypes.influences",
  precedent_for: "graph.edgeTypes.precedentFor",
  part_of: "graph.edgeTypes.partOf",
  has_part: "graph.edgeTypes.hasPart",
  is_a: "graph.edgeTypes.isA",
  instance_of: "graph.edgeTypes.instanceOf",
  same_as: "graph.edgeTypes.sameAs",
  located_in: "graph.edgeTypes.locatedIn",
  contains: "graph.edgeTypes.contains",
  produced_by: "graph.edgeTypes.producedBy",
  used_by: "graph.edgeTypes.usedBy",
  derived_from: "graph.edgeTypes.derivedFrom",
  wasderivedfrom: "graph.edgeTypes.wasDerivedFrom",
  wasgeneratedby: "graph.edgeTypes.wasGeneratedBy",
  used: "graph.edgeTypes.used",
  wasassociatedwith: "graph.edgeTypes.wasAssociatedWith",
  actedonbehalfof: "graph.edgeTypes.actedOnBehalfOf",
  parent_of: "graph.edgeTypes.parentOf",
  child_of: "graph.edgeTypes.childOf",
  references: "graph.edgeTypes.references",
  cites: "graph.edgeTypes.cites",
};

export function translateEdgeType(
  t: GraphTranslateFn,
  edgeType: string | null | undefined,
): string {
  if (!edgeType) {
    return "";
  }
  const raw = String(edgeType);
  const key = EDGE_TYPE_KEYS[raw.toLowerCase()] ?? EDGE_TYPE_KEYS[raw];
  if (!key) {
    return raw;
  }
  const translated = t(key);
  return translated === key ? raw : translated;
}

export type GraphPluginId = string;
export type GraphPluginPanelPlacement = "side" | "bottom";

export interface GraphInspectorState {
  selectedNodeId: string | null;
  ownsSelectionDetails: boolean;
}

export type GraphPluginActionRequest =
  | { type: "fitView" }
  | { type: "focusNode"; nodeId: string }
  | { type: "selectNode"; nodeId: string }
  | { type: "setViewMode"; viewMode: GraphViewMode }
  | { type: "collapseNeighborhood" }
  | { type: "expandNeighborhood" }
  | { type: "toggleEffect"; effect: GraphEffectToggle }
  | { type: "setEffect"; effect: GraphEffectToggle; enabled: boolean }
  | { type: "togglePanel"; panelId: string }
  | { type: "openPanel"; panelId: string }
  | { type: "closePanel"; panelId: string };

export interface GraphPluginToolbarItem {
  id: string;
  label: string;
  title?: string;
  active?: boolean;
  order?: number;
  onClick: () => void;
}

export interface GraphPluginPanelDescriptor {
  id: string;
  title: string;
  placement: GraphPluginPanelPlacement;
  order?: number;
  defaultOpen?: boolean;
  preferredHeight?: number;
  preferredWidth?: number;
  content: ReactNode;
}

export interface GraphPluginOverlayDescriptor {
  id: string;
  layer?: number;
  order?: number;
  element: ReactNode;
}

export interface GraphPluginContext {
  readonly t: GraphTranslateFn;
  readonly scene: GraphSceneRuntime | null;
  readonly graph: typeof graph | Graph<NodeAttributes, EdgeAttributes>;
  readonly displayGraph: typeof graph | Graph<NodeAttributes, EdgeAttributes>;
  readonly theme: GraphTheme;
  getInteractionState: () => GraphInteractionState;
  getSelectedNodeState: () => GraphSelectedNodeState | null;
  getInspectorState: () => GraphInspectorState;
  getGraphSummary: () => GraphLoadSummary | null;
  getTemporalState: () => GraphTemporalState | null;
  getEffectsState: () => GraphEffectsState;
  getDiagnosticsSnapshot: () => GraphDiagnosticsSnapshot | null;
  getAnalyticsSnapshot: () => GraphAnalyticsSnapshot | null;
  getDisplayState: () => GraphDisplayStateSnapshot;
  isPanelOpen: (panelId: string) => boolean;
  dispatchAction: (action: GraphPluginActionRequest) => void;
}

export interface GraphPlugin {
  id: GraphPluginId;
  mount: (context: GraphPluginContext) => void;
  unmount: (context: GraphPluginContext) => void;
  onStateChange: (context: GraphPluginContext, interactionState: GraphInteractionState) => void;
  renderOverlay?: (
    context: GraphPluginContext,
  ) => GraphPluginOverlayDescriptor | GraphPluginOverlayDescriptor[] | null;
  renderPanel?: (
    context: GraphPluginContext,
  ) => GraphPluginPanelDescriptor | GraphPluginPanelDescriptor[] | null;
  toolbarItems?: (context: GraphPluginContext) => GraphPluginToolbarItem[];
}

export interface GraphPluginRegistryEntry {
  plugin: GraphPlugin;
  enabled?: boolean;
}
