---
title: "Change Management Module"
description: "Version control, SHA-256 checksums, diff analysis, rollback, and audit trails for knowledge graphs and ontologies."
icon: "clock-rotate-left"
---

**`semantica.change_management`** provides **enterprise-grade versioning and audit trails** for knowledge graphs and ontologies:

- SHA-256 checksums on every snapshot: tamper detection without external infrastructure
- Structural diff between any two versions: nodes added, removed, or modified
- Full rollback to any named snapshot
- Per-entity mutation history for audit trail queries
- Compliance frameworks supported: HIPAA, SOX, GDPR, FDA 21 CFR Part 11

<Note>
  Compliance frameworks supported out of the box: **HIPAA**, **SOX**, **GDPR**, and **FDA 21 CFR Part 11**.
</Note>


## Exported Classes

| Class | Role |
| :--- | :--- |
| `TemporalVersionManager` | Snapshot, diff, rollback, and per-node mutation history for KGs |
| `OntologyVersionManager` | Schema versioning with structural diff support |
| `InMemoryVersionStorage` | Fast in-memory storage for dev and testing: no persistence |
| `SQLiteVersionStorage` | Production storage: persists to a local SQLite file |
| `compute_checksum()` | Returns SHA-256 fingerprint of any dict (graph snapshot, ontology snapshot) |
| `verify_checksum()` | Detects tampering by recomputing and comparing the stored checksum inside a snapshot dict |

## What You Get

<CardGroup cols={2}>
  <Card title="TemporalVersionManager" icon="code-branch">
    Snapshot, diff, rollback, and per-entity audit trail for knowledge graphs.
  </Card>
  <Card title="OntologyVersionManager" icon="sitemap">
    Version control for OWL ontologies with diff and schema migration support.
  </Card>
  <Card title="VersionStorage" icon="database">
    Pluggable backends: `InMemoryVersionStorage` for tests, `SQLiteVersionStorage` for production.
  </Card>
  <Card title="Integrity Verification" icon="shield-check">
    SHA-256 checksums on every snapshot to detect any unauthorised modification.
  </Card>
  <Card title="ChangeLogEntry" icon="list-check">
    Internal metadata validated on every snapshot: ISO 8601 timestamp, email author, and description (max 500 chars).
  </Card>
  <Card title="Version History" icon="file-shield">
    Full tamper-evident version history via `list_versions()` and `diff()` for regulatory review.
  </Card>
</CardGroup>

## Typical Workflow

<Steps>
  <Step title="Initialise the version manager">
    ```python
    from semantica.change_management import TemporalVersionManager

    manager = TemporalVersionManager(storage_path="versions.db")
    ```
  </Step>
  <Step title="Snapshot before every destructive operation">
    ```python
    snapshot = manager.create_snapshot(
        graph=kg,
        version_label="v1.0",
        author="user@example.com",
        description="Before deduplication run"
    )
    print("Snapshot label:", snapshot["label"])
    print("Checksum:", snapshot["checksum"])
    ```
  </Step>
  <Step title="Make your changes">
    Run deduplication, conflict resolution, merges, or any graph modification. The version manager tracks nothing automatically: you control when snapshots are taken.
  </Step>
  <Step title="Snapshot the result">
    ```python
    snapshot_v2 = manager.create_snapshot(
        graph=kg,
        version_label="v2.0",
        author="user@example.com",
        description="After deduplication: 1 342 duplicates merged"
    )
    ```
  </Step>
  <Step title="Diff to review what changed">
    ```python
    diff = manager.diff("v1.0", "v2.0")
    summary = diff["summary"]
    print("Entities added:   ", summary["entities_added"])
    print("Entities removed: ", summary["entities_removed"])
    print("Entities modified:", summary["entities_modified"])
    ```
  </Step>
</Steps>

<Warning>
  **Snapshot before every destructive operation.** Call `manager.create_snapshot()` before running deduplication, conflict resolution, or merge operations. `restore_snapshot()` is only possible if a snapshot exists before the change.
</Warning>

## TemporalVersionManager

Version control for knowledge graphs: snapshot, diff, and rollback.

### Constructor Parameters

| Parameter | Type | Default | Description |
| :--------- | :---- | :------- | :----------- |
| `storage_path` | `str` | `None` | Path to SQLite database; uses in-memory if omitted |

### List and Retrieve

```python
# List all versions: returns List[Dict] with label, author, timestamp, checksum, entity_count
versions = manager.list_versions()
for v in versions:
    print(v["label"], "|", v["author"], "|", v["timestamp"], "|", v["checksum"][:8], "...")

# Retrieve a specific version (returns full snapshot dict)
snapshot = manager.get_version("v1.0")
```

### TemporalVersionManager Methods

