import assert from "node:assert/strict";
import test from "node:test";

import { JSDOM } from "jsdom";
import React from "react";

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
dom.window.confirm = () => true;

// Testing Library and the components must load after the jsdom globals above.
const { act, cleanup, fireEvent, render, waitFor } = await import(
  "@testing-library/react"
);
const { MarkdownContentViewer } = await import(
  "../src/workspaces/GraphWorkspace/MarkdownContentViewer.tsx"
);
const { MemoryWorkspace } = await import(
  "../src/workspaces/MemoryWorkspace.tsx"
);

test.afterEach(() => {
  cleanup();
  dom.window.confirm = () => true;
});

const resource = { kind: "context-node" as const, id: "node-1" };
const originalSource = "---\nid: node-1\ntype: Note\n---\n\nOriginal";

function jsonResponse(body: unknown, status = 200): Response {
  return new Response(JSON.stringify(body), {
    status,
    headers: { "Content-Type": "application/json" },
  });
}

test("Edit and Apply send canonical Markdown and publish the applied result", async () => {
  const requests: Array<{ url: string; init?: RequestInit }> = [];
  let appliedBody = "";
  globalThis.fetch = async (input, init) => {
    requests.push({ url: String(input), init });
    if (init?.method === "PUT") {
      return jsonResponse({
        resource,
        source: originalSource.replace("Original", "Updated"),
        body: "Updated",
        revision: "sha256:updated",
        editable: true,
        changed: true,
      });
    }
    return jsonResponse({
      resource,
      source: originalSource,
      body: "Original",
      revision: "sha256:original",
      editable: true,
    });
  };

  const view = render(
    <MarkdownContentViewer
      content="Original"
      resource={resource}
      onApplied={(result) => { appliedBody = result.body; }}
    />,
  );
  fireEvent.click(view.getByRole("button", { name: "Edit" }));
  const textarea = await view.findByRole("textbox", { name: "Markdown source" });
  fireEvent.input(textarea, {
    target: { value: originalSource.replace("Original", "Updated") },
  });
  fireEvent.click(view.getByRole("button", { name: "Apply" }));

  await waitFor(() => assert.equal(appliedBody, "Updated"));
  assert.deepEqual(requests.map(({ init }) => init?.method ?? "GET"), ["GET", "PUT"]);
  assert.equal(
    JSON.parse(String(requests[1].init?.body)).expected_revision,
    "sha256:original",
  );
  assert.equal(
    view.getByRole("tab", { name: "Preview" }).getAttribute("aria-selected"),
    "true",
  );
});

test("Cancel restores the previous view and never sends a PUT", async () => {
  const methods: string[] = [];
  globalThis.fetch = async (_input, init) => {
    methods.push(init?.method ?? "GET");
    return jsonResponse({
      resource,
      source: originalSource,
      body: "Original",
      revision: "sha256:original",
      editable: true,
    });
  };

  const view = render(<MarkdownContentViewer content="Original" resource={resource} />);
  fireEvent.click(view.getByRole("button", { name: "Edit" }));
  const textarea = await view.findByRole("textbox", { name: "Markdown source" });
  fireEvent.input(textarea, {
    target: { value: originalSource.replace("Original", "Draft") },
  });
  fireEvent.click(view.getByRole("button", { name: "Cancel" }));

  assert.deepEqual(methods, ["GET"]);
  assert.equal(view.queryByRole("textbox", { name: "Markdown source" }), null);
  assert.equal(
    view.getByRole("tab", { name: "Preview" }).getAttribute("aria-selected"),
    "true",
  );
});

test("validation failures keep the draft visible for correction", async () => {
  globalThis.fetch = async (_input, init) => {
    if (init?.method === "PUT") {
      return jsonResponse({
        detail: {
          code: "invalid_markdown_frontmatter",
          message: "Markdown frontmatter contains invalid YAML.",
        },
      }, 422);
    }
    return jsonResponse({
      resource,
      source: originalSource,
      body: "Original",
      revision: "sha256:original",
      editable: true,
    });
  };

  const view = render(<MarkdownContentViewer content="Original" resource={resource} />);
  fireEvent.click(view.getByRole("button", { name: "Edit" }));
  const textarea = await view.findByRole("textbox", { name: "Markdown source" });
  const invalidDraft = "---\nid: [\n---\n\nDraft";
  fireEvent.input(textarea, { target: { value: invalidDraft } });
  fireEvent.click(view.getByRole("button", { name: "Apply" }));

  const alert = await view.findByRole("alert");
  assert.match(alert.textContent ?? "", /invalid YAML/);
  assert.equal(
    (view.getByRole("textbox", { name: "Markdown source" }) as HTMLTextAreaElement)
      .value,
    invalidDraft,
  );
});


