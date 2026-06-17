---
title: "Ingest Module"
description: "Universal data ingestion from files, Parquet, XML, web, public APIs, feeds, streams, repositories, email, and databases."
icon: "database"
---

**`semantica.ingest`** is the **universal entry point** for loading data into Semantica:

- 15+ ingestion adapters: files, web, SQL, Snowflake, Kafka, MCP, Git repos, email
- PyArrow Parquet with column selection and partitioned dataset support
- XXE-safe lxml XML with optional XSD schema validation
- `ingest()` unified dispatcher — auto-detects source type from path or URL
- Each ingestor returns its own typed object (`FileObject`, `WebContent`, `TableData`, etc.)


## Exported Classes

| Class | Role |
| :--- | :--- |
| `FileIngestor` | PDF, DOCX, HTML, JSON, CSV, Excel, PPTX, ZIP/TAR — type auto-detected from extension |
| `CloudStorageIngestor` | Unified client for AWS S3, Google Cloud Storage, and Azure Blob Storage |
| `WebIngestor` | Web scraping and crawling with `ingest_url`, `crawl_sitemap`, `crawl_domain` |
| `RESTIngestor` | Generic REST API ingestion with headers, params, retries, and pagination |
| `PublicAPIIngestor` | No-auth public API ingestion with pre-configured examples and rate limiting |
| `FeedIngestor` | RSS/Atom feed ingestion with live monitoring via `FeedMonitor` |
| `StreamIngestor` | Real-time ingestion from Kafka, RabbitMQ, AWS Kinesis, and Apache Pulsar |
| `RepoIngestor` | Git repositories — source files, commit history, and metadata |
| `DBIngestor` | SQL databases via SQLAlchemy — tables, views, and custom queries |
| `SnowflakeIngestor` | Snowflake data warehouse queries and table exports |
| `ParquetIngestor` | Apache Parquet files and partitioned datasets with column selection |
| `XMLIngestor` | XXE-safe XML parsing with optional XSD schema validation |
| `EmailIngestor` | IMAP/POP3 email ingestion with attachment extraction |
| `OntologyIngestor` | OWL/RDF/Turtle ontology file ingestion |
| `MCPIngestor` | Model Context Protocol (MCP) resource ingestion |
| `ingest()` | Unified dispatcher — detects source type automatically from path or URL |

## Getting Started

Use **`FileIngestor`** for local files — it **auto-detects format** from the file extension and handles archives:

```python
from semantica.ingest import FileIngestor

ingestor = FileIngestor()

# Single file -> FileObject
file_obj = ingestor.ingest_file("data/report.pdf")
print(file_obj.name)       # "report.pdf"
print(file_obj.file_type)  # "pdf"
print(file_obj.text)       # decoded text content (property on FileObject)
print(file_obj.size)       # bytes

# Directory scan -> List[FileObject]
files = ingestor.ingest_directory("data/", recursive=True)
for f in files:
    print(f.name, f.file_type, f.size)
```

For web, database, or stream sources, each ingestor exposes its own typed method:

```python
# Web
from semantica.ingest import WebIngestor
wc = WebIngestor(delay=1.0, respect_robots=True).ingest_url("https://example.com")
print(wc.title, wc.text)

# Database — constructor takes no required args; pass connection_string to methods
from semantica.ingest import DBIngestor
db = DBIngestor()
result = db.ingest_database("postgresql://user:pass@localhost/db")
# result["tables"]["documents"]["rows"] contains the rows

# Unified dispatcher — auto-detects source type
from semantica.ingest import ingest
result = ingest("data/report.pdf")          # -> {"files": [FileObject]}
result = ingest("https://example.com")      # -> {"content": WebContent}
result = ingest("data/events.parquet")      # -> {"data": ParquetData}
result = ingest("ontology.ttl")             # -> {"ontology": OntologyData}
```

## Quick Start

