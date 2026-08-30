import test from "node:test";
import assert from "node:assert/strict";

import { createTemporalSnapshotGuards } from "../src/workspaces/GraphWorkspace/temporalSnapshotGuards.ts";

const POSITION_1 = new Date("2023-07-02T00:00:00Z").getTime();
const POSITION_2 = new Date("2024-01-02T00:00:00Z").getTime();
const POSITION_3 = new Date("2024-07-02T00:00:00Z").getTime();

const SNAPSHOT = { active_node_ids: ["n1", "n2"], active_node_count: 2 };

// ── begin: one request per scrubber position ─────────────────────────────────

test("begin: a new position returns a fresh request sequence", () => {
  const guards = createTemporalSnapshotGuards();
  assert.deepEqual(guards.begin(POSITION_1), { seq: 1, cached: null });
});

test("begin: an identical in-flight request is deduplicated (no duplicate fetch)", () => {
  const guards = createTemporalSnapshotGuards();
  guards.begin(POSITION_1);
  assert.deepEqual(guards.begin(POSITION_1), { seq: null, cached: null });
});

test("begin: distinct positions request independently", () => {
  const guards = createTemporalSnapshotGuards();
  assert.equal(guards.begin(POSITION_1).seq, 1);
  assert.equal(guards.begin(POSITION_2).seq, 2);
});

test("begin: revisiting an applied position returns its cached snapshot", () => {
  const guards = createTemporalSnapshotGuards();
  const { seq } = guards.begin(POSITION_1);
  guards.apply(POSITION_1, seq, SNAPSHOT);
  const revisit = guards.begin(POSITION_1);
  assert.equal(revisit.seq, 2);
  assert.deepEqual(revisit.cached, SNAPSHOT);
});

test("begin: a failed position (finished) can be requested again", () => {
  const guards = createTemporalSnapshotGuards();
  const { seq } = guards.begin(POSITION_1);
  guards.finish(POSITION_1, seq);
  const retry = guards.begin(POSITION_1);
  assert.equal(retry.seq, 2);
  assert.equal(retry.cached, null);
});

test("finish: does not clear a position whose snapshot was already applied", () => {
  const guards = createTemporalSnapshotGuards();
  const { seq } = guards.begin(POSITION_1);
  guards.apply(POSITION_1, seq, SNAPSHOT);
  guards.finish(POSITION_1, seq);
  assert.deepEqual(guards.begin(POSITION_1).cached, SNAPSHOT);
});

test("finish: a stale sequence cannot release a newer request's position", () => {
  const guards = createTemporalSnapshotGuards();
  const first = guards.begin(POSITION_1);
  guards.finish(POSITION_1, first.seq);
  guards.begin(POSITION_1); // seq 2, in flight again
  guards.finish(POSITION_1, first.seq); // stale seq: must not release seq 2
  assert.deepEqual(guards.begin(POSITION_1), { seq: null, cached: null });
});

// ── shouldApply: applied only while the scrubber is on that position ─────────

test("shouldApply: the current position's response is applied", () => {
  const guards = createTemporalSnapshotGuards();
  const { seq } = guards.begin(POSITION_1);
  assert.equal(guards.shouldApply(POSITION_1, seq), true);
});

test("shouldApply: a response for a position the scrubber left is discarded", () => {
  const guards = createTemporalSnapshotGuards();
  const { seq: seq1 } = guards.begin(POSITION_1);
  guards.begin(POSITION_2);
  assert.equal(guards.shouldApply(POSITION_1, seq1), false);
  assert.equal(guards.shouldApply(POSITION_2, 2), true);
});

test("shouldApply: a late response for the position the scrubber returned to is applied", () => {
  const guards = createTemporalSnapshotGuards();
  const { seq: seq1 } = guards.begin(POSITION_1);
  const { seq: seq2 } = guards.begin(POSITION_2);
  guards.begin(POSITION_1); // back to 1: deduplicated, no new request
  assert.equal(guards.shouldApply(POSITION_1, seq1), true);
  assert.equal(guards.shouldApply(POSITION_2, seq2), false);
});

test("shouldApply: an unknown sequence is discarded", () => {
  const guards = createTemporalSnapshotGuards();
  guards.begin(POSITION_1);
  assert.equal(guards.shouldApply(POSITION_1, 99), false);
});

test("shouldApply: after a reset no pre-reset response applies", () => {
  const guards = createTemporalSnapshotGuards();
  const { seq } = guards.begin(POSITION_1);
  guards.reset();
  assert.equal(guards.shouldApply(POSITION_1, seq), false);
});

// ── apply: caching for revisits ─────────────────────────────────────────────

test("apply: stores the snapshot so a revisit re-applies it without a request", () => {
  const guards = createTemporalSnapshotGuards();
  const { seq } = guards.begin(POSITION_1);
  guards.apply(POSITION_1, seq, SNAPSHOT);
  guards.begin(POSITION_2);
  assert.deepEqual(guards.begin(POSITION_1).cached, SNAPSHOT);
});

test("apply: play wrap-around re-applies the wrapped-to position's snapshot", () => {
  const guards = createTemporalSnapshotGuards();
  const { seq } = guards.begin(POSITION_1);
  guards.apply(POSITION_1, seq, SNAPSHOT);
  guards.begin(POSITION_2);
  guards.begin(POSITION_3);
  const wrap = guards.begin(POSITION_1);
  assert.deepEqual(wrap.cached, SNAPSHOT);
  assert.equal(guards.shouldApply(POSITION_1, wrap.seq), true);
});

// ── reset: graph reload ─────────────────────────────────────────────────────

test("reset: clears requested and cached state so positions refetch", () => {
  const guards = createTemporalSnapshotGuards();
  const { seq } = guards.begin(POSITION_1);
  guards.apply(POSITION_1, seq, SNAPSHOT);
  guards.reset();
  const fresh = guards.begin(POSITION_1);
  assert.equal(fresh.seq, 1);
  assert.equal(fresh.cached, null);
});

// ── cache bound ─────────────────────────────────────────────────────────────

test("cache: oldest positions are evicted when the cache is full", () => {
  const guards = createTemporalSnapshotGuards();
  const count = 300;
  for (let i = 0; i < count; i++) {
    const { seq } = guards.begin(POSITION_1 + i * 1000);
    guards.apply(POSITION_1 + i * 1000, seq, SNAPSHOT);
  }
  const oldest = guards.begin(POSITION_1);
  assert.equal(oldest.cached, null); // evicted: must refetch on revisit
  const newest = guards.begin(POSITION_1 + (count - 1) * 1000);
  assert.deepEqual(newest.cached, SNAPSHOT); // still cached
});
