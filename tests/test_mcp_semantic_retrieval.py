"""
Tests for the MCP semantic retrieval tools (#1235).

Covers the six acceptance behaviours proposed in the issue:

1. store_document chunks content and stores it in a real supported
   vector backend with provenance metadata (status / version / hash).
2. retrieve_context returns semantically relevant chunks with scores
   and provenance, combined with related graph relationships.
3. update_document replaces stored content under (source, version).
4. remove_document deletes every chunk of a document.
5. Remove-then-store does not collide with surviving in-memory ids
   (regression guard for the #1029 interaction).
6. The same tool set works against the sqlite backend (real persistent
   store, skipped when the sqlite_vec extension is missing).
"""

import os
import sys
import tempfile
import unittest
import zlib
from unittest.mock import patch

import numpy as np

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import mcp.session as session
import semantica.embeddings as _embeddings_pkg
import semantica.vector_store.vector_store as _vs_module
from mcp.session import get_vector_store, reset_vector_store
from mcp.tools import TOOL_DEFINITIONS
from mcp.tools.retrieval import (
    _chunk_id,
    _chunk_text,
    handle_remove_document,
    handle_retrieve_context,
    handle_store_document,
    handle_update_document,
)


class FakeTextEmbedder:
    def __init__(self, dim: int = 64):
        self.dim = dim

    def get_embedding_dimension(self) -> int:
        return self.dim


class FakeEmbedder:
    """
    Deterministic keyword-bag embedder on a fixed dimension.

    Same words land on the same dimensions, so a query sharing vocabulary
    with a chunk scores higher than one that does not — enough signal for
    ranking assertions without any model download.  crc32 keeps the
    word-to-dimension mapping stable across processes (unlike builtin
    hash(), whose per-process salt would make collisions flaky), and 64
    dims keep the test keywords collision-free.
    """

    def __init__(self, dim: int = 64):
        self.dim = dim
        self.text_embedder = FakeTextEmbedder(dim)

    def get_text_method(self) -> str:
        return "fake"

    def generate_embeddings(self, texts):
        out = []
        for t in texts:
            v = np.zeros(self.dim, dtype=float)
            for w in str(t).lower().split():
                if w == "x":
                    # "x" is the filler make_doc pads with; treating it
                    # as a stopword keeps vectors keyword-driven instead
                    # of filler-dominated.
                    continue
                v[zlib.crc32(w.encode("utf-8")) % self.dim] += 1.0
            norm = np.linalg.norm(v)
            if norm:
                v /= norm
            out.append(v)
        return np.array(out)


