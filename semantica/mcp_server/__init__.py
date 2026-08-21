"""
Semantica MCP Server

Exposes Semantica's knowledge graph, decision intelligence, semantic extraction,
reasoning, and analytics capabilities as an MCP (Model Context Protocol) server
over stdio — compatible with Claude Desktop, Windsurf, Cline, Continue, VS Code,
Roo Code, and any other MCP-aware tool.

Usage
-----
Configure in your tool's MCP settings:

    Claude Desktop / Windsurf / Cline / Continue / VS Code:
    {
        "mcpServers": {
            "semantica": {
                "command": "semantica-mcp"
            }
        }
    }

Or using python -m:
    {
        "mcpServers": {
            "semantica": {
                "command": "python",
                "args": ["-m", "semantica.mcp_server"]
            }
        }
    }

Run directly for testing:
    semantica-mcp
    # or
    python -m semantica.mcp_server

Environment variables:
    SEMANTICA_KG_PATH   — path to a persisted graph to load on start (optional)
    SEMANTICA_LOG_LEVEL — log level: DEBUG, INFO, WARNING (default: WARNING)
"""

from __future__ import annotations

import json
import logging
import os
import sys
import threading
import urllib.request
from typing import Any, Optional

# `semantica.__version__` is the authoritative package version — it is kept in
# sync with pyproject.toml's static `version` field by the release process and
# is always present whenever this submodule is importable.  Using it directly
# is simpler and more reliable than `importlib.metadata.version("semantica")`,
# which reads dist-info written at install time and can lag the source in
# editable installs (egg-info / dist-info is not regenerated on every version
# bump, so it can reflect a stale value).
from semantica import __version__ as _SEMANTICA_VERSION

# ── logging ────────────────────────────────────────────────────────────────
_log_level = getattr(logging, os.environ.get("SEMANTICA_LOG_LEVEL", "WARNING").upper(), logging.WARNING)
logging.basicConfig(stream=sys.stderr, level=_log_level,
                    format="%(asctime)s [semantica-mcp] %(levelname)s %(message)s")
log = logging.getLogger("semantica.mcp_server")

# ── lazy graph session ──────────────────────────────────────────────────────
_graph: Any = None

# Incremental mutations collected from the graph's mutation callback during a
# single tool call, flushed (persist + push to Explorer) at the end of the
# call by _flush().  The callback runs while ContextGraph holds its own lock,
# so it must only append to this list — never do I/O or HTTP inside it.
_pending_batch: list = []
_pending_lock = threading.Lock()


def _on_graph_mutation(event_type: str, entity_id: str, payload: dict) -> None:
    """Collect ADD_NODE / ADD_EDGE / UPDATE_NODE events for the active tool call."""
    with _pending_lock:
        _pending_batch.append(
            {"event_type": event_type, "entity_id": entity_id, "payload": payload}
        )


def _explorer_sync_url() -> Optional[str]:
    base = os.environ.get("SEMANTICA_EXPLORER_URL") or ""
    return (base.rstrip("/") + "/api/graph/sync") if base else None


