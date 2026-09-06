import assert from "node:assert/strict";
import test from "node:test";

import {
  classifyNodeType,
  compactNodeType,
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

test("node types classify identically in compact and full IRI form", () => {
  const cases: Array<[string, string, string]> = [
    ["owl:Ontology", "http://www.w3.org/2002/07/owl#Ontology", "ontology"],
    ["owl:Class", "http://www.w3.org/2002/07/owl#Class", "class"],
    ["rdfs:Class", "http://www.w3.org/2000/01/rdf-schema#Class", "class"],
    ["owl:ObjectProperty", "http://www.w3.org/2002/07/owl#ObjectProperty", "property"],
    ["owl:DatatypeProperty", "http://www.w3.org/2002/07/owl#DatatypeProperty", "property"],
    ["owl:AnnotationProperty", "http://www.w3.org/2002/07/owl#AnnotationProperty", "property"],
  ];
  for (const [compact, fullIri, expected] of cases) {
    assert.equal(classifyNodeType(compact), expected, compact);
    assert.equal(classifyNodeType(fullIri), expected, fullIri);
  }
  assert.equal(classifyNodeType("owl:NamedIndividual"), "external");
  assert.equal(classifyNodeType("http://www.w3.org/2004/02/skos/core#Concept"), "external");
});

test("compactNodeType leaves unknown namespaces untouched", () => {
  assert.equal(compactNodeType("https://example.org/custom#Thing"), "https://example.org/custom#Thing");
  assert.equal(compactNodeType("owl:Class"), "owl:Class");
});
