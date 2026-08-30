# Regulatory Intelligence

An end-to-end Semantica pipeline that turns real U.S. federal AI-governance and cybersecurity regulations into an explainable, ontology-driven knowledge graph.

## Use case

- Federal AI-governance and cybersecurity regulations are published independently by different agencies (NIST, OMB, HHS, the Federal Reserve), with no cross-referencing between documents.
- A compliance question spanning several of them, such as "which regulations apply to an AI system in sector X," "do these two frameworks agree," or "what changed between versions," currently requires a human to read all of them and cross-reference manually.
- This notebook builds a knowledge graph that answers those questions directly, with cited evidence, computed (not narrated) conflict and diff detection, and policy-gated, auditable decisions for two sectors: healthcare and financial services.
- Scope is deliberately narrow: 9 real documents, not full corpora. See "Scope" below.

## Questions this notebook answers

- Which cybersecurity regulations apply to hospitals? Answered with hybrid GraphRAG retrieval (`AgentContext.query_with_reasoning()`).
- Which policies contradict each other? Answered with real conflict detection (`ConflictDetector`) between OMB M-24-10's binary AI risk-classification approach and NIST AI 600-1's continuous one.
- What changed between framework versions? Answered with real, document-verified temporal diffing (`TemporalVersionManager`): CSF 2.0 added the Govern function relative to CSF 1.1.
- Show every regulation related to AI transparency. Answered with a connected subgraph via SPARQL, not a flat document list.
- Can Hospital X or Bank Y deploy this AI system under current regulations? Answered with a policy-gated, precedent-aware, causally-explainable Decision Intelligence workflow.

## Pipeline

```
 Real Documents (PDF / XML)
        │
        ▼
 Ingestion            PDFParser · DoclingParser · ingest_xml
        │
        ▼
 Chunking             TextSplitter (all 9 documents)
        │
        ▼
 Extraction           NERExtractor · RelationExtractor · TripletExtractor
        │
        ▼
 Ontology Import      OntologyIngestor  ◄──── 6 real W3C/SPAR ontologies
        │                                     (ORG · PROV-O · SKOS · DCAT · OWL-Time · FRBR)
        ▼
 Curated Requirement Clauses     JSONParser
        │
        ▼
 Entity Resolution    EntityResolver · SimilarityCalculator
        │
        ▼
 Knowledge Graph      ContextGraph via GraphBuilder
        │
        ├──► Ontology Generation & Evaluation   OntologyGenerator · OntologyEvaluator
        ├──► SHACL Validation                   SHACLGenerator · pyshacl
        ├──► Deterministic Reasoning             Reasoner (forward-chaining)
        ├──► Provenance                          ProvenanceManager (PROV-O)
        └──► Persistent RDF Database             Oxigraph (on-disk) + TripletStore (Blazegraph/Jena)
        │
        ▼
 Conflict Detection · Temporal Reasoning    ConflictDetector · TemporalVersionManager
        │
        ▼
 SPARQL · JSON-LD                            Oxigraph · rdflib · RDFExporter
        │
        ▼
 GraphRAG Retrieval                          AgentContext.query_with_reasoning()
        │
        ▼
 Decision Intelligence      PolicyEngine · CausalChainAnalyzer · precedent search · audit report
        │
        ▼
 Explainable, evidence-backed answer
```

## What each layer demonstrates

- **Ingestion**: `PDFParser` (fast) and `DoclingParser` (layout-aware, used selectively) turn heterogeneous file formats into normalized text.
- **Chunking**: `TextSplitter` breaks every one of the 9 documents into bounded, citation-addressable units (840 chunks total in a real run).
- **Extraction**: `NERExtractor`, `RelationExtractor`, and `TripletExtractor` run fully automatic entity, relation, and triplet extraction across a representative sample from all 9 documents (287 entities, 392 relations, 390 triplets in a real run). The real, noisy output is the rationale for why this pipeline also relies on curated data for dense legal text.
- **Ontology**: `OntologyIngestor` reuses 6 real external ontologies rather than inventing new ones. `OntologyGenerator` and `OntologyEvaluator` generate and score a working ontology from the graph itself.
- **Validation**: `SHACLGenerator` and `pyshacl` validate instance data against structural constraints.
- **Reasoning**: `Reasoner` performs deterministic, rule-based forward-chaining inference, distinct from the LLM-based reasoning used later in GraphRAG. For example, it infers that a Regulation applies to a sector because one of its clauses does, without that being asserted directly.
- **Provenance**: `ProvenanceManager` emits real W3C PROV-O lineage for every fact.
- **Storage**: an Oxigraph store gives genuine on-disk RDF persistence with zero extra infrastructure, verified in a real run by closing and reopening the store from disk. `TripletStore` is Semantica's own interface to a dedicated production graph-database server (Blazegraph, Jena, RDF4J, AnzoGraph). Semantica's built-in SKOS vocabulary *management*, `OntologyEngine.list_vocabularies()`, `.list_concepts()`, and `.search_concepts()` (the same operations behind `semantica ontology skos search` on the CLI), is backed by that same server.
- **Cross-document reasoning**: `ConflictDetector` and `TemporalVersionManager` find real disagreements and diffs between frameworks.
- **Retrieval**: `AgentContext.query_with_reasoning()` implements GraphRAG, retrieval that expands across graph edges rather than text similarity alone.
- **Decision Intelligence**: `PolicyEngine`, `CausalChainAnalyzer`, precedent search, and a decision audit report treat AI-assisted decisions as first-class, queryable, explainable graph objects.

