---
title: "Snowflake Integration"
description: "Ingest structured data from Snowflake tables and queries into Semantica's KG pipeline."
icon: "snowflake"
---

> Extract data from Snowflake into Semantica with password, key-pair, OAuth, and SSO authentication.


## Installation

```bash
# Install with Snowflake support
pip install "semantica[db-snowflake]"

# Or install the connector separately
pip install snowflake-connector-python
```


## Basic Usage

```python
from semantica.ingest import SnowflakeIngestor
import os

ingestor = SnowflakeIngestor(
    account=os.getenv("SNOWFLAKE_ACCOUNT"),
    user=os.getenv("SNOWFLAKE_USER"),
    password=os.getenv("SNOWFLAKE_PASSWORD"),
    warehouse=os.getenv("SNOWFLAKE_WAREHOUSE"),
    database=os.getenv("SNOWFLAKE_DATABASE"),
    schema=os.getenv("SNOWFLAKE_SCHEMA"),
)

data = ingestor.ingest_table("CUSTOMERS")
print(f"Retrieved {data.row_count} rows: columns: {data.columns}")
```

<Tip>
Use environment variables (or a `.env` file with `python-dotenv`) to keep credentials out of source code. `SnowflakeIngestor()` with no arguments reads from `SNOWFLAKE_*` environment variables automatically.
</Tip>


## Authentication Methods

<Tabs>
  <Tab title="Password">
    ```python
    ingestor = SnowflakeIngestor(
        account="myaccount",
        user="myuser",
        password="mypassword",
        warehouse="COMPUTE_WH",
    )
    ```
  </Tab>
  <Tab title="Key-Pair (Recommended)">
    ```python
    ingestor = SnowflakeIngestor(
        account="myaccount",
        user="myuser",
        private_key_path="/path/to/rsa_key.p8",
        warehouse="COMPUTE_WH",
    )
    ```
    Preferred for production: no password stored in config.
  </Tab>
  <Tab title="OAuth">
    ```python
    ingestor = SnowflakeIngestor(
        account="myaccount",
        user="myuser",
        authenticator="oauth",
        token="your_oauth_token",
        warehouse="COMPUTE_WH",
    )
    ```
  </Tab>
  <Tab title="SSO">
    ```python
    ingestor = SnowflakeIngestor(
        account="myaccount",
        user="myuser",
        authenticator="externalbrowser",
        warehouse="COMPUTE_WH",
    )
    ```
  </Tab>
</Tabs>


## Querying

### Ingest a table with filters

```python
data = ingestor.ingest_table(
    "CUSTOMERS",
    where="COUNTRY = 'USA' AND CREATED_DATE > '2024-01-01'",
    order_by="CREATED_DATE DESC",
    limit=10000,
)
```

### Custom SQL

```python
data = ingestor.ingest_query("""
    SELECT CUSTOMER_ID, SUM(AMOUNT) AS TOTAL_AMOUNT
    FROM SALES
    WHERE DATE >= '2024-01-01'
    GROUP BY CUSTOMER_ID
""")
```

### Schema introspection

```python
schema = ingestor.get_table_schema("CUSTOMERS")
for column in schema["columns"]:
    print(f"{column['name']}: {column['type']}")
```


## Export as Semantica Documents

```python
documents = ingestor.export_as_documents(
    data,
    id_field="CUSTOMER_ID",
    text_fields=["NAME", "EMAIL", "NOTES"],
)
print(f"Created {len(documents)} documents for processing")
```


## Batch Processing Large Tables

```python
PAGE_SIZE = 5000
for page in range(total_pages):
    data = ingestor.ingest_table(
        "LARGE_TABLE",
        limit=PAGE_SIZE,
        offset=page * PAGE_SIZE,
    )
    process_batch(data)
```

Or use the built-in `batch_size` parameter:

```python
data = ingestor.ingest_query(
    "SELECT * FROM LARGE_TABLE",
    batch_size=5000,
)
```


## Troubleshooting

```python
from semantica.ingest import SnowflakeConnector

connector = SnowflakeConnector(account="myaccount", user="myuser", password="mypassword")
if not connector.test_connection():
    print("Connection failed: check credentials and account identifier")
```


## See Also

- [Ingest Module](../reference/ingest) — Full SnowflakeIngestor and all other ingestors.
- [Pipeline](../reference/pipeline) — Use Snowflake ingestion as a pipeline step.
- [Installation](../installation) — All optional dependency extras.
- [Knowledge Graph](../reference/kg) — Build a KG from ingested Snowflake data.
