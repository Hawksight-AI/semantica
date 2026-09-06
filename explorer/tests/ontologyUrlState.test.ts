import assert from "node:assert/strict";
import test from "node:test";

import {
  applyEntitySelection,
  applyTab,
  clearEntitySelection,
  hasOntologyUrlState,
  parseOntologyUrlState,
  readOntologyUrlState,
  removeEntitySelection,
  writeEntitySelection,
  writeTab,
} from "../src/workspaces/OntologyWorkspace/ontologyUrlState";

function withStubbedLocation(search: string, hash: string, body: () => void): string[] {
  const written: string[] = [];
  const original = (globalThis as { window?: unknown }).window;
  (globalThis as { window?: unknown }).window = {
    location: { search, hash },
    history: { replaceState: (_s: unknown, _t: string, url: string) => written.push(url) },
  };
  try {
    body();
  } finally {
    (globalThis as { window?: unknown }).window = original;
  }
  return written;
}

test("selecting an entity round-trips and pins the editor tab", () => {
  const search = applyEntitySelection("", "https://example.test/foo#Bar");
  assert.deepEqual(parseOntologyUrlState(search), {
    tab: "editor",
    entityUri: "https://example.test/foo#Bar",
  });
});

test("clearing the selection drops only the entity and keeps unrelated params", () => {
  const search = applyEntitySelection("?view=graph&depth=2", "https://example.test/foo#Bar");
  const cleared = parseOntologyUrlState(removeEntitySelection(search));

  assert.equal(cleared.entityUri, undefined);
  assert.equal(cleared.tab, "editor");
  assert.equal(new URLSearchParams(removeEntitySelection(search)).get("depth"), "2");
});

test("writing a tab leaves an existing entity selection alone", () => {
  const search = applyTab(applyEntitySelection("", "urn:x"), "health");
  assert.deepEqual(parseOntologyUrlState(search), { tab: "health", entityUri: "urn:x" });
});

test("absent params read as undefined, blank params as empty strings", () => {
  assert.deepEqual(parseOntologyUrlState(""), { tab: undefined, entityUri: undefined });
  assert.deepEqual(parseOntologyUrlState("?other=1"), { tab: undefined, entityUri: undefined });
  assert.deepEqual(parseOntologyUrlState("?ontologyTab=&ontologyEntity="), {
    tab: "",
    entityUri: "",
  });
});

test("a present but blank param still counts as ontology deep-link state", () => {
  assert.equal(hasOntologyUrlState("?ontologyEntity="), true);
  assert.equal(hasOntologyUrlState("?ontologyTab="), true);
  assert.equal(hasOntologyUrlState("?view=graph"), false);
  assert.equal(hasOntologyUrlState(""), false);
});

test("malformed search strings degrade to plain values instead of throwing", () => {
  assert.deepEqual(parseOntologyUrlState("???"), { tab: undefined, entityUri: undefined });
  assert.deepEqual(parseOntologyUrlState("ontologyEntity=urn%3Ax&&=&"), {
    tab: undefined,
    entityUri: "urn:x",
  });
});

test("entity URIs survive characters that need escaping", () => {
  const entityUri = "https://example.test/vocab#Has Part/&?=";
  const search = applyEntitySelection("?keep=1", entityUri);
  assert.equal(parseOntologyUrlState(search).entityUri, entityUri);
});

test("every writer preserves the URL fragment", () => {
  const written = withStubbedLocation("?view=graph", "#section-3", () => {
    writeTab("health");
    writeEntitySelection("urn:x");
    clearEntitySelection();
  });

  assert.deepEqual(written, [
    "?view=graph&ontologyTab=health#section-3",
    "?view=graph&ontologyTab=editor&ontologyEntity=urn%3Ax#section-3",
    "?view=graph#section-3",
  ]);
});

test("readOntologyUrlState with no argument reads live URL state", () => {
  withStubbedLocation("?ontologyTab=editor&ontologyEntity=urn%3Ax", "", () => {
    assert.deepEqual(readOntologyUrlState(), { tab: "editor", entityUri: "urn:x" });
    assert.equal(hasOntologyUrlState(), true);
  });
});
