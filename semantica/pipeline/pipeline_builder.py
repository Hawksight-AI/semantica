"""
Pipeline Construction Module

This module handles construction and configuration of processing pipelines, providing
a fluent DSL for building workflows, step chaining, validation, and serialization.

Key Features:
    - Pipeline construction DSL
    - Step configuration and chaining
    - Pipeline validation and optimization
    - Error handling and recovery
    - Pipeline serialization and deserialization
    - Dependency management
    - Step status tracking

Main Classes:
    - PipelineBuilder: Pipeline construction DSL
    - Pipeline: Pipeline definition dataclass
    - PipelineStep: Pipeline step definition dataclass
    - StepStatus: Enum for step status
    - PipelineSerializer: Pipeline serialization utility

Example Usage:
    >>> from semantica.pipeline import PipelineBuilder
    >>> builder = PipelineBuilder()
    >>> pipeline = builder.add_step("ingest", "file_ingest").add_step("parse", "document_parse").build()
    >>> serialized = builder.serialize(pipeline)

Author: Semantica Contributors
License: MIT
"""

from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Callable, Dict, List, Optional, Union, TYPE_CHECKING

from ..utils.exceptions import ProcessingError, ValidationError
from ..utils.logging import get_logger
from ..utils.progress_tracker import get_progress_tracker

if TYPE_CHECKING:
    from .pipeline_validator import PipelineValidator


class StepStatus(Enum):
    """Pipeline step status."""

    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    SKIPPED = "skipped"


@dataclass
class PipelineStep:
    """Pipeline step definition."""

    name: str
    step_type: str
    config: Dict[str, Any] = field(default_factory=dict)
    dependencies: List[str] = field(default_factory=list)
    handler: Optional[Callable] = None
    status: StepStatus = StepStatus.PENDING
    result: Any = None
    error: Optional[Exception] = None
    delta_mode: bool = False
    base_version_id: Optional[str] = None
    target_version_id: Optional[str] = None
    parallel_safe: bool = False


@dataclass
class Pipeline:
    """Pipeline definition."""

    name: str
    steps: List[PipelineStep] = field(default_factory=list)
    config: Dict[str, Any] = field(default_factory=dict)
    metadata: Dict[str, Any] = field(default_factory=dict)