def make_doc(*keywords) -> str:
    """
    Build filler text with exactly one keyword per chunk.

    With the default 1000 window / 200 overlap, chunk i covers
    [800*i, 800*i+1000).  Keyword i is placed at 800*i + 300, which sits
    inside chunk i only — clear of both neighbouring overlap zones.
    Filler is spaced "x " tokens, which the fake embedder treats as a
    stopword, so chunk vectors are keyword-driven.
    """
    filler = "x "
    parts = []
    pos = 0
    for i, word in enumerate(keywords):
        target = 800 * i + 300
        parts.append(filler * ((target - pos) // 2))
        parts.append(word + " ")
        pos = target + len(word) + 1
    parts.append(filler * 30)
    return "".join(parts)


def patch_embedding_generators():
    """
    Patch every EmbeddingGenerator construction site with FakeEmbedder.

    The real EmbeddingGenerator probes FastEmbed / sentence-transformers
    on init; where those packages are installed but the model is not
    cached, the probe blocks on a full TCP connect timeout (~30s each).
    VectorStore's in-memory branch builds one internally, so tests patch
    both import sites to keep the suite fast and network-free.
    """
    return (
        patch.object(_embeddings_pkg, "EmbeddingGenerator", FakeEmbedder),
        patch.object(_vs_module, "EmbeddingGenerator", FakeEmbedder),
    )


def _clear_retrieval_env():
    for var in ("SEMANTICA_VECTOR_PATH", "SEMANTICA_VECTOR_BACKEND", "SEMANTICA_VECTOR_DB_PATH"):
        os.environ.pop(var, None)


class InmemoryBackendTestBase(unittest.TestCase):
    def setUp(self):
        _clear_retrieval_env()
        session._embedder = FakeEmbedder()
        session._vector_store = None
        session._graph = None
        self._patches = patch_embedding_generators()
        for p in self._patches:
            p.start()

    def tearDown(self):
        for p in self._patches:
            p.stop()
        session._embedder = None
        reset_vector_store()
        session._graph = None
        _clear_retrieval_env()


class TestChunking(InmemoryBackendTestBase):
    def test_fixed_window_with_overlap(self):
        text = "a" * 2600
        chunks = _chunk_text(text, 1000, 200)
        self.assertEqual([c[:2] for c in chunks], [(0, 1000), (800, 1800), (1600, 2600)])
        self.assertTrue(all(c == text[s:e] for s, e, c in chunks))

    def test_short_text_single_chunk(self):
        chunks = _chunk_text("short", 1000, 200)
        self.assertEqual(chunks, [(0, 5, "short")])

    def test_overlap_must_be_smaller_than_window(self):
        with self.assertRaises(ValueError):
            _chunk_text("abc", 200, 200)

    def test_chunk_id_is_stable_and_position_sensitive(self):
        a = _chunk_id("src", "v1", 0, "hello")
        b = _chunk_id("src", "v1", 0, "hello")
        c = _chunk_id("src", "v1", 1, "hello")
        self.assertEqual(a, b)
        self.assertNotEqual(a, c)


class TestStoreDocument(InmemoryBackendTestBase):
    def test_chunks_carry_provenance_metadata(self):
        result = handle_store_document(
            {
                "content": make_doc("alpha", "beta"),
                "source": "policy_manual#p12",
                "authority": "official",
                "version": "v2",
                "project": "lending",
            }
        )
        self.assertNotIn("error", result)
        self.assertEqual(result["status"], "stored")
        self.assertEqual(result["chunk_count"], len(result["chunk_ids"]))

        store = get_vector_store()
        first = next(
            m
            for m in store.metadata.values()
            if m.get("source") == "policy_manual#p12" and m.get("chunk_index") == 0
        )
        self.assertEqual(first["chunk_id"], result["chunk_ids"][0])
        self.assertEqual(first["authority"], "official")
        self.assertEqual(first["version"], "v2")
        self.assertEqual(first["project"], "lending")
        self.assertEqual(first["status"], "active")
        self.assertEqual(first["hash"], result["hash"])
        self.assertEqual(first["char_start"], 0)

    def test_identical_content_is_a_noop(self):
        args = {"content": "same content", "source": "doc", "authority": "official"}
        first = handle_store_document(args)
        second = handle_store_document(args)
        self.assertEqual(second["status"], "unchanged")
        self.assertEqual(second["chunk_ids"], first["chunk_ids"])
        self.assertEqual(get_vector_store().count(), first["chunk_count"])

    def test_missing_authority_rejected(self):
        result = handle_store_document({"content": "text", "source": "doc"})
        self.assertIn("error", result)

    def test_caller_metadata_cannot_override_provenance(self):
        result = handle_store_document(
            {
                "content": make_doc("alpha"),
                "source": "real_source",
                "authority": "official",
                "metadata": {
                    "source": "spoofed_source",
                    "authority": "backdated",
                    "status": "tombstone",
                    "hash": "deadbeef",
                    "version": "v99",
                    "project": "shadow_project",
                    "dept": "risk",
                },
            }
        )
        self.assertNotIn("error", result)

        store = get_vector_store()
        meta = next(
            m
            for m in store.metadata.values()
            if m.get("chunk_id") == result["chunk_ids"][0]
        )
        self.assertEqual(meta["source"], "real_source")
        self.assertEqual(meta["authority"], "official")
        self.assertEqual(meta["status"], "active")
        self.assertEqual(meta["hash"], result["hash"])
        self.assertEqual(meta["version"], "v1")
        self.assertNotIn("project", meta)
        # Non-provenance keys still land.
        self.assertEqual(meta["dept"], "risk")

        # Provenance stays intact, so the idempotent no-op still works.
        again = handle_store_document(
            {
                "content": make_doc("alpha"),
                "source": "real_source",
                "authority": "official",
            }
        )
        self.assertEqual(again["status"], "unchanged")

    def test_non_dict_metadata_rejected(self):
        result = handle_store_document(
            {"content": "text", "source": "doc", "authority": "official", "metadata": ["bad"]}
        )
        self.assertIn("error", result)


class TestRetrieveContext(InmemoryBackendTestBase):
    def setUp(self):
        super().setUp()
        handle_store_document(
            {
                "content": make_doc("approval", "collateral", "interest"),
                "source": "lending_policy",
                "authority": "official",
                "project": "lending",
            }
        )
        handle_store_document(
            {
                "content": make_doc("payment", "refund"),
                "source": "billing_faq",
                "authority": "draft",
                "project": "billing",
            }
        )

    def test_relevant_chunks_ranked_with_provenance(self):
        result = handle_retrieve_context({"query": "collateral", "top_k": 3})
        self.assertNotIn("error", result)
        self.assertGreater(result["count"], 0)
        relevant = [r for r in result["results"] if r["score"] and r["score"] > 0]
        self.assertTrue(relevant)
        top = relevant[0]
        self.assertIn("collateral", top["text"])
        self.assertEqual(top["source"], "lending_policy")
        self.assertEqual(top["authority"], "official")
        self.assertEqual(top["version"], "v1")
        self.assertEqual(top["status"], "active")
        self.assertTrue(top["hash"])
        self.assertIsInstance(top["score"], float)

    def test_top_k_is_capped_at_ten(self):
        # 13 chunks (one keyword per chunk) so the cap is actually hit;
        # with fewer stored chunks the assertion would pass trivially.
        handle_store_document(
            {
                "content": make_doc(*["k%02d" % i for i in range(1, 14)]),
                "source": "capdoc",
                "authority": "official",
            }
        )
        result = handle_retrieve_context({"query": "k01", "top_k": 99})
        self.assertEqual(result["count"], 10)

    def test_project_filter_narrows_results(self):
        result = handle_retrieve_context({"query": "collateral", "project": "billing"})
        for r in result["results"]:
            self.assertEqual(r["project"], "billing")

    def test_graph_relationships_attached(self):
        graph = session.get_graph()
        graph.add_node(
            node_id="policy_doc_lending_policy",
            label="Lending policy doc",
            node_type="Document",
            metadata={"source": "lending_policy"},
        )
        graph.add_node(node_id="risk_team", label="Risk team", node_type="Team")
        graph.add_edge(
            source_id="policy_doc_lending_policy",
            target_id="risk_team",
            edge_type="OWNED_BY",
        )
        result = handle_retrieve_context({"query": "collateral"})
        self.assertGreaterEqual(len(result["graph_context"]), 1)
        rel = result["graph_context"][0]
        self.assertEqual(rel["node"]["source"], "lending_policy")
        self.assertEqual(rel["related"]["id"], "risk_team")
        self.assertEqual(rel["relationship"], "OWNED_BY")

    def test_empty_query_rejected(self):
        result = handle_retrieve_context({"query": "  "})
        self.assertIn("error", result)


class TestUpdateDocument(InmemoryBackendTestBase):
    def test_update_replaces_chunks(self):
        handle_store_document(
            {
                "content": make_doc("oldterm", "legacy"),
                "source": "handbook",
                "authority": "official",
            }
        )
        result = handle_update_document(
            {
                "content": make_doc("newterm"),
                "source": "handbook",
                "version": "v1",
            }
        )
        self.assertEqual(result["status"], "updated")
        self.assertEqual(result["chunk_count"], 1)

        hits = handle_retrieve_context({"query": "newterm"})["results"]
        hits = [h for h in hits if h["score"] and h["score"] > 0]
        self.assertTrue(hits and "newterm" in hits[0]["text"])
        stale = handle_retrieve_context({"query": "oldterm"})["results"]
        stale = [h for h in stale if h["score"] and h["score"] > 0]
        self.assertEqual(stale, [])
        # Authority is inherited from the stored version when omitted.
        self.assertEqual(hits[0]["authority"], "official")
        self.assertEqual(get_vector_store().count(), 1)

    def test_update_rolls_back_when_new_write_fails(self):
        handle_store_document(
            {
                "content": make_doc("oldterm", "legacy"),
                "source": "handbook",
                "authority": "official",
            }
        )
        store = get_vector_store()
        real_store_vectors = store.store_vectors

        def failing_write(vectors, metas):
            if any("phoenix" in (m.get("text") or "") for m in metas):
                raise RuntimeError("simulated write failure")
            return real_store_vectors(vectors, metas)

        with patch.object(store, "store_vectors", side_effect=failing_write):
            result = handle_update_document(
                {"content": make_doc("phoenix"), "source": "handbook"}
            )
        self.assertIn("error", result)
        self.assertIn("simulated write failure", result["error"])

        # The old document must survive the failed replacement, with no
        # trace of the new content.
        store = get_vector_store()
        self.assertEqual(store.count(), 2)
        old = [
            h
            for h in handle_retrieve_context({"query": "oldterm"})["results"]
            if h["score"] and h["score"] > 0
        ]
        self.assertTrue(old and "oldterm" in old[0]["text"])
        self.assertEqual(old[0]["source"], "handbook")
        self.assertEqual(old[0]["authority"], "official")
        phoenix = [
            h
            for h in handle_retrieve_context({"query": "phoenix"})["results"]
            if h["score"] and h["score"] > 0
        ]
        self.assertEqual(phoenix, [])


class TestRemoveDocument(InmemoryBackendTestBase):
    def test_remove_deletes_every_chunk(self):
        handle_store_document(
            {
                "content": make_doc("alpha", "beta", "gamma"),
                "source": "docA",
                "authority": "official",
            }
        )
        result = handle_remove_document({"source": "docA"})
        self.assertEqual(result["status"], "removed")
        self.assertEqual(result["removed_chunks"], 3)
        self.assertEqual(get_vector_store().count(), 0)
        again = handle_remove_document({"source": "docA"})
        self.assertEqual(again["status"], "not_found")

    def test_remove_missing_document_reports_not_found(self):
        result = handle_remove_document({"source": "never_stored"})
        self.assertEqual(result["status"], "not_found")


class TestInMemoryIdCollisionRegression(InmemoryBackendTestBase):
    """
    #1029 interaction guard.

    In-memory vector ids are ``vec_{len(self.vectors) + i}``.  Deleting a
    document that is NOT a suffix makes len() fall below surviving ids, so
    the next plain write overwrites live data.  Our rebuild path must
    prevent that: store a 1-chunk doc, then a 3-chunk doc, remove the
    1-chunk one, then store another doc.  Without the rebuild the last
    store lands on the surviving document's third chunk id and destroys
    it.
    """

    def test_remove_then_store_keeps_surviving_chunks_intact(self):
        handle_store_document(
            {"content": make_doc("alpha"), "source": "docA", "authority": "official"}
        )
        handle_store_document(
            {
                "content": make_doc("bravo", "charlie", "delta"),
                "source": "docB",
                "authority": "official",
            }
        )
        self.assertEqual(get_vector_store().count(), 4)

        removed = handle_remove_document({"source": "docA"})
        self.assertEqual(removed["status"], "removed")

        stored = handle_store_document(
            {"content": make_doc("echo"), "source": "docC", "authority": "official"}
        )
        self.assertEqual(stored["status"], "stored")

        store = get_vector_store()
        self.assertEqual(store.count(), 4)

        delta_hits = handle_retrieve_context({"query": "delta"})["results"]
        delta_hits = [h for h in delta_hits if h["score"] and h["score"] > 0]
        self.assertTrue(delta_hits, "docB's third chunk was destroyed by an id collision")
        self.assertIn("delta", delta_hits[0]["text"])
        self.assertEqual(delta_hits[0]["source"], "docB")

        for keyword, expected_source in (
            ("bravo", "docB"),
            ("charlie", "docB"),
            ("echo", "docC"),
        ):
            hits = [
                h
                for h in handle_retrieve_context({"query": keyword})["results"]
                if h["score"] and h["score"] > 0
            ]
            self.assertTrue(hits, f"expected a hit for {keyword}")
            self.assertEqual(hits[0]["source"], expected_source)


class TestBackendPolicy(InmemoryBackendTestBase):
    def test_unsupported_backend_fails_fast(self):
        # faiss/pgvector lack a metadata-scoped delete, so update/remove
        # cannot work on them; selecting them must fail at startup, not
        # mid-update.
        for backend in ("faiss", "pgvector"):
            with self.subTest(backend=backend):
                os.environ["SEMANTICA_VECTOR_BACKEND"] = backend
                with self.assertRaises(ValueError) as ctx:
                    get_vector_store()
                self.assertIn("not supported", str(ctx.exception))

    def test_oversized_document_rejected_before_embedding(self):
        # chunk_size=1 turns a 12k-char body into 12k chunks, crossing
        # the ingestion cap without any expensive embedding work.
        result = handle_store_document(
            {
                "content": "ab" * 6000,
                "source": "bigdoc",
                "authority": "official",
                "chunk_size": 1,
                "chunk_overlap": 0,
            }
        )
        self.assertIn("error", result)
        self.assertIn("chunks", result["error"])
        self.assertEqual(get_vector_store().count(), 0)


class TestToolRegistration(unittest.TestCase):
    def test_retrieval_tools_are_registered(self):
        retrieval = {
            t["name"]: t
            for t in TOOL_DEFINITIONS
            if t["name"] in ("store_document", "retrieve_context", "update_document", "remove_document")
        }
        self.assertEqual(len(retrieval), 4)
        for name, t in retrieval.items():
            self.assertTrue(callable(t["_handler"]))
            self.assertIn("required", t["inputSchema"])


class TestSqliteBackend(unittest.TestCase):
    def setUp(self):
        try:
            import sqlite_vec  # noqa: F401
        except ImportError:
            self.skipTest("sqlite_vec extension not installed")
        self.tmpdir = tempfile.mkdtemp(prefix="semantica_sqlite_test_")
        self.patches = patch_embedding_generators()
        for p in self.patches:
            p.start()
        _clear_retrieval_env()
        os.environ["SEMANTICA_VECTOR_BACKEND"] = "sqlite"
        os.environ["SEMANTICA_VECTOR_DB_PATH"] = os.path.join(self.tmpdir, "vectors.db")
        session._embedder = FakeEmbedder()
        session._vector_store = None

    def tearDown(self):
        for p in self.patches:
            p.stop()
        session._embedder = None
        reset_vector_store()
        _clear_retrieval_env()
        import shutil

        shutil.rmtree(self.tmpdir, ignore_errors=True)

    def test_sqlite_backend_roundtrip(self):
        handle_store_document(
            {
                "content": make_doc("alpha", "beta"),
                "source": "docS",
                "authority": "official",
            }
        )
        hits = handle_retrieve_context({"query": "beta"})["results"]
        self.assertTrue(hits and "beta" in hits[0]["text"])
        self.assertEqual(hits[0]["source"], "docS")

        updated = handle_update_document(
            {"content": make_doc("gamma"), "source": "docS"}
        )
        self.assertEqual(updated["status"], "updated")
        # NB: score scales differ across backends (sqlite maps distance
        # through 1/(1+d), so an orthogonal chunk still scores 0.5).
        # Assert on text, the only backend-independent signal.
        stale = [
            h
            for h in handle_retrieve_context({"query": "beta"})["results"]
            if "beta" in (h.get("text") or "")
        ]
        self.assertEqual(stale, [])
        self.assertTrue(handle_retrieve_context({"query": "gamma"})["results"])

        removed = handle_remove_document({"source": "docS"})
        self.assertEqual(removed["status"], "removed")
        self.assertEqual(get_vector_store().count(), 0)

    def test_sqlite_multi_document_isolation(self):
        handle_store_document(
            {
                "content": make_doc("harbor", "vessel"),
                "source": "nav_docs",
                "authority": "official",
            }
        )
        handle_store_document(
            {
                "content": make_doc("ledger", "invoice"),
                "source": "fin_docs",
                "authority": "draft",
                "version": "v2",
            }
        )

        nav = [
            h
            for h in handle_retrieve_context({"query": "vessel"})["results"]
            if "vessel" in (h.get("text") or "")
        ]
        self.assertTrue(nav)
        self.assertEqual(nav[0]["source"], "nav_docs")
        self.assertEqual(nav[0]["authority"], "official")
        self.assertEqual(nav[0]["status"], "active")
        self.assertTrue(nav[0]["hash"])

        # Updating one document must leave the other untouched.
        updated = handle_update_document(
            {"content": make_doc("anchor"), "source": "nav_docs"}
        )
        self.assertEqual(updated["status"], "updated")
        fin = [
            h
            for h in handle_retrieve_context({"query": "invoice"})["results"]
            if "invoice" in (h.get("text") or "")
        ]
        self.assertTrue(fin)
        self.assertEqual(fin[0]["source"], "fin_docs")
        self.assertEqual(fin[0]["authority"], "draft")
        vessel_stale = [
            h
            for h in handle_retrieve_context({"query": "vessel"})["results"]
            if "vessel" in (h.get("text") or "")
        ]
        self.assertEqual(vessel_stale, [])

        # Removing the other document must leave the first intact.
        removed = handle_remove_document({"source": "fin_docs", "version": "v2"})
        self.assertEqual(removed["status"], "removed")
        anchor = [
            h
            for h in handle_retrieve_context({"query": "anchor"})["results"]
            if "anchor" in (h.get("text") or "")
        ]
        self.assertTrue(anchor and anchor[0]["source"] == "nav_docs")
        ledger_stale = [
            h
            for h in handle_retrieve_context({"query": "ledger"})["results"]
            if "ledger" in (h.get("text") or "")
        ]
        self.assertEqual(ledger_stale, [])

    def test_sqlite_update_rolls_back_on_write_failure(self):
        # Persistent path: removal is a direct delete_vectors, so the
        # rollback has to re-store the snapshotted rows (plain lists,
        # not arrays) when the new write fails.
        handle_store_document(
            {
                "content": make_doc("oldterm", "legacy"),
                "source": "handbook",
                "authority": "official",
            }
        )
        store = get_vector_store()
        real_store_vectors = store.store_vectors

        def failing_write(vectors, metas):
            if any("phoenix" in (m.get("text") or "") for m in metas):
                raise RuntimeError("simulated write failure")
            return real_store_vectors(vectors, metas)

        with patch.object(store, "store_vectors", side_effect=failing_write):
            result = handle_update_document(
                {"content": make_doc("phoenix"), "source": "handbook"}
            )
        self.assertIn("error", result)
        self.assertEqual(get_vector_store().count(), 2)
        old = [
            h
            for h in handle_retrieve_context({"query": "oldterm"})["results"]
            if "oldterm" in (h.get("text") or "")
        ]
        self.assertTrue(old and old[0]["source"] == "handbook")

    def test_sqlite_without_db_path_raises(self):
        os.environ.pop("SEMANTICA_VECTOR_DB_PATH", None)
        with self.assertRaises(ValueError):
            get_vector_store()


class TestPersistence(InmemoryBackendTestBase):
    def test_store_persists_and_reloads(self):
        tmpdir = tempfile.mkdtemp(prefix="semantica_vec_test_")
        try:
            os.environ["SEMANTICA_VECTOR_PATH"] = tmpdir
            result = handle_store_document(
                {"content": make_doc("persist"), "source": "docP", "authority": "official"}
            )
            self.assertTrue(result["persisted"])
            self.assertTrue(os.path.isfile(os.path.join(tmpdir, "store_data.json")))

            # Fresh session state: the store must reload from disk.
            reset_vector_store()
            hits = handle_retrieve_context({"query": "persist"})["results"]
            self.assertTrue(hits and "persist" in hits[0]["text"])
            self.assertEqual(hits[0]["source"], "docP")
        finally:
            import shutil

            shutil.rmtree(tmpdir, ignore_errors=True)

    def test_persist_failure_is_reported_not_silent(self):
        tmpdir = tempfile.mkdtemp(prefix="semantica_vec_test_")
        try:
            os.environ["SEMANTICA_VECTOR_PATH"] = tmpdir
            store = get_vector_store()
            with patch.object(store, "save", side_effect=RuntimeError("disk full")):
                result = handle_store_document(
                    {"content": make_doc("volatile"), "source": "docV", "authority": "official"}
                )
            # The write itself succeeded; only the durable copy failed.
            self.assertEqual(result["status"], "stored")
            self.assertFalse(result["persisted"])
        finally:
            import shutil

            shutil.rmtree(tmpdir, ignore_errors=True)

    def test_reload_dimension_mismatch_rejected(self):
        tmpdir = tempfile.mkdtemp(prefix="semantica_vec_test_")
        try:
            os.environ["SEMANTICA_VECTOR_PATH"] = tmpdir
            handle_store_document(
                {"content": make_doc("persist"), "source": "docP", "authority": "official"}
            )
            # A different embedder dimension must not silently rank
            # vectors from an incompatible embedding space.
            session._embedder = FakeEmbedder(32)
            reset_vector_store()
            with self.assertRaises(ValueError) as ctx:
                get_vector_store()
            self.assertIn("dimension", str(ctx.exception))
        finally:
            import shutil

            shutil.rmtree(tmpdir, ignore_errors=True)


if __name__ == "__main__":
    unittest.main()
