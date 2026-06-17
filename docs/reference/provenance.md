---
title: "Provenance Module"
description: "W3C PROV-O lineage tracking, source attribution, tamper-evident checksums, and audit trails across all modules."
icon: "link"
---

`semantica.provenance` tracks the full lineage of every fact: from raw ingestion through extraction, chunking, and relationship building:

- W3C PROV-O compliant: suitable for HIPAA, SOX, GDPR, FDA 21 CFR Part 11 audit trails
- SHA-256 checksums for tamper detection on every stored `ProvenanceEntry`
- `SQLiteStorage` for persistence across restarts; `InMemoryStorage` for development
- `ProvenanceManager` provides `track_entity`, `track_relationship`, `track_chunk`, and `get_lineage`
- Bridges to W3C PROV-O ontology via `BridgeAxiom` for semantic web export


## Exported Classes

| Class | Role |
| :--- | :--- |
| `ProvenanceManager` | Central tracker: `track_entity`, `track_relationship`, `track_chunk`, `get_lineage`, `get_statistics` |
| `ProvenanceEntry` | Single lineage record: `{entity_id, entity_type, activity_id, source_document, confidence, checksum, ...}` |
| `SourceReference` | Rich source pointer: `{document, page, section, line, confidence, metadata}` |
| `ProvenanceStorage` | Abstract storage interface |
| `InMemoryStorage` | Default backend: fast, not persisted across restarts |
| `SQLiteStorage` | Persistent backend: persists to a local SQLite file |
| `compute_checksum` | Returns SHA-256 fingerprint of a `ProvenanceEntry` |
| `verify_checksum` | Detects tampering by comparing stored vs recomputed hash |

## Getting Started

<Tabs>
  <Tab title="In-Memory (default)">
    Zero configuration: fast, no disk writes. Use for notebooks, testing, and single-run scripts.

    ```python
    from semantica.provenance import ProvenanceManager, compute_checksum, verify_checksum

    manager = ProvenanceManager()   # InMemoryStorage by default

    entry = manager.track_entity(
        entity_id="apple_inc",
        source="annual_report_2023.pdf",
        source_location="Page 12, Section 3.1",
        source_quote="Apple Inc. was incorporated on January 3, 1977.",
        confidence=0.98,
    )

    print(entry.checksum)        # SHA-256 hex auto-computed
    print(verify_checksum(entry))  # True: tamper detection
    ```

    <Note>
      In-memory storage is lost when the process exits. Use `SQLiteStorage` for anything that needs to survive restarts.
    </Note>
  </Tab>
  <Tab title="SQLite (persistent)">
    Persists provenance to a local SQLite file. Use for production pipelines and audit trails.

    ```python
    from semantica.provenance import ProvenanceManager, SQLiteStorage

    # Option 1: explicit storage instance
    manager = ProvenanceManager(storage=SQLiteStorage("provenance.db"))

    # Option 2: shorthand: equivalent to above
    manager = ProvenanceManager(storage_path="provenance.db")

    entry = manager.track_entity(
        entity_id="apple_inc",
        source="annual_report_2023.pdf",
        source_location="Page 12, Section 3.1",
        confidence=0.98,
    )

    # Retrieve lineage after restart: entries persist in provenance.db
    lineage = manager.get_lineage("apple_inc")
    print(f"{len(lineage)} provenance entries for apple_inc")
    ```

    <Check>
      The SQLite file is created automatically on first write. No schema setup required.
    </Check>
  </Tab>
</Tabs>

## ProvenanceManager

**`ProvenanceManager`** is the central tracker for all lineage data. Every call to `track_entity`, `track_relationship`, or `track_chunk` automatically computes and stores a **SHA-256 checksum** for tamper detection.

### Constructor

```python
ProvenanceManager(
    storage=None,        # ProvenanceStorage instance; defaults to InMemoryStorage
    storage_path=None,   # str path: creates SQLiteStorage if provided
)
```

If both `storage` and `storage_path` are omitted, an `InMemoryStorage` is used.

<Warning>
  **`InMemoryStorage` does not persist across restarts.** Pass `storage_path="provenance.db"` or an explicit `SQLiteStorage` instance in any environment where the audit trail must survive process exits.
</Warning>

### Tracking Methods

