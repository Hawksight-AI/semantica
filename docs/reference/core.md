---
title: "Core Module"
description: "Framework orchestration, lifecycle management, configuration, and plugin system."
icon: "gear"
---

**`semantica.core`** is the **coordination layer** for the framework:

- `Semantica` orchestrator coordinates the full KG construction pipeline from a YAML config
- `ConfigManager` loads YAML config with deep-merge, validation, and environment variable overrides
- `PluginRegistry` enables dynamic component registration and loading at runtime
- `LifecycleManager` manages startup/shutdown with health monitoring and lifecycle hooks

<Tip>
  Use individual modules directly for the vast majority of use cases. Reach for `semantica.core` only when you need application-level lifecycle management, centralized config, or a plugin system.
</Tip>


## What You Get

- **Semantica** — High-level orchestrator: coordinates the full KG construction pipeline from a single `config.yaml`. Entry point for application-level deployments.
- **ConfigManager** — YAML config with deep-merge, `SEMANTICA_` env var overrides, and dot-notation nested key access. Keeps secrets out of source files.
- **LifecycleManager** — Ordered startup/shutdown hooks, health monitoring, and a 6-state machine. Essential for long-running services like FastAPI apps.
- **PluginRegistry** — Register custom ingestors, parsers, exporters, or any component. Load them by name at runtime: no imports required.

## Exported Classes

| Class | Role |
| :--- | :--- |
| `Semantica` | Orchestration entry point: coordinates the full KG construction pipeline |
| `ConfigManager` | YAML config loading, deep-merge, validation, and env var overrides |
| `LifecycleManager` | Startup/shutdown state machine with health monitoring and lifecycle hooks |
| `PluginRegistry` | Dynamic plugin discovery, registration, and loading |
| `method_registry` | Global `MethodRegistry` instance: register and dispatch custom orchestration methods |


## Semantica (Orchestration)

**`Semantica`** is the high-level entry point that coordinates the **full KG construction pipeline**:

```python
from semantica.core import Semantica, ConfigManager

config_manager = ConfigManager()
config = config_manager.load_from_file("config.yaml")

framework = Semantica(config=config)
framework.initialize()

try:
    result = framework.build_knowledge_base(
        sources=["doc1.pdf", "doc2.docx"],
        embeddings=True,
        graph=True,
    )
    status = framework.get_status()
    print(f"State: {status['state']}")
finally:
    framework.shutdown(graceful=True)
```

### Core Methods

| Method | Description |
| :------ | :----------- |
| `initialize()` | Initialize all framework components |
| `build_knowledge_base(sources, **kwargs)` | Orchestrate full KG construction pipeline |
| `run_pipeline(pipeline, data)` | Execute an existing `Pipeline` instance |
| `get_status()` | Return system health and current state |
| `shutdown(graceful=True)` | Graceful shutdown: waits for in-flight operations |

## ConfigManager

Centralized config loading with deep-merge and environment variable overrides:

```python
from semantica.core import ConfigManager

manager = ConfigManager()
config = manager.load_from_file("config.yaml")

# Merge base config with environment-specific overrides
merged = manager.merge_configs(
    manager.load_from_file("base.yaml"),
    manager.load_from_file("prod.yaml"),
)

# Nested key access with dot notation
batch_size = config.get("processing.batch_size", default=16)
config.set("processing.batch_size", 64)
config.validate()
```

### YAML Configuration

```yaml
llm_provider:
  name: openai
  model: gpt-4o
  # Do not put API keys in YAML: use environment variables instead.
  # ConfigManager loads YAML with yaml.safe_load(), which does not
  # interpolate ${...} expressions. Set secrets via env vars (see below).

processing:
  batch_size: 32
  max_workers: 4

quality:
  min_confidence: 0.7

logging:
  level: INFO
```

Environment variable overrides (prefix `SEMANTICA_`):

Use double underscores (`__`) to produce a dot separator for nested key access. The implementation strips the `SEMANTICA_` prefix, lowercases the result, and replaces `__` with `.` before calling `set_nested_value()` on the config dict.

```bash
# Double underscores map to nested keys:
export SEMANTICA_LLM_PROVIDER__MODEL=gpt-4o
export SEMANTICA_LLM_PROVIDER__NAME=openai
export SEMANTICA_PROCESSING__BATCH_SIZE=64
export SEMANTICA_QUALITY__MIN_CONFIDENCE=0.8
export SEMANTICA_LOGGING__LEVEL=DEBUG
```

## LifecycleManager

Manages framework state with a defined state machine and ordered startup/shutdown hooks:

**State machine:** `UNINITIALIZED` → `INITIALIZING` → `READY` → `RUNNING` → `STOPPING` → `STOPPED`

```python
from semantica.core import LifecycleManager

manager = LifecycleManager()

def init_db():
    print("Initializing database...")

def cleanup_db():
    print("Closing database connections...")

# Lower priority values run first during startup
# Higher priority values run first during shutdown
manager.register_startup_hook(init_db,     priority=10)
manager.register_shutdown_hook(cleanup_db, priority=10)

manager.startup()

# Component health monitoring
class DatabaseComponent:
    def health_check(self):
        return {"healthy": True, "message": "Connected"}

manager.register_component("database", DatabaseComponent())
summary = manager.get_health_summary()
# → {
#     "state": "ready",
#     "is_healthy": True,
#     "total_components": 1,
#     "healthy_components": 1,
#     "unhealthy_components": 0,
#     "last_check": 1234567890.0,
#     "components": {
#         "database": {"healthy": True, "message": "Connected", "timestamp": ...}
#     }
#   }

manager.shutdown(graceful=True)
```

## PluginRegistry

Register custom components that participate in the full pipeline: provenance tracking, retry policies, and parallel execution included:

```python
from semantica.core import PluginRegistry

class MyPlugin:
    def initialize(self):
        print("Plugin initialized")

    def execute(self, data):
        return {"processed": True}

registry = PluginRegistry(plugin_paths=["./plugins"])
registry.register_plugin("my_plugin", MyPlugin, version="1.0.0")

plugin = registry.load_plugin("my_plugin", api_key="xxx")
result = plugin.execute("sample data")

for info in registry.list_plugins():
    print(f"{info['name']}: {info['version']}")
```

## MethodRegistry

Register custom orchestration methods and dispatch them by name:

```python
from semantica.core import method_registry
from semantica.core.methods import build_knowledge_base

def fast_kb_builder(sources, **kwargs):
    # Custom logic: skip embeddings for speed
    ...

method_registry.register("knowledge_base", "fast", fast_kb_builder)

result = build_knowledge_base(sources=["doc.pdf"], method="fast")
```

## When to Use Core vs. Individual Modules

| Scenario | Recommended Approach |
| :-------- | :-------------------- |
| Single extraction task | `from semantica.semantic_extract import NERExtractor` |
| Build a knowledge graph | `from semantica.kg import GraphBuilder` |
| Multi-step pipeline | `from semantica.pipeline import Pipeline` |
| App-level lifecycle + config | `from semantica.core import Semantica, ConfigManager` |
| Custom dispatch / plugins | `from semantica.core import method_registry, PluginRegistry` |

<Tip>
  Use `Semantica` and `LifecycleManager` only when building a long-running application (e.g. a FastAPI service) that needs ordered startup, health checks, and graceful shutdown. For scripts and notebooks, use individual modules directly.
</Tip>

- [Pipeline](pipeline) — Pipeline execution and step orchestration.
- [Utils](utils) — Shared utilities used by Core internally.
- [Getting Started](../getting-started) — Learn the basics before using Core.
- [LLMs](llms) — Configure LLM providers via ConfigManager.
