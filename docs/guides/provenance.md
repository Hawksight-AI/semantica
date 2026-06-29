---
title: "Provenance & Audit Trails"
description: "How Semantica tracks the origin and lineage of every entity, relationship, chunk, and property with W3C PROV-O compliant records — with SHA-256 integrity checksums, SQLite persistence, and cross-module audit trails for defense, pharma, banking, and security compliance."
icon: "file-certificate"
---

## What Is Provenance?

Provenance is the systematic recording of where data came from, how it was transformed, and who was responsible for each step in its lifecycle. Unlike ordinary graph metadata that simply describes entities, provenance creates an immutable audit trail that tracks the complete history of every piece of information in your system.

**Key provenance concepts:**

**Lineage** traces the chain of custody from original source through all transformations to the current state, showing exactly how data evolved over time.

**Source attribution** records the specific document, database, API call, or human input that produced each data element, enabling precise citation and verification.

**Integrity verification** uses cryptographic checksums to detect any unauthorized changes to provenance records after they were created.

**Audit trails** provide regulatory compliance by maintaining tamper-evident logs of all data operations, transformations, and decisions.

Provenance differs from simple metadata by creating legally defensible, cryptographically verifiable records that answer critical questions: "Where did this come from?", "Who processed it?", "When did it change?", and "Has it been tampered with?"

## Why Use Provenance?

**Compliance with regulatory requirements.** Meet FDA 21 CFR Part 11, ICH E6(R2) GCP, Basel III BCBS 239, and defense intelligence sharing agreements that mandate complete data traceability and electronic record integrity.

**Source attribution and citation.** Trace every entity, relationship, and property value back to its exact source document, API response, or human input for scientific reproducibility and legal defensibility.

**Auditability and transparency.** Provide auditors, regulators, and stakeholders with complete visibility into data processing workflows, including who performed each operation and when changes occurred.

**Conflict resolution and data quality.** When multiple sources provide different values for the same property, provenance records enable evidence-based conflict resolution by comparing source credibility, recency, and confidence levels.

**Tamper detection and forensics.** Cryptographic integrity verification detects unauthorized modifications to data records, supporting incident response and forensic analysis in security-sensitive environments.

**Traceability for data lineage.** Answer complex questions about data ancestry, especially in multi-stage processing pipelines where entities undergo extraction, enrichment, fusion, and analysis transformations.

## When To Use / When Not To Use

**Use provenance tracking for:**
- Regulated environments requiring audit trails (healthcare, finance, defense, pharmaceuticals)
- Multi-source data fusion where conflicting information must be resolved with evidence
- Long-lived knowledge graphs where data quality and source credibility matter
- Production systems where data integrity and tamper detection are critical
- Complex processing pipelines where entities undergo multiple transformations
- Situations requiring legal defensibility of decisions based on extracted data

**Provenance may be unnecessary for:**
- Simple prototypes and proof-of-concept demonstrations where compliance is not required
- Ephemeral workflows that process data once and discard results immediately
- Stateless applications that don't persist data across sessions
- Internal research projects with trusted single-source data
- High-frequency, low-latency operations where provenance overhead impacts performance
- Scenarios where all data comes from a single, highly trusted source that never changes

**Consider simpler alternatives when:**
- Basic metadata (creation timestamp, source file name) provides sufficient traceability
- Data processing is transparent and reproducible through version control alone
- Regulatory compliance does not require cryptographic integrity verification

`ProvenanceManager` records a W3C PROV-O compliant entry for every entity, relationship, document chunk, and property value — with a SHA-256 checksum for tamper detection and automatic version chaining on every `track_entity()` call. Use it when you need to answer regulatory questions about where a value came from, who wrote it, and whether it has changed since first ingestion.

<Info>
The KG pipeline auto-calls `track_entity()` and `track_relationship()` on everything it extracts, so entities that enter through the standard pipeline are already tracked. Use the manual API covered here when you need custom audit integrations, cross-module lineage chains, or fine-grained property-level attribution across multiple sources.
</Info>

## Setting up the provenance store

`ProvenanceManager` supports two storage backends. In-memory storage is zero-dependency and useful for testing. SQLite storage persists across restarts, supports concurrent reads, and gives your compliance team a standard database they can query directly.

