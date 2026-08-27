"""
Pipeline Execution Engine Module

This module provides pipeline execution and orchestration for complex data processing
workflows, including task scheduling, resource management, progress tracking, and
performance monitoring.

Key Features:
    - Pipeline execution and orchestration
    - Task scheduling and management
    - Resource allocation and monitoring
    - Performance optimization
    - Progress tracking and reporting
    - Status management (pending, running, paused, completed, failed)
    - Execution result tracking
    - Thread-safe execution

Main Classes:
    - ExecutionEngine: Pipeline execution engine
    - ExecutionResult: Dataclass for execution results
    - PipelineStatus: Enum for pipeline status
    - ProgressTracker: Progress tracking utility

Example Usage:
    >>> from semantica.pipeline import ExecutionEngine, Pipeline
    >>> engine = ExecutionEngine()
    >>> result = engine.execute(pipeline)
    >>> status = engine.get_status(pipeline)
    >>> progress = engine.get_progress(pipeline)

Author: Semantica Contributors
License: MIT
"""

import copy
import threading
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any, Callable, Dict, List, Optional

from ..utils.exceptions import ProcessingError, ValidationError
from ..utils.logging import get_logger
from ..utils.progress_tracker import get_progress_tracker
from .failure_handler import FailureHandler
from .parallelism_manager import ParallelismManager
from .pipeline_builder import Pipeline, PipelineStep, StepStatus
from .resource_scheduler import ResourceScheduler


class PipelineStatus(Enum):
    """Pipeline execution status."""

    PENDING = "pending"
    RUNNING = "running"
    PAUSED = "paused"
    COMPLETED = "completed"
    FAILED = "failed"
    STOPPED = "stopped"


class _ParallelResultContractError(ProcessingError):
    """Raised when a parallel step violates the dict-result contract.

    Contract violations are deterministic: re-running the handler cannot
    change its return type, so the retry loop must be skipped entirely.
    """


@dataclass
class ExecutionResult:
    """Pipeline execution result."""

    success: bool
    output: Any
    metadata: Dict[str, Any] = field(default_factory=dict)
    metrics: Dict[str, Any] = field(default_factory=dict)
    errors: List[str] = field(default_factory=list)


