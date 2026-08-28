import { useQuery, useQueryClient } from "@tanstack/react-query";
import { batchMergeEdges, batchMergeNodes, clearGraph } from "../../store/graphStore";
import type { EdgeAttributes, NodeAttributes } from "../../store/graphStore";
import { curveGroupForPair, pairRegistryKey } from "../../store/edgePairKeys.js";
import {
  GRAPH_THEME,
  clamp,
  darkenHex,
  hashString,
  withAlpha,
  type GraphBadgeKind,
  type GraphEdgeVariant,
  type GraphEntityShapeVariant,
  type GraphLabelVisibilityPolicy,
  type GraphNodeShapeVariant,
} from "./graphTheme";
import { classifyEntityShape } from "./graphEntityShape";
import { createGraphLoadProgress } from "./graphLoading";
import type { GraphLoadProgress, GraphLoadSummary } from "./types";

const SEMANTIC_COLOR_FIELDS = [
  "community",
  "cluster",
  "module",
  "group",
  "category",
  "domain",
  "layer",
  "source",
  "nodeType",
] as const;

const PROVENANCE_KEYS = ["source", "source_url", "pmid", "pmids", "evidence", "provenance", "confidence"] as const;

function getSemanticFieldValue(attributes: NodeAttributes, field: (typeof SEMANTIC_COLOR_FIELDS)[number]): string | null {
  if (field === "nodeType") {
    const value = attributes.nodeType;
    return typeof value === "string" && value.trim() ? value : null;
  }

  const value = attributes.properties?.[field];
  return typeof value === "string" && value.trim() ? value : null;
}

function normalizedEntropy(counts: number[], total: number): number {
  if (counts.length <= 1 || total <= 0) {
    return 0;
  }

  let entropy = 0;
  for (const count of counts) {
    const probability = count / total;
    entropy -= probability * Math.log(probability);
  }

  return entropy / Math.log(counts.length);
}

function chooseColorAccessor(
  nodes: Array<{ id: string; attributes: NodeAttributes }>,
): (nodeId: string, attributes: NodeAttributes) => string {
  let bestField: (typeof SEMANTIC_COLOR_FIELDS)[number] | null = null;
  let bestScore = 0;

  for (const field of SEMANTIC_COLOR_FIELDS) {
    const counts = new Map<string, number>();
    let covered = 0;

    for (const node of nodes) {
      const value = getSemanticFieldValue(node.attributes, field);
      if (!value) {
        continue;
      }
      covered += 1;
      counts.set(value, (counts.get(value) ?? 0) + 1);
    }

    const uniqueCount = counts.size;
    if (covered === 0 || uniqueCount <= 1) {
      continue;
    }

    const countValues = [...counts.values()];
    const coverage = covered / nodes.length;
    const dominantRatio = Math.max(...countValues) / covered;
    const entropy = normalizedEntropy(countValues, covered);
    const diversity = Math.min(uniqueCount, GRAPH_THEME.palette.semantic.length) / GRAPH_THEME.palette.semantic.length;
    const score = entropy * 0.65 + diversity * 0.2 + coverage * 0.15;

    const isInformative =
      coverage >= 0.45 &&
      entropy >= 0.45 &&
      dominantRatio <= 0.88;

    if (!isInformative) {
      continue;
    }

    if (score > bestScore) {
      bestField = field;
      bestScore = score;
    }
  }

  if (bestField) {
    return (_nodeId: string, attributes: NodeAttributes) =>
      getSemanticFieldValue(attributes, bestField) ?? structuralColorKey(_nodeId, attributes);
  }

  return (nodeId: string, attributes: NodeAttributes) => structuralColorKey(nodeId, attributes);
}

function structuralColorKey(nodeId: string, attributes: NodeAttributes): string {
  const shard = hashString(nodeId) % GRAPH_THEME.palette.semantic.length;
  return `${attributes.nodeType || "entity"}:${shard}`;
}

function readFiniteCoordinate(value: unknown): number | null {
  const numeric = Number(value);
  return Number.isFinite(numeric) ? numeric : null;
}

function seededUnit(value: string): number {
  return (hashString(value) % 10000) / 10000;
}

