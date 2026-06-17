---
title: "Utils Module"
description: "Shared utilities for logging, validation, error handling, progress tracking, and common operations."
icon: "wrench"
---

**`semantica.utils`** provides **shared infrastructure** used throughout Semantica:

- Structured logging: `setup_logging()`, `get_logger()`, `log_execution_time` decorator
- Validation helpers: `validate_entity()` and `validate_config()` return `(bool, Optional[str])` without raising
- Progress tracking: `ProgressTracker` class and `track_progress()` iterable wrapper with ETA
- Typed exceptions: `SemanticaError`, `ValidationError`, `ProcessingError`, `ConfigurationError`, `QualityError`

Most users won't call utils directly — it's the **shared foundation** for all modules.


## Exported Classes

| Name | Type | Role |
| :--- | :--- | :--- |
| `setup_logging` | function | Configure the `semantica` root logger — accepts `level`, `file`, `console`, `rotation` kwargs |
| `get_logger` | function | Get a named logger instance (`semantica.<name>`) |
| `log_execution_time` | decorator | Wraps a function — logs name, execution time, and success/failure |
| `log_performance` | function | Log pre-collected performance metrics: `log_performance(func_name, execution_time, **metrics)` |
| `validate_entity` | function | Validate entity dict — returns `(bool, Optional[str])`; does not raise |
| `validate_config` | function | Validate config dict — returns `(bool, Optional[str])`; does not raise |
| `ProgressTracker` | class | Class-based progress tracker with ETA and step callbacks |
| `track_progress` | function | Wrap any iterable with a live progress bar |
| `clean_text` | function | Normalize whitespace and strip zero-width control characters |
| `hash_data` | function | Deterministic SHA-256 hash of a `str`, `bytes`, or `dict` |
| `SemanticaError` | exception | Base exception for all Semantica errors |
| `ValidationError` | exception | Raised when input fails validation; has `.field`, `.value`, `.message` |
| `ProcessingError` | exception | Raised during extraction, graph build, or pipeline step; has `.stage` |
| `ConfigurationError` | exception | Raised for configuration validation failures |
| `QualityError` | exception | Raised when data quality falls below threshold |

## What You Get

<CardGroup cols={2}>
  <Card title="Logging" icon="scroll">
    Structured logging with `@log_execution_time` decorator and quality metrics via environment variables.
  </Card>
  <Card title="Validation" icon="shield-check">
    `validate_entity` and `validate_config` with a typed `ValidationError` carrying field and value context.
  </Card>
  <Card title="Progress Tracking" icon="bars-progress">
    `track_progress` wraps any iterable — auto-detects console vs Jupyter for the right renderer.
  </Card>
  <Card title="Helper Functions" icon="wrench">
    `clean_text`, `hash_data`, `safe_filename`, and nested dict utilities used throughout the framework.
  </Card>
  <Card title="Exception Hierarchy" icon="triangle-exclamation">
    `SemanticaError` → `ValidationError`, `ProcessingError` — typed exceptions for targeted recovery.
  </Card>
  <Card title="File Utilities" icon="file">
    `read_json_file` raises `FileNotFoundError` or `json.JSONDecodeError` on failure — no boilerplate try/except around JSON I/O.
  </Card>
</CardGroup>

## Logging

<Steps>
  <Step title="Initialize logging at application startup">
    ```python
    from semantica.utils import setup_logging, get_logger

    setup_logging(level="INFO")   # "DEBUG" | "INFO" | "WARNING" | "ERROR"
    logger = get_logger(__name__)
    ```
  </Step>
  <Step title="Instrument expensive functions with the performance decorator">
    ```python
    from semantica.utils import log_execution_time

    @log_execution_time
    def expensive_step(data):
        ...
    # Logs: "expensive_step completed in 2.34s"
    ```
  </Step>
  <Step title="Configure via environment variables">
    ```bash
    export SEMANTICA_LOG_LEVEL=DEBUG
    export SEMANTICA_LOG_FORMAT=json     # "json" | "text"
    export SEMANTICA_DISABLE_PROGRESS=true
    ```
  </Step>
</Steps>

## Validation

```python
from semantica.utils import validate_entity, validate_config, ValidationError

# validate_entity returns (is_valid, error_message)
is_valid, error = validate_entity({"id": "1", "type": "PERSON", "text": "Alice"})
if not is_valid:
    raise ValidationError(error)

# validate_config returns (is_valid, error_message)
is_valid, error = validate_config(config, required_keys=["model", "provider"])
if not is_valid:
    print(f"Invalid config: {error}")
```

| Function | Description | Returns |
| :-------- | :----------- | :------- |
| `validate_entity(data)` | Check entity dict has **required** fields (`id`, `text`, `type`) and correct types | `Tuple[bool, Optional[str]]` |
| `validate_config(cfg, required_keys=None)` | Check configuration dict; optionally enforce **required** keys | `Tuple[bool, Optional[str]]` |

