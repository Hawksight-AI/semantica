"""Focused tests for pipeline parallel execution (issue #1223).

Covers:
    - ``PipelineBuilder.set_parallelism()`` validation
    - dependency-layer parallel execution gated on ``parallel_safe``
    - input isolation via deep copies
    - incremental dict merging of parallel outputs
    - failure handling and cancellation semantics
    - ``parallel_safe`` not leaking into handler kwargs
    - ``parallel_safe`` surviving serialization round-trips
"""

import threading
import time
import unittest
from unittest.mock import MagicMock, patch

from semantica.pipeline.execution_engine import ExecutionEngine
from semantica.pipeline.failure_handler import RetryPolicy, RetryStrategy
from semantica.pipeline.pipeline_builder import (
    Pipeline,
    PipelineBuilder,
    PipelineSerializer,
    PipelineStep,
    StepStatus,
)
from semantica.utils.exceptions import ProcessingError, ValidationError


class ConcurrencyProbe:
    """Thread-safe tracker of handler invocations and concurrency level."""

    def __init__(self):
        self._lock = threading.Lock()
        self.active = 0
        self.max_active = 0
        self.calls = 0

    def __enter__(self):
        with self._lock:
            self.active += 1
            self.calls += 1
            self.max_active = max(self.max_active, self.active)
        return self

    def __exit__(self, *exc):
        with self._lock:
            self.active -= 1
        return False


def branch_handler(probe, key, value=True, delay=0.0):
    """Build a handler that records concurrency and adds one output key."""

    def handler(data, **kwargs):
        with probe:
            if delay:
                time.sleep(delay)
            return {**data, key: value}

    return handler


class Undeepcopyable:
    """Object whose deepcopy always fails."""

    def __deepcopy__(self, memo):
        raise TypeError("cannot deepcopy this object")


class TestSetParallelismValidation(unittest.TestCase):
    """set_parallelism() must only accept positive integers."""

    def test_rejects_invalid_levels(self):
        builder = PipelineBuilder()
        for invalid in (0, -1, 1.5, True, False, "2", None):
            with self.assertRaises(ValidationError):
                builder.set_parallelism(invalid)

    def test_accepts_positive_integers(self):
        builder = PipelineBuilder()
        builder.set_parallelism(4)
        self.assertEqual(builder.pipeline_config["parallelism"], 4)


