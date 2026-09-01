import test from "node:test";
import assert from "node:assert/strict";

import {
  batchMergeEdges,
  batchMergeNodes,
  clearGraph,
  graph,
} from "../src/store/graphStore.ts";
import {
  buildStructuralDistanceSnapshot,
  classifyFullGraphEdge,
  resolveDisplayGraph,
  resolveEdgeElementStyle,
  resolveEdgeVisualState,
  resolveNodeElementStyle,
  resolveNodeVisualState,
  shouldForceNodeLabel,
} from "../src/workspaces/GraphWorkspace/graphSceneState.ts";
import { GRAPH_THEME, type GraphZoomTier } from "../src/workspaces/GraphWorkspace/graphTheme.ts";

test.beforeEach(() => {
  clearGraph();
});

test.after(() => {
  clearGraph();
});

/**
 * Loads the canonical 4-node, 3-edge deterministic test graph (Semantica #1037).
 *
 * Graph structure:
 *   Alice (Person)       --WORKS_AT-->    Acme (Organization)
 *   Bob (Person)         --KNOWS-->       Alice (Person)
 *   Acme (Organization)  --LOCATED_IN-->  New York (Location)
 */
function loadDeterministicTestGraph() {
  batchMergeNodes([
    {
      id: "alice",
      attributes: {
        label: "Alice",
        content: "Alice",
        x: 0,
        y: 0,
        size: 8,
        color: "#63E6FF",
        baseColor: "#63E6FF",
        nodeType: "Person",
        semanticGroup: "Person",
        properties: {},
      },
    },
    {
      id: "bob",
      attributes: {
        label: "Bob",
        content: "Bob",
        x: -50,
        y: 0,
        size: 8,
        color: "#63E6FF",
        baseColor: "#63E6FF",
        nodeType: "Person",
        semanticGroup: "Person",
        properties: {},
      },
    },
    {
      id: "acme",
      attributes: {
        label: "Acme",
        content: "Acme",
        x: 50,
        y: 0,
        size: 8,
        color: "#A78BFA",
        baseColor: "#A78BFA",
        nodeType: "Organization",
        semanticGroup: "Organization",
        properties: {},
      },
    },
    {
      id: "new_york",
      attributes: {
        label: "New York",
        content: "New York",
        x: 100,
        y: 0,
        size: 8,
        color: "#34D399",
        baseColor: "#34D399",
        nodeType: "Location",
        semanticGroup: "Location",
        properties: {},
      },
    },
  ]);

  batchMergeEdges([
    {
      id: "edge_alice_acme",
      source: "alice",
      target: "acme",
      attributes: {
        edgeId: "edge_alice_acme",
        edgeType: "WORKS_AT",
        weight: 1.0,
        visualPriority: 0.8,
        baseSize: 0.8,
        properties: {},
      },
    },
    {
      id: "edge_bob_alice",
      source: "bob",
      target: "alice",
      attributes: {
        edgeId: "edge_bob_alice",
        edgeType: "KNOWS",
        weight: 1.0,
        visualPriority: 0.8,
        baseSize: 0.8,
        properties: {},
      },
    },
    {
      id: "edge_acme_new_york",
      source: "acme",
      target: "new_york",
      attributes: {
        edgeId: "edge_acme_new_york",
        edgeType: "LOCATED_IN",
        weight: 1.0,
        visualPriority: 0.8,
        baseSize: 0.8,
        properties: {},
      },
    },
  ]);
}

