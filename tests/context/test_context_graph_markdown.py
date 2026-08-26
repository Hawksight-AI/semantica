import os
import stat
import subprocess
from pathlib import Path

import pytest
import yaml

import semantica.context.context_graph as context_graph_module
from semantica.change_management.managers import TemporalVersionManager
from semantica.context.context_graph import ContextEdge, ContextGraph, ContextNode


def _read_markdown(path: Path):
    lines = path.read_text(encoding="utf-8").splitlines(keepends=True)
    closing_index = next(
        index
        for index, line in enumerate(lines[1:], start=1)
        if line.rstrip("\r\n") == "---"
    )
    frontmatter = yaml.safe_load("".join(lines[1:closing_index])) or {}
    body = "".join(lines[closing_index + 1 :])
    if body.startswith("\r\n"):
        body = body[2:]
    elif body.startswith("\n"):
        body = body[1:]
    return frontmatter, body


def _write_markdown(path: Path, frontmatter, body: str) -> None:
    yaml_text = yaml.safe_dump(
        frontmatter,
        sort_keys=False,
        allow_unicode=True,
        default_flow_style=False,
    )
    path.write_text(f"---\n{yaml_text}---\n\n{body}", encoding="utf-8")


def _node_file(export_path: Path, node_id: str) -> Path:
    for path in (export_path / "nodes").glob("*.md"):
        frontmatter, _ = _read_markdown(path)
        if frontmatter.get("id") == node_id:
            return path
    raise AssertionError(f"No Markdown file found for node {node_id!r}")


def _normalized_state(graph: ContextGraph):
    links = {link_id: dict(link) for link_id, link in graph._unresolved_links.items()}
    for link_id, (
        other_graph,
        source_node_id,
        target_node_id,
    ) in graph._linked_graphs.items():
        links[link_id] = {
            "link_id": link_id,
            "source_node_id": source_node_id,
            "target_node_id": target_node_id,
            "other_graph_id": other_graph.graph_id,
        }
    return {
        "graph_id": graph.graph_id,
        "nodes": {
            node_id: {
                "type": node.node_type,
                "content": node.content,
                "properties": node.properties,
                "metadata": node.metadata,
                "valid_from": node.valid_from,
                "valid_until": node.valid_until,
            }
            for node_id, node in graph.nodes.items()
        },
        "edges": sorted(
            (
                {
                    "id": edge.edge_id,
                    "family_id": edge.family_id,
                    "source": edge.source_id,
                    "target": edge.target_id,
                    "type": edge.edge_type,
                    "weight": edge.weight,
                    "metadata": edge.metadata,
                    "valid_from": edge.valid_from,
                    "valid_until": edge.valid_until,
                }
                for edge in graph.edges
            ),
            key=lambda edge: edge["id"],
        ),
        "links": links,
    }


def _sample_graph():
    graph = ContextGraph(advanced_analytics=False)
    graph.graph_id = "graph-primary"
    graph._add_internal_node(
        ContextNode(
            node_id="policy/\u6771\u4eac",
            node_type="Policy",
            content="# Retention\n\nKeep evidence.\n---\n",
            properties={"priority": 2, "nested": {"owner": "governance"}},
            metadata={"source": "manual", "tags": ["retention", "legal"]},
            valid_from="2026-01-01T00:00:00+00:00",
            valid_until="2027-01-01T00:00:00+00:00",
        )
    )
    graph._add_internal_node(
        ContextNode(
            node_id="evidence-1",
            node_type="Evidence",
            content="Original source",
            properties={"checksum": "abc123"},
            metadata={"classification": "internal"},
        )
    )
    graph._add_internal_edge(
        ContextEdge(
            edge_id="edge-supports",
            family_id="family-supports",
            source_id="evidence-1",
            target_id="policy/\u6771\u4eac",
            edge_type="SUPPORTS",
            weight=0.75,
            metadata={"confidence": 0.9},
            valid_from="2026-02-01",
            valid_until="2026-12-31",
        )
    )

    other = ContextGraph(advanced_analytics=False)
    other.graph_id = "graph-secondary"
    other.add_node("source-page", "Page", "Source page")
    link_id = graph.link_graph(other, "policy/\u6771\u4eac", "source-page")
    return graph, other, link_id


