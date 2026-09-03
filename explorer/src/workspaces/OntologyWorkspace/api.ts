import type {
  AlignmentRelation,
  AlignmentSuggestion,
  OntologyAlignment,
  OntologyEntry,
  OntologyHealthResponse,
  ShaclGenerateResponse,
  ShaclShapesResponse,
  ShaclValidationResponse,
} from "./types";

export type OntologyGraphNode = {
  id: string;
  type: string;
  content?: string;
  properties?: Record<string, unknown>;
};

export type OntologyGraphEdge = {
  id?: string;
  source: string;
  target: string;
  type: string;
  weight?: number;
  properties?: Record<string, unknown>;
};

export type OntologyGraphResponse = {
  uri: string;
  nodes: OntologyGraphNode[];
  edges: OntologyGraphEdge[];
};

export type OntologyEntityOwner = {
  owning_ontology?: string;
  source_ontology?: string;
};

async function parseResponse<T>(response: Response): Promise<T> {
  if (!response.ok) {
    let detail = `Request failed with status ${response.status}`;
    try {
      const body = await response.json();
      detail = body.detail || detail;
    } catch {
      // Keep the generic HTTP detail.
    }
    throw new Error(detail);
  }
  const data = await response.json();
  if (response.status === 207) {
    console.warn("Partial Success:", data.message || "Warning: 207 Multi-Status");
  }
  return data as T;
}

export async function loadOntologyRegistry(): Promise<OntologyEntry[]> {
  return parseResponse<OntologyEntry[]>(await fetch("/api/ontology/registry"));
}

export async function loadOntologyGraph(uri: string, signal?: AbortSignal): Promise<OntologyGraphResponse> {
  return parseResponse<OntologyGraphResponse>(
    await fetch(`/api/ontology/graph?uri=${encodeURIComponent(uri)}`, { signal }),
  );
}

export async function loadOntologyEntityOwner(uri: string): Promise<string | undefined> {
  const response = await fetch(`/api/ontology/entity/${encodeURIComponent(uri)}`);
  if (!response.ok) return undefined;
  const owner = await response.json() as OntologyEntityOwner;
  // owning_ontology is the backend's resolved verdict; source_ontology is the
  // raw scheme_uri property, which only covers explicitly annotated entities.
  return owner.owning_ontology ?? owner.source_ontology;
}

export async function loadAlignments(uri?: string): Promise<OntologyAlignment[]> {
  const query = uri ? `?uri=${encodeURIComponent(uri)}` : "";
  return parseResponse<OntologyAlignment[]>(await fetch(`/api/ontology/alignments${query}`));
}

export async function saveAlignment(payload: {
  source_uri: string;
  target_uri: string;
  relation: AlignmentRelation;
  confidence: number;
  provenance?: string;
  source?: string;
  reviewer?: string;
}): Promise<OntologyAlignment> {
  return parseResponse<OntologyAlignment>(
    await fetch("/api/ontology/alignments", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload),
    }),
  );
}

export async function removeAlignment(id: string): Promise<void> {
  await parseResponse<{ status: string }>(
    await fetch(`/api/ontology/alignments?id=${encodeURIComponent(id)}`, { method: "DELETE" }),
  );
}

export async function suggestAlignments(payload: {
  source_ontology_uri?: string;
  target_ontology_uri?: string;
  threshold: number;
  limit: number;
}): Promise<AlignmentSuggestion[]> {
  return parseResponse<AlignmentSuggestion[]>(
    await fetch("/api/ontology/suggest-alignments", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload),
    }),
  );
}

export async function loadOntologyHealth(uri: string): Promise<OntologyHealthResponse> {
  return parseResponse<OntologyHealthResponse>(
    await fetch(`/api/ontology/health?uri=${encodeURIComponent(uri)}`),
  );
}

export async function generateShacl(uri: string, qualityTier: "standard" | "strict" = "strict"): Promise<ShaclGenerateResponse> {
  return parseResponse<ShaclGenerateResponse>(
    await fetch("/api/ontology/shacl/generate", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ uri, quality_tier: qualityTier }),
    }),
  );
}

export async function loadShaclShapes(uri: string): Promise<ShaclShapesResponse> {
  return parseResponse<ShaclShapesResponse>(
    await fetch(`/api/ontology/shacl/shapes?uri=${encodeURIComponent(uri)}`),
  );
}

export async function validateShacl(uri: string, shaclTurtle: string): Promise<ShaclValidationResponse> {
  return parseResponse<ShaclValidationResponse>(
    await fetch("/api/ontology/shacl/validate", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ uri, shacl_turtle: shaclTurtle }),
    }),
  );
}