test("deterministic graph contains exactly 4 nodes and 3 edges in store", () => {
  loadDeterministicTestGraph();

  assert.equal(graph.order, 4, "Expected exactly 4 nodes");
  assert.equal(graph.size, 3, "Expected exactly 3 edges");

  // Verify node identities and labels
  const alice = graph.getNodeAttributes("alice");
  const bob = graph.getNodeAttributes("bob");
  const acme = graph.getNodeAttributes("acme");
  const newYork = graph.getNodeAttributes("new_york");

  assert.equal(alice.label, "Alice");
  assert.equal(alice.nodeType, "Person");
  assert.equal(alice.color, "#63E6FF");

  assert.equal(bob.label, "Bob");
  assert.equal(bob.nodeType, "Person");
  assert.equal(bob.color, "#63E6FF");

  assert.equal(acme.label, "Acme");
  assert.equal(acme.nodeType, "Organization");
  assert.equal(acme.color, "#A78BFA");

  assert.equal(newYork.label, "New York");
  assert.equal(newYork.nodeType, "Location");
  assert.equal(newYork.color, "#34D399");

  // Verify edge connectivity and canonical edgeType labels
  const edgeAliceAcme = graph.getEdgeAttributes("edge_alice_acme");
  const edgeBobAlice = graph.getEdgeAttributes("edge_bob_alice");
  const edgeAcmeNewYork = graph.getEdgeAttributes("edge_acme_new_york");

  assert.equal(edgeAliceAcme.edgeType, "WORKS_AT");
  assert.equal(graph.source("edge_alice_acme"), "alice");
  assert.equal(graph.target("edge_alice_acme"), "acme");

  assert.equal(edgeBobAlice.edgeType, "KNOWS");
  assert.equal(graph.source("edge_bob_alice"), "bob");
  assert.equal(graph.target("edge_bob_alice"), "alice");

  assert.equal(edgeAcmeNewYork.edgeType, "LOCATED_IN");
  assert.equal(graph.source("edge_acme_new_york"), "acme");
  assert.equal(graph.target("edge_acme_new_york"), "new_york");
});

test("display graph resolution preserves all 4 nodes and 3 edges in full view", () => {
  loadDeterministicTestGraph();

  const { graph: displayGraph } = resolveDisplayGraph("", [], [], "full", { aggregationEnabled: false });

  assert.equal(displayGraph.order, 4);
  assert.equal(displayGraph.size, 3);
  assert.ok(displayGraph.hasNode("alice"));
  assert.ok(displayGraph.hasNode("bob"));
  assert.ok(displayGraph.hasNode("acme"));
  assert.ok(displayGraph.hasNode("new_york"));
  assert.ok(displayGraph.hasEdge("edge_alice_acme"));
  assert.ok(displayGraph.hasEdge("edge_bob_alice"));
  assert.ok(displayGraph.hasEdge("edge_acme_new_york"));
});

test("structural distance calculation resolves correct hop counts across the 3-edge chain", () => {
  loadDeterministicTestGraph();

  // From Bob: Bob (0) -> Alice (1) -> Acme (2) -> New York (3)
  const distances = buildStructuralDistanceSnapshot(graph, "bob", 3);

  assert.equal(distances.bob, 0);
  assert.equal(distances.alice, 1);
  assert.equal(distances.acme, 2);
  assert.equal(distances.new_york, 3);
});

test("edge rendering and canonical edge labels remain legible across zoom tiers and inspection modes", () => {
  loadDeterministicTestGraph();

  const canonicalEdges = [
    { id: "edge_alice_acme", source: "alice", target: "acme", label: "WORKS_AT" },
    { id: "edge_bob_alice", source: "bob", target: "alice", label: "KNOWS" },
    { id: "edge_acme_new_york", source: "acme", target: "new_york", label: "LOCATED_IN" },
  ];

  // 1. Edge attributes preserve canonical edgeType labels in graph store:
  for (const item of canonicalEdges) {
    const attrs = graph.getEdgeAttributes(item.id);
    assert.equal(attrs.edgeType, item.label, `Edge ${item.id} must have edgeType ${item.label}`);
    assert.equal(graph.source(item.id), item.source);
    assert.equal(graph.target(item.id), item.target);
  }

  // 2. In active context / neighbor state across all zoom tiers (overview, structure, inspection):
  const allTiers: GraphZoomTier[] = ["overview", "structure", "inspection"];
  for (const tier of allTiers) {
    for (const item of canonicalEdges) {
      const attrs = graph.getEdgeAttributes(item.id);
      const contextStyle = resolveEdgeElementStyle(
        GRAPH_THEME,
        tier,
        "neighbor",
        attrs,
        item.source,
        item.target,
        "full",
        item.id,
      );

      assert.equal(
        contextStyle.hidden,
        false,
        `Edge ${item.id} (${item.label}) in context state 'neighbor' must be visible in zoom tier '${tier}'`,
      );
      assert.ok(
        contextStyle.size !== undefined && contextStyle.size > 0,
        `Edge ${item.id} (${item.label}) must have positive render size in zoom tier '${tier}'`,
      );
    }
  }

  // 3. In selected state in inspection zoom tier (close examination of edge details and label):
  for (const item of canonicalEdges) {
    const attrs = graph.getEdgeAttributes(item.id);
    const selectedStyle = resolveEdgeElementStyle(
      GRAPH_THEME,
      "inspection",
      "selected",
      attrs,
      item.source,
      item.target,
      "full",
      item.id,
      "selected",
    );

    assert.equal(
      selectedStyle.hidden,
      false,
      `Selected edge ${item.id} (${item.label}) must be visible in inspection zoom tier`,
    );
    assert.ok(
      selectedStyle.size !== undefined && selectedStyle.size > 0,
      `Selected edge ${item.id} (${item.label}) must have positive render size`,
    );
  }

  // 4. Verify inspection zoom tier camera and arrow rendering settings
  assert.equal(GRAPH_THEME.zoomTiers.inspection.showContextualArrows, true);
  assert.equal(GRAPH_THEME.zoomTiers.inspection.showCurves, true);
});

