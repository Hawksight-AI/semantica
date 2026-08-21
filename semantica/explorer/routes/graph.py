"""
Graph routes for explorer node, edge, path, and search APIs.
"""

import asyncio
import logging
import time
from enum import Enum
from typing import List, Optional

logger = logging.getLogger(__name__)

from fastapi import APIRouter, Depends, HTTPException, Query

from ...utils.helpers import classify_path_distance
from ..dependencies import get_session
from ..schemas import (
    DistanceMatrixRequest,
    DistanceMatrixResponse,
    EdgeListResponse,
    EdgeResponse,
    GraphStatsResponse,
    NeighborResponse,
    NodeListResponse,
    NodeResponse,
    PathResponse,
    SearchRequest,
    SearchResultItem,
    SearchResultResponse,
    SemanticNeighborItem,
    SemanticNeighborhoodResponse,
)
from ..session import GraphSession

router = APIRouter(prefix="/api/graph", tags=["Graph"])


def _build_interpretation(
    distance_band: str,
    hop_count: int,
    bottleneck_node: Optional[str],
    confidence_decay: Optional[float],
) -> str:
    if distance_band == "direct":
        base = "Direct relationship"
    elif distance_band == "near":
        base = f"Closely related via {hop_count - 1} intermediate node(s)"
    elif distance_band == "mid-range":
        base = f"Reachable in {hop_count} steps across topic boundaries"
    else:
        base = f"Distal connection spanning {hop_count} hops"

    if bottleneck_node:
        base += f", routed through bottleneck '{bottleneck_node}'"

    if confidence_decay is not None:
        if confidence_decay > 0.7:
            base += " — high confidence."
        elif confidence_decay > 0.4:
            base += " — moderate confidence."
        else:
            base += " — low confidence, treat as weak evidence."
    else:
        base += "."

    return base


def _parse_bbox(raw_bbox: Optional[str]) -> Optional[tuple[float, float, float, float]]:
    if not raw_bbox:
        return None
    parts = [part.strip() for part in raw_bbox.split(",")]
    if len(parts) != 4:
        raise ValueError("bbox must be four comma-separated numbers: min_x,min_y,max_x,max_y")
    min_x, min_y, max_x, max_y = [float(part) for part in parts]
    if min_x > max_x or min_y > max_y:
        raise ValueError("bbox minimum values must be less than or equal to maximum values")
    return min_x, min_y, max_x, max_y


def _get_cached_embeddings(session: GraphSession) -> dict[str, List[float]]:
    """Get embeddings from session cache for optimal performance."""
    return session.get_cached_embeddings()


def _node_response(node: dict) -> NodeResponse:
    return NodeResponse(**node)


def _edge_response(edge: dict) -> EdgeResponse:
    return EdgeResponse(**edge)


@router.get("/nodes", response_model=NodeListResponse)
async def list_nodes(
    type: Optional[str] = Query(None, description="Filter by node type"),
    search: Optional[str] = Query(None, description="Keyword search over node content"),
    bbox: Optional[str] = Query(None, description="Viewport filter: min_x,min_y,max_x,max_y"),
    skip: int = Query(0, ge=0),
    limit: int = Query(100, ge=1, le=5000),
    cursor: Optional[str] = Query(None, description="Opaque cursor for forward pagination"),
    session: GraphSession = Depends(get_session),
):
    parsed_bbox = _parse_bbox(bbox)
    nodes, total, next_cursor = await asyncio.to_thread(
        session.paginate_nodes,
        node_type=type,
        search=search,
        skip=skip,
        limit=limit,
        cursor=cursor,
        bbox=parsed_bbox,
    )
    return NodeListResponse(
        nodes=[_node_response(node) for node in nodes],
        total=total,
        skip=skip,
        limit=limit,
        next_cursor=next_cursor,
        has_more=next_cursor is not None,
    )


@router.get("/node/{node_id}", response_model=NodeResponse)
async def get_node(
    node_id: str,
    session: GraphSession = Depends(get_session),
):
    node = await asyncio.to_thread(session.get_node, node_id)
    if node is None:
        raise HTTPException(status_code=404, detail=f"Node '{node_id}' not found")
    return _node_response(node)


