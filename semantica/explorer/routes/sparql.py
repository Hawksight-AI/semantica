"""
SPARQL routes backed by an in-memory rdflib projection of the current graph.

Security contract
-----------------
* Only SELECT, ASK, CONSTRUCT, and DESCRIBE are accepted, and the query
  body is scanned for SPARQL Update keywords (INSERT/DELETE/DROP/LOAD/
  CLEAR/CREATE/COPY/MOVE/ADD) after stripping comments and PREFIX/BASE
  declarations — both enforced before graph construction, so rejected
  queries never touch the session. A multi-statement injection appended
  after an allowed keyword (e.g. ``SELECT ... ; DROP ALL``) is caught by
  the keyword scan itself, not left to rdflib's parser.
* rdflib's parser remains a second line of defense for malformed multi-
  statement syntax that doesn't contain any forbidden keyword (e.g.
  ``SELECT ... ; ASK ...``), which SPARQL 1.1 Query doesn't permit.
* The in-memory rdflib graph is a read-only projection — the live
  ``GraphSession`` is never mutated by this route.
"""

import asyncio
import re
from typing import Any, Dict, List, Optional, Tuple

import rdflib
from fastapi import APIRouter, Depends
from pydantic import BaseModel

from ..dependencies import get_session
from ..session import GraphSession

router = APIRouter(prefix="/api/sparql", tags=["Power User Tools"])

_ALLOWED_QUERY_TYPES = re.compile(
    r"^(SELECT|ASK|CONSTRUCT|DESCRIBE)\b",
    re.IGNORECASE,
)

# SPARQL Update keywords that must never appear in read-only queries.
# These are checked AFTER comment/prefix stripping to prevent bypass via
# comments like: # INSERT DATA { ... }\nSELECT ...
_FORBIDDEN_KEYWORDS = re.compile(
    r"\b(INSERT|DELETE|DROP|LOAD|CLEAR|CREATE|COPY|MOVE|ADD)\b",
    re.IGNORECASE,
)

# Matches SPARQL single-line comments (# ...) and PREFIX/BASE declarations.
# The comment regex only treats '#' as a comment-starter at line-start or
# after whitespace — not mid-token — since RDF namespace IRIs commonly
# contain a literal '#' (e.g. ".../1999/02/22-rdf-syntax-ns#"), and a naive
# `#[^\n]*` would truncate every such PREFIX declaration's IRI, corrupting
# the query. BASE declarations have no prefix name between the keyword and
# the IRI (`BASE <...>`, vs. `PREFIX ex: <...>`), so the prefix-name token
# is optional.
#
# ReDoS fix (CodeQL py/polynomial-redos, issue #1897):
#
# The original pattern `<[^>]*>\s*` was vulnerable because `\s*` (which
# matches newlines) could overlap with `[^>]*` on inputs that contain no
# closing `>` (e.g. `base<!!<!<...`), forcing the engine to explore every
# possible split between the two quantifiers — O(n²) backtracking.
#
# The fix uses `<[^>\r\n]*>` for the IRI body: excluding CR and LF from
# the character class means the IRI match can never span a line boundary,
# and the disjoint trailing `[ \t]*` (horizontal whitespace only) has zero
# character-class overlap with `[^>\r\n]*`, so the engine has exactly one
# way to match.  No end-of-line anchor is needed or used, which correctly
# handles both inline prologues (`PREFIX ex: <...> SELECT ...` on one line)
# and CRLF line endings (`\r\n`) without any special casing.
_COMMENT_LINE = re.compile(r"(?:^|(?<=\s))#[^\n]*", re.MULTILINE)
_PREFIX_DECL = re.compile(
    r"^[ \t]*(?:PREFIX[ \t]+\S+|BASE)[ \t]*<[^>\r\n]*>[ \t]*",
    re.IGNORECASE | re.MULTILINE,
)