def _directory_contents(path: Path):
    return {
        str(file_path.relative_to(path)): file_path.read_bytes()
        for file_path in path.rglob("*")
        if file_path.is_file()
    }


def test_markdown_round_trip_preserves_complete_graph_state(tmp_path):
    graph, other, link_id = _sample_graph()
    export_path = tmp_path / "context-graph"

    graph.save_to_file(export_path, format="markdown")

    restored = ContextGraph(advanced_analytics=False)
    restored.load_from_file(export_path, format="markdown")

    assert _normalized_state(restored) == _normalized_state(graph)
    assert restored.resolve_links({other.graph_id: other}) == 1
    linked_graph, entry_node = restored.navigate_to(link_id)
    assert linked_graph is other
    assert entry_node == "source-page"


def test_markdown_manual_node_and_edge_edits_are_imported(tmp_path):
    graph, _, _ = _sample_graph()
    export_path = tmp_path / "context-graph"
    graph.save_to_file(export_path, format="markdown")

    node_path = _node_file(export_path, "policy/\u6771\u4eac")
    node_frontmatter, _ = _read_markdown(node_path)
    node_frontmatter["metadata"]["reviewed"] = True
    _write_markdown(node_path, node_frontmatter, "# Updated policy\n")

    manifest_path = export_path / "graph.md"
    manifest, manifest_body = _read_markdown(manifest_path)
    manifest["edges"][0]["type"] = "VERIFIES"
    manifest["edges"][0]["weight"] = 1.0
    manifest["edges"][0]["metadata"]["reviewed_by"] = "human"
    _write_markdown(manifest_path, manifest, manifest_body)

    restored = ContextGraph(advanced_analytics=False)
    restored.load_from_file(export_path, format="markdown")

    node = restored.nodes["policy/\u6771\u4eac"]
    assert node.content == "# Updated policy\n"
    assert node.metadata["reviewed"] is True
    edge = restored.edges[0]
    assert edge.edge_type == "VERIFIES"
    assert edge.weight == 1.0
    assert edge.metadata["reviewed_by"] == "human"


def test_markdown_export_is_deterministic_and_removes_stale_nodes(tmp_path):
    graph = ContextGraph(advanced_analytics=False)
    graph.graph_id = "deterministic-graph"
    graph.add_node("kept", "Note", "Keep")
    graph.add_node("removed", "Note", "Remove")
    graph.add_edge("kept", "removed", "REFERENCES")
    first = tmp_path / "first"
    second = tmp_path / "second"

    graph.save_to_file(first, format="markdown")
    graph.save_to_file(second, format="markdown")
    assert _directory_contents(first) == _directory_contents(second)

    stale_path = _node_file(first, "removed")
    graph.nodes.pop("removed")
    graph.edges.clear()
    graph.save_to_file(first, format="markdown")

    assert not stale_path.exists()
    restored = ContextGraph(advanced_analytics=False)
    restored.load_from_file(first, format="markdown")
    assert set(restored.nodes) == {"kept"}
    assert restored.edges == []


def test_markdown_empty_graph_round_trip(tmp_path):
    graph = ContextGraph(advanced_analytics=False)
    graph.graph_id = "empty-graph"
    export_path = tmp_path / "empty"

    graph.save_to_file(export_path, format="markdown")
    restored = ContextGraph(advanced_analytics=False)
    restored.load_from_file(export_path, format="markdown")

    assert restored.graph_id == "empty-graph"
    assert restored.nodes == {}
    assert restored.edges == []


def test_markdown_export_rejects_duplicate_edge_ids_before_writing(tmp_path):
    graph = ContextGraph(advanced_analytics=False)
    graph.add_node("source", "Note", "Source")
    graph.add_node("target", "Note", "Target")
    graph.add_edge("source", "target", "REFERENCES")
    graph.edges.append(graph.edges[0])
    export_path = tmp_path / "graph"

    assert graph.edges[0].edge_id == graph.edges[1].edge_id
    with pytest.raises(ValueError, match=r"duplicate edge ID.*[0-9a-f-]+"):
        graph.save_to_file(export_path, format="markdown")

    assert not export_path.exists()