test("node hover interaction preserves edge visibility and highlights canonical incident edge types", () => {
  loadDeterministicTestGraph();

  // Scenario 1: Hover Alice
  // Incident edges: Alice -> Acme (WORKS_AT) and Bob -> Alice (KNOWS)
  const aliceAttrs = graph.getNodeAttributes("alice");
  const aliceVisual = resolveNodeVisualState("alice", "structure", "alice", "", "", new Set(), new Set(), new Set());
  assert.equal(aliceVisual, "hovered");

  const aliceStyle = resolveNodeElementStyle(GRAPH_THEME, "structure", "hovered", aliceAttrs, "Alice");
  assert.equal(aliceStyle.forceLabel, true, "Hovered Alice must force-render label");
  assert.equal(aliceStyle.label, "Alice");
  assert.equal(aliceStyle.showHalo, true, "Hovered Alice must show interactive halo");

  const aliceIncidentEdges = new Set(["edge_alice_acme", "edge_bob_alice"]);

  // Edge Alice -> Acme (WORKS_AT) under Alice hover
  const aliceAcmeAttrs = graph.getEdgeAttributes("edge_alice_acme");
  assert.equal(aliceAcmeAttrs.edgeType, "WORKS_AT");
  const aliceAcmeState = resolveEdgeVisualState(
    "edge_alice_acme",
    "alice",
    "acme",
    "structure",
    "alice",
    "",
    "",
    new Set(),
    new Set(),
    aliceIncidentEdges,
  );
  assert.equal(aliceAcmeState, "hovered");
  const aliceAcmeStyle = resolveEdgeElementStyle(
    GRAPH_THEME,
    "structure",
    "hovered",
    aliceAcmeAttrs,
    "alice",
    "acme",
    "full",
    "edge_alice_acme",
  );
  assert.equal(aliceAcmeStyle.hidden, false, "Incident edge WORKS_AT must remain visible on hover");
  assert.ok(aliceAcmeStyle.size !== undefined && aliceAcmeStyle.size > 0);

  // Edge Bob -> Alice (KNOWS) under Alice hover
  const bobAliceAttrs = graph.getEdgeAttributes("edge_bob_alice");
  assert.equal(bobAliceAttrs.edgeType, "KNOWS");
  const bobAliceState = resolveEdgeVisualState(
    "edge_bob_alice",
    "bob",
    "alice",
    "structure",
    "alice",
    "",
    "",
    new Set(),
    new Set(),
    aliceIncidentEdges,
  );
  assert.equal(bobAliceState, "hovered");
  const bobAliceStyle = resolveEdgeElementStyle(
    GRAPH_THEME,
    "structure",
    "hovered",
    bobAliceAttrs,
    "bob",
    "alice",
    "full",
    "edge_bob_alice",
  );
  assert.equal(bobAliceStyle.hidden, false, "Incident edge KNOWS must remain visible on hover");

  // Non-incident edge Acme -> New York (LOCATED_IN) under Alice hover
  const acmeNyAttrs = graph.getEdgeAttributes("edge_acme_new_york");
  assert.equal(acmeNyAttrs.edgeType, "LOCATED_IN");
  const acmeNyState = resolveEdgeVisualState(
    "edge_acme_new_york",
    "acme",
    "new_york",
    "structure",
    "alice",
    "",
    "",
    new Set(),
    new Set(),
    aliceIncidentEdges,
  );
  assert.equal(acmeNyState, "muted");

  // Scenario 2: Hover Acme
  // Incident edges: Alice -> Acme (WORKS_AT) and Acme -> New York (LOCATED_IN)
  const acmeAttrs = graph.getNodeAttributes("acme");
  const acmeStyle = resolveNodeElementStyle(GRAPH_THEME, "structure", "hovered", acmeAttrs, "Acme");
  assert.equal(acmeStyle.forceLabel, true);
  assert.equal(acmeStyle.label, "Acme");

  const acmeIncidentEdges = new Set(["edge_alice_acme", "edge_acme_new_york"]);
  const acmeNyHoverState = resolveEdgeVisualState(
    "edge_acme_new_york",
    "acme",
    "new_york",
    "structure",
    "acme",
    "",
    "",
    new Set(),
    new Set(),
    acmeIncidentEdges,
  );
  assert.equal(acmeNyHoverState, "hovered");
  const acmeNyHoverStyle = resolveEdgeElementStyle(
    GRAPH_THEME,
    "structure",
    "hovered",
    acmeNyAttrs,
    "acme",
    "new_york",
    "full",
    "edge_acme_new_york",
  );
  assert.equal(acmeNyHoverStyle.hidden, false, "Incident edge LOCATED_IN must remain visible on hover");

  // Scenario 3: Hover Bob
  // Incident edge: Bob -> Alice (KNOWS)
  const bobAttrs = graph.getNodeAttributes("bob");
  const bobStyle = resolveNodeElementStyle(GRAPH_THEME, "structure", "hovered", bobAttrs, "Bob");
  assert.equal(bobStyle.forceLabel, true);
  assert.equal(bobStyle.label, "Bob");

  const bobIncidentEdges = new Set(["edge_bob_alice"]);
  const bobAliceHoverState = resolveEdgeVisualState(
    "edge_bob_alice",
    "bob",
    "alice",
    "structure",
    "bob",
    "",
    "",
    new Set(),
    new Set(),
    bobIncidentEdges,
  );
  assert.equal(bobAliceHoverState, "hovered");
});