| Method | Returns | Description |
| :------ | :------- | :----------- |
| `create_snapshot(graph, version_label, author, description)` | `Dict[str, Any]` | Create a version snapshot; returns the full snapshot dict including `checksum` |
| `get_version(label)` | `Optional[Dict[str, Any]]` | Retrieve a snapshot dict for a specific version label |
| `list_versions()` | `List[Dict[str, Any]]` | List all version metadata dicts |
| `diff(version_a, version_b)` | `Dict[str, Any]` | Compare two snapshots; alias for `compare_versions` |
| `compare_versions(v1, v2)` | `Dict[str, Any]` | Detailed entity/relationship diff between two snapshots |
| `restore_snapshot(graph, target_version, require_confirmation=True)` | `bool` | Restore a live graph to a previous version; raises by default unless `require_confirmation=False` |
| `get_node_history(node_id)` | `List[Dict[str, Any]]` | Return chronological mutation history for a specific node |
| `tag_version(version_label, tag_name)` | `None` | Create a named tag pointing to a version label |
| `list_tags()` | `Dict[str, str]` | Return mapping of tag name → version label |
| `prune_versions(keep_last_n)` | `Dict[str, Any]` | Delete old snapshots, keeping the most recent N |
| `verify_checksum(snapshot)` | `bool` | Verify snapshot integrity against its stored checksum |

## Diff Analysis

Compare any two snapshots to see exactly what changed: useful for code review, incident investigation, and regulatory audit:

```python
diff = manager.diff("v1.0", "v2.0")

summary = diff["summary"]
print("Entities added:      ", summary["entities_added"])
print("Entities removed:    ", summary["entities_removed"])
print("Entities modified:   ", summary["entities_modified"])
print("Relationships added: ", summary["relationships_added"])
print("Relationships removed:", summary["relationships_removed"])

# Inspect individual modified entities
for item in diff["entities_modified"]:
    print("Modified:", item["id"])
    for field, change in item["changes"].items():
        print("  %s: %s -> %s" % (field, change["from"], change["to"]))
```

<Tip>
  **Use `diff()` for code review and incident investigation.** `manager.diff("v1.0", "v2.0")` returns a plain dict with `"summary"`, `"entities_added"`, `"entities_removed"`, and `"entities_modified"`: use the `"summary"` sub-dict to get counts and `"entities_modified"` to inspect property-level changes.
</Tip>

<Accordion title="diff() return schema">

```python
# diff() / compare_versions() returns a plain dict:
{
    "version1": str,                  # first version label
    "version2": str,                  # second version label
    "summary": {
        "entities_added":          int,
        "entities_removed":        int,
        "entities_modified":       int,
        "relationships_added":     int,
        "relationships_removed":   int,
        "relationships_modified":  int,
        # also present as nodes_*/edges_* aliases
    },
    "entities_added":    List[Dict],  # full entity dicts
    "entities_removed":  List[Dict],
    "entities_modified": List[Dict],  # {id, before, after, changes}
    "relationships_added":    List[Dict],
    "relationships_removed":  List[Dict],
    "relationships_modified": List[Dict],  # {key, before, after, changes}
    # node_*/edge_* aliases point to the same lists
}
```

</Accordion>

## OntologyVersionManager

Version control for ontologies: save, diff, and track schema changes:

```python
from semantica.change_management import OntologyVersionManager

manager = OntologyVersionManager()

# Save a version
snapshot = manager.create_snapshot(
    ontology_data=ontology,
    version_label="1.2.0",
    author="ontology-team@example.com",
    description="Added FHIR alignment mappings"
)

# Diff two ontology versions: returns a plain dict
diff = manager.compare_versions("1.1.0", "1.2.0")
print("Classes added:    ", diff["classes_added"])
print("Classes removed:  ", diff["classes_removed"])
print("Properties added: ", diff["properties_added"])
```

## VersionStorage Backends

<Tabs>
  <Tab title="SQLite (production)">
    ```python
    from semantica.change_management import SQLiteVersionStorage, TemporalVersionManager

    # Pass path directly to the manager (recommended)
    manager = TemporalVersionManager(storage_path="versions.db")
    ```

    Persists all version history to disk. Survives process restarts. Recommended for any environment where you need to retain the audit trail.
  </Tab>
  <Tab title="In-Memory (tests)">
    ```python
    from semantica.change_management import InMemoryVersionStorage, TemporalVersionManager

    # Default (no storage_path) uses in-memory storage automatically
    manager = TemporalVersionManager()
    ```

    Fast and zero-setup. Data is **not persisted**: all version history is lost when the process exits. Use this for unit tests and development only.
  </Tab>
</Tabs>

<Warning>
  The default `TemporalVersionManager()` with no arguments uses in-memory storage. Always pass `storage_path="versions.db"` or an explicit `SQLiteVersionStorage` in production: otherwise your entire version history disappears on restart.
</Warning>

<Tip>
  **Use `SQLiteVersionStorage` in production.** The default in-memory storage loses all version history when the process exits. Pass `storage_path="versions.db"` to `TemporalVersionManager` or create `SQLiteVersionStorage(db_path="versions.db")` explicitly.
</Tip>

## Integrity Verification

SHA-256 checksums detect any unauthorized modification to a graph between snapshots:

```python
from semantica.change_management import compute_checksum, verify_checksum

# Compute a checksum for any dict
checksum = compute_checksum({"nodes": [], "edges": []})

# verify_checksum takes the snapshot dict directly.
# It reads the "checksum" key from the snapshot and recomputes to compare.
snapshot = manager.get_version("v1.0")
is_valid = verify_checksum(snapshot)

if not is_valid:
    raise RuntimeError("Snapshot has been tampered with")
```

<Tip>
  `verify_checksum` takes the full snapshot dict (which contains the stored `"checksum"` key). Pass the dict returned by `create_snapshot` or `get_version` directly: no separate `expected_checksum` argument is needed.
</Tip>

## ChangeLogEntry

`ChangeLogEntry` is the internal metadata object created inside `create_snapshot`. It validates the author (must be a valid email address) and description (non-empty, max 500 characters) before the snapshot is stored.

```python
from semantica.change_management.change_log import ChangeLogEntry

# Create using current timestamp
entry = ChangeLogEntry.create_now(
    author="user@example.com",     # must be a valid email
    description="Initial snapshot" # max 500 chars, non-empty
)
print(entry.timestamp)   # ISO 8601 timestamp
print(entry.author)      # "user@example.com"
print(entry.description) # "Initial snapshot"
```

<Accordion title="ChangeLogEntry schema">

```python
@dataclass
class ChangeLogEntry:
    timestamp:       str            # ISO 8601 timestamp
    author:          str            # valid email address (validated on init)
    description:     str            # change description, max 500 chars
    change_id:       Optional[str]  # optional unique identifier
    related_changes: List[str]      # optional list of related change IDs
```

</Accordion>

## Compliance and Version History

All version snapshots form a tamper-evident audit trail. Use `list_versions()` and `diff()` to reconstruct and review changes for regulatory purposes:

```python
from semantica.change_management import TemporalVersionManager

manager = TemporalVersionManager(storage_path="versions.db")

# Enumerate the full version history
for v in manager.list_versions():
    print(v["timestamp"], "|", v["author"], "|", v["label"], "|", v["description"])

# Diff any two snapshots for a change report
diff = manager.diff("v1.0", "v2.0")
s = diff["summary"]
print("Added: %d | Removed: %d | Modified: %d" % (
    s["entities_added"], s["entities_removed"], s["entities_modified"]))
```

<Tip>
  **Use `list_versions()` and `diff()` for compliance reviews.** `manager.list_versions()` returns a list of metadata dicts (with `label`, `author`, `timestamp`, `checksum`). Run `verify_checksum(snapshot)` on the dict returned by `get_version()` to confirm integrity before any export.
</Tip>

Use `verify_checksum()` before any compliance export to confirm snapshot integrity:

```python
from semantica.change_management import verify_checksum

snapshot = manager.get_version("v1.0")
is_valid = verify_checksum(snapshot)
if not is_valid:
    raise RuntimeError("Snapshot has been modified since it was recorded")
```

Per-node mutation history is available for HIPAA subject-access and SOX audit workflows:

```python
# Get full mutation history for a specific node
history = manager.get_node_history("patient_001")
for record in history:
    print(record["timestamp"], record["operation"], record["version_label"])
```

### Compliance Coverage

<AccordionGroup>
  <Accordion title="HIPAA: subject-access requests">
    Use `manager.get_node_history("patient_001")` to retrieve every recorded mutation on a patient entity. Each `MutationRecord` includes `timestamp`, `operation`, `entity_id`, `payload`, and `version_label`. The SHA-256 checksum on each snapshot proves the record has not been altered.
  </Accordion>
  <Accordion title="SOX: quarterly reviews">
    Use `manager.list_versions()` to enumerate all snapshots and `manager.diff(v1, v2)` to scope the change report to the relevant quarter. The immutable snapshot chain provides the chain of custody required by SOX Section 404.
  </Accordion>
  <Accordion title="GDPR: right to erasure verification">
    After deleting a data subject's entities, snapshot the graph and diff against the pre-deletion snapshot. `diff["entities_removed"]` provides a machine-readable record of exactly what was deleted and when, satisfying Article 17 documentation requirements.
  </Accordion>
  <Accordion title="FDA 21 CFR Part 11: electronic records">
    Every snapshot dict includes `author`, `timestamp`, and `checksum`: the three fields required for a compliant electronic record. `verify_checksum(snapshot)` provides the tamper-evidence required by 21 CFR § 11.10(e).
  </Accordion>
</AccordionGroup>

<CardGroup cols={2}>
  <Card title="Provenance" icon="link" href="provenance">
    W3C PROV-O lineage tracking.
  </Card>
  <Card title="Knowledge Graph" icon="diagram-project" href="kg">
    The graph being versioned.
  </Card>
  <Card title="Export" icon="file-export" href="export">
    Export versioned snapshots.
  </Card>
  <Card title="Conflicts" icon="triangle-exclamation" href="conflicts">
    Detect conflicts introduced between versions.
  </Card>
</CardGroup>