@router.get("/node/{node_id}/neighbors", response_model=list[NeighborResponse])
async def get_neighbors(
    node_id: str,
    depth: int = Query(1, ge=1, le=5),
    session: GraphSession = Depends(get_session),
):
    neighbors = await asyncio.to_thread(session.get_neighbors, node_id, depth)
    return [
        NeighborResponse(
            id=neighbor.get("id", ""),
            type=neighbor.get("type", ""),
            content=neighbor.get("content", ""),
            relationship=neighbor.get("relationship", ""),
            weight=neighbor.get("weight", 1.0),
            hop=neighbor.get("hop", 1),
        )
        for neighbor in neighbors
    ]


@router.get("/edges", response_model=EdgeListResponse)
async def list_edges(
    type: Optional[str] = Query(None, description="Filter by edge type"),
    source: Optional[str] = Query(None, description="Filter by source node ID"),
    target: Optional[str] = Query(None, description="Filter by target node ID"),
    skip: int = Query(0, ge=0),
    limit: int = Query(100, ge=1, le=5000),
    cursor: Optional[str] = Query(None, description="Opaque cursor for forward pagination"),
    session: GraphSession = Depends(get_session),
):
    edges, total, next_cursor = await asyncio.to_thread(
        session.paginate_edges,
        edge_type=type,
        source=source,
        target=target,
        skip=skip,
        limit=limit,
        cursor=cursor,
    )
    return EdgeListResponse(
        edges=[_edge_response(edge) for edge in edges],
        total=total,
        skip=skip,
        limit=limit,
        next_cursor=next_cursor,
        has_more=next_cursor is not None,
    )


class _PathAlgorithm(str, Enum):
    bfs = "bfs"
    dijkstra = "dijkstra"




