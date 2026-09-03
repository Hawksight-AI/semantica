"""
Pipeline Templates Module

This module provides pre-built pipeline templates for common use cases and workflows,
enabling quick pipeline creation with customizable configurations.

Key Features:
    - Pre-built pipeline templates
    - Common workflow patterns
    - Template customization and configuration
    - Performance optimization
    - Error handling and recovery
    - Template registration and management

Main Classes:
    - PipelineTemplateManager: Pipeline template management system
    - PipelineTemplate: Dataclass for pipeline template definition

Example Usage:
    >>> from semantica.pipeline import PipelineTemplateManager
    >>> manager = PipelineTemplateManager()
    >>> template = manager.get_template("knowledge_graph")
    >>> pipeline = manager.create_from_template("knowledge_graph", config={})

Author: Semantica Contributors
License: MIT
"""

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

from ..utils.exceptions import ProcessingError, ValidationError
from ..utils.logging import get_logger
from ..utils.progress_tracker import get_progress_tracker
from .pipeline_builder import PipelineBuilder


@dataclass
class PipelineTemplate:
    """Pipeline template definition."""

    name: str
    description: str
    steps: List[Dict[str, Any]] = field(default_factory=list)
    config: Dict[str, Any] = field(default_factory=dict)
    metadata: Dict[str, Any] = field(default_factory=dict)


