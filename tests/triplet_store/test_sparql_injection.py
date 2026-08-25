"""Regression tests for GHSA-8vgg-8mr4-r236: unvalidated triplet IRIs
allowed arbitrary SPARQL update injection in the Blazegraph and RDF4J
stores, and query-filter injection on the Jena read path.

Triplet.subject/predicate (and, in some builders, .object) are document
text in the normal ingest pipeline — entity names extracted from ingested
content. A subject containing '>' closes the '<...>' IRI token early, so
the rest of the value is parsed as more SPARQL, letting an attacker
append operations like CLEAR ALL that run with the application's store
credentials.

Mirrors the advisory's own PoC payload: a subject/predicate crafted to
close the current triple pattern and append a destructive `; CLEAR ALL ;`
statement. After the fix, sparql_escaping.validate_uri (already used by
anzo_store.py, the one backend that was already hardened) rejects it
before any query/update text is built.
"""

import unittest
from unittest.mock import patch

from semantica.semantic_extract.triplet_extractor import Triplet
from semantica.triplet_store.blazegraph_store import BlazegraphStore
from semantica.triplet_store.rdf4j_store import RDF4JStore
from semantica.triplet_store.jena_store import JenaStore
from semantica.utils.exceptions import ProcessingError, ValidationError

# The advisory's own injection payload: closes the <...> token, then the
# triple pattern, then appends a store-wide wipe and a rogue insert.
EVIL_SUBJECT = (
    "http://example.com/a> <http://example.com/b> <http://example.com/c> . } "
    "; CLEAR ALL ; INSERT DATA { <http://evil.example/owned"
)


class TestBlazegraphSparqlInjection(unittest.TestCase):
    @patch.object(BlazegraphStore, "_connect", autospec=True)
    def _make_store(self, _mock_connect):
        return BlazegraphStore(endpoint="http://localhost:9999/blazegraph")

    def test_build_insert_data_rejects_malicious_subject(self):
        store = self._make_store()
        triplet = Triplet(subject=EVIL_SUBJECT, predicate="http://p", object="x")
        with self.assertRaises(ValidationError):
            store._build_insert_data([triplet])

    def test_triplets_to_rdf_rejects_malicious_subject(self):
        store = self._make_store()
        triplet = Triplet(subject=EVIL_SUBJECT, predicate="http://p", object="x")
        with self.assertRaises(ValidationError):
            store._triplets_to_rdf([triplet])

    def test_delete_triplet_rejects_malicious_subject(self):
        store = self._make_store()
        store.connected = True
        triplet = Triplet(subject=EVIL_SUBJECT, predicate="http://p", object="x")
        with self.assertRaises(ValidationError):
            store.delete_triplet(triplet)

    def test_get_triplets_rejects_malicious_subject_filter(self):
        store = self._make_store()
        with self.assertRaises(ValidationError):
            store.get_triplets(subject=EVIL_SUBJECT)

    def test_bulk_load_rejects_malicious_graph_option(self):
        # bulk_load() wraps its whole body in except Exception: raise
        # ProcessingError(...) (pre-existing, unrelated to this fix), so the
        # ValidationError sanitize_uri raises surfaces as ProcessingError.
        # The security property that matters — the malicious query is never
        # sent — holds either way.
        store = self._make_store()
        store.connected = True
        triplet = Triplet(subject="http://s", predicate="http://p", object="x")
        with self.assertRaises(ProcessingError) as ctx:
            store.bulk_load([triplet], graph=EVIL_SUBJECT)
        self.assertIn("Invalid URI", str(ctx.exception))

    def test_legitimate_triplet_still_builds_correct_query(self):
        store = self._make_store()
        triplet = Triplet(subject="http://s", predicate="http://p", object="x")
        insert_data = store._build_insert_data([triplet])
        self.assertIn("<http://s> <http://p>", insert_data)
        self.assertNotIn("CLEAR ALL", insert_data)

    def test_format_object_rejects_malicious_pre_wrapped_iri(self):
        """A caller-supplied object already wrapped in '<...>' must still be
        fully validated, not just checked for a literal space/'>' — a
        narrower ad-hoc check here previously let this branch bypass
        validate_uri() entirely (Codex-flagged follow-up to GHSA-8vgg)."""
        store = self._make_store()
        evil_object = f"<{EVIL_SUBJECT}>"
        triplet = Triplet(subject="http://s", predicate="http://p", object=evil_object)
        with self.assertRaises(ValidationError):
            store._format_object_for_sparql(triplet)

    def test_format_object_accepts_legitimate_pre_wrapped_iri(self):
        store = self._make_store()
        triplet = Triplet(subject="http://s", predicate="http://p", object="<http://o>")
        self.assertEqual(store._format_object_for_sparql(triplet), "<http://o>")


