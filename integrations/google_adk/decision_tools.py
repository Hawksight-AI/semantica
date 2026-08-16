from __future__ import annotations

from datetime import datetime
from typing import Any, Dict, List, Optional
import threading
import uuid


try:
    from google.adk.tools import FunctionTool

    ADK_AVAILABLE = True
except ImportError:
    FunctionTool = None
    ADK_AVAILABLE = False
_default_graph: Optional[Any] = None
_default_graph_lock = threading.Lock()


_graph_locks_guard = threading.Lock()
_graph_locks: Dict[int, threading.RLock] = {}


def _graph_lock(graph: Any) -> threading.RLock:
    """return a lock associated with a graph instance."""
    key = id(graph)

    with _graph_locks_guard:
        lock = _graph_locks.get(key)

        if lock is None:
            lock = threading.RLock()
            _graph_locks[key] = lock

        return lock


def _get_default_graph() -> Any:
    """Return the process-local default ContextGraph."""
    global _default_graph

    if _default_graph is None:
        with _default_graph_lock:
            if _default_graph is None:
                from semantica.context import ContextGraph

                _default_graph = ContextGraph()

    return _default_graph


def _get_decision_models() -> Any:
    """Import Semantica decision models lazily."""
    from semantica.context.decision_models import Decision

    return Decision


def _get_decision_recorder(graph: Any) -> Any:
    """Create a DecisionRecorder backed by the supplied graph."""
    from semantica.context import DecisionRecorder

    return DecisionRecorder(graph_store=graph)


def _decision_to_dict(decision: Any) -> dict:
    """Convert a Semantica Decision model into a serializable dictionary."""
    if hasattr(decision, "model_dump"):
        return decision.model_dump()

    if hasattr(decision, "dict"):
        return decision.dict()

    if isinstance(decision, dict):
        return decision

    return {
        key: value
        for key, value in vars(decision).items()
        if not key.startswith("_")
    }


def record_decision(
    category: str,
    scenario: str,
    reasoning: str,
    outcome: str,
    confidence: float = 1.0,
    decision_maker: str = "agent",
    entities: Optional[List[str]] = None,
    source_documents: Optional[List[str]] = None,
) -> dict:
    """
    Record a decision using Semantica's DecisionRecorder.

    Args:
        category: Decision category such as "research", "planning", or
            "approval".
        scenario: Situation in which the decision was made.
        reasoning: Explanation for the decision.
        outcome: Result or selected action.
        confidence: Confidence score between 0 and 1.
        decision_maker: Agent, user, or system responsible for the decision.
        entities: Optional entity IDs related to the decision.
        source_documents: Optional source document IDs supporting the decision.

    Returns:
        Dictionary containing the recorded decision ID and decision metadata.
    """
    return _record_decision(
        category=category,
        scenario=scenario,
        reasoning=reasoning,
        outcome=outcome,
        confidence=confidence,
        decision_maker=decision_maker,
        entities=entities or [],
        source_documents=source_documents or [],
        graph=_get_default_graph(),
    )


def _record_decision(
    category: str,
    scenario: str,
    reasoning: str,
    outcome: str,
    confidence: float,
    decision_maker: str,
    entities: List[str],
    source_documents: List[str],
    graph: Any,
) -> dict:
    """Internal implementation of decision recording."""
    try:
        confidence = max(0.0, min(1.0, float(confidence)))

        Decision = _get_decision_models()

        decision = Decision(
            decision_id=str(uuid.uuid4()),
            category=category,
            scenario=scenario,
            reasoning=reasoning,
            outcome=outcome,
            confidence=confidence,
            decision_maker=decision_maker,
            timestamp=datetime.now(),
        )

        recorder = _get_decision_recorder(graph)

        with _graph_lock(graph):
            decision_id = recorder.record_decision(
                decision=decision,
                entities=entities,
                source_documents=source_documents,
            )

        return {
            "decision_id": decision_id,
            "category": category,
            "scenario": scenario,
            "outcome": outcome,
            "confidence": confidence,
            "decision_maker": decision_maker,
        }

    except Exception as exc:
        return {
            "decision_id": "",
            "error": str(exc),
        }