function buildClusterSeedPositions(
  nodes: Array<{
    id: string;
    semanticGroup: string;
    priority: number;
  }>,
): Map<string, { x: number; y: number }> {
  const grouped = new Map<string, Array<{ id: string; priority: number }>>();
  nodes.forEach((node) => {
    const entry = grouped.get(node.semanticGroup);
    if (entry) {
      entry.push({ id: node.id, priority: node.priority });
    } else {
      grouped.set(node.semanticGroup, [{ id: node.id, priority: node.priority }]);
    }
  });

  const groupEntries = [...grouped.entries()]
    .sort((left, right) => {
      const countDelta = right[1].length - left[1].length;
      if (countDelta !== 0) {
        return countDelta;
      }
      return left[0].localeCompare(right[0]);
    });

  const groupCenters = new Map<string, { x: number; y: number; spread: number }>();
  groupEntries.forEach(([group, members], index) => {
    const angle = index * 2.399963229728653;
    const radius = 170 + Math.sqrt(index + 1) * 195;
    const spread = 72 + Math.sqrt(members.length) * 16;
    groupCenters.set(group, {
      x: Math.cos(angle) * radius * 1.14,
      y: Math.sin(angle) * radius * 0.84,
      spread,
    });
  });

  const seeded = new Map<string, { x: number; y: number }>();
  groupEntries.forEach(([group, members]) => {
    const center = groupCenters.get(group);
    if (!center) {
      return;
    }

    members
      .sort((left, right) => {
        if (right.priority !== left.priority) {
          return right.priority - left.priority;
        }
        return left.id.localeCompare(right.id);
      })
      .forEach((member, index) => {
        const angle = index * 2.399963229728653 + seededUnit(`${group}:${member.id}:angle`) * 0.72;
        const radial = Math.sqrt((index + 0.5) / Math.max(members.length, 1)) * center.spread;
        const jitterX = (seededUnit(`${member.id}:jx`) - 0.5) * center.spread * 0.22;
        const jitterY = (seededUnit(`${member.id}:jy`) - 0.5) * center.spread * 0.18;
        seeded.set(member.id, {
          x: center.x + Math.cos(angle) * radial + jitterX,
          y: center.y + Math.sin(angle) * radial * 0.86 + jitterY,
        });
      });
  });

  return seeded;
}

function getProvenanceCount(properties: Record<string, unknown>): number {
  return PROVENANCE_KEYS.reduce(
    (count, key) => (properties[key] !== undefined && properties[key] !== null ? count + 1 : count),
    0,
  );
}

function resolveEntityShape(attributes: NodeAttributes, semanticGroup: string): GraphEntityShapeVariant {
  return classifyEntityShape(
    attributes.nodeType,
    semanticGroup,
    attributes.content,
    attributes.properties as Record<string, unknown> | undefined,
  );
}

function resolveNodeVariantMetadata(
  baseColor: string,
  sizeRatio: number,
  hasTemporalBounds: boolean,
  provenanceCount: number,
): Pick<
  NodeAttributes,
  "nodeVariant" | "nodeShapeVariant" | "badgeKind" | "badgeCount" | "ringColor" | "haloColor" | "labelVisibilityPolicy"
> {
  let nodeShapeVariant: GraphNodeShapeVariant = "default";
  let badgeKind: GraphBadgeKind | undefined;
  let badgeCount: number | undefined;

  if (hasTemporalBounds) {
    nodeShapeVariant = "temporal";
    badgeKind = "temporal";
  } else if (provenanceCount > 0) {
    nodeShapeVariant = "provenance";
    badgeKind = "provenance";
    badgeCount = provenanceCount;
  }

  let labelVisibilityPolicy: GraphLabelVisibilityPolicy = "none";
  if (sizeRatio >= 0.86) {
    labelVisibilityPolicy = "always";
  } else if (badgeKind) {
    labelVisibilityPolicy = "local";
  } else if (sizeRatio >= 0.56) {
    labelVisibilityPolicy = "priority";
  }

  return {
    nodeVariant: nodeShapeVariant,
    nodeShapeVariant,
    badgeKind,
    badgeCount,
    ringColor: GRAPH_THEME.nodes.selectedRing.color,
    haloColor: withAlpha(baseColor, 0.38),
    labelVisibilityPolicy,
  };
}