class TestRDF4JSparqlInjection(unittest.TestCase):
    @patch.object(RDF4JStore, "_connect", autospec=True)
    def _make_store(self, _mock_connect):
        return RDF4JStore(endpoint="http://localhost:9999/rdf4j", repository_id="mem")

    def test_triplets_to_ntriples_rejects_malicious_subject(self):
        store = self._make_store()
        triplet = Triplet(subject=EVIL_SUBJECT, predicate="http://p", object="x")
        with self.assertRaises(ValidationError):
            store._triplets_to_ntriples([triplet])

    def test_delete_triplet_rejects_malicious_subject(self):
        store = self._make_store()
        store.connected = True
        triplet = Triplet(subject=EVIL_SUBJECT, predicate="http://p", object="http://o")
        with self.assertRaises(ValidationError):
            store.delete_triplet(triplet)

    # ------------------------------------------------------------------
    # Regression tests for the literal-object bug fixed after the
    # adversarial review of PR #911: delete_triplet() previously called
    # validate_uri(triplet.object) unconditionally, which rejected every
    # non-URI object with ValidationError even though literal objects are
    # perfectly legal in RDF.  The fix routes the object through
    # _format_object_for_ntriples so URI-valued objects are still validated
    # while literal objects go through escape_literal unchanged.
    # ------------------------------------------------------------------

    def _make_connected_store_with_captured_query(self):
        """Return (store, captured_dict) where captured['update'] is the
        SPARQL update string passed to requests.post once delete_triplet
        succeeds."""
        import requests as req_mod
        from unittest.mock import MagicMock

        store = self._make_store()
        store.connected = True
        captured = {}

        mock_resp = MagicMock()
        mock_resp.raise_for_status = MagicMock()

        def fake_post(url, **kwargs):
            captured["update"] = kwargs.get("data", {}).get("update", "")
            return mock_resp

        store._post = fake_post  # not used directly; patch requests.post below
        store._captured = captured
        return store, captured

    def test_delete_triplet_literal_object_succeeds(self):
        """A triplet with a plain-string literal object must delete without
        raising ValidationError — the regression that prompted this fix."""
        store, captured = self._make_connected_store_with_captured_query()

        with patch("requests.post") as mock_post:
            mock_post.return_value.__enter__ = lambda s: s
            mock_post.return_value.raise_for_status = lambda: None

            result = store.delete_triplet(
                Triplet(subject="http://s", predicate="http://p", object="Paris")
            )

        self.assertEqual(result, {"success": True})
        # Confirm query shape: object must be a quoted literal, not <Paris>
        query_sent = mock_post.call_args[1]["data"]["update"]
        self.assertIn("<http://s> <http://p>", query_sent)
        self.assertIn('"Paris"', query_sent)
        self.assertNotIn("<Paris>", query_sent)
        self.assertNotIn("CLEAR ALL", query_sent)

    def test_delete_triplet_uri_object_still_works(self):
        """A triplet whose object is a URI must still delete correctly."""
        store, _ = self._make_connected_store_with_captured_query()

        with patch("requests.post") as mock_post:
            mock_post.return_value.raise_for_status = lambda: None

            result = store.delete_triplet(
                Triplet(subject="http://s", predicate="http://p", object="http://o")
            )

        self.assertEqual(result, {"success": True})
        query_sent = mock_post.call_args[1]["data"]["update"]
        self.assertIn("<http://s> <http://p> <http://o>", query_sent)
        self.assertNotIn("CLEAR ALL", query_sent)

    def test_delete_triplet_malicious_uri_object_rejected_before_post(self):
        """A URI-shaped object containing '>' must be rejected by
        _format_object_for_ntriples → validate_uri before requests.post
        is ever called."""
        evil_obj = "http://evil.com/a>;CLEARALL"
        store, _ = self._make_connected_store_with_captured_query()

        with patch("requests.post") as mock_post:
            with self.assertRaises(ValidationError):
                store.delete_triplet(
                    Triplet(subject="http://s", predicate="http://p", object=evil_obj)
                )
        mock_post.assert_not_called()

    def test_delete_triplet_malicious_subject_still_rejected(self):
        """Subject injection protection must remain intact after the fix."""
        store, _ = self._make_connected_store_with_captured_query()

        with patch("requests.post") as mock_post:
            with self.assertRaises(ValidationError):
                store.delete_triplet(
                    Triplet(subject=EVIL_SUBJECT, predicate="http://p", object="http://o")
                )
        mock_post.assert_not_called()

    def test_get_triplets_rejects_malicious_subject_filter(self):
        store = self._make_store()
        with self.assertRaises(ValidationError):
            store.get_triplets(subject=EVIL_SUBJECT)

    def test_legitimate_triplet_still_builds_correct_ntriples(self):
        store = self._make_store()
        triplet = Triplet(subject="http://s", predicate="http://p", object="x")
        ntriples = store._triplets_to_ntriples([triplet])
        self.assertIn("<http://s> <http://p>", ntriples)
        self.assertNotIn("CLEAR ALL", ntriples)

    def test_format_object_rejects_malicious_pre_wrapped_iri(self):
        """Same pre-wrapped-object bypass as Blazegraph, fixed in
        _format_object_for_ntriples."""
        store = self._make_store()
        evil_object = f"<{EVIL_SUBJECT}>"
        triplet = Triplet(subject="http://s", predicate="http://p", object=evil_object)
        with self.assertRaises(ValidationError):
            store._format_object_for_ntriples(triplet)

    def test_format_object_accepts_legitimate_pre_wrapped_iri(self):
        store = self._make_store()
        triplet = Triplet(subject="http://s", predicate="http://p", object="<http://o>")
        self.assertEqual(store._format_object_for_ntriples(triplet), "<http://o>")