class PipelineBuilder:
    """
    Pipeline construction and configuration handler.

    • Constructs processing pipelines using DSL
    • Configures pipeline steps and connections
    • Validates pipeline structure and dependencies
    • Optimizes pipeline performance
    • Handles pipeline serialization
    • Supports complex pipeline topologies
    """

    def __init__(self, config=None, **kwargs):
        """
        Initialize pipeline builder.

        Args:
            config: Configuration dictionary
            **kwargs: Additional configuration options
        """
        self.logger = get_logger("pipeline_builder")
        self.config = config or {}
        self.config.update(kwargs)

        # Initialize progress tracker
        self.progress_tracker = get_progress_tracker()
        # Ensure progress tracker is enabled
        if not self.progress_tracker.enabled:
            self.progress_tracker.enabled = True

        from .pipeline_validator import PipelineValidator

        self.validator = PipelineValidator(**self.config)
        self.steps: List[PipelineStep] = []
        self.step_registry: Dict[str, Callable] = {}
        self.pipeline_config: Dict[str, Any] = {}

    def add_step(self, step_name: str, step_type: str, **config) -> "PipelineStep":
        """
        Add step to pipeline.

        Args:
            step_name: Step name/identifier
            step_type: Step type/category
            **config: Step configuration

        Returns:
            Created PipelineStep object
        """
        delta_mode = config.pop("delta_mode", False)
        base_version_id = config.pop("base_version_id", None)
        target_version_id = config.pop("target_version_id", None)
        dependencies = config.pop("dependencies", [])
        handler = config.pop("handler", None)
        parallel_safe = config.pop("parallel_safe", False)
        if not isinstance(parallel_safe, bool):
            raise ValidationError(
                f"parallel_safe must be a boolean, got "
                f"{type(parallel_safe).__name__} for step '{step_name}'"
            )
        if handler is None:
            handler = self.step_registry.get(step_type)

        step = PipelineStep(
            name=step_name,
            step_type=step_type,
            config=config,
            dependencies=dependencies,
            handler=handler,
            delta_mode = delta_mode,
            base_version_id=base_version_id,
            target_version_id=target_version_id,
            parallel_safe=parallel_safe,
        )

        self.steps.append(step)
        self.logger.debug(f"Added step: {step_name} ({step_type}) | Delta Mode: {delta_mode}")

        return step

    def connect_steps(
        self, from_step: str, to_step: str, **options
    ) -> "PipelineBuilder":
        """
        Connect pipeline steps.

        Args:
            from_step: Source step name
            to_step: Target step name
            **options: Connection options

        Returns:
            Self for method chaining
        """
        # Find target step and add dependency
        target_step = next((s for s in self.steps if s.name == to_step), None)
        if target_step:
            if from_step not in target_step.dependencies:
                target_step.dependencies.append(from_step)
        else:
            raise ValidationError(f"Target step not found: {to_step}")

        return self

    def set_parallelism(self, level: int) -> "PipelineBuilder":
        """
        Set parallelism level.

        Args:
            level: Parallelism level (number of parallel workers)

        Returns:
            Self for method chaining
        """
        if (
            isinstance(level, bool)
            or not isinstance(level, int)
            or level <= 0
        ):
            raise ValidationError(
                f"Parallelism level must be a positive integer, got {level!r}"
            )
        self.pipeline_config["parallelism"] = level
        return self

    def build(self, name: str = "default_pipeline") -> Pipeline:
        """
        Build pipeline from configuration.

        Args:
            name: Pipeline name

        Returns:
            Built pipeline
        """
        tracking_id = self.progress_tracker.start_tracking(
            module="pipeline",
            submodule="PipelineBuilder",
            message=f"Building pipeline: {name}",
        )

        try:
            # Validate pipeline structure
            self.progress_tracker.update_tracking(
                tracking_id, message="Validating pipeline structure..."
            )
            validation_result = self.validator.validate_pipeline(self)
            if not validation_result.valid:
                errors = validation_result.errors
                raise ValidationError(f"Pipeline validation failed: {errors}")

            self.progress_tracker.update_tracking(
                tracking_id, message="Creating pipeline object..."
            )
            pipeline = Pipeline(
                name=name,
                steps=list(self.steps),
                config=self.pipeline_config,
                metadata={
                    "step_count": len(self.steps),
                    "parallelism": self.pipeline_config.get("parallelism", 1),
                },
            )

            self.logger.info(f"Built pipeline: {name} with {len(self.steps)} steps")
            self.progress_tracker.stop_tracking(
                tracking_id,
                status="completed",
                message=f"Built pipeline: {name} with {len(self.steps)} steps",
            )
            return pipeline

        except Exception as e:
            self.progress_tracker.stop_tracking(
                tracking_id, status="failed", message=str(e)
            )
            raise

    def build_pipeline(self, pipeline_config: Dict[str, Any], **options) -> Pipeline:
        """
        Build pipeline from configuration dictionary.

        Args:
            pipeline_config: Pipeline configuration
            **options: Additional options

        Returns:
            Built pipeline
        """
        tracking_id = self.progress_tracker.start_tracking(
            module="pipeline",
            submodule="PipelineBuilder",
            message="Building pipeline from configuration",
        )

        try:
            # Parse configuration
            self.progress_tracker.update_tracking(
                tracking_id, message="Parsing pipeline configuration..."
            )
            pipeline_name = pipeline_config.get("name", "default_pipeline")
            steps_config = pipeline_config.get("steps", [])

            # Add steps from configuration
            self.progress_tracker.update_tracking(
                tracking_id,
                message=f"Adding {len(steps_config)} steps from configuration...",
            )
            for step_config in steps_config:
                step_name = step_config.get("name")
                step_type = step_config.get("type")
                if step_name and step_type:
                    step = self.add_step(
                        step_name, step_type, **step_config.get("config", {})
                    )
                    step.dependencies = list(
                        step_config.get("dependencies", step.dependencies)
                    )
                    step.delta_mode = step_config.get("delta_mode", step.delta_mode)
                    step.base_version_id = step_config.get(
                        "base_version_id", step.base_version_id
                    )
                    step.target_version_id = step_config.get(
                        "target_version_id", step.target_version_id
                    )
                    raw_parallel_safe = step_config.get(
                        "parallel_safe", step.parallel_safe
                    )
                    if not isinstance(raw_parallel_safe, bool):
                        raise ValidationError(
                            "parallel_safe must be a boolean for step "
                            f"'{step_name}', got "
                            f"{type(raw_parallel_safe).__name__}"
                        )
                    step.parallel_safe = raw_parallel_safe

            # Set parallelism if specified
            if "parallelism" in pipeline_config:
                self.progress_tracker.update_tracking(
                    tracking_id, message="Setting parallelism..."
                )
                self.set_parallelism(pipeline_config["parallelism"])

            result = self.build(pipeline_name)
            self.progress_tracker.stop_tracking(
                tracking_id,
                status="completed",
                message=f"Built pipeline from configuration: {pipeline_name}",
            )
            return result

        except Exception as e:
            self.progress_tracker.stop_tracking(
                tracking_id, status="failed", message=str(e)
            )
            raise

    def register_step_handler(self, step_type: str, handler: Callable) -> None:
        """
        Register step handler function.

        Args:
            step_type: Step type
            handler: Handler function
        """
        self.step_registry[step_type] = handler
        self.logger.debug(f"Registered handler for step type: {step_type}")

    def get_step(self, step_name: str) -> Optional[PipelineStep]:
        """Get step by name."""
        return next((s for s in self.steps if s.name == step_name), None)

    def serialize(self, format: str = "json") -> Union[str, Dict[str, Any]]:
        """
        Serialize pipeline configuration.

        Args:
            format: Serialization format

        Returns:
            Serialized pipeline
        """
        pipeline_data = {
            "name": "pipeline",
            "steps": [
                {
                    "name": step.name,
                    "type": step.step_type,
                    "config": step.config,
                    "dependencies": step.dependencies,
                    "parallel_safe": step.parallel_safe,
                }
                for step in self.steps
            ],
            "config": self.pipeline_config,
        }

        if format == "json":
            import json

            return json.dumps(pipeline_data, indent=2)
        else:
            return pipeline_data

    def validate_pipeline(self) -> Dict[str, Any]:
        """
        Validate pipeline structure and configuration.

        Returns:
            Validation results
        """
        tracking_id = self.progress_tracker.start_tracking(
            module="pipeline",
            submodule="PipelineBuilder",
            message="Validating pipeline",
        )

        try:
            result = self.validator.validate_pipeline(self)
            self.progress_tracker.stop_tracking(
                tracking_id,
                status="completed",
                message=f"Validation complete: {'Valid' if result.get('valid', False) else 'Invalid'}",
            )
            return result

        except Exception as e:
            self.progress_tracker.stop_tracking(
                tracking_id, status="failed", message=str(e)
            )
            raise


