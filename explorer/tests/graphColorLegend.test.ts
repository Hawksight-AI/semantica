import assert from "node:assert/strict";
import test from "node:test";
import Graph from "graphology";

import type { NodeAttributes } from "../src/store/graphStore.ts";
import { buildGraphColorLegend } from "../src/workspaces/GraphWorkspace/graphColorLegend.ts";
import { resolveNodeElementStyle } from "../src/workspaces/GraphWorkspace/graphSceneState.ts";
import { GRAPH_THEME, withAlpha } from "../src/workspaces/GraphWorkspace/graphTheme.ts";

function attributes(overrides: Partial<NodeAttributes> = {}): NodeAttributes {
  return {
    label: "Example", content: "Example", x: 0, y: 0, size: 8,
    nodeType: "Person", semanticGroup: "Person", color: "#123456",
    properties: {}, ...overrides,
  };
}

test("legend matches normal canvas colors, including color and theme fallbacks", () => {
  const graph = new Graph();
  const samples = [
    attributes({ baseColor: "#abcdef" }),
    attributes({ semanticGroup: "Organization" }),
    attributes({ semanticGroup: "Location", color: "" }),
  ];
  samples.forEach((attrs, i) => graph.addNode(String(i), attrs));
  const items = buildGraphColorLegend(graph);
  for (const attrs of samples) {
    const item = items.find((entry) => entry.group === attrs.semanticGroup)!;
    const style = resolveNodeElementStyle(GRAPH_THEME, "inspection", "default", attrs, attrs.label);
    assert.equal(style.color, withAlpha(item.color, GRAPH_THEME.nodes.entityShapes.entity.fillAlpha));
  }
  assert.equal(items.find((item) => item.group === "Person")?.color, "#abcdef");
  assert.equal(items.find((item) => item.group === "Organization")?.color, "#123456");
  assert.equal(items.find((item) => item.group === "Location")?.color, GRAPH_THEME.palette.semantic[0]);
});

test("semantic groups, not shape categories, determine labels and distinct entries", () => {
  const graph = new Graph();
  graph.addNode("one", attributes({ semanticGroup: "Research", entityShape: "compound" }));
  graph.addNode("two", attributes({ semanticGroup: "Research", entityShape: "entity" }));
  graph.addNode("synthetic", attributes({ semanticGroup: "Research", baseColor: "#654321", isCommunityGroup: true }));
  graph.addNode("hidden", { ...attributes(), hidden: true });
  assert.deepEqual(buildGraphColorLegend(graph).map(({ group, color, count }) => ({ group, color, count })), [
    { group: "Research", color: "#123456", count: 2 },
    { group: "Research", color: "#654321", count: 1 },
  ]);
  assert.equal(new Set(buildGraphColorLegend(graph).map((item) => item.id)).size, 2);
});

test("legend rebuilds after in-place changes and uses only the supplied display graph", () => {
  const graph = new Graph();
  graph.addNode("one", attributes());
  graph.addNode("two", attributes({ semanticGroup: "Location" }));
  const first = buildGraphColorLegend(graph);
  graph.mergeNodeAttributes("one", { semanticGroup: "Project", baseColor: "#fedcba" });
  graph.dropNode("two");
  assert.equal(first.length, 2);
  assert.deepEqual(buildGraphColorLegend(graph).map(({ group, color }) => ({ group, color })), [
    { group: "Project", color: "#fedcba" },
  ]);
  graph.clear();
  assert.deepEqual(buildGraphColorLegend(graph), []);
});

test("fallback labels and ordering are stable and no groups are silently dropped", () => {
  const graph = new Graph();
  graph.addNode("fallback", attributes({ semanticGroup: undefined, nodeType: "" }));
  for (let i = 11; i >= 0; i -= 1) graph.addNode(String(i), attributes({ semanticGroup: undefined, nodeType: `Type ${i}` }));
  const items = buildGraphColorLegend(graph);
  assert.equal(items.length, 13);
  assert.ok(items.some((item) => item.group === "entity"));
  const reverse = new Graph();
  graph.nodes().reverse().forEach((id) => reverse.addNode(id, graph.getNodeAttributes(id)));
  assert.deepEqual(items, buildGraphColorLegend(reverse));
});
