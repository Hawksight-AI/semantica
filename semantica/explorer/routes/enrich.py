"""
Enrichment and reasoning routes.
"""

import asyncio
import re
from typing import Dict, List, Optional, Tuple

from fastapi import APIRouter, Depends, HTTPException

from ..dependencies import get_session
from ..schemas import (
    DedupRequest,
    DedupResponse,
    EnrichExtractRequest,
    EnrichExtractResponse,
    LinkPredictionRequest,
    LinkPredictionResponse,
    MergeRequest,
    MergeResponse,
    ReasoningRequest,
    ReasoningResponse,
)
from ..session import GraphSession

router = APIRouter(tags=["Enrichment"])
_FACT_RE = re.compile(r"^(?P<predicate>[A-Za-z_][\w:-]*)\((?P<args>.*)\)$")

# SECURITY: Cap the candidate pool loaded by link prediction to prevent a
# single request from exhausting server memory (CWE-770).  Without a cap the
# endpoint calls session.get_nodes(limit=999_999) and scores every node in
# O(N^2), consuming ~1.6 GB RAM at the maximum limit (measured via
# tracemalloc at 1.7 KB/node with 128-dim embeddings; see poc_runner.py).
# Mirrors the SPARQL DoS fix from PR #898 (50k cap + semaphore).
#
# NOTE: session.get_nodes()/get_edges() (paginate_nodes/paginate_edges)
# normalize the *entire* matching set before applying `limit` -- passing
# limit=_LINK_PREDICTION_MAX_NODES does not bound that work. The `total`
# they return can only be checked *after* paying that full cost. To actually
# reject an oversized graph before doing that work, check session.get_raw_counts()
# (O(1) collection lengths) first -- see predict_links() below.
_LINK_PREDICTION_MAX_NODES = 10_000
_LINK_PREDICTION_MAX_EDGES = 50_000
_link_prediction_semaphore = asyncio.Semaphore(2)


def _safe_dict(obj) -> dict:
    if isinstance(obj, dict):
        return obj
    if hasattr(obj, "__dict__"):
        return {key: value for key, value in obj.__dict__.items() if not key.startswith("_")}
    return {"value": str(obj)}


def _parse_fact(fact: str) -> Optional[Tuple[str, List[str]]]:
    match = _FACT_RE.match((fact or "").strip())
    if not match:
        return None
    args = [arg.strip().strip('"').strip("'") for arg in match.group("args").split(",") if arg.strip()]
    return match.group("predicate"), args


def _parse_rule(rule: str) -> Optional[Tuple[List[Tuple[str, List[str]]], Tuple[str, List[str]]]]:
    cleaned = (rule or "").strip()
    if not cleaned.upper().startswith("IF ") or " THEN " not in cleaned.upper():
        return None
    upper = cleaned.upper()
    then_index = upper.index(" THEN ")
    antecedent_text = cleaned[3:then_index]
    consequent_text = cleaned[then_index + 6 :]
    antecedents = []
    for segment in re.split(r" AND ", " ".join(antecedent_text.split()), flags=re.IGNORECASE):
        parsed = _parse_fact(segment)
        if parsed is None:
            return None
        antecedents.append(parsed)
    consequent = _parse_fact(consequent_text)
    if consequent is None:
        return None
    return antecedents, consequent


def _token_is_variable(token: str) -> bool:
    return token.startswith("?")


def _match_pattern(pattern: Tuple[str, List[str]], fact: Tuple[str, List[str]], bindings: Dict[str, str]) -> Optional[Dict[str, str]]:
    pattern_predicate, pattern_args = pattern
    fact_predicate, fact_args = fact
    if pattern_predicate != fact_predicate or len(pattern_args) != len(fact_args):
        return None

    next_bindings = dict(bindings)
    for pattern_arg, fact_arg in zip(pattern_args, fact_args):
        if _token_is_variable(pattern_arg):
            bound_value = next_bindings.get(pattern_arg)
            if bound_value is None:
                next_bindings[pattern_arg] = fact_arg
            elif bound_value != fact_arg:
                return None
        elif pattern_arg != fact_arg:
            return None
    return next_bindings


