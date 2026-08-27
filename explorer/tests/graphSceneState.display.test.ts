import test from "node:test";
import assert from "node:assert/strict";

import {
  batchMergeEdges,
  batchMergeNodes,
  clearGraph,
  graph,
} from "../src/store/graphStore.ts";
import {
  buildGraphAnalyticsSnapshot,
  computeGraphAnalyticsBase,
} from "../src/workspaces/GraphWorkspace/graphAnalytics.ts";
import {
  buildHeatmapRenderSnapshot,
  buildStructuralDistanceSnapshot,
  classifyFullGraphEdge,
  checkGroupedViewAvailability,
  mapFullEdgeClassToVisualState,
  resolveDistanceEdgeStyle,
  resolveDistanceNodeStyle,
  resolveEdgeElementStyle,
  resolveEdgeVisualState,
  resolveDisplayGraph,
  resolveGroupedDisplayNodeId,
  resolveGroupedDisplayStateSnapshot,
  summarizeDistanceBuckets,
} from "../src/workspaces/GraphWorkspace/graphSceneState.ts";
import {
  buildGraphStructureCurveCache,
  evaluateGraphStructureLayerGate,
} from "../src/workspaces/GraphWorkspace/graphStructureLayer.ts";
import { GRAPH_THEME } from "../src/workspaces/GraphWorkspace/graphTheme.ts";
import type { GraphDistanceVisualState, GraphFullEdgeClass, GraphFullEdgeClassCounts } from "../src/workspaces/GraphWorkspace/types.ts";

function addNode(id: string, semanticGroup = "entity") {
  batchMergeNodes([
    {
      id,
      attributes: {
        label: id,
        content: id,
        x: 0,
        y: 0,
        size: 8,
        color: "#63E6FF",
        baseColor: "#63E6FF",
        nodeType: semanticGroup,
        semanticGroup,
        properties: {},
      },
    },
  ]);
}

function setNodePosition(id: string, x: number, y: number) {
  graph.mergeNodeAttributes(id, { x, y });
}

function addEdge(id: string, source: string, target: string, weight = 1) {
  batchMergeEdges([
    {
      id,
      source,
      target,
      attributes: {
        edgeType: "related_to",
        weight,
        properties: {},
      },
    },
  ]);
}

test.beforeEach(() => {
  clearGraph();
});

test.after(() => {
  clearGraph();
});

const BASE_NODE_STYLE = {
  color: "#63E6FF",
  shellColor: "#63E6FF",
  coreScale: 1,
  size: 8,
  forceLabel: false,
  label: "node",
  zIndex: 1,
  hidden: false,
  borderColor: "#63E6FF",
  borderSize: 1,
  nodeVariant: "default",
  entityShape: "entity",
  entityShapeKind: 0,
  entityAspectRatio: 1,
  showBadge: false,
  showRing: false,
  ringSize: 0,
  showHalo: false,
  haloColor: "transparent",
} as const;

const BASE_EDGE_STYLE = {
  hidden: true,
  color: "#334155",
  size: 0.5,
  zIndex: 0,
  edgeVariant: "line",
  arrowVisibilityPolicy: "hidden",
  curveStrength: 0,
  curvature: 0,
} as const;

function makeDistanceState(overrides: Partial<GraphDistanceVisualState>): GraphDistanceVisualState {
  return {
    mode: "off",
    anchorNodeId: null,
    anchorLabel: null,
    maxHops: 2,
    structuralDistances: {},
    semanticScores: {},
    semanticNeighborCount: 0,
    status: "ready",
    error: null,
    ...overrides,
  };
}

test("buildStructuralDistanceSnapshot returns bounded BFS hop distances", () => {
  addNode("anchor");
  addNode("near");
  addNode("far");
  addNode("outside");
  addNode("too-far");
  addEdge("e-anchor-near", "anchor", "near");
  addEdge("e-near-far", "near", "far");
  addEdge("e-far-outside", "far", "outside");
  addEdge("e-outside-too-far", "outside", "too-far");

  const distances = buildStructuralDistanceSnapshot(graph, "anchor", 3);

  assert.equal(distances.anchor, 0);
  assert.equal(distances.near, 1);
  assert.equal(distances.far, 2);
  assert.equal(distances.outside, 3);
  assert.equal(distances["too-far"], undefined);
});

test("summarizeDistanceBuckets reports local rings and outside count", () => {
  const counts = summarizeDistanceBuckets({
    anchor: 0,
    one: 1,
    two: 2,
    three: 3,
  }, 6);

  assert.deepEqual(counts, {
    anchor: 1,
    oneHop: 1,
    twoHop: 1,
    threeHopPlus: 1,
    outside: 2,
  });
});

test("buildHeatmapRenderSnapshot caps and deterministically samples large rings", () => {
  addNode("anchor");
  for (let index = 0; index < 130; index += 1) {
    const nodeId = `one-${index}`;
    addNode(nodeId);
    graph.mergeNodeAttributes(nodeId, { visualPriority: index % 7, labelPriority: index % 5 });
    addEdge(`edge-anchor-${nodeId}`, "anchor", nodeId, index % 11);
  }
  for (let index = 0; index < 700; index += 1) {
    const nodeId = `two-${index}`;
    addNode(nodeId);
    graph.mergeNodeAttributes(nodeId, { visualPriority: index % 13, labelPriority: index % 3 });
    addEdge(`edge-one-two-${index}`, `one-${index % 130}`, nodeId, index % 17);
  }
  for (let index = 0; index < 950; index += 1) {
    const nodeId = `three-${index}`;
    addNode(nodeId);
    graph.mergeNodeAttributes(nodeId, { visualPriority: index % 19, labelPriority: index % 4 });
    addEdge(`edge-two-three-${index}`, `two-${index % 700}`, nodeId, index % 23);
  }

  const distances = buildStructuralDistanceSnapshot(graph, "anchor", 3);
  const firstSnapshot = buildHeatmapRenderSnapshot(graph, "anchor", distances, 3);
  const secondSnapshot = buildHeatmapRenderSnapshot(graph, "anchor", distances, 3);

  assert.equal(firstSnapshot.ringCounts.anchor, 1);
  assert.equal(firstSnapshot.ringCounts.oneHop, 130);
  assert.equal(firstSnapshot.ringCounts.twoHop, 700);
  assert.equal(firstSnapshot.ringCounts.threeHopPlus, 950);
  assert.equal(firstSnapshot.renderedRingCounts.anchor, 1);
  assert.equal(firstSnapshot.renderedRingCounts.oneHop, 120);
  assert.equal(firstSnapshot.renderedRingCounts.twoHop, 650);
  assert.equal(firstSnapshot.renderedRingCounts.threeHopPlus, 900);
  assert.equal(firstSnapshot.saturationMode, "sampled");
  assert.deepEqual(firstSnapshot.visibleNodeIds, secondSnapshot.visibleNodeIds);
  assert.ok(firstSnapshot.visibleNodeIds.includes("anchor"));
});

