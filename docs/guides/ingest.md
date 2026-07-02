---
title: "Ingest Anything"
description: "Load data from files, websites, Git repos, databases, Kafka streams, RSS feeds, and more — unified ingestion API."
---

Semantica's ingest module provides a single consistent function call for each source type. File, web, and feed sources return objects with a `.text` property. API and database sources return structured objects (`APIData.data`, `List[Dict]`) that you transform into text before storage. Git repository sources return a dict with `code_files` and `commits` keys; stream sources return `StreamMessage` objects with a `.content` field. All of them compose cleanly into one graph ingestion script — see the per-source sections for the exact access pattern.

<Info>
  All ingest functions live in `semantica.ingest`. Optional dependencies are loaded lazily — you only need `pip install beautifulsoup4` for web/feed ingestion, `pip install gitpython` for repository ingestion, and `pip install pyarrow` for Parquet. Missing a dependency raises a clear `ImportError` message naming the exact package.
</Info>

## Why Ingestion Matters

Before Semantica can analyze, search, reason over, or connect your data, it needs to reach the data. Ingestion is that first step — pulling content from wherever it lives and converting it into a form that `AgentContext` can store and index.

Once ingested, your content flows into two places: a vector index for semantic search and an optional `ContextGraph` for entity relationships. From there, every downstream module — semantic extraction, reasoning, GraphRAG, decision intelligence — operates on the same unified data, regardless of whether it originally came from a PDF, a database row, an API response, or a live stream.

## Typical Workflow

Most ingestion pipelines follow the same four steps regardless of source type:

1. **Connect to the source** — call the appropriate ingest function with your connection details.
2. **Retrieve the data** — the function returns either text-bearing objects (files, web, feeds) or structured data (APIs, databases) that need one more step.
3. **Transform when necessary** — for structured sources, build a plain text string from each record so `AgentContext.store()` can embed and index it.
4. **Store in AgentContext** — pass a string, a list of strings, or a list of dicts to `context.store()`. Optionally enable entity and relationship extraction to populate a `ContextGraph` at the same time.

```python
from semantica.context import AgentContext, ContextGraph
from semantica.vector_store import VectorStore

# AgentContext is the entry point for storage.
# ContextGraph is optional — attach it to build a searchable entity graph.
graph   = ContextGraph()
context = AgentContext(
    vector_store    = VectorStore(backend="faiss", dimension=768),
    knowledge_graph = graph,   # omit if you only need vector search
)

# store() accepts a string, a list of strings, or a list of dicts
context.store("A single observation or document text.")
context.store(["Doc one text.", "Doc two text."])
context.store([{"content": "Doc text.", "metadata": {"source": "wiki"}}])
```

## When To Use Ingestion

Use the ingest module when your data lives outside Semantica and you need to bring it in:

- **Files and documents** — PDFs, Word docs, CSVs, JSON, XML, and whole directories on disk or in cloud storage.
- **Web content** — public documentation sites, regulatory publication pages, news feeds, or any URL you can crawl.
- **REST APIs** — internal platforms (SIEM, EDR, ITSM, CRM), threat intelligence feeds, or any paginated HTTP endpoint.
- **Databases** — existing SQL databases where relevant records can be fetched with a targeted query.
- **Live streams** — Kafka or other message brokers where you need to process events as they arrive.
- **Git repositories** — source code, documentation, or configuration files tracked in version control.

If your data is already a Python string or dict in memory, skip ingestion and call `context.store()` directly.

## Source 1 — PDF Vendor Reports and Internal Documents

Pass a file path or directory to `ingest_file()` to extract plain text from PDFs and other document formats. This works equally well for vendor threat reports, internal policy documents, product manuals, or any text-bearing file on disk:

```python
from semantica.ingest import ingest_file

# Single file
report = ingest_file("apt29_q4_2024.pdf", method="file")
print(report.text[:500])       # extracted plain text
print(report.metadata)         # {"file_type": "pdf", "size": 1843200, ...}
print(report.name)             # "apt29_q4_2024.pdf"
print(report.file_type)        # "pdf"

# Whole directory at once — recursive by default
reports = ingest_file("./vendor_reports/", method="directory", recursive=True)
for r in reports:
    print(f"{r.name}: {len(r.text)} chars extracted")

# apt29_q4_2024.pdf:    42317 chars extracted
# lazarus_group_h2.pdf: 38901 chars extracted
# fin7_campaign.pdf:    51204 chars extracted
# cozy_bear_ttps.pdf:   29876 chars extracted
```