def _instantiate(pattern: Tuple[str, List[str]], bindings: Dict[str, str]) -> str:
    predicate, args = pattern
    resolved = [bindings.get(arg, arg) for arg in args]
    return f"{predicate}({', '.join(resolved)})"


def _run_fallback_reasoner(facts: List[str], rules: List[str]) -> List[str]:
    parsed_facts = [parsed for parsed in (_parse_fact(fact) for fact in facts) if parsed is not None]
    inferred: List[str] = []
    known = set(facts)

    for rule in rules:
        parsed_rule = _parse_rule(rule)
        if parsed_rule is None:
            continue
        antecedents, consequent = parsed_rule
        bindings_list: List[Dict[str, str]] = [{}]
        for antecedent in antecedents:
            next_bindings: List[Dict[str, str]] = []
            for bindings in bindings_list:
                for fact in parsed_facts:
                    matched = _match_pattern(antecedent, fact, bindings)
                    if matched is not None:
                        next_bindings.append(matched)
            bindings_list = next_bindings
            if not bindings_list:
                break
        for bindings in bindings_list:
            candidate = _instantiate(consequent, bindings)
            if candidate not in known:
                known.add(candidate)
                inferred.append(candidate)
    return inferred


def _apply_inferred_edges(
    session: GraphSession,
    inferred_facts: List[str],
    body: ReasoningRequest,
) -> int:
    added_edges = 0
    for fact in inferred_facts:
        parsed = _parse_fact(fact)
        if parsed is None:
            continue
        predicate, args = parsed
        if len(args) != 2:
            continue
        source, target = args
        if session.get_node(source) is None:
            session.add_node(source, "entity", content=source)
        if session.get_node(target) is None:
            session.add_node(target, "entity", content=target)
        edge_type = body.inferred_edge_type or predicate
        session.add_edge(
            source,
            target,
            edge_type=edge_type,
            inferred=True,
            inferred_from=fact,
            reasoning_mode=body.mode,
            rules=list(body.rules),
        )
        added_edges += 1
    return added_edges


@router.post("/api/enrich/extract", response_model=EnrichExtractResponse)
async def extract_entities(
    body: EnrichExtractRequest,
    session: GraphSession = Depends(get_session),
):
    try:
        from ...semantic_extract import NamedEntityRecognizer, RelationExtractor
    except ImportError:
        raise HTTPException(
            status_code=503,
            detail="semantic_extract module not available. Ensure spacy and transformers are installed.",
        )

    recognizer = NamedEntityRecognizer(confidence_threshold=0.7)
    extractor = RelationExtractor(confidence_threshold=0.6)

    entities = await asyncio.to_thread(recognizer.extract_entities, body.text)

    ent_list = entities if isinstance(entities, list) else getattr(entities, "entities", [])

    relations = await asyncio.to_thread(
        extractor.extract_relations, body.text, ent_list
    )

    rel_list = relations if isinstance(relations, list) else getattr(relations, "relations", [])

    return EnrichExtractResponse(
        entities=[_safe_dict(entity) for entity in ent_list],
        relations=[_safe_dict(relation) for relation in rel_list],
    )


