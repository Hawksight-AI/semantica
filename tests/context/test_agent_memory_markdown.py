import errno
import sys
from copy import deepcopy
from datetime import datetime, timedelta, timezone
from unittest.mock import MagicMock, patch

import pytest
import yaml

from semantica.context.agent_memory import AgentMemory

_ERROR_PRIVILEGE_NOT_HELD = 1314


class TrackingVectorStore:
    def __init__(self):
        self.items = {}
        self.events = []
        self.fail_after_add = False

    def add(self, items):
        memory_ids = []
        for item in items:
            self.items[item.memory_id] = deepcopy(item)
            memory_ids.append(item.memory_id)
        self.events.append(("add", memory_ids))
        if self.fail_after_add:
            raise RuntimeError("vector add failed after mutation")
        return memory_ids

    def delete(self, memory_ids):
        self.events.append(("delete", list(memory_ids)))
        for memory_id in memory_ids:
            self.items.pop(memory_id, None)
        return True


class TrackingConcreteVectorStore:
    def __init__(self):
        self.events = []
        self.next_id = 0

    def store_vectors(self, vectors, metadata):
        vector_id = f"vec_{self.next_id}"
        self.next_id += 1
        self.events.append(("store", vector_id))
        return [vector_id]

    def delete_vectors(self, vector_ids):
        self.events.append(("delete", list(vector_ids)))
        return True


def markdown_document(frontmatter, body=""):
    yaml_text = yaml.safe_dump(frontmatter, sort_keys=False, allow_unicode=True)
    return f"---\n{yaml_text}---\n\n{body}"


def required_frontmatter(memory_id="mem_test", **overrides):
    frontmatter = {
        "id": memory_id,
        "created_at": "2026-07-22T09:00:00+00:00",
        "updated_at": "2026-07-22T10:00:00+00:00",
        "type": "note",
    }
    frontmatter.update(overrides)
    return frontmatter


def test_markdown_round_trip_is_lossless_and_deterministic():
    memory = AgentMemory()
    content = "\n# Editable memory\n\n<!-- marker-like body text -->\n\n"
    memory.store(
        content,
        metadata={
            "type": "note",
            "updated_at": "2026-07-22T12:30:00+00:00",
            "source": "caf\u00e9 review",
            "tags": ["alpha", "beta"],
            "id": "metadata-id",
            "kind": "metadata-kind",
        },
        entities=[{"id": "ent_1", "type": "topic", "text": "Memory"}],
        relationships=[
            {
                "source_id": "ent_1",
                "target_id": "ent_2",
                "type": "related_to",
                "confidence": 0.9,
            }
        ],
        memory_id="mem_round_trip",
        timestamp=datetime.fromisoformat("2026-07-22T12:00:00+00:00"),
    )

    exported = memory.export(format="markdown")
    restored = AgentMemory()

    assert restored.import_data(exported, format="markdown") == 1
    assert restored.get("mem_round_trip") == memory.get("mem_round_trip")
    assert restored.export(format="markdown") == exported
    assert "caf\u00e9 review" in exported


def test_markdown_directory_round_trip_uses_one_stable_file_per_memory(tmp_path):
    memory = AgentMemory()
    for index in range(2):
        timestamp = f"2026-07-22T0{index + 8}:00:00"
        memory.store(
            f"Memory {index}",
            metadata={
                "type": "reference",
                "updated_at": timestamp,
                "source": f"source-{index}",
            },
            memory_id=f"mem_{index}",
            timestamp=datetime.fromisoformat(timestamp),
        )

    first_export = tmp_path / "first"
    assert memory.export(format="markdown", destination=first_export) == str(
        first_export
    )
    first_files = sorted(first_export.glob("*.md"))
    assert len(first_files) == 2

    restored = AgentMemory()
    assert restored.import_data(first_export, format="markdown") == 2
    assert set(restored.memory_items) == {"mem_0", "mem_1"}

    second_export = tmp_path / "second"
    restored.export(format="markdown", destination=second_export)
    assert {path.name: path.read_text(encoding="utf-8") for path in first_files} == {
        path.name: path.read_text(encoding="utf-8")
        for path in sorted(second_export.glob("*.md"))
    }


