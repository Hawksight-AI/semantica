import assert from "node:assert/strict";
import test from "node:test";

import { JSDOM } from "jsdom";
import React from "react";

import { fetchAgentMemoryAvailability } from "../src/explorerCapabilities.ts";

(globalThis as typeof globalThis & { React: typeof React }).React = React;
const dom = new JSDOM("<!doctype html><html><body></body></html>", {
  url: "http://localhost",
});
Object.assign(globalThis, {
  window: dom.window,
  document: dom.window.document,
  HTMLElement: dom.window.HTMLElement,
  Node: dom.window.Node,
});
Object.defineProperty(globalThis, "navigator", {
  configurable: true,
  value: dom.window.navigator,
});

const { cleanup, render } = await import("@testing-library/react");
const { ExploreWorkspaceTabs } = await import("../src/ExploreWorkspaceTabs.tsx");

test.afterEach(cleanup);

test("reports AgentMemory when the Explorer host provides it", async () => {
  const available = await fetchAgentMemoryAvailability(async () => (
    new Response(
      JSON.stringify({ capabilities: { agent_memory: true } }),
      { status: 200, headers: { "content-type": "application/json" } },
    )
  ));

  assert.equal(available, true);
});

test("keeps AgentMemory hidden when the capability is absent or unavailable", async () => {
  const absent = await fetchAgentMemoryAvailability(async () => (
    new Response(JSON.stringify({ status: "active" }), { status: 200 })
  ));
  const unavailable = await fetchAgentMemoryAvailability(async () => {
    throw new Error("network unavailable");
  });

  assert.equal(absent, false);
  assert.equal(unavailable, false);
});

test("shows the Memories tab only when the host provides AgentMemory", () => {
  const availableView = render(
    <ExploreWorkspaceTabs
      activeView="graph"
      agentMemoryAvailable
      onSelect={() => undefined}
    />,
  );
  assert.ok(availableView.getByRole("button", { name: "Memories" }));
  cleanup();

  const unavailableView = render(
    <ExploreWorkspaceTabs
      activeView="graph"
      agentMemoryAvailable={false}
      onSelect={() => undefined}
    />,
  );
  assert.equal(
    unavailableView.queryByRole("button", { name: "Memories" }),
    null,
  );
});
