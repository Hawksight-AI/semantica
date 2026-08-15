import test from "node:test";
import assert from "node:assert/strict";

import {
  shouldFetchTemporalBounds,
  shouldFetchTemporalSnapshot,
} from "../src/workspaces/GraphWorkspace/temporalLifecyclePredicates.ts";
import type { GraphLoadSummary } from "../src/workspaces/GraphWorkspace/types.ts";

const sampleSummary: GraphLoadSummary = {
  nodeCount: 42,
  edgeCount: 78,
  loadTimeMs: 120,
  hasCoordinates: true,
  layoutSource: "provided",
  layoutReady: true,
};

const emptyGraphSummary: GraphLoadSummary = {
  nodeCount: 0,
  edgeCount: 0,
  loadTimeMs: 15,
  hasCoordinates: false,
  layoutSource: "runtime",
  layoutReady: false,
};

// ── shouldFetchTemporalBounds ────────────────────────────────────────────────

test("temporal bounds: false when summary is undefined (initial mount or failed load)", () => {
  assert.equal(
    shouldFetchTemporalBounds(undefined),
    false,
    "bounds request must not run before graph load succeeds",
  );
});

test("temporal bounds: true when non-empty summary is present", () => {
  assert.equal(
    shouldFetchTemporalBounds(sampleSummary),
    true,
    "bounds request should run when successful graph summary exists",
  );
});

test("temporal bounds: true when successful summary has nodeCount of 0", () => {
  assert.equal(
    shouldFetchTemporalBounds(emptyGraphSummary),
    true,
    "an empty graph is still a successful load and must allow bounds fetching",
  );
});

// ── shouldFetchTemporalSnapshot ──────────────────────────────────────────────

test("temporal snapshot: false when summary is undefined even if scrubber time is set and isLoading is false", () => {
  assert.equal(
    shouldFetchTemporalSnapshot({
      debouncedTime: new Date("2024-01-01T00:00:00Z"),
      isLoading: false,
      summary: undefined,
    }),
    false,
    "snapshot request must not run when graph load failed",
  );
});

test("temporal snapshot: false when graph is currently loading", () => {
  assert.equal(
    shouldFetchTemporalSnapshot({
      debouncedTime: new Date("2024-01-01T00:00:00Z"),
      isLoading: true,
      summary: sampleSummary,
    }),
    false,
    "snapshot request must not run while graph is loading",
  );
});

test("temporal snapshot: false when debouncedTime is null", () => {
  assert.equal(
    shouldFetchTemporalSnapshot({
      debouncedTime: null,
      isLoading: false,
      summary: sampleSummary,
    }),
    false,
    "snapshot request must not run without a scrubber timestamp",
  );
});

test("temporal snapshot: true when summary exists, isLoading is false, and time is set", () => {
  assert.equal(
    shouldFetchTemporalSnapshot({
      debouncedTime: new Date("2024-01-01T00:00:00Z"),
      isLoading: false,
      summary: sampleSummary,
    }),
    true,
    "snapshot request should run after graph load succeeds and time is set",
  );
});

test("temporal snapshot: true when successful summary has 0 nodes, isLoading is false, and time is set", () => {
  assert.equal(
    shouldFetchTemporalSnapshot({
      debouncedTime: new Date("2024-01-01T00:00:00Z"),
      isLoading: false,
      summary: emptyGraphSummary,
    }),
    true,
    "empty successful graph must allow snapshot requests once ready",
  );
});