def test_multiple_memories_require_a_destination_but_filters_can_select_one():
    memory = AgentMemory()
    for memory_type in ("note", "reference"):
        memory.store(
            memory_type,
            metadata={
                "type": memory_type,
                "updated_at": "2026-07-22T10:00:00",
            },
            memory_id=f"mem_{memory_type}",
            timestamp=datetime(2026, 7, 22, 9, 0, 0),
        )

    with pytest.raises(ValueError, match="destination"):
        memory.export(format="markdown")

    exported = memory.export(format="markdown", type="note")
    assert "id: mem_note" in exported
    assert "id: mem_reference" not in exported


def test_markdown_update_replaces_supported_fields_and_preserves_id():
    memory = AgentMemory()
    memory.store(
        "Original content",
        metadata={
            "type": "note",
            "updated_at": "2026-07-22T09:30:00",
            "remove_me": True,
        },
        memory_id="mem_existing",
        timestamp=datetime(2026, 7, 22, 9, 0, 0),
    )
    edited = markdown_document(
        required_frontmatter(
            "mem_existing",
            created_at="2026-07-22T09:15:00",
            updated_at="2026-07-22T11:00:00",
            type="decision",
            source="manual edit",
        ),
        "Updated content",
    )

    assert memory.import_data(edited, format="markdown") == 1

    updated = memory.get("mem_existing")
    assert memory.count() == 1
    assert updated["memory_id"] == "mem_existing"
    assert updated["content"] == "Updated content"
    assert updated["timestamp"] == "2026-07-22T09:15:00"
    assert updated["metadata"] == {
        "type": "decision",
        "source": "manual edit",
        "updated_at": "2026-07-22T11:00:00",
    }
    assert memory.stats["items_by_type"] == {"decision": 1}
    assert [item.memory_id for item in memory.short_term_memory] == ["mem_existing"]


def test_public_update_preserves_id_and_statistics():
    memory = AgentMemory()
    memory.store(
        "Original",
        metadata={"type": "note"},
        memory_id="mem_update",
        timestamp=datetime(2026, 7, 22, 9, 0, 0),
    )

    assert memory.update("mem_update", content="Updated", metadata={"type": "decision"})
    assert memory.get("mem_update")["content"] == "Updated"
    assert set(memory.memory_items) == {"mem_update"}
    assert list(memory.memory_index) == ["mem_update"]
    assert memory.stats["total_items"] == 1
    assert memory.stats["items_by_type"] == {"decision": 1}


def test_reusing_custom_id_replaces_item_without_statistics_drift():
    vector_store = TrackingVectorStore()
    memory = AgentMemory(vector_store=vector_store)
    memory.store(
        "Original",
        metadata={"type": "note"},
        memory_id="mem_reused",
        timestamp=datetime(2026, 7, 22, 9, 0, 0),
    )

    vector_store.events.clear()
    memory.store(
        "Replacement",
        metadata={"type": "decision"},
        memory_id="mem_reused",
        timestamp=datetime(2026, 7, 22, 10, 0, 0),
    )

    assert memory.get("mem_reused")["content"] == "Replacement"
    assert list(memory.memory_index) == ["mem_reused"]
    assert [item.memory_id for item in memory.short_term_memory] == ["mem_reused"]
    assert memory.stats["total_items"] == 1
    assert memory.stats["items_by_type"] == {"decision": 1}
    assert vector_store.items["mem_reused"].content == "Replacement"
    assert vector_store.events == [("add", ["mem_reused"])]

    assert memory.delete_memory("mem_reused")
    assert memory.stats["total_items"] == 0
    assert memory.stats["items_by_type"] == {}
    assert vector_store.items == {}


def test_reimporting_unchanged_markdown_does_not_rewrite_memory():
    memory = AgentMemory()
    document = markdown_document(required_frontmatter(), "Unchanged")
    assert memory.import_data(document, format="markdown") == 1
    before = memory.get("mem_test")

    with patch.object(
        memory, "_replace_memory_item", wraps=memory._replace_memory_item
    ) as replace:
        assert memory.import_data(document, format="markdown") == 1

    replace.assert_not_called()
    assert memory.get("mem_test") == before
    assert memory.count() == 1


