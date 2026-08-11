"""Tests for the SPARQL Explorer route (semantica/explorer/routes/sparql.py).

Filed as #773: this route executes arbitrary SPARQL against an in-memory
rdflib projection of the live graph and had zero test coverage anywhere in
the repo. Coverage here focuses on the two things that matter most for a
query-execution surface: (1) the read-only allowlist can't be bypassed, and
(2) the resource-limiting behavior (row cap, timeout) actually engages.
"""

import asyncio
import concurrent.futures
from unittest.mock import patch

import pytest

from semantica.context.context_graph import ContextGraph
from semantica.explorer.app import create_app
from semantica.explorer.session import GraphSession

try:
    from starlette.testclient import TestClient
except ImportError:
    pytest.skip(
        "starlette TestClient is required for explorer tests. Install semantica[explorer].",
        allow_module_level=True,
    )

import semantica.explorer.routes.sparql as sparql_mod


def _build_sample_graph() -> ContextGraph:
    graph = ContextGraph(advanced_analytics=False)
    graph.add_node(
        "python",
        node_type="language",
        content="Python programming language",
        popularity="high",
    )
    graph.add_node("javascript", node_type="language", content="JavaScript programming language")
    graph.add_node("web_dev", node_type="concept", content="Web Development")
    graph.add_edge("python", "web_dev", edge_type="used_in", weight=0.5)
    return graph


@pytest.fixture(scope="module")
def client():
    session = GraphSession(_build_sample_graph())
    app = create_app(session=session)
    with TestClient(app) as test_client:
        yield test_client


def _post(client, query):
    return client.post("/api/sparql", json={"query": query})


# ---------------------------------------------------------------------------
# Happy-path query types
# ---------------------------------------------------------------------------

def test_select_returns_expected_columns_and_rows(client):
    resp = _post(client, "SELECT ?s ?label WHERE { ?s <http://www.w3.org/2000/01/rdf-schema#label> ?label }")
    assert resp.status_code == 200
    payload = resp.json()
    assert payload["error"] is None
    assert set(payload["columns"]) == {"s", "label"}
    assert payload["total"] == len(payload["rows"])
    labels = {row["label"] for row in payload["rows"]}
    assert "Python programming language" in labels
    assert "JavaScript programming language" in labels


def test_ask_query_returns_boolean_like_result(client):
    resp = _post(
        client,
        "ASK { ?s <http://www.w3.org/2000/01/rdf-schema#label> \"Python programming language\" }",
    )
    assert resp.status_code == 200
    payload = resp.json()
    assert payload["error"] is None
    assert payload["columns"] == ["result"]
    assert payload["rows"] == [{"result": "true"}]
    assert payload["total"] == 1


def test_construct_query_succeeds(client):
    resp = _post(
        client,
        "CONSTRUCT { ?s <http://www.w3.org/2000/01/rdf-schema#label> ?label } "
        "WHERE { ?s <http://www.w3.org/2000/01/rdf-schema#label> ?label }",
    )
    assert resp.status_code == 200
    payload = resp.json()
    assert payload["error"] is None
    assert payload["columns"] == ["subject", "predicate", "object"]
    assert payload["total"] > 0
    assert any(
        row["subject"] == "http://semantica.local/entity/python"
        and row["predicate"] == "http://www.w3.org/2000/01/rdf-schema#label"
        and row["object"] == "Python programming language"
        for row in payload["rows"]
    )


def test_describe_query_succeeds(client):
    resp = _post(client, "DESCRIBE <http://semantica.local/entity/python>")
    assert resp.status_code == 200
    payload = resp.json()
    assert payload["error"] is None
    assert payload["columns"] == ["subject", "predicate", "object"]
    assert payload["total"] > 0
    assert any(
        row["subject"] == "http://semantica.local/entity/python"
        and row["predicate"] == "http://www.w3.org/1999/02/22-rdf-syntax-ns#type"
        and row["object"] == "http://semantica.local/entity/language"
        for row in payload["rows"]
    )