## What's real, what's schema

- **9 real documents** (`data/`): official NIST, GovInfo/Federal Register, eCFR, whitehouse.gov, and federalreserve.gov publications. See `data/README.md` for exact source URLs and retrieval dates.
- **6 real vendored ontologies** (`ontology/external/`): W3C Organization Ontology, PROV-O, SKOS, DCAT, OWL-Time, and FRBR Core (SPAR edition), fetched byte-for-byte from their official namespaces and repositories. See `ontology/README.md`.
- **Two small hand-authored schema files** (`ontology/regulatory_extension.ttl`, `ontology/skos/regulatory_taxonomy.ttl`): not data. Every term in them was verified to appear in the real source documents before being written.
- **`data/requirement_clauses.json`**: 20 citation-traceable requirement clauses, hand-curated from the real ingested text and loaded through `JSONParser` rather than an inline Python literal. The notebook's Step 3 demonstrates, with real output, why fully-automatic extraction isn't trusted for this instead.

Nothing in this use case is fabricated or LLM-generated data.

## Folder structure

```
regulatory_intelligence/
├── README.md                       (this file)
├── data/
│   ├── download_data.py             fetches the 9 real documents
│   ├── requirement_clauses.json     20 real, citation-traceable requirement clauses
│   ├── raw/                         the fetched documents, plus source_manifest.json
│   └── README.md
├── ontology/
│   ├── download_ontologies.py       fetches the 6 real external ontologies
│   ├── external/                    the vendored real ontology files
│   ├── regulatory_extension.ttl
│   ├── skos/regulatory_taxonomy.ttl
│   └── README.md
└── notebook/
    └── regulatory_intelligence.ipynb
```

## How to run

```bash
pip install semantica[shacl] pdfplumber rdflib requests pyoxigraph jupyter

# Optional: higher-fidelity, layout-aware PDF parsing for one document in Step 1.
# Adds torch and an ML layout model; the first run downloads model weights.
pip install semantica[parse-docling]

cd data && python download_data.py && cd ..
cd ontology && python download_ontologies.py && cd ..

jupyter notebook notebook/regulatory_intelligence.ipynb
```

Or execute headlessly:

```bash
jupyter nbconvert --to notebook --execute notebook/regulatory_intelligence.ipynb
```

Step 13 persists the graph's triples to a real, on-disk Oxigraph database, then closes and reopens it to prove the data survived. That part needs no setup at all. The same step also attempts a live connection to a Blazegraph/Jena/RDF4J/AnzoGraph server through Semantica's `TripletStore`; without one running it fails fast with a clear message. To see that path succeed instead:

```bash
docker run -p 9999:9999 lyrasis/blazegraph
```

An LLM API key (for example `GROQ_API_KEY`) is optional. `AgentContext.retrieve()` always returns cited evidence regardless of whether an LLM provider is configured, so the GraphRAG step degrades gracefully to evidence-only retrieval without one.

## Runtime

This notebook covers substantially more ground than a minimal "first knowledge graph" tutorial: ingestion (including optional ML-based parsing), chunking every document, automatic extraction across the corpus, ontology import, generation, and evaluation, entity resolution, graph construction, SHACL validation, deterministic reasoning, provenance, a persistent RDF database, conflict detection, temporal diffing, SPARQL, JSON-LD, GraphRAG, and a five-agent Decision Intelligence workflow. It runs longer than a strict 30-minute cap as a result. The dataset stays small (9 documents, roughly 50 graph nodes) even though the pipeline covers a lot of ground. Without the optional Docling step it runs noticeably faster.

## Scope

Included:
- 9 real documents across AI governance (NIST AI RMF/600-1, EO 14110, OMB M-24-10) and cybersecurity (NIST CSF 1.1/2.0, HIPAA Security Rule, NIST SP 800-66) regulation, spanning healthcare and financial-services sector applications.
- 6 real vendored ontologies (ORG, PROV-O, SKOS, DCAT, OWL-Time, FRBR) plus one small hand-authored extension.
- The full pipeline described above, end to end.

Excluded, deliberately, to stay laptop-runnable:
- Full US Code / CFR ingestion (only the relevant HIPAA subpart is used).
- The full NIST SP 800 series (only SP 800-66 is used).
- Sectors beyond healthcare and financial services.
- Docling parsing for all 9 documents. It costs about 30 seconds per 10 pages on CPU, so it's used for one document to keep total runtime reasonable; the tradeoff itself is part of the lesson.
- A dedicated Blazegraph/Jena/RDF4J/AnzoGraph server. Oxigraph gives real on-disk persistence without one; the server-backed `TripletStore` path is demonstrated as a genuine connection attempt only.

