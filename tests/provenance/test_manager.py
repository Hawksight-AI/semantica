"""
Test Unified Provenance Manager

Tests for ProvenanceManager functionality including entity tracking,
chunk tracking, source tracking, and lineage tracing.
"""

import pytest
import warnings
from unittest.mock import patch
from datetime import datetime, timedelta, timezone
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

    def test_clear_resets_chain_state(self):
        """Regression: clear() must fully reset chain state so the first write
        after clear starts a fresh chain and verify_chain() passes."""
        prov_mgr = ProvenanceManager()

        prov_mgr.track_entity("e1", source="doc1")
        prov_mgr.track_entity("e2", source="doc1")
        prov_mgr.clear()

        # Chain head must be empty immediately after clear
        assert prov_mgr.storage.get_chain_head() is None

        # First write after clear starts a fresh chain (sequence_id=1, previous_checksum=None)
        entry = prov_mgr.track_entity("e3", source="doc2")
        assert entry.sequence_id == 1
        assert entry.previous_checksum is None

        # verify_chain() must pass on the fresh chain
        prov_mgr.track_entity("e4", source="doc2")
        result = prov_mgr.verify_chain()
        assert result["valid"] is True
        assert result["total_entries"] == 2
        assert result["broken_links"] == []

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

    def test_track_relationship_storage_error_swallowed_sqlite(self, tmp_path):
        """Test that track_relationship returns None when storage.store() fails
        on the SQLite backend, mirroring the InMemory contract verified by
        test_track_relationship_storage_error_swallowed (#783/#785)."""
        db_path = str(tmp_path / "test_track_relationship_sqlite.db")
        prov_mgr = ProvenanceManager(storage_path=db_path)
        with patch.object(prov_mgr.storage, "store", side_effect=RuntimeError("storage error")):
            entry = prov_mgr.track_relationship("r_test", source="doc_1")
            # Returning None is correct because nothing was actually persisted,
            # and the old assertion was encoding the bug this issue was filed to fix.
            assert entry is None

    def test_track_chunk_storage_error_swallowed_sqlite(self, tmp_path):
        """Test that track_chunk returns None when storage.store() fails
        on the SQLite backend, mirroring the InMemory contract verified by
        test_track_chunk_storage_error_swallowed (#783/#785)."""
        db_path = str(tmp_path / "test_track_chunk_sqlite.db")
        prov_mgr = ProvenanceManager(storage_path=db_path)
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

    def test_track_property_source_storage_error_swallowed_sqlite(self, tmp_path):
        """Test that track_property_source returns None when storage.store() fails
        on the SQLite backend, mirroring the InMemory contract verified by
        test_track_property_source_storage_error_swallowed (#783/#785)."""
        db_path = str(tmp_path / "test_track_property_source_sqlite.db")
        prov_mgr = ProvenanceManager(storage_path=db_path)
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
            first_seen=datetime.now(timezone.utc).isoformat(),
            last_updated=datetime.now(timezone.utc).isoformat(),
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

    def test_chunks_batch_logs_per_item_failure_memory(self):
        """Test that track_chunks_batch emits item-level logs via _save_entry when items fail,
        mirroring test_track_entities_batch_logs_per_item_failure for the chunk path (#783/#785)."""
        prov_mgr = ProvenanceManager()
        chunks = [
            {"id": "chk_fail_1", "start_index": 0, "end_index": 10},
            {"id": "chk_fail_2", "start_index": 0, "end_index": 10},
        ]
        with patch.object(prov_mgr.storage, "_store_with_conn", side_effect=RuntimeError("batch store error")), \
             patch.object(prov_mgr.logger, "error") as mock_log_error:
            count = prov_mgr.track_chunks_batch(chunks, source_document="doc_1")
            assert count == 0
            assert mock_log_error.call_count == 2

    def test_track_chunks_batch_block_level_transaction_failure_logs(self, tmp_path):
        """Test that track_chunks_batch logs the block-level failure message when the
        shared transaction itself fails to commit, mirroring the entities-batch coverage
        established by test_batch_rollback_does_not_count_unpersisted_entries (#807/#785)."""
        from contextlib import contextmanager
        import sqlite3

        db_path = str(tmp_path / "test_chunks_block_level_failure.db")
        prov_mgr = ProvenanceManager(storage_path=db_path)
        chunks = [{"id": f"chk_{i}", "start_index": 0, "end_index": 10} for i in range(5)]

        # Capture the unpatched bound method first: once `transaction` is patched below,
        # `prov_mgr.storage.transaction` would resolve to the mock itself, and calling it
        # from inside failing_tx() would recurse into the mock instead of the real
        # implementation (RecursionError, not the intended sqlite3.OperationalError).
        orig_transaction = prov_mgr.storage.transaction

        @contextmanager
        def failing_tx():
            with orig_transaction() as conn:
                yield conn
                raise sqlite3.OperationalError("Commit failed")

        with patch.object(prov_mgr.storage, "transaction", side_effect=failing_tx), \
             patch.object(prov_mgr.logger, "error") as mock_log_error:
            count = prov_mgr.track_chunks_batch(chunks, source_document="doc_1")
            assert count == 0
            mock_log_error.assert_called_once()
            assert "Block-level storage transaction failed in track_chunks_batch" in mock_log_error.call_args[0][0]
            # Confirm the logged exception is the injected commit failure, not some
            # other failure mode (e.g. a mocking mistake re-entering the patched mock).
            logged_exc = mock_log_error.call_args[0][1]
            assert isinstance(logged_exc, sqlite3.OperationalError)
            assert str(logged_exc) == "Commit failed"

        assert len(prov_mgr.storage.retrieve_all()) == 0

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


