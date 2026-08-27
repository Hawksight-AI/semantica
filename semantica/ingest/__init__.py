"""
Data Ingestion Module

This module provides comprehensive data ingestion capabilities from various sources
including files, web content, feeds, streams, repositories, emails, and databases.

Algorithms Used:

File Ingestion:
    - File Type Detection: Multi-method detection using extension,
      MIME type, and magic number analysis
    - Directory Scanning: Recursive directory traversal with filtering
    - Cloud Storage Integration: AWS S3, Google Cloud Storage, Azure Blob
      Storage API integration
    - File Validation: Size limits, format validation, content verification
    - Batch Processing: Parallel file processing with progress tracking
    - Magic Number Analysis: Binary file signature detection for accurate
      type identification

Web Ingestion:
    - HTTP Request Handling: GET/POST requests with retry logic and error handling
    - Rate Limiting: Time-based delay enforcement between requests
    - Robots.txt Compliance: RobotFileParser-based robots.txt checking and URL filtering
    - Content Extraction: BeautifulSoup-based HTML parsing and text extraction
    - Sitemap Crawling: XML sitemap parsing and URL discovery
    - Link Discovery: HTML link extraction and domain filtering
    - JavaScript Rendering: Optional Selenium/Playwright integration for dynamic content
    - URL Normalization: URL parsing, joining, and canonicalization

Feed Ingestion:
    - RSS/Atom Parsing: XML parsing with format auto-detection
    - Feed Discovery: HTML link tag parsing for feed discovery
    - Date Parsing: Multiple date format parsing (RFC 822, ISO 8601, etc.)
    - Feed Validation: XML schema validation and format verification
    - Update Monitoring: Polling-based feed update detection with callbacks
    - Content Extraction: Feed item content and metadata extraction

Stream Ingestion:
    - Kafka Processing: Kafka consumer group management and message processing
    - RabbitMQ Processing: AMQP protocol handling and queue management
    - AWS Kinesis Processing: Kinesis stream reading and shard management
    - Apache Pulsar Processing: Pulsar consumer and subscription management
    - Message Transformation: Custom transformation pipeline for stream messages
    - Error Handling: Retry logic, dead letter queue handling, error recovery
    - Stream Monitoring: Health checks, metrics collection, performance monitoring
    - Partition Management: Partition assignment and load balancing

Repository Ingestion:
    - Git Operations: Repository cloning, branch checking, commit traversal
    - Code Extraction: File content extraction with language detection
    - Commit Analysis: Git log parsing, diff analysis, statistics calculation
    - Language Detection: File extension and content-based programming
      language identification
    - Code Structure Analysis: AST parsing for classes, functions, imports extraction
    - Dependency Analysis: Package manager file parsing
      (requirements.txt, package.json, etc.)
    - Documentation Extraction: README, docstring, and comment extraction

Email Ingestion:
    - IMAP Protocol: IMAP connection, mailbox selection, message retrieval
    - POP3 Protocol: POP3 connection and message downloading
    - Email Parsing: RFC 822 email message parsing with header and body extraction
    - Attachment Processing: MIME attachment extraction and file saving
    - Content Extraction: Plain text and HTML body extraction with BeautifulSoup
    - Thread Analysis: Message-ID and In-Reply-To header-based conversation threading
    - Link Extraction: URL extraction from email HTML content

Database Ingestion:
    - Database Connection: SQLAlchemy-based connection management with
      connection pooling
    - SQL Query Execution: Parameterized query execution with result set processing
    - Schema Introspection: Database schema analysis and table/column discovery
    - Data Type Conversion: Database-specific type to Python type conversion
    - Pagination: Large dataset processing with LIMIT/OFFSET or cursor-based pagination
    - Data Export: Result set to dictionary/JSON conversion
    - Multi-database Support: PostgreSQL, MySQL, SQLite, Oracle, SQL Server abstraction

Key Features:
    - Multiple ingestion source types (file, web, public API, feed, stream,
      repo, email, db)
    - Unified ingestion function with source type dispatch
    - Method registry for extensibility
    - Configuration management with environment variables and config files
    - Batch processing and progress tracking
    - Error handling and retry logic
    - Content extraction and transformation

Main Classes:
    - FileIngestor: Local and cloud file processing
    - WebIngestor: Web scraping and crawling
    - PublicAPIIngestor: No-auth public REST API processing
    - FeedIngestor: RSS/Atom feed processing
    - StreamIngestor: Real-time stream processing
    - RepoIngestor: Git repository processing
    - EmailIngestor: Email protocol handling
    - DBIngestor: Database export handling
    - OntologyIngestor: Ontology file processing
    - ParquetIngestor: Apache Parquet file and partitioned dataset processing
    - ArrowIngestor: Apache Arrow IPC and Feather file processing
    - XMLIngestor: XML file parsing, validation, and metadata extraction
    - MethodRegistry: Registry for custom ingestion methods
    - IngestConfig: Configuration manager for ingest module

Convenience Functions:
    - ingest: Unified ingestion function with source type dispatch
    - ingest_file: File ingestion wrapper
    - ingest_web: Web ingestion wrapper
    - ingest_public_api: Public API ingestion wrapper
    - ingest_feed: Feed ingestion wrapper
    - ingest_stream: Stream ingestion wrapper
    - ingest_repository: Repository ingestion wrapper
    - ingest_email: Email ingestion wrapper
    - ingest_database: Database ingestion wrapper
    - ingest_ontology: Ontology ingestion wrapper
    - ingest_parquet: Parquet ingestion wrapper
    - ingest_arrow: Arrow IPC/Feather ingestion wrapper
    - ingest_xml: XML ingestion wrapper


Example Usage:
    >>> from semantica.ingest import ingest, ingest_file, ingest_web
    >>> # Unified ingestion
    >>> result = ingest("document.pdf", source_type="file")
    >>> # File ingestion
    >>> files = ingest_file("./documents", method="directory")
    >>> # Web ingestion
    >>> content = ingest_web("https://example.com", method="url")
"""