<Steps>
  <Step title="Ingest local files">
    ```python
    from semantica.ingest import FileIngestor

    ingestor = FileIngestor()

    # Single file — type auto-detected from extension
    file_obj = ingestor.ingest_file("data/report.pdf")

    # Recursive directory scan
    files = ingestor.ingest_directory("data/", recursive=True)

    # ingest() also works: routes to file or directory automatically
    from semantica.ingest import ingest
    result = ingest("data/report.pdf")   # {"files": [FileObject]}
    ```
  </Step>
  <Step title="Connect to a database">
    ```python
    from semantica.ingest import DBIngestor

    ingestor = DBIngestor()

    # Ingest all tables
    result = ingestor.ingest_database(
        "postgresql://user:pass@localhost/db",
        include_tables=["documents"],
    )
    # result["tables"]["documents"]["rows"] contains the row dicts

    # Run a custom query
    rows = ingestor.execute_query(
        "postgresql://user:pass@localhost/db",
        "SELECT id, content, created_at FROM documents WHERE status = :s",
        s="active",
    )
    ```
  </Step>
  <Step title="Feed into the pipeline">
    ```python
    from semantica.ingest import FileIngestor
    from semantica.pipeline import PipelineBuilder, ExecutionEngine
    from semantica.parse import DocumentParser
    from semantica.semantic_extract import NERExtractor

    ingestor  = FileIngestor()
    parser    = DocumentParser()
    extractor = NERExtractor(method="ml")

    builder = PipelineBuilder()
    builder.add_step("ingest",  "file_ingest",    handler=ingestor.ingest_file)
    builder.add_step("parse",   "document_parse", handler=parser.parse)
    builder.add_step("extract", "ner_extract",    handler=extractor.extract)
    builder.connect_steps("ingest", "parse")
    builder.connect_steps("parse",  "extract")

    pipeline = builder.build("my_pipeline")
    result   = ExecutionEngine().execute_pipeline(pipeline, data="data/report.pdf")
    ```
  </Step>
</Steps>

## Ingestors

