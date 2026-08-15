"""Tests for YAML export key recognition (issue #953).

``SemanticNetworkYAMLExporter`` built its output from ``.get(key, [])``
lookups, so a mapping keyed by anything it did not read -- an ``export_json``
envelope, a typo'd 'entitys', ``ContextGraph.to_dict()``'s 'nodes'/'edges' --
serialized to a structurally valid file with every collection empty. Nothing
signalled the loss: no exception, no warning, and the progress log reported a
completed export. ``YAMLSchemaExporter`` had the same defect over a different
key set.

The exporters are run for real rather than mocked, and the written files are
parsed back, since the behaviour under test is what actually lands on disk.
"""

from pathlib import Path

import pytest
import yaml

from semantica.context.context_graph import ContextGraph
from semantica.export.methods import export_json, export_yaml
from semantica.export.yaml_exporter import (
    SemanticNetworkYAMLExporter,
    YAMLSchemaExporter,
)
from semantica.utils.exceptions import ProcessingError, ValidationError

ENTITIES = [{"id": "e1", "name": "Acme"}, {"id": "e2", "name": "Beta"}]
RELATIONSHIPS = [{"id": "r1", "source": "e1", "target": "e2", "type": "PARTNER"}]
TRIPLETS = [{"subject": "e1", "predicate": "partner_of", "object": "e2"}]


def _load(path):
    with open(path, "r", encoding="utf-8") as handle:
        return yaml.safe_load(handle)


