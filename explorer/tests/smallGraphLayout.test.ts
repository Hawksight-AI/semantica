import assert from "node:assert/strict";
import test from "node:test";

import {
  SMALL_GRAPH_MAX_NODES,
  buildSmallGraphSeedPositions,
  resolveGraphLayoutDecision,
  resolveNodeLayoutPosition,
  shouldUseSmallGraphLayout,
} from "../src/workspaces/GraphWorkspace/smallGraphLayout.ts";

test("small graph layout is selected only when coordinates are not already usable", () => {
  assert.equal(shouldUseSmallGraphLayout(12, 0), true);
  assert.equal(shouldUseSmallGraphLayout(SMALL_GRAPH_MAX_NODES + 1, 0), false);
  assert.equal(shouldUseSmallGraphLayout(12, 0.95), false);
});

test("small graph layout ignores isolated partial coordinates", () => {
  const decision = resolveGraphLayoutDecision(12, 1 / 12);
  assert.deepEqual(
    resolveNodeLayoutPosition(decision, { x: 50_000, y: -50_000 }, { x: 24, y: -18 }),
    { x: 24, y: -18 },
  );
  assert.deepEqual(
    resolveNodeLayoutPosition(decision, { x: 50_000, y: null }, { x: -12, y: 36 }),
    { x: -12, y: 36 },
  );
});

test("small graph load is immediately ready and skips runtime stabilization", () => {
  assert.deepEqual(resolveGraphLayoutDecision(12, 0), {
    useProvidedCoordinates: false,
    useSmallGraphLayout: true,
    layoutReady: true,
  });
  assert.deepEqual(resolveGraphLayoutDecision(SMALL_GRAPH_MAX_NODES + 1, 0), {
    useProvidedCoordinates: false,
    useSmallGraphLayout: false,
    layoutReady: false,
  });
  assert.deepEqual(resolveGraphLayoutDecision(12, 1), {
    useProvidedCoordinates: true,
    useSmallGraphLayout: false,
    layoutReady: true,
  });
});

test("small graph layout is deterministic and keeps connected nodes together", () => {
  const nodes = ["Apple", "Steve", "Ronald", "Cupertino", "California"];
  const edges = [
    { source: "Apple", target: "Steve" },
    { source: "Ronald", target: "Cupertino" },
  ];
  const first = buildSmallGraphSeedPositions(nodes, edges);
  const second = buildSmallGraphSeedPositions([...nodes].reverse(), [...edges].reverse());

  assert.deepEqual([...first.entries()].sort(), [...second.entries()].sort());
  assert.equal(first.size, nodes.length);

  const distance = (left: string, right: string) => {
    const a = first.get(left);
    const b = first.get(right);
    assert.ok(a && b);
    return Math.hypot(a.x - b.x, a.y - b.y);
  };
  assert.ok(distance("Apple", "Steve") < distance("Apple", "California"));
  assert.ok(distance("Ronald", "Cupertino") < distance("Ronald", "California"));
});

test("small graph layout keeps maximum-radius components separated", () => {
  const componentCount = 4;
  const nodesPerComponent = 12;
  const nodes = Array.from(
    { length: componentCount * nodesPerComponent },
    (_, index) => `component-${Math.floor(index / nodesPerComponent)}-node-${index % nodesPerComponent}`,
  );
  const edges = Array.from({ length: componentCount }).flatMap((_, componentIndex) => {
    const prefix = `component-${componentIndex}-node-`;
    return Array.from({ length: nodesPerComponent - 1 }, (_unused, nodeIndex) => ({
      source: `${prefix}${nodeIndex}`,
      target: `${prefix}${nodeIndex + 1}`,
    }));
  });
  const positions = buildSmallGraphSeedPositions(nodes, edges);

  for (let leftComponent = 0; leftComponent < componentCount; leftComponent += 1) {
    for (let rightComponent = leftComponent + 1; rightComponent < componentCount; rightComponent += 1) {
      let closestDistance = Number.POSITIVE_INFINITY;
      for (let leftNode = 0; leftNode < nodesPerComponent; leftNode += 1) {
        for (let rightNode = 0; rightNode < nodesPerComponent; rightNode += 1) {
          const left = positions.get(`component-${leftComponent}-node-${leftNode}`);
          const right = positions.get(`component-${rightComponent}-node-${rightNode}`);
          assert.ok(left && right);
          closestDistance = Math.min(closestDistance, Math.hypot(left.x - right.x, left.y - right.y));
        }
      }
      assert.ok(closestDistance >= 48, `components are only ${closestDistance} units apart`);
    }
  }
});