test("edge selection maintains canonical edge type labels and active visual state", () => {
  loadDeterministicTestGraph();

  const edgeCases = [
    { id: "edge_alice_acme", source: "alice", target: "acme", label: "WORKS_AT" },
    { id: "edge_bob_alice", source: "bob", target: "alice", label: "KNOWS" },
    { id: "edge_acme_new_york", source: "acme", target: "new_york", label: "LOCATED_IN" },
  ];

  for (const { id, source, target, label } of edgeCases) {
    const attrs = graph.getEdgeAttributes(id);
    assert.equal(attrs.edgeType, label);

    const visualState = resolveEdgeVisualState(
      id,
      source,
      target,
      "inspection",
      null,
      "",
      id, // selected edge
      new Set(),
      new Set(),
    );
    assert.equal(visualState, "selected", `Selected edge ${id} must resolve to 'selected' state`);

    const style = resolveEdgeElementStyle(
      GRAPH_THEME,
      "inspection",
      "selected",
      attrs,
      source,
      target,
      "full",
      id,
      "selected",
    );

    assert.equal(style.hidden, false, `Selected edge ${id} (${label}) must not be hidden`);
    assert.ok(
      style.size !== undefined && style.size > 0,
      `Selected edge ${id} (${label}) must have positive render size`,
    );
  }
});

test("node labels remain forced visible during hover, selection, and inspection zoom tier", () => {
  loadDeterministicTestGraph();

  const nodes = ["alice", "bob", "acme", "new_york"];

  for (const nid of nodes) {
    const attrs = graph.getNodeAttributes(nid);

    // Hover state forces label visibility
    const hoverForcesLabel = shouldForceNodeLabel(GRAPH_THEME, "structure", "hovered", attrs, 0);
    assert.equal(hoverForcesLabel, true, `Node ${nid} label must force visible on hover`);

    // Selected state forces label visibility
    const selectForcesLabel = shouldForceNodeLabel(GRAPH_THEME, "structure", "selected", attrs, 0);
    assert.equal(selectForcesLabel, true, `Node ${nid} label must force visible on selection`);

    // Resolved style emits actual string label
    const style = resolveNodeElementStyle(GRAPH_THEME, "inspection", "hovered", attrs, attrs.label);
    assert.equal(style.forceLabel, true);
    assert.equal(style.label, attrs.label);
  }
});