@pytest.mark.parametrize(
    "corruption, expected_error",
    [
        ("unsupported-version", "Unsupported ContextGraph Markdown version"),
        ("duplicate-edge", "Duplicate Markdown edge ID"),
        ("duplicate-node", "Duplicate Markdown node ID"),
        ("cyclic-skos", "SKOS hierarchy contains a cycle"),
    ],
)
def test_invalid_markdown_does_not_mutate_existing_graph(
    tmp_path, corruption, expected_error
):
    source, _, _ = _sample_graph()
    export_path = tmp_path / corruption
    source.save_to_file(export_path, format="markdown")

    manifest_path = export_path / "graph.md"
    manifest, manifest_body = _read_markdown(manifest_path)
    if corruption == "unsupported-version":
        manifest["version"] = 2
    elif corruption == "duplicate-edge":
        manifest["edges"].append(dict(manifest["edges"][0]))
    elif corruption == "duplicate-node":
        original = _node_file(export_path, "evidence-1")
        (original.parent / "duplicate.md").write_bytes(original.read_bytes())
    elif corruption == "cyclic-skos":
        manifest["edges"] = [
            {
                "id": "broader-1",
                "family_id": "broader-1",
                "source": "evidence-1",
                "target": "policy/\u6771\u4eac",
                "type": "skos:broader",
                "weight": 1.0,
                "metadata": {},
            },
            {
                "id": "broader-2",
                "family_id": "broader-2",
                "source": "policy/\u6771\u4eac",
                "target": "evidence-1",
                "type": "skos:broader",
                "weight": 1.0,
                "metadata": {},
            },
        ]
    _write_markdown(manifest_path, manifest, manifest_body)

    target = ContextGraph(advanced_analytics=False)
    target.add_node("sentinel", "Existing", "Do not replace")
    before = _normalized_state(target)

    with pytest.raises(ValueError, match=expected_error):
        target.load_from_file(export_path, format="markdown")

    assert _normalized_state(target) == before


def test_markdown_import_creates_json_compatible_stub_nodes_for_dangling_edges(
    tmp_path,
):
    source, _, _ = _sample_graph()
    export_path = tmp_path / "dangling-edge"
    source.save_to_file(export_path, format="markdown")
    manifest_path = export_path / "graph.md"
    manifest, manifest_body = _read_markdown(manifest_path)
    manifest["edges"][0]["target"] = "missing-node"
    _write_markdown(manifest_path, manifest, manifest_body)

    restored = ContextGraph(advanced_analytics=False)
    restored.load_from_file(export_path, format="markdown")

    stub = restored.nodes["missing-node"]
    assert stub.node_type == "entity"
    assert stub.content == "missing-node"
    assert any(edge.target_id == "missing-node" for edge in restored.edges)


@pytest.mark.parametrize(
    ("location", "field_name"),
    [("node", "valid_from"), ("edge", "valid_until")],
)
def test_invalid_markdown_temporal_value_does_not_mutate_existing_graph(
    tmp_path, location, field_name
):
    source, _, _ = _sample_graph()
    export_path = tmp_path / location
    source.save_to_file(export_path, format="markdown")

    if location == "node":
        document_path = _node_file(export_path, "policy/\u6771\u4eac")
    else:
        document_path = export_path / "graph.md"
    frontmatter, body = _read_markdown(document_path)
    if location == "node":
        frontmatter[field_name] = "not-a-date"
    else:
        frontmatter["edges"][0][field_name] = "not-a-date"
    _write_markdown(document_path, frontmatter, body)

    target = ContextGraph(advanced_analytics=False)
    target.add_node("sentinel", "Existing", "Do not replace")
    before = _normalized_state(target)

    with pytest.raises(ValueError, match=rf"'{field_name}'.*valid ISO-8601"):
        target.load_from_file(export_path, format="markdown")

    assert _normalized_state(target) == before


def test_duplicate_yaml_keys_are_rejected(tmp_path):
    graph = ContextGraph(advanced_analytics=False)
    graph.add_node("node-1", "Note", "Body")
    export_path = tmp_path / "graph"
    graph.save_to_file(export_path, format="markdown")
    node_path = _node_file(export_path, "node-1")
    document = node_path.read_text(encoding="utf-8")
    node_path.write_text(document.replace("id: node-1", "id: node-1\nid: duplicate"))

    with pytest.raises(ValueError, match="duplicate key 'id'"):
        ContextGraph(advanced_analytics=False).load_from_file(
            export_path, format="markdown"
        )


