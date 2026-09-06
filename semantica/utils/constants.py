"""
Constants and Configuration Module

This module provides constants and configuration values for the Semantica framework,
including supported file formats, default configurations, error codes, performance
thresholds, and framework-wide constants.

Key Features:
    - Supported file format definitions (documents, images, audio, video, RDF)
    - Vector store and graph database backends
    - Default configuration templates
    - Error code definitions
    - Performance and quality thresholds
    - Entity and relationship type definitions
    - Processing status and data type enumerations

Main Constants:
    - SUPPORTED_DOCUMENT_FORMATS: List of supported document formats
    - SUPPORTED_IMAGE_FORMATS: List of supported image formats
    - SUPPORTED_AUDIO_FORMATS: List of supported audio formats
    - SUPPORTED_VIDEO_FORMATS: List of supported video formats
    - SUPPORTED_RDF_FORMATS: List of supported RDF serialization formats
    - SUPPORTED_VECTOR_STORES: List of supported vector store backends
    - SUPPORTED_GRAPH_DBS: List of supported graph database backends
    - DEFAULT_CONFIG: Default framework configuration
    - ERROR_CODES: Error code mappings
    - PERFORMANCE_THRESHOLDS: Performance limit definitions
    - QUALITY_LEVELS: Quality score thresholds
    - ENTITY_TYPES: Available entity type definitions
    - RELATIONSHIP_TYPES: Available relationship type definitions

Example Usage:
    >>> from semantica.utils import SUPPORTED_DOCUMENT_FORMATS, DEFAULT_CONFIG
    >>> if file_extension in SUPPORTED_DOCUMENT_FORMATS:
    ...     process_document(file_path)
    >>>
    >>> config = DEFAULT_CONFIG.copy()
    >>> config["processing"]["batch_size"] = 200
    >>>
    >>> from semantica.utils import ERROR_CODES, PERFORMANCE_THRESHOLDS
    >>> error_code = ERROR_CODES["VALIDATION_ERROR"]
    >>> max_time = PERFORMANCE_THRESHOLDS["max_processing_time"]

Author: Semantica Contributors
License: MIT
"""

# Supported Data Formats
SUPPORTED_DOCUMENT_FORMATS = [
    "pdf",
    "docx",
    "doc",
    "txt",
    "html",
    "xml",
    "json",
    "jsonl",
    "ndjson",
    "csv",
    "xlsx",
    "pptx",
    "parquet",
    "pq",
    "arrow",
    "feather",
    "ipc",
]

SUPPORTED_IMAGE_FORMATS = ["jpg", "jpeg", "png", "gif", "bmp", "tiff", "webp", "svg"]

SUPPORTED_AUDIO_FORMATS = ["mp3", "wav", "flac", "aac", "ogg", "wma", "m4a"]

SUPPORTED_VIDEO_FORMATS = ["mp4", "avi", "mov", "wmv", "flv", "webm", "mkv"]

# Supported RDF Formats
SUPPORTED_RDF_FORMATS = ["turtle", "rdfxml", "jsonld", "n3", "ntriples"]

# Supported Vector Store Backends
SUPPORTED_VECTOR_STORES = [
    "faiss",
    "weaviate",
    "qdrant",
    "milvus",
    "chroma",
    "sqlite",
]

# Supported Graph Databases
SUPPORTED_GRAPH_DBS = [
    "neo4j",
    "blazegraph",
    "apache_jena",
    "allegrograph",
    "amazon_neptune",
]

# Default Configuration
DEFAULT_CONFIG = {
    "logging": {
        "level": "INFO",
        "format": "%(asctime)s - %(name)s - %(levelname)s - %(message)s",
        "file": "semantica.log",
    },
    "processing": {"batch_size": 100, "max_workers": 4, "timeout": 300},
    "quality": {"min_confidence": 0.7, "max_errors": 10, "validation_enabled": True},
    "security": {
        "encryption_enabled": False,
        "access_control_enabled": True,
        "audit_logging_enabled": True,
    },
}

# Error Codes
ERROR_CODES = {
    "VALIDATION_ERROR": "SEM001",
    "PROCESSING_ERROR": "SEM002",
    "CONFIGURATION_ERROR": "SEM003",
    "QUALITY_ERROR": "SEM004",
    "SECURITY_ERROR": "SEM005",
    "NETWORK_ERROR": "SEM006",
    "STORAGE_ERROR": "SEM007",
    "PERMISSION_ERROR": "SEM008",
}

# Performance Thresholds
PERFORMANCE_THRESHOLDS = {
    "max_processing_time": 3600,  # 1 hour
    "max_memory_usage": 8192,  # 8GB
    "max_file_size": 104857600,  # 100MB
    "max_batch_size": 1000,
    "min_quality_score": 0.7,
}

# Quality Levels
QUALITY_LEVELS = {"HIGH": 0.9, "MEDIUM": 0.7, "LOW": 0.5, "POOR": 0.3}

# Entity Types
ENTITY_TYPES = [
    "PERSON",
    "ORGANIZATION",
    "LOCATION",
    "EVENT",
    "PRODUCT",
    "CONCEPT",
    "DATE",
    "TIME",
    "MONEY",
    "PERCENT",
    "QUANTITY",
    "ORDINAL",
    "CARDINAL",
]

# Relationship Types
RELATIONSHIP_TYPES = [
    "WORKS_FOR",
    "LOCATED_IN",
    "PART_OF",
    "RELATED_TO",
    "CAUSES",
    "AFFECTS",
    "BEFORE",
    "AFTER",
    "DURING",
    "SAME_AS",
    "DIFFERENT_FROM",
    "SIMILAR_TO",
]

# Processing Status
PROCESSING_STATUS = {
    "PENDING": "pending",
    "PROCESSING": "processing",
    "COMPLETED": "completed",
    "FAILED": "failed",
    "CANCELLED": "cancelled",
}

# Data Types
DATA_TYPES = {
    "TEXT": "text",
    "IMAGE": "image",
    "AUDIO": "audio",
    "VIDEO": "video",
    "DOCUMENT": "document",
    "STRUCTURED": "structured",
    "UNSTRUCTURED": "unstructured",
}

# API Endpoints
API_ENDPOINTS = {
    "BASE_URL": "https://api.semantica.dev",
    "VERSION": "v1",
    "ENDPOINTS": {
        "PROCESS": "/process",
        "EXTRACT": "/extract",
        "ANALYZE": "/analyze",
        "EXPORT": "/export",
        "STATUS": "/status",
    },
}

# File Size Limits
FILE_SIZE_LIMITS = {
    "MAX_DOCUMENT_SIZE": 104857600,  # 100MB
    "MAX_IMAGE_SIZE": 52428800,  # 50MB
    "MAX_AUDIO_SIZE": 104857600,  # 100MB
    "MAX_VIDEO_SIZE": 524288000,  # 500MB
    "MAX_BATCH_SIZE": 1000,
}

# Retry Configuration
RETRY_CONFIG = {
    "MAX_RETRIES": 3,
    "RETRY_DELAY": 1,  # seconds
    "BACKOFF_FACTOR": 2,
    "MAX_DELAY": 60,  # seconds
}

# Cache Configuration
CACHE_CONFIG = {
    "ENABLED": True,
    "TTL": 3600,  # 1 hour
    "MAX_SIZE": 1000,
    "CLEANUP_INTERVAL": 300,  # 5 minutes
}