class TestPipelineParallelExecution(unittest.TestCase):

    def setUp(self):
        self.mock_tracker_patcher = patch(
            "semantica.utils.progress_tracker.get_progress_tracker"
        )
        self.mock_get_tracker = self.mock_tracker_patcher.start()
        self.mock_get_tracker.return_value = MagicMock()

    def tearDown(self):
        self.mock_tracker_patcher.stop()

    def _build(self, steps, parallelism=None, name="parallel_pipeline"):
        """steps: list of (step_name, step_type, handler, parallel_safe)."""
        builder = PipelineBuilder()
        for step_name, step_type, handler, parallel_safe in steps:
            builder.add_step(
                step_name, step_type, handler=handler, parallel_safe=parallel_safe
            )
        if parallelism is not None:
            builder.set_parallelism(parallelism)
        return builder.build(name)

    def test_unconfigured_pipeline_stays_serial(self):
        probe = ConcurrencyProbe()
        pipeline = self._build(
            [
                ("a", "branch", branch_handler(probe, "a"), True),
                ("b", "branch", branch_handler(probe, "b"), True),
            ]
        )

        result = ExecutionEngine().execute_pipeline(pipeline, data={"text": "hi"})

        self.assertTrue(result.success)
        self.assertEqual(probe.max_active, 1)

    def test_parallelism_one_stays_serial(self):
        probe = ConcurrencyProbe()
        pipeline = self._build(
            [
                ("a", "branch", branch_handler(probe, "a"), True),
                ("b", "branch", branch_handler(probe, "b"), True),
            ],
            parallelism=1,
        )

        result = ExecutionEngine().execute_pipeline(pipeline, data={"text": "hi"})

        self.assertTrue(result.success)
        self.assertEqual(probe.max_active, 1)

    def test_parallel_safe_steps_overlap_with_barrier(self):
        barrier = threading.Barrier(2)
        done = {"a": False, "b": False}

        def handler(key):
            def inner(data, **kwargs):
                barrier.wait(timeout=5)
                done[key] = True
                return {**data, key: True}

            return inner

        pipeline = self._build(
            [
                ("a", "branch", handler("a"), True),
                ("b", "branch", handler("b"), True),
            ],
            parallelism=2,
        )

        result = ExecutionEngine().execute_pipeline(pipeline, data={"text": "hi"})

        self.assertTrue(result.success, msg=str(result.errors))
        self.assertTrue(done["a"])
        self.assertTrue(done["b"])

    def test_active_workers_do_not_exceed_parallelism(self):
        probe = ConcurrencyProbe()
        pipeline = self._build(
            [
                ("a", "branch", branch_handler(probe, "a", delay=0.15), True),
                ("b", "branch", branch_handler(probe, "b", delay=0.15), True),
                ("c", "branch", branch_handler(probe, "c", delay=0.15), True),
                ("d", "branch", branch_handler(probe, "d", delay=0.15), True),
            ],
            parallelism=2,
        )

        result = ExecutionEngine().execute_pipeline(pipeline, data={"text": "hi"})

        self.assertTrue(result.success)
        self.assertLessEqual(probe.max_active, 2)
        self.assertGreaterEqual(probe.max_active, 2)

    def test_unmarked_steps_stay_serial(self):
        probe = ConcurrencyProbe()
        pipeline = self._build(
            [
                ("a", "branch", branch_handler(probe, "a"), False),
                ("b", "branch", branch_handler(probe, "b"), False),
            ],
            parallelism=2,
        )

        result = ExecutionEngine().execute_pipeline(pipeline, data={"text": "hi"})

        self.assertTrue(result.success)
        self.assertEqual(probe.max_active, 1)

    def test_layer_with_one_unsafe_step_is_serial(self):
        probe = ConcurrencyProbe()
        pipeline = self._build(
            [
                ("a", "branch", branch_handler(probe, "a"), True),
                ("b", "branch", branch_handler(probe, "b"), False),
            ],
            parallelism=2,
        )

        result = ExecutionEngine().execute_pipeline(pipeline, data={"text": "hi"})

        self.assertTrue(result.success)
        self.assertEqual(probe.max_active, 1)

    def test_pure_dependency_chain_stays_serial(self):
        probe = ConcurrencyProbe()

        def chain_handler(key):
            def inner(data, **kwargs):
                with probe:
                    return {**data, key: True}

            return inner

        builder = PipelineBuilder()
        builder.add_step(
            "a", "branch", handler=chain_handler("a"), parallel_safe=True
        )
        builder.add_step(
            "b",
            "branch",
            handler=chain_handler("b"),
            parallel_safe=True,
            dependencies=["a"],
        )
        builder.add_step(
            "c",
            "branch",
            handler=chain_handler("c"),
            parallel_safe=True,
            dependencies=["b"],
        )
        builder.set_parallelism(4)
        pipeline = builder.build("chain_pipeline")

        result = ExecutionEngine().execute_pipeline(pipeline, data={"text": "hi"})

        self.assertTrue(result.success)
        self.assertEqual(probe.max_active, 1)
        self.assertEqual(result.output, {"text": "hi", "a": True, "b": True, "c": True})

    def test_non_dict_input_falls_back_to_serial(self):
        probe = ConcurrencyProbe()

        def passthrough(data, **kwargs):
            with probe:
                return data

        pipeline = self._build(
            [
                ("a", "branch", passthrough, True),
                ("b", "branch", passthrough, True),
            ],
            parallelism=2,
        )

        result = ExecutionEngine().execute_pipeline(
            pipeline, data="plain-text-input"
        )

        self.assertTrue(result.success)
        self.assertEqual(probe.calls, 2)
        self.assertEqual(probe.max_active, 1)
        self.assertEqual(result.output, "plain-text-input")

    def test_deepcopy_failure_falls_back_to_serial(self):
        probe = ConcurrencyProbe()

        pipeline = self._build(
            [
                ("a", "branch", branch_handler(probe, "a"), True),
                ("b", "branch", branch_handler(probe, "b"), True),
            ],
            parallelism=2,
        )

        result = ExecutionEngine().execute_pipeline(
            pipeline, data={"text": "hi", "obj": Undeepcopyable()}
        )

        self.assertTrue(result.success, msg=str(result.errors))
        self.assertEqual(probe.calls, 2)
        self.assertEqual(probe.max_active, 1)
        self.assertIn("a", result.output)
        self.assertIn("b", result.output)

    def test_parallel_results_merge_different_fields(self):
        probe = ConcurrencyProbe()
        pipeline = self._build(
            [
                ("a", "branch", branch_handler(probe, "entities", ["Alice"]), True),
                ("b", "branch", branch_handler(probe, "triplets", [(1, 2)]), True),
            ],
            parallelism=2,
        )

        result = ExecutionEngine().execute_pipeline(
            pipeline, data={"text": "Alice works at Acme"}
        )

        self.assertTrue(result.success)
        self.assertEqual(
            result.output,
            {
                "text": "Alice works at Acme",
                "entities": ["Alice"],
                "triplets": [(1, 2)],
            },
        )

    def test_parallel_results_same_key_same_value_allowed(self):
        probe = ConcurrencyProbe()
        pipeline = self._build(
            [
                ("a", "branch", branch_handler(probe, "shared", [1, 2]), True),
                ("b", "branch", branch_handler(probe, "shared", [1, 2]), True),
            ],
            parallelism=2,
        )

        result = ExecutionEngine().execute_pipeline(pipeline, data={"text": "hi"})

        self.assertTrue(result.success, msg=str(result.errors))
        self.assertEqual(result.output["shared"], [1, 2])

    def test_parallel_results_same_key_different_values_raises(self):
        probe = ConcurrencyProbe()
        pipeline = self._build(
            [
                ("a", "branch", branch_handler(probe, "shared", 1), True),
                ("b", "branch", branch_handler(probe, "shared", 2), True),
            ],
            parallelism=2,
        )

        result = ExecutionEngine().execute_pipeline(pipeline, data={"text": "hi"})

        self.assertFalse(result.success)
        error_text = result.errors[0] if result.errors else ""
        self.assertIn("shared", error_text)
        self.assertIn("a", error_text)
        self.assertIn("b", error_text)

    def test_parallel_handler_non_dict_return_fails(self):
        probe = ConcurrencyProbe()

        def non_dict_handler(data, **kwargs):
            with probe:
                return "not-a-dict"

        pipeline = self._build(
            [
                ("a", "branch", branch_handler(probe, "a"), True),
                ("b", "branch", non_dict_handler, True),
            ],
            parallelism=2,
        )

        result = ExecutionEngine().execute_pipeline(pipeline, data={"text": "hi"})

        self.assertFalse(result.success)
        error_text = result.errors[0] if result.errors else ""
        self.assertIn("b", error_text)
        self.assertIn("str", error_text)

    def test_non_dict_handler_executed_only_once(self):
        probe = ConcurrencyProbe()

        def non_dict_handler(data, **kwargs):
            with probe:
                return "not-a-dict"

        pipeline = self._build(
            [
                ("a", "branch", branch_handler(probe, "a"), True),
                ("b", "branch", non_dict_handler, True),
            ],
            parallelism=2,
        )

        result = ExecutionEngine().execute_pipeline(pipeline, data={"text": "hi"})

        self.assertFalse(result.success)
        self.assertEqual(probe.calls, 2)  # one invocation per handler, no re-runs

    def test_parallel_step_retry_succeeds(self):
        engine = ExecutionEngine()
        engine.failure_handler.set_retry_policy(
            "flaky",
            RetryPolicy(
                max_retries=2, initial_delay=0.0, strategy=RetryStrategy.FIXED
            ),
        )

        probe = ConcurrencyProbe()
        attempts = {"flaky": 0}

        def flaky_handler(data, **kwargs):
            with probe:
                attempts["flaky"] += 1
                if attempts["flaky"] == 1:
                    raise RuntimeError("transient failure")
                return {**data, "flaky": True}

        pipeline = self._build(
            [
                ("a", "flaky", flaky_handler, True),
                ("b", "branch", branch_handler(probe, "b"), True),
            ],
            parallelism=2,
        )

        result = engine.execute_pipeline(pipeline, data={"text": "hi"})

        self.assertTrue(result.success, msg=str(result.errors))
        self.assertEqual(attempts["flaky"], 2)

    def test_failed_branch_skips_downstream_layer(self):
        engine = ExecutionEngine()
        engine.failure_handler.set_retry_policy(
            "always_fail", RetryPolicy(max_retries=0)
        )

        probe = ConcurrencyProbe()

        def failing_handler(data, **kwargs):
            with probe:
                raise RuntimeError("permanent failure")

        downstream_calls = {"c": 0}

        def downstream_handler(data, **kwargs):
            downstream_calls["c"] += 1
            return {**data, "c": True}

        builder = PipelineBuilder()
        builder.add_step("a", "always_fail", handler=failing_handler, parallel_safe=True)
        builder.add_step("b", "branch", handler=branch_handler(probe, "b"), parallel_safe=True)
        builder.add_step(
            "c", "branch", handler=downstream_handler, dependencies=["a", "b"]
        )
        builder.set_parallelism(2)
        pipeline = builder.build("failure_pipeline")

        result = engine.execute_pipeline(pipeline, data={"text": "hi"})

        self.assertFalse(result.success)
        self.assertEqual(downstream_calls["c"], 0)

        failed_step = next(s for s in pipeline.steps if s.name == "a")
        self.assertEqual(failed_step.status, StepStatus.FAILED)
        self.assertIsNotNone(failed_step.error)

    def test_parallel_safe_not_passed_to_handler_kwargs(self):
        received_kwargs = {}

        def capturing_handler(data, **kwargs):
            received_kwargs.update(kwargs)
            return data

        builder = PipelineBuilder()
        builder.add_step(
            "a", "branch", handler=capturing_handler, parallel_safe=True, batch_size=2
        )
        pipeline = builder.build("kwargs_pipeline")

        result = ExecutionEngine().execute_pipeline(pipeline, data={"text": "hi"})

        self.assertTrue(result.success)
        self.assertIn("batch_size", received_kwargs)
        self.assertNotIn("parallel_safe", received_kwargs)
        self.assertNotIn("parallel_safe", pipeline.steps[0].config)

    def test_unchanged_echoed_key_does_not_conflict(self):
        probe = ConcurrencyProbe()
        pipeline = self._build(
            [
                # "a" echoes the base value of "shared" (unchanged),
                # "b" legitimately changes it: no false conflict.
                ("a", "branch", branch_handler(probe, "shared", 1), True),
                ("b", "branch", branch_handler(probe, "shared", 2), True),
            ],
            parallelism=2,
        )

        result = ExecutionEngine().execute_pipeline(
            pipeline, data={"text": "hi", "shared": 1}
        )

        self.assertTrue(result.success, msg=str(result.errors))
        self.assertEqual(result.output["shared"], 2)

    def test_ambiguous_equality_counts_as_changed(self):
        sentinel = Uncomparable()

        def echo(data, **kwargs):
            return {**data, "shared": data["shared"]}

        def change(data, **kwargs):
            return {**data, "shared": "changed"}

        pipeline = self._build(
            [("a", "branch", echo, True), ("b", "branch", change, True)],
            parallelism=2,
        )

        result = ExecutionEngine().execute_pipeline(
            pipeline, data={"text": "hi", "shared": sentinel}
        )

        # Ambiguous equality must not be treated as unchanged, so both
        # branches count as writes and the merge reports the conflict.
        self.assertFalse(result.success)
        error_text = result.errors[0] if result.errors else ""
        self.assertIn("shared", error_text)

    def test_non_boolean_parallel_safe_stays_serial(self):
        probe = ConcurrencyProbe()
        pipeline = self._build(
            [
                ("a", "branch", branch_handler(probe, "a"), True),
                ("b", "branch", branch_handler(probe, "b"), True),
            ],
            parallelism=2,
        )
        # Simulate a truthy non-bool value reaching the engine (e.g. set
        # directly on the step attribute): must not enable concurrency.
        for step in pipeline.steps:
            step.parallel_safe = "false"

        result = ExecutionEngine().execute_pipeline(pipeline, data={"text": "hi"})

        self.assertTrue(result.success)
        self.assertEqual(probe.max_active, 1)

    def test_non_dict_result_reports_failure_not_completion(self):
        probe = ConcurrencyProbe()
        tracking_ids = {}
        counter = {"n": 0}

        def fake_start(*args, **kwargs):
            tid = f"tid_{counter['n']}"
            counter["n"] += 1
            tracking_ids[kwargs.get("submodule")] = tid
            return tid

        with patch(
            "semantica.pipeline.execution_engine.get_progress_tracker"
        ) as mock_get:
            tracker = MagicMock()
            tracker.start_tracking.side_effect = fake_start
            mock_get.return_value = tracker
            engine = ExecutionEngine()

        def non_dict_handler(data, **kwargs):
            with probe:
                return "not-a-dict"

        pipeline = self._build(
            [
                ("a", "branch", branch_handler(probe, "a"), True),
                ("b", "branch", non_dict_handler, True),
            ],
            parallelism=2,
            name="progress_pipeline",
        )

        result = engine.execute_pipeline(pipeline, data={"text": "hi"})

        self.assertFalse(result.success)
        failed_step = next(s for s in pipeline.steps if s.name == "b")
        self.assertEqual(failed_step.status, StepStatus.FAILED)
        self.assertIsInstance(failed_step.error, ProcessingError)
        # Handler ran exactly once: never re-run serially.
        self.assertEqual(probe.calls, 2)

        b_tid = tracking_ids.get("progress_pipeline:branch:b")
        self.assertIsNotNone(
            b_tid, f"expected tracking for step b, got {tracking_ids}"
        )
        b_stops = [
            c
            for c in tracker.stop_tracking.call_args_list
            if (c.args[0] if c.args else c.kwargs.get("tracking_id")) == b_tid
        ]
        self.assertTrue(b_stops)
        for call in b_stops:
            status = call.kwargs.get("status")
            self.assertEqual(status, "failed")
            self.assertNotEqual(status, "completed")

    def test_same_type_steps_get_distinct_tracking_records(self):
        probe = ConcurrencyProbe()
        pipeline = self._build(
            [
                ("a", "branch", branch_handler(probe, "a"), True),
                ("b", "branch", branch_handler(probe, "b"), True),
            ],
            parallelism=2,
            name="tracking_pipeline",
        )

        with patch(
            "semantica.pipeline.execution_engine.get_progress_tracker"
        ) as mock_get:
            tracker = MagicMock()
            mock_get.return_value = tracker
            engine = ExecutionEngine()

        result = engine.execute_pipeline(pipeline, data={"text": "hi"})

        self.assertTrue(result.success, msg=str(result.errors))
        submodules = [
            call.kwargs.get("submodule")
            for call in tracker.start_tracking.call_args_list
            if call.kwargs.get("module") == "pipeline"
        ]
        # Concurrent steps of the same step_type get distinct submodules
        # (and therefore distinct tracking IDs), including pipeline identity.
        self.assertIn("tracking_pipeline:branch:a", submodules)
        self.assertIn("tracking_pipeline:branch:b", submodules)


