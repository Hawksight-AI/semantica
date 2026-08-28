import Graph from "graphology";
import type {
  GraphArrowVisibilityPolicy,
  GraphBadgeKind,
  GraphEdgeVariant,
  GraphEntityShapeVariant,
  GraphLabelVisibilityPolicy,
  GraphNodeShapeVariant,
} from "../workspaces/GraphWorkspace/graphTheme";
import { curveGroupForPair, pairRegistryKey } from "./edgePairKeys.js";


export const graph = new Graph({ 
  type: "directed", 
  multi: true, 
  allowSelfLoops: false 
});



export interface NodeAttributes {

  label: string;
  x: number;
  y: number;
  size: number;
  color: string;
  baseColor?: string;
  mutedColor?: string;
  glowColor?: string;
  baseSize?: number;
  visualPriority?: number;
  labelPriority?: number;
  semanticGroup?: string;
  strokeColor?: string;
  borderColor?: string;
  borderSize?: number;
  nodeVariant?: GraphNodeShapeVariant;
  nodeShapeVariant?: GraphNodeShapeVariant;
  entityShape?: GraphEntityShapeVariant;
  badgeKind?: GraphBadgeKind;
  badgeCount?: number;
  ringColor?: string;
  haloColor?: string;
  labelVisibilityPolicy?: GraphLabelVisibilityPolicy;
  highlighted?: boolean;
  communityId?: string;
  isCommunityGroup?: boolean;
  memberCount?: number;
  anchorNodeId?: string | null;

  nodeType: string;
  content: string;
  valid_from?: string | null;
  valid_until?: string | null;
  properties: Record<string, any>;
}

export interface EdgeAttributes {
  edgeId?: string;
  familyId?: string;
  sourceId?: string;
  targetId?: string;
 
  size?: number;
  baseSize?: number;
  color?: string;
  baseColor?: string;
  mutedColor?: string;
  type?: string;
  curvature?: number;
  visualPriority?: number;
  edgeFamily?: "line" | "parallel" | "bidirectional" | "path";
  isBidirectional?: boolean;
  curveGroup?: string | null;
  edgeVariant?: GraphEdgeVariant;
  arrowVisibilityPolicy?: GraphArrowVisibilityPolicy;
  relationshipStrength?: number;
  isParallelPair?: boolean;
  parallelIndex?: number;
  parallelCount?: number;
  familySize?: number;
  rawEdgeIds?: string[];
  isAggregated?: boolean;
  aggregateCount?: number;
  dominantEdgeType?: string;
  representativeWeight?: number;
  bundleKind?: "parallel" | "bidirectional" | "community";
  
 
  edgeType: string;
  weight: number;
  properties: Record<string, any>;
}

function normalizeParallelMetadataForPair(source: string, target: string): void {
  const edgeIds: string[] = [];
  graph.forEachDirectedEdge(source, target, (edgeId) => {
    edgeIds.push(String(edgeId));
  });

  const pairCount = edgeIds.length;
  const familyCounts = new Map<string, number>();
  edgeIds.forEach((edgeId) => {
    const attrs = graph.getEdgeAttributes(edgeId) as EdgeAttributes;
    const familyId = String(attrs.familyId || edgeId);
    familyCounts.set(familyId, (familyCounts.get(familyId) ?? 0) + 1);
  });

  edgeIds
    .sort((left, right) => {
      const leftAttrs = graph.getEdgeAttributes(left) as EdgeAttributes;
      const rightAttrs = graph.getEdgeAttributes(right) as EdgeAttributes;
      const priorityDelta = Number(rightAttrs.visualPriority ?? 0) - Number(leftAttrs.visualPriority ?? 0);
      if (priorityDelta !== 0) {
        return priorityDelta;
      }
      const weightDelta = Number(rightAttrs.weight ?? 0) - Number(leftAttrs.weight ?? 0);
      if (weightDelta !== 0) {
        return weightDelta;
      }
      return left.localeCompare(right);
    })
    .forEach((edgeId, index) => {
      const attrs = graph.getEdgeAttributes(edgeId) as EdgeAttributes;
      const familyId = String(attrs.familyId || edgeId);
      graph.mergeEdgeAttributes(edgeId, {
        edgeId,
        familyId,
        sourceId: source,
        targetId: target,
        isParallelPair: pairCount > 1,
        parallelIndex: index,
        parallelCount: pairCount,
        familySize: familyCounts.get(familyId) ?? 1,
        curveGroup: curveGroupForPair(source, target),
      });
    });
}


export function batchMergeNodes(
  nodes: { id: string; attributes: NodeAttributes }[]
): void {
  for (const { id, attributes } of nodes) {
    graph.mergeNode(id, attributes);
  }
}


export function batchMergeEdges(
  edges: { id: string; familyId?: string; source: string; target: string; attributes: EdgeAttributes }[]
): void {
  const touchedPairs = new Map<string, { source: string; target: string }>();

  for (const { id, familyId, source, target, attributes } of edges) {
    if (source === target) continue; // skip self-loops; graph was created with allowSelfLoops: false
    const edgeId = String(attributes.edgeId || id);
    const resolvedFamilyId = String(attributes.familyId || familyId || edgeId);

    if (graph.hasNode(source) && graph.hasNode(target)) {
      graph.mergeDirectedEdgeWithKey(edgeId, source, target, {
        ...attributes,
        edgeId,
        familyId: resolvedFamilyId,
        sourceId: source,
        targetId: target,
      });
      touchedPairs.set(pairRegistryKey(source, target), { source, target });
    }
  }

  touchedPairs.forEach(({ source, target }) => {
    normalizeParallelMetadataForPair(source, target);
  });
}

export function clearGraph(): void {
  graph.clear();
}