def _is_read_only_query(query: str) -> bool:
    """Return True only for genuine read-only SPARQL queries.

    Strips comments, PREFIX/BASE declarations, and leading whitespace before
    checking the first keyword. Also rejects queries containing SPARQL Update
    keywords anywhere in the body, preventing injection via embedded strings
    or multi-statement tricks.

    Note: callers are responsible for enforcing any input-length limit *before*
    calling this function so that an oversized-query rejection can be surfaced
    as a distinct, actionable error rather than the generic read-only message.
    """
    # 1. Remove single-line comments that could hide the real query type
    cleaned = _COMMENT_LINE.sub("", query)
    # 2. Remove PREFIX/BASE declarations
    cleaned = _PREFIX_DECL.sub("", cleaned)
    # 3. Strip remaining whitespace
    cleaned = cleaned.strip()

    # 4. Check that the first keyword is a read-only query type
    if not _ALLOWED_QUERY_TYPES.match(cleaned):
        return False

    # 5. Block any forbidden (mutating) keywords anywhere in the query
    if _FORBIDDEN_KEYWORDS.search(cleaned):
        return False

    return True


class SparqlRequest(BaseModel):
    query: str


class SparqlResponse(BaseModel):
    columns: List[str]
    rows: List[Dict[str, Any]]
    total: int
    truncated: bool = False  # True when _SPARQL_MAX_ROWS was hit
    error: Optional[str] = None
    error_line: Optional[int] = None
    error_column: Optional[int] = None


NS = rdflib.Namespace("http://semantica.local/entity/")
PROP = rdflib.Namespace("http://semantica.local/prop/")


def _build_rdflib_graph(session: GraphSession) -> rdflib.Graph:
    graph = rdflib.Graph()
    graph.bind("ent", NS)
    graph.bind("prop", PROP)

    # SECURITY: Cap the number of entities materialized into memory to
    # prevent denial-of-service via memory exhaustion.  Without this guard
    # an attacker can send concurrent SPARQL queries that each load ~1M
    # nodes/edges into rdflib Graph objects, consuming gigabytes of RAM.
    nodes, total_nodes = session.get_nodes(skip=0, limit=_SPARQL_MAX_GRAPH_NODES + 1)
    if len(nodes) > _SPARQL_MAX_GRAPH_NODES:
        raise ValueError(
            f"Graph has more than {_SPARQL_MAX_GRAPH_NODES:,} nodes. "
            f"SPARQL queries are limited to graphs with at most "
            f"{_SPARQL_MAX_GRAPH_NODES:,} nodes to prevent excessive "
            f"memory usage. Use the REST API for large graph operations."
        )

    edges, _ = session.get_edges(skip=0, limit=_SPARQL_MAX_GRAPH_NODES + 1)
    if len(edges) > _SPARQL_MAX_GRAPH_NODES:
        raise ValueError(
            f"Graph has more than {_SPARQL_MAX_GRAPH_NODES:,} edges. "
            f"SPARQL queries are limited to graphs with at most "
            f"{_SPARQL_MAX_GRAPH_NODES:,} edges to prevent excessive "
            f"memory usage. Use the REST API for large graph operations."
        )

    for node in nodes:
        subject = NS[str(node.get("id", ""))]
        node_type = node.get("type", "Entity")
        graph.add((subject, rdflib.RDF.type, NS[node_type]))

        content = node.get("content", "")
        if content:
            graph.add((subject, rdflib.RDFS.label, rdflib.Literal(content)))

        for key, value in node.get("properties", {}).items():
            if key in {"content", "valid_from", "valid_until"}:
                continue
            graph.add((subject, PROP[key], rdflib.Literal(value)))

    for edge in edges:
        source = NS[str(edge.get("source", ""))]
        target = NS[str(edge.get("target", ""))]
        relationship = edge.get("type", "relatedTo")
        graph.add((source, PROP[relationship], target))

    return graph


# ---------------------------------------------------------------------------
# Resource limits (override in tests via patch.object)
# ---------------------------------------------------------------------------
_SPARQL_MAX_ROWS = 5_000     # hard cap on returned rows
_SPARQL_TIMEOUT_S = 30       # seconds before abandoning the await
_SPARQL_MAX_CONCURRENT = 4   # semaphore: max simultaneous executions
_SPARQL_MAX_GRAPH_NODES = 50_000  # cap on graph nodes/edges to prevent OOM
# Defense-in-depth against ReDoS: reject inputs longer than this before any
# regex work so that even a future regex regression is bounded.  Checked in
# execute_sparql() (not inside _is_read_only_query) so the route can return
# a distinct, actionable error message rather than the generic read-only one.
_SPARQL_MAX_QUERY_LEN = 10_000  # chars

