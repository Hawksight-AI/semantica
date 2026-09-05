import assert from "node:assert/strict";
import test from "node:test";

import {
  NodeMarkdownRefreshGuard,
  buildNodeMarkdownAttributeUpdate,
  readNodeMarkdownAttributeUpdate,
} from "../src/workspaces/GraphWorkspace/nodeMarkdownSync.ts";


test("saved Markdown updates graph content and its visible label", () => {
  const update = buildNodeMarkdownAttributeUpdate(
    "issue-1327",
    "# Issue 1328888\n\nUpdated body",
    { status: "implemented" },
  );

  assert.equal(update.content, "# Issue 1328888\n\nUpdated body");
  assert.equal(update.label, "# Issue 1328888\n\nUpdated body");
  assert.deepEqual(update.properties, {
    status: "implemented",
    content: "# Issue 1328888\n\nUpdated body",
  });
});


test("empty Markdown falls back to the stable node id label", () => {
  const update = buildNodeMarkdownAttributeUpdate("issue-1327", "", {});

  assert.equal(update.label, "issue-1327");
  assert.equal(update.content, "");
});


test("saved frontmatter is refreshed from the canonical graph node", async () => {
  const update = await readNodeMarkdownAttributeUpdate(
    "node/1",
    async (input) => {
      assert.equal(String(input), "/api/graph/node?node_id=node%2F1");
      return new Response(JSON.stringify({
        id: "node/1",
        type: "Decision",
        content: "Updated body",
        properties: {
          content: "Updated body",
          status: "accepted",
          valid_from: "2026-09-01T00:00:00Z",
        },
        valid_from: "2026-09-01T00:00:00Z",
        valid_until: null,
      }), {
        status: 200,
        headers: { "Content-Type": "application/json" },
      });
    },
  );
  assert.deepEqual(update, {
    label: "Updated body",
    content: "Updated body",
    properties: {
      content: "Updated body",
      status: "accepted",
      valid_from: "2026-09-01T00:00:00Z",
    },
    nodeType: "Decision",
    valid_from: "2026-09-01T00:00:00Z",
    valid_until: null,
  });
});


test("realtime updates invalidate an older local-save refresh", () => {
  const guard = new NodeMarkdownRefreshGuard();
  const localSaveRefresh = guard.begin("node-1");

  guard.invalidate("node-1");

  assert.equal(guard.isCurrent("node-1", localSaveRefresh), false);
});


test("refresh invalidation is scoped to one node", () => {
  const guard = new NodeMarkdownRefreshGuard();
  const firstNodeRefresh = guard.begin("node-1");
  const secondNodeRefresh = guard.begin("node-2");

  guard.invalidate("node-1");

  assert.equal(guard.isCurrent("node-1", firstNodeRefresh), false);
  assert.equal(guard.isCurrent("node-2", secondNodeRefresh), true);
});