async def _find_path_impl(
    source: str,
    target: str,
    algorithm: _PathAlgorithm,
    directed: bool,
    session: GraphSession,
) -> PathResponse:
    """Resolve and enrich a path between two arbitrary graph node ids."""
    path_finder = session.path_finder
    if path_finder is None:
        raise HTTPException(status_code=503, detail="PathFinder not available; KG extras may not be installed.")

    graph_dict = await asyncio.to_thread(session.build_graph_dict)
    path_fn = (
        path_finder.dijkstra_shortest_path
        if algorithm == _PathAlgorithm.dijkstra
        else path_finder.bfs_shortest_path
    )
    try:
        result = await asyncio.to_thread(path_fn, graph_dict, source, target, directed=directed)
    except Exception as exc:
        raise HTTPException(status_code=404, detail=f"No path found from '{source}' to '{target}': {exc}")

    path_nodes = result.get("path", []) if isinstance(result, dict) else (result or [])
    if not path_nodes:
        raise HTTPException(status_code=404, detail=f"No path found from '{source}' to '{target}'")

    total_weight = result.get("total_weight", 0.0) if isinstance(result, dict) else 0.0
    edge_ids = await asyncio.to_thread(session.resolve_path_edge_ids, path_nodes)

    hop_count = len(path_nodes) - 1 if path_nodes else 0
    distance_band = classify_path_distance(hop_count)

    # FR-4 enrichment — compute optional fields from existing session analytics
    confidence_decay: Optional[float] = None
    bottleneck_node: Optional[str] = None
    semantic_similarity: Optional[float] = None
    path_coherence_score: Optional[float] = None
    alternative_path_count: int = 0

    try:
        graph_dict = await asyncio.to_thread(session.build_graph_dict)

        # Build edge weight index once in O(E) so each hop lookup is O(1).
        # graph_dict may use "edges" or "relationships" depending on the graph source.
        edge_weight_index: dict = {}
        for _e in graph_dict.get("edges") or graph_dict.get("relationships", []):
            _s, _t = _e.get("source"), _e.get("target")
            _w = float(_e.get("weight", 1.0))
            edge_weight_index[(_s, _t)] = _w
            if not directed:
                edge_weight_index.setdefault((_t, _s), _w)

        # Confidence decay — product of edge weights along the path (O(L))
        decay = 1.0
        for i in range(len(path_nodes) - 1):
            decay *= edge_weight_index.get((path_nodes[i], path_nodes[i + 1]), 1.0)
        confidence_decay = decay

        # Bottleneck — intermediate node with highest betweenness in subgraph
        intermediates = path_nodes[1:-1] if len(path_nodes) > 2 else []
        if intermediates and session.centrality is not None:
            sub_dict = await asyncio.to_thread(session.build_graph_dict, path_nodes)
            centrality_result = await asyncio.to_thread(
                session.centrality.calculate_betweenness_centrality, sub_dict
            )
            scores = centrality_result.get("betweenness", {}) if isinstance(centrality_result, dict) else {}
            if scores:
                bottleneck_node = max(
                    (n for n in intermediates if n in scores),
                    key=lambda n: scores.get(n, 0.0),
                    default=None,
                )

        # Alternative paths — count simple paths within hop_count + 2
        if path_finder is not None and hop_count > 0:
            try:
                k_paths = await asyncio.to_thread(
                    path_finder.find_k_shortest_paths,
                    graph_dict, source, target, hop_count + 2, directed=directed
                )
                alternative_path_count = max(0, len(k_paths) - 1)
            except Exception as exc:
                logger.debug("k_shortest_paths unavailable for enrichment: %s", exc)

        # Semantic similarity (source ↔ target)
        if session.similarity is not None:
            try:
                sim_result = await asyncio.to_thread(
                    session.similarity.cosine_similarity,
                    graph_dict, source, target
                )
                if isinstance(sim_result, (int, float)):
                    semantic_similarity = float(sim_result)
            except Exception as exc:
                logger.debug("semantic_similarity unavailable for enrichment: %s", exc)

        # Path coherence — mean pairwise similarity of consecutive nodes
        if session.similarity is not None and len(path_nodes) >= 2:
            try:
                pair_sims: List[float] = []
                for i in range(len(path_nodes) - 1):
                    sim = await asyncio.to_thread(
                        session.similarity.cosine_similarity,
                        graph_dict, path_nodes[i], path_nodes[i + 1]
                    )
                    if isinstance(sim, (int, float)):
                        pair_sims.append(float(sim))
                if pair_sims:
                    path_coherence_score = sum(pair_sims) / len(pair_sims)
            except Exception as exc:
                logger.debug("path_coherence unavailable for enrichment: %s", exc)

    except Exception as exc:
        logger.debug("FR-4 enrichment skipped: %s", exc)

    interpretation = _build_interpretation(distance_band, hop_count, bottleneck_node, confidence_decay)

    return PathResponse(
        source=source,
        target=target,
        algorithm=algorithm.value,
        path=path_nodes,
        edge_ids=edge_ids,
        total_weight=total_weight,
        directed=directed,
        hop_count=hop_count,
        distance_band=distance_band,
        semantic_similarity=semantic_similarity,
        path_coherence_score=path_coherence_score,
        confidence_decay=confidence_decay,
        bottleneck_node=bottleneck_node,
        alternative_path_count=alternative_path_count,
        interpretation=interpretation,
    )


@router.get("/path", response_model=PathResponse)
async def find_path_by_query(
    source: str = Query(..., description="Source node ID"),
    target: str = Query(..., description="Target node ID"),
    algorithm: _PathAlgorithm = Query(_PathAlgorithm.bfs, description="Algorithm: bfs or dijkstra"),
    directed: bool = Query(True, description="If false, treat edges as undirected for traversal"),
    session: GraphSession = Depends(get_session),
):
    return await _find_path_impl(source, target, algorithm, directed, session)


@router.get("/node/{node_id}/path", response_model=PathResponse)
async def find_path(
    node_id: str,
    target: str = Query(..., description="Target node ID"),
    algorithm: _PathAlgorithm = Query(_PathAlgorithm.bfs, description="Algorithm: bfs or dijkstra"),
    directed: bool = Query(True, description="If false, treat edges as undirected for traversal"),
    session: GraphSession = Depends(get_session),
):
    """Deprecated path-segment route kept for backward compatibility.

    Node IDs that contain slashes will return 404 because FastAPI decodes
    %2F before route matching.  Use GET /api/graph/path?source=...&target=...
    for slash-safe path lookup.
    """
    return await _find_path_impl(node_id, target, algorithm, directed, session)