<Tabs>
  <Tab title="File-Based">
    ### FileIngestor

    ```python
    from semantica.ingest import FileIngestor

    ingestor = FileIngestor()

    # Single file
    file_obj = ingestor.ingest_file("data/report.pdf")

    # Directory — returns List[FileObject]
    files = ingestor.ingest_directory("data/", recursive=True)

    # ingest() dispatches to ingest_file or ingest_directory automatically
    files = ingestor.ingest("data/")
    ```

    Supported formats: PDF, DOCX, TXT, HTML, JSON, CSV, Excel (XLSX/XLS), PPTX, ZIP/TAR archives.

    <Note>
      Glob patterns (e.g. `"data/**/*.docx"`) are **not** supported. `ingest()` accepts a file path or a directory path only. To filter by extension inside a directory, use `ingest_directory()` with the `pattern=` filter option.
    </Note>

    ### ParquetIngestor

    PyArrow-based ingestion for Apache Parquet files, including Hive-style partitioned datasets:

    ```python
    from semantica.ingest import ParquetIngestor

    ingestor = ParquetIngestor()

    # Single Parquet file -> ParquetData
    data = ingestor.ingest_file("data/events.parquet")

    # Partitioned directory (year=2024/month=01/...)
    data = ingestor.ingest_directory("data/partitioned/")

    # Load only specific columns — pass as kwarg
    from semantica.ingest import ingest_parquet
    data = ingest_parquet("data/events.parquet", columns=["id", "text", "timestamp"])

    # Extract schema without loading data
    schema = ingest_parquet("data/events.parquet", method="schema")
    ```

    Requires `pyarrow`: `pip install pyarrow`.

    ### XMLIngestor

    XXE-safe lxml-based ingestion with optional schema validation:

    ```python
    from semantica.ingest import XMLIngestor

    # Basic ingestion
    ingestor = XMLIngestor()
    data = ingestor.ingest_file("data/records.xml")

    # With XSD validation — pass schema_path as kwarg
    from semantica.ingest import ingest_xml
    data = ingest_xml("data/records.xml", schema_path="schema.xsd")

    # Validation report only
    report = ingest_xml("data/feed.xml", method="validate", schema_path="schema.xsd")

    # Directory scan
    results = ingestor.ingest_directory("data/records/")
    ```

    <Note>
      `XMLIngestor` uses lxml with `resolve_entities=False` to prevent XML External Entity (XXE) injection attacks.
    </Note>
  </Tab>
  <Tab title="Web & Feed">
    ### WebIngestor

    ```python
    from semantica.ingest import WebIngestor

    ingestor = WebIngestor(
        delay=1.0,             # seconds between requests
        respect_robots=True,   # honor robots.txt
        timeout=30,
    )

    # Single URL -> WebContent
    content = ingestor.ingest_url("https://example.com/about")
    print(content.title)
    print(content.text)
    print(content.links)

    # Sitemap crawl -> List[WebContent]
    pages = ingestor.crawl_sitemap("https://example.com/sitemap.xml")

    # Domain crawl -> List[WebContent]
    pages = ingestor.crawl_domain("https://example.com", max_pages=50)
    ```

    Requires `beautifulsoup4`: `pip install beautifulsoup4`.

    ### PublicAPIIngestor

    Use this for public REST-style APIs that do not require keys or tokens:

    ```python
    from semantica.ingest import PublicAPIIngestor, PublicAPIExamples, ingest_public_api

    ingestor = PublicAPIIngestor(rate_limit_delay=1.0)

    # Ingest any public endpoint
    data = ingestor.ingest_public_api("https://jsonplaceholder.typicode.com/posts")

    # Use a pre-configured example by name
    data = ingestor.ingest_example("rest_countries_all")

    # Check if endpoint is accessible without auth
    detection = ingestor.detect_public_api("https://jsonplaceholder.typicode.com/posts")

    # List available pre-configured examples
    examples = PublicAPIExamples.list_examples()

    # Convenience function
    data = ingest_public_api("https://jsonplaceholder.typicode.com/posts")
    ```

    Public API ingestion rejects common auth headers and query parameters by
    default. Use `RESTIngestor` for authenticated APIs.

    ### FeedIngestor (RSS/Atom)

    ```python
    from semantica.ingest import FeedIngestor

    ingestor = FeedIngestor()

    # Ingest a feed -> FeedData
    feed = ingestor.ingest_feed("https://feeds.example.com/rss")

    # Discover feeds from a website
    from semantica.ingest import ingest_feed
    feeds = ingest_feed("https://example.com", method="discover")
    ```

    Requires `beautifulsoup4`: `pip install beautifulsoup4`.

    ### RepoIngestor

    Ingest Git repositories — source code, commit history, and dependency graphs:

    ```python
    from semantica.ingest import RepoIngestor

    ingestor = RepoIngestor(
        branch="main",
        file_types=[".py", ".md", ".yaml"],
        include_commits=True,
        commit_range="HEAD~100..HEAD",
    )

    result = ingestor.ingest_repository("https://github.com/org/repo")
    result = ingestor.ingest_repository("/path/to/local/repo")
    ```

    Requires `GitPython`: `pip install gitpython`.

    ### EmailIngestor

    Ingest emails via IMAP or POP3 with attachment extraction and thread analysis:

    ```python
    from semantica.ingest import EmailIngestor
    import os

    ingestor = EmailIngestor(
        protocol="imap",
        host="imap.gmail.com",
        port=993,
        use_ssl=True,
        username=os.getenv("EMAIL_USER"),
        password=os.getenv("EMAIL_PASS"),
        folder="INBOX",
        attachment_types=[".pdf", ".docx", ".txt"],
        include_thread_analysis=True,
        max_emails=500,
    )
    emails = ingestor.ingest()
    ```

    Requires `beautifulsoup4`: `pip install beautifulsoup4`.
  </Tab>
  <Tab title="Cloud Storage">
    ### CloudStorageIngestor

    `CloudStorageIngestor` is a unified client for AWS S3, Google Cloud Storage, and Azure Blob Storage:

    ```python
    from semantica.ingest import CloudStorageIngestor
    import os

    # AWS S3 — list and download objects
    ingestor = CloudStorageIngestor(
        provider="s3",
        access_key_id=os.getenv("AWS_ACCESS_KEY_ID"),
        secret_access_key=os.getenv("AWS_SECRET_ACCESS_KEY"),
        region="us-east-1",
    )
    objects = ingestor.list_objects("my-documents-bucket", prefix="reports/2024/")
    content = ingestor.download_object("my-documents-bucket", "reports/2024/report.pdf")

    # FileIngestor.ingest_cloud() wraps CloudStorageIngestor
    from semantica.ingest import FileIngestor
    files = FileIngestor().ingest_cloud(
        provider="s3",
        bucket="my-documents-bucket",
        prefix="reports/2024/",
        access_key_id=os.getenv("AWS_ACCESS_KEY_ID"),
        secret_access_key=os.getenv("AWS_SECRET_ACCESS_KEY"),
        region="us-east-1",
    )
    ```
  </Tab>
  <Tab title="Database">
    ### DBIngestor (SQL)

    `DBIngestor` takes no required constructor args. Pass the connection string to each method:

    ```python
    from semantica.ingest import DBIngestor

    ingestor = DBIngestor()

    # Ingest entire database (all tables, or filtered)
    result = ingestor.ingest_database(
        "postgresql://user:pass@localhost/db",
        include_tables=["documents"],
    )
    # result["schema"], result["tables"], result["total_tables"]

    # Run a custom query -> List[Dict]
    rows = ingestor.execute_query(
        "postgresql://user:pass@localhost/db",
        "SELECT id, content FROM documents WHERE status = :s",
        s="active",
    )

    # Export a single table -> TableData
    table = ingestor.export_table(
        "postgresql://user:pass@localhost/db",
        table_name="documents",
        limit=1000,
    )
    ```

    Requires `sqlalchemy`: `pip install sqlalchemy` plus your database driver.

    ### SnowflakeIngestor

    ```python
    from semantica.ingest import SnowflakeIngestor
    import os

    ingestor = SnowflakeIngestor(
        account=os.getenv("SNOWFLAKE_ACCOUNT"),
        user=os.getenv("SNOWFLAKE_USER"),
        password=os.getenv("SNOWFLAKE_PASSWORD"),
        warehouse="COMPUTE_WH",
        database="ANALYTICS",
        schema="PUBLIC",
    )
    result = ingestor.ingest_query("SELECT * FROM documents")
    result = ingestor.ingest_table("documents")
    ```
  </Tab>
  <Tab title="Stream">
    ### StreamIngestor

    Real-time ingestion from message brokers — each method returns a typed processor:

    ```python
    from semantica.ingest import StreamIngestor

    ingestor = StreamIngestor()

    # Kafka -> KafkaProcessor
    processor = ingestor.ingest_kafka(
        topic="documents",
        bootstrap_servers=["localhost:9092"],
    )
    processor.set_message_handler(lambda msg: print(msg))
    processor.start_consuming()

    # RabbitMQ -> RabbitMQProcessor
    processor = ingestor.ingest_rabbitmq(
        queue="document_queue",
        connection_url="amqp://guest:guest@localhost/",
    )

    # AWS Kinesis -> KinesisProcessor
    processor = ingestor.ingest_kinesis(
        stream_name="documents-stream",
        region="us-east-1",
    )

    # Apache Pulsar -> PulsarProcessor
    processor = ingestor.ingest_pulsar(
        topic="persistent://public/default/documents",
        service_url="pulsar://localhost:6650",
    )

    # Start all processors at once
    ingestor.start_streaming()
    # Stop all processors
    ingestor.stop_streaming()

    # Monitor stream health
    health = ingestor.monitor.check_health()
    ```

    Stream processors require the appropriate client library (kafka-python, pika, boto3, pulsar-client).
  </Tab>
