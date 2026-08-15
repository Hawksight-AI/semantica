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
from typing import Any

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


def _get_graph():
    global _graph
    if _graph is None:
        from semantica.context import ContextGraph
        _graph = ContextGraph(advanced_analytics=True)
        kg_path = os.environ.get("SEMANTICA_KG_PATH")
        if kg_path and os.path.exists(kg_path):
            try:
                _graph.load(kg_path)
                log.info("Loaded graph from %s", kg_path)
            except Exception as exc:
                log.warning("Could not load graph from %s: %s", kg_path, exc)
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
    """Extract relations and triplets from text."""
    text = args.get("text", "")
    if not text:
        return {"error": "text is required"}
    from semantica.semantic_extract import RelationExtractor, TripletExtractor
    relations = RelationExtractor().extract_relations(text)
    triplets = TripletExtractor().extract_triplets(text)
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


def _tool_record_decision(args: dict) -> dict:
    """Record a decision with full context into the graph."""
    required = ["category", "scenario", "reasoning", "outcome", "confidence"]
    for field in required:
        if field not in args:
            return {"error": f"missing required field: {field}"}
    graph = _get_graph()
    decision_id = graph.record_decision(
        category=args["category"],
        scenario=args["scenario"],
        reasoning=args["reasoning"],
        outcome=args["outcome"],
        confidence=float(args["confidence"]),
        entities=args.get("entities", []),
        decision_maker=args.get("decision_maker", "mcp_client"),
        valid_from=args.get("valid_from"),
        valid_until=args.get("valid_until"),
    )
    return {"decision_id": decision_id, "status": "recorded"}


def _tool_query_decisions(args: dict) -> dict:
    """Query decisions by natural language or structured filters."""
    query = args.get("query", "")
    category = args.get("category")
    limit = int(args.get("limit", 10))
    graph = _get_graph()
    try:
        if query:
            results = graph.find_similar_decisions(query, max_results=limit)
        elif category:
            nodes = graph.find_nodes(node_type="decision")
            results = [n for n in nodes if n.get("category") == category][:limit]
        else:
            results = graph.find_nodes(node_type="decision")[:limit]
        return {"decisions": results if isinstance(results, list) else list(results)}
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


def _tool_get_causal_chain(args: dict) -> dict:
    """Get the causal chain for a decision."""
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
        return {"chain": chain if isinstance(chain, list) else list(chain)}
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
    return {"status": "added", "source": source, "target": target, "type": rel_type}


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
        from semantica.export import RDFExporter, JSONExporter
        if fmt in ("turtle", "ttl", "nt", "xml", "json-ld"):
            result = RDFExporter().export_to_rdf(graph, format=fmt)
        else:
            result = JSONExporter().export(graph)
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
        "description": "Trace the causal chain upstream or downstream from a decision.",
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