test("resolveDistanceNodeStyle applies ego muting without mutating graph data", () => {
  const state = makeDistanceState({
    mode: "ego",
    anchorNodeId: "anchor",
    anchorLabel: "Anchor",
    maxHops: 2,
    structuralDistances: { anchor: 0, near: 1 },
  });

  const anchorStyle = resolveDistanceNodeStyle(GRAPH_THEME, "inspection", BASE_NODE_STYLE, state, "anchor");
  const outsideStyle = resolveDistanceNodeStyle(GRAPH_THEME, "inspection", BASE_NODE_STYLE, state, "outside");

  assert.equal(anchorStyle.forceLabel, true);
  assert.equal(anchorStyle.label, "Anchor");
  assert.ok(Number(anchorStyle.size) > BASE_NODE_STYLE.size);
  assert.equal(outsideStyle.label, "");
  assert.ok(Number(outsideStyle.size) < BASE_NODE_STYLE.size);
});

test("resolveDistanceNodeStyle applies readable heatmap rings only when ready", () => {
  const readyState = makeDistanceState({
    mode: "heatmap",
    anchorNodeId: "anchor",
    maxHops: 3,
    structuralDistances: { anchor: 0, one: 1, two: 2, three: 3 },
    heatmapVisibleNodeIds: ["anchor", "one", "two", "three"],
    distanceCounts: {
      anchor: 1,
      oneHop: 1,
      twoHop: 1,
      threeHopPlus: 1,
      outside: 1,
    },
  });
  const loadingState = makeDistanceState({ ...readyState, status: "loading" });

  const anchorStyle = resolveDistanceNodeStyle(GRAPH_THEME, "overview", BASE_NODE_STYLE, readyState, "anchor");
  const oneHopStyle = resolveDistanceNodeStyle(GRAPH_THEME, "overview", BASE_NODE_STYLE, readyState, "one");
  const twoHopStyle = resolveDistanceNodeStyle(GRAPH_THEME, "overview", BASE_NODE_STYLE, readyState, "two");
  const threeHopStyle = resolveDistanceNodeStyle(GRAPH_THEME, "overview", BASE_NODE_STYLE, readyState, "three");
  const outsideStyle = resolveDistanceNodeStyle(GRAPH_THEME, "overview", BASE_NODE_STYLE, readyState, "outside");
  const loadingStyle = resolveDistanceNodeStyle(GRAPH_THEME, "overview", BASE_NODE_STYLE, loadingState, "near");

  assert.notEqual(anchorStyle.color, oneHopStyle.color);
  assert.notEqual(oneHopStyle.color, twoHopStyle.color);
  assert.notEqual(twoHopStyle.color, threeHopStyle.color);
  assert.ok(Number(anchorStyle.size) > Number(oneHopStyle.size));
  assert.ok(Number(oneHopStyle.size) > Number(twoHopStyle.size));
  assert.ok(Number(twoHopStyle.size) > Number(threeHopStyle.size));
  assert.equal(outsideStyle.label, "");
  assert.ok(Number(outsideStyle.size) < BASE_NODE_STYLE.size);
  assert.deepEqual(loadingStyle, {});
});

test("resolveDistanceNodeStyle compresses saturated heatmap far rings", () => {
  const saturatedState = makeDistanceState({
    mode: "heatmap",
    anchorNodeId: "anchor",
    maxHops: 3,
    structuralDistances: { anchor: 0, one: 1, two: 2, three: 3 },
    heatmapVisibleNodeIds: ["anchor", "one", "two", "three"],
    distanceCounts: {
      anchor: 1,
      oneHop: 32,
      twoHop: 3350,
      threeHopPlus: 7412,
      outside: 3280,
    },
  });

  const oneHopStyle = resolveDistanceNodeStyle(GRAPH_THEME, "overview", BASE_NODE_STYLE, saturatedState, "one");
  const twoHopStyle = resolveDistanceNodeStyle(GRAPH_THEME, "overview", BASE_NODE_STYLE, saturatedState, "two");
  const threeHopStyle = resolveDistanceNodeStyle(GRAPH_THEME, "overview", BASE_NODE_STYLE, saturatedState, "three");
  const outsideStyle = resolveDistanceNodeStyle(GRAPH_THEME, "overview", BASE_NODE_STYLE, saturatedState, "outside");

  assert.ok(Number(oneHopStyle.size) > Number(twoHopStyle.size));
  assert.ok(Number(twoHopStyle.size) > Number(threeHopStyle.size));
  assert.ok(Number(threeHopStyle.size) > Number(outsideStyle.size));
  assert.equal(threeHopStyle.label, "");
});