def test_naive_and_aware_equivalent_timestamps_match_idempotently():
    memory = AgentMemory()
    utc_dt = datetime(2026, 7, 22, 9, 0, 0, tzinfo=timezone.utc)
    naive_dt = utc_dt.astimezone().replace(tzinfo=None)
    memory.store(
        "Unchanged",
        metadata={"type": "note", "updated_at": "2026-07-22T10:00:00+00:00"},
        memory_id="mem_test",
        timestamp=naive_dt,
    )
    document = markdown_document(
        required_frontmatter("mem_test", created_at="2026-07-22T09:00:00+00:00"),
        "Unchanged",
    )

    with patch.object(
        memory, "_replace_memory_item", wraps=memory._replace_memory_item
    ) as replace:
        assert memory.import_data(document, format="markdown") == 1

    replace.assert_not_called()


def test_kind_is_accepted_as_the_type_alias():
    frontmatter = required_frontmatter()
    frontmatter["kind"] = frontmatter.pop("type")

    memory = AgentMemory()
    assert (
        memory.import_data(
            markdown_document(frontmatter, "Kind alias"), format="markdown"
        )
        == 1
    )
    assert memory.get("mem_test")["metadata"]["type"] == "note"


@pytest.mark.parametrize("missing_field", ["id", "created_at", "updated_at", "type"])
def test_required_frontmatter_fields_are_enforced(missing_field):
    frontmatter = required_frontmatter()
    frontmatter.pop(missing_field)

    with pytest.raises(ValueError, match="missing required"):
        AgentMemory().import_data(
            markdown_document(frontmatter, "Invalid"), format="markdown"
        )


@pytest.mark.parametrize(
    ("overrides", "message"),
    [
        ({"id": 123}, "'id' must be a string"),
        ({"created_at": "yesterday"}, "ISO-8601"),
        ({"updated_at": "later"}, "ISO-8601"),
        ({"type": ["note"]}, "must be a string"),
        ({"kind": "decision"}, "must match"),
        ({"metadata": []}, "must be a mapping"),
        ({"entities": {}}, "must be a list"),
        ({"entities": ["entity"]}, "must be a mapping"),
        ({"relationships": [1]}, "must be a mapping"),
        ({"metadata": {"type": "nested"}}, "duplicates reserved"),
        ({"metadata": {"source": "nested"}, "source": "top"}, "defined both"),
    ],
)
def test_invalid_frontmatter_values_return_actionable_errors(overrides, message):
    document = markdown_document(required_frontmatter(**overrides), "Invalid")

    with pytest.raises(ValueError, match=message):
        AgentMemory().import_data(document, format="markdown")


@pytest.mark.parametrize(
    "document",
    [
        "not frontmatter",
        "---\nid: broken",
        "---\nid: [unterminated\n---\n",
        (
            "---\nid: first\nid: second\ncreated_at: 2026-07-22T09:00:00\n"
            "updated_at: 2026-07-22T10:00:00\ntype: note\n---\n"
        ),
    ],
)
def test_malformed_frontmatter_is_rejected(document):
    with pytest.raises(ValueError, match="frontmatter"):
        AgentMemory().import_data(document, format="markdown")


def test_directory_is_fully_validated_before_any_memory_is_changed(tmp_path):
    valid = markdown_document(required_frontmatter("mem_valid"), "Valid")
    invalid_fields = required_frontmatter("mem_invalid")
    invalid_fields.pop("updated_at")
    invalid = markdown_document(invalid_fields, "Invalid")
    (tmp_path / "a-valid.md").write_text(valid, encoding="utf-8")
    (tmp_path / "z-invalid.md").write_text(invalid, encoding="utf-8")

    memory = AgentMemory()
    with pytest.raises(ValueError, match="updated_at"):
        memory.import_data(tmp_path, format="markdown")

    assert memory.count() == 0