class TestAgentTyping:
    """Issue #825, Part A item 3 — agent_id/agent_type/is_automated actually
    populate on tracked entries (previously a dead field: no track_* method
    read agent_id from kwargs at all)."""

    def test_track_entity_scalar_agent_kwargs(self):
        prov_mgr = ProvenanceManager()
        entry = prov_mgr.track_entity(
            "e1", source="doc1",
            agent_id="alice", agent_type="person", is_automated=False, role="approver",
        )
        assert entry.agent_id == "alice"
        assert entry.agent_type == "person"
        assert entry.is_automated is False
        assert entry.role == "approver"

    def test_track_entity_agent_record_kwarg(self):
        from semantica.provenance import AgentRecord
        prov_mgr = ProvenanceManager()
        agent = AgentRecord(id="reviewer_bob", agent_type="person", is_automated=False)
        entry = prov_mgr.track_entity("e1", source="doc1", agent=agent, role="approver")
        assert entry.agent_id == "reviewer_bob"
        assert entry.agent_type == "person"
        assert entry.is_automated is False
        assert entry.role == "approver"

    def test_track_entity_default_agent_unchanged(self):
        """No agent kwargs supplied should still default to 'semantica' (back-compat)."""
        prov_mgr = ProvenanceManager()
        entry = prov_mgr.track_entity("e1", source="doc1")
        assert entry.agent_id == "semantica"
        assert entry.agent_type == "software_agent"
        assert entry.is_automated is True

    def test_track_relationship_agent_kwargs(self):
        prov_mgr = ProvenanceManager()
        entry = prov_mgr.track_relationship("r1", source="doc1", agent_id="bot1")
        assert entry.agent_id == "bot1"

    def test_track_chunk_agent_kwargs_not_leaked_into_metadata(self):
        """agent_id/agent_type/is_automated passed to track_chunk must populate
        the real fields, not leak into the opaque metadata blob."""
        prov_mgr = ProvenanceManager()
        entry = prov_mgr.track_chunk(
            "c1", source_document="doc1", agent_id="chunker_v2", note="hello"
        )
        assert entry.agent_id == "chunker_v2"
        assert "agent_id" not in entry.metadata
        assert entry.metadata.get("note") == "hello"

    def test_track_property_source_agent_kwargs(self):
        prov_mgr = ProvenanceManager()
        source = SourceReference(document="doc1")
        entry = prov_mgr.track_property_source(
            "e1", "prop", "value", source, agent_id="prop_tracker"
        )
        assert entry.agent_id == "prop_tracker"
        assert "agent_id" not in entry.metadata

    def test_track_entities_batch_agent_id_not_swallowed_into_metadata(self):
        """Regression test for the documented bug: track_entities_batch used to
        merge agent_id/entity_type/activity_id into the metadata dict instead
        of forwarding them as real track_entity kwargs."""
        prov_mgr = ProvenanceManager()
        count = prov_mgr.track_entities_batch(
            [{"id": "b1"}, {"id": "b2"}],
            source="doc_batch",
            agent_id="batch_service_v2",
            entity_type="credit_feature",
            activity_id="bureau_parsing",
            extra_note="kept as free-form metadata",
        )
        assert count == 2
        for eid in ("b1", "b2"):
            entry = prov_mgr.storage.retrieve(eid)
            assert entry.agent_id == "batch_service_v2"
            assert entry.entity_type == "credit_feature"
            assert entry.activity_id == "bureau_parsing"
            assert "agent_id" not in entry.metadata
            assert entry.metadata.get("extra_note") == "kept as free-form metadata"


class TestVersioningVsDerivation:
    """Issue #825, Part A item 4 — previous_version_id (correction) is
    additive alongside derived_from_id (cross-source derivation); both are
    populated without disturbing the legacy parent_entity_id field."""

    def test_retrack_without_parent_sets_previous_version_id_only(self):
        prov_mgr = ProvenanceManager()
        prov_mgr.track_entity("X", source="doc_1")
        v2 = prov_mgr.track_entity("X", source="doc_1")

        assert v2.previous_version_id is not None
        assert v2.previous_version_id.startswith("X:v:")
        assert v2.derived_from_id is None
        # Legacy field behavior is unchanged
        assert v2.parent_entity_id == v2.previous_version_id

    def test_retrack_with_explicit_parent_sets_both_fields(self):
        prov_mgr = ProvenanceManager()
        prov_mgr.track_entity("X", source="doc_1")
        v2 = prov_mgr.track_entity("X", source="doc_1", parent_entity_id="explicit_parent")

        assert v2.derived_from_id == "explicit_parent"
        assert v2.previous_version_id is not None
        assert v2.previous_version_id.startswith("X:v:")
        # Legacy field keeps explicit-wins semantics
        assert v2.parent_entity_id == "explicit_parent"

    def test_track_chunk_split_sets_derived_from_id(self):
        prov_mgr = ProvenanceManager()
        entry = prov_mgr.track_chunk(
            "c2", source_document="doc1", parent_chunk_id="c1"
        )
        assert entry.derived_from_id == "c1"
        assert entry.previous_version_id is None
        assert entry.parent_entity_id == "c1"