test("resolveDistanceNodeStyle mutes unsampled heatmap nodes instead of coloring them", () => {
  const sampledState = makeDistanceState({
    mode: "heatmap",
    anchorNodeId: "anchor",
    maxHops: 3,
    structuralDistances: { anchor: 0, rendered: 2, unsampled: 2 },
    heatmapVisibleNodeIds: ["anchor", "rendered"],
    distanceCounts: {
      anchor: 1,
      oneHop: 0,
      twoHop: 2,
      threeHopPlus: 0,
      outside: 0,
    },
    heatmapRenderedRingCounts: {
      anchor: 1,
      oneHop: 0,
      twoHop: 1,
      threeHopPlus: 0,
      outside: 0,
    },
    heatmapSaturationMode: "sampled",
  });

  const renderedStyle = resolveDistanceNodeStyle(GRAPH_THEME, "overview", BASE_NODE_STYLE, sampledState, "rendered");
  const unsampledStyle = resolveDistanceNodeStyle(GRAPH_THEME, "overview", BASE_NODE_STYLE, sampledState, "unsampled");

  assert.notEqual(renderedStyle.color, unsampledStyle.color);
  assert.ok(Number(renderedStyle.size) > Number(unsampledStyle.size));
  assert.equal(unsampledStyle.label, "");
});

test("resolveDistanceEdgeStyle reveals structural and semantic context edges", () => {
  const structuralState = makeDistanceState({
    mode: "structural",
    anchorNodeId: "anchor",
    maxHops: 2,
    structuralDistances: { anchor: 0, near: 1 },
  });
  const semanticState = makeDistanceState({
    mode: "semantic",
    anchorNodeId: "anchor",
    semanticScores: { semantic: 0.82 },
  });

  const structuralStyle = resolveDistanceEdgeStyle(BASE_EDGE_STYLE, structuralState, "anchor", "near");
  const semanticStyle = resolveDistanceEdgeStyle(BASE_EDGE_STYLE, semanticState, "anchor", "semantic");
  const unrelatedStyle = resolveDistanceEdgeStyle(BASE_EDGE_STYLE, semanticState, "near", "semantic");

  assert.equal(structuralStyle.hidden, false);
  assert.equal(semanticStyle.hidden, false);
  assert.deepEqual(unrelatedStyle, {});
});

test("resolveDistanceEdgeStyle suppresses heatmap background edges but preserves context", () => {
  const heatmapState = makeDistanceState({
    mode: "heatmap",
    anchorNodeId: "anchor",
    maxHops: 3,
    structuralDistances: { anchor: 0, one: 1 },
  });

  const backgroundStyle = resolveDistanceEdgeStyle(BASE_EDGE_STYLE, heatmapState, "anchor", "one", "backbone");
  const contextStyle = resolveDistanceEdgeStyle(BASE_EDGE_STYLE, heatmapState, "anchor", "one", "local-context");
  const pathStyle = resolveDistanceEdgeStyle(BASE_EDGE_STYLE, heatmapState, "anchor", "one", "path");

  assert.equal(backgroundStyle.hidden, true);
  assert.deepEqual(contextStyle, {});
  assert.deepEqual(pathStyle, {});
});

test("resolveEdgeVisualState caps selected-node incident edge promotion", () => {
  const uncappedState = resolveEdgeVisualState(
    "edge-1",
    "hub",
    "leaf",
    "inspection",
    null,
    "hub",
    "",
    new Set(["hub", "leaf"]),
    new Set(),
    new Set(),
  );
  assert.equal(uncappedState, "muted");

  const cappedState = resolveEdgeVisualState(
    "edge-1",
    "hub",
    "leaf",
    "inspection",
    null,
    "hub",
    "",
    new Set(["hub", "leaf"]),
    new Set(),
    new Set(["edge-1"]),
  );
  assert.equal(cappedState, "selected");
});

test("resolveEdgeElementStyle applies full-graph LOD to directional background edges", () => {
  const style = resolveEdgeElementStyle(
    GRAPH_THEME,
    "overview",
    "default",
    {
      edgeType: "related_to",
      weight: 1,
      properties: {},
      edgeVariant: "directional",
      visualPriority: 0.1,
      baseSize: 0.5,
    },
    "source",
    "target",
    "full",
    "directional-low-priority",
  );

  assert.equal(style.hidden, true);
});

test("classifyFullGraphEdge applies deterministic priority order", () => {
  const edgeClass = classifyFullGraphEdge(
    "edge-priority",
    "source",
    "target",
    "inspection",
    "source",
    "source",
    "edge-priority",
    new Set(["source", "target"]),
    new Set(["edge-priority"]),
    new Set(["edge-priority"]),
    new Set(["edge-priority"]),
    { label: "source", x: 0, y: 0, size: 1, color: "#fff", nodeType: "gene", content: "source", semanticGroup: "gene", properties: {} },
    { label: "target", x: 0, y: 0, size: 1, color: "#fff", nodeType: "disease", content: "target", semanticGroup: "disease", properties: {} },
  );

  assert.equal(edgeClass, "path");

  const selectedClass = classifyFullGraphEdge(
    "edge-priority",
    "source",
    "target",
    "inspection",
    "source",
    "source",
    "edge-priority",
    new Set(["source", "target"]),
    new Set(),
    new Set(["edge-priority"]),
  );

  assert.equal(selectedClass, "selected");
});

test("classifyFullGraphEdge separates capped local context from muted hub edges", () => {
  const mutedClass = classifyFullGraphEdge(
    "hub-edge",
    "hub",
    "leaf",
    "inspection",
    null,
    "hub",
    "",
    new Set(["hub", "leaf"]),
    new Set(),
    new Set(),
  );

  assert.equal(mutedClass, "muted");

  const localContextClass = classifyFullGraphEdge(
    "hub-edge",
    "hub",
    "leaf",
    "inspection",
    null,
    "hub",
    "",
    new Set(["hub", "leaf"]),
    new Set(),
    new Set(["hub-edge"]),
  );

  assert.equal(localContextClass, "local-context");
});