`ingest_file()` returns a `FileObject` (single file) or `List[FileObject]` (directory). The `.text` property is always a decoded string — you never handle bytes or encoding manually. For DOCX, XLSX, CSV, TXT, JSON, and XML files the same call works; file type is detected from the extension and MIME type automatically.

The same approach works for internal knowledge bases. If your team stores runbooks, product documentation, or customer-facing guides as PDFs or Word documents:

```python
from semantica.ingest import ingest_file
from semantica.context import AgentContext, ContextGraph
from semantica.vector_store import VectorStore

graph   = ContextGraph(advanced_analytics=True)
context = AgentContext(
    vector_store    = VectorStore(backend="faiss"),
    knowledge_graph = graph,
)

# Internal documentation — same API as vendor reports
docs = ingest_file("./internal_docs/", method="directory", recursive=True)
doc_texts = [d.text for d in docs]
context.store(doc_texts, extract_entities=True)
```

If your vendor also drops reports into an S3 bucket, switch to cloud ingestion without changing the rest of your pipeline:

```python
s3_reports = ingest_file(
    "s3://intel-vendor-bucket/weekly-reports/",
    method="cloud",
    provider="s3",
    aws_access_key_id="AKIA...",
    aws_secret_access_key="...",
)
# Returns List[FileObject] — same shape as the local directory call
```

## Source 2 — REST APIs

`RESTIngestor` handles authentication, retry logic, and pagination. Unlike file sources, REST APIs return structured JSON — `APIData.data` is a `List[Dict]`, not a text string. You need to build a text representation from each record before passing it to `AgentContext.store()`.

```python
from semantica.ingest import RESTIngestor

ingestor = RESTIngestor()

# Single paginated endpoint — returns APIData
# APIData.data is List[Dict] — one dict per record, not a .text string
api_data = ingestor.ingest_endpoint(
    "https://misp.internal/events/restSearch",
    headers={"Authorization": "YOUR_MISP_API_KEY"},
    params={"limit": 100, "page": 1, "threat_level_id": "1"},
)

# api_data.data is List[Dict] — one dict per event
events = api_data.data
print(f"Retrieved {len(events)} MISP events")
print(f"Endpoint: {api_data.endpoint}")
print(f"Status:   {api_data.response_status}")

# Convert to text blobs for the knowledge graph
event_texts = []
for event in events:
    attrs = ", ".join(
        a.get("value", "") for a in event.get("Event", {}).get("Attribute", [])
    )
    text = (
        f"MISP Event {event['Event']['id']}: "
        f"{event['Event'].get('info', '')} "
        f"[TLP: {event['Event'].get('distribution', '')}] "
        f"Attributes: {attrs[:300]}"
    )
    event_texts.append(text)
```

The same pattern applies to any REST API — a support ticket system, a CRM, or an internal service catalog. Fetch the structured records, then build a sentence or two per record that captures the key facts for search and extraction.

For endpoints that return thousands of records across many pages, `paginated_fetch()` walks all pages automatically and returns one `APIData` object per page:

```python
all_events = ingestor.paginated_fetch(
    "https://misp.internal/events/restSearch",
    headers={"Authorization": "YOUR_MISP_API_KEY"},
    page_size=100,
)
# all_events is List[APIData] across all pages
total_events = sum(len(page.data) for page in all_events if isinstance(page.data, list))
print(f"Pages fetched: {len(all_events)}")
print(f"Total events fetched: {total_events}")
```

## Source 3 — SQL Databases

`DBIngestor.execute_query()` returns `List[Dict]` — one dict per row. Like REST APIs, database results are structured data and require a text transformation step before storage in `AgentContext`. Keep your query focused: fetch only the rows and columns you actually need rather than dumping entire tables.

