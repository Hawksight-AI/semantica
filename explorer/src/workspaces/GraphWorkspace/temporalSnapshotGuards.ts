/**
 * Guards for the temporal snapshot fetch/apply lifecycle.
 *
 * The snapshot effect previously fetched /api/temporal/snapshot with no
 * idempotency or ordering protection. Upstream churn (timeline recreation
 * while bounds settle, play ticks resetting the playhead, drag events) could
 * re-request the same `at` repeatedly, and responses could arrive after the
 * scrubber had moved on.
 *
 * The guards enforce:
 * - at most one in-flight request per scrubber position (identical `at`
 *   values are deduplicated while a request is pending, breaking the
 *   idle/play polling loop);
 * - successful snapshots are cached per position and re-applied when the
 *   scrubber returns (play wrap-around, back-scrubbing) without a refetch;
 * - a response is applied only while the scrubber is still on its position,
 *   so out-of-order responses cannot clobber a newer position's count;
 * - failed, cancelled, or superseded requests release their position so it
 *   can be fetched again on the next visit;
 * - `reset()` drops all state when the underlying graph data is replaced
 *   (reload/retry), because cached snapshots describe the previous graph.
 *
 * `createTemporalSnapshotGuards()` is stateful by design.
 */

export interface TemporalSnapshotResponse {
  active_node_ids: string[];
  active_node_count: number;
}

export interface TemporalSnapshotRequest {
  /** null when the request was deduplicated because one is already in flight. */
  seq: number | null;
  /** The snapshot previously applied for this position, when revisiting it. */
  cached: TemporalSnapshotResponse | null;
}

export interface TemporalSnapshotGuards {
  /** Begin (or dedupe) a request for `atMs`; marks it as the current position. */
  begin(atMs: number): TemporalSnapshotRequest;
  /** True when the response for `atMs`/`seq` may be applied (scrubber still on `atMs`). */
  shouldApply(atMs: number, seq: number): boolean;
  /** Record a successful application and cache its snapshot for revisits. */
  apply(atMs: number, seq: number, data: TemporalSnapshotResponse): void;
  /** Release a position whose request failed, was cancelled, or was superseded. */
  finish(atMs: number, seq: number): void;
  /** Drop all state; call when the underlying graph data is replaced (reload). */
  reset(): void;
}

interface SnapshotEntry {
  seq: number;
  /** null while the request is in flight (or before the first success). */
  data: TemporalSnapshotResponse | null;
}

/** Upper bound on cached positions so long scrubbing sessions stay bounded. */
const MAX_CACHED_POSITIONS = 256;

export function createTemporalSnapshotGuards(): TemporalSnapshotGuards {
  const entries = new Map<number, SnapshotEntry>();
  let latestRequestSeq = 0;
  let currentAtMs: number | null = null;

  const evictOldest = () => {
    while (entries.size > MAX_CACHED_POSITIONS) {
      const oldestAtMs = entries.keys().next().value;
      if (oldestAtMs === undefined) return;
      entries.delete(oldestAtMs);
    }
  };

  return {
    begin(atMs) {
      const existing = entries.get(atMs);
      if (existing && existing.data === null) {
        // Identical request already in flight: dedupe, but the scrubber is here now.
        currentAtMs = atMs;
        return { seq: null, cached: null };
      }
      latestRequestSeq += 1;
      const seq = latestRequestSeq;
      entries.set(atMs, { seq, data: existing?.data ?? null });
      currentAtMs = atMs;
      evictOldest();
      return { seq, cached: existing?.data ?? null };
    },

    shouldApply(atMs, seq) {
      return atMs === currentAtMs && entries.get(atMs)?.seq === seq;
    },

    apply(atMs, seq, data) {
      const entry = entries.get(atMs);
      if (entry && entry.seq === seq) {
        entry.data = data;
      }
    },

    finish(atMs, seq) {
      const entry = entries.get(atMs);
      if (entry && entry.seq === seq && entry.data === null) {
        entries.delete(atMs);
      }
    },

    reset() {
      entries.clear();
      latestRequestSeq = 0;
      currentAtMs = null;
    },
  };
}