test("resource changes discard the previous editor session", async () => {
  globalThis.fetch = async (input) => {
    const id = String(input).endsWith("node-2") ? "node-2" : "node-1";
    return jsonResponse({
      resource: { kind: "context-node", id },
      source: `---\nid: ${id}\ntype: Note\n---\n\n${id}`,
      body: id,
      revision: `sha256:${id}`,
      editable: true,
    });
  };

  const view = render(
    <MarkdownContentViewer content="node-1" resource={resource} />,
  );
  fireEvent.click(view.getByRole("button", { name: "Edit" }));
  const textarea = await view.findByRole("textbox", { name: "Markdown source" });
  fireEvent.input(textarea, {
    target: { value: `${(textarea as HTMLTextAreaElement).value}\nDraft` },
  });

  view.rerender(
    <MarkdownContentViewer
      content="node-2"
      resource={{ kind: "context-node", id: "node-2" }}
    />,
  );
  await waitFor(() => assert.equal(
    view.queryByRole("textbox", { name: "Markdown source" }),
    null,
  ));

  view.rerender(
    <MarkdownContentViewer content="node-1" resource={resource} />,
  );
  await waitFor(() => assert.equal(
    view.queryByRole("textbox", { name: "Markdown source" }),
    null,
  ));
  assert.ok(view.getByRole("button", { name: "Edit" }));
});


test("unmounting a dirty editor clears the parent dirty guard", async () => {
  const dirtyStates: boolean[] = [];
  globalThis.fetch = async () => jsonResponse({
    resource,
    source: originalSource,
    body: "Original",
    revision: "sha256:original",
    editable: true,
  });

  const view = render(
    <MarkdownContentViewer
      content="Original"
      resource={resource}
      onDirtyChange={(dirty) => dirtyStates.push(dirty)}
    />,
  );
  fireEvent.click(view.getByRole("button", { name: "Edit" }));
  const textarea = await view.findByRole("textbox", { name: "Markdown source" });
  fireEvent.input(textarea, {
    target: { value: originalSource.replace("Original", "Draft") },
  });
  await waitFor(() => assert.equal(dirtyStates.at(-1), true));

  view.unmount();

  assert.equal(dirtyStates.at(-1), false);
});

test("MemoryWorkspace protects a dirty memory draft when selection changes", async () => {
  const requestedUrls: string[] = [];
  globalThis.fetch = async (input) => {
    const url = String(input);
    requestedUrls.push(url);
    if (url.startsWith("/api/memories")) {
      return jsonResponse({
        items: [
          { id: "mem-1", type: "note", excerpt: "First", updated_at: null },
          { id: "mem-2", type: "note", excerpt: "Second", updated_at: null },
        ],
        total: 2,
        skip: 0,
        limit: 100,
      });
    }
    const id = url.endsWith("mem-2") ? "mem-2" : "mem-1";
    return jsonResponse({
      resource: { kind: "agent-memory", id },
      source: `---\nid: ${id}\ntype: note\n---\n\n${id}`,
      body: id,
      revision: `sha256:${id}`,
      editable: true,
    });
  };

  const view = render(<MemoryWorkspace />);
  await view.findByText("Selected memory");
  fireEvent.click(view.getByRole("button", { name: "Edit" }));
  const textarea = await view.findByRole("textbox", { name: "Markdown source" });
  fireEvent.input(textarea, {
    target: { value: `${(textarea as HTMLTextAreaElement).value}\nDraft` },
  });

  dom.window.confirm = () => false;
  fireEvent.click(view.getByRole("button", { name: /mem-2/ }));

  assert.equal(requestedUrls.some((url) => url.endsWith("mem-2")), false);
  assert.equal(view.getByText("mem-1", { selector: "strong" }).textContent, "mem-1");
});


test("MemoryWorkspace loads memories beyond the first server page", async () => {
  const requestedUrls: string[] = [];
  const firstPage = Array.from({ length: 100 }, (_, index) => ({
    id: `mem-${index + 1}`,
    type: "note",
    excerpt: `Memory ${index + 1}`,
    updated_at: null,
  }));
  globalThis.fetch = async (input) => {
    const url = String(input);
    requestedUrls.push(url);
    if (url === "/api/memories?skip=0&limit=100") {
      return jsonResponse({
        items: firstPage,
        total: 101,
        skip: 0,
        limit: 100,
      });
    }
    if (url === "/api/memories?skip=100&limit=100") {
      return jsonResponse({
        items: [{
          id: "mem-101",
          type: "note",
          excerpt: "Memory 101",
          updated_at: null,
        }],
        total: 101,
        skip: 100,
        limit: 100,
      });
    }
    return jsonResponse({
      resource: { kind: "agent-memory", id: "mem-1" },
      source: "---\nid: mem-1\ntype: note\n---\n\nmem-1",
      body: "mem-1",
      revision: "sha256:mem-1",
      editable: true,
    });
  };

  const view = render(<MemoryWorkspace />);
  await view.findByText("Selected memory");
  fireEvent.click(view.getByRole("button", { name: "Load more memories" }));

  await view.findByRole("button", { name: /mem-101/ });
  assert.ok(requestedUrls.includes("/api/memories?skip=100&limit=100"));
  assert.equal(view.getByText("101 of 101 loaded").textContent, "101 of 101 loaded");
});


