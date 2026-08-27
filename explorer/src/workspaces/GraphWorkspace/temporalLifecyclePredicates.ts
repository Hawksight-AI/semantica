import type { GraphLoadSummary } from "./types";

/**
 * Predicates for gating GraphWorkspace temporal API requests.
 *
 * Temporal bounds and snapshot requests must strictly not execute until the
 * initial graph load has succeeded (summary !== undefined). An empty graph
 * (nodeCount: 0) is still a successful load and must not be rejected.
 */

export function shouldFetchTemporalBounds(
  summary: GraphLoadSummary | undefined,
): boolean {
  return summary !== undefined;
}

export function shouldFetchTemporalSnapshot({
  debouncedTime,
  isLoading,
  summary,
}: {
  debouncedTime: Date | null;
  isLoading: boolean;
  summary: GraphLoadSummary | undefined;
}): boolean {
  return (
    summary !== undefined &&
    debouncedTime !== null &&
    !isLoading
  );
}
