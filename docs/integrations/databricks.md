---
title: "Databricks Integration"
description: "Ingest Unity Catalog metadata and Delta Lake tables from Databricks into Semantica's KG pipeline."
icon: "cloud"
---

> Extract Delta Lake tables and Unity Catalog metadata (schemas, lineage) from Databricks into Semantica with personal access token or OAuth M2M authentication.


## Installation

```bash
# Install with Databricks support
pip install "semantica[db-databricks]"

# Or install the connectors separately
pip install databricks-sdk databricks-sql-connector
```


## Basic Usage

```python
from semantica.ingest import DatabricksIngestor
import os

ingestor = DatabricksIngestor(
    host=os.getenv("DATABRICKS_HOST"),           # e.g. https://adb-xxx.azuredatabricks.net
    token=os.getenv("DATABRICKS_TOKEN"),
    http_path=os.getenv("DATABRICKS_HTTP_PATH"),  # SQL warehouse or cluster HTTP path
    catalog=os.getenv("DATABRICKS_CATALOG", "main"),
    schema=os.getenv("DATABRICKS_SCHEMA", "default"),
)

data = ingestor.ingest_table("customers")
print(f"Retrieved {data.row_count} rows: columns: {data.columns}")
```

<Tip>
Use environment variables (or a `.env` file with `python-dotenv`) to keep credentials out of source code. `DatabricksIngestor()` with no arguments reads from `DATABRICKS_*` environment variables automatically.
</Tip>


## Authentication Methods

<Tabs>
  <Tab title="Personal Access Token">
    ```python
    ingestor = DatabricksIngestor(
        host="https://adb-xxx.azuredatabricks.net",
        token="dapi-xxxxxxxx",
        http_path="/sql/1.0/warehouses/xxxxxxxx",
    )
    ```
  </Tab>
  <Tab title="OAuth M2M (Recommended)">
    ```python
    ingestor = DatabricksIngestor(
        host="https://adb-xxx.azuredatabricks.net",
        client_id="your_service_principal_client_id",
        client_secret="your_service_principal_client_secret",
        http_path="/sql/1.0/warehouses/xxxxxxxx",
    )
    ```
    Preferred for production: no long-lived personal token stored in config.
  </Tab>
</Tabs>

<Note>
`http_path` identifies the SQL warehouse or all-purpose cluster used for query execution. Find it in the Databricks UI under **SQL Warehouses → Connection details**. Unity Catalog metadata calls (`list_catalogs`, `get_table_schema`, `get_table_lineage`, …) only need `host` and credentials — `http_path` is not required for those.
</Note>


## Querying

### Ingest a table with filters

```python
data = ingestor.ingest_table(
    "customers",
    catalog="main",
    schema="default",
    where="country = 'USA' AND created_date > '2024-01-01'",
    order_by="created_date DESC",
    limit=10000,
)
```

### Custom SQL

```python
data = ingestor.ingest_query("""
    SELECT customer_id, SUM(amount) AS total_amount
    FROM main.default.sales
    WHERE date >= '2024-01-01'
    GROUP BY customer_id
""")
```


## Unity Catalog Metadata

### Schema introspection

```python
schema = ingestor.get_table_schema("customers")
for column in schema["columns"]:
    print(f"{column['name']}: {column['type']}")
```

### Catalogs, schemas, and tables

```python
catalogs = ingestor.list_catalogs()
schemas = ingestor.list_schemas(catalog="main")
tables = ingestor.list_tables(catalog="main", schema="default")
```

### Table and column lineage

```python
lineage = ingestor.get_table_lineage("customers", catalog="main", schema="default")
print(lineage["upstream"])    # tables that feed into `customers`
print(lineage["downstream"])  # tables derived from `customers`
```

Use `get_table_lineage` to build `Table --DEPENDS_ON--> Table` edges in the knowledge graph directly from Unity Catalog's lineage tracking, without re-deriving lineage from query logs.

<Tip>
Pass `include_column_lineage=True` to also resolve per-column upstream/downstream references (one extra Unity Catalog request per column, so it's opt-in):

```python
lineage = ingestor.get_table_lineage(
    "customers", catalog="main", schema="default", include_column_lineage=True,
)
print(lineage["columns"]["email"])
# {"upstream": ["main.default.raw_customers.email_address"], "downstream": []}
```

</Tip>


## Export as Semantica Documents

```python
documents = ingestor.export_as_documents(
    data,
    id_field="customer_id",
    text_fields=["name", "email", "notes"],
)
print(f"Created {len(documents)} documents for processing")
```


## Batch Processing Large Tables

```python
PAGE_SIZE = 5000
for page in range(total_pages):
    data = ingestor.ingest_table(
        "large_table",
        limit=PAGE_SIZE,
        offset=page * PAGE_SIZE,
    )
    process_batch(data)
```

Or use the built-in `batch_size` parameter:

```python
data = ingestor.ingest_query(
    "SELECT * FROM main.default.large_table",
    batch_size=5000,
)
```


## Troubleshooting

```python
from semantica.ingest import DatabricksConnector

connector = DatabricksConnector(
    host="https://adb-xxx.azuredatabricks.net",
    token="dapi-xxxxxxxx",
    http_path="/sql/1.0/warehouses/xxxxxxxx",
)
if not connector.test_connection():
    print("Connection failed: check host, http_path, and credentials")
```


## See Also

- [Ingest Module](../reference/ingest) — Full DatabricksIngestor and all other ingestors.
- [Snowflake Integration](/integrations/snowflake) — Companion connector for a Snowflake + Databricks hybrid estate.
- [Pipeline](../reference/pipeline) — Use Databricks ingestion as a pipeline step.
- [Installation](../installation) — All optional dependency extras.
- [Knowledge Graph](../reference/kg) — Build a KG from ingested Databricks data.