class PipelineSerializer:
    """
    Pipeline serialization handler.

    • Serializes pipelines to various formats
    • Handles pipeline deserialization
    • Manages pipeline versioning
    • Processes pipeline metadata
    """

    def __init__(self, **config):
        """Initialize pipeline serializer."""
        self.logger = get_logger("pipeline_serializer")
        self.config = config

    def serialize_pipeline(
        self, pipeline: Pipeline, format: str = "json", **options
    ) -> Union[str, Dict[str, Any]]:
        """
        Serialize pipeline to specified format.

        Args:
            pipeline: Pipeline object
            format: Serialization format
            **options: Additional options

        Returns:
            Serialized pipeline

        Notes:
            Step handlers are runtime callables and are intentionally omitted from
            the serialized representation. They must be rebound after deserialization.
        """
        reserved_config_keys = {
            "handler",
            "dependencies",
            "delta_mode",
            "base_version_id",
            "target_version_id",
            "parallel_safe",
        }
        pipeline_data = {
            "name": pipeline.name,
            "steps": [
                {
                    "name": step.name,
                    "type": step.step_type,
                    "config": {
                        key: value
                        for key, value in step.config.items()
                        if key not in reserved_config_keys
                    },
                    "dependencies": step.dependencies,
                    "delta_mode": getattr(step, "delta_mode", False),
                    "base_version_id": getattr(step, "base_version_id", None),
                    "target_version_id": getattr(step, "target_version_id", None),
                    "parallel_safe": getattr(step, "parallel_safe", False),
                }
                for step in pipeline.steps
            ],
            "config": pipeline.config,
            "metadata": pipeline.metadata,
        }

        if format == "json":
            import json

            return json.dumps(pipeline_data, indent=2, default=str)
        else:
            return pipeline_data

    def deserialize_pipeline(
        self, serialized_pipeline: Union[str, Dict[str, Any]], **options
    ) -> Pipeline:
        """
        Deserialize pipeline from serialized format.

        Args:
            serialized_pipeline: Serialized pipeline data
            **options: Additional options

        Returns:
            Reconstructed pipeline
        """
        # Parse if string
        if isinstance(serialized_pipeline, str):
            import json

            pipeline_data = json.loads(serialized_pipeline)
        else:
            pipeline_data = serialized_pipeline

        # Runtime handlers are process-local and cannot be reconstructed safely
        # from serialized data. Copy before sanitizing so dict inputs are not mutated.
        pipeline_data = dict(pipeline_data)
        sanitized_steps = []
        for step_data in pipeline_data.get("steps", []):
            sanitized_step = dict(step_data)
            step_config = dict(sanitized_step.get("config", {}))
            step_config.pop("handler", None)
            sanitized_step["config"] = step_config
            sanitized_steps.append(sanitized_step)
        pipeline_data["steps"] = sanitized_steps

        # Reapply pipeline-level config (e.g. parallelism) at the top level
        # so build_pipeline picks it up
        serialized_config = pipeline_data.pop("config", None) or {}
        for key, value in serialized_config.items():
            pipeline_data.setdefault(key, value)

        # Reconstruct pipeline
        builder = PipelineBuilder(**self.config)
        pipeline = builder.build_pipeline(pipeline_data, **options)

        return pipeline

    def version_pipeline(
        self, pipeline: Pipeline, version_info: Dict[str, Any]
    ) -> Pipeline:
        """
        Add versioning information to pipeline.

        Args:
            pipeline: Pipeline object
            version_info: Version information

        Returns:
            Versioned pipeline
        """
        pipeline.metadata["version"] = version_info.get("version", "1.0")
        pipeline.metadata["version_info"] = version_info

        return pipeline
