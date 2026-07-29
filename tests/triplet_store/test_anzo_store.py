import os
import sys
import unittest
from unittest.mock import MagicMock, patch

PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

from semantica.semantic_extract.triplet_extractor import Triplet
from semantica.triplet_store.anzo_store import AnzoStore
from semantica.utils.exceptions import ProcessingError, ValidationError

DATASET_URI = "http://cambridgesemantics.com/Graphmart/abc123"


def _make_connected_store(**overrides) -> AnzoStore:
    """Create an AnzoStore instance bypassing the real _connect() call,
    with .connected forced True (mirrors the state execute_sparql requires)."""
    kwargs = {"endpoint": "http://localhost:8080", "dataset_uri": DATASET_URI}
    kwargs.update(overrides)
    with patch.object(AnzoStore, "_connect", autospec=True):
        store = AnzoStore(**kwargs)
    store.connected = True
    return store


CONSTRUCT_QUERY = "CONSTRUCT { ?s ?p ?o } WHERE { ?s ?p ?o }"


class TestAnzoStoreConstruction(unittest.TestCase):
    def test_requires_dataset_uri(self):
        with self.assertRaises(ValidationError):
            AnzoStore(endpoint="http://localhost:8080")

    def test_default_store_type_is_graphmart(self):
        store = _make_connected_store()
        self.assertEqual(store.store_type, "graphmart")

    def test_store_type_override(self):
        store = _make_connected_store(store_type="lds")
        self.assertEqual(store.store_type, "lds")


class TestAnzoStoreEndpointEncoding(unittest.TestCase):
    def test_sparql_endpoint_url_encodes_dataset_uri(self):
        store = _make_connected_store()
        endpoint = store._get_sparql_endpoint()
        self.assertEqual(
            endpoint,
            "http://localhost:8080/sparql/graphmart/"
            "http%3A%2F%2Fcambridgesemantics.com%2FGraphmart%2Fabc123",
        )

    def test_sparql_endpoint_uses_store_type_in_path(self):
        store = _make_connected_store(store_type="lds")
        endpoint = store._get_sparql_endpoint()
        self.assertIn("/sparql/lds/", endpoint)

    def test_update_endpoint_matches_query_endpoint(self):
        store = _make_connected_store()
        self.assertEqual(store._get_update_endpoint(), store._get_sparql_endpoint())

    def test_dataset_uri_with_special_characters_is_fully_encoded(self):
        store = _make_connected_store(dataset_uri="http://ex.org/g?x=1&y=2#frag")
        endpoint = store._get_sparql_endpoint()
        # No raw reserved characters from the dataset URI should leak into the path.
        path_segment = endpoint.split("/sparql/graphmart/", 1)[1]
        for char in ("/", "?", "&", "#", ":"):
            self.assertNotIn(char, path_segment)


class TestAnzoStoreIsConstructQuery(unittest.TestCase):
    def test_detects_uppercase(self):
        self.assertTrue(_make_connected_store()._is_construct_query(CONSTRUCT_QUERY))

    def test_detects_lowercase(self):
        self.assertTrue(
            _make_connected_store()._is_construct_query(
                "construct { ?s ?p ?o } where { ?s ?p ?o }"
            )
        )

    def test_false_for_select(self):
        self.assertFalse(
            _make_connected_store()._is_construct_query("SELECT ?s WHERE { ?s ?p ?o }")
        )

    def test_false_for_ask(self):
        self.assertFalse(_make_connected_store()._is_construct_query("ASK { ?s ?p ?o }"))

    def test_no_false_positive_on_constructor_substring(self):
        self.assertFalse(
            _make_connected_store()._is_construct_query(
                'SELECT ?s WHERE { ?s <urn:p> "CONSTRUCTOR" }'
            )
        )

    def test_is_construct_query_detects_mixed_case_keyword(self):
        store = _make_connected_store()
        self.assertTrue(
            store._is_construct_query("Construct { ?s ?p ?o } Where { ?s ?p ?o }")
        )

    def test_is_construct_query_detects_complex_preambles(self):
        # Permanent regression tests covering edge cases discovered during
        # regex stress-testing (issue #7): multiline declarations, empty
        # prefix namespaces, and inline comments embedded in the preamble.
        store = _make_connected_store()
        cases = {
            "multiline_prefix": "PREFIX foaf:\n  <http://xmlns.com/foaf/0.1/>\nCONSTRUCT { ?s ?p ?o } WHERE { ?s ?p ?o }",
            "empty_prefix_namespace": "PREFIX : <http://ex.org/> CONSTRUCT { ?s ?p ?o }",
            "inline_comment": "PREFIX ex: <http://ex.org/>\n# inline comment\nCONSTRUCT { ?s ?p ?o }",
        }
        for name, query in cases.items():
            with self.subTest(case=name):
                self.assertTrue(store._is_construct_query(query))