test("classifyFullGraphEdge marks curated bridge and backbone candidates", () => {
  const bridgeClass = classifyFullGraphEdge(
    "curated-bridge",
    "source",
    "target",
    "overview",
    null,
    "",
    "",
    new Set(),
    new Set(),
    new Set(),
    new Set(["curated-bridge"]),
    { label: "source", x: 0, y: 0, size: 1, color: "#fff", nodeType: "gene", content: "source", semanticGroup: "gene", properties: {} },
    { label: "target", x: 0, y: 0, size: 1, color: "#fff", nodeType: "disease", content: "target", semanticGroup: "disease", properties: {} },
  );

  assert.equal(bridgeClass, "bridge");

  const backboneClass = classifyFullGraphEdge(
    "curated-backbone",
    "source",
    "target",
    "overview",
    null,
    "",
    "",
    new Set(),
    new Set(),
    new Set(),
    new Set(["curated-backbone"]),
    { label: "source", x: 0, y: 0, size: 1, color: "#fff", nodeType: "gene", content: "source", semanticGroup: "gene", properties: {} },
    { label: "target", x: 0, y: 0, size: 1, color: "#fff", nodeType: "gene", content: "target", semanticGroup: "gene", properties: {} },
  );

  assert.equal(backboneClass, "backbone");
});

test("classifyFullGraphEdge hides ordinary full-graph overview edges", () => {
  const edgeClass = classifyFullGraphEdge(
    "ordinary-edge",
    "source",
    "target",
    "overview",
    null,
    "",
    "",
    new Set(),
    new Set(),
    new Set(),
  );

  assert.equal(edgeClass, "hidden");
});

test("mapFullEdgeClassToVisualState renders curated backbone and bridge as backbone", () => {
  assert.equal(
    mapFullEdgeClassToVisualState("backbone", { hoveredNodeId: null, hasActiveInteraction: false }),
    "backbone",
  );
  assert.equal(
    mapFullEdgeClassToVisualState("bridge", { hoveredNodeId: null, hasActiveInteraction: false }),
    "backbone",
  );
  assert.equal(
    mapFullEdgeClassToVisualState("hidden", { hoveredNodeId: null, hasActiveInteraction: false }),
    "inactive",
  );
});

test("resolveEdgeElementStyle renders curated full-graph backbone quietly", () => {
  const style = resolveEdgeElementStyle(
    GRAPH_THEME,
    "overview",
    "backbone",
    {
      edgeType: "related_to",
      weight: 2,
      properties: {},
      visualPriority: 0.9,
      baseSize: 0.8,
    },
    "source",
    "target",
    "full",
    "curated-backbone-edge",
    "backbone",
  );

  assert.equal(style.hidden, false);
  assert.equal(style.type, "line");
  assert.match(style.color ?? "", /rgba\(.+,\s*0\.08\)/);
  assert.ok(Number(style.size ?? 0) <= GRAPH_THEME.edges.fullGraphStructure.backboneMaxSize);
});

test("resolveEdgeElementStyle renders high-value bridge as a calm curved teal edge", () => {
  const style = resolveEdgeElementStyle(
    GRAPH_THEME,
    "overview",
    "backbone",
    {
      edgeType: "related_to",
      weight: 4,
      properties: {},
      visualPriority: 0.95,
      baseSize: 0.9,
      edgeVariant: "line",
    },
    "source",
    "target",
    "full",
    "curated-bridge-edge",
    "bridge",
  );

  assert.equal(style.hidden, false);
  assert.equal(style.type, "curve");
  assert.notEqual(style.type, "arrow");
  assert.match(style.color ?? "", /rgba\(.+,\s*0\.14\)/);
  assert.equal(style.curvature, GRAPH_THEME.edges.fullGraphStructure.bridgeCurveStrength);
  assert.ok(Number(style.size ?? 0) <= GRAPH_THEME.edges.fullGraphStructure.bridgeMaxSize);
});

test("resolveEdgeElementStyle keeps low-priority bridge straight", () => {
  const style = resolveEdgeElementStyle(
    GRAPH_THEME,
    "overview",
    "backbone",
    {
      edgeType: "related_to",
      weight: 1,
      properties: {},
      visualPriority: 0.2,
      baseSize: 0.9,
      edgeVariant: "line",
    },
    "source",
    "target",
    "full",
    "low-value-bridge-edge",
    "bridge",
  );

  assert.equal(style.hidden, false);
  assert.equal(style.type, "line");
  assert.equal(style.curvature, 0);
});

test("evaluateGraphStructureLayerGate enables only sparse settled full-graph structure", () => {
  const counts: GraphFullEdgeClassCounts = {
    hidden: 20,
    backbone: 6,
    bridge: 4,
    "local-context": 0,
    selected: 0,
    path: 0,
    muted: 0,
  };

  assert.deepEqual(
    evaluateGraphStructureLayerGate({
      mode: "auto",
      viewMode: "grouped",
      isLayoutRunning: false,
      edgeDiagnostics: {
        mode: "grouped",
        zoomTier: "overview",
        totalEdges: 30,
        visibleEdges: 10,
        counts,
        updatedAt: 1,
      },
      minimumLiteralEdges: 24,
    }),
    { enabled: false, disabledReason: "non-full-mode" },
  );

  assert.deepEqual(
    evaluateGraphStructureLayerGate({
      mode: "auto",
      viewMode: "full",
      isLayoutRunning: true,
      edgeDiagnostics: {
        mode: "full",
        zoomTier: "overview",
        totalEdges: 30,
        visibleEdges: 10,
        counts,
        updatedAt: 1,
      },
      minimumLiteralEdges: 24,
    }),
    { enabled: false, disabledReason: "layout-running" },
  );

  assert.deepEqual(
    evaluateGraphStructureLayerGate({
      mode: "auto",
      viewMode: "full",
      isLayoutRunning: false,
      edgeDiagnostics: {
        mode: "full",
        zoomTier: "overview",
        totalEdges: 30,
        visibleEdges: 24,
        counts: { ...counts, backbone: 18, bridge: 6 },
        updatedAt: 1,
      },
      minimumLiteralEdges: 24,
    }),
    { enabled: false, disabledReason: "enough-literal-edges" },
  );

  assert.deepEqual(
    evaluateGraphStructureLayerGate({
      mode: "auto",
      viewMode: "full",
      isLayoutRunning: false,
      edgeDiagnostics: {
        mode: "full",
        zoomTier: "overview",
        totalEdges: 30,
        visibleEdges: 10,
        counts,
        updatedAt: 1,
      },
      minimumLiteralEdges: 24,
    }),
    { enabled: true, disabledReason: null },
  );
});