class TestParallelSafeSerialization(unittest.TestCase):
    """parallel_safe must survive dict and JSON round-trips."""

    def _build_pipeline(self):
        builder = PipelineBuilder()
        builder.add_step("extract", "source", parallel_safe=True, batch_size=10)
        builder.add_step("index", "sink", dependencies=["extract"])
        builder.set_parallelism(3)
        return builder.build("parallel-serialization")

    def test_serializer_roundtrip_preserves_parallel_safe(self):
        pipeline = self._build_pipeline()
        serializer = PipelineSerializer()

        serialized = serializer.serialize_pipeline(pipeline, format="dict")
        self.assertTrue(serialized["steps"][0]["parallel_safe"])
        self.assertFalse(serialized["steps"][1]["parallel_safe"])

        restored = serializer.deserialize_pipeline(serialized)
        self.assertTrue(restored.steps[0].parallel_safe)
        self.assertFalse(restored.steps[1].parallel_safe)
        self.assertEqual(restored.config.get("parallelism"), 3)

    def test_serializer_json_roundtrip_preserves_parallel_safe(self):
        pipeline = self._build_pipeline()
        serializer = PipelineSerializer()

        serialized = serializer.serialize_pipeline(pipeline, format="json")
        restored = serializer.deserialize_pipeline(serialized)

        self.assertTrue(restored.steps[0].parallel_safe)
        self.assertFalse(restored.steps[1].parallel_safe)

    def test_builder_serialize_outputs_parallel_safe(self):
        builder = PipelineBuilder()
        builder.add_step("extract", "source", parallel_safe=True)
        builder.add_step("index", "sink", dependencies=["extract"])
        builder.set_parallelism(2)

        serialized = builder.serialize(format="dict")

        self.assertTrue(serialized["steps"][0]["parallel_safe"])
        self.assertFalse(serialized["steps"][1]["parallel_safe"])
        self.assertEqual(serialized["config"]["parallelism"], 2)


