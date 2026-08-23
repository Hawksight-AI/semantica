import pytest
import time
from unittest.mock import MagicMock, patch
from semantica.pipeline import (
    PipelineBuilder,
    ExecutionEngine,
    FailureHandler,
    ParallelismManager,
    RetryPolicy,
    RetryStrategy,
    PipelineStatus,
    StepStatus,
    Task,
    ErrorSeverity,
    PipelineTemplateManager,
    PipelineTemplate,
    PipelineValidator,
    ResourceScheduler,
    ResourceType
)
from semantica.pipeline.pipeline_builder import Pipeline, PipelineSerializer
from semantica.pipeline.execution_engine import ExecutionResult

pytestmark = pytest.mark.integration

# --- Fixtures ---

@pytest.fixture
def pipeline_serializer():
    return PipelineSerializer()

@pytest.fixture
def pipeline_builder():
    return PipelineBuilder()

@pytest.fixture
def execution_engine():
    return ExecutionEngine()

@pytest.fixture
def failure_handler():
    return FailureHandler()

@pytest.fixture
def parallelism_manager():
    return ParallelismManager(max_workers=2)

@pytest.fixture
def template_manager():
    return PipelineTemplateManager()

@pytest.fixture
def validator():
    return PipelineValidator()

@pytest.fixture
def resource_scheduler():
    return ResourceScheduler()

# --- Test PipelineBuilder ---

def test_pipeline_serializer(pipeline_serializer, pipeline_builder):
    # Create a pipeline first
    pipeline = pipeline_builder.add_step("s1", "t1").build("test_pipe")
    
    # Test serialization
    serialized_json = pipeline_serializer.serialize_pipeline(pipeline, format="json")
    assert isinstance(serialized_json, str)
    assert "s1" in serialized_json
    
    serialized_dict = pipeline_serializer.serialize_pipeline(pipeline, format="dict")
    assert isinstance(serialized_dict, dict)
    assert serialized_dict["name"] == "test_pipe"
    
    # Test deserialization
    deserialized = pipeline_serializer.deserialize_pipeline(serialized_dict)
    assert deserialized.name == "test_pipe"
    assert len(deserialized.steps) == 1
    assert deserialized.steps[0].name == "s1"
    
    # Test versioning
    versioned = pipeline_serializer.version_pipeline(pipeline, {"version": "2.0"})
    assert versioned.metadata["version"] == "2.0"

def test_pipeline_builder_add_step(pipeline_builder):
    pipeline_builder.add_step("step1", "type1", foo="bar")
    assert len(pipeline_builder.steps) == 1
    step = pipeline_builder.steps[0]
    assert step.name == "step1"
    assert step.step_type == "type1"
    assert step.config["foo"] == "bar"

def test_pipeline_builder_connect_steps(pipeline_builder):
    pipeline_builder.add_step("step1", "type1")
    pipeline_builder.add_step("step2", "type2")
    pipeline_builder.connect_steps("step1", "step2")
    
    step2 = pipeline_builder.get_step("step2")
    assert "step1" in step2.dependencies

def test_pipeline_builder_build(pipeline_builder):
    pipeline_builder.add_step("step1", "type1")
    pipeline = pipeline_builder.build("test_pipeline")
    
    assert isinstance(pipeline, Pipeline)
    assert pipeline.name == "test_pipeline"
    assert len(pipeline.steps) == 1

def test_pipeline_builder_from_config(pipeline_builder):
    config = {
        "name": "config_pipeline",
        "steps": [
            {"name": "s1", "type": "t1", "config": {"a": 1}},
            {"name": "s2", "type": "t2", "config": {"dependencies": ["s1"]}}
        ]
    }
    pipeline = pipeline_builder.build_pipeline(config)
    assert pipeline.name == "config_pipeline"
    assert len(pipeline.steps) == 2
    assert pipeline.steps[1].dependencies == ["s1"]

# --- Test ExecutionEngine ---

