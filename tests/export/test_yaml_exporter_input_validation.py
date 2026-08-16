"""Regression tests for YAML export input validation (issue #952).

``export_yaml`` declared ``Union[Dict[str, Any], List[Dict[str, Any]]]`` but
both YAML exporters read their payload by key, so a list reached
``semantic_network.get(...)`` and surfaced as a bare
``AttributeError: 'list' object has no attribute 'get'`` from inside the
exporter — an error that names neither the offending argument nor the shape
expected.

A list is rejected rather than wrapped. These formats distinguish entities
from relationships from triplets, so inferring which collection a bare list
represents would silently mislabel the records; and wrapping it under an
unrecognised key would write a structurally valid file with every collection
empty, trading a loud failure for silent data loss.

Both directions are pinned: non-mappings raise ``ProcessingError`` with an
actionable message, and every mapping that worked before still exports.
"""

import os
import shutil
import tempfile
import unittest
from collections import OrderedDict, defaultdict

import yaml

from semantica.export.methods import export_yaml
from semantica.export.yaml_exporter import (
    SemanticNetworkYAMLExporter,
    YAMLSchemaExporter,
)
from semantica.utils.exceptions import ProcessingError

# Non-mapping payloads that must be rejected. A list of dicts is the shape
# from #952; the rest guard the same path against other sequence/scalar types.
NON_MAPPINGS = {
    "list_of_dicts": [{"id": "1", "name": "Acme"}],
    "empty_list": [],
    "tuple_of_dicts": ({"id": "1"},),
    "list_of_scalars": ["a", "b"],
    "string": "entities",
    "bytes": b"entities",
    "int": 42,
    "none": None,
    "set": {"a"},
}

# Both YAML methods, with a minimal valid payload and the key names the
# corresponding error message must mention.
METHODS = {
    "semantic_network": {
        "valid": {
            "entities": [{"id": "1", "name": "Acme"}],
            "relationships": [],
            "triplets": [],
        },
        "expected_key": "entities",
        "top_level_key": "entities",
    },
    "schema": {
        "valid": {"classes": [{"name": "Thing"}], "properties": []},
        "expected_key": "classes",
        "top_level_key": "classes",
    },
}


class TestExportYamlRejectsNonMappings(unittest.TestCase):
    """Non-mapping input fails loudly, through the public wrapper."""

    def setUp(self):
        self.tmpdir = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, self.tmpdir, ignore_errors=True)

    def _path(self, name="out.yaml"):
        return os.path.join(self.tmpdir, name)

    def test_fixture_tables_are_populated(self):
        """Guard against a vacuous suite.

        Every test below iterates a table; emptying or renaming one would let
        those loops pass without asserting anything.
        """
        self.assertGreaterEqual(len(NON_MAPPINGS), 9)
        self.assertEqual(set(METHODS), {"semantic_network", "schema"})

    def test_non_mapping_raises_processing_error(self):
        for method in METHODS:
            for label, payload in NON_MAPPINGS.items():
                with self.subTest(method=method, case=label):
                    with self.assertRaises(ProcessingError):
                        export_yaml(payload, self._path(), method=method)

    def test_error_names_the_offending_type_and_expected_keys(self):
        """The message must be actionable, not just the right exception type."""
        for method, spec in METHODS.items():
            with self.subTest(method=method):
                with self.assertRaises(ProcessingError) as ctx:
                    export_yaml([{"id": "1"}], self._path(), method=method)
                message = str(ctx.exception)
                self.assertIn("list", message)
                self.assertIn(spec["expected_key"], message)

    def test_no_file_is_written_when_input_is_rejected(self):
        """A rejected export must not leave a partial or empty artefact."""
        for method in METHODS:
            with self.subTest(method=method):
                path = self._path(f"{method}_rejected.yaml")
                with self.assertRaises(ProcessingError):
                    export_yaml([{"id": "1"}], path, method=method)
                self.assertFalse(os.path.exists(path))

    def test_exporter_classes_reject_non_mappings_directly(self):
        """Validation lives in the exporters, not only the convenience wrapper.

        Callers using the classes directly get the same contract.
        """
        for label, payload in NON_MAPPINGS.items():
            with self.subTest(exporter="SemanticNetworkYAMLExporter", case=label):
                with self.assertRaises(ProcessingError):
                    SemanticNetworkYAMLExporter().export_semantic_network(payload)
            with self.subTest(exporter="YAMLSchemaExporter", case=label):
                with self.assertRaises(ProcessingError):
                    YAMLSchemaExporter().export_ontology_schema(payload)


class TestExportYamlStillAcceptsMappings(unittest.TestCase):
    """Everything that exported before must still export."""

    def setUp(self):
        self.tmpdir = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, self.tmpdir, ignore_errors=True)

    def _path(self, name="out.yaml"):
        return os.path.join(self.tmpdir, name)

    def _load(self, path):
        with open(path, encoding="utf-8") as handle:
            return yaml.safe_load(handle)

    def test_valid_mapping_exports_for_each_method(self):
        for method, spec in METHODS.items():
            with self.subTest(method=method):
                path = self._path(f"{method}.yaml")
                export_yaml(spec["valid"], path, method=method)
                self.assertTrue(os.path.exists(path))
                loaded = self._load(path)
                self.assertIn(spec["top_level_key"], loaded)

    def test_semantic_network_records_survive_the_round_trip(self):
        path = self._path("network.yaml")
        export_yaml(METHODS["semantic_network"]["valid"], path)
        loaded = self._load(path)
        self.assertEqual(loaded["entities"], [{"id": "1", "name": "Acme"}])

    def test_empty_mapping_is_still_accepted(self):
        """An empty dict is a mapping; rejecting it would be a behaviour change."""
        for method in METHODS:
            with self.subTest(method=method):
                path = self._path(f"{method}_empty.yaml")
                export_yaml({}, path, method=method)
                self.assertTrue(os.path.exists(path))

    def test_mapping_subclasses_are_accepted(self):
        """Validation is by Mapping, not dict, so these must keep working."""
        valid = METHODS["semantic_network"]["valid"]
        subclasses = {
            "OrderedDict": OrderedDict(valid),
            "defaultdict": defaultdict(list, valid),
        }
        for label, payload in subclasses.items():
            with self.subTest(case=label):
                path = self._path(f"{label}.yaml")
                export_yaml(payload, path)
                loaded = self._load(path)
                self.assertEqual(loaded["entities"], valid["entities"])


if __name__ == "__main__":
    unittest.main()
