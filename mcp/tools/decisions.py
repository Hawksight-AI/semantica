"""
Decision intelligence tools — record, query, precedents, causal chain, impact.
"""

from __future__ import annotations

import logging
import os

from mcp.schemas import (
    ANALYZE_DECISION_IMPACT,
    FIND_PRECEDENTS,
    GET_CAUSAL_CHAIN,
    QUERY_DECISIONS,
    RECORD_DECISION,
)
from mcp.session import get_graph, is_persistence_safe

log = logging.getLogger("semantica.mcp.tools.decisions")


def handle_record_decision(args: dict) -> dict:
    """Record a decision with full context into the knowledge graph."""
    required = ["category", "scenario", "reasoning", "outcome", "confidence"]
    missing = [f for f in required if f not in args]
    if missing:
        return {"error": f"Missing required fields: {', '.join(missing)}"}
    try:
        graph = get_graph()
        decision_id = graph.record_decision(
            category=str(args["category"]),
            scenario=str(args["scenario"]),
            reasoning=str(args["reasoning"]),
            outcome=str(args["outcome"]),
            confidence=float(args["confidence"]),
            entities=args.get("entities", []),
            decision_maker=args.get("decision_maker", "mcp_client"),
            valid_from=args.get("valid_from"),
            valid_until=args.get("valid_until"),
        )
        # Persist back to disk so the decision survives server restarts.
        # Skip when the initial load failed to avoid overwriting original data.
        kg_path = os.environ.get("SEMANTICA_KG_PATH", "").strip()
        if kg_path:
            if not is_persistence_safe():
                # Roll back the in-memory mutation so the client-visible state
                # matches the persisted state (neither is saved).
                if hasattr(graph, "_decisions") and decision_id in graph._decisions:
                    del graph._decisions[decision_id]
                    if hasattr(graph, "_decision_index"):
                        cat = args.get("category", "")
                        if cat in graph._decision_index:
                            graph._decision_index[cat].discard(decision_id)
                return {
                    "error": (
                        "Persistence blocked: the configured SEMANTICA_KG_PATH "
                        "could not be loaded at startup. Restart the server with "
                        "a readable graph file to re-enable persistence."
                    )
                }
            try:
                graph.save_to_file(kg_path)
            except Exception as save_exc:
                # Atomic write failed. Roll back the in-memory mutation so the
                # client-visible and persisted states remain consistent.
                if hasattr(graph, "_decisions") and decision_id in graph._decisions:
                    del graph._decisions[decision_id]
                    if hasattr(graph, "_decision_index"):
                        cat = args.get("category", "")
                        if cat in graph._decision_index:
                            graph._decision_index[cat].discard(decision_id)
                log.exception("save_to_file failed after record_decision; mutation rolled back")
                return {"error": f"Mutation rolled back: could not persist graph: {save_exc}"}
        return {
            "decision_id": decision_id,
            "status": "recorded",
            "category": args["category"],
            "outcome": args["outcome"],
        }
    except Exception as exc:
        log.exception("record_decision failed")
        return {"error": str(exc)}


def handle_query_decisions(args: dict) -> dict:
    """Query recorded decisions by natural language or structured filters."""
    query = args.get("query", "").strip()
    category = args.get("category", "").strip()
    outcome_filter = args.get("outcome", "").strip()
    limit = int(args.get("limit", 10))
    try:
        graph = get_graph()
        if query:
            results = graph.find_similar_decisions(query, max_results=limit)
            decisions = results if isinstance(results, list) else list(results)
        else:
            nodes = graph.find_nodes(node_type="decision")
            decisions = list(nodes)[:limit * 5]  # over-fetch for filtering
            if category:
                decisions = [d for d in decisions if d.get("category") == category]
            if outcome_filter:
                decisions = [d for d in decisions if d.get("outcome") == outcome_filter]
            decisions = decisions[:limit]
        return {"decisions": decisions, "count": len(decisions)}
    except Exception as exc:
        log.exception("query_decisions failed")
        return {"error": str(exc), "decisions": []}


def handle_find_precedents(args: dict) -> dict:
    """Find past decisions similar to a given scenario using hybrid similarity search."""
    scenario = args.get("scenario", "").strip()
    if not scenario:
        return {"error": "scenario is required", "precedents": []}
    max_results = int(args.get("max_results", 5))
    try:
        graph = get_graph()
        precedents = graph.find_similar_decisions(scenario, max_results=max_results)
        results = precedents if isinstance(precedents, list) else list(precedents)
        return {"precedents": results, "count": len(results)}
    except Exception as exc:
        log.exception("find_precedents failed")
        return {"error": str(exc), "precedents": []}