def _flush(extra_deleted: Optional[list] = None) -> None:
    """Persist the graph to SEMANTICA_KG_PATH and push pending mutations to the Explorer.

    Called at the end of every write tool.  Never raises: persistence and
    Explorer-sync failures are logged and non-fatal so a transient Explorer
    outage cannot break an MCP write.
    """
    global _pending_batch
    with _pending_lock:
        batch = _pending_batch
        _pending_batch = []

    graph = _get_graph()

    # 1) Persist locally (atomic write to the shared JSON volume).
    kg_path = os.environ.get("SEMANTICA_KG_PATH")
    if kg_path:
        try:
            graph.save_to_file(kg_path)
        except Exception as exc:  # noqa: BLE001
            log.warning("persist graph to %s failed: %s", kg_path, exc)

    # 2) Push the incremental mutation batch to the Explorer so the platform
    #    graph and the frontend reflect MCP writes immediately.
    sync_url = _explorer_sync_url()
    if not sync_url:
        return
    nodes: list = []
    edges: list = []
    for item in batch:
        event_type = str(item.get("event_type", "")).upper()
        payload = item.get("payload") or {}
        if event_type in ("ADD_NODE", "UPDATE_NODE") and payload.get("id"):
            nodes.append(payload)
        elif event_type in ("ADD_EDGE", "UPDATE_EDGE") and payload.get("id"):
            edges.append(payload)
    deleted = [str(x) for x in (extra_deleted or []) if x]
    if not (nodes or edges or deleted):
        return
    body = {"nodes": nodes, "edges": edges, "deleted": deleted}
    try:
        data = json.dumps(body).encode("utf-8")
        req = urllib.request.Request(
            sync_url,
            data=data,
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        with urllib.request.urlopen(req, timeout=10) as resp:
            resp.read()
        log.info("pushed %d nodes, %d edges, %d deletes to explorer",
                 len(nodes), len(edges), len(deleted))
    except Exception as exc:  # noqa: BLE001
        log.warning("push %d mutations to explorer failed: %s",
                    len(nodes) + len(edges) + len(deleted), exc)


def _get_graph():
    global _graph
    if _graph is None:
        from semantica.context import ContextGraph
        _graph = ContextGraph(advanced_analytics=True)
        kg_path = os.environ.get("SEMANTICA_KG_PATH")
        if kg_path and os.path.exists(kg_path):
            try:
                # Note: must be load_from_file — ContextGraph has no `.load()`.
                _graph.load_from_file(kg_path)
                log.info("Loaded graph from %s", kg_path)
            except Exception as exc:
                log.warning("Could not load graph from %s: %s", kg_path, exc)
        # Collect mutations made by write tools and flush them at the end of
        # the tool call (persist + push to Explorer).
        _graph.mutation_callback = _on_graph_mutation
    return _graph


# ══════════════════════════════════════════════════════════════════════════════
# Tool implementations
# ══════════════════════════════════════════════════════════════════════════════

def _tool_extract_entities(args: dict) -> dict:
    """Extract named entities from text."""
    text = args.get("text", "")
    if not text:
        return {"error": "text is required"}
    from semantica.semantic_extract import NamedEntityRecognizer
    entities = NamedEntityRecognizer().extract_entities(text)
    return {
        "entities": [
            {"label": getattr(e, "label", str(e)),
             "type": getattr(e, "type", None),
             "start": getattr(e, "start", None),
             "end": getattr(e, "end", None)}
            for e in (entities or [])
        ]
    }


def _tool_extract_relations(args: dict) -> dict:
    """Extract relations and triplets from text.

    The underlying ``RelationExtractor.extract_relations(text, entities)``
    requires ``entities`` as a positional argument (no default).  To keep the
    MCP tool signature ``text``-only (recommendation A), we run NER internally
    first and feed the detected entities.  If NER returns nothing (e.g. weak
    Chinese recall) or fails, we fall back to an empty list — ``extract_relations``
    then safely returns ``[]`` instead of crashing.
    """
    text = args.get("text", "")
    if not text:
        return {"error": "text is required"}
    from semantica.semantic_extract import (
        NamedEntityRecognizer,
        RelationExtractor,
        TripletExtractor,
    )

    # Run NER internally; never let an NER failure abort relation extraction.
    entities: list = []
    try:
        entities = NamedEntityRecognizer().extract_entities(text) or []
    except Exception as exc:  # noqa: BLE001
        log.warning("NER failed during extract_relations; continuing with no entities: %s", exc)
        entities = []

    relations = RelationExtractor().extract_relations(text, entities)
    triplets = TripletExtractor().extract_triplets(text, entities=entities)
    return {
        "relations": [
            {"source": getattr(r, "source", None),
             "type": getattr(r, "type", None),
             "target": getattr(r, "target", None)}
            for r in (relations or [])
        ],
        "triplets": [
            {"subject": getattr(t, "subject", None),
             "predicate": getattr(t, "predicate", None),
             "object": getattr(t, "object", None)}
            for t in (triplets or [])
        ],
    }


def _to_id_list(value) -> List[str]:
    """Coerce an MCP argument into a list of non-empty decision-ID strings.

    Accepts None, a single string, or a list/tuple. Anything else -> [].
    """
    if value is None:
        return []
    if isinstance(value, str):
        return [value] if value.strip() else []
    if isinstance(value, (list, tuple)):
        return [str(v).strip() for v in value if v and str(v).strip()]
    return []


def _tool_record_decision(args: dict) -> dict:
    """Record a decision with full context into the graph."""
    required = ["category", "scenario", "reasoning", "outcome", "confidence"]
    for field in required:
        if field not in args:
            return {"error": f"missing required field: {field}"}
    graph = _get_graph()

    # `entities` is an optional list of entity IDs to link to the decision.
    entities = _to_id_list(args.get("entities"))

    # `causes` / `caused_by` are optional decision-ID lists declaring causal
    # links (see get_causal_chain). Both are backward-compatible optional args.
    causes = _to_id_list(args.get("causes"))
    caused_by = _to_id_list(args.get("caused_by"))

    decision_id = graph.record_decision(
        category=args["category"],
        scenario=args["scenario"],
        reasoning=args["reasoning"],
        outcome=args["outcome"],
        confidence=float(args["confidence"]),
        entities=entities,
        decision_maker=args.get("decision_maker", "mcp_client"),
        causes=causes,
        caused_by=caused_by,
        valid_from=args.get("valid_from"),
        valid_until=args.get("valid_until"),
    )
    _flush()
    return {"decision_id": decision_id, "status": "recorded",
            "entities": entities, "causes": causes, "caused_by": caused_by}


def _tool_query_decisions(args: dict) -> dict:
    """Query decisions by natural language or structured filters."""
    query = args.get("query", "")
    category = args.get("category")
    limit = int(args.get("limit", 10))
    graph = _get_graph()
    try:
        if query:
            raw = graph.find_similar_decisions(query, max_results=limit)
            decisions = [_normalize_decision(d) for d in raw] if raw else []
        elif category:
            nodes = graph.find_nodes(node_type="decision")
            # `record_decision` stores `category` as a node *property* (via
            # add_node(category=...)), so `find_nodes` surfaces it under
            # `metadata.category`, NOT as a top-level key. Read both paths so
            # the filter actually matches stored decisions.
            def _node_category(n: dict) -> Optional[str]:
                cat = n.get("category")
                if cat is None:
                    cat = (n.get("metadata") or {}).get("category")
                return cat
            decisions = [_normalize_decision(n) for n in nodes if _node_category(n) == category][:limit]
        else:
            decisions = [_normalize_decision(n) for n in graph.find_nodes(node_type="decision")][:limit]
        return {"decisions": decisions}
    except Exception as exc:
        return {"error": str(exc), "decisions": []}


def _tool_find_precedents(args: dict) -> dict:
    """Find past decisions similar to a given scenario."""
    scenario = args.get("scenario", "")
    if not scenario:
        return {"error": "scenario is required"}
    max_results = int(args.get("max_results", 5))
    graph = _get_graph()
    try:
        precedents = graph.find_similar_decisions(scenario, max_results=max_results)
        return {"precedents": precedents if isinstance(precedents, list) else list(precedents)}
    except Exception as exc:
        return {"error": str(exc), "precedents": []}


def _normalize_decision(d) -> dict:
    """Normalize a decision node (dict from find_nodes) or a Decision object into
    a consistent, JSON-safe dict that exposes ``decision_id`` and ``category`` at
    the top level.

    ``find_nodes(node_type="decision")`` otherwise hides ``category`` under
    ``metadata`` and uses ``id`` rather than ``decision_id`` — which made the
    queried decisions unusable (``decision_id=None``). ``id`` is retained for
    backward compatibility with existing consumers/tests.
    """
    if isinstance(d, dict):
        meta = d.get("metadata") or {}
        base_id = d.get("id") or d.get("decision_id")
        return {
            "decision_id": base_id,
            "id": base_id,
            "category": d.get("category") or meta.get("category"),
            "scenario": d.get("scenario") or meta.get("scenario"),
            "reasoning": d.get("reasoning") or meta.get("reasoning"),
            "outcome": d.get("outcome") or meta.get("outcome"),
            "confidence": d.get("confidence", meta.get("confidence")),
            "decision_maker": d.get("decision_maker") or meta.get("decision_maker"),
            "timestamp": d.get("timestamp") or meta.get("timestamp"),
        }
    # Decision object returned by find_similar_decisions
    return {
        "decision_id": getattr(d, "decision_id", None),
        "id": getattr(d, "decision_id", None),
        "category": getattr(d, "category", None),
        "scenario": getattr(d, "scenario", None),
        "reasoning": getattr(d, "reasoning", None),
        "outcome": getattr(d, "outcome", None),
        "confidence": getattr(d, "confidence", None),
        "decision_maker": getattr(d, "decision_maker", None),
        "timestamp": getattr(d, "timestamp", None),
    }


def _decision_to_chain_node(d) -> dict:
    """Normalize a Decision object (or decision dict) to a JSON-safe chain node.

    Returns only the fields the causal-chain consumer needs: decision_id,
    outcome, and a short summary (the scenario description).
    """
    if isinstance(d, dict):
        decision_id = d.get("decision_id") or d.get("id")
        outcome = d.get("outcome", "")
        summary = d.get("scenario") or d.get("summary") or ""
    else:
        decision_id = getattr(d, "decision_id", None) or getattr(d, "id", None)
        outcome = getattr(d, "outcome", "")
        summary = getattr(d, "scenario", None) or ""
    return {"decision_id": decision_id, "outcome": outcome, "summary": summary}


def _tool_get_causal_chain(args: dict) -> dict:
    """Get the causal chain for a decision.

    Traverses causal links declared via record_decision(causes/caused_by) and
    any CAUSED/INFLUENCED/PRECEDENT_FOR edges in the knowledge graph.
    Contract for an unknown decision_id: return an empty chain (no exception),
    because a decision with no causal neighbours simply has an empty chain.
    """
    decision_id = args.get("decision_id", "")
    if not decision_id:
        return {"error": "decision_id is required"}
    direction = args.get("direction", "downstream")
    max_depth = int(args.get("max_depth", 5))
    graph = _get_graph()
    try:
        from semantica.context.causal_analyzer import CausalChainAnalyzer
        analyzer = CausalChainAnalyzer(graph_store=graph)
        chain = analyzer.get_causal_chain(decision_id, direction=direction, max_depth=max_depth)
        nodes = [_decision_to_chain_node(d) for d in (chain or [])]
        return {"chain": nodes}
    except Exception as exc:
        return {"error": str(exc), "chain": []}


def _tool_add_entity(args: dict) -> dict:
    """Add a node/entity to the knowledge graph."""
    node_id = args.get("id", "")
    label = args.get("label", node_id)
    node_type = args.get("type", "Entity")
    if not node_id:
        return {"error": "id is required"}
    graph = _get_graph()
    graph.add_node(node_id=node_id, label=label, node_type=node_type,
                   metadata=args.get("metadata", {}))
    _flush()
    return {"status": "added", "id": node_id}


def _tool_add_relationship(args: dict) -> dict:
    """Add a relationship (edge) between two entities."""
    source = args.get("source", "")
    target = args.get("target", "")
    rel_type = args.get("type", "RELATED_TO")
    if not source or not target:
        return {"error": "source and target are required"}
    graph = _get_graph()
    graph.add_edge(source_id=source, target_id=target, edge_type=rel_type,
                   metadata=args.get("metadata", {}))
    _flush()
    return {"status": "added", "source": source, "target": target, "type": rel_type}


def _tool_delete_entity(args: dict) -> dict:
    """Delete a node/entity (and optionally its incident edges) from the graph."""
    node_id = args.get("id", "")
    if not node_id:
        return {"error": "id is required"}
    cascade = args.get("cascade_edges", True)
    if isinstance(cascade, str):
        cascade = cascade.strip().lower() in ("1", "true", "yes", "y", "on")
    graph = _get_graph()
    try:
        result = graph.delete_node(node_id=node_id, cascade_edges=bool(cascade))
        if result.get("node_found"):
            _flush(extra_deleted=[node_id])
        else:
            result["error"] = f"node not found: {node_id}"
        return result
    except Exception as exc:  # noqa: BLE001
        return {"error": str(exc), "deleted": False, "node_found": False, "edges_removed": 0}


def _tool_run_reasoning(args: dict) -> dict:
    """Run forward-chaining reasoning rules over a set of facts."""
    facts = args.get("facts", [])
    rules = args.get("rules", [])
    if not facts or not rules:
        return {"error": "facts and rules are required"}
    from semantica.reasoning import Reasoner
    reasoner = Reasoner()
    for rule in rules:
        reasoner.add_rule(rule)
    derived = reasoner.infer_facts(facts)
    return {"derived_facts": derived if isinstance(derived, list) else list(derived)}


def _tool_get_graph_analytics(args: dict) -> dict:
    """Compute graph analytics: centrality, community detection, metrics."""
    graph = _get_graph()
    try:
        from semantica.kg import CentralityCalculator, CommunityDetector
        centrality = CentralityCalculator().calculate_pagerank(graph)
        communities = CommunityDetector().detect_communities(graph)
        node_count = len(list(graph.find_nodes()))
        edge_count = getattr(graph, "edge_count", lambda: 0)()
        return {
            "node_count": node_count,
            "edge_count": edge_count,
            "top_nodes_by_pagerank": sorted(
                centrality.items() if hasattr(centrality, "items") else [],
                key=lambda x: x[1], reverse=True
            )[:10],
            "community_count": len(communities) if isinstance(communities, (list, dict)) else 0,
        }
    except Exception as exc:
        return {"error": str(exc)}


def _tool_export_graph(args: dict) -> dict:
    """Export the current knowledge graph to a serialised format."""
    fmt = args.get("format", "json-ld")
    graph = _get_graph()
    try:
        from semantica.export import RDFExporter
        if fmt in ("turtle", "ttl", "nt", "xml", "json-ld"):
            result = RDFExporter().export_to_rdf(graph, format=fmt)
        else:
            # JSON — build the payload directly from the graph (the upstream
            # JSONExporter.export now requires a file_path argument).
            nodes = list(graph.find_nodes())
            edges: list = []
            if hasattr(graph, "find_edges"):
                try:
                    edges = list(graph.find_edges())
                except Exception as exc:  # noqa: BLE001
                    log.warning("Failed to collect edges during JSON export: %s", exc)
            result = {"nodes": nodes, "edges": edges}
        return {"format": fmt, "data": result}
    except Exception as exc:
        return {"error": str(exc)}


def _tool_get_graph_summary(args: dict) -> dict:
    """Return a high-level summary of the current graph."""
    graph = _get_graph()
    try:
        node_count = len(list(graph.find_nodes()))
        decisions = graph.find_nodes(node_type="decision")
        return {
            "node_count": node_count,
            "decision_count": len(list(decisions)),
            "graph_ready": True,
        }
    except Exception as exc:
        return {"error": str(exc), "graph_ready": False}


# ══════════════════════════════════════════════════════════════════════════════
# MCP protocol tables
# ══════════════════════════════════════════════════════════════════════════════

TOOLS = [
    {
        "name": "extract_entities",
        "description": "Extract named entities (people, places, organisations, concepts) from text using Semantica NER.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "text": {"type": "string", "description": "Input text to extract entities from"}
            },
            "required": ["text"],
        },
        "_handler": _tool_extract_entities,
    },
    {
        "name": "extract_relations",
        "description": "Extract relations and (subject, predicate, object) triplets from text.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "text": {"type": "string", "description": "Input text to extract relations from"}
            },
            "required": ["text"],
        },
        "_handler": _tool_extract_relations,
    },
    {
        "name": "record_decision",
        "description": "Record a decision into the Semantica knowledge graph with full context, causal links, and metadata.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "category":      {"type": "string", "description": "Decision category, e.g. 'loan_approval'"},
                "scenario":      {"type": "string", "description": "Natural-language situation description"},
                "reasoning":     {"type": "string", "description": "Why this decision was made"},
                "outcome":       {"type": "string", "description": "Decision outcome, e.g. 'approved'"},
                "confidence":    {"type": "number", "description": "Confidence score 0–1"},
                "entities":      {"type": "array", "items": {"type": "string"}, "description": "Entity IDs to link to this decision (optional)"},
                "causes":        {"type": "array", "items": {"type": "string"}, "description": "Decision IDs this decision caused (optional causal link)"},
                "caused_by":     {"type": "array", "items": {"type": "string"}, "description": "Decision IDs that caused this decision (optional causal link)"},
                "decision_maker":{"type": "string", "description": "Who/what made the decision"},
                "valid_from":    {"type": "string", "description": "ISO date validity start (optional)"},
                "valid_until":   {"type": "string", "description": "ISO date validity end (optional)"},
            },
            "required": ["category", "scenario", "reasoning", "outcome", "confidence"],
        },
        "_handler": _tool_record_decision,
    },
    {
        "name": "query_decisions",
        "description": "Query recorded decisions by natural language, category, or get all recent decisions.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "query":    {"type": "string", "description": "Natural language query (optional)"},
                "category": {"type": "string", "description": "Filter by category (optional)"},
                "limit":    {"type": "integer", "description": "Max results (default 10)"},
            },
        },
        "_handler": _tool_query_decisions,
    },
    {
        "name": "find_precedents",
        "description": "Find past decisions similar to a given scenario using hybrid similarity search.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "scenario":    {"type": "string", "description": "Scenario description to find precedents for"},
                "max_results": {"type": "integer", "description": "Max results (default 5)"},
            },
            "required": ["scenario"],
        },
        "_handler": _tool_find_precedents,
    },
    {
        "name": "get_causal_chain",
        "description": "Trace the causal chain upstream or downstream from a decision, following causal links declared via record_decision(causes/caused_by) and any CAUSED/INFLUENCED/PRECEDENT_FOR knowledge-graph edges.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "decision_id": {"type": "string", "description": "Decision ID to trace"},
                "direction":   {"type": "string", "enum": ["upstream", "downstream"], "description": "Trace direction"},
                "max_depth":   {"type": "integer", "description": "Max chain depth (default 5)"},
            },
            "required": ["decision_id"],
        },
        "_handler": _tool_get_causal_chain,
    },
    {
        "name": "add_entity",
        "description": "Add a node/entity to the Semantica knowledge graph.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "id":       {"type": "string", "description": "Unique node ID"},
                "label":    {"type": "string", "description": "Human-readable label"},
                "type":     {"type": "string", "description": "Node type, e.g. 'Person', 'Organisation'"},
                "metadata": {"type": "object", "description": "Additional properties"},
            },
            "required": ["id"],
        },
        "_handler": _tool_add_entity,
    },
    {
        "name": "add_relationship",
        "description": "Add a directed relationship (edge) between two entities in the knowledge graph.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "source":   {"type": "string", "description": "Source node ID"},
                "target":   {"type": "string", "description": "Target node ID"},
                "type":     {"type": "string", "description": "Relationship type, e.g. 'WORKS_AT'"},
                "metadata": {"type": "object", "description": "Additional edge properties"},
            },
            "required": ["source", "target"],
        },
        "_handler": _tool_add_relationship,
    },
    {
        "name": "delete_entity",
        "description": "Delete a node/entity from the Semantica knowledge graph. By default also removes all edges incident to the node (cascade).",
        "inputSchema": {
            "type": "object",
            "properties": {
                "id":             {"type": "string", "description": "Unique ID of the node to delete"},
                "cascade_edges":  {"type": "boolean", "description": "Also delete edges connected to this node (default: true)"},
            },
            "required": ["id"],
        },
        "_handler": _tool_delete_entity,
    },
    {
        "name": "run_reasoning",
        "description": "Run forward-chaining IF/THEN rules over a set of facts to derive new facts.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "facts": {
                    "type": "array", "items": {"type": "string"},
                    "description": "List of fact strings, e.g. ['Person(John)', 'Employee(John)']",
                },
                "rules": {
                    "type": "array", "items": {"type": "string"},
                    "description": "IF/THEN rule strings, e.g. ['IF Employee(?x) THEN WorkerBee(?x)']",
                },
            },
            "required": ["facts", "rules"],
        },
        "_handler": _tool_run_reasoning,
    },
    {
        "name": "get_graph_analytics",
        "description": "Compute PageRank centrality and community detection over the knowledge graph.",
        "inputSchema": {"type": "object", "properties": {}},
        "_handler": _tool_get_graph_analytics,
    },
    {
        "name": "export_graph",
        "description": "Export the current knowledge graph. Formats: turtle, ttl, nt, xml, json-ld, json.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "format": {
                    "type": "string",
                    "enum": ["turtle", "ttl", "nt", "xml", "json-ld", "json"],
                    "description": "Export format (default: json-ld)",
                }
            },
        },
        "_handler": _tool_export_graph,
    },
    {
        "name": "get_graph_summary",
        "description": "Return a high-level summary of the current knowledge graph: node count, decision count, status.",
        "inputSchema": {"type": "object", "properties": {}},
        "_handler": _tool_get_graph_summary,
    },
]

