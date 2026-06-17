---
title: "Pipeline Module"
description: "Pipeline DSL with parallel workers, retry policies, failure handling, and progress tracking."
icon: "gear"
---

**`semantica.pipeline`** lets you chain Semantica components into **reproducible, fault-tolerant workflows**:

- Per-step failure strategies: `skip`, `retry`, `abort`, or `fallback`
- Parallel workers via `ParallelismManager`: thread or process pool
- `PipelineValidator` catches cycles, missing handlers, and config errors before running
- Pre-built templates: `"document_processing"`, `"rag_pipeline"`, `"kg_construction"`, `"ontology_generation"`
- Pipelines are serializable to YAML: save and reload in any environment


## Exported Classes

| Class | Role |
| :--- | :--- |
| `PipelineBuilder` | DSL for wiring steps: `add_step`, `connect_steps`, `set_parallel`, `build` |
| `ExecutionEngine` | Runs a built pipeline: `execute_pipeline(pipeline, data)` → `ExecutionResult` |
| `ExecutionResult` | `{success, output, metadata, metrics, errors}`: full run summary |
| `FailureHandler` | Per-step strategy: `skip`, `retry`, `abort`, or `fallback` on failure |
| `ParallelismManager` | Thread or process pool for concurrent step execution with configurable workers |
| `PipelineValidator` | Catches dependency cycles, missing handlers, and config errors before running |
| `PipelineTemplateManager` | Pre-built templates: `"document_processing"`, `"rag_pipeline"`, `"kg_construction"`, `"ontology_generation"` |

## Why Use a Pipeline?

You could wire Semantica modules together with plain Python code. Pipelines add:

<CardGroup cols={2}>
  <Card title="Retry and failure handling" icon="arrow-rotate-right">
    A single bad document doesn't crash a 10,000-document run.
  </Card>
  <Card title="Parallelism" icon="bolt">
    Run extraction across multiple workers with one parameter.
  </Card>
  <Card title="Progress tracking" icon="chart-line">
    tqdm console bar or WebSocket streaming to Explorer.
  </Card>
  <Card title="Reproducibility" icon="floppy-disk">
    Save the exact pipeline configuration to YAML and replay on any machine.
  </Card>
  <Card title="Delta mode" icon="code-compare">
    On re-runs, only process documents that changed since the last run.
  </Card>
  <Card title="Validation" icon="shield-check">
    Catch misconfigured steps and dependency cycles before they fail mid-run.
  </Card>
</CardGroup>

<Note>
  Use plain module calls for quick scripts and notebooks. Use pipelines for anything you run repeatedly, at scale, or in production.
</Note>

<img src="/assets/img/diagrams/pipeline-flow.svg" alt="Pipeline step sequence: Ingest → Parse → Normalize → Extract → Build KG → QA → Store → Deliver" style={{ width: '100%', borderRadius: '10px', margin: '0 0 24px' }} />

## Quick Start

<Steps>
  <Step title="Build a pipeline">
    ```python
    from semantica.pipeline import PipelineBuilder
    from semantica.ingest import FileIngestor
    from semantica.parse import DocumentParser
    from semantica.semantic_extract import NERExtractor
    from semantica.kg import GraphBuilder

    ingestor   = FileIngestor()
    parser     = DocumentParser()
    extractor  = NERExtractor(method="ml")
    kg_builder = GraphBuilder(merge_entities=True)

    builder = PipelineBuilder()
    builder.add_step("ingest",   "file_ingest",    handler=ingestor.ingest_file)
    builder.add_step("parse",    "document_parse", handler=parser.parse)
    builder.add_step("extract",  "ner_extract",    handler=extractor.extract)
    builder.add_step("build_kg", "graph_build",    handler=kg_builder.build)
    builder.connect_steps("ingest", "parse")
    builder.connect_steps("parse",  "extract")
    builder.connect_steps("extract","build_kg")

    pipeline = builder.build("my_pipeline")
    ```
  </Step>
  <Step title="Validate before running">
    ```python
    from semantica.pipeline import PipelineValidator

    validator = PipelineValidator()
    result = validator.validate_pipeline(pipeline)

    if not result.valid:
        for error in result.errors:   # errors is List[str]
            print(f"Error: {error}")
        for warning in result.warnings:
            print(f"Warning: {warning}")
    ```
  </Step>
  <Step title="Execute and inspect results">
    ```python
    from semantica.pipeline import ExecutionEngine

    engine = ExecutionEngine()
    result = engine.execute_pipeline(pipeline, data="data/")

    kg = result.output
    print(f"Success:        {result.success}")
    print(f"Steps executed: {result.metrics['steps_executed']}")
    print(f"Steps failed:   {result.metrics['steps_failed']}")
    print(f"Duration:       {result.metrics['execution_time']:.1f}s")
    ```
  </Step>