class TestAnzoStoreExecuteSparql(unittest.TestCase):
    def test_not_connected_raises_processing_error(self):
        with patch.object(AnzoStore, "_connect", autospec=True):
            store = AnzoStore(endpoint="http://localhost:8080", dataset_uri=DATASET_URI)
        store.connected = False
        with self.assertRaises(ProcessingError):
            store.execute_sparql("SELECT ?s WHERE { ?s ?p ?o }")

    def test_select_sends_basic_auth_when_credentials_given(self):
        store = _make_connected_store(username="user", password="pass")
        mock_resp = MagicMock()
        mock_resp.json.return_value = {"head": {"vars": []}, "results": {"bindings": []}}
        mock_resp.raise_for_status = MagicMock()
        with patch(
            "semantica.triplet_store.anzo_store.requests.post", return_value=mock_resp
        ) as mp:
            store.execute_sparql("SELECT ?s WHERE { ?s ?p ?o }")
        _, kw = mp.call_args
        self.assertEqual(kw["auth"], ("user", "pass"))

    def test_select_response_shape(self):
        store = _make_connected_store()
        mock_resp = MagicMock()
        mock_resp.json.return_value = {
            "head": {"vars": ["s", "p", "o"]},
            "results": {
                "bindings": [
                    {
                        "s": {"type": "uri", "value": "http://ex.org/s1"},
                        "p": {"type": "uri", "value": "http://ex.org/p1"},
                        "o": {"type": "literal", "value": "v1"},
                    }
                ]
            },
        }
        mock_resp.raise_for_status = MagicMock()
        with patch(
            "semantica.triplet_store.anzo_store.requests.post", return_value=mock_resp
        ) as mp:
            result = store.execute_sparql("SELECT ?s ?p ?o WHERE { ?s ?p ?o }")
        _, kw = mp.call_args
        self.assertNotEqual(kw["headers"].get("Accept"), "text/turtle")
        self.assertEqual(
            result,
            {
                "success": True,
                "bindings": mock_resp.json.return_value["results"]["bindings"],
                "variables": ["s", "p", "o"],
                "metadata": {
                    "query": "SELECT ?s ?p ?o WHERE { ?s ?p ?o }",
                    "endpoint": store._get_sparql_endpoint(),
                },
            },
        )
        self.assertNotIn("triples", result)

    def test_construct_sends_turtle_accept_header(self):
        store = _make_connected_store()
        mock_resp = MagicMock()
        mock_resp.content = b'@prefix ex: <http://ex.org/> .\nex:s1 ex:p1 "v" .\n'
        mock_resp.raise_for_status = MagicMock()
        with patch(
            "semantica.triplet_store.anzo_store.requests.post", return_value=mock_resp
        ) as mp:
            store.execute_sparql(CONSTRUCT_QUERY)
        _, kw = mp.call_args
        self.assertEqual(kw["headers"]["Accept"], "text/turtle")

    def test_construct_parses_triples_from_turtle_fixture(self):
        store = _make_connected_store()
        fixture = (
            b"@prefix ex: <http://ex.org/> .\n"
            b'ex:s1 ex:p1 "value1" .\n'
            b"ex:s1 ex:p2 ex:o2 .\n"
        )
        mock_resp = MagicMock()
        mock_resp.content = fixture
        mock_resp.raise_for_status = MagicMock()
        with patch(
            "semantica.triplet_store.anzo_store.requests.post", return_value=mock_resp
        ):
            result = store.execute_sparql(CONSTRUCT_QUERY)
        self.assertTrue(result["success"])
        self.assertEqual(result["metadata"]["result_format"], "construct")
        triples = {(s, p, o) for s, p, o, _m in result["triples"]}
        self.assertIn(("http://ex.org/s1", "http://ex.org/p1", "value1"), triples)
        self.assertIn(("http://ex.org/s1", "http://ex.org/p2", "http://ex.org/o2"), triples)

    def test_result_format_construct_forces_construct_path(self):
        store = _make_connected_store()
        mock_resp = MagicMock()
        mock_resp.content = b'@prefix ex: <http://ex.org/> .\nex:s1 ex:p1 "v" .\n'
        mock_resp.raise_for_status = MagicMock()
        with patch(
            "semantica.triplet_store.anzo_store.requests.post", return_value=mock_resp
        ) as mp:
            result = store.execute_sparql(
                "SELECT ?s WHERE { ?s ?p ?o }", result_format="construct"
            )
        _, kw = mp.call_args
        self.assertEqual(kw["headers"]["Accept"], "text/turtle")
        self.assertIn("triples", result)

    def test_malformed_turtle_raises_processing_error(self):
        store = _make_connected_store()
        mock_resp = MagicMock()
        mock_resp.content = b"this is { not [ valid turtle at all !!!"
        mock_resp.raise_for_status = MagicMock()
        with patch(
            "semantica.triplet_store.anzo_store.requests.post", return_value=mock_resp
        ):
            with self.assertRaises(ProcessingError) as ctx:
                store.execute_sparql(CONSTRUCT_QUERY)
        self.assertIsInstance(ctx.exception, ProcessingError)

    def test_invalid_result_format_raises_validation_error(self):
        store = _make_connected_store()
        with self.assertRaises(ValidationError):
            store.execute_sparql("SELECT ?s WHERE { ?s ?p ?o }", result_format="nope")

    def test_execute_sparql_construct_handles_literal_with_braces_in_valid_turtle(
        self,
    ):
        # Adversarial case implied by the brace-matching bug found in the
        # template-string layer (construct_templates._find_matching_brace):
        # confirm rdflib itself parses a *valid* Turtle literal containing
        # brace characters correctly, since this is a different parsing
        # layer (real Turtle syntax, not our {{param}} template string).
        store = _make_connected_store()
        turtle_fixture = (
            b"@prefix ex: <http://ex.org/> .\n"
            b'ex:s1 ex:p1 "text with { and } braces inside" .\n'
        )
        mock_response = MagicMock()
        mock_response.content = turtle_fixture
        mock_response.raise_for_status = MagicMock()

        with patch(
            "semantica.triplet_store.anzo_store.requests.post",
            return_value=mock_response,
        ):
            result = store.execute_sparql("CONSTRUCT { ?s ?p ?o } WHERE { ?s ?p ?o }")

        self.assertEqual(len(result["triples"]), 1)
        subject, predicate, obj, metadata = result["triples"][0]
        self.assertEqual(subject, "http://ex.org/s1")
        self.assertEqual(predicate, "http://ex.org/p1")
        self.assertEqual(obj, "text with { and } braces inside")
        self.assertEqual(metadata, {})


