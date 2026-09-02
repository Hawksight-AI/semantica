import type { EdgeAttributes } from "../../store/graphStore";
import { curveGroupForPair } from "../../store/edgePairKeys.js";
import { GRAPH_THEME } from "./graphTheme";

export type RealtimeEdgePayload = {
  id: string;
  familyId?: string;
  source_id: string;
  target_id: string;
  type?: string;
  weight?: number;
  properties?: Record<string, unknown>;
};

export function buildRealtimeEdgeAttributes(
  payload: RealtimeEdgePayload,
  options: { isBidirectional: boolean; isSmallGraph: boolean },
): EdgeAttributes {
  const properties = payload.properties || {};
  const isInferred = Boolean(properties.inferred);
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
    isBidirectional: options.isBidirectional,
    edgeFamily: isInferred ? "path" : options.isBidirectional ? "bidirectional" : "line",
    curveGroup: options.isBidirectional ? curveGroupForPair(payload.source_id, payload.target_id) : null,
    type: "line",
    edgeVariant: isInferred ? "pathSignal" : options.isBidirectional ? "bidirectionalCurve" : "directional",
    arrowVisibilityPolicy: isInferred ? "always" : "contextual",
    relationshipStrength: isInferred ? 0.95 : 0.52,
    isParallelPair: false,
    parallelIndex: 0,
    parallelCount: 1,
    familySize: 1,
    isSmallGraph: options.isSmallGraph,
  };
}