For ad hoc SQL queries, use `DBIngestor.execute_query()`:

```python
from semantica.ingest import DBIngestor

db = DBIngestor()

# Returns List[Dict] — one dict per row
cves = db.execute_query(
    "postgresql://readonly:pass@cvedb.internal:5432/nvd",
    """
        SELECT
            cve_id,
            description,
            cvss_v3_score,
            affected_products,
            published_date,
            last_modified
        FROM cve_records
        WHERE cvss_v3_score >= 7.0
          AND published_date >= NOW() - INTERVAL '30 days'
        ORDER BY cvss_v3_score DESC
    """,
)

print(f"High-severity CVEs (last 30 days): {len(cves)}")

# Convert rows to text for the knowledge graph
cve_texts = [
    f"{r['cve_id']} (CVSS {r['cvss_v3_score']}): "
    f"{r['description']} "
    f"Affects: {r['affected_products']}"
    for r in cves
]
```

The same `DBIngestor.execute_query()` pattern covers MySQL, SQLite, Oracle, and SQL Server — swap the connection string. For schema discovery before writing your query:

```python
schema = db.execute_query(
    "postgresql://readonly:pass@cvedb.internal:5432/nvd",
    """
        SELECT table_name, column_name, data_type
        FROM information_schema.columns
        WHERE table_schema = 'public'
        ORDER BY table_name, ordinal_position
    """,
)
for col in schema[:10]:
    print(f"{col['table_name']}.{col['column_name']} ({col['data_type']})")
```

## Source 4 — RSS and Atom Feeds

`ingest_feed()` pulls RSS and Atom feeds and returns a `FeedData` object with a list of `FeedItem` objects. Each item exposes `.title`, `.description`, and `.published` as strings — they are ready to concatenate into text without further transformation:

```python
from semantica.ingest import ingest_feed

# RSS feed — returns FeedData; iterate .items for FeedItem objects
feed = ingest_feed(
    "https://github.com/advisories.atom",
    method="atom",
)

print(f"Feed title:   {feed.title}")
print(f"Total items:  {len(feed.items)}")

# Convert feed items to text blobs
advisory_texts = []
for item in feed.items:
    text = f"Advisory: {item.title}\n{item.description}"
    advisory_texts.append(text)
    print(f"  {item.title[:80]}  [{item.published}]")

# For NVD's own RSS feed of new CVEs:
nvd_feed = ingest_feed(
    "https://nvd.nist.gov/feeds/xml/cve/misc/nvd-rss.xml",
    method="rss",
)
nvd_texts = [
    f"{item.title}: {item.description}"
    for item in nvd_feed.items
]
```

If you don't know whether a site uses RSS or Atom, `method="discover"` finds all available feed URLs from the page's HTML link tags:

```python
feeds = ingest_feed("https://github.com/advisories", method="discover")
# feeds is a list of validated feed URLs
for f in feeds:
    print(f)
```

## Source 5 — Filesystem STIX Bundles

Use `ingest_file()` on a directory to extract text from every STIX JSON file deposited by an overnight daemon:

```python
from semantica.ingest import ingest_file

# Ingest all STIX JSON files from the directory
stix_files = ingest_file("./stix_bundles/", method="directory", recursive=True)

stix_texts = []
for f in stix_files:
    if f.file_type == "json":
        stix_texts.append(f.text)
        print(f"{f.name}: {f.size:,} bytes")

# apt29_stix_bundle_2024-12-01.json:  184,320 bytes
# lazarus_stix_bundle_2024-12-01.json: 97,408 bytes
# fin7_stix_bundle_2024-12-01.json:   211,968 bytes
```

For large XML-based STIX 1.x bundles, use `ingest_xml()` to get structured parse results instead of raw text:

```python
from semantica.ingest import ingest_xml

stix_xml_files = ingest_xml("./stix_xml_bundles/", method="directory")
for bundle in stix_xml_files:
    print(f"{bundle.source_path}: {len(bundle.elements)} elements parsed")
```

## Combining All Five Sources

Once you have text from each source, `AgentContext.store()` accepts a flat list of strings. Semantica embeds and indexes them together — the context graph has no concept of which string came from which source unless you add metadata explicitly.