```python
from semantica.provenance import ProvenanceManager

# In-memory — session only, no persistence
prov = ProvenanceManager()

# SQLite — persists to disk, free concurrent reads
prov = ProvenanceManager(storage_path="provenance.db")

# Custom backend — pass any ProvenanceStorage implementation
from semantica.provenance.storage import SQLiteStorage
prov = ProvenanceManager(storage=SQLiteStorage("audit.db"))
```

For any regulated deployment — security operations, clinical data, financial risk — use `storage_path`. A SQLite file can be backed up, versioned, and queried with standard tools without requiring a server.

## Recording provenance when ingesting data

The moment data enters your graph is the moment provenance must be recorded. `track_entity()` captures the source document, the timestamp, the operator or pipeline that ran the extraction, a verbatim quote from the source, and a confidence score. It returns a `ProvenanceEntry` with a SHA-256 checksum computed automatically.

```python
# Ingesting CVE-2024-3400 from NVD and a commercial feed
# Both are tracked separately so the full multi-source picture is preserved.

entry_nvd = prov.track_entity(
    entity_id="cve-2024-3400",
    source="NVD_feed_2024-04-12",
    metadata={
        "cvss_score": 10.0,
        "vector": "AV:N/AC:L/PR:N/UI:N/S:C/C:H/I:H/A:H",
        "exploit_status": "unconfirmed",
    },
    confidence=0.98,
    entity_type="vulnerability",
    activity_id="nvd_feed_ingestion",
    source_location="CVE-2024-3400 JSON record",
    source_quote='{"cvssMetricV31":[{"cvssData":{"baseScore":10.0}}]}',
)

print(f"Entity tracked : {entry_nvd.entity_id}")
print(f"Source         : {entry_nvd.source_document}")
print(f"Timestamp      : {entry_nvd.timestamp}")
print(f"Checksum       : {entry_nvd.checksum}")       # SHA-256 hex digest
print(f"First seen     : {entry_nvd.first_seen}")     # set on first call only
```

```text
Entity tracked : cve-2024-3400
Source         : NVD_feed_2024-04-12
Timestamp      : 2024-04-12T14:22:07.881Z
Checksum       : 3f7a9c2d...                          # tamper-detectable
First seen     : 2024-04-12T14:22:07.881Z
```

Now track the same entity arriving from the commercial feed an hour later. Calling `track_entity()` again on the same `entity_id` automatically archives the NVD entry as a history record and creates a new current entry linked to it via `parent_entity_id`:

```python
entry_commercial = prov.track_entity(
    entity_id="cve-2024-3400",
    source="commercial_feed_2024-04-12",
    metadata={
        "cvss_score": 9.8,
        "exploit_status": "in_wild",
        "observed_exploitation": True,
    },
    confidence=0.91,
    entity_type="vulnerability",
    activity_id="commercial_feed_ingestion",
)

# The NVD entry is now archived as cve-2024-3400:v:2024-04-12T14:22:07
# The commercial entry is the new current state
# entry_commercial.parent_entity_id == "cve-2024-3400:v:2024-04-12T14:22:07"
```

This version chaining happens automatically. You do not need to manage history entries manually.

## Tracking multi-source property values

When the same property appears in multiple sources with different values — exactly the CVE score situation — use `track_property_source()` to record each attribution separately. This feeds directly into conflict detection downstream: the conflict module can compare all tracked values for a property and surface disagreements with full source metadata attached.

**SourceReference** is a structured metadata container that captures exactly where a piece of information came from within a document. It includes the document identifier, specific location (page, section, byte range), confidence level, and custom metadata fields for domain-specific attribution requirements.

```python
from semantica.provenance.schemas import SourceReference

nvd_ref = SourceReference(
    document="NVD_feed_2024-04-12",
    section="cvssMetricV31",
    confidence=0.98,
    metadata={"publisher": "NIST", "feed_type": "NVD"},
)

commercial_ref = SourceReference(
    document="commercial_feed_2024-04-12",
    section="cvss_assessment",
    confidence=0.91,
    metadata={"publisher": "ThreatFeed-Co", "observed": True},
)

# Track each source's value separately under the same entity + property key
prov.track_property_source("cve-2024-3400", "cvss_score", 10.0, nvd_ref)
prov.track_property_source("cve-2024-3400", "cvss_score", 9.8,  commercial_ref)

# Property sources are stored under "<entity_id>_<property_name>"
# Later: retrieve all sources for this property to answer "where did 9.8 come from?"
sources = prov.get_all_sources("cve-2024-3400_cvss_score")
for s in sources:
    print(f"{s['source']:<35}  confidence={s['confidence']:.2f}  loc={s['location'] or '—'}")
```