@router.post("/search", response_model=SearchResultResponse)
async def search_nodes(
    body: SearchRequest,
    session: GraphSession = Depends(get_session),
):
    results = await asyncio.to_thread(session.search, body.query, body.limit, body.filters)

    # FR-7 — compute hop distances from anchor when requested
    hop_by_id: dict = {}
    if body.anchor_node:
        neighbors = await asyncio.to_thread(
            session.graph.get_neighbor_distances,
            body.anchor_node,
            hops=body.max_hops if body.max_hops is not None else 10,
        )
        hop_by_id = {n.get("id"): n.get("hop") for n in neighbors}
        hop_by_id[body.anchor_node] = 0

    items: List[SearchResultItem] = []
    for result in results:
        node_data = result.get("node", {})
        node_id = node_data.get("id", "")
        raw_score = result.get("score", 0.0)

        hop_distance: Optional[int] = hop_by_id.get(node_id) if body.anchor_node else None

        # Drop results beyond max_hops
        if body.anchor_node and body.max_hops is not None:
            if hop_distance is None or hop_distance > body.max_hops:
                continue

        # Compute combined ranking score
        final_score = raw_score
        if body.anchor_node and hop_distance is not None:
            proximity = 1.0 if hop_distance == 0 else 1.0 / hop_distance
            if body.rank_by == "proximity":
                final_score = proximity
            elif body.rank_by == "hybrid":
                final_score = 0.6 * raw_score + 0.4 * proximity

        items.append(
            SearchResultItem(
                node=_node_response(node_data),
                score=final_score,
                hop_distance=hop_distance,
            )
        )

    if body.rank_by in ("proximity", "hybrid") and body.anchor_node:
        items.sort(key=lambda item: item.score, reverse=True)

    return SearchResultResponse(results=items, total=len(items), query=body.query)


@router.post("/distance-matrix", response_model=DistanceMatrixResponse)
async def distance_matrix(
    body: DistanceMatrixRequest,
    session: GraphSession = Depends(get_session),
):
    if len(body.node_ids) > 50:
        raise HTTPException(
            status_code=413,
            detail=f"Too many nodes: {len(body.node_ids)} requested; maximum is 50 per request.",
        )

    if body.metric == "semantic" and session.similarity is None:
        raise HTTPException(
            status_code=503,
            detail="metric='semantic' requires an embedding backend which is not available in this session.",
        )

    started = time.perf_counter()
    path_finder = session.path_finder

    n = len(body.node_ids)
    matrix: List[List[Optional[float]]] = [[None] * n for _ in range(n)]
    unreachable: List[tuple] = []

    for i in range(n):
        matrix[i][i] = 0.0
        for j in range(i + 1, n):
            src, tgt = body.node_ids[i], body.node_ids[j]
            try:
                if body.metric == "semantic" and session.similarity is not None:
                    # Use cached embeddings for semantic distance calculation
                    embeddings = _get_cached_embeddings(session)
                    src_embedding = embeddings.get(src)
                    tgt_embedding = embeddings.get(tgt)
                    
                    if src_embedding is None or tgt_embedding is None:
                        val = None
                    else:
                        # Calculate cosine similarity directly from cached embeddings
                        import numpy as np
                        src_vec = np.array(src_embedding)
                        tgt_vec = np.array(tgt_embedding)
                        sim = np.dot(src_vec, tgt_vec) / (np.linalg.norm(src_vec) * np.linalg.norm(tgt_vec))
                        val = 1.0 - float(sim) if isinstance(sim, (int, float)) else None
                    
                    matrix[i][j] = val
                    matrix[j][i] = val
                elif path_finder is not None:
                    path_fn = (
                        path_finder.dijkstra_shortest_path
                        if body.metric == "weighted"
                        else path_finder.bfs_shortest_path
                    )
                    graph_dict = await asyncio.to_thread(session.build_graph_dict)
                    result = await asyncio.to_thread(path_fn, graph_dict, src, tgt)
                    path_nodes = result.get("path", []) if isinstance(result, dict) else (result or [])
                    if path_nodes:
                        val = (
                            float(result.get("total_weight", len(path_nodes) - 1))
                            if body.metric == "weighted"
                            else float(len(path_nodes) - 1)
                        )
                        matrix[i][j] = val
                        matrix[j][i] = val
                    else:
                        unreachable.append((src, tgt))
                        unreachable.append((tgt, src))
            except Exception as exc:
                logger.debug("distance_matrix pair (%s, %s) failed: %s", src, tgt, exc)
                unreachable.append((src, tgt))
                unreachable.append((tgt, src))

    elapsed_ms = round((time.perf_counter() - started) * 1000, 2)
    return DistanceMatrixResponse(
        nodes=body.node_ids,
        metric=body.metric,
        matrix=matrix,
        unreachable_pairs=unreachable,
        computation_time_ms=elapsed_ms,
    )