def test_duplicate_ids_in_a_directory_are_rejected_before_import(tmp_path):
    document = markdown_document(required_frontmatter("mem_duplicate"), "Body")
    (tmp_path / "first.md").write_text(document, encoding="utf-8")
    (tmp_path / "second.markdown").write_text(document, encoding="utf-8")

    memory = AgentMemory()
    with pytest.raises(ValueError, match="Duplicate Markdown memory ID"):
        memory.import_data(tmp_path, format="markdown")

    assert memory.count() == 0


def test_markdown_import_keeps_provenance_out_of_the_context_graph():
    knowledge_graph = MagicMock()
    memory = AgentMemory(knowledge_graph=knowledge_graph)
    fields = required_frontmatter(
        entities=[{"id": "entity_1", "type": "topic"}],
        relationships=[
            {
                "source_id": "entity_1",
                "target_id": "entity_2",
                "type": "related_to",
            }
        ],
    )

    assert (
        memory.import_data(markdown_document(fields, "Provenance"), format="markdown")
        == 1
    )
    assert memory.get("mem_test")["entities"][0]["id"] == "entity_1"
    knowledge_graph.add_nodes.assert_not_called()
    knowledge_graph.add_edges.assert_not_called()


def test_operational_failure_restores_existing_in_memory_state():
    memory = AgentMemory()
    memory.store(
        "Original",
        metadata={
            "type": "note",
            "updated_at": "2026-07-22T09:30:00",
        },
        memory_id="mem_existing",
        timestamp=datetime(2026, 7, 22, 9, 0, 0),
    )
    before_memory = deepcopy(memory.get("mem_existing"))
    before_stats = deepcopy(memory.stats)
    edited_fields = required_frontmatter("mem_existing")
    original_store = memory.store

    def fail_after_store(*args, **kwargs):
        original_store(*args, **kwargs)
        raise RuntimeError("store unavailable")

    with patch.object(memory, "store", side_effect=fail_after_store):
        with pytest.raises(RuntimeError, match="store unavailable"):
            memory.import_data(
                markdown_document(edited_fields, "Edited"), format="markdown"
            )

    assert memory.get("mem_existing") == before_memory
    assert memory.stats == before_stats
    assert list(memory.memory_index) == ["mem_existing"]
    assert [item.memory_id for item in memory.short_term_memory] == ["mem_existing"]


def test_failed_markdown_update_does_not_mutate_vector_store_before_rollback():
    vector_store = TrackingVectorStore()
    memory = AgentMemory(vector_store=vector_store)
    memory.store(
        "Original",
        metadata={"type": "note"},
        memory_id="mem_existing",
        timestamp=datetime(2026, 7, 22, 9, 0, 0),
    )
    vector_store.events.clear()
    original_store = memory.store

    def fail_after_local_store(*args, **kwargs):
        original_store(*args, **kwargs)
        raise RuntimeError("local store failed")

    with patch.object(memory, "store", side_effect=fail_after_local_store):
        with pytest.raises(RuntimeError, match="local store failed"):
            memory.import_data(
                markdown_document(required_frontmatter("mem_existing"), "Replacement"),
                format="markdown",
            )

    assert memory.get("mem_existing")["content"] == "Original"
    assert vector_store.items["mem_existing"].content == "Original"
    assert vector_store.events == []


def test_vector_sync_runs_after_markdown_commit_and_never_triggers_rollback():
    vector_store = TrackingVectorStore()
    memory = AgentMemory(vector_store=vector_store)
    memory.store(
        "Original",
        metadata={"type": "note"},
        memory_id="mem_existing",
        timestamp=datetime(2026, 7, 22, 9, 0, 0),
    )
    vector_store.events.clear()
    vector_store.fail_after_add = True

    assert (
        memory.import_data(
            markdown_document(required_frontmatter("mem_existing"), "Replacement"),
            format="markdown",
        )
        == 1
    )

    assert memory.get("mem_existing")["content"] == "Replacement"
    assert vector_store.items["mem_existing"].content == "Replacement"
    assert vector_store.events == [("add", ["mem_existing"])]