class TestInvalidation:
    """Issue #825, Part A item 1 — tombstone instead of hard delete."""

    def test_invalidate_marks_entry_without_deleting(self):
        prov_mgr = ProvenanceManager()
        prov_mgr.track_entity("e1", source="doc1")

        result = prov_mgr.invalidate("e1", agent_id="reviewer_jane", reason="retracted")

        assert result.invalidated is True
        assert result.invalidated_by == "reviewer_jane"
        assert result.invalidation_reason == "retracted"
        assert result.invalidated_at_time is not None

        # Entry remains visible via retrieve (tombstone, not delete)
        stored = prov_mgr.storage.retrieve("e1")
        assert stored is not None
        assert stored.invalidated is True

    def test_invalidate_unknown_entity_raises(self):
        prov_mgr = ProvenanceManager()
        with pytest.raises(ValueError):
            prov_mgr.invalidate("never_tracked", agent_id="reviewer_jane")

    def test_check_reports_invalidated_count(self):
        prov_mgr = ProvenanceManager()
        prov_mgr.track_entity("e1", source="doc1")
        prov_mgr.track_entity("e2", source="doc1")
        prov_mgr.invalidate("e1", agent_id="reviewer_jane")

        result = prov_mgr.check()
        assert result["invalidated_count"] == 1


class TestHashChain:
    """Issue #825, Part A item 2 — hash-chained integrity: chained checksums
    detect wholesale row deletion, which per-row checksums alone cannot."""

    def test_verify_chain_valid_on_clean_history(self):
        prov_mgr = ProvenanceManager()
        prov_mgr.track_entity("e1", source="doc1")
        prov_mgr.track_entity("e2", source="doc1")
        prov_mgr.track_entity("X", source="doc1")
        prov_mgr.track_entity("X", source="doc1")  # triggers archival
        prov_mgr.track_entity("X", source="doc1", parent_entity_id="explicit_p")

        result = prov_mgr.verify_chain()
        assert result["valid"] is True
        assert result["broken_links"] == []
        assert result["total_entries"] == 5

    def test_verify_chain_detects_deleted_row(self, tmp_path):
        """A hard delete of a row must break the chain for whatever followed it."""
        import sqlite3
        db_path = str(tmp_path / "chain.db")
        prov_mgr = ProvenanceManager(storage_path=db_path)
        prov_mgr.track_entity("e1", source="doc1")
        prov_mgr.track_entity("e2", source="doc1")
        prov_mgr.track_entity("e3", source="doc1")

        conn = sqlite3.connect(db_path)
        conn.execute("DELETE FROM provenance WHERE entity_id = 'e2'")
        conn.commit()
        conn.close()

        prov_mgr2 = ProvenanceManager(storage_path=db_path)
        result = prov_mgr2.verify_chain()
        assert result["valid"] is False
        assert any(link["reason"] == "chain_break" for link in result["broken_links"])

    def test_verify_chain_detects_tampered_sequence_gap(self, tmp_path):
        """The sequence_id continuity check catches a gap introduced by
        directly tampering with a row's sequence_id column, independent of
        the previous_checksum comparison — hardening against the narrow case
        where compute_checksum()'s deliberate exclusion of entity_id could
        otherwise let two distinct rows coincidentally share a checksum."""
        import sqlite3
        db_path = str(tmp_path / "chain_seq_gap.db")
        prov_mgr = ProvenanceManager(storage_path=db_path)
        prov_mgr.track_entity("e1", source="doc1")
        prov_mgr.track_entity("e2", source="doc1")
        prov_mgr.track_entity("e3", source="doc1")

        conn = sqlite3.connect(db_path)
        conn.execute("UPDATE provenance SET sequence_id = 10 WHERE entity_id = 'e3'")
        conn.commit()
        conn.close()

        prov_mgr2 = ProvenanceManager(storage_path=db_path)
        result = prov_mgr2.verify_chain()
        assert result["valid"] is False
        broken = [link for link in result["broken_links"] if link["entity_id"] == "e3"]
        assert broken
        assert broken[0]["expected_sequence_id"] == 3

    def test_sequence_ids_are_assigned_and_monotonic(self):
        prov_mgr = ProvenanceManager()
        e1 = prov_mgr.track_entity("e1", source="doc1")
        e2 = prov_mgr.track_entity("e2", source="doc1")
        assert e1.sequence_id is not None
        assert e2.sequence_id is not None
        assert e2.sequence_id > e1.sequence_id
        assert e2.previous_checksum == e1.checksum

    def test_chain_survives_interleaved_retrack_and_invalidate(self, tmp_path):
        """Regression test: an entry that already chained its previous_checksum
        from another entity's checksum (Y -> X) must stay valid even after X
        is later retracked (archived/relabeled) and then invalidated — both
        of which write NEW entries under X's canonical key. Mutating X's
        existing row in place (rather than archiving-then-appending) used to
        silently orphan Y's chain link, producing a false-positive break."""
        db_path = str(tmp_path / "interleaved.db")
        prov_mgr = ProvenanceManager(storage_path=db_path)

        prov_mgr.track_entity("e1", source="doc1")
        prov_mgr.track_entity("X", source="doc1")
        prov_mgr.track_entity("Y", source="doc1", parent_entity_id="X")
        prov_mgr.track_entity("X", source="doc1")  # retrack: archives old X
        prov_mgr.track_entity("Z", source="doc1", parent_entity_id="X")
        prov_mgr.invalidate("X", agent_id="reviewer")  # archives again
        prov_mgr.track_entity("W", source="doc1", parent_entity_id="X")

        result = prov_mgr.verify_chain()
        assert result["valid"] is True
        assert result["broken_links"] == []

    def test_invalidate_does_not_break_chain(self):
        prov_mgr = ProvenanceManager()
        prov_mgr.track_entity("e1", source="doc1")
        prov_mgr.track_entity("e2", source="doc1", parent_entity_id="e1")
        prov_mgr.invalidate("e1", agent_id="reviewer_jane")

        result = prov_mgr.verify_chain()
        assert result["valid"] is True