test("buildGraphStructureCurveCache prefers bridges, caps curves, and skips invalid endpoints", () => {
  addNode("a", "gene");
  addNode("b", "disease");
  addNode("c", "gene");
  addNode("d", "compound");
  setNodePosition("a", 0, 0);
  setNodePosition("b", 100, 0);
  setNodePosition("c", 0, 100);
  setNodePosition("d", Number.NaN, 100);

  addEdge("backbone-1", "a", "c", 1);
  graph.mergeEdgeAttributes("backbone-1", { visualPriority: 1 });
  addEdge("bridge-1", "a", "b", 0.2);
  graph.mergeEdgeAttributes("bridge-1", { visualPriority: 0.1 });
  addEdge("selected-1", "b", "c", 1);
  graph.mergeEdgeAttributes("selected-1", { visualPriority: 1 });
  addEdge("invalid-bridge", "a", "d", 1);
  graph.mergeEdgeAttributes("invalid-bridge", { visualPriority: 1 });

  const edgeClasses = new Map<string, GraphFullEdgeClass>([
    ["backbone-1", "backbone"],
    ["bridge-1", "bridge"],
    ["selected-1", "selected"],
    ["invalid-bridge", "bridge"],
  ]);

  const capped = buildGraphStructureCurveCache({
    graphRef: graph,
    cacheKey: "test-cache",
    classifyEdge: (edgeId) => edgeClasses.get(edgeId) ?? "hidden",
    maxCurves: 1,
    curveStrength: 0.12,
  });

  assert.equal(capped.curves.length, 1);
  assert.equal(capped.curves[0].edgeId, "bridge-1");
  assert.equal(capped.bridgeCurveCount, 1);
  assert.equal(capped.backboneCurveCount, 0);

  const uncapped = buildGraphStructureCurveCache({
    graphRef: graph,
    cacheKey: "test-cache-all",
    classifyEdge: (edgeId) => edgeClasses.get(edgeId) ?? "hidden",
    maxCurves: 10,
    curveStrength: 0.12,
  });

  assert.deepEqual(
    uncapped.curves.map((curve) => curve.edgeId).sort(),
    ["backbone-1", "bridge-1"],
  );
});

test("resolveEdgeVisualState suppresses automatic overview backbone in clean baseline", () => {
  const state = resolveEdgeVisualState(
    "overview-backbone-high-priority",
    "source",
    "target",
    "overview",
    null,
    "",
    "",
    new Set(),
    new Set(),
  );

  assert.equal(state, "inactive");
});

test("resolveEdgeElementStyle keeps full-graph selected and path edges controlled", () => {
  const selectedStyle = resolveEdgeElementStyle(
    GRAPH_THEME,
    "inspection",
    "selected",
    {
      edgeType: "related_to",
      weight: 2,
      properties: {},
      visualPriority: 0.9,
      baseSize: 0.8,
    },
    "source",
    "target",
    "full",
    "selected-context-edge",
  );
  const pathStyle = resolveEdgeElementStyle(
    GRAPH_THEME,
    "inspection",
    "path",
    {
      edgeType: "causes",
      weight: 2,
      properties: {},
      visualPriority: 0.9,
      baseSize: 0.8,
    },
    "source",
    "target",
    "full",
    "path-context-edge",
  );

  assert.equal(selectedStyle.hidden, false);
  assert.match(selectedStyle.color ?? "", /rgba\(.+,\s*0\.6\)/);
  assert.equal(pathStyle.hidden, false);
  assert.match(pathStyle.color ?? "", /rgba\(.+,\s*0\.76\)/);
});

test("buildGraphAnalyticsSnapshot emits a readable capped overview backbone", () => {
  const semanticGroups = ["gene/protein", "disease", "drug", "pathway"];
  for (let index = 0; index < 16; index += 1) {
    addNode(`n${index}`, semanticGroups[index % semanticGroups.length]);
  }

  let edgeIndex = 0;
  for (let sourceIndex = 0; sourceIndex < 16; sourceIndex += 1) {
    for (let offset = 1; offset <= 3; offset += 1) {
      const targetIndex = (sourceIndex + offset * 3) % 16;
      if (sourceIndex === targetIndex) {
        continue;
      }
      addEdge(`ambient-edge-${edgeIndex}`, `n${sourceIndex}`, `n${targetIndex}`, 1 + (edgeIndex % 5));
      edgeIndex += 1;
    }
  }

  const base = computeGraphAnalyticsBase(graph, {
    computeCommunities: false,
    computeCentrality: true,
  });
  const analytics = buildGraphAnalyticsSnapshot({
    graphRef: graph,
    interactionState: {
      hoveredNodeId: null,
      selectedNodeId: "",
      selectedEdgeId: "",
      focusedNodeId: "",
      activePath: [],
      activePathEdgeIds: [],
      viewMode: "full",
      zoomTier: "overview",
      isLayoutRunning: false,
    },
    base,
    visibleNodeIds: graph.nodes(),
  });

  assert.equal(analytics.overviewBackbone.ready, true);
  assert.ok(analytics.overviewBackbone.edgeIds.length > 6);
  assert.ok(analytics.overviewBackbone.edgeIds.length <= 128);
});

