import assert from "node:assert/strict";
import test from "node:test";

import {
  inferOntologyUri,
  isEditableEntityType,
  ONTOLOGY_MINIMAP_THEME,
} from "../src/workspaces/OntologyWorkspace/ontologyEditorModel";

const registry = [
  { uri: "https://example.test/foo", name: "Foo" },
  { uri: "https://example.test/foo/nested", name: "Nested" },
];

test("ontology inference requires a URI delimiter and prefers the closest namespace", () => {
  assert.equal(inferOntologyUri(registry, "https://example.test/foobar/Class"), undefined);
  assert.equal(
    inferOntologyUri(registry, "https://example.test/foo/nested#Class"),
    "https://example.test/foo/nested",
  );
});

test("explicit scheme ownership wins when an entity uses another namespace", () => {
  assert.equal(
    inferOntologyUri(registry, "https://vocabulary.test/Class", "https://example.test/foo"),
    "https://example.test/foo",
  );
});

test("only draft-supported class and property nodes are editable", () => {
  assert.equal(isEditableEntityType("class"), true);
  assert.equal(isEditableEntityType("property"), true);
  assert.equal(isEditableEntityType("ontology"), false);
  assert.equal(isEditableEntityType("external"), false);
});

test("the ontology minimap has an explicit dark, high-contrast theme", () => {
  assert.equal(ONTOLOGY_MINIMAP_THEME.bgColor, "#0b1625");
  assert.equal(ONTOLOGY_MINIMAP_THEME.maskStrokeColor, "#5faeff");
  assert.equal(ONTOLOGY_MINIMAP_THEME.nodeStrokeColor, "#9acbff");
  assert.match(ONTOLOGY_MINIMAP_THEME.style.border, /#29435c/);
});