from __future__ import annotations

import importlib
from typing import Any, Dict, Tuple

from .config import IngestConfig, ingest_config
from .file_ingestor import (
    CloudStorageIngestor,
    FileIngestor,
    FileObject,
    FileTypeDetector,
)
from .methods import (
    get_ingest_method,
    ingest,
    ingest_arrow,
    ingest_database,
    ingest_email,
    ingest_feed,
    ingest_file,
    ingest_mcp,
    ingest_ontology,
    ingest_parquet,
    ingest_public_api,
    ingest_repository,
    ingest_salesforce,
    ingest_stream,
    ingest_web,
    ingest_xml,
    list_available_methods,
)
from .registry import MethodRegistry, method_registry

_LAZY_EXPORTS: Dict[str, Tuple[str, str]] = {
    # Web ingestion
    "WebIngestor": (".web_ingestor", "WebIngestor"),
    "WebContent": (".web_ingestor", "WebContent"),
    "RateLimiter": (".web_ingestor", "RateLimiter"),
    "RobotsChecker": (".web_ingestor", "RobotsChecker"),
    "ContentExtractor": (".web_ingestor", "ContentExtractor"),
    "SitemapCrawler": (".web_ingestor", "SitemapCrawler"),
    # REST and public API ingestion
    "RESTIngestor": (".api_ingestor", "RESTIngestor"),
    "APIData": (".api_ingestor", "APIData"),
    "PublicAPIIngestor": (".public_api_ingestor", "PublicAPIIngestor"),
    "PublicAPIExample": (".public_api_ingestor", "PublicAPIExample"),
    "PublicAPIExamples": (".public_api_ingestor", "PublicAPIExamples"),
    "PublicAPIDetection": (".public_api_ingestor", "PublicAPIDetection"),
    # Feed ingestion
    "FeedIngestor": (".feed_ingestor", "FeedIngestor"),
    "FeedItem": (".feed_ingestor", "FeedItem"),
    "FeedData": (".feed_ingestor", "FeedData"),
    "FeedParser": (".feed_ingestor", "FeedParser"),
    "FeedMonitor": (".feed_ingestor", "FeedMonitor"),
    # Stream ingestion
    "StreamIngestor": (".stream_ingestor", "StreamIngestor"),
    "StreamMessage": (".stream_ingestor", "StreamMessage"),
    "StreamProcessor": (".stream_ingestor", "StreamProcessor"),
    "KafkaProcessor": (".stream_ingestor", "KafkaProcessor"),
    "RabbitMQProcessor": (".stream_ingestor", "RabbitMQProcessor"),
    "KinesisProcessor": (".stream_ingestor", "KinesisProcessor"),
    "PulsarProcessor": (".stream_ingestor", "PulsarProcessor"),
    "StreamMonitor": (".stream_ingestor", "StreamMonitor"),
    # Repository ingestion
    "RepoIngestor": (".repo_ingestor", "RepoIngestor"),
    "CodeFile": (".repo_ingestor", "CodeFile"),
    "CommitInfo": (".repo_ingestor", "CommitInfo"),
    "CodeExtractor": (".repo_ingestor", "CodeExtractor"),
    "GitAnalyzer": (".repo_ingestor", "GitAnalyzer"),
    # Email ingestion
    "EmailIngestor": (".email_ingestor", "EmailIngestor"),
    "EmailData": (".email_ingestor", "EmailData"),
    "AttachmentProcessor": (".email_ingestor", "AttachmentProcessor"),
    "EmailIngestorParser": (".email_ingestor", "EmailParser"),
    # Database ingestion
    "DBIngestor": (".db_ingestor", "DBIngestor"),
    "TableData": (".db_ingestor", "TableData"),
    "DatabaseConnector": (".db_ingestor", "DatabaseConnector"),
    "DataExporter": (".db_ingestor", "DataExporter"),
    # MCP ingestion
    "MCPIngestor": (".mcp_ingestor", "MCPIngestor"),
    "MCPData": (".mcp_ingestor", "MCPData"),
    "MCPClient": (".mcp_client", "MCPClient"),
    "MCPResource": (".mcp_client", "MCPResource"),
    "MCPTool": (".mcp_client", "MCPTool"),
    # Ontology ingestion
    "OntologyIngestor": (".ontology_ingestor", "OntologyIngestor"),
    "OntologyData": (".ontology_ingestor", "OntologyData"),
    # Snowflake ingestion
    "SnowflakeIngestor": (".snowflake_ingestor", "SnowflakeIngestor"),
    "SnowflakeData": (".snowflake_ingestor", "SnowflakeData"),
    "SnowflakeConnector": (".snowflake_ingestor", "SnowflakeConnector"),
    # Databricks ingestion
    "DatabricksIngestor": (".databricks_ingestor", "DatabricksIngestor"),
    "DatabricksData": (".databricks_ingestor", "DatabricksData"),
    "DatabricksConnector": (".databricks_ingestor", "DatabricksConnector"),
    # Parquet ingestion
    "ParquetIngestor": (".parquet_ingestor", "ParquetIngestor"),
    "ParquetData": (".parquet_ingestor", "ParquetData"),
    # Arrow IPC / Feather ingestion
    "ArrowIngestor": (".arrow_ingestor", "ArrowIngestor"),
    "ArrowData": (".arrow_ingestor", "ArrowData"),
    # XML ingestion
    "XMLIngestor": (".xml_ingestor", "XMLIngestor"),
    "XMLIngestionData": (".xml_ingestor", "XMLIngestionData"),
    # Salesforce ingestion
    "SalesforceIngestor": (".salesforce_ingestor", "SalesforceIngestor"),
    "SalesforceData": (".salesforce_ingestor", "SalesforceData"),
    "SalesforceConnector": (".salesforce_ingestor", "SalesforceConnector"),
}