## Progress Tracking

```python
from semantica.utils import track_progress

# Wraps any iterable — auto-detects console vs Jupyter
for item in track_progress(items, desc="Processing documents"):
    process(item)
```

Supports:
- **Console** — tqdm progress bar with ETA
- **Jupyter** — notebook-compatible widget (auto-detected)
- **File** — write progress to a log file

## Helper Functions

```python
from semantica.utils import clean_text, hash_data, safe_filename

# Normalize whitespace and strip control characters
clean = clean_text("  Hello   World  ")     # -> "Hello World"

# Deterministic SHA-256 hash of a string, bytes, or dict
uid   = hash_data({"key": "value"})         # -> hex digest string

# Sanitize a string for use as a filename
fname = safe_filename("My File?.txt")       # -> "My_File.txt"
```

## Nested Dict Utilities

Helper functions for deep configuration access — used extensively inside `Config` and `ConfigManager`:

```python
from semantica.utils import get_nested_value, set_nested_value, merge_dicts

config = {
    "processing": {"batch_size": 32, "max_workers": 4},
    "llm":        {"provider": "groq", "model": "llama-3.3-70b-versatile"},
}

# Dot-notation read — returns default if key path is absent
batch = get_nested_value(config, "processing.batch_size", default=16)
# -> 32

# Dot-notation write
set_nested_value(config, "processing.batch_size", 64)

# Deep merge — nested keys are merged recursively (deep=True by default)
base      = {"a": {"x": 1, "y": 2}, "b": 3}
overrides = {"a": {"y": 99, "z": 4}, "c": 5}
merged    = merge_dicts(base, overrides)
# -> {"a": {"x": 1, "y": 99, "z": 4}, "b": 3, "c": 5}
```

## Exception Hierarchy

<AccordionGroup>
  <Accordion title="Exception types and when they're raised">

```python
from semantica.utils import SemanticaError, ValidationError, ProcessingError

try:
    run_pipeline(data)
except ValidationError as e:
    # Input data did not pass schema validation
    logger.error("Validation failed: %s", e.message)
except ProcessingError as e:
    # Failure during extraction or graph construction
    logger.error("Processing failed at stage %s: %s", e.stage, e)
except SemanticaError as e:
    # Catch-all for all Semantica framework errors
    logger.error("Framework error: %s", e)
```

| Exception | When Raised | Key Attributes |
| :--------- | :----------- | :-------------- |
| `SemanticaError` | Base class — all framework errors inherit from this | `.message`, `.context`, `.error_code` |
| `ValidationError` | Input data failed schema or type validation | `.field`, `.value`, `.constraint` |
| `ProcessingError` | Failure during extraction, graph build, or pipeline step | `.stage`, `.input_data`, `.output_data` |
| `ConfigurationError` | Configuration key missing or wrong type | `.config_key`, `.config_value`, `.expected_type` |
| `QualityError` | Data quality score fell below threshold | `.quality_score`, `.threshold`, `.metrics` |

  </Accordion>
</AccordionGroup>

## File Utilities

```python
from semantica.utils import read_json_file

# Read and parse a JSON file — raises FileNotFoundError or json.JSONDecodeError on failure
config = read_json_file("config.json")
```

## Tips and Common Pitfalls

<Warning>
  **Call `setup_logging(level="INFO")` once at application startup.** Without it, Semantica falls back to Python's root logger, which may be silent or misconfigured. Call it before importing other Semantica modules to capture initialization messages.
</Warning>

<Tip>
  **`@log_execution_time` is the performance decorator.** Apply it to any function to automatically log its name, execution time, and success/failure. `log_performance` is a lower-level function for logging metrics you've already collected — it is not a decorator.
</Tip>

<Tip>
  **`hash_data()` is deterministic across runs.** Given the same input dict (any JSON-serializable object), `hash_data()` always returns the same SHA-256 hex string — suitable as a cache key or idempotency token in pipeline steps.
</Tip>

<Tip>
  **Catch `SemanticaError` as the broadest exception net.** All framework errors inherit from `SemanticaError`, so `except SemanticaError` catches validation failures, processing errors, and everything in between. Use specific subclasses for targeted recovery logic.
</Tip>

<Tip>
  **`track_progress` auto-detects Jupyter.** In a terminal it renders a tqdm progress bar; in a Jupyter notebook it renders an interactive widget. You don't need to check the environment — the same call works in both.
</Tip>

<CardGroup cols={2}>
  <Card title="Core" icon="gear" href="core">
    Framework orchestration that uses Utils internally.
  </Card>
  <Card title="Pipeline" icon="arrows-turn-to-dots" href="pipeline">
    Uses ProgressTracker for per-step tracking.
  </Card>
</CardGroup>
