import assert from "node:assert/strict";
import { spawn, type ChildProcess } from "node:child_process";
import { existsSync } from "node:fs";
import { setTimeout as delay } from "node:timers/promises";
import test from "node:test";
import { chromium, type Page } from "playwright";

const PORT = 4173;
const BASE_URL = `http://127.0.0.1:${PORT}`;

const nodes = [
  { id: "alice", type: "Person", content: "Alice", properties: {} },
  { id: "bob", type: "Person", content: "Bob", properties: {} },
  { id: "acme", type: "Organization", content: "Acme", properties: {} },
  { id: "new_york", type: "Location", content: "New York", properties: {} },
];

const edges = [
  { id: "edge_alice_acme", familyId: "edge_alice_acme", source: "alice", target: "acme", type: "WORKS_AT", weight: 1, properties: {} },
  { id: "edge_bob_alice", familyId: "edge_bob_alice", source: "bob", target: "alice", type: "KNOWS", weight: 1, properties: {} },
  { id: "edge_acme_new_york", familyId: "edge_acme_new_york", source: "acme", target: "new_york", type: "LOCATED_IN", weight: 1, properties: {} },
];

let server: ChildProcess | undefined;

async function startVite(): Promise<void> {
  server = spawn("npm", ["run", "dev", "--", "--host", "127.0.0.1", "--port", String(PORT)], {
    cwd: process.cwd(),
    stdio: "ignore",
  });

  for (let attempt = 0; attempt < 50; attempt += 1) {
    try {
      const response = await fetch(BASE_URL);
      if (response.ok) return;
    } catch {
      // Vite is still starting.
    }
    await delay(100);
  }
  throw new Error("Vite did not become ready");
}

async function installApiFixture(page: Page): Promise<void> {
  await page.route("**/api/info", async (route) => {
    await route.fulfill({ json: { capabilities: { agent_memory: false } } });
  });
  await page.route("**/api/graph/**", async (route) => {
    const pathname = new URL(route.request().url()).pathname;
    if (pathname === "/api/graph/stats") {
      await route.fulfill({ json: { node_count: 4, edge_count: 3 } });
    } else if (pathname === "/api/graph/nodes") {
      await route.fulfill({ json: { nodes, total: nodes.length, skip: 0, limit: 1000, next_cursor: null } });
    } else if (pathname === "/api/graph/edges") {
      await route.fulfill({ json: { edges, total: edges.length, skip: 0, limit: 1000, next_cursor: null } });
    } else {
      await route.continue();
    }
  });
}

test("real Explorer loading path hydrates and renders API edge labels", async (t) => {
  await startVite();
  t.after(async () => {
    server?.kill();
  });

  const browser = await chromium.launch({
    headless: true,
    executablePath: process.env.CHROMIUM_PATH || (existsSync("/usr/bin/chromium") ? "/usr/bin/chromium" : undefined),
  });
  t.after(() => browser.close());
  const page = await browser.newPage({ viewport: { width: 1440, height: 1000 } });

  await page.addInitScript(() => {
    const captured = (window as Window & { __capturedCanvasText?: string[] }).__capturedCanvasText = [];
    const originalFillText = CanvasRenderingContext2D.prototype.fillText;
    CanvasRenderingContext2D.prototype.fillText = function (text: string, ...args: [number, number, number?, number?]) {
      captured.push(String(text));
      return originalFillText.call(this, text, ...args);
    };
  });
  await installApiFixture(page);
  await page.goto(BASE_URL);
  await page.getByRole("button", { name: /Open Semantica Explorer/ }).click();

  await page.locator("canvas").nth(0).waitFor({ state: "attached" });
  await page.waitForFunction(() => document.querySelectorAll("canvas").length >= 2);
  await page.waitForFunction(() => {
    const labels = (window as Window & { __capturedCanvasText?: string[] }).__capturedCanvasText ?? [];
    return ["WORKS_AT", "KNOWS", "LOCATED_IN"].every((label) => labels.includes(label));
  }, undefined, { timeout: 10_000 });

  const capturedLabels = await page.evaluate(() => (window as Window & { __capturedCanvasText?: string[] }).__capturedCanvasText ?? []);
  for (const label of ["WORKS_AT", "KNOWS", "LOCATED_IN"]) {
    assert.ok(capturedLabels.includes(label), `Expected rendered edge label ${label}`);
  }
  assert.ok(capturedLabels.includes("Alice"));

  await page.getByRole("button", { name: "Zoom In" }).click();
  await page.waitForTimeout(250);
  const labelsAfterZoom = await page.evaluate(() => (window as Window & { __capturedCanvasText?: string[] }).__capturedCanvasText ?? []);
  for (const label of ["WORKS_AT", "KNOWS", "LOCATED_IN"]) {
    assert.ok(labelsAfterZoom.includes(label), `Expected edge label ${label} after zoom`);
  }
});
