export const SMALL_GRAPH_MAX_NODES = 48;
const PROVIDED_COORDINATE_COVERAGE = 0.92;
const MAX_COMPONENT_RADIUS = 78;
const COMPONENT_GAP = 48;

type LayoutEdge = {
  source: string;
  target: string;
};

export function shouldUseSmallGraphLayout(nodeCount: number, coordinateCoverage: number): boolean {
  return nodeCount > 0
    && nodeCount <= SMALL_GRAPH_MAX_NODES
    && coordinateCoverage < PROVIDED_COORDINATE_COVERAGE;
}

export function resolveGraphLayoutDecision(nodeCount: number, coordinateCoverage: number): {
  useProvidedCoordinates: boolean;
  useSmallGraphLayout: boolean;
  layoutReady: boolean;
} {
  const useProvidedCoordinates = coordinateCoverage >= PROVIDED_COORDINATE_COVERAGE;
  const useSmallGraphLayout = shouldUseSmallGraphLayout(nodeCount, coordinateCoverage);
  return {
    useProvidedCoordinates,
    useSmallGraphLayout,
    layoutReady: useProvidedCoordinates || useSmallGraphLayout,
  };
}

export function resolveNodeLayoutPosition(
  decision: ReturnType<typeof resolveGraphLayoutDecision>,
  provided: { x: number | null; y: number | null },
  seeded: { x: number; y: number } | undefined,
): { x: number; y: number } {
  if (decision.useProvidedCoordinates) {
    return { x: provided.x ?? 0, y: provided.y ?? 0 };
  }
  if (decision.useSmallGraphLayout) {
    return { x: seeded?.x ?? 0, y: seeded?.y ?? 0 };
  }
  return {
    x: provided.x ?? seeded?.x ?? 0,
    y: provided.y ?? seeded?.y ?? 0,
  };
}

/**
 * Produce a compact deterministic layout for small graphs.
 *
 * ForceAtlas2 is useful for large connected datasets, but it makes tiny graphs
 * with several disconnected components look like scattered dots. This layout
 * keeps each connected component together and packs components into a centered
 * grid so instance relationships remain legible on first render.
 */
export function buildSmallGraphSeedPositions(
  nodeIds: string[],
  edges: LayoutEdge[],
): Map<string, { x: number; y: number }> {
  const ids = [...new Set(nodeIds)].sort((left, right) => left.localeCompare(right));
  const adjacency = new Map(ids.map((id) => [id, new Set<string>()]));

  edges.forEach(({ source, target }) => {
    if (!adjacency.has(source) || !adjacency.has(target) || source === target) {
      return;
    }
    adjacency.get(source)?.add(target);
    adjacency.get(target)?.add(source);
  });

  const visited = new Set<string>();
  const components: string[][] = [];
  ids.forEach((start) => {
    if (visited.has(start)) {
      return;
    }
    const component: string[] = [];
    const queue = [start];
    visited.add(start);
    while (queue.length > 0) {
      const current = queue.shift();
      if (!current) {
        continue;
      }
      component.push(current);
      [...(adjacency.get(current) ?? [])]
        .sort((left, right) => left.localeCompare(right))
        .forEach((neighbor) => {
          if (!visited.has(neighbor)) {
            visited.add(neighbor);
            queue.push(neighbor);
          }
        });
    }
    component.sort((left, right) => {
      const degreeDelta = (adjacency.get(right)?.size ?? 0) - (adjacency.get(left)?.size ?? 0);
      return degreeDelta || left.localeCompare(right);
    });
    components.push(component);
  });

  components.sort((left, right) => right.length - left.length || left[0].localeCompare(right[0]));

  const columns = Math.max(1, Math.ceil(Math.sqrt(components.length)));
  const rows = Math.max(1, Math.ceil(components.length / columns));
  // Adjacent cells must leave room for two maximum-radius components plus a
  // readable gap. A smaller row height allows valid 12-node components to
  // overlap vertically.
  const cellWidth = MAX_COMPONENT_RADIUS * 2 + COMPONENT_GAP;
  const cellHeight = MAX_COMPONENT_RADIUS * 2 + COMPONENT_GAP;
  const positions = new Map<string, { x: number; y: number }>();

  components.forEach((component, componentIndex) => {
    const column = componentIndex % columns;
    const row = Math.floor(componentIndex / columns);
    const centerX = (column - (columns - 1) / 2) * cellWidth;
    const centerY = (row - (rows - 1) / 2) * cellHeight;

    if (component.length === 1) {
      positions.set(component[0], { x: centerX, y: centerY });
      return;
    }

    const radius = Math.min(MAX_COMPONENT_RADIUS, 30 + component.length * 9);
    component.forEach((nodeId, nodeIndex) => {
      const angle = -Math.PI / 2 + (nodeIndex * Math.PI * 2) / component.length;
      positions.set(nodeId, {
        x: centerX + Math.cos(angle) * radius,
        y: centerY + Math.sin(angle) * radius,
      });
    });
  });

  return positions;
}
