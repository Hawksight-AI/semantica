import assert from "node:assert/strict";
import { spawn } from "node:child_process";
import { setTimeout as delay } from "node:timers/promises";
import test from "node:test";
import { chromium, type Page } from "playwright";

const BASE_URL = "http://127.0.0.1:4175";
const initialNodes = [
  { id: "alice", type: "Person", content: "Alice", properties: {} },
  { id: "bob", type: "Person", content: "Bob", properties: {} },
  { id: "acme", type: "Organization", content: "Acme", properties: {} },
  { id: "london", type: "Location", content: "London", properties: {} },
  { id: "research", type: "Project", content: "Research", properties: {} },
  { id: "report", type: "Document", content: "Report", properties: {} },
];
const edges = [
  ["alice", "acme", "WORKS_AT"], ["bob", "acme", "WORKS_AT"],
  ["acme", "london", "LOCATED_IN"], ["alice", "research", "LEADS"],
  ["bob", "report", "AUTHORED"], ["report", "research", "DESCRIBES"],
].map(([source, target, type], i) => ({
  id: `edge_${i}`, familyId: `edge_${i}`, source, target, type, weight: 1, properties: {},
}));

async function assertLegendMatchesGraph(page: Page) {
  const result = await page.evaluate(async () => {
    const storePath = "/src/store/graphStore.ts";
    const { graph } = await import(storePath);
    const colors: Record<string, string> = {};
    graph.forEachNode((_id: string, attrs: { semanticGroup: string; baseColor: string }) => {
      const hex = attrs.baseColor.replace("#", "");
      colors[attrs.semanticGroup] = `rgb(${[0, 2, 4].map((i) => parseInt(hex.slice(i, i + 2), 16)).join(", ")})`;
    });
    const items = [...document.querySelectorAll(".explore-color-legend-item")].map((item) => ({
      group: item.querySelector(".explore-color-legend-name")?.textContent,
      color: getComputedStyle(item.querySelector(".explore-color-legend-mark")!).backgroundColor,
    }));
    return { colors, items };
  });
  assert.equal(result.items.length, Object.keys(result.colors).length);
  for (const item of result.items) {
    assert.equal(item.color, result.colors[item.group!], `Swatch for ${item.group} must match the loaded canvas color`);
  }
}

test("visible legend follows loaded data, reloads, and distance mode", async (t) => {
  const server = spawn("npm", ["run", "dev", "--", "--host", "127.0.0.1", "--port", "4175", "--strictPort"], { stdio: "ignore" });
  t.after(() => { server.kill(); });
  let ready = false;
  for (let i = 0; i < 100; i += 1) {
    try { if ((await fetch(BASE_URL)).ok) { ready = true; break; } } catch { /* Starting Vite. */ }
    await delay(100);
  }
  assert.ok(ready, "Vite must start");
  const browser = await chromium.launch({ headless: true, executablePath: process.env.CHROMIUM_PATH || undefined });
  t.after(() => browser.close());
  const page = await browser.newPage({ viewport: { width: 1440, height: 1000 } });
  page.setDefaultTimeout(10_000);
  const errors: string[] = [];
  page.on("pageerror", (error) => errors.push(error.message));
  page.on("console", (message) => { if (message.type() === "error") errors.push(message.text()); });
  let nodes = initialNodes;
  await page.routeWebSocket("**/ws/graph-updates", () => {});
  await page.route("**/api/**", async (route) => {
    const path = new URL(route.request().url()).pathname;
    let json: unknown = {};
    if (path === "/api/info") json = { capabilities: { agent_memory: false } };
    if (path === "/api/graph/stats") json = { node_count: nodes.length, edge_count: edges.length };
    if (path === "/api/graph/nodes") json = { nodes, total: nodes.length, next_cursor: null };
    if (path === "/api/graph/edges") json = { edges, total: edges.length, next_cursor: null };
    if (path === "/api/temporal/bounds") json = { min: null, max: null };
    if (path === "/api/temporal/snapshot") json = { active_node_ids: nodes.map((n) => n.id), active_node_count: nodes.length };
    if (path === "/api/graph/search") json = { results: [{ node: nodes[0], score: 1 }] };
    await route.fulfill({ json });
  });
  await page.goto(BASE_URL);
  await page.getByRole("button", { name: "Open Semantica Explorer" }).click();
  const legend = page.getByRole("group", { name: "Node colors" });
  await legend.waitFor();
  await page.locator("canvas").first().waitFor({ state: "visible" });
  await assertLegendMatchesGraph(page);
  assert.equal(await legend.getByText("Person", { exact: true }).count(), 1);
  assert.equal(await legend.getByText("Biomolecule", { exact: true }).count(), 0);

  nodes = initialNodes.map((node) => ({ ...node, type: node.type === "Person" ? "Researcher" : node.type }));
  await page.getByRole("button", { name: "Reload graph data" }).click();
  await legend.getByText("Researcher", { exact: true }).waitFor();
  assert.equal(await legend.getByText("Person", { exact: true }).count(), 0);
  await assertLegendMatchesGraph(page);

  await page.getByPlaceholder("Search command, node, or concept").fill("Alice");
  await page.getByRole("option").filter({ hasText: "Alice" }).click();
  const heatmap = page.getByRole("button", { name: "Heatmap", exact: true });
  await heatmap.click();
  await legend.waitFor({ state: "hidden" });
  await heatmap.click();
  await legend.waitFor();
  await assertLegendMatchesGraph(page);
  assert.deepEqual(errors, []);
});
