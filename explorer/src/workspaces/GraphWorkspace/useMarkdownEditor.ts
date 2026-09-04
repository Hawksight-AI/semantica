import {
  useCallback,
  useEffect,
  useLayoutEffect,
  useRef,
  useState,
} from "react";
import {
  MarkdownClientError,
  applyMarkdownResource,
  readMarkdownResource,
  type MarkdownApplyResult,
} from "./markdownResourceClient";
import {
  cancelEdit,
  createEditSession,
  createLoadingSession,
  isDirty,
  saveFailed,
  saveStarted,
  saveSucceeded,
  updateDraft,
  type MarkdownEditorError,
  type MarkdownEditSession,
  type MarkdownResourceRef,
} from "./markdownEditorState";

interface MarkdownEditorOptions {
  resource?: MarkdownResourceRef;
  onApplied?: (result: MarkdownApplyResult) => void;
  onDirtyChange?: (dirty: boolean) => void;
}

interface KeyedError {
  resourceKey: string;
  error: MarkdownEditorError;
}

function keyOf(resource?: MarkdownResourceRef): string {
  return resource ? `${resource.kind}:${resource.id}` : "";
}

function normalizeError(failure: unknown): MarkdownEditorError {
  if (failure instanceof MarkdownClientError) return failure;
  return {
    kind: "network",
    message: "The Markdown service could not be reached. Your draft was kept.",
  };
}

export function useMarkdownEditor({
  resource,
  onApplied,
  onDirtyChange,
}: MarkdownEditorOptions) {
  const resourceKey = keyOf(resource);
  const [session, setSession] = useState<MarkdownEditSession | null>(null);
  const [viewError, setViewError] = useState<KeyedError | null>(null);
  const [renderedResourceKey, setRenderedResourceKey] = useState(resourceKey);
  const loadGenerationRef = useRef(0);

  if (renderedResourceKey !== resourceKey) {
    setRenderedResourceKey(resourceKey);
    setSession(null);
    setViewError(null);
  }

  useLayoutEffect(() => {
    loadGenerationRef.current += 1;
  }, [resourceKey]);

  const activeSession = session && keyOf(session.resource) === resourceKey
    ? session
    : null;
  const dirty = isDirty(activeSession);
  const editing = activeSession !== null
    && activeSession.status !== "viewing"
    && activeSession.status !== "loading-document";
  const saving = activeSession?.status === "saving";
  const loading = activeSession?.status === "loading-document";
  const error = activeSession?.error
    ?? (viewError?.resourceKey === resourceKey ? viewError.error : null);

  useEffect(() => {
    onDirtyChange?.(dirty);
    return () => {
      if (dirty) onDirtyChange?.(false);
    };
  }, [dirty, onDirtyChange]);

  useEffect(() => {
    if (!dirty) return;
    const protectDraft = (event: BeforeUnloadEvent) => {
      event.preventDefault();
      event.returnValue = "";
    };
    window.addEventListener("beforeunload", protectDraft);
    return () => window.removeEventListener("beforeunload", protectDraft);
  }, [dirty]);

  const beginEdit = useCallback(async () => {
    if (!resource) return false;
    const loadGeneration = ++loadGenerationRef.current;
    setViewError(null);
    setSession(createLoadingSession(resource));
    try {
      const document = await readMarkdownResource(resource);
      if (loadGeneration !== loadGenerationRef.current) return false;
      setSession(createEditSession(resource, document));
      return true;
    } catch (failure) {
      if (loadGeneration !== loadGenerationRef.current) return false;
      setSession(null);
      setViewError({ resourceKey, error: normalizeError(failure) });
      return false;
    }
  }, [resource, resourceKey]);

  const discard = useCallback(() => {
    if (!activeSession || saving) return;
    setSession(cancelEdit());
    setViewError(null);
  }, [activeSession, saving]);

  const save = useCallback(async () => {
    if (!activeSession || saving || !dirty) return false;
    const resourceGeneration = loadGenerationRef.current;
    const pending = saveStarted(activeSession);
    setSession(pending);
    try {
      const result = await applyMarkdownResource(
        pending.resource,
        pending.draft,
        pending.baseRevision,
      );
      if (resourceGeneration !== loadGenerationRef.current) return false;
      setSession(saveSucceeded(pending, result));
      onApplied?.(result);
      return true;
    } catch (failure) {
      if (resourceGeneration !== loadGenerationRef.current) return false;
      setSession(saveFailed(pending, normalizeError(failure)));
      return false;
    }
  }, [activeSession, dirty, onApplied, saving]);

  const reloadLatest = useCallback(async () => {
    if (!resource || saving) return;
    if (
      dirty
      && !window.confirm("Discard this draft and reload the latest applied version?")
    ) return;
    await beginEdit();
  }, [beginEdit, dirty, resource, saving]);

  const changeDraft = useCallback((draft: string) => {
    setSession((current) => (
      current && keyOf(current.resource) === resourceKey
        ? updateDraft(current, draft)
        : current
    ));
  }, [resourceKey]);

  return {
    session: activeSession,
    error,
    dirty,
    editing,
    saving,
    loading,
    beginEdit,
    discard,
    save,
    reloadLatest,
    changeDraft,
  };
}
