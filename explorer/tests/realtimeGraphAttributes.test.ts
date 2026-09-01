import assert from "node:assert/strict";
import test from "node:test";

import { buildRealtimeEdgeAttributes } from "../src/workspaces/GraphWorkspace/realtimeGraphAttributes.ts";

const payload = {
  id: "edge-live",
  source_id: "source",
  target_id: "target",
  type: "related_to",
  properties: {},
};

test("realtime edges retain the active small-graph visibility marker", () => {
  const attributes = buildRealtimeEdgeAttributes(payload, {
    isBidirectional: false,
    isSmallGraph: true,
  });

  assert.equal(attributes.isSmallGraph, true);
  assert.equal(attributes.edgeVariant, "directional");
});

test("realtime edges do not retain the marker after graph leaves small-graph mode", () => {
  const attributes = buildRealtimeEdgeAttributes(payload, {
    isBidirectional: false,
    isSmallGraph: false,
  });

  assert.equal(attributes.isSmallGraph, false);
});