def test_markdown_update_replaces_concrete_adapter_vector_id_after_commit():
    vector_store = TrackingConcreteVectorStore()
    memory = AgentMemory(vector_store=vector_store)
    memory.store(
        "Original",
        metadata={"type": "note"},
        memory_id="mem_existing",
        timestamp=datetime(2026, 7, 22, 9, 0, 0),
    )
    assert memory._vector_ids == {"mem_existing": ["vec_0"]}
    vector_store.events.clear()

    assert (
        memory.import_data(
            markdown_document(required_frontmatter("mem_existing"), "Replacement"),
            format="markdown",
        )
        == 1
    )

    assert memory._vector_ids == {"mem_existing": ["vec_1"]}
    assert vector_store.events == [("store", "vec_1"), ("delete", ["vec_0"])]


def test_vector_id_mapping_survives_save_and_load(tmp_path):
    vector_store = TrackingConcreteVectorStore()
    memory = AgentMemory(vector_store=vector_store)
    memory.store(
        "Persisted",
        metadata={"type": "note"},
        memory_id="mem_persisted",
    )
    memory.save(str(tmp_path))

    restored = AgentMemory(vector_store=vector_store)
    restored.load(str(tmp_path))
    vector_store.events.clear()

    assert restored._vector_ids == {"mem_persisted": ["vec_0"]}
    assert restored.delete_memory("mem_persisted")
    assert vector_store.events == [("delete", ["vec_0"])]


def test_failed_multi_file_import_never_starts_vector_synchronization(tmp_path):
    vector_store = TrackingVectorStore()
    memory = AgentMemory(vector_store=vector_store)
    for name in ("a-first.md", "b-second.md"):
        memory_id = name[:-3]
        (tmp_path / name).write_text(
            markdown_document(required_frontmatter(memory_id), name),
            encoding="utf-8",
        )

    original_store = memory.store
    calls = 0

    def fail_on_second_store(*args, **kwargs):
        nonlocal calls
        calls += 1
        stored_id = original_store(*args, **kwargs)
        if calls == 2:
            raise RuntimeError("second local store failed")
        return stored_id

    with patch.object(memory, "store", side_effect=fail_on_second_store):
        with pytest.raises(RuntimeError, match="second local store failed"):
            memory.import_data(tmp_path, format="markdown")

    assert memory.count() == 0
    assert vector_store.events == []
    assert vector_store.items == {}


def test_import_does_not_report_retention_pruned_memory_as_successful():
    memory = AgentMemory(retention_policy="1_days")
    fields = required_frontmatter(
        "mem_expired",
        created_at="2000-01-01T00:00:00",
        updated_at="2000-01-01T00:00:00",
    )

    with pytest.raises(RuntimeError, match="did not confirm"):
        memory.import_data(markdown_document(fields, "Expired"), format="markdown")

    assert memory.count() == 0
    assert memory.stats["total_items"] == 0


def test_timezone_aware_import_supports_retention_sorting_and_date_filters():
    now_utc = datetime.now(timezone.utc)
    memory = AgentMemory(retention_policy="1_days")
    memory.store(
        "Naive memory",
        metadata={"type": "note"},
        memory_id="mem_naive",
        timestamp=datetime.now(),
    )
    fields = required_frontmatter(
        "mem_aware",
        created_at=now_utc.isoformat(),
        updated_at=now_utc.isoformat(),
    )

    assert (
        memory.import_data(markdown_document(fields, "Aware memory"), "markdown") == 1
    )
    assert memory.get("mem_aware")["timestamp"].endswith("+00:00")
    assert {item["memory_id"] for item in memory.get_recent()} == {
        "mem_naive",
        "mem_aware",
    }

    start = now_utc - timedelta(hours=1)
    end = now_utc + timedelta(hours=1)
    assert {item["memory_id"] for item in memory.get_by_date(start, end)} == {
        "mem_naive",
        "mem_aware",
    }
    assert {
        item["memory_id"]
        for item in memory.retrieve(
            "memory", start_date=start.isoformat(), end_date=end.isoformat()
        )
    } == {"mem_naive", "mem_aware"}