class TestDownstreamLineage:
    """Issue #825, Part A item 5 — downstream/descendant traversal (reverse
    BFS), complementing the existing upstream-only trace_lineage/get_lineage."""

    def test_get_descendants_finds_direct_child(self):
        prov_mgr = ProvenanceManager()
        prov_mgr.track_entity("parent1", source="doc1")
        prov_mgr.track_entity(
            "child1", source="doc1", parent_entity_id="parent1", used_entities=["parent1"]
        )

        result = prov_mgr.get_descendants("parent1")
        entity_ids = {e["entity_id"] for e in result["entries"]}
        assert "child1" in entity_ids

    def test_get_descendants_transitive(self):
        prov_mgr = ProvenanceManager()
        prov_mgr.track_entity("a", source="doc1")
        prov_mgr.track_entity("b", source="doc1", parent_entity_id="a")
        prov_mgr.track_entity("c", source="doc1", parent_entity_id="b")

        result = prov_mgr.get_descendants("a")
        entity_ids = {e["entity_id"] for e in result["entries"]}
        assert entity_ids == {"b", "c"}

    def test_get_descendants_empty_for_leaf(self):
        prov_mgr = ProvenanceManager()
        prov_mgr.track_entity("leaf", source="doc1")
        assert prov_mgr.get_descendants("leaf") == {}

    def test_descendants_work_on_sqlite_backend(self, tmp_path):
        db_path = str(tmp_path / "desc.db")
        prov_mgr = ProvenanceManager(storage_path=db_path)
        prov_mgr.track_entity("parent1", source="doc1")
        prov_mgr.track_entity("child1", source="doc1", parent_entity_id="parent1")

        result = prov_mgr.get_descendants("parent1")
        entity_ids = {e["entity_id"] for e in result["entries"]}
        assert "child1" in entity_ids


class TestQualifiedExport:
    """Issue #825, Part A item 6 — qualified Association with hadRole, plus
    qualified Invalidation, in the RDF export."""

    def test_export_prov_includes_qualified_association_and_role(self):
        prov_mgr = ProvenanceManager()
        prov_mgr.track_entity(
            "e1", source="doc1", agent_id="alice", agent_type="person", role="approver"
        )
        ttl = prov_mgr.export_prov(format="turtle")
        assert "qualifiedAssociation" in ttl
        assert "hadRole" in ttl
        assert "role_approver" in ttl
        assert "Person" in ttl

    def test_export_prov_includes_qualified_invalidation(self):
        prov_mgr = ProvenanceManager()
        prov_mgr.track_entity("e1", source="doc1")
        prov_mgr.invalidate("e1", agent_id="reviewer_jane", reason="retracted")

        ttl = prov_mgr.export_prov(format="turtle")
        assert "qualifiedInvalidation" in ttl
        assert "Invalidation" in ttl


class TestTypedActivity:
    """Issue #825, Part B Tier 1 — typed Activity via ActivityRecord."""

    def test_track_entity_activity_record_kwarg(self):
        from semantica.provenance import ActivityRecord
        prov_mgr = ProvenanceManager()
        activity = ActivityRecord(
            id="bureau_parsing_run_42",
            started_at_time="2026-01-01T00:00:00",
            ended_at_time="2026-01-01T00:00:03",
        )
        entry = prov_mgr.track_entity("e1", source="doc1", activity=activity)
        assert entry.activity_id == "bureau_parsing_run_42"
        assert entry.activity_started_at_time == "2026-01-01T00:00:00"
        assert entry.activity_ended_at_time == "2026-01-01T00:00:03"

    def test_track_entity_activity_scalar_kwargs(self):
        prov_mgr = ProvenanceManager()
        entry = prov_mgr.track_entity(
            "e1", source="doc1",
            activity_id="parse_step", activity_started_at_time="t0", activity_ended_at_time="t1",
        )
        assert entry.activity_id == "parse_step"
        assert entry.activity_started_at_time == "t0"
        assert entry.activity_ended_at_time == "t1"

    def test_export_prov_qualified_generation_usage_derivation(self):
        prov_mgr = ProvenanceManager()
        prov_mgr.track_entity("parent1", source="doc1")
        prov_mgr.track_entity(
            "child1", source="doc1",
            parent_entity_id="parent1", used_entities=["parent1"],
            activity_id="transform",
        )
        ttl = prov_mgr.export_prov(format="turtle")
        assert "qualifiedGeneration" in ttl
        assert "Generation" in ttl
        assert "qualifiedUsage" in ttl
        assert "Usage" in ttl
        assert "qualifiedDerivation" in ttl
        assert "Derivation" in ttl

    def test_export_prov_activity_timing(self):
        from semantica.provenance import ActivityRecord
        prov_mgr = ProvenanceManager()
        prov_mgr.track_entity(
            "e1", source="doc1",
            activity=ActivityRecord(id="act1", started_at_time="2026-01-01T00:00:00",
                                     ended_at_time="2026-01-01T00:00:05"),
        )
        ttl = prov_mgr.export_prov(format="turtle")
        assert "startedAtTime" in ttl
        assert "endedAtTime" in ttl


