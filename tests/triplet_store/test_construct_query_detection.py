"""Regression tests for CONSTRUCT query-form detection (issue #931).

``CONSTRUCT_QUERY_RE``'s comment alternative used to be written ``\\#[^\\n]*``.
The trailing ``*`` backtracks, so for a query like::

    # CONSTRUCT in a comment
    SELECT * WHERE { }

the engine consumed the ``#``, gave back everything after it, and let the
CONSTRUCT *inside the comment* satisfy the query-form keyword. Every SPARQL
backend delegates to this one regex, so a SELECT/ASK carrying such a leading
comment was routed down the CONSTRUCT path of ``execute_sparql`` — which sends
``Accept: text/turtle`` and parses the body as Turtle, failing with a
misleading "Failed to parse CONSTRUCT response as Turtle".

Both directions are pinned here: the false positives that motivated the fix,
and the queries that were already detected correctly, so a future tightening
cannot silently start dropping real CONSTRUCT queries instead.
"""

import unittest
from unittest.mock import patch

from semantica.triplet_store import sparql_escaping
from semantica.triplet_store.anzo_store import AnzoStore
from semantica.triplet_store.blazegraph_store import BlazegraphStore
from semantica.triplet_store.jena_store import JenaStore
from semantica.triplet_store.rdf4j_store import RDF4JStore

# Queries whose *form* is CONSTRUCT. Each must be detected.
CONSTRUCT_CASES = {
    "bare": "CONSTRUCT { ?s ?p ?o } WHERE { ?s ?p ?o }",
    "lowercase": "construct { ?s ?p ?o } where { ?s ?p ?o }",
    "mixed_case": "Construct { ?s ?p ?o } Where { ?s ?p ?o }",
    "leading_whitespace": "   \n\t CONSTRUCT { ?s ?p ?o } WHERE { ?s ?p ?o }",
    "prefix_preamble": (
        "PREFIX e: <http://e/>\nCONSTRUCT { ?s ?p ?o } WHERE { ?s ?p ?o }"
    ),
    "base_preamble": "BASE <http://e/> CONSTRUCT { ?s ?p ?o } WHERE { ?s ?p ?o }",
    "comment_then_construct": "# a comment\nCONSTRUCT { ?s ?p ?o } WHERE { ?s ?p ?o }",
    "two_comments_then_construct": "#\n#\nCONSTRUCT { ?s ?p ?o } WHERE { ?s ?p ?o }",
    "comment_crlf": "# a comment\r\nCONSTRUCT { ?s ?p ?o } WHERE { ?s ?p ?o }",
    "comment_cr_only": "# a comment\rCONSTRUCT { ?s ?p ?o } WHERE { ?s ?p ?o }",
    "empty_comment": "#\nCONSTRUCT { ?s ?p ?o } WHERE { ?s ?p ?o }",
    "mixed_preamble": (
        "  \n # header \n PREFIX e: <http://e/>\n # note \n "
        "CONSTRUCT { ?s ?p ?o } WHERE { ?s ?p ?o }"
    ),
}

# Queries whose form is NOT CONSTRUCT. None may be detected.
NON_CONSTRUCT_CASES = {
    "plain_select": "SELECT ?s WHERE { ?s ?p ?o }",
    "plain_ask": "ASK { ?s ?p ?o }",
    "describe": "DESCRIBE <urn:x>",
    "keyword_in_literal": 'SELECT * WHERE { ?s ?p "please CONSTRUCT this" }',
    "keyword_in_trailing_comment": "SELECT * WHERE { } # CONSTRUCT",
    "keyword_as_substring": 'SELECT ?s WHERE { ?s <urn:p> "CONSTRUCTOR" }',
    # The issue #931 payloads: CONSTRUCT inside a *leading* comment.
    "leading_comment_lf": "# CONSTRUCT in a comment\nSELECT * WHERE { }",
    "leading_comment_crlf": "# CONSTRUCT in a comment\r\nSELECT * WHERE { }",
    "leading_comment_cr_only": "# CONSTRUCT in a comment\rSELECT * WHERE { }",
    "leading_comment_no_space": "#CONSTRUCT\nSELECT * WHERE { }",
    "leading_comment_mid_sentence": "# we will CONSTRUCT later\nSELECT * WHERE { }",
    "leading_comment_second_line": "#\n# CONSTRUCT\nSELECT * WHERE { }",
    "leading_comment_before_ask": "# TODO: CONSTRUCT\nASK { ?s ?p ?o }",
    "leading_comment_word_construction": "# CONSTRUCTION notes\nSELECT * WHERE { }",
    "comment_only_no_newline": "# CONSTRUCT",
}


def _blazegraph_store() -> BlazegraphStore:
    with patch.object(BlazegraphStore, "_connect", autospec=True):
        store = BlazegraphStore(endpoint="http://localhost:9999/blazegraph")
    store.connected = True
    return store