@router.post("/api/enrich/links", response_model=LinkPredictionResponse)
async def predict_links(
    body: LinkPredictionRequest,
    session: GraphSession = Depends(get_session),
):
    predictor = session.link_predictor
    if predictor is None:
        raise HTTPException(status_code=503, detail="LinkPredictor not available; KG extras may not be installed.")

    node = await asyncio.to_thread(session.get_node, body.node_id)
    if node is None:
        raise HTTPException(status_code=404, detail=f"Node '{body.node_id}' not found")

    # SECURITY: Acquire semaphore BEFORE loading data so concurrent requests
    # cannot pile up expensive threadpool work and memory pressure (Qodo #2).
    async with _link_prediction_semaphore:
        # SECURITY: Reject an oversized graph using the O(1) raw collection
        # lengths BEFORE calling get_nodes()/get_edges(), which normalize the
        # *entire* matching set before applying `limit` -- checking `total`
        # only after that call still pays the full O(graph size) cost the cap
        # is meant to avoid.
        total_nodes, total_edges = await asyncio.to_thread(session.get_raw_counts)
        if total_nodes > _LINK_PREDICTION_MAX_NODES:
            raise HTTPException(
                status_code=413,
                detail=(
                    f"Graph has {total_nodes:,} nodes; link prediction is capped at "
                    f"{_LINK_PREDICTION_MAX_NODES:,} nodes to prevent memory exhaustion. "
                    "Use the graph search endpoint for large graphs."
                ),
            )
        if total_edges > _LINK_PREDICTION_MAX_EDGES:
            raise HTTPException(
                status_code=413,
                detail=(
                    f"Graph has {total_edges:,} edges; link prediction is capped at "
                    f"{_LINK_PREDICTION_MAX_EDGES:,} edges to prevent memory exhaustion. "
                    "Use the graph search endpoint for large graphs."
                ),
            )

        # SECURITY: Load at most _LINK_PREDICTION_MAX_NODES candidates.
        # The hardcoded limit in the original code consumed ~1.6 GB RAM
        # per request and had no concurrency guard, making it trivially DoS-able.
        nodes, _ = await asyncio.to_thread(session.get_nodes, skip=0, limit=_LINK_PREDICTION_MAX_NODES)

        # Load edges specific to the queried node rather than a globally
        # truncated page — avoids missing neighbours when the node's edges
        # fall outside the first page (Qodo #3).
        edges_out, _ = await asyncio.to_thread(
            session.get_edges, source=body.node_id, skip=0, limit=_LINK_PREDICTION_MAX_NODES,
        )
        edges_in, _ = await asyncio.to_thread(
            session.get_edges, target=body.node_id, skip=0, limit=_LINK_PREDICTION_MAX_NODES,
        )

        existing_neighbors = {
            edge.get("target") for edge in edges_out
        } | {
            edge.get("source") for edge in edges_in
        }

        def _score_all() -> list:
            results = []
            for candidate_node in nodes:
                candidate_id = candidate_node.get("id")
                if not candidate_id or candidate_id == body.node_id or candidate_id in existing_neighbors:
                    continue
                if body.candidate_type and candidate_node.get("type") != body.candidate_type:
                    continue
                try:
                    score = predictor.score_link(session.graph, body.node_id, candidate_id)
                except Exception:
                    continue
                if score >= body.min_score:
                    results.append(
                        {
                            "target": candidate_id,
                            "score": score,
                            "type": candidate_node.get("type", "entity"),
                            "label": candidate_node.get("content", candidate_id),
                        }
                    )
            results.sort(key=lambda item: item["score"], reverse=True)
            return results

        scored = await asyncio.to_thread(_score_all)
    return LinkPredictionResponse(node_id=body.node_id, predictions=scored[: body.top_n])


@router.post("/api/enrich/dedup", response_model=DedupResponse)
async def detect_duplicates(
    body: DedupRequest,
    session: GraphSession = Depends(get_session),
):
    try:
        from ...deduplication import DuplicateDetector

        detector = DuplicateDetector()
        nodes, _ = await asyncio.to_thread(session.get_nodes, skip=0, limit=999_999)
        entities = [
            {"id": node.get("id"), "text": node.get("content", node.get("id", "")), "type": node.get("type", "entity")}
            for node in nodes
        ]
        duplicates = await asyncio.to_thread(detector.detect_duplicates, entities, threshold=body.threshold)
        duplicate_list = duplicates if isinstance(duplicates, list) else getattr(duplicates, "duplicates", [])
        return DedupResponse(duplicates=[_safe_dict(item) for item in duplicate_list], total_flagged=len(duplicate_list))
    except ImportError:
        raise HTTPException(status_code=503, detail="Deduplication module not available.")
    except Exception as exc:
        raise HTTPException(status_code=422, detail=f"Dedup scan failed: {exc}")