def test_lowercase_query_keyword_is_accepted(client):
    """The allowlist regex is case-insensitive; confirm lowercase keywords work too."""
    resp = _post(client, "select ?s where { ?s a <http://semantica.local/entity/language> }")
    assert resp.status_code == 200
    payload = resp.json()
    assert payload["error"] is None


def test_select_with_no_results_returns_empty_rows(client):
    resp = _post(client, "SELECT ?s WHERE { ?s a <http://semantica.local/entity/nonexistent> }")
    assert resp.status_code == 200
    payload = resp.json()
    assert payload["error"] is None
    assert payload["rows"] == []
    assert payload["total"] == 0


# ---------------------------------------------------------------------------
# Read-only allowlist: this is the security-relevant surface (#773's core risk)
# ---------------------------------------------------------------------------

@pytest.mark.parametrize(
    "query",
    [
        "INSERT DATA { <http://semantica.local/entity/x> a <http://semantica.local/entity/hacked> }",
        "DELETE DATA { <http://semantica.local/entity/python> a <http://semantica.local/entity/language> }",
        "DELETE WHERE { ?s ?p ?o }",
        "DROP ALL",
        "DROP GRAPH <http://example.org/g>",
        "CLEAR ALL",
        "CLEAR GRAPH <http://example.org/g>",
        "LOAD <http://example.org/data.ttl>",
        "CREATE GRAPH <http://example.org/g>",
        "MODIFY <http://example.org/g> DELETE { ?s ?p ?o } WHERE { ?s ?p ?o }",
        "",
        "   ",
        "not a sparql query at all",
        # A write statement smuggled after a comment prefix fails prefix-matching
        "# comment\nDROP ALL",
    ],
)
def test_write_and_non_read_queries_are_rejected_by_allowlist(client, query):
    resp = _post(client, query)
    assert resp.status_code == 200, "rejection is a normal 200 response with an error field, not an HTTP error"
    payload = resp.json()
    assert payload["error"] is not None
    assert payload["rows"] == []
    assert payload["columns"] == []
    assert payload["total"] == 0


def test_multi_statement_injection_is_rejected_by_parser(client):
    """A multi-statement injection starting with SELECT passes the prefix
    allowlist check but is rejected by rdflib's SPARQL parser as invalid
    query syntax, preventing any mutation or secondary execution."""
    resp = _post(client, "SELECT ?s WHERE { ?s ?p ?o } ; DROP ALL")
    assert resp.status_code == 200
    payload = resp.json()
    assert payload["error"] is not None
    assert payload["rows"] == []
    assert payload["columns"] == []
    assert payload["total"] == 0


@pytest.mark.parametrize(
    "query",
    [
        "DROP ALL",
        "INSERT DATA { <http://semantica.local/entity/x> a <http://semantica.local/entity/y> }",
        "# comment\nDROP ALL",
        "",
    ],
)
def test_allowlist_rejected_query_never_touches_the_graph(client, query):
    """An input failing _is_read_only_query must short-circuit before any graph is built/queried."""
    with patch.object(sparql_mod, "_build_rdflib_graph") as mock_build:
        resp = _post(client, query)
    assert resp.status_code == 200
    assert resp.json()["error"] is not None
    mock_build.assert_not_called()


def test_multi_statement_injection_is_rejected_by_forbidden_keyword_check(client):
    """A string starting with an allowed keyword (SELECT) but containing a
    forbidden Update keyword later in the body (';  DROP ALL') is now
    rejected by _is_read_only_query's keyword scan itself, before a graph
    is ever built — a stronger, earlier rejection than relying solely on
    rdflib's parser to reject the syntax."""
    with patch.object(sparql_mod, "_build_rdflib_graph") as mock_build:
        resp = _post(client, "SELECT ?s WHERE { ?s ?p ?o } ; DROP ALL")
    assert resp.status_code == 200
    assert resp.json()["error"] is not None
    mock_build.assert_not_called()