def test_execution_engine_execute_simple_pipeline(execution_engine, pipeline_builder):
    # Define a simple handler
    def step_handler(data, **config):
        return {**data, "processed": True}

    pipeline = (
        pipeline_builder
        .add_step("step1", "type1", handler=step_handler)
        .build()
    )

    input_data = {"raw": "data"}
    result = execution_engine.execute_pipeline(pipeline, input_data)

    assert isinstance(result, ExecutionResult)
    assert result.success is True
    assert result.output["processed"] is True
    assert result.metrics["steps_executed"] == 1
    assert result.metrics["steps_failed"] == 0

def test_execution_engine_execute_pipeline_with_dependencies(execution_engine, pipeline_builder):
    def step1_handler(data, **config):
        return {**data, "step1": True}
    
    def step2_handler(data, **config):
        return {**data, "step2": True}

    pipeline = (
        pipeline_builder
        .add_step("step1", "type1", handler=step1_handler)
        .add_step("step2", "type2", dependencies=["step1"], handler=step2_handler)
        .build()
    )

    result = execution_engine.execute_pipeline(pipeline, {})
    assert result.success is True
    assert result.output["step1"] is True
    assert result.output["step2"] is True

def test_execution_engine_failure(execution_engine, pipeline_builder):
    def failing_handler(data, **config):
        raise ValueError("Oops")

    pipeline = (
        pipeline_builder
        .add_step("step1", "type1", handler=failing_handler)
        .build()
    )

    result = execution_engine.execute_pipeline(pipeline, {})
    assert result.success is False
    assert result.metrics["steps_failed"] == 1
    assert "Oops" in str(result.errors)

# --- Test FailureHandler ---

def test_failure_handler_classify_error(failure_handler):
    error = ValueError("Something wrong")
    classification = failure_handler.classify_error(error)
    assert classification["error_type"] == "ValueError"
    # ValueError maps to MEDIUM by default else block logic? No, check code:
    # default severity is MEDIUM.
    assert classification["severity"] == ErrorSeverity.MEDIUM

    timeout_error = RuntimeError("Connection timeout")
    classification = failure_handler.classify_error(timeout_error)
    assert classification["severity"] == ErrorSeverity.MEDIUM # Based on code analysis

def test_failure_handler_retry_policy(failure_handler):
    policy = RetryPolicy(max_retries=2, strategy=RetryStrategy.FIXED, initial_delay=0.1)
    failure_handler.set_retry_policy("test_type", policy)
    
    retrieved_policy = failure_handler.get_retry_policy("test_type")
    assert retrieved_policy.max_retries == 2
    assert retrieved_policy.strategy == RetryStrategy.FIXED

def test_failure_handler_handle_step_failure(failure_handler, pipeline_builder):
    step = pipeline_builder.add_step("step1", "test_type").steps[0]
    error = ValueError("fail")
    
    # Mock retry policy to ensure it says "retry"
    policy = RetryPolicy(max_retries=1, strategy=RetryStrategy.FIXED, initial_delay=0.0)
    failure_handler.set_retry_policy("test_type", policy)
    
    # We need to mock _should_retry or ensure logic allows it.
    # _should_retry defaults to True if no retryable_errors list or if error is in list.
    # And we need to make sure we don't actually sleep long.
    
    result = failure_handler.handle_step_failure(step, error)
    assert result["retry"] is True
    assert result["retry_delay"] == 0.0

# --- Test ParallelismManager ---

def test_parallelism_manager_execute_parallel(parallelism_manager):
    def task_func(x):
        return x * 2

    tasks = [
        Task("t1", task_func, args=(1,)),
        Task("t2", task_func, args=(2,))
    ]

    results = parallelism_manager.execute_parallel(tasks)
    assert len(results) == 2
    
    r1 = next(r for r in results if r.task_id == "t1")
    r2 = next(r for r in results if r.task_id == "t2")
    
    assert r1.success is True
    assert r1.result == 2
    assert r2.success is True
    assert r2.result == 4

def test_parallelism_manager_identify_parallelizable_steps(parallelism_manager, pipeline_builder):
    # s1 -> s2
    # s1 -> s3
    # s2, s3 can be parallel
    pipeline = (
        pipeline_builder
        .add_step("s1", "t1")
        .add_step("s2", "t2", dependencies=["s1"])
        .add_step("s3", "t3", dependencies=["s1"])
        .build()
    )
    
    groups = parallelism_manager.identify_parallelizable_steps(pipeline)
    # Expected groups: [ [s1], [s2, s3] ] (or similar structure depending on level calculation)
    # Level 0: s1
    # Level 1: s2, s3
    
    assert len(groups) == 2
    assert len(groups[0]) == 1
    assert groups[0][0].name == "s1"
    assert len(groups[1]) == 2
    names = {s.name for s in groups[1]}
    assert "s2" in names
    assert "s3" in names