</Steps>

## Parallel Processing

Set parallelism on the builder and pass `max_workers` to `ExecutionEngine`:

```python
from semantica.pipeline import PipelineBuilder, ExecutionEngine

builder = PipelineBuilder()
builder.add_step("ingest",  "file_ingest",    handler=ingestor.ingest_file)
builder.add_step("parse",   "document_parse", handler=parser.parse)
builder.add_step("extract", "ner_extract",    handler=extractor.extract)
builder.add_step("build",   "graph_build",    handler=kg_builder.build)
builder.set_parallelism(4)

pipeline = builder.build("parallel_pipeline")
engine   = ExecutionEngine(max_workers=4)
result   = engine.execute_pipeline(pipeline, data="data/")
```

## Retry and Error Handling

<Tabs>
  <Tab title="Exponential backoff (recommended)">
    ```python
    from semantica.pipeline import RetryPolicy, RetryStrategy, FailureHandler, ExecutionEngine

    policy = RetryPolicy(
        max_retries=3,
        strategy=RetryStrategy.EXPONENTIAL,
        initial_delay=1.0,    # 1s → 2s → 4s
        backoff_factor=2.0
    )

    handler = FailureHandler()
    handler.set_retry_policy("ner_extract", policy)   # keyed by step_type

    engine = ExecutionEngine(default_max_retries=3, default_backoff_factor=2.0)
    result = engine.execute_pipeline(pipeline, data="data/")
    ```

    Best for transient API errors and rate limits: waits longer with each retry, giving upstream services time to recover.
  </Tab>
  <Tab title="Linear backoff">
    ```python
    from semantica.pipeline import RetryPolicy, RetryStrategy

    policy = RetryPolicy(
        max_retries=3,
        strategy=RetryStrategy.LINEAR,
        initial_delay=2.0    # 2s → 4s → 6s
    )
    ```

    Use when the delay between retries should grow predictably: e.g., waiting for a database lock to release.
  </Tab>
  <Tab title="Fixed backoff">
    ```python
    from semantica.pipeline import RetryPolicy, RetryStrategy

    policy = RetryPolicy(
        max_retries=5,
        strategy=RetryStrategy.FIXED,
        initial_delay=1.0    # 1s every attempt
    )
    ```

    Use when retrying against a service with a fixed cooldown window.
  </Tab>
</Tabs>

### Failure Strategies

| Strategy | Behaviour | When to Use |
| :-------- | :--------- | :----------- |
| `"skip"` | Log failure, continue to next document | Production: one bad doc shouldn't stop 10k |
| `"stop"` | Raise exception immediately | Development: surface errors fast |
| `"retry"` | Retry via `RetryPolicy`, then skip | When failures are likely transient |

<Warning>
  In production, configure a `RetryPolicy` with limited retries so a single failing step does not stop the whole run. After execution, inspect `result.errors` to find and reprocess failed documents.
</Warning>

## Progress Tracking

<Tabs>
  <Tab title="Console (tqdm)">
    ```python
    from semantica.pipeline import ExecutionEngine

    engine = ExecutionEngine()
    result = engine.execute_pipeline(pipeline, data="data/")
    # The progress tracker outputs tqdm bars to the console during execution
    ```

    Displays a live progress bar in the terminal via Semantica's built-in progress tracker. Best for scripts and CLI tools.
  </Tab>
  <Tab title="Live status check">
    ```python
    from semantica.pipeline import ExecutionEngine
    import threading, time

    engine = ExecutionEngine()

    # Run in a background thread, poll progress from main thread
    def run():
        engine.execute_pipeline(pipeline, data="data/")

    t = threading.Thread(target=run, daemon=True)
    t.start()

    while t.is_alive():
        progress = engine.get_progress(pipeline.name)
        if progress:
            print(f"  {progress['completed_steps']}/{progress['total_steps']} steps: {progress['status']}")
        time.sleep(2)
    ```

    Poll `get_progress()` for live status during execution.
  </Tab>