RESOURCES = [
    {
        "uri": "semantica://graph/summary",
        "name": "Graph Summary",
        "description": "High-level statistics about the current knowledge graph",
        "mimeType": "application/json",
    },
    {
        "uri": "semantica://decisions/list",
        "name": "Decisions",
        "description": "List of all recorded decisions in the graph",
        "mimeType": "application/json",
    },
    {
        "uri": "semantica://schema/info",
        "name": "Schema Info",
        "description": "Semantica server info and available capabilities",
        "mimeType": "application/json",
    },
]


def _read_resource(uri: str) -> dict:
    if uri == "semantica://graph/summary":
        return _tool_get_graph_summary({})
    if uri == "semantica://decisions/list":
        return _tool_query_decisions({"limit": 50})
    if uri == "semantica://schema/info":
        return {
            "name": "Semantica",
            "version": _SEMANTICA_VERSION,
            "tools": [t["name"] for t in TOOLS],
            "resources": [r["uri"] for r in RESOURCES],
        }
    return {"error": f"Unknown resource URI: {uri}"}


# ══════════════════════════════════════════════════════════════════════════════
# JSON-RPC / MCP protocol handler
# ══════════════════════════════════════════════════════════════════════════════

SERVER_INFO = {
    "name": "semantica",
    "version": _SEMANTICA_VERSION,
}

