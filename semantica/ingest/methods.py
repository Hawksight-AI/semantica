"""
Ingestion Methods Module

This module provides all ingestion methods as simple, reusable functions for
ingesting data from various sources including files, web, feeds, streams, repositories,
emails, and databases. It supports multiple ingestion approaches and integrates with
the method registry for extensibility.

Supported Methods:

File Ingestion:
    - "file": File ingestion from local filesystem
    - "directory": Directory ingestion with recursive scanning
    - "cloud": Cloud storage ingestion (S3, GCS, Azure)

Parquet Ingestion:
    - "file": Single Parquet file ingestion
    - "directory": Partitioned Parquet directory ingestion
    - "schema": Parquet schema extraction
    - "metadata": Parquet file or directory metadata extraction

Arrow IPC / Feather Ingestion:
    - "file": Single Arrow IPC or Feather file ingestion
    - "schema": Arrow schema extraction
    - "metadata": Arrow file metadata extraction

XML Ingestion:
    - "file": Single XML file ingestion with structured parsing
    - "directory": Directory ingestion for XML files
    - "metadata": XML structure and namespace metadata extraction
    - "validate": XSD and DTD validation report

Web Ingestion:
    - "url": Single URL ingestion
    - "sitemap": Sitemap-based crawling
    - "crawl": Domain crawling

Public API Ingestion:
    - "endpoint": No-auth public API endpoint ingestion
    - "example": Pre-configured public API examples
    - "detect": Endpoint-level public/no-auth detection
    - "batch": Multiple no-auth public API endpoints

Feed Ingestion:
    - "rss": RSS feed ingestion
    - "atom": Atom feed ingestion
    - "discover": Feed discovery from websites

Stream Ingestion:
    - "kafka": Kafka stream ingestion
    - "rabbitmq": RabbitMQ stream ingestion
    - "kinesis": AWS Kinesis stream ingestion
    - "pulsar": Apache Pulsar stream ingestion

Repository Ingestion:
    - "git": Git repository ingestion
    - "clone": Repository cloning
    - "analyze": Repository analysis

Email Ingestion:
    - "imap": IMAP email ingestion
    - "pop3": POP3 email ingestion

Database Ingestion:
    - "postgresql": PostgreSQL database ingestion
    - "mysql": MySQL database ingestion
    - "sqlite": SQLite database ingestion
    - "oracle": Oracle database ingestion
    - "mssql": SQL Server database ingestion

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
    - Multiple ingestion source types
    - Unified ingestion function with source type dispatch
    - Method dispatchers with registry support
    - Custom method registration capability
    - Consistent interface across all methods

Main Functions:
    - ingest_file: File ingestion wrapper
    - ingest_web: Web ingestion wrapper
    - ingest_public_api: No-auth public API ingestion wrapper
    - ingest_feed: Feed ingestion wrapper
    - ingest_stream: Stream ingestion wrapper
    - ingest_repository: Repository ingestion wrapper
    - ingest_email: Email ingestion wrapper
    - ingest_database: Database ingestion wrapper
    - ingest_parquet: Parquet ingestion wrapper
    - ingest_arrow: Arrow IPC / Feather ingestion wrapper
    - ingest_xml: XML ingestion wrapper
    - ingest: Unified ingestion function with source type dispatch
    - get_ingest_method: Get ingestion method by name
    - list_available_methods: List registered methods

Example Usage:
    >>> from semantica.ingest.methods import ingest, ingest_file, ingest_web
    >>> # Unified ingestion
    >>> result = ingest("document.pdf", source_type="file")
    >>> # File ingestion
    >>> files = ingest_file("./documents", method="directory")
    >>> # Web ingestion
    >>> content = ingest_web("https://example.com", method="url")
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import TYPE_CHECKING, Any, Callable, Dict, List, Optional, Union

from ..utils.exceptions import ConfigurationError, ProcessingError
from ..utils.logging import get_logger
from .config import ingest_config
from .file_ingestor import FileIngestor, FileObject
from .registry import method_registry

# SCP-like SSH remotes (user@host:path) — keep in sync with repo_ingestor
_SCP_LIKE_REPO_URL_RE = re.compile(r"^[^@\s]+@[^:\s]+:.+$")


def _is_scp_like_repo_source(source: str) -> bool:
    """Return True for scp-like SSH remotes (``user@host:path``)."""
    return bool(_SCP_LIKE_REPO_URL_RE.match(source.strip()))

if TYPE_CHECKING:
    from .api_ingestor import APIData
    from .arrow_ingestor import ArrowData
    from .db_ingestor import TableData
    from .email_ingestor import EmailData
    from .feed_ingestor import FeedData
    from .mcp_ingestor import MCPData
    from .ontology_ingestor import OntologyData
    from .parquet_ingestor import ParquetData
    from .public_api_ingestor import PublicAPIDetection
    from .stream_ingestor import StreamProcessor
    from .web_ingestor import WebContent
    from .xml_ingestor import XMLIngestionData

logger = get_logger("ingest_methods")


def _missing_optional_dependency(feature: str, package: str) -> ConfigurationError:
    return ConfigurationError(
        f"{feature} requires optional dependency '{package}'. "
        f"Install it before using this ingestion backend."
    )


def _is_missing_dependency(exc: ModuleNotFoundError, *dependency_names: str) -> bool:
    missing_name = getattr(exc, "name", None)
    return missing_name in dependency_names


def ingest_file(
    source: Union[str, Path, List[Union[str, Path]]], method: str = "file", **kwargs
) -> Union[FileObject, List[FileObject], Dict[str, Any]]:
    """
    Ingest files from source (convenience function).

    This is a user-friendly wrapper that ingests files using the specified method.

    Args:
        source: File path, directory path, or list of paths
        method: Ingestion method (default: "file")
            - "file": Single file ingestion
            - "directory": Directory ingestion with recursive scanning
            - "cloud": Cloud storage ingestion
        **kwargs: Additional options passed to FileIngestor

    Returns:
        FileObject, List[FileObject], or Dict with ingestion results

    Examples:
        >>> from semantica.ingest.methods import ingest_file
        >>> file_obj = ingest_file("document.pdf", method="file")
        >>> files = ingest_file("./documents", method="directory", recursive=True)
    """
    # Check for custom method in registry
    custom_method = method_registry.get("file", method)
    if custom_method and custom_method != ingest_file:
        try:
            return custom_method(source, **kwargs)
        except Exception as e:
            logger.warning(
                f"Custom method {method} failed: {e}, falling back to default"
            )

    try:
        # Get config
        config = ingest_config.get_method_config("file")
        config.update(kwargs)

        ingestor = FileIngestor(**config)

        source_path = Path(source) if isinstance(source, (str, Path)) else None

        if method == "file" and source_path and source_path.is_file():
            return ingestor.ingest_file(source_path, **kwargs)
        elif method == "directory" or (source_path and source_path.is_dir()):
            recursive = kwargs.get("recursive", ingest_config.get("recursive", True))
            return ingestor.ingest_directory(
                source_path or source, recursive=recursive, **kwargs
            )
        elif method == "cloud":
            from .file_ingestor import CloudStorageIngestor

            provider = kwargs.get("provider", "s3")
            cloud_ingestor = CloudStorageIngestor(provider=provider, **config)
            return cloud_ingestor.ingest(source, **kwargs)
        else:
            # Default: try as file
            return ingestor.ingest_file(source, **kwargs)

    except Exception as e:
        logger.error(f"Failed to ingest file: {e}")
        raise


def ingest_parquet(
    source: Union[str, Path, List[Union[str, Path]]],
    method: str = "file",
    **kwargs,
) -> Union[ParquetData, List[ParquetData], Dict[str, Any]]:
    """
    Ingest Apache Parquet files or partitioned directories.

    Args:
        source: Parquet file path, directory path, or list of paths
        method: Ingestion method:
            - "file": Single Parquet file ingestion
            - "directory": Parquet directory or partitioned dataset ingestion
            - "schema": Extract schema without reading data
            - "metadata": Extract file/directory metadata without reading data
        **kwargs: Additional options passed to ParquetIngestor

    Returns:
        ParquetData, list of ParquetData, or metadata/schema dictionary

    Examples:
        >>> from semantica.ingest.methods import ingest_parquet
        >>> data = ingest_parquet("events.parquet", columns=["id"], limit=100)
        >>> schema = ingest_parquet("events.parquet", method="schema")
        >>> dataset = ingest_parquet("./events_by_date", method="directory")
    """
    custom_method = method_registry.get("parquet", method)
    if custom_method and custom_method != ingest_parquet:
        try:
            return custom_method(source, **kwargs)
        except Exception as e:
            logger.warning(
                f"Custom method {method} failed: {e}, falling back to default"
            )

    try:
        try:
            from .parquet_ingestor import ParquetIngestor
        except ModuleNotFoundError as exc:
            if _is_missing_dependency(exc, "pyarrow"):
                raise _missing_optional_dependency(
                    "Parquet ingestion",
                    "pyarrow",
                ) from exc
            raise

        config = ingest_config.get_method_config("parquet")
        config.update(kwargs)
        try:
            ingestor = ParquetIngestor(**config)
        except ImportError as exc:
            raise _missing_optional_dependency(
                "Parquet ingestion",
                "pyarrow",
            ) from exc

        def _run_single(path: Union[str, Path]) -> Union[ParquetData, Dict[str, Any]]:
            source_path = Path(path)

            if method == "schema":
                return ingestor.extract_schema(source_path, **kwargs)
            if method == "metadata":
                return ingestor.extract_metadata(source_path, **kwargs)
            if method == "directory" or source_path.is_dir():
                return ingestor.ingest_directory(source_path, **kwargs)

            return ingestor.ingest_file(source_path, **kwargs)

        if isinstance(source, list):
            return [_run_single(path) for path in source]

        return _run_single(source)

    except ConfigurationError:
        raise
    except Exception as e:
        logger.error(f"Failed to ingest Parquet: {e}")
        raise


def ingest_arrow(
    source: Union[str, Path, List[Union[str, Path]]],
    method: str = "file",
    **kwargs,
) -> Union[ArrowData, List[ArrowData], Dict[str, Any]]:
    """
    Ingest Apache Arrow IPC or Feather files.

    Args:
        source: Arrow / Feather file path or list of paths
        method: Ingestion method:
            - "file": Single Arrow IPC / Feather file ingestion
            - "schema": Extract schema without reading data
            - "metadata": Extract file metadata without reading data
        **kwargs: Additional options passed to ArrowIngestor

    Returns:
        ArrowData, list of ArrowData, or metadata/schema dictionary

    Examples:
        >>> from semantica.ingest.methods import ingest_arrow
        >>> data = ingest_arrow("events.arrow", columns=["id"], limit=100)
        >>> schema = ingest_arrow("events.arrow", method="schema")
        >>> feather = ingest_arrow("data.feather")
    """
    custom_method = method_registry.get("arrow", method)
    if custom_method and custom_method != ingest_arrow:
        try:
            return custom_method(source, **kwargs)
        except Exception as e:
            logger.warning(
                f"Custom method {method} failed: {e}, falling back to default"
            )

    try:
        try:
            from .arrow_ingestor import ArrowIngestor
        except ModuleNotFoundError as exc:
            if _is_missing_dependency(exc, "pyarrow"):
                raise _missing_optional_dependency(
                    "Arrow ingestion",
                    "pyarrow",
                ) from exc
            raise

        config = ingest_config.get_method_config("arrow")
        config.update(kwargs)
        try:
            ingestor = ArrowIngestor(**config)
        except ImportError as exc:
            raise _missing_optional_dependency(
                "Arrow ingestion",
                "pyarrow",
            ) from exc

        def _run_single(path: Union[str, Path]) -> Union[ArrowData, Dict[str, Any]]:
            source_path = Path(path)

            if method == "schema":
                return ingestor.extract_schema(source_path, **kwargs)
            if method == "metadata":
                return ingestor.extract_metadata(source_path, **kwargs)

            return ingestor.ingest_file(source_path, **kwargs)

        if isinstance(source, list):
            return [_run_single(path) for path in source]

        return _run_single(source)

    except ConfigurationError:
        raise
    except Exception as e:
        logger.error(f"Failed to ingest Arrow: {e}")
        raise


def ingest_xml(
    source: Union[str, Path, List[Union[str, Path]]],
    method: str = "file",
    **kwargs,
) -> Union[
    XMLIngestionData,
    List[XMLIngestionData],
    Dict[str, Any],
    List[Dict[str, Any]],
]:
    """
    Ingest XML files from source (convenience function).

    Args:
        source: XML file path, directory path, or list of XML file paths
        method: Ingestion method:
            - "file": Single XML file ingestion
            - "directory": Directory ingestion with recursive scanning
            - "metadata": Extract XML metadata without returning the full tree
            - "validate": Return XSD/DTD validation report
        **kwargs: Additional options passed to XMLIngestor

    Returns:
        XMLIngestionData, list of XMLIngestionData, metadata dict, or validation dict

    Examples:
        >>> from semantica.ingest.methods import ingest_xml
        >>> data = ingest_xml("catalog.xml")
        >>> report = ingest_xml(
        ...     "catalog.xml", method="validate", schema_path="catalog.xsd"
        ... )
    """
    custom_method = method_registry.get("xml", method)
    if custom_method and custom_method != ingest_xml:
        try:
            return custom_method(source, **kwargs)
        except Exception as e:
            logger.warning(
                f"Custom method {method} failed: {e}, falling back to default"
            )

    try:
        from .xml_ingestor import XMLIngestor

        config = ingest_config.get_method_config("xml")
        config.update(kwargs)
        ingestor = XMLIngestor(**config)

        def _run_single(
            path: Union[str, Path],
        ) -> Union[XMLIngestionData, Dict[str, Any]]:
            if method == "metadata":
                return ingestor.extract_metadata(path, **kwargs)
            if method in {"validate", "validation"}:
                return ingestor.validate_file(path, **kwargs)
            return ingestor.ingest_file(path, **kwargs)

        if isinstance(source, list):
            return [_run_single(path) for path in source]

        source_path = Path(source)
        if method == "directory" or source_path.is_dir():
            return ingestor.ingest_directory(source_path, **kwargs)

        return _run_single(source_path)

    except Exception as e:
        logger.error(f"Failed to ingest XML: {e}")
        raise


def ingest_web(
    source: Union[str, List[str]], method: str = "url", **kwargs
) -> Union[WebContent, List[WebContent], Dict[str, Any]]:
    """
    Ingest web content from source (convenience function).

    This is a user-friendly wrapper that ingests web content using the specified method.

    Args:
        source: URL or list of URLs
        method: Ingestion method (default: "url")
            - "url": Single URL ingestion
            - "sitemap": Sitemap-based crawling
            - "crawl": Domain crawling
        **kwargs: Additional options passed to WebIngestor

    Returns:
        WebContent, List[WebContent], or Dict with ingestion results

    Examples:
        >>> from semantica.ingest.methods import ingest_web
        >>> content = ingest_web("https://example.com", method="url")
        >>> pages = ingest_web("https://example.com/sitemap.xml", method="sitemap")
    """
    # Check for custom method in registry
    custom_method = method_registry.get("web", method)
    if custom_method and custom_method != ingest_web:
        try:
            return custom_method(source, **kwargs)
        except Exception as e:
            logger.warning(
                f"Custom method {method} failed: {e}, falling back to default"
            )

    try:
        try:
            from .web_ingestor import WebIngestor
        except ModuleNotFoundError as exc:
            if _is_missing_dependency(exc, "bs4"):
                raise _missing_optional_dependency(
                    "Web ingestion",
                    "beautifulsoup4",
                ) from exc
            raise

        # Get config
        config = ingest_config.get_method_config("web")
        config.update(kwargs)
        if "allow_private_ips" in config:
            from .ssrf import parse_bool

            config["allow_private_ips"] = parse_bool(
                config["allow_private_ips"], default=False
            )

        ingestor = WebIngestor(**config)

        if method == "url":
            if isinstance(source, list):
                return [ingestor.ingest_url(url, **kwargs) for url in source]
            else:
                return ingestor.ingest_url(source, **kwargs)
        elif method == "sitemap":
            return ingestor.crawl_sitemap(source, **kwargs)
        elif method == "crawl":
            return ingestor.crawl_domain(source, **kwargs)
        else:
            # Default: try as URL
            return ingestor.ingest_url(source, **kwargs)

    except ConfigurationError:
        raise
    except Exception as e:
        logger.error(f"Failed to ingest web: {e}")
        raise


def ingest_public_api(
    source: Union[str, List[str]],
    method: str = "endpoint",
    **kwargs,
) -> Union[
    APIData,
    List[APIData],
    PublicAPIDetection,
    List[PublicAPIDetection],
    Dict[str, Any],
]:
    """
    Ingest public, no-auth API endpoints.

    Args:
        source: Endpoint URL, example name, or list of endpoint URLs/example names
        method: Public API ingestion method:
            - "endpoint": Ingest a single no-auth endpoint
            - "example": Ingest a pre-configured public API example
            - "detect": Check whether endpoint access works without auth
            - "batch": Ingest multiple no-auth endpoints
            - "examples": List pre-configured public API examples
        **kwargs: Additional options passed to PublicAPIIngestor. Use
            ``http_method`` to override the HTTP method because ``method`` is
            reserved for ingestion dispatch.

    Returns:
        APIData, list of APIData, detection result(s), or examples dictionary

    Examples:
        >>> from semantica.ingest.methods import ingest_public_api
        >>> data = ingest_public_api("https://jsonplaceholder.typicode.com/posts")
        >>> countries = ingest_public_api("rest_countries_all", method="example")
        >>> detection = ingest_public_api(
        ...     "https://jsonplaceholder.typicode.com/posts",
        ...     method="detect",
        ... )
    """
    custom_method = method_registry.get("public_api", method)
    if custom_method and custom_method != ingest_public_api:
        try:
            return custom_method(source, **kwargs)
        except Exception as e:
            logger.warning(
                f"Custom method {method} failed: {e}, falling back to default"
            )

    try:
        from .public_api_ingestor import PublicAPIExamples, PublicAPIIngestor

        config = ingest_config.get_method_config("public_api")
        config.update(kwargs)
        ingestor = PublicAPIIngestor(**config)

        request_kwargs = kwargs.copy()
        for config_only_key in (
            "backoff_factor",
            "delay",
            "fail_fast",
            "max_retries",
            "rate_limit_delay",
            "validate_no_auth",
        ):
            request_kwargs.pop(config_only_key, None)

        http_method = request_kwargs.pop("http_method", None)
        if http_method:
            request_kwargs["method"] = http_method

        if method in {"examples", "list_examples"}:
            tag = request_kwargs.pop("tag", None)
            return {"examples": PublicAPIExamples.list_examples(tag=tag)}

        if method in {"detect", "detection"}:
            if isinstance(source, list):
                return [
                    ingestor.detect_public_api(endpoint, **request_kwargs)
                    for endpoint in source
                ]
            return ingestor.detect_public_api(source, **request_kwargs)

        if method in {"example", "sample"}:
            if isinstance(source, list):
                return [
                    ingestor.ingest_example(name, **request_kwargs) for name in source
                ]
            return ingestor.ingest_example(source, **request_kwargs)

        if method == "batch" or isinstance(source, list):
            if not isinstance(source, list):
                raise ProcessingError("Public API batch ingestion requires a list")
            return ingestor.batch_public_apis(source, **request_kwargs)

        return ingestor.ingest_public_api(source, **request_kwargs)

    except Exception as e:
        logger.error(f"Failed to ingest public API: {e}")
        raise


def ingest_feed(
    source: Union[str, List[str]], method: str = "rss", **kwargs
) -> Union[FeedData, List[FeedData], Dict[str, Any]]:
    """
    Ingest feeds from source (convenience function).

    This is a user-friendly wrapper that ingests feeds using the specified method.

    Args:
        source: Feed URL or list of feed URLs
        method: Ingestion method (default: "rss")
            - "rss": RSS feed ingestion
            - "atom": Atom feed ingestion
            - "discover": Feed discovery from websites
        **kwargs: Additional options passed to FeedIngestor

    Returns:
        FeedData, List[FeedData], or Dict with ingestion results

    Examples:
        >>> from semantica.ingest.methods import ingest_feed
        >>> feed = ingest_feed("https://example.com/feed.xml", method="rss")
        >>> feeds = ingest_feed("https://example.com", method="discover")
    """
    # Check for custom method in registry
    custom_method = method_registry.get("feed", method)
    if custom_method and custom_method != ingest_feed:
        try:
            return custom_method(source, **kwargs)
        except Exception as e:
            logger.warning(
                f"Custom method {method} failed: {e}, falling back to default"
            )

    try:
        try:
            from .feed_ingestor import FeedIngestor
        except ModuleNotFoundError as exc:
            if _is_missing_dependency(exc, "bs4"):
                raise _missing_optional_dependency(
                    "Feed ingestion",
                    "beautifulsoup4",
                ) from exc
            raise

        # Get config
        config = ingest_config.get_method_config("feed")
        config.update(kwargs)

        ingestor = FeedIngestor(**config)

        if method == "discover":
            return ingestor.discover_feeds(source, **kwargs)
        else:
            if isinstance(source, list):
                return [ingestor.ingest_feed(url, **kwargs) for url in source]
            else:
                return ingestor.ingest_feed(source, **kwargs)

    except ConfigurationError:
        raise
    except Exception as e:
        logger.error(f"Failed to ingest feed: {e}")
        raise


def ingest_stream(
    source: Dict[str, Any], method: str = "kafka", **kwargs
) -> StreamProcessor:
    """
    Ingest stream from source (convenience function).

    This is a user-friendly wrapper that ingests streams using the specified method.

    Args:
        source: Stream source configuration dictionary
        method: Ingestion method (default: "kafka")
            - "kafka": Kafka stream ingestion
            - "rabbitmq": RabbitMQ stream ingestion
            - "kinesis": AWS Kinesis stream ingestion
            - "pulsar": Apache Pulsar stream ingestion
        **kwargs: Additional options passed to StreamIngestor

    Returns:
        StreamProcessor instance

    Examples:
        >>> from semantica.ingest.methods import ingest_stream
        >>> processor = ingest_stream(
        ...     {"topic": "my-topic", "bootstrap_servers": ["localhost:9092"]},
        ...     method="kafka"
        ... )
    """
    # Check for custom method in registry
    custom_method = method_registry.get("stream", method)
    if custom_method and custom_method != ingest_stream:
        try:
            return custom_method(source, **kwargs)
        except Exception as e:
            logger.warning(
                f"Custom method {method} failed: {e}, falling back to default"
            )

    try:
        from .stream_ingestor import StreamIngestor

        # Get config
        config = ingest_config.get_method_config("stream")
        config.update(kwargs)

        ingestor = StreamIngestor(**config)

        if method == "kafka":
            return ingestor.ingest_kafka(
                source.get("topic", ""), source.get("bootstrap_servers", []), **kwargs
            )
        elif method == "rabbitmq":
            return ingestor.ingest_rabbitmq(
                source.get("queue", ""),
                source.get("host", "localhost"),
                source.get("port", 5672),
                **kwargs,
            )
        elif method == "kinesis":
            return ingestor.ingest_kinesis(
                source.get("stream_name", ""),
                source.get("region", "us-east-1"),
                **kwargs,
            )
        elif method == "pulsar":
            return ingestor.ingest_pulsar(
                source.get("topic", ""),
                source.get("service_url", "pulsar://localhost:6650"),
                **kwargs,
            )
        else:
            raise ProcessingError(f"Unknown stream method: {method}")

    except Exception as e:
        logger.error(f"Failed to ingest stream: {e}")
        raise


def ingest_repository(
    source: Union[str, Path], method: str = "git", **kwargs
) -> Dict[str, Any]:
    """
    Ingest repository from source (convenience function).

    This is a user-friendly wrapper that ingests repositories using the
    specified method.

    Args:
        source: Repository URL or local path
        method: Ingestion method (default: "git")
            - "git": Git repository ingestion
            - "clone": Repository cloning
            - "analyze": Repository analysis
        **kwargs: Additional options passed to RepoIngestor

    Returns:
        Dict with repository ingestion results

    Examples:
        >>> from semantica.ingest.methods import ingest_repository
        >>> repo_data = ingest_repository(
        ...     "https://github.com/user/repo.git", method="git"
        ... )
        >>> analysis = ingest_repository("./repo", method="analyze")
    """
    # Check for custom method in registry
    custom_method = method_registry.get("repo", method)
    if custom_method and custom_method != ingest_repository:
        try:
            return custom_method(source, **kwargs)
        except Exception as e:
            logger.warning(
                f"Custom method {method} failed: {e}, falling back to default"
            )

    try:
        try:
            from .repo_ingestor import RepoIngestor
        except ModuleNotFoundError as exc:
            if _is_missing_dependency(exc, "git"):
                raise _missing_optional_dependency(
                    "Repository ingestion", "GitPython"
                ) from exc
            raise

        # Get config
        config = ingest_config.get_method_config("repo")
        config.update(kwargs)

        ingestor = RepoIngestor(**config)

        if method == "clone" or (
            isinstance(source, str)
            and (
                source.startswith(("http://", "https://"))
                or _is_scp_like_repo_source(source)
            )
        ):
            return ingestor.ingest_repository(source, **kwargs)
        elif method == "analyze":
            return ingestor.analyze_repository(source, **kwargs)
        else:
            # Default: ingest repository
            return ingestor.ingest_repository(source, **kwargs)

    except ConfigurationError:
        raise
    except Exception as e:
        logger.error(f"Failed to ingest repository: {e}")
        raise


def ingest_email(
    source: Dict[str, Any], method: str = "imap", **kwargs
) -> Union[EmailData, List[EmailData], Dict[str, Any]]:
    """
    Ingest emails from source (convenience function).

    This is a user-friendly wrapper that ingests emails using the specified method.

    Args:
        source: Email source configuration dictionary
        method: Ingestion method (default: "imap")
            - "imap": IMAP email ingestion
            - "pop3": POP3 email ingestion
        **kwargs: Additional options passed to EmailIngestor

    Returns:
        EmailData, List[EmailData], or Dict with ingestion results

    Examples:
        >>> from semantica.ingest.methods import ingest_email
        >>> emails = ingest_email(
        ...     {"host": "imap.example.com", "username": "user", "password": "pass"},
        ...     method="imap"
        ... )
    """
    # Check for custom method in registry
    custom_method = method_registry.get("email", method)
    if custom_method and custom_method != ingest_email:
        try:
            return custom_method(source, **kwargs)
        except Exception as e:
            logger.warning(
                f"Custom method {method} failed: {e}, falling back to default"
            )

    try:
        try:
            from .email_ingestor import EmailIngestor
        except ModuleNotFoundError as exc:
            if _is_missing_dependency(exc, "bs4"):
                raise _missing_optional_dependency(
                    "Email ingestion",
                    "beautifulsoup4",
                ) from exc
            raise

        # Get config
        config = ingest_config.get_method_config("email")
        config.update(kwargs)

        ingestor = EmailIngestor(**config)

        if method == "imap":
            ingestor.connect_imap(
                source.get("host", ""),
                username=source.get("username", ""),
                password=source.get("password", ""),
                **kwargs,
            )
            mailbox = source.get("mailbox", "INBOX")
            max_emails = source.get("max_emails", 100)
            return ingestor.ingest_mailbox(mailbox, max_emails=max_emails, **kwargs)
        elif method == "pop3":
            ingestor.connect_pop3(
                source.get("host", ""),
                username=source.get("username", ""),
                password=source.get("password", ""),
                **kwargs,
            )
            max_emails = source.get("max_emails", 100)
            return ingestor.ingest_pop3(max_emails=max_emails, **kwargs)
        else:
            raise ProcessingError(f"Unknown email method: {method}")

    except ConfigurationError:
        raise
    except Exception as e:
        logger.error(f"Failed to ingest email: {e}")
        raise


def ingest_ontology(
    source: Union[str, Path, List[Union[str, Path]]], method: str = "file", **kwargs
) -> Union[OntologyData, List[OntologyData]]:
    """
    Ingest ontology from source (convenience function).

    This is a user-friendly wrapper that ingests ontologies using the specified method.

    Args:
        source: Ontology file path, directory path, or list of paths
        method: Ingestion method (default: "file")
            - "file": Single file ingestion
            - "directory": Directory ingestion with recursive scanning
        **kwargs: Additional options passed to OntologyIngestor

    Returns:
        OntologyData, List[OntologyData] with ingestion results

    Examples:
        >>> from semantica.ingest.methods import ingest_ontology
        >>> ontology = ingest_ontology("ontology.ttl")
        >>> ontologies = ingest_ontology("./ontologies", method="directory")
    """
    # Check for custom method in registry
    custom_method = method_registry.get("ontology", method)
    if custom_method and custom_method != ingest_ontology:
        try:
            return custom_method(source, **kwargs)
        except Exception as e:
            logger.warning(
                f"Custom method {method} failed: {e}, falling back to default"
            )

    try:
        from .ontology_ingestor import OntologyIngestor

        # Get config
        config = ingest_config.get_method_config("ontology")
        config.update(kwargs)

        ingestor = OntologyIngestor(**config)

        source_path = str(source) if isinstance(source, (str, Path)) else None

        if method == "file" and source_path:
            if isinstance(source, list):
                return [ingestor.ingest_ontology(str(s), **kwargs) for s in source]
            return ingestor.ingest_ontology(source_path, **kwargs)
        elif method == "directory" and source_path:
            recursive = kwargs.get("recursive", ingest_config.get("recursive", True))
            return ingestor.ingest_directory(source_path, recursive=recursive, **kwargs)
        else:
            # Default: try as file
            if isinstance(source, list):
                return [ingestor.ingest_ontology(str(s), **kwargs) for s in source]
            return ingestor.ingest_ontology(str(source), **kwargs)

    except Exception as e:
        logger.error(f"Failed to ingest ontology: {e}")
        raise


def ingest_database(
    source: Union[str, Dict[str, Any]], method: Optional[str] = None, **kwargs
) -> Union[TableData, List[TableData], Dict[str, Any]]:
    """
    Ingest database from source (convenience function).

    This is a user-friendly wrapper that ingests databases using the specified method.

    Args:
        source: Database connection string or configuration dictionary
        method: Ingestion method (auto-detected from connection string if None)
            - "postgresql": PostgreSQL database ingestion
            - "mysql": MySQL database ingestion
            - "sqlite": SQLite database ingestion
            - "oracle": Oracle database ingestion
            - "mssql": SQL Server database ingestion
        **kwargs: Additional options passed to DBIngestor

    Returns:
        TableData, List[TableData], or Dict with ingestion results

    Examples:
        >>> from semantica.ingest.methods import ingest_database
        >>> data = ingest_database("postgresql://user:pass@localhost/db", table="users")
        >>> tables = ingest_database("sqlite:///db.sqlite")
    """
    # Check for custom method in registry
    if method:
        custom_method = method_registry.get("db", method)
        if custom_method and custom_method != ingest_database:
            try:
                return custom_method(source, **kwargs)
            except Exception as e:
                logger.warning(
                    f"Custom method {method} failed: {e}, falling back to default"
                )

    try:
        from .db_ingestor import DBIngestor

        # Get config
        config = ingest_config.get_method_config("db")
        config.update(kwargs)

        ingestor = DBIngestor(**config)

        # Auto-detect database type from connection string
        if isinstance(source, str):
            if "postgresql" in source or "postgres" in source:
                method = "postgresql"
            elif "mysql" in source or "mariadb" in source:
                method = "mysql"
            elif "sqlite" in source:
                method = "sqlite"
            elif "oracle" in source:
                method = "oracle"
            elif "mssql" in source or "sqlserver" in source:
                method = "mssql"

        # Ingest database
        if "table" in kwargs:
            return ingestor.export_table(
                source,
                kwargs["table"],
                **{k: v for k, v in kwargs.items() if k != "table"},
            )
        else:
            return ingestor.ingest_database(source, **kwargs)

    except Exception as e:
        logger.error(f"Failed to ingest database: {e}")
        raise


def ingest_mcp(
    source: Union[str, Dict[str, Any]],
    method: str = "resources",
    server_name: Optional[str] = None,
    **kwargs,
) -> Union[MCPData, List[MCPData], Dict[str, Any]]:
    """
    Ingest data from MCP server (convenience function).

    **IMPORTANT**: Supports only Python MCP servers and FastMCP servers.
    Users can bring their own Python/FastMCP MCP servers via URL.

    This is a user-friendly wrapper that ingests data from MCP servers using
    the specified method. Works with Python and FastMCP MCP servers.

    Args:
        source: MCP server URL, configuration dict with "url" key, or server
            name if already connected
            - URL string: "http://localhost:8000/mcp"
            - Dict: {"url": "http://localhost:8000/mcp", "headers": {...}}
        method: Ingestion method (default: "resources")
            - "resources": Ingest from MCP server resources
            - "tools": Ingest by calling MCP tools
            - "all": Ingest all resources
        server_name: Name for MCP server connection (auto-generated if not provided)
        **kwargs: Additional options:
            - headers: Custom headers for authentication
            - resource_uris: List of resource URIs to ingest
            - tool_name: Tool name to call
            - tool_arguments: Tool arguments

    Returns:
        MCPData, List[MCPData], or Dict with ingestion results

    Examples:
        >>> from semantica.ingest.methods import ingest_mcp
        >>> # Connect via URL and ingest resources
        >>> data = ingest_mcp("http://localhost:8000/mcp", method="resources")
        >>> # Connect via URL dict and ingest all resources
        >>> data = ingest_mcp(
        ...     {
        ...         "url": "https://api.example.com/mcp",
        ...         "headers": {"Authorization": "Bearer token"},
        ...     },
        ...     method="all"
        ... )
        >>> # Ingest from already connected server
        >>> data = ingest_mcp(
        ...     "server1",
        ...     method="resources",
        ...     resource_uris=["resource://example"],
        ... )
        >>> # Call tool
        >>> result = ingest_mcp(
        ...     "server1",
        ...     method="tools",
        ...     tool_name="get_data",
        ...     tool_arguments={},
        ... )
    """
    # Check for custom method in registry
    custom_method = method_registry.get("mcp", method)
    if custom_method and custom_method != ingest_mcp:
        try:
            return custom_method(source, **kwargs)
        except Exception as e:
            logger.warning(
                f"Custom method {method} failed: {e}, falling back to default"
            )

    try:
        from .mcp_ingestor import MCPIngestor

        # Get config
        config = ingest_config.get_method_config("mcp")
        config.update(kwargs)

        ingestor = MCPIngestor(**config)

        # If source is a string, check if it's a URL or server name
        if isinstance(source, str):
            # Check if it looks like a URL
            if source.startswith(("http://", "https://", "mcp://", "sse://")):
                # It's a URL, connect to it
                if not server_name:
                    server_name = f"mcp_server_{len(ingestor.get_connected_servers())}"
                ingestor.connect(
                    server_name=server_name, url=source, headers=kwargs.get("headers")
                )
            else:
                # Assume it's a server name (already connected)
                server_name = source
                if not ingestor.is_connected(server_name):
                    raise ProcessingError(
                        f"MCP server '{server_name}' not connected. "
                        f"Provide MCP server URL: http://, https://, or mcp://"
                    )
        elif isinstance(source, dict):
            # Connect to MCP server
            if not server_name:
                server_name = source.get(
                    "server_name", f"mcp_server_{len(ingestor.get_connected_servers())}"
                )

            # Extract URL (required)
            url = source.get("url")
            if not url:
                raise ProcessingError(
                    "MCP server URL is required. Provide 'url' in configuration dict: "
                    "http://, https://, or mcp://"
                )

            ingestor.connect(
                server_name=server_name,
                url=url,
                headers=source.get("headers"),
                **{
                    k: v
                    for k, v in source.items()
                    if k not in ("url", "headers", "server_name")
                },
            )
        else:
            raise ProcessingError(
                "Source must be MCP server URL (str), configuration dict "
                "with 'url' key, "
                "or server name (str) if already connected"
            )

        # Ingest based on method
        if method == "resources" or method == "all":
            resource_uris = kwargs.get("resource_uris")
            if method == "all":
                return ingestor.ingest_all_resources(server_name, **kwargs)
            else:
                return ingestor.ingest_resources(
                    server_name, resource_uris=resource_uris, **kwargs
                )
        elif method == "tools":
            tool_name = kwargs.get("tool_name")
            if not tool_name:
                raise ProcessingError("tool_name required for tools method")
            tool_arguments = kwargs.get("tool_arguments", {})
            return ingestor.ingest_tool_output(
                server_name, tool_name, tool_arguments, **kwargs
            )
        else:
            raise ProcessingError(f"Unknown MCP method: {method}")

    except Exception as e:
        logger.error(f"Failed to ingest MCP: {e}")
        raise


def ingest(
    sources: Union[List[Union[str, Path]], str, Path],
    source_type: Optional[str] = None,
    method: Optional[str] = None,
    **kwargs,
) -> Dict[str, Any]:
    """
    Ingest data from sources (unified convenience function).

    This is a user-friendly wrapper that automatically routes to the appropriate
    ingestor based on source type or auto-detection.

    Args:
        sources: Data source(s) - can be file paths, URLs, directories, etc.
        source_type: Source type (auto-detected if not specified)
            - "file": File ingestion
            - "web": Web ingestion
            - "public_api" / "api": No-auth public API ingestion
            - "feed": Feed ingestion
            - "stream": Stream ingestion
            - "repo": Repository ingestion
            - "email": Email ingestion
            - "db": Database ingestion
            - "ontology": Ontology ingestion
            - "parquet": Apache Parquet file or directory ingestion
            - "xml": XML file or directory ingestion
        method: Optional specific ingestion method
        **kwargs: Additional options passed to ingestor

    Returns:
        Dict with ingestion results. The top-level key depends on source_type:
            - "files": file ingestion
            - "content": web ingestion
            - "data": public API, database, parquet, or MCP ingestion
            - "feeds": feed ingestion
            - "emails": email ingestion
            - "ontology": ontology ingestion
            - "xml": XML file or directory ingestion (use ``result["xml"]``)

    Examples:
        >>> from semantica.ingest.methods import ingest
        >>> # File ingestion
        >>> result = ingest("document.pdf", source_type="file")
        >>> # Web ingestion
        >>> result = ingest("https://example.com", source_type="web")
        >>> # Auto-detect from source
        >>> result = ingest("https://example.com/feed.xml")  # Auto-detects feed
        >>> # XML ingestion — access via result["xml"]
        >>> result = ingest("catalog.xml")
        >>> xml_data = result["xml"]
    """
    # Auto-detect source type if not specified
    if not source_type:
        if isinstance(sources, (str, Path)):
            source_str = str(sources)
            source_str_lower = source_str.lower()
            if source_str_lower.startswith(("http://", "https://")):
                # Check if it's a feed URL
                if any(
                    ext in source_str_lower
                    for ext in [".xml", "/feed", "/rss", "/atom"]
                ):
                    source_type = "feed"
                else:
                    source_type = "web"
            elif source_str_lower.startswith(
                ("postgresql://", "mysql://", "sqlite://", "oracle://", "mssql://")
            ):
                source_type = "db"
            elif _is_scp_like_repo_source(source_str) or source_str_lower.startswith(
                ("https://github.com", "https://gitlab.com")
            ):
                source_type = "repo"
            elif source_str_lower.endswith(
                (".ttl", ".owl", ".rdf", ".jsonld", ".n3", ".nt")
            ):
                source_type = "ontology"
            elif source_str_lower.endswith((".parquet", ".pq")):
                source_type = "parquet"
            elif source_str_lower.endswith((".arrow", ".feather", ".ipc")):
                source_type = "arrow"
            elif source_str_lower.endswith(".xml"):
                source_type = "xml"
            else:
                source_type = "file"
        elif (
            isinstance(sources, list)
            and sources
            and all(
                str(source).lower().endswith((".parquet", ".pq")) for source in sources
            )
        ):
            source_type = "parquet"
        elif (
            isinstance(sources, list)
            and sources
            and all(
                str(source).lower().endswith((".arrow", ".feather", ".ipc"))
                for source in sources
            )
        ):
            source_type = "arrow"
        elif (
            isinstance(sources, list)
            and sources
            and all(str(source).lower().endswith(".xml") for source in sources)
        ):
            source_type = "xml"
        else:
            source_type = "file"

    # Route to appropriate ingestor
    if source_type == "file":
        return {"files": ingest_file(sources, method=method or "file", **kwargs)}
    elif source_type == "web":
        return {"content": ingest_web(sources, method=method or "url", **kwargs)}
    elif source_type in {"public_api", "api"}:
        return {
            "data": ingest_public_api(sources, method=method or "endpoint", **kwargs)
        }
    elif source_type == "feed":
        return {"feeds": ingest_feed(sources, method=method or "rss", **kwargs)}
    elif source_type == "stream":
        if isinstance(sources, dict):
            return {
                "processor": ingest_stream(sources, method=method or "kafka", **kwargs)
            }
        else:
            raise ProcessingError("Stream ingestion requires configuration dictionary")
    elif source_type == "repo":
        return ingest_repository(sources, method=method or "git", **kwargs)
    elif source_type == "email":
        if isinstance(sources, dict):
            return {"emails": ingest_email(sources, method=method or "imap", **kwargs)}
        else:
            raise ProcessingError("Email ingestion requires configuration dictionary")
    elif source_type == "db":
        return {"data": ingest_database(sources, method=method, **kwargs)}
    elif source_type == "parquet":
        return {"data": ingest_parquet(sources, method=method or "file", **kwargs)}
    elif source_type == "arrow":
        return {"data": ingest_arrow(sources, method=method or "file", **kwargs)}
    elif source_type == "xml":
        return {"xml": ingest_xml(sources, method=method or "file", **kwargs)}
    elif source_type == "ontology":
        return {"ontology": ingest_ontology(sources, method=method or "file", **kwargs)}
    elif source_type == "mcp":
        return {"data": ingest_mcp(sources, method=method or "resources", **kwargs)}
    else:
        raise ProcessingError(f"Unknown source type: {source_type}")


def get_ingest_method(task: str, name: str) -> Optional[Callable]:
    """
    Get a registered ingestion method.

    Args:
        task: Task type ("file", "web", "feed", "stream", "repo", "email",
            "db", "mcp", "parquet", "xml", "ingest")
        name: Method name

    Returns:
        Registered method or None if not found

    Examples:
        >>> from semantica.ingest.methods import get_ingest_method
        >>> method = get_ingest_method("file", "custom_method")
        >>> if method:
        ...     result = method("document.pdf")
    """
    return method_registry.get(task, name)


def list_available_methods(task: Optional[str] = None) -> Dict[str, List[str]]:
    """
    List all available ingestion methods.

    Args:
        task: Optional task type filter

    Returns:
        Dictionary mapping task types to method names

    Examples:
        >>> from semantica.ingest.methods import list_available_methods
        >>> all_methods = list_available_methods()
        >>> file_methods = list_available_methods("file")
    """
    return method_registry.list_all(task)


# Register default methods
method_registry.register("file", "default", ingest_file)
method_registry.register("file", "file", ingest_file)
method_registry.register("file", "directory", ingest_file)
method_registry.register("file", "cloud", ingest_file)
method_registry.register("web", "default", ingest_web)
method_registry.register("web", "url", ingest_web)
method_registry.register("web", "sitemap", ingest_web)
method_registry.register("web", "crawl", ingest_web)
method_registry.register("public_api", "default", ingest_public_api)
method_registry.register("public_api", "endpoint", ingest_public_api)
method_registry.register("public_api", "example", ingest_public_api)
method_registry.register("public_api", "sample", ingest_public_api)
method_registry.register("public_api", "detect", ingest_public_api)
method_registry.register("public_api", "detection", ingest_public_api)
method_registry.register("public_api", "batch", ingest_public_api)
method_registry.register("public_api", "examples", ingest_public_api)
method_registry.register("public_api", "list_examples", ingest_public_api)
method_registry.register("api", "public", ingest_public_api)
method_registry.register("api", "endpoint", ingest_public_api)
method_registry.register("feed", "default", ingest_feed)
method_registry.register("feed", "rss", ingest_feed)
method_registry.register("feed", "atom", ingest_feed)
method_registry.register("feed", "discover", ingest_feed)
method_registry.register("stream", "default", ingest_stream)
method_registry.register("stream", "kafka", ingest_stream)
method_registry.register("stream", "rabbitmq", ingest_stream)
method_registry.register("stream", "kinesis", ingest_stream)
method_registry.register("stream", "pulsar", ingest_stream)
method_registry.register("repo", "default", ingest_repository)
method_registry.register("repo", "git", ingest_repository)
method_registry.register("repo", "clone", ingest_repository)
method_registry.register("repo", "analyze", ingest_repository)
method_registry.register("email", "default", ingest_email)
method_registry.register("email", "imap", ingest_email)
method_registry.register("email", "pop3", ingest_email)
method_registry.register("db", "default", ingest_database)
method_registry.register("db", "postgresql", ingest_database)
method_registry.register("db", "mysql", ingest_database)
method_registry.register("db", "sqlite", ingest_database)
method_registry.register("db", "oracle", ingest_database)
method_registry.register("db", "mssql", ingest_database)
method_registry.register("parquet", "default", ingest_parquet)
method_registry.register("parquet", "file", ingest_parquet)
method_registry.register("parquet", "directory", ingest_parquet)
method_registry.register("parquet", "schema", ingest_parquet)
method_registry.register("parquet", "metadata", ingest_parquet)
method_registry.register("file", "parquet", ingest_parquet)
method_registry.register("arrow", "default", ingest_arrow)
method_registry.register("arrow", "file", ingest_arrow)
method_registry.register("arrow", "schema", ingest_arrow)
method_registry.register("arrow", "metadata", ingest_arrow)
method_registry.register("file", "arrow", ingest_arrow)
method_registry.register("xml", "default", ingest_xml)
method_registry.register("xml", "file", ingest_xml)
method_registry.register("xml", "directory", ingest_xml)
method_registry.register("xml", "metadata", ingest_xml)
method_registry.register("xml", "validate", ingest_xml)
method_registry.register("xml", "validation", ingest_xml)
method_registry.register("file", "xml", ingest_xml)
method_registry.register("mcp", "default", ingest_mcp)
method_registry.register("mcp", "resources", ingest_mcp)
method_registry.register("mcp", "tools", ingest_mcp)
method_registry.register("mcp", "all", ingest_mcp)
method_registry.register("ontology", "default", ingest_ontology)
method_registry.register("ontology", "file", ingest_ontology)
method_registry.register("ontology", "directory", ingest_ontology)
method_registry.register("ingest", "default", ingest)
method_registry.register("ingest", "unified", ingest)
