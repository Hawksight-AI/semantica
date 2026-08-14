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

    # Include error status columns for auditable exports:
    df = exporter.to_dataframe(include=["hop_count", "metric_errors"])
"""

import csv
import io
import json
from typing import Any, Dict, List, Optional, Tuple

from ..utils.helpers import classify_path_distance
from ..utils.logging import get_logger

logger = get_logger("export.distance_exporter")

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

# Error status columns — opt-in via include=["metric_errors"]
# (used by compute_pairs when "metric_errors" is in include set)


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

    def _betweenness(self, graph_dict: Dict[str, Any]) -> Tuple[Dict[str, float], Optional[str]]:
        """Return (betweenness_dict, error). error is None on success."""
        if self._centrality is None:
            return {}, None
        try:
            result = self._centrality.calculate_betweenness_centrality(graph_dict)
            return (result.get("betweenness", {}) if isinstance(result, dict) else {}), None
        except Exception:
            logger.warning("Betweenness centrality computation failed; omitting from export", exc_info=True)
            return {}, "betweenness"

    def _hop_distance(self, graph_dict: Dict[str, Any], src: str, tgt: str) -> Tuple[Optional[int], Optional[str]]:
        """Return (hop_count, error). error is None on success or a short description on failure."""
        if self._path_finder is None:
            return None, None  # KG unavailable — not an error, just no data
        try:
            result = self._path_finder.bfs_shortest_path(graph_dict, src, tgt)
            path = result.get("path", []) if isinstance(result, dict) else (result or [])
            return (len(path) - 1 if path else None), None
        except Exception:
            logger.warning("Hop distance computation failed for %s -> %s; returning None sentinel", src, tgt, exc_info=True)
            return None, "hop_count"

    def _weighted_distance(self, graph_dict: Dict[str, Any], src: str, tgt: str) -> Tuple[Optional[float], Optional[str]]:
        """Return (weighted_distance, error). error is None on success."""
        if self._path_finder is None:
            return None, None
        try:
            result = self._path_finder.dijkstra_shortest_path(graph_dict, src, tgt)
            if isinstance(result, dict):
                return float(result.get("total_weight", len(result.get("path", [])) - 1)), None
            return None, None
        except Exception:
            logger.warning("Weighted distance computation failed for %s -> %s; returning None sentinel", src, tgt, exc_info=True)
            return None, "weighted_distance"

    def _semantic_similarity(self, graph_dict: Dict[str, Any], src: str, tgt: str) -> Tuple[Optional[float], Optional[str]]:
        """Return (similarity, error). error is None on success."""
        if self._similarity is None:
            return None, None
        try:
            sim = self._similarity.cosine_similarity(graph_dict, src, tgt)
            return (float(sim) if isinstance(sim, (int, float)) else None), None
        except Exception:
            logger.warning("Semantic similarity computation failed for %s -> %s; returning None sentinel", src, tgt, exc_info=True)
            return None, "semantic_similarity"

    def compute_pairs(
        self,
        include: Optional[List[str]] = None,
        node_subset: Optional[List[str]] = None,
    ) -> List[Dict[str, Any]]:
        """Compute all pairwise distance metrics and return as a list of dicts.

        When ``include`` contains ``"metric_errors"``, each row gains a
        ``metric_errors`` field: an empty string when all metrics succeeded, or
        a comma-separated list of metric names that raised during computation
        (e.g. ``"hop_count,weighted_distance"``). This lets downstream consumers
        distinguish legitimate ``None`` (no path) from computation failure.
        """
        include_set = set(include or _ALL_COLUMNS)
        track_errors = "metric_errors" in include_set
        include_set.discard("metric_errors")  # not a real metric to compute
        graph_dict = self._build_graph_dict()

        node_ids = node_subset or list(self.graph.nodes.keys())

        betweenness: Dict[str, float] = {}
        betweenness_err: Optional[str] = None
        if "source_betweenness" in include_set or "target_betweenness" in include_set:
            betweenness, betweenness_err = self._betweenness(graph_dict)

        rows = []
        for i, src in enumerate(node_ids):
            for tgt in node_ids:
                if src == tgt:
                    continue
                row: Dict[str, Any] = {}
                errors: List[str] = []
                if betweenness_err:
                    errors.append(betweenness_err)

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
                    hop_count, hop_err = self._hop_distance(graph_dict, src, tgt)
                    if hop_err:
                        errors.append(hop_err)
                    if "hop_count" in include_set:
                        row["hop_count"] = hop_count

                if "weighted_distance" in include_set:
                    wd_val, wd_err = self._weighted_distance(graph_dict, src, tgt)
                    row["weighted_distance"] = wd_val
                    if wd_err:
                        errors.append(wd_err)

                if "semantic_similarity" in include_set:
                    ss_val, ss_err = self._semantic_similarity(graph_dict, src, tgt)
                    row["semantic_similarity"] = ss_val
                    if ss_err:
                        errors.append(ss_err)

                if "distance_band" in include_set:
                    row["distance_band"] = classify_path_distance(hop_count) if hop_count is not None else "distant"

                if "source_betweenness" in include_set:
                    row["source_betweenness"] = betweenness.get(src)
                if "target_betweenness" in include_set:
                    row["target_betweenness"] = betweenness.get(tgt)

                if track_errors:
                    row["metric_errors"] = ",".join(errors) if errors else ""

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