_OPTIONAL_DEPENDENCY_MESSAGES = {
    ".repo_ingestor": (
        "Repository ingestion requires optional dependency 'GitPython'. "
        "Install it before importing RepoIngestor or using ingest_repository()."
    ),
    ".web_ingestor": (
        "Web ingestion requires optional dependency 'beautifulsoup4'. "
        "Install it before importing WebIngestor or using ingest_web()."
    ),
    ".feed_ingestor": (
        "Feed ingestion requires optional dependency 'beautifulsoup4'. "
        "Install it before importing FeedIngestor or using ingest_feed()."
    ),
    ".email_ingestor": (
        "Email ingestion requires optional dependency 'beautifulsoup4'. "
        "Install it before importing EmailIngestor or using ingest_email()."
    ),
    ".parquet_ingestor": (
        "Parquet ingestion requires optional dependency 'pyarrow'. "
        "Install it before importing ParquetIngestor or using ingest_parquet()."
    ),
    ".arrow_ingestor": (
        "Arrow ingestion requires optional dependency 'pyarrow'. "
        "Install it before importing ArrowIngestor or using ingest_arrow()."
    ),
    ".salesforce_ingestor": (
        "Salesforce ingestion requires optional dependency 'simple-salesforce'. "
        "Install it with: pip install \"semantica[db-salesforce]\" "
        "or: pip install simple-salesforce>=1.12.0"
    ),
}