With each source returning text, pass everything into `AgentContext.store()` in one batch:

```python
from semantica.context import AgentContext, ContextGraph
from semantica.vector_store import VectorStore
from semantica.ingest import ingest_file, ingest_feed, RESTIngestor, DBIngestor

# --- Infrastructure ---
graph   = ContextGraph(advanced_analytics=True)
context = AgentContext(
    vector_store    = VectorStore(backend="faiss", dimension=768),
    knowledge_graph = graph,
    graph_expansion = True,
)

# --- Source 1: PDF reports ---
reports      = ingest_file("./vendor_reports/", method="directory")
report_texts = [r.text for r in reports]

# --- Source 2: MISP API ---
ingestor   = RESTIngestor()
api_data   = ingestor.paginated_fetch(
    "https://misp.internal/events/restSearch",
    headers={"Authorization": "YOUR_MISP_API_KEY"},
    page_size=100,
)
misp_texts = [
    f"MISP {e['Event']['id']}: {e['Event'].get('info', '')} "
    f"attrs={len(e['Event'].get('Attribute', []))}"
    for page in api_data
    for e in page.data
]

# --- Source 3: PostgreSQL CVEs ---
db        = DBIngestor()
cves      = db.execute_query(
    "postgresql://readonly:pass@cvedb.internal:5432/nvd",
    "SELECT cve_id, description, cvss_v3_score FROM cve_records "
    "WHERE cvss_v3_score >= 7.0 AND published_date >= NOW() - INTERVAL '30 days'",
)
cve_texts = [f"{r['cve_id']} (CVSS {r['cvss_v3_score']}): {r['description']}" for r in cves]

# --- Source 4: GitHub Advisory feed ---
feed           = ingest_feed("https://github.com/advisories.atom", method="atom")
advisory_texts = [f"{item.title}: {item.description}" for item in feed.items]

# --- Source 5: STIX bundles ---
stix_files = ingest_file("./stix_bundles/", method="directory")
stix_texts = [f.text for f in stix_files if f.file_type == "json"]

# --- Combine and store ---
all_texts = report_texts + misp_texts + cve_texts + advisory_texts + stix_texts

context.store(
    all_texts,
    extract_entities      = True,
    extract_relationships = True,
)

s = graph.stats()
print(f"Graph: {s['node_count']} nodes, {s['edge_count']} edges")
print(f"Total documents ingested: {len(all_texts)}")
```

## Common Pitfalls

**Ingesting more data than needed.** Fetching entire tables or crawling unlimited pages fills your vector index with noise and slows retrieval. Use `WHERE` clauses, date filters, and `page_size` limits to fetch only the records relevant to your use case.

**Poor text quality from structured data.** A database row or API response contains field names, IDs, and raw values — not sentences. A string like `"2025-06-21|CVE-2024-3400|10.0"` will embed poorly and produce weak search results. Format each record as a natural sentence: `"CVE-2024-3400 (CVSS 10.0): critical RCE in PAN-OS, published 2025-06-21."` The extra effort pays off in retrieval quality.

**Not handling pagination.** `RESTIngestor.ingest_endpoint()` fetches a single page. If your endpoint has thousands of records, use `paginated_fetch()` — otherwise you silently ingest only the first page.

**Rate limits on APIs.** `RESTIngestor` automatically retries on HTTP 429 responses with exponential back-off (controlled by `backoff_factor` in `RESTIngestor(config={"backoff_factor": 2})`). This handles burst rate limits reactively, but does not proactively pace requests between successful calls. For APIs with strict per-second quotas, reduce `page_size` to lower request frequency or add delays between `paginated_fetch()` calls in your own loop.

**Large database exports.** Exporting hundreds of thousands of rows into `AgentContext` is rarely the right approach. Write a query that selects only the records relevant to your domain, filters by date range, and projects only the columns you need for text formatting.

## Handling Errors Gracefully

Wrap each source in a try/except so the pipeline continues and reports failures at the end rather than crashing on the first bad source. This is especially important in scheduled jobs where partial data is better than no data:

```python
from semantica.ingest import ingest_file, ingest_feed, RESTIngestor, DBIngestor

all_texts = []
errors    = []

# Source 1: PDFs
try:
    reports = ingest_file("./vendor_reports/", method="directory")
    all_texts.extend(r.text for r in reports)
    print(f"PDFs:       {len(reports)} files ingested")
except Exception as e:
    errors.append(f"PDF ingest failed: {e}")

# Source 2: MISP
try:
    ingestor = RESTIngestor()
    events   = ingestor.paginated_fetch(
        "https://misp.internal/events/restSearch",
        headers={"Authorization": "YOUR_MISP_API_KEY"},
        page_size=100,
    )
    all_texts.extend(
        f"MISP {e['Event']['id']}: {e['Event'].get('info', '')}"
        for page in events
        for e in page.data
    )
    print(f"MISP:       {sum(len(page.data) for page in events if isinstance(page.data, list))} events ingested")
except Exception as e:
    errors.append(f"MISP API failed: {e}")

# Source 3: PostgreSQL
try:
    db = DBIngestor()
    cves = db.execute_query(
        "postgresql://readonly:pass@cvedb.internal:5432/nvd",
        "SELECT cve_id, description, cvss_v3_score FROM cve_records "
        "WHERE cvss_v3_score >= 7.0 AND published_date >= NOW() - INTERVAL '30 days'",
    )
    all_texts.extend(f"{r['cve_id']}: {r['description']}" for r in cves)
    print(f"CVEs:       {len(cves)} records ingested")
except Exception as e:
    errors.append(f"PostgreSQL failed: {e}")

# Source 4: GitHub feed
try:
    feed = ingest_feed("https://github.com/advisories.atom", method="atom")
    all_texts.extend(f"{item.title}: {item.description}" for item in feed.items)
    print(f"Advisories: {len(feed.items)} items ingested")
except Exception as e:
    errors.append(f"GitHub feed failed: {e}")

# Source 5: STIX files
try:
    stix_files = ingest_file("./stix_bundles/", method="directory")
    stix_texts = [f.text for f in stix_files if f.file_type == "json"]
    all_texts.extend(stix_texts)
    print(f"STIX:       {len(stix_texts)} bundles ingested")
except Exception as e:
    errors.append(f"STIX directory failed: {e}")

# Report any failures — don't silently swallow them
if errors:
    print(f"\n{len(errors)} source(s) failed:")
    for err in errors:
        print(f"  - {err}")

print(f"\nTotal documents for graph: {len(all_texts)}")
```

## Scheduling Recurring Ingestion

Wrap the combined ingestion in a function and call it from your scheduler of choice (cron, Airflow, a cloud scheduler):

