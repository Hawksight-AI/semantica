"""Tests for YAML exporter input handling (issues #952, #953).

Issue #952: export_yaml raised AttributeError on List[Dict], a type its own
            signature declares as supported.
Issue #953: export_yaml silently wrote an empty export when the input dict
            lacked its expected keys, with no warning and a success log.
"""

import logging

import pytest
import yaml

from semantica.export import SemanticNetworkYAMLExporter, YAMLSchemaExporter
from semantica.export.methods import export_yaml
from semantica.utils.exceptions import ValidationError


@pytest.fixture
def rows():
    return [{"id": "1", "name": "Acme"}, {"id": "2", "name": "Beta"}]


@pytest.fixture
def network():
    return {
        "entities": [{"id": "1", "name": "Acme"}],
        "relationships": [{"source": "1", "target": "2", "type": "knows"}],
        "triplets": [{"subject": "Acme", "predicate": "knows", "object": "Beta"}],
    }


# ---------------------------------------------------------------------------
# Issue #952: list input must not crash either dispatch method
# ---------------------------------------------------------------------------


class TestListInput:
    def test_semantic_network_method_accepts_list(self, tmp_path, rows):
        out = tmp_path / "out.yaml"
        export_yaml(rows, out)
        data = yaml.safe_load(out.read_text())
        assert data["entities"] == rows

    def test_schema_method_accepts_list(self, tmp_path, rows):
        out = tmp_path / "schema.yaml"
        export_yaml(rows, out, method="schema")
        data = yaml.safe_load(out.read_text())
        assert data["classes"] == rows

    def test_exporter_export_accepts_list(self, tmp_path, rows):
        out = tmp_path / "direct.yaml"
        SemanticNetworkYAMLExporter().export(rows, out)
        data = yaml.safe_load(out.read_text())
        assert data["entities"] == rows

    def test_export_semantic_network_returns_yaml_for_list(self, rows):
        result = SemanticNetworkYAMLExporter().export_semantic_network(rows)
        assert yaml.safe_load(result)["entities"] == rows

    def test_list_with_non_dict_items_raises_validation_error(self, tmp_path):
        with pytest.raises(ValidationError):
            export_yaml([{"id": "1"}, "not-a-dict"], tmp_path / "bad.yaml")

    def test_non_dict_non_list_raises_validation_error(self, tmp_path):
        with pytest.raises(ValidationError):
            export_yaml("not-a-dict", tmp_path / "bad.yaml")

    def test_schema_method_rejects_invalid_input(self, tmp_path):
        with pytest.raises(ValidationError):
            export_yaml(42, tmp_path / "bad.yaml", method="schema")


# ---------------------------------------------------------------------------
# Issue #953: unrecognized keys must not silently produce an empty export
# ---------------------------------------------------------------------------


class TestUnrecognizedKeysWarning:
    def test_semantic_network_warns_on_unrecognized_keys(self, tmp_path, caplog, rows):
        with caplog.at_level(logging.WARNING, logger="semantica.yaml_exporter"):
            export_yaml({"data": rows}, tmp_path / "out.yaml")
        assert any(
            "recognized keys" in record.message for record in caplog.records
        )

    def test_schema_warns_on_unrecognized_keys(self, tmp_path, caplog, rows):
        with caplog.at_level(logging.WARNING, logger="semantica.yaml_schema_exporter"):
            export_yaml({"data": rows}, tmp_path / "out.yaml", method="schema")
        assert any(
            "recognized keys" in record.message for record in caplog.records
        )

    def test_recognized_keys_do_not_warn(self, tmp_path, caplog, network):
        with caplog.at_level(logging.WARNING, logger="semantica.yaml_exporter"):
            export_yaml(network, tmp_path / "out.yaml")
        assert not any(
            "recognized keys" in record.message for record in caplog.records
        )

    def test_empty_dict_does_not_warn(self, tmp_path, caplog):
        with caplog.at_level(logging.WARNING, logger="semantica.yaml_exporter"):
            export_yaml({}, tmp_path / "out.yaml")
        assert not any(
            "recognized keys" in record.message for record in caplog.records
        )


# ---------------------------------------------------------------------------
# Regression: existing dict behavior is unchanged
# ---------------------------------------------------------------------------


class TestExistingBehavior:
    def test_dict_round_trip(self, tmp_path, network):
        out = tmp_path / "network.yaml"
        export_yaml(network, out)
        data = yaml.safe_load(out.read_text())
        assert data["entities"] == network["entities"]
        assert data["relationships"] == network["relationships"]
        assert data["triplets"] == network["triplets"]
        assert "exported_at" in data["metadata"]

    def test_metadata_is_merged(self, tmp_path, network):
        network["metadata"] = {"source": "unit-test"}
        out = tmp_path / "network.yaml"
        export_yaml(network, out)
        data = yaml.safe_load(out.read_text())
        assert data["metadata"]["source"] == "unit-test"
        assert "exported_at" in data["metadata"]

    def test_schema_dict_round_trip(self, tmp_path):
        ontology = {
            "uri": "http://example.org/onto",
            "title": "Test",
            "classes": [{"id": "Person"}],
            "properties": [{"id": "knows"}],
            "namespaces": {"ex": "http://example.org/"},
        }
        out = tmp_path / "schema.yaml"
        export_yaml(ontology, out, method="schema")
        data = yaml.safe_load(out.read_text())
        assert data["ontology"]["uri"] == "http://example.org/onto"
        assert data["classes"] == ontology["classes"]
        assert data["namespaces"] == ontology["namespaces"]

    def test_unknown_method_raises(self, tmp_path, network):
        from semantica.utils.exceptions import ProcessingError

        with pytest.raises(ProcessingError):
            export_yaml(network, tmp_path / "out.yaml", method="nonexistent")