class TestAnzoStoreBulkLoadAndCrud(unittest.TestCase):
    def _t(self):
        return Triplet(
            subject="http://ex.org/s1",
            predicate="http://ex.org/p",
            object="http://ex.org/o1",
        )

    def test_bulk_load_posts_insert_data_to_update_endpoint(self):
        store = _make_connected_store()
        mock_resp = MagicMock()
        mock_resp.raise_for_status = MagicMock()
        with patch(
            "semantica.triplet_store.anzo_store.requests.post", return_value=mock_resp
        ) as mp:
            result = store.bulk_load([self._t()])
        self.assertTrue(result["success"])
        self.assertEqual(result["triplets_loaded"], 1)
        self.assertEqual(result["dataset_uri"], DATASET_URI)
        call_url = mp.call_args[0][0]
        self.assertEqual(call_url, store._get_update_endpoint())
        self.assertIn("INSERT DATA", mp.call_args[1]["data"]["update"])

    def test_bulk_load_with_graph_nests_graph_block_inside_insert_data(self):
        # SPARQL 1.1 Update requires the GRAPH block *inside* the INSERT DATA
        # braces: INSERT DATA { GRAPH <g> { ... } }, not
        # "INSERT DATA GRAPH <g> { ... }".
        store = _make_connected_store()
        mock_resp = MagicMock()
        mock_resp.raise_for_status = MagicMock()
        with patch(
            "semantica.triplet_store.anzo_store.requests.post", return_value=mock_resp
        ) as mp:
            store.bulk_load([self._t()], graph="http://ex.org/g")
        update_query = mp.call_args[1]["data"]["update"]
        self.assertIn("INSERT DATA { GRAPH <http://ex.org/g> {", update_query)
        self.assertNotIn("INSERT DATA GRAPH", update_query)

    def test_bulk_load_rejects_invalid_graph_uri(self):
        store = _make_connected_store()
        with self.assertRaises(ValidationError):
            store.bulk_load([self._t()], graph="http://ex.org/g with space")

    def test_bulk_load_rejects_injected_subject(self):
        store = _make_connected_store()
        bad_triplet = Triplet(
            subject="http://ex.org/s1> } ; DROP ALL #",
            predicate="http://ex.org/p",
            object="http://ex.org/o1",
        )
        with self.assertRaises(ValidationError):
            store.bulk_load([bad_triplet])

    def test_bulk_load_not_connected_raises(self):
        with patch.object(AnzoStore, "_connect", autospec=True):
            store = AnzoStore(endpoint="http://localhost:8080", dataset_uri=DATASET_URI)
        store.connected = False
        with self.assertRaises(ProcessingError):
            store.bulk_load([self._t()])

    def test_add_triplet_delegates_to_bulk_load(self):
        store = _make_connected_store()
        with patch.object(store, "bulk_load", return_value={"success": True}) as mb:
            store.add_triplet(self._t())
        mb.assert_called_once_with([self._t()])

    def test_add_triplets_delegates_to_bulk_load(self):
        store = _make_connected_store()
        triplets = [self._t(), self._t()]
        with patch.object(store, "bulk_load", return_value={"success": True}) as mb:
            store.add_triplets(triplets)
        mb.assert_called_once_with(triplets)

    def test_delete_triplet_posts_delete_data(self):
        store = _make_connected_store()
        mock_resp = MagicMock()
        mock_resp.raise_for_status = MagicMock()
        with patch(
            "semantica.triplet_store.anzo_store.requests.post", return_value=mock_resp
        ) as mp:
            result = store.delete_triplet(self._t())
        self.assertTrue(result["success"])
        self.assertIn("DELETE DATA", mp.call_args[1]["data"]["update"])

    def test_delete_triplet_not_connected_raises(self):
        with patch.object(AnzoStore, "_connect", autospec=True):
            store = AnzoStore(endpoint="http://localhost:8080", dataset_uri=DATASET_URI)
        store.connected = False
        with self.assertRaises(ProcessingError):
            store.delete_triplet(self._t())

    def test_delete_triplet_rejects_injected_subject(self):
        store = _make_connected_store()
        bad_triplet = Triplet(
            subject="http://ex.org/s1> } ; DROP ALL #",
            predicate="http://ex.org/p",
            object="http://ex.org/o1",
        )
        with self.assertRaises(ValidationError):
            store.delete_triplet(bad_triplet)

    def test_get_triplets_builds_select_and_parses_bindings(self):
        store = _make_connected_store()
        mock_resp = MagicMock()
        mock_resp.json.return_value = {
            "head": {"vars": ["s", "p", "o"]},
            "results": {
                "bindings": [
                    {
                        "s": {"type": "uri", "value": "http://ex.org/s1"},
                        "p": {"type": "uri", "value": "http://ex.org/p1"},
                        "o": {"type": "literal", "value": "v1"},
                    }
                ]
            },
        }
        mock_resp.raise_for_status = MagicMock()
        with patch(
            "semantica.triplet_store.anzo_store.requests.post", return_value=mock_resp
        ):
            triplets = store.get_triplets(subject="http://ex.org/s1")
        self.assertEqual(len(triplets), 1)
        self.assertEqual(triplets[0].subject, "http://ex.org/s1")
        self.assertEqual(triplets[0].metadata.get("source"), "anzo")

    def test_get_triplets_emits_valid_filter_based_query(self):
        # The WHERE clause must remain a syntactically valid graph pattern
        # (?s ?p ?o .) with constraints expressed via FILTER(...), not bare
        # equality expressions appended inside the group graph pattern.
        store = _make_connected_store()
        mock_resp = MagicMock()
        mock_resp.json.return_value = {"head": {"vars": []}, "results": {"bindings": []}}
        mock_resp.raise_for_status = MagicMock()
        with patch(
            "semantica.triplet_store.anzo_store.requests.post", return_value=mock_resp
        ) as mp:
            store.get_triplets(subject="http://ex.org/s1", predicate="http://ex.org/p1")
        query = mp.call_args[1]["data"]["query"]
        self.assertIn("?s ?p ?o .", query)
        self.assertIn("FILTER(", query)
        self.assertIn("?s = <http://ex.org/s1>", query)
        self.assertIn("?p = <http://ex.org/p1>", query)
        self.assertNotIn("?o } WHERE", query)

    def test_get_triplets_no_filters_omits_filter_clause(self):
        store = _make_connected_store()
        mock_resp = MagicMock()
        mock_resp.json.return_value = {"head": {"vars": []}, "results": {"bindings": []}}
        mock_resp.raise_for_status = MagicMock()
        with patch(
            "semantica.triplet_store.anzo_store.requests.post", return_value=mock_resp
        ) as mp:
            store.get_triplets()
        query = mp.call_args[1]["data"]["query"]
        self.assertNotIn("FILTER(", query)
        self.assertEqual(query, "SELECT ?s ?p ?o WHERE { ?s ?p ?o . }")

    def test_get_triplets_rejects_invalid_subject_uri(self):
        store = _make_connected_store()
        with self.assertRaises(ValidationError):
            store.get_triplets(subject="not a valid uri")