# --- End-to-End Pipeline Orchestration Test ---

def test_end_to_end_pipeline_orchestration(pipeline_builder, execution_engine):
    # This simulates a complete pipeline orchestration workflow
    
    # Mocks for actual components to avoid file I/O and heavy processing
    file_ingestor_mock = MagicMock()
    file_ingestor_mock.ingest_file.return_value = MagicMock(path="dummy.pdf")
    
    document_parser_mock = MagicMock()
    document_parser_mock.parse_document.return_value = {"text": "Alice works at Tech Corp."}
    
    ner_extractor_mock = MagicMock()
    ner_entity = MagicMock()
    ner_entity.text = "Alice"
    ner_entity.label = "PERSON"
    ner_extractor_mock.extract_entities.return_value = [ner_entity]
    
    graph_builder_mock = MagicMock()
    graph_builder_mock.build.return_value = {"nodes": [{"id": "e0"}], "edges": []}
    
    # Handlers
    def ingest_handler(data, **config):
        files = data.get("files", [])
        if files:
            file_obj = file_ingestor_mock.ingest_file(files[0], read_content=True)
            return {**data, "file": file_obj}
        return data

    def parse_handler(data, **config):
        file_obj = data.get("file")
        if file_obj:
            parsed = document_parser_mock.parse_document(file_obj.path)
            text = parsed.get("text")
            return {**data, "text": text}
        return data

    def extract_handler(data, **config):
        text = data.get("text", "")
        entities = ner_extractor_mock.extract_entities(text)
        entity_dicts = [
            {"id": f"e{i}", "name": e.text, "type": e.label} for i, e in enumerate(entities)
        ]
        return {**data, "entities": entity_dicts}

    def build_graph_handler(data, **config):
        entities = data.get("entities", [])
        graph = graph_builder_mock.build({"entities": entities})
        return {**data, "graph": graph}

    # Build Pipeline
    pipeline = (
        pipeline_builder
        .add_step("ingest", "ingest", handler=ingest_handler)
        .add_step("parse", "parse", dependencies=["ingest"], handler=parse_handler)
        .add_step("extract", "extract", dependencies=["parse"], handler=extract_handler)
        .add_step("build_graph", "build_graph", dependencies=["extract"], handler=build_graph_handler)
        .build()
    )
    
    input_data = {
        "files": ["test.pdf"]
    }
    
    # Execute
    result = execution_engine.execute_pipeline(pipeline, input_data)
    
    assert result.success is True
    assert "graph" in result.output
    assert result.output["graph"]["nodes"][0]["id"] == "e0"
    
    # Verify failure handling configuration
    execution_engine.failure_handler.set_retry_policy(
        "extract",
        RetryPolicy(max_retries=3, backoff_factor=2.0, strategy=RetryStrategy.EXPONENTIAL)
    )
    policy = execution_engine.failure_handler.get_retry_policy("extract")
    assert policy.max_retries == 3
    
    # Verify parallelism identification
    parallelism = ParallelismManager(max_workers=4)
    groups = parallelism.identify_parallelizable_steps(pipeline)
    # This pipeline is sequential, so each group should have 1 step
    assert len(groups) == 4
    assert len(groups[0]) == 1

# --- Test PipelineTemplateManager ---

def test_template_manager_defaults(template_manager):
    templates = template_manager.list_templates()
    assert "document_processing" in templates
    assert "rag_pipeline" in templates
    assert "kg_construction" in templates
    assert "bug_bounty_hunting" in templates

def test_template_manager_get_template(template_manager):
    template = template_manager.get_template("document_processing")
    assert isinstance(template, PipelineTemplate)
    assert template.name == "document_processing"
    assert len(template.steps) > 0