```text
NVD_feed_2024-04-12                   confidence=0.98  loc=cvssMetricV31
commercial_feed_2024-04-12            confidence=0.91  loc=cvss_assessment
```

When the regulator asks "where did the 9.8 come from?", this is the answer: `commercial_feed_2024-04-12`, section `cvss_assessment`, confidence 0.91, with full metadata showing it was a commercial publisher that reported observed exploitation.

## Tracing the lineage of a node

Once you have multiple provenance entries for an entity, you can trace its complete history to understand how it evolved over time. Six months after ingestion, run a lineage trace. `get_lineage()` returns the full version chain — every state the entity has passed through, oldest to newest — along with summary metadata:

```python
lineage = prov.get_lineage("cve-2024-3400")

print(f"Entity      : {lineage['entity_id']}")
print(f"First seen  : {lineage['first_seen']}")
print(f"Last updated: {lineage['last_updated']}")
print(f"History depth: {lineage['entity_count']} entries")
print(f"Sources seen : {lineage['source_documents']}")
print()
print("Full version chain (oldest → newest):")
for entry in lineage["lineage_chain"]:
    print(f"  [{entry['timestamp'][:19]}]  agent={entry['agent_id']}")
    print(f"    source={entry['source_document']}")
    print(f"    activity={entry['activity_id']}")
```

```text
Entity      : cve-2024-3400
First seen  : 2024-04-12T14:22:07.881Z
Last updated: 2024-10-08T09:11:44.302Z
History depth: 4 entries
Sources seen : ['NVD_feed_2024-04-12', 'commercial_feed_2024-04-12',
                'NVD_feed_2024-07-18', 'commercial_feed_2024-10-08']

Full version chain (oldest → newest):
  [2024-04-12T14:22:07]  agent=semantica
    source=NVD_feed_2024-04-12
    activity=nvd_feed_ingestion
  [2024-04-12T15:18:33]  agent=semantica
    source=commercial_feed_2024-04-12
    activity=commercial_feed_ingestion
  [2024-07-18T08:04:11]  agent=semantica
    source=NVD_feed_2024-07-18
    activity=nvd_feed_ingestion       # NVD updated their score
  [2024-10-08T09:11:44]  agent=semantica
    source=commercial_feed_2024-10-08
    activity=commercial_feed_ingestion
```

The chain answers all three of the regulator's questions. The 9.8 came from `commercial_feed_2024-04-12`. The operator was `threat_ingest_pipeline_v2`. The score has changed — NVD updated their record on July 18 — and the chain shows exactly when.

## Verifying integrity

Every `ProvenanceEntry` carries a SHA-256 checksum computed at write time. If any field is modified after the fact — by a misconfigured pipeline, a database migration, or deliberate tampering — the checksum will not match on recomputation. 

Integrity verification is critical for regulatory compliance and forensic analysis. Run integrity checks as part of any compliance audit:

```python
from semantica.provenance.integrity import compute_checksum

raw_entries = prov.trace_lineage("cve-2024-3400")

print("Integrity check:")
for e in raw_entries:
    stored   = e.checksum
    computed = compute_checksum(e)
    status   = "OK" if stored == computed else "TAMPERED"
    print(f"  [{status}] {e.entity_id[:50]}  {(stored or '')[:16]}...")
```

```text
Integrity check:
  [OK] cve-2024-3400                                 3f7a9c2d...
  [OK] cve-2024-3400:v:2024-04-12T14:22:07           a1b2c3d4...
  [OK] cve-2024-3400:v:2024-04-12T15:18:33           e5f6a7b8...
  [OK] cve-2024-3400:v:2024-07-18T08:04:11           c9d0e1f2...
```

A `TAMPERED` status means the stored hash does not match what would be computed from the current field values — evidence of post-write modification that must be investigated before the record is used for compliance purposes.

## Tracking document chunks and their children

Provenance is not just for entities. When a document is split into chunks for retrieval-augmented generation (RAG) or natural language processing workflows, each chunk needs its own provenance record linking it to the source file and byte range. 

Child chunks (from recursive splitting) link to their parent via `parent_chunk_id`, which maps to `prov:wasDerivedFrom` in the W3C PROV-O standard:

```python
# Track the parent chunk (a section of an advisory PDF)
prov.track_chunk(
    chunk_id="advisory_section_3",
    source_document="CISA_advisory_AA24-099A.pdf",
    source_path="/feeds/cisa/advisories/AA24-099A.pdf",
    start_index=4096,
    end_index=8192,
)

# Track a child chunk derived from recursive splitting
prov.track_chunk(
    chunk_id="advisory_section_3a",
    source_document="CISA_advisory_AA24-099A.pdf",
    source_path="/feeds/cisa/advisories/AA24-099A.pdf",
    start_index=4096,
    end_index=6144,
    parent_chunk_id="advisory_section_3",   # prov:wasDerivedFrom
)

# Retrieve the provenance record for a chunk
record = prov.get_provenance("advisory_section_3a")
if record:
    print(f"Source   : {record['source_document']}")
    print(f"Range    : bytes {record['start_index']}–{record['end_index']}")
    print(f"Parent   : {record['parent_entity_id']}")  # advisory_section_3
    print(f"Checksum : {record['checksum']}")
```

For GDPR right-of-erasure workflows, the byte range in each chunk's provenance record tells you exactly which part of which document to delete when a data subject makes a deletion request.

## Statistics across the provenance store

After a large ingestion run, `get_statistics()` gives a summary of everything tracked:

```python
stats = prov.get_statistics()

print(f"Total tracked    : {stats['total_entries']}")
print(f"By entity type   : {stats['entity_types']}")
print(f"Unique sources   : {stats['unique_sources']}")
```

```text
Total tracked    : 14,822
By entity type   : {'vulnerability': 3041, 'chunk': 8204, 'relationship': 2891,
                    'property': 686}
Unique sources   : 12
```

This summary is the starting point for a compliance attestation: you can state the total number of tracked records, the number of distinct data sources, and the breakdown by record type.

## Common Pitfalls

**Provenance does not guarantee truth.** Provenance records faithfully track where information came from and how it was processed, but it cannot verify that the original sources were accurate. A perfectly documented chain from a flawed or malicious source still produces unreliable data.

**Reusing generic source identifiers.** Using non-specific source IDs like "daily_feed" or "batch_001" makes it impossible to trace individual records back to their exact origins. Always include timestamps, version numbers, or unique batch identifiers in source document names.

**Bypassing provenance workflows.** Manually inserting data or using ad-hoc scripts that skip `track_entity()` calls creates gaps in the audit trail. Ensure all data entry points—automated pipelines, manual corrections, and administrative operations—record appropriate provenance.

**Ignoring lineage verification.** Provenance chains can become complex in multi-stage processing pipelines. Regularly verify that `get_lineage()` and `trace_lineage()` return complete, logical chains without missing links or circular references.

**Overusing provenance in low-value scenarios.** Recording provenance for every intermediate calculation or temporary variable creates storage overhead without compliance benefit. Focus provenance tracking on entities, relationships, and properties that have legal, regulatory, or business significance.

**Failing to validate integrity checksums.** Cryptographic integrity verification only works if you actually check it. Include regular `compute_checksum()` validation in audit workflows and incident response procedures.

**Mixing provenance granularities.** Tracking some entities at the document level and others at the sentence level creates inconsistent audit trails. Establish consistent granularity standards for each data type and processing workflow.

## Domain examples

<Tabs>

<Tab title="Defense — CTI/Threat">

A signals intelligence fusion cell tracks custody of every intelligence entity from raw collection through analytic processing to finished product. Each tier of the chain — raw collection, NER extraction, fusion, and finished intelligence — must be recorded separately with the appropriate classification handling and operator identity. The provenance chain is the chain of custody: it proves that a finished intelligence product is traceable to authorized collection and authorized analysis at every step.

Under ITAR and intelligence community sharing agreements, the provenance record must show which collection method produced the raw data, which analyst processed it, and which fusion activity combined it with other intelligence before the entity reached the finished product. `track_chunk()`, `track_entity()`, and `track_relationship()` each correspond to one tier of that chain.