class TestAssociationDelegationChaining:
    """Issue #825, Part B Tier 2 — wasAssociatedWith, actedOnBehalfOf, wasInformedBy."""

    def test_acted_on_behalf_of(self):
        prov_mgr = ProvenanceManager()
        entry = prov_mgr.track_entity(
            "e1", source="doc1", agent_id="bot1", acted_on_behalf_of="org1"
        )
        assert entry.acted_on_behalf_of == "org1"
        ttl = prov_mgr.export_prov(format="turtle")
        assert "actedOnBehalfOf" in ttl

    def test_informed_by_activities(self):
        prov_mgr = ProvenanceManager()
        entry = prov_mgr.track_entity(
            "e1", source="doc1", activity_id="parse", informed_by=["ingest_activity"]
        )
        assert entry.informed_by_activities == ["ingest_activity"]
        ttl = prov_mgr.export_prov(format="turtle")
        assert "wasInformedBy" in ttl

    def test_was_associated_with_in_export(self):
        prov_mgr = ProvenanceManager()
        prov_mgr.track_entity("e1", source="doc1", agent_id="alice", activity_id="act1")
        ttl = prov_mgr.export_prov(format="turtle")
        assert "wasAssociatedWith" in ttl

    def test_track_entities_batch_forwards_tier2_kwargs(self):
        """Regression test for the batch-kwargs-vs-metadata bug (issue #825,
        Part A) extended to the new Tier 2/3 keys."""
        prov_mgr = ProvenanceManager()
        count = prov_mgr.track_entities_batch(
            [{"id": "b1"}],
            source="doc_batch",
            activity_id="bureau_parsing",
            acted_on_behalf_of="org1",
            informed_by=["ingest_activity"],
            bundle_id="run_1",
        )
        assert count == 1
        entry = prov_mgr.storage.retrieve("b1")
        assert entry.activity_id == "bureau_parsing"
        assert entry.acted_on_behalf_of == "org1"
        assert entry.informed_by_activities == ["ingest_activity"]
        assert entry.bundle_id == "run_1"
        assert "acted_on_behalf_of" not in entry.metadata


class TestBitemporalMerge:
    """Issue #825, Part B Tier 3 — revision_history()/query_recorded_between()
    close kg.ProvenanceTracker's documented 'no direct equivalent yet' gaps."""

    def test_revision_history_ascending_with_valid_until(self):
        prov_mgr = ProvenanceManager()
        prov_mgr.track_entity("X", source="doc1", agent_id="alice")
        prov_mgr.track_entity("X", source="doc1", agent_id="bob", revision_type="correction")
        prov_mgr.track_entity("X", source="doc1", agent_id="carol", supersedes="X_old_claim")

        history = prov_mgr.revision_history("X")
        assert len(history) == 3
        assert [h["version"] for h in history] == [1, 2, 3]
        assert history[0]["author"] == "alice"
        assert history[1]["author"] == "bob"
        assert history[1]["revision_type"] == "correction"
        assert history[2]["author"] == "carol"
        assert history[2]["supersedes"] == "X_old_claim"
        # Every version except the last has a valid_until set to the next version's timestamp
        assert history[0]["valid_until"] == history[1]["valid_from"]
        assert history[1]["valid_until"] == history[2]["valid_from"]
        assert history[2]["valid_until"] is None

    def test_revision_history_empty_for_untracked_entity(self):
        prov_mgr = ProvenanceManager()
        assert prov_mgr.revision_history("never_tracked") == []

    def test_revision_history_single_version(self):
        prov_mgr = ProvenanceManager()
        prov_mgr.track_entity("Y", source="doc1")
        history = prov_mgr.revision_history("Y")
        assert len(history) == 1
        assert history[0]["version"] == 1
        assert history[0]["valid_until"] is None

    def test_query_recorded_between(self):
        prov_mgr = ProvenanceManager()
        prov_mgr.track_entity("e1", source="doc1")
        prov_mgr.track_entity("e2", source="doc1")

        results = prov_mgr.query_recorded_between("2000-01-01T00:00:00", "2100-01-01T00:00:00")
        entity_ids = {r["entity_id"] for r in results}
        assert {"e1", "e2"}.issubset(entity_ids)

        no_results = prov_mgr.query_recorded_between("1990-01-01T00:00:00", "1990-01-02T00:00:00")
        assert no_results == []

    def test_check_flags_missing_informed_by_activity(self):
        prov_mgr = ProvenanceManager()
        prov_mgr.track_entity("e1", source="doc1", informed_by=["never_tracked_activity"])
        result = prov_mgr.check()
        assert result["valid"] is False
        assert any("never_tracked_activity" in ref for ref in result["missing_references"])