class TestSemanticNetworkKeyRecognition:
    """An unrecognized mapping is refused instead of silently emptied."""

    def test_export_json_envelope_is_rejected(self, tmp_path):
        """The realistic trigger: re-exporting an export_json payload.

        ``export_json`` wraps records as ``{"data": [...], "count": N,
        "metadata": {...}}``. Feeding that straight to ``export_yaml`` used to
        write a file with every record gone. Note the envelope's 'metadata'
        key is deliberately not enough to make the payload recognized --
        treating it as sufficient would readmit exactly this case.
        """
        json_path = tmp_path / "records.json"
        export_json(ENTITIES, json_path)
        envelope = yaml.safe_load(json_path.read_text(encoding="utf-8"))
        assert "data" in envelope and "metadata" in envelope

        yaml_path = tmp_path / "records.yaml"
        with pytest.raises(ValidationError) as excinfo:
            export_yaml(envelope, yaml_path)

        message = str(excinfo.value)
        assert "'data'" in message, "error should name the supplied keys"
        assert "'entities'" in message, "error should name the expected keys"
        assert not yaml_path.exists(), "a rejected export must write nothing"

    @pytest.mark.parametrize(
        "payload",
        [
            {"records": ENTITIES},
            {"entitys": ENTITIES},
            {"data": ENTITIES},
            {"metadata": {"source": "test"}},
        ],
        ids=["records", "typo", "data", "metadata-only"],
    )
    def test_unrecognized_mappings_are_rejected(self, payload):
        exporter = SemanticNetworkYAMLExporter()
        with pytest.raises(ValidationError):
            exporter.export_semantic_network(payload)

    @pytest.mark.parametrize(
        "payload",
        [
            {"entities": [], "data": ENTITIES},
            {"nodes": [], "edges": [], "records": ENTITIES},
            {"triplets": [], "data": ENTITIES, "metadata": {"source": "test"}},
        ],
        ids=["entities-empty", "nodes-edges-empty", "triplets-empty"],
    )
    def test_recognized_but_empty_with_records_elsewhere_is_rejected(self, payload):
        """Presence of a recognized key is not proof the records survived.

        ``{"entities": [], "data": [...]}`` clears a presence-only check and
        still resolves to empty, dropping everything under 'data' -- the same
        silent-empty export by a narrower route.
        """
        exporter = SemanticNetworkYAMLExporter()
        with pytest.raises(ValidationError) as excinfo:
            exporter.export_semantic_network(payload)

        message = str(excinfo.value)
        assert "holds records" in message
        assert "'entities'" in message, "error should name where records belong"

    def test_empty_graph_with_non_record_keys_still_exports(self, tmp_path):
        """The rejection must key on dropped *records*, not on unread keys.

        ``ContextGraph.to_dict()`` always carries a populated 'statistics'
        dict, so an empty graph would be refused if any unread key counted.
        """
        graph = ContextGraph()
        path = tmp_path / "empty_graph.yaml"
        export_yaml(graph.to_dict(), path)

        written = _load(path)
        assert written["entities"] == []
        assert written["relationships"] == []

    def test_empty_mapping_still_exports(self, tmp_path):
        """An empty graph is legitimate and carries nothing that could be lost."""
        path = tmp_path / "empty.yaml"
        export_yaml({}, path)

        written = _load(path)
        assert written["entities"] == []
        assert written["relationships"] == []
        assert written["triplets"] == []

    def test_recognized_keys_still_export(self, tmp_path):
        path = tmp_path / "network.yaml"
        export_yaml(
            {
                "entities": ENTITIES,
                "relationships": RELATIONSHIPS,
                "triplets": TRIPLETS,
                "metadata": {"source": "test"},
            },
            path,
        )

        written = _load(path)
        assert written["entities"] == ENTITIES
        assert written["relationships"] == RELATIONSHIPS
        assert written["triplets"] == TRIPLETS
        assert written["metadata"]["source"] == "test"

    def test_nodes_edges_alias_exports_records(self, tmp_path):
        path = tmp_path / "aliased.yaml"
        export_yaml({"nodes": ENTITIES, "edges": RELATIONSHIPS}, path)

        written = _load(path)
        assert written["entities"] == ENTITIES
        assert written["relationships"] == RELATIONSHIPS

    def test_context_graph_to_dict_round_trips(self, tmp_path):
        """The most direct path from this library's own graph type to YAML.

        Built from a real ``ContextGraph`` rather than a hand-written
        'nodes'/'edges' dict, so the test breaks if ``to_dict()`` changes
        vocabulary.
        """
        graph = ContextGraph()
        graph.add_node("n1", node_type="Person", content="Alice")
        graph.add_node("n2", node_type="Org", content="Acme")
        graph.add_edge("n1", "n2", "WORKS_FOR")

        path = tmp_path / "context.yaml"
        export_yaml(graph.to_dict(), path)

        written = _load(path)
        assert len(written["entities"]) == 2
        assert len(written["relationships"]) == 1

    def test_conflicting_spellings_are_refused(self):
        """Two populated spellings of one collection: no basis to pick either."""
        exporter = SemanticNetworkYAMLExporter()
        with pytest.raises(ValidationError):
            exporter.export_semantic_network(
                {"entities": ENTITIES, "nodes": [{"id": "other"}]}
            )

    def test_non_mapping_raises_processing_error(self):
        """A wrong type is a different failure from a wrong-keyed mapping.

        ProcessingError says the object cannot be exported at all;
        ValidationError says the mapping's contents are unusable. Pinned here
        so the two do not quietly converge.
        """
        exporter = SemanticNetworkYAMLExporter()
        with pytest.raises(ProcessingError):
            exporter.export_semantic_network(ENTITIES)

    def test_rejected_export_creates_no_output_directory(self, tmp_path):
        """Validation runs before the output directory is created."""
        target = tmp_path / "nested" / "out.yaml"
        exporter = SemanticNetworkYAMLExporter()

        with pytest.raises(ValidationError):
            exporter.export({"data": ENTITIES}, target)

        assert not target.parent.exists()