## Notes on real-world library behavior

This notebook reports what the underlying tools actually do, including rough edges in the installed library version, rather than working around them quietly:

- **Extraction** (Step 3): pattern-based NER, relation, and triplet extraction over dense regulatory prose is genuinely noisy. Institution names get mislabeled and most sentences match no relation pattern. The real output is shown as the rationale for using curated data for the rest of the pipeline.
- **Entity resolution** (Step 7): `EntityResolver.resolve_entities()`'s batch merge doesn't actually merge these near-duplicate agency names in the installed version. Shown alongside the real pairwise `SimilarityCalculator` scores (0.54 to 0.80) that should drive it.
- **Ontology validation** (Step 9): the `OntologyValidator` embedded automatically in `OntologyGenerator`'s output is a placeholder in the installed version (`valid`, `consistent`, and `satisfiable` are effectively always `True`). Real structural evaluation comes from `OntologyEvaluator`, called explicitly.
- **Precedent search** (Step 19): `AgentContext.find_precedents_advanced()`'s vector-store path has an internal attribute bug and returns zero results even for a seeded, on-topic precedent. The notebook falls back to a native `ContextGraph.find_nodes()` lookup that works. Root cause traced below, under GraphRAG retrieval re-ranking: it is the same underlying gap in `VectorStore`, not a separate issue.
- **GraphRAG retrieval re-ranking** (Step 18): `ContextGraph.query_with_reasoning()`/`AgentContext.retrieve()` can log an internal `TextEmbedder` failure ("Text cannot be empty or whitespace-only") during re-ranking. Traced to its exact source: `VectorStore.store_vectors()` (`vector_store.py`, around line 499) drops the `metadata` argument when delegating to a backend that exposes `add_vectors()` but not `store_vectors()`, which includes the real FAISS backend this notebook uses for genuine ANN search. Every memory stored through `AgentContext.store()` therefore reaches FAISS with empty metadata, so `ContextRetriever._retrieve_from_vector()` recovers an empty string for `content`, and `_rank_and_merge()` embeds it. `TextEmbedder.embed_text()` correctly rejects the empty string and reports the failure to Semantica's progress tracker (visible as a `TextEmbedder` ❌ in the CLI progress table), then `VectorStore.embed()` catches it and substitutes a random fallback vector with a warning. The retrieval call still returns real results; only that one result's re-ranking score is degraded to a random vector instead of a real one. Confirmed with a standalone reproduction against the installed version, not inferred from the log line alone.
- **Hybrid search** (used internally by advanced retrieval paths): `HybridSearch.search()` (`hybrid_search.py`, around line 314) unconditionally reads `self.vector_store.vectors`, a dict `VectorStore` only creates for `backend="inmemory"`. Every other backend, including FAISS, never gets that attribute, so `HybridSearch` raises `AttributeError`, caught internally and reported to the progress tracker as a `HybridSearch` ❌. This is the same class of backend-inconsistency bug as the metadata drop above: code written against the in-memory backend's internals, applied to a `VectorStore` configured for a different, real backend.
- **Server-backed RDF database** (Step 13): `TripletStore` has no embedded or in-memory mode by design; it always dials a real server. The notebook makes a genuine connection attempt and reports the real, expected connection failure (a `BlazegraphStore` ❌ in the CLI progress table, not a bug: there is no local Blazegraph server running). `OntologyEngine`'s built-in SKOS search shares the same requirement and is demonstrated against the same connection attempt, failing for the same reason rather than a separate limitation. The Oxigraph store earlier in the same step is unaffected and persists real data regardless.
- **SKOS hierarchy validation** (Step 8): `ContextGraph` automatically runs `semantica.utils.skos.validate_skos_hierarchy()` whenever an edge is typed `skos:broader` or `skos:narrower`. Demonstrated with the real hierarchy edges extracted from `regulatory_taxonomy.ttl`, then with a deliberately cycle-forming edge that the validator correctly rejects.

None of these three are notebook bugs: they are reproducible defects in the installed Semantica version's `VectorStore`/`HybridSearch` internals (metadata dropped for non-in-memory backends) or an expected, by-design external-server requirement (`TripletStore`/Blazegraph). Each is caught internally with a safe fallback except the Blazegraph connection, which fails loudly as intended. The notebook's own entity list (Step 8) explicitly adds every SKOS concept referenced by a relationship as a named entity before the relationship is built, which avoids an unrelated, separate source of empty-content nodes: `GraphBuilder` auto-creating an unnamed placeholder the first time a node ID is seen only as a relationship target.

Extending this notebook: add a document, add its clauses to `data/requirement_clauses.json` with a verified citation. Every downstream step, including SHACL, provenance, conflict detection, SPARQL, GraphRAG, and Decision Intelligence, picks it up automatically.