class ExecutionEngine:
    """
    Pipeline execution engine.

    • Pipeline execution and orchestration
    • Task scheduling and management
    • Resource allocation and monitoring
    • Performance optimization
    • Error handling and recovery
    • Parallel and distributed execution
    """

    def __init__(self, config: Optional[Dict[str, Any]] = None, **kwargs):
        """
        Initialize execution engine.

        Args:
            config: Configuration dictionary
            **kwargs: Additional configuration options:
                - max_workers: Maximum parallel workers
                - retry_on_failure: Enable retry on failure
        """
        self.logger = get_logger("execution_engine")
        self.config = config or {}
        self.config.update(kwargs)

        self.failure_handler = FailureHandler(**self.config)
        self.parallelism_manager = ParallelismManager(**self.config)
        self.resource_scheduler = ResourceScheduler(**self.config)

        self.running_pipelines: Dict[str, Pipeline] = {}
        self.pipeline_status: Dict[str, PipelineStatus] = {}
        self.pipeline_lock = threading.Lock()

        # Initialize progress tracker
        self.progress_tracker = get_progress_tracker()
        # Ensure progress tracker is enabled
        if not self.progress_tracker.enabled:
            self.progress_tracker.enabled = True

    def execute_pipeline(
        self, pipeline: Pipeline, data: Any = None, **options
    ) -> ExecutionResult:
        """
        Execute pipeline.

        Args:
            pipeline: Pipeline object
            data: Input data
            **options: Execution options

        Returns:
            Execution result
        """
        pipeline_id = pipeline.name
        start_time = time.time()

        # Track pipeline execution
        pipeline_tracking_id = self.progress_tracker.start_tracking(
            module="pipeline",
            submodule="ExecutionEngine",
            message=f"Executing pipeline: {pipeline_id}",
            pipeline_id=pipeline_id,
        )

        try:
            self.logger.info(f"Executing pipeline: {pipeline_id}")

            # Register pipeline modules for progress tracking
            module_list = []
            module_order = {}
            if hasattr(pipeline, "steps") and pipeline.steps:
                for idx, step in enumerate(pipeline.steps):
                    # Extract module name from step
                    module_name = (
                        getattr(step, "module", None)
                        or getattr(step, "name", None)
                        or str(step)
                    )
                    if module_name and module_name not in module_list:
                        module_list.append(module_name)
                        module_order[module_name] = idx

            # If no steps found, try to infer from pipeline structure
            if not module_list:
                # Common pipeline modules
                module_list = [
                    "ingest",
                    "parse",
                    "normalize",
                    "semantic_extract",
                    "kg",
                    "embeddings",
                ]
                module_order = {module: idx for idx, module in enumerate(module_list)}

            # Register pipeline modules
            if module_list:
                self.progress_tracker.register_pipeline_modules(
                    pipeline_id=pipeline_id,
                    module_list=module_list,
                    module_order=module_order,
                )

            # Set status
            with self.pipeline_lock:
                self.pipeline_status[pipeline_id] = PipelineStatus.RUNNING
                self.running_pipelines[pipeline_id] = pipeline

            # Allocate resources
            resources = self.resource_scheduler.allocate_resources(pipeline, **options)

            try:
                # Execute steps
                result = self._execute_steps(pipeline, data, **options)

                # Collect metrics
                execution_time = time.time() - start_time
                metrics = {
                    "execution_time": execution_time,
                    "steps_executed": len(
                        [s for s in pipeline.steps if s.status == StepStatus.COMPLETED]
                    ),
                    "steps_failed": len(
                        [s for s in pipeline.steps if s.status == StepStatus.FAILED]
                    ),
                }

                # Update status
                with self.pipeline_lock:
                    if metrics["steps_failed"] == 0:
                        self.pipeline_status[pipeline_id] = PipelineStatus.COMPLETED
                    else:
                        self.pipeline_status[pipeline_id] = PipelineStatus.FAILED

                # Update progress tracking
                self.progress_tracker.stop_tracking(
                    pipeline_tracking_id,
                    status="completed" if metrics["steps_failed"] == 0 else "failed",
                    message=f"Executed {metrics['steps_executed']} steps in {execution_time:.2f}s",
                )

                # Clear pipeline context when pipeline completes
                self.progress_tracker.clear_pipeline_context(pipeline_id)

                return ExecutionResult(
                    success=metrics["steps_failed"] == 0,
                    output=result,
                    metadata={
                        "pipeline_id": pipeline_id,
                        "execution_time": execution_time,
                    },
                    metrics=metrics,
                )

            finally:
                # Release resources
                self.resource_scheduler.release_resources(resources)

        except Exception as e:
            self.progress_tracker.stop_tracking(
                pipeline_tracking_id, status="failed", message=str(e)
            )
            # Clear pipeline context on failure
            self.progress_tracker.clear_pipeline_context(pipeline_id)
            self.logger.error(f"Pipeline execution failed: {e}")
            with self.pipeline_lock:
                self.pipeline_status[pipeline_id] = PipelineStatus.FAILED

            return ExecutionResult(success=False, output=None, errors=[str(e)])

    def _execute_steps(self, pipeline: Pipeline, data: Any, **options) -> Any:
        """
        Execute pipeline steps.

        Steps are grouped into dependency layers. When a pipeline is
        configured with parallelism > 1, a layer whose steps are all marked
        ``parallel_safe`` and whose input is a dict is executed concurrently
        (bounded by the effective parallelism); every other layer runs
        sequentially, preserving the default serial behaviour.
        """
        effective_parallelism = self._get_effective_parallelism(pipeline)

        if effective_parallelism <= 1:
            return self._execute_steps_sequential(pipeline, data, **options)

        layers = self._group_steps_by_dependency_level(pipeline.steps)

        current_data = data
        for layer in layers:
            if self.pipeline_status.get(pipeline.name) == PipelineStatus.STOPPED:
                break

            # Wait if paused
            while self.pipeline_status.get(pipeline.name) == PipelineStatus.PAUSED:
                time.sleep(0.1)

            if self._can_run_layer_in_parallel(layer, current_data):
                merged = self._execute_parallel_group(
                    layer,
                    current_data,
                    effective_parallelism,
                    pipeline_name=pipeline.name,
                    **options,
                )
                if merged is None:
                    # Input isolation failed before any handler started;
                    # run this layer sequentially instead.
                    current_data = self._execute_steps_sequential(
                        pipeline, current_data, steps=layer, **options
                    )
                else:
                    current_data = merged
            else:
                current_data = self._execute_steps_sequential(
                    pipeline, current_data, steps=layer, **options
                )

        return current_data

    def _execute_steps_sequential(
        self,
        pipeline: Pipeline,
        data: Any,
        steps: Optional[List[PipelineStep]] = None,
        **options,
    ) -> Any:
        """Execute steps sequentially following dependency order."""
        if steps is None:
            sorted_steps = self._topological_sort(pipeline.steps)
        else:
            sorted_steps = list(steps)

        current_data = data
        total_steps = len(sorted_steps)

        for step_idx, step in enumerate(sorted_steps):
            if self.pipeline_status.get(pipeline.name) == PipelineStatus.STOPPED:
                break

            # Wait if paused
            while self.pipeline_status.get(pipeline.name) == PipelineStatus.PAUSED:
                time.sleep(0.1)

            current_data = self._execute_step_with_retries(
                step,
                current_data,
                step_label=f"Step {step_idx + 1}/{total_steps}: {step.name}",
                pipeline_name=pipeline.name,
                **options,
            )

        return current_data

    def _execute_step_with_retries(
        self,
        step: PipelineStep,
        data: Any,
        step_label: Optional[str] = None,
        pipeline_name: Optional[str] = None,
        require_dict_result: bool = False,
        **options,
    ) -> Any:
        """
        Execute a single step with retry handling.

        Shared by the sequential and parallel execution paths so that retry
        policies, step status tracking and progress reporting behave
        identically. Returns the step result, or raises the final error
        after retries are exhausted.

        When ``require_dict_result`` is set (parallel layers), a handler
        returning a non-dict raises ProcessingError before the step is
        marked completed, so status and progress reporting stay consistent.
        Such contract violations are never retried: the handler's return
        type cannot change between attempts.
        """
        step_tracking_id = self.progress_tracker.start_tracking(
            module="pipeline",
            # Pipeline identity + step name keep tracking IDs unique so
            # concurrent steps of the same step_type cannot overwrite each
            # other's progress records.
            submodule=(
                f"{pipeline_name or 'pipeline'}:"
                f"{step.step_type or 'step'}:{step.name}"
            ),
            message=step_label or f"Executing step: {step.name}",
        )

        try:
            step.status = StepStatus.RUNNING
            step_result = self._execute_step(step, data, **options)
            if require_dict_result and not isinstance(step_result, dict):
                raise _ParallelResultContractError(
                    f"Step '{step.name}' is marked parallel_safe and must "
                    f"return a dict so parallel results can be merged, got "
                    f"{type(step_result).__name__}"
                )
            step.status = StepStatus.COMPLETED
            step.result = step_result

            self.progress_tracker.stop_tracking(
                step_tracking_id,
                status="completed",
                message=f"Completed step: {step.name}",
            )
            return step_result

        except Exception as e:
            step.status = StepStatus.FAILED
            step.error = e

            # Contract violations are deterministic failures: re-running
            # the handler cannot change its return type, so never consult
            # the retry policy for them.
            if isinstance(e, _ParallelResultContractError):
                self.progress_tracker.stop_tracking(
                    step_tracking_id, status="failed", message=str(e)
                )
                raise

            # Retry loop respecting max_retries from the policy
            retry_policy = self.failure_handler.get_retry_policy(step.step_type)
            max_retries = retry_policy.max_retries if retry_policy else 0
            retry_count = 0
            success = False

            while retry_count < max_retries:
                recovery_result = self.failure_handler.handle_step_failure(step, e)
                if not recovery_result.get("retry", False):
                    break
                retry_delay = recovery_result.get("retry_delay", 0.0)
                if retry_delay > 0:
                    time.sleep(retry_delay)
                self.progress_tracker.update_tracking(
                    step_tracking_id,
                    status="running",
                    message=f"Retrying step: {step.name} (attempt {retry_count + 1})",
                )
                step.status = StepStatus.RUNNING
                try:
                    step_result = self._execute_step(step, data, **options)
                    if require_dict_result and not isinstance(
                        step_result, dict
                    ):
                        raise _ParallelResultContractError(
                            f"Step '{step.name}' is marked parallel_safe "
                            f"and must return a dict so parallel results "
                            f"can be merged, got "
                            f"{type(step_result).__name__}"
                        )
                    step.status = StepStatus.COMPLETED
                    step.result = step_result
                    success = True
                    break
                except Exception as retry_e:
                    step.status = StepStatus.FAILED
                    step.error = retry_e
                    e = retry_e
                    retry_count += 1

            if success:
                self.progress_tracker.stop_tracking(
                    step_tracking_id,
                    status="completed",
                    message=f"Retry successful: {step.name}",
                )
                return step_result
            else:
                self.progress_tracker.stop_tracking(
                    step_tracking_id, status="failed", message=str(e)
                )
                raise e

    def _get_effective_parallelism(self, pipeline: Pipeline) -> int:
        """Return the parallelism actually used for this pipeline."""
        configured = pipeline.config.get("parallelism", 1)
        if not isinstance(configured, int) or configured <= 0:
            return 1
        return min(configured, self.parallelism_manager.max_workers)

    def _group_steps_by_dependency_level(
        self, steps: List[PipelineStep]
    ) -> List[List[PipelineStep]]:
        """
        Group steps into dependency layers, preserving declaration order.

        Circular or unknown dependencies raise ValidationError so the
        parallel path fails deterministically, matching the validation
        behaviour of the serial topological sort.
        """
        step_map = {step.name: step for step in steps}
        levels: Dict[str, int] = {}
        visiting: set = set()

        for step in steps:
            for dep in step.dependencies:
                if dep not in step_map:
                    raise ValidationError(
                        f"Step '{step.name}' depends on unknown step '{dep}'"
                    )

        def get_level(step_name: str) -> int:
            if step_name in levels:
                return levels[step_name]
            if step_name in visiting:
                raise ValidationError(
                    "Circular dependency detected in pipeline "
                    f"(cycle passes through step '{step_name}')"
                )
            visiting.add(step_name)
            step = step_map[step_name]
            if not step.dependencies:
                level = 0
            else:
                level = max(get_level(dep) for dep in step.dependencies) + 1
            visiting.discard(step_name)
            levels[step_name] = level
            return level

        for step in steps:
            get_level(step.name)

        grouped: Dict[int, List[PipelineStep]] = {}
        for step in steps:
            grouped.setdefault(levels[step.name], []).append(step)
        return [grouped[level] for level in sorted(grouped)]

    def _can_run_layer_in_parallel(self, layer: List[PipelineStep], data: Any) -> bool:
        """Check whether a dependency layer can safely run in parallel."""
        if len(layer) <= 1:
            return False
        if not isinstance(data, dict):
            return False
        for step in layer:
            # Strict boolean check: truthy non-bool values (e.g. the
            # string "false") must never opt a step into concurrency.
            if getattr(step, "parallel_safe", False) is not True:
                return False
            if getattr(step, "delta_mode", False):
                return False
        return True

    def _execute_parallel_group(
        self,
        layer: List[PipelineStep],
        data: Any,
        effective_parallelism: int,
        pipeline_name: Optional[str] = None,
        **options,
    ) -> Optional[Any]:
        """
        Execute a dependency layer concurrently.

        Per-step inputs are deep-copied before any handler starts so that
        parallel steps do not share mutable state. Returns the merged dict
        result, or None when input isolation failed (before any handler
        ran) and the layer should fall back to sequential execution.
        """
        # Isolate per-step inputs before starting any handler
        try:
            step_inputs = {step.name: copy.deepcopy(data) for step in layer}
        except Exception as e:
            self.logger.warning(
                f"Falling back to sequential execution: input for parallel "
                f"layer could not be isolated ({e})"
            )
            return None

        step_results: Dict[str, Any] = {}
        failure: Optional[BaseException] = None
        max_workers = min(effective_parallelism, len(layer))

        with ThreadPoolExecutor(max_workers=max_workers) as executor:
            futures = {
                executor.submit(
                    self._execute_step_with_retries,
                    step,
                    step_inputs[step.name],
                    # Validate the dict-result contract inside the shared
                    # lifecycle path, before completion is reported.
                    pipeline_name=pipeline_name,
                    require_dict_result=True,
                    **options,
                ): step
                for step in layer
            }

            for future in as_completed(futures):
                step = futures[future]
                try:
                    step_result = future.result()
                except Exception as e:
                    if failure is None:
                        failure = e
                    # Cancel steps that have not started yet
                    for pending in futures:
                        pending.cancel()
                else:
                    step_results[step.name] = step_result

        if failure is not None:
            raise failure

        return self._merge_parallel_results(data, layer, step_results)

    def _merge_parallel_results(
        self,
        base: Dict[str, Any],
        layer: List[PipelineStep],
        step_results: Dict[str, Any],
    ) -> Dict[str, Any]:
        """
        Merge the results of a parallel layer into a single dict.

        Steps are processed in declaration order (never by completion
        order). Keys whose values are unchanged from the shared base input
        are skipped (handlers commonly return complete dicts such as
        ``{**data, ...}``); only added or changed keys count as branch
        writes. Keys written with equal values by multiple steps are
        allowed; conflicting values for the same key raise a
        ProcessingError naming the key and both steps. Ambiguous equality
        comparisons count as changed, never as unchanged.
        """
        merged = dict(base)
        key_sources: Dict[str, str] = {}

        for step in layer:
            step_result = step_results.get(step.name)
            if step_result is None:
                continue
            for key, value in step_result.items():
                if key in base and self._values_equal(base[key], value):
                    # Echo of the shared input: not a branch write, so it
                    # cannot conflict with a sibling that changes the key.
                    continue
                if key in key_sources and not self._values_equal(
                    merged.get(key), value
                ):
                    raise ProcessingError(
                        f"Conflicting values for key '{key}' in parallel step "
                        f"results: step '{step.name}' produced {value!r}, but "
                        f"step '{key_sources[key]}' previously produced "
                        f"{merged.get(key)!r}"
                    )
                key_sources[key] = step.name
                merged[key] = value

        return merged

    @staticmethod
    def _values_equal(left: Any, right: Any) -> bool:
        """Safely compare two values; ambiguous comparisons count as conflicts."""
        try:
            return bool(left == right)
        except (TypeError, ValueError):
            return False


    def _execute_step(self, step: PipelineStep, data: Any, **options) -> Any:
        """
        Execute a single step.
        
        If delta_mode is enabled for the step, this intercepts the execution to compute
        the delta between the base and target versions, passing only the changes
        (added/removed triples) to the handler.
        """

        if getattr(step, "delta_mode", False):
            self.logger.info(f"Executing step '{step.name}' in incremental delta mode.")
            
            version_manager = options.get("version_manager") or self.config.get("version_manager")
            triplet_store = options.get("triplet_store") or self.config.get("triplet_store")
            
            if not version_manager or not triplet_store:
                raise ProcessingError(
                    f"Step '{step.name}' requires 'version_manager' and 'triplet_store' "
                    f"in execution options for delta processing."
                )
            
            if not step.base_version_id or not step.target_version_id:
                raise ValidationError(
                    f"Step '{step.name}' in delta_mode requires 'base_version_id' "
                    f"and 'target_version_id' to be set."
                )
            

            base_snap = version_manager.get_version(step.base_version_id)
            target_snap = version_manager.get_version(step.target_version_id)
            
            if not base_snap:
                raise ValidationError(f"Base version '{step.base_version_id}' not found in storage.")
            if not target_snap:
                raise ValidationError(f"Target version '{step.target_version_id}' not found in storage.")
                
            base_uri = base_snap.get("graph_uri")
            target_uri = target_snap.get("graph_uri")
            
            if not base_uri or not target_uri:
                raise ValidationError(
                    "Both base and target snapshots must contain a 'graph_uri' "
                    "to compute native store deltas."
                )
 
            self.logger.debug(f"Computing delta between {base_uri} and {target_uri}")
            delta_result = triplet_store.compute_delta(base_uri, target_uri, **options)
   
            data = delta_result
        
        if step.handler is not None:
            return step.handler(data, **step.config, **options)
        else:
            return data

    def _topological_sort(self, steps: List[PipelineStep]) -> List[PipelineStep]:
        """Sort steps by dependencies (topological sort)."""
        tracking_id = self.progress_tracker.start_tracking(
            module="pipeline",
            submodule="ExecutionEngine",
            message=f"Sorting {len(steps)} steps by dependencies",
        )

        try:
            # Build dependency graph
            self.progress_tracker.update_tracking(
                tracking_id, message="Building dependency graph..."
            )
            step_map = {step.name: step for step in steps}
            in_degree = {step.name: len(step.dependencies) for step in steps}

            # Find steps with no dependencies
            self.progress_tracker.update_tracking(
                tracking_id, message="Finding entry points..."
            )
            queue = [step for step in steps if in_degree[step.name] == 0]
            sorted_steps = []

            # Perform topological sort
            self.progress_tracker.update_tracking(
                tracking_id, message="Performing topological sort..."
            )
            while queue:
                step = queue.pop(0)
                sorted_steps.append(step)

                # Update in-degrees of dependent steps
                for other_step in steps:
                    if step.name in other_step.dependencies:
                        in_degree[other_step.name] -= 1
                        if in_degree[other_step.name] == 0:
                            queue.append(other_step)

            # Check for cycles
            self.progress_tracker.update_tracking(
                tracking_id, message="Checking for circular dependencies..."
            )
            if len(sorted_steps) != len(steps):
                raise ValidationError("Circular dependency detected in pipeline")

            self.progress_tracker.stop_tracking(
                tracking_id,
                status="completed",
                message=f"Sorted {len(steps)} steps by dependencies",
            )
            return sorted_steps

        except Exception as e:
            self.progress_tracker.stop_tracking(
                tracking_id, status="failed", message=str(e)
            )
            raise

    def pause_pipeline(self, pipeline_id: str) -> None:
        """Pause pipeline execution."""
        with self.pipeline_lock:
            if pipeline_id in self.pipeline_status:
                if self.pipeline_status[pipeline_id] == PipelineStatus.RUNNING:
                    self.pipeline_status[pipeline_id] = PipelineStatus.PAUSED
                    self.logger.info(f"Paused pipeline: {pipeline_id}")

    def resume_pipeline(self, pipeline_id: str) -> None:
        """Resume paused pipeline."""
        with self.pipeline_lock:
            if pipeline_id in self.pipeline_status:
                if self.pipeline_status[pipeline_id] == PipelineStatus.PAUSED:
                    self.pipeline_status[pipeline_id] = PipelineStatus.RUNNING
                    self.logger.info(f"Resumed pipeline: {pipeline_id}")

    def stop_pipeline(self, pipeline_id: str) -> None:
        """Stop pipeline execution."""
        with self.pipeline_lock:
            if pipeline_id in self.pipeline_status:
                self.pipeline_status[pipeline_id] = PipelineStatus.STOPPED
                self.logger.info(f"Stopped pipeline: {pipeline_id}")

    def get_pipeline_status(self, pipeline_id: str) -> Optional[PipelineStatus]:
        """Get pipeline status."""
        return self.pipeline_status.get(pipeline_id)

    def get_progress(self, pipeline_id: str) -> Dict[str, Any]:
        """Get pipeline execution progress."""
        if pipeline_id not in self.running_pipelines:
            return {}

        pipeline = self.running_pipelines[pipeline_id]
        total_steps = len(pipeline.steps)
        completed_steps = len(
            [s for s in pipeline.steps if s.status == StepStatus.COMPLETED]
        )

        return {
            "total_steps": total_steps,
            "completed_steps": completed_steps,
            "progress_percentage": (
                (completed_steps / total_steps * 100) if total_steps > 0 else 0.0
            ),
            "status": self.pipeline_status.get(
                pipeline_id, PipelineStatus.PENDING
            ).value,
        }