class TestPipelineExportKeyRecognition:
    """export_for_pipeline read the same defaulted lookups, so it had the bug too."""

    def test_unrecognized_mapping_is_rejected(self):
        exporter = SemanticNetworkYAMLExporter()
        with pytest.raises(ValidationError):
            exporter.export_for_pipeline({"data": ENTITIES})

    def test_non_mapping_raises_processing_error(self):
        exporter = SemanticNetworkYAMLExporter()
        with pytest.raises(ProcessingError):
            exporter.export_for_pipeline(ENTITIES)

    def test_aliases_resolve_into_the_semantic_network(self):
        exporter = SemanticNetworkYAMLExporter()
        written = yaml.safe_load(
            exporter.export_for_pipeline({"nodes": ENTITIES, "edges": RELATIONSHIPS})
        )

        assert written["semantic_network"]["entities"] == ENTITIES
        assert written["semantic_network"]["relationships"] == RELATIONSHIPS

    def test_metadata_is_preserved(self):
        exporter = SemanticNetworkYAMLExporter()
        written = yaml.safe_load(
            exporter.export_for_pipeline(
                {"entities": ENTITIES, "metadata": {"source": "test"}}
            )
        )

        assert written["metadata"]["source"] == "test"
        assert written["semantic_network"]["entities"] == ENTITIES


class TestSchemaKeyRecognition:
    """method="schema" emitted empty classes/properties/namespaces the same way."""

    def test_unrecognized_mapping_is_rejected(self, tmp_path):
        path = tmp_path / "schema.yaml"
        with pytest.raises(ValidationError) as excinfo:
            export_yaml({"nodes": [{"id": "1"}]}, path, method="schema")

        message = str(excinfo.value)
        assert "'nodes'" in message
        assert "'classes'" in message
        assert not path.exists()

    def test_non_mapping_raises_processing_error(self):
        exporter = YAMLSchemaExporter()
        with pytest.raises(ProcessingError):
            exporter.export_ontology_schema([{"id": "1"}])

    def test_recognized_but_empty_with_records_elsewhere_is_rejected(self):
        """The schema path had the same presence-only hole."""
        exporter = YAMLSchemaExporter()
        with pytest.raises(ValidationError) as excinfo:
            exporter.export_ontology_schema({"classes": [], "nodes": [{"id": "1"}]})

        assert "holds records" in str(excinfo.value)

    def test_ontology_metadata_without_records_still_exports(self):
        """A schema described only by its identity is not a dropped export."""
        exporter = YAMLSchemaExporter()
        written = yaml.safe_load(
            exporter.export_ontology_schema(
                {"uri": "http://example.org/o", "classes": []}
            )
        )

        assert written["ontology"]["uri"] == "http://example.org/o"
        assert written["classes"] == []

    def test_empty_mapping_still_exports(self, tmp_path):
        path = tmp_path / "schema.yaml"
        export_yaml({}, path, method="schema")

        written = _load(path)
        assert written["classes"] == []
        assert written["properties"] == []
        assert written["namespaces"] == {}

    @pytest.mark.parametrize(
        "payload",
        [
            {"classes": ["Person"], "properties": ["WORKS_FOR"]},
            {"namespaces": {"ex": "http://example.org/"}},
            {"uri": "http://example.org/ontology"},
        ],
        ids=["classes-properties", "namespaces-only", "uri-only"],
    )
    def test_recognized_keys_still_export(self, payload, tmp_path):
        path = tmp_path / "schema.yaml"
        export_yaml(payload, path, method="schema")

        written = _load(path)
        assert written["classes"] == payload.get("classes", [])
        assert written["properties"] == payload.get("properties", [])
        assert written["ontology"]["uri"] == payload.get("uri", "")

    # ── Fix regression: scalar recognized keys must not short-circuit the ──
    # ── dropped-records check (version, uri, title, description). ──────────

    @pytest.mark.parametrize(
        "scalar_key, scalar_value",
        [
            ("version", "1.0"),
            ("uri", "http://example.org/ontology"),
            ("title", "My Ontology"),
            ("description", "A test ontology"),
        ],
        ids=["version", "uri", "title", "description"],
    )
    def test_scalar_recognized_key_does_not_excuse_records_under_unread_key(
        self, scalar_key, scalar_value
    ):
        """A truthy scalar such as version='1.0' must not silence the dropped-
        records check.  Before the fix, any truthy value from _SCHEMA_KEYS
        would make _require_nothing_dropped believe something resolved and
        return early, silently discarding a list under an unread key.
        """
        exporter = YAMLSchemaExporter()
        with pytest.raises(ValidationError) as excinfo:
            exporter.export_ontology_schema(
                {scalar_key: scalar_value, "nodes": [{"id": "c1"}]}
            )
        assert "holds records" in str(excinfo.value), str(excinfo.value)

    def test_valid_classes_with_scalar_metadata_is_accepted(self):
        """classes/properties populated alongside version/uri must still work."""
        exporter = YAMLSchemaExporter()
        written = yaml.safe_load(
            exporter.export_ontology_schema(
                {
                    "classes": [{"id": "Person"}],
                    "properties": [{"id": "name"}],
                    "version": "2.0",
                    "uri": "http://example.org/o",
                }
            )
        )
        assert written["classes"] == [{"id": "Person"}]
        assert written["properties"] == [{"id": "name"}]
        assert written["ontology"]["version"] == "2.0"
        assert written["ontology"]["uri"] == "http://example.org/o"


