"""Tests for Neo4j bulk CSV export."""

import csv
from pathlib import Path

import pytest

from semantica.export import Neo4jCSVExporter
from semantica.export.methods import export_knowledge_graph, export_neo4j_csv
from semantica.kg.knowledge_graph import KnowledgeGraph
from semantica.utils.exceptions import ValidationError


def _read_csv(path: Path):
    with open(path, "r", encoding="utf-8", newline="") as handle:
        return list(csv.reader(handle))


def _sample_graph():
    return {
        "entities": [
            {
                "id": "2",
                "labels": ["Person", "Engineer"],
                "name": "Alice",
                "type": "user",
                "properties": {
                    "age": 30,
                    "email": "alice@example.com",
                },
            },
            {
                "id": "1",
                "type": "Company",
                "name": "Acme, Inc.",
                "properties": {"founded": 2024},
            },
            {
                "text": "No ID concept",
                "type": "Concept",
                "properties": {
                    "empty": "",
                    "quote": 'He said "hello"',
                    "unicode": "東京",
                },
            },
        ],
        "relationships": [
            {
                "source": "2",
                "target": "1",
                "type": "WORKS_FOR",
                "properties": {"role": "Engineer", "since": 2024},
            },
            {
                "source": "Alice",
                "target": "Acme, Inc.",
                "relationship_type": "KNOWS",
                "properties": {"note": 'line1\nline2, "quoted"'},
            },
        ],
    }


def test_header_correctness_and_node_csv_structure(tmp_path):
    exporter = Neo4jCSVExporter()
    exporter.export_knowledge_graph(_sample_graph(), tmp_path)

    rows = _read_csv(tmp_path / "nodes.csv")

    assert rows[0] == [
        ":id",
        ":LABEL",
        "age",
        "email",
        "empty",
        "founded",
        "name",
        "quote",
        "text",
        "type",
        "unicode",
    ]

    by_id = {row[0]: row for row in rows[1:]}
    assert list(by_id) == sorted(by_id)
    assert by_id["2"][1] == "Person;Engineer"
    assert by_id["2"][2] == "30"
    assert by_id["2"][6] == "Alice"
    assert by_id["2"][9] == "user"
    assert by_id["1"][1] == "Company"
    assert by_id["1"][2] == ""
    assert by_id["1"][5] == "2024"

    derived_ids = [node_id for node_id in by_id if node_id.startswith("n_")]
    assert len(derived_ids) == 1
    derived_row = by_id[derived_ids[0]]
    assert derived_row[4] == ""
    assert derived_row[7] == 'He said "hello"'
    assert derived_row[8] == "No ID concept"
    assert derived_row[10] == "東京"


def test_relationship_csv_structure_and_properties(tmp_path):
    exporter = Neo4jCSVExporter()
    exporter.export(_sample_graph(), tmp_path)

    rows = _read_csv(tmp_path / "relationships.csv")

    assert rows[0] == [":START_ID", ":END_ID", ":TYPE", "note", "role", "since"]
    assert rows[1] == ["2", "1", "KNOWS", 'line1\nline2, "quoted"', "", ""]
    assert rows[2] == ["2", "1", "WORKS_FOR", "", "Engineer", "2024"]


def test_missing_properties_create_empty_cells(tmp_path):
    exporter = Neo4jCSVExporter()
    exporter.export(
        {
            "nodes": [
                {"id": "a", "type": "Thing", "properties": {"optional": "present"}},
                {"id": "b", "type": "Thing"},
            ],
            "edges": [{"source": "a", "target": "b", "type": "RELATED"}],
        },
        tmp_path,
    )

    rows = _read_csv(tmp_path / "nodes.csv")
    optional_index = rows[0].index("optional")
    by_id = {row[0]: row for row in rows[1:]}

    assert by_id["a"][optional_index] == "present"
    assert by_id["b"][optional_index] == ""


def test_deterministic_output_with_permuted_graph(tmp_path):
    graph_a = {
        "entities": [
            {"name": "Bob", "type": "Person"},
            {"name": "Alice", "type": "Person"},
        ],
        "relationships": [
            {"source": "Alice", "target": "Bob", "type": "KNOWS"},
        ],
    }
    graph_b = {
        "entities": list(reversed(graph_a["entities"])),
        "relationships": list(reversed(graph_a["relationships"])),
    }

    exporter = Neo4jCSVExporter()
    out_a = tmp_path / "a"
    out_b = tmp_path / "b"

    exporter.export(graph_a, out_a)
    exporter.export(graph_b, out_b)

    assert (out_a / "nodes.csv").read_text(encoding="utf-8") == (
        out_b / "nodes.csv"
    ).read_text(encoding="utf-8")
    assert (out_a / "relationships.csv").read_text(encoding="utf-8") == (
        out_b / "relationships.csv"
    ).read_text(encoding="utf-8")


