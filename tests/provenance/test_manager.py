"""
Test Unified Provenance Manager

Tests for ProvenanceManager functionality including entity tracking,
chunk tracking, source tracking, and lineage tracing.
"""

import pytest
from unittest.mock import patch
from datetime import datetime
from semantica.provenance import ProvenanceManager, SourceReference, ProvenanceEntry
from semantica.provenance.storage import InMemoryStorage, SQLiteStorage


class TestProvenanceManager:
    """Test ProvenanceManager functionality."""

    @pytest.fixture(autouse=True)
    def reset_default_storage_path(self):
        original = ProvenanceManager._default_storage_path
        try:
            yield
        finally:
            ProvenanceManager._default_storage_path = original

    def test_default_storage_path_pattern(self, tmp_path):
        """Test global default storage pattern, config kwarg, and test-isolation context manager."""
        from semantica.provenance import default_storage_path, InMemoryStorage, SQLiteStorage

        # 1. Default should fallback to InMemoryStorage when no path/config
        prov_mgr = ProvenanceManager()
        assert isinstance(prov_mgr.storage, InMemoryStorage)

        # 2. Config kwarg should extract storage_path gracefully (CLI bug fix)
        cfg_path = str(tmp_path / "cfg_test.db")
        cfg = {"provenance": {"storage_path": cfg_path}}
        prov_mgr = ProvenanceManager(config=cfg)
        assert isinstance(prov_mgr.storage, SQLiteStorage)

        # 3. Explicit storage_path arg overrides config and default
        explicit_path = str(tmp_path / "explicit.db")
        prov_mgr = ProvenanceManager(storage_path=explicit_path, config=cfg)
        assert isinstance(prov_mgr.storage, SQLiteStorage)

        # 4. default_storage_path context manager should temporarily set default and restore on exit
        ctx_path = str(tmp_path / "ctx_test.db")
        with default_storage_path(ctx_path):
            assert ProvenanceManager._default_storage_path == ctx_path
            prov_mgr = ProvenanceManager()
            assert isinstance(prov_mgr.storage, SQLiteStorage)

        # Should be restored after context exit
        assert ProvenanceManager._default_storage_path is None
        prov_mgr = ProvenanceManager()
        assert isinstance(prov_mgr.storage, InMemoryStorage)

        # 5. Guaranteed restoration even on exception
        exc_path = str(tmp_path / "exception_test.db")
        try:
            with ProvenanceManager.default_storage_path(exc_path):
                assert ProvenanceManager._default_storage_path == exc_path
                raise RuntimeError("Test exception inside context")
        except RuntimeError:
            pass
        assert ProvenanceManager._default_storage_path is None

        # 6. Nested contexts should restore correctly from stack
        outer_path = str(tmp_path / "outer.db")
        inner_path = str(tmp_path / "inner.db")
        with default_storage_path(outer_path):
            assert ProvenanceManager._default_storage_path == outer_path
            with default_storage_path(inner_path):
                assert ProvenanceManager._default_storage_path == inner_path
            assert ProvenanceManager._default_storage_path == outer_path
        assert ProvenanceManager._default_storage_path is None

    def test_default_storage_path_concurrency_safety(self, tmp_path):
        """Test that default_storage_path context manager is thread-safe under concurrent use."""
        import threading
        import time
        from semantica.provenance import default_storage_path, SQLiteStorage

        errors = []

        def _worker(path, delay):
            try:
                with default_storage_path(path):
                    time.sleep(delay)
                    prov_mgr = ProvenanceManager()
                    assert isinstance(prov_mgr.storage, SQLiteStorage)
                    assert prov_mgr.storage.db_path == path
            except Exception as e:
                errors.append(e)

        path_a = str(tmp_path / "thread_a.db")
        path_b = str(tmp_path / "thread_b.db")

        t1 = threading.Thread(target=_worker, args=(path_a, 0.05))
        t2 = threading.Thread(target=_worker, args=(path_b, 0.01))
        t1.start()
        t2.start()
        t1.join()
        t2.join()

        assert not errors, f"Errors in concurrent context worker: {errors}"
        assert ProvenanceManager._default_storage_path is None

    def test_isolation_part_1_with_context_manager(self, tmp_path):
        """Part 1: Prove context manager sets default storage path for ProvenanceManager created inside context."""
        from semantica.provenance import default_storage_path, SQLiteStorage
        iso_db = str(tmp_path / "iso_part1.db")
        with default_storage_path(iso_db):
            prov_mgr = ProvenanceManager()
            assert isinstance(prov_mgr.storage, SQLiteStorage)
            assert prov_mgr.storage.db_path == iso_db

    def test_isolation_part_2_no_leakage_after_context(self):
        """Part 2: Prove that in a SEPARATE test function after context exit, ProvenanceManager falls back to InMemoryStorage without leakage."""
        from semantica.provenance import InMemoryStorage
        assert ProvenanceManager._default_storage_path is None
        prov_mgr = ProvenanceManager()
        assert isinstance(prov_mgr.storage, InMemoryStorage)

    def test_orchestrator_config_wiring(self, tmp_path):
        """Test Semantica orchestrator configures ProvenanceManager._default_storage_path."""
        from semantica.core import Semantica
        from semantica.provenance import ProvenanceManager, InMemoryStorage, SQLiteStorage

        # 1. No path set in config means InMemoryStorage fallback
        _ = Semantica()
        prov_mgr = ProvenanceManager()
        assert isinstance(prov_mgr.storage, InMemoryStorage)

        # 2. Config with provenance.storage_path sets default storage path
        test_db = str(tmp_path / "orch_test.db")
        _ = Semantica(config={"provenance": {"storage_path": test_db}})
        assert ProvenanceManager._default_storage_path == test_db
        prov_mgr = ProvenanceManager()
        assert isinstance(prov_mgr.storage, SQLiteStorage)

    def test_initialization(self):
        """Test manager initialization."""
        prov_mgr = ProvenanceManager()
        
        assert prov_mgr is not None
        assert prov_mgr.storage is not None
    
    def test_track_entity(self):
        """Test tracking entity provenance."""
        prov_mgr = ProvenanceManager()
        
        entry = prov_mgr.track_entity(
            entity_id="entity_1",
            source="doc_1",
            metadata={"confidence": 0.9}
        )
        
        assert entry is not None
        assert entry.entity_id == "entity_1"
        assert entry.source_document == "doc_1"
        assert entry.checksum is not None
    
    def test_track_relationship(self):
        """Test tracking relationship provenance."""
        prov_mgr = ProvenanceManager()
        
        entry = prov_mgr.track_relationship(
            relationship_id="rel_1",
            source="doc_1",
            metadata={"type": "founded"}
        )
        
        assert entry is not None
        assert entry.entity_id == "rel_1"
        assert entry.entity_type == "relationship"
    
    def test_track_chunk(self):
        """Test tracking chunk provenance."""
        prov_mgr = ProvenanceManager()
        
        entry = prov_mgr.track_chunk(
            chunk_id="chunk_1",
            source_document="doc_1",
            source_path="/path/to/doc.pdf",
            start_index=0,
            end_index=500
        )
        
        assert entry is not None
        assert entry.entity_id == "chunk_1"
        assert entry.entity_type == "chunk"
        assert entry.start_index == 0
        assert entry.end_index == 500
    
    def test_track_property_source(self):
        """Test tracking property source."""
        prov_mgr = ProvenanceManager()
        
        source = SourceReference(
            document="DOI:10.1038/...",
            page=4,
            confidence=0.92
        )
        
        entry = prov_mgr.track_property_source(
            entity_id="entity_1",
            property_name="biomass_increase",
            value="463%",
            source=source
        )
        
        assert entry is not None
        assert entry.entity_type == "property"
        assert entry.metadata["property_name"] == "biomass_increase"
    
    def test_get_lineage(self):
        """Test getting complete lineage."""
        prov_mgr = ProvenanceManager()
        
        # Create lineage chain
        prov_mgr.track_entity("entity_1", "doc_1")
        prov_mgr.track_chunk(
            chunk_id="chunk_1",
            source_document="doc_1",
            parent_chunk_id="entity_1"
        )
        
        lineage = prov_mgr.get_lineage("chunk_1")
        
        assert lineage is not None
        assert "lineage_chain" in lineage
        assert len(lineage["lineage_chain"]) > 0

    def test_get_lineage_via_derived_from_metadata(self):
        """metadata['derived_from'] should link entities into the lineage chain
        even when they share a source URL rather than one being a known entity_id."""
        prov_mgr = ProvenanceManager()

        prov_mgr.track_entity(
            entity_id="doc:X",
            source="https://example.com/api",
            metadata={"content_type": "drug_label"},
        )
        prov_mgr.track_entity(
            entity_id="decision:Y",
            source="https://example.com/api",
            metadata={"derived_from": "doc:X"},
        )

        lineage = prov_mgr.get_lineage("decision:Y")

        assert lineage["entity_count"] == 2
        entity_ids = [e["entity_id"] for e in lineage["lineage_chain"]]
        assert "doc:X" in entity_ids
        assert "decision:Y" in entity_ids

    def test_derived_from_does_not_override_explicit_parent(self):
        """An explicit parent_entity_id kwarg should win over metadata['derived_from']."""
        prov_mgr = ProvenanceManager()

        prov_mgr.track_entity(entity_id="explicit_parent", source="doc_1")
        prov_mgr.track_entity(entity_id="ignored_parent", source="doc_1")
        entry = prov_mgr.track_entity(
            entity_id="child",
            source="doc_1",
            metadata={"derived_from": "ignored_parent"},
            parent_entity_id="explicit_parent",
        )

        assert entry.parent_entity_id == "explicit_parent"

    def test_derived_from_takes_precedence_over_source_as_entity_id(self):
        """If `source` happens to also be a known entity_id, an explicit
        metadata['derived_from'] should still win over that fallback linking."""
        prov_mgr = ProvenanceManager()

        prov_mgr.track_entity(entity_id="source_as_entity", source="doc_0")
        prov_mgr.track_entity(entity_id="real_parent", source="doc_0")
        entry = prov_mgr.track_entity(
            entity_id="child",
            source="source_as_entity",  # resolvable as an entity_id
            metadata={"derived_from": "real_parent"},
        )

        assert entry.parent_entity_id == "real_parent"

    def test_derived_from_nonexistent_entity_does_not_crash(self):
        """derived_from pointing at an entity that was never tracked should be
        stored as the parent link without raising, and lineage traversal should
        stop gracefully instead of erroring."""
        prov_mgr = ProvenanceManager()

        entry = prov_mgr.track_entity(
            entity_id="orphan_child",
            source="doc_1",
            metadata={"derived_from": "never_tracked"},
        )

        assert entry.parent_entity_id == "never_tracked"

        lineage = prov_mgr.get_lineage("orphan_child")
        entity_ids = [e["entity_id"] for e in lineage["lineage_chain"]]
        assert entity_ids == ["orphan_child"]

    def test_derived_from_non_string_is_ignored(self):
        """A non-string derived_from value (e.g. accidentally passing an int or
        list) should be ignored rather than raising or being used as a parent id."""
        prov_mgr = ProvenanceManager()

        entry = prov_mgr.track_entity(
            entity_id="entity_bad_derived_from",
            source="doc_1",
            metadata={"derived_from": 12345},
        )

        assert entry.parent_entity_id is None

    def test_derived_from_empty_string_is_ignored(self):
        """An empty-string derived_from is falsy and should not be treated as a parent link."""
        prov_mgr = ProvenanceManager()

        entry = prov_mgr.track_entity(
            entity_id="entity_empty_derived_from",
            source="doc_1",
            metadata={"derived_from": ""},
        )

        assert entry.parent_entity_id is None

    def test_derived_from_self_reference_does_not_infinite_loop(self):
        """An entity that (incorrectly) declares itself as its own derived_from
        parent should not cause get_lineage to hang or infinitely recurse."""
        prov_mgr = ProvenanceManager()

        prov_mgr.track_entity(
            entity_id="self_ref",
            source="doc_1",
            metadata={"derived_from": "self_ref"},
        )

        lineage = prov_mgr.get_lineage("self_ref")
        entity_ids = [e["entity_id"] for e in lineage["lineage_chain"]]
        assert entity_ids == ["self_ref"]

    def test_derived_from_multi_hop_chain(self):
        """derived_from links should chain transitively: A <- B <- C should
        all appear when tracing lineage from C."""
        prov_mgr = ProvenanceManager()

        prov_mgr.track_entity(entity_id="grandparent", source="doc_1")
        prov_mgr.track_entity(
            entity_id="parent",
            source="doc_1",
            metadata={"derived_from": "grandparent"},
        )
        prov_mgr.track_entity(
            entity_id="child",
            source="doc_1",
            metadata={"derived_from": "parent"},
        )

        lineage = prov_mgr.get_lineage("child")

        assert lineage["entity_count"] == 3
        entity_ids = {e["entity_id"] for e in lineage["lineage_chain"]}
        assert entity_ids == {"grandparent", "parent", "child"}

    def test_derived_from_without_metadata_dict_does_not_crash(self):
        """track_entity called with no metadata at all should behave as before
        (no parent link derived), exercising the `metadata and isinstance(...)` guard."""
        prov_mgr = ProvenanceManager()

        entry = prov_mgr.track_entity(entity_id="no_metadata_entity", source="doc_1")

        assert entry.parent_entity_id is None

    def test_get_lineage_metadata_prefers_queried_entity_over_ancestors(self):
        """Aggregated lineage metadata should let the queried entity's own
        values win over ancestor values on conflicting keys, matching the
        documented "most recent entry's metadata takes precedence" intent."""
        prov_mgr = ProvenanceManager()

        prov_mgr.track_entity(
            entity_id="ancestor",
            source="doc_1",
            metadata={"status": "draft", "shared_only_on_ancestor": True},
        )
        prov_mgr.track_entity(
            entity_id="descendant",
            source="doc_1",
            metadata={"status": "final", "derived_from": "ancestor"},
        )

        lineage = prov_mgr.get_lineage("descendant")

        assert lineage["metadata"]["status"] == "final"
        assert lineage["metadata"]["shared_only_on_ancestor"] is True

    def test_derived_from_accepts_non_dict_mapping(self):
        """metadata['derived_from'] should be honored for any Mapping
        implementation, not just a concrete dict (e.g. types.MappingProxyType
        or a custom collections.abc.Mapping)."""
        from types import MappingProxyType

        prov_mgr = ProvenanceManager()

        prov_mgr.track_entity(entity_id="mapping_parent", source="doc_1")
        entry = prov_mgr.track_entity(
            entity_id="mapping_child",
            source="doc_1",
            metadata=MappingProxyType({"derived_from": "mapping_parent"}),
        )

        assert entry.parent_entity_id == "mapping_parent"

        lineage = prov_mgr.get_lineage("mapping_child")
        assert lineage["entity_count"] == 2

    def test_batch_entity_tracking(self):
        """Test batch entity tracking."""
        prov_mgr = ProvenanceManager()
        
        entities = [
            {"id": "entity_1", "confidence": 0.9},
            {"id": "entity_2", "confidence": 0.85}
        ]
        
        count = prov_mgr.track_entities_batch(entities, "doc_1")
        
        assert count == 2
    
    def test_batch_chunk_tracking(self):
        """Test batch chunk tracking."""
        prov_mgr = ProvenanceManager()
        
        chunks = [
            {"id": "chunk_1", "start_index": 0, "end_index": 100},
            {"id": "chunk_2", "start_index": 100, "end_index": 200}
        ]
        
        count = prov_mgr.track_chunks_batch(chunks, "doc_1")
        
        assert count == 2
    
    def test_get_statistics(self):
        """Test getting provenance statistics."""
        prov_mgr = ProvenanceManager()
        
        prov_mgr.track_entity("entity_1", "doc_1")
        prov_mgr.track_chunk("chunk_1", "doc_1")
        
        stats = prov_mgr.get_statistics()
        
        assert stats["total_entries"] == 2
        assert "entity_types" in stats
    
    def test_clear(self):
        """Test clearing provenance data."""
        prov_mgr = ProvenanceManager()
        
        prov_mgr.track_entity("entity_1", "doc_1")
        count = prov_mgr.clear()
        
        assert count == 1
        
        lineage = prov_mgr.get_lineage("entity_1")
        assert lineage == {}

    def test_retrack_with_explicit_parent_overrides_history_link(self):
        """#742 — re-tracking an entity with an explicit parent_entity_id must
        honor the new value, not silently replace it with an auto-generated
        history pointer."""
        prov_mgr = ProvenanceManager()

        e1 = prov_mgr.track_entity("X", source="doc_1", parent_entity_id="parent_v1")
        e2 = prov_mgr.track_entity("X", source="doc_1", parent_entity_id="parent_v2")

        assert e1.parent_entity_id == "parent_v1"
        assert e2.parent_entity_id == "parent_v2"

    def test_retrack_without_explicit_parent_still_uses_history_link(self):
        """#742 — when NO explicit parent is given on a re-track call, the
        auto-generated history link (Y:v:<timestamp>) should still be used,
        preserving pre-existing behavior for callers that don't supply a parent."""
        prov_mgr = ProvenanceManager()

        y1 = prov_mgr.track_entity("Y", source="doc_1")
        y2 = prov_mgr.track_entity("Y", source="doc_1")

        assert y1.parent_entity_id is None
        assert y2.parent_entity_id is not None
        assert y2.parent_entity_id.startswith("Y:v:")

    def test_retrack_with_derived_from_overrides_history_link(self):
        """#742 — re-tracking with metadata['derived_from'] (no parent_entity_id
        kwarg) should also override the auto-generated history link, not just
        the parent_entity_id kwarg case."""
        prov_mgr = ProvenanceManager()

        prov_mgr.track_entity("parent_A", source="doc_1")
        prov_mgr.track_entity("parent_B", source="doc_1")

        e1 = prov_mgr.track_entity("Z", source="doc_1", metadata={"derived_from": "parent_A"})
        e2 = prov_mgr.track_entity("Z", source="doc_1", metadata={"derived_from": "parent_B"})

        assert e1.parent_entity_id == "parent_A"
        assert e2.parent_entity_id == "parent_B"

    def test_retrack_history_reachable_via_used_entities(self):
        """#742 — when re-tracking with an explicit parent, the archived history
        entry for the previous version must still be reachable in the lineage
        chain via used_entities (prov:used), even though it's no longer the
        direct parent_entity_id."""
        prov_mgr = ProvenanceManager()

        prov_mgr.track_entity("explicit_parent", source="doc_1")
        prov_mgr.track_entity("X", source="doc_1")  # first track, no parent

        # Re-track with an explicit parent — should NOT lose the history entry
        e2 = prov_mgr.track_entity("X", source="doc_1", parent_entity_id="explicit_parent")

        assert e2.parent_entity_id == "explicit_parent"
        assert len(e2.used_entities) == 1
        assert e2.used_entities[0].startswith("X:v:")

        # trace_lineage should reach: X, explicit_parent (via parent_entity_id),
        # AND the archived history snapshot (via used_entities)
        lineage = prov_mgr.get_lineage("X")
        entity_ids = {e["entity_id"] for e in lineage["lineage_chain"]}

        assert "X" in entity_ids
        assert "explicit_parent" in entity_ids
        assert e2.used_entities[0] in entity_ids, (
            "Archived history entry should be reachable via used_entities in lineage"
        )

    def test_cli_lineage(self):
        """Test CLI lineage wrapper method on ProvenanceManager."""
        prov_mgr = ProvenanceManager()
        prov_mgr.track_entity("e_cli", source="doc_cli")
        res = prov_mgr.lineage("e_cli", depth=2)
        assert res["entity_id"] == "e_cli"
        assert res["depth"] == 2
        assert isinstance(res["lineage"], list)
        assert len(res["lineage"]) > 0
        assert len(res["entries"]) > 0
        assert res["lineage"][0]["entity_id"] == "e_cli"
        assert isinstance(res["sources"], list)

    def test_cli_audit_log(self):
        """Test CLI audit_log wrapper method on ProvenanceManager."""
        prov_mgr = ProvenanceManager()
        prov_mgr.track_entity("e_audit", source="doc_audit")
        res_table = prov_mgr.audit_log(format="table")
        assert isinstance(res_table, str)
        assert "ENTITY_ID" in res_table
        res_csv = prov_mgr.audit_log(format="csv")
        assert "entity_id,entity_type,activity_id,agent_id,timestamp" in res_csv
        res_json = prov_mgr.audit_log(format="json")
        assert isinstance(res_json, list)

    def test_cli_export_prov(self):
        """Test CLI export_prov method on ProvenanceManager."""
        prov_mgr = ProvenanceManager()
        prov_mgr.track_entity("e_parent", source="doc_rdf")
        prov_mgr.track_entity(
            "e_child",
            source="doc_rdf",
            parent_entity_id="e_parent",
            used_entities=["e_parent"],
            activity_id="act_transform",
        )
        ttl = prov_mgr.export_prov(format="turtle")
        assert "prov:Entity" in ttl or "http://www.w3.org/ns/prov#Entity" in ttl
        assert "wasDerivedFrom" in ttl
        assert "used" in ttl

    def test_cli_check(self):
        """Test CLI check integrity method on ProvenanceManager."""
        prov_mgr = ProvenanceManager()
        prov_mgr.track_entity("e_valid_parent", source="doc_1")
        prov_mgr.track_entity(
            "e_valid_child",
            source="doc_1",
            parent_entity_id="e_valid_parent",
            used_entities=["e_valid_parent"],
        )
        check_res = prov_mgr.check(strict=True)
        assert check_res["valid"] is True
        assert check_res["total_entries"] >= 2
        assert check_res["errors"] == 0

        # Confirm non-strict mode still reports valid=False and errors > 0 when references are missing
        prov_mgr.track_entity(
            "e_broken_child",
            source="doc_1",
            parent_entity_id="non_existent_parent",
        )
        check_broken = prov_mgr.check(strict=False)
        assert check_broken["valid"] is False
        assert check_broken["errors"] >= 1
        assert "e_broken_child -> non_existent_parent" in check_broken["missing_references"]

    def test_track_entity_storage_error_swallowed(self):
        """Test that track_entity returns None when storage.store() fails on a brand-new entity,
        since nothing was persisted (#782)."""
        prov_mgr = ProvenanceManager()
        with patch.object(prov_mgr.storage, "store", side_effect=RuntimeError("storage error")):
            entry = prov_mgr.track_entity("e_test", source="doc_1")
            # Returning None is correct because nothing was actually persisted,
            # and the old assertion was encoding the bug this issue was filed to fix.
            assert entry is None

    def test_track_relationship_storage_error_swallowed(self):
        """Test that track_relationship returns None when storage.store() fails,
        since nothing was persisted (#783)."""
        prov_mgr = ProvenanceManager()
        with patch.object(prov_mgr.storage, "store", side_effect=RuntimeError("storage error")):
            entry = prov_mgr.track_relationship("r_test", source="doc_1")
            # Returning None is correct because nothing was actually persisted,
            # and the old assertion was encoding the bug this issue was filed to fix.
            assert entry is None

    def test_track_chunk_storage_error_swallowed(self):
        """Test that track_chunk returns None when storage.store() fails,
        since nothing was persisted (#783)."""
        prov_mgr = ProvenanceManager()
        with patch.object(prov_mgr.storage, "store", side_effect=RuntimeError("storage error")):
            entry = prov_mgr.track_chunk(
                chunk_id="c_test",
                source_document="doc_1",
                source_path="/path/to/doc.pdf",
                start_index=0,
                end_index=100,
            )
            # Returning None is correct because nothing was actually persisted,
            # and the old assertion was encoding the bug this issue was filed to fix.
            assert entry is None

    def test_track_property_source_storage_error_swallowed(self):
        """Test that track_property_source returns None when storage.store() fails,
        since nothing was persisted (#783)."""
        prov_mgr = ProvenanceManager()
        source = SourceReference(document="doc_1", page=1, confidence=0.9)
        with patch.object(prov_mgr.storage, "store", side_effect=RuntimeError("storage error")):
            entry = prov_mgr.track_property_source(
                entity_id="e_test",
                property_name="prop_test",
                value="val",
                source=source,
            )
            # Returning None is correct because nothing was actually persisted,
            # and the old assertion was encoding the bug this issue was filed to fix.
            assert entry is None

    def test_save_entry_logs_on_every_failure_path(self):
        """Test that _save_entry logs on storage failures for both raising and swallowing paths (#783)."""
        prov_mgr = ProvenanceManager()
        entry = ProvenanceEntry(
            entity_id="log_test_id",
            entity_type="entity",
            activity_id="test",
            source_document="doc_1",
            first_seen=datetime.utcnow().isoformat(),
            last_updated=datetime.utcnow().isoformat(),
        )
        with patch.object(prov_mgr.storage, "store", side_effect=RuntimeError("storage error")), \
             patch.object(prov_mgr.logger, "error") as mock_log_error:
            # Swallowing branch (_raise_on_error=False)
            res = prov_mgr._save_entry(entry, _raise_on_error=False)
            assert res is None
            mock_log_error.assert_called_once()
            assert "log_test_id" in mock_log_error.call_args[0][1]

            mock_log_error.reset_mock()

            # Raising branch (_raise_on_error=True)
            with pytest.raises(RuntimeError, match="storage error"):
                prov_mgr._save_entry(entry, _raise_on_error=True)
            mock_log_error.assert_called_once()
            assert "log_test_id" in mock_log_error.call_args[0][1]

    def test_track_entities_batch_logs_per_item_failure(self):
        """Test that track_entities_batch emits item-level logs via _save_entry when items fail (#783)."""
        prov_mgr = ProvenanceManager()
        entities = [{"id": "e_fail_1"}, {"id": "e_fail_2"}]
        with patch.object(prov_mgr.storage, "_store_with_conn", side_effect=RuntimeError("batch store error")), \
             patch.object(prov_mgr.logger, "error") as mock_log_error:
            count = prov_mgr.track_entities_batch(entities, "doc_1")
            assert count == 0
            assert mock_log_error.call_count == 2

    def test_track_entity_pre_build_failure_fallback_skips_store(self):
        """Test that when track_entity fails before the entry is built (e.g. a
        retrieve error inside the atomic transaction) on a brand-new entity,
        it returns None (#782/#784)."""
        prov_mgr = ProvenanceManager()
        with patch.object(
            prov_mgr.storage, "_retrieve_with_conn", side_effect=RuntimeError("retrieve error")
        ), patch.object(prov_mgr.storage, "store") as mock_store:
            entry = prov_mgr.track_entity("e_test", source="doc_1")
            # Returning None is correct because nothing was actually persisted,
            # and the old assertion was encoding the bug this issue was filed to fix.
            assert entry is None
            mock_store.assert_not_called()

    @pytest.mark.parametrize("backend_type", ["memory", "sqlite"])
    def test_track_entity_atomic_rollback_on_history_write_failure(self, backend_type, tmp_path):
        """Test that history write failure rolls back transaction cleanly on both InMemory and SQLite storage."""
        if backend_type == "memory":
            class FlakyInMemory(InMemoryStorage):
                def __init__(self):
                    super().__init__()
                    self.store_calls = 0
                    self.fail_on_call = None
                def _store_with_conn(self, conn, entry):
                    self.store_calls += 1
                    if self.store_calls == self.fail_on_call:
                        raise RuntimeError(f"Simulated error on call {self.store_calls}")
                    super()._store_with_conn(conn, entry)
            storage = FlakyInMemory()
        else:
            db_path = str(tmp_path / "test_hist.db")
            class FlakySQLite(SQLiteStorage):
                def __init__(self, path):
                    super().__init__(path)
                    self.store_calls = 0
                    self.fail_on_call = None
                def _store_with_conn(self, conn, entry):
                    self.store_calls += 1
                    if self.store_calls == self.fail_on_call:
                        raise RuntimeError(f"Simulated error on call {self.store_calls}")
                    super()._store_with_conn(conn, entry)
            storage = FlakySQLite(db_path)

        mgr = ProvenanceManager(storage=storage)
        v1 = mgr.track_entity("e1", source="doc1")
        assert v1.source_document == "doc1"

        storage.fail_on_call = 2
        # Standalone call should not raise, should return pre-failure state (v1)
        res = mgr.track_entity("e1", source="doc2")
        in_storage = storage.retrieve("e1")
        assert res.source_document == "doc1"
        assert in_storage.source_document == "doc1"
        assert [e.entity_id for e in storage.retrieve_all()] == ["e1"]

        # Batch call (_conn supplied) should raise
        storage.store_calls = 1
        with pytest.raises(RuntimeError):
            with mgr._get_or_create_transaction() as conn:
                mgr.track_entity("e1", source="doc2", _conn=conn)

    @pytest.mark.parametrize("backend_type", ["memory", "sqlite"])
    def test_track_entity_atomic_rollback_on_primary_write_failure(self, backend_type, tmp_path):
        """Test that primary write failure after history write rolls back the entire transaction."""
        if backend_type == "memory":
            class FlakyInMemory(InMemoryStorage):
                def __init__(self):
                    super().__init__()
                    self.store_calls = 0
                    self.fail_on_call = None
                def _store_with_conn(self, conn, entry):
                    self.store_calls += 1
                    if self.store_calls == self.fail_on_call:
                        raise RuntimeError(f"Simulated error on call {self.store_calls}")
                    super()._store_with_conn(conn, entry)
            storage = FlakyInMemory()
        else:
            db_path = str(tmp_path / "test_prim.db")
            class FlakySQLite(SQLiteStorage):
                def __init__(self, path):
                    super().__init__(path)
                    self.store_calls = 0
                    self.fail_on_call = None
                def _store_with_conn(self, conn, entry):
                    self.store_calls += 1
                    if self.store_calls == self.fail_on_call:
                        raise RuntimeError(f"Simulated error on call {self.store_calls}")
                    super()._store_with_conn(conn, entry)
            storage = FlakySQLite(db_path)

        mgr = ProvenanceManager(storage=storage)
        v1 = mgr.track_entity("e1", source="doc1")
        assert v1.source_document == "doc1"

        storage.fail_on_call = 3
        # Standalone call should not raise, should return pre-failure state (v1)
        res = mgr.track_entity("e1", source="doc2")
        in_storage = storage.retrieve("e1")
        assert res.source_document == "doc1"
        assert in_storage.source_document == "doc1"
        assert [e.entity_id for e in storage.retrieve_all()] == ["e1"]

        # Batch call (_conn supplied) should raise
        storage.store_calls = 1
        with pytest.raises(RuntimeError):
            with mgr._get_or_create_transaction() as conn:
                mgr.track_entity("e1", source="doc2", _conn=conn)

    @pytest.mark.parametrize("backend_type", ["memory", "sqlite"])
    def test_track_entity_rollback_returns_safe_copy(self, backend_type, tmp_path):
        """Test that after a rollback returning the existing entry, mutating the returned object does not affect storage."""
        if backend_type == "memory":
            class FlakyInMemory(InMemoryStorage):
                def __init__(self):
                    super().__init__()
                    self.store_calls = 0
                    self.fail_on_call = None
                def _store_with_conn(self, conn, entry):
                    self.store_calls += 1
                    if self.store_calls == self.fail_on_call:
                        raise RuntimeError(f"Simulated error on call {self.store_calls}")
                    super()._store_with_conn(conn, entry)
            storage = FlakyInMemory()
        else:
            db_path = str(tmp_path / "test_safe_copy.db")
            class FlakySQLite(SQLiteStorage):
                def __init__(self, path):
                    super().__init__(path)
                    self.store_calls = 0
                    self.fail_on_call = None
                def _store_with_conn(self, conn, entry):
                    self.store_calls += 1
                    if self.store_calls == self.fail_on_call:
                        raise RuntimeError(f"Simulated error on call {self.store_calls}")
                    super()._store_with_conn(conn, entry)
            storage = FlakySQLite(db_path)

        mgr = ProvenanceManager(storage=storage)
        v1 = mgr.track_entity("e1", source="doc1", metadata={"key": "val"})
        assert v1.source_document == "doc1"

        # Force failure on update
        storage.fail_on_call = 2
        res = mgr.track_entity("e1", source="doc2")
        assert res.source_document == "doc1"

        # Mutate the returned pre-failure object
        res.source_document = "mutated"
        res.metadata["tampered"] = True

        # Assert stored copy in storage is completely unchanged
        in_storage = storage.retrieve("e1")
        assert in_storage.source_document == "doc1"
        assert in_storage.metadata == {"key": "val"}
        assert "tampered" not in in_storage.metadata

    @pytest.mark.parametrize("backend_type", ["memory", "sqlite"])
    def test_track_entities_batch_per_item_savepoint_rollback(self, backend_type, tmp_path):
        """Test that in batch mode, an exception during primary write rolls back any staged history archive for that item."""
        if backend_type == "memory":
            class FlakyInMemory(InMemoryStorage):
                def __init__(self):
                    super().__init__()
                    self.store_calls = 0
                    self.fail_on_call = None
                def _store_with_conn(self, conn, entry):
                    self.store_calls += 1
                    if self.store_calls == self.fail_on_call:
                        raise RuntimeError(f"Simulated error on call {self.store_calls}")
                    super()._store_with_conn(conn, entry)
            storage = FlakyInMemory()
        else:
            db_path = str(tmp_path / "test_batch_sp.db")
            class FlakySQLite(SQLiteStorage):
                def __init__(self, path):
                    super().__init__(path)
                    self.store_calls = 0
                    self.fail_on_call = None
                def _store_with_conn(self, conn, entry):
                    self.store_calls += 1
                    if self.store_calls == self.fail_on_call:
                        raise RuntimeError(f"Simulated error on call {self.store_calls}")
                    super()._store_with_conn(conn, entry)
            storage = FlakySQLite(db_path)

        mgr = ProvenanceManager(storage=storage)
        v1 = mgr.track_entity("e1", source="doc1")
        assert v1.source_document == "doc1"

        # Fail on call 3 (the primary update for e1, after its history entry was stored on call 2)
        storage.fail_on_call = 3
        count = mgr.track_entities_batch(
            [{"id": "e1"}, {"id": "e2"}],
            source="doc_batch"
        )

        assert count == 1  # Only e2 should succeed
        all_entries = {e.entity_id: e for e in storage.retrieve_all()}

        # Assert e2 is present
        assert "e2" in all_entries
        assert all_entries["e2"].source_document == "doc_batch"

        # Assert e1 is untouched and NO history archive was left behind
        assert all_entries["e1"].source_document == "doc1"
        assert not any(":v:" in eid for eid in all_entries.keys()), f"Found leaked history entry: {list(all_entries.keys())}"

    def test_track_entity_logs_exception_with_exc_info(self):
        """Test that track_entity logs errors with exc_info=True when a storage write fails."""
        class FlakyInMemory(InMemoryStorage):
            def _store_with_conn(self, conn, entry):
                raise RuntimeError("Simulated write failure")
        storage = FlakyInMemory()
        mgr = ProvenanceManager(storage=storage)

        with patch.object(mgr.logger, "error") as mock_error:
            res = mgr.track_entity("e1", source="doc1")
            assert res is None
            assert mock_error.called
            _, kwargs = mock_error.call_args
            assert kwargs.get("exc_info") is True