```python
from datetime import datetime, timedelta
from semantica.context import AgentContext, ContextGraph
from semantica.vector_store import VectorStore
from semantica.ingest import ingest_file, ingest_feed, RESTIngestor, DBIngestor

def run_daily_ingest(since: datetime = None):
    """Run the full five-source ingest pipeline. Returns graph stats dict."""
    since = since or datetime.now() - timedelta(days=1)

    graph   = ContextGraph(advanced_analytics=True)
    context = AgentContext(
        vector_store    = VectorStore(backend="faiss", dimension=768),
        knowledge_graph = graph,
        graph_expansion = True,
    )

    all_texts = []
    errors    = []

    # PDFs deposited since last run
    try:
        reports = ingest_file("./vendor_reports/", method="directory")
        # Filter by modification time in production — simplified here
        all_texts.extend(r.text for r in reports)
    except Exception as e:
        errors.append(f"PDF: {e}")

    # MISP events since last run
    try:
        ingestor = RESTIngestor()
        events   = ingestor.paginated_fetch(
            "https://misp.internal/events/restSearch",
            headers={"Authorization": "YOUR_MISP_API_KEY"},
            params={"timestamp": int(since.timestamp())},
            page_size=100,
        )
        all_texts.extend(
            f"MISP {e['Event']['id']}: {e['Event'].get('info', '')}"
            for page in events
            for e in page.data
        )
    except Exception as e:
        errors.append(f"MISP: {e}")

    # CVEs published since last run
    try:
        db = DBIngestor()
        cves = db.execute_query(
            "postgresql://readonly:pass@cvedb.internal:5432/nvd",
            f"SELECT cve_id, description, cvss_v3_score FROM cve_records "
            f"WHERE published_date >= '{since.isoformat()}' AND cvss_v3_score >= 7.0",
        )
        all_texts.extend(f"{r['cve_id']}: {r['description']}" for r in cves)
    except Exception as e:
        errors.append(f"PostgreSQL: {e}")

    # GitHub advisory feed (always latest)
    try:
        feed = ingest_feed("https://github.com/advisories.atom", method="atom")
        all_texts.extend(f"{item.title}: {item.description}" for item in feed.items)
    except Exception as e:
        errors.append(f"GitHub feed: {e}")

    # STIX bundles deposited since last run
    try:
        stix_files = ingest_file("./stix_bundles/", method="directory")
        all_texts.extend(f.text for f in stix_files if f.file_type == "json")
    except Exception as e:
        errors.append(f"STIX: {e}")

    if all_texts:
        context.store(all_texts, extract_entities=True, extract_relationships=True)
        context.save("./cti_state/")

    return {
        "run_at":     datetime.now().isoformat(),
        "documents":  len(all_texts),
        "errors":     errors,
        "graph":      graph.stats(),
    }

if __name__ == "__main__":
    result = run_daily_ingest()
    print(f"Ingested {result['documents']} documents")
    print(f"Graph: {result['graph']['node_count']} nodes, {result['graph']['edge_count']} edges")
    if result["errors"]:
        print("Errors:", result["errors"])
```

## Business Examples

These two patterns come up frequently outside of security and research contexts.

**Internal product documentation.** If your team maintains product docs, runbooks, or onboarding guides as Markdown or PDF files in a shared drive, ingest them once and let agents answer questions against the full corpus rather than keyword search.

```python
from semantica.ingest import ingest_file
from semantica.context import AgentContext, ContextGraph
from semantica.vector_store import VectorStore

graph   = ContextGraph(advanced_analytics=True)
context = AgentContext(
    vector_store    = VectorStore(backend="faiss"),
    knowledge_graph = graph,
)

docs = ingest_file("./product_docs/", method="directory", recursive=True)
context.store(
    [d.text for d in docs],
    extract_entities=True,
)
print(f"Indexed {len(docs)} documentation pages")
```

**Customer support tickets from a database.** Support tickets stored in a SQL database capture real-world product issues in natural language. Ingesting them lets you surface patterns, find similar past issues, and build retrieval-augmented support tools.

```python
from semantica.ingest import DBIngestor
from semantica.context import AgentContext, ContextGraph
from semantica.vector_store import VectorStore

graph   = ContextGraph(advanced_analytics=True)
context = AgentContext(
    vector_store    = VectorStore(backend="faiss"),
    knowledge_graph = graph,
)

db = DBIngestor()
# Fetch only resolved tickets from the last 90 days — avoid full table dumps
tickets = db.execute_query(
    "postgresql://readonly:YOUR_DB_PASSWORD@support-db:5432/helpdesk",
    """
        SELECT ticket_id, subject, description, resolution, product_area
        FROM support_tickets
        WHERE status = 'resolved'
          AND created_at >= NOW() - INTERVAL '90 days'
        ORDER BY created_at DESC
        LIMIT 5000
    """,
)

# Transform each row into a readable text string
# Guard against NULL description/resolution — common in real helpdesk schemas
ticket_texts = [
    f"Ticket {r['ticket_id']} [{r['product_area']}]: {r['subject']}. "
    f"Description: {(r['description'] or '')[:300]}. "
    f"Resolution: {(r['resolution'] or '')[:200]}"
    for r in tickets
]

context.store(ticket_texts, extract_entities=True)
print(f"Indexed {len(ticket_texts)} support tickets")
```

## Domain Examples

The following examples show complete multi-source pipelines for common deployment contexts. Each follows the same workflow: ingest from multiple sources, transform structured data into text, then store in a shared context.

<Tabs>
  <Tab title="Defense — CTI/Threat">
    A joint intelligence cell fuses three live sources every six hours: NVD CVE RSS, classified PDF drops from a partner agency, and an internal MISP instance.