function resolveEdgeVariantMetadata(
  edge: ApiEdge,
  sourcePriority: number,
  targetPriority: number,
  isBidirectional: boolean,
): Pick<
  EdgeAttributes,
  "edgeVariant" | "arrowVisibilityPolicy" | "relationshipStrength" | "isParallelPair" | "parallelIndex" | "parallelCount"
> {
  const relationshipStrength = clamp(
    0.12,
    0.18 + Math.log(Math.max(Number(edge.weight) || 1, 1)) / Math.log(12),
    1,
  );

  let edgeVariant: GraphEdgeVariant = "line";
  if (isBidirectional) {
    edgeVariant = "bidirectionalCurve";
  } else if (Math.max(sourcePriority, targetPriority, relationshipStrength) >= 0.58) {
    edgeVariant = "directional";
  }

  return {
    edgeVariant,
    arrowVisibilityPolicy: edgeVariant === "line" ? "hidden" : "contextual",
    relationshipStrength,
    isParallelPair: false,
    parallelIndex: 0,
    parallelCount: 1,
  };
}

interface ApiNode {
  id: string;
  type: string;
  content: string;
  properties: Record<string, unknown>;
  valid_from?: string | null;
  valid_until?: string | null;
}

interface ApiEdge {
  id: string;
  familyId: string;
  source: string;
  target: string;
  type: string;
  weight: number;
  properties: Record<string, unknown>;
}

interface NodeListResponse {
  nodes: ApiNode[];
  total: number;
  skip: number;
  limit: number;
  next_cursor?: string | null;
}

interface EdgeListResponse {
  edges: ApiEdge[];
  total: number;
  skip: number;
  limit: number;
  next_cursor?: string | null;
}

const PAGE_LIMIT = 1000;

async function fetchAllNodes(
  signal: AbortSignal,
  onProgress?: (progress: GraphLoadProgress) => void,
): Promise<ApiNode[]> {
  let cursor: string | null = null;
  const collected: ApiNode[] = [];
  let total: number | null = null;

  while (true) {
    const url = new URL("/api/graph/nodes", window.location.origin);
    url.searchParams.set("limit", String(PAGE_LIMIT));
    if (cursor) {
      url.searchParams.set("cursor", cursor);
    }

    const response = await fetch(url.toString(), { signal });
    if (!response.ok) {
      throw new Error(`Fetch failed: ${response.status}`);
    }

    const data: NodeListResponse = await response.json();
    if (!data.nodes?.length) {
      break;
    }

    total = data.total ?? total;
    collected.push(...data.nodes);
    onProgress?.(createGraphLoadProgress({
      phase: "fetching_nodes",
      progressKind: total ? "determinate" : "indeterminate",
      loaded: collected.length,
      total,
      nodesLoaded: collected.length,
      nodesTotal: total,
      edgesLoaded: 0,
      edgesTotal: null,
      message: total
        ? `Loading nodes ${collected.length.toLocaleString()} of ${total.toLocaleString()}`
        : `Loading nodes ${collected.length.toLocaleString()}`,
    }));

    if (!data.next_cursor) {
      break;
    }
    cursor = data.next_cursor;
    await yieldToMain();
  }

  return collected;
}