```python
from semantica.provenance import ProvenanceManager
from semantica.provenance.schemas import SourceReference

prov = ProvenanceManager(storage_path="intel_provenance.db")

# Tier 1: Raw collection
prov.track_chunk(
    chunk_id="osint_collection_20260621_0442Z",
    source_document="COLLECTION_TASKING_TK-2026-0192",
    source_path="/osint/raw/20260621_0442Z.txt",
    start_index=0,
    end_index=2048,
    classification="UNCLASSIFIED//FOUO",
    collection_method="OSINT",
    collector_id="STATION_ECHO",
)

# Tier 2: Entity extracted from collection
prov.track_entity(
    entity_id="threat_actor_DELTA9",
    source="osint_collection_20260621_0442Z",
    metadata={"label": "THREAT_ACTOR", "confidence_level": "C2"},
    confidence=0.87,
    entity_type="threat_actor",
    activity_id="ner_extraction",
    source_location="paragraph_3",
)

# Tier 3: Campaign relationship from all-source fusion
prov.track_relationship(
    relationship_id="DELTA9_operates_CAMPAIGN_IRON",
    source="FUSION_REPORT_FP-2026-0447",
    metadata={"type": "operates", "confidence": 0.81},
    confidence=0.81,
    activity_id="all_source_fusion",
)

# Tier 4: Property from two independent INT sources
humint_src = SourceReference(
    document="HUMINT_REPORT_HR-2026-0821",
    confidence=0.91,
    metadata={"classification": "SECRET", "source_country": "PARTNER_5EYES"},
)
imint_src = SourceReference(
    document="IMINT_PRODUCT_IP-2026-1104",
    page=3,
    section="Ground Truth Assessment",
    confidence=0.87,
    metadata={"sensor": "OPIR", "resolution_m": 0.3},
)
prov.track_property_source("DELTA9", "location_country", "COUNTRY_X", humint_src)
prov.track_property_source("DELTA9", "location_country", "COUNTRY_X", imint_src)

# Finished product audit — full chain of custody
lineage = prov.get_lineage("threat_actor_DELTA9")
print("Chain of custody:")
for entry in lineage["lineage_chain"]:
    print(f"  [{entry['timestamp'][:19]}]  {entry['activity_id']}  agent={entry['agent_id']}")

# Corroborating INT sources for the location assessment
sources = prov.get_all_sources("DELTA9_location_country")
for s in sources:
    print(f"  INT source: {s['source']}  (conf={s['confidence']:.2f})")
```

</Tab>

<Tab title="Security — SOC/Incident">

A SOC threat intelligence platform tracks every CVE from its first NVD ingestion through enrichment runs, CVSS updates, and analyst annotations. The provenance chain answers the question that matters most during incident response: "Is this vulnerability record current, and has the CVSS score been revised since we last checked?"

The version chain created by repeated `track_entity()` calls on the same `entity_id` gives you a complete update history. If NVD revised a score from 7.5 to 9.8 following a proof-of-concept release, the chain shows the exact timestamp of that revision and which pipeline wrote the updated value.

```python
from semantica.provenance import ProvenanceManager
from semantica.provenance.schemas import SourceReference
from semantica.provenance.integrity import compute_checksum

prov = ProvenanceManager(storage_path="soc_provenance.db")

# Initial NVD ingestion
prov.track_entity(
    entity_id="cve-2023-44487",
    source="NVD_feed_2023-10-10",
    metadata={"cvss_score": 7.5, "description": "HTTP/2 Rapid Reset DDoS"},
    confidence=0.98,
    entity_type="vulnerability",
    activity_id="nvd_feed_ingestion",
)

# Six weeks later: NVD revised the score after PoC publication
prov.track_entity(
    entity_id="cve-2023-44487",
    source="NVD_feed_2023-11-22",
    metadata={"cvss_score": 7.5, "kev_added": True, "known_exploited": True},
    confidence=0.98,
    entity_type="vulnerability",
    activity_id="nvd_feed_update",
)

# Track CISA KEV addition as a separate property source
kev_ref = SourceReference(
    document="CISA_KEV_catalog_2023-11-22",
    section="Known Exploited Vulnerabilities",
    confidence=1.0,
    metadata={"publisher": "CISA", "mandatory_remediation": True},
)
prov.track_property_source("cve-2023-44487", "known_exploited", True, kev_ref)

# Incident response query: full history for this CVE
lineage = prov.get_lineage("cve-2023-44487")
print(f"CVE first seen  : {lineage['first_seen'][:10]}")
print(f"CVE last updated: {lineage['last_updated'][:10]}")
print(f"Update count    : {lineage['entity_count']} records")

# Integrity check before relying on the record for a patch decision
entries = prov.trace_lineage("cve-2023-44487")
for e in entries:
    ok = compute_checksum(e) == e.checksum
    print(f"  [{('OK' if ok else 'TAMPERED')}] {e.timestamp[:19]}  source={e.source_document}")
```