def test_markdown_export_refuses_unmanaged_nonempty_directory(tmp_path):
    destination = tmp_path / "existing"
    destination.mkdir()
    marker = destination / "keep.txt"
    marker.write_text("keep", encoding="utf-8")

    with pytest.raises(ValueError, match="not a managed ContextGraph export"):
        ContextGraph(advanced_analytics=False).save_to_file(
            destination, format="markdown"
        )

    assert marker.read_text(encoding="utf-8") == "keep"


def test_markdown_export_rejects_unrelated_graph_markdown_file(tmp_path):
    destination = tmp_path / "existing"
    destination.mkdir()
    unrelated = destination / "graph.md"
    _write_markdown(unrelated, {"title": "Unrelated notes"}, "Keep me")

    with pytest.raises(ValueError, match="not a managed ContextGraph export"):
        ContextGraph(advanced_analytics=False).save_to_file(
            destination, format="markdown"
        )

    assert unrelated.exists()


@pytest.mark.parametrize("extra_location", ["root", "nodes"])
def test_markdown_export_refuses_managed_directory_with_untracked_files(
    tmp_path, extra_location
):
    graph = ContextGraph(advanced_analytics=False)
    graph.add_node("node-1", "Note", "Body")
    destination = tmp_path / "existing"
    graph.save_to_file(destination, format="markdown")
    parent = destination if extra_location == "root" else destination / "nodes"
    human_file = parent / "human-notes.txt"
    human_file.write_text("do not delete", encoding="utf-8")
    original_contents = _directory_contents(destination)

    with pytest.raises(ValueError, match="not a managed ContextGraph export"):
        graph.save_to_file(destination, format="markdown")

    assert _directory_contents(destination) == original_contents


def test_markdown_export_refuses_noncanonical_node_layout(tmp_path):
    graph = ContextGraph(advanced_analytics=False)
    graph.add_node("node-1", "Note", "Body")
    destination = tmp_path / "existing"
    graph.save_to_file(destination, format="markdown")
    canonical = _node_file(destination, "node-1")
    renamed = canonical.with_name("human-name.md")
    canonical.rename(renamed)
    original_contents = _directory_contents(destination)

    with pytest.raises(ValueError, match="not a managed ContextGraph export"):
        graph.save_to_file(destination, format="markdown")

    assert _directory_contents(destination) == original_contents


def test_markdown_export_preserves_manifest_inspection_errors(tmp_path, monkeypatch):
    graph = ContextGraph(advanced_analytics=False)
    destination = tmp_path / "existing"
    graph.save_to_file(destination, format="markdown")
    real_reader = ContextGraph._read_markdown_file

    def fail_manifest_read(path):
        if path == destination / "graph.md":
            raise PermissionError("permission denied")
        return real_reader(path)

    monkeypatch.setattr(
        ContextGraph, "_read_markdown_file", staticmethod(fail_manifest_read)
    )

    with pytest.raises(PermissionError, match="permission denied"):
        graph.save_to_file(destination, format="markdown")


def test_markdown_export_restores_previous_directory_when_publish_fails(
    tmp_path, monkeypatch
):
    graph = ContextGraph(advanced_analytics=False)
    graph.add_node("original", "Note", "Original")
    destination = tmp_path / "graph"
    graph.save_to_file(destination, format="markdown")
    original_contents = _directory_contents(destination)
    graph.add_node("new", "Note", "New")

    real_replace = context_graph_module.os.replace

    def fail_staged_publish(source, target):
        if ".staging-" in Path(source).name and Path(target) == destination:
            raise OSError("simulated publish failure")
        return real_replace(source, target)

    monkeypatch.setattr(context_graph_module.os, "replace", fail_staged_publish)

    with pytest.raises(OSError, match="simulated publish failure"):
        graph.save_to_file(destination, format="markdown")

    assert _directory_contents(destination) == original_contents
    assert not list(tmp_path.glob(".graph.staging-*"))
    assert not list(tmp_path.glob(".graph.backup-*"))