@router.post("/api/reason", response_model=ReasoningResponse)
async def run_reasoning(
    body: ReasoningRequest,
    session: GraphSession = Depends(get_session),
):
    inferred_facts: List[str] = []
    try:
        from ...reasoning.reasoner import Reasoner

        reasoner = Reasoner()
        inferred = await asyncio.to_thread(reasoner.infer_facts, body.facts, body.rules)
        if isinstance(inferred, list):
            inferred_facts = inferred
        if not inferred_facts:
            inferred_facts = _run_fallback_reasoner(body.facts, body.rules)
    except ImportError:
        inferred_facts = _run_fallback_reasoner(body.facts, body.rules)
    except Exception:
        inferred_facts = _run_fallback_reasoner(body.facts, body.rules)

    added_edges = 0
    if body.apply_to_graph and inferred_facts:
        added_edges = await asyncio.to_thread(_apply_inferred_edges, session, inferred_facts, body)

    return ReasoningResponse(
        inferred_facts=inferred_facts,
        rules_fired=len(inferred_facts),
        added_edges=added_edges,
        mutated=added_edges > 0,
    )


@router.post("/api/enrich/merge", response_model=MergeResponse)
async def merge_nodes(
    body: MergeRequest,
    session: GraphSession = Depends(get_session),
):
    primary_id = body.primary_id
    duplicate_ids = body.duplicate_ids

    node = await asyncio.to_thread(session.get_node, primary_id)
    if node is None:
        raise HTTPException(status_code=404, detail=f"Primary node '{primary_id}' not found")

    def _do_merge() -> tuple[list[str], int]:
        removed: list[str] = []
        edges_updated = 0
        graph = session.graph

        for duplicate_id in duplicate_ids:
            if duplicate_id == primary_id or duplicate_id not in graph:
                continue

            duplicate_node = graph.nodes.get(duplicate_id)
            primary_node = graph.nodes.get(primary_id)
            if duplicate_node and primary_node:
                for key, value in (duplicate_node.properties or {}).items():
                    if key not in (primary_node.properties or {}):
                        primary_node.properties[key] = value
                        primary_node.metadata[key] = value

            edges_to_add = []
            retained_edges = []
            for edge in list(graph.edges):
                if edge.source_id == duplicate_id or edge.target_id == duplicate_id:
                    new_source = primary_id if edge.source_id == duplicate_id else edge.source_id
                    new_target = primary_id if edge.target_id == duplicate_id else edge.target_id
                    if new_source != new_target:
                        edges_to_add.append(
                            {
                                "source_id": new_source,
                                "target_id": new_target,
                                "type": edge.edge_type,
                                "weight": edge.weight,
                                "properties": edge.metadata,
                            }
                        )
                        edges_updated += 1
                else:
                    retained_edges.append(edge)

            graph.edges = retained_edges
            graph._adjacency.pop(duplicate_id, None)
            for adjacency in graph._adjacency.values():
                adjacency[:] = [edge for edge in adjacency if edge.target_id != duplicate_id]
            graph.edge_type_index.clear()
            for edge in graph.edges:
                graph.edge_type_index[edge.edge_type].append(edge)

            old_type = graph.nodes[duplicate_id].node_type
            graph.node_type_index.get(old_type, set()).discard(duplicate_id)
            del graph.nodes[duplicate_id]
            removed.append(duplicate_id)

            if edges_to_add:
                graph.add_edges(edges_to_add)

        return removed, edges_updated

    removed_ids, edges_updated = await asyncio.to_thread(_do_merge)
    if removed_ids:
        await asyncio.to_thread(session.rebuild_search_index)
    return MergeResponse(merged_into=primary_id, removed_ids=removed_ids, edges_updated=edges_updated)