CAPABILITIES = {
    "tools":     {"listChanged": False},
    "resources": {"listChanged": False, "subscribe": False},
}


def _handle(req: dict) -> dict | None:
    """Dispatch a single JSON-RPC request; return None for notifications."""
    method = req.get("method", "")
    params = req.get("params") or {}
    req_id = req.get("id")

    def ok(result):
        return {"jsonrpc": "2.0", "id": req_id, "result": result}

    def err(code, message):
        return {"jsonrpc": "2.0", "id": req_id, "error": {"code": code, "message": message}}

    # Notifications (no id) — acknowledge silently
    if req_id is None and method.startswith("notifications/"):
        return None

    if method == "initialize":
        return ok({
            "protocolVersion": "2024-11-05",
            "capabilities": CAPABILITIES,
            "serverInfo": SERVER_INFO,
        })

    if method == "notifications/initialized":
        return None

    if method == "ping":
        return ok({})

    if method == "tools/list":
        tools_out = [
            {"name": t["name"], "description": t["description"], "inputSchema": t["inputSchema"]}
            for t in TOOLS
        ]
        return ok({"tools": tools_out})

    if method == "tools/call":
        name = params.get("name", "")
        arguments = params.get("arguments") or {}
        handler = next((t["_handler"] for t in TOOLS if t["name"] == name), None)
        if handler is None:
            return err(-32601, f"Unknown tool: {name}")
        try:
            result = handler(arguments)
            text = json.dumps(result, ensure_ascii=False, indent=2)
            return ok({"content": [{"type": "text", "text": text}]})
        except Exception as exc:
            log.exception("Tool %s raised", name)
            return err(-32603, str(exc))

    if method == "resources/list":
        return ok({"resources": RESOURCES})

    if method == "resources/read":
        uri = params.get("uri", "")
        data = _read_resource(uri)
        text = json.dumps(data, ensure_ascii=False, indent=2)
        return ok({"contents": [{"uri": uri, "mimeType": "application/json", "text": text}]})

    if method == "prompts/list":
        return ok({"prompts": []})

    return err(-32601, f"Method not found: {method}")


# ══════════════════════════════════════════════════════════════════════════════
# stdio event loop
# ══════════════════════════════════════════════════════════════════════════════

def _run_stdio():
    log.info("Semantica MCP server starting on stdio")
    # Use binary stdin/stdout for reliable newline handling on Windows
    stdin = sys.stdin.buffer
    stdout = sys.stdout.buffer

    while True:
        try:
            line = stdin.readline()
            if not line:
                break
            line = line.strip()
            if not line:
                continue
            try:
                req = json.loads(line)
            except json.JSONDecodeError as exc:
                resp = {"jsonrpc": "2.0", "id": None,
                        "error": {"code": -32700, "message": f"Parse error: {exc}"}}
                stdout.write(json.dumps(resp).encode() + b"\n")
                stdout.flush()
                continue

            resp = _handle(req)
            if resp is not None:
                stdout.write(json.dumps(resp, ensure_ascii=False).encode() + b"\n")
                stdout.flush()
        except EOFError:
            break
        except KeyboardInterrupt:
            break
        except Exception as exc:
            log.exception("Unhandled error in MCP loop: %s", exc)

    log.info("Semantica MCP server stopped")


def main():
    _run_stdio()
