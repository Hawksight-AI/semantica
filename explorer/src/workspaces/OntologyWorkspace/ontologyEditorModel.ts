export type EditorEntityType = "ontology" | "class" | "property" | "external";

export type RegistryEntry = {
  uri: string;
  name: string;
};

export const ONTOLOGY_MINIMAP_THEME = {
  bgColor: "#0b1625",
  maskColor: "rgba(7, 17, 31, 0.72)",
  maskStrokeColor: "#5faeff",
  maskStrokeWidth: 2,
  nodeColor: "#2d7fd3",
  nodeStrokeColor: "#9acbff",
  nodeStrokeWidth: 1,
  style: {
    border: "1px solid #29435c",
    borderRadius: 6,
    boxShadow: "0 4px 16px rgba(0, 0, 0, 0.32)",
  },
} as const;

// The backend emits node types in compact (owl:Class) or full IRI
// (http://www.w3.org/2002/07/owl#Class) form; classification must accept both.
const FULL_IRI_PREFIXES: Array<[string, string]> = [
  ["http://www.w3.org/2002/07/owl#", "owl:"],
  ["http://www.w3.org/2000/01/rdf-schema#", "rdfs:"],
  ["http://www.w3.org/2004/02/skos/core#", "skos:"],
];

export function compactNodeType(type: string): string {
  for (const [iri, prefix] of FULL_IRI_PREFIXES) {
    if (type.startsWith(iri)) {
      return `${prefix}${type.slice(iri.length)}`;
    }
  }
  return type;
}

export function classifyNodeType(rawType: string): EditorEntityType {
  const type = compactNodeType(rawType);
  if (type === "owl:Ontology") return "ontology";
  if (type === "owl:Class" || type === "rdfs:Class") return "class";
  if (type.includes("Property")) return "property";
  return "external";
}

function ownsByNamespace(entityUri: string, ontologyUri: string): boolean {
  const stem = ontologyUri.replace(/[/#]+$/, "");
  return entityUri === ontologyUri
    || entityUri.startsWith(`${stem}#`)
    || entityUri.startsWith(`${stem}/`);
}

export function inferOntologyUri(
  entries: RegistryEntry[],
  entityUri: string,
  explicitOwner?: string,
): string | undefined {
  if (explicitOwner && entries.some((entry) => entry.uri === explicitOwner)) {
    return explicitOwner;
  }
  return [...entries]
    .filter((entry) => ownsByNamespace(entityUri, entry.uri))
    .sort((left, right) => right.uri.length - left.uri.length)[0]?.uri;
}

export function isEditableEntityType(entityType?: EditorEntityType): boolean {
  return entityType === "class" || entityType === "property";
}
