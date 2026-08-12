"""Tests for the shared graph-payload normalizer (issue #956).

Graph payloads circulate under two vocabularies -- 'entities'/'relationships'
and 'nodes'/'edges' -- and consumers each reconciled them locally with at
least three competing idioms. The same payload could therefore be exported,
silently dropped, or rejected depending on which consumer read it:
``export_lpg`` dropped every entity when 'nodes' was present but empty, which
is precisely the shape ``JSONExporter`` emits.

The end-to-end assertions run the real exporters rather than mocking them,
since the behaviour under test is that the exporters now agree.
"""

import os
import shutil
import tempfile
import unittest

from semantica.export import methods as export_methods
from semantica.utils import normalize_graph_payload
from semantica.utils.exceptions import ValidationError

ENTITY = {"id": "e1", "name": "Acme"}
RELATIONSHIP = {"id": "r1", "source": "e1", "target": "e2"}


class TestVocabularyResolution(unittest.TestCase):
    def test_canonical_keys_pass_through(self):
        result = normalize_graph_payload(
            {"entities": [ENTITY], "relationships": [RELATIONSHIP]}
        )
        self.assertEqual(result["entities"], [ENTITY])
        self.assertEqual(result["relationships"], [RELATIONSHIP])
        self.assertEqual(result["triplets"], [])

    def test_aliases_are_mapped_to_canonical_keys(self):
        result = normalize_graph_payload({"nodes": [ENTITY], "edges": [RELATIONSHIP]})
        self.assertEqual(result["entities"], [ENTITY])
        self.assertEqual(result["relationships"], [RELATIONSHIP])

    def test_empty_alias_does_not_mask_a_populated_canonical_key(self):
        """The JSONExporter round-trip shape, and the #956 data-loss case."""
        result = normalize_graph_payload(
            {"entities": [ENTITY], "nodes": [], "relationships": [], "edges": []}
        )
        self.assertEqual(result["entities"], [ENTITY])

    def test_empty_canonical_key_does_not_mask_a_populated_alias(self):
        result = normalize_graph_payload({"entities": [], "nodes": [ENTITY]})
        self.assertEqual(result["entities"], [ENTITY])

    def test_identical_spellings_are_accepted(self):
        result = normalize_graph_payload({"entities": [ENTITY], "nodes": [ENTITY]})
        self.assertEqual(result["entities"], [ENTITY])

    def test_conflicting_spellings_are_refused(self):
        """No basis to prefer either, and picking one would lose the other."""
        with self.assertRaises(ValidationError) as ctx:
            normalize_graph_payload(
                {"entities": [ENTITY], "nodes": [{"id": "different"}]}
            )
        message = str(ctx.exception)
        self.assertIn("entities", message)
        self.assertIn("nodes", message)

    def test_triplets_are_carried_through(self):
        result = normalize_graph_payload({"triplets": [{"s": "a", "p": "b", "o": "c"}]})
        self.assertEqual(result["triplets"], [{"s": "a", "p": "b", "o": "c"}])

    def test_missing_collections_default_to_empty_lists(self):
        result = normalize_graph_payload({"entities": [ENTITY]})
        self.assertEqual(result["relationships"], [])
        self.assertEqual(result["triplets"], [])

    def test_result_does_not_alias_the_input_collections(self):
        payload = {"entities": [ENTITY]}
        result = normalize_graph_payload(payload)
        result["entities"].append({"id": "e2"})
        self.assertEqual(len(payload["entities"]), 1)


class TestUnrecognizedInput(unittest.TestCase):
    def test_unrecognized_keys_raise_by_default(self):
        for payload in ({"data": [ENTITY]}, {"records": [ENTITY]}, {"foo": "bar"}):
            with self.subTest(payload=payload):
                with self.assertRaises(ValidationError):
                    normalize_graph_payload(payload)

    def test_error_names_supplied_and_expected_keys(self):
        with self.assertRaises(ValidationError) as ctx:
            normalize_graph_payload({"data": [ENTITY]})
        message = str(ctx.exception)
        self.assertIn("data", message)
        self.assertIn("entities", message)
        self.assertIn("nodes", message)

    def test_unrecognized_keys_can_degrade_to_empty_when_asked(self):
        result = normalize_graph_payload({"data": [ENTITY]}, require_recognized=False)
        self.assertEqual(result["entities"], [])
        self.assertEqual(result["relationships"], [])

    def test_empty_mapping_is_accepted(self):
        """An empty graph is legitimate and carries nothing that could be lost."""
        result = normalize_graph_payload({})
        self.assertEqual(result, {"entities": [], "relationships": [], "triplets": []})

    def test_non_mapping_input_raises(self):
        for payload in ([ENTITY], (ENTITY,), "entities", 42, None):
            with self.subTest(payload=repr(payload)):
                with self.assertRaises(ValidationError):
                    normalize_graph_payload(payload)


class TestExportersAgree(unittest.TestCase):
    """The divergence from #956, run against the real exporters."""

    # export_csv is excluded: it writes entities/relationships/nodes/edges to
    # four separate files by design, so it is not resolving two spellings of
    # one collection and is out of scope for this change.
    EXPORTERS = ("export_json", "export_arango", "export_neo4j_csv", "export_lpg")

    def setUp(self):
        self.tmpdir = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, self.tmpdir, ignore_errors=True)

    def _export_and_read(self, name, payload):
        outdir = os.path.join(self.tmpdir, name)
        os.makedirs(outdir, exist_ok=True)
        getattr(export_methods, name)(payload, os.path.join(outdir, "out"))
        blob = ""
        for root, _, files in os.walk(outdir):
            for filename in files:
                with open(os.path.join(root, filename), errors="ignore") as handle:
                    blob += handle.read()
        return blob

    def test_exporter_list_is_populated(self):
        """Guard against a vacuous suite if the list is emptied."""
        self.assertGreaterEqual(len(self.EXPORTERS), 4)

    def test_every_exporter_keeps_records_when_an_alias_is_empty(self):
        payload = {
            "entities": [ENTITY],
            "nodes": [],
            "relationships": [],
            "edges": [],
        }
        for name in self.EXPORTERS:
            with self.subTest(exporter=name):
                self.assertIn(
                    "Acme",
                    self._export_and_read(name, payload),
                    f"{name} dropped the entity when 'nodes' was present but empty",
                )

    def test_every_exporter_accepts_the_alias_vocabulary(self):
        payload = {"nodes": [ENTITY], "edges": []}
        for name in self.EXPORTERS:
            with self.subTest(exporter=name):
                self.assertIn(
                    "Acme",
                    self._export_and_read(name, payload),
                    f"{name} dropped the entity supplied as 'nodes'",
                )


if __name__ == "__main__":
    unittest.main()
