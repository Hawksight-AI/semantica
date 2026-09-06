import type Graph from "graphology";

import type { NodeAttributes } from "../../store/graphStore";
import { GRAPH_THEME, type GraphTheme } from "./graphTheme";

export type GraphColorLegendItem = {
  id: string;
  group: string;
  color: string;
  count: number;
};

/** Normal semantic color, before selection, distance, or zoom styling. */
export function getSemanticNodeColor(
  attrs: Pick<NodeAttributes, "baseColor" | "color">,
  theme: GraphTheme = GRAPH_THEME,
) {
  return String(attrs.baseColor || attrs.color || theme.palette.semantic[0]);
}

/** Use the displayed graph so synthetic groups and filtered views keep their colors. */
export function buildGraphColorLegend(graph: Graph, theme: GraphTheme = GRAPH_THEME): GraphColorLegendItem[] {
  const entries = new Map<string, GraphColorLegendItem>();
  graph.forEachNode((_id, attrs) => {
    if (attrs.hidden) return;
    const group = String(attrs.semanticGroup || attrs.nodeType || "entity");
    const color = getSemanticNodeColor(attrs as NodeAttributes, theme);
    // A synthetic display node can share a semantic label with a different color.
    const id = JSON.stringify([group, color]);
    const current = entries.get(id);
    if (current) current.count += 1;
    else entries.set(id, { id, group, color, count: 1 });
  });
  return [...entries.values()].sort((a, b) => a.group.localeCompare(b.group) || a.color.localeCompare(b.color));
}