class TestAnzoStoreObjectFormatting(unittest.TestCase):
    def test_format_object_serializes_uri_object(self):
        store = _make_connected_store()
        triplet = Triplet(
            subject="urn:entity:person:1",
            predicate="urn:property:knows",
            object="urn:entity:person:2",
        )
        self.assertEqual(
            store._format_object_for_sparql(triplet), "<urn:entity:person:2>"
        )

    def test_format_object_serializes_literal_object(self):
        store = _make_connected_store()
        triplet = Triplet(
            subject="urn:entity:person:1",
            predicate="urn:property:name",
            object="Jane Doe",
        )
        self.assertEqual(store._format_object_for_sparql(triplet), "\"Jane Doe\"")

    def test_format_object_serializes_typed_literal(self):
        store = _make_connected_store()
        triplet = Triplet(
            subject="urn:entity:person:1",
            predicate="urn:property:age",
            object="42",
            metadata={"datatype": "xsd:integer"},
        )
        self.assertEqual(
            store._format_object_for_sparql(triplet),
            "\"42\"^^<http://www.w3.org/2001/XMLSchema#integer>",
        )

    def test_format_object_rejects_injected_lang_tag(self):
        store = _make_connected_store()
        triplet = Triplet(
            subject="urn:entity:person:1",
            predicate="urn:property:label",
            object="Color",
            metadata={"lang": "en . CLEAR ALL #"},
        )
        with self.assertRaises(ValueError):
            store._format_object_for_sparql(triplet)

    def test_format_object_escapes_literal_object(self):
        store = _make_connected_store()
        triplet = Triplet(
            subject="urn:entity:person:1",
            predicate="urn:property:note",
            object='line "one"\\line2',
        )
        obj = store._format_object_for_sparql(triplet)
        self.assertEqual(
            obj,
            "\"line \\\"one\\\"\\\\line2\"",
        )

    def test_format_object_serializes_language_literal(self):
        store = _make_connected_store()
        triplet = Triplet(
            subject="urn:entity:person:1",
            predicate="urn:property:label",
            object="Color",
            metadata={"lang": "en"},
        )
        obj = store._format_object_for_sparql(triplet)
        self.assertEqual(obj, "\"Color\"@en")

    def test_format_object_does_not_treat_invalid_uri_like_text_as_uri(self):
        store = _make_connected_store()
        triplet = Triplet(
            subject="urn:entity:person:1",
            predicate="urn:property:note",
            object="http not a uri",
        )
        obj = store._format_object_for_sparql(triplet)
        self.assertEqual(obj, "\"http not a uri\"")

    def test_format_object_expands_rdf_prefix_to_full_iri(self):
        store = _make_connected_store()
        triplet = Triplet(
            subject="urn:entity:person:1",
            predicate="urn:property:value",
            object="hello",
            metadata={"datatype": "rdf:langString"},
        )
        obj = store._format_object_for_sparql(triplet)
        self.assertEqual(
            obj,
            "\"hello\"^^<http://www.w3.org/1999/02/22-rdf-syntax-ns#langString>",
        )

    def test_format_object_rejects_unknown_prefix(self):
        store = _make_connected_store()
        triplet = Triplet(
            subject="urn:entity:person:1",
            predicate="urn:property:value",
            object="hello",
            metadata={"datatype": "myns:customType"},
        )
        with self.assertRaises(ValueError):
            store._format_object_for_sparql(triplet)

    def test_format_object_rejects_datatype_with_whitespace(self):
        store = _make_connected_store()
        triplet = Triplet(
            subject="urn:entity:person:1",
            predicate="urn:property:age",
            object="42",
            metadata={"datatype": "http://example.org/type CLEAR ALL"},
        )
        with self.assertRaises(ValueError):
            store._format_object_for_sparql(triplet)

    def test_format_object_accepts_full_iri_datatype_no_brackets(self):
        store = _make_connected_store()
        triplet = Triplet(
            subject="urn:entity:person:1",
            predicate="urn:property:age",
            object="42",
            metadata={"datatype": "http://www.w3.org/2001/XMLSchema#integer"},
        )
        obj = store._format_object_for_sparql(triplet)
        self.assertEqual(
            obj,
            "\"42\"^^<http://www.w3.org/2001/XMLSchema#integer>",
        )

    def test_format_object_accepts_bracketed_iri_datatype(self):
        store = _make_connected_store()
        triplet = Triplet(
            subject="urn:entity:person:1",
            predicate="urn:property:age",
            object="42",
            metadata={"datatype": "<http://www.w3.org/2001/XMLSchema#integer>"},
        )
        obj = store._format_object_for_sparql(triplet)
        self.assertEqual(
            obj,
            "\"42\"^^<http://www.w3.org/2001/XMLSchema#integer>",
        )

    def test_format_object_accepts_hyphenated_lang_tag(self):
        store = _make_connected_store()
        triplet = Triplet(
            subject="urn:entity:person:1",
            predicate="urn:property:label",
            object="Colour",
            metadata={"lang": "en-GB"},
        )
        obj = store._format_object_for_sparql(triplet)
        self.assertEqual(obj, "\"Colour\"@en-GB")


if __name__ == "__main__":
    unittest.main()