class TestBundleAndBaseUri:
    """Issue #825, Part B Tier 3 — prov:Bundle membership and configurable base_uri."""

    def test_bundle_id_produces_bundle_triples(self):
        prov_mgr = ProvenanceManager()
        prov_mgr.track_entity("e1", source="doc1", bundle_id="ingestion_run_1")
        ttl = prov_mgr.export_prov(format="turtle")
        assert "Bundle" in ttl
        assert "hadMember" in ttl

    def test_default_base_uri_matches_rdf_exporter_namespace(self):
        from semantica.provenance.manager import DEFAULT_BASE_URI
        from semantica.export.rdf_exporter import NamespaceManager
        assert NamespaceManager().namespaces["semantica"] == DEFAULT_BASE_URI

    def test_export_prov_base_uri_override(self):
        prov_mgr = ProvenanceManager()
        prov_mgr.track_entity("e1", source="doc1")

        default_ttl = prov_mgr.export_prov(format="turtle")
        assert "https://semantica.dev/ns#" in default_ttl

        custom_ttl = prov_mgr.export_prov(format="turtle", base_uri="https://example.org/kg#")
        assert "https://example.org/kg#" in custom_ttl
        assert "https://semantica.dev/ns#" not in custom_ttl

    def test_owl_exporter_default_ontology_uri_matches_shared_namespace(self):
        """Issue #825 follow-up — OWLExporter was the one exporter left out of
        the Part B Tier 3 namespace interlinking; its default ontology_uri
        must match the same shared DEFAULT_BASE_URI as RDFExporter and
        export_prov()."""
        from semantica.provenance.manager import DEFAULT_BASE_URI
        from semantica.export.owl_exporter import OWLExporter
        assert OWLExporter().ontology_uri == DEFAULT_BASE_URI


class TestExplicitBitemporalFields:
    """Issue #825 follow-up — valid_from/valid_until as explicit,
    caller-supplied ProvenanceEntry fields (matching the deprecated
    kg.ProvenanceTracker's actual contract: these were always caller-supplied
    metadata keys, never auto-computed)."""

    def test_valid_from_valid_until_are_plain_passthrough_fields(self):
        prov_mgr = ProvenanceManager()
        entry = prov_mgr.track_entity(
            "price1", source="doc1", valid_from="2026-01-01", valid_until="2026-06-01"
        )
        assert entry.valid_from == "2026-01-01"
        assert entry.valid_until == "2026-06-01"

    def test_revision_history_prefers_explicit_valid_from_until(self):
        prov_mgr = ProvenanceManager()
        prov_mgr.track_entity(
            "price1", source="doc1", valid_from="2026-01-01", valid_until="2026-06-01"
        )
        history = prov_mgr.revision_history("price1")
        assert history[0]["valid_from"] == "2026-01-01"
        assert history[0]["valid_until"] == "2026-06-01"

    def test_revision_history_falls_back_to_timestamp_when_unset(self):
        """Backward-compat: entries that don't set valid_from/valid_until
        explicitly still get the dynamic timestamp-based derivation."""
        prov_mgr = ProvenanceManager()
        prov_mgr.track_entity("X", source="doc1")
        prov_mgr.track_entity("X", source="doc1")
        history = prov_mgr.revision_history("X")
        assert history[0]["valid_until"] == history[1]["valid_from"]
        assert history[1]["valid_until"] is None

    def test_valid_from_until_survive_sqlite_round_trip(self, tmp_path):
        db_path = str(tmp_path / "bitemporal.db")
        prov_mgr = ProvenanceManager(storage_path=db_path)
        prov_mgr.track_entity(
            "price1", source="doc1", valid_from="2026-01-01", valid_until="2026-06-01"
        )
        prov_mgr2 = ProvenanceManager(storage_path=db_path)
        entry = prov_mgr2.storage.retrieve("price1")
        assert entry.valid_from == "2026-01-01"
        assert entry.valid_until == "2026-06-01"