```python
from semantica.provenance import ProvenanceManager, SourceReference

manager = ProvenanceManager()

# Track an entity
entry = manager.track_entity(
    entity_id="apple_inc",        # required
    source="annual_report.pdf",   # required: document ID, DOI, file path
    source_location="Page 12",    # optional kwarg
    source_quote="Incorporated on January 3, 1977.",  # optional kwarg
    confidence=0.98,              # optional kwarg, default 1.0
    entity_type="organization",   # optional kwarg, default "entity"
    metadata={"sector": "tech"},  # optional metadata dict
)

# Track a relationship
rel_entry = manager.track_relationship(
    relationship_id="jobs_founded_apple",
    source="annual_report.pdf",
    confidence=0.95,
    metadata={"type": "founded"},
)

# Track a document chunk (after splitting)
chunk_entry = manager.track_chunk(
    chunk_id="chunk_001",
    source_document="report.pdf",
    source_path="/docs/report.pdf",
    start_index=0,
    end_index=500,
    parent_chunk_id=None,
)

# Track a property with a SourceReference
source_ref = SourceReference(
    document="DOI:10.1038/s41586-021-03371-z",
    page=4,
    section="Table S4",
    confidence=0.92,
)
prop_entry = manager.track_property_source(
    entity_id="cabo_pulmo",
    property_name="biomass_increase",
    value="463%",
    source=source_ref,
)
```

### Batch Tracking

```python
entities = [
    {"id": "entity_1", "confidence": 0.9},
    {"id": "entity_2", "confidence": 0.85},
]
count = manager.track_entities_batch(entities, source="doc_1")
# Returns the number of entities successfully tracked

chunks = [
    {"id": "chunk_0", "start_index": 0, "end_index": 500},
    {"id": "chunk_1", "start_index": 500, "end_index": 1000},
]
count = manager.track_chunks_batch(chunks, source_document="doc_1")
```

### Retrieving Lineage

```python
# get_lineage returns a dict: not a ProvenanceEntry
lineage = manager.get_lineage("apple_inc")

print(lineage["entity_id"])        # "apple_inc"
print(lineage["source_documents"]) # ["annual_report.pdf"]
print(lineage["first_seen"])       # ISO timestamp string
print(lineage["last_updated"])     # ISO timestamp string
print(lineage["entity_count"])     # number of entries in chain
print(lineage["lineage_chain"])    # list of entry dicts (full history)
print(lineage["metadata"])         # merged metadata dict

# trace_lineage returns the raw ProvenanceEntry objects
entries = manager.trace_lineage("apple_inc")
for entry in entries:
    print(entry.entity_id, entry.source_document, entry.confidence)

# get_all_sources returns a list of source dicts
sources = manager.get_all_sources("apple_inc")
for s in sources:
    print(s["source"], s["location"], s["confidence"])

# get_provenance returns the most recent entry as a dict (or None)
prov = manager.get_provenance("apple_inc")
if prov:
    print(prov["source_document"])
```

<Note>
  `get_lineage()` returns an aggregated **dict**, not a `ProvenanceEntry`. Use `trace_lineage()` to get the raw `ProvenanceEntry` objects when you need field-level access such as `entry.checksum`.
</Note>

### Utility Methods

```python
# Statistics about all tracked entries
stats = manager.get_statistics()
# {"total_entries": 42, "entity_types": {"entity": 30, "chunk": 12}, "unique_sources": 5}

# Clear all provenance data; returns count of cleared entries
cleared = manager.clear()
```

### ProvenanceManager Methods Reference

| Method | Returns | Description |
| :------ | :------- | :----------- |
| `track_entity(entity_id, source, metadata, **kwargs)` | `ProvenanceEntry` | Record entity provenance; checksum set automatically |
| `track_relationship(relationship_id, source, metadata, **kwargs)` | `ProvenanceEntry` | Record relationship provenance |
| `track_chunk(chunk_id, source_document, ...)` | `ProvenanceEntry` | Record chunk provenance with char offsets |
| `track_property_source(entity_id, property_name, value, source)` | `ProvenanceEntry` | Record property-level source attribution |
| `track_entities_batch(entities, source)` | `int` | Batch-track entities; returns success count |
| `track_chunks_batch(chunks, source_document)` | `int` | Batch-track chunks; returns success count |
| `get_lineage(entity_id)` | `Dict[str, Any]` | Full lineage as aggregated dict |
| `trace_lineage(entity_id)` | `List[ProvenanceEntry]` | Full lineage as raw `ProvenanceEntry` objects |
| `get_all_sources(entity_id)` | `List[Dict]` | All source documents for an entity |
| `get_provenance(entity_id)` | `Dict \| None` | Most recent provenance entry as dict |
| `get_statistics()` | `Dict[str, Any]` | Count of entries by type and unique sources |
| `clear()` | `int` | Clear all records; returns count cleared |

## ProvenanceEntry Fields

`ProvenanceEntry` is the core dataclass. Every tracking method returns one:

```python
from semantica.provenance import ProvenanceEntry

# All fields with their types and defaults
entry = ProvenanceEntry(
    entity_id="entity_001",           # str: required
    entity_type="entity",             # str: required (entity, chunk, relationship, property)
    activity_id="ner_extraction",     # str: required
    agent_id="semantica",             # str: default "semantica"
    source_document="report.pdf",     # str: default ""
    source_location="Page 4",         # Optional[str]: default None
    source_quote="Relevant text...",  # Optional[str]: default None
    timestamp="2024-01-01T12:00:00",  # str: auto-set to utcnow()
    first_seen=None,                  # Optional[str]: ISO timestamp
    last_updated=None,                # Optional[str]: ISO timestamp
    confidence=0.9,                   # float: default 1.0
    checksum=None,                    # Optional[str]: set by compute_checksum()
    parent_entity_id=None,            # Optional[str]: prov:wasDerivedFrom
    used_entities=[],                 # List[str]: prov:used
    start_index=None,                 # Optional[int]: for chunks
    end_index=None,                   # Optional[int]: for chunks
    credibility=None,                 # Optional[float]: source credibility
    metadata={},                      # Dict[str, Any]
    version="1.0",                    # str
)

# Convert to dict
d = entry.to_dict()

# Reconstruct from dict
entry2 = ProvenanceEntry.from_dict(d)
```

## SourceReference Fields

`SourceReference` provides a citable pointer to a location within a source document:

```python
from semantica.provenance import SourceReference

ref = SourceReference(
    document="DOI:10.1038/s41586-021-03371-z",  # str: required (DOI, URL, file path)
    page=4,                                       # Optional[int]
    section="Table S4",                           # Optional[str]
    line=None,                                    # Optional[int]
    timestamp=None,                               # Optional[datetime]
    confidence=0.92,                              # float: default 1.0
    metadata={"credibility": "peer-reviewed"},    # Dict[str, Any]
)

# Use with track_property_source
manager.track_property_source(
    entity_id="cabo_pulmo",
    property_name="biomass_increase",
    value="463%",
    source=ref,
)
```

## Storage Backends

### InMemoryStorage

Fast, no persistence. Suitable for development, tests, and short-lived processes:

```python
from semantica.provenance import InMemoryStorage, ProvenanceManager

manager = ProvenanceManager(storage=InMemoryStorage())
```

### SQLiteStorage

Persists to disk. Suitable for production, audit trails, and regulatory compliance:

```python
from semantica.provenance import SQLiteStorage, ProvenanceManager

manager = ProvenanceManager(storage=SQLiteStorage("provenance.db"))

# Or use the shorthand
manager = ProvenanceManager(storage_path="provenance.db")
```

`SQLiteStorage` creates the database and indexes automatically on first use.

## Tamper-Evident Checksums

`compute_checksum` and `verify_checksum` are auto-used by `track_entity` and all other tracking methods. You can also call them directly:

```python
from semantica.provenance import compute_checksum, verify_checksum

entry = manager.trace_lineage("apple_inc")[0]

# Recompute checksum from entry fields
checksum = compute_checksum(entry)

# Verify using stored checksum (entry.checksum)
is_valid = verify_checksum(entry)

# Or verify against a separately stored expected checksum
is_valid = verify_checksum(entry, expected_checksum=checksum)

if not is_valid:
    raise RuntimeError("Provenance record has been tampered with.")
```

The checksum covers `entity_id`, `entity_type`, `activity_id`, `source_document`, `timestamp`, and `confidence`.

<Tip>
  **Run `verify_checksum(entry)` before any compliance export.** Pass the `ProvenanceEntry` object returned by `trace_lineage()` directly. If the stored checksum no longer matches, raise an error before the export proceeds.
</Tip>

## Bridge Axiom Translation Chains

`BridgeAxiom` and `TranslationChain` are available in `semantica.provenance.bridge_axiom` for tracking multi-layer domain translations with full coefficient attribution:

```python
from semantica.provenance.bridge_axiom import BridgeAxiom, create_translation_chain
from semantica.provenance import ProvenanceManager

manager = ProvenanceManager()

# Define a bridge axiom with DOI-backed coefficient
axiom = BridgeAxiom(
    axiom_id="BA-001",
    name="biomass_tourism_elasticity",
    rule="1% biomass increase -> 0.346% tourism revenue increase",
    coefficient=0.346,
    source_doi="10.1038/s41586-021-03371-z",
    source_page="Table S4",
    confidence=0.92,
    input_domain="ecological",
    output_domain="financial",
)

# Apply to a value with provenance tracking
result = axiom.apply(
    input_entity="cabo_pulmo_biomass",
    input_value=463.0,
    prov_manager=manager,
)
print(result["output_value"])  # 463.0 * 0.346 = 160.098

# Build a multi-step translation chain
input_data = {"entity_id": "cabo_pulmo", "value": 463.0, "source": "DOI:10.1371/..."}
chain = create_translation_chain(input_data, [axiom], prov_manager=manager)
print(chain.confidence)  # 0.92
```

