#!/usr/bin/env python3
"""Regression tests for ``ContextGraph.to_dict()`` thread safety.

``ContextGraph`` guards its state with ``self._lock`` (an ``RLock``), and every
reader on the class takes it -- ``stats``, ``density``, ``find_nodes``,
``find_edges``, ``get_neighbors``, ``get_nodes_by_label``, ``state_at`` and
``save_to_file`` all do. ``to_dict`` was the one exception: it iterated
``self.nodes.values()`` and ``self.edges`` unguarded, so a concurrent writer
raised ``RuntimeError: dictionary changed size during iteration``.

``save_to_file`` was safe only incidentally -- it holds the lock and builds its
payload inline rather than delegating to ``to_dict``.
"""

import threading
import time

from semantica.context.context_graph import ContextGraph


def _seeded_graph(node_count: int = 200) -> ContextGraph:
    graph = ContextGraph(advanced_analytics=False)
    for i in range(node_count):
        graph.add_node(f"seed{i}", "seed")
    return graph


class TestToDictHoldsTheLock:
    """``to_dict`` must take ``_lock``, like every sibling reader."""

    def test_to_dict_waits_for_the_lock(self):
        """Deterministic proof the lock is held -- no race window needed.

        With the lock held elsewhere, ``to_dict`` must block. Without the fix it
        returns immediately, since it never asks for the lock at all.
        """
        graph = _seeded_graph(10)
        started = threading.Event()
        finished = threading.Event()

        def snapshot():
            started.set()
            graph.to_dict()
            finished.set()

        with graph._lock:
            worker = threading.Thread(target=snapshot, daemon=True)
            worker.start()
            assert started.wait(timeout=5.0), "the worker thread never started running"
            # The worker is now running and cannot finish while this thread
            # owns the lock.
            assert not finished.wait(timeout=0.5), (
                "to_dict() completed while another thread held _lock, so it is "
                "reading graph state unguarded"
            )

        assert finished.wait(timeout=5.0), "to_dict() did not complete after _lock was released"
        worker.join(timeout=5.0)
        assert not worker.is_alive(), "the worker thread is still running after to_dict() finished"

    def test_to_dict_is_reentrant_for_a_caller_holding_the_lock(self):
        """``_lock`` is an ``RLock``, so lock-holding callers must not deadlock.

        The nested acquisition runs in a daemon worker joined with a timeout so
        that a non-reentrant lock fails the test instead of hanging it.
        """
        graph = _seeded_graph(10)
        result = {}

        def nested_snapshot():
            with graph._lock:
                result["snapshot"] = graph.to_dict()

        worker = threading.Thread(target=nested_snapshot, daemon=True)
        worker.start()
        worker.join(timeout=5.0)

        assert not worker.is_alive(), (
            "to_dict() deadlocked when called by a thread already holding "
            "_lock -- the lock is no longer reentrant"
        )
        assert len(result["snapshot"]["nodes"]) == 10


class TestToDictUnderConcurrentWrites:
    """The reported race: snapshot one thread, mutate from another."""

    def _run_race(self, graph: ContextGraph, reader, duration: float = 1.0):
        """Hammer ``reader`` while a writer adds nodes. Returns (errors, reads)."""
        stop = threading.Event()
        errors = []
        reads = []

        def writer():
            i = 0
            while not stop.is_set():
                try:
                    graph.add_node(f"w{i}", "written")
                except Exception as exc:  # pragma: no cover - writer must stay healthy
                    errors.append(exc)
                    return
                i += 1

        def reader_loop():
            while not stop.is_set():
                try:
                    reads.append(reader())
                except Exception as exc:
                    errors.append(exc)
                    stop.set()
                    return

        threads = [
            threading.Thread(target=writer, daemon=True),
            threading.Thread(target=reader_loop, daemon=True),
        ]
        for thread in threads:
            thread.start()
        time.sleep(duration)
        stop.set()
        for thread in threads:
            thread.join(timeout=5.0)
            assert not thread.is_alive(), (
                "a worker thread was still running 5s after the stop signal -- "
                "a hang here would otherwise leak into subsequent tests"
            )

        return errors, reads

    def test_to_dict_does_not_raise_during_concurrent_writes(self):
        graph = _seeded_graph()
        errors, reads = self._run_race(graph, graph.to_dict)

        assert not errors, f"to_dict() raised under concurrent writes: {errors[0]!r}"
        assert reads, "the reader thread never completed a to_dict() call"

    def test_to_dict_snapshot_is_internally_consistent(self):
        """The reported statistics must describe the payload actually emitted.

        ``to_dict`` builds ``nodes``/``edges`` and then reads ``len(self.nodes)``
        and ``len(self.edges)`` for its ``statistics`` block. Unguarded, a write
        landing between those steps yields counts that contradict the lists.
        """
        graph = _seeded_graph()
        errors, reads = self._run_race(graph, graph.to_dict)

        assert not errors, f"to_dict() raised under concurrent writes: {errors[0]!r}"
        assert reads, "the reader thread never completed a to_dict() call"
        for snapshot in reads:
            stats = snapshot["statistics"]
            assert stats["node_count"] == len(snapshot["nodes"]), (
                f"statistics.node_count={stats['node_count']} contradicts the "
                f"{len(snapshot['nodes'])} nodes in the same snapshot"
            )
            assert stats["edge_count"] == len(snapshot["edges"]), (
                f"statistics.edge_count={stats['edge_count']} contradicts the "
                f"{len(snapshot['edges'])} edges in the same snapshot"
            )

    def test_snapshot_node_ids_are_unique(self):
        """A torn read can emit the same node twice; a locked one cannot."""
        graph = _seeded_graph()
        errors, reads = self._run_race(graph, graph.to_dict)

        assert not errors, f"to_dict() raised under concurrent writes: {errors[0]!r}"
        for snapshot in reads:
            ids = [node["id"] for node in snapshot["nodes"]]
            assert len(ids) == len(set(ids)), "to_dict() emitted duplicate node ids"