def test_template_manager_create_pipeline(template_manager):
    builder = template_manager.create_pipeline_from_template(
        "document_processing",
        pipeline_config={"parallelism": 5},
        ingest={"source": "custom_source"}
    )
    pipeline = builder.build()
    
    assert pipeline.config["parallelism"] == 5
    
    # Check overrides
    ingest_step = next(s for s in pipeline.steps if s.name == "ingest")
    assert ingest_step.config["source"] == "custom_source"

def test_template_manager_register_template(template_manager):
    new_template = PipelineTemplate(
        name="custom_template",
        description="Custom Description",
        steps=[{"name": "step1", "type": "test"}]
    )
    template_manager.register_template(new_template)
    assert "custom_template" in template_manager.list_templates()
    
    info = template_manager.get_template_info("custom_template")
    assert info["name"] == "custom_template"
    assert info["step_count"] == 1

# --- Test PipelineValidator ---

def test_pipeline_validator_valid_structure(validator, pipeline_builder):
    pipeline = (
        pipeline_builder
        .add_step("step1", "type1")
        .add_step("step2", "type2", dependencies=["step1"])
        .build()
    )
    
    result = validator.validate_pipeline(pipeline)
    assert result.valid is True
    assert len(result.errors) == 0

def test_pipeline_validator_missing_dependency(validator, pipeline_builder):
    pipeline = (
        pipeline_builder
        .add_step("step1", "type1", dependencies=["missing_step"])
        .build()
    )
    
    result = validator.validate_pipeline(pipeline)
    assert result.valid is False
    assert any("missing step" in e for e in result.errors)

def test_pipeline_validator_circular_dependency(validator, pipeline_builder):
    pipeline = (
        pipeline_builder
        .add_step("step1", "type1", dependencies=["step2"])
        .add_step("step2", "type2", dependencies=["step1"])
        .build()
    )
    
    result = validator.validate_pipeline(pipeline)
    # The validator might catch this in check_dependencies
    assert result.valid is False
    assert any("Circular dependency" in e for e in result.errors)

def test_pipeline_validator_performance(validator, pipeline_builder):
    pipeline = pipeline_builder.add_step("s1", "t1").build()
    perf_result = validator.validate_performance(pipeline)
    assert perf_result["step_count"] == 1
    # Should be no warnings for simple pipeline
    assert len(perf_result["warnings"]) == 0

# --- Test ResourceScheduler ---

def test_resource_scheduler_initialization(resource_scheduler):
    usage = resource_scheduler.get_resource_usage()
    assert "cpu" in usage
    assert "memory" in usage
    assert usage["cpu"]["capacity"] > 0

def test_resource_scheduler_allocation(resource_scheduler, pipeline_builder):
    pipeline = pipeline_builder.add_step("s1", "t1").build("test_pipe")
    
    allocations = resource_scheduler.allocate_resources(
        pipeline,
        cpu_cores=1,
        memory_gb=0.1
    )
    
    assert "cpu" in allocations
    assert "memory" in allocations
    assert allocations["cpu"].amount == 1
    assert allocations["memory"].amount == 0.1
    
    # Check usage update
    usage = resource_scheduler.get_resource_usage()
    assert usage["cpu"]["allocated"] >= 1

def test_resource_scheduler_release(resource_scheduler, pipeline_builder):
    pipeline = pipeline_builder.add_step("s1", "t1").build("test_pipe")
    allocations = resource_scheduler.allocate_resources(
        pipeline,
        cpu_cores=1
    )
    
    assert allocations["cpu"].amount == 1
    
    resource_scheduler.release_resources(allocations)
    
    usage = resource_scheduler.get_resource_usage()
    # It might not be exactly 0 if other things are running, but should be less than before release if isolated.
    # Since we are in a fresh test fixture, allocated should be 0.
    assert usage["cpu"]["allocated"] == 0

def test_resource_scheduler_optimization(resource_scheduler, pipeline_builder):
    pipeline = (
        pipeline_builder
        .add_step("s1", "t1")
        .add_step("s2", "t2")
        .build("opt_pipe")
    )
    
    optimization = resource_scheduler.optimize_resource_allocation(pipeline)
    recs = optimization["recommendations"]
    assert recs["parallel_execution"] is True  # s1 and s2 are independent
    assert recs["cpu_cores"] >= 1
