import unittest
from unittest.mock import MagicMock, patch
from semantica.pipeline.pipeline_builder import PipelineBuilder, StepStatus
from semantica.pipeline.execution_engine import ExecutionEngine, PipelineStatus

class TestPipelineModule(unittest.TestCase):

    def setUp(self):
        # Mock progress tracker
        self.mock_tracker_patcher = patch("semantica.utils.progress_tracker.get_progress_tracker")
        self.mock_get_tracker = self.mock_tracker_patcher.start()
        self.mock_tracker = MagicMock()
        self.mock_get_tracker.return_value = self.mock_tracker

    def tearDown(self):
        self.mock_tracker_patcher.stop()

    def test_pipeline_builder_basic(self):
        """Test building a simple pipeline."""
        builder = PipelineBuilder()
        builder.add_step("step1", "dummy")
        builder.add_step("step2", "dummy")
        
        # Connect step1 -> step2
        builder.connect_steps("step1", "step2")
        
        pipeline = builder.build("test_pipeline")
        
        self.assertEqual(pipeline.name, "test_pipeline")
        self.assertEqual(len(pipeline.steps), 2)
        
        step2 = next(s for s in pipeline.steps if s.name == "step2")
        self.assertIn("step1", step2.dependencies)

    def test_pipeline_builder_validation(self):
        """Test pipeline validation logic."""
        builder = PipelineBuilder()
        builder.add_step("step1", "dummy")
        
        # Try to connect to non-existent step
        with self.assertRaises(Exception): # ValidationError
            builder.connect_steps("step1", "non_existent")

    def test_execution_engine_success(self):
        """Test successful pipeline execution."""
        # Define handlers
        def step1_handler(data, **kwargs):
            return data + 1
            
        def step2_handler(data, **kwargs):
            return data * 2
            
        # Build pipeline
        builder = PipelineBuilder()
        builder.add_step("step1", "math", handler=step1_handler)
        builder.add_step("step2", "math", handler=step2_handler)
        builder.connect_steps("step1", "step2")
        
        pipeline = builder.build("math_pipeline")
        
        # Execute
        engine = ExecutionEngine()
        result = engine.execute_pipeline(pipeline, data=5)
        
        self.assertTrue(result.success)
        self.assertEqual(result.output, 12) # (5 + 1) * 2 = 12
        self.assertEqual(pipeline.steps[0].status, StepStatus.COMPLETED)

    def test_registered_step_handler_executes(self):
        """A handler registered by step type should execute."""
        def increment(data):
            return data + 1

        builder = PipelineBuilder()
        builder.register_step_handler("math", increment)
        builder.add_step("increment", "math")

        result = ExecutionEngine().execute_pipeline(
            builder.build("registered"), data=1
        )

        self.assertTrue(result.success)
        self.assertEqual(result.output, 2)

    def test_explicit_handler_does_not_receive_control_fields(self):
        """Builder-only fields should not be passed to strict handlers."""
        def source(data):
            return data

        def increment(data, amount):
            return data + amount

        builder = PipelineBuilder()
        builder.add_step("source", "source", handler=source)
        step = builder.add_step(
            "increment",
            "math",
            handler=increment,
            dependencies=["source"],
            amount=2,
        )

        result = ExecutionEngine().execute_pipeline(
            builder.build("strict"), data=1
        )

        self.assertTrue(result.success)
        self.assertEqual(result.output, 3)
        self.assertEqual(step.config, {"amount": 2})

    def test_explicit_handler_overrides_registered_handler(self):
        """An explicit step handler should take precedence over the registry."""
        builder = PipelineBuilder()
        builder.register_step_handler("math", lambda data: data + 100)
        builder.add_step("increment", "math", handler=lambda data: data + 1)

        result = ExecutionEngine().execute_pipeline(
            builder.build("override"), data=1
        )

        self.assertTrue(result.success)
        self.assertEqual(result.output, 2)

    def test_step_without_handler_passes_input_through(self):
        """A step with no explicit or registered handler should be a no-op."""
        builder = PipelineBuilder()
        builder.add_step("passthrough", "unregistered")

        result = ExecutionEngine().execute_pipeline(
            builder.build("handlerless"), data={"value": 1}
        )

        self.assertTrue(result.success)
        self.assertEqual(result.output, {"value": 1})

    def test_falsy_explicit_handler_is_invoked(self):
        """A handler whose __bool__ is False must still be dispatched."""

        class FalseyHandler:
            def __bool__(self):
                return False

            def __call__(self, data):
                return {"explicit": data}

        builder = PipelineBuilder()
        builder.add_step("step1", "mytype", handler=FalseyHandler())

        result = ExecutionEngine().execute_pipeline(
            builder.build("falsy"), data=1
        )

        self.assertTrue(result.success)
        self.assertEqual(result.output, {"explicit": 1})

    def test_execution_engine_failure(self):
        """Test pipeline failure handling."""
        def failing_handler(data, **kwargs):
            raise ValueError("Something went wrong")
            
        builder = PipelineBuilder()
        builder.add_step("step1", "fail", handler=failing_handler)
        pipeline = builder.build("fail_pipeline")
        
        engine = ExecutionEngine()
        result = engine.execute_pipeline(pipeline, data=None)
        
        self.assertFalse(result.success)
        self.assertIn("Something went wrong", result.errors[0])
        self.assertEqual(pipeline.steps[0].status, StepStatus.FAILED)

    def test_topological_sort(self):
        """Test execution order respects dependencies."""
        execution_order = []
        
        def make_handler(name):
            def handler(data, **kwargs):
                execution_order.append(name)
                return data
            return handler
            
        builder = PipelineBuilder()
        builder.add_step("C", "type", handler=make_handler("C"))
        builder.add_step("B", "type", handler=make_handler("B"))
        builder.add_step("A", "type", handler=make_handler("A"))
        
        # Dependency: A -> B -> C
        builder.connect_steps("A", "B")
        builder.connect_steps("B", "C")
        
        pipeline = builder.build("ordered_pipeline")
        engine = ExecutionEngine()
        engine.execute_pipeline(pipeline)
        
        self.assertEqual(execution_order, ["A", "B", "C"])

    def test_imports_no_circular_dependencies(self):
        import semantica

        _ = semantica.pipeline

        from semantica.deduplication import DuplicateDetector
        from semantica.pipeline import PipelineBuilder, PipelineValidator

        builder = PipelineBuilder()
        builder.add_step("step1", "dummy")
        pipeline = builder.build("import_test_pipeline")

        validator = PipelineValidator()
        result = validator.validate_pipeline(pipeline)

        self.assertTrue(result.valid)

        detector = DuplicateDetector()
        self.assertIsNotNone(detector)

if __name__ == "__main__":
    unittest.main()