class PipelineTemplateManager:
    """
    Pipeline template management system.

    • Pre-built pipeline templates
    • Common workflow patterns
    • Template customization and configuration
    • Performance optimization
    • Error handling and recovery
    • Advanced template features
    """

    def __init__(self, config: Optional[Dict[str, Any]] = None, **kwargs):
        """
        Initialize template manager.

        Args:
            config: Configuration dictionary
            **kwargs: Additional configuration options
        """
        self.logger = get_logger("pipeline_template_manager")
        self.config = config or {}
        self.config.update(kwargs)

        # Initialize progress tracker
        self.progress_tracker = get_progress_tracker()
        # Ensure progress tracker is enabled
        if not self.progress_tracker.enabled:
            self.progress_tracker.enabled = True

        self.templates: Dict[str, PipelineTemplate] = {}
        self._load_default_templates()

    def _load_default_templates(self) -> None:
        """Load default pipeline templates."""
        # Document Processing Template
        self.templates["document_processing"] = PipelineTemplate(
            name="document_processing",
            description="Complete document processing pipeline from ingestion to knowledge graph",
            steps=[
                {
                    "name": "ingest",
                    "type": "ingest",
                    "config": {"source": "documents/"},
                },
                {
                    "name": "parse",
                    "type": "parse",
                    "config": {"formats": ["pdf", "docx"]},
                    "dependencies": ["ingest"],
                },
                {
                    "name": "normalize",
                    "type": "normalize",
                    "config": {},
                    "dependencies": ["parse"],
                },
                {
                    "name": "extract",
                    "type": "extract",
                    "config": {"entities": True, "relations": True},
                    "dependencies": ["normalize"],
                },
                {
                    "name": "embed",
                    "type": "embed",
                    "config": {"model": "text-embedding-3-large"},
                    "dependencies": ["extract"],
                },
                {
                    "name": "build_kg",
                    "type": "build_kg",
                    "config": {},
                    "dependencies": ["extract", "embed"],
                },
            ],
            config={"parallelism": 2},
            metadata={"category": "document_processing"},
        )

        # RAG Pipeline Template
        self.templates["rag_pipeline"] = PipelineTemplate(
            name="rag_pipeline",
            description="RAG pipeline for question answering",
            steps=[
                {
                    "name": "ingest",
                    "type": "ingest",
                    "config": {"source": "documents/"},
                },
                {
                    "name": "chunk",
                    "type": "chunk",
                    "config": {"chunk_size": 512},
                    "dependencies": ["ingest"],
                },
                {
                    "name": "embed",
                    "type": "embed",
                    "config": {},
                    "dependencies": ["chunk"],
                },
                {
                    "name": "store_vectors",
                    "type": "store_vectors",
                    "config": {"store": "weaviate"},
                    "dependencies": ["embed"],
                },
            ],
            config={"parallelism": 4},
            metadata={"category": "rag"},
        )

        # Knowledge Graph Construction Template
        self.templates["kg_construction"] = PipelineTemplate(
            name="kg_construction",
            description="Knowledge graph construction from multiple sources",
            steps=[
                {"name": "ingest_sources", "type": "ingest", "config": {"sources": []}},
                {
                    "name": "extract_entities",
                    "type": "extract",
                    "config": {"entities": True},
                    "dependencies": ["ingest_sources"],
                },
                {
                    "name": "extract_relations",
                    "type": "extract",
                    "config": {"relations": True},
                    "dependencies": ["ingest_sources"],
                },
                {
                    "name": "deduplicate",
                    "type": "deduplicate",
                    "config": {},
                    "dependencies": ["extract_entities"],
                },
                {
                    "name": "resolve_conflicts",
                    "type": "resolve_conflicts",
                    "config": {},
                    "dependencies": ["extract_entities", "extract_relations"],
                },
                {
                    "name": "build_graph",
                    "type": "build_kg",
                    "config": {},
                    "dependencies": ["deduplicate", "resolve_conflicts"],
                },
            ],
            config={"parallelism": 3},
            metadata={"category": "knowledge_graph"},
        )

        # Ontology Generation Template
        self.templates["ontology_generation"] = PipelineTemplate(
            name="ontology_generation",
            description="Ontology generation from extracted data",
            steps=[
                {
                    "name": "extract_concepts",
                    "type": "extract",
                    "config": {"entities": True},
                },
                {
                    "name": "infer_classes",
                    "type": "infer_classes",
                    "config": {},
                    "dependencies": ["extract_concepts"],
                },
                {
                    "name": "infer_properties",
                    "type": "infer_properties",
                    "config": {},
                    "dependencies": ["infer_classes"],
                },
                {
                    "name": "generate_owl",
                    "type": "generate_owl",
                    "config": {},
                    "dependencies": ["infer_classes", "infer_properties"],
                },
                {
                    "name": "validate_ontology",
                    "type": "validate_ontology",
                    "config": {},
                    "dependencies": ["generate_owl"],
                },
            ],
            config={"parallelism": 1},
            metadata={"category": "ontology"},
        )

        # Bug Bounty Hunting (graph/case-management orchestration)
        self.templates["bug_bounty_hunting"] = PipelineTemplate(
            name="bug_bounty_hunting",
            description=(
                "Authorized bug bounty hunting flow: scope gates, asset inventory, "
                "evidence provenance, surface mapping, finding triage, and report "
                "composition as a dependency graph (n8n-style)."
            ),
            steps=[
                {
                    "name": "program_scope",
                    "type": "program_scope",
                    "config": {"program_name": "example-program", "in_scope": []},
                },
                {
                    "name": "scope_check",
                    "type": "scope_check",
                    "config": {"block_out_of_scope": True},
                    "dependencies": ["program_scope"],
                },
                {
                    "name": "asset_inventory",
                    "type": "asset_inventory",
                    "config": {"assets": []},
                    "dependencies": ["scope_check"],
                },
                {
                    "name": "evidence_ingest",
                    "type": "evidence_ingest",
                    "config": {},
                    "dependencies": ["asset_inventory"],
                },
                {
                    "name": "surface_map",
                    "type": "surface_map",
                    "config": {},
                    "dependencies": ["evidence_ingest"],
                },
                {
                    "name": "finding_record",
                    "type": "finding_record",
                    "config": {},
                    "dependencies": ["surface_map"],
                },
                {
                    "name": "duplicate_check",
                    "type": "duplicate_check",
                    "config": {"threshold": 0.85},
                    "dependencies": ["finding_record"],
                },
                {
                    "name": "severity_triage",
                    "type": "severity_triage",
                    "config": {"min_severity": "low"},
                    "dependencies": ["duplicate_check"],
                },
                {
                    "name": "report_compose",
                    "type": "report_compose",
                    "config": {},
                    "dependencies": ["severity_triage"],
                },
                {
                    "name": "submission_gate",
                    "type": "submission_gate",
                    "config": {"block_if_not_ready": True},
                    "dependencies": ["report_compose"],
                },
                {
                    "name": "graph_export",
                    "type": "graph_export",
                    "config": {},
                    "dependencies": ["submission_gate"],
                },
            ],
            config={"parallelism": 1},
            metadata={
                "category": "security_research",
                "style": "n8n_graph",
                "authorized_only": True,
            },
        )

    def get_template(self, template_name: str) -> Optional[PipelineTemplate]:
        """
        Get template by name.

        Args:
            template_name: Template name

        Returns:
            Pipeline template or None
        """
        return self.templates.get(template_name)

    def create_pipeline_from_template(
        self, template_name: str, **overrides
    ) -> "PipelineBuilder":
        """
        Create pipeline from template.

        Args:
            template_name: Template name
            **overrides: Configuration overrides

        Returns:
            Pipeline builder
        """
        tracking_id = self.progress_tracker.start_tracking(
            module="pipeline",
            submodule="PipelineTemplateManager",
            message=f"Creating pipeline from template: {template_name}",
        )

        try:
            self.progress_tracker.update_tracking(
                tracking_id, message="Getting template..."
            )
            template = self.get_template(template_name)
            if not template:
                raise ValidationError(f"Template not found: {template_name}")

            builder = PipelineBuilder(**self.config)

            # Add steps from template
            self.progress_tracker.update_tracking(
                tracking_id,
                message=f"Adding {len(template.steps)} steps from template...",
            )
            for step_config in template.steps:
                step_name = step_config["name"]
                step_type = step_config["type"]
                config = step_config.get("config", {})
                dependencies = step_config.get("dependencies", [])

                # Apply overrides
                if step_name in overrides:
                    config.update(overrides[step_name])

                builder.add_step(
                    step_name, step_type, dependencies=dependencies, **config
                )

            # Set pipeline config
            self.progress_tracker.update_tracking(
                tracking_id, message="Setting pipeline configuration..."
            )
            pipeline_config = template.config.copy()
            pipeline_config.update(overrides.get("pipeline_config", {}))

            for key, value in pipeline_config.items():
                if key == "parallelism":
                    builder.set_parallelism(value)

            self.progress_tracker.stop_tracking(
                tracking_id,
                status="completed",
                message=f"Created pipeline from template: {template_name} with {len(template.steps)} steps",
            )
            return builder

        except Exception as e:
            self.progress_tracker.stop_tracking(
                tracking_id, status="failed", message=str(e)
            )
            raise

    def register_template(self, template: PipelineTemplate) -> None:
        """
        Register a custom template.

        Args:
            template: Pipeline template
        """
        self.templates[template.name] = template
        self.logger.info(f"Registered template: {template.name}")

    def list_templates(self, category: Optional[str] = None) -> List[str]:
        """
        List available templates.

        Args:
            category: Optional category filter

        Returns:
            List of template names
        """
        if category:
            return [
                name
                for name, template in self.templates.items()
                if template.metadata.get("category") == category
            ]
        return list(self.templates.keys())

    def get_template_info(self, template_name: str) -> Optional[Dict[str, Any]]:
        """
        Get template information.

        Args:
            template_name: Template name

        Returns:
            Template information dictionary
        """
        template = self.get_template(template_name)
        if not template:
            return None

        return {
            "name": template.name,
            "description": template.description,
            "step_count": len(template.steps),
            "config": template.config,
            "metadata": template.metadata,
        }