</Tab>

<Tab title="Life Science — Clinical/Pharma">

A clinical evidence graph tracks efficacy data from source publications through structured extraction to regulatory submission. The W3C PROV-O chain satisfies ICH E6(R2) GCP requirements for data traceability and 21 CFR Part 11 requirements for electronic record integrity. Every entity in the submission package must be traceable to a source document, an extraction activity, and an operator.

`track_property_source()` is particularly important here: when two independent studies report different efficacy values for the same endpoint, each must be tracked separately with full citation metadata. The resulting multi-source record is the evidence base for a meta-analysis, and the provenance entries become the supporting documentation in the regulatory dossier.

```python
from semantica.provenance import ProvenanceManager
from semantica.provenance.schemas import SourceReference
from semantica.provenance.integrity import compute_checksum

prov = ProvenanceManager(storage_path="clinical_provenance.db")

# Track the source document chunk (Phase III study report section)
prov.track_chunk(
    chunk_id="phase3_primary_endpoint_C4591001",
    source_document="STUDY_REPORT_BNT162b2_C4591001_MOD2",
    source_path="/submissions/EMA_rolling_review/mod2_clinical_overview.pdf",
    start_index=4096,
    end_index=6144,
    study_phase="Phase_III",
    ctgov="NCT04368728",
    sponsor="BioNTech_Pfizer",
)

# Track extracted efficacy entity with verbatim source quote
prov.track_entity(
    entity_id="VE_primary_BNT162b2_C4591001",
    source="phase3_primary_endpoint_C4591001",
    metadata={"value": "95.0%", "CI_95": "[90.3–97.6]", "label": "EFFICACY_MEASURE"},
    confidence=0.99,
    entity_type="clinical_endpoint",
    activity_id="structured_data_extraction",
    source_quote="Vaccine efficacy against COVID-19 was 95.0% (95% CI, 90.3–97.6)",
)

# Multi-study property tracking for meta-analysis
study1 = SourceReference(
    document="NEJM_doi_10.1056_NEJMoa2034577",
    page=9, section="Table 2",
    confidence=0.99,
    metadata={"study_id": "C4591001", "n_participants": 43448},
)
study2 = SourceReference(
    document="Lancet_doi_10.1016_S0140-6736_21_00448-7",
    page=6, section="Results",
    confidence=0.97,
    metadata={"study_id": "EXT_COHORT", "n_participants": 9119},
)
prov.track_property_source("BNT162b2", "vaccine_efficacy_symptomatic_covid19", "95.0", study1)
prov.track_property_source("BNT162b2", "vaccine_efficacy_symptomatic_covid19", "94.1", study2)

# Regulatory submission audit — evidence chain
lineage = prov.get_lineage("VE_primary_BNT162b2_C4591001")
print("Evidence chain for regulatory submission:")
for entry in lineage["lineage_chain"]:
    print(f"  {entry['timestamp'][:10]} | {entry['source_document'][:45]} | "
          f"agent={entry['agent_id']}")

# Integrity verification (21 CFR Part 11 requirement)
entries = prov.trace_lineage("VE_primary_BNT162b2_C4591001")
for e in entries:
    status = "OK" if compute_checksum(e) == e.checksum else "TAMPERED"
    print(f"  Integrity [{status}]: {e.entity_id}")

stats = prov.get_statistics()
print(f"\nTotal evidence records in dossier: {stats['total_entries']}")
```

</Tab>

<Tab title="Banking — Risk/Compliance">

A mortgage origination system records full provenance for every credit decision, satisfying SR 11-7 model risk management guidelines and EBA model documentation requirements. Every feature used in the underwriting model — credit score, DTI ratio, property valuation — must be traceable to its source data pull, the operator that ran the model, and the timestamp of the decision.

Property valuation is tracked from two sources (RICS appraisal and AVM estimate) using `track_property_source()`, giving the compliance team a complete picture of how the LTV was calculated and which valuation method the model ultimately relied on.

