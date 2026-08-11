"""
Distance-Enriched Export (FR-10)

Exports pairwise node distance metrics — hop count, weighted distance,
semantic similarity, distance band, betweenness centrality — in CSV or
JSONL format for downstream ML pipelines (GNN training, clustering,
link prediction).

Python API:
    exporter = DistanceExporter(graph)
    df = exporter.to_dataframe(include=["hops", "semantic_similarity", "distance_band"])
    exporter.to_csv("distances.csv")
    exporter.to_jsonl("distances.jsonl")
"""

import csv
import io
import json
from typing import Any, Dict, List, Optional

from ..utils.helpers import classify_path_distance
from ..utils.logging import get_logger

logger = get_logger(__name__)

_KG_AVAILABLE = False
try:
    from ..kg import PathFinder, SimilarityCalculator, CentralityCalculator
    _KG_AVAILABLE = True
except ImportError as exc:
    logger.debug("KG components not available; distance exporter will run in reduced mode: %s", exc)

_ALL_COLUMNS = [
    "source_id", "source_type", "target_id", "target_type",
    "hop_count", "weighted_distance", "semantic_similarity",
    "distance_band", "source_betweenness", "target_betweenness",
]


class DistanceExporter:
    """Compute and export pairwise distance metrics for a ContextGraph."""

    def __init__(self, graph: Any) -> None:
        self.graph = graph
        self._path_finder = PathFinder() if _KG_AVAILABLE else None
        self._similarity = SimilarityCalculator() if _KG_AVAILABLE else None
        self._centrality = CentralityCalculator() if _KG_AVAILABLE else None

    def _build_graph_dict(self) -> Dict[str, Any]:
        nodes = [
            {"id": n.node_id, "type": n.node_type, "content": n.content, "properties": n.properties}
            for n in self.graph.nodes.values()
        ]
        edges_raw = getattr(self.graph, "edges", [])
        edges = [
            {
                "id": e.edge_id, "source": e.source_id, "target": e.target_id,
                "type": e.edge_type, "weight": e.weight,
            }
            for e in edges_raw
        ]
        return {"nodes": nodes, "edges": edges}

    def _node_type(self, node_id: str) -> str:
        node = getattr(self.graph, "nodes", {}).get(node_id)
        return getattr(node, "node_type", "") if node else ""

    def _betweenness(self, graph_dict: Dict[str, Any]) -> Dict[str, float]:
        if self._centrality is None:
            return {}
        try:
            result = self._centrality.calculate_betweenness_centrality(graph_dict)
            return result.get("betweenness", {}) if isinstance(result, dict) else {}
        except Exception as exc:
            logger.debug(
                "betweenness_centrality computation failed: %s — returning empty dict", exc
            )
            return {}

    def _hop_distance(self, graph_dict: Dict[str, Any], src: str, tgt: str) -> Optional[int]:
        if self._path_finder is None:
            return None
        try:
            result = self._path_finder.bfs_shortest_path(graph_dict, src, tgt)
            path = result.get("path", []) if isinstance(result, dict) else (result or [])
            return len(path) - 1 if path else None
        except Exception as exc:
            logger.debug(
                "hop_distance(%s, %s) failed: %s — returning None"
                " (indistinguishable from 'no path exists')",
                src, tgt, exc,
            )
            return None

    def _weighted_distance(self, graph_dict: Dict[str, Any], src: str, tgt: str) -> Optional[float]:
        if self._path_finder is None:
            return None
        try:
            result = self._path_finder.dijkstra_shortest_path(graph_dict, src, tgt)
            if isinstance(result, dict):
                return float(result.get("total_weight", len(result.get("path", [])) - 1))
            return None
        except Exception as exc:
            logger.debug(
                "weighted_distance(%s, %s) failed: %s — returning None"
                " (indistinguishable from 'no path exists')",
                src, tgt, exc,
            )
            return None

    def _semantic_similarity(self, graph_dict: Dict[str, Any], src: str, tgt: str) -> Optional[float]:
        if self._similarity is None:
            return None
        try:
            sim = self._similarity.cosine_similarity(graph_dict, src, tgt)
            return float(sim) if isinstance(sim, (int, float)) else None
        except Exception as exc:
            logger.debug(
                "semantic_similarity(%s, %s) failed: %s — returning None",
                src, tgt, exc,
            )
            return None

    def compute_pairs(
        self,
        include: Optional[List[str]] = None,
        node_subset: Optional[List[str]] = None,
    ) -> List[Dict[str, Any]]:
        """Compute all pairwise distance metrics and return as a list of dicts."""
        include_set = set(include or _ALL_COLUMNS)
        graph_dict = self._build_graph_dict()

        node_ids = node_subset or list(self.graph.nodes.keys())

        betweenness: Dict[str, float] = {}
        if "source_betweenness" in include_set or "target_betweenness" in include_set:
            betweenness = self._betweenness(graph_dict)

        rows = []
        for i, src in enumerate(node_ids):
            for tgt in node_ids:
                if src == tgt:
                    continue
                row: Dict[str, Any] = {}
                if "source_id" in include_set:
                    row["source_id"] = src
                if "source_type" in include_set:
                    row["source_type"] = self._node_type(src)
                if "target_id" in include_set:
                    row["target_id"] = tgt
                if "target_type" in include_set:
                    row["target_type"] = self._node_type(tgt)

                hop_count: Optional[int] = None
                if "hop_count" in include_set or "distance_band" in include_set:
                    hop_count = self._hop_distance(graph_dict, src, tgt)
                    if "hop_count" in include_set:
                        row["hop_count"] = hop_count

                if "weighted_distance" in include_set:
                    row["weighted_distance"] = self._weighted_distance(graph_dict, src, tgt)

                if "semantic_similarity" in include_set:
                    row["semantic_similarity"] = self._semantic_similarity(graph_dict, src, tgt)

                if "distance_band" in include_set:
                    row["distance_band"] = classify_path_distance(hop_count) if hop_count is not None else "distant"

                if "source_betweenness" in include_set:
                    row["source_betweenness"] = betweenness.get(src)
                if "target_betweenness" in include_set:
                    row["target_betweenness"] = betweenness.get(tgt)

                rows.append(row)
        return rows

    def to_dataframe(
        self,
        include: Optional[List[str]] = None,
        node_subset: Optional[List[str]] = None,
    ) -> Any:
        """Return a pandas DataFrame of pairwise distances."""
        try:
            import pandas as pd
        except ImportError as exc:
            raise ImportError("pandas is required for to_dataframe()") from exc
        rows = self.compute_pairs(include=include, node_subset=node_subset)
        return pd.DataFrame(rows)

    def to_csv(
        self,
        path: str,
        include: Optional[List[str]] = None,
        node_subset: Optional[List[str]] = None,
    ) -> None:
        """Write pairwise distances to a CSV file."""
        rows = self.compute_pairs(include=include, node_subset=node_subset)
        if not rows:
            with open(path, "w", newline="", encoding="utf-8") as fh:
                fh.write("")
            return
        fieldnames = list(rows[0].keys())
        with open(path, "w", newline="", encoding="utf-8") as fh:
            writer = csv.DictWriter(fh, fieldnames=fieldnames)
            writer.writeheader()
            writer.writerows(rows)

    def to_jsonl(
        self,
        path: str,
        include: Optional[List[str]] = None,
        node_subset: Optional[List[str]] = None,
    ) -> None:
        """Write pairwise distances to a JSONL file (one JSON object per line)."""
        rows = self.compute_pairs(include=include, node_subset=node_subset)
        with open(path, "w", encoding="utf-8") as fh:
            for row in rows:
                fh.write(json.dumps(row, default=str) + "\n")

    def to_csv_string(
        self,
        include: Optional[List[str]] = None,
        node_subset: Optional[List[str]] = None,
    ) -> str:
        """Return CSV as a string (for API responses)."""
        rows = self.compute_pairs(include=include, node_subset=node_subset)
        if not rows:
            return ""
        buf = io.StringIO()
        fieldnames = list(rows[0].keys())
        writer = csv.DictWriter(buf, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)
        return buf.getvalue()

    def to_jsonl_string(
        self,
        include: Optional[List[str]] = None,
        node_subset: Optional[List[str]] = None,
    ) -> str:
        """Return JSONL as a string (for API responses)."""
        rows = self.compute_pairs(include=include, node_subset=node_subset)
        return "\n".join(json.dumps(row, default=str) for row in rows)