```python
from semantica.ingest import ingest_file, ingest_feed, RESTIngestor
from semantica.context import AgentContext, ContextGraph
from semantica.vector_store import VectorStore

graph   = ContextGraph(advanced_analytics=True, community_detection=True)
context = AgentContext(
    vector_store    = VectorStore(backend="faiss", dimension=768),
    knowledge_graph = graph,
    graph_expansion = True,
)

# NVD CVE feed — new CVEs in last 6 hours
nvd_feed  = ingest_feed(
    "https://nvd.nist.gov/feeds/xml/cve/misc/nvd-rss.xml",
    method="rss",
)
nvd_texts = [f"{item.title}: {item.description}" for item in nvd_feed.items]

# Classified PDF drop from partner agency
partner_docs  = ingest_file("//partner-share/intel-drops/", method="directory")
partner_texts = [doc.text for doc in partner_docs]

# MISP events tagged TLP:AMBER or higher
ingestor   = RESTIngestor()
misp_data  = ingestor.paginated_fetch(
    "https://misp.internal/events/restSearch",
    headers={"Authorization": "YOUR_MISP_API_KEY"},
    params={"tags": "tlp:amber||tlp:red", "threat_level_id": "1"},
    page_size=100,
)
misp_texts = [
    f"MISP {e['Event']['id']}: {e['Event'].get('info', '')}"
    for page in misp_data
    for e in page.data
]

# Fuse all three into the graph
context.store(
    nvd_texts + partner_texts + misp_texts,
    extract_entities=True, extract_relationships=True,
)
print(f"Fused graph: {graph.stats()['node_count']} nodes")
```

  </Tab>

  <Tab title="Security — SOC/Incident">
    During an active incident the SOC enriches the timeline on a 15-minute cycle from three sources: SIEM alert CSV exports, an EDR REST API, and the internal CVE database.

```python
from semantica.ingest import ingest_file, RESTIngestor, DBIngestor
from semantica.context import AgentContext, ContextGraph
from semantica.vector_store import VectorStore

graph   = ContextGraph(advanced_analytics=True)
context = AgentContext(
    vector_store    = VectorStore(backend="faiss", dimension=768),
    knowledge_graph = graph,
)

# SIEM alert CSV exports (written by SIEM every 15 minutes)
alert_files  = ingest_file("./siem_exports/", method="directory")
alert_texts  = [
    f.text for f in alert_files if f.file_type == "csv"
]

# EDR platform REST API — host telemetry for the affected segment
ingestor  = RESTIngestor()
edr_data  = ingestor.ingest_endpoint(
    "https://edr.internal/api/v1/telemetry",
    headers={"X-API-Key": "EDR_KEY"},
    params={"segment": "finance", "severity": "high", "limit": 500},
)
edr_texts = [
    f"Host {e.get('hostname')}: {e.get('event_type')} — {e.get('description')}"
    for e in edr_data.data
]

# CVE cross-reference for any CVE IDs observed in alerts
db = DBIngestor()
exploited_cves = db.execute_query(
    "postgresql://readonly:pass@cvedb.internal:5432/nvd",
    "SELECT cve_id, description, cvss_v3_score FROM cve_records "
    "WHERE cve_id = ANY(ARRAY['CVE-2024-3400', 'CVE-2024-21762'])",
)
cve_texts = [f"{r['cve_id']} (CVSS {r['cvss_v3_score']}): {r['description']}"
             for r in exploited_cves]

context.store(
    alert_texts + edr_texts + cve_texts,
    extract_entities=True, extract_relationships=True,
)
print(f"Incident graph: {graph.stats()['node_count']} nodes enriched")
```

  </Tab>

  <Tab title="Life Science — Clinical/Pharma">
    A pharmacovigilance platform ingests three data sources after each trial phase closes: FDA submission PDFs, a PostgreSQL clinical trials database, and PubMed literature via web scraping.