</Tabs>

## `ingest()` Unified Dispatcher

`ingest()` auto-detects source type from the path or URL and routes to the appropriate ingestor. It returns a `Dict[str, Any]` where the key depends on source type:

```python
from semantica.ingest import ingest

# File
result = ingest("report.pdf")               # {"files": [FileObject]}
result = ingest("data/", source_type="file") # {"files": [FileObject, ...]}

# Web
result = ingest("https://example.com")       # {"content": WebContent}

# Feed (auto-detected from URL pattern)
result = ingest("https://example.com/feed.xml") # {"feeds": FeedData}

# Parquet (auto-detected from .parquet extension)
result = ingest("events.parquet")            # {"data": ParquetData}

# XML (auto-detected from .xml extension)
result = ingest("records.xml")               # {"xml": XMLIngestionData}

# Ontology (auto-detected from .ttl/.owl/.rdf)
result = ingest("ontology.ttl")              # {"ontology": OntologyData}

# Database (auto-detected from connection string prefix)
result = ingest("postgresql://user:pass@localhost/db") # {"data": ...}

# Public API
result = ingest(
    "https://jsonplaceholder.typicode.com/posts",
    source_type="public_api",
)                                            # {"data": APIData}
```

### `ingest()` Parameters

| Parameter | Type | Default | Description |
| :--------- | :---- | :------- | :----------- |
| `sources` | `str`, `Path`, or `List` | **required** | File path, URL, directory, or connection string |
| `source_type` | `str` | `None` (auto-detected) | `"file"`, `"web"`, `"public_api"`, `"feed"`, `"stream"`, `"repo"`, `"email"`, `"db"`, `"parquet"`, `"xml"`, `"ontology"`, `"mcp"` |
| `method` | `str` | `None` | Optional method override passed to the underlying ingestor |
| `**kwargs` | | | Extra options forwarded to the underlying ingestor method |