def test_csv_quoting_escaping_and_unicode(tmp_path):
    exporter = Neo4jCSVExporter()
    exporter.export(_sample_graph(), tmp_path)

    nodes_text = (tmp_path / "nodes.csv").read_text(encoding="utf-8")
    relationships_text = (tmp_path / "relationships.csv").read_text(encoding="utf-8")

    assert '"Acme, Inc."' in nodes_text
    assert '"He said ""hello"""' in nodes_text
    assert "東京" in nodes_text
    assert '"line1\nline2, ""quoted"""' in relationships_text

    assert _read_csv(tmp_path / "nodes.csv")
    assert _read_csv(tmp_path / "relationships.csv")


def test_empty_graph_export_writes_importable_headers(tmp_path):
    exporter = Neo4jCSVExporter()
    exporter.export({"entities": [], "relationships": []}, tmp_path)

    assert _read_csv(tmp_path / "nodes.csv") == [[":id", ":LABEL"]]
    assert _read_csv(tmp_path / "relationships.csv") == [
        [":START_ID", ":END_ID", ":TYPE"]
    ]

    validation = exporter.validate_export(tmp_path)
    assert validation == {"valid": True, "errors": []}


def test_dry_run_and_written_validation(tmp_path):
    exporter = Neo4jCSVExporter()
    summary = exporter.dry_run(_sample_graph())

    assert summary["valid"] is True
    assert summary["node_count"] == 3
    assert summary["relationship_count"] == 2
    assert summary["node_header"][:2] == [":id", ":LABEL"]
    assert summary["relationship_header"][:3] == [
        ":START_ID",
        ":END_ID",
        ":TYPE",
    ]

    exporter.export(_sample_graph(), tmp_path, validate=True)
    assert exporter.validate_export(tmp_path)["valid"] is True


def test_knowledge_graph_dataclass_and_convenience_wrappers(tmp_path):
    kg = KnowledgeGraph(
        entities=[
            {"id": "a", "type": "Person", "name": "Alice"},
            {"id": "b", "type": "Person", "name": "Bob"},
        ],
        relationships=[{"source": "a", "target": "b", "type": "KNOWS"}],
    )

    result = export_neo4j_csv(kg, tmp_path / "direct")
    assert result["nodes"].name == "nodes.csv"
    assert result["relationships"].name == "relationships.csv"
    assert result["nodes"].exists()

    export_knowledge_graph(kg, tmp_path / "unified", format="neo4j_csv")
    assert (tmp_path / "unified" / "nodes.csv").exists()
    assert (tmp_path / "unified" / "relationships.csv").exists()


def test_invalid_relationship_endpoint_fails_strict_validation(tmp_path):
    exporter = Neo4jCSVExporter()

    with pytest.raises(ValidationError):
        exporter.export(
            {
                "entities": [{"id": "a", "type": "Thing"}],
                "relationships": [
                    {"source": "a", "target": "missing", "type": "RELATED"}
                ],
            },
            tmp_path,
        )


def test_ambiguous_aliases_are_not_resolved(tmp_path):
    exporter = Neo4jCSVExporter()

    # Create two nodes with the same alias/name "Alice"
    graph = {
        "entities": [
            {"id": "node1", "name": "Alice", "type": "Person"},
            {"id": "node2", "name": "Alice", "type": "Person"},
        ],
        "relationships": [{"source": "Alice", "target": "node1", "type": "KNOWS"}],
    }

    # Verify that strict export raises ValidationError because the alias is ambiguous
    with pytest.raises(ValidationError):
        exporter.export(graph, tmp_path)


def test_duplicate_node_ids_fail_validation(tmp_path):
    exporter = Neo4jCSVExporter()

    # Create two nodes with the same explicit ID
    graph = {
        "entities": [
            {"id": "node1", "name": "Alice", "type": "Person"},
            {"id": "node1", "name": "Bob", "type": "Person"},
        ],
        "relationships": [],
    }

    # Verify duplicate explicit node IDs raise ValidationError
    with pytest.raises(ValidationError):
        exporter.export(graph, tmp_path)


def test_nested_properties_are_json_serialized(tmp_path):
    exporter = Neo4jCSVExporter()

    graph = {
        "entities": [
            {
                "id": "node1",
                "type": "Person",
                "properties": {"nested_dict": {"k": "v"}, "nested_list": [1, 2, 3]},
            }
        ],
        "relationships": [],
    }

    exporter.export(graph, tmp_path)

    rows = _read_csv(tmp_path / "nodes.csv")
    assert rows[0] == [":id", ":LABEL", "nested_dict", "nested_list", "type"]

    # Verify that the nested properties are serialized as deterministic JSON strings
    by_id = {row[0]: row for row in rows[1:]}
    assert by_id["node1"][2] == '{"k":"v"}'
    assert by_id["node1"][3] == "[1,2,3]"