def test_exported_filenames_cannot_escape_or_collide_with_destination(tmp_path):
    memory = AgentMemory()
    for memory_id in ("../outside", "a/b", "a\\b", "A/B"):
        memory.store(
            memory_id,
            metadata={
                "type": "note",
                "updated_at": "2026-07-22T10:00:00",
            },
            memory_id=memory_id,
            timestamp=datetime(2026, 7, 22, 9, 0, 0),
        )

    destination = tmp_path / "export"
    memory.export(format="markdown", destination=destination)
    exported_files = list(destination.glob("*.md"))

    assert len(exported_files) == 4
    assert len({path.name.casefold() for path in exported_files}) == 4
    assert all(path.parent == destination for path in exported_files)
    assert not (tmp_path / "outside.md").exists()


def test_markdown_export_rejects_symlink_without_touching_target(tmp_path):
    memory = AgentMemory()
    memory.store(
        "Protected content",
        metadata={"type": "note", "updated_at": "2026-07-22T10:00:00"},
        memory_id="mem_symlink",
        timestamp=datetime(2026, 7, 22, 9, 0, 0),
    )
    destination = tmp_path / "export"
    destination.mkdir()
    outside = tmp_path / "outside.md"
    outside.write_text("do not overwrite", encoding="utf-8")
    output_path = destination / memory._memory_markdown_filename("mem_symlink")
    try:
        output_path.symlink_to(outside)
    except OSError as error:
        winerror = getattr(error, "winerror", None)
        if sys.platform == "win32" and winerror == _ERROR_PRIVILEGE_NOT_HELD:
            pytest.skip("Windows symlink creation requires an unavailable privilege")
        raise

    with pytest.raises(ValueError, match="symbolic link"):
        memory.export(format="markdown", destination=destination)

    assert output_path.is_symlink()
    assert outside.read_text(encoding="utf-8") == "do not overwrite"


def test_empty_markdown_export_and_import_are_no_ops():
    memory = AgentMemory()

    assert memory.export(format="markdown") == ""
    assert memory.import_data("", format="markdown") == 0


def test_markdown_string_path_read_errors_are_not_treated_as_content(tmp_path):
    source = tmp_path / "memory.md"
    source.write_text(
        markdown_document(required_frontmatter(), "Content"), encoding="utf-8"
    )
    memory = AgentMemory()

    with patch.object(
        memory,
        "_read_markdown_path",
        side_effect=PermissionError("read denied"),
    ):
        with pytest.raises(PermissionError, match="read denied"):
            memory.import_data(str(source), format="markdown")


def test_markdown_string_path_inspection_errors_are_actionable():
    memory = AgentMemory()
    original_error = PermissionError(
        errno.EACCES,
        "inspection denied",
        "blocked-memory.md",
    )

    with patch(
        "semantica.context.agent_memory.Path.exists",
        side_effect=original_error,
    ):
        with pytest.raises(
            OSError, match="Failed to inspect possible Markdown import path"
        ) as exc_info:
            memory.import_data("memory.md", format="markdown")

    assert exc_info.value.errno == errno.EACCES
    assert exc_info.value.filename == "blocked-memory.md"
    assert "inspection denied" in str(exc_info.value)
    assert exc_info.value.__cause__ is original_error


def test_legacy_dict_import_behavior_is_unchanged():
    memory = AgentMemory()
    data = {
        "memories": [
            {
                "memory_id": "source_id",
                "content": "Legacy import",
                "metadata": {"type": "note"},
                "timestamp": "2000-01-01T00:00:00",
            }
        ]
    }

    assert memory.import_data(data, format="dict") == 1
    assert not memory.exists("source_id")
    imported = next(iter(memory.memory_items.values()))
    assert imported.content == "Legacy import"
    assert imported.metadata == {"type": "note"}


def test_markdown_export_destination_must_be_a_directory(tmp_path):
    destination = tmp_path / "memory.md"
    destination.write_text("occupied", encoding="utf-8")

    with pytest.raises(ValueError, match="not a directory"):
        AgentMemory().export(format="markdown", destination=destination)


