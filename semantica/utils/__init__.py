"""
Utilities Module

This module provides shared utilities and helper functions for the Semantica framework,
including logging, exception handling, data validation, helper functions, constants,
and type definitions used throughout the framework.

Key Features:
    - Comprehensive logging utilities with structured output
    - Custom exception hierarchy with error context
    - Data validation and type checking
    - Common helper functions for data manipulation
    - Framework constants and configuration defaults
    - Type definitions and protocols

Main Classes:
    - Logging utilities: setup_logging, get_logger, log_performance, log_error
    - Exception classes: SemanticaError, ValidationError, ProcessingError, ConfigurationError, QualityError
    - Validators: validate_data, validate_config, validate_entity, validate_relationship
    - Helpers: format_data, clean_text, normalize_entities, hash_data, merge_dicts
    - Types: Entity, Relationship, ProcessingResult, QualityMetrics

Example Usage:
    >>> from semantica.utils import setup_logging, get_logger
    >>> logger = setup_logging(level="INFO")
    >>> module_logger = get_logger(__name__)
    >>> 
    >>> from semantica.utils import ValidationError, validate_entity
    >>> entity = {"id": "e1", "text": "John Doe", "type": "PERSON"}
    >>> is_valid, error = validate_entity(entity)
    >>> 
    >>> from semantica.utils import clean_text, merge_dicts
    >>> cleaned = clean_text("  Hello   World  ")
    >>> merged = merge_dicts({"a": 1}, {"b": 2})

Author: Semantica Contributors
License: MIT
"""

from .constants import (
    API_ENDPOINTS,
    CACHE_CONFIG,
    DATA_TYPES,
    DEFAULT_CONFIG,
    ENTITY_TYPES,
    ERROR_CODES,
    FILE_SIZE_LIMITS,
    PERFORMANCE_THRESHOLDS,
    PROCESSING_STATUS,
    QUALITY_LEVELS,
    RELATIONSHIP_TYPES,
    RETRY_CONFIG,
    SUPPORTED_AUDIO_FORMATS,
    SUPPORTED_DOCUMENT_FORMATS,
    SUPPORTED_GRAPH_DBS,
    SUPPORTED_IMAGE_FORMATS,
    SUPPORTED_RDF_FORMATS,
    SUPPORTED_VECTOR_STORES,
    SUPPORTED_VIDEO_FORMATS,
)
from .exceptions import (
    ConfigurationError,
    ProcessingError,
    QualityError,
    SemanticaError,
    TemporalValidationError,
    ValidationError,
    format_exception,
    handle_exception,
)
from .helpers import (
    chunk_list,
    clean_text,
    ensure_directory,
    flatten_dict,
    format_data,
    format_timestamp,
    get_file_size,
    get_nested_value,
    hash_data,
    merge_dicts,
    normalize_entities,
    normalize_graph_payload,
    parse_timestamp,
    read_json_file,
    retry_on_error,
    safe_filename,
    safe_import,
    set_nested_value,
    write_json_file,
)
from .logging import (
    get_logger,
    log_data_quality,
    log_error,
    log_execution_time,
    log_performance,
    setup_logging,
)
from .progress_tracker import (
    ConsoleProgressDisplay,
    FileProgressDisplay,
    JupyterProgressDisplay,
    ModuleDetector,
    ProgressDisplay,
    ProgressItem,
    ProgressTracker,
    get_progress_tracker,
    track_progress,
)
from .types import (  # Type Aliases; Enums; Data Classes; Generic Types; Type Guards; Conversion Functions
    BatchResult,
    ConfigDict,
    DataDict,
    DataType,
    Entity,
    EntityDict,
    EntityType,
    JSONType,
    ProcessingResult,
    ProcessingStatus,
    QualityLevel,
    QualityMetrics,
    Relationship,
    RelationshipDict,
    RelationshipType,
    Result,
    dict_to_entity,
    dict_to_relationship,
    entity_to_dict,
    is_entity_dict,
    is_processing_result,
    is_relationship_dict,
    relationship_to_dict,
)
from .validators import (
    validate_config,
    validate_data,
    validate_email,
    validate_entity,
    validate_file_path,
    validate_list_constraints,
    validate_numeric_constraints,
    validate_relationship,
    validate_required_fields,
    validate_schema,
    validate_string_constraints,
    validate_types,
    validate_url,
)

__all__ = [
    # Logging
    "setup_logging",
    "get_logger",
    "log_performance",
    "log_error",
    "log_data_quality",
    "log_execution_time",
    # Exceptions
    "SemanticaError",
    "ValidationError",
    "TemporalValidationError",
    "ProcessingError",
    "ConfigurationError",
    "QualityError",
    "handle_exception",
    "format_exception",
    # Validators
    "validate_data",
    "validate_config",
    "validate_schema",
    "validate_types",
    "validate_required_fields",
    "validate_string_constraints",
    "validate_numeric_constraints",
    "validate_list_constraints",
    "validate_entity",
    "validate_relationship",
    "validate_file_path",
    "validate_url",
    "validate_email",
    # Helpers
    "format_data",
    "clean_text",
    "normalize_entities",
    "normalize_graph_payload",
    "hash_data",
    "safe_filename",
    "ensure_directory",
    "read_json_file",
    "write_json_file",
    "get_file_size",
    "format_timestamp",
    "parse_timestamp",
    "merge_dicts",
    "chunk_list",
    "flatten_dict",
    "get_nested_value",
    "set_nested_value",
    "retry_on_error",
    "safe_import",
    # Constants
    "SUPPORTED_DOCUMENT_FORMATS",
    "SUPPORTED_IMAGE_FORMATS",
    "SUPPORTED_AUDIO_FORMATS",
    "SUPPORTED_VIDEO_FORMATS",
    "SUPPORTED_RDF_FORMATS",
    "SUPPORTED_VECTOR_STORES",
    "SUPPORTED_GRAPH_DBS",
    "DEFAULT_CONFIG",
    "ERROR_CODES",
    "PERFORMANCE_THRESHOLDS",
    "QUALITY_LEVELS",
    "ENTITY_TYPES",
    "RELATIONSHIP_TYPES",
    "PROCESSING_STATUS",
    "DATA_TYPES",
    "API_ENDPOINTS",
    "FILE_SIZE_LIMITS",
    "RETRY_CONFIG",
    "CACHE_CONFIG",
    # Types
    "JSONType",
    "EntityDict",
    "RelationshipDict",
    "ConfigDict",
    "DataDict",
    "EntityType",
    "DataType",
    "ProcessingStatus",
    "QualityLevel",
    "RelationshipType",
    "Entity",
    "Relationship",
    "ProcessingResult",
    "QualityMetrics",
    "Result",
    "BatchResult",
    "is_entity_dict",
    "is_relationship_dict",
    "is_processing_result",
    "entity_to_dict",
    "dict_to_entity",
    "relationship_to_dict",
    "dict_to_relationship",
    # Progress Tracking
    "ProgressTracker",
    "ProgressDisplay",
    "ConsoleProgressDisplay",
    "JupyterProgressDisplay",
    "FileProgressDisplay",
    "ProgressItem",
    "ModuleDetector",
    "get_progress_tracker",
    "track_progress",
]