```python
from semantica.provenance import ProvenanceManager
from semantica.provenance.schemas import SourceReference

prov = ProvenanceManager(storage_path="credit_provenance.db")
app_id = "APP-2026-994421"

# Track the bureau data pull
prov.track_chunk(
    chunk_id=f"{app_id}_bureau_pull",
    source_document=f"EXPERIAN_CREDITEXPERT_{app_id}_2026-06-21",
    source_path=f"/bureau/experian/{app_id}/2026-06-21.json",
    start_index=0,
    end_index=4096,
    bureau="Experian",
    pull_timestamp="2026-06-21T09:14:32Z",
    consent_ref=f"CONSENT-{app_id}",
)

# Batch-track extracted credit features
features = [
    {"id": f"{app_id}_credit_score",         "confidence": 1.0, "value": 714},
    {"id": f"{app_id}_dti_ratio",             "confidence": 1.0, "value": 0.38},
    {"id": f"{app_id}_derogatory_count_7yr",  "confidence": 1.0, "value": 0},
]
prov.track_entities_batch(
    features,
    source=f"{app_id}_bureau_pull",
    entity_type="credit_feature",
    activity_id="bureau_parsing",
    agent_id="credit_data_service_v2",
)

# Track competing property valuations
rics_val = SourceReference(
    document=f"RICS_VALUATION_{app_id}_2026-06-18",
    page=3, section="Market Value Assessment",
    confidence=0.96,
    metadata={"valuer": "JLL_Residential", "method": "comparable_sales"},
)
avm_val = SourceReference(
    document=f"AVM_ESTIMATE_{app_id}_2026-06-21",
    confidence=0.84,
    metadata={"provider": "Hometrack_AVM", "model_version": "v8.3"},
)
prov.track_property_source(app_id, "property_value_GBP", "410000", rics_val)
prov.track_property_source(app_id, "property_value_GBP", "403500", avm_val)

# Track the underwriting decision itself
prov.track_entity(
    entity_id=f"DECISION_{app_id}",
    source=f"{app_id}_bureau_pull",
    metadata={"outcome": "approved_conditional_lmi", "model": "underwriting_model_v4"},
    confidence=0.89,
    entity_type="credit_decision",
    activity_id="automated_underwriting",
)

# SR 11-7 audit output
print("=== MODEL AUDIT TRAIL ===")
lineage = prov.get_lineage(f"DECISION_{app_id}")
for entry in lineage["lineage_chain"]:
    print(f"  [{entry['timestamp'][:19]}]  {entry['activity_id']}  agent={entry['agent_id']}")

print("\n=== PROPERTY VALUATION SOURCES ===")
for s in prov.get_all_sources(f"{app_id}_property_value_GBP"):
    print(f"  {s['source'][:55]}  conf={s['confidence']:.2f}")

stats = prov.get_statistics()
print(f"\nTotal audit records: {stats['total_entries']}  |  Sources: {stats['unique_sources']}")
```

</Tab>

</Tabs>

## The W3C PROV-O mapping

Every `ProvenanceEntry` maps directly to W3C PROV-O terms. If your compliance team or a regulator requires a PROV-O export, the field mapping is one-to-one:

| PROV-O Term | `ProvenanceEntry` field | What it records |
| :--- | :--- | :--- |
| `prov:Entity` | `entity_id` | The tracked object — entity, chunk, relationship, or property |
| `prov:Activity` | `activity_id` | The process that produced it — `"ner_extraction"`, `"bureau_parsing"` |
| `prov:Agent` | `agent_id` | Who ran the activity — pipeline name, analyst ID |
| `prov:wasDerivedFrom` | `parent_entity_id` | The previous version of this entity — enables version chaining |
| `prov:used` | `used_entities` | Entity IDs consumed to produce this one |
| `prov:generatedAtTime` | `timestamp` | ISO datetime, auto-set to `datetime.utcnow()` at write time |

The `checksum` field is not part of the PROV-O standard — it is Semantica's tamper-detection extension. Every entry's SHA-256 is computed from its content fields at write time and can be recomputed at any time to verify the record has not been modified.

## Related Guides

- [Semantic Extraction](semantic-extraction) — the NER and relation extraction pipeline that auto-generates provenance entries for every extracted entity
- [Conflict Resolution](conflict-resolution) — provenance property sources feed directly into conflict detection; every resolved value is traceable to its source
- [Deduplication](deduplication) — merge operations are recorded in merge history; pair with provenance for a complete lineage from source to canonical entity
- [Provenance Reference](../reference/provenance) — full storage backend API, `InMemoryStorage`, `SQLiteStorage`, and `ProvenanceEntry` schema