</Tabs>

## Pipeline DSL

`PipelineBuilder` uses `add_step(name, type, **config)` and `connect_steps(from, to)` to define a DAG:

```python
from semantica.pipeline import PipelineBuilder, ExecutionEngine

builder = PipelineBuilder()

# Add steps: step_type is a string label, handler is the callable invoked at runtime
builder.add_step("ingest",      "file_ingest",    handler=ingestor.ingest_file)
builder.add_step("parse",       "document_parse", handler=parser.parse)
builder.add_step("normalize",   "text_normalize", handler=normalizer.normalize)
builder.add_step("extract",     "ner_extract",    handler=extractor.extract)
builder.add_step("rel_extract", "rel_extract",    handler=rel_extractor.extract)
builder.add_step("build_kg",    "graph_build",    handler=kg_builder.build)
builder.add_step("deduplicate", "dedup",          handler=deduplicator.deduplicate)
builder.add_step("export",      "rdf_export",     handler=exporter.export, format="turtle", path="output.ttl")

# Wire the data flow
builder.connect_steps("ingest",      "parse")
builder.connect_steps("parse",       "normalize")
builder.connect_steps("normalize",   "extract")
builder.connect_steps("extract",     "rel_extract")
builder.connect_steps("rel_extract", "build_kg")
builder.connect_steps("build_kg",    "deduplicate")
builder.connect_steps("deduplicate", "export")

pipeline = builder.build("full_pipeline")
result   = ExecutionEngine().execute_pipeline(pipeline, data="data/")
```

## Serialize and Restore Pipelines

`PipelineSerializer` converts a pipeline to JSON or dict for storage and reloads it later:

```python
from semantica.pipeline import PipelineSerializer

serializer = PipelineSerializer()

# Serialize to JSON string
json_str = serializer.serialize_pipeline(pipeline, format="json")

# Save to file
with open("pipeline_config.json", "w") as f:
    f.write(json_str)

# Restore on any machine and execute
with open("pipeline_config.json") as f:
    restored = serializer.deserialize_pipeline(f.read())

result = ExecutionEngine().execute_pipeline(restored, data="data/")
```