def test_markdown_export_preserves_publish_error_when_restore_fails(
    tmp_path, monkeypatch, caplog
):
    graph = ContextGraph(advanced_analytics=False)
    graph.add_node("original", "Note", "Original")
    destination = tmp_path / "graph"
    graph.save_to_file(destination, format="markdown")
    original_contents = _directory_contents(destination)
    graph.add_node("new", "Note", "New")

    real_replace = context_graph_module.os.replace

    def fail_publish_and_restore(source, target):
        source_path = Path(source)
        if ".staging-" in source_path.name and Path(target) == destination:
            raise OSError("simulated publish failure")
        if ".backup-" in source_path.name and Path(target) == destination:
            raise PermissionError("simulated restore failure")
        return real_replace(source, target)

    monkeypatch.setattr(context_graph_module.os, "replace", fail_publish_and_restore)
    caplog.set_level("ERROR")

    with pytest.raises(OSError, match="simulated publish failure"):
        graph.save_to_file(destination, format="markdown")

    assert "preserving the original publish error" in caplog.text
    assert "simulated restore failure" in caplog.text
    assert not destination.exists()
    backup_paths = list(tmp_path.glob(".graph.backup-*"))
    assert len(backup_paths) == 1
    assert _directory_contents(backup_paths[0]) == original_contents
    assert not list(tmp_path.glob(".graph.staging-*"))


def test_markdown_load_rebuilds_indexes_and_emits_json_compatible_events(tmp_path):
    source, _, _ = _sample_graph()
    destination = tmp_path / "graph"
    source.save_to_file(destination, format="markdown")
    events = []
    target = ContextGraph(
        advanced_analytics=False,
        mutation_callback=lambda *event: events.append(event),
    )
    target._retractions[("node", "stale")] = {"entity_id": "stale"}
    target._tombstones[("edge", "stale")] = {"entity_id": "stale"}

    target.load_from_file(destination, format="markdown")

    assert target.node_type_index["Policy"] == {"policy/\u6771\u4eac"}
    assert target.edge_type_index["SUPPORTS"][0].edge_id == "edge-supports"
    assert target._edge_index["edge-supports"].edge_type == "SUPPORTS"
    assert target._adjacency["evidence-1"][0].target_id == "policy/\u6771\u4eac"
    assert target._retractions == {}
    assert target._tombstones == {}
    assert [event[0] for event in events] == ["ADD_NODE"] * len(target.nodes) + [
        "ADD_EDGE"
    ] * len(target.edges)
    assert {event[1] for event in events if event[0] == "ADD_NODE"} == set(target.nodes)
    assert {event[1] for event in events if event[0] == "ADD_EDGE"} == {
        edge.edge_id for edge in target.edges
    }


def test_markdown_load_records_granular_change_manager_history(tmp_path):
    source, _, _ = _sample_graph()
    destination = tmp_path / "graph"
    source.save_to_file(destination, format="markdown")
    target = ContextGraph(advanced_analytics=False)
    manager = TemporalVersionManager()
    manager.attach_to_graph(target)

    target.load_from_file(destination, format="markdown")

    assert manager.get_node_history("evidence-1")[0]["operation"] == "ADD_NODE"
    assert manager.get_node_history("edge-supports")[0]["operation"] == "ADD_EDGE"


def test_markdown_export_rejects_recursive_metadata(tmp_path):
    recursive = {}
    recursive["self"] = recursive
    graph = ContextGraph(advanced_analytics=False)
    graph._add_internal_node(ContextNode("node-1", "Note", "Body", metadata=recursive))

    with pytest.raises(ValueError, match="values cannot contain cycles"):
        graph.save_to_file(tmp_path / "graph", format="markdown")


def test_markdown_import_and_export_reject_symlinks(tmp_path):
    graph = ContextGraph(advanced_analytics=False)
    graph.add_node("node-1", "Note", "Body")
    real_export = tmp_path / "real"
    graph.save_to_file(real_export, format="markdown")

    directory_link = tmp_path / "directory-link"
    try:
        directory_link.symlink_to(real_export, target_is_directory=True)
    except (NotImplementedError, OSError):
        pytest.skip("Symbolic links are not available on this platform")

    with pytest.raises(ValueError, match="symbolic link"):
        ContextGraph(advanced_analytics=False).load_from_file(
            directory_link, format="markdown"
        )
    with pytest.raises(ValueError, match="symbolic link"):
        graph.save_to_file(directory_link, format="markdown")

    manifest_path = real_export / "graph.md"
    manifest_target = tmp_path / "manifest.md"
    manifest_target.write_bytes(manifest_path.read_bytes())
    manifest_path.unlink()
    manifest_path.symlink_to(manifest_target)
    with pytest.raises(ValueError, match="symbolic link"):
        ContextGraph(advanced_analytics=False).load_from_file(
            real_export, format="markdown"
        )


