---
title: "Changelog"
description: "Full release history for Semantica — every version, every change."
---

<AccordionGroup>

<Accordion title="Unreleased" icon="code-branch" defaultOpen={true}>

### Added

**Public API Ingestion** (#602 — @Luffy2208 @Sameer6305)

- `PublicAPIIngestor` class built on `RESTIngestor` for credential-free REST endpoints
- `PublicAPIExamples` catalog with 6 pre-configured no-auth examples: `jsonplaceholder_posts/users/todos`, `rest_countries_all`, `data_gov_datasets`, `open_meteo_forecast`
- Polite rate limiting with per-request and per-ingestor `rate_limit_delay` controls
- Response parsing for JSON, CSV, and XML with `response_format="auto"` content-type detection
- Nested `record_path` dot-notation extraction (e.g. `"result.results"` for envelope APIs)
- `batch_public_apis()` for multi-endpoint ingestion with optional `fail_fast`
- `ingest_public_api()` convenience function; `ingest(..., source_type="public_api")` unified dispatch
- Registry integration: `public_api` and `api` task namespaces
- 18 mocked tests + 3 optional-import tests

### Fixed

- **Public API XML XXE hardening** — replaced stdlib `xml.etree.ElementTree` with `defusedxml`; falls back to hardened `lxml` (`resolve_entities=False`, `no_network=True`)
- **`validate_no_auth` string coercion** — `bool("false")` evaluated `True`; replaced with `_coerce_bool()` that maps `"false"/"0"/"no"/"off"` → `False`
- **Auth detection in URL query strings** — `detect_public_api()` now scans endpoint URL for `api_key`, `token`, `access_token` params via `urllib.parse.parse_qs`
- **`ingest_examples` mutable options mutation** — shared `**options` dict deep-copied on each iteration to prevent cross-call contamination
- **`rate_limit_delay` forwarded twice** — added to `config_only_key` strip list so it is consumed once at construction time only
- **NERExtractor LLM silent fallback** (#554 — @KaifAhmad1) — fixed 3 root causes: silent exception swallowing, `response_format=json_object` sent to incompatible gateways, no fallback in `generate_typed` repair loop; 17 regression tests added

### Security

- **GitHub Actions permissions hardened** — explicit `permissions: contents: read` + `security-events: write` in `defender-for-devops.yml`
- **DOMPurify → 3.4.0+** via npm overrides — fixes 6 Dependabot alerts including prototype pollution → XSS, mutation-XSS, `SAFE_FOR_TEMPLATES` bypass, `ADD_TAGS`/`ADD_ATTR` bypasses
- **`uuid` → 13.0.1+** — fixes missing buffer bounds check in `v3`/`v5`/`v6` APIs (CVE-2026-41907)
- **Vite → 6.4.3** — resolves path traversal in optimised-deps `.map` handling (CVE-2026-39365) and esbuild dev-server CORS issue
- **esbuild forced to 0.28.1+** — fixes missing binary integrity verification in Deno distribution module; `npm audit` now reports 0 vulnerabilities
- **Leaked Groq API keys removed** from 10 cookbook notebooks across `supply_chain`, `intelligence`, `cybersecurity`, `finance`, `blockchain`, `advanced_rag`, and `biomedical` — revoke affected keys in the Groq console

</Accordion>

<Accordion title="v0.5.0 — Ontology Hub & Distance Intelligence" icon="star">

Released **May 11, 2026**

```bash
pip install semantica==0.5.0
```

### Added

**Ontology Hub** (PRs #518, #519, #524 — @KaifAhmad1 @ZohaibHassan16)

- **Visual Ontology Editor** — @xyflow/react canvas for authoring classes/properties/individuals without hand-writing OWL/Turtle; context menus on nodes and edges; all edits debounced as pending diffs via `PATCH /api/ontology/draft`
- **Ontology Registry** — full CRUD with status/format badges, per-ontology stats, live search, filter pills (All/OWL/SKOS/Internal/External)
- **Ontology Loader** — three-mode modal: URL import (fetch preview + load), file upload (`.ttl/.rdf/.owl/.nt/.jsonld/.n3`), create new (scratch/from-data/from-text)
- **Alignments Tab** — cross-ontology alignment authoring; pairwise alignment matrix; alignment suggestions via `POST /api/ontology/suggest-alignments` (0.4×label + 0.6×TF-IDF cosine blend)
- **Health Dashboard** — per-ontology quality scoring across Completeness, Consistency, SHACL, Alignment, Documentation; issue list with severity badges; downloadable JSON health report
- **SHACL Studio** — shape generation via `POST /api/ontology/shacl/generate` (permissive/standard/strict tiers); Monaco editor with custom Turtle syntax tokenizer; shape library panel
- **Versions & Proposals Tab** — version timeline, proposal review (approve/reject/publish), SHACL pre-validation, side-by-side diff
- **Entity Search Panel** — debounced 320ms search across all loaded ontologies; type filter pills; result detail with super/subclasses, domain/range, instance count
- **SKOS Vocabulary Manager** — hierarchical concept browser with recursive `ConceptTreeNode`; full SKOS annotation detail
- 16 backend endpoints under `/api/ontology`

**Distance Intelligence** (PR #502 — @KaifAhmad1)

- `ContextGraph.get_neighbors(include_distance_metadata)` — adds `distance_band`, `confidence_decay`, `path_to_anchor` per result
- `AgentContext.retrieve()` / `find_precedents()` blend graph proximity with semantic score (`combined_score = (1−w)×semantic + w×proximity`)
- 5 new API endpoints: distance matrix, semantic neighborhood, causal distance, temporal distance history, distance-enriched export
- Explorer UI: Ego Mode (BFS depth-of-field fading, depth slider 1–8), Structural overlay, Semantic overlay, Heatmap (green→red by hop); path inspector with distance band chip
- Per-session graph revision-based embedding cache — `get_cached_embeddings()` with thread-safe caching and automatic invalidation
- 57 new tests in `tests/context/test_distance_intelligence.py`

**Parquet Ingestion** (PR #548 — @Luffy2208)

- `ParquetIngestor` with PyArrow backend; single file and partitioned directory ingestion; schema/metadata extraction; selective column reading; Hive-style partition discovery; 32/32 tests passing

**Graph Explorer**

- Landing page redesign with hero section, animated SVG preview, live graph stats (PR #516 — @ZohaibHassan16)
- Bidirectional path finding — `directed=false` on BFS and Dijkstra (PR #475 — @KaifAhmad1)
- Indexed search — purpose-built inverted index with LRU cache; 24ms → 0.004ms on 118k-node graph (PR #481 — @ZohaibHassan16)
- `PathResponse` gains `hop_count` and `distance_band` ("direct"/"near"/"mid-range"/"distant")

**DuplicateDetector result limiting** (Issue #534 — @KaifAhmad1)

- `max_results`, `top_k_per_entity`, `min_similarity`, `sort_by` options with construction-time validation
- 15 new tests in `TestResultLimiting`

### Fixed

- **`ConflictDetector.detect_conflicts()` duplicate definition** (Issue #533) — Python was silently overwriting the dispatcher definition; merged into single method with `method` param support
- **`semantica[all]` fails on Windows** (Issue #532) — removed `faiss-gpu` from `[all]` extra; GPU users install `semantica[gpu]` explicitly
- **`UnicodeEncodeError` on Windows cp1252** (Issue #531) — 5 direct `sys.stdout.write()` calls in `ConsoleProgressDisplay.update()` replaced with `self._safe_write()`
- **Circular import in `semantic_extract`** (Issue #528) — shared types extracted to `types.py`; `TripleExtractor` alias added; `from __future__ import annotations` for Python 3.8 compat
- **Lazy-load optional ingest backends** (Issue #527) — optional backends deferred behind `__getattr__`; `except ImportError` → `except ModuleNotFoundError` to prevent masking real bugs
- **OWLExporter Turtle syntax** (Closes #478) — invalid multi-block output fixed; data properties no longer silently dropped; 43 tests added
- **Ontology Hub post-review hardening** — broken registry filters, toggle/refresh URI corruption, SSRF in URL fetch, file upload format misdetection, XML hardening, `O(999999)` search scan, ReDoS in format detector

### Security

- **12 vulnerability fixes** (@KaifAhmad1):
  - `[CRITICAL — CWE-95]` Eval injection in `media_parser.py` — replaced `eval(ffprobe_output)` with `fractions.Fraction`
  - `[CRITICAL — CWE-502]` Pickle deserialization in `agent_memory.py` — replaced with JSON; legacy `.pkl` files refused with migration message
  - `[HIGH — CWE-89]` SQL injection in `snowflake_ingestor.py` — `LIMIT`/`OFFSET` parameterized; `ORDER BY` regex-validated
  - `[HIGH — CWE-611]` XXE in `rdf_parser.py` — `defusedxml.defuse_stdlib()` before all RDF/XML parsing
  - `[HIGH — CWE-346/200]` Missing security headers in `server.py` — `CORSMiddleware`, `X-Content-Type-Options`, `X-Frame-Options`, HSTS
  - `[MEDIUM — CWE-20]` Algorithm param unconstrained in `graph.py` — enum-validated `bfs|dijkstra` only
  - `[MEDIUM — CWE-434]` RDF upload without extension check — `.ttl/.rdf/.owl/.xml/.jsonld` allowlist enforced
  - `[MEDIUM — CWE-1336]` Prompt injection in `llm_extraction.py` — user-supplied content wrapped in `json.dumps()`
  - `[MEDIUM — CWE-95]` Dynamic `__import__()` in `pipeline_validator.py` — replaced with proper import
  - `[MEDIUM — CWE-1333]` ReDoS in `enrich.py` — whitespace-normalize then split on literal `" AND "`
  - `[LOW — CWE-22]` Path traversal in `server.py` SPA route — `Path.resolve().relative_to()` guard
  - `[LOW — CWE-400]` Unbounded SPARQL — 5,000-row cap, 30s timeout, `Semaphore(4)` concurrency cap

</Accordion>

<Accordion title="v0.4.0 — Temporal Intelligence & Knowledge Explorer" icon="clock">

Released **April 8, 2026**

```bash
pip install semantica==0.4.0
```

### Added

**Temporal Intelligence** (@KaifAhmad1, PRs #396–#402)

- **Core Temporal Data Model** — `TemporalBound`, `BiTemporalFact`, valid-time and transaction-time filtering; history-preserving revisions with supersession semantics
- **Point-in-Time Query Engine** — `TemporalGraphQuery.reconstruct_at_time()` builds consistent subgraphs without mutating source; `TemporalConsistencyReport` detects inverted intervals, overlapping relationships, and temporal gaps
- **Allen Interval Algebra** — full 13-relation `IntervalRelation` enum; `TemporalReasoningEngine` with interval merging, gap analysis, coverage calculation, timelines; zero LLM calls
- **Temporal Awareness in ContextGraph** — `Decision` gains `valid_from`/`valid_until`; `ContextGraph.state_at(timestamp)` serializable snapshot; `AgentContext.checkpoint()`, `diff_checkpoints()`, `flush_checkpoint()`
- **`TemporalNormalizer`** — zero LLM calls, pure regex + dateutil; `normalize(value)` → UTC datetime tuple; 13-domain default phrase map; `TemporalAmbiguityWarning` for ambiguous DD/MM/YYYY inputs (never silently guesses locale)
- **Temporal Provenance & OWL-Time Export** — `ProvenanceTracker.track_entity()` auto-stamps `recorded_at`; `RDFExporter.export_to_rdf(include_temporal=True, time_axis="valid|transaction|both")`
- **Temporal GraphRAG** — `TemporalGraphRetriever` filters context to a point in time; `TemporalQueryRewriter` extracts temporal intent from natural language

**Ontology** (@KaifAhmad1 @ZohaibHassan16)

- **SHACL Shape Generation & Validation** (PR #318) — `SHACLGenerator`; three quality tiers (basic/standard/strict); Turtle/JSON-LD/N-Triples output; plain-English explanations for all 7 constraint types. `pip install semantica[shacl]`
- **SKOS Vocabulary Module** (PR #319) — `TripletStore.add_skos_concept()`, `OntologyEngine.list_vocabularies()/search_concepts()`
- **Ontology Alignment API** (PR #361) — `create_alignment()`, `get_alignments()`; OWL/SKOS standard predicates; `ReuseManager.suggest_alignments()`
- **Ontology Diff & Migration** (PR #367) — `VersionManager.diff_ontologies()`; `ChangeLogAnalyzer` classifying CRITICAL/HIGH/MEDIUM/INFO impact; `OntologyEngine.compare_versions()`

**Knowledge Explorer API** (@ZohaibHassan16 @KaifAhmad1)

- **Full FastAPI backend** (PR #384) — graph, analytics, decisions, temporal, enrichment, export/import, annotations routes; 12 export formats; WebSocket progress; 99 integration tests. `pip install semantica[explorer]`
- **Thread safety** (PR #385) — `ContextGraph` and `GraphSession` protected with `threading.RLock`
- **O(N) → O(limit) Pagination** (PR #431) — `find_nodes`/`find_edges` use `itertools.islice` on generators
- **Audit trail & rollback protection** (PR #394) — mutation-level audit tracking, named version tags, `restore_snapshot()` requires explicit confirmation

**Integrations**

- **Agno Agentic Framework** (Issue #249 — @KaifAhmad1) — 5 components: `AgnoContextStore`, `AgnoKnowledgeGraph`, `AgnoDecisionKit` (6 tools), `AgnoKGToolkit` (7 tools), `AgnoSharedContext`; 110 integration tests; 3 cookbook notebooks. `pip install semantica[agno]`
- **Novita AI Provider** (PR #374 — @Alex-wuhu) — OpenAI-compatible; default model `deepseek/deepseek-v3.2`; `NOVITA_API_KEY`

**Reasoning**

- **Native Datalog Reasoning Engine** (PR #371 — @ZohaibHassan16) — pure-Python bottom-up semi-naive fixpoint; recursive Horn clause rules; guaranteed termination; `DatalogReasoner`, `DatalogFact`, `DatalogRule` exported from `semantica.reasoning`

### Fixed

- **Pattern Matcher restored** (PR #387) — dead code silently overwrote `_match_pattern` regex with `re.escape`, breaking transitivity/symmetry/self-join rules
- **OllamaProvider `base_url` ignored** (PR #408 — @AlexeyMyslin) — `ollama.Client(host=self.base_url)` instead of raw module assignment
- **`find_path` always used BFS** (PR #384) — algorithm query param now correctly dispatched to Dijkstra or BFS
- **`ChangeCategory` enum typo** (PR #367) — `"potenitally_breaking"` → `"potentially_breaking"`
- **Snapshot schema** (PR #393) — silent restore failures when `nodes`/`edges` schema didn't match legacy `entities`/`relationships`

### Security

- **CWE-312/359/532** — Removed `api_key` debug `print` blocks from `relation_extractor.py` and `triplet_extractor.py`
- **SHACL path traversal** (PR #318) — replaced `len < 500 and "\n" not in s` heuristic with `os.path.exists()`
- **SPARQL injection** (PR #361) — `search_concepts`, `list_alignments`, `build_values_clause` fully hardened
- **CI overpermissions** — `permissions: contents: read` added to `benchmark.yml` and `security.yml`

</Accordion>

<Accordion title="v0.3.0 — Context Graph Features & Decision Intelligence" icon="brain">

Released **March 10, 2026**

```bash
pip install semantica==0.3.0
```

### Added

**Context Graph** (@KaifAhmad1)

- `ContextNode` / `ContextEdge` gain `valid_from` / `valid_until` with `is_active(at_time) -> bool`
- `ContextGraph.find_active_nodes(node_type, at_time)` — temporal node filtering
- `get_neighbors(min_weight)` — confidence-filtered BFS (default 0.0 passes all edges)
- `link_graph()` / `navigate_to()` / `resolve_links(registry)` / `cross_graph_path()` — cross-graph navigation with full save/load round-trip
- `graph_id` UUID field persisted to JSON

### Fixed

- `is_active()` tz-aware/naive datetime normalization
- `valid_from`/`valid_until` serialization in `add_nodes()`, `add_edges()`, `to_dict()`, `from_dict()`
- Cross-graph link phantom-node prevention in `link_graph()`
- `ProvenanceTracker` added to `semantica/kg/__init__.py` exports
- Duplicate relation creation in `_parse_relation_result` — orphaned legacy block removed
- 14 tests in `test_cross_graph_navigation.py`; 85 real-world tests in `test_030_realworld_comprehensive.py`

</Accordion>

<Accordion title="v0.3.0-beta" icon="flask">

Released **March 7, 2026**

### Added

- **Multi-Founder LLM Extraction** (PR #354 — @KaifAhmad1) — `_parse_relation_result` produces synthetic `UNKNOWN` entity for unmatched subjects/objects; `_match_pattern` rewritten with pre-bound variable resolution and repeated-variable backreferences
- **TTL Export Aliases** (PR #355) — `format="ttl"/"nt"/"xml"/"rdf"/"json-ld"` resolve correctly before validation; 8 tests added
- **Incremental/Delta Processing** (PR #349 — @ZohaibHassan16) — native delta computation between graph snapshots via SPARQL; `delta_mode` in pipeline execution; snapshot retention with `prune_versions()`
- **Deduplication v2**:
  - **Candidate Generation v2** (PR #338) — multi-key blocking, phonetic (Soundex) blocking; 63.6% faster (0.259s → 0.094s)
  - **Two-Stage Scoring Prefilter** (PR #339) — type mismatch, length ratio, token overlap gates; 18–25% faster batch processing
  - **Semantic Relationship Deduplication v2** (PR #340) — predicate synonym mapping; 6.98× speedup (~83ms vs ~579ms)
- **ArangoDB AQL Export** (PR #342 — @tibisabau) — AQL INSERT generation, configurable collections, batch processing (default 1,000); 17 tests
- **Apache Parquet Export** (PR #343 — @tibisabau) — columnar storage, configurable compression (snappy/gzip/brotli/zstd/lz4/none); 25 tests

### Fixed

- Context: `_extract_entities_from_query` uses `word[0].isupper()`; `expand_context` BFS method added
- KG: `calculate_pagerank` aliases; `community_detector._to_networkx` no longer silently loses edges
- Pipeline: retry loop honours `max_retries`; `FailureHandler.handle_failure()` added; `validate` alias added
- `NameError`: missing `Type` import in `utils/helpers.py`

</Accordion>

<Accordion title="v0.3.0-alpha — Decision Tracking & Advanced KG Algorithms" icon="flask">

Released **February 19, 2026**

### Added

- **Decision Tracking System** — complete lifecycle management: `record_decision()` → `add_causal_relationship()` → `find_similar_decisions()` → `trace_decision_chain()` → `analyze_decision_impact()` → `check_decision_rules()` → `get_decision_insights()`
- **Advanced KG Algorithms** — Node2Vec embeddings, betweenness/closeness/eigenvector centrality, Louvain community detection; `GraphBuilderWithProvenance` / `AlgorithmTrackerWithProvenance`
- **Context Engineering Enhancement** (PR #307 — @KaifAhmad1) — full decision tracking, hybrid search, `PolicyException` model, `GraphStore` validation; 9 critical bug fixes, 100% test coverage
- **PgVector Store** (PR #303 — @Sameer6305 @KaifAhmad1) — HNSW/IVFFlat indexing, JSONB metadata filtering, psycopg3/psycopg2 fallback, SQL injection protection; 36+ tests
- **Apache AGE Backend** (PR #311 — @Sameer6305) — `AgeStore` with `GraphStore` API compatibility, SQL injection protection
- **ResourceScheduler Deadlock Fix** (PRs #299 #301 — @d4ndr4d3 @KaifAhmad1) — `threading.Lock` → `threading.RLock`; allocation validation; 6 regression tests
- **Dependabot & Security Automation** — bi-weekly security updates, automated Bandit/Safety/Semgrep scans

### Fixed

- Context Graphs decision tracking: empty/`None` decision ID, `None` metadata, causal chain depth logic, `to_dict`/`from_dict` round-trip
- `PolicyEngine` latest version selection; `AgentContext` fallback robustness and secure logging
- Import issues in test suite (ProvenanceTracker location); causal analyzer `max_depth` bounds

</Accordion>

<Accordion title="v0.2.7 — Snowflake & Benchmarks" icon="database">

Released **February 9, 2026**

```bash
pip install semantica==0.2.7
```

### Added

- **Snowflake Connector** (PR #276 — @Sameer6305) — multi-auth (password/OAuth/key-pair/SSO), table and query ingestion, SQL injection prevention, progress tracking; 24 tests. `pip install semantica[db-snowflake]`
- **Apache Arrow Export** (PR #273 — @Sameer6305) — explicit Arrow schemas, entity/relationship export, Pandas/DuckDB compatible; 20 tests
- **Benchmark Suite** (PR #289 — @ZohaibHassan16 @KaifAhmad1) — 137+ benchmarks across all 10 modules, Z-score statistical regression detection, GitHub Actions workflow. CLI: `python benchmarks/benchmark_runner.py`

</Accordion>

<Accordion title="v0.2.6 — Provenance & Change Management" icon="shield-check">

Released **February 3, 2026**

```bash
pip install semantica==0.2.6
```

### Added

- **W3C PROV-O Provenance Tracking** (Issues #254 #246 — @KaifAhmad1) — comprehensive provenance across all 17 modules; InMemory/SQLite backends; SHA-256 integrity; FDA 21 CFR Part 11, SOX, HIPAA, TNFD compliance infrastructure; 237 tests; opt-in (`provenance=False` by default)
- **Enhanced Change Management** (Issues #248 #243 — @KaifAhmad1) — `TemporalVersionManager` and `OntologyVersionManager` with SQLite/in-memory backends; SHA-256 checksums; detailed diffs; 104 tests; 17.6ms for 10k entities
- **CSV Ingestion Enhancements** (PR #244 — @saloni0318) — auto-detect encoding (chardet) and delimiter (csv.Sniffer); tolerant decoding; optional chunked reading
- **Ingest Unit Tests** (Issues #239 #232 — @Mohammed2372) — file, web, and feed ingestors; 998 lines of tests; 80–86% coverage

### Fixed

- **Temperature Compatibility** (Issues #256 #252 — @F0rt1s @IGES-Institut) — `temperature=None` now omits parameter so APIs use model defaults; `_add_if_set` helper applied to all 5 providers; 10 tests
- **JenaStore Empty Graph** (Issues #257 #258 — @ZohaibHassan16) — `if self.graph is None:` replaces implicit falsy check in 5 methods

</Accordion>

<Accordion title="v0.2.5 — Pinecone, BYOM & Enhanced Extraction" icon="magnifying-glass">

Released **January 27, 2026**

```bash
pip install semantica==0.2.5
```

### Added

- **Pinecone Vector Store** — serverless and pod-based indexes, namespace support, metadata filtering, unified `VectorStore` integration
- **Configurable LLM Retry Logic** — `max_retries` parameter (default 3) in `NERExtractor`, `RelationExtractor`, `TripletExtractor`
- **Bring Your Own Model (BYOM)** — custom HuggingFace models in all extractors; custom tokenizer support; runtime `model=` overrides
- **Enhanced NER** — configurable aggregation strategies (simple/first/average/max); IOB/BILOU parsing; confidence scoring
- **Relation Extraction** — entity marker technique (`<subj>`/`<obj>` tags) for sequence classification models
- **Triplet Extraction** — Seq2Seq model support (REBEL) for direct structured triplet generation

### Fixed

- LLM extraction: strict `max_retries` enforcement prevents infinite retry loops
- Model parameter precedence: runtime arguments correctly override config defaults in HuggingFace extractors
- Circular imports in test suites

</Accordion>

<Accordion title="v0.2.4 — Ontology Ingestion" icon="sitemap">

Released **January 22, 2026**

```bash
pip install semantica==0.2.4
```

### Added

- **Ontology Ingestion Module** — `OntologyIngestor` for Turtle/RDF-XML/JSON-LD/N3 files; `ingest_ontology()` convenience function; recursive directory scanning; `OntologyData` dataclass; `ingest(source_type="ontology")` dispatch

</Accordion>

<Accordion title="v0.2.3 — Neptune, High-Perf Ingestion & LLM Extraction" icon="bolt">

Released **January 20, 2026**

```bash
pip install semantica==0.2.3
```

### Added

- Amazon Neptune dev environment — CloudFormation template; `cfn-lint` in pre-commit
- Vector Store high-performance ingestion — `VectorStore.add_documents()` with batching and parallel processing (`max_workers=6`); `VectorStore.embed_batch()` helper
- LLM relation extraction tests (mocked and Groq integration)

### Fixed

- **LLM Relation Extraction Parsing** — normalized typed responses to consistent dict format before parsing; structured JSON fallback
- **Pipeline Circular Import** (Issues #192 #193) — lazy-loaded `PipelineValidator` inside `PipelineBuilder.__init__`; `TYPE_CHECKING` guard
- **JupyterLab Progress** (Issue #181) — `SEMANTICA_DISABLE_JUPYTER_PROGRESS` env var suppresses rich progress tables

</Accordion>

<Accordion title="v0.2.2 — Parallel Extraction & Gemini SDK" icon="microchip">

Released **January 15, 2026**

```bash
pip install semantica==0.2.2
```

### Added

- **Parallel Extraction Engine** — `concurrent.futures.ThreadPoolExecutor` across all extractors; `max_workers` parameter; thread-safe `ProgressTracker`; ~1.89× speedup

### Changed

- **Gemini SDK Migration** — `google-genai` SDK with `google.generativeai` fallback
- Raised global `optimization.max_workers` default to 8

### Security

- **Credential sanitization** — hardcoded API keys removed from 8 notebooks; `ExtractionCache` excludes `api_key`/`token`/`password` from cache keys; cache key hashing upgraded MD5 → SHA-256

</Accordion>

<Accordion title="v0.2.1 — LLM Output Stability" icon="wrench">

Released **January 12, 2026**

```bash
pip install semantica==0.2.1
```

### Fixed

- **LLM Output Stability** (Bug #176) — correct `max_tokens` propagation; automatic chunk-halving and retry on context/output limit errors
- Removed hardcoded `max_length` constraints from `Entity`, `Relation`, `Triplet`
- Orchestrator lazy property initialization and configuration normalization
- Pinned `protobuf>=5.29.1,<7.0`, `grpcio>=1.71.2`; added `GitPython` and `chardet` to `pyproject.toml`

### Changed

- Increased default `max_text_length` to 64,000 characters for all major providers
- Standardized Groq defaults: `llama-3.3-70b-versatile`, 64k context, native `max_tokens`/`max_completion_tokens`

</Accordion>

<Accordion title="v0.2.0 — Amazon Neptune, Docling & Robust Fallbacks" icon="rocket">

Released **January 10, 2026**

```bash
pip install semantica==0.2.0
```

### Added

- **Amazon Neptune Support** — `AmazonNeptuneStore` via Bolt/OpenCypher; `NeptuneAuthTokenManager` with AWS IAM SigV4 signing; retry/backoff. `pip install semantica[graph-amazon-neptune]`
- **Docling Integration** — `DoclingParser` for PDF/DOCX/PPTX/XLSX/HTML/image parsing; OCR support; Markdown/HTML/JSON export
- **Robust Extraction Fallbacks** — ML/LLM → Pattern → Last Resort chains across all extractors
- **Provenance & Tracking** — `batch_index` and `document_id` metadata on all extracted items
- **Semantic Extract** — auto-chunking for long text; `silent_fail` parameter; JSON parsing with 3-attempt exponential backoff

### Fixed

- `NameError` in `extraction_validator.py` (missing `Union` import)
- Extractors returning empty lists for valid input when primary methods fail
- Model switching bug in `TextEmbedder` (state not cleared on model switch) — Issue #160
- `TypeError: unhashable type: 'Entity'` in `GraphAnalyzer` — Issue #159

</Accordion>

<Accordion title="v0.1.1 — DoclingParser Cross-Platform" icon="puzzle-piece">

Released **January 5, 2026**

```bash
pip install semantica==0.1.1
```

### Added

- Exported `DoclingParser` and `DoclingMetadata` from `semantica.parse`
- Windows-specific troubleshooting note for PyTorch DLL issues

### Fixed

- `DoclingParser` import/export across platforms (Windows, Linux, Google Colab)
- Error messaging when optional `docling` dependency is missing
- Versioning inconsistencies across the framework

</Accordion>

<Accordion title="v0.1.0 — CLI, REST API & PyPI Release" icon="flag">

Released **December 31, 2025**

```bash
pip install semantica==0.1.0
```

### Added

- Command-line interface (`semantica` CLI) with knowledge base building and info commands
- FastAPI-based REST API server for remote access
- Background worker component for scalable task processing
- Automated release workflow with Trusted Publishing support

</Accordion>

<Accordion title="v0.0.1 – v0.0.5 — Early Releases" icon="seedling">

**v0.0.5** *(November 26, 2025)* — Configured Trusted Publishing for secure automated PyPI deployments.

**v0.0.4** *(November 26, 2025)* — Fixed PyPI deployment issues from v0.0.3.

**v0.0.3** *(November 25, 2025)* — Added issue templates, PR template, `SUPPORT.md`, `FUNDING.yml`, and 10+ domain-specific cookbook examples (Finance, Healthcare, Cybersecurity, etc.). Simplified CI/CD workflows.

**v0.0.2** *(November 25, 2025)* — Updated README; expanded cookbook notebooks; improved documentation structure.

**v0.0.1** *(January 2024)* — Initial framework: universal data ingestion, semantic intelligence engine (NER, relation extraction, event detection), knowledge graph construction, 6-stage ontology generation pipeline, GraphRAG engine, multi-agent system infrastructure, multiple vector/graph store backends, temporal knowledge graph support, conflict detection, deduplication, multi-format export, and visualization.

</Accordion>

</AccordionGroup>

---

| Label | Meaning |
|:------|:--------|
| **Added** | New features |
| **Changed** | Changes in existing functionality |
| **Deprecated** | Soon-to-be removed features |
| **Removed** | Removed features |
| **Fixed** | Bug fixes |
| **Security** | Vulnerability fixes |
| **Performance** | Performance improvements |