def test_markdown_import_file_open_security_rejects_symlink(tmp_path):
    memory = AgentMemory()
    target = tmp_path / "secret.txt"
    target.write_text("secret content", encoding="utf-8")
    symlink_file = tmp_path / "memory.md"
    try:
        symlink_file.symlink_to(target)
    except OSError as error:
        winerror = getattr(error, "winerror", None)
        if sys.platform == "win32" and winerror == _ERROR_PRIVILEGE_NOT_HELD:
            pytest.skip("Windows symlink creation requires an unavailable privilege")
        raise

    with pytest.raises(ValueError, match="Symlink Markdown import paths are rejected"):
        memory._read_markdown_file_content(symlink_file)

def test_markdown_import_public_api_rejects_symlink(tmp_path):
    """
    import_data(..., format="markdown") must propagate the symlink rejection
    through the full call chain: import_data → _import_markdown_payload →
    _read_markdown_path → _read_markdown_file_content.

    This complements test_markdown_import_file_open_security_rejects_symlink,
    which only tests the private helper.  A future refactor that bypasses
    _read_markdown_file_content would silently stop being protected; this test
    catches that.
    """
    target = tmp_path / "secret.txt"
    target.write_text("secret content", encoding="utf-8")
    symlink_file = tmp_path / "memory.md"
    try:
        symlink_file.symlink_to(target)
    except OSError as error:
        winerror = getattr(error, "winerror", None)
        if sys.platform == "win32" and winerror == _ERROR_PRIVILEGE_NOT_HELD:
            pytest.skip("Windows symlink creation requires an unavailable privilege")
        raise

    memory = AgentMemory()
    with pytest.raises(ValueError, match="Symlink Markdown import paths are rejected"):
        memory.import_data(symlink_file, format="markdown")


def test_markdown_import_directory_silently_skips_symlinked_entries(tmp_path):
    """
    When importing a directory, symlink entries must be silently excluded.
    Only real regular files must be read.

    This tests the filter in _read_markdown_path:
        not file_path.is_symlink()
    which was added by PR #932.
    """
    # Write a real Markdown file in the directory
    real_md = tmp_path / "real.md"
    real_md.write_text(
        markdown_document(required_frontmatter(memory_id="dir-real"), "Real content"),
        encoding="utf-8",
    )
    # Write the symlink target outside the directory
    target = tmp_path.parent / "outside.txt"
    target.write_text("must not be read", encoding="utf-8")
    link_md = tmp_path / "evil.md"
    try:
        link_md.symlink_to(target)
    except OSError as error:
        winerror = getattr(error, "winerror", None)
        if sys.platform == "win32" and winerror == _ERROR_PRIVILEGE_NOT_HELD:
            pytest.skip("Windows symlink creation requires an unavailable privilege")
        raise

    memory = AgentMemory()
    # Must succeed, returning only the real file
    results = memory._read_markdown_path(tmp_path)
    assert len(results) == 1, (
        f"Expected 1 result (real.md only), got {len(results)}: "
        f"{[r[0] for r in results]}"
    )
    assert "Real content" in results[0][1]


def test_markdown_import_rejects_non_regular_file(tmp_path):
    """
    _read_markdown_file_content must raise ValueError when the opened file
    descriptor does not refer to a regular file (S_ISREG fails).

    This tests the fstat()/S_ISREG guard, which is the defense-in-depth layer
    that catches special files (FIFOs, character devices) even when the
    is_symlink() pre-check passes.  The test works on both POSIX and Windows
    because it mocks os.fstat rather than relying on platform-specific
    filesystem objects.
    """
    import stat as stat_module

    real_file = tmp_path / "not_really_regular.md"
    real_file.write_text("some data", encoding="utf-8")

    # Build a mock stat result whose st_mode describes a FIFO (S_IFIFO).
    fake_stat = MagicMock()
    fake_stat.st_mode = stat_module.S_IFIFO | 0o600  # FIFO with rw permissions

    memory = AgentMemory()
    with patch("semantica.context.agent_memory.os.fstat", return_value=fake_stat):
        with pytest.raises(ValueError, match="not a regular file"):
            memory._read_markdown_file_content(real_file)
