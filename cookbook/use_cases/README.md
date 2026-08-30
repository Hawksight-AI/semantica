# Use Cases

Self-contained, end-to-end examples that combine multiple Semantica modules to solve a real-world problem, built from real public data and real external ontologies rather than synthetic samples. Unlike the tutorials in `introduction/` and `advanced/`, each use case is a folder, not a single notebook, with its own `data/` (real source documents plus a download script) and `ontology/` (vendored real ontologies plus a small domain extension) alongside the notebook itself.

## Available Use Cases

- **[Regulatory Intelligence](regulatory_intelligence/README.md)**. Turns 9 real U.S. federal AI-governance and cybersecurity-regulation documents (NIST AI RMF, NIST CSF 1.1/2.0, HIPAA Security Rule, Executive Order 14110, OMB M-24-10, and more) into an explainable, ontology-driven knowledge graph. Full pipeline: ingestion (`PDFParser`/`DoclingParser`), chunking (`TextSplitter`), automatic entity, relation, and triplet extraction across the corpus, ontology import, generation, and evaluation, entity resolution, graph construction (`GraphBuilder`), SHACL validation, deterministic rule-based reasoning (`Reasoner`), PROV-O provenance, a persistent RDF database (Oxigraph on disk, plus Semantica's `TripletStore` for a production server), conflict detection, temporal reasoning, SPARQL, JSON-LD, GraphRAG, and a five-agent Decision Intelligence workflow (precedent search, causal-chain interpretation, policy gating, decision audit reports). Reuses real W3C ontologies (ORG, PROV-O, SKOS, DCAT, OWL-Time, FRBR) rather than inventing new ones.

## Folder Convention

```
use_cases/<name>/
├── README.md           overview, architecture, data and ontology attribution, how to run
├── data/
│   ├── download_*.py    fetches real source documents from their official URLs
│   ├── raw/              the fetched documents, plus a source_manifest.json (real URLs, retrieval dates)
│   └── README.md         data dictionary and source attribution
├── ontology/
│   ├── download_*.py    fetches real external ontologies (vendored byte-for-byte)
│   ├── external/         the vendored real ontology files
│   ├── *.ttl             small hand-authored schema extensions, aligned to the vendored ontologies
│   └── README.md
└── notebook/
    └── *.ipynb           the end-to-end walkthrough
```