## Integration with GraphBuilder

`GraphBuilderWithProvenance` (from `semantica.kg`) automatically records provenance for every node and edge:

```python
from semantica.kg import GraphBuilderWithProvenance
from semantica.provenance import ProvenanceManager, SQLiteStorage

prov_manager = ProvenanceManager(storage=SQLiteStorage("provenance.db"))
builder = GraphBuilderWithProvenance(provenance_manager=prov_manager)
kg = builder.build_single_source(graph_data)

# Retrieve lineage: get_lineage returns a dict
lineage = prov_manager.get_lineage("apple_inc")
print(lineage["source_documents"])  # list of source document IDs
print(lineage["first_seen"])        # ISO timestamp
```

## Integration with NERExtractor

`NERExtractor` and other extractors accept `provenance=True` to embed provenance metadata on each extracted entity. You must track the results manually using `ProvenanceManager`:

```python
from semantica.semantic_extract import NERExtractor
from semantica.provenance import ProvenanceManager

manager = ProvenanceManager()

ner = NERExtractor(method="ml", provenance=True)
entities = ner.extract("Steve Jobs founded Apple Inc.")

# Track each extracted entity manually
for entity in entities:
    manager.track_entity(
        entity_id=entity.id,
        source="source_document.txt",
        confidence=entity.confidence,
        entity_type=entity.type,
    )

# Now retrieve lineage
lineage = manager.get_lineage(entities[0].id)
print(lineage["source_documents"])
```

<Note>
  Setting `provenance=True` on `NERExtractor` embeds metadata on the extracted entity objects — it does not automatically call `ProvenanceManager.track_entity()`. You must call `track_entity()` yourself after extraction.
</Note>

## Common Workflows

<Tabs>
  <Tab title="Entity Tracking">
    ```python
    from semantica.provenance import ProvenanceManager

    manager = ProvenanceManager(storage_path="provenance.db")

    # Track an entity extracted from a document
    entry = manager.track_entity(
        entity_id="entity_001",
        source="report_2024.pdf",
        source_location="Page 5",
        source_quote="Revenue grew 12% year-over-year.",
        confidence=0.95,
    )
    # entry.checksum is set automatically

    # Retrieve full lineage
    lineage = manager.get_lineage("entity_001")
    print(lineage["source_documents"])
    ```
  </Tab>
  <Tab title="Chunk Tracking">
    ```python
    from semantica.provenance import ProvenanceManager

    manager = ProvenanceManager()

    # Track chunks produced by the split module
    manager.track_chunk(
        chunk_id="chunk_0001",
        source_document="report.pdf",
        start_index=0,
        end_index=512,
    )

    # Batch-track all chunks at once
    chunks = [
        {"id": "c0", "start_index": 0,   "end_index": 512},
        {"id": "c1", "start_index": 512, "end_index": 1024},
    ]
    count = manager.track_chunks_batch(chunks, source_document="report.pdf")
    ```
  </Tab>
  <Tab title="Integrity Check">
    ```python
    from semantica.provenance import (
        ProvenanceManager, compute_checksum, verify_checksum
    )

    manager = ProvenanceManager(storage_path="provenance.db")
    manager.track_entity("e1", source="doc.pdf", confidence=0.9)

    entries = manager.trace_lineage("e1")
    entry = entries[0]

    # Verify the stored checksum is still valid
    if not verify_checksum(entry):
        raise RuntimeError("Provenance tampered: " + entry.entity_id)
    ```
  </Tab>
</Tabs>

## Compliance Notes

Provenance tracking in Semantica produces the following audit artifacts:

| Standard | Available |
| :-------- | :--------- |
| **W3C PROV-O** | Compliant data model; `to_dict()` and `from_dict()` for serialization |
| **HIPAA** | Audit trail: entity → source document → timestamp → confidence |
| **SOX** | Tamper-evident checksums; timestamps on every entry |
| **GDPR** | Lineage graph supports data erasure impact analysis |
| **FDA 21 CFR Part 11** | Electronic record with `timestamp`, `agent_id`, `activity_id`, `checksum` |

<Note>
  `ProvenanceManager` does not include built-in Turtle or JSON-LD serialization. Use `entry.to_dict()` and `get_lineage()` to retrieve provenance data, then serialize with your preferred RDF library if W3C PROV-O RDF output is required.
</Note>

- [Change Management](change_management) — Version control and snapshot audit trails.
- [Ingest](ingest) — Provenance begins at the ingestion stage.
- [Export](export) — Include provenance metadata in RDF exports.
- [Context](context) — Decision provenance via AgentContext.