test("resolveDisplayGraph bundles parallel edges in full view", () => {
  addNode("a");
  addNode("b");
  addEdge("e1", "a", "b", 1);
  addEdge("e2", "a", "b", 2);

  const { graph } = resolveDisplayGraph("", [], [], "full", { aggregationEnabled: true });
  assert.equal(graph.size, 1);

  const edgeId = graph.edges()[0];
  const attrs = graph.getEdgeAttributes(edgeId) as {
    isAggregated?: boolean;
    aggregateCount?: number;
    rawEdgeIds?: string[];
    bundleKind?: string;
  };

  assert.equal(attrs.isAggregated, true);
  assert.equal(attrs.aggregateCount, 2);
  assert.deepEqual(new Set(attrs.rawEdgeIds ?? []), new Set(["e1", "e2"]));
  assert.equal(attrs.bundleKind, "parallel");
});

test("resolveDisplayGraph collapse keeps path neighbor visible", () => {
  addNode("center");
  for (let index = 0; index < 10; index += 1) {
    const neighbor = `n${index}`;
    addNode(neighbor);
    addEdge(`edge-${index}`, "center", neighbor, 1);
  }

  const { state } = resolveDisplayGraph("center", ["center", "n9"], [], "full", {
    aggregationEnabled: false,
    collapsedNeighborhoodNodeIds: ["center"],
  });

  assert.equal(state.selectedRootNodeId, "center");
  assert.equal(state.selectedVisibleNeighborIds.includes("n9"), true);
  assert.equal(state.selectedVisibleNeighborIds.length, 9);
  assert.equal(state.selectedCollapsedNeighborIds.length, 1);
});

test("resolveDisplayGraph grouped view emits community nodes and edges", () => {
  const left = ["a1", "a2", "a3", "a4"];
  const right = ["b1", "b2", "b3", "b4"];

  [...left, ...right].forEach((nodeId, index) => {
    addNode(nodeId, index < left.length ? "left" : "right");
  });

  let edgeIndex = 0;
  for (let i = 0; i < left.length; i += 1) {
    for (let j = 0; j < left.length; j += 1) {
      if (i !== j) {
        addEdge(`l-${edgeIndex++}`, left[i], left[j], 3);
      }
    }
  }

  for (let i = 0; i < right.length; i += 1) {
    for (let j = 0; j < right.length; j += 1) {
      if (i !== j) {
        addEdge(`r-${edgeIndex++}`, right[i], right[j], 3);
      }
    }
  }

  addEdge("bridge-1", "a1", "b1", 0.1);
  addEdge("bridge-2", "a2", "b2", 0.1);

  const { graph, state } = resolveDisplayGraph("", [], [], "grouped", { aggregationEnabled: true });

  assert.equal(state.groupedViewAvailable, true);

  const communityNodes = graph.nodes().filter((nodeId) => nodeId.startsWith("__community__"));
  assert.ok(communityNodes.length >= 2);

  const hasCommunityEdge = graph
    .edges()
    .map((edgeId) => graph.getEdgeAttributes(edgeId) as { bundleKind?: string; isAggregated?: boolean; aggregateCount?: number })
    .some((attrs) => attrs.bundleKind === "community" && attrs.isAggregated === true && Number(attrs.aggregateCount ?? 0) > 0);

  assert.equal(hasCommunityEdge, true);
});

// ── resolveGroupedDisplayNodeId ──────────────────────────────────────────────

test("resolveGroupedDisplayNodeId returns null for empty nodeId", () => {
  const { graph: displayGraph } = resolveDisplayGraph("", [], [], "full", { aggregationEnabled: false });
  assert.equal(resolveGroupedDisplayNodeId(displayGraph, ""), null);
});

test("resolveGroupedDisplayNodeId returns nodeId when it exists directly in display graph", () => {
  addNode("x");
  const { graph: displayGraph } = resolveDisplayGraph("", [], [], "full", { aggregationEnabled: false });
  assert.equal(resolveGroupedDisplayNodeId(displayGraph, "x"), "x");
});

test("resolveGroupedDisplayNodeId resolves base node to its community node", () => {
  const left = ["a1", "a2", "a3", "a4"];
  const right = ["b1", "b2", "b3", "b4"];
  [...left, ...right].forEach((nodeId, index) => addNode(nodeId, index < left.length ? "left" : "right"));

  let edgeIndex = 0;
  for (let i = 0; i < left.length; i += 1) {
    for (let j = 0; j < left.length; j += 1) {
      if (i !== j) addEdge(`l-${edgeIndex++}`, left[i], left[j], 3);
    }
  }
  for (let i = 0; i < right.length; i += 1) {
    for (let j = 0; j < right.length; j += 1) {
      if (i !== j) addEdge(`r-${edgeIndex++}`, right[i], right[j], 3);
    }
  }
  addEdge("bridge-1", "a1", "b1", 0.1);

  const { graph: displayGraph } = resolveDisplayGraph("", [], [], "grouped", { aggregationEnabled: true });
  const communityNodes = displayGraph.nodes().filter((n) => n.startsWith("__community__"));
  assert.ok(communityNodes.length >= 2, "expected community nodes");

  const resolved = resolveGroupedDisplayNodeId(displayGraph, "a1");
  assert.ok(resolved !== null, "should resolve a1 to a community node");
  assert.ok(resolved!.startsWith("__community__"), "resolved id should be a community node");
});

// ── resolveGroupedDisplayStateSnapshot ──────────────────────────────────────