class TestFailureIsObservable:
    """The complaint in #953 was that the logs affirmatively reported success."""

    def test_no_success_is_logged_for_a_rejected_export(self, tmp_path, caplog):
        path = tmp_path / "out.yaml"

        with caplog.at_level("DEBUG"):
            with pytest.raises(ValidationError):
                export_yaml({"data": ENTITIES}, path)

        assert "Exported YAML to" not in caplog.text
        assert any(
            record.levelname in ("WARNING", "ERROR", "CRITICAL")
            for record in caplog.records
        ), "a rejected export should leave something at warning or above"


class _RecordingTracker:
    """Records the exporter's own progress calls, which are what is under test."""

    def __init__(self):
        self.stopped = []
        self._next_id = 0

    def start_tracking(self, **kwargs):
        self._next_id += 1
        return str(self._next_id)

    def update_tracking(self, tracking_id, **kwargs):
        pass

    def stop_tracking(self, tracking_id, status=None, message=None):
        self.stopped.append((status, message))


class TestProgressReflectsTheWrite:
    """Serialization completing is not the same as the file landing on disk."""

    def test_failed_write_is_not_reported_as_completed(self, tmp_path):
        """A write failure after serialization must not leave a clean tracker.

        The path's parent is an existing *file*, so directory creation fails
        after `export_semantic_network` has already reported its own
        completion.
        """
        blocker = tmp_path / "blocker"
        blocker.write_text("not a directory", encoding="utf-8")
        target = blocker / "nested" / "out.yaml"

        exporter = SemanticNetworkYAMLExporter()
        tracker = _RecordingTracker()
        exporter.progress_tracker = tracker

        with pytest.raises(OSError):
            exporter.export({"entities": ENTITIES}, target)

        assert not target.exists()
        statuses = [status for status, _ in tracker.stopped]
        assert "failed" in statuses, f"write failure went unreported: {tracker.stopped}"
        assert not any(
            status == "completed" and "Exported YAML" in (message or "")
            for status, message in tracker.stopped
        ), "no span may claim a completed export when nothing was written"

    def test_successful_write_is_reported_as_completed(self, tmp_path):
        target = tmp_path / "out.yaml"
        exporter = SemanticNetworkYAMLExporter()
        tracker = _RecordingTracker()
        exporter.progress_tracker = tracker

        exporter.export({"entities": ENTITIES}, target)

        assert target.exists()
        assert all(status == "completed" for status, _ in tracker.stopped)
        assert any(
            "Exported YAML" in (message or "") for _, message in tracker.stopped
        ), "the write should report its own completion, not just serialization"


class TestUnaffectedExporters:
    """export_json's own behaviour is untouched -- only the YAML path changed."""

    def test_export_json_still_accepts_a_bare_list(self, tmp_path):
        path = tmp_path / "records.json"
        export_json(ENTITIES, path)

        assert Path(path).exists()