class ProgressTracker:
    """Progress tracking for pipeline execution."""

    def __init__(self, **config):
        """Initialize progress tracker."""
        self.logger = get_logger("progress_tracker")
        self.config = config
        self.tracking_data: Dict[str, Dict[str, Any]] = {}

    def track_progress(self, pipeline_id: str, step_name: str, progress: float) -> None:
        """Track progress for a pipeline step."""
        if pipeline_id not in self.tracking_data:
            self.tracking_data[pipeline_id] = {}

        self.tracking_data[pipeline_id][step_name] = {
            "progress": progress,
            "timestamp": datetime.now().isoformat(),
        }

    def get_completion_percentage(self, pipeline_id: str) -> float:
        """Get overall completion percentage."""
        if pipeline_id not in self.tracking_data:
            return 0.0

        steps = self.tracking_data[pipeline_id]
        if not steps:
            return 0.0

        total_progress = sum(step["progress"] for step in steps.values())
        return total_progress / len(steps)

    def estimate_remaining_time(
        self, pipeline_id: str, start_time: float
    ) -> Optional[float]:
        """Estimate remaining execution time."""
        completion = self.get_completion_percentage(pipeline_id)
        if completion == 0:
            return None

        elapsed = time.time() - start_time
        estimated_total = elapsed / completion
        remaining = estimated_total - elapsed

        return max(0, remaining)