test("resolveGroupedDisplayStateSnapshot returns none-kind when no node selected", () => {
  addNode("p");
  addNode("q");
  addEdge("e1", "p", "q");
  const { graph: displayGraph } = resolveDisplayGraph("", [], [], "full", { aggregationEnabled: false });
  const state = resolveGroupedDisplayStateSnapshot(displayGraph, "", {
    groupedViewAvailable: true,
    groupedViewReason: null,
  });
  assert.equal(state.selectedNodeKind, "none");
  assert.equal(state.selectedRootNodeId, null);
});

test("resolveGroupedDisplayStateSnapshot maps selected base node to community in grouped graph", () => {
  const left = ["c1", "c2", "c3", "c4"];
  const right = ["d1", "d2", "d3", "d4"];
  [...left, ...right].forEach((nodeId, index) => addNode(nodeId, index < left.length ? "left" : "right"));

  let edgeIndex = 0;
  for (let i = 0; i < left.length; i += 1) {
    for (let j = 0; j < left.length; j += 1) {
      if (i !== j) addEdge(`lc-${edgeIndex++}`, left[i], left[j], 3);
    }
  }
  for (let i = 0; i < right.length; i += 1) {
    for (let j = 0; j < right.length; j += 1) {
      if (i !== j) addEdge(`rc-${edgeIndex++}`, right[i], right[j], 3);
    }
  }
  addEdge("bridge-c1", "c1", "d1", 0.1);
  addEdge("bridge-c2", "c2", "d2", 0.1);

  const { graph: displayGraph } = resolveDisplayGraph("", [], [], "grouped", { aggregationEnabled: true });
  const state = resolveGroupedDisplayStateSnapshot(displayGraph, "c1", {
    groupedViewAvailable: true,
    groupedViewReason: null,
    selectedNodeKind: "grouped",
  });

  assert.ok(state.selectedRootNodeId !== null, "should resolve to a community node");
  assert.ok(state.selectedRootNodeId!.startsWith("__community__"), "root should be a community node");
  assert.equal(state.groupedViewAvailable, true);
});

// ── checkGroupedViewAvailability ─────────────────────────────────────────────

test("checkGroupedViewAvailability returns unavailable on empty graph", () => {
  const result = checkGroupedViewAvailability();
  assert.equal(result.available, false);
  assert.ok(typeof result.reason === "string" && result.reason.length > 0);
});

test("checkGroupedViewAvailability returns available when communities exist", () => {
  const left = ["e1", "e2", "e3", "e4"];
  const right = ["f1", "f2", "f3", "f4"];
  [...left, ...right].forEach((nodeId, index) => addNode(nodeId, index < left.length ? "left" : "right"));

  let edgeIndex = 0;
  for (let i = 0; i < left.length; i += 1) {
    for (let j = 0; j < left.length; j += 1) {
      if (i !== j) addEdge(`le-${edgeIndex++}`, left[i], left[j], 3);
    }
  }
  for (let i = 0; i < right.length; i += 1) {
    for (let j = 0; j < right.length; j += 1) {
      if (i !== j) addEdge(`re-${edgeIndex++}`, right[i], right[j], 3);
    }
  }
  addEdge("bridge-e1", "e1", "f1", 0.1);

  const result = checkGroupedViewAvailability();
  assert.equal(result.available, true);
  assert.equal(result.reason, null);
});


// ── #1009: edge label data-path regression tests ─────────────────────────────

test("resolveDisplayGraph parallel-bundle preserves edgeType on aggregated edge", () => {
  addNode("a");
  addNode("b");
  batchMergeEdges([
    { id: "e1", source: "a", target: "b", attributes: { edgeType: "causes", weight: 1, properties: {} } },
    { id: "e2", source: "a", target: "b", attributes: { edgeType: "causes", weight: 2, properties: {} } },
  ]);

  const { graph: displayGraph } = resolveDisplayGraph("", [], [], "full", { aggregationEnabled: true });
  assert.equal(displayGraph.size, 1);

  const edgeId = displayGraph.edges()[0];
  const attrs = displayGraph.getEdgeAttributes(edgeId) as { edgeType?: string; isAggregated?: boolean };
  assert.equal(attrs.isAggregated, true);
  // The aggregated representative must carry the relationship text through to
  // the edgeReducer's label assignment.
  assert.equal(typeof attrs.edgeType, "string");
  assert.ok((attrs.edgeType ?? "").length > 0, "aggregated edge must have a non-empty edgeType");
});

test("resolveDisplayGraph parallel-bundle picks dominant edgeType across mixed types", () => {
  addNode("a");
  addNode("b");
  batchMergeEdges([
    { id: "e1", source: "a", target: "b", attributes: { edgeType: "inhibits", weight: 1, properties: {} } },
    { id: "e2", source: "a", target: "b", attributes: { edgeType: "inhibits", weight: 1, properties: {} } },
    { id: "e3", source: "a", target: "b", attributes: { edgeType: "activates", weight: 1, properties: {} } },
  ]);

  const { graph: displayGraph } = resolveDisplayGraph("", [], [], "full", { aggregationEnabled: true });
  const edgeId = displayGraph.edges()[0];
  const attrs = displayGraph.getEdgeAttributes(edgeId) as { edgeType?: string; dominantEdgeType?: string };
  // "inhibits" appears twice so it must be the dominant type.
  assert.equal(attrs.edgeType, "inhibits");
  assert.equal(attrs.dominantEdgeType, "inhibits");
});

