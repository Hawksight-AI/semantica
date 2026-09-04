---
title: "Salesforce Integration"
description: "Ingest CRM records from Salesforce sObjects and SOQL queries into Semantica's KG pipeline."
icon: "cloud"
---

> Extract Accounts, Contacts, Opportunities, and custom objects from Salesforce into Semantica with username/password/security-token, JWT bearer, or session-based authentication.


## Installation

```bash
# Install with Salesforce support
pip install "semantica[db-salesforce]"

# Or install the connector separately
pip install simple-salesforce>=1.12.0
```


## Basic Usage

```python
from semantica.ingest import SalesforceIngestor
import os

ingestor = SalesforceIngestor(
    username=os.getenv("SALESFORCE_USERNAME"),
    password=os.getenv("SALESFORCE_PASSWORD"),
    security_token=os.getenv("SALESFORCE_SECURITY_TOKEN"),
    domain=os.getenv("SALESFORCE_DOMAIN", "login"),   # "test" for sandbox
)

data = ingestor.ingest_sobject("Account", fields=["Id", "Name", "Industry"], limit=1000)
print(f"Retrieved {data.row_count} of {data.total_size} matching records")
print(f"Columns: {data.columns}")
```

<Tip>
Use environment variables (or a `.env` file with `python-dotenv`) to keep credentials out of source code. `SalesforceIngestor()` with no arguments reads from `SALESFORCE_*` environment variables automatically.
</Tip>


## Authentication Methods

<Tabs>
  <Tab title="Username / Password / Security Token">
    ```python
    import os
    from semantica.ingest import SalesforceIngestor

    ingestor = SalesforceIngestor(
        username=os.getenv("SALESFORCE_USERNAME"),
        password=os.getenv("SALESFORCE_PASSWORD"),
        security_token=os.getenv("SALESFORCE_SECURITY_TOKEN"),
        domain="login",   # production; use "test" for sandbox
    )
    ```
    Set the required environment variables before running:
    ```bash
    export SALESFORCE_USERNAME="your-username@example.com"
    export SALESFORCE_PASSWORD="your-password"
    export SALESFORCE_SECURITY_TOKEN="your-security-token"
    ```
    The standard server-side flow. The security token is appended to the
    password during Salesforce SOAP login. Generate or reset it under
    **Settings → My Personal Information → Reset My Security Token**.
  </Tab>
  <Tab title="JWT Bearer (Recommended for CI/CD)">
    ```python
    import os
    from semantica.ingest import SalesforceIngestor

    ingestor = SalesforceIngestor(
        username=os.getenv("SALESFORCE_USERNAME"),
        consumer_key=os.getenv("SALESFORCE_CONSUMER_KEY"),
        privatekey_file=os.getenv("SALESFORCE_PRIVATE_KEY_FILE"),
        domain="login",   # or "test" for sandbox
    )
    ```
    ```bash
    export SALESFORCE_USERNAME="your-username@example.com"
    export SALESFORCE_CONSUMER_KEY="your-connected-app-consumer-key"
    export SALESFORCE_PRIVATE_KEY_FILE="/path/to/server.key"
    ```
    The JWT bearer flow authenticates with a signed token — no password
    is transmitted. Ideal for server-to-server integrations and CI/CD
    pipelines. Requires a Salesforce connected app configured with
    **Use digital signatures** and the pre-authorised user listed under
    **Manage → Profiles / Permission Sets**.

    If you prefer to pass the key material as a string instead of a file
    path, use `SALESFORCE_PRIVATE_KEY` (the PEM contents) in place of
    `SALESFORCE_PRIVATE_KEY_FILE`.
  </Tab>
  <Tab title="Session ID + Instance URL">
    ```python
    ingestor = SalesforceIngestor(
        session_id=os.getenv("SALESFORCE_SESSION_ID"),
        instance_url=os.getenv("SALESFORCE_INSTANCE_URL"),
    )
    ```
    Use this when your environment already manages the OAuth token
    lifecycle (e.g. a connected app obtaining tokens via the web-server
    or device flow). Pass the access token as `session_id` and the full
    instance URL (e.g. `https://myorg.my.salesforce.com`) as
    `instance_url`.
  </Tab>
  <Tab title="Sandbox">
    ```python
    import os
    from semantica.ingest import SalesforceIngestor

    ingestor = SalesforceIngestor(
        username=os.getenv("SALESFORCE_USERNAME"),
        password=os.getenv("SALESFORCE_PASSWORD"),
        security_token=os.getenv("SALESFORCE_SECURITY_TOKEN"),
        domain="test",   # routes to test.salesforce.com
    )
    ```
    ```bash
    export SALESFORCE_USERNAME="your-sandbox-username@example.com.sandbox"
    export SALESFORCE_PASSWORD="your-password"
    export SALESFORCE_SECURITY_TOKEN="your-security-token"
    export SALESFORCE_DOMAIN="test"
    ```
    Replace `domain="login"` with `domain="test"` (or set
    `SALESFORCE_DOMAIN=test` in your environment) to connect to a
    developer or full sandbox.
  </Tab>