def test_malformed_syntax_without_forbidden_keywords_still_fails_in_parser(client):
    """The parser remains a real second line of defense for malformed
    queries that don't contain any forbidden keyword — these pass
    _is_read_only_query and reach rdflib, which rejects the syntax."""
    with patch.object(
        sparql_mod, "_build_rdflib_graph", wraps=sparql_mod._build_rdflib_graph
    ) as spy_build:
        resp = _post(client, "SELECT ?s WHERE { ?s ?p ?o } ; ASK { ?x ?y ?z }")
    assert resp.status_code == 200
    assert resp.json()["error"] is not None
    spy_build.assert_called_once()


# ---------------------------------------------------------------------------
# Error handling for malformed queries
# ---------------------------------------------------------------------------

def test_malformed_query_returns_error_without_crashing(client):
    resp = _post(client, "SELECT ?s WHERE { this is not valid sparql syntax")
    assert resp.status_code == 200
    payload = resp.json()
    assert payload["error"] is not None
    assert payload["rows"] == []
    assert payload["total"] == 0


def test_malformed_query_error_includes_line_and_column_when_present(client):
    resp = _post(client, "SELECT ?s WHERE { $$$ invalid $$$ }")
    payload = resp.json()
    assert payload["error"] is not None
    # error_line/error_column are best-effort extraction from the pyparsing
    # error message; they may be None depending on rdflib's error text, but
    # the fields must always be present and of the right type when set.
    assert payload["error_line"] is None or isinstance(payload["error_line"], int)
    assert payload["error_column"] is None or isinstance(payload["error_column"], int)


# ---------------------------------------------------------------------------
# Resource limits: row cap and timeout
# ---------------------------------------------------------------------------

def test_row_cap_truncates_results(client):
    with patch.object(sparql_mod, "_SPARQL_MAX_ROWS", 1):
        resp = _post(
            client,
            "SELECT ?s WHERE { ?s a <http://semantica.local/entity/language> }",
        )
    assert resp.status_code == 200
    payload = resp.json()
    assert payload["error"] is None
    assert len(payload["rows"]) == 1
    assert payload["total"] == 1
    assert payload["truncated"] is True


def test_result_below_cap_is_not_marked_truncated(client):
    resp = _post(client, "SELECT ?s WHERE { ?s a <http://semantica.local/entity/language> }")
    payload = resp.json()
    assert payload["truncated"] is False


def test_row_cap_truncates_construct_results(client):
    """CONSTRUCT/DESCRIBE share _cap_rows with SELECT; confirm the cap applies there too."""
    with patch.object(sparql_mod, "_SPARQL_MAX_ROWS", 1):
        resp = _post(
            client,
            "CONSTRUCT { ?s <http://www.w3.org/2000/01/rdf-schema#label> ?label } "
            "WHERE { ?s <http://www.w3.org/2000/01/rdf-schema#label> ?label }",
        )
    assert resp.status_code == 200
    payload = resp.json()
    assert payload["error"] is None
    assert len(payload["rows"]) == 1
    assert payload["total"] == 1
    assert payload["truncated"] is True


def test_query_timeout_returns_clean_error_not_a_crash(client):
    async def _raise_timeout(coro, timeout=None):
        coro.close()  # avoid a 'coroutine was never awaited' warning from the mock
        raise asyncio.TimeoutError()

    with patch.object(sparql_mod.asyncio, "wait_for", side_effect=_raise_timeout):
        resp = _post(client, "SELECT ?s WHERE { ?s a <http://semantica.local/entity/language> }")
    assert resp.status_code == 200
    payload = resp.json()
    assert payload["error"] is not None
    assert "timed out" in payload["error"].lower()
    assert payload["rows"] == []


def test_oversized_graph_returns_clean_error_not_a_crash(client):
    """The DoS-prevention node cap (GHSA-8c7v-adjacent hardening) must return
    a normal SparqlResponse error, not an unhandled 500. Regression test for
    a bug where _build_rdflib_graph's ValueError was raised outside of
    execute_sparql's try/except, before the semaphore block."""
    with patch.object(sparql_mod, "_SPARQL_MAX_GRAPH_NODES", 1):
        resp = _post(client, "SELECT ?s WHERE { ?s a <http://semantica.local/entity/language> }")
    assert resp.status_code == 200
    payload = resp.json()
    assert payload["error"] is not None
    assert "more than" in payload["error"].lower()
    assert payload["rows"] == []