class TestJenaSparqlInjection(unittest.TestCase):
    def setUp(self):
        from rdflib import Graph

        self.store = JenaStore()
        self.store.graph = Graph()

    def test_get_triplets_never_queries_with_malicious_subject_filter(self):
        """get_triplets() catches all exceptions and returns [] (pre-existing,
        broad error-handling behavior unrelated to this fix), so the
        observable contract is: the malicious filter must never reach
        graph.query() at all."""
        with patch.object(self.store.graph, "query", wraps=self.store.graph.query) as spy:
            result = self.store.get_triplets(subject=EVIL_SUBJECT)
        self.assertEqual(result, [])
        spy.assert_not_called()

    def test_get_triplets_with_legitimate_filter_still_reaches_query(self):
        """A validated identifier must not be rejected by the sanitizer —
        it should reach graph.query(). (Whether the WHERE-clause filter
        syntax jena_store.py builds is itself correct SPARQL is a separate,
        pre-existing question this test doesn't assert on: the query here
        is `{ ?s ?p ?o ?s = <http://s> }`, missing a FILTER()/separator,
        and unrelated to sanitize_uri.)"""
        self.store.graph.parse(
            data='<http://s> <http://p> "x" .', format="ntriples"
        )
        with patch.object(self.store.graph, "query", wraps=self.store.graph.query) as spy:
            self.store.get_triplets(subject="http://s")
        spy.assert_called_once()
        self.assertIn("http://s", spy.call_args[0][0])


if __name__ == "__main__":
    unittest.main()
