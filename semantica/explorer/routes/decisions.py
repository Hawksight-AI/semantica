"""
Decision routes using ContextGraph-native fallbacks.
"""

import asyncio
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query

from ..dependencies import get_session
from ..schemas import CausalChainResponse, CausalDistanceReport, ComplianceResponse, DecisionResponse
from ..session import GraphSession

router = APIRouter(prefix="/api/decisions", tags=["Decisions"])


def _node_to_decision(node: dict) -> DecisionResponse:
    properties = node.get("properties", {})
    return DecisionResponse(
        decision_id=node.get("id", ""),
        category=properties.get("category", ""),
        scenario=properties.get("scenario", ""),
        reasoning=properties.get("reasoning", ""),
        outcome=properties.get("outcome", ""),
        confidence=float(properties.get("confidence", 0.0) or 0.0),
        timestamp=properties.get("timestamp"),
        metadata=properties,
    )


@router.get("", response_model=list[DecisionResponse])
async def list_decisions(
    category: Optional[str] = Query(None),
    skip: int = Query(0, ge=0),
    limit: int = Query(50, ge=1, le=500),
    session: GraphSession = Depends(get_session),
):
    nodes, _ = await asyncio.to_thread(
        session.get_nodes,
        node_type="decision",
        skip=0,
        limit=999_999,
    )

    if category:
        nodes = [
            node
            for node in nodes
            if str(node.get("properties", {}).get("category", "")).lower() == category.lower()
        ]

    return [_node_to_decision(node) for node in nodes[skip : skip + limit]]


@router.get("/{decision_id}", response_model=DecisionResponse)
async def get_decision(
    decision_id: str,
    session: GraphSession = Depends(get_session),
):
    node = await asyncio.to_thread(session.get_node, decision_id)
    if node is None:
        raise HTTPException(status_code=404, detail=f"Decision '{decision_id}' not found")
    return _node_to_decision(node)


@router.get("/{decision_id}/chain", response_model=CausalChainResponse)
async def get_causal_chain(
    decision_id: str,
    session: GraphSession = Depends(get_session),
):
    node = await asyncio.to_thread(session.get_node, decision_id)
    if node is None:
        raise HTTPException(status_code=404, detail=f"Decision '{decision_id}' not found")

    neighbors = await asyncio.to_thread(session.get_neighbors, decision_id, 5)
    chain = [
        {
            "id": neighbor.get("id"),
            "type": neighbor.get("type"),
            "relationship": neighbor.get("relationship"),
            "hop": neighbor.get("hop"),
            "content": neighbor.get("content", ""),
        }
        for neighbor in neighbors
    ]
    return CausalChainResponse(decision_id=decision_id, chain=chain)


@router.get("/{decision_id}/precedents", response_model=list[DecisionResponse])
async def get_precedents(
    decision_id: str,
    limit: int = Query(10, ge=1, le=100),
    session: GraphSession = Depends(get_session),
):
    node = await asyncio.to_thread(session.get_node, decision_id)
    if node is None:
        raise HTTPException(status_code=404, detail=f"Decision '{decision_id}' not found")

    properties = node.get("properties", {})
    category = str(properties.get("category", ""))
    scenario_words = set(str(properties.get("scenario", "")).lower().split())

    all_decisions, _ = await asyncio.to_thread(
        session.get_nodes,
        node_type="decision",
        skip=0,
        limit=999_999,
    )

    scored = []
    for decision in all_decisions:
        if decision.get("id") == decision_id:
            continue
        other_props = decision.get("properties", {})
        score = 0.0
        if category and str(other_props.get("category", "")).lower() == category.lower():
            score += 0.5
        other_words = set(str(other_props.get("scenario", "")).lower().split())
        if scenario_words and other_words:
            overlap = len(scenario_words & other_words) / max(len(scenario_words | other_words), 1)
            score += 0.5 * overlap
        scored.append((score, decision))

    scored.sort(key=lambda item: item[0], reverse=True)
    return [_node_to_decision(decision) for _, decision in scored[:limit]]


@router.get("/causal-distance", response_model=CausalDistanceReport)
async def causal_distance(
    source: str = Query(..., description="Source node/decision ID"),
    target: str = Query(..., description="Target node/decision ID"),
    session: GraphSession = Depends(get_session),
):
    """FR-8 — Compute causal distance between two decisions via causal-edge-only traversal."""
    from ...context.causal_analyzer import CausalChainAnalyzer

    analyzer = CausalChainAnalyzer(session.graph)
    report = await asyncio.to_thread(analyzer.interpret_causal_distance, source, target)
    return CausalDistanceReport(**report)


@router.get("/{decision_id}/compliance", response_model=ComplianceResponse)
async def check_compliance(
    decision_id: str,
    session: GraphSession = Depends(get_session),
):
    node = await asyncio.to_thread(session.get_node, decision_id)
    if node is None:
        raise HTTPException(status_code=404, detail=f"Decision '{decision_id}' not found")

    edges, _ = await asyncio.to_thread(session.get_edges, skip=0, limit=999_999)
    violation_types = {"violates", "non_compliant", "breaches"}
    violations = [
        {
            "policy_id": edge.get("target"),
            "type": edge.get("type"),
            "metadata": edge.get("properties", {}),
        }
        for edge in edges
        if edge.get("source") == decision_id and edge.get("type") in violation_types
    ]

    return ComplianceResponse(
        decision_id=decision_id,
        compliant=len(violations) == 0,
        violations=violations,
    )