test("resolveDisplayGraph grouped view community edges carry non-empty edgeType", () => {
  const left = ["g1", "g2", "g3", "g4"];
  const right = ["h1", "h2", "h3", "h4"];
  [...left, ...right].forEach((nodeId, index) => addNode(nodeId, index < left.length ? "left" : "right"));

  let edgeIndex = 0;
  for (let i = 0; i < left.length; i += 1) {
    for (let j = 0; j < left.length; j += 1) {
      if (i !== j) {
        batchMergeEdges([{
          id: `lg-${edgeIndex++}`,
          source: left[i],
          target: left[j],
          attributes: { edgeType: "co_occurs", weight: 3, properties: {} },
        }]);
      }
    }
  }
  for (let i = 0; i < right.length; i += 1) {
    for (let j = 0; j < right.length; j += 1) {
      if (i !== j) {
        batchMergeEdges([{
          id: `rg-${edgeIndex++}`,
          source: right[i],
          target: right[j],
          attributes: { edgeType: "co_occurs", weight: 3, properties: {} },
        }]);
      }
    }
  }
  batchMergeEdges([{ id: "bridge-g", source: "g1", target: "h1", attributes: { edgeType: "interacts_with", weight: 0.1, properties: {} } }]);

  const { graph: displayGraph, state } = resolveDisplayGraph("", [], [], "grouped", { aggregationEnabled: true });
  assert.equal(state.groupedViewAvailable, true);

  const communityEdges = displayGraph.edges().filter((edgeId) => {
    const attrs = displayGraph.getEdgeAttributes(edgeId) as { bundleKind?: string };
    return attrs.bundleKind === "community";
  });
  assert.ok(communityEdges.length > 0, "expected at least one community bundle edge");

  for (const edgeId of communityEdges) {
    const attrs = displayGraph.getEdgeAttributes(edgeId) as { edgeType?: string };
    assert.equal(typeof attrs.edgeType, "string");
    assert.ok((attrs.edgeType ?? "").length > 0, `community edge ${edgeId} must have a non-empty edgeType`);
  }
});

test("resolveDisplayGraph raw edge preserves exact edgeType string for label rendering", () => {
  addNode("src");
  addNode("tgt");
  batchMergeEdges([{
    id: "raw-1",
    source: "src",
    target: "tgt",
    attributes: { edgeType: "works_for", weight: 1, properties: {} },
  }]);

  // In full view without aggregation the edge passes through unchanged.
  const { graph: displayGraph } = resolveDisplayGraph("", [], [], "full", { aggregationEnabled: false });
  assert.equal(displayGraph.size, 1);

  const edgeId = displayGraph.edges()[0];
  const attrs = displayGraph.getEdgeAttributes(edgeId) as { edgeType?: string };
  assert.equal(attrs.edgeType, "works_for");
});

test("resolveDisplayGraph does not produce empty-string edgeType on aggregated edges when source has empty type", () => {
  addNode("a");
  addNode("b");
  // Simulate an API response where type is empty string — the aggregation
  // path must not propagate a blank label.
  batchMergeEdges([
    { id: "e-empty-1", source: "a", target: "b", attributes: { edgeType: "", weight: 1, properties: {} } },
    { id: "e-empty-2", source: "a", target: "b", attributes: { edgeType: "", weight: 1, properties: {} } },
  ]);

  const { graph: displayGraph } = resolveDisplayGraph("", [], [], "full", { aggregationEnabled: true });
  const edgeId = displayGraph.edges()[0];
  const attrs = displayGraph.getEdgeAttributes(edgeId) as {
    edgeType?: string;
    isAggregated?: boolean;
  };
  assert.equal(attrs.isAggregated, true);
  // The aggregation falls back to "related_to" when all source edgeTypes are
  // empty, so the rendered label should never be an empty string.
  assert.equal(attrs.edgeType, "related_to");
});

test("resolveEdgeElementStyle hidden class produces hidden:true for suppressed edges", () => {
  // Verify the data condition the edgeReducer relies on: hidden-classified
  // edges must have hidden:true so that the label assignment sets undefined.
  const style = resolveEdgeElementStyle(
    GRAPH_THEME,
    "overview",
    "inactive",
    {
      edgeType: "causes",
      weight: 1,
      properties: {},
      edgeVariant: "line",
      visualPriority: 0.05,
      baseSize: 0.3,
    },
    "source",
    "target",
    "full",
    "inactive-edge",
    "hidden",
  );
  assert.equal(style.hidden, true);
});

// ── #1009 maintainer-blocking regression: single-edge empty edgeType ─────────

test("resolveDisplayGraph single-edge normalizes empty-string edgeType to related_to", () => {
  addNode("a");
  addNode("b");
  // One edge only — exercises the entries.length === 1 path in aggregateDisplayGraph.
  batchMergeEdges([{
    id: "e-single-empty",
    source: "a",
    target: "b",
    attributes: { edgeType: "", weight: 1, properties: {} },
  }]);

  const { graph: displayGraph } = resolveDisplayGraph("", [], [], "full", { aggregationEnabled: true });
  assert.equal(displayGraph.size, 1);

  const edgeId = displayGraph.edges()[0];
  const attrs = displayGraph.getEdgeAttributes(edgeId) as { edgeType?: string; dominantEdgeType?: string };
  assert.equal(attrs.edgeType, "related_to",
    "single-edge path must normalize empty edgeType to the canonical fallback");
  assert.equal(attrs.dominantEdgeType, "related_to",
    "single-edge dominantEdgeType must also be normalized");
});

test("resolveDisplayGraph single-edge preserves a valid non-empty edgeType unchanged", () => {
  addNode("a");
  addNode("b");
  batchMergeEdges([{
    id: "e-single-valid",
    source: "a",
    target: "b",
    attributes: { edgeType: "works_for", weight: 1, properties: {} },
  }]);

  const { graph: displayGraph } = resolveDisplayGraph("", [], [], "full", { aggregationEnabled: true });
  assert.equal(displayGraph.size, 1);

  const edgeId = displayGraph.edges()[0];
  const attrs = displayGraph.getEdgeAttributes(edgeId) as { edgeType?: string };
  assert.equal(attrs.edgeType, "works_for",
    "single-edge path must not alter a valid relationship type");
});
