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