class TestActivityTimingAcrossWrappers:
    """Issue #825 follow-up — activity_started_at_time/ended_at_time wired
    into all *_provenance.py wrapper modules that measure real work, not
    just the 2 wrappers from the original Part B pass."""

    def test_embedding_wrapper_records_activity_timing(self):
        from semantica.embeddings.embeddings_provenance import EmbeddingGeneratorWithProvenance
        wrapper = EmbeddingGeneratorWithProvenance(provenance=True, agent_id="embed_svc")
        wrapper._generator.embed = lambda texts, **kw: [[0.1, 0.2] for _ in texts]
        wrapper.embed(["hello", "world"])
        entries = wrapper._prov_manager.storage.retrieve_all()
        assert len(entries) == 1
        assert entries[0].activity_started_at_time is not None
        assert entries[0].activity_ended_at_time is not None

    def test_kg_algorithm_tracker_accepts_caller_supplied_activity_timing(self):
        from semantica.kg.kg_provenance import AlgorithmTrackerWithProvenance
        tracker = AlgorithmTrackerWithProvenance(provenance=True, agent_id="algo_svc")
        eid = tracker.track_embedding_computation(
            graph=object(), algorithm="node2vec", embeddings={"n1": [0.1, 0.2]},
            parameters={"d": 2},
            activity_started_at_time="t0", activity_ended_at_time="t1",
        )
        entry = tracker._prov_manager.get_provenance(eid)
        assert entry["activity_started_at_time"] == "t0"
        assert entry["activity_ended_at_time"] == "t1"

    def test_graph_builder_build_operation_has_no_end_time_yet(self):
        """The build-operation marker is recorded before the build runs, so
        it legitimately has a start but no end time."""
        from semantica.kg.kg_provenance import GraphBuilderWithProvenance
        builder = GraphBuilderWithProvenance(provenance=True, agent_id="builder_svc")
        builder._builder.build_single_source = lambda kg_data, **kw: {"entities": [], "relationships": []}
        builder.build_single_source({"foo": "bar"})
        entries = builder._prov_manager.storage.retrieve_all()
        # NOTE: entity_type isn't asserted here — kg_provenance.py has a
        # pre-existing, out-of-scope bug where entity_type is nested inside
        # the metadata dict instead of passed as a track_entity kwarg, so it
        # never actually populates the real field for this call site.
        build_entries = [e for e in entries if e.entity_id.startswith("graph_build_single_")]
        assert len(build_entries) == 1
        assert build_entries[0].activity_started_at_time is not None
        assert build_entries[0].activity_ended_at_time is None

    def test_semantic_extract_wrapper_records_activity_timing(self):
        from semantica.semantic_extract.semantic_extract_provenance import ProvenanceMixin

        class FakeExtractor(ProvenanceMixin):
            pass

        wrapper = FakeExtractor(provenance=True, agent_id="extract_svc")
        wrapper._track_extraction(
            entity_id="e1", source="doc1", entity_type="named_entity",
            activity_started_at_time="t0", activity_ended_at_time="t1",
        )
        entry = wrapper._prov_manager.get_provenance("e1")
        assert entry["activity_started_at_time"] == "t0"
        assert entry["activity_ended_at_time"] == "t1"
        assert "activity_started_at_time" not in entry["metadata"]

    def test_conflicts_wrapper_records_activity_timing(self):
        from semantica.conflicts.conflicts_provenance import SourceTrackerWithUnifiedBackend

        class FakeSource:
            document = "doc1"
            page = 1
            section = None
            confidence = 0.9

        tracker = SourceTrackerWithUnifiedBackend(agent_id="conflicts_svc")
        tracker.track_property_source("e1", "prop", "val", FakeSource())
        entry = tracker._unified_manager.get_provenance("e1_prop")
        assert entry["activity_started_at_time"] is not None
        assert entry["activity_ended_at_time"] is not None


class TestTimezoneAwareUtcTimestamps:
    """Issue #946 — timezone-aware UTC stamps without datetime.utcnow()."""

    def test_track_entity_stamps_timezone_aware_utc(self):
        before = datetime.now(timezone.utc) - timedelta(seconds=1)
        with warnings.catch_warnings(record=True) as caught:
            warnings.simplefilter("always", DeprecationWarning)
            prov_mgr = ProvenanceManager()
            entry = prov_mgr.track_entity("utc_entity", source="doc_1")
        after = datetime.now(timezone.utc) + timedelta(seconds=1)

        utcnow_warnings = [
            w
            for w in caught
            if issubclass(w.category, DeprecationWarning)
            and "utcnow" in str(w.message).lower()
        ]
        assert utcnow_warnings == []

        for field in ("timestamp", "first_seen", "last_updated"):
            value = getattr(entry, field)
            parsed = datetime.fromisoformat(value)
            assert parsed.tzinfo is not None, f"{field}={value!r} is naive"
            assert parsed.utcoffset() == timedelta(0), f"{field}={value!r} is not UTC"
            assert before <= parsed <= after

        stored = prov_mgr.get_provenance("utc_entity")
        assert stored is not None
        assert stored["source_document"] == "doc_1"
        assert stored["last_updated"] == entry.last_updated

    def test_invalidate_stamps_timezone_aware_utc(self):
        prov_mgr = ProvenanceManager()
        prov_mgr.track_entity("utc_invalidate", source="doc_1")
        result = prov_mgr.invalidate(
            "utc_invalidate", agent_id="reviewer", reason="test"
        )
        parsed = datetime.fromisoformat(result.invalidated_at_time)
        assert parsed.tzinfo is not None
        assert parsed.utcoffset() == timedelta(0)

    def test_graph_builder_activity_times_are_timezone_aware_utc(self):
        from semantica.kg.kg_provenance import GraphBuilderWithProvenance

        builder = GraphBuilderWithProvenance(provenance=True, agent_id="builder_svc")
        result = builder.build_single_source({
            "entities": [{"id": "person1", "type": "Person", "name": "Ada"}],
            "relationships": [],
        })
        assert result["entities"][0]["id"] == "person1"

        person = builder._prov_manager.get_provenance("person1")
        assert person is not None
        assert person["metadata"]["operation"] == "build_entity"
        for field in ("activity_started_at_time", "activity_ended_at_time"):
            parsed = datetime.fromisoformat(person[field])
            assert parsed.tzinfo is not None, (
                f"{field}={person[field]!r} is naive"
            )
            assert parsed.utcoffset() == timedelta(0)
        started = datetime.fromisoformat(person["activity_started_at_time"])
        ended = datetime.fromisoformat(person["activity_ended_at_time"])
        assert started <= ended