class Uncomparable:
    """Object whose equality comparison always raises TypeError."""

    def __eq__(self, other):
        raise TypeError("cannot compare")


class TestParallelDependencyValidation(unittest.TestCase):
    """Cyclic/unknown dependencies must fail with ValidationError in the
    parallel path, not RecursionError/KeyError (review finding #1)."""

    def _engine(self):
        with patch(
            "semantica.pipeline.execution_engine.get_progress_tracker"
        ) as mock_get:
            mock_get.return_value = MagicMock()
            engine = ExecutionEngine()
        return engine

    def _handler(self):
        return lambda data, **kwargs: data

    def test_cyclic_dependencies_raise_validation_error(self):
        # Construct the pipeline directly: the builder already rejects
        # cycles at build time, so bypassing it exercises the engine-level
        # grouping guard (which otherwise hits RecursionError).
        steps = [
            PipelineStep(
                name="a",
                step_type="branch",
                handler=self._handler(),
                dependencies=["b"],
                parallel_safe=True,
            ),
            PipelineStep(
                name="b",
                step_type="branch",
                handler=self._handler(),
                dependencies=["a"],
                parallel_safe=True,
            ),
        ]
        pipeline = Pipeline(
            name="cyclic_pipeline",
            steps=steps,
            config={"parallelism": 4},
        )

        result = self._engine().execute_pipeline(pipeline, data={"text": "hi"})

        self.assertFalse(result.success)
        error_text = result.errors[0] if result.errors else ""
        self.assertIn("Circular dependency", error_text)

    def test_unknown_dependency_raises_validation_error(self):
        # Construct the pipeline directly so the engine-level unknown
        # dependency guard is exercised (instead of a builder-time
        # KeyError from the grouping DFS).
        steps = [
            PipelineStep(
                name="a",
                step_type="branch",
                handler=self._handler(),
                dependencies=["missing"],
                parallel_safe=True,
            ),
        ]
        pipeline = Pipeline(
            name="unknown_dep_pipeline",
            steps=steps,
            config={"parallelism": 4},
        )

        result = self._engine().execute_pipeline(pipeline, data={"text": "hi"})

        self.assertFalse(result.success)
        error_text = result.errors[0] if result.errors else ""
        self.assertIn("unknown step 'missing'", error_text)
        self.assertIn("'a'", error_text)


class TestParallelSafeMustBeBoolean(unittest.TestCase):
    """parallel_safe must be an explicit boolean everywhere (review #4)."""

    def test_add_step_rejects_non_boolean_values(self):
        builder = PipelineBuilder()
        for invalid in ("false", "true", 1, 0, None, [True]):
            with self.assertRaises(ValidationError):
                builder.add_step(
                    "a",
                    "branch",
                    handler=lambda data, **kwargs: data,
                    parallel_safe=invalid,
                )

    def test_build_pipeline_rejects_non_boolean_values(self):
        builder = PipelineBuilder()
        config = {
            "name": "invalid_parallel_safe",
            "steps": [
                {"name": "a", "type": "branch", "parallel_safe": "false"}
            ],
        }
        with self.assertRaises(ValidationError):
            builder.build_pipeline(config)


if __name__ == "__main__":
    unittest.main()