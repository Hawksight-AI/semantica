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
from dataclasses import dataclass

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

    def test_reordered_identical_spellings_are_accepted(self):
        """Same records, different order, is not a conflict.

        A caller round-tripping through a dict-keyed cache or a set has no
        reason to preserve list order; comparing spellings with plain list
        equality rejected this as if the records differed.
        """
        other = {"id": "e2", "name": "Beta"}
        result = normalize_graph_payload(
            {"entities": [ENTITY, other], "nodes": [other, ENTITY]}
        )
        self.assertCountEqual(result["entities"], [ENTITY, other])

    def test_reordered_spellings_with_duplicate_records_still_conflict(self):
        """Multiset comparison must still catch a real count mismatch."""
        with self.assertRaises(ValidationError):
            normalize_graph_payload({"entities": [ENTITY, ENTITY], "nodes": [ENTITY]})

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

    def test_every_exporter_raises_processing_error_for_non_mapping_input(self):
        """A wrong-type payload is rejected the same way everywhere.

        export_yaml and export_neo4j_csv raised ProcessingError for a bare
        list; export_lpg and export_arango called normalize_graph_payload()
        directly with no type guard, so they alone raised ValidationError
        (from inside the resolver) for the identical mistake.
        """
        from semantica.utils.exceptions import ProcessingError

        for name in ("export_arango", "export_neo4j_csv", "export_lpg"):
            with self.subTest(exporter=name):
                outdir = os.path.join(self.tmpdir, name + "_bad_type")
                os.makedirs(outdir, exist_ok=True)
                with self.assertRaises(ProcessingError):
                    getattr(export_methods, name)([ENTITY], os.path.join(outdir, "out"))

    def test_every_exporter_converts_object_shaped_records(self):
        """A dataclass record must not merely pass validation.

        normalize_graph_payload() accepts dataclass/attribute-bearing
        records (Neo4jCSVExporter reads them off attributes), but
        export_lpg and export_arango read records with ``.get(...)``. A
        record that passed validation unconverted crashed with a raw
        AttributeError once used -- the exact failure the boundary exists
        to prevent.
        """

        @dataclass
        class Node:
            id: str
            name: str

        payload = {"entities": [Node(id="e1", name="Acme")], "relationships": []}
        for name in ("export_arango", "export_neo4j_csv", "export_lpg"):
            with self.subTest(exporter=name):
                self.assertIn("Acme", self._export_and_read(name, payload))

    def test_neo4j_accepts_non_dict_mappings(self):
        """Neo4jCSVExporter's mapping path must not be narrower than the rest.

        _normalize_graph checked isinstance(graph, dict), so a non-dict
        Mapping (a MappingProxyType, a ChainMap) fell into the
        object-attribute branch and was rejected as an unrecognized object,
        even though the identical payload exports fine via LPG/Arango/YAML.
        """
        import types

        payload = types.MappingProxyType({"entities": [ENTITY], "relationships": []})
        self.assertIn("Acme", self._export_and_read("export_neo4j_csv", payload))


class TestRecordsCannotBeDroppedSilently(unittest.TestCase):
    """Presence of a recognized key is not proof the records survived.

    ``{"entities": [], "data": [...]}`` clears a presence-only check and still
    resolves to empty, so the records under 'data' would be dropped with no
    signal -- the same failure the recognition check exists to prevent.
    """

    def test_empty_recognized_key_does_not_excuse_records_elsewhere(self):
        with self.assertRaises(ValidationError) as ctx:
            normalize_graph_payload({"entities": [], "data": [ENTITY]})

        message = str(ctx.exception)
        self.assertIn("'data'", message)
        self.assertIn("holds records", message)

    def test_check_applies_to_every_recognized_spelling(self):
        for key in ("entities", "nodes", "relationships", "edges", "triplets"):
            with self.subTest(key=key):
                with self.assertRaises(ValidationError):
                    normalize_graph_payload({key: [], "records": [ENTITY]})

    def test_non_record_keys_are_not_mistaken_for_dropped_records(self):
        """ContextGraph.to_dict() always carries 'statistics'.

        An empty graph must stay exportable, so only a non-empty list counts
        as evidence that records were dropped.
        """
        result = normalize_graph_payload(
            {"nodes": [], "edges": [], "statistics": {"node_count": 0}}
        )

        self.assertEqual(result["entities"], [])
        self.assertEqual(result["relationships"], [])

    def test_records_alongside_a_populated_collection_are_not_refused(self):
        """Something resolved, so the export is not silently empty."""
        result = normalize_graph_payload({"entities": [ENTITY], "statistics": {"n": 1}})

        self.assertEqual(result["entities"], [ENTITY])


