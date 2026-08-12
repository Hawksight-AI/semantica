"""Tests for PipelineWithProvenance.

Verifies that:
1. The import path is correct (no ModuleNotFoundError).
2. PipelineWithProvenance accepts a built Pipeline and runs it via ExecutionEngine.
3. Provenance tracking gracefully degrades when the provenance package is absent.
"""

import sys
from unittest.mock import patch

import pytest

from semantica.pipeline import PipelineBuilder
from semantica.pipeline.pipeline_provenance import PipelineWithProvenance
from semantica.pipeline.execution_engine import ExecutionResult


class TestPipelineWithProvenance:
    """Tests for PipelineWithProvenance."""

    @pytest.fixture
    def simple_pipeline(self):
        """Build a minimal two-step pipeline for testing."""
        builder = PipelineBuilder()
        builder.add_step("ingest", "file_ingest")
        builder.add_step("parse", "document_parse")
        return builder.build("test_provenance_pipeline")

    def test_instantiation_with_pipeline(self, simple_pipeline):
        """Should accept a built Pipeline instance."""
        runner = PipelineWithProvenance(simple_pipeline, provenance=False)
        assert runner._pipeline is simple_pipeline

    def test_run_returns_execution_result(self, simple_pipeline):
        """run() should delegate to ExecutionEngine and return an ExecutionResult."""
        runner = PipelineWithProvenance(simple_pipeline, provenance=False)
        result = runner.run()
        assert isinstance(result, ExecutionResult)
        assert result.success is True

    def test_getattr_delegates_to_pipeline(self, simple_pipeline):
        """Attribute access should fall through to the wrapped Pipeline."""
        runner = PipelineWithProvenance(simple_pipeline, provenance=False)
        assert runner.name == "test_provenance_pipeline"
        assert len(runner.steps) == 2

    def test_provenance_disabled_when_import_fails(self, simple_pipeline):
        """When semantica.provenance is unavailable, provenance should be disabled."""
        # Force the provenance import to raise ImportError
        with patch.dict(sys.modules, {"semantica.provenance": None}):
            runner = PipelineWithProvenance(simple_pipeline, provenance=True)
            assert runner.provenance is False
            assert runner._prov_manager is None
            # Should still execute successfully without provenance
            result = runner.run()
            assert isinstance(result, ExecutionResult)
            assert result.success is True

    def test_run_with_data(self, simple_pipeline):
        """run() should accept data and kwargs without error."""
        runner = PipelineWithProvenance(simple_pipeline, provenance=False)
        result = runner.run(data={"key": "value"})
        assert isinstance(result, ExecutionResult)
