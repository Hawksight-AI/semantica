import type {
  MarkdownEditorError,
  MarkdownResourceRef,
} from "./markdownEditorState";

export interface MarkdownDocument {
  resource: MarkdownResourceRef;
  source: string;
  body: string;
  revision: string;
  editable: boolean;
}

export interface MarkdownApplyResult extends MarkdownDocument {
  changed: boolean;
}

type ErrorDetail = {
  code?: string;
  message?: string;
  field?: string;
  current_revision?: string;
};

export class MarkdownClientError extends Error implements MarkdownEditorError {
  readonly kind: MarkdownEditorError["kind"];
  readonly field?: string;
  readonly currentRevision?: string;

  constructor(error: MarkdownEditorError) {
    super(error.message);
    this.name = "MarkdownClientError";
    this.kind = error.kind;
    this.field = error.field;
    this.currentRevision = error.currentRevision;
  }
}

function resourceUrl(ref: MarkdownResourceRef): string {
  return `/api/markdown/${ref.kind}/${encodeURIComponent(ref.id)}`;
}

async function responseError(response: Response): Promise<MarkdownClientError> {
  let detail: ErrorDetail = {};
  try {
    const payload = (await response.json()) as { detail?: ErrorDetail };
    if (payload.detail && typeof payload.detail === "object") {
      detail = payload.detail;
    }
  } catch {
    // A non-JSON response is mapped from its status below.
  }

  const kind: MarkdownEditorError["kind"] =
    response.status === 422
      ? "validation"
      : response.status === 409
        ? "conflict"
        : "save";
  return new MarkdownClientError({
    kind,
    message: detail.message || `Markdown request failed (${response.status}).`,
    field: detail.field,
    currentRevision: detail.current_revision,
  });
}

async function request<T>(input: RequestInfo | URL, init?: RequestInit): Promise<T> {
  try {
    const response = await fetch(input, init);
    if (!response.ok) {
      throw await responseError(response);
    }
    return (await response.json()) as T;
  } catch (error) {
    if (error instanceof MarkdownClientError) throw error;
    throw new MarkdownClientError({
      kind: "network",
      message: "The Markdown service could not be reached. Your draft was kept.",
    });
  }
}

export function readMarkdownResource(
  ref: MarkdownResourceRef,
): Promise<MarkdownDocument> {
  return request<MarkdownDocument>(resourceUrl(ref));
}

export function applyMarkdownResource(
  ref: MarkdownResourceRef,
  markdown: string,
  expectedRevision: string,
): Promise<MarkdownApplyResult> {
  return request<MarkdownApplyResult>(resourceUrl(ref), {
    method: "PUT",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      markdown,
      expected_revision: expectedRevision,
    }),
  });
}
