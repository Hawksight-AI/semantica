import assert from "node:assert/strict";
import test from "node:test";

import {
  cancelEdit,
  createEditSession,
  createLoadingSession,
  isDirty,
  saveFailed,
  saveStarted,
  saveSucceeded,
  shouldConfirmDiscard,
  updateDraft,
} from "../src/workspaces/GraphWorkspace/markdownEditorState.ts";

const resource = { kind: "context-node" as const, id: "node-1" };


test("enters loading and editing with the canonical source", () => {
  const loading = createLoadingSession(resource);
  const editing = createEditSession(resource, {
    source: "---\nid: node-1\n---\n\nBody",
    revision: "sha256:one",
  });

  assert.equal(loading.status, "loading-document");
  assert.equal(editing.status, "editing");
  assert.equal(editing.draft, editing.baseSource);
  assert.equal(isDirty(editing), false);
});


test("draft changes derive dirty state and clear prior errors", () => {
  const session = createEditSession(resource, {
    source: "base",
    revision: "sha256:one",
  });
  const failed = saveFailed(session, {
    kind: "validation",
    message: "Invalid",
  });
  const edited = updateDraft(failed, "draft");

  assert.equal(edited.status, "editing");
  assert.equal(edited.error, null);
  assert.equal(isDirty(edited), true);
  assert.equal(shouldConfirmDiscard(edited), true);
});


test("cancel discards the edit session without saving", () => {
  const session = updateDraft(
    createEditSession(resource, { source: "base", revision: "sha256:one" }),
    "draft",
  );

  assert.equal(isDirty(session), true);
  assert.equal(cancelEdit(), null);
});


test("no-op save never enters saving state", () => {
  const session = createEditSession(resource, {
    source: "base",
    revision: "sha256:one",
  });

  assert.equal(saveStarted(session), session);
  assert.equal(isDirty(session), false);
});


test("save success replaces the base source and revision", () => {
  const session = saveStarted(
    updateDraft(
      createEditSession(resource, { source: "base", revision: "sha256:one" }),
      "draft",
    ),
  );
  const saved = saveSucceeded(session, {
    source: "canonical saved",
    revision: "sha256:two",
  });

  assert.equal(saved.status, "viewing");
  assert.equal(saved.baseSource, "canonical saved");
  assert.equal(saved.draft, "canonical saved");
  assert.equal(saved.baseRevision, "sha256:two");
  assert.equal(isDirty(saved), false);
});


test("validation, conflict, and save failures retain the draft for retry", () => {
  const draft = updateDraft(
    createEditSession(resource, { source: "base", revision: "sha256:one" }),
    "draft",
  );

  const validation = saveFailed(draft, {
    kind: "validation",
    message: "Invalid",
  });
  const conflict = saveFailed(draft, {
    kind: "conflict",
    message: "Stale",
    currentRevision: "sha256:two",
  });
  const network = saveFailed(draft, {
    kind: "network",
    message: "Offline",
  });

  assert.equal(validation.status, "validation-error");
  assert.equal(conflict.status, "conflict");
  assert.equal(network.status, "save-error");
  assert.equal(validation.draft, "draft");
  assert.equal(conflict.draft, "draft");
  assert.equal(network.draft, "draft");
  assert.equal(saveStarted(network).status, "saving");
});


test("saving sessions do not allow a competing discard confirmation", () => {
  const saving = saveStarted(
    updateDraft(
      createEditSession(resource, { source: "base", revision: "sha256:one" }),
      "draft",
    ),
  );

  assert.equal(shouldConfirmDiscard(saving), false);
});
