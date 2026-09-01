export type MarkdownResourceRef =
  | { kind: "context-node"; id: string }
  | { kind: "agent-memory"; id: string };

export type EditorStatus =
  | "viewing"
  | "loading-document"
  | "editing"
  | "saving"
  | "validation-error"
  | "save-error"
  | "conflict";

export interface MarkdownEditorError {
  kind: "validation" | "conflict" | "save" | "network";
  message: string;
  field?: string;
  currentRevision?: string;
}

export interface MarkdownEditSession {
  resource: MarkdownResourceRef;
  baseSource: string;
  baseRevision: string;
  draft: string;
  status: EditorStatus;
  error: MarkdownEditorError | null;
}

export interface MarkdownSavedDocument {
  source: string;
  revision: string;
}

export function createLoadingSession(resource: MarkdownResourceRef): MarkdownEditSession {
  return {
    resource,
    baseSource: "",
    baseRevision: "",
    draft: "",
    status: "loading-document",
    error: null,
  };
}

export function createEditSession(
  resource: MarkdownResourceRef,
  document: MarkdownSavedDocument,
): MarkdownEditSession {
  return {
    resource,
    baseSource: document.source,
    baseRevision: document.revision,
    draft: document.source,
    status: "editing",
    error: null,
  };
}

export function updateDraft(
  session: MarkdownEditSession,
  draft: string,
): MarkdownEditSession {
  return {
    ...session,
    draft,
    status: "editing",
    error: null,
  };
}

export function isDirty(session: MarkdownEditSession | null): boolean {
  return session !== null && session.draft !== session.baseSource;
}

export function saveStarted(session: MarkdownEditSession): MarkdownEditSession {
  if (!isDirty(session)) return session;
  return { ...session, status: "saving", error: null };
}

export function saveSucceeded(
  session: MarkdownEditSession,
  document: MarkdownSavedDocument,
): MarkdownEditSession {
  return {
    ...session,
    baseSource: document.source,
    baseRevision: document.revision,
    draft: document.source,
    status: "viewing",
    error: null,
  };
}

export function saveFailed(
  session: MarkdownEditSession,
  error: MarkdownEditorError,
): MarkdownEditSession {
  const status: EditorStatus =
    error.kind === "validation"
      ? "validation-error"
      : error.kind === "conflict"
        ? "conflict"
        : "save-error";
  return { ...session, status, error };
}

export function cancelEdit(): null {
  return null;
}

export function shouldConfirmDiscard(session: MarkdownEditSession | null): boolean {
  return isDirty(session) && session?.status !== "saving";
}