# Semaphore caps how many graph.query calls run concurrently so that
# timed-out threads (which keep running in the pool) cannot crowd out
# other requests by exhausting the default ThreadPoolExecutor workers.
_sparql_semaphore = asyncio.Semaphore(_SPARQL_MAX_CONCURRENT)


def _cap_rows(items: Any, row_builder) -> Tuple[List[Dict[str, Any]], bool]:
    """Materialize up to ``_SPARQL_MAX_ROWS`` items via ``row_builder``, reporting truncation.

    Shared by the SELECT and CONSTRUCT/DESCRIBE branches below so the row cap
    is enforced identically regardless of query type.
    """
    rows: List[Dict[str, Any]] = []
    truncated = False
    for item in items:
        if len(rows) >= _SPARQL_MAX_ROWS:
            truncated = True
            break
        rows.append(row_builder(item))
    return rows, truncated


@router.post("", response_model=SparqlResponse)
async def execute_sparql(
    req: SparqlRequest,
    session: GraphSession = Depends(get_session),
):
    # Resource-limit check: reject oversized queries before any regex work.
    # This is intentionally a separate, earlier check from _is_read_only_query
    # so clients receive a specific, actionable message rather than the generic
    # read-only rejection, and operators can tune _SPARQL_MAX_QUERY_LEN without
    # touching query-semantics code.
    if len(req.query) > _SPARQL_MAX_QUERY_LEN:
        return SparqlResponse(
            columns=[],
            rows=[],
            total=0,
            error=(
                f"Query exceeds the maximum allowed length of "
                f"{_SPARQL_MAX_QUERY_LEN:,} characters "
                f"({len(req.query):,} received). "
                f"Please shorten your query."
            ),
        )

    if not _is_read_only_query(req.query):
        return SparqlResponse(
            columns=[],
            rows=[],
            total=0,
            error="Only SELECT, ASK, CONSTRUCT, and DESCRIBE queries are permitted.",
        )

    try:
        graph = await asyncio.to_thread(_build_rdflib_graph, session)
    except ValueError as exc:
        return SparqlResponse(
            columns=[],
            rows=[],
            total=0,
            error=str(exc),
        )

    async with _sparql_semaphore:
        try:
            query_results = await asyncio.wait_for(
                asyncio.to_thread(graph.query, req.query),
                timeout=_SPARQL_TIMEOUT_S,
            )
        except asyncio.TimeoutError:
            return SparqlResponse(
                columns=[],
                rows=[],
                total=0,
                error=f"Query timed out after {_SPARQL_TIMEOUT_S} seconds.",
            )
        except Exception as exc:
            error = str(exc)
            line_match = re.search(r"line[\s:]+(\d+)", error, re.IGNORECASE)
            column_match = re.search(r"col(?:umn)?[\s:]+(\d+)", error, re.IGNORECASE)
            return SparqlResponse(
                columns=[],
                rows=[],
                total=0,
                error=error,
                error_line=int(line_match.group(1)) if line_match else None,
                error_column=int(column_match.group(1)) if column_match else None,
            )

    # ---------------------------------------------------------------------------
    # Serialize results into a type-aware tabular representation.
    # ASK      → single row: {"result": "true"|"false"}
    # CONSTRUCT/DESCRIBE → rows of {"subject", "predicate", "object"} triples
    # SELECT   → rows keyed by projected variable names
    # ---------------------------------------------------------------------------
    query_type: str = query_results.type  # always set by rdflib

    if query_type == "ASK":
        columns = ["result"]
        rows = [{"result": "true" if query_results.askAnswer else "false"}]
        truncated = False

    elif query_type in ("CONSTRUCT", "DESCRIBE"):
        columns = ["subject", "predicate", "object"]
        rows, truncated = _cap_rows(
            query_results,  # rdflib always yields (s, p, o) 3-tuples
            lambda triple: {
                "subject": str(triple[0]),
                "predicate": str(triple[1]),
                "object": str(triple[2]),
            },
        )

    else:  # SELECT
        columns = [str(var) for var in (query_results.vars or [])]
        rows, truncated = _cap_rows(
            query_results,
            lambda row: {
                column: (str(row[index]) if row[index] is not None else None)
                for index, column in enumerate(columns)
            },
        )

    return SparqlResponse(columns=columns, rows=rows, total=len(rows), truncated=truncated)
