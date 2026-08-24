# Enhanced Change Management Usage Guide

This guide demonstrates how to use the Enhanced Change Management module for version control, audit trails, and compliance tracking in Semantica.

## Table of Contents

1. [Quick Start](#quick-start)
2. [Core Components](#core-components)
3. [Storage Backends](#storage-backends)
4. [Knowledge Graph Versioning](#knowledge-graph-versioning)
5. [Ontology Versioning](#ontology-versioning)
6. [Change Metadata & Audit Trails](#change-metadata--audit-trails)
7. [Data Integrity & Security](#data-integrity--security)
8. [Real-World Examples](#real-world-examples)
9. [Performance & Best Practices](#performance--best-practices)

---

## Quick Start

### Basic Knowledge Graph Versioning

```python
from semantica.change_management import TemporalVersionManager

# Initialize with in-memory storage (for development)
manager = TemporalVersionManager()

# Create a knowledge graph
healthcare_kg = {
    "entities": [
        {"id": "patient_001", "type": "Patient", "name": "John Doe", "age": 45},
        {"id": "diagnosis_001", "type": "Diagnosis", "code": "I10", "description": "Hypertension"}
    ],
    "relationships": [
        {"source": "patient_001", "target": "diagnosis_001", "type": "has_diagnosis"}
    ]
}

# Create a versioned snapshot
snapshot = manager.create_snapshot(
    healthcare_kg,
    version_label="v1.0",
    author="dr.smith@hospital.com",
    description="Initial patient record"
)

print(f"Created snapshot: {snapshot['label']}")
print(f"Checksum: {snapshot['checksum']}")
```

### Basic Ontology Versioning

```python
from semantica.change_management import OntologyVersionManager

# Initialize ontology version manager
ont_manager = OntologyVersionManager()

# Create an ontology
financial_ontology = {
    "uri": "https://bank.com/ontology",
    "version_info": {"version": "1.0", "date": "2024-01-30"},
    "structure": {
        "classes": ["Account", "Customer", "Transaction"],
        "properties": ["accountNumber", "balance", "amount"],
        "individuals": ["SavingsAccount", "CheckingAccount"],
        "axioms": ["Account belongsTo exactly 1 Customer"]
    }
}

# Create versioned snapshot
ont_snapshot = ont_manager.create_snapshot(
    financial_ontology,
    version_label="financial_v1.0",
    author="architect@bank.com",
    description="Initial financial ontology"
)
```

---

## Core Components

### 1. ChangeLogEntry

Standardized metadata structure for version changes with validation.

```python
from semantica.change_management import ChangeLogEntry

# Create a change log entry
entry = ChangeLogEntry.create_now(
    author="developer@company.com",
    description="Updated entity relationships based on new requirements",
    change_id="TICKET-123"  # Optional: link to issue tracker
)

print(f"Timestamp: {entry.timestamp}")
print(f"Author: {entry.author}")
print(f"Description: {entry.description}")
```

**Validation Features:**
- ISO 8601 timestamp format enforcement
- Email validation for authors
- Description length limits (500 characters)
- Optional change ID for linking to external systems

### 2. VersionStorage

Abstract base class for storage implementations.

```python
from semantica.change_management import VersionStorage, InMemoryVersionStorage, SQLiteVersionStorage

# In-memory storage (development/testing)
memory_storage = InMemoryVersionStorage()

# Persistent SQLite storage (production)
sqlite_storage = SQLiteVersionStorage("versions.db")

# Common operations for all storage backends
snapshot = {
    "label": "v1.0",
    "timestamp": "2024-01-30T12:00:00Z",
    "author": "user@example.com",
    "description": "Initial version",
    "data": {"entities": [], "relationships": []}
}

# Save snapshot
storage.save(snapshot)

# Retrieve snapshot
retrieved = storage.get("v1.0")

# List all versions
versions = storage.list_all()

# Check existence
exists = storage.exists("v1.0")

# Delete version
deleted = storage.delete("v1.0")
```

### 3. TemporalVersionManager

Advanced knowledge graph version management with detailed change tracking.

```python
from semantica.change_management import TemporalVersionManager

# Initialize with persistent storage
manager = TemporalVersionManager(storage_path="kg_versions.db")

# Create snapshot
snapshot = manager.create_snapshot(
    graph_data,
    version_label="v1.0",
    author="user@example.com",
    description="Initial version"
)

# List all versions
versions = manager.list_versions()

# Get specific version
version = manager.get_version("v1.0")

# Verify data integrity
is_valid = manager.verify_checksum(snapshot)

# Compare versions with detailed diff
diff = manager.compare_versions("v1.0", "v2.0")
print(f"Entities added: {diff['summary']['entities_added']}")
print(f"Entities modified: {diff['summary']['entities_modified']}")
print(f"Relationships added: {diff['summary']['relationships_added']}")
```

### 4. OntologyVersionManager

Advanced ontology version management with structural comparison.

```python
from semantica.change_management import OntologyVersionManager

# Initialize ontology manager
manager = OntologyVersionManager(storage_path="ontology_versions.db")

# Create ontology snapshot
snapshot = manager.create_snapshot(
    ontology_data,
    version_label="ont_v1.0",
    author="architect@company.com",
    description="Initial ontology design"
)

# Compare ontology versions
diff = manager.compare_versions("ont_v1.0", "ont_v2.0")
print(f"Classes added: {diff['classes_added']}")
print(f"Properties added: {diff['properties_added']}")
print(f"Axioms modified: {diff['axioms_modified']}")
```

---

## Storage Backends

### In-Memory Storage

Fast, volatile storage for development and testing.

```python
from semantica.change_management import InMemoryVersionStorage

storage = InMemoryVersionStorage()

# Advantages:
# - Lightning fast (sub-millisecond operations)
# - No file I/O overhead
# - Perfect for unit tests

# Disadvantages:
# - Data lost when process ends
# - Limited by available RAM
```

**Performance:** 0.37-16ms for save/get operations (10-1000 entities)

### SQLite Storage

Persistent, production-ready storage with ACID guarantees.

```python
from semantica.change_management import SQLiteVersionStorage

storage = SQLiteVersionStorage("production_versions.db")

# Advantages:
# - Persistent across restarts
# - ACID transaction guarantees
# - Efficient indexing and queries
# - No external database required

# Disadvantages:
# - Slightly slower than in-memory (still fast)
# - File-based storage
```

**Performance:** 7-25ms for save operations, 2-8ms for get operations (10-1000 entities)

### Custom Storage Backend

Implement your own storage backend by extending `VersionStorage`:

```python
from semantica.change_management import VersionStorage
from typing import Dict, Any, List, Optional

class RedisVersionStorage(VersionStorage):
    """Custom Redis-based storage backend."""
    
    def __init__(self, redis_url: str):
        import redis
        self.client = redis.from_url(redis_url)
    
    def save(self, snapshot: Dict[str, Any]) -> None:
        label = snapshot.get("label")
        self.client.set(f"version:{label}", json.dumps(snapshot))
    
    def get(self, label: str) -> Optional[Dict[str, Any]]:
        data = self.client.get(f"version:{label}")
        return json.loads(data) if data else None
    
    def list_all(self) -> List[Dict[str, Any]]:
        keys = self.client.keys("version:*")
        return [self.get(k.decode().split(":")[1]) for k in keys]
    
    def exists(self, label: str) -> bool:
        return self.client.exists(f"version:{label}") > 0
    
    def delete(self, label: str) -> bool:
        return self.client.delete(f"version:{label}") > 0
```

---

## Knowledge Graph Versioning

### Creating Snapshots

```python
from semantica.change_management import TemporalVersionManager

manager = TemporalVersionManager(storage_path="kg_versions.db")

# Healthcare knowledge graph
healthcare_kg = {
    "entities": [
        {
            "id": "patient_001",
            "type": "Patient",
            "name": "John Doe",
            "age": 45,
            "medical_record": "MR-2024-001"
        },
        {
            "id": "diagnosis_001",
            "type": "Diagnosis",
            "code": "I10",
            "description": "Essential (primary) hypertension"
        },
        {
            "id": "medication_001",
            "type": "Medication",
            "name": "Lisinopril",
            "dosage": "10mg",
            "frequency": "once daily"
        }
    ],
    "relationships": [
        {
            "source": "patient_001",
            "target": "diagnosis_001",
            "type": "has_diagnosis",
            "date": "2024-01-15"
        },
        {
            "source": "patient_001",
            "target": "medication_001",
            "type": "prescribed",
            "date": "2024-01-15"
        }
    ]
}

# Create initial snapshot
v1 = manager.create_snapshot(
    healthcare_kg,
    version_label="patient_001_v1.0",
    author="dr.smith@hospital.com",
    description="Initial patient record with hypertension diagnosis"
)

print(f"Snapshot created: {v1['label']}")
print(f"Entities: {len(v1['entities'])}")
print(f"Relationships: {len(v1['relationships'])}")
print(f"Checksum: {v1['checksum']}")
```

### Updating and Tracking Changes

```python
# Update the knowledge graph (medication dosage increased)
healthcare_kg["entities"][2]["dosage"] = "20mg"

# Add new lab result
healthcare_kg["entities"].append({
    "id": "lab_001",
    "type": "LabResult",
    "test": "Blood Pressure",
    "value": "140/90 mmHg",
    "date": "2024-01-20"
})

healthcare_kg["relationships"].append({
    "source": "patient_001",
    "target": "lab_001",
    "type": "has_result",
    "date": "2024-01-20"
})

# Create updated snapshot
v2 = manager.create_snapshot(
    healthcare_kg,
    version_label="patient_001_v2.0",
    author="dr.johnson@hospital.com",
    description="Increased medication dosage based on lab results"
)
```

### Comparing Versions

```python
# Get detailed comparison between versions
diff = manager.compare_versions("patient_001_v1.0", "patient_001_v2.0")

# Summary statistics
print(f"Entities added: {diff['summary']['entities_added']}")
print(f"Entities modified: {diff['summary']['entities_modified']}")
print(f"Entities removed: {diff['summary']['entities_removed']}")
print(f"Relationships added: {diff['summary']['relationships_added']}")

# Detailed entity changes
for entity_id, changes in diff['entity_changes'].items():
    print(f"\nEntity {entity_id}:")
    print(f"  Status: {changes['status']}")
    if changes['status'] == 'modified':
        print(f"  Before: {changes['before']}")
        print(f"  After: {changes['after']}")

# Detailed relationship changes
for rel_key, changes in diff['relationship_changes'].items():
    print(f"\nRelationship {rel_key}:")
    print(f"  Status: {changes['status']}")
```

### Listing and Retrieving Versions

```python
# List all versions
versions = manager.list_versions()
for v in versions:
    print(f"{v['label']}: {v['description']} by {v['author']}")

# Get specific version
version = manager.get_version("patient_001_v1.0")
print(f"Retrieved version: {version['label']}")
print(f"Entities: {len(version['entities'])}")

# Verify data integrity
is_valid = manager.verify_checksum(version)
print(f"Data integrity verified: {is_valid}")
```

---

## Ontology Versioning

### Creating Ontology Snapshots

```python
from semantica.change_management import OntologyVersionManager

manager = OntologyVersionManager(storage_path="ontology_versions.db")

# Financial domain ontology
financial_ontology = {
    "uri": "https://bank.com/ontology/financial",
    "version_info": {
        "version": "1.0",
        "date": "2024-01-30",
        "author": "Ontology Team"
    },
    "structure": {
        "classes": [
            "Account",
            "Customer",
            "Transaction",
            "Branch",
            "Employee"
        ],
        "properties": [
            "accountNumber",
            "balance",
            "transactionAmount",
            "customerName",
            "branchCode"
        ],
        "individuals": [
            "SavingsAccount",
            "CheckingAccount",
            "CreditAccount"
        ],
        "axioms": [
            "Account belongsTo exactly 1 Customer",
            "Transaction involves exactly 1 Account",
            "Customer hasAccount some Account"
        ]
    }
}

# Create initial ontology snapshot
ont_v1 = manager.create_snapshot(
    financial_ontology,
    version_label="financial_ont_v1.0",
    author="architect@bank.com",
    description="Initial financial domain ontology"
)
```

### Evolving Ontologies

```python
# Add compliance and risk management features
financial_ontology["structure"]["classes"].extend([
    "ComplianceCheck",
    "RiskProfile",
    "AuditLog"
])

financial_ontology["structure"]["properties"].extend([
    "riskScore",
    "complianceStatus",
    "auditTimestamp"
])

financial_ontology["structure"]["axioms"].extend([
    "Customer hasRiskProfile exactly 1 RiskProfile",
    "Transaction requiresCompliance some ComplianceCheck",
    "ComplianceCheck generatesAudit exactly 1 AuditLog"
])

financial_ontology["version_info"]["version"] = "2.0"

# Create updated ontology snapshot
ont_v2 = manager.create_snapshot(
    financial_ontology,
    version_label="financial_ont_v2.0",
    author="compliance@bank.com",
    description="Added compliance and risk management features"
)
```

### Comparing Ontology Versions

```python
# Get structural comparison
diff = manager.compare_versions("financial_ont_v1.0", "financial_ont_v2.0")

print("Ontology Evolution Summary:")
print(f"Classes added: {diff['classes_added']}")
print(f"Properties added: {diff['properties_added']}")
print(f"Individuals added: {diff['individuals_added']}")
print(f"Axioms added: {diff['axioms_added']}")

# Detailed changes
print("\nNew Classes:")
for cls in diff['classes_added']:
    print(f"  - {cls}")

print("\nNew Axioms:")
for axiom in diff['axioms_added']:
    print(f"  - {axiom}")
```

---

## Change Metadata & Audit Trails

### Creating Standardized Change Logs

```python
from semantica.change_management import ChangeLogEntry

# Create change log entry with current timestamp
entry = ChangeLogEntry.create_now(
    author="developer@company.com",
    description="Updated patient medication based on lab results",
    change_id="JIRA-1234"
)

# Access metadata
print(f"Change ID: {entry.change_id}")
print(f"Timestamp: {entry.timestamp}")
print(f"Author: {entry.author}")
print(f"Description: {entry.description}")

# Manual timestamp (for historical records)
historical_entry = ChangeLogEntry(
    timestamp="2024-01-15T10:30:00Z",
    author="admin@company.com",
    description="System migration completed",
    change_id="MIGRATION-2024-01"
)
```

### Building Audit Trails

```python
from semantica.change_management import TemporalVersionManager, ChangeLogEntry

manager = TemporalVersionManager(storage_path="audit_trail.db")

# Track a series of changes
changes = [
    ("v1.0", "Initial patient record", "dr.smith@hospital.com"),
    ("v1.1", "Added lab results", "lab.tech@hospital.com"),
    ("v1.2", "Updated medication dosage", "dr.johnson@hospital.com"),
    ("v2.0", "Added follow-up appointment", "nurse@hospital.com")
]

for version, description, author in changes:
    # Create change log entry
    log_entry = ChangeLogEntry.create_now(
        author=author,
        description=description,
        change_id=f"PATIENT-001-{version}"
    )
    
    # Create snapshot with metadata
    snapshot = manager.create_snapshot(
        graph_data,
        version_label=version,
        author=author,
        description=description
    )
    
    print(f"Recorded change: {version} by {author}")

# Generate audit report
versions = manager.list_versions()
print("\n=== Audit Trail Report ===")
for v in versions:
    print(f"{v['timestamp']}: {v['label']} - {v['description']} ({v['author']})")
```

---

## Data Integrity & Security

### Checksum Computation and Verification

```python
from semantica.change_management import compute_checksum, verify_checksum

# Compute checksum for data
data = {
    "entities": [...],
    "relationships": [...]
}

checksum = compute_checksum(data)
print(f"SHA-256 Checksum: {checksum}")

# Add checksum to snapshot
snapshot = data.copy()
snapshot["checksum"] = checksum

# Verify data integrity
is_valid = verify_checksum(snapshot)
print(f"Data integrity verified: {is_valid}")

# Detect tampering
snapshot["entities"][0]["name"] = "Modified"
is_valid = verify_checksum(snapshot)
print(f"Data integrity after modification: {is_valid}")  # False
```

### Automatic Integrity Verification

```python
from semantica.change_management import TemporalVersionManager

manager = TemporalVersionManager(storage_path="secure_versions.db")

# Checksums are automatically computed during snapshot creation
snapshot = manager.create_snapshot(
    graph_data,
    version_label="v1.0",
    author="user@example.com",
    description="Secure snapshot"
)

# Automatic verification
is_valid = manager.verify_checksum(snapshot)
print(f"Automatic integrity check: {is_valid}")

# Retrieve and verify from storage
retrieved = manager.get_version("v1.0")
is_valid = manager.verify_checksum(retrieved)
print(f"Retrieved data integrity: {is_valid}")
```

---

## Real-World Examples

### Example 1: Healthcare Patient Records (HIPAA Compliance)

```python
from semantica.change_management import TemporalVersionManager

# Initialize with persistent storage for compliance
manager = TemporalVersionManager(storage_path="hipaa_compliant_records.db")

# Patient knowledge graph
patient_kg = {
    "entities": [
        {
            "id": "patient_12345",
            "type": "Patient",
            "name": "Jane Smith",
            "dob": "1980-05-15",
            "mrn": "MR-2024-12345"
        },
        {
            "id": "diagnosis_hypertension",
            "type": "Diagnosis",
            "code": "I10",
            "description": "Essential hypertension",
            "date": "2024-01-15"
        }
    ],
    "relationships": [
        {
            "source": "patient_12345",
            "target": "diagnosis_hypertension",
            "type": "has_diagnosis"
        }
    ]
}

# Create HIPAA-compliant audit trail
snapshot = manager.create_snapshot(
    patient_kg,
    version_label="patient_12345_2024_01_15",
    author="dr.williams@hospital.com",
    description="Initial diagnosis - Essential hypertension"
)

# All changes are tracked with:
# - Author attribution (who made the change)
# - Timestamp (when the change was made)
# - Description (what changed and why)
# - Data integrity checksums (tamper detection)

print("HIPAA-compliant record created with full audit trail")
```

### Example 2: Financial System (SOX Compliance)

```python
from semantica.change_management import OntologyVersionManager

# Initialize for financial ontology versioning
manager = OntologyVersionManager(storage_path="sox_compliant_ontology.db")

# Financial system ontology
financial_ontology = {
    "uri": "https://company.com/ontology/financial",
    "version_info": {"version": "1.0", "date": "2024-01-30"},
    "structure": {
        "classes": ["Account", "Transaction", "AuditLog", "ComplianceRule"],
        "properties": ["amount", "timestamp", "approver", "status"],
        "axioms": [
            "Transaction requiresApproval exactly 1 Approver",
            "Transaction generatesAuditLog exactly 1 AuditLog"
        ]
    }
}

# Create SOX-compliant ontology version
snapshot = manager.create_snapshot(
    financial_ontology,
    version_label="financial_v1.0_sox",
    author="cfo@company.com",
    description="SOX-compliant financial ontology with audit requirements"
)

# Track all ontology changes for compliance audits
print("SOX-compliant ontology version created")
```

### Example 3: Pharmaceutical Research (FDA 21 CFR Part 11)

```python
from semantica.change_management import TemporalVersionManager, ChangeLogEntry

# Initialize with secure storage
manager = TemporalVersionManager(storage_path="fda_compliant_research.db")

# Clinical trial knowledge graph
clinical_trial_kg = {
    "entities": [
        {
            "id": "trial_001",
            "type": "ClinicalTrial",
            "name": "Phase III Efficacy Study",
            "drug": "Compound-X",
            "status": "active"
        },
        {
            "id": "patient_cohort_001",
            "type": "PatientCohort",
            "size": 500,
            "demographics": "Adults 18-65"
        }
    ],
    "relationships": [
        {
            "source": "trial_001",
            "target": "patient_cohort_001",
            "type": "includes_cohort"
        }
    ]
}

# Create FDA-compliant record with electronic signature
snapshot = manager.create_snapshot(
    clinical_trial_kg,
    version_label="trial_001_baseline",
    author="principal.investigator@pharma.com",
    description="Baseline clinical trial data - FDA 21 CFR Part 11 compliant"
)

# Verify data integrity (required for FDA compliance)
is_valid = manager.verify_checksum(snapshot)
print(f"FDA 21 CFR Part 11 data integrity verified: {is_valid}")

# Generate audit report
versions = manager.list_versions()
print("\n=== FDA Audit Report ===")
for v in versions:
    print(f"{v['timestamp']}: {v['label']} by {v['author']}")
    print(f"  Description: {v['description']}")
    print(f"  Checksum: {v['checksum']}")
```

---

## Performance & Best Practices

### Performance Benchmarks

Based on comprehensive testing:

| Operation | Small (100 entities) | Medium (500 entities) | Large (2000 entities) |
|-----------|---------------------|----------------------|----------------------|
| **Snapshot Creation** | 2.33ms | 10.70ms | 54.23ms |
| **Version Retrieval** | 1.88ms | 7.33ms | 26.04ms |
| **Version Comparison** | 3.46ms | 17.39ms | 32.83ms |
| **Checksum Computation** | 1.29ms | 5.48ms | 22.15ms |
| **SQLite Save** | 8.69ms | 13.37ms | 25.33ms |
| **InMemory Save** | 1.18ms | 10.60ms | 14.11ms |

**Concurrent Performance:**
- 510+ operations per second with 10 concurrent threads
- Thread-safe operations with no performance degradation

### Best Practices

#### 1. Choose the Right Storage Backend

```python
# Development/Testing: Use in-memory storage
dev_manager = TemporalVersionManager()

# Production: Use SQLite storage
prod_manager = TemporalVersionManager(storage_path="production.db")

# High-scale: Implement custom storage (Redis, PostgreSQL, etc.)
```

#### 2. Use Descriptive Version Labels

```python
# Good: Semantic versioning with context
manager.create_snapshot(data, "patient_001_v2.1_medication_update", ...)

# Bad: Generic labels
manager.create_snapshot(data, "v1", ...)
```

#### 3. Provide Detailed Descriptions

```python
# Good: Explains what changed and why
manager.create_snapshot(
    data,
    "v2.0",
    "dr.smith@hospital.com",
    "Increased Lisinopril dosage from 10mg to 20mg based on elevated BP readings (140/90)"
)

# Bad: Vague description
manager.create_snapshot(data, "v2.0", "user@example.com", "Updated")
```

#### 4. Verify Data Integrity Regularly

```python
# Verify after retrieval
version = manager.get_version("v1.0")
if not manager.verify_checksum(version):
    raise SecurityError("Data integrity compromised!")

# Periodic integrity checks
for version_info in manager.list_versions():
    version = manager.get_version(version_info['label'])
    if not manager.verify_checksum(version):
        print(f"WARNING: Integrity issue in {version_info['label']}")
```

#### 5. Link Changes to External Systems

```python
from semantica.change_management import ChangeLogEntry

# Link to issue tracking systems
entry = ChangeLogEntry.create_now(
    author="developer@company.com",
    description="Fixed entity resolution bug",
    change_id="JIRA-1234"  # Links to external ticket
)
```

#### 6. Implement Retention Policies

```python
from datetime import datetime, timedelta

def cleanup_old_versions(manager, retention_days=90):
    """Remove versions older than retention period."""
    cutoff_date = datetime.now() - timedelta(days=retention_days)
    
    for version in manager.list_versions():
        version_date = datetime.fromisoformat(version['timestamp'].replace('Z', '+00:00'))
        if version_date < cutoff_date:
            manager.storage.delete(version['label'])
            print(f"Deleted old version: {version['label']}")
```

#### 7. Batch Operations for Performance

```python
# Efficient: Batch multiple changes
changes = [...]
for change in changes:
    manager.create_snapshot(change['data'], change['label'], ...)

# Inefficient: Individual operations with delays
for change in changes:
    manager.create_snapshot(...)
    time.sleep(1)  # Unnecessary delay
```

#### 8. Use Detailed Diffs for Analysis

```python
# Get detailed comparison
diff = manager.compare_versions("v1.0", "v2.0")

# Analyze entity-level changes
for entity_id, changes in diff['entity_changes'].items():
    if changes['status'] == 'modified':
        # Implement custom business logic
        analyze_entity_changes(entity_id, changes['before'], changes['after'])

# Track relationship evolution
for rel_key, changes in diff['relationship_changes'].items():
    if changes['status'] == 'added':
        # Log new relationships
        log_new_relationship(rel_key, changes['after'])
```

---

## Migration from Legacy Systems

### From TemporalVersionManager

```python
# Old approach (still supported)
from semantica.kg.temporal_query import TemporalVersionManager

old_manager = TemporalVersionManager()
version = old_manager.create_version(graph, "v1.0")

# New approach (enhanced features)
from semantica.change_management import TemporalVersionManager

new_manager = TemporalVersionManager(storage_path="versions.db")
snapshot = new_manager.create_snapshot(
    graph,
    "v1.0",
    "user@example.com",
    "Migrated from legacy system"
)

# Both approaches work - choose based on your needs
```

### From OntologyVersion

```python
# Old approach
from semantica.ontology import VersionManager

old_manager = VersionManager(base_uri="https://example.com/ont/")
version = old_manager.create_version("1.0", ontology)

# New approach (with enhanced features)
from semantica.change_management import OntologyVersionManager

new_manager = OntologyVersionManager(storage_path="ontologies.db")
snapshot = new_manager.create_snapshot(
    ontology,
    "v1.0",
    "architect@example.com",
    "Enhanced ontology with compliance features"
)
```

---

## Troubleshooting

### Common Issues

**Issue: "Version already exists" error**
```python
# Solution: Use unique version labels or check existence first
if not manager.storage.exists("v1.0"):
    manager.create_snapshot(data, "v1.0", ...)
```

**Issue: Checksum verification fails**
```python
# Solution: Data may have been modified - investigate
version = manager.get_version("v1.0")
if not manager.verify_checksum(version):
    # Check for data corruption or tampering
    print("WARNING: Data integrity compromised!")
    # Implement recovery procedures
```

**Issue: Performance degradation with large datasets**
```python
# Solution: Use SQLite storage and implement pagination
manager = TemporalVersionManager(storage_path="large_data.db")

# For very large graphs, consider splitting into modules
```

---

## Additional Resources

- **API Reference**: See `docs/reference/change_management.md`
- **Performance Tests**: See `tests/change_management/test_performance.py`
- **Examples**: See `examples/change_management_examples.py`
- **CHANGELOG**: See `CHANGELOG.md` for version history

---

## Support

For questions or issues:
- GitHub Issues: https://github.com/semantica-agi/semantica/issues
- Documentation: https://semantica.readthedocs.io
- Community: https://discord.gg/sV34vps5hH
