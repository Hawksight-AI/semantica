"""Bounded, call-serialized spaCy model cache (review findings on the cache PR).

The cache used to retain every model it ever loaded for the life of the
process (each spaCy Language is hundreds of MB), and it handed the SAME
Language object to every caller while batch extraction fans out over a
ThreadPoolExecutor — spaCy pipelines are not safe to invoke from concurrent
threads.
"""

import sys
import os
import threading
import unittest
from unittest.mock import MagicMock, patch

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from semantica.semantic_extract import methods
from semantica.semantic_extract.methods import (
    MAX_SPACY_MODELS_CACHED,
    clear_spacy_model_cache,
    run_spacy_text,
    spacy_pipeline_guard,
    _spacy_model_cache,
)


def make_spacy_mock():
    spacy = MagicMock()
    spacy.load = MagicMock(side_effect=lambda name: MagicMock(name=f"nlp-{name}"))
    return spacy


class TestBoundedCache(unittest.TestCase):
    def setUp(self):
        clear_spacy_model_cache()

    def tearDown(self):
        clear_spacy_model_cache()

    def test_cache_evicts_beyond_the_bound(self):
        spacy = make_spacy_mock()
        with patch.object(methods, "spacy", spacy):
            for i in range(MAX_SPACY_MODELS_CACHED + 2):
                with spacy_pipeline_guard(f"model_{i}"):
                    pass
        self.assertLessEqual(
            len(_spacy_model_cache), MAX_SPACY_MODELS_CACHED,
            f"the cache must stay bounded at {MAX_SPACY_MODELS_CACHED} models, "
            "not pin every model the process ever touched",
        )
        self.assertNotIn("model_0", _spacy_model_cache, "oldest entries evict first")

    def test_recently_used_entries_survive(self):
        spacy = make_spacy_mock()
        with patch.object(methods, "spacy", spacy):
            for i in range(MAX_SPACY_MODELS_CACHED):
                with spacy_pipeline_guard(f"model_{i}"):
                    pass
            # Touch the oldest, then overflow: LRU evicts the next-oldest.
            with spacy_pipeline_guard("model_0"):
                pass
            with spacy_pipeline_guard("model_new"):
                pass
        self.assertIn("model_0", _spacy_model_cache)
        self.assertNotIn("model_1", _spacy_model_cache)


class TestPerModelSerialization(unittest.TestCase):
    def setUp(self):
        clear_spacy_model_cache()

    def tearDown(self):
        clear_spacy_model_cache()

    def test_concurrent_calls_on_one_model_never_overlap(self):
        overlaps = []
        active = []
        lock = threading.Lock()

        def slow_nlp(text):
            with lock:
                active.append(text)
                if len(active) > 1:
                    overlaps.append(list(active))
            # Hold the "pipeline" long enough for a racing thread to enter
            # if the guard did not serialize.
            import time
            time.sleep(0.05)
            with lock:
                active.pop()
            return MagicMock(name=f"doc-{text}")

        spacy = MagicMock()
        spacy.load = MagicMock(return_value=MagicMock(side_effect=slow_nlp))
        with patch.object(methods, "spacy", spacy):
            threads = [
                threading.Thread(target=lambda i=i: run_spacy_text("m", f"t{i}"))
                for i in range(4)
            ]
            for t in threads:
                t.start()
            for t in threads:
                t.join()

        self.assertEqual(
            overlaps, [],
            "the per-model call lock must serialize concurrent invocations of "
            "the same shared Language",
        )

    def test_different_models_run_in_parallel(self):
        entered = threading.Barrier(2, timeout=5)

        def blocking_nlp(text):
            # Blocks until BOTH models are inside a call — impossible if the
            # guard were a single global lock.
            entered.wait()
            return MagicMock()

        spacy = MagicMock()
        spacy.load = MagicMock(return_value=MagicMock(side_effect=blocking_nlp))
        with patch.object(methods, "spacy", spacy):
            threads = [
                threading.Thread(target=lambda n=n: run_spacy_text(n, "t"))
                for n in ("model_a", "model_b")
            ]
            for t in threads:
                t.start()
            for t in threads:
                t.join(timeout=10)
                if t.is_alive():
                    for alive in threads:
                        alive.join(timeout=5)
                    self.fail("a barrier across two models timed out — the guard must be per-model, not global")


if __name__ == "__main__":
    unittest.main()