```python
from semantica.ingest import ingest_file, ingest_web, DBIngestor
from semantica.context import AgentContext, ContextGraph
from semantica.vector_store import VectorStore

graph   = ContextGraph(advanced_analytics=True)
context = AgentContext(
    vector_store    = VectorStore(backend="faiss", dimension=768),
    knowledge_graph = graph,
    retention_days  = None,   # regulatory data — unlimited retention
)

# FDA submissions for Phase III oncology trials
submissions  = ingest_file("./fda_submissions/phase3_oncology/", method="directory")
sub_texts    = [s.text for s in submissions]

# Clinical trials database — protocol and AE records
db = DBIngestor()
trial_records = db.execute_query(
    "postgresql://readonly:pass@clindb.internal:5432/trials",
    """
        SELECT t.protocol_id, t.title, t.primary_endpoint,
               ae.event_type, ae.severity, ae.frequency_pct
        FROM clinical_trials t
        JOIN adverse_events ae ON t.protocol_id = ae.protocol_id
        WHERE t.phase = 'III' AND t.therapeutic_area = 'oncology'
        ORDER BY ae.severity DESC
    """,
)
trial_texts = [
    f"Protocol {r['protocol_id']}: {r['title']} "
    f"AE: {r['event_type']} (severity={r['severity']}, freq={r['frequency_pct']}%)"
    for r in trial_records
]

# PubMed literature for the drug compound
pubmed_pages = ingest_web(
    "https://pubmed.ncbi.nlm.nih.gov/?term=dapagliflozin+cardiovascular",
    method="url",
)
pub_texts = [pubmed_pages.text]

context.store(
    sub_texts + trial_texts + pub_texts,
    extract_entities=True, extract_relationships=True,
)
print(f"Pharmacovigilance graph: {graph.stats()['node_count']} nodes")
```

  </Tab>

  <Tab title="Banking — Risk/Compliance">
    A compliance team pulls from three sources each quarter: BIS and Basel publications (web sitemap crawl), internal policy PDFs, and a regulatory rules database.

```python
from semantica.ingest import ingest_file, ingest_web, DBIngestor
from semantica.context import AgentContext, ContextGraph
from semantica.vector_store import VectorStore

graph   = ContextGraph(advanced_analytics=True)
context = AgentContext(
    vector_store    = VectorStore(backend="faiss", dimension=768),
    knowledge_graph = graph,
    retention_days  = 2555,   # 7-year regulatory retention requirement
)

# BIS/Basel publications via sitemap crawl — filter to capital/liquidity pages
bis_pages    = ingest_web("https://www.bis.org/sitemap.xml", method="sitemap")
basel_pages  = [p for p in bis_pages if any(
    kw in p.url.lower() for kw in ["bcbs", "capital", "liquidity", "leverage"]
)]
bis_texts    = [p.text for p in basel_pages]
print(f"BIS pages matched: {len(bis_texts)}")

# Internal policy library
policies     = ingest_file("./regulatory_library/", method="directory", recursive=True)
policy_texts = [p.text for p in policies]

# Regulatory rules database — active rules only
db = DBIngestor()
rules = db.execute_query(
    "postgresql://compliance_ro:pass@regdb.internal:5432/compliance",
    """
        SELECT rule_id, title, requirement_text, effective_date, jurisdiction
        FROM regulations
        WHERE active = true AND jurisdiction IN ('EU', 'US', 'UK')
        ORDER BY effective_date DESC
    """,
)
rule_texts = [
    f"{r['rule_id']} [{r['jurisdiction']}] {r['title']}: {r['requirement_text']}"
    for r in rules
]

context.store(
    bis_texts + policy_texts + rule_texts,
    extract_entities=True, extract_relationships=True,
)
print(f"Compliance graph: {graph.stats()['node_count']} nodes, "
      f"{graph.stats()['edge_count']} edges")
```

  </Tab>
</Tabs>

## Related Guides

- [Pipeline](pipeline) — chain ingest steps with `PipelineBuilder` for automated, retryable, parallelised workflows
- [Context Graphs](context-graphs) — storing and querying the entities you ingest as a typed property graph
- [Semantic Extraction](semantic-extraction) — NER, relation extraction, and triplet extraction from ingested text
- [Provenance](provenance) — tracking the origin document, confidence score, and ingestion timestamp for every extracted entity