test("MemoryWorkspace ignores stale selection responses", async () => {
  let resolveMem2: ((response: Response) => void) | undefined;
  let resolveMem3: ((response: Response) => void) | undefined;
  const mem2Response = new Promise<Response>((resolve) => {
    resolveMem2 = resolve;
  });
  const mem3Response = new Promise<Response>((resolve) => {
    resolveMem3 = resolve;
  });

  globalThis.fetch = async (input) => {
    const url = String(input);
    if (url.startsWith("/api/memories")) {
      return jsonResponse({
        items: [
          { id: "mem-1", type: "note", excerpt: "First", updated_at: null },
          { id: "mem-2", type: "note", excerpt: "Second", updated_at: null },
          { id: "mem-3", type: "note", excerpt: "Third", updated_at: null },
        ],
        total: 3,
        skip: 0,
        limit: 100,
      });
    }
    if (url.endsWith("mem-2")) return mem2Response;
    if (url.endsWith("mem-3")) return mem3Response;
    return jsonResponse({
      resource: { kind: "agent-memory", id: "mem-1" },
      source: "---\nid: mem-1\ntype: note\n---\n\nmem-1",
      body: "mem-1",
      revision: "sha256:mem-1",
      editable: true,
    });
  };

  const view = render(<MemoryWorkspace />);
  await view.findByText("Selected memory");
  fireEvent.click(view.getByRole("button", { name: /mem-2/ }));
  fireEvent.click(view.getByRole("button", { name: /mem-3/ }));

  await act(async () => {
    resolveMem3?.(jsonResponse({
      resource: { kind: "agent-memory", id: "mem-3" },
      source: "---\nid: mem-3\ntype: note\n---\n\nmem-3",
      body: "mem-3",
      revision: "sha256:mem-3",
      editable: true,
    }));
    await mem3Response;
  });
  await waitFor(() => assert.equal(
    view.getByText("mem-3", { selector: "strong" }).textContent,
    "mem-3",
  ));

  await act(async () => {
    resolveMem2?.(jsonResponse({
      resource: { kind: "agent-memory", id: "mem-2" },
      source: "---\nid: mem-2\ntype: note\n---\n\nmem-2",
      body: "mem-2",
      revision: "sha256:mem-2",
      editable: true,
    }));
    await mem2Response;
  });

  assert.equal(
    view.getByText("mem-3", { selector: "strong" }).textContent,
    "mem-3",
  );
});


test("MemoryWorkspace refreshes frontmatter summaries after apply", async () => {
  let listRequests = 0;
  globalThis.fetch = async (input, init) => {
    const url = String(input);
    if (url.startsWith("/api/memories")) {
      listRequests += 1;
      const saved = listRequests > 1;
      return jsonResponse({
        items: [{
          id: "mem-1",
          type: saved ? "decision" : "note",
          excerpt: saved ? "Updated memory" : "Original memory",
          updated_at: saved ? "2026-09-01T12:00:00+00:00" : null,
        }],
        total: 1,
        skip: 0,
        limit: 100,
      });
    }
    if (init?.method === "PUT") {
      return jsonResponse({
        resource: { kind: "agent-memory", id: "mem-1" },
        source: "---\nid: mem-1\ntype: decision\n---\n\nUpdated memory",
        body: "Updated memory",
        revision: "sha256:updated",
        editable: true,
        changed: true,
      });
    }
    return jsonResponse({
      resource: { kind: "agent-memory", id: "mem-1" },
      source: "---\nid: mem-1\ntype: note\n---\n\nOriginal memory",
      body: "Original memory",
      revision: "sha256:original",
      editable: true,
    });
  };

  const view = render(<MemoryWorkspace />);
  await view.findByText("Selected memory");
  fireEvent.click(view.getByRole("button", { name: "Edit" }));
  const textarea = await view.findByRole("textbox", { name: "Markdown source" });
  fireEvent.input(textarea, {
    target: {
      value: (textarea as HTMLTextAreaElement).value
        .replace("type: note", "type: decision")
        .replace("Original memory", "Updated memory"),
    },
  });
  fireEvent.click(view.getByRole("button", { name: "Apply" }));

  await view.findByText("decision");
  assert.equal(listRequests, 2);
  assert.equal(view.getAllByText("Updated memory").length, 2);
});