def test_oversized_query_returns_distinct_length_error(client):
    """A query exceeding _SPARQL_MAX_QUERY_LEN must be rejected with a
    specific, actionable error message — not the generic read-only message.
    Clients need to distinguish a size-limit rejection from an actual
    non-read-only query rejection to react correctly (e.g. split the query
    vs. rewrite it)."""
    with patch.object(sparql_mod, "_SPARQL_MAX_QUERY_LEN", 10):
        resp = _post(client, "SELECT ?s WHERE { ?s ?p ?o }")  # 30 chars > 10
    assert resp.status_code == 200
    payload = resp.json()
    assert payload["error"] is not None
    # Must mention the limit, not the generic read-only message
    assert "length" in payload["error"].lower() or "characters" in payload["error"].lower()
    assert "Only SELECT" not in payload["error"]
    assert payload["rows"] == []
    assert payload["columns"] == []
    assert payload["total"] == 0


def test_oversized_query_never_touches_the_graph(client):
    """An oversized query must be rejected before _build_rdflib_graph is
    called — the length guard must short-circuit the entire pipeline."""
    with patch.object(sparql_mod, "_SPARQL_MAX_QUERY_LEN", 10):
        with patch.object(sparql_mod, "_build_rdflib_graph") as mock_build:
            resp = _post(client, "SELECT ?s WHERE { ?s ?p ?o }")
    assert resp.status_code == 200
    assert resp.json()["error"] is not None
    mock_build.assert_not_called()


def test_query_exactly_at_length_limit_is_accepted(client):
    """A query whose length equals the limit exactly must not be rejected —
    the guard is strictly greater-than, not greater-than-or-equal."""
    short_query = "ASK {}"
    with patch.object(sparql_mod, "_SPARQL_MAX_QUERY_LEN", len(short_query)):
        resp = _post(client, short_query)
    assert resp.status_code == 200
    payload = resp.json()
    assert payload["error"] is None


# ---------------------------------------------------------------------------
# Data-mapping fidelity: does the graph->RDF projection reflect session state?
# ---------------------------------------------------------------------------

def test_node_properties_are_projected_as_literals_excluding_reserved_keys(client):
    resp = _post(
        client,
        "SELECT ?p ?v WHERE { <http://semantica.local/entity/python> ?p ?v }",
    )
    payload = resp.json()
    predicates = {row["p"] for row in payload["rows"]}
    # 'popularity' is a real property and should be projected.
    assert any("popularity" in p for p in predicates)
    # content/valid_from/valid_until are excluded from prop: projection
    # (content instead becomes rdfs:label, handled separately).
    assert not any(p.endswith("/prop/content") for p in predicates)


def test_edges_are_projected_with_their_relationship_type(client):
    resp = _post(
        client,
        "SELECT ?o WHERE { <http://semantica.local/entity/python> "
        "<http://semantica.local/prop/used_in> ?o }",
    )
    payload = resp.json()
    assert payload["error"] is None
    assert any("web_dev" in row["o"] for row in payload["rows"])


def test_concurrent_requests_all_complete_successfully(client):
    """Basic smoke test that the concurrency semaphore doesn't deadlock or
    drop requests under light concurrent load."""
    import concurrent.futures

    def _run():
        return _post(client, "SELECT ?s WHERE { ?s a <http://semantica.local/entity/language> }")

    pool = concurrent.futures.ThreadPoolExecutor(max_workers=6)
    try:
        futures = [pool.submit(_run) for _ in range(6)]
        results = []
        for idx, fut in enumerate(futures):
            try:
                results.append(fut.result(timeout=10.0))
            except concurrent.futures.TimeoutError:
                pytest.fail(
                    f"Concurrent SPARQL query #{idx} deadlocked or timed out after 10.0s"
                )
    finally:
        pool.shutdown(wait=False, cancel_futures=True)

    for resp in results:
        assert resp.status_code == 200
        assert resp.json()["error"] is None
