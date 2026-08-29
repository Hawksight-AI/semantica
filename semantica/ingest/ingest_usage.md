# Ingest Module Usage Guide

This guide demonstrates how to use the ingest module for ingesting data from various sources including files, XML, web content, public APIs, feeds, streams, repositories, emails, and databases.

## Table of Contents

1. [Basic Usage](#basic-usage)
2. [File Ingestion](#file-ingestion)
3. [Parquet Ingestion](#parquet-ingestion)
4. [XML Ingestion](#xml-ingestion)
5. [Web Ingestion](#web-ingestion)
6. [Public API Ingestion](#public-api-ingestion)
7. [Feed Ingestion](#feed-ingestion)
8. [Stream Ingestion](#stream-ingestion)
9. [Repository Ingestion](#repository-ingestion)
10. [Email Ingestion](#email-ingestion)
11. [Database Ingestion](#database-ingestion)
12. [MCP Server Ingestion](#mcp-server-ingestion)
13. [Unified Ingestion](#unified-ingestion)
14. [Using Methods](#using-methods)
15. [Using Registry](#using-registry)
16. [Configuration](#configuration)
17. [Advanced Examples](#advanced-examples)

## Basic Usage

### Using the Unified Ingestion Function

```python
from semantica.ingest import ingest

# Ingest a file (auto-detects source type)
result = ingest("document.pdf", source_type="file")

# Ingest a Parquet file
result = ingest("events.parquet")

# Ingest an XML file
result = ingest("catalog.xml")

# Ingest from web URL
result = ingest("https://example.com", source_type="web")

# Ingest from a public API with no authentication
result = ingest(
    "https://jsonplaceholder.typicode.com/posts",
    source_type="public_api",
)

# Ingest from feed
result = ingest("https://example.com/feed.xml", source_type="feed")
```

### Using Main Classes

```python
from semantica.ingest import FileIngestor, PublicAPIIngestor, WebIngestor, XMLIngestor

# Create ingestor
file_ingestor = FileIngestor()
web_ingestor = WebIngestor(delay=1.0, respect_robots=True)
xml_ingestor = XMLIngestor()
api_ingestor = PublicAPIIngestor(rate_limit_delay=1.0)

# Ingest files
files = file_ingestor.ingest_directory("./documents", recursive=True)

# Ingest web content
content = web_ingestor.ingest_url("https://example.com")

# Ingest XML content
xml_data = xml_ingestor.ingest_file("catalog.xml")

# Ingest public API records without credentials
api_data = api_ingestor.ingest_public_api(
    "https://jsonplaceholder.typicode.com/posts"
)
```

## File Ingestion

### Single File Ingestion

```python
from semantica.ingest import ingest_file, FileIngestor

# Using convenience function
file_obj = ingest_file("document.pdf", method="file")

# Using class directly
ingestor = FileIngestor()
file_obj = ingestor.ingest_file("document.pdf", read_content=True)

print(f"File: {file_obj.name}")
print(f"Type: {file_obj.file_type}")
print(f"Size: {file_obj.size} bytes")
```

### Directory Ingestion

```python
from semantica.ingest import ingest_file

# Ingest directory recursively
files = ingest_file("./documents", method="directory", recursive=True)

# Ingest directory with filters
files = ingest_file(
    "./documents",
    method="directory",
    recursive=True,
    file_extensions=[".pdf", ".docx", ".txt"]
)

print(f"Ingested {len(files)} files")
```

### Cloud Storage Ingestion

```python
from semantica.ingest import ingest_file, FileIngestor
from semantica.ingest.file_ingestor import CloudStorageIngestor

# AWS S3 ingestion
s3_config = {
    "provider": "s3",
    "access_key_id": "your_key",
    "secret_access_key": "your_secret",
    "region": "us-east-1"
}

files = ingest_file("s3://bucket-name/path/", method="cloud", **s3_config)

# Google Cloud Storage ingestion
gcs_config = {
    "provider": "gcs",
    "credentials_path": "/path/to/credentials.json"
}

files = ingest_file("gs://bucket-name/path/", method="cloud", **gcs_config)

# Azure Blob Storage ingestion
azure_config = {
    "provider": "azure",
    "connection_string": "your_connection_string"
}

files = ingest_file("https://account.blob.core.windows.net/container/", method="cloud", **azure_config)
```

### File Type Detection

```python
from semantica.ingest import FileTypeDetector

detector = FileTypeDetector()

# Detect by extension
file_type = detector.detect_type("document.pdf")

# Detect by MIME type
file_type = detector.detect_type("document.pdf")

# Detect by magic numbers
with open("document.pdf", "rb") as f:
    content = f.read(1024)
    file_type = detector.detect_type("document.pdf", content=content)
```

## Parquet Ingestion

Parquet ingestion requires PyArrow:

```bash
pip install pyarrow
```

### Single Parquet File

```python
from semantica.ingest import ParquetIngestor, ingest_parquet

# Using convenience function
data = ingest_parquet(
    "events.parquet",
    columns=["event_id", "event_type"],
    limit=1000,
)

# Using class directly
ingestor = ParquetIngestor()
data = ingestor.ingest_file("events.parquet")

print(f"Rows returned: {data.row_count}")
print(f"Columns: {data.columns}")
print(f"Total rows in file: {data.metadata['total_rows']}")
```

### Schema and Metadata Extraction

```python
from semantica.ingest import ParquetIngestor

ingestor = ParquetIngestor()

schema = ingestor.extract_schema("events.parquet")
metadata = ingestor.extract_metadata("events.parquet")

print(schema["columns"])
print(metadata["compression_codecs"])
print(metadata["row_groups"])
```

### Partitioned Parquet Directories

```python
from semantica.ingest import ingest_parquet

# Reads Hive-style directories such as country=US/year=2026/part-0.parquet
data = ingest_parquet(
    "./warehouse/events",
    method="directory",
    columns=["event_id", "event_type", "country", "year"],
)

print(data.metadata["partition_columns"])
print(data.metadata["partition_values"])
```

## XML Ingestion

### Single XML File

```python
from semantica.ingest import XMLIngestor, ingest_xml

# Using convenience function
xml_data = ingest_xml("catalog.xml")

# Using class directly
ingestor = XMLIngestor()
xml_data = ingestor.ingest_file("catalog.xml")

print(f"Root: {xml_data.root_tag}")
print(f"Namespaces: {xml_data.namespaces}")
print(f"Elements: {xml_data.metadata['element_count']}")
```

### XML Namespaces and Attributes

```python
from semantica.ingest import XMLIngestor

data = XMLIngestor().ingest_file("catalog.xml")

for element in data.elements:
    print(element["path"], element["tag"], element["attributes"])
```

### XSD and DTD Validation

```python
from semantica.ingest import XMLIngestor, ingest_xml

# XSD validation runs automatically when schema_path is provided
validated = ingest_xml("catalog.xml", schema_path="catalog.xsd")
print(validated.validation["schema"]["valid"])

# Return a report without raising on validation errors
report = XMLIngestor().validate_file(
    "catalog.xml",
    schema_path="catalog.xsd",
    validate_dtd=True,
)
print(report["is_valid"])
```

### XML Metadata

```python
from semantica.ingest import ingest_xml

metadata = ingest_xml("catalog.xml", method="metadata")

print(metadata["root_tag"])
print(metadata["namespace_count"])
print(metadata["tag_counts"])
```

## Web Ingestion

### Single URL Ingestion

```python
from semantica.ingest import ingest_web, WebIngestor

# Using convenience function
content = ingest_web("https://example.com", method="url")

# Using class directly
ingestor = WebIngestor(delay=1.0, respect_robots=True)
content = ingestor.ingest_url("https://example.com")

print(f"Title: {content.title}")
print(f"Text length: {len(content.text)}")
print(f"Links: {len(content.links)}")
```

### Sitemap Crawling

```python
from semantica.ingest import ingest_web

# Crawl sitemap
pages = ingest_web("https://example.com/sitemap.xml", method="sitemap")

print(f"Found {len(pages)} pages from sitemap")
for page in pages:
    print(f"  - {page.url}")
```

### Domain Crawling

```python
from semantica.ingest import ingest_web

# Crawl domain
pages = ingest_web(
    "https://example.com",
    method="crawl",
    max_pages=100,
    respect_robots=True,
    delay=1.0
)

print(f"Crawled {len(pages)} pages")
```

### Rate Limiting and Robots.txt

```python
from semantica.ingest import WebIngestor

# Create ingestor with rate limiting and robots.txt compliance
ingestor = WebIngestor(
    delay=2.0,  # 2 second delay between requests
    respect_robots=True,  # Check robots.txt
    user_agent="MyBot/1.0"
)

content = ingestor.ingest_url("https://example.com")
```

### Content Extraction

```python
from semantica.ingest import ContentExtractor

extractor = ContentExtractor()

# Extract text from HTML
html = "<html><body><p>Hello World</p></body></html>"
text = extractor.extract_text(html)

# Extract metadata
metadata = extractor.extract_metadata(html, url="https://example.com")

# Extract links
links = extractor.extract_links(html, base_url="https://example.com")
```

## Public API Ingestion

Public API ingestion is for REST-style endpoints that do not require API keys,
OAuth tokens, or other credentials. It is useful for examples, tests, CI, and
contributor development because all requests are made without authentication.

Use `RESTIngestor` instead when an endpoint requires `Authorization`,
`X-API-Key`, `api_key`, or similar credentials.

### Public Endpoint Ingestion

```python
from semantica.ingest import PublicAPIIngestor, ingest_public_api

# Using convenience function
posts = ingest_public_api(
    "https://jsonplaceholder.typicode.com/posts",
    rate_limit_delay=1.0,
)

# Using class directly
ingestor = PublicAPIIngestor(rate_limit_delay=1.0)
users = ingestor.ingest_public_api(
    "https://jsonplaceholder.typicode.com/users",
)

print(posts.metadata["record_count"])
print(users.data[0]["name"])
```

### Pre-Configured Public API Examples

```python
from semantica.ingest import PublicAPIExamples, PublicAPIIngestor

print(PublicAPIExamples.names())
print(PublicAPIExamples.endpoints())

ingestor = PublicAPIIngestor(rate_limit_delay=1.0)

# JSONPlaceholder: fake REST resources for testing
posts = ingestor.ingest_example("jsonplaceholder_posts")

# REST Countries: country reference data
countries = ingestor.ingest_example("rest_countries_all")

# Data.gov catalog search: nested records extracted from result.results
datasets = ingestor.ingest_example(
    "data_gov_datasets",
    params={"q": "transportation", "rows": 5},
)
```

### Public API Detection

```python
from semantica.ingest import PublicAPIIngestor

ingestor = PublicAPIIngestor(rate_limit_delay=1.0)

detection = ingestor.detect_public_api(
    "https://jsonplaceholder.typicode.com/posts"
)

print(detection.is_public)
print(detection.requires_auth)
print(detection.response_status)
```

Detection is endpoint-level. A successful no-auth response means that endpoint
appears public; it does not prove that every endpoint on the same API is public.

### JSON, CSV, and XML Responses

```python
from semantica.ingest import PublicAPIIngestor

ingestor = PublicAPIIngestor(rate_limit_delay=1.0)

# JSON is auto-detected from Content-Type or response body
json_data = ingestor.ingest_public_api(
    "https://jsonplaceholder.typicode.com/todos"
)

# CSV can be parsed into dictionaries
csv_data = ingestor.ingest_public_api(
    "https://example.com/data.csv",
    response_format="csv",
)

# XML is converted to nested dictionaries; record_path can select child nodes
xml_data = ingestor.ingest_public_api(
    "https://example.com/data.xml",
    response_format="xml",
    record_path="children",
)
```

### Testing Helpers

```python
from semantica.ingest import PublicAPIExamples

# Mock payloads for unit tests without live network calls
payload = PublicAPIExamples.sample_response("jsonplaceholder_posts")
data_gov_payload = PublicAPIExamples.sample_response("data_gov_datasets")
```

These fixtures are intentionally small and credential-free. Use mocked HTTP
responses in CI rather than depending on public API uptime.

## Feed Ingestion

### RSS Feed Ingestion

```python
from semantica.ingest import ingest_feed, FeedIngestor

# Using convenience function
feed = ingest_feed("https://example.com/feed.xml", method="rss")

# Using class directly
ingestor = FeedIngestor()
feed = ingestor.ingest_feed("https://example.com/feed.xml")

print(f"Feed: {feed.title}")
print(f"Items: {len(feed.items)}")
for item in feed.items:
    print(f"  - {item.title}: {item.link}")
```

### Atom Feed Ingestion

```python
from semantica.ingest import ingest_feed

# Atom feed ingestion
feed = ingest_feed("https://example.com/atom.xml", method="atom")

print(f"Feed: {feed.title}")
print(f"Updated: {feed.updated}")
```

### Feed Discovery

```python
from semantica.ingest import ingest_feed

# Discover feeds from website
feeds = ingest_feed("https://example.com", method="discover")

print(f"Found {len(feeds)} feeds")
for feed_url in feeds:
    print(f"  - {feed_url}")
```

### Feed Monitoring

```python
from semantica.ingest import FeedMonitor

def on_update(feed_data):
    print(f"Feed updated: {feed_data.title}")
    print(f"New items: {len(feed_data.items)}")

monitor = FeedMonitor(
    feed_url="https://example.com/feed.xml",
    check_interval=300,  # Check every 5 minutes
    on_update=on_update
)

monitor.start()
```

## Stream Ingestion

### Kafka Stream Ingestion

```python
from semantica.ingest import ingest_stream

# Kafka stream ingestion
kafka_config = {
    "topic": "my-topic",
    "bootstrap_servers": ["localhost:9092"]
}

processor = ingest_stream(kafka_config, method="kafka")

# Set message handler
def handle_message(message):
    print(f"Received: {message.content}")

processor.set_message_handler(handle_message)
processor.start_consuming()
```

### RabbitMQ Stream Ingestion

```python
from semantica.ingest import ingest_stream

# RabbitMQ stream ingestion
rabbitmq_config = {
    "queue": "my-queue",
    "host": "localhost",
    "port": 5672,
    "username": "guest",
    "password": "guest"
}

processor = ingest_stream(rabbitmq_config, method="rabbitmq")

def handle_message(message):
    print(f"Received: {message.content}")

processor.set_message_handler(handle_message)
processor.start_consuming()
```

### AWS Kinesis Stream Ingestion

```python
from semantica.ingest import ingest_stream

# Kinesis stream ingestion
kinesis_config = {
    "stream_name": "my-stream",
    "region": "us-east-1"
}

processor = ingest_stream(kinesis_config, method="kinesis")

def handle_message(message):
    print(f"Received: {message.content}")

processor.set_message_handler(handle_message)
processor.start_consuming()
```

### Apache Pulsar Stream Ingestion

```python
from semantica.ingest import ingest_stream

# Pulsar stream ingestion
pulsar_config = {
    "topic": "my-topic",
    "service_url": "pulsar://localhost:6650"
}

processor = ingest_stream(pulsar_config, method="pulsar")

def handle_message(message):
    print(f"Received: {message.content}")

processor.set_message_handler(handle_message)
processor.start_consuming()
```

### Stream Monitoring

```python
from semantica.ingest import StreamIngestor

ingestor = StreamIngestor()

# Start multiple streams
ingestor.ingest_kafka("topic1", ["localhost:9092"])
ingestor.ingest_rabbitmq("queue1", "amqp://guest:guest@localhost:5672/")
ingestor.start_streaming()

# Check health
health = ingestor.monitor.check_health()
print(f"Overall Status: {health['overall']}")

for name, status in health['processors'].items():
    print(f"Processor {name}: {'Healthy' if status['healthy'] else 'Unhealthy'}")
    print(f"  Processed: {status['processed']}")
    print(f"  Errors: {status['errors']}")
```

## Repository Ingestion

### Git Repository Ingestion

```python
from semantica.ingest import ingest_repository, RepoIngestor

# Clone and ingest repository
repo_data = ingest_repository(
    "https://github.com/user/repo.git",
    method="git"
)

print(f"Repository: {repo_data['name']}")
print(f"Files: {len(repo_data['files'])}")
print(f"Commits: {len(repo_data['commits'])}")
```

### Repository Analysis

```python
from semantica.ingest import ingest_repository

# Analyze existing repository
analysis = ingest_repository("./repo", method="analyze")

print(f"Languages: {analysis['languages']}")
print(f"Total lines: {analysis['total_lines']}")
print(f"Files: {len(analysis['files'])}")
```

### Commit Analysis

```python
from semantica.ingest import RepoIngestor

ingestor = RepoIngestor()

# Analyze commits
commits = ingestor.analyze_commits("./repo", max_commits=100)

for commit in commits:
    print(f"{commit.hash}: {commit.message}")
    print(f"  Author: {commit.author}")
    print(f"  Date: {commit.date}")
    print(f"  Changes: +{commit.additions} -{commit.deletions}")
```

### Code Structure Analysis

```python
from semantica.ingest import CodeExtractor

extractor = CodeExtractor()

# Extract code structure
code_file = extractor.extract_code("./src/main.py")

print(f"Language: {code_file.language}")
print(f"Classes: {code_file.metadata.get('classes', [])}")
print(f"Functions: {code_file.metadata.get('functions', [])}")
```

## Email Ingestion

### IMAP Email Ingestion

```python
from semantica.ingest import ingest_email, EmailIngestor

# IMAP email ingestion
imap_config = {
    "host": "imap.example.com",
    "username": "user@example.com",
    "password": "password",
    "mailbox": "INBOX",
    "max_emails": 100
}

emails = ingest_email(imap_config, method="imap")

print(f"Retrieved {len(emails)} emails")
for email in emails:
    print(f"  - {email.subject} from {email.from_address}")
```

### POP3 Email Ingestion

```python
from semantica.ingest import ingest_email

# POP3 email ingestion
pop3_config = {
    "host": "pop3.example.com",
    "username": "user@example.com",
    "password": "password",
    "max_emails": 100
}

emails = ingest_email(pop3_config, method="pop3")

print(f"Retrieved {len(emails)} emails")
```

### Email Thread Analysis

```python
from semantica.ingest import EmailIngestor

ingestor = EmailIngestor()
ingestor.connect_imap("imap.example.com", username="user", password="pass")

emails = ingestor.ingest_mailbox("INBOX", max_emails=100)

# Analyze threads
threads = ingestor.analyze_threads(emails)

print(f"Found {len(threads)} conversation threads")
for thread_id, thread_emails in threads.items():
    print(f"  Thread {thread_id}: {len(thread_emails)} messages")
```

### Attachment Processing

```python
from semantica.ingest import AttachmentProcessor

processor = AttachmentProcessor()

# Process attachment
attachment_info = processor.process_attachment(
    attachment_data,
    filename="document.pdf",
    content_type="application/pdf"
)

print(f"Saved to: {attachment_info['saved_path']}")
print(f"Extracted text: {attachment_info.get('extracted_text', 'N/A')}")

# Cleanup
processor.cleanup_attachments([attachment_info['saved_path']])
```

## Database Ingestion

### PostgreSQL Ingestion

```python
from semantica.ingest import ingest_database, DBIngestor

# PostgreSQL ingestion
connection_string = "postgresql://user:password@localhost/dbname"

# Ingest entire database
data = ingest_database(connection_string)

# Ingest specific table
table_data = ingest_database(
    connection_string,
    table="users",
    limit=1000
)

print(f"Table: {table_data.table_name}")
print(f"Rows: {table_data.row_count}")
print(f"Columns: {[col['name'] for col in table_data.columns]}")
```

### MySQL Ingestion

```python
from semantica.ingest import ingest_database

# MySQL ingestion
connection_string = "mysql://user:password@localhost/dbname"

table_data = ingest_database(connection_string, table="users")
```

### SQLite Ingestion

```python
from semantica.ingest import ingest_database

# SQLite ingestion
connection_string = "sqlite:///database.db"

table_data = ingest_database(connection_string, table="users")
```

### Custom SQL Query

```python
from semantica.ingest import DBIngestor

ingestor = DBIngestor()

# Execute custom query
connection_string = "postgresql://user:password@localhost/dbname"
results = ingestor.execute_query(
    connection_string,
    "SELECT * FROM users WHERE age > ?",
    params=[18]
)

print(f"Retrieved {len(results)} rows")
```

### Schema Introspection

```python
from semantica.ingest import DatabaseConnector

connector = DatabaseConnector("postgresql")
engine = connector.connect("postgresql://user:password@localhost/dbname")

# Get schema information
schema = connector.get_schema(engine)

    print(f"Tables: {schema['tables']}")
    for table_name, columns in schema['columns'].items():
        print(f"  {table_name}: {[col['name'] for col in columns]}")
```

## SAP OData Ingestion

`SAPIngestor` reads an Entity Set from a SAP OData service — S/4HANA Cloud,
SuccessFactors, or an on-prem NetWeaver Gateway over its REST surface. It
follows OData v2/v4 server-driven pagination and flattens each record into a
document dict via `export_as_documents()`.

Install with `pip install 'semantica[ingest-sap]'`.

### Connector Construction & Authentication

```python
from semantica.ingest import SAPIngestor

# OAuth2 client-credentials (BTP / S/4HANA Cloud)
ing = SAPIngestor(
    base_url="https://my-sap.example.com/sap/opu/odata/sap/API_BUSINESS_PARTNER",
    client_id="...", client_secret="...",
    token_url="https://my-sap.example.com/oauth/token",
)
# On-prem NetWeaver often uses Basic auth instead — swap the block above for:
# ing = SAPIngestor(base_url="...", username="erp_user", password="...")
```

### Entity-Set Ingestion & Document Export

```python
# 1. Discover entity sets + field types from $metadata
sets = ing.discover_service()

# 2. Page-walk an Entity Set (v2/v4 next links handled automatically)
partners = ing.ingest_entity_set(
    entity_set="A_BusinessPartnerSet",
    select="BusinessPartner,BusinessPartnerFullName",
    top=1000,
)

# 3. Flatten to document dicts that GraphBuilder can consume directly
docs = ing.export_as_documents(partners)
```

- Use `expand="to_Item"` on a sales-order header set to pull nested line items
  in one request — handy for modeling order → line-item → material relations.
- Every outbound request, including the OAuth2 token exchange, is routed through
  the SSRF guard, and pagination never follows a next link that points to a
  different host than the service root.

> **Security Note:** Never hardcode credentials (`client_secret`, `password`);
> pass them via environment variables (`SAP_CLIENT_SECRET`, `SAP_PASSWORD`) or a
> secrets manager.

## MCP Server Ingestion

**IMPORTANT**: This implementation supports **ONLY Python-based MCP servers and FastMCP servers**. Users can bring their own Python or FastMCP MCP servers via URL connections. JavaScript, TypeScript, C#, Java, and other language implementations are **NOT supported**.

The MCP (Model Context Protocol) server ingestion allows you to connect to Python/FastMCP MCP servers via URL and ingest data from their resources and tools. The implementation is generic and works with Python/FastMCP MCP servers across diverse domains.

### Basic MCP Server Connection

```python
from semantica.ingest import ingest_mcp, MCPIngestor

# Using convenience function - connect via URL and ingest resources
data = ingest_mcp(
    "http://localhost:8000/mcp",  # MCP server URL
    method="resources"
)

print(f"Ingested {len(data)} resources")
```

### Using MCPIngestor Class

```python
from semantica.ingest import MCPIngestor

# Create ingestor
ingestor = MCPIngestor()

# Connect to MCP server via URL (primary method)
ingestor.connect(
    "db_server",
    url="http://localhost:8000/mcp"  # MCP server URL
)

# List available resources
resources = ingestor.list_available_resources("db_server")
print(f"Available resources: {[r.uri for r in resources]}")

# List available tools
tools = ingestor.list_available_tools("db_server")
print(f"Available tools: {[t.name for t in tools]}")
```

### Resource-Based Ingestion

```python
from semantica.ingest import ingest_mcp, MCPIngestor

# Ingest specific resources
ingestor = MCPIngestor()
ingestor.connect("file_server", url="http://localhost:8000/mcp")

# Ingest specific resource URIs
data = ingestor.ingest_resources(
    "file_server",
    resource_uris=["resource://file/documents", "resource://file/reports"]
)

for item in data:
    print(f"Resource: {item.resource_uri}")
    print(f"Content type: {item.data_type}")
    print(f"Metadata: {item.metadata}")
```

### Ingest All Resources

```python
from semantica.ingest import MCPIngestor

ingestor = MCPIngestor()
ingestor.connect("db_server", url="http://localhost:8000/mcp")

# Ingest all available resources
all_data = ingestor.ingest_all_resources("db_server")

print(f"Ingested {len(all_data)} resources")
```

### Tool-Based Ingestion

```python
from semantica.ingest import ingest_mcp, MCPIngestor

# Using convenience function
result = ingest_mcp(
    "db_server",  # Server name (must be already connected)
    method="tools",
    tool_name="query_database",
    tool_arguments={"query": "SELECT * FROM users LIMIT 10"}
)

# Using class directly
ingestor = MCPIngestor()
ingestor.connect("db_server", url="http://localhost:8000/mcp")

result = ingestor.ingest_tool_output(
    "db_server",
    tool_name="query_database",
    arguments={"query": "SELECT * FROM users LIMIT 10"}
)

print(f"Tool result: {result.content}")
```

### Multiple MCP Servers

```python
from semantica.ingest import MCPIngestor

ingestor = MCPIngestor()

# Connect multiple MCP servers via URLs
ingestor.connect(
    "db_server",
    url="http://localhost:8001/mcp"
)

ingestor.connect(
    "file_server",
    url="https://api.example.com/mcp",
    headers={"Authorization": "Bearer token"}
)

ingestor.connect(
    "api_server",
    url="http://localhost:8002/mcp"
)

# Ingest from different servers
db_data = ingestor.ingest_resources("db_server", resource_uris=["resource://database/tables"])
file_data = ingestor.ingest_all_resources("file_server")
api_result = ingestor.ingest_tool_output("api_server", tool_name="fetch_data", arguments={})

# List all connected servers
servers = ingestor.get_connected_servers()
print(f"Connected servers: {servers}")
```

### HTTPS Transport with Authentication

```python
from semantica.ingest import MCPIngestor

ingestor = MCPIngestor()

# Connect via HTTPS with authentication (transport auto-detected from URL)
ingestor.connect(
    "remote_server",
    url="https://api.example.com/mcp",
    headers={
        "Authorization": "Bearer your_token",
        "Content-Type": "application/json"
    }
)

# Ingest resources
data = ingestor.ingest_resources("remote_server")
```

### Resource Filtering

```python
from semantica.ingest import MCPIngestor

ingestor = MCPIngestor()
ingestor.connect("file_server", url="http://localhost:8000/mcp")

# Filter resources by custom function
def filter_pdf_resources(resource):
    return resource.uri.endswith(".pdf") or "pdf" in resource.mime_type

pdf_resources = ingestor.ingest_resources(
    "file_server",
    filter_func=filter_pdf_resources
)

print(f"Found {len(pdf_resources)} PDF resources")
```

### Reading Individual Resources

```python
from semantica.ingest import MCPIngestor

ingestor = MCPIngestor()
ingestor.connect("db_server", url="http://localhost:8000/mcp")

# Read a specific resource
resource_data = ingestor.read_resource("db_server", "resource://database/users")

print(f"Resource data: {resource_data}")
```

### Calling Individual Tools

```python
from semantica.ingest import MCPIngestor

ingestor = MCPIngestor()
ingestor.connect("api_server", url="http://localhost:8000/mcp")

# Call a tool directly
result = ingestor.call_tool(
    "api_server",
    tool_name="get_user_data",
    arguments={"user_id": 123}
)

print(f"Tool result: {result}")
```

### Disconnecting Servers

```python
from semantica.ingest import MCPIngestor

ingestor = MCPIngestor()
ingestor.connect("server1", url="http://localhost:8001/mcp")
ingestor.connect("server2", url="http://localhost:8002/mcp")

# Disconnect specific server
ingestor.disconnect("server1")

# Disconnect all servers
ingestor.disconnect()
```

### Supported MCP Server Domains

**IMPORTANT**: Only Python MCP servers and FastMCP servers are supported. Users can bring their own Python/FastMCP MCP servers via URL.

The implementation works generically with Python and FastMCP MCP servers, including:

- **Database Connectors**: SQLite, PostgreSQL, MySQL, Firebase, Google Drive
- **File Systems**: Local filesystem, cloud storage (S3, GCS, Azure)
- **Code Execution**: Pydantic AI MCP, MCP-Run-Python, SonarQube, VSCode
- **Communication**: Telegram, Microsoft Teams, Mac Messages, ntfy
- **Calendar & Tasks**: Google Calendar, Google Tasks
- **CRM**: HubSpot
- **Financial Data**: Alphavantage
- **News & Media**: Google News
- **Authentication**: Keycloak
- **System Admin**: iTerm
- **Document Processing**: PDF, Markdown, HTML parsers
- **Custom Domains**: Any user-created Python MCP server

### Configuration via Environment Variables

```bash
# MCP server configuration (URL-based)
export MCP_SERVER_URL="http://localhost:8000/mcp"
export MCP_SERVER_TIMEOUT=30.0
```

### Example: Database MCP Server

```python
from semantica.ingest import MCPIngestor

ingestor = MCPIngestor()

# Connect to database MCP server via URL
ingestor.connect(
    "postgres_mcp",
    url="http://localhost:8000/mcp"
)

# List available resources (tables, views, etc.)
resources = ingestor.list_available_resources("postgres_mcp")
print(f"Database resources: {[r.uri for r in resources]}")

# Ingest table data via resource
table_data = ingestor.ingest_resources(
    "postgres_mcp",
    resource_uris=["resource://database/users"]
)

# Or use a tool to query
query_result = ingestor.ingest_tool_output(
    "postgres_mcp",
    tool_name="execute_query",
    arguments={"sql": "SELECT * FROM users WHERE age > 18"}
)
```

### Example: File System MCP Server

```python
from semantica.ingest import MCPIngestor

ingestor = MCPIngestor()

# Connect to filesystem MCP server via URL
ingestor.connect(
    "fs_mcp",
    url="http://localhost:8000/mcp"
)

# Ingest all file resources
files = ingestor.ingest_all_resources("fs_mcp")

# Filter for specific file types
pdf_files = ingestor.ingest_resources(
    "fs_mcp",
    filter_func=lambda r: r.uri.endswith(".pdf")
)
```

## Unified Ingestion

### Auto-Detection

```python
from semantica.ingest import ingest

# Auto-detect source type from source
result = ingest("document.pdf")  # Auto-detects file
result = ingest("events.parquet")  # Auto-detects Parquet
result = ingest("catalog.xml")  # Auto-detects XML
result = ingest("https://example.com")  # Auto-detects web
result = ingest("https://example.com/feed.xml")  # Auto-detects feed
result = ingest("postgresql://user:pass@localhost/db")  # Auto-detects database
result = ingest("http://localhost:8000/mcp", source_type="mcp")  # MCP server ingestion via URL
```

Public APIs should be explicit because regular URLs default to web ingestion:

```python
result = ingest(
    "https://jsonplaceholder.typicode.com/posts",
    source_type="public_api",
)
```

### Explicit Source Type

```python
from semantica.ingest import ingest

# Explicit source type
result = ingest("document.pdf", source_type="file")
result = ingest("catalog.xml", source_type="xml")
result = ingest("https://example.com", source_type="web")
result = ingest("https://jsonplaceholder.typicode.com/posts", source_type="public_api")
result = ingest("https://example.com/feed.xml", source_type="feed")
```

### Batch Ingestion

```python
from semantica.ingest import ingest

# Ingest multiple sources
sources = [
    "document1.pdf",
    "document2.docx",
    "document3.txt"
]

result = ingest(sources, source_type="file")
print(f"Ingested {len(result['files'])} files")
```

## Using Methods

### Format-Specific Methods

```python
from semantica.ingest.methods import (
    ingest_file,
    ingest_web,
    ingest_public_api,
    ingest_feed,
    ingest_stream,
    ingest_repository,
    ingest_email,
    ingest_database,
    ingest_mcp,
    ingest_parquet,
    ingest_xml,
)

# File ingestion
files = ingest_file("./documents", method="directory")

# Web ingestion
content = ingest_web("https://example.com", method="url")

# Public API ingestion
api_data = ingest_public_api(
    "https://jsonplaceholder.typicode.com/posts",
    method="endpoint",
)

# Feed ingestion
feed = ingest_feed("https://example.com/feed.xml", method="rss")

# Stream ingestion
processor = ingest_stream({"topic": "my-topic", "bootstrap_servers": ["localhost:9092"]}, method="kafka")

# Repository ingestion
repo_data = ingest_repository("https://github.com/user/repo.git", method="git")

# Email ingestion
emails = ingest_email({"host": "imap.example.com", "username": "user", "password": "pass"}, method="imap")

# Database ingestion
data = ingest_database("postgresql://user:pass@localhost/db", table="users")

# Parquet ingestion
events = ingest_parquet("events.parquet", columns=["event_id"], limit=1000)

# XML ingestion
xml_data = ingest_xml("catalog.xml", schema_path="catalog.xsd")

# MCP server ingestion via URL
data = ingest_mcp("http://localhost:8000/mcp", method="resources")
```

## Using Registry

### Registering Custom Methods

```python
from semantica.ingest.registry import method_registry

def custom_file_ingestion(source, **kwargs):
    """Custom file ingestion function."""
    # Your custom implementation
    pass

# Register custom method
method_registry.register("file", "custom_method", custom_file_ingestion)

# Use custom method
from semantica.ingest.methods import ingest_file
files = ingest_file("document.pdf", method="custom_method")
```

### Listing Available Methods

```python
from semantica.ingest.methods import list_available_methods

# List all methods
all_methods = list_available_methods()
print(all_methods)

# List methods for specific task
file_methods = list_available_methods("file")
print(file_methods)
```

### Getting Registered Methods

```python
from semantica.ingest.methods import get_ingest_method

# Get method from registry
method = get_ingest_method("file", "custom_method")
if method:
    result = method("document.pdf")
```

## Configuration

### Environment Variables

```bash
# Set ingestion configuration via environment variables
export INGEST_DEFAULT_SOURCE_TYPE="file"
export INGEST_MAX_FILE_SIZE=10485760
export INGEST_RECURSIVE="true"
export INGEST_READ_CONTENT="true"
export INGEST_RATE_LIMIT_DELAY=1.0
export INGEST_RESPECT_ROBOTS="true"
export INGEST_BATCH_SIZE=100
export INGEST_TIMEOUT=30.0

# MCP server configuration (URL-based, Python/FastMCP only)
export MCP_SERVER_URL="http://localhost:8000/mcp"
export MCP_SERVER_TIMEOUT=30.0
```

### Programmatic Configuration

```python
from semantica.ingest.config import ingest_config

# Set configuration
ingest_config.set("default_source_type", "file")
ingest_config.set("max_file_size", 10485760)
ingest_config.set("recursive", True)

# Get configuration
source_type = ingest_config.get("default_source_type", default="file")
max_size = ingest_config.get("max_file_size", default=10485760)

# Method-specific configuration
ingest_config.set_method_config("file", max_size=10485760, recursive=True)
file_config = ingest_config.get_method_config("file")
```

### Config File (YAML)

```yaml
ingest:
  default_source_type: "file"
  max_file_size: 10485760
  recursive: true
  read_content: true
  rate_limit_delay: 1.0
  respect_robots: true
  batch_size: 100
  timeout: 30.0

ingest_methods:
  file:
    max_size: 10485760
    recursive: true
  web:
    delay: 1.0
    respect_robots: true
  feed:
    timeout: 30.0
  stream:
    batch_size: 1000
  mcp:
    timeout: 30.0
    # URL is provided when connecting, not in config file
```

```python
from semantica.ingest.config import IngestConfig

# Load from config file
config = IngestConfig(config_file="config.yaml")
```

## Advanced Examples

### Complete Ingestion Pipeline

```python
from semantica.ingest import ingest, ingest_file, ingest_web, ingest_feed

# Ingest from multiple sources
file_result = ingest_file("./documents", method="directory")
web_result = ingest_web("https://example.com", method="url")
feed_result = ingest_feed("https://example.com/feed.xml", method="rss")

# Process results
all_content = []
all_content.extend([f.content for f in file_result if hasattr(f, 'content')])
all_content.append(web_result.text)
all_content.extend([item.content for item in feed_result.items])
```

### Batch Processing with Progress Tracking

```python
from semantica.ingest import FileIngestor
from semantica.utils.progress_tracker import get_progress_tracker

ingestor = FileIngestor()
progress = get_progress_tracker()

# Ingest with progress tracking
files = ingestor.ingest_directory(
    "./documents",
    recursive=True,
    progress_callback=lambda current, total: progress.update(current, total)
)
```

### Error Handling

```python
from semantica.ingest import ingest
from semantica.utils.exceptions import ProcessingError

try:
    result = ingest("document.pdf", source_type="file")
except ProcessingError as e:
    print(f"Ingestion failed: {e}")
except Exception as e:
    print(f"Unexpected error: {e}")
```

### Custom Ingestion Method

```python
from semantica.ingest.registry import method_registry
from semantica.ingest.methods import ingest_file

def custom_pdf_ingestion(source, **kwargs):
    """Custom PDF ingestion with special processing."""
    from semantica.ingest import FileIngestor

    ingestor = FileIngestor()
    file_obj = ingestor.ingest_file(source, **kwargs)

    # Custom processing
    if file_obj.file_type == "pdf":
        # Add custom metadata
        file_obj.metadata["processed"] = True
        file_obj.metadata["custom_field"] = "custom_value"

    return file_obj

# Register custom method
method_registry.register("file", "custom_pdf", custom_pdf_ingestion)

# Use custom method
files = ingest_file("document.pdf", method="custom_pdf")
```

### Multi-Source Ingestion

```python
from semantica.ingest import ingest

# Ingest from multiple source types
sources = {
    "files": ["./documents"],
    "web": ["https://example.com"],
    "feeds": ["https://example.com/feed.xml"]
}

results = {}
for source_type, source_list in sources.items():
    for source in source_list:
        try:
            result = ingest(source, source_type=source_type)
            results[source] = result
        except Exception as e:
            print(f"Failed to ingest {source}: {e}")
```

## Best Practices

1. **Source Type Selection**: Choose the appropriate source type for your data
   - Files: Local filesystem or cloud storage
   - Web: URLs, sitemaps, domain crawling
   - Feeds: RSS, Atom feeds
   - Streams: Real-time data streams (Kafka, RabbitMQ, etc.)
   - Repositories: Git repositories
   - Emails: IMAP, POP3 email servers
   - Databases: SQL databases
   - MCP Servers: Any Python-based MCP server (databases, file systems, APIs, etc.)

2. **Rate Limiting**: Always use rate limiting for web ingestion
   ```python
   ingestor = WebIngestor(delay=1.0, respect_robots=True)
   ```

3. **Error Handling**: Always handle ingestion errors gracefully
   ```python
   try:
       result = ingest(source, source_type="file")
   except Exception as e:
       logger.error(f"Ingestion failed: {e}")
   ```

4. **Batch Processing**: Use batch processing for large datasets
   ```python
   ingestor = FileIngestor()
   files = ingestor.ingest_directory("./documents", batch_size=100)
   ```

5. **Progress Tracking**: Use progress tracking for long-running operations
   ```python
   from semantica.utils.progress_tracker import get_progress_tracker
   progress = get_progress_tracker()
   ```

6. **Configuration Management**: Use environment variables or config files for consistent settings
   ```python
   ingest_config.set("default_source_type", "file")
   ```

7. **Resource Cleanup**: Always cleanup resources after ingestion
   ```python
   processor = ingest_stream(config, method="kafka")
   try:
       processor.start_consuming()
   finally:
       processor.stop()
   ```

## Performance Tips

1. **Parallel Processing**: Use parallel processing for multiple sources
   ```python
   from concurrent.futures import ThreadPoolExecutor

   with ThreadPoolExecutor() as executor:
       executor.submit(ingest_file, "./documents1")
       executor.submit(ingest_file, "./documents2")
   ```

2. **Caching**: Cache ingested content when possible
   ```python
   # Check if already ingested
   if not Path("cache/document.pdf").exists():
       result = ingest_file("document.pdf")
       # Cache result
   ```

3. **Streaming**: Use streaming for large files or datasets
   ```python
   # Stream processing for large files
   processor = ingest_stream(config, method="kafka")
   processor.set_message_handler(process_message)
   ```

4. **Connection Pooling**: Reuse connections for database ingestion
   ```python
   connector = DatabaseConnector("postgresql")
   engine = connector.connect(connection_string)
   # Reuse engine for multiple queries
   ```

6. **MCP Server Connection Reuse**: Reuse MCP server connections for multiple operations
   ```python
   ingestor = MCPIngestor()
   ingestor.connect("server1", transport="stdio", command="python", args=["-m", "mcp_server"])
   # Reuse connection for multiple operations
   data1 = ingestor.ingest_resources("server1")
   data2 = ingestor.ingest_tool_output("server1", tool_name="get_data", arguments={})
   ```

5. **Memory Management**: Process large datasets in batches
   ```python
   # Process in batches to avoid memory issues
   for batch in process_in_batches(large_dataset, batch_size=1000):
       result = ingest(batch)
   ```