class TestCollectionValuesAreValidated(unittest.TestCase):
    """A recognized key is not proof its value is a collection of records.

    Resolving on truthiness alone let ``{"entities": "abc"}`` through as three
    single-character "records" and let ``{"entities": 42}`` surface as a raw
    ``TypeError`` from ``list()`` inside an exporter, naming the exporter
    rather than the payload key at fault. Both are rejected here, at the
    boundary that owns the question.
    """

    COLLECTION_KEYS = ("entities", "nodes", "relationships", "edges", "triplets")

    # Every public export path that reads its payload through the normalizer.
    # export_json is excluded: it treats the payload as opaque records rather
    # than resolving graph collections, so it never calls the normalizer.
    NORMALIZING_EXPORTERS = (
        "export_arango",
        "export_neo4j_csv",
        "export_lpg",
        "export_yaml",
    )

    def test_string_value_is_not_treated_as_a_collection(self):
        for key in self.COLLECTION_KEYS:
            with self.subTest(key=key):
                with self.assertRaises(ValidationError) as ctx:
                    normalize_graph_payload({key: "abc"})
                message = str(ctx.exception)
                self.assertIn(f"'{key}'", message)
                self.assertIn("str", message)

    def test_bytes_value_is_not_treated_as_a_collection(self):
        for value in (b"abc", bytearray(b"abc")):
            with self.subTest(value=repr(value)):
                with self.assertRaises(ValidationError):
                    normalize_graph_payload({"entities": value})

    def test_scalar_value_raises_validation_error_not_type_error(self):
        for key in self.COLLECTION_KEYS:
            for value in (42, 3.5, True, object()):
                with self.subTest(key=key, value=repr(value)):
                    with self.assertRaises(ValidationError) as ctx:
                        normalize_graph_payload({key: value})
                    self.assertIn(f"'{key}'", str(ctx.exception))

    def test_mapping_value_is_not_treated_as_a_collection(self):
        """``{"nodes": {"id": "n1"}}`` -- a single record, or an ID index."""
        for payload in (
            {"nodes": {"id": "n1"}},
            {"entities": {"e1": ENTITY}},
            {"edges": {"id": "r1"}},
        ):
            with self.subTest(payload=payload):
                with self.assertRaises(ValidationError) as ctx:
                    normalize_graph_payload(payload)
                self.assertIn("mapping", str(ctx.exception))

    def test_non_record_elements_are_rejected(self):
        for value in (["Acme"], [ENTITY, "Acme"], [42], [None], [[ENTITY]]):
            with self.subTest(value=repr(value)):
                with self.assertRaises(ValidationError) as ctx:
                    normalize_graph_payload({"entities": value})
                self.assertIn("'entities'", str(ctx.exception))

    def test_error_names_the_offending_index(self):
        with self.assertRaises(ValidationError) as ctx:
            normalize_graph_payload({"entities": [ENTITY, ENTITY, "Acme"]})
        self.assertIn("index 2", str(ctx.exception))

    def test_object_records_are_accepted(self):
        """Attribute-bearing objects are accepted and converted to dicts.

        LPGExporter and ArangoAQLExporter read records with ``.get(...)``, so
        an object record that merely passed validation unconverted would
        still crash with AttributeError once used; the boundary converts it.
        """

        class Node:
            def __init__(self):
                self.id = "e1"
                self.name = "Acme"

        node = Node()
        result = normalize_graph_payload({"entities": [node]})
        self.assertEqual(result["entities"], [{"id": "e1", "name": "Acme"}])

    def test_dataclass_records_are_accepted(self):
        @dataclass
        class Node:
            id: str

        node = Node(id="e1")
        result = normalize_graph_payload({"entities": [node]})
        self.assertEqual(result["entities"], [{"id": "e1"}])

    def test_tuple_collections_are_accepted_and_materialized(self):
        result = normalize_graph_payload({"entities": (ENTITY,)})
        self.assertEqual(result["entities"], [ENTITY])

    def test_none_is_read_as_an_absent_collection(self):
        """JSON round-trips an absent collection to null."""
        result = normalize_graph_payload(
            {"entities": None, "relationships": [RELATIONSHIP]}
        )
        self.assertEqual(result["entities"], [])
        self.assertEqual(result["relationships"], [RELATIONSHIP])

    def test_null_collection_still_cannot_hide_dropped_records(self):
        with self.assertRaises(ValidationError):
            normalize_graph_payload({"entities": None, "data": [ENTITY]})

    def test_every_spelling_is_validated_not_just_the_winner(self):
        """A malformed alias is a defect even when the canonical key resolves."""
        with self.assertRaises(ValidationError) as ctx:
            normalize_graph_payload({"entities": [ENTITY], "nodes": "abc"})
        self.assertIn("'nodes'", str(ctx.exception))

    def test_malformed_value_reaches_no_exporter(self):
        """The end-to-end half: no exporter sees a TypeError from list()."""
        tmpdir = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, tmpdir, ignore_errors=True)

        for name in self.NORMALIZING_EXPORTERS:
            for value in ("abc", 42, {"id": "n1"}):
                with self.subTest(exporter=name, value=repr(value)):
                    outdir = os.path.join(tmpdir, f"{name}_{type(value).__name__}")
                    os.makedirs(outdir, exist_ok=True)
                    with self.assertRaises(ValidationError):
                        getattr(export_methods, name)(
                            {"entities": value}, os.path.join(outdir, "out")
                        )