def handle_get_causal_chain(args: dict) -> dict:
    """Trace the upstream or downstream causal chain from a decision."""
    if not isinstance(args, dict):
        return {"error": "args must be a dictionary", "chain": []}
    decision_id = str(args.get("decision_id") or "").strip()
    if not decision_id:
        return {"error": "decision_id is required", "chain": []}
    direction = str(args.get("direction") or "downstream").strip()
    try:
        max_depth = int(args.get("max_depth", 5))
        if max_depth <= 0:
            max_depth = 5
        max_depth = min(max_depth, 100)
    except (ValueError, TypeError):
        max_depth = 5
    try:
        graph = get_graph()
        try:
            from semantica.context.causal_analyzer import CausalChainAnalyzer
            analyzer = CausalChainAnalyzer(graph_store=graph)
            chain = analyzer.get_causal_chain(
                decision_id, direction=direction, max_depth=max_depth
            )
        except (ImportError, AttributeError):
            if hasattr(graph, "get_causal_chain"):
                import inspect
                # Introspect the signature in its own try/except: only
                # failure to introspect (ValueError/TypeError from
                # inspect.signature itself, e.g. a C-extension callable)
                # should fall through to the trial-and-error cascade below.
                # A call made after a *successful* introspection must not be
                # wrapped in that cascade's except block — otherwise a
                # genuine bug inside get_causal_chain (raising an unrelated
                # TypeError) gets misread as "wrong signature" and the
                # backend is invoked a second time with identical arguments.
                try:
                    params = inspect.signature(graph.get_causal_chain).parameters
                except (ValueError, TypeError):
                    params = None

                if params is not None:
                    has_var_kwargs = any(
                        p.kind == inspect.Parameter.VAR_KEYWORD
                        for p in params.values()
                    )
                    if has_var_kwargs or (
                        "direction" in params and "max_depth" in params
                    ):
                        chain = graph.get_causal_chain(
                            decision_id,
                            direction=direction,
                            max_depth=max_depth,
                        )
                    elif "depth" in params:
                        chain = graph.get_causal_chain(
                            decision_id,
                            depth=max_depth,
                        )
                    else:
                        chain = graph.get_causal_chain(decision_id)
                else:
                    try:
                        chain = graph.get_causal_chain(
                            decision_id,
                            direction=direction,
                            max_depth=max_depth,
                        )
                    except TypeError as exc:
                        if "unexpected keyword argument" in str(
                            exc
                        ) or "positional" in str(exc):
                            try:
                                chain = graph.get_causal_chain(
                                    decision_id,
                                    depth=max_depth,
                                )
                            except TypeError as exc2:
                                if "unexpected keyword argument" in str(
                                    exc2
                                ) or "positional" in str(exc2):
                                    chain = graph.get_causal_chain(decision_id)
                                else:
                                    raise
                        else:
                            raise
            else:
                return {
                    "error": (
                        "Causal chain analysis is not supported on this graph"
                        " backend"
                    ),
                    "chain": [],
                }
        result = chain if isinstance(chain, list) else list(chain)
        return {"chain": result, "count": len(result), "direction": direction}
    except Exception as exc:
        log.exception("get_causal_chain failed")
        return {"error": str(exc), "chain": []}


def handle_analyze_decision_impact(args: dict) -> dict:
    """Analyse the downstream impact of a decision on the graph."""
    decision_id = args.get("decision_id", "").strip()
    if not decision_id:
        return {"error": "decision_id is required"}
    try:
        graph = get_graph()
        if hasattr(graph, "analyze_decision_impact"):
            impact = graph.analyze_decision_impact(decision_id)
        elif hasattr(graph, "analyze_decision_influence"):
            impact = graph.analyze_decision_influence(decision_id)
        else:
            impact = {"message": "impact analysis not available on this graph instance"}
        return {"decision_id": decision_id, "impact": impact}
    except Exception as exc:
        log.exception("analyze_decision_impact failed")
        return {"error": str(exc)}


DECISION_TOOLS = [
    {
        "name": "record_decision",
        "description": "Record a decision with full context, causal links, and metadata into the Semantica knowledge graph.",
        "inputSchema": RECORD_DECISION,
        "_handler": handle_record_decision,
    },
    {
        "name": "query_decisions",
        "description": "Query recorded decisions by natural language, category, or outcome filter.",
        "inputSchema": QUERY_DECISIONS,
        "_handler": handle_query_decisions,
    },
    {
        "name": "find_precedents",
        "description": "Find past decisions similar to a given scenario using hybrid similarity search.",
        "inputSchema": FIND_PRECEDENTS,
        "_handler": handle_find_precedents,
    },
    {
        "name": "get_causal_chain",
        "description": "Trace the causal chain upstream or downstream from a recorded decision.",
        "inputSchema": GET_CAUSAL_CHAIN,
        "_handler": handle_get_causal_chain,
    },
    {
        "name": "analyze_decision_impact",
        "description": "Analyse the downstream impact and influence of a decision across the knowledge graph.",
        "inputSchema": ANALYZE_DECISION_IMPACT,
        "_handler": handle_analyze_decision_impact,
    },
]