def query_decisions(query: str) -> dict:
    """
    Query previously recorded decisions by keyword.
    """
    return _query_decisions(query, _get_default_graph())

def _query_decisions(query: str, graph: Any) -> dict:
    """Internal decision query implementation."""
    if not isinstance(query, str):
        return {
            "query": query,
            "decisions": [],
            "count": 0,
            "error": "query must be a string",
        }

    query = query.strip()

    if not query:
        return {
            "query": query,
            "decisions": [],
            "count": 0,
        }

    try:
        query_lower = query.lower()
        decisions = []
        seen = set()

        for node in graph.find_nodes() or []:
            if not isinstance(node, dict):
                continue

            node_type = node.get("type")

            if str(node_type).lower() != "decision":
                continue

            node_id = str(node.get("id") or "")

            if not node_id or node_id in seen:
                continue

            metadata = node.get("metadata") or {}

            category = metadata.get("category", "")
            scenario = metadata.get("scenario", "")
            reasoning = metadata.get("reasoning", "")
            outcome = metadata.get("outcome", "")
            decision_maker = metadata.get("decision_maker", "")

            searchable = " ".join(
                str(value or "")
                for value in (
                    node_id,
                    category,
                    scenario,
                    reasoning,
                    outcome,
                    decision_maker,
                )
            ).lower()

            if query_lower not in searchable:
                continue

            seen.add(node_id)

            decisions.append(
                {
                    "decision_id": node_id,
                    "category": str(category or ""),
                    "scenario": str(scenario or ""),
                    "reasoning": str(reasoning or "")[:1000],
                    "outcome": str(outcome or ""),
                    "decision_maker": str(
                        decision_maker or ""
                    ),
                }
            )

        return {
            "query": query,
            "decisions": decisions,
            "count": len(decisions),
        }

    except Exception as exc:
        return {
            "query": query,
            "decisions": [],
            "count": 0,
            "error": str(exc),
        }

def semantica_decision_tools(
    graph: Optional[Any] = None,
) -> List[Any]:
    """
    Return Google ADK FunctionTools bound to a shared ContextGraph.

    Args:
        graph:
            Optional ContextGraph shared by the ADK agent and other
            Semantica tools.

    Returns:
        ADK FunctionTools for recording and querying decisions.

    Raises:
        ImportError:
            If google-adk is not installed.
    """
    if not ADK_AVAILABLE or FunctionTool is None:
        raise ImportError(
            "Google ADK is required for semantica_decision_tools(). "
            "Install it with: pip install semantica[google-adk]"
        )

    shared_graph = graph if graph is not None else _get_default_graph()

    def record_shared_decision(
        category: str,
        scenario: str,
        reasoning: str,
        outcome: str,
        confidence: float = 1.0,
        decision_maker: str = "agent",
        entities: Optional[List[str]] = None,
        source_documents: Optional[List[str]] = None,
    ) -> dict:
        """Record a decision in the shared Semantica knowledge graph."""
        return _record_decision(
            category=category,
            scenario=scenario,
            reasoning=reasoning,
            outcome=outcome,
            confidence=confidence,
            decision_maker=decision_maker,
            entities=entities or [],
            source_documents=source_documents or [],
            graph=shared_graph,
        )

    def query_shared_decisions(query: str) -> dict:
        """Query decisions stored in the shared Semantica knowledge graph."""
        return _query_decisions(query, shared_graph)

    return [
        FunctionTool(record_shared_decision),
        FunctionTool(query_shared_decisions),
    ]


__all__ = [
    "ADK_AVAILABLE",
    "record_decision",
    "query_decisions",
    "semantica_decision_tools",
]