class TestMixedFormatTimestampComparisons:
    """Issue #946 review — naive and offset-bearing stamps must compare as instants.

    Records written before the timezone-aware change carry a naive UTC stamp
    (``2026-08-19T22:35:38.501697``); records written after carry ``+00:00``.
    Comparing the two as raw strings puts the offset-bearing form above a naive
    bound at the identical instant, so the record falls outside a range that
    should contain it. These tests pin the boundary in both directions.
    """

    NAIVE = "2026-08-19T12:00:00.500000"
    AWARE = "2026-08-19T12:00:00.500000+00:00"

    def _manager_with(self, *timestamps):
        prov_mgr = ProvenanceManager()
        for index, stamp in enumerate(timestamps):
            prov_mgr.storage.store(
                ProvenanceEntry(
                    entity_id=f"entity_{index}",
                    entity_type="entity",
                    activity_id="test",
                    source_document="doc_1",
                    timestamp=stamp,
                )
            )
        return prov_mgr

    def test_raw_string_compare_would_exclude_the_boundary_record(self):
        """Guards the premise: the two forms are not string-comparable."""
        assert not (self.AWARE <= self.NAIVE)
        assert datetime.fromisoformat(self.AWARE) == datetime.fromisoformat(
            self.NAIVE
        ).replace(tzinfo=timezone.utc)

    def test_query_range_with_naive_bounds_includes_aware_record(self):
        prov_mgr = self._manager_with(self.AWARE)
        results = prov_mgr.query_recorded_between(
            "2026-08-19T12:00:00.500000", "2026-08-19T12:00:00.500000"
        )
        assert [r["entity_id"] for r in results] == ["entity_0"]

    def test_query_range_with_aware_bounds_includes_naive_record(self):
        prov_mgr = self._manager_with(self.NAIVE)
        results = prov_mgr.query_recorded_between(
            "2026-08-19T12:00:00.500000+00:00", "2026-08-19T12:00:00.500000+00:00"
        )
        assert [r["entity_id"] for r in results] == ["entity_0"]

    def test_query_range_returns_both_formats_from_a_mixed_store(self):
        prov_mgr = self._manager_with(self.NAIVE, self.AWARE)
        results = prov_mgr.query_recorded_between(
            "2026-08-19T11:00:00", "2026-08-19T13:00:00+00:00"
        )
        assert {r["entity_id"] for r in results} == {"entity_0", "entity_1"}

    def test_query_range_sorts_mixed_formats_chronologically(self):
        prov_mgr = self._manager_with(
            "2026-08-19T12:00:02+00:00",  # entity_0, latest
            "2026-08-19T12:00:00",        # entity_1, earliest
            "2026-08-19T12:00:01+00:00",  # entity_2, middle
        )
        results = prov_mgr.query_recorded_between(
            "2026-08-19T11:00:00", "2026-08-19T13:00:00"
        )
        assert [r["entity_id"] for r in results] == [
            "entity_1",
            "entity_2",
            "entity_0",
        ]

    def test_query_range_accepts_trailing_z(self):
        prov_mgr = self._manager_with(self.NAIVE)
        results = prov_mgr.query_recorded_between(
            "2026-08-19T11:00:00Z", "2026-08-19T13:00:00Z"
        )
        assert len(results) == 1

    def test_query_range_skips_unparseable_timestamp(self):
        prov_mgr = self._manager_with("not-a-timestamp", self.AWARE)
        results = prov_mgr.query_recorded_between(
            "2026-08-19T11:00:00", "2026-08-19T13:00:00"
        )
        assert [r["entity_id"] for r in results] == ["entity_1"]

    def test_audit_log_since_naive_bound_includes_aware_record(self):
        prov_mgr = self._manager_with(self.AWARE)
        entries = prov_mgr.audit_log(
            since="2026-08-19T12:00:00.500000", format="json"
        )
        assert [e["entity_id"] for e in entries] == ["entity_0"]

    def test_audit_log_since_aware_bound_includes_naive_record(self):
        prov_mgr = self._manager_with(self.NAIVE)
        entries = prov_mgr.audit_log(
            since="2026-08-19T12:00:00.500000+00:00", format="json"
        )
        assert [e["entity_id"] for e in entries] == ["entity_0"]

    def test_audit_log_excludes_records_before_since_across_formats(self):
        prov_mgr = self._manager_with(
            "2026-08-19T11:59:59",        # entity_0, before
            "2026-08-19T12:00:01+00:00",  # entity_1, after
        )
        entries = prov_mgr.audit_log(since="2026-08-19T12:00:00+00:00", format="json")
        assert [e["entity_id"] for e in entries] == ["entity_1"]

    def test_audit_log_sorts_mixed_formats_chronologically(self):
        prov_mgr = self._manager_with(
            "2026-08-19T12:00:02+00:00",
            "2026-08-19T12:00:00",
            "2026-08-19T12:00:01+00:00",
        )
        entries = prov_mgr.audit_log(format="json")
        assert [e["entity_id"] for e in entries] == [
            "entity_1",
            "entity_2",
            "entity_0",
        ]

    def test_audit_log_unparseable_timestamp_sorts_first(self):
        prov_mgr = self._manager_with("not-a-timestamp", "2026-08-19T12:00:00+00:00")
        entries = prov_mgr.audit_log(format="json")
        assert [e["entity_id"] for e in entries] == ["entity_0", "entity_1"]

    def test_audit_log_since_excludes_unparseable_timestamp(self):
        prov_mgr = self._manager_with("not-a-timestamp", "2026-08-19T12:00:00+00:00")
        entries = prov_mgr.audit_log(since="2026-08-19T11:00:00", format="json")
        assert [e["entity_id"] for e in entries] == ["entity_1"]