## FileObject Fields

`FileIngestor` returns `FileObject` instances:

<Accordion title="FileObject schema">

```python
from dataclasses import dataclass
from datetime import datetime
from typing import Any, Dict, Optional

@dataclass
class FileObject:
    path:        str                    # absolute file path
    name:        str                    # filename (e.g. "report.pdf")
    size:        int                    # size in bytes
    file_type:   str                    # detected type without dot (e.g. "pdf", "docx")
    mime_type:   Optional[str]          # MIME type if detectable
    content:     Optional[bytes]        # raw bytes (None if read_content=False)
    metadata:    Dict[str, Any]         # extension, parent dir, is_supported, etc.
    ingested_at: datetime               # ingestion timestamp

    @property
    def text(self) -> str:
        """Decoded text from content bytes (UTF-8 with latin-1 fallback)."""
        ...
```

To get text from an ingested file, use the `.text` property:

```python
file_obj = FileIngestor().ingest_file("report.pdf")
text = file_obj.text       # decoded string
raw  = file_obj.content    # raw bytes
```

Skip reading content (useful for directory scanning without loading files):

```python
files = FileIngestor().ingest_directory("data/", recursive=True, read_content=False)
```

</Accordion>

## OntologyIngestor

Ingest existing OWL or RDF ontology files as structured knowledge sources:

```python
from semantica.ingest import OntologyIngestor

ingestor = OntologyIngestor()

data = ingestor.ingest_ontology("domain_ontology.owl", format="turtle")

# Or using the convenience function
from semantica.ingest import ingest_ontology
data = ingest_ontology("domain_ontology.ttl")
```

## Custom Ingestors

Register a custom ingestor function to participate in the full registry:

```python
from semantica.ingest.registry import method_registry
from semantica.ingest import FileObject

def my_ingestor(source, **kwargs):
    # Return whatever your format produces
    return FileObject(
        path=source,
        name=source,
        size=0,
        file_type="custom",
        content=b"...",
        metadata={},
    )

method_registry.register("file", "my_format", my_ingestor)

# Now callable via the convenience function
from semantica.ingest import ingest_file
result = ingest_file("source_path", method="my_format")
```

## Tips and Common Pitfalls

<Warning>
  **`DBIngestor()` takes no connection string in its constructor.** Pass the connection string to `ingest_database()`, `execute_query()`, or `export_table()` as the first positional argument — not to `DBIngestor()` itself.
</Warning>

<Tip>
  **`FileIngestor` is always the fastest path for local files.** It auto-detects format from extension, handles ZIP/TAR archives automatically, and reads content into `.content` bytes or the `.text` property. Use `read_content=False` when you only need file metadata.
</Tip>

<Tip>
  **Use `ParquetIngestor` instead of `FileIngestor` for structured analytical data.** Parquet ingestion preserves column types (int, float, datetime) that CSV reading loses. Use `columns=["id", "text"]` to avoid loading unused columns — critical for wide tables with hundreds of columns.
</Tip>

<Warning>
  **`XMLIngestor` is XXE-safe by default.** Do not use standard `xml.etree.ElementTree` to pre-parse XML before passing to Semantica — it does not block XXE attacks. `XMLIngestor` uses lxml with `resolve_entities=False` to safely parse untrusted XML.
</Warning>

<Tip>
  **Rate-limit web crawling.** `WebIngestor(delay=1.0, respect_robots=True)` is the responsible default. Without rate limiting you risk getting blocked by the target server or violating its terms of service.
</Tip>

<Warning>
  **`StreamIngestor` methods require the target broker's client library to be installed.** `ingest_kafka` needs `kafka-python`, `ingest_rabbitmq` needs `pika`, `ingest_kinesis` needs `boto3`, and `ingest_pulsar` needs `pulsar-client`. Missing dependencies raise `ImportError` at call time, not at import time.
</Warning>

<CardGroup cols={2}>
  <Card title="Parse" icon="file-lines" href="parse">
    Parse raw sources into structured text and tables.
  </Card>
  <Card title="Pipeline" icon="gear" href="pipeline">
    Orchestrate ingest as the first pipeline step.
  </Card>
  <Card title="Snowflake Integration" icon="snowflake" href="../integrations/snowflake">
    Snowflake-specific setup and authentication guide.
  </Card>
  <Card title="Provenance" icon="link" href="provenance">
    Track lineage from ingest through to inference.
  </Card>
</CardGroup>