</Tabs>

### Environment variables

All constructor parameters have environment-variable fallbacks:

| Variable | Parameter | Default |
|---|---|---|
| `SALESFORCE_USERNAME` | `username` | — |
| `SALESFORCE_PASSWORD` | `password` | — |
| `SALESFORCE_SECURITY_TOKEN` | `security_token` | — |
| `SALESFORCE_DOMAIN` | `domain` | `"login"` |
| `SALESFORCE_INSTANCE_URL` | `instance_url` | — |
| `SALESFORCE_SESSION_ID` | `session_id` | — |
| `SALESFORCE_CONSUMER_KEY` | `consumer_key` | — |
| `SALESFORCE_PRIVATE_KEY_FILE` | `privatekey_file` | — |
| `SALESFORCE_PRIVATE_KEY` | `privatekey` | — |
| `SALESFORCE_API_VERSION` | `api_version` | library default (`59.0`) |


## Object Ingestion

### Ingest a standard object

```python
data = ingestor.ingest_sobject(
    "Account",
    fields=["Id", "Name", "Industry", "AnnualRevenue", "BillingCity"],
    where="Type = 'Customer' AND AnnualRevenue > 1000000",
    order_by="Name ASC",
    limit=5000,
)
print(f"Retrieved {data.row_count} of {data.total_size} matching records")
```

<Note>
`data.row_count` is the number of records in `data.data` (i.e. what was actually returned after any `limit`). `data.total_size` is Salesforce's `totalSize` — the number of records matching the query *before* the limit. Compare them to know whether you got all results.
</Note>

### Ingest a custom object

Custom objects end with `__c` in their API name:

```python
data = ingestor.ingest_sobject(
    "My_Custom_Object__c",
    fields=["Id", "Name", "Custom_Field__c"],
)
```

Relationship traversal fields (`Owner.Name`) are also supported:

```python
data = ingestor.ingest_sobject(
    "Contact",
    fields=["Id", "Name", "Email", "Account.Name", "Owner.Name"],
    limit=10000,
)
```

### Let Semantica choose the fields

When `fields` is omitted, all selectable fields are fetched via `describe()`
(one extra API call). Compound address and geolocation fields (`type=address`,
`type=location`) are automatically excluded — select their components
(`BillingStreet`, `BillingCity`, `Location__Latitude__s`, …) individually if
you need them.

```python
data = ingestor.ingest_sobject("Opportunity")
```


## Raw SOQL Ingestion

Pass any valid SOQL query verbatim — pagination is handled automatically:

```python
data = ingestor.ingest_query("""
    SELECT Id, Name, StageName, Amount, CloseDate,
           Account.Name, Owner.Name
    FROM Opportunity
    WHERE IsClosed = false
    ORDER BY CloseDate ASC
""")
print(f"Open opportunities: {data.row_count}")
```

The query is passed to the Salesforce REST API unchanged. The caller is
responsible for SOQL correctness and safety.

<Warning>
`ingest_query` does not validate or sanitise the SOQL string. Use
`ingest_sobject` (which validates sObject names, field names, and WHERE/ORDER
BY fragments) when building queries from application-controlled inputs.
</Warning>


## Document Export