class TestIsRecordBoundary(unittest.TestCase):
    """_is_record gates the validation boundary introduced by this PR.

    Modules and class/type objects carry ``__dict__`` but are not graph
    records.  Passing them through previously produced ``AttributeError``
    inside exporters rather than a ``ValidationError`` at the boundary.
    """

    def test_python_module_in_entities_raises_validation_error(self):
        """import math; {"entities": [math]} must be rejected at the boundary."""
        import math

        with self.assertRaises(ValidationError) as ctx:
            normalize_graph_payload({"entities": [math]})
        self.assertIn("'entities'", str(ctx.exception))

    def test_class_object_in_entities_raises_validation_error(self):
        """A class (type object) is not a graph record."""

        class MyNode:
            pass

        with self.assertRaises(ValidationError) as ctx:
            normalize_graph_payload({"entities": [MyNode]})
        self.assertIn("'entities'", str(ctx.exception))

    def test_user_defined_instance_with_attributes_is_accepted(self):
        """Attribute-bearing instances are the legitimate use-case, converted
        to a dict so every exporter -- not just Neo4jCSVExporter -- can read
        it with ``.get(...)``."""

        class Node:
            def __init__(self):
                self.id = "n1"
                self.name = "Alice"

        node = Node()
        result = normalize_graph_payload({"entities": [node]})
        self.assertEqual(result["entities"], [{"id": "n1", "name": "Alice"}])

    def test_dataclass_instance_is_accepted(self):
        """Dataclasses are a common record type used by Neo4jCSVExporter,
        converted to a dict at the boundary so LPGExporter and
        ArangoAQLExporter can read it too."""
        node = dataclass_node()
        result = normalize_graph_payload({"entities": [node]})
        self.assertEqual(result["entities"], [{"id": "dc1"}])

    def test_mapping_record_is_accepted(self):
        """Plain dicts are the canonical record shape."""
        result = normalize_graph_payload({"entities": [ENTITY]})
        self.assertEqual(result["entities"], [ENTITY])

    def test_module_rejected_through_normalizing_exporter(self):
        """End-to-end: a module element must not reach an exporter's internals."""
        import math

        tmpdir = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, tmpdir, ignore_errors=True)

        for name in ("export_arango", "export_neo4j_csv", "export_lpg"):
            with self.subTest(exporter=name):
                outdir = os.path.join(tmpdir, name)
                os.makedirs(outdir, exist_ok=True)
                with self.assertRaises(ValidationError):
                    getattr(export_methods, name)(
                        {"entities": [math]}, os.path.join(outdir, "out")
                    )


@dataclass
class _DataclassNode:
    id: str


def dataclass_node():
    return _DataclassNode(id="dc1")


if __name__ == "__main__":
    unittest.main()