def __getattr__(name: str) -> Any:
    """Load optional ingestion backends only when callers request them."""
    if name not in _LAZY_EXPORTS:
        raise AttributeError(f"module {__name__!r} has no attribute {name!r}")

    module_name, attr_name = _LAZY_EXPORTS[name]
    try:
        module = importlib.import_module(module_name, __name__)
    except ModuleNotFoundError as exc:
        message = _OPTIONAL_DEPENDENCY_MESSAGES.get(module_name)
        missing_name = getattr(exc, "name", None)
        if message and missing_name in {"git", "bs4", "pyarrow", "simple_salesforce"}:
            raise ImportError(message) from exc
        raise

    value = getattr(module, attr_name)
    globals()[name] = value
    return value


__all__ = [
    # File ingestion
    "FileIngestor",
    "FileObject",
    "FileTypeDetector",
    "CloudStorageIngestor",
    # Web ingestion
    "WebIngestor",
    "WebContent",
    "RateLimiter",
    "RobotsChecker",
    "ContentExtractor",
    "SitemapCrawler",
    # REST and public API ingestion
    "RESTIngestor",
    "APIData",
    "PublicAPIIngestor",
    "PublicAPIExample",
    "PublicAPIExamples",
    "PublicAPIDetection",
    # Feed ingestion
    "FeedIngestor",
    "FeedItem",
    "FeedData",
    "FeedParser",
    "FeedMonitor",
    # Stream ingestion
    "StreamIngestor",
    "StreamMessage",
    "StreamProcessor",
    "KafkaProcessor",
    "RabbitMQProcessor",
    "KinesisProcessor",
    "PulsarProcessor",
    "StreamMonitor",
    # Repository ingestion
    "RepoIngestor",
    "CodeFile",
    "CommitInfo",
    "CodeExtractor",
    "GitAnalyzer",
    # Email ingestion
    "EmailIngestor",
    "EmailData",
    "AttachmentProcessor",
    "EmailIngestorParser",
    # Database ingestion
    "DBIngestor",
    "TableData",
    "DatabaseConnector",
    "DataExporter",
    # MCP ingestion
    "MCPIngestor",
    "MCPData",
    "MCPClient",
    "MCPResource",
    "MCPTool",
    # Ontology ingestion
    "OntologyIngestor",
    "OntologyData",
    # Snowflake ingestion
    "SnowflakeIngestor",
    "SnowflakeData",
    "SnowflakeConnector",
    # Databricks ingestion
    "DatabricksIngestor",
    "DatabricksData",
    "DatabricksConnector",
    # Parquet ingestion
    "ParquetIngestor",
    "ParquetData",
    # Arrow IPC / Feather ingestion
    "ArrowIngestor",
    "ArrowData",
    # XML ingestion
    "XMLIngestor",
    "XMLIngestionData",
    # Salesforce ingestion
    "SalesforceIngestor",
    "SalesforceData",
    "SalesforceConnector",
    # Registry and Methods
    "MethodRegistry",
    "method_registry",
    "ingest",
    "ingest_file",
    "ingest_web",
    "ingest_feed",
    "ingest_stream",
    "ingest_repository",
    "ingest_email",
    "ingest_database",
    "ingest_salesforce",
    "ingest_ontology",
    "ingest_arrow",
    "ingest_parquet",
    "ingest_public_api",
    "ingest_xml",
    "ingest_mcp",
    "get_ingest_method",
    "list_available_methods",
    # Configuration
    "IngestConfig",
    "ingest_config",
]
