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
  resolveDisplayGraph,
  resolveEdgeElementStyle,
} from "../src/workspaces/GraphWorkspace/graphSceneState.ts";
import { GRAPH_THEME } from "../src/workspaces/GraphWorkspace/graphTheme.ts";

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
  assert.equal(bob.label, "Bob");
  assert.equal(bob.nodeType, "Person");
  assert.equal(acme.label, "Acme");
  assert.equal(acme.nodeType, "Organization");
  assert.equal(newYork.label, "New York");
  assert.equal(newYork.nodeType, "Location");

  // Verify edge connectivity and labels/types
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

test("edge visual state and styling resolves correctly on selection and hover", () => {
  loadDeterministicTestGraph();

  const style = resolveEdgeElementStyle(
    GRAPH_THEME,
    "inspection",
    "selected",
    {
      edgeType: "WORKS_AT",
      weight: 1,
      properties: {},
      visualPriority: 0.8,
      baseSize: 0.7,
    },
    "alice",
    "acme",
    "full",
    "edge_alice_acme",
    "selected",
  );

  assert.equal(style.hidden, false);
  assert.ok(style.size > 0);
});