Convert ingested records to the Semantica document format for use with
`GraphBuilder`:

```python
documents = ingestor.export_as_documents(
    data,
    id_field="Id",                            # default; Salesforce 18-char record Id
    text_fields=["Name", "Description"],      # omit to join all string fields
)

print(f"Created {len(documents)} documents")
# Each document:
# {
#   "id": "001xx000003GYk2AAG",
#   "text": "Acme Corp Enterprise software company",
#   "metadata": {
#     "source": "salesforce",
#     "sobject": "Account",
#     "instance_url": "https://myorg.my.salesforce.com",
#     "row_data": { ... full cleaned record ... }
#   }
# }
```

Feed the documents directly into `GraphBuilder`:

```python
from semantica.kg import GraphBuilder

builder = GraphBuilder()
kg = builder.build(documents)
```


## Object and Schema Discovery

```python
# List all accessible sObjects
sobject_names = ingestor.list_sobjects()
print(sobject_names[:10])   # ["Account", "Case", "Contact", ...]

# Inspect fields for a specific sObject
schema = ingestor.get_sobject_schema("Account")
for field in schema["fields"]:
    print(f"{field['name']}: {field['type']} (nillable={field['nillable']})")
```


## Context Manager

Prefer the context manager for long-running jobs — it opens one connection on
entry and closes it on exit, so every ingestion call inside the `with` block
reuses the same authenticated session:

```python
with SalesforceIngestor(
    username=os.getenv("SALESFORCE_USERNAME"),
    password=os.getenv("SALESFORCE_PASSWORD"),
    security_token=os.getenv("SALESFORCE_SECURITY_TOKEN"),
) as sf:
    accounts = sf.ingest_sobject("Account", limit=10000)
    contacts = sf.ingest_sobject("Contact", limit=10000)
    sobjects = sf.list_sobjects()
```


## Convenience Function

Use `ingest_salesforce()` for one-liner ingestion:

```python
from semantica.ingest import ingest_salesforce

# Fetch records
data = ingest_salesforce(
    method="sobject",
    sobject_name="Account",
    fields=["Id", "Name", "Industry"],
    limit=500,
)

# Execute raw SOQL (credentials from environment variables)
data = ingest_salesforce(
    method="query",
    soql="SELECT Id, Name FROM Contact WHERE IsActive = true",
)

# Ingest + export to documents in one step
docs = ingest_salesforce(
    method="documents",
    sobject_name="Account",
    text_fields=["Name", "Description"],
    limit=1000,
)

# List accessible sObjects
sobject_names = ingest_salesforce(method="list_sobjects")
```

Or use the unified `ingest()` dispatcher:

```python
from semantica.ingest import ingest

result = ingest(
    None,
    source_type="salesforce",
    method="sobject",
    sobject_name="Account",
    fields=["Id", "Name"],
    limit=500,
)
data = result["data"]   # SalesforceData
```


## Troubleshooting

```python
import os
from semantica.ingest import SalesforceConnector

connector = SalesforceConnector(
    username=os.getenv("SALESFORCE_USERNAME"),
    password=os.getenv("SALESFORCE_PASSWORD"),
    security_token=os.getenv("SALESFORCE_SECURITY_TOKEN"),
)
if not connector.test_connection():
    print("Connection failed: check username, password, security token, and domain")
```

Common causes of authentication failures:

- **Wrong domain**: production orgs use `domain="login"`; sandboxes use `domain="test"`.
- **Stale security token**: reset it under **Settings → Reset My Security Token**. The new token is emailed to you.
- **IP restriction**: your org's trusted IP ranges may block the originating IP. Check **Setup → Network Access**.
- **API access disabled**: ensure the connected profile has the **API Enabled** permission.


## See Also

- [Ingest Module](../reference/ingest) — Full `SalesforceIngestor` API and all other ingestors.
- [Snowflake Integration](/integrations/snowflake) — Relational warehouse connector with a similar design.
- [Databricks Integration](/integrations/databricks) — Lakehouse connector.
- [Installation](../installation) — All optional dependency extras.
- [Knowledge Graph](../reference/kg) — Build a KG from ingested Salesforce data.