async function fetchAllEdges(
  signal: AbortSignal,
  nodeIds: Set<string>,
  nodeProgress: { loaded: number; total: number | null },
  onProgress?: (progress: GraphLoadProgress) => void,
): Promise<ApiEdge[]> {
  let cursor: string | null = null;
  const collected: ApiEdge[] = [];
  const seenEdgeIds = new Set<string>();
  let total: number | null = null;
  let warnedOverTotal = false;

  while (true) {
    const url = new URL("/api/graph/edges", window.location.origin);
    url.searchParams.set("limit", String(PAGE_LIMIT));
    if (cursor) {
      url.searchParams.set("cursor", cursor);
    }

    const response = await fetch(url.toString(), { signal });
    if (!response.ok) {
      throw new Error(`Fetch failed: ${response.status}`);
    }

    const data: EdgeListResponse = await response.json();
    if (!data.edges?.length) {
      break;
    }

    total = data.total ?? total;
    const validEdges = data.edges.filter((edge) => {
      if (!nodeIds.has(edge.source) || !nodeIds.has(edge.target)) {
        return false;
      }
      if (seenEdgeIds.has(edge.id)) {
        return false;
      }
      seenEdgeIds.add(edge.id);
      return true;
    });
    collected.push(...validEdges);
    const safeLoaded = total ? Math.min(seenEdgeIds.size, total) : seenEdgeIds.size;
    if (!warnedOverTotal && total !== null && seenEdgeIds.size > total) {
      warnedOverTotal = true;
      console.warn("[graph-load] edge pagination returned more unique edge ids than total", {
        uniqueEdgesLoaded: seenEdgeIds.size,
        total,
      });
    }
    onProgress?.(createGraphLoadProgress({
      phase: "fetching_edges",
      progressKind: total ? "determinate" : "indeterminate",
      loaded: safeLoaded,
      total,
      nodesLoaded: nodeProgress.loaded,
      nodesTotal: nodeProgress.total,
      edgesLoaded: safeLoaded,
      edgesTotal: total,
      message: total
        ? `Loading edges ${safeLoaded.toLocaleString()} of ${total.toLocaleString()}`
        : `Loading edges ${safeLoaded.toLocaleString()}`,
    }));

    if (!data.next_cursor) {
      break;
    }
    cursor = data.next_cursor;
    await yieldToMain();
  }

  return collected;
}

function yieldToMain(): Promise<void> {
  if ("scheduler" in window && typeof (window as Window & { scheduler?: { yield?: () => Promise<void> } }).scheduler?.yield === "function") {
    return (window as Window & { scheduler: { yield: () => Promise<void> } }).scheduler.yield();
  }
  return new Promise((resolve) => setTimeout(resolve, 0));
}

interface UseLoadGraphOptions {
  enabled?: boolean;
  onGraphReady?: (summary: GraphLoadSummary) => void;
  onProgress?: (progress: GraphLoadProgress) => void;
}