def _rdf4j_store() -> RDF4JStore:
    with patch.object(RDF4JStore, "_connect", autospec=True):
        store = RDF4JStore(
            endpoint="http://localhost:8080/rdf4j-server", repository_id="repo1"
        )
    store.connected = True
    return store


def _anzo_store() -> AnzoStore:
    with patch.object(AnzoStore, "_connect", autospec=True):
        store = AnzoStore(
            endpoint="http://localhost:8080",
            dataset_uri="http://cambridgesemantics.com/Graphmart/abc123",
        )
    store.connected = True
    return store


def _jena_store() -> JenaStore:
    return JenaStore()


# Every backend that delegates to CONSTRUCT_QUERY_RE. Detection is shared, so
# a per-backend regression would otherwise only surface in whichever backend
# happened to be covered.
BACKENDS = {
    "blazegraph": _blazegraph_store,
    "rdf4j": _rdf4j_store,
    "anzo": _anzo_store,
    "jena": _jena_store,
}


class TestConstructQueryRegex(unittest.TestCase):
    """Direct tests of the shared regex."""

    def test_case_tables_are_populated(self):
        """Guard against a vacuous suite.

        Every test below iterates a table; if a table were emptied or renamed
        away, those loops would pass without asserting anything.
        """
        self.assertGreaterEqual(len(CONSTRUCT_CASES), 12)
        self.assertGreaterEqual(len(NON_CONSTRUCT_CASES), 15)
        self.assertEqual(len(BACKENDS), 4)

    def test_detects_construct_query_forms(self):
        for label, query in CONSTRUCT_CASES.items():
            with self.subTest(case=label):
                self.assertIsNotNone(
                    sparql_escaping.CONSTRUCT_QUERY_RE.search(query),
                    f"{label}: real CONSTRUCT query was not detected",
                )

    def test_rejects_non_construct_query_forms(self):
        for label, query in NON_CONSTRUCT_CASES.items():
            with self.subTest(case=label):
                self.assertIsNone(
                    sparql_escaping.CONSTRUCT_QUERY_RE.search(query),
                    f"{label}: non-CONSTRUCT query was misdetected as CONSTRUCT",
                )

    def test_comment_alternative_does_not_backtrack(self):
        """The specific mechanism behind #931.

        A comment must be consumed up to its terminator. If the character
        class backtracks, the match ends *inside* the comment instead of
        failing, which is what let CONSTRUCT-in-a-comment win.
        """
        query = "# CONSTRUCT in a comment\nSELECT * WHERE { }"
        self.assertIsNone(sparql_escaping.CONSTRUCT_QUERY_RE.search(query))

    def test_carriage_return_terminates_a_comment(self):
        """CR alone ends a comment, so CONSTRUCT after it is a real CONSTRUCT.

        Pins the difference between `[^\\n]*(?:\\n|\\Z)` and the shipped
        `[^\\n\\r]*(?:[\\n\\r]|\\Z)`: the former treats a CR-terminated comment
        as running to end of input, swallowing the query form after it.
        """
        self.assertIsNotNone(
            sparql_escaping.CONSTRUCT_QUERY_RE.search(
                "# a comment\rCONSTRUCT { ?s ?p ?o } WHERE { ?s ?p ?o }"
            )
        )
        self.assertIsNone(
            sparql_escaping.CONSTRUCT_QUERY_RE.search(
                "# CONSTRUCT in a comment\rSELECT * WHERE { }"
            )
        )


class TestConstructDetectionAcrossBackends(unittest.TestCase):
    """The regex is shared, so assert every backend's public detector agrees."""

    def test_all_backends_detect_construct_query_forms(self):
        for backend, factory in BACKENDS.items():
            store = factory()
            for label, query in CONSTRUCT_CASES.items():
                with self.subTest(backend=backend, case=label):
                    self.assertTrue(
                        store._is_construct_query(query),
                        f"{backend}/{label}: real CONSTRUCT query was not detected",
                    )

    def test_all_backends_reject_non_construct_query_forms(self):
        for backend, factory in BACKENDS.items():
            store = factory()
            for label, query in NON_CONSTRUCT_CASES.items():
                with self.subTest(backend=backend, case=label):
                    self.assertFalse(
                        store._is_construct_query(query),
                        f"{backend}/{label}: non-CONSTRUCT query was misdetected",
                    )

    def test_every_backend_exposes_the_detector(self):
        """Fail loudly if a backend stops delegating to the shared regex.

        Without this, a backend that dropped `_is_construct_query` would make
        the loops above error rather than report a meaningful failure.
        """
        for backend, factory in BACKENDS.items():
            with self.subTest(backend=backend):
                store = factory()
                self.assertTrue(
                    callable(getattr(store, "_is_construct_query", None)),
                    f"{backend}: no callable _is_construct_query",
                )


if __name__ == "__main__":
    unittest.main()