async def _semantic_neighborhood_impl(
    node_id: str,
    top_k: int,
    min_similarity: float,
    session: GraphSession,
) -> SemanticNeighborhoodResponse:
    node = await asyncio.to_thread(session.get_node, node_id)
    if node is None:
        raise HTTPException(status_code=404, detail=f"Node '{node_id}' not found")

    similarity = session.similarity
    if similarity is None:
        raise HTTPException(
            status_code=503,
            detail="Semantic similarity is unavailable for this graph session.",
        )

    embeddings = _get_cached_embeddings(session)
    query_embedding = embeddings.get(node_id)
    if not embeddings or query_embedding is None:
        raise HTTPException(
            status_code=503,
            detail="Semantic similarity is unavailable because this graph has no node embeddings.",
        )

    neighbors: List[SemanticNeighborItem] = []
    try:
        similar = await asyncio.to_thread(
            similarity.find_most_similar,
            embeddings,
            query_embedding,
            top_k=top_k * 2,
        )
    except Exception as exc:
        logger.debug("semantic_neighborhood similarity search failed: %s", exc)
        raise HTTPException(
            status_code=503,
            detail="Semantic similarity search failed for this graph session.",
        ) from exc

    # find_most_similar returns list of (node_id, score) or dicts
    for item in similar:
        if isinstance(item, (list, tuple)) and len(item) >= 2:
            nid, sim_score = item[0], item[1]
        elif isinstance(item, dict):
            nid = item.get("node_id") or item.get("id", "")
            sim_score = item.get("similarity", item.get("score", 0.0))
        else:
            continue
        if float(sim_score) < min_similarity or nid == node_id:
            continue
        neighbor_node = await asyncio.to_thread(session.get_node, nid)
        if neighbor_node is None:
            continue
        neighbors.append(
            SemanticNeighborItem(
                id=str(nid),
                type=neighbor_node.get("type", ""),
                content=neighbor_node.get("content", ""),
                similarity=float(sim_score),
            )
        )
        if len(neighbors) >= top_k:
            break

    return SemanticNeighborhoodResponse(
        anchor_node=node_id,
        neighbors=neighbors,
        total=len(neighbors),
    )


@router.get("/semantic-neighborhood", response_model=SemanticNeighborhoodResponse)
async def semantic_neighborhood_by_query(
    node_id: str = Query(..., description="Anchor node ID"),
    top_k: int = Query(20, ge=1, le=200),
    min_similarity: float = Query(0.0, ge=0.0, le=1.0),
    session: GraphSession = Depends(get_session),
):
    return await _semantic_neighborhood_impl(node_id, top_k, min_similarity, session)


@router.get("/node/{node_id}/semantic-neighborhood", response_model=SemanticNeighborhoodResponse)
async def semantic_neighborhood(
    node_id: str,
    top_k: int = Query(20, ge=1, le=200),
    min_similarity: float = Query(0.0, ge=0.0, le=1.0),
    session: GraphSession = Depends(get_session),
):
    """Deprecated path-segment route kept for backward compatibility.

    Node IDs that contain slashes will return 404 because FastAPI decodes
    %2F before route matching.  Use GET /api/graph/semantic-neighborhood?node_id=...
    for slash-safe semantic neighborhood lookup.
    """
    return await _semantic_neighborhood_impl(node_id, top_k, min_similarity, session)


@router.get("/stats", response_model=GraphStatsResponse)
async def graph_stats(
    session: GraphSession = Depends(get_session),
):
    stats = await asyncio.to_thread(session.get_stats)
    return GraphStatsResponse(**stats)