export function useLoadGraph(options: UseLoadGraphOptions = {}) {
  const { enabled = true, onGraphReady, onProgress } = options;

  return useQuery<GraphLoadSummary>({
    queryKey: ["graph", "full-load"],
    enabled,
    staleTime: Infinity,
    retry: 0,
    queryFn: async ({ signal }): Promise<GraphLoadSummary> => {
      const startedAt = performance.now();
      onProgress?.(createGraphLoadProgress({
        phase: "bootstrapping",
        progressKind: "indeterminate",
        nodesLoaded: 0,
        nodesTotal: null,
        edgesLoaded: 0,
        edgesTotal: null,
        message: "Preparing graph session",
      }));

      const fetchedNodes = await fetchAllNodes(signal, onProgress);
      const nodeIds = new Set(fetchedNodes.map((node) => node.id));
      const fetchedEdges = await fetchAllEdges(
        signal,
        nodeIds,
        { loaded: fetchedNodes.length, total: fetchedNodes.length },
        onProgress,
      );

      const degreeByNode = new Map<string, number>();
      for (const nodeId of nodeIds) {
        degreeByNode.set(nodeId, 0);
      }
      for (const edge of fetchedEdges) {
        degreeByNode.set(edge.source, (degreeByNode.get(edge.source) ?? 0) + 1);
        degreeByNode.set(edge.target, (degreeByNode.get(edge.target) ?? 0) + 1);
      }

      const maxDegree = Math.max(...degreeByNode.values(), 1);
      const draftAttributes = fetchedNodes.map((node) => ({
        id: node.id,
        attributes: {
          label: node.content || node.id,
          x: 0,
          y: 0,
          nodeType: node.type,
          content: node.content,
          valid_from: node.valid_from,
          valid_until: node.valid_until,
          properties: node.properties,
        } as NodeAttributes,
      }));

      onProgress?.(createGraphLoadProgress({
        phase: "computing_styling",
        progressKind: "indeterminate",
        nodesLoaded: fetchedNodes.length,
        nodesTotal: fetchedNodes.length,
        edgesLoaded: fetchedEdges.length,
        edgesTotal: fetchedEdges.length,
        message: "Applying semantic color, sizing, and structural styling",
      }));

      const colorAccessor = chooseColorAccessor(draftAttributes);
      const nodePriorityById = new Map<string, number>();

      for (const nodeId of nodeIds) {
        const degree = degreeByNode.get(nodeId) ?? 0;
        const sizeRatio = Math.log(degree + 1) / Math.log(maxDegree + 1);
        nodePriorityById.set(nodeId, sizeRatio);
      }

      const semanticKeyByNodeId = new Map<string, string>();
      draftAttributes.forEach(({ id, attributes }) => {
        semanticKeyByNodeId.set(id, colorAccessor(id, attributes));
      });

      const providedCoordinateCount = fetchedNodes.reduce((count, node) => {
        const properties = node.properties as Record<string, unknown>;
        return readFiniteCoordinate(properties?.x) !== null && readFiniteCoordinate(properties?.y) !== null
          ? count + 1
          : count;
      }, 0);
      const coordinateCoverage = fetchedNodes.length > 0 ? providedCoordinateCount / fetchedNodes.length : 0;
      const useProvidedCoordinates = coordinateCoverage >= 0.92;
      const seededPositions = useProvidedCoordinates
        ? null
        : buildClusterSeedPositions(
            draftAttributes.map(({ id, attributes }) => ({
              id,
              semanticGroup: semanticKeyByNodeId.get(id) ?? structuralColorKey(id, attributes),
              priority: nodePriorityById.get(id) ?? 0,
            })),
          );

      const nodesToMerge = draftAttributes.map(({ id, attributes }) => {
        const semanticGroup = semanticKeyByNodeId.get(id) ?? colorAccessor(id, attributes);
        const colorIndex = hashString(semanticGroup) % GRAPH_THEME.palette.semantic.length;
        const baseColor = GRAPH_THEME.palette.semantic[colorIndex];
        const sizeRatio = nodePriorityById.get(id) ?? 0;
        const dynamicSize = clamp(1.8, 1.8 + 8.8 * sizeRatio, 11.8);
        const hasTemporalBounds = Boolean(attributes.valid_from || attributes.valid_until);
        const provenanceCount = getProvenanceCount(attributes.properties ?? {});
        const properties = attributes.properties as Record<string, unknown>;
        const entityShape = resolveEntityShape(attributes, semanticGroup);
        const providedX = readFiniteCoordinate(properties?.x);
        const providedY = readFiniteCoordinate(properties?.y);
        const seededPosition = seededPositions?.get(id);
        const x = useProvidedCoordinates
          ? providedX ?? 0
          : providedX ?? seededPosition?.x ?? 0;
        const y = useProvidedCoordinates
          ? providedY ?? 0
          : providedY ?? seededPosition?.y ?? 0;
        return {
          id,
          attributes: {
            ...attributes,
            x,
            y,
            semanticGroup,
            color: baseColor,
            baseColor,
            mutedColor: withAlpha(baseColor, GRAPH_THEME.nodes.mutedAlpha),
            glowColor: withAlpha(baseColor, 0.24),
            size: dynamicSize,
            baseSize: dynamicSize,
            visualPriority: sizeRatio,
            labelPriority: sizeRatio,
            strokeColor: darkenHex(baseColor, 112),
            borderColor: darkenHex(baseColor, 112),
            borderSize: 0.72,
            entityShape,
            ...resolveNodeVariantMetadata(baseColor, sizeRatio, hasTemporalBounds, provenanceCount),
          } as NodeAttributes,
        };
      });

      const edgeKeys = new Set(fetchedEdges.map((edge) => pairRegistryKey(edge.source, edge.target)));
      const parallelCounts = new Map<string, number>();
      const familyCounts = new Map<string, number>();
      fetchedEdges.forEach((edge) => {
        const pairKey = pairRegistryKey(edge.source, edge.target);
        parallelCounts.set(pairKey, (parallelCounts.get(pairKey) ?? 0) + 1);
        familyCounts.set(edge.familyId, (familyCounts.get(edge.familyId) ?? 0) + 1);
      });
      const parallelOffsets = new Map<string, number>();

      const edgesToMerge = fetchedEdges.map((edge) => {
        const sourcePriority = nodePriorityById.get(edge.source) ?? 0;
        const targetPriority = nodePriorityById.get(edge.target) ?? 0;
        const isBidirectional = edgeKeys.has(pairRegistryKey(edge.target, edge.source));
        const pairKey = pairRegistryKey(edge.source, edge.target);
        const parallelIndex = parallelOffsets.get(pairKey) ?? 0;
        parallelOffsets.set(pairKey, parallelIndex + 1);
        const parallelCount = parallelCounts.get(pairKey) ?? 1;
        const normalizedWeight = clamp(0, Math.log1p(Math.max(Number(edge.weight) || 1, 1)) / 6, 1);
        const edgeVisualPriority = clamp(
          0,
          Math.sqrt(Math.max(sourcePriority, 0) * Math.max(targetPriority, 0)) * 0.72 + normalizedWeight * 0.28,
          1,
        );

        return {
          id: edge.id,
          familyId: edge.familyId,
          source: edge.source,
          target: edge.target,
          attributes: {
            edgeId: edge.id,
            familyId: edge.familyId,
            sourceId: edge.source,
            targetId: edge.target,
            weight: edge.weight,
            edgeType: edge.type,
            properties: edge.properties,
            size: clamp(0.18, 0.22 + Math.sqrt(Math.max(Number(edge.weight) || 1, 1)) * 0.2, 0.88),
            baseSize: clamp(0.18, 0.22 + Math.sqrt(Math.max(Number(edge.weight) || 1, 1)) * 0.2, 0.88),
            color: GRAPH_THEME.palette.muted.edgeStructure,
            baseColor: GRAPH_THEME.palette.muted.edgeStructure,
            mutedColor: GRAPH_THEME.palette.muted.edgeOverview,
            visualPriority: edgeVisualPriority,
            isBidirectional,
            edgeFamily: isBidirectional ? "bidirectional" : "line",
            curveGroup: curveGroupForPair(edge.source, edge.target),
            type: "line",
            isParallelPair: parallelCount > 1,
            parallelIndex,
            parallelCount,
            familySize: familyCounts.get(edge.familyId) ?? 1,
            ...resolveEdgeVariantMetadata(edge, sourcePriority, targetPriority, isBidirectional),
          } as EdgeAttributes,
        };
      });

      onProgress?.(createGraphLoadProgress({
        phase: "hydrating_scene",
        progressKind: "indeterminate",
        nodesLoaded: nodesToMerge.length,
        nodesTotal: nodesToMerge.length,
        edgesLoaded: edgesToMerge.length,
        edgesTotal: edgesToMerge.length,
        message: "Preparing renderer and hydrating graph scene",
      }));

      try {
        clearGraph();
      } catch (error) {
        console.error("[graph-load] clearGraph failed", error);
        throw error;
      }

      try {
        batchMergeNodes(nodesToMerge);
      } catch (error) {
        console.error("[graph-load] batchMergeNodes failed", error);
        throw error;
      }

      try {
        batchMergeEdges(edgesToMerge);
      } catch (error) {
        console.error("[graph-load] batchMergeEdges failed", error);
        throw error;
      }

      const summary = {
        nodeCount: nodesToMerge.length,
        edgeCount: edgesToMerge.length,
        loadTimeMs: Math.round(performance.now() - startedAt),
        hasCoordinates: useProvidedCoordinates,
        layoutSource: useProvidedCoordinates ? "provided" : "runtime",
        layoutReady: useProvidedCoordinates,
      } satisfies GraphLoadSummary;

      onProgress?.(createGraphLoadProgress({
        phase: summary.layoutReady ? "ready" : "stabilizing_layout",
        progressKind: "indeterminate",
        nodesLoaded: summary.nodeCount,
        nodesTotal: summary.nodeCount,
        edgesLoaded: summary.edgeCount,
        edgesTotal: summary.edgeCount,
        message: summary.layoutReady ? "Graph ready" : "Settling runtime layout",
        showGraphBehind: !summary.layoutReady,
        layoutSource: summary.layoutSource,
        layoutState: summary.layoutReady ? "interactive" : "bootstrapping",
      }));

      onGraphReady?.(summary);
      return summary;
    },
  });
}

export function useReloadGraph() {
  const queryClient = useQueryClient();
  return () => queryClient.invalidateQueries({ queryKey: ["graph", "full-load"] });
}