<Tip>
  Serialized pipelines capture step names, types, and config: but not handler functions (callables can't be serialized). Re-register handlers on the restored steps before executing.
</Tip>

## Pre-Built Templates

`PipelineTemplateManager` wires common workflows with the correct step order: no manual wiring required:

```python
from semantica.pipeline import PipelineTemplateManager

manager = PipelineTemplateManager()
```

The `create_pipeline_from_template(name)` method returns a configured `PipelineBuilder`. Call `.build(pipeline_name)` on it to produce a runnable `Pipeline`.

<CardGroup cols={2}>
  <Card title="document_processing" icon="diagram-project">
    **Ingest → Parse → Normalize → Extract → Embed → Build KG**

    Complete document processing from ingestion to knowledge graph.

    ```python
    builder  = manager.create_pipeline_from_template("document_processing")
    pipeline = builder.build("doc_pipeline")
    ```
  </Card>
  <Card title="rag_pipeline" icon="magnifying-glass">
    **Ingest → Chunk → Embed → Store Vectors**

    RAG pipeline for question answering: builds a vector-indexed store.

    ```python
    builder  = manager.create_pipeline_from_template("rag_pipeline")
    pipeline = builder.build("rag_pipeline")
    ```
  </Card>
  <Card title="kg_construction" icon="chart-bar">
    **Ingest → Extract Entities → Extract Relations → Dedup → Resolve → Build Graph**

    Knowledge graph construction from multiple sources.

    ```python
    builder  = manager.create_pipeline_from_template("kg_construction")
    pipeline = builder.build("kg_pipeline")
    ```
  </Card>
  <Card title="ontology_generation" icon="shield-check">
    **Extract Concepts → Infer Classes → Infer Properties → Generate OWL → Validate**

    Ontology generation from extracted data.

    ```python
    builder  = manager.create_pipeline_from_template("ontology_generation")
    pipeline = builder.build("ontology_pipeline")
    ```
  </Card>
</CardGroup>

## ExecutionEngine

Fine-grained control over pipeline execution: pause, resume, cancel, and inspect live progress:

```python
from semantica.pipeline import ExecutionEngine

engine = ExecutionEngine(max_workers=4)

# pipeline.name is the pipeline ID used for all control operations
result = engine.execute_pipeline(pipeline, data="data/")

pipeline_id = pipeline.name   # e.g. "my_pipeline"

# Pause after the current step finishes
engine.pause_pipeline(pipeline_id)

progress = engine.get_progress(pipeline_id)
print(f"Completed: {progress['completed_steps']}/{progress['total_steps']}")
print(f"Status: {progress['status']}")

engine.resume_pipeline(pipeline_id)
engine.stop_pipeline(pipeline_id)
```

| Method | Returns | Description |
| :------ | :------- | :----------- |
| `execute_pipeline(pipeline, data)` | `ExecutionResult` | Execute pipeline from start to finish |
| `get_pipeline_status(pipeline_id)` | `PipelineStatus` | Current state (RUNNING, PAUSED, STOPPED) |
| `get_progress(pipeline_id)` | `Dict` | `completed_steps`, `total_steps`, `progress_percentage`, `status` |
| `pause_pipeline(pipeline_id)` | `None` | Suspend after current step completes |
| `resume_pipeline(pipeline_id)` | `None` | Resume from paused state |
| `stop_pipeline(pipeline_id)` | `None` | Cancel and clean up immediately |

## PipelineValidator

Catches problems before they surface as mid-run failures:

```python
from semantica.pipeline import PipelineValidator

validator = PipelineValidator()
result    = validator.validate_pipeline(pipeline)

if result.valid:
    print("Pipeline is valid: safe to run")
else:
    for error in result.errors:     # errors is List[str]
        print(f"Error: {error}")
    for warning in result.warnings: # warnings is List[str]
        print(f"Warning: {warning}")
```

Checks performed:
- **Dependency cycle detection**: A depends on B, B depends on A
- **Step type validation**: each step type must be registered
- **Connection integrity**: referenced step names must exist
- **Configuration completeness**: required parameters must be present

## ParallelismManager

<Tabs>
  <Tab title="Thread pool (I/O-bound)">
    ```python
    from semantica.pipeline import ParallelismManager, Task

    # use_processes=False (default) → thread pool for I/O-bound tasks
    manager = ParallelismManager(max_workers=8, use_processes=False)

    tasks   = [Task(task_id=f"t{i}", handler=ner.extract, args=(text,)) for i, text in enumerate(texts)]
    results = manager.execute_parallel(tasks)
    # returns List[ParallelExecutionResult]

    successes = [r for r in results if r.success]
    failures  = [r for r in results if not r.success]
    ```

    Use thread pools for **I/O-bound** steps: web fetching, database queries, API calls.
  </Tab>
  <Tab title="Process pool (CPU-bound)">
    ```python
    from semantica.pipeline import ParallelismManager, Task

    # use_processes=True → process pool, bypasses Python GIL
    manager = ParallelismManager(max_workers=4, use_processes=True)

    tasks   = [Task(task_id=f"t{i}", handler=embedder.generate_embeddings, args=(chunk,)) for i, chunk in enumerate(chunks)]
    results = manager.execute_parallel(tasks)
    ```

    Use process pools for **CPU-bound** steps: embedding, OCR, large NER batches.
  </Tab>
</Tabs>

## ResourceScheduler

Prevents memory oversubscription on large runs:

```python
from semantica.pipeline import ResourceScheduler, ExecutionEngine

scheduler = ResourceScheduler()
engine    = ExecutionEngine()

resources = scheduler.allocate_resources(pipeline)

try:
    result = engine.execute_pipeline(pipeline, data="data/")
finally:
    scheduler.release_resources(resources)
```

## Delta Mode

Re-process only data that has changed since the last run:

```python
from semantica.pipeline import PipelineBuilder, ExecutionEngine

builder = PipelineBuilder()

# delta_mode=True tells ExecutionEngine to compute the diff between two snapshots
# and pass only changed triples to this step's handler
builder.add_step(
    "ingest",  "file_ingest",
    handler=ingestor.ingest_file,
    delta_mode=True, base_version_id="v1", target_version_id="v2"
)
builder.add_step(
    "extract", "ner_extract",
    handler=extractor.extract,
    delta_mode=True, base_version_id="v1", target_version_id="v2"
)
builder.add_step(
    "build", "graph_build",
    handler=kg_builder.build,
    delta_mode=False  # always rebuild the merged graph
)
builder.connect_steps("ingest", "extract")
builder.connect_steps("extract", "build")

pipeline = builder.build("delta_pipeline")
engine   = ExecutionEngine()
result   = engine.execute_pipeline(
    pipeline,
    data="data/",
    version_manager=version_manager,   # required for delta mode
    triplet_store=triplet_store        # required for delta mode
)
```

<Note>
  Delta detection uses SHA-256 checksums on source content. Only sources whose checksum differs from `base_version_id` are passed to downstream steps. For pipelines that run hourly or daily against a growing corpus, delta mode eliminates redundant re-embedding and re-extraction.
</Note>

## Schemas

<AccordionGroup>
  <Accordion title="ExecutionResult schema">

```python
@dataclass
class ExecutionResult:
    success:  bool            # True if all steps completed without failure
    output:   Any             # output from the final pipeline step
    metadata: Dict[str, Any]  # {"pipeline_id": "...", "execution_time": 1.23}
    metrics:  Dict[str, Any]  # {"steps_executed": 4, "steps_failed": 0, "execution_time": 1.23}
    errors:   List[str]       # error messages from failed steps (empty on full success)

# Access pattern
result.success                       # bool
result.output                        # final step output
result.metadata["pipeline_id"]       # pipeline name used as ID
result.metadata["execution_time"]    # total wall-clock seconds
result.metrics["steps_executed"]     # count of successfully completed steps
result.metrics["steps_failed"]       # count of failed steps
result.errors                        # List[str] of error messages
```

  </Accordion>
  <Accordion title="PipelineStep schema">

```python
@dataclass
class PipelineStep:
    name:              str
    step_type:         str
    config:            Dict[str, Any]
    dependencies:      List[str]          # names of steps this step waits for
    handler:           Optional[Callable]
    status:            StepStatus
    result:            Any
    error:             Optional[Exception]
    delta_mode:        bool               # True = process only changed data
    base_version_id:   Optional[str]     # snapshot ID to diff against
    target_version_id: Optional[str]     # snapshot ID being produced
```

  </Accordion>
  <Accordion title="StepStatus enum">

```python
from semantica.pipeline import StepStatus

StepStatus.PENDING    # Not yet started
StepStatus.RUNNING    # Currently executing
StepStatus.COMPLETED  # Finished successfully
StepStatus.FAILED     # Error occurred: check step.error
StepStatus.SKIPPED    # Skipped due to FailureHandler "skip" strategy
```

  </Accordion>
</AccordionGroup>

## Tips and Common Pitfalls

<Tip>
  **Use `PipelineValidator` before running in production.** It catches dependency cycles, missing step names, and misconfigured connections that would only surface as errors mid-run. Validation is instant; catching them after a 30-minute extraction job is not.
</Tip>

<Tip>
  **Set `workers=` based on workload type.** Thread workers for I/O-bound steps (web fetching, DB queries), process workers for CPU-bound steps (embedding, OCR, large NER batches). Mixing pool types on the wrong step type wastes resources without speed gains.
</Tip>

<Warning>
  **Configure retry policies to contain failures in production.** Use `handler.set_retry_policy("step_type", RetryPolicy(max_retries=3))` so transient errors are retried without stopping the pipeline. After the run, inspect `result.errors` to find and reprocess any documents that exhausted retries.
</Warning>

<Tip>
  **Use templates from `PipelineTemplateManager` for common patterns.** `create_pipeline_from_template("kg_construction")` wires normalization, deduplication, conflict detection, and graph construction in the correct order: saving you from common mistakes like deduplicating before normalizing.
</Tip>

<Tip>
  **Inspect `result.metrics` to find bottlenecks.** `result.metrics['steps_executed']` and `result.metrics['execution_time']` give a quick read on overall pipeline health. For per-step timing, check `step.result` on each `PipelineStep` after the run.
</Tip>

<CardGroup cols={2}>
  <Card title="Ingest" icon="database" href="ingest">
    First step in most pipelines.
  </Card>
  <Card title="Semantic Extract" icon="magnifying-glass" href="semantic_extract">
    Core extraction step.
  </Card>
  <Card title="Knowledge Graph" icon="diagram-project" href="kg">
    Graph construction step.
  </Card>
  <Card title="Export" icon="file-export" href="export">
    Final output step.
  </Card>
</CardGroup>