def test_markdown_import_and_export_reject_windows_junctions(tmp_path, monkeypatch):
    graph = ContextGraph(advanced_analytics=False)
    graph.add_node("node-1", "Note", "Body")
    export_path = tmp_path / "junction"
    graph.save_to_file(export_path, format="markdown")

    monkeypatch.setattr(
        os.path,
        "isjunction",
        lambda candidate: Path(candidate) == export_path,
        raising=False,
    )

    with pytest.raises(ValueError, match="junction"):
        ContextGraph(advanced_analytics=False).load_from_file(
            export_path, format="markdown"
        )
    with pytest.raises(ValueError, match="junction"):
        graph.save_to_file(export_path, format="markdown")


def test_markdown_import_rejects_windows_reparse_point_fallback(tmp_path, monkeypatch):
    source = tmp_path / "reparse-point"
    source.mkdir()
    real_lstat = os.lstat

    class ReparseStat:
        st_file_attributes = getattr(stat, "FILE_ATTRIBUTE_REPARSE_POINT", 0x400)

    monkeypatch.delattr(os.path, "isjunction", raising=False)
    monkeypatch.setattr(Path, "is_symlink", lambda self: False)
    monkeypatch.setattr(
        os,
        "lstat",
        lambda candidate: (
            ReparseStat() if Path(candidate) == source else real_lstat(candidate)
        ),
    )

    with pytest.raises(ValueError, match="junction"):
        ContextGraph(advanced_analytics=False).load_from_file(source, format="markdown")


@pytest.mark.skipif(os.name != "nt", reason="requires Windows junctions")
def test_markdown_import_rejects_real_windows_junction(tmp_path):
    graph = ContextGraph(advanced_analytics=False)
    graph.add_node("node-1", "Note", "Body")
    outside = tmp_path / "outside"
    graph.save_to_file(outside, format="markdown")
    source = tmp_path / "junction"
    result = subprocess.run(
        ["cmd.exe", "/c", "mklink", "/J", str(source), str(outside)],
        capture_output=True,
        text=True,
        check=False,
    )
    if result.returncode != 0:
        pytest.skip(f"could not create Windows junction: {result.stderr}")

    try:
        with pytest.raises(ValueError, match="junction"):
            ContextGraph(advanced_analytics=False).load_from_file(
                source, format="markdown"
            )
    finally:
        os.rmdir(source)


@pytest.mark.skipif(
    not hasattr(context_graph_module.os, "O_NOFOLLOW"),
    reason="O_NOFOLLOW is unavailable on this platform",
)
def test_markdown_import_nofollow_check_closes_symlink_race(tmp_path, monkeypatch):
    graph = ContextGraph(advanced_analytics=False)
    graph.add_node("node-1", "Note", "Body")
    export_path = tmp_path / "graph"
    graph.save_to_file(export_path, format="markdown")
    node_path = _node_file(export_path, "node-1")
    target = tmp_path / "target.md"
    target.write_bytes(node_path.read_bytes())
    node_path.unlink()
    node_path.symlink_to(target)

    real_is_symlink = Path.is_symlink

    def miss_precheck(path):
        if path == node_path:
            return False
        return real_is_symlink(path)

    monkeypatch.setattr(Path, "is_symlink", miss_precheck)

    with pytest.raises(ValueError, match="symbolic link"):
        ContextGraph(advanced_analytics=False).load_from_file(
            export_path, format="markdown"
        )


def test_json_remains_default_and_unknown_format_is_rejected(tmp_path):
    graph = ContextGraph(advanced_analytics=False)
    graph.add_node("node-1", "Note", "Body")
    json_path = tmp_path / "graph.json"
    graph.save_to_file(json_path)

    restored = ContextGraph(advanced_analytics=False)
    restored._analytics_cache["stale"] = {"value": True}
    restored.load_from_file(json_path)
    assert "node-1" in restored.nodes
    assert restored._analytics_cache == {}

    before = _normalized_state(restored)
    restored.load_from_file(tmp_path / "missing", format="markdown")
    assert _normalized_state(restored) == before

    with pytest.raises(ValueError, match="Unsupported context graph"):
        graph.save_to_file(tmp_path / "graph", format="html")
