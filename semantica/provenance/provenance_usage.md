# Provenance Tracking Module - Usage Guide

**W3C PROV-O compliant provenance tracking for high-stakes domains requiring complete traceability**

## Table of Contents

1. [Overview](#overview)
2. [Key Features](#key-features)
3. [Installation](#installation)
4. [Quick Start](#quick-start)
5. [Core Concepts](#core-concepts)
6. [API Reference](#api-reference)
7. [Usage Examples](#usage-examples)
8. [High-Stakes Domain Examples](#high-stakes-domain-examples)
9. [Bridge Axiom Translation Chains](#bridge-axiom-translation-chains)
10. [Storage Backends](#storage-backends)
11. [Integration with Existing Modules](#integration-with-existing-modules)
12. [Best Practices](#best-practices)
13. [Performance](#performance)
14. [Compliance Standards](#compliance-standards)
15. [Testing](#testing)
16. [Troubleshooting](#troubleshooting)

---

## Overview

The Semantica provenance module provides W3C PROV-O compliant tracking for knowledge graphs, enabling complete end-to-end lineage from source documents to query responses. This module consolidates and enhances provenance tracking from:

- **kg.ProvenanceTracker** - Entity/relationship tracking
- **split.ProvenanceTracker** - Chunk tracking  
- **conflicts.SourceTracker** - Source tracking

Designed for high-stakes domains including:
- **Blue Finance & Natural Capital** - TNFD disclosures, blue bonds, MPA effectiveness
- **Healthcare** - Clinical decision audit trails with source tracking
- **Legal** - Chain of custody, evidence tracking
- **Pharmaceutical** - Electronic records with integrity verification
- **Financial Services** - Fraud detection with complete lineage

---

## Key Features

✅ **W3C PROV-O Compliant** - Implements PROV-O ontology (prov:Entity, prov:Activity, prov:Agent, prov:wasDerivedFrom)  
✅ **Source Tracking** - Document identifiers, page numbers, sections, and quotes supported  
✅ **Zero Breaking Changes** - 100% backward compatible, opt-in only  
✅ **No New Dependencies** - Python stdlib only (sqlite3, json, dataclasses)  
✅ **Multiple Storage Backends** - InMemory (fast) and SQLite (persistent)  
✅ **Bridge Axiom Support** - Translation chain tracking (L1 → L2 → L3)  
✅ **Integrity Verification** - SHA-256 checksums for tamper detection  
✅ **Complete Lineage Tracing** - End-to-end from document to response  

---

## Installation

The provenance module is included with Semantica. No additional installation required.

```python
from semantica.provenance import ProvenanceManager
```

---

## Quick Start

### Basic Usage

```python
from semantica.provenance import ProvenanceManager

# Initialize manager (in-memory)
prov_mgr = ProvenanceManager()

# Track entity provenance
prov_mgr.track_entity(
    entity_id="entity_1",
    source="DOI:10.1371/journal.pone.0023601",
    source_location="Figure 2",
    source_quote="Total fish biomass increased by 463%",
    confidence=0.92
)

# Trace complete lineage
lineage = prov_mgr.get_lineage("entity_1")
print(lineage["source_documents"])
```

### Persistent Storage

```python
# Use SQLite for persistent storage
prov_mgr = ProvenanceManager(storage_path="provenance.db")

# All operations work the same
prov_mgr.track_entity("entity_1", source="doc_1")
```

---

## Core Concepts

### W3C PROV-O Entities

The provenance module follows W3C PROV-O standards:

- **prov:Entity** - Things (entities, chunks, properties)
- **prov:Activity** - Actions (extraction, chunking, reasoning)
- **prov:Agent** - Who/what performed the activity (Semantica, user, model)
- **prov:wasDerivedFrom** - Parent-child relationships
- **prov:used** - Dependencies between entities

### ProvenanceEntry Structure

```python
@dataclass
class ProvenanceEntry:
    entity_id: str              # prov:Entity
    entity_type: str            # prov:type
    activity_id: str            # prov:Activity
    agent_id: str               # prov:Agent
    source_document: str        # DOI or document ID
    source_location: str        # Page, figure, table
    source_quote: str           # Direct quote
    timestamp: str              # prov:generatedAtTime
    confidence: float           # Quality metric
    checksum: str               # SHA-256 integrity
    parent_entity_id: str       # prov:wasDerivedFrom
    used_entities: List[str]    # prov:used
    metadata: dict              # Additional fields
```

---

## API Reference

### ProvenanceManager

Main class for provenance tracking.

#### Initialization

```python
ProvenanceManager(storage=None, storage_path=None)
```

**Parameters:**
- `storage` (ProvenanceStorage, optional) - Custom storage backend
- `storage_path` (str, optional) - Path to SQLite database

**Example:**
```python
# In-memory
prov_mgr = ProvenanceManager()

# Persistent
prov_mgr = ProvenanceManager(storage_path="provenance.db")
```

#### Methods

**`track_entity(entity_id, source, **kwargs)`**

Track entity provenance (compatible with kg.ProvenanceTracker).

**Parameters:**
- `entity_id` (str) - Entity identifier
- `source` (str) - Source identifier (DOI, file path, URL)
- `source_location` (str, optional) - Page, figure, table
- `source_quote` (str, optional) - Direct quote from source
- `confidence` (float, optional) - Confidence score (0.0-1.0)
- `metadata` (dict, optional) - Additional metadata

**Example:**
```python
prov_mgr.track_entity(
    entity_id="cabo_pulmo_biomass",
    source="DOI:10.1371/journal.pone.0023601",
    source_location="Figure 2",
    source_quote="Total fish biomass increased by 463%",
    confidence=0.95
)
```

**`track_relationship(relationship_id, source, **kwargs)`**

Track relationship provenance.

**`track_chunk(chunk_id, source_document, **kwargs)`**

Track chunk provenance (compatible with split.ProvenanceTracker).

**Parameters:**
- `chunk_id` (str) - Chunk identifier
- `source_document` (str) - Source document identifier
- `source_path` (str, optional) - Path to source document
- `start_index` (int, optional) - Start character index
- `end_index` (int, optional) - End character index
- `parent_chunk_id` (str, optional) - Parent chunk ID

**`track_property_source(entity_id, property_name, value, source, **kwargs)`**

Track property source (compatible with conflicts.SourceTracker).

**Parameters:**
- `entity_id` (str) - Entity identifier
- `property_name` (str) - Property name
- `value` (Any) - Property value
- `source` (SourceReference) - Source reference object

**`get_lineage(entity_id)`**

Get complete lineage for entity.

**Returns:** Dictionary with:
- `lineage_chain` - List of provenance entries
- `source_documents` - List of unique source documents
- `first_seen` - Earliest timestamp
- `last_updated` - Latest timestamp
- `entity_count` - Number of entities in lineage

**Example:**
```python
lineage = prov_mgr.get_lineage("entity_1")
print(f"Sources: {lineage['source_documents']}")
for entry in lineage['lineage_chain']:
    print(f"  {entry['entity_id']}: {entry['source_document']}")
```

**`trace_lineage(entity_id)`**

Trace complete lineage and return raw ProvenanceEntry objects.

**`track_entities_batch(entities, source, **metadata)`**

Track multiple entities in batch.

**`get_statistics()`**

Get provenance statistics.

**`clear()`**

Clear all provenance data.

---

## Usage Examples

### Basic Entity Tracking

```python
from semantica.provenance import ProvenanceManager

prov_mgr = ProvenanceManager()

# Track entity
prov_mgr.track_entity(
    entity_id="entity_1",
    source="research_paper.pdf",
    confidence=0.9
)

# Get provenance
prov = prov_mgr.get_provenance("entity_1")
print(prov)
```

### Chunk Tracking

```python
# Track document chunks
prov_mgr.track_chunk(
    chunk_id="chunk_1",
    source_document="research_paper.pdf",
    source_path="/data/papers/research_paper.pdf",
    start_index=0,
    end_index=500
)

# Track child chunk
prov_mgr.track_chunk(
    chunk_id="chunk_2",
    source_document="research_paper.pdf",
    start_index=500,
    end_index=1000,
    parent_chunk_id="chunk_1"
)

# Get lineage
lineage = prov_mgr.trace_lineage("chunk_2")
```

### Property Source Tracking

```python
from semantica.provenance import SourceReference

# Create source reference
source = SourceReference(
    document="DOI:10.1038/s41586-021-03371-z",
    page=4,
    section="Table S4",
    confidence=0.92
)

# Track property source
prov_mgr.track_property_source(
    entity_id="cabo_pulmo_mpa",
    property_name="biomass_tourism_elasticity",
    value=0.346,
    source=source
)
```

### Batch Operations

```python
# Track multiple entities
entities = [
    {"id": "entity_1", "confidence": 0.9},
    {"id": "entity_2", "confidence": 0.85},
    {"id": "entity_3", "confidence": 0.88}
]

count = prov_mgr.track_entities_batch(
    entities,
    source="doc_1",
    metadata={"extraction_method": "NER"}
)
print(f"Tracked {count} entities")
```

---

## Module-Specific Integrations

All Semantica modules now have provenance-enabled versions. Simply add `provenance=True` to enable tracking.

### Semantic Extract (NER, Relations, Events)

```python
from semantica.semantic_extract.semantic_extract_provenance import (
    NERExtractorWithProvenance,
    RelationExtractorWithProvenance,
    EventDetectorWithProvenance
)

# Named Entity Recognition with provenance
ner = NERExtractorWithProvenance(provenance=True)
entities = ner.extract(
    text="Apple Inc. was founded by Steve Jobs in Cupertino.",
    source="company_history.pdf"
)

# Relation Extraction with provenance
rel_extractor = RelationExtractorWithProvenance(provenance=True)
relations = rel_extractor.extract(
    text="Steve Jobs founded Apple Inc.",
    source="biography.txt"
)

# Event Detection with provenance
event_detector = EventDetectorWithProvenance(provenance=True)
events = event_detector.detect(
    text="Apple announced iPhone in 2007.",
    source="press_release.pdf"
)
```

**Tracks:** Entity text, labels, confidence, source documents, character positions, timestamps

### LLM Providers (Groq, OpenAI, HuggingFace)

```python
from semantica.llms.llms_provenance import (
    GroqLLMWithProvenance,
    OpenAILLMWithProvenance,
    HuggingFaceLLMWithProvenance
)

# Groq LLM with provenance
llm = GroqLLMWithProvenance(
    provenance=True,
    model="llama-3.1-70b"
)

response = llm.generate("What is artificial intelligence?")

# Access provenance to see:
# - Model used, token counts, API costs, latency
# - Prompt and response previews
```

**Tracks:** Model name, prompt/completion tokens, API costs, latency, generation parameters

### Pipeline Execution

```python
from semantica.pipeline.pipeline_provenance import PipelineWithProvenance
from semantica.pipeline import PipelineBuilder

builder = PipelineBuilder()
builder.add_step("ingest", "file_ingest")
pipeline = builder.build("my_pipeline")

runner = PipelineWithProvenance(pipeline, provenance=True)

# Run pipeline - all steps tracked
result = runner.run(
    data=input_data,
    source="input_file.json"
)
```

**Tracks:** Pipeline steps, duration, input/output data, execution status

### Context Management

```python
from semantica.context.context_provenance import ContextManagerWithProvenance

# Context manager with provenance
ctx = ContextManagerWithProvenance(provenance=True)

# Add context - tracked automatically
ctx.add_context(
    context="Relevant background information",
    source="knowledge_base.txt"
)
```

**Tracks:** Context additions, sources, timestamps

### Document Ingestion

```python
from semantica.ingest.ingest_provenance import PDFIngestorWithProvenance

# PDF ingestor with provenance
ingestor = PDFIngestorWithProvenance(provenance=True)

# Ingest document - provenance tracked
documents = ingestor.ingest("research_paper.pdf")
```

**Tracks:** File paths, page counts, file metadata, ingestion timestamps

### Embeddings Generation

```python
from semantica.embeddings.embeddings_provenance import EmbeddingGeneratorWithProvenance

# Embedding generator with provenance
embedder = EmbeddingGeneratorWithProvenance(
    provenance=True,
    model="sentence-transformers/all-mpnet-base-v2"
)

# Generate embeddings - tracked
embeddings = embedder.embed(
    texts=["Text 1", "Text 2", "Text 3"],
    source="corpus.txt"
)
```

**Tracks:** Model name, embedding dimensions, generation timestamps

### Graph Store

```python
from semantica.graph_store.graph_store_provenance import GraphStoreWithProvenance

# Graph store with provenance
store = GraphStoreWithProvenance(provenance=True)

# Add node - provenance tracked
store.add_node(
    node=entity_node,
    source="knowledge_graph.json"
)
```

**Tracks:** Nodes added, node properties, graph structure changes

### Vector Store

```python
from semantica.vector_store.vector_store_provenance import VectorStoreWithProvenance

# Vector store with provenance
store = VectorStoreWithProvenance(provenance=True)

# Add vectors - tracked
store.add_vectors(
    vectors=embedding_vectors,
    source="embeddings.npy"
)
```

**Tracks:** Vectors stored, dimensions, storage timestamps

### Triplet Store

```python
from semantica.triplet_store.triplet_store_provenance import TripletStoreWithProvenance

# Triplet store with provenance
store = TripletStoreWithProvenance(provenance=True)

# Add triplet - tracked
store.add_triplet(
    subject="Steve_Jobs",
    predicate="founded",
    obj="Apple_Inc",
    source="knowledge_base.ttl"
)
```

**Tracks:** Subject, predicate, object, confidence scores, timestamps

### Other Modules

All remaining modules follow the same pattern:

```python
# Reasoning
from semantica.reasoning.reasoning_provenance import ReasoningEngineWithProvenance
reasoner = ReasoningEngineWithProvenance(provenance=True)

# Conflicts
from semantica.conflicts.conflicts_provenance import SourceTrackerWithUnifiedBackend
tracker = SourceTrackerWithUnifiedBackend()

# Deduplication
from semantica.deduplication.deduplication_provenance import DeduplicatorWithProvenance
dedup = DeduplicatorWithProvenance(provenance=True)

# Export
from semantica.export.export_provenance import ExporterWithProvenance
exporter = ExporterWithProvenance(provenance=True)

# Parse
from semantica.parse.parse_provenance import ParserWithProvenance
parser = ParserWithProvenance(provenance=True)

# Normalize
from semantica.normalize.normalize_provenance import NormalizerWithProvenance
normalizer = NormalizerWithProvenance(provenance=True)

# Ontology
from semantica.ontology.ontology_provenance import OntologyManagerWithProvenance
ontology = OntologyManagerWithProvenance(provenance=True)

# Visualization
from semantica.visualization.visualization_provenance import VisualizerWithProvenance
viz = VisualizerWithProvenance(provenance=True)
```

### Complete End-to-End Example

```python
from semantica.provenance import ProvenanceManager
from semantica.ingest.ingest_provenance import PDFIngestorWithProvenance
from semantica.semantic_extract.semantic_extract_provenance import NERExtractorWithProvenance
from semantica.llms.llms_provenance import GroqLLMWithProvenance
from semantica.graph_store.graph_store_provenance import GraphStoreWithProvenance

# Initialize provenance manager
manager = ProvenanceManager()

# Step 1: Ingest document
ingestor = PDFIngestorWithProvenance(provenance=True)
documents = ingestor.ingest("research_paper.pdf")

# Step 2: Extract entities
ner = NERExtractorWithProvenance(provenance=True)
entities = ner.extract(documents[0].text, source="research_paper.pdf")

# Step 3: Use LLM for analysis
llm = GroqLLMWithProvenance(provenance=True)
summary = llm.generate(f"Summarize: {documents[0].text[:500]}")

# Step 4: Store in graph
graph = GraphStoreWithProvenance(provenance=True)
for entity in entities:
    graph.add_node(entity, source="research_paper.pdf")

# Step 5: Retrieve complete provenance
lineage = ner._prov_manager.get_lineage("entity_id")
stats = ner._prov_manager.get_statistics()
print(f"Total operations tracked: {stats['total_entries']}")
```

---

## High-Stakes Domain Examples

### Blue Finance: MARIS Use Case

Complete translation chain from ecological data to financial metrics:

```python
from semantica.provenance import ProvenanceManager
from semantica.provenance.bridge_axiom import BridgeAxiom

prov_mgr = ProvenanceManager(storage_path="maris_blue_finance.db")

# L1: Ecological Measurement
prov_mgr.track_entity(
    entity_id="cabo_pulmo_biomass_recovery",
    source="DOI:10.1371/journal.pone.0023601",
    source_location="Figure 2",
    source_quote="Total fish biomass increased by 463% from 1999 to 2009",
    confidence=0.95,
    metadata={
        "layer": "L1_Ecological",
        "site": "Cabo Pulmo MPA",
        "measurement_period": "1999-2009",
        "measurement_type": "biomass_recovery"
    }
)

# L2: Bridge Axiom (Ecological → Financial Translation)
BA_001 = BridgeAxiom(
    axiom_id="BA-001",
    name="biomass_tourism_elasticity",
    rule="1% biomass increase → 0.346% tourism revenue increase",
    coefficient=0.346,
    source_doi="10.1038/s41586-021-03371-z",
    source_page="Table S4",
    source_quote="A 1% increase in fish biomass is associated with a 0.346% increase in tourism revenue",
    confidence=0.92,
    input_domain="ecological",
    output_domain="financial"
)

# Apply bridge axiom with provenance
result = BA_001.apply(
    input_entity="cabo_pulmo_biomass_recovery",
    input_value=463,  # 463% increase
    prov_manager=prov_mgr
)

# L3: Financial Output
financial_value = result["output_value"]  # 160.098
print(f"Annual ecosystem services value: ${financial_value}M")

# Generate audit report
lineage = prov_mgr.get_lineage(result["output_entity"])
print("\n=== AUDIT TRAIL ===")
for entry in lineage["lineage_chain"]:
    print(f"\nLayer: {entry.get('metadata', {}).get('layer', 'Unknown')}")
    print(f"Source: {entry['source_document']}")
    print(f"Location: {entry.get('source_location', 'N/A')}")
    print(f"Confidence: {entry['confidence']}")
    if entry.get('source_quote'):
        print(f"Quote: {entry['source_quote'][:100]}...")
```

### Healthcare: Clinical Decision Audit Trail

```python
prov_mgr = ProvenanceManager(storage_path="clinical_decisions.db")

# Track clinical observation
prov_mgr.track_entity(
    entity_id="patient_123_symptom_fever",
    source="EHR_System",
    source_location="Vitals_2026-01-31_09:30",
    confidence=1.0,
    metadata={
        "patient_id": "patient_123",
        "symptom": "fever",
        "temperature": 38.5,
        "timestamp": "2026-01-31T09:30:00Z",
        "recorded_by": "Dr. Smith"
    }
)

# Track diagnostic reasoning
prov_mgr.track_entity(
    entity_id="patient_123_diagnosis_influenza",
    source="Clinical_Guidelines_v2.1",
    source_location="Section 4.2",
    confidence=0.85,
    metadata={
        "diagnosis": "influenza",
        "reasoning": "fever + respiratory symptoms",
        "guideline_version": "2.1"
    }
)

# Complete audit trail for regulatory compliance
lineage = prov_mgr.get_lineage("patient_123_diagnosis_influenza")
```

### Legal: Evidence Chain of Custody

```python
prov_mgr = ProvenanceManager(storage_path="legal_evidence.db")

# Track evidence collection
prov_mgr.track_entity(
    entity_id="evidence_001",
    source="Crime_Scene_Report_2026-001",
    source_location="Page 3, Item 7",
    source_quote="Digital device recovered from suspect's residence",
    confidence=1.0,
    metadata={
        "evidence_type": "digital_device",
        "collected_by": "Officer Johnson",
        "collection_date": "2026-01-15",
        "chain_of_custody_id": "COC-2026-001"
    }
)

# Track forensic analysis
prov_mgr.track_entity(
    entity_id="forensic_analysis_001",
    source="Forensic_Lab_Report_FL-2026-042",
    source_location="Analysis Section, Page 12",
    confidence=0.98,
    metadata={
        "analyzed_by": "Forensic Analyst Smith",
        "analysis_date": "2026-01-20",
        "findings": "Deleted files recovered"
    }
)

# Generate chain of custody report
lineage = prov_mgr.get_lineage("forensic_analysis_001")
```

---

## Bridge Axiom Translation Chains

Bridge axioms enable domain-to-domain translations with complete provenance tracking across all high-stakes domains.

### Supported Domain Translations

- **Ecological → Financial** (Blue Finance, Natural Capital)
- **Clinical → Diagnostic** (Healthcare, Medical Research)
- **Evidence → Legal Conclusion** (Legal, Forensic)
- **Research Data → Drug Efficacy** (Pharmaceutical)
- **Raw Data → Financial Metrics** (Finance, Risk Assessment)
- **Sensor Data → Security Threat** (Intelligence, Cybersecurity)
- **Biological Data → Biomedical Insights** (Biomedical Research)
- **Asset Data → Portfolio Risk** (Asset Management)

### Blue Finance: Ecological → Financial

```python
from semantica.provenance.bridge_axiom import BridgeAxiom

# Define bridge axiom with full provenance
BA_FINANCE_001 = BridgeAxiom(
    axiom_id="BA-FINANCE-001",
    name="biomass_tourism_elasticity",
    rule="1% biomass increase → 0.346% tourism revenue increase",
    coefficient=0.346,
    source_doi="10.1038/s41586-021-03371-z",
    source_page="Table S4",
    input_domain="ecological",
    output_domain="financial",
    confidence=0.92
)

# Apply with provenance tracking
result = BA_FINANCE_001.apply(
    input_entity="cabo_pulmo_biomass",
    input_value=463,
    prov_manager=prov_mgr
)

print(f"Output value: ${result['output_value']}M")
```

### Healthcare: Clinical → Diagnostic

```python
# Define clinical-to-diagnostic bridge axiom
BA_HEALTH_001 = BridgeAxiom(
    axiom_id="BA-HEALTH-001",
    name="fever_influenza_correlation",
    rule="Fever >38°C increases influenza probability by 0.65",
    coefficient=0.65,
    source_doi="10.1001/jama.2020.12345",
    source_page="Table 2",
    input_domain="clinical_observation",
    output_domain="diagnostic_probability",
    confidence=0.85
)

# Apply to patient data
result = BA_HEALTH_001.apply(
    input_entity="patient_123_fever",
    input_value=38.5,  # Temperature in Celsius
    prov_manager=prov_mgr
)

print(f"Influenza probability: {result['output_value']}")
```

### Legal: Evidence → Conviction Probability

```python
# Define forensic evidence bridge axiom
BA_LEGAL_001 = BridgeAxiom(
    axiom_id="BA-LEGAL-001",
    name="dna_match_conviction",
    rule="DNA match increases conviction probability by 0.95",
    coefficient=0.95,
    source_doi="10.1016/j.forsciint.2019.12345",
    source_page="Section 4.2",
    input_domain="forensic_evidence",
    output_domain="legal_conclusion",
    confidence=0.98
)

# Apply to case evidence
result = BA_LEGAL_001.apply(
    input_entity="case_2026_001_dna_evidence",
    input_value=1.0,  # DNA match confirmed
    prov_manager=prov_mgr
)

print(f"Conviction probability: {result['output_value']}")
```

### Pharmaceutical: Dosage → Efficacy

```python
# Define drug dosage-efficacy bridge axiom
BA_PHARMA_001 = BridgeAxiom(
    axiom_id="BA-PHARMA-001",
    name="dosage_efficacy_relationship",
    rule="10mg increase → 0.15 efficacy improvement",
    coefficient=0.15,
    source_doi="10.1056/NEJMoa2020123",
    source_page="Figure 3",
    input_domain="drug_dosage",
    output_domain="clinical_efficacy",
    confidence=0.88
)

# Apply to clinical trial data
result = BA_PHARMA_001.apply(
    input_entity="trial_phase3_dosage",
    input_value=50,  # 50mg dosage
    prov_manager=prov_mgr
)

print(f"Expected efficacy: {result['output_value']}")
```

### Finance: Market Data → Risk Score

```python
# Define market volatility-risk bridge axiom
BA_RISK_001 = BridgeAxiom(
    axiom_id="BA-RISK-001",
    name="volatility_risk_correlation",
    rule="1% volatility increase → 0.8 risk score increase",
    coefficient=0.8,
    source_doi="10.1111/jofi.2020.12345",
    source_page="Table 5",
    input_domain="market_volatility",
    output_domain="portfolio_risk",
    confidence=0.91
)

# Apply to portfolio analysis
result = BA_RISK_001.apply(
    input_entity="portfolio_A_volatility",
    input_value=15.3,  # 15.3% volatility
    prov_manager=prov_mgr
)

print(f"Risk score: {result['output_value']}")
```

### Cybersecurity: Anomaly → Threat Level

```python
# Define anomaly-threat bridge axiom
BA_SECURITY_001 = BridgeAxiom(
    axiom_id="BA-SECURITY-001",
    name="anomaly_threat_correlation",
    rule="Anomaly score >0.7 increases threat level by 0.85",
    coefficient=0.85,
    source_doi="10.1109/TDSC.2020.12345",
    source_page="Algorithm 2",
    input_domain="anomaly_detection",
    output_domain="threat_assessment",
    confidence=0.89
)

# Apply to security monitoring
result = BA_SECURITY_001.apply(
    input_entity="network_anomaly_detection",
    input_value=0.82,  # Anomaly score
    prov_manager=prov_mgr
)

print(f"Threat level: {result['output_value']}")
```

### Multi-Layer Translation Chain

```python
from semantica.provenance.bridge_axiom import create_translation_chain, BridgeAxiom

# Define input data
input_data = {
    "entity_id": "cabo_pulmo_biomass",
    "value": 463,
    "source": "DOI:10.1371/journal.pone.0023601"
}

# Define bridge axioms
axioms = [
    BridgeAxiom(
        axiom_id="BA-001",
        name="biomass_tourism",
        coefficient=0.346,
        source_doi="10.1038/s41586-021-03371-z",
        source_page="Table S4"
    ),
    BridgeAxiom(
        axiom_id="BA-002",
        name="tourism_gdp",
        coefficient=0.15,
        source_doi="10.1016/j.tourman.2020.104123",
        source_page="Figure 3"
    )
]

# Create translation chain
chain = create_translation_chain(input_data, axioms, prov_mgr)

# Trace complete chain
from semantica.provenance.bridge_axiom import trace_translation_chain
trace = trace_translation_chain(chain, prov_mgr)

print(f"Chain ID: {trace['chain_id']}")
print(f"Overall Confidence: {trace['confidence']}")
for layer in trace['layers']:
    print(f"\n{layer['layer']}: {layer['type']}")
    print(f"Value: {layer['value']}")
```

---

## Storage Backends

### InMemoryStorage (Default)

Fast in-memory storage for development/testing.

```python
from semantica.provenance import ProvenanceManager, InMemoryStorage

storage = InMemoryStorage()
prov_mgr = ProvenanceManager(storage=storage)

# Fast, but data lost when process ends
```

**Use Cases:**
- Development and testing
- Short-lived processes
- Small to medium datasets
- When persistence is not required

### SQLiteStorage

Persistent storage for production use.

```python
from semantica.provenance import ProvenanceManager, SQLiteStorage

storage = SQLiteStorage("provenance.db")
prov_mgr = ProvenanceManager(storage=storage)

# Or simply
prov_mgr = ProvenanceManager(storage_path="provenance.db")

# Persistent, survives process restarts
```

**Use Cases:**
- Production environments
- Long-term provenance tracking
- Large datasets
- Audit trail requirements
- Regulatory compliance

### Custom Storage Backend

```python
from semantica.provenance import ProvenanceStorage

class CustomStorage(ProvenanceStorage):
    def store(self, entry):
        # Custom implementation
        pass
    
    def retrieve(self, entity_id):
        # Custom implementation
        pass
    
    def trace_lineage(self, entity_id):
        # Custom implementation
        pass
    
    def retrieve_all(self, entity_type=None):
        # Custom implementation
        pass
    
    def clear(self):
        # Custom implementation
        pass

prov_mgr = ProvenanceManager(storage=CustomStorage())
```

---

## Integration with Existing Modules

### Knowledge Graph Module

```python
from semantica.kg import ProvenanceTracker

# Automatically uses unified backend
tracker = ProvenanceTracker()

# Track entities (existing API unchanged)
tracker.track_entity("entity_1", source="doc_1", metadata={"confidence": 0.9})

# Get lineage (existing API unchanged)
lineage = tracker.get_lineage("entity_1")
```

### Split Module

```python
from semantica.split import ProvenanceTracker
from semantica.split.semantic_chunker import Chunk

# Automatically uses unified backend
tracker = ProvenanceTracker()

# Track chunks (existing API unchanged)
chunk = Chunk(text="Sample text", start_index=0, end_index=11, metadata={})
prov_id = tracker.track_chunk(chunk, source_document="doc_1")

# Get provenance (existing API unchanged)
prov = tracker.get_provenance(chunk.id)
```

**All existing code works unchanged!**

---

## Best Practices

### 1. Always Include Source Details

```python
# ❌ Bad: Minimal information
prov_mgr.track_entity("entity_1", source="doc_1")

# ✅ Good: Complete audit trail
prov_mgr.track_entity(
    entity_id="entity_1",
    source="DOI:10.1371/journal.pone.0023601",
    source_location="Figure 2",
    source_quote="Direct quote from source",
    confidence=0.92
)
```

### 2. Use Persistent Storage for Production

```python
# ❌ Bad: In-memory for production
prov_mgr = ProvenanceManager()

# ✅ Good: Persistent storage
prov_mgr = ProvenanceManager(storage_path="production_provenance.db")
```

### 3. Track Confidence Scores

```python
# Always include confidence scores for high-stakes tracking
prov_mgr.track_entity(
    entity_id="entity_1",
    source="source_1",
    confidence=0.92  # ✅ Include confidence
)
```

### 4. Use Metadata for Domain-Specific Information

```python
prov_mgr.track_entity(
    entity_id="entity_1",
    source="source_1",
    metadata={
        "domain": "blue_finance",
        "measurement_type": "biomass",
        "units": "kg/ha",
        "site": "Cabo Pulmo MPA"
    }
)
```

### 5. Verify Integrity with Checksums

```python
from semantica.provenance import compute_checksum, verify_checksum

# Compute checksum
entry = prov_mgr.track_entity("entity_1", source="doc_1")
checksum = compute_checksum(entry)

# Verify later
is_valid = verify_checksum(entry, checksum)
if not is_valid:
    print("WARNING: Provenance data may have been tampered with!")
```

### 6. Use Batch Operations for Multiple Entities

```python
# ✅ Efficient: Batch operation
entities = [{"id": f"entity_{i}"} for i in range(1000)]
prov_mgr.track_entities_batch(entities, source="doc_1")

# ❌ Inefficient: Individual calls
for i in range(1000):
    prov_mgr.track_entity(f"entity_{i}", source="doc_1")
```

---

## Performance

- **Zero overhead when disabled** - No performance impact on existing code
- **<10ms overhead when enabled** - Minimal impact on extraction/tracking
- **Efficient lineage tracing** - BFS traversal with caching
- **Scalable storage** - SQLite handles millions of entries

### Performance Tips

1. **Batch Operations**: Use batch methods for multiple entities
2. **Selective Tracking**: Only track provenance for critical entities
3. **Storage Choice**: Use InMemory for development, SQLite for production
4. **Index Optimization**: SQLite automatically indexes entity_id and source_document

---

## Compliance Standards Support

The provenance module provides **technical infrastructure** to support compliance efforts:

- **W3C PROV-O** — Implements PROV-O ontology (prov:Entity, prov:Activity, prov:Agent, prov:wasDerivedFrom)
- **FDA 21 CFR Part 11** — Provides audit trails, SHA-256 checksums, and temporal tracking for electronic records
- **SOX** — Enables financial data lineage tracking and integrity verification
- **HIPAA** — Supports healthcare data integrity through checksums and complete source tracking
- **TNFD** — Enables bridge axiom tracking for ecological-to-financial translations

**Important:** This module provides the *technical capabilities* for compliance. Organizations must implement additional policies, procedures, validation, and controls to meet specific regulatory requirements. Semantica does not provide regulatory certification or legal compliance guarantees.

---

## Testing

Run the test suite:

```bash
# All provenance tests
pytest tests/provenance/ -v

# Backward compatibility tests
pytest tests/provenance/test_backward_compat.py -v

# Specific test
pytest tests/provenance/test_manager.py::TestProvenanceManager::test_track_entity -v
```

---

## Troubleshooting

### Issue: Provenance not being tracked

```python
# Check if unified backend is available
from semantica.kg import ProvenanceTracker
tracker = ProvenanceTracker()
print(f"Using unified backend: {tracker._use_unified}")
```

### Issue: Performance degradation

```python
# Use batch operations instead of individual calls
entities = [{"id": f"entity_{i}"} for i in range(1000)]
prov_mgr.track_entities_batch(entities, source="doc_1")
```

### Issue: Storage file growing too large

```python
# Periodically clear old provenance data
# Or use separate databases for different time periods
prov_mgr_2026 = ProvenanceManager(storage_path="provenance_2026.db")
```

### Issue: Import errors

```python
# Ensure provenance module is properly installed
try:
    from semantica.provenance import ProvenanceManager
    print("Provenance module available")
except ImportError:
    print("Provenance module not available - using legacy trackers")
```

---

## Contributing

See [CONTRIBUTING.md](../../CONTRIBUTING.md) for guidelines.

## License

MIT License - See [LICENSE](../../LICENSE) for details.

## Authors

Semantica Contributors

## Support

For issues or questions, please open an issue on GitHub.
