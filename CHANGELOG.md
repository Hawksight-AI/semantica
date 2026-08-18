# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

---

## [Unreleased]

### Added

- **First-class CrewAI integration** (#962)
  - New `pip install semantica[crewai]` extra (`crewai>=0.80.0`) — crewai core provides `BaseTool`/`BaseKnowledgeSource`, so `crewai-tools` is intentionally not included, and the extra is intentionally **not** part of the `all` bundle: crewai hard-requires `chromadb~=1.1.0`, which is affected by the unpatched pre-auth code-injection CVE-2026-45829 (see `integrations/crewai/README.md`)
  - `integrations/crewai/SemanticaKGTool` — a CrewAI `BaseTool` exposing 5 KG actions (`extract_entities`, `extract_relations`, `add_to_graph`, `query_graph`, `find_related`) backed by `NERExtractor` / `RelationExtractor` / `ContextGraph`; supports both sync `run()` and async `arun()`
  - `integrations/crewai/SemanticaDecisionTool` — a CrewAI `BaseTool` wrapping `AgentContext` with 5 decision-intelligence actions (`record_decision`, `find_precedents`, `trace_causal_chain`, `analyze_impact`, `check_policy`)
  - `integrations/crewai/SemanticaKnowledgeSource` — a CrewAI `BaseKnowledgeSource` that serializes a `ContextGraph` into crew knowledge storage; implements both the legacy `load_content()` and current `validate_content()`/`aadd()` contracts so it works across `crewai>=0.80.0`
  - All three classes degrade gracefully when `crewai` is not installed (still importable, full Semantica API available)
  - New `tests/integrations/crewai/`: 70 tests covering stub-based present-case behavior (Pydantic/BaseTool subclassing, every action, knowledge-source chunking/storage) plus a subprocess isolation test for the crewai-absent degradation path
  - Docs: `docs/integrations/crewai.md` page, `docs.json` Integrations nav entry, and README integration-matrix/install updates
  - **Hardened during code review**: live `graph`/`context`/extractor state is excluded from CrewAI JSON serialization (`model_dump(mode="json")`) with `model_post_init` self-healing defaults, so checkpoint/resume no longer raises `PydanticSerializationError`; `query_graph` now searches node content (not just ids/types); `trace_causal_chain` returns an explicit error instead of substituting similarity precedents when causal tracing is unavailable, and calls `trace_decision_causality(..., max_depth=...)` with the correct argument name; `find_precedents` propagates `max_precedents` as the backend `limit`; `add_to_graph` writes are serialized under a module lock so concurrent agents can't double-count duplicate adds; nameless entities are skipped instead of creating `repr()`-junk nodes
  - **Hardened during second code review**: `check_policy` rules are now coerced type-aware — `bool("false")` was truthy, so `enabled == false` reported a violation for `enabled: false`, and string datums like `"0.90"` were compared lexicographically instead of numerically; `trace_causal_chain` no longer raises `AttributeError` (which escaped the tool) when the decision context has no `knowledge_graph`, returning honest error JSON instead; knowledge-source storage failures log an actionable ERROR (a missing crew embedder otherwise silently left agents with empty retrieval); `add_to_graph` uses a per-graph re-entrant lock instead of a process-global one (independent graphs no longer serialize each other, and re-entrant extractors can't deadlock); entity/relation `confidence=None` normalizes to `1.0` instead of failing the whole extraction; added a subprocess integration test against the real `crewai` package covering `Crew`-level serialization round-trip and restore

- **`ContextGraph` gains retraction and purge — the graph previously had no way to remove a node or edge without discarding everything via `clear()`** (#957, closes #955) by @pravit-amp, reviewed by @KaifAhmad1
  - `retract_node()`/`retract_edge()` close an entity's validity window rather than deleting it, reusing the existing `valid_from`/`valid_until`/`state_at()` machinery: the entity drops out of `find_active_nodes()` and future `state_at()` queries going forward, but `state_at()` calls before the retraction time still return it, so decisions recorded against it stay explainable. A `("kind", id)`-keyed retraction record captures who/why/when, retrievable via `get_retraction()`/`list_retractions()`
  - `purge_node()`/`purge_edge()` are the destructive counterpart: the entity is removed outright, from history as well as the active view, for erasure obligations retraction alone cannot satisfy (e.g. GDPR Article 17). Only a tombstone remains — that a purge happened, when, and why — deliberately never the purged content, via `get_tombstone()`/`list_tombstones()`. Purge is graph-scope only: `AgentMemory` and any bound vector store are not reached, so it is one step of an erasure workflow rather than the whole of it
  - Both operations default to `cascade=True` (also touching every incident edge, and for `purge_node`, the marker node of any cross-graph link the node exits through) since leaving edges active around an inactive/removed node produces an inconsistent active view or dangling endpoints; both accept `cascade=False` for callers that want to handle edges themselves
  - Both are idempotent: retracting/purging an already-retracted/purged entity returns `False` rather than raising, and a repeat retraction preserves the original record's reason rather than overwriting it
  - Retraction/purge closing a validity window never widens an existing one — a node or edge added with `valid_until` already in the past keeps that earlier bound rather than being pushed later by a subsequent retraction time
  - Reuses the existing audit-trail path with no changes to `change_management`: `MutationRecord` already documented `REMOVE_NODE`/`REMOVE_EDGE` in its operation vocabulary; retraction now emits `UPDATE_NODE`/`UPDATE_EDGE`, purge emits `REMOVE_NODE`/`REMOVE_EDGE`, matching the documented contract. Mutation payloads are snapshotted inside the lock and the callback fires after it is released, so a callback that itself mutates the graph (e.g. `clear()`) can't observe or lose in-flight records
  - **Fixed during review** (@KaifAhmad1): `retract_edge()`/`purge_edge()` resolved "the edge" for a given `edge_id` via the first matching object only. `edge_id` is content-derived and, prior to #926, was not guaranteed unique — a graph holding two identical `add_edge()` calls had two edge objects sharing one id. A direct `retract_edge()`/`purge_edge()` call would silently leave the second duplicate untouched (still live, still active) while returning `True` and recording a tombstone/retraction that claimed the edge was fully handled; repeat `purge_edge()` calls also silently overwrote the tombstone's `reason`/`purged_at` on each partial attempt instead of no-op'ing. The same gap let `retract_node()`'s cascade skip a duplicate outright, since it checked the live `_retractions` dict mid-loop and treated the first duplicate's just-written record as proof the second was already handled. `#926` (merged) stops *new* duplicates from being created, but any graph already holding one — loaded from a save made before that fix, or built during the window before it landed — could still trigger this. Now `retract_edge()`/`purge_edge()` act on every edge matching the id under one record, and the cascade's dedup check is snapshotted before the loop starts so within-call duplicates are still closed rather than skipped. 5 new regression tests in `TestDuplicateEdgeId`
  - New `tests/context/test_context_graph_retraction.py`: 49 tests, covering retraction/purge semantics, cascade, idempotency, validity-window narrowing, id-keyspace collisions between node and edge ids, cross-graph link teardown, `clear()`/`load_from_file()` resetting retraction/tombstone state, audit-trail integration against a real `TemporalVersionManager`, mutation-emission ordering under a concurrent `clear()`, and concurrent purges
  - Full `tests/context/` suite: 533 passed
- **`DistanceExporter.compute_pairs()` gains an opt-in `metric_errors` column to distinguish legitimate `None` results from computation failures** (#960, follow-up to #879) by @Karunasagar12
  - Previously, a `None` in `hop_count`/`weighted_distance`/`semantic_similarity`/betweenness could mean either "no path exists" or "the underlying computation raised" — logged as a warning per #879, but not otherwise surfaced, so the two cases were indistinguishable in exported CSV/JSONL/DataFrame data. `include=["metric_errors"]` now adds a `metric_errors` field per row: `""` when all requested metrics succeeded, or a comma-separated list of metric names that raised (e.g. `"hop_count,weighted_distance"`)
  - Opt-in only — default `compute_pairs()`/`to_csv()`/`to_dataframe()`/`to_jsonl()` schema is unchanged unless `"metric_errors"` is explicitly requested
  - The four metric helpers (`_betweenness`, `_hop_distance`, `_weighted_distance`, `_semantic_similarity`) now return `(value, error_name | None)` tuples internally; `compute_pairs()` aggregates the error names per row
  - **Fixed during review** (Qodo): `_betweenness()` failures weren't tracked into `metric_errors` in the initial version — centrality computation could raise and the column would still report `""`. Now returns its error tuple like the other three helpers
  - **Known limitation**: `include=["metric_errors"]` with no other metric names computes nothing, so the column is always `""` in that case — pass it alongside the metrics you want tracked, e.g. `include=["hop_count", "metric_errors"]`
  - New `tests/export/test_distance_exporter_metric_errors.py`: 6 tests covering success, single/multiple failures, opt-out, the no-path-vs-error distinction, and default-schema stability; existing `tests/export/test_distance_exporter.py` updated for the new tuple return type
  - Full `tests/export/` suite: 77 passed

### Changed

- **`GraphBuilder`'s 6 public methods now have Google-style docstrings** (#878, closes #876) by @cakeni
  - `semantica/kg/graph_builder.py`'s `build`, `build_single_source`, `add_temporal_edge`, `create_temporal_snapshot`, `query_temporal`, and `load_from_neo4j` — the core knowledge-graph construction API, imported directly by callers — previously had zero docstrings across all 6 methods, the only file in a 10-file audit sample with that gap, despite CONTRIBUTING.md requiring Google-style `Args`/`Returns`/`Raises`/`Example` docs for public methods. Added full docstrings for all 6, plus the previously undocumented `build_single_source`, with runnable (`# doctest: +SKIP`) usage examples
  - **Corrected during review**: `query_temporal`'s docstring claimed the query text was used to filter the graph; the implementation only records it in the result (`results = {"query": query, ...}`) with no interpretation or filtering. Corrected to state that explicitly
  - **Corrected during review**: `create_temporal_snapshot`'s docstring implied entities were filtered for validity at the snapshot timestamp like relationships are; the implementation copies all entities unfiltered and only filters `relationships` by `valid_from`/`valid_until`. Docstring now distinguishes the two
  - **Corrected during review**: `add_temporal_edge`/`create_temporal_snapshot` docstrings overclaimed numeric-timestamp support; `_parse_time()` only special-cases `str` and `datetime`, falling back to a bare `str()` cast for anything else (not true numeric parsing). Narrowed to "datetime or ISO-formatted string"
  - **Fixed along the way**: `build()`'s `**options` documented a default only for `extract`; `extract_relations`, `extract_triplets`, `ner_method`, `relation_method`, and `triplet_method` all have concrete defaults in `_extract_from_text()` (`True`, `True`, `"llm"`, `"llm"`, `"llm"`) that were left unstated, inconsistent with CONTRIBUTING.md's own docstring example of noting defaults inline
  - `python -m pytest tests/kg/test_kg.py tests/kg/test_graph_builder_external.py -q`: 45 passed
- **`GraphBuilder` raw-text extraction now defaults to local extractors instead of LLM extraction** (closes #930) by @dex0shubham
  - `GraphBuilder._extract_from_text()` defaulted `ner_method`, `relation_method`, and `triplet_method` to `"llm"`, and ran relation extraction unconditionally (`extract_relations` defaulted to `True`) — all four contradicting the defaults documented in the `build()` docstring at the time (`"ml"` / `"pattern"` / `False`), and diverging from the standalone extractors (`NERExtractor` defaults to `method="ml"`, `RelationExtractor` and `TripletExtractor` to `method="pattern"`). The practical effect was that any raw-text `build()` call silently required a configured provider, an API key, and network access
  - Defaults are now `ner_method="ml"`, `relation_method="pattern"`, `triplet_method="pattern"`, and `extract_relations=False`, matching the docstring. LLM extraction remains fully available and is now opt-in
  - **To restore the previous behaviour**, pass the methods explicitly:
    ```python
    builder.build(
        sources,
        ner_method="llm",
        relation_method="llm",
        triplet_method="llm",
        extract_relations=True,
    )
    ```
  - #878 landed in the meantime and resolved the same mismatch in the opposite direction, documenting the LLM values (`"llm"` / `"llm"` / `"llm"`, `extract_relations: True`) as the contract. Per the decision on #930 the code is the side that changes, so those docstring defaults are corrected here to `"ml"` / `"pattern"` / `"pattern"` / `False`, keeping #878's formatting
  - Removed the stale `# Default to LLM methods as per requirement` comment, which read as an intentional decision but did not match the documented contract
  - **Fixed along the way**: `_extract_from_text()` constructed a fresh extractor for every text, and `NERExtractor.__init__` loads its spaCy model eagerly when the method includes `"ml"` — so with the new default, a multi-document build would have reloaded the model once per source. Extractors are now built once per `(kind, method)` and reused for the lifetime of the builder, via `GraphBuilder._get_extractor()`. This path was previously unreachable by default because the old `"llm"` default never touched spaCy
  - **Fixed along the way**: `_extract_from_text()` never forwarded its extracted relations to triplet extraction — it passed only `entities=`, so `TripletExtractor` re-derived relations itself (via a method taken from `triplet_method`) whenever `relations is None`, duplicating work and producing triplets that could disagree with the relations already extracted using `relation_method`. Relations are now passed through as `relations=`; when relation extraction is disabled or fails, `None` is forwarded and `TripletExtractor` keeps its existing self-derivation behaviour
  - **Fixed along the way**: `GraphBuilder._extraction_stats` was only initialised inside `build()`, so calling `_extract_from_text()` directly raised an `AttributeError` that the extraction path's broad `except` swallowed and reported as `"Entity extraction failed"`. It is now seeded in `__init__` as well; `build()` still resets it per run
  - New regression coverage in `tests/kg/test_graph_builder_extraction_defaults.py` pinning all four defaults, verifying that no default resolves to `"llm"`, confirming explicit LLM opt-in still routes correctly, asserting extractors are constructed once across repeated texts, covering fallback method lists (e.g. `ner_method=["pattern", "ml"]`) for all three extractors, asserting relations are forwarded to triplet extraction (and that `None` is forwarded when relation extraction is disabled or fails), and running the real default path end to end with no provider mocked. Verified to fail against the pre-fix code
  - Full `kg` suite: 473 passed

### Fixed

- **`split`/chunking paths bypassed the centralized spaCy model cache, reloading the model on every call** (#1042, closes #998) by @Accute9, reviewed by @Sameer6305
  - `semantica/split/methods.py`'s `split_by_sentences()` and `semantica/split/semantic_chunker.py`'s `SemanticChunker.__init__` each called `spacy.load()` directly instead of reusing the process-level cache added in #889/`semantic_extract/methods.py`'s `load_spacy_model()` — every call/construction re-paid the ~120ms model-load cost independently of `NERExtractor`, which already used the cache
  - Both now route through `load_spacy_model()`, sharing one cached `Language` instance per model name across `split_by_sentences()`, `SemanticChunker`, and `NERExtractor`; a missing model still falls back to regex/paragraph chunking without poisoning the cache for a later successful load
  - **Fixed during review** (@Sameer6305): `NERExtractor.__init__()` still had a direct `spacy.load()` call site with the same cache-bypass issue, outside the two files named in #998 but sharing the same root cause; routed through the cache alongside stale test patch targets and a strengthened cache-configuration assertion
  - **Fixed during review** (@KaifAhmad1): `SemanticChunker.__init__` only caught `OSError` around `load_spacy_model()`, while the sibling fix to `NERExtractor` in this same PR added a broader `except Exception` for a model that is installed but fails at runtime (e.g. a config incompatible with the installed spaCy version). A broken-but-present model crashed `SemanticChunker()` outright instead of degrading to fallback chunking like every other path in this PR. Added the matching `except Exception` branch, leaving `self.nlp` as `None`; new `test_semantic_chunker_falls_back_when_spacy_runtime_is_broken` mirrors the existing `NERExtractor` regression test for the same scenario
  - New `tests/split/test_spacy_model_cache.py`: cache reuse across repeated calls/instances, shared cache between `split_by_sentences()`/`SemanticChunker`/`NERExtractor`, distinct model names loading separately, missing-model fallback without poisoning the cache, and the broken-runtime fallback added above
  - `pytest tests/split/test_spacy_model_cache.py tests/split/test_splitter.py tests/split/test_chunkers.py`: all passing (3 pre-existing, unrelated `tests/test_ner_configurations.py` failures confirmed present on `main` before this PR)

- **`export_yaml` raised a raw `AttributeError` on list input, silently wrote empty exports for unrecognized dict keys, and graph payloads were reconciled differently by every exporter** (#958, closes #956, #952, #953) by @pravit-amp, reviewed by @Sameer6305
  - Graph payloads circulate under two vocabularies, `entities`/`relationships` and `nodes`/`edges`, and each exporter reconciled them locally with a different idiom — `LPGExporter` in particular dropped every entity whenever `nodes` was present but empty, the exact shape `JSONExporter` emits. A new `normalize_graph_payload()` in `utils/helpers.py` centralizes that decision once, adopted by `LPGExporter`, `ArangoAQLExporter`, `Neo4jCSVExporter`, and both YAML exporters; `ContextGraph.to_dict()` now round-trips through YAML correctly as a result
  - `export_yaml(records, path)` on a bare list previously failed with `AttributeError` from inside the exporter; it and the other YAML methods now reject non-mapping input with an actionable `ProcessingError` naming the expected keys, since these formats distinguish entities/relationships/triplets and guessing which one a list represents would mislabel the records
  - `export_yaml({"data": [...]}, path)` previously wrote a structurally valid file with every collection empty, no exception, no warning, and the progress log reporting a completed export. `export_semantic_network`, `export_for_pipeline`, and `export_ontology_schema` now raise `ValidationError` when the payload shares no recognized key with what the method reads, or resolves to nothing while an unread key still holds records — an empty mapping is still accepted, since a genuinely empty graph has no records to lose
  - **Breaking**: the two cases above, plus a bare list, now raise instead of returning cleanly with data silently dropped or a raw `AttributeError` from exporter internals. Migration: pass records under a recognized key (`{"entities": [...]}` / `{"nodes": [...]}` for `semantic_network`, `{"classes": [...]}` for `schema`)
  - **Fixed during review** (Qodo): progress tracking could report a completed export before the output directory existed or the file was written; `export()` now creates the directory and serializes before starting tracking, so a rejected export leaves nothing behind
  - **Fixed during review** (@Sameer6305, round 1): `normalize_graph_payload()`'s collection resolver treated any truthy value as a collection — `{"entities": "abc"}` silently became three single-character records, `{"entities": 42}` leaked a raw `TypeError` from inside `list()`. Collection values are now validated before conversion, rejecting strings/bytes/mappings/non-iterable scalars by name. Separately, `Neo4jCSVExporter._normalize_graph` called the shared resolver with `require_recognized=False`, so it alone kept accepting an unrecognized mapping as a silent empty export; the opt-out (introduced earlier in this same PR, with no other caller) was removed
  - **Fixed during review** (@Sameer6305, round 2): `YAMLSchemaExporter`'s usable-schema check could treat scalar schema metadata (`version`, `uri`, `title`, `description`) as evidence records had been exported, letting records under an unread key drop silently; and `_is_record()` accepted modules and class/type objects through the generic `__dict__` path, which would have reached exporter internals instead of failing at the boundary. Both closed, with regression coverage
  - **Fixed during final maintainer review** (before merge): four more gaps in the shared boundary that the earlier rounds didn't reach
    - `LPGExporter`/`ArangoAQLExporter` called `normalize_graph_payload()` with no type guard, so non-mapping input raised `ValidationError` from inside the resolver — while YAML and `Neo4jCSVExporter` raised `ProcessingError` for the identical mistake, per this PR's own stated contract. The `_require_mapping()` guard that already existed in `yaml_exporter.py` is now shared from `utils/helpers.py` and used by all three
    - `Neo4jCSVExporter._normalize_graph` checked `isinstance(graph, dict)`, so a non-dict `Mapping` (`MappingProxyType`, `ChainMap`) fell through to the object-attribute branch and was rejected, even though the identical payload exported fine via `LPGExporter`/`ArangoAQLExporter`/YAML. Now checks `isinstance(graph, Mapping)`
    - `normalize_graph_payload()` accepts dataclass and attribute-bearing object records (`Neo4jCSVExporter._record_to_dict` reads them), but `LPGExporter`/`ArangoAQLExporter` call `.get(...)` directly on resolved entities — an object-shaped record passed validation only to crash with a raw `AttributeError` once used, the exact failure this PR's boundary exists to prevent. Records are now converted to plain dicts at the boundary (`_coerce_records` → new `_record_to_dict`), so every consumer gets a uniform shape regardless of which reading the caller used
    - Two non-empty spellings of the same collection (e.g. `entities` and `nodes`) holding identical records in a different order were rejected as conflicting, since the check used plain list equality; a caller round-tripping through a dict-keyed cache or a set has no reason to preserve order. Comparison is now an order-independent multiset of each record's canonical JSON form
  - New regression coverage in `tests/utils/test_normalize_graph_payload.py`: exception-type parity for non-mapping input across `export_lpg`/`export_arango`/`export_neo4j_csv`, dataclass-record conversion verified end-to-end through the same three exporters, `Neo4jCSVExporter` accepting a `MappingProxyType` payload, and reordered-alias equality (plus a duplicate-count case confirming the multiset check still catches real conflicts); 4 existing tests updated to assert the corrected dict-conversion behavior instead of the previous object passthrough
  - `pytest tests/export tests/utils tests/context tests/test_export_module.py tests/test_export_methods_wrapper.py tests/test_notebooks_simulation.py`: 718 passed, 4 skipped (up from 641 passed, 62 subtests at PR submission); `black`/`isort`/`flake8 --max-line-length=88` clean on every line this PR touches; `python -m build`: succeeds

- **`ContextGraph.add_edge` had no dedupe — identical edges were stored repeatedly under one shared edge ID, and re-ingest doubled the edge set** (#926, closes #922) by @pravit-amp
  - `_add_internal_edge` appended to `self.edges`, `edge_type_index`, and `_adjacency` unconditionally, with no check for an edge already present. Edge identity is content-derived (`_resolve_edge_identity` builds `edge_id` from `source_id`/`target_id`/`edge_type`/`weight`/`metadata`/`valid_from`/`valid_until`), so two identical `add_edge` calls produced two edge objects sharing one `edge_id` — the graph already considered them the same edge, it just kept both copies. `self.nodes` already deduped by ID; edges did not, so `stats()["edge_count"]` inflated, `density()` could exceed its mathematical maximum of `1.0`, and a refresh/restore job calling `build_from_entities_and_relationships()` (or reloading a saved graph) doubled the edge set on every cycle
  - Added an `edge_id -> ContextEdge` index (`_edge_index`), mirroring how `self.nodes` dedupes by node ID. `_add_internal_edge` now returns `False` when the `edge_id` already exists, checked before touching `edges`/`edge_type_index`/`_adjacency` and before firing the mutation callback, so a repeat `add_edge` is a silent no-op with no phantom `ADD_EDGE` audit event
  - Genuinely parallel edges are unaffected: differing type/weight/metadata/validity still produce distinct content-derived `edge_id`s, so multigraph semantics are preserved
  - Both state-reset paths (`load_from_file()` and `clear()`) also clear `_edge_index`
  - New tests: repeat `add_edge` is a no-op, parallel edges with distinct attributes are preserved, re-ingest via `build_from_entities_and_relationships()` stays at one edge, and `clear()` resets the dedupe index
  - `pytest tests/context/test_context.py`: 31 passed

- **`POST /api/enrich/extract` returned 503 on every request; the whole `/api/decisions*` family returned 500 as soon as a decision existed** (#886, closes #883, closes #884, closes #889) by @joseedson18jc, reviewed by @Sameer6305
  - `semantica/explorer/routes/enrich.py` imported `extract_entities`/`extract_relations` from `semantica.semantic_extract.methods`, names that module never defined (only per-strategy variants like `extract_entities_ml` exist) — the `except ImportError` handler reported this as `"semantic_extract module not available"`, masking a wiring bug as a missing dependency. The route now calls `NamedEntityRecognizer`/`RelationExtractor` directly and forwards extracted entities into relation extraction instead of re-deriving them
  - `ContextGraph.record_decision()` stores `timestamp` as `datetime.now().timestamp()` (a float), while `DecisionResponse.timestamp` was typed `Optional[str]`; passing the value through unconverted failed pydantic validation on every decision route (`/api/decisions`, `/{id}`, `/{id}/chain`, `/{id}/precedents`, `/{id}/compliance`). Added a `field_validator(mode="before")` on `DecisionResponse` normalizing float/int/datetime inputs to ISO-8601
  - Folds in the fix for #889: `extract_entities_ml`/`extract_relations_similarity`/`extract_relations_dependency` called `spacy.load()` on every invocation (~120ms of a ~132ms call, ~60x the actual extraction work). Added a process-level, lock-guarded `load_spacy_model()` cache in `semantic_extract/methods.py`, keyed by model name; failed loads are not cached, and the separate `get_nlp_model()` cache (different `disable=` pipeline config for similarity work) is kept independent to avoid handing one caller's spaCy pipeline to another
  - **Fixed during review** (@Sameer6305): capped previously-unbounded input text on `/api/enrich/extract`; tightened the route's exception handling
  - **Fixed during review** (@KaifAhmad1): the timestamp validator's `math.isfinite()` guard only rejected NaN/inf — a finite-but-out-of-range epoch (e.g. milliseconds mistakenly stored instead of seconds, such as `1723600000000`) still raised an uncaught `OverflowError`/`OSError` from `datetime.fromtimestamp()`, reintroducing an unhandled 500 on `/api/decisions*` for exactly the class of bug this PR closes. Now caught and re-raised as a `ValueError`. Also excluded `bool` from the numeric branch (`isinstance(True, int)` is `True` in Python, so `timestamp=True` was silently coerced to epoch 1 instead of being rejected)
  - New/updated tests: `tests/explorer/test_explorer_api.py` (`TestRecordedDecisions`, extraction coverage, 4 new `TestDecisionResponseTimestampValidator` cases for the range/bool fixes), `tests/semantic_extract/test_spacy_model_cache.py` (6 tests)
  - `pytest tests/explorer tests/semantic_extract/test_spacy_model_cache.py`: 266 passed

- **Explorer UI hid backend failures: graph load hung forever, landing page always showed "System Online"** (#980, closes #977) by @ZohaibHassan16, reviewed by @Sameer6305
  - `GraphWorkspace.tsx` only destructured `{ data, isLoading, isFetching }` from `useLoadGraph()`, ignoring the `isError`/`error`/`refetch` that `useQuery` (`retry: 0`) already returned. Combined with `GraphLoadingOverlay` having no error prop and `showLoadingOverlay` staying true whenever `loadingProgress` held a stale frame, a backend-down or failed fetch left the graph workspace stuck on the last progress frame indefinitely, with no error message and no way to recover short of a full page reload
  - `GraphLoadingOverlay` now accepts `error`/`onRetry` and renders an error card with the real fetch error message and a Retry button (`refetch()`) instead of the stuck progress UI
  - The landing page's `WelcomeScreen` replaced its hardcoded `ready: boolean` (and hardcoded "System Online" text) with a real `checking` / `online` / `offline` status derived from the same connectivity probe already driving the 4th metric card, so the status dot, text, and metric can no longer drift apart or lie about connectivity
  - **Smaller fixes bundled in the same PR**: search results are now dismissible (previously stayed open indefinitely, pushing the graph down); relevance scores display as rounded whole numbers instead of `96.900`/`138.000`; added a debounced (250ms) typeahead combobox to graph search with arrow-key navigation, `aria-activedescendant`, and Escape-to-close, using the existing `/api/graph/search` endpoint
  - **Fixed during review** (Qodo): the typeahead's debounced fetch had no `AbortController`, so a fast-typing user could have a stale suggestion response resolve after a newer one, replacing correct suggestions with outdated ones. In-flight requests are now aborted on every re-debounce and when the query is cleared after a selection
  - **Noted during review** (@Sameer6305): `GraphWorkspaceShell.tsx` contains a third, unused implementation of the same graph-loading/error-handling logic this PR fixes — the issue itself named "two copies that drifted apart" as the root cause the original bug slipped through. Deliberately left out of this PR's scope and tracked separately in #981 rather than blocking this fix
  - `npx tsc -b`: clean; `test:graph-store`/`test:graph-workspace`/`test:plugin-registry`: 42 passed; `npm run build`: succeeds

- **Markdown import hardened against TOCTOU symlink races during file reads** (#932, closes #856) by @lakshanmuruganandam, with fixes by @Sameer6305
  - `AgentMemory._read_markdown_path` read files via `Path.read_text()` after a `Path.is_symlink()` pre-check, leaving a time-of-check/time-of-use window: a path validated as a regular file could be swapped for a symlink before the actual read, causing the importer to follow the link and read an unintended target
  - Reads now go through a new `_read_markdown_file_content()` helper: the path is opened via low-level `os.open()` with `os.O_NOFOLLOW` on platforms that support it (POSIX), so a symlink substituted after validation fails atomically with `ELOOP` instead of being followed; the resulting file descriptor is then verified with `os.fstat()`/`stat.S_ISREG()` to reject non-regular files (FIFOs, devices) even after a successful open
  - Directory imports now also exclude symlinked entries from the file listing (`not file_path.is_symlink()`), consistent with the single-file path already rejecting them
  - **Known limitation**: Windows has no `os.O_NOFOLLOW`, so on that platform the only defense is the earlier `is_symlink()` pre-check, leaving a narrow TOCTOU window; documented inline rather than implying a stronger cross-platform guarantee than the implementation provides
  - New `tests/context/test_agent_memory_markdown.py` coverage: rejecting a symlinked path at both the private helper and the public `import_data()` API, silently excluding symlinked entries during directory import, and the `fstat()`/`S_ISREG` guard against non-regular files (mocked FIFO)
  - `pytest tests/context/test_agent_memory_markdown.py`: 46 passed, 4 skipped (symlink-creation tests skip on Windows without `SeCreateSymbolicLinkPrivilege`)

- **`VectorManager.maintain_store()`/`collect_statistics()` crashed with `AttributeError` on persistent `VectorStore` backends** (#914, closes #855) by @yunaremaia, with fixes by @Sameer6305
  - Both methods accessed `store.vectors`/`store.metadata` directly, which are only initialized for the `inmemory` backend — any persistent backend (FAISS, Qdrant, Pinecone, Milvus, SQLite, PgVector, Weaviate) crashed immediately. Same root cause as the #839/#843/#845/#848 cluster, but `VectorManager` operates on a `VectorStore` instance from the outside, so the fix needed a public accessor rather than another internal guard
  - Added a backend-agnostic `VectorStore.count()`: the `inmemory` backend counts its local dict; persistent backends delegate to a `count()` on the wrapped backend store when one exists, or raise `NotImplementedError` — following the `get_vector()`/`get_metadata()` precedent from #843, a missing/uninitialized backend store is never silently reported as an empty, healthy store
  - `maintain_store()` and `collect_statistics()` now go through `store.count()` instead of touching `.vectors`/`.metadata`
  - **Fixed during review** (@Sameer6305): the initial version had `count()` implemented at the dispatch level only, with no shipped backend actually providing one, and `maintain_store()` manufactured a vacuous `metadata_count == vector_count` tautology for persistent backends (always reporting `healthy: True` without checking anything). Added real `count()` implementations to `FAISSStore` (`len(index.vector_ids)` — FAISS has no delete path, so this list is always consistent with the index), `SQLiteVecStore`, and `PgVectorStore` (both via `SELECT COUNT(*)`); `Qdrant`/`Pinecone`/`Milvus`/`Weaviate` continue to raise `NotImplementedError` since none of them guarantee a cheap, reliable synchronous count. `maintain_store()` now reports `metadata_count: None` for persistent backends instead of the fabricated equality, with `healthy` meaning "store is reachable," not "metadata verified"
  - Two earlier Qodo findings (a count() path that silently returned 0 for a missing backend store, and an unvalidated `hasattr` check that could raise `TypeError` on a mis-shaped adapter) were fixed before this review — replaced with `NotImplementedError` and a `getattr`+`callable()` capability check, respectively
  - New `tests/vector_store/test_vector_manager_persistent.py`: dispatch-level tests for `count()` (inmemory, delegation, missing backend, non-callable `count`, mis-shaped adapter), full `VectorManager` inmemory semantics including divergence detection, persistent-backend dispatch tests, and backend-specific tests against real/mocked FAISS, SQLite (`sqlite-vec`, skipped if unavailable), and PgVector stores
  - Core `vector_store` suite: 40 passed

- **`ContextGraph.get_node_property`/`get_node_attributes` "not found" contract clarified; `add_node_attribute` mutation-callback exception safety fixed** (#882, closes #877) by @ZohaibHassan16
  - `get_node_property` returned `None` for both "node missing" and "property missing" with no way to distinguish them, and `get_node_attributes` returned `{}` for a missing node while its siblings disagreed on the not-found signal (`get_node_property`/`find_node` → `None`, `get_edge_data` → `{}`). Both now accept a `default=` parameter matching `dict.get()`'s convention, defaulting to their historical return values (`None` and `{}` respectively) for backward compatibility. Callers that need to disambiguate "node missing" from "value legitimately absent" can pass a private sentinel as `default`
  - Added Google-style docstrings to `get_node_property`, `get_node_attributes`, `get_edge_data`, and `find_node` documenting each method's not-found contract, addressing #877's "sibling not-found contract undocumented" gap
  - **Corrected during review**: the PR as submitted claimed to fix `add_node_attribute` firing its `mutation_callback` "outside `with self._lock`, without holding the lock," but the diff only removed a stray blank line — the callback call remained outside the lock, unchanged. Further investigation found this was not actually a bug: `self._lock` is a `threading.RLock`, and the same release-the-lock-before-invoking-the-callback pattern is used deliberately in `_add_internal_node`/`_add_internal_edge` elsewhere in this class, avoiding holding the lock for the duration of an arbitrary user-supplied callback. The real inconsistency was that, unlike those two siblings, `add_node_attribute`'s callback call wasn't wrapped in `try/except` — a raising callback propagated uncaught here but was caught and logged there. Now wrapped the same way (`except Exception as e: self.logger.warning(...)`)
  - 13 tests covering happy path, missing node, missing property, sentinel disambiguation, falsy-zero, callback firing/non-firing, and (added during review) a raising callback no longer propagating out of `add_node_attribute`
  - `pytest tests/context/test_context.py -q`: 27 passed

- **Three `tests/normalize/` tests failed for reasons unrelated to the normalize implementations: a missing optional-dependency skip guard, an incomplete chardet allowlist, and a UTC/local timezone mismatch** (#881, closes #860) by @aoright
  - `test_detect_language`/`test_detect_with_confidence` in `tests/normalize/test_language_detector.py` asserted on real `langdetect` output with no skip guard, even though `langdetect` is an optional dependency absent from `pyproject.toml` that `LanguageDetector` already degrades gracefully without (`LANGDETECT_AVAILABLE = False`, falls back to `default_language`) — any environment without it failed both tests unconditionally, including a fresh CI run without optional extras installed. Both are now gated with `@unittest.skipUnless(LANGDETECT_AVAILABLE, ...)`
  - `test_detect_encoding` in `tests/normalize/test_encoding_handler.py` asserted `chardet.detect()`'s result against a 3-name allowlist (`iso-8859-1`/`windows-1252`/`latin-1`); on a short Latin-1 sample, chardet is free to return other compatible single-byte codepages (e.g. `windows-1253`), which fails the allowlist and then cascades into `test_convert_to_utf8` decoding the bytes as Greek instead of the original text. The test now uses a longer, unambiguous Latin-1 corpus and asserts that the detected encoding round-trip-decodes the original text instead of matching a fixed name list; `test_convert_to_utf8` now passes `source_encoding="latin-1"` explicitly rather than relying on chardet's heuristic auto-detection
  - `test_normalize_date_relative` in `tests/normalize/test_date_normalizer.py` compared `RelativeDateProcessor`'s local-clock-based `"today"` (`datetime.now()`, naive, UTC-normalized after the fact by `convert_to_utc()`) against a separately-computed UTC reference date — failing intermittently in any timezone east of UTC whenever the local and UTC dates diverge for part of the day. The test now patches `datetime.now()` to a fixed reference time, making the assertion independent of host timezone
  - `pytest tests/normalize`: 77 passed, 2 skipped (`langdetect` not installed); `black`/`isort`/`flake8 --max-line-length=88` clean on all three changed files. Test-only change; no production code touched

- **MCP server reported a stale `0.4.0` version instead of the installed package version** (#870, closes #863) by @oiahoon
  - `semantica/mcp_server/__init__.py` hardcoded `"version": "0.4.0"` in both the MCP `initialize` response (`SERVER_INFO`) and the `semantica://schema/info` resource, regardless of the actual installed `semantica` version — every MCP client (Claude Desktop, Windsurf, Cline, Continue, VS Code Copilot, etc.) showed the wrong server version. Both surfaces now derive from `semantica.__version__`, the package's authoritative version source, so they can no longer drift from `pyproject.toml`
  - New regression coverage in `tests/test_mcp_server_version.py`, including `!= "0.4.0"` canaries and a cross-surface consistency check
  - **Fixed along the way**: the separate root-level `mcp/` package (`mcp/__init__.py`, `mcp/server.py`, `mcp/resources/registry.py`) — a companion MCP server implementation not included in the built distribution, but documented in `mcp/__init__.py` as a supported way to run against Claude Desktop/Windsurf/etc. from a source checkout — had the same three hardcoded `0.4.0` literals; fixed the same way, with matching regression tests in `tests/test_mcp_package_version.py`

- **`VectorStore._filter_by_metadata()` `AttributeError` on all persistent backends** (#857, closes #849) by @TaherTadpatri
  - `_filter_by_metadata()` iterated `self.metadata` directly, which only exists on the `inmemory` backend — any persistent backend (`faiss`, `qdrant`, `pinecone`, `milvus`, `pgvector`, `sqlite`, `weaviate`) crashed with `AttributeError` on `filter_decisions(query=None, ...)` / metadata-only filtering. Filtering is now delegated to a native `filter_by_metadata()` implemented on each backend store, using backend-native payload/SQL/JSON filtering (Qdrant `scroll()`, Pinecone `query()`, Milvus expression filters, PostgreSQL JSONB, SQLite `json_extract()`, Weaviate collection filters)
  - **Fixed along the way**: `PineconeStore.get_index()` and `filter_by_metadata()` called a nonexistent `self.describe_index_stats()` on the store itself (the method only exists on the `PineconeIndex` wrapper returned by `self.index`); the resulting `AttributeError` was silently swallowed, so dimension auto-detection always failed quietly. Now correctly calls `self.index.describe_index_stats()`
  - **Fixed along the way**: `PineconeStore.filter_by_metadata()` probed for filter-only matches using an all-zero dummy query vector, which Pinecone rejects for cosine-metric indexes — the library's own default — making metadata-only filtering silently non-functional out of the box. Now uses a unit vector instead
  - **Fixed along the way**: `PgVectorStore.filter_by_metadata()`'s list-filter branch formatted boolean values with `str(v)` (`'True'`/`'False'`), never matching PostgreSQL JSONB's lowercase `'true'`/`'false'` text rendering, even though the equivalent scalar-filter branch already handled this correctly
  - **Fixed along the way**: list-valued metadata fields (e.g. `{"tags": ["python", "js"]}`) could never match a list filter on the SQLite or PostgreSQL backends, because both extracted the whole array as its JSON/text representation instead of matching individual elements — silently diverging from the in-memory backend's set-intersection semantics. SQLite now uses `json_each()` over a `json_type`-guarded array/scalar wrapper; PostgreSQL now uses the `?|` "any array element" operator alongside the existing scalar `= ANY(...)` path
  - **Fixed along the way**: `FAISSStore.filter_by_metadata(limit=0)` returned one result instead of zero, because the limit check ran after appending the current match
  - **Fixed along the way**: `MilvusStore`'s metadata expression builder rendered `NaN`/`Infinity` filter values as bare unquoted tokens, producing an invalid Milvus expression whose server-side rejection was then swallowed by a broad `except`, indistinguishable from "no matches"; these values are now rejected up front with a clear `ValidationError`
  - New/expanded test coverage in `tests/vector_store/test_backend_metadata_filtering.py` (all 7 backends, including the Pinecone dimension/zero-vector, PgVector boolean-list, FAISS `limit=0`, and Milvus `NaN` regressions) and `tests/vector_store/test_sqlite_vec_store.py` (new `TestSQLiteVecStoreFilterByMetadata`, run against the real `sqlite-vec` extension, including the array-vs-scalar intersection case)

- **`DistanceExporter` silently swallowed metric computation failures, exporting `None` values indistinguishable from a legitimate "no path" result** (#879, closes #874) by @AmirF194
  - `_betweenness`, `_hop_distance`, `_weighted_distance`, and `_semantic_similarity` each caught `Exception` and returned their sentinel (`None`/`{}`) with no logging; a failed computation and a real "no path exists" looked identical in exported CSV/JSONL/DataFrame data. All four now log a `warning` with `exc_info=True` before returning the sentinel; exported row shape and values are unchanged
  - **Fixed along the way**: the module logger was built with `get_logger(__name__)`, which double-prefixed it to `semantica.semantica.export.distance_exporter` — a name `setup_logging()` never configures — so this module's logging (including a pre-existing `logger.debug` call) was silent regardless. Now uses `get_logger("export.distance_exporter")`, matching every other exporter in the module
  - New regression coverage in `tests/export/test_distance_exporter.py`: warnings fire on exception for all four helpers, exported sentinel values/shape stay unchanged, and the legitimate "no KG backend" `None` path still logs nothing
  - Full `tests/export/` suite: 71 passed

### Security

- **`Authorization`/`Proxy-Authorization` credentials could leak to a different origin across HTTP redirects, and several ingest paths bypassed the shared SSRF/redirect guard entirely** (#1067, closes #947) by @Sameer6305, reviewed by @KaifAhmad1
  - `request_with_ssrf_guard()` previously only stripped sensitive headers from per-request `kwargs["headers"]` on a cross-origin redirect; session-level `Authorization`/`Proxy-Authorization` headers, `session.auth`, and `session.trust_env` (`.netrc` lookup) could all still resurrect credentials on the hop to a foreign origin. All five credential sources are now stripped case-insensitively, kept stripped for the remainder of a multi-hop redirect chain (no resurrection even if a later hop returns to the original host), and unconditionally restored via `finally` — including on exceptions and redirect-limit errors
  - `MCPClient._send_request_http()` and `PublicAPIIngestor.detect_public_api()`/`ingest_public_api()` called `httpx.post()`/`requests.post()`/`session.request()` directly, bypassing `request_with_ssrf_guard()` entirely. Both now route through the shared guard, including when `validate_no_auth=False`
  - `SeedDataManager.load_from_api()` mutated the caller-supplied `headers` dict in place when adding an API-key `Authorization` header, silently leaking the key back into a dict the caller might reuse elsewhere. Now copies before modifying
  - **Fixed during review** (@KaifAhmad1): `allow_private_ips=True` (used to let MCP servers run on localhost/internal networks) was applied to every redirect hop, not just the operator-configured host — a compromised or malicious MCP server could 302-redirect to an internal address (e.g. `169.254.169.254` cloud metadata) and the guard would follow it unchecked, defeating the SSRF protection this PR otherwise adds. Added `allow_private_ips_on_redirect` to `request_with_ssrf_guard()`: a redirect target inherits the original host's private-IP trust only when it matches that host; any other host falls back to strict validation. `MCPClient` now pins `allow_private_ips_on_redirect=False`, so only same-host redirects on a trusted MCP server keep working — a cross-host hop into private address space is blocked
  - **Fixed during review** (@KaifAhmad1): `detect_public_api()` only caught `requests.exceptions.RequestException`, but `request_with_ssrf_guard()` raises `ValidationError` (a disjoint hierarchy) for SSRF-blocked hosts, blocked redirect targets, missing `Location`, or exceeded redirect limits — unlike its sibling `ingest_public_api()`, which already caught it. Callers (including `is_public_api()`) got an undocumented raw `ValidationError` instead of `ProcessingError`, and the error-logging call was skipped. Now catches `(ValidationError, ProcessingError)` and re-raises, matching the sibling method
  - **Fixed during review** (@KaifAhmad1): `detect_public_api()`/`ingest_public_api()` forwarded `**options` into `request_with_ssrf_guard(..., session=self.session, allow_private_ips=self.allow_private_ips, **request_options)` without stripping `session`/`allow_private_ips` from `request_options` first — a caller passing either through the per-call `**options` (a plausible mistake, since `allow_private_ips` is also a documented constructor-level knob) got a raw `TypeError: got multiple values for keyword argument`. Both are now popped from `request_options` before the call
  - New regression coverage added during review: `TestAllowPrivateIpsOnRedirect` (cross-host redirect into private space blocked, same-host redirect trust preserved, default behavior unchanged for existing callers that don't pass the new kwarg) and `TestMCPClientAuthRedirect::test_redirect_to_private_ip_is_blocked`/`test_same_host_redirect_on_private_mcp_server_is_not_blocked` in `tests/ingest/test_auth_header_redirect_security.py`; `test_detect_public_api_propagates_ssrf_validation_error` and duplicate-kwarg regression tests for both methods in `tests/ingest/test_public_api_ingestor.py`
  - `pytest tests/ingest/test_auth_header_redirect_security.py tests/ingest/test_public_api_ingestor.py tests/test_seed_manager.py tests/ingest/test_submodules.py tests/ingest/test_cookbook_integration.py`: 111 passed

- **`FeedIngestor`/`FeedMonitor` (RSS/Atom feed ingestion) had no SSRF protection, allowing requests to internal/private network targets** (#928, closes #927) by @ZohaibHassan16
  - `FeedIngestor.ingest_feed()`, `discover_feeds()` (link-tag fetch, common-path HEAD probe, and feed-validation GET), and `FeedMonitor.check_updates()` all called `requests.get()`/`requests.head()` directly with default redirect-following and no scheme allowlist or private/loopback/link-local IP validation — despite `semantica/ingest/ssrf.py`'s `request_with_ssrf_guard()` already existing and being used by `web_ingestor.py`/`api_ingestor.py`. `ingest_feed()`'s own URL check only verified `urlparse(url).scheme`/`.netloc` were non-empty, never that the scheme was http/https or that the resolved target IP was safe. Reachable via the public `ingest_feed()`/`ingest()` entry points with any caller-supplied feed URL
  - All 5 call sites now route through `request_with_ssrf_guard()`, which validates scheme (http/https only) and resolved IP before the request, and re-validates every redirect `Location` before following it — closing both the direct-IP and redirect-chain SSRF paths. Added an `allow_private_ips` config option to both `FeedIngestor` and `FeedMonitor`, consistent with the other ingestors
  - **Fixed during review** (Qodo): `test_discover_feeds_empty` mocked `requests.get`, which no longer executes now that the code path goes through `request_with_ssrf_guard()` (backed by `requests.request`) — the test was passing without exercising the real code. Corrected to mock `requests.request` and `socket.getaddrinfo`
  - `pytest tests/ingest/test_feed_ingestor.py`: 12/12 passed. Independently reproduced the issue's own PoC (`FeedIngestor().ingest_feed("http://127.0.0.1:8765/feed.xml")` against a live local server) and confirmed it now raises `ValidationError` instead of succeeding
  - **Known limitation carried over from `discover_feeds()`'s pre-existing design**: its common-path and feed-validation loops use a blanket `except Exception: continue`, which now also silently absorbs `ValidationError` from a blocked candidate URL the same way it already absorbed network failures — the request is still correctly blocked before reaching the network, so this is not an SSRF bypass, just a missed opportunity to log "blocked as SSRF target" distinctly from "unreachable"

- **`RepoIngestor` clone surface hardened against GitPython URL/option injection** (#905, closes #868) by @pravit-amp
  - `RepoIngestor.ingest_repository()` passed the caller-supplied repository URL and arbitrary `**options` straight through to `git.Repo.clone_from()` on a `GitPython>=3.1.50` floor predating hardening for `ext::`-style transport helpers and `$VAR`/`${VAR}` environment-variable expansion in clone URLs — unvalidated clone options (`upload_pack`, `multi_options`, `template`, `config`, `env`, ...) could be abused for command execution, and unvalidated hostnames allowed SSRF against internal services (e.g. cloud metadata endpoints)
  - `GitPython` floor raised to `>=3.1.58`
  - Clone options passed to `clone_from()` are now allowlisted to `{depth, branch, single_branch, no_tags}`; anything else raises `ValidationError` before the clone is attempted
  - Repository URLs are validated before cloning: scheme allowlist (`https`, `http`, `git`, `ssh`), rejection of `$VAR`/`${VAR}` tokens, and hostname resolution with every returned address screened against private/loopback/link-local/unspecified ranges. scp-like SSH remotes (`user@host:path`) are recognized and normalized to `ssh://` before the clone call
  - **Fixed during review** (@Sameer6305): the SSRF check originally used `ip.is_reserved`, which flags the NAT64 Well-Known Prefix (`64:ff9b::/96`, RFC 6052) as reserved — falsely blocking `github.com` and other public hosts on IPv6-only/dual-stack networks using NAT64. Narrowed the block list to private/loopback/link-local/unspecified only
  - **Fixed during review** (@Sameer6305): local filesystem repository paths (`git clone /path/to/local/repo`) were being treated as remote URLs and rejected outright; local paths now bypass network validation entirely since they make no network requests and carry no SSRF risk
  - **Known limitation**: the SSRF host check does not classify RFC 6598 Carrier-Grade NAT space (`100.64.0.0/10`) as blocked — Python's `ipaddress.IPv4Address.is_private` does not cover that range, so a hostname resolving into it (e.g. some Kubernetes/CNI pod networks) would not be caught. Follow-up recommended to add it explicitly alongside the existing private/loopback/link-local checks
  - `pytest tests/ingest/test_repo_ingestor_security.py -v`: 44 passed

- **HTTP response header injection via `node_id`, unbounded-memory DoS in link prediction, and unsanitized imported node IDs in the Explorer** (#912) by @Sunil56224972
  - `semantica/explorer/routes/provenance.py`'s `GET /api/provenance/report` f-string-interpolated the `node_id` query parameter directly into the `Content-Disposition` response header; a `\r\n`-bearing `node_id` could inject arbitrary response headers (`Set-Cookie` session fixation, `Content-Type` override for reflected XSS). Fixed with `_safe_content_disposition_filename()`, which strips `\r`, `\n`, `\x00`, `"`, `\` and length-caps the value before interpolation
  - `POST /api/enrich/links` (link prediction) loaded up to 999,999 nodes with no cap or concurrency guard, then scored every candidate — a single request could consume ~1.6 GB RAM, and concurrent requests compounded that with no limit. Capped the candidate pool at 10,000 nodes (`413` if exceeded) and added an `asyncio.Semaphore(2)`, mirroring the SPARQL DoS fix in #898
  - `POST /api/import` stored uploaded JSON/CSV node IDs verbatim; since provenance reports reflect `node_id` into `Content-Disposition`, an attacker could upload a node with a CRLF-bearing ID once and trigger the header-injection chain above for every subsequent viewer. Added `_sanitize_import_node_id()`, applied to node and edge `source_id`/`target_id` fields on both the JSON and CSV import paths
  - **Corrected during review**: the JSON import path had a second, unsanitized branch — any uploaded node object already carrying a `"properties"` key (the shape this app's own `/api/export` produces, and already used elsewhere in the test suite) was appended to the graph as-is, bypassing `_sanitize_import_node_id()` entirely and leaving the stored-header-injection chain open via a one-line payload (`{"id": "<crlf>", "properties": {}}`). That branch now sanitizes `id` before storing
  - **Corrected during review**: the link-prediction cap checked `total` only *after* calling `session.get_nodes()`/`get_edges()`, which normalize the graph's *entire* matching node/edge set before applying `limit` — so the guard ran after the expensive work it was meant to prevent had already happened, on every request regardless of graph size. Added `GraphSession.get_raw_counts()`, an O(1) check against the raw `len(graph.nodes)`/`len(graph.edges)` collections, and moved the size check ahead of the normalizing calls
  - **Corrected during review**: 5 of the original PR's 22 regression tests asserted that literal words like `"Set-Cookie"`/`"Content-Type"` disappeared from the sanitized value — the sanitizer only strips `\r\n\x00"\\`, not letters, so those assertions failed against the PR's own fix as submitted. Corrected to assert on the property that actually blocks header injection (no `\r`/`\n` survives), and added end-to-end tests that exercise the real `/api/import` → `/api/provenance/report` route chain (not just the standalone sanitizer function) so the `properties`-key bypass has regression coverage
  - Full `explorer` suite: 241 passed; `tests/test_security_regression_pr2.py`: 30 passed

- **`fastapi`/`python-multipart` floors in the `explorer` extra allowed PYSEC-2024-38 (CVE-2024-24762 / GHSA-2jv5-9r88-3w3p, `python-multipart` ReDoS)** (#871, closes #869) by @agu2347
  - `explorer` declared `fastapi>=0.100.0` and `python-multipart>=0.0.6`; both floors resolve to versions carrying a ReDoS in `python-multipart`'s `Content-Type` header option parser (`parse_options_header`), reachable by any endpoint that accepts form/multipart data — an attacker-crafted header option can stall the event loop for minutes
  - **Corrected during review**: the original fix raised only `fastapi>=0.109.1`, leaving `python-multipart>=0.0.6` unchanged. `python-multipart` is declared as its own direct dependency in the `explorer` extra rather than pulled in transitively via `fastapi[all]`, so a bare `fastapi` install enforces no `python-multipart` floor at all — the vulnerable `0.0.6` could still resolve with `fastapi>=0.109.1` in place. Floors raised to `fastapi>=0.109.2` / `python-multipart>=0.0.7`, the first versions of each that exclude the vulnerable range
  - **Fixed along the way**: the `Security` workflow's `pip-audit` job ran only on a weekly schedule with `continue-on-error: true`, against a bare Python environment with none of Semantica's optional extras installed — it would never have seen `fastapi`/`python-multipart` regardless of which floor was pinned. `security-scan.yml`'s Safety check has the same blind spot (`pip install -e ".[llm-litellm]"` only, never `[explorer]`). `pip-audit` now also runs on `pull_request` when `pyproject.toml` changes, installs `semantica[all]`, and fails the build on any finding for that trigger; the schedule/`workflow_dispatch` runs stay non-blocking pending a full pass over any pre-existing findings across the whole `[all]` tree
  - **Caught by the new gate on its first run**: `python -m pip install -e ".[all]"` pulled in `setuptools==79.0.1`, vulnerable to CVE-2026-59890/GHSA-h35f-9h28-mq5c/PYSEC-2026-3447 (Unicode-normalization bypass of `MANIFEST.in` exclude/prune patterns on macOS APFS/HFS+, letting excluded files leak into a built sdist), fixed in `83.0.0`. `[build-system] requires` had the exact same too-permissive-floor pattern this whole entry is about (`setuptools>=61.0`), and `actions/setup-python`'s baked-in `setuptools` isn't governed by that pin at all since it's outside any isolated build. Bumped `[build-system] requires` to `setuptools>=83.0.0`, and the `Security` workflow now runs `pip install --upgrade pip setuptools` before auditing so the scanned environment can't have a stale ambient copy regardless of what governs it
  - Full `explorer` suite: 241 passed

## [0.6.5] - 2026-08-11

### Added

- **Embedded Oxigraph backend for `TripletStore`** (#838, closes #834) by @Linxiushen
  - Added `OxigraphStore` (`semantica/triplet_store/oxigraph_store.py`), an in-process SPARQL 1.1 store via the optional `pyoxigraph` dependency — no external server (Blazegraph/Jena/RDF4J/Anzo) required, fixing the confusing plain connection-error failure `TripletStore` previously produced with no server running (no local Docker daemon, no Java, CI, or a fresh laptop)
  - Runs fully in memory by default, or persists to a local directory via `TripletStore(backend="oxigraph", path=...)`; reopening the same directory resumes existing data
  - Full CRUD, native batch loading (`Store.extend`), named-graph scoping (`graph=` on add/query), and SPARQL SELECT/ASK/CONSTRUCT/DESCRIBE result mapping matching the existing backend contract; reuses `sparql_escaping.py` for datatype-IRI resolution instead of reimplementing it, and preserves RDF literal datatype/language metadata across writes, reads, and query results
  - New optional `semantica[tripletstore-oxigraph]` extra (`pyoxigraph>=0.5.0`), included in the `all` extra; the import is lazy, so `TripletStore` and the rest of Semantica keep working without `pyoxigraph` installed
  - Wired into `TripletStore` (`backend="oxigraph"`, added to `SUPPORTED_BACKENDS` and `NAMED_GRAPH_CAPABLE_BACKENDS`) and exported from `semantica.triplet_store`; README, module reference, glossary, and usage guide updated with install/configuration examples
  - **Fixed along the way**: a missing `pyoxigraph` install surfaced as a generic wrapped `ProcessingError` instead of the underlying `ImportError` and its install hint, because `TripletStore._initialize_store_backend()`'s broad `except Exception` caught and rewrapped it; `ImportError` is now re-raised as-is so the `pip install "semantica[tripletstore-oxigraph]"` hint reaches the caller
  - New integration tests in `tests/triplet_store/test_oxigraph_store.py` covering persistence/reopen, named-graph isolation, SELECT/ASK/CONSTRUCT result shapes, and the missing-dependency error message; skipped automatically when `pyoxigraph` isn't installed, and not yet exercised in CI since it doesn't install the optional extra or run the Python test suite

- **PROV-O trust blockers and general spec completeness for `ProvenanceManager`** (#825) by @KaifAhmad1
  - **Invalidation instead of hard delete**: new `ProvenanceManager.invalidate(entity_id, agent_id, reason=None)` tombstones an entry — archives its pre-invalidation state under a stable versioned key, then appends the invalidated entry (`invalidated`, `invalidated_at_time`, `invalidated_by`, `invalidation_reason`) — instead of mutating or deleting it, so an audit can prove a fact existed, was reviewed, and was retracted. `ProvenanceManager.clear()` remains the bulk dev/test store-reset utility it always was; it was not repurposed
  - **Hash-chained integrity**: every entry now carries `sequence_id`/`previous_checksum`, chaining it to the entry immediately before it in insertion order. New `ProvenanceManager.verify_chain()` walks the chain and reports any break, including a row hard-deleted directly from the underlying table — something a lone per-row SHA-256 checksum can never detect on its own. `compute_checksum()` now also covers `agent_id`/`agent_type`, the lineage-link fields, and the invalidation fields, closing several fields that previously weren't tamper-evident
  - **Typed Agent/Activity**: `agent_id` was a dead field — no `track_*` method read it from kwargs, so it was always the `"semantica"` default regardless of what callers passed; fixed, and paired with new `AgentRecord(id, agent_type, is_automated)` / `ActivityRecord(id, activity_type, started_at_time, ended_at_time)` dataclasses (pass via `agent=`/`activity=` kwargs) so a human reviewer, an LLM call, and an automated pipeline stage are now distinguishable, and activities carry real start/end timing. Wired through all 18 `*_provenance.py` wrapper modules and `track_entity`/`track_relationship`/`track_chunk`/`track_property_source`
  - **Versioning vs. derivation split**: new `previous_version_id` ("this corrects a prior version of the same fact") and `derived_from_id` ("this was derived from a different source entity") fields, additive alongside the legacy combined `parent_entity_id` so existing readers are unaffected
  - **Downstream lineage traversal**: new `get_descendants()`/`trace_descendants()` (reverse BFS in both `InMemoryStorage` and `SQLiteStorage`), closing the gap flagged in `semantica/explorer/routes/provenance.py` where `direction="downstream"` was dead code with no reverse lookup to feed it; the Explorer's `/api/provenance` lineage response now merges both directions
  - **W3C PROV-O qualified relations**: `export_prov()` now emits `prov:qualifiedAssociation`/`hadRole` (distinguishing "approved by" from "generated by" for sign-off workflows), `qualifiedGeneration`/`Generation`, `qualifiedUsage`/`Usage`, `qualifiedDerivation`/`Derivation`, `qualifiedInvalidation`/`Invalidation`, `wasAssociatedWith` (Activity→Agent), `actedOnBehalfOf` (Agent→Agent delegation), and `wasInformedBy` (Activity→Activity, via a new `informed_by=[...]` kwarg), alongside the existing plain triples
  - **Bitemporal + Bundle support**: `revision_type`/`supersedes`/`valid_from`/`valid_until` fields (plain caller-supplied passthrough, matching the deprecated `kg.ProvenanceTracker`'s actual contract) plus new `revision_history()` and `query_recorded_between()` methods, closing the two "no direct equivalent yet" rows in `docs/migration/kg-provenance-tracker.md`; `bundle_id` emits `prov:Bundle`/`hadMember` membership triples to partition provenance by source/dataset/ingestion-run
  - **Configurable, interlinked namespace**: `export_prov(base_uri=...)` / `--base-uri` CLI flag, defaulting to a new `ProvenanceManager.DEFAULT_BASE_URI` (`https://semantica.dev/ns#`) that `RDFExporter`'s `NamespaceManager` and `OWLExporter`'s default `ontology_uri` now both reuse, so KG-exported, OWL-exported, and PROV-exported URIs for the same `entity_id` co-resolve instead of three independently-hardcoded placeholder domains
  - New CLI commands: `semantica provenance invalidate|verify-chain|descendants`
  - **Fixed along the way**: `track_entities_batch()` silently absorbed batch-level typed kwargs (`agent_id`, `entity_type`, `activity_id`) into the opaque `metadata` JSON blob instead of forwarding them, so the documented banking example in `docs/guides/provenance.md` never actually worked as written
  - **Fixed along the way**: `compute_checksum()` had to exclude `entity_id` itself from the hash — `track_entity()`'s versioning archives a prior value by copying it to a new key (`"X"` → `"X:v:<timestamp>"`), and hashing `entity_id` meant that legitimate relabel permanently orphaned any other entry that had already chained its `previous_checksum` from the pre-relabel value, surfacing as a false-positive "broken chain." Archival and invalidation are now always a pure relabel (unchanged checksum/sequence position) followed by a fresh chained append, never an in-place mutation of an already-chained entry
  - **Fixed along the way**: `InMemoryStorage.get_chain_head()` ignored the already-committed chain head whenever the current transaction had staged any entries, understating the head and corrupting the next append's chain link
  - **Fixed along the way**: several new `ProvenanceEntry` fields were initially wired into the dataclass and `export_prov()` but not into `SQLiteStorage`'s DDL/INSERT/row-mapping — `InMemoryStorage` stores the dataclass directly so it masked the gap. Added a permanent regression test (`test_all_fields_round_trip_through_sqlite`) asserting every field survives a SQLite round trip, to catch this class of bug for any future field additions
  - Flagged, not fixed (separate, pre-existing issues independent of #825): `semantica/pipeline/pipeline_provenance.py` imports a nonexistent module and wraps a `Pipeline` dataclass with no `run()` method, so `PipelineWithProvenance` has never worked; most of the 18 wrapper modules' backing classes are themselves missing or incomplete (e.g. `context.context_manager`, `deduplication.deduplicator`, `normalize.normalizer` don't exist; `EmbeddingGenerator` exists but has no `.embed()`); `kg_provenance.py` passes `entity_type` inside its `metadata={}` dict instead of as a top-level `track_entity()` kwarg across most of its ~30 call sites, so it never actually populates the real field
  - Extensive new test coverage across `tests/provenance/test_manager.py`, `test_schemas.py`, and `test_storage.py` (invalidation, hash-chain verification including a simulated hard-delete-detection case and an interleaved-chaining stress test, agent/activity typing, versioning/derivation split, downstream lineage, qualified export triples, bitemporal methods, Bundle export, and namespace interlinking)

- **Altair Anzo triplet store backend** (#813) by @KaifAhmad1
  - Added `AnzoStore` (`semantica/triplet_store/anzo_store.py`), a fourth peer to `BlazegraphStore`/`RDF4JStore`/`JenaStore` speaking plain SPARQL 1.1 over HTTP — no new dependency, since Anzo has no official Python SDK but needs none
  - The one structural difference from the existing backends: Anzo addresses data by a dataset/graphmart **URI** (`dataset_uri`, required) rather than a short namespace/repository name, so the endpoint path (`<endpoint>/sparql/<store_type>/<url-encoded_dataset_uri>`) percent-encodes it; `store_type` defaults to `"graphmart"` and can be set to `"dataset"`
  - Reuses the shared `sparql_escaping.py` literal-escaping, datatype-IRI resolution, and CONSTRUCT-detection helpers rather than reimplementing them, matching `BlazegraphStore`'s CONSTRUCT/bindings `execute_sparql` contract exactly
  - Wired into `TripletStore` (`backend="anzo"`, added to `SUPPORTED_BACKENDS` and `NAMED_GRAPH_CAPABLE_BACKENDS`) and `config.py` (`TRIPLET_STORE_ANZO_ENDPOINT` env var / `anzo_endpoint` config key), and exported from `semantica.triplet_store`
  - 32 new tests in `tests/triplet_store/test_anzo_store.py` (mocked HTTP, no live Anzo instance needed), including dataset-URI percent-encoding cases that don't apply to the other backends
  - Bulk loading uses SPARQL `INSERT DATA` (the same approach `BlazegraphStore` uses) rather than Anzo's separate HTTP Client Interface, keeping the `bulk_load()` contract identical across backends

- **Comprehensive unit and security test suite for the `/api/sparql` Explorer route** (#773) by @Sameer6305
  - Added `tests/explorer/test_sparql_route.py` (34 tests) covering the SPARQL Explorer route (`semantica/explorer/routes/sparql.py`), which executes arbitrary SPARQL queries against an in-memory rdflib projection of the live graph and previously had zero test coverage
  - Verified read-only allowlist enforcement against write and mutation queries (`INSERT DATA`, `DELETE DATA`, `DELETE WHERE`, `DROP ALL`, `CLEAR ALL`, `LOAD`, `CREATE GRAPH`, `MODIFY`, comments, and multi-statement injections like `SELECT ... ; DROP ALL`), confirming rejected queries short-circuit before any graph is built or queried
  - Verified resource-limiting behavior, confirming row capping (`_SPARQL_MAX_ROWS`) truncates results and sets `truncated: true`, query timeout (`_SPARQL_TIMEOUT_S`) returns a clean error message without crashing, and concurrency semaphore (`_SPARQL_MAX_CONCURRENT`) prevents thread starvation under load
  - Verified RDF projection fidelity for node properties and edge relationships, and error formatting for malformed SPARQL syntax with line and column extraction
  - Follow-up review fixes (#805): extracted the duplicated row-cap-and-truncate loop (previously copy-pasted between the `CONSTRUCT`/`DESCRIBE` and `SELECT` branches) into a shared `_cap_rows()` helper so the `_SPARQL_MAX_ROWS` cap is enforced identically by both; added `test_row_cap_truncates_construct_results`, since the truncation path for `CONSTRUCT`/`DESCRIBE` results had no direct test coverage even though `SELECT` truncation did

- **Global default persistent storage for `ProvenanceManager`, plus a working `provenance` CLI** (#795, #802) by @Sameer6305 and @KaifAhmad1
  - Every ingestion/processing module (`kg_provenance.py`, `pipeline_provenance.py`, and 20+ other call sites) instantiated its own `ProvenanceManager()` with no `storage_path`, so all of them silently fell back to `InMemoryStorage` and the SQLite audit trail was never actually written. `ProvenanceManager.set_default_storage_path(path)` now sets a class-level default that every no-arg instantiation picks up, and `Semantica.__init__` wires `config.provenance.storage_path` into it automatically during orchestrator init
  - Added the thread-safe `default_storage_path(path)` context manager (`semantica.provenance.default_storage_path`) for test isolation — it stacks nested overrides and guarantees restoration of the previous default on exit, even on exception, so tests can't leak global state into each other
  - Fixed `ProvenanceManager.__init__` raising `TypeError` on the CLI's `config=` kwarg, and implemented the four methods the CLI already called but that didn't exist on the class: `lineage()`, `audit_log()`, `export_prov()` (W3C PROV-O turtle/ntriples/jsonld via `rdflib`), and `check()` — unblocking `semantica provenance lineage|audit|export|check` end-to-end
  - Follow-up review fixes: `track_entity` no longer aliases a caller-supplied `used_entities` list (it copied the reference and later mutated it in place via `.append()`, which could corrupt a list the caller still held); removed dead fallback branches in `orchestrator.py`/`manager.py` left over from not realizing `Config.get()` already resolves dotted paths; added a `--dry-run` option to `provenance audit` to match `provenance export` (previously only the global `--dry-run` flag worked, not a local one); and `provenance check --strict` no longer prints a green "✓" success line immediately before failing — a failing check now renders as a warning before the `ClickException` is raised

- **Markdown round-trip export/import for `AgentMemory`** (#765, #786) by @SaurabhScripts and @Sameer6305
  - `AgentMemory.export(format="markdown")` and `import_data(format="markdown")` add a human-editable, diff-friendly alternative to the existing JSON/dict serialization: one Markdown file per memory item, with `id`, `created_at`, `updated_at`, and `type`/`kind` in required YAML frontmatter and the memory content as the Markdown body
  - Exporting without a `destination` returns a single memory as a Markdown string; exporting a set requires a destination directory and writes one stable, content-hashed filename per memory ID, so re-exporting an unchanged set is byte-for-byte idempotent
  - Importing upserts by ID: unknown IDs create new memories, known IDs replace them atomically (local state and vector store are only mutated after the whole batch validates cleanly), and unchanged re-imports are a deterministic no-op
  - Malformed frontmatter, duplicate IDs within an import batch, and duplicate YAML keys are all rejected before any memory is mutated, with actionable error messages
  - Export refuses to overwrite symbolic links and replaces files atomically; import safely compares timezone-aware and timezone-naive timestamps so retention, recency sorting, and date filters stay correct across both
  - Entities and relationships round-trip as memory-local provenance only — Markdown import intentionally does not write into `ContextGraph`, matching the MVP scope agreed on in #765
  - Documented the file contract and workflow in `docs/reference/context.md`; 43 new tests in `tests/context/test_agent_memory_markdown.py` cover round-trip losslessness, idempotency, validation errors, rollback on failure, and vector-store sync ordering

### Fixed

- **`PipelineWithProvenance` raised `ModuleNotFoundError` on import and `AttributeError` on `.run()`** (#858, closes #858) by @Karunasagar12
  - `from .pipeline import Pipeline` failed because `semantica/pipeline/pipeline.py` does not exist; corrected to `from .pipeline_builder import Pipeline`
  - `.run()` called `self._pipeline.run()` on the `Pipeline` dataclass, which has no such method; replaced with `self._engine.execute_pipeline(self._pipeline, ...)` delegating to `ExecutionEngine`
  - Constructor now accepts a built `Pipeline` instance (from `PipelineBuilder.build()`) instead of `**config`; the old `Pipeline(**config)` internal construction was invalid and never functional
  - Replaced deprecated `datetime.utcnow()` with `datetime.now(timezone.utc)` in `run()`

- **`VectorStore.search_vectors()` returned inconsistent result shapes across backend implementations** (#853, closes #845) by @Sameer6305, reviewed by @KaifAhmad1
  - Every built-in backend (FAISS, Milvus, pgvector, Pinecone, Qdrant, SQLite-vec, Weaviate, in-memory) now returns the same canonical `SearchResult` shape (`id`, `score`, `metadata`, `vector`, `distance`), instead of some backends omitting `vector`/`metadata`/`distance` or, for Weaviate, returning a backend-specific `properties` key instead of `metadata`
  - Added a `SearchResult` `TypedDict` (`semantica/vector_store/vector_store.py`, exported from `semantica.vector_store`) documenting the contract; `metadata` now always defaults to `{}` rather than being absent, and `id` accepts `Union[str, int]` to accommodate Milvus/Qdrant's native integer IDs without casting
  - **Review fix**: the score-normalization formula added for Pinecone and Qdrant (`1.0 / (1.0 + max(0.0, 1.0 - score))`) clamped every raw score `>= 1.0` to an identical `1.0`, silently collapsing result ranking whenever the raw score could exceed 1 — which happens routinely for dot-product-metric indexes (unbounded), as opposed to cosine (bounded to `[-1, 1]`). Replaced with `(score / (1 + |score|) + 1) / 2`, which is strictly monotonic and bounded in `(0, 1)` for any real input, so ranking order is preserved regardless of metric or vector normalization
  - Added `test_qdrant_unbounded_dot_product_scores_preserve_ranking` and `test_pinecone_unbounded_dotproduct_scores_preserve_ranking` (`tests/vector_store/test_search_result_schema.py`) asserting normalized scores stay strictly ordered and bounded for raw scores well above 1.0, the case the original formula silently collapsed and the existing tests (which only used scores `< 1`) never exercised
  - Left out of scope, per the original PR: Weaviate's `similarity_search()` still isn't wired into `VectorStore.search_vectors()`'s backend dispatch; Milvus's collection schema still has no metadata column so its results always return `metadata: {}`; and `include_vectors` support (populating the `vector` field) is not yet implemented for any backend

- **`DecisionEmbeddingPipeline.find_similar_decisions()` crashed with `AttributeError` for any `VectorStore` backend other than `inmemory`** (#842, closes #839) by @Sameer6305
  - `_get_candidate_embeddings()` iterated `VectorStore.vectors`/`VectorStore.metadata` directly, internal dicts only populated for `backend="inmemory"`; every persistent backend (FAISS, Pinecone, Qdrant, Milvus, ...) raised `AttributeError`. It now fetches candidates via the backend-agnostic `VectorStore.search_vectors()`, reading metadata via a `res.get("metadata") or res.get("payload")` fallback for backends that key it differently
  - Backends such as FAISS don't return the raw vector for each hit; `find_similar_decisions()` and `_find_semantic_similar()` now fall back to the search-provided score (normalized from `distance` when present) as the semantic similarity for those candidates instead of computing cosine similarity against a zero placeholder vector
  - `get_decision_statistics()` had the identical bug iterating `store.metadata.values()`; it now returns a limited stats payload with an explanatory `warning` field for backends that don't expose a full in-memory metadata dict, instead of crashing
  - **Fixed along the way**: `_get_candidate_embeddings()`'s expand-and-retry loop (which widens the search pool when post-filtering leaves too few matches) discarded every candidate it had found once the pool hit its cap (`limit * 10`) without ever collecting `limit` matches or getting a short page back from the backend — the loop fell through without executing the branch that assigns results, silently returning `[]` even when matching candidates existed. It now falls back to the last batch collected instead of dropping it
  - Added end-to-end regression tests against real `inmemory` and `faiss` backends (no mocks) plus a targeted unit test for the expand-and-retry loop's fallback behavior

- **`QdrantStore.search_vectors()` returned results keyed by `"payload"` instead of `"metadata"`** (#841, closes #840) by @divyankshah
  - `QdrantCollection.search_points()` built its result dicts as `{"id", "score", "payload"}`, while `PineconeStore.search_vectors()` and every other backend consumed by `HybridSearch` use `"metadata"`. This silently dropped Qdrant metadata from results and made `HybridSearch.filter_by_metadata()` reject every candidate whenever a filter was applied, since it looks up `result["metadata"]` and got nothing back
  - Normalized `search_points()` to return `"metadata"` instead of `"payload"`, matching the existing convention; no other module reads the old key, so the rename is a straight fix rather than a partial one
  - Extended `tests/vector_store/test_vector_store_deepdive.py::test_qdrant_store` to assert the returned key is `"metadata"` (not `"payload"`) and that `HybridSearch.filter_by_metadata()` correctly matches against Qdrant results end-to-end

- **Explorer Temporal panel never rendered after clicking the toolbar button** (#830, #836) by @Sameer6305
  - The panel stayed permanently stuck on "Loading temporal…" in `npm run dev`, with repeating "Maximum update depth exceeded" errors in the browser console. Two independent render loops were responsible:
  - **Diagnostics state churn**: `handleDiagnosticsChange` unconditionally called `setGraphDiagnosticsState` on every invocation. `buildEffectAvailability` (inside `GraphCanvas`'s diagnostics `useEffect`) always returns a new object, so each call scheduled a re-render that immediately retriggered the effect. Fixed by comparing the incoming snapshot field-by-field against the last accepted value via `lastDiagnosticsRef` before calling `setState`
  - **scrubberTime churn**: React 18 concurrent mode re-ran `TimelinePanel`'s `useEffect` with a structurally-new `Date` object for the same timestamp when speculative renders discarded `useMemo` caches, causing repeated `setScrubberTime` calls that propagated into `temporalState` churn and retriggered the diagnostics effect. Fixed by deduplicating by millisecond value via `onTimeChange`/`lastScrubberMsRef`
  - **Bonus**: `temporal-overlay`'s `shouldLoad` predicate was changed to gate strictly on `panelState["temporal-panel"]`, removing the `|| temporalState?.currentTime` branch that caused eager loading on every scrubber update and continuously cancelled in-flight `load()` completions
  - **Bonus**: `temporalState` removed from the plugin-loading `useEffect` dependency array; predicates extracted into `pluginRegistryPredicates.ts` and wired through `GraphWorkspace.tsx` so regression tests exercise the production code rather than a local copy
  - The `scrubberTime`-churn fix was also applied to the equivalent (but currently unused/unmounted) `GraphWorkspaceShell.tsx`, which shares the same `TimelinePanel` integration pattern but does not have the diagnostics-churn code path
  - **Follow-up review fix**: the diagnostics dedup's `structureLayer` comparison now also covers `disabledReason`, `curveCount`, `bridgeCurveCount`, and `backboneCurveCount` (previously only `cacheKey`/`lastDrawAt`/`enabled` were compared, so a pure `disabledReason` transition could leave the dev-only diagnostics panel stale)
  - **Follow-up review fix**: `test:graph-store`, `test:graph-workspace`, and the new `test:plugin-registry` regression test are now run in CI (`.github/workflows/ci.yml`) — previously none of the Explorer frontend's `node --test` suites executed anywhere in CI, only `npm run build`, so this fix's own regression coverage (and all prior frontend test coverage) provided no protection against silent regressions
- **`HybridSearch.search()` crashed with `AttributeError` for any `VectorStore` backend other than `inmemory`** (#833, #837) by @KaifAhmad1
  - `HybridSearch.search()` read `self.vector_store.vectors` directly, an internal dict `VectorStore` only populates for `backend="inmemory"`; every other backend (faiss, weaviate, qdrant, milvus, pinecone, pgvector, sqlite) raised `AttributeError`, making `HybridSearch` unusable against any real store. It now delegates to `VectorStore.search_vectors()` (the backend-agnostic public API) for non-inmemory backends, applies `metadata_filter` as a post-filter over the returned candidates, and normalizes results to a consistent `{id, score, distance, metadata}` shape
  - **Fixed along the way**: `vector_ids` could stay `None` when callers passed explicit `vectors`/`metadata` without `vector_ids`, crashing downstream list indexing — now defaulted to generated positional IDs
  - **Fixed along the way**: a `query_vector` passed as a plain list crashed backend stores (e.g. `FAISSStore.search_similar`) that call `.ndim` on it — now normalized to a numpy array up front
  - **Fixed along the way**: `VectorStore.store_vectors()` silently dropped metadata for FAISS (and any `add_vectors`-only backend) because it called `add_vectors(vectors, **options)` without forwarding `metadata`, even though `FAISSStore.add_vectors()` accepts it — this blocked `HybridSearch`'s metadata filtering from ever matching anything on FAISS
  - **Follow-up review fixes**: the legacy `top_k` kwarg was read but left in `options`, then forwarded via `**options` into `VectorStore.search_vectors()`, colliding with backends (sqlite, pgvector) that pass an explicit `top_k=k` to their own `search()` and raising `TypeError: got multiple values for keyword argument 'top_k'` — now popped instead of just read; `VectorStore.search_vectors()`'s dispatch only recognized backend methods named `search`/`search_similar`, so delegation still hit `NotImplementedError` for qdrant/milvus/pinecone, which name their method `search_vectors()` with a differently-named count parameter (`limit` vs `k`) — added a third dispatch branch that binds the count positionally so it works regardless of the backend's parameter name; a missing `distance` in backend-delegated results defaulted to the raw `score`, silently reusing the local path's cosine-similarity convention (`distance = 1 - score`) even for backends using unrelated metrics (L2, inner product) — now left as `None` instead of a fabricated, metric-inconsistent value
  - Verified across all 7 supported backends: `inmemory`/`faiss`/`sqlite` work live end-to-end; `pgvector`'s dispatch reaches `PgVectorStore.add()`/`.search()` (blocked only by no Postgres server in the verification sandbox); `qdrant`/`milvus`/`pinecone` now reach their real `search_vectors()` method instead of crashing, though their storage side (`store_vectors()`) still doesn't recognize `insert_vectors`/`upsert_vectors`, and `weaviate` remains entirely unwired (`add_objects`/`query_vectors`) on both sides — both are separate, pre-existing gaps independent of this fix, left for a follow-up

- **`VectorStore.store_vectors()` silently dropped metadata for FAISS (and any `add_vectors`-only) backend** (#832, #835) by @KaifAhmad1
  - `store_vectors()` fell into a branch that called `self._backend_store.add_vectors(vectors, **options)` without `metadata` whenever the backend exposed `add_vectors()` but neither `add()` nor `store_vectors()` — true for `FAISSStore`, the backend most real usage configures for genuine ANN search. Every caller that stores vectors with metadata (e.g. `AgentMemory._store_memory_vector()`, used internally by `AgentContext.store()`) lost that metadata once it reached FAISS, with no error or warning
  - Downstream, `ContextRetriever._retrieve_from_vector()` recovers a result's text via `metadata.get("content", "")`, which was always `""` for any vector stored this way; `_rank_and_merge()` then embedded that empty string, tripping `TextEmbedder.embed_text()`'s empty-text rejection and masking the real bug as a spurious `TextEmbedder` failure recorded by the progress tracker
  - `store_vectors()` now forwards `metadata` to `add_vectors()`, but only when the backend's `add_vectors()` signature actually accepts it (checked via `inspect.signature`, accepting either an explicit `metadata` parameter or a `**kwargs` catch-all), so a future/custom backend with a stricter signature raises no `TypeError`
  - **Follow-up review fix**: the `inspect.signature()` probe is wrapped in `try/except (ValueError, TypeError)`, consistent with the identical pattern already used in `ProvenanceManager.trace_lineage()`, so signature introspection failing on an unusual callable can no longer abort `store_vectors()` before it even attempts to call the backend

- **`AgnoDecisionKit.check_policy` silently treated unevaluable policy rules as compliant** (#778, #822) by @Sameer6305
  - `_eval_rule()` previously `return`ed `True` when a rule referenced a field missing from the decision payload, or when the rule string didn't match the expected `<field> <op> <value>` format — the docstring's claim that exceptions never silently return `compliant=True` didn't cover this, since neither path raised
  - Both cases now raise `ValueError` instead, which routes through `check_policy`'s existing exception handler and records a `warnings` entry (e.g. `"Could not evaluate rule 'minimum_score >= 0.9': rule references undefined field 'minimum_score'"`) instead of disappearing with no signal
  - `violations`/`compliant` are unaffected — an unevaluable rule is not counted as a violation, since it's genuinely unknown whether it would have passed; this matches the existing `compliant`/`violations`/`warnings` shape already used by `ContextGraph.enforce_decision_policy`
  - This is additive: `warnings` was already part of the return contract and populated for other exception cases, so no caller that only checks `compliant` is affected, and no existing test asserts `warnings == []` for a payload that hits either of these paths
  - **Follow-up review fix**: `check_policy` decoded `policy_rules` with `json.loads` and iterated the result without checking it was actually a list; a JSON-encoded bare string (e.g. `policy_rules='"confidence >= 0.7"'`) decodes to a `str`, so iterating it evaluated one "rule" per character — combined with the fix above, an 18-character rule string produced 17 warnings instead of being treated as the single rule it was meant to be. A decoded string is now wrapped as a single-element rule list; any other non-list shape (number, object, etc.) or non-string list element now produces exactly one `warnings` entry instead of silently misbehaving or being iterated character-by-character
  - **Follow-up review fix**: `_eval_rule` used `data.get(field) is None` to detect a missing field, which can't distinguish a genuinely absent key from a key explicitly present with a JSON `null` value — both produced the same "undefined field" warning, misdiagnosing nullable fields. Field presence is now checked with `field not in data` first; a present-but-`null` value now raises a distinct `"field {field!r} is null — cannot evaluate rule"` message instead of the misleading "undefined field" one
  - **Follow-up review fix**: `check_policy` only checked that `decision_data` was valid JSON, not that it decoded to an object. When it decoded to a list, `field not in data` silently became list-*membership* testing instead of a key check (e.g. `"confidence" not in ["confidence", 0.95]` is `False`), so a matching rule fell through to `data["confidence"]`, which raised a raw, confusing `TypeError: list indices must be integers or slices, not str` instead of any meaningful diagnostic; numbers/strings/bools produced similarly opaque `TypeError`s. `check_policy` now rejects any `decision_data` that doesn't decode to a JSON object upfront with a single clear `violations` entry, the same way it already rejects malformed JSON
  - Added 15 tests to `tests/integrations/agno/test_decision_kit.py` covering the missing-field case (the issue's traced example), the malformed-rule-string case, the bare-JSON-string `policy_rules` amplification case, non-list/non-string `policy_rules` shapes, the missing-key-vs-null-value distinction, non-object `decision_data` shapes (list/number/string/bool/null), and regression checks confirming normal rule evaluation on present fields is unchanged

- **No cycle detection for SKOS concepts at write time** (#774, #819) by @mikemikimike, reviewed by @Sameer6305 and @KaifAhmad1
  - Added cycle detection (`validate_skos_hierarchy`) for `skos:broader` and `skos:narrower` relationships in `ContextGraph.add_edge()` and `ContextGraph.add_edges()`, preventing direct 2-node cycles, self-loops, and multi-hop hierarchy cycles
  - Added `GraphSession.add_nodes_and_edges()` to validate SKOS hierarchy edges upfront under lock before node insertion, preventing partial-write leaks where nodes remain after a cyclic edge is rejected
  - Updated vocabulary, ontology (`/api/ontology/load`, `/api/ontology/create`), and JSON/CSV import routes to use `add_nodes_and_edges()` and return HTTP 422 with actionable error messages when a cycle is detected
  - Follow-up fix by @KaifAhmad1: `validate_skos_hierarchy()` previously re-walked *every* SKOS hierarchy edge already in the graph on each write, so one pre-existing cycle anywhere (e.g. legacy data) blocked all unrelated future writes; it now only traverses concepts touched by the edges being written, while still checking against existing edges for cycles that span old and new data
  - Follow-up fix by @KaifAhmad1: in `/api/ontology/load`, `except HTTPException: raise` was unreachable because a broader `except Exception` clause above it already matched `HTTPException`, so a 422 raised after a successful `OntologyIngestor` parse was silently swallowed and reprocessed via the fallback RDF parser; reordered the clauses so the deliberate 422 always propagates
  - Follow-up fix (#775): `/api/ontology/{uri}/refresh` was missed by the original sweep and still called `session.add_nodes()` then `session.add_edges()` as two independent operations, so a cyclic SKOS edge rejected by `add_edges()` left the nodes from the preceding `add_nodes()` call committed to the graph; switched to `session.add_nodes_and_edges()` with the same `except ValueError` → HTTP 422 handling already used by `/api/ontology/load` and `/api/ontology/create`. Audited every other `add_nodes()`/`add_edges()` pairing in the repo (`GraphStore`, `graph_builder.py`, `agent_memory.py`, `context_graph.py.load()`, `enrich.py`) — none share `GraphSession`'s SKOS-cycle-validation write path, so none were changed

- **Agno `_AgentScopedStore.upsert_memory` silently swallowed decision recording failures** (#779)
  - `upsert_memory()` now logs `logger.warning("[%s] record_decision failed: %s", self._role, exc, exc_info=True)` when `record_decision()` fails, matching the error-logging convention used for `store()` in the same method with traceback context preserved
  - Preserves graceful fallback behavior: `record_decision()` remains optional and `upsert_memory()` continues without propagating the exception
  - Added regression coverage in `tests/integrations/agno/test_shared_context.py` for both `store()` and `record_decision()` warning paths

- **`AgnoDecisionKit`/`AgnoKGToolkit` silently swallowed Agno tool registration failures** (#780, #818) by @Sameer6305 and @KaifAhmad1
  - Removed the `try/except: pass` wrapped around `self.register(fn)` in both toolkits' `__init__`; when Agno is installed, a registration failure now propagates immediately instead of leaving the toolkit half-registered with no signal to the caller
  - Graceful degradation when Agno isn't installed (`AGNO_AVAILABLE=False`) is unchanged — `_tools` is still populated so callers can introspect available tools without the package
  - Fixed a related duplicate-entry bug: `self._tools` was appended to unconditionally *before* `register()` ran, which could double-count a tool when Agno's own `Toolkit.register()` also tracks it in `self._tools`
  - This is a behavior change for callers that construct these toolkits expecting instantiation to always succeed — audited: no in-repo call site relies on the old silent-failure behavior
  - Expanded `tests/integrations/agno/test_decision_kit.py` and `test_kg_toolkit.py` with coverage for registration invocation counts, failure propagation, graceful degradation, and no-duplicate-`_tools` assertions

- **`ProvenanceManager` tracking methods silently swallowed failures without logging and returned fabricated entries** (#783)
  - `track_relationship()`, `track_chunk()`, and `track_property_source()` now return `Optional[ProvenanceEntry]` (`None` on storage failure, consistent with #782's `track_entity` fix) instead of a fabricated populated object
  - `_save_entry()` now always logs on any storage failure, including previously-silent per-item batch failures
  - `track_entities_batch()` and `track_chunks_batch()`'s rare block-level transaction failures are now logged too
  - `source_tracker.py`'s `track_sources_batch()` no longer counts failed tracking calls in its stats

- **MCP `handle_get_causal_chain` returned an empty-but-valid-looking response when both `CausalChainAnalyzer` and the graph fallback were unavailable** (#781, #817) by @Sameer6305 and @KaifAhmad1
  - Returns an explicit `{"error": "Causal chain analysis is not supported on this graph backend", "chain": []}` instead of `{"chain": [], "count": 0, "direction": ...}`, letting clients distinguish "unsupported" from a legitimately empty chain
  - The fallback path now introspects `graph.get_causal_chain`'s signature to forward `direction`/`max_depth` (or a `depth` kwarg, or nothing, depending on what the backend accepts) instead of always calling with just `decision_id`, matching the primary analyzer path's behavior
  - Hardened input handling: non-dict `args`, non-string `decision_id` (previously a latent `AttributeError` on `.strip()`), and `max_depth` clamped to `(0, 100]` with a safe default on invalid input
  - Added `tests/test_mcp_decisions_causal_chain.py` (11 tests) covering the unsupported-backend, fallback-forwarding, and validation/exception paths across multiple backend signature shapes
  - **Follow-up review fix**: the signature-detection try/except previously caught the *actual call*'s exceptions in the same block used for introspection failures, so a genuine bug inside a backend's `get_causal_chain` (raising an unrelated `TypeError`) was misread as a signature mismatch and the backend was invoked a second time with identical arguments before the real error surfaced. Signature introspection and the resulting call are now split into separate try/excepts so a successfully-introspected call is made exactly once; added `test_internal_typeerror_calls_backend_only_once` to lock this in

- **`ProvenanceManager.track_entity` persisted partial history and returned fabricated entries on storage failure** (#782, #816) by @Sameer6305 and @KaifAhmad1
  - `track_entity()`'s two-step write (history archive + primary update) is now atomic — if either write fails, the whole operation rolls back via the existing #807 `transaction()` mechanism, instead of silently persisting a partial state
  - `track_entity()`'s return type is now `Optional[ProvenanceEntry]`: on failure it returns a safe deep copy of the pre-failure existing entry (if one existed) or `None` (if this was a brand-new, never-successfully-tracked entity) — never a fabricated object claiming values that were never actually persisted
  - This is a behavior change for callers that inspect the return value without checking for `None` first — audited: 0 of 47 production call sites in the repo currently dereference the return value, so this is safe today, but any NEW caller must handle `None`
  - `InMemoryStorage` gained real transactional rollback (staging-buffer based) to match this guarantee — previously `transaction()` was a no-op

- **`ProvenanceManager` duplicated the same checksum/persist/exception-swallow block across 4 tracking methods** (#784, #815) by @Sameer6305 and @KaifAhmad1
  - Consolidated the repeated `entry.checksum = compute_checksum(entry)` / `try: self.storage.store(entry) except Exception: pass` block used by `track_entity`, `track_relationship`, `track_chunk`, and `track_property_source` into a single `ProvenanceManager._save_entry()` helper, preserving the existing graceful-failure behavior and the batch `_conn`/re-raise semantics from #807
  - Added 4 regression tests (`tests/provenance/test_manager.py`) covering storage-failure swallowing for each of the four tracking methods, none of which had coverage for this path before
  - **Follow-up review fix**: the initial refactor of `track_entity`'s exception fallback (the branch that runs when a failure happens *before* the entry is built, e.g. a retrieve error inside the atomic transaction) routed through `_save_entry()`, which made a new `self.storage.store(entry)` call outside the already-failed transaction — a real behavioral change from the original code (which only computed a checksum on that path) that could have reintroduced the exact race #807's `BEGIN IMMEDIATE` transaction serialization was meant to prevent. Reverted that branch to only compute the checksum, and added `test_track_entity_pre_build_failure_fallback_skips_store` asserting `storage.store` is never called on that path

- **`SQLiteStorage` and `ProvenanceManager` connection churn, non-atomic writes, and batch tracking overhead** (#807) by @Sameer6305
  - Scoped a single SQLite connection to the full duration of each public storage method call (`track_entity()`, `store()`, `retrieve_all()`, `clear()`) instead of opening independent connections per internal SQL statement, reducing connection churn by ~67% while closing the handle before the public method returns to preserve Windows filesystem unlink safety
  - Implemented the `SQLiteStorage.transaction()` context manager with Write-Ahead Logging (`PRAGMA journal_mode=WAL`), `busy_timeout=5000`, `synchronous=NORMAL`, and immediate write transactions (`BEGIN IMMEDIATE`), ensuring concurrent read-modify-write sequences (including history version ID generation) are serialized without lock contention or data loss
  - Added block-level transaction sharing to `track_entities_batch()` and `track_chunks_batch()`, reducing SQLite commit overhead by ~99.9% for large batches and deferring `tracked_count` increments until successful commit so rolled-back items are never reported as successes
  - Preserved 100% backward compatibility for custom storage backends overriding `trace_lineage(self, entity_id)` by inspecting signatures dynamically before passing `max_depth`, and optimized BFS lineage queries with batched IN-clause lookups per frontier level
  - **Follow-up fix**: `retrieve()` and `trace_lineage()` were initially routed through `transaction()` too, so plain reads took the same `BEGIN IMMEDIATE` writer lock as read-modify-write calls, serializing every read behind every other read/write and defeating the WAL concurrency this PR was meant to add. They now use a dedicated `_read_connection()` (configured, no explicit `BEGIN`) so reads no longer contend for the writer lock
  - **Follow-up fix**: `track_entity()`/`track_chunk()` caught all internal storage exceptions unconditionally, so when called from `track_entities_batch()`/`track_chunks_batch()`'s shared per-block transaction, a single item's storage failure (e.g. non-JSON-serializable metadata) was swallowed inside the call and never surfaced to the batch loop's per-item `except`, inflating `tracked_count` for entries that were never persisted. Both methods now re-raise when invoked with a shared `_conn` (batch context) while still degrading gracefully on standalone calls, so batch counts match what's actually committed
  - Added 8 dedicated regression tests in `tests/provenance/test_sqlite_storage_performance_807.py` covering PRAGMA configuration, Windows unlink safety, batch transaction sharing, BFS `max_depth`, rollback count accuracy, custom storage backward compatibility, concurrent read-modify-write serialization, and connection cleanup guards on configuration error

- **Closed remaining `ProvenanceManager` storage-failure test-coverage gaps identified by a #785 audit** (#785)
  - An audit of `tests/provenance/` (filed against a claim that zero tests exercised `storage.store()` failures) found #782/#783/#784/#807 had already closed most of the gap, but two residual surfaces had no test: `track_relationship()`, `track_chunk()`, and `track_property_source()`'s storage-failure-swallowing contract (returns `None`, logs, persists nothing) was only verified against `InMemoryStorage`, never `SQLiteStorage`; and `track_chunks_batch()` had no test for per-item `_save_entry` failure logging or for the block-level transaction-failure log message, even though `track_entities_batch()` had both
  - No production code changed — #782/#783/#784/#807 already implemented the correct behavior; this closes the coverage gap proving it holds on both backends
  - Added `test_track_relationship_storage_error_swallowed_sqlite`, `test_track_chunk_storage_error_swallowed_sqlite`, `test_track_property_source_storage_error_swallowed_sqlite`, `test_chunks_batch_logs_per_item_failure_memory`, and `test_track_chunks_batch_block_level_transaction_failure_logs` to `tests/provenance/test_manager.py`
  - Read-path failure coverage (`get_lineage()`/`trace_lineage()`/`get_provenance()`/`clear()` propagating a raised storage exception) remains untested and is a candidate for a follow-up issue, since none of those methods currently wrap the underlying storage call in a try/except

- **Explorer's Provenance UI used a naive 2-hop graph traversal instead of the audit-grade `ProvenanceManager` backend** (#792, #809) by @Sameer6305
  - `semantica/explorer/routes/provenance.py` never imported or called `ProvenanceManager` (`semantica/provenance/manager.py`); `/api/provenance` and `/api/provenance/report` built their lineage response entirely from a naive 2-hop networkx traversal over the live graph instead of querying the SQLite-backed, checksummed audit log. Both endpoints now query `session.provenance_manager.get_lineage(node_id)` first, and a new `_transform_audit_lineage()` maps the W3C PROV-O entries into the exact `{"nodes": [...], "edges": [...]}` shape `LineageDiagram.tsx` already expects — no frontend changes required
  - Falls back to the original 2-hop traversal, never a 500: no audit records for a node, a `ProvenanceManager` storage failure (corrupted DB, permissions), or a failed SHA-256 integrity check on any entry in the lineage chain all degrade cleanly to the naive path. A new `source: "audit" | "graph_traversal"` field on the response discloses which path actually served the data
  - `ProvenanceManager.get_lineage()` now returns `integrity_verified`, computed by re-verifying every entry's checksum before it's trusted; a single tampered or corrupted entry anywhere in the lineage chain now falls the *entire* response back to graph traversal rather than serving partially-verified audit data
  - Replaced an initial classmethod-based `ProvenanceManager.set_default_storage_path()` approach (caught in review before merge — it would have let any two sessions/apps in the same process silently share and overwrite each other's storage path, including across unrelated test runs) with `provenance_storage_path` threaded through `GraphSession.__init__` and `create_app(...)`, so each session's `ProvenanceManager` is independently scoped
  - Disclosed limitation: `ProvenanceManager.trace_lineage()`/`get_lineage()` only walk `parent_entity_id`/`used_entities` backward, so the audit path currently surfaces upstream lineage only — the naive fallback remains the only source for downstream/descendant relationships until `ProvenanceManager` gains a reverse lookup
  - New `tests/explorer/test_provenance_manager_wiring.py` (8 tests): the audit path via a real multi-hop `track_entity()` chain, empty-record fallback, simulated storage-failure degradation (asserts `200`, not `500`), checksum-tamper fallback, evidence-field preservation, `create_app()` storage-path wiring, and cross-session storage isolation, confirmed order-invariant across `tests/explorer/` and `tests/provenance/` in both execution orders

- **`POST /shacl/validate` and the `/health` SHACL dimension never ran live SHACL validation** (#772, #804) by @Sameer6305 and @KaifAhmad1
  - `/shacl/validate` had no data graph to validate submitted shapes against — only a Turtle syntax check. Added `_data_graph_turtle_for_uri()`, which serializes the loaded ontology's nodes/edges into an RDF/Turtle instance graph (CURIE resolution across owl/rdfs/skos/dct/dc, arbitrary node-property projection, typed individuals) and wires both `/shacl/validate` and the `/health` SHACL dimension to `OntologyEngine.validate_graph()` via pySHACL, returning real `conforms`/violations instead of a hardcoded `status="unavailable"` stub
  - Fixed a cross-ontology namespace leak in `_node_belongs_to_ontology`: its prefix fallback (`_extract_namespace()`) split only on the last `/`, so sibling ontologies sharing a domain (e.g. `.../onto-a` and `.../onto-b`) could match entities across ontologies that shouldn't be related; fixed by comparing against the full URI stem via the new `_ontology_namespace()` helper
  - Added resource guardrails to `/shacl/validate` to close a DoS risk flagged in review: a submitted-Turtle byte cap (`SEMANTICA_MAX_SHACL_TURTLE_BYTES`, default 256 KB), a parsed-triple cap (`SEMANTICA_MAX_SHACL_TRIPLES`, default 1,000), a validation timeout (`SEMANTICA_MAX_SHACL_TIMEOUT`, default 15s), and a global concurrency semaphore (`SEMANTICA_MAX_SHACL_CONCURRENCY`, default 4)
  - Fixed `HealthDimension.status` being set to `"error"` on a real (non-`ImportError`) validation exception, which isn't a valid value on that model — Pydantic construction raised and turned the whole `/health` endpoint into a 422 on any real bug; now reports `status="critical"` (already a valid value) with a regression test forcing this exact path
  - Follow-up review fixes: reverted an unrelated regression that had crept into this PR — `POST /api/ontology/create` had gone back to silently swallowing `OntologyEngine.from_data`/`from_text` failures into a near-empty "minimal" ontology instead of raising `HTTPException(500)`, undoing the earlier #770/#787 fix for the same endpoint (and breaking `TestOntologyCreateFailures`, which wasn't run before this PR's initial merge request); `sh:Warning`/`sh:Info`-severity pySHACL results were silently dropped from the `/shacl/validate` response — a shape using non-`Violation` severities could report `conforms=False` with an empty `violations` list and no explanation, so warnings/infos are now folded into the response's `violations` array; and `/health` was independently re-fetching and re-truncation-checking the same ontology's nodes/edges once for the generated SHACL shapes and once for the data graph — both now share a single fetch via `_fetch_analysis_graph()`
  - New regression tests: `TestOntologyCreateFailures` (pre-existing, now passing again), `test_shacl_validate_surfaces_warning_severity_results`, `test_health_dedupes_node_edge_fetch`, plus the existing 26-test `tests/explorer/test_ontology_subissue3.py` suite (28/28 passing) and the pre-existing `tests/ontology/` suite (83/83 passing)

- **Neptune cookbook CloudFormation stack exposed the database port to the entire internet and had no network audit trail** ([code scanning alert #28](https://github.com/semantica-agi/semantica/security/code-scanning/28), [#26](https://github.com/semantica-agi/semantica/security/code-scanning/26), [#27](https://github.com/semantica-agi/semantica/security/code-scanning/27), `AC_AWS_0276`/`AC_AWS_0369`/`AC_AWS_0148`) by @KaifAhmad1
  - `cookbook/introduction/neptune-setup.yaml`'s security group let anyone on `0.0.0.0/0` reach the Neptune Bolt/OpenCypher port (8182); it now requires a `ClientCidr` parameter (CIDR-validated, no default) so the stack can't be created without the deployer explicitly scoping access to their own IP or VPN/office range
  - Added `AWS::EC2::FlowLog` plus a dedicated CloudWatch Logs group and IAM role so all traffic in the stack's VPC is now logged
  - Left the account-wide IAM password policy check (`AC_AWS_0148`) unimplemented as a stack resource on purpose: `AWS::IAM::AccountPasswordPolicy` is an account singleton, and wiring it into a disposable per-learner tutorial stack would mean creating or deleting this stack also mutates or removes the account's real password policy — suppressed with a documented `ts:skip=AC_AWS_0148` explaining why, rather than "fixed"
  - Updated `21_Amazon_Neptune_Store.ipynb`'s `aws cloudformation create-stack` instructions, prerequisites, and cost table to match the new required `ClientCidr` parameter and flow-log line item

- **Follow-up to the knowledge-explorer Helm chart default-namespace/seccomp scanner findings reopening** ([code scanning alert #846](https://github.com/semantica-agi/semantica/security/code-scanning/846), [#847](https://github.com/semantica-agi/semantica/security/code-scanning/847), [#848](https://github.com/semantica-agi/semantica/security/code-scanning/848), [#68](https://github.com/semantica-agi/semantica/security/code-scanning/68), [#63](https://github.com/semantica-agi/semantica/security/code-scanning/63), `CKV_K8S_21`/`AC_K8S_0086`/`AC_K8S_0080`) by @KaifAhmad1
  - The `checkov.io/skip1` metadata annotation added previously (see the `CKV_K8S_21` entry below) evidently isn't being honored by the Microsoft Defender for DevOps scan — the same finding reopened under new alert numbers on the current `main`. Added the more standard `# checkov:skip=CKV_K8S_21` and `# ts:skip=AC_K8S_0086` inline comments at the top of `templates/deployment.yaml`, `templates/service.yaml`, and `templates/configmap.yaml` as a second suppression path (matching the convention already used in `deploy/gcp/cloudrun-service.yaml`), plus `# ts:skip=AC_K8S_0080` on `templates/deployment.yaml` for the seccomp finding, which trips for the same root cause: terrascan's static template scan never resolves `{{ toYaml .Values.podSecurityContext }}`, even though `values.yaml` sets `seccompProfile.type: RuntimeDefault` correctly
  - Confirmed the `deploy/kubernetes/*` (non-Helm) manifests already had TLS and seccomp configured correctly, so no code change was needed there for the corresponding alerts (#61 and the non-Helm seccomp finding) — expected to close on the next scan
  - Documented both suppression mechanisms and the reasoning in `.checkov.yaml`
  - Residual risk: this environment could not run checkov/terrascan locally to confirm the inline comments are actually honored during a Helm-rendered scan; if the alerts are still open after the next scan, the reliable fallback is splitting the CI checkov/terrascan invocation so `deploy/helm/` is scanned with these specific checks excluded via `--skip-check` instead of relying on in-file suppression

- **`react-hooks/set-state-in-effect` cascading renders across 12 Explorer workspace files** (#769, #796) by @Sameer6305 and @KaifAhmad1
  - Replaced synchronous `setState` calls inside `useEffect` bodies with React's recommended "adjust state during render" pattern (`if (x !== prevX) { setPrevX(x); ...setState... }`) across `OntologyWorkspace`, `ManageWorkspace`, `LineageWorkspace`, and `GraphWorkspace`, and inlined async data-fetching effects with `ignore` flags to prevent race conditions and stale writes after unmount
  - Fixed a regression the inlining itself introduced: `AlignmentsTab.tsx`, `KGOverviewTab.tsx`, `OntologyManager.tsx`, and `VersionsTab.tsx` each duplicated their existing fetch callback (`reload` / `fetchOverview` / `fetchRegistry` / `loadVersions`+`loadProposals`) into a second, inline copy for the mount effect, and the copy silently dropped the `setError`/`flashMsg` calls the original had — re-introducing, on the very first page load, the exact error-swallowing behavior that #767/#790 had already fixed for these same files. The inline copies now mirror the original's error handling (including `207` partial-success messages) exactly
  - Fixed `LineageDiagram.tsx` only clearing the previously-rendered nodes/edges when the new `activeId` was falsy instead of on every id change, so switching directly between two lineage views briefly kept showing the *previous* view's stale diagram instead of clearing before the new fetch resolved
  - `GraphWorkspace.tsx` and `GraphLoadingOverlay.tsx` still have unrelated `react-hooks/set-state-in-effect` violations outside this PR's 12-file scope (confirmed via `npx eslint .`); left as follow-up work rather than expanding this PR further

- **Checkov flagged the knowledge-explorer Helm chart for using the default Kubernetes namespace** ([code scanning alert #779](https://github.com/semantica-agi/semantica/security/code-scanning/779), [#778](https://github.com/semantica-agi/semantica/security/code-scanning/778), [#777](https://github.com/semantica-agi/semantica/security/code-scanning/777), `CKV_K8S_21`) by @KaifAhmad1
  - `templates/service.yaml`, `templates/deployment.yaml`, and `templates/configmap.yaml` all already set `metadata.namespace` to `{{ .Release.Namespace }}`, which is only bound at `helm install`/`helm template` time; Checkov's helm framework renders the chart without a namespace override, so it always resolves to `default` and trips `CKV_K8S_21` even though the chart is namespace-agnostic by design
  - Added a `checkov.io/skip1: CKV_K8S_21` metadata annotation to each of the three files to suppress the scanner artifact false-positive properly in Helm templates, and documented the reasoning in `.checkov.yaml`

- **No React error boundaries around lazy-loaded Explorer workspaces — a single render error crashed the whole app** (#768, #794) by @Sameer6305
  - Added an `ErrorBoundary` class component (`explorer/src/ErrorBoundary.tsx`) and wrapped each lazy-loaded workspace's `<Suspense>` block in `App.tsx` with it, keyed on the active sub-view so navigating away from and back to a crashed tab remounts it cleanly
  - Failed retries are capped at 3 before the fallback UI switches from "Try Again" to a "Reload Application" dead-end, preventing infinite retry loops on deterministic crashes; raw error/stack details are logged via `console.error` only and never rendered into the fallback UI
  - Fixed the retry counter so it resets after a retry actually succeeds and stays error-free for a few seconds, instead of never resetting (which could permanently exhaust the retry budget on unrelated, individually-recoverable transient errors) or resetting on the very next commit (which could fire prematurely while `Suspense` was still showing its fallback)

- **Explorer frontend workspaces silently swallowed network/server errors** (#767, #790) by @Sameer6305
  - `ShaclStudio.tsx`, `VersionsTab.tsx`, `SKOSVocabularyManager.tsx`, `EntityResolutionTab.tsx`, `LineageDiagram.tsx`, `DecisionWorkspace.tsx`, `KGOverviewTab.tsx`, `OntologyManager.tsx`, `OntologySearch.tsx`, `ReasoningWorkspace.tsx`, and `SparqlWorkspace.tsx` now render a visible error banner instead of only `console.error()`-ing failed fetches
  - Added explicit `response.status === 207` (Multi-Status) handling across these workspaces so partial backend failures surface a warning instead of reading as a full success (`response.ok` is `true` for all 2xx codes, including 207)
  - Added defensive JSON parsing so an unexpected non-JSON (e.g. HTML 500) response body no longer crashes the app with `SyntaxError: Unexpected token < in JSON`
  - Fixed `KGOverviewTab.tsx` dropping the `/api/graph/nodes` partial-success warning whenever `/api/graph/stats` also returned 207 — both warnings are now shown (appended) instead of one being silently discarded
  - Fixed `HealthTab.tsx`'s registry load still using a bare `.catch(() => {})` that swallowed errors identically to the pattern fixed elsewhere in this same folder; failures now populate the existing error banner
  - Fixed `AlignmentsTab.tsx`'s `reload()` using `Promise.allSettled` but never handling the `"rejected"` branches for the registry/alignments fetches, so both failures previously vanished with no error surfaced and no logging

- **`tests/explorer/test_explorer_api.py` failed with `TypeError: Client.__init__() got an unexpected keyword argument 'app'` on current httpx** (#788, #789) by @Sameer6305
  - `httpx>=0.28.0` removed the `app=` kwarg that Starlette's `TestClient` relies on to wrap a FastAPI app for testing; `httpx` wasn't pinned anywhere in `pyproject.toml`, so different environments could independently resolve an incompatible transitive version and hit the same break
  - Added an explicit `httpx<0.28.0` constraint to the main `[project.dependencies]` array (not just a dev extra), so it applies globally across production, dev, and CI installs
  - Without the pin, the full test suite fails to even complete collection (fails immediately on `tests/explorer/test_vocabulary.py` with the same `TestClient` error); with it, `tests/explorer/test_explorer_api.py` goes from 7 failed/12 passed/58 errors to 77 passed, 0 errors

- **Explorer backend routes returned HTTP 200 with error/empty bodies on failure, defeating frontend error handling** (#770, #787) by @Sameer6305 and @KaifAhmad1
  - `GET /api/temporal/patterns` now raises `HTTPException(500)` on a genuine computation failure instead of silently returning an empty-but-valid `TemporalPatternResponse`; the `ImportError` fallback (optional `kg` extra not installed) is unchanged and still degrades gracefully to an empty list
  - `POST /api/ontology/create` now raises `HTTPException(500)` when ontology generation fails in either the `sample_data` or `schema_text` mode, instead of silently falling back to a partial/minimal ontology with a misleading `nodes_added` count
  - `GET /api/analytics` sets `response.status_code = 207` (Multi-Status) when some, but not all, of the requested metrics fail, and raises `HTTPException(500)` when every requested metric fails — a plain 2xx (including 207) reads as success to callers that only check `response.ok`, so an all-failed request now surfaces as a hard error rather than a body full of `{"error": ...}`
  - Added regression tests covering all three failure paths (`test_patterns_failure_returns_500`, `test_analytics_partial_failure_returns_207`, `test_analytics_total_failure_returns_500`, and two `TestOntologyCreateFailures` cases)

### Security

- **DNS check-then-use hardening for the ontology URL fetcher, and a remaining object-IRI validation gap** (#916, follow-up to GHSA-8c7v-62gr-hj6g and GHSA-8vgg-8mr4-r236) by @KaifAhmad1
  - **DNS check-then-use (TOCTOU) window**: GHSA-8c7v-62gr-hj6g's own fix description flagged this as a secondary gap — `_validate_fetch_url()` resolved and validated a hostname once, but `_fetch_url_sync()` then let `requests` resolve the same hostname again independently at connect time. A low-TTL or rebinding DNS answer could differ between the two lookups, reopening the SSRF window the validation exists to close
  - `_validate_fetch_url()` now returns the validated IP, and a new `_make_pinned_session()` builds a per-hop `requests.Session` whose connection pool is pinned directly to that IP — bypassing DNS resolution for the connection entirely — while explicitly restoring the real hostname as the outgoing HTTP `Host` header and, for HTTPS, the TLS SNI `server_hostname`/`assert_hostname`, so the connection reaches the validated IP but still presents (and is verified against) the real hostname's identity, keeping virtual hosting and certificate validation correct
  - Caught during implementation: an earlier draft set urllib3's `_dns_host` post-construction, assuming (as in some urllib3 releases) that it was decoupled from `host`. In the version this project installs (2.7.0), `host` is a property that reads/writes `_dns_host` directly, so that approach would have silently changed the Host header too — caught by an end-to-end test against a real local server before landing, rather than shipping. Verified with real (non-mocked) local HTTP and HTTPS servers, the latter using a generated self-signed certificate to prove SNI/cert-hostname verification checks the real hostname rather than the pinned IP, plus a negative control confirming a hostname/cert mismatch is still correctly rejected, not silently bypassed
  - **Object-IRI validation gap** (GHSA-8vgg-8mr4-r236 follow-up, distinct from the object-branch fix already shipped in #911): a triplet object already wrapped in `<...>` skipped `sparql_escaping.validate_uri()` in both `blazegraph_store.py` and `rdf4j_store.py`'s `_format_object_for_sparql`/`_format_object_for_ntriples`, only checking the inner content for a literal space or `>` — the pre-wrapped and unwrapped branches now validate identically
  - **Fixed along the way** (caught in automated review across two follow-up rounds): `_validate_fetch_url()` originally pinned to only the first resolved IP, so a hostname with multiple A/AAAA records would fail outright if that specific address was unreachable — it now returns every validated IP and `_make_pinned_session()` falls back through all of them, verified by pinning to a genuinely unreachable address followed by a working one and confirming the fetch still succeeds; the test HTTPS server allowed TLSv1/TLSv1.1 by not setting a minimum version, now pinned to TLSv1.2; and when an HTTP(S) proxy applied, pinning was silently skipped in favor of the unpinned path — proxies are now disabled outright for this fetcher (`session.trust_env = False`, so `HTTP_PROXY`/`HTTPS_PROXY` env vars are never consulted) with a fail-closed 502 backstop if a proxy is ever forced onto the session some other way, verified by pointing `HTTP_PROXY` at an address that would fail if actually used and confirming the fetch still succeeds directly
  - New `tests/explorer/test_ontology_dns_pinning.py` (12 tests: real local HTTP/HTTPS servers including 2 real-TLS checks, multi-IP fallback success/failure, and no-proxy-trust verification — gracefully skipped without the optional `cryptography` package where applicable); updated `tests/explorer/test_ontology_ssrf.py` for the new per-hop session construction; 4 new tests in `tests/triplet_store/test_sparql_injection.py` for the object-IRI fix. Full `explorer` + `triplet_store` suite: 572 passed

- **Missing Origin validation on the `/ws/graph-updates` WebSocket handshake** (#917, GHSA-4643-wpgq-w329) by @KaifAhmad1
  - `CORSMiddleware` doesn't cover WebSocket handshakes at all (Starlette's CORS support only wraps HTTP), so under `SEMANTICA_ALLOW_ANONYMOUS=true` — the mode `docker-compose.dev.yml` ships — the anonymous-mode key bypass accepted a `/ws/graph-updates` connection from any origin. Loopback binding isn't a boundary against a browser: any page the operator has open can still reach `ws://localhost:8000/ws/graph-updates` directly, and `ConnectionManager.broadcast` sends every `graph_mutation` to every connected socket with no per-connection scoping. Combined with `/api/import` accepting `multipart/form-data` (a CORS-safelisted content type that skips preflight), a hostile page could write to the graph over REST and read the result back over the unauthenticated WebSocket
  - Not affected: any deployment with `SEMANTICA_API_KEY` configured — the handshake already rejects without a valid key in that mode. This was an anonymous-mode-only, development-configuration exposure
  - Fix: check the handshake's `Origin` header against `app.state.explorer_settings['allowed_origins']` — the same list `CORSMiddleware` already enforces for HTTP — before the key check. A missing `Origin` (native/CLI clients, which never set the header) is still allowed through, since the browser is the only threat this closes
  - 4 new tests in `tests/explorer/test_explorer_auth.py`: hostile Origin rejected under anonymous mode; hostile Origin rejected even with a correct key (Origin is checked first, so a leaked key alone can't hijack the socket); an allowlisted Origin still connects; a missing Origin still connects. Full `explorer` suite: 226 passed

- **Polynomial-time ReDoS in the SPARQL route's `_PREFIX_DECL` regex** (#915, CodeQL `py/polynomial-redos`) by @Sameer6305
  - The prior pattern's trailing `\s*` overlapped with the preceding `<[^>]*>` IRI-body match on inputs containing no closing `>` (e.g. `base<` followed by thousands of `!<` repetitions), forcing the regex engine to explore every possible split between the two quantifiers — O(n²) backtracking reachable from `req.query` via `_is_read_only_query()`
  - Fixed by making the two quantifiers character-disjoint: horizontal whitespace only (`[ \t]`, never overlapping the IRI body) instead of `\s*`, and excluding CR/LF from the IRI body (`[^>\r\n]*`) so it can never span a line boundary. Independently verified: the exact pathological payload (`base<` + `!<` × 5,000/20,000) scales linearly (0.238ms → 0.841ms for 4x input, not the ~16x a surviving quadratic blowup would show)
  - Added `_SPARQL_MAX_QUERY_LEN = 10_000` as defense-in-depth, checked in `execute_sparql()` before any regex work so a future pattern regression stays bounded regardless
  - Two correctness regressions raised in review were checked and did not reproduce: comment-then-prefix stripping order means an inline comment after a `PREFIX` line (`PREFIX ex: <...> # comment`) is already gone by the time `_PREFIX_DECL` runs, verified directly against the pipeline; and the allowlist's `.sub()`-based cleaning only ever affects the yes/no decision, never the query actually sent to `graph.query()` — so even the narrow case of a multi-line string literal that happens to start a line with the literal text `PREFIX` or `BASE` can only cause a legitimate query to be wrongly rejected, never let something malicious through, since rdflib's parser still gates whatever actually executes
  - 20 new/updated tests in `tests/explorer/test_sparql_route.py` and `tests/test_security_regression.py` (inline prologues, CRLF line endings, multi-line CRLF prefix chains, oversized-query rejection). 225 `explorer` + 82 SPARQL-specific tests passing

- **SPARQL injection via unvalidated triplet IRIs** (#911, GHSA-8vgg-8mr4-r236) by @KaifAhmad1
  - `Triplet.subject`/`.predicate` (and, in some builders, `.object`) were interpolated directly into SPARQL update/query strings in the Blazegraph and RDF4J stores, and into a SELECT filter in the Jena store. A subject containing `>` closes the `<...>` IRI token early, so the rest of the value is parsed as more SPARQL. Entity names are document text in the normal ingest pipeline, so anyone whose content gets processed could append operations like `CLEAR ALL`, running with the application's store credentials
  - Applied the existing `sparql_escaping.validate_uri` (already used by `anzo_store.py`, the one backend that was already hardened — this generalizes its approach rather than inventing a new one) at every subject/predicate/object interpolation site: `blazegraph_store.py`'s `_build_insert_data`, `_triplets_to_rdf`, `bulk_load`'s `graph` option, `get_triplets`'s filter, and `delete_triplet`; `rdf4j_store.py`'s `_triplets_to_ntriples`, `get_triplets`'s filter, and `delete_triplet`; `jena_store.py`'s `get_triplets`'s filter (the only vulnerable site there — `add_triplets`/`delete_triplet` already use rdflib's native `Graph.add`/`.remove` with `URIRef` rather than building query strings)
  - **Fixed along the way** (caught in review, by @ZohaibHassan16): `_format_object_for_sparql`'s URI branch — used when a triplet's *object* is itself a URI rather than a literal — only checked for spaces and `>` inline instead of running the same `validate_uri` check applied to subject/predicate, leaving the object position as a narrower but real gap in both Blazegraph and RDF4J. Also fixed test flakiness in `RDF4JStore`'s test fixtures, which weren't mocking `_connect()` and so were making real network calls
  - New `tests/triplet_store/test_sparql_injection.py` (12+ tests) reproducing the advisory's own injection payload (`http://example.com/a> ... ; CLEAR ALL ; INSERT DATA { ...`) against all three backends' write and read paths, asserting the malicious query is never built or sent. Full triplet_store suite: 330+ tests passing
  - Side note, not part of this fix: found that `jena_store.py`'s `get_triplets()` builds syntactically invalid SPARQL for its WHERE-clause filters (missing a `FILTER()`/separator before the equality conditions) — a pre-existing correctness bug, unrelated to the injection fix, left alone here and worth a separate follow-up

- **Cypher injection via unvalidated node labels, relationship types, and property keys** (#910, GHSA-482h-hw99-h62p) by @KaifAhmad1
  - Node labels and property keys passed to `create_node`/`create_relationship` were interpolated directly into Cypher strings in the Neptune, Neo4j, and FalkorDB graph stores. Property *values* are parameterized, but labels and keys can't be bound as query parameters, and nothing validated them — so a document-derived entity type or property name (the normal ingest path) could close the current Cypher token early and append arbitrary statements (e.g. `DETACH DELETE`), running with the application's database credentials
  - New shared `semantica/graph_store/query_sanitize.py`: `sanitize_identifier()` generalizes `age_store.py`'s existing `_sanitize_label`/`_sanitize_rel_type` (the only backend that already validated this) into a helper the other backends import without an import cycle with `graph_store.py`/`methods.py`
  - Applied at every label/relationship-type/property-key interpolation site in `amazon_neptune.py`, `neo4j_store.py`, `falkordb_store.py`, `graph_store.py` (`degree_centrality`'s own query builder), and `methods.py` (`update_relationship`'s own query builder) — covers `create_node`, `create_nodes`, `create_relationship`, `get_nodes`, `get_relationships`, `get_neighbors`, `shortest_path`, `update_node`, `create_index`, and all relationship-type filters across the three backends
  - **Fixed along the way** (caught in review, by @Sameer6305): `depth`/`max_depth` path-length parameters are meant to be integers, but `Neo4jStore.get_neighbors()`/`shortest_path()` interpolated them into the Cypher variable-length-path syntax (`*1..{depth}`) without coercion — unlike the Neptune/FalkorDB equivalents, which already cast to `int()`. A string `depth` (e.g. `"1]->(x) DETACH DELETE x //"`) reached the query verbatim. Added the same `int()` coercion Neptune/FalkorDB already had, plus `GraphStore.get_neighbors()`'s `hops`/`depth` alias resolution
  - New `tests/graph_store/test_cypher_injection.py` (unit tests on `sanitize_identifier` plus the labels/keys/rel-types injection payload run against Neptune/Neo4j/FalkorDB `create_node`/`create_relationship`, asserting the malicious query is never built or sent) and the depth-coercion regression above; plus additions to `tests/test_graph_store.py` (`degree_centrality`) and `tests/test_graph_store_methods.py` (`update_relationship`). Full graph_store suite: 224+ tests passing

- **4 critical/high vulnerabilities in the Explorer API and vector store: RCE, SSRF, XXE, and DoS, plus Cypher/SPARQL injection hardening found along the way** (#898) by @Sunil56224972
  - **[CWE-502] Arbitrary code execution via `pickle.load()`**: `VectorStore.save()`/`load()` used `pickle` for the on-disk `store_data.pkl`; a crafted `.pkl` file placed in the store directory (file upload, shared filesystem, or supply-chain compromise) could execute arbitrary code on deserialization. Replaced with JSON — vectors and metadata are fully JSON-serializable, so nothing is lost — and `load()` now refuses any legacy `.pkl` file it finds with a migration error rather than deserializing it
  - **[CWE-918] SSRF via redirect bypass in `ontology.py`'s URL fetcher**: `_validate_fetch_url()` correctly blocked private/loopback/reserved addresses on the caller-supplied URL, but `_fetch_url_sync()` fetched with `allow_redirects=True`, so a validated *public* first hop could 302 to `http://169.254.169.254/...` (cloud instance metadata) or an internal service, and `requests` followed it with no re-check. Redirects are now followed manually, capped at 5 hops, with `_validate_fetch_url()` re-run against every hop's target — including relative `Location` headers, resolved via `urljoin()` before validation — and every response (redirect or final) is explicitly closed to avoid leaking connections back to the pool
  - **[CWE-611] XXE injection in the RDF/XML parser**: `_safe_parse_rdf()` depended on `defusedxml` for XXE protection, but `defusedxml` wasn't declared in `pyproject.toml`'s `explorer` extra, so it was silently absent in normal installs and the code fell back to a bare warning plus unsafe parsing — a crafted RDF/XML ontology with an external entity could read arbitrary server files. Added `defusedxml>=0.7.1` to the extra, and `_safe_parse_rdf()` now fails closed: it raises rather than parsing untrusted RDF/XML if `defusedxml` isn't importable, replacing an earlier regex-based DOCTYPE-stripping fallback that was reviewed and rejected as bypassable
  - **[CWE-770] DoS via unbounded SPARQL graph materialization**: `_build_rdflib_graph()` loaded up to 999,999 nodes and 999,999 edges into memory per query, and with up to 4 concurrent SPARQL requests permitted, an attacker could exhaust server memory. Added a 50,000 node/edge cap (`_SPARQL_MAX_GRAPH_NODES`); oversized graphs now return a clean error instead of attempting materialization
  - **Cypher injection via Apache AGE's `graph_name` and `$$`-delimiter breakout**: `graph_name` was interpolated unvalidated into `cypher('{graph_name}', $$ ... $$)`, and raw Cypher query text containing `$$` could close AGE's dollar-quoted string delimiter early and append arbitrary SQL. `graph_name` is now validated against the same identifier allowlist `age_store.py` already used for labels/relationship types, and any query containing `$$` is rejected outright
  - **SPARQL Explorer route (`/api/sparql`) hardened against comment/PREFIX-hiding bypass**: `_is_read_only_query()` now strips comments and PREFIX/BASE declarations before checking the leading keyword, and additionally scans the full query body for SPARQL Update keywords (INSERT/DELETE/DROP/LOAD/CLEAR/CREATE/COPY/MOVE/ADD) — so `SELECT ... ; DROP ALL` is now rejected by the keyword scan itself rather than relying solely on rdflib's parser
  - **Fixed along the way** (maintainer follow-up, addressing automated review findings and a regression introduced across several rounds of iteration on the original fix):
    - `VectorStore.save()`'s numpy handling used `list(v)` for the JSON fallback path, which produces `numpy.float32` elements that `json.dump()` can't serialize — changed to `v.tolist()`
    - the SPARQL graph-size `ValueError` was raised outside `execute_sparql()`'s exception handling and surfaced as an unhandled 500 instead of a clean API error — moved inside
    - every streamed `requests` response in the ontology redirect loop, including the one actually read and returned, is now closed in a `finally` block — a connection-pool leak that a rework of the redirect logic had briefly reintroduced after an earlier fix
    - a later commit meant to add opt-in API-key auth (`explorer/auth.py`, gated on `EXPLORER_API_KEY`) instead **replaced and silently disabled** the `Depends(require_auth)` enforcement already merged into `main` for GHSA-j4mq-hprp-987v (Critical — unauthenticated Explorer API), removed the `/ws/graph-updates` handshake check, and — unlike `require_auth` — failed *open* (allowed all requests) whenever its key was unset. Merging that version would have silently reverted an already-fixed Critical CVE the moment this branch landed. Removed `explorer/auth.py`; restored the per-router `Depends(require_auth)` wiring and the WebSocket auth check; kept the one genuine improvement in that commit (adding `X-API-Key` to the CORS `allow_headers` list) by folding it into the existing CORS config
    - the new SPARQL keyword-scan's comment-stripping regex (`#[^\n]*`) also matched the `#` inside standard RDF namespace IRIs (e.g. `.../1999/02/22-rdf-syntax-ns#`), corrupting any query with a normal `rdf:`/`rdfs:`-style `PREFIX` declaration — caught because the hardening's own bundled tests failed against two of its own cases. Fixed by only treating `#` as a comment-start at line-start or after whitespace; the companion `PREFIX`/`BASE` regex was also fixed to accept bare `BASE <...>` declarations, which have no prefix-name token between the keyword and the IRI
  - New/updated regression tests: `tests/explorer/test_ontology_ssrf.py` (redirect re-validation, relative-redirect resolution, response closing, redirect-cap enforcement), `tests/test_security_regression.py` (Cypher/SPARQL injection, XXE, numpy serialization, SSRF redirect handling), plus additions to `tests/explorer/test_sparql_route.py`, `tests/vector_store/test_vector_store.py`, and `tests/explorer/test_explorer_auth.py`
  - Note: the Cypher-injection hardening here is scoped to `age_store.py`'s `graph_name`/`$$` breakout, found while reviewing this PR. The broader label/property-key/relationship-type injection across the Neptune, Neo4j, and FalkorDB backends (GHSA-482h-hw99-h62p, #910) and the triplet-store SPARQL injection across Blazegraph/RDF4J/Jena (GHSA-8vgg-8mr4-r236, #911) are covered by separate, still-open PRs, as is the unauthenticated-Explorer-API fix referenced above (GHSA-j4mq-hprp-987v, #909, already merged)

- **CI/CD supply-chain hardening against mutable-tag Action compromise (LiteLLM/Trivy-class attack)** (#824) by @KaifAhmad1
  - Every third-party GitHub Action across all 8 workflows is now pinned to a full commit SHA instead of a mutable tag (`@v7` → `@3d3c42e... # v7`), closing the exact vector used against LiteLLM in March 2026 (a compromised Trivy Action tag stole a long-lived publishing token)
  - Added `verify-action-pins.yml` + `.github/scripts/verify-action-pins.sh`: a CI check that fails closed on any `uses:` reference that isn't a full SHA (catching a newly introduced mutable tag, not just auditing existing pins) and re-verifies every pin against the GitHub API on each workflow change, on push to `main`, and weekly; an unresolvable API lookup is treated as a failure rather than a silent skip
  - `release.yml`: scoped `permissions` to the job level (workflow default is now `contents: read`), added a `concurrency` group so simultaneous tag pushes can't race the publish job, and added SLSA build provenance attestation (`actions/attest-build-provenance`) for every released wheel
  - Created a protected `pypi` GitHub Environment (required reviewer, restricted to `v*` tag deployments) and enabled branch protection on `main` (required PR review with stale-approval dismissal, required status checks, no force-push/deletion, required conversation resolution) — PyPI publishing already used Trusted Publishing (OIDC) with no long-lived token
  - Grouped Dependabot's `github-actions` updates into a single PR

- **`security-scan.yml`'s Safety dependency-vulnerability check was silently non-functional** (#824) by @KaifAhmad1
  - `safety check --json --output safety-report.json` is invalid in Safety 3.x (`--output` now selects a console format, not a file path); the command errored on every run, swallowed by `|| true`, so no report was ever produced and the job always fell back to a generic "scan completed" message with the vulnerability count hardcoded to 0
  - Switched to `--save-json`, the correct flag for writing a JSON report to disk; also fixed `vuln.package` → `vuln.package_name` and Semgrep's `issue.rule_id` → `issue.check_id` (both produced `undefined` in the PR comment)
  - The job never installed Semantica's own dependencies before scanning, so Safety was auditing the scanner tools' own transitive deps, not the project's; added `pip install -e ".[llm-litellm]"` so the actual dependency tree — including the LiteLLM extra — is what gets scanned
  - Rewrote the PR-comment builder: every line previously used `\\n` inside JS template literals, which renders as the literal text `\n` rather than a newline, producing an unreadable wall of text; now builds real line arrays and collapses long finding lists into a `<details>` block
  - Added the `pull-requests: write` permission the comment-posting step was missing (silently failing via its own try/catch on every prior run)

- **`pypdf2==3.0.1` removed (CVE-2023-36464)** (#824) by @KaifAhmad1
  - Surfaced by the Safety fix above: PyPDF2 is a discontinued project (merged into `pypdf`) permanently frozen at the vulnerable 3.0.1 with no patched release possible. `grep -rn "import PyPDF2"` found zero real usages anywhere in the codebase — it was only referenced in docstrings describing a `PyPDF2.PdfReader()` fallback for PDF parsing that was never actually implemented (`pdfplumber` does the real work). Removed the dependency and corrected the stale docstrings in `parse/__init__.py`, `parse/methods.py`, `parse/pdf_parser.py`, and `ingest/email_ingestor.py`

- **10 Bandit B324 false positives suppressed (non-cryptographic MD5 use)** (#824) by @KaifAhmad1
  - Surfaced by the same Safety fix restoring a working CI gate: Bandit's HIGH-severity check was blocking on 10 pre-existing `hashlib.md5()` calls, all generating short deterministic cache keys, entity IDs, or IRI suffixes from non-secret input — none used for passwords, tokens, or verifying untrusted data
  - Bandit's own message suggests `usedforsecurity=False`, but that keyword argument needs Python 3.9+ and `pyproject.toml` declares `requires-python = ">=3.8"`; used a targeted `# nosec B324` with a one-line justification instead, which suppresses only this check with no runtime behavior change on any supported Python version

## [0.6.0] - 2026-07-21

### Added

- **Named-graph support for `JenaStore` via `Dataset` migration** (#756, #757) by @Sameer6305 and @KaifAhmad1
  - `JenaStore` now backs onto `rdflib.Dataset(default_union=False)` instead of `rdflib.Graph`, closing #756 and fully closing out the #754/#756 cross-backend named-graph parity effort across Blazegraph, RDF4J, and Jena
  - `default_union=False` is explicitly set so existing `execute_sparql()`/`get_triplets()` calls that don't pass `graph=` keep seeing only the default graph, not a union across all named graphs
  - `add_triplets()` accepts a `graph=` option: when supplied, triples are written to that named graph (4-tuple add via `Dataset.graph(uri)`); when omitted, behavior is unchanged (3-tuple add routes to the default graph)
  - Fixed a pre-existing bug where the remote-endpoint path instantiated the read-only rdflib `SPARQLStore` instead of `SPARQLUpdateStore`, so every `add_triplets()` call against a remote Fuseki endpoint silently failed (`TypeError` swallowed, `success=True`/`added=0` returned); also fixed a constructor bug where `self.endpoint` was always `None` regardless of how `JenaStore` was called, making the remote path unreachable in practice
  - `serialize()` now logs a warning instead of silently dropping named-graph content when the requested format (`turtle`, `xml`, `n3`, …) can only serialize the default graph; use `format="trig"` or `format="nquads"` to include all graphs
  - `create_model()`'s `triplet_count` now documented as counting across all graphs (default + named), not just the default graph, matching the `Dataset`-wide semantics
  - `delete_triplet()` remains scoped to the default graph only (named-graph parity for delete is an explicit follow-up, matching the maintainer's scoping of this migration to `add_triplets`); the removal is passed `self.graph.default_graph` explicitly as its context, since `Dataset.remove()` on a bare 3-tuple resolves to a wildcard context internally and would otherwise delete matching triples out of every named graph too — a follow-up fix to the initial PR #757 for a bug that had no test coverage
  - 9 new tests covering `Dataset` construction, `default_union=False` confirmation, named-graph write isolation, `serialize()` warning behavior, and `delete_triplet()`'s default-graph scoping

- **SPARQL CONSTRUCT query templates** (#752, #322, #755, #754) by @Sameer6305
  - Added parameterized, injection-safe `CONSTRUCT` templates (`ConstructTemplate`, `ParameterDescriptor`, `ConstructTemplateRegistry`)
  - Extended CONSTRUCT execution support from Blazegraph-only to the RDF4J and Jena backends (#755), closing #754
    - `RDF4JStore.execute_sparql` gains a CONSTRUCT-aware path (`Accept: text/turtle`, rdflib Turtle parsing, the same `(s, p, o, metadata)` 4-tuple contract) and named-graph writes via RDF4J's REST `context` parameter
    - `JenaStore.execute_sparql` gains the equivalent CONSTRUCT-aware path over its in-process `rdflib.Graph`
    - `_CONSTRUCT_QUERY_RE` moved to `sparql_escaping.py` as a shared, backend-agnostic constant used by all three backends
  - Added pipeline integration via the `construct_template` step type

- **Databricks Connector (Unity Catalog + Delta Lake ingestion)** (#747) by @KaifAhmad1
  - Added `DatabricksIngestor` (`semantica/ingest/databricks_ingestor.py`), mirroring `SnowflakeIngestor`'s structure and public API shape: a `DatabricksConnector` connection handler, a `DatabricksData` dataclass, and an optional-import guard for `databricks-sdk`/`databricks-sql-connector`
  - Supports personal access token and OAuth M2M (service principal `client_id`/`client_secret`) authentication, configurable via constructor args or `DATABRICKS_*` environment variables
  - `ingest_table()`/`ingest_query()` run against a SQL warehouse or cluster via `databricks-sql-connector`, with `where`/`order_by`/`limit`/`offset` support and the same identifier-escaping and unsafe-`ORDER BY` rejection as `SnowflakeIngestor`; each call closes the SQL connection it opened unless one is already open (e.g. via the `with DatabricksIngestor(...)` context manager), which reuses and closes it exactly once instead of leaking a second connection per call
  - `get_table_schema()`, `list_catalogs()`, `list_schemas()`, and `list_tables()` introspect Unity Catalog via `databricks-sdk`'s `WorkspaceClient`, validating both catalog and schema are resolved before calling the SDK; `get_table_lineage()` calls Unity Catalog's table-lineage REST API for upstream/downstream `Table --DEPENDS_ON--> Table` dependencies, plus an opt-in `include_column_lineage=True` that resolves per-column lineage via the column-lineage API
  - `export_as_documents()` converts ingested rows into Semantica document dicts for KG construction, matching `SnowflakeIngestor.export_as_documents()`'s shape
  - Registered as a lazy export in `semantica.ingest` (`DatabricksIngestor`, `DatabricksData`, `DatabricksConnector`) and as the `db-databricks` optional extra (`pip install "semantica[db-databricks]"`) in `pyproject.toml`, included in `db-all`
  - New `docs/integrations/databricks.md` page modeled on `docs/integrations/snowflake.md`, plus a `DatabricksIngestor` section and table row in `docs/reference/ingest.md` and cross-links between the two integration pages
  - 35 unit tests in `tests/test_databricks_ingestor.py` covering both auth methods, table/query ingestion, connection lifecycle (including reuse under the context manager), pagination, unsafe `ORDER BY` rejection, catalog/schema validation, schema/catalog/table listing, table and column lineage, document export, and the missing-dependency error path, closing #747

- **SQLite Vector Store Backend (`sqlite-vec`)** (#726) by @Luffy2208 and @KaifAhmad1
  - Added `SQLiteVecStore` (`semantica/vector_store/sqlite_vec_store.py`), a disk-backed local vector store using the `sqlite-vec` extension's `vec0` virtual tables, closing #240
  - Supports Cosine and L2 distance metrics, dynamic JSON metadata filtering, read-only mode, and an in-memory (`:memory:`) mode
  - Registered as the `"sqlite"` backend in `VectorStore.SUPPORTED_BACKENDS`, with `db_path`/`sqlite_path` config and a `VECTOR_STORE_SQLITE_PATH` environment variable
  - Batched `add`/`delete`/`get` and `executemany`-based `update` to avoid per-row round trips; optional `use_wal=True` enables `journal_mode=WAL` + `synchronous=NORMAL` for improved write concurrency
  - Lazy-imports `sqlite-vec` so the dependency stays fully optional (`pip install semantica[vectorstore-sqlite]`); table names and metadata filter keys are validated against a strict identifier pattern before SQL interpolation
  - Fixes `VectorStore.update_vectors`/`delete_vectors` to delegate to the active backend store instead of only mutating in-memory state, correcting existing behavior for all non-`inmemory` backends
  - 25 unit and integration tests in `tests/vector_store/test_sqlite_vec_store.py` covering init, add, search, get, update, delete, read-only mode, and stats

### Fixed

- **`kg.ProvenanceTracker` compatibility wrapper out of sync with `ProvenanceManager`, causing 9 pre-existing test failures** (#744, #751) by @Sameer6305 and @KaifAhmad1
  - `kg.ProvenanceTracker` was a standalone in-memory implementation that never delegated to the unified `ProvenanceManager` backend; its own test suite asserted the existence of `get_lineage`, `track_relationship`, `track_entities_batch`, `get_provenance`, and `_use_unified`, none of which were ever implemented, plus a stale `get_all_sources()` assertion expecting `"timestamp"` instead of the actual `"recorded_at"` key
  - Rather than completing the abandoned compatibility layer, `kg.ProvenanceTracker` and its remaining supported methods (`track_entity`, `get_all_sources`, `query_recorded_between`, `revision_history`, `export_audit_log`) now emit `DeprecationWarning`s pointing callers to `semantica.provenance.ProvenanceManager`
  - Removed/rewrote the 9 tests that only exercised the never-implemented compatibility methods to instead verify the observable behavior of the still-supported API, and corrected the stale `get_all_sources()` assertion
  - Added the previously-missing `docs/migration/kg-provenance-tracker.md` migration guide referenced by every new deprecation warning, with a method-mapping table to `ProvenanceManager` and a before/after example, closing #744

- **`ProvenanceManager.track_entity` silently overrides an explicit `parent_entity_id`/`derived_from` on re-track** (#742) by @Sameer6305
  - `track_entity()` resolved `parent_id` via a documented precedence chain (`parent_entity_id` kwarg > `metadata["derived_from"]` > source-as-known-entity-id fallback), but the history-preservation block that runs afterward unconditionally overwrote that resolved value with an auto-generated `f"{entity_id}:v:{existing.last_updated}"` history pointer whenever the entity was being re-tracked, discarding whatever parent the caller had just explicitly supplied with no warning
  - `track_entity()` now records whether the precedence chain already resolved an explicit parent (`parent_entity_id` kwarg, `metadata["derived_from"]`, or the source-as-known-entity-id fallback) before the history block runs, and only falls back to the auto-generated history pointer when the caller supplied no explicit parent on that call
  - The archived history entry for the previous version is still kept reachable in `get_lineage()` via `used_entities` (BFS-traversed by `InMemoryStorage.trace_lineage()`) even when an explicit parent is supplied, so re-tracking with a new parent no longer orphans the prior version from the lineage chain; when no explicit parent is supplied, `used_entities` is left alone since `parent_entity_id` already points at the same history id, avoiding a duplicate self-reference
  - Added `test_retrack_with_explicit_parent_overrides_history_link`, `test_retrack_without_explicit_parent_still_uses_history_link`, `test_retrack_with_derived_from_overrides_history_link`, and `test_retrack_history_reachable_via_used_entities` regression tests, closing #742

- **`ProvenanceManager.get_lineage` does not link entities that share a source URL** (#735) by @KaifAhmad1
  - `track_entity()`'s only auto-linking logic looked up `source` as if it were an existing entity's `entity_id`, so passing the same real URL/DOI as `source` for two conceptually linked entities (e.g. a document and a decision derived from it) never produced a parent link, leaving `get_lineage()` returning a chain of length 1
  - `metadata["derived_from"]` was preserved and echoed back in the output JSON but was never consulted by any linking or traversal code, so the caller's explicit relationship was silently inert
  - `track_entity()` now treats `metadata["derived_from"]` as an explicit parent link (unless `parent_entity_id` was already passed directly), so `InMemoryStorage.trace_lineage()`'s existing BFS over `parent_entity_id` picks it up for free
  - `metadata["derived_from"]` is now recognized on any `collections.abc.Mapping`, not just a concrete `dict`, so e.g. `types.MappingProxyType` metadata still creates the parent link
  - `get_lineage()`'s metadata aggregation now applies the queried entity's own metadata last so it wins over ancestor metadata on conflicting keys, matching the documented "most recent entry's metadata takes precedence" behavior — previously `trace_lineage()`'s BFS order caused ancestor metadata (now reachable via `derived_from` chains) to silently overwrite the queried entity's own values
  - Added 9 regression/edge-case tests in `tests/provenance/test_manager.py` covering the happy path, explicit `parent_entity_id` precedence over `derived_from`, precedence over the `source`-as-known-entity-id fallback, a `derived_from` pointing at a never-tracked entity, non-string/empty-string `derived_from` values being ignored, a self-referencing `derived_from` not hanging traversal, multi-hop `derived_from` chains, metadata precedence between a queried entity and its ancestors, and non-`dict` `Mapping` metadata, closing #735

- **`Reasoner.add_rule` had no deduplication, doubling rules and silently emptying `forward_chain()` on rerun** (#732) by @KaifAhmad1
  - `add_rule()` unconditionally appended to `self.rules`, so re-running the same setup code on an existing `Reasoner` instance (e.g. re-executing a Jupyter cell) duplicated every rule; since `forward_chain()` only records a conclusion if it isn't already in `self.facts`, the second run's duplicated rules matched but produced no new results, with no error or warning
  - `add_rule()` now compares an incoming rule's `rule_type`, `conditions`, and `conclusion` against existing rules and returns the existing `Rule` instead of appending a duplicate, keeping repeated `add_rule()` calls with the same definition idempotent
  - Added `test_add_rule_deduplicates_identical_rule`, `test_add_rule_deduplication_is_idempotent_across_forward_chain`, and `test_add_rule_does_not_dedupe_distinct_rules` regression tests

- **`InferenceResult.premises` always empty from `forward_chain`/`backward_chain`** (#739) by @Sameer6305
  - `_match_rule()` discarded matched facts and returned only instantiated conclusions, so `ExplanationGenerator` always produced empty premises lists regardless of which facts actually satisfied a rule, closing #733
  - `_match_rule()` now returns `(conclusion, matched_facts)` tuples; `forward_chain()` threads those facts into `InferenceResult(premises=...)`, merging premises when the same conclusion is derived more than once within a pass
  - `_prove_goal()`'s base cases (goal already a known fact; goal matched via pattern unification) now return `premises=[goal]`/`premises=[fact]` instead of `[]`
  - Facts are matched against a `sorted()` snapshot instead of the raw `set` so rule matching and premise selection are deterministic
  - Added `test_forward_chaining_premises` regression test mirroring the existing backward-chaining premises test

- **Missing `shacl` optional-dependency extra** (#736) by @Sameer6305
  - `pip install semantica[shacl]` referenced no matching extra in `pyproject.toml`, so `pyshacl` was never installed despite being documented as the fix in `ontology_validator.py`'s `ImportError` message, the Explorer API, the healthcare cookbook notebook, and the changelog
  - Added `shacl = ["pyshacl>=0.25.0"]` to `[project.optional-dependencies]` and folded `shacl` into the `all` extra

- **`NodeEmbedder` `AttributeError` masked in `ContextGraph.analyze_graph_with_kg`** (#734) by @Sameer6305
  - `analyze_graph_with_kg()` called a non-existent `NodeEmbedder.generate_embeddings()`, and the surrounding broad `except Exception` swallowed the resulting `AttributeError`, silently returning `{"error": "Graph analysis failed due to an internal error"}` from `get_causal_chain()`'s supporting analytics and `get_decision_insights()`
  - Rewired the call site to the real `NodeEmbedder.compute_embeddings(graph_store, node_labels, relationship_types)` API, deriving `node_labels`/`relationship_types` from `self.node_type_index`/`self.edge_type_index`
  - Added a dedicated `except AttributeError` branch that logs distinctly and re-raises, so a broken internal method call surfaces as a diagnosable error instead of being indistinguishable from a legitimately empty analysis result

---

## [0.5.1] - 2026-06-29

### Added

- **Apache Arrow & Feather File Ingestion** (#705) by @Luffy2208
  - Added `ArrowIngestor` (`semantica/ingest/arrow_ingestor.py`) for reading `.arrow`, `.feather`, and `.ipc` files via PyArrow
  - Supports Arrow IPC File format (random-access), Arrow IPC Stream format, Feather v1 and v2
  - Selective column reads, optional row limits, and batch-aware iteration that stops early without scanning the full file
  - `extract_schema()` and `extract_metadata()` convenience methods for schema/metadata inspection without reading row data
  - `_ArrowReaderWrapper` provides a unified interface across all three reader types, preventing stream exhaustion during schema inspection
  - `ingest_arrow()` convenience function and `ingest(..., source_type="arrow")` unified dispatch
  - Automatic Arrow format detection in `ingest()` by file extension (`.arrow`, `.feather`, `.ipc`) and by Arrow IPC magic bytes (`ARROW1\x00\x00`) in `FileTypeDetector`
  - Registry integration under the `arrow` task namespace with `file`, `schema`, and `metadata` methods
  - Lazy-import exports of `ArrowIngestor`, `ArrowData`, and `ingest_arrow` from `semantica.ingest`
  - Optional dependency group: `pip install semantica[ingest-arrow]`; included in `pip install semantica[all]`
  - 34 tests covering schema extraction, metadata inspection, row limits, column selection, multi-batch reading, IPC stream format, Feather ingestion, empty datasets, null values, magic-byte detection, and failure modes

- **Knowledge Explorer Deployment Templates** (#684) by @ZohaibHassan16 and @KaifAhmad1
  - Added `deploy/` directory with ready-to-use templates for 7 platforms, closing #681
  - **Docker** — fixed `Dockerfile` path (was broken on clean checkout), added non-root user, `HEALTHCHECK`, `.dockerignore`; fixed `docker-compose.yml` to start Explorer alongside FalkorDB on a shared network; added `docker-compose.dev.yml` with source volume-mounts for hot-reload (`docker compose up` brings up the full stack in one command)
  - **Railway** — `deploy/railway/railway.toml` with Dockerfile builder, healthcheck path, restart policy, and env vars wired from the Railway Redis plugin
  - **Render** — `deploy/render/render.yaml` Blueprint provisioning the web service and a Redis instance together with cross-linked env vars
  - **Fly.io** — `deploy/fly/fly.toml` with region, 512 MB VM, auto-stop, HTTP healthcheck, and a short README with four `flyctl` commands to deploy from zero
  - **GCP Cloud Run** — `deploy/gcp/cloudbuild.yaml` (build → push → deploy pipeline) and `deploy/gcp/cloudrun-service.yaml` (scale-to-zero, Secret Manager env vars, liveness probe)
  - **Azure Container Apps** — `deploy/azure/azure.yaml`, `main.bicep` (Container App + managed environment, HTTP ingress, HPA min 0 / max 10, liveness probe), and `main.parameters.json`; deployable with `azd up`
  - **Kubernetes + Helm** — raw manifests (`namespace`, `configmap`, `secret.example`, `deployment` with 2 replicas + rolling update, `service`, `ingress` with cert-manager TLS, `kustomization`); Helm chart with `Chart.yaml`, `values.yaml`, `values.prod.yaml`, HPA template, and `helm lint`-passing templates; all templates carry `namespace: {{ .Release.Namespace }}`
  - Added `/api/health` endpoint returning `{"status": "ok"}` used by all platform healthchecks
  - Wired `ALLOWED_ORIGINS`, `FALKORDB_HOST`, and `FALKORDB_PORT` from environment variables in `semantica/explorer/app.py`
  - Security hardened: non-root containers, `readOnlyRootFilesystem`, `NetworkPolicy` with explicit ingress/egress selectors, `seccompProfile: RuntimeDefault`, capabilities dropped; secrets via `secret.yaml.example` templates only — no committed credentials

### Fixed

- **Arrow ingestion double full-scan on every data read** (#705) by @KaifAhmad1
  - `ingest_file` previously called `_file_metadata` (a full batch scan) before `_read_batches`, meaning every read scanned the entire file twice; for a `limit=1` read on a large file the metadata pass visited every batch while the data pass read only one; replaced with a single-pass `_read_batches_with_info` that collects batch metadata as a side effect of the data read; `_file_metadata` is now only invoked for `include_data=False`

- **Dead `num_record_batches` property on `_ArrowReaderWrapper` materialised all table batches** (#705) by @KaifAhmad1
  - The property was never called by production code but its `is_table` branch called `to_batches()` purely to take `len()`, materialising the entire table in memory just for a count; property removed

- **Arrow `_open_file` chained the wrong exception** (#705) by @KaifAhmad1
  - The fallback cascade (IPC file → IPC stream → Feather) raised `from feather_err`, surfacing the least diagnostic error in the Python traceback chain; changed to `from file_err` so the IPC file open error — the most informative signal for unrecognised formats — appears as `__cause__`

- **Neo4j Bulk CSV Export** (#665) by @Luffy2208
  - Added `Neo4jCSVExporter` for generating Neo4j bulk-import CSV files compatible with `neo4j-admin database import`
  - Produces deterministic `nodes.csv` and `relationships.csv` with stable node IDs — reuses existing graph IDs or derives reproducible SHA-256 content-based IDs when none are present
  - Multi-label support via Neo4j `:LABEL` convention with configurable `label_separator` (default `;`)
  - Alphabetically sorted property columns and deterministic row ordering for reproducible output across permuted inputs
  - Relationship endpoint resolution: aliases (`name`, `text`, `label`) automatically mapped to stable node IDs
  - Nested property serialisation to canonical JSON; flat scalar values written directly
  - `dry_run()` method for pre-flight CSV validation without writing files
  - `validate_export()` for post-write integrity checks (unique `:id`, consistent column widths, valid endpoint references)
  - `export_nodes()` and `export_relationships()` for partial exports
  - `strict=True` mode raises `ValidationError` on unresolved relationship endpoints
  - `export_neo4j_csv()` convenience function and `format="neo4j_csv"` / `format="neo4j-csv"` dispatch in `export_knowledge_graph()`
  - Registry integration under the `neo4j_csv` task namespace
  - Documentation added to `semantica/export/export_usage.md` with usage examples, mapping assumptions, and `neo4j-admin` import command
  - 13 tests covering headers, node/relationship CSV structure, multi-label, missing properties, deterministic output, CSV quoting/escaping, Unicode, empty graphs, dry-run, duplicate ID detection, ambiguous alias handling, nested property serialisation, and `KnowledgeGraph` integration

### Fixed

- **Neo4j CSV exporter `_write_csv` crashed with `TypeError` on dialect kwargs** (#665) by @KaifAhmad1
  - Passing `delimiter=`, `encoding=`, or any caller kwarg to `export_neo4j_csv` caused `csv.writer` to receive unknown or duplicate keyword arguments; `_write_csv` now whitelists only valid `csv.writer` dialect params (`quotechar`, `doublequote`, `skipinitialspace`, `escapechar`, `strict`)

- **`export_neo4j_csv` double-passed kwargs to both the constructor and `export()`** (#665) by @KaifAhmad1
  - Constructor-level settings (`node_file_name`, `relationship_file_name`, `encoding`, `delimiter`, `label_separator`, `strict`) were merged into config for the constructor then re-forwarded as `**kwargs` to `export_knowledge_graph`, causing dialect params to collide; kwargs are now split into `init_kwargs` and `call_kwargs` before forwarding

- **Dead `node_id_lookup` dict removed from `_prepare_export`** (#665) by @KaifAhmad1
  - The `{original_index → stable_id}` mapping was built on every export but never consumed; removed to avoid misleading future readers

- **Dropped ambiguous `format="neo4j"` alias from `export_knowledge_graph` dispatch** (#665) by @KaifAhmad1
  - `"neo4j"` is used throughout the codebase to identify the live Bolt/Cypher graph store backend; routing it silently to the offline bulk-CSV exporter would have confused callers; only `"neo4j_csv"` and `"neo4j-csv"` are accepted

- **`export_usage.md` documented non-existent constructor and function parameters** (#665) by @KaifAhmad1
  - Examples showed `node_label_sep` (correct: `label_separator`), `strict_validation` (correct: `strict`), and `nodes_path`/`rels_path` kwargs that do not exist; all three examples corrected to match the actual API

- **Public API Ingestion Support** (#602) by @Luffy2208
  - Added `PublicAPIIngestor` class built on top of `RESTIngestor` for credential-free REST endpoints
  - Added `PublicAPIExample` and `PublicAPIExamples` catalog with 6 pre-configured no-auth examples:
    - `jsonplaceholder_posts`, `jsonplaceholder_users`, `jsonplaceholder_todos` — fake REST resources for testing
    - `rest_countries_all` — country reference data
    - `data_gov_datasets` — Data.gov CKAN catalog search
    - `open_meteo_forecast` — weather forecast (Berlin sample)
  - Added `PublicAPIDetection` dataclass for endpoint-level public/no-auth detection
  - Endpoint-level public API detection via `detect_public_api()` (informational, never raises)
  - No-auth validation: rejects `Authorization`, `X-Api-Key`, and all common auth headers before sending the request
  - Auth credential detection in URL query strings (`api_key=`, `token=`, `access_token=`, etc.)
  - Polite rate limiting with per-request and per-ingestor `rate_limit_delay` controls
  - Response parsing for JSON, CSV, and XML with `response_format="auto"` content-type detection
  - HTML response guard — `text/html` responses are never misclassified as XML
  - Nested `record_path` dot-notation extraction (e.g. `"result.results"` for Data.gov envelope)
  - `_to_records` normalization with automatic envelope unwrapping for `items`, `data`, `results`, `records` keys
  - `batch_public_apis()` for multi-endpoint ingestion with optional `fail_fast`
  - `ingest_examples()` for bulk example ingestion
  - `sample_response()` fixtures on `PublicAPIExamples` for mocked unit tests without live network calls
  - `ingest_public_api()` convenience function and `ingest(..., source_type="public_api")` unified dispatch
  - `source_type="api"` alias supported in `ingest()`
  - Registry integration: `public_api` and `api` task namespaces with `endpoint`, `example`, `detect`, `batch`, `examples` methods
  - Lazy-import exports of `RESTIngestor`, `APIData`, `PublicAPIIngestor`, `PublicAPIExample`, `PublicAPIExamples`, `PublicAPIDetection` from `semantica.ingest`
  - Documentation: updated `docs/reference/ingest.md`, `docs/modules.md`, and `semantica/ingest/ingest_usage.md` with full usage examples
  - 18 mocked tests covering JSON/CSV/XML parsing, nested record extraction, auth rejection, detection, string boolean config, batch dispatch, and unified `ingest()` routing
  - 3 optional-import tests covering `defusedxml` fallback path and import isolation without web-scraping backends

### Fixed

- **Public API XML parsing hardened against malicious payloads** (#602) by @Luffy2208
  - Replaced stdlib `xml.etree.ElementTree` with `defusedxml.ElementTree` (XXE/entity-expansion safe); falls back to a hardened `lxml` parser (`resolve_entities=False`, `no_network=True`, `load_dtd=False`, `huge_tree=False`) when `defusedxml` is not installed
  - Added regression test asserting XXE entity payloads raise `ProcessingError`

- **`validate_no_auth` config value not honoured when passed as a string** (#602) by @Luffy2208
  - `bool("false")` evaluated to `True`, making `validate_no_auth=False` impossible via config files or environment variables; replaced with explicit `_coerce_bool()` that maps `"false"`, `"0"`, `"no"`, `"off"` → `False` and rejects unrecognised strings with `ValidationError`

- **Auth credential detection extended to URL query strings** (#602) by @Sameer6305
  - `detect_public_api()` and `ingest_public_api()` now scan the endpoint URL itself for auth parameters (`api_key`, `token`, `access_token`, etc.) via `urllib.parse.parse_qs`, not only request headers and explicit `params=` dicts
  - Added regression tests for URL auth rejection (3 parametrized cases)

- **`ingest_examples` and `batch_public_apis` mutable options mutation** (#602)
  - Shared `**options` dict was passed by reference across loop iterations; mutable values such as `params` dicts were silently mutated after the first call, causing subsequent calls to receive a different (partially modified) options set; fixed by deep-copying options on each iteration

- **`rate_limit_delay` forwarded twice in `ingest_public_api` method dispatcher** (#602)
  - `rate_limit_delay` was consumed by the `PublicAPIIngestor` constructor via `config` but also leaked into `request_kwargs` forwarded to the ingestor method; added to the `config_only_key` strip list so it is consumed once at construction time only

- **XML File Ingestion Support** (#560) by @Luffy2208
  - Added `XMLIngestor` class with `lxml` backend for parsing local XML files
  - Nested element hierarchy and flat element list extraction
  - Namespace and prefix extraction with collision handling
  - Attribute and element metadata extraction
  - Optional XSD schema validation with detailed error reporting
  - Optional DTD validation (internal and external)
  - Secure-by-default parser (`resolve_entities=False`, `no_network=True`) blocking XXE attacks
  - `ingest_xml()` convenience function and `ingest_file(..., method="xml")` support
  - Unified `.xml` auto-detection via `ingest("file.xml")`
  - Directory ingestion with recursive scanning and `fail_fast` support
  - `ingest_string()` for in-memory XML bytes/str ingestion
  - Comprehensive test coverage (8/8 tests passing)

### Fixed

- **NERExtractor LLM method returning pattern-based output on custom gateways** (#554, PR #556) by @KaifAhmad1

  `NERExtractor(method="llm")` silently fell back to regex/pattern extraction when used with OpenAI-compatible enterprise or self-hosted gateways (Qwen, LLaMA proxies, internal routing layers). Returned entities carried `extraction_method='pattern'` even though the LLM itself was producing correct tool-call output. Three root causes fixed:

  - **Silent exception swallowing** — `exc_info=True` was missing from the method-failure `WARNING` in `NERExtractor.extract_entities`. The full gateway-rejection traceback was invisible in logs even with `DEBUG` level enabled, making the failure impossible to diagnose without reading source code.

  - **`response_format=json_object` sent to incompatible gateways** — `OpenAIProvider.generate_structured` unconditionally included `response_format={"type": "json_object"}` in every API call. Custom/enterprise gateways frequently reject this parameter, causing both the `instructor` path and the manual repair loop to fail with the same error on every retry, eventually triggering `_extract_fallback` (pattern extraction).

  - **No fallback in the `generate_typed` manual repair loop** — when `generate_structured` itself raised (due to gateway rejection), the repair loop retried the identical failing call up to `max_retries` times before giving up. There was no path to recover via plain `generate()` + JSON parsing.

  **Additional fixes applied during PR review:**

  - Mode.JSON retry in `generate_typed` now strips `response_format` from `create_kwargs` before forwarding to the retry client, preventing incompatible kwargs from being sent to a client configured for a different instructor mode.
  - `exc_info=True` added to the `generate_structured` fallback warning in the manual repair loop for consistent observability across all failure paths.
  - Removed dead duplicate `is_available` definition in `GroqProvider` — Python silently kept only the second definition; the first was unreachable.
  - `OpenAIProvider._init_client` now validates `base_url` scheme at construction time. Non-HTTP(S) schemes (`file://`, `ftp://`, `javascript:`, etc.) raise `ValueError` immediately, preventing SSRF if `base_url` originates from configuration rather than hardcoded values.

  **17 regression tests** added in `tests/test_issue_554_fixes.py` covering all bug paths, including harshalizode's exact gateway configuration.

### Security

- **GitHub Actions workflow permissions hardened** — added explicit `permissions: contents: read` + `security-events: write` block to `defender-for-devops.yml`, resolving CodeQL alert [actions/missing-workflow-permissions](https://github.com/semantica-agi/semantica/security/code-scanning/25) (CWE: principle of least privilege).

- **DOMPurify upgraded to 3.4.0+ via npm overrides** — `monaco-editor` pinned `dompurify` at 3.2.7; added `overrides` in `explorer/package.json` to force `^3.4.0` (resolved to 3.4.10). Fixes 6 Dependabot alerts:
  - Prototype pollution → XSS bypass via `CUSTOM_ELEMENT_HANDLING` fallback (CVE-2026-41238 / GHSA-v9jr-rg53-9pgp)
  - Mutation-XSS via re-contextualization into raw-text wrappers (GHSA-h8r8-wccr-v5f2)
  - `SAFE_FOR_TEMPLATES` bypass in `RETURN_DOM` mode (CVE-2026-41239 / GHSA-crv5-9vww-q3g8)
  - `ADD_TAGS` function-predicate bypasses `FORBID_TAGS` (GHSA-39q2-94rc-95cp / GHSA-h7mw-gpvr-xq4m)
  - `ADD_ATTR` predicate skips URI validation, allowing `javascript:` URLs (GHSA-cjmm-f4jc-qw8r)
  - `USE_PROFILES` prototype pollution allows event handlers (GHSA-cj63-jhhr-wcxv)

- **`uuid` upgraded to 13.0.1+ via npm overrides** — bumped from 13.0.0 to 13.0.2, fixing missing buffer bounds check in `v3`/`v5`/`v6` APIs that allowed silent partial writes into caller-provided buffers (CVE-2026-41907 / GHSA-w5hq-g745-h8pq).

- **Vite upgraded from 5.x to 6.4.3** — resolves path traversal in optimised-deps `.map` handling (CVE-2026-39365 / GHSA-4w7w-66w2-5vf9) and the esbuild dev-server CORS issue (GHSA-4w7w-66w2-5vf9). Bundled esbuild updated from 0.21.5 → 0.25.12.

- **esbuild forced to 0.28.1+ via npm override** — vite 6.4.3 bundles esbuild 0.25.12 which is vulnerable to missing binary integrity verification in the Deno distribution module (GHSA-gv7w-rqvm-qjhr); added `"esbuild": "^0.28.1"` to `overrides` in `explorer/package.json`. `npm audit` now reports 0 vulnerabilities (Dependabot #15).

- **Leaked Groq API keys removed from cookbook notebooks** — 6 hardcoded `GROQ_API_KEY` values (`gsk_...`) stripped from configuration cells in `supply_chain/01`, `intelligence/01`, `cybersecurity/01`, `cybersecurity/02`, `finance/01`, and `blockchain/02`; fallback replaced with empty string (secret scanning alerts #1–#6). Keys were already publicly exposed — rotate them in the Groq console.

- **Leaked Groq API keys removed from additional cookbook notebooks** — 6 distinct hardcoded `GROQ_API_KEY` values stripped from 4 additional notebooks: `advanced_rag/01_GraphRAG_Complete`, `advanced_rag/02_RAG_vs_GraphRAG_Comparison`, `blockchain/01_DeFi_Protocol_Intelligence`, and `biomedical/01_Drug_Discovery_Pipeline` (secret scanning alerts #1–#6). Affected keys: `gsk_SLLE0...`, `gsk_S4dBVJ...`, `gsk_SLOv6...`, `gsk_lR6Qcj...`, `gsk_ToJis6...`, `gsk_LmbQBr...`; all publicly exposed since Dec 2025 — revoke in the Groq console and close the GitHub secret scanning alerts as "Revoked" in the Security tab.

---

## [0.5.0] - 2026-05-11

### Added

- **Distance Intelligence Embedding Cache Optimization** by @KaifAhmad1
  - Implemented per-session graph revision-based embedding cache to avoid re-scanning all nodes on every request
  - Added `get_cached_embeddings()` method to GraphSession with thread-safe caching and automatic invalidation
  - Updated distance matrix and semantic neighborhood endpoints to use cached embeddings for significant performance improvement
  - Added graph revision tracking using hash-based identifiers for cache invalidation
  - Implemented force refresh capability and automatic cache invalidation on graph modifications (add_nodes/add_edges)
  - Resolved TODO in `graph.py` for embedding caching optimization
- **Parquet File Ingestion Support** (#548) by @Luffy2208
  - Added ParquetIngestor class with PyArrow backend
  - Single file and partitioned directory ingestion
  - Schema and metadata extraction capabilities
  - Selective column reading with memory efficiency
  - Hive-style partition discovery support
  - Unified dispatch integration
  - Optional dependency management (ingest-parquet extra)
  - Comprehensive test coverage (32/32 tests passing)

**Ontology Hub** (part of #517)

- **Alignments tab** (PR #524, @KaifAhmad1 @ZohaibHassan16) — cross-ontology alignment authoring UI:
  - Create/edit/delete alignments with source URI, target URI, relation selector (owl:equivalentClass, all five skos:*Match variants), confidence slider, provenance, and reviewer fields.
  - Pairwise alignment matrix: scrollable table for all loaded ontology pairs; clicking a badge pre-fills the form.
  - Alignment suggestions via `POST /api/ontology/suggest-alignments` — blended score (0.4×label + 0.6×TF-IDF char-ngram cosine); one-click accept.
  - Ephemeral-storage banner; all handlers wrapped in `useCallback`.
- **Health Dashboard** (PR #524) — per-ontology quality scoring across 5 dimensions:
  - Completeness, Consistency, SHACL (stub), Alignment, Documentation.
  - Total score computed as mean of scoreable dimensions only (SHACL excluded when unavailable).
  - Issue list with severity badges (error/warning/info), entity URI chip, "Fix in Editor" deep-link.
  - Downloadable JSON health report; `GET /api/ontology/health` with `_MAX_ANALYSIS_NODES = 5 000` OOM cap.
- **SHACL Studio** (PR #524) — interactive SHACL shape authoring:
  - Shape generation via `POST /api/ontology/shacl/generate` (permissive/standard/strict tiers).
  - Shape library panel with per-shape Turtle extraction; "View all" restores full document.
  - Monaco editor with custom Monarch tokenizer for Turtle syntax.
  - Validation stub via `POST /api/ontology/shacl/validate`; rejects empty/invalid Turtle with HTTP 422.
- **Visual Ontology Editor** (PR #519, @KaifAhmad1) — @xyflow/react canvas for authoring classes/properties/individuals without hand-writing OWL/Turtle:
  - Context menus on nodes (rename, add super/subclass, restrictions, SKOS metadata, deprecation, delete with impact count) and edges (toggle functional/symmetric/transitive/inverse-functional, add inverse).
  - All edits debounced and staged as pending diffs via `PATCH /api/ontology/draft`; nothing commits until proposal publish.
- **Versions & Proposals tab** (PR #519) — version timeline, proposal review (approve/reject/publish), SHACL pre-validation, side-by-side diff via `VersionManager.diff_ontologies()`.
- **Ontology Registry** (PR #518, @KaifAhmad1) — full CRUD with status/format badges, per-ontology stats, live search, filter pills (All/OWL/SKOS/Internal/External), action feedback auto-hide.
- **Ontology Loader** (PR #518) — three-mode modal: URL import (fetch preview + load), file upload (.ttl/.rdf/.owl/.nt/.jsonld/.n3), create new (scratch/from-data/from-text).
- **Entity Search panel** (PR #518) — debounced 320 ms search across all loaded ontologies; type filter pills; result detail panel with super/subclasses, domain/range, instance count.
- **SKOS Vocabulary Manager** (PR #518) — hierarchical concept browser with recursive `ConceptTreeNode`, client-side `filterConcepts()`, full SKOS annotation detail (definition, scopeNote, broader/narrower/related/exactMatch).
- **16 backend endpoints** under `/api/ontology` — registry, preview, load, create, search, entity, skos/schemes, skos/concept, draft, proposals CRUD, versions, alignments, health, shacl/generate, shacl/shapes, shacl/validate (PRs #518, #519, #524).
- **Explorer landing page redesign** (PR #516, @ZohaibHassan16) — hero section, animated SVG graph preview, live `/api/graph/stats` metrics, workspace launcher; `Space Grotesk` / `IBM Plex Sans` fonts; `prefers-reduced-motion` support.
- **Distance Intelligence** (PR #502, @KaifAhmad1):
  - `ContextGraph.get_neighbors(include_distance_metadata)` — adds `distance_band`, `confidence_decay`, `path_to_anchor` per result.
  - `AgentContext.retrieve()` / `find_precedents()` blend graph proximity with semantic score (`combined_score = (1−w)×semantic + w×proximity`).
  - 5 new API endpoints: `POST /api/graph/distance-matrix` (N×N, upper-triangle mirrored), `GET /api/graph/node/{id}/semantic-neighborhood`, `GET /api/decisions/causal-distance`, `GET /api/temporal/distance-history`, `POST /api/export/distance-enriched` (CSV/JSONL, capped at 200 nodes).
  - Explorer UI: Ego Mode (BFS depth-of-field fading, depth slider 1–8), Structural overlay, Semantic overlay, Heatmap (green→red by hop); Path inspector with distance band chip, metric cards, bottleneck node highlight.
  - 57 new tests in `tests/context/test_distance_intelligence.py`.
- **Graph Explorer visual refresh** (PR #503, @ZohaibHassan16) — structured `ui.*` design-token namespace; per-shape biomolecule/condition/compound config; decomposed toolbar memos; typed sub-components (`SearchCommandBar`, `ToolbarCluster`, etc.); deterministic LOD edge classification via `GraphFullEdgeClass`.
- **Graph Workspace declutter** (PR #483, @ZohaibHassan16) — calmer default presentation for dense graphs, display-edge aggregation with raw-edge bundle retention, grouped community view, neighborhood collapse/expand.
- **Bidirectional path finding** (closes #469, @KaifAhmad1) — `directed=false` query param on BFS and Dijkstra; undirected view built via `graph.to_undirected()` for traversal only; empty-path 404 guard; `PathResponse.directed` field.
- **Node distance semantics in path responses** (closes #472) — `PathResponse` gains `hop_count` and `distance_band` ("direct"/"near"/"mid-range"/"distant"); `classify_path_distance()` in `semantica/utils/helpers.py`; `KGVisualizer.visualize_network(highlight_path)` with band-scaled edge rendering.
- **Native `KnowledgeGraph` type support in `KGVisualizer`** (closes #471) — formal `KnowledgeGraph` dataclass (`entities`, `relationships`, `metadata`); `_normalize_graph()` duck-types input; raises clear `ProcessingError` on unknown types. 21 tests added.
- **Indexed search for large graphs** (PR #481, @ZohaibHassan16) — purpose-built inverted index with exact/token/prefix lookup tiers; LRU cache (128 slots); O(log n) mutation sync via `bisect.insort`; warm-query time 24 ms → 0.004 ms on 118 k-node graph.
- **Provenance traversal multi-hop fix** (PR #480, @Sameer6305) — undirected ego-graph expansion so upstream ancestors at depth ≥ 2 are no longer silently excluded; `ProvenanceEdge.direction` field (upstream/downstream/lateral); grouped markdown report under `## Upstream/Downstream/Lateral` sections.
- **TripletStore ontology namespace** (PR #447, @KaifAhmad1) — `_resolve_iri()` applies `base_uri` before `urn:` fallback; W3C prefix expansion table (owl/xsd/rdf/rdfs/skos) expands to canonical IRIs regardless of `base_uri`.
- **Blazegraph literal serialization** (PR #448, @KaifAhmad1) — `_format_object_for_sparql()` selects IRI/typed-literal/language-tagged-literal/plain-literal token; `_resolve_datatype_iri()` with prefix expansion; RFC 5646 language-tag validation; `_escape_literal()` for string escaping.
- **DeepSeek provider via OpenAI SDK** (PR #482, @liling) — `_init_client` rewritten using `openai.OpenAI(base_url=self.base_url)` instead of defunct `deepseek` package; `verbose_mode` assignment fix; `pyproject.toml` updated to `openai>=1.0.0`.

- **`DuplicateDetector` result limiting and ranking** (issue #534, by @KaifAhmad1):
  - `max_results` — hard global cap on returned candidates; applied after sorting. `None` means no limit.
  - `top_k_per_entity` — keep at most *k* candidates per entity (by the sort field) so no single entity floods the output. `None` means no per-entity limit.
  - `min_similarity` — extra similarity floor on top of `similarity_threshold`; candidates below it are dropped before ranking. `None` means no extra floor.
  - `sort_by` — ranking field before limits are applied; accepts `"confidence"` (default) or `"similarity_score"`. Invalid values raise `ValueError` at construction time.
  - All four options are applied by the new `_apply_result_limits` helper and are respected by both `detect_duplicates()` and `incremental_detect()`.
  - 15 new tests in `TestResultLimiting` covering each option in isolation and in combination.
  - **Follow-up Qodo review fixes** (by @KaifAhmad1):
    - `top_k_per_entity` now uses OR semantics — a candidate is kept if *either* entity is still under quota, preventing high-quality pairs from being silently dropped when a popular counterpart saturates its limit.
    - `max_results` and `top_k_per_entity` now validated at construction time; negative or non-integer values raise `ValueError`.
    - `min_similarity` now validated in `[0.0, 1.0]` at construction; out-of-range values raise `ValueError`.
    - Added `_normalize_entity_id` helper (always returns `str`) used consistently in both `_apply_result_limits` and `_build_duplicate_groups`, eliminating `int` vs `str` ID key mismatches.
    - Updated `detect_duplicates` and `incremental_detect` docstrings to reflect the configurable `sort_by` field.

### Fixed

- **Fix: `ConflictDetector.detect_conflicts()` raises `AttributeError` when called with `method=` or `property_name=` kwargs** (issue #533, PR conflicts, by @KaifAhmad1):
  - `detect_conflicts` was defined twice in `conflict_detector.py`; Python silently overwrote the first (dispatcher) definition with the second (comprehensive), which accepted no `method` or `property_name` parameters — causing `AttributeError` or `TypeError` for any caller using those kwargs.
  - Removed the first (dead) definition and merged its dispatcher logic into the surviving method. New signature: `detect_conflicts(entities, method="all", property_name=None, entity_type=None, **kwargs)`.
  - Supported `method` values: `"all"` (default, comprehensive), `"value"`, `"property"`, `"type"`, `"relationship"`, `"temporal"`, `"logical"`, `"entity"`. Unknown values raise `ValueError`.
  - Fixed `method="relationship"` silently defaulting `relationships` to the entities list, which caused entity dicts to be iterated as relationship dicts producing silent wrong results (`None_None_None` keys). Now defaults to `[]` with dict normalization.
  - Removed unreachable dead code (`for field_name in fields_to_check` loop after `try/except raise`) in `detect_entity_conflicts`.
  - **Follow-up Qodo review fix** — hardened `method="relationship"` normalization: when `relationships` kwarg is a dict whose `"relationships"` value is itself a non-list (or the key is absent), the value is now always wrapped in a list before being passed to `detect_relationship_conflicts`, guaranteeing `List[Dict]` input in all cases.

- **Fix: `semantica[all]` installation fails on Windows due to `faiss-gpu` dependency** (issue #532, PR #utlis, by @KaifAhmad1):
  - `[all]` bundled the `[gpu]` extra (`faiss-gpu>=1.7.0`, `cupy>=10.0.0`), which has no Windows builds, causing `pip install "semantica[all]"` to fail with `No matching distribution found for faiss-gpu>=1.7.0`.
  - Removed `gpu` from both `[all]` lines in `pyproject.toml` — `[all]` now installs only cross-platform dependencies. Users on Linux who need GPU acceleration can install `semantica[gpu]` explicitly.

- **Fix: Progress tracker crashes with `UnicodeEncodeError` on Windows cp1252 consoles** (issue #531, PR #utlis, by @KaifAhmad1):
  - `ConsoleProgressDisplay.update()` had 5 direct `sys.stdout.write()` calls that bypassed the existing `_safe_write()` guard, causing `UnicodeEncodeError` when emoji characters (`🧠`, `📊`) were written to cp1252-encoded consoles during any progress-tracked operation.
  - All 5 calls replaced with `self._safe_write()`, which catches `UnicodeEncodeError` and re-encodes output with `errors="replace"` so progress output never crashes the process.
  - Added `TestProgressTrackerEncoding` regression class (3 tests) covering `_safe_write` safety, pipeline header write, and auto emoji-disable on cp1252 stdout.

- **Fix: Break circular import in `semantic_extract`; address Qodo review bug** (issue #528, PR #536, by @ZohaibHassan16, review fixes by @KaifAhmad1):
  - **Root cause** — `ner_extractor.py` imported `get_entity_method` from `methods.py`, while `methods.py` imported `Entity` from `ner_extractor.py`, creating a circular import that raised `ImportError: cannot import name 'Entity' from partially initialized module` on any import of `semantica.semantic_extract`.
  - `semantica/semantic_extract/types.py` (new) — shared `Entity`, `Relation`, and `Triplet` dataclasses extracted into a dedicated module that neither side of the old cycle imports, so both `ner_extractor`, `relation_extractor`, `triplet_extractor`, and `methods` can import from it freely.
  - `semantica/semantic_extract/__init__.py` — lazy-loads package-level exports so core extractor imports do not pull in optional modules (e.g. the YAML-backed semantic network extractor); added `TripleExtractor` as a compatibility alias for `TripletExtractor`; legacy re-exports from the individual extractor modules preserved for backward compatibility.
  - `semantica/semantic_extract/methods.py` — updated to import shared types from `types.py`; extractor-specific imports moved to function scope where needed to prevent re-introducing the cycle.
  - Added regression tests (`tests/semantic_extract/test_imports.py`) covering import order independence (methods-before-extractors and extractors-before-methods), legacy type import compatibility, `TripleExtractor` alias, and that core imports do not require `yaml`.
  - **Review fix (Qodo — Py3.8 test import crash)**: `test_imports.py` annotated `_run_python` as `-> subprocess.CompletedProcess[str]`, which is not subscriptable at runtime on Python 3.8 (generic subscript on built-in types requires 3.9+). Added `from __future__ import annotations` (PEP 563) so all annotations are lazy strings never evaluated at import time, restoring compatibility with the declared `requires-python = ">=3.8"` without any behaviour change on 3.9+.
- **Fix: Lazy-load optional ingest backends; address Qodo review bugs** (issue #527, PR #535, by @ZohaibHassan16, review fixes by @KaifAhmad1):
  - `semantica/ingest/__init__.py` — core exports (`FileIngestor`, `ingest_file`, config, registry) remain eagerly imported; all optional backends (`WebIngestor`, `FeedIngestor`, `RepoIngestor`, `EmailIngestor`, `StreamIngestor`, `DBIngestor`, `MCPIngestor`, `OntologyIngestor`, `SnowflakeIngestor`) are now deferred behind a module-level `__getattr__`, so `from semantica.ingest import FileIngestor` no longer fails when GitPython or BeautifulSoup4 are absent.
  - `semantica/ingest/methods.py` — backend imports relocated into their respective ingestion functions (`ingest_web`, `ingest_feed`, `ingest_repository`, `ingest_email`) with helper `_missing_optional_dependency()` / `_is_missing_dependency()` for consistent, actionable error messages.
  - **Review fix (Bug 1 — overbroad missing-dep detection)**: replaced `except ImportError` with `except ModuleNotFoundError` in all four function-level import guards and in `__getattr__`. `ImportError` catches failures thrown by code *inside* a successfully found module, masking real bugs with a misleading "package not installed" message; `ModuleNotFoundError` (its subclass) is specific to absent modules. Simplified `_is_missing_dependency` to rely solely on `exc.name` now that `ModuleNotFoundError` always sets it.
  - **Review fix (Bug 2 — expected errors logged as failures)**: added `except ConfigurationError: raise` before the blanket `except Exception` handlers in `ingest_web`, `ingest_feed`, `ingest_repository`, and `ingest_email`. Missing optional dependencies are expected user-configuration issues and must not produce error-level log entries.
  - **Review fix (Bug 3 — test blocker not setting `exc.name`)**: `OptionalDependencyBlocker.find_spec` now sets `err.name = root_name` on the manually constructed `ModuleNotFoundError`, matching what Python's import machinery does, so `_is_missing_dependency` correctly identifies the missing package in tests.
  - Added regression tests (`tests/ingest/test_optional_imports.py`) that block the `git` and `bs4` modules via a custom meta path finder and assert core imports succeed and backends raise `ConfigurationError` with an actionable message.
- **Fix: Ontology Hub post-review bug fixes and security hardening** (follow-up to #518, closes security advisory #23, by @KaifAhmad1):
  - **Broken registry filters** — `fetchRegistry` was sending toolbar filter values (`owl`, `skos`, `internal`, `external`) to the backend as the `status` query param, which only accepts `published|draft|external`, causing those filters to return empty lists. Removed the spurious `status` param; all format/kind filtering is now applied client-side via `filteredEntries`, which already had the correct logic.
  - **Toggle/refresh URI corruption** — `toggle_ontology` and `refresh_ontology` applied `.removesuffix("/toggle")` / `.removesuffix("/refresh")` to the captured path parameter, which would silently corrupt any ontology URI that legitimately ends with those strings. Starlette's route regex (`/{uri:path}/toggle`) already strips the literal suffix via backtracking, so the `removesuffix` calls were removed and the raw `ontology_uri` parameter is used directly.
  - **SSRF in URL fetch** — `_fetch_url_sync()` accepted arbitrary user-supplied URLs and called `requests.get()` with no validation, enabling server-side request forgery against internal services. Added `_validate_fetch_url()` which rejects non-`http`/`https` schemes and resolves the hostname via `socket.getaddrinfo`, blocking loopback, private, link-local, reserved, and multicast addresses.
  - **File upload format misdetected** — the file picker accepted `.xml` and `.json` but `fmtMap` had no entries for those extensions, causing them to default to `turtle`. Added `xml: "xml"` and `json: "json-ld"` mappings. Changed the unknown-extension fallback from `|| "turtle"` to `?? ""` (empty string), and omit the `format` key from the request body when empty so the backend `_detect_format()` runs instead of receiving a forced incorrect value. Also added `.n3` to the accepted extension list and dropzone hint.
  - **Inconsistent XML hardening** — `_parse_rdf_sync()` called `rdflib.Graph().parse()` directly, bypassing the `defusedxml`-based XXE protection already present in `semantica/explorer/utils/rdf_parser.py`. Now routes through `_safe_parse_rdf()` from that module, applying consistent protection for all RDF/XML parse paths.
  - **Search scans whole graph** (`GET /api/ontology/search`) — the endpoint fetched up to 999 999 nodes and performed a linear Python substring scan on every request. Replaced with `session.search(q, limit * 6)` which uses the `GraphSearchIndex`; results are then post-filtered by `_SEARCHABLE_TYPES` and `entity_type` before being returned up to the requested limit.
  - **ReDoS in format detector** (security advisory #23, CodeQL `py/polynomial-redos`, CWE-1333/730/400) — `_detect_format()` used `re.match(r"_:\w+|<[^>]+>\s+<[^>]+>", ...)` to detect N-Triples content. The `<[^>]+>\s+<[^>]+>` alternative was flagged as a polynomial regular expression on uncontrolled data. The URI-subject branch was already unreachable (strings starting with `<` return `"xml"` two lines above), so the entire regex was replaced with two O(1) string operations: `stripped.startswith("_:")` and `" <" in stripped`. `import re` removed as now unused.
- **OWLExporter Turtle syntax** (closes #478) — invalid multi-block output fixed via `_ttl_block()`; data properties no longer silently dropped; `_escape_ttl_str()` applied to all label/comment/version sites. 43 tests added.
- **OWLGenerator schema compatibility** (Issue #446) — label-first IRI fallback, list-typed datatype ranges, per-call namespace consistency, `subClassOf`/`subclassOf` parity.
- **TripletStore IRI regressions** (PR #447 follow-up) — non-string IDs coerced to `str()`; W3C prefix expansion now correct regardless of `base_uri`.
- **`KGVisualizer` accepts `KnowledgeGraph` objects** (closes #458) — `_normalize_graph()` duck-types input; raises clear `ProcessingError` on unknown types. 21 tests added.
- **Semantic Distance UI slash-safe routes** (PR #515, @ZohaibHassan16) — query-param routes `/api/graph/semantic-neighborhood?node_id=` and `/api/graph/path?source=&target=` bypass FastAPI's `%2F` pre-decode; legacy path-segment routes kept as deprecated aliases.
- **Explorer Distance Intelligence rendering** (PR #513, @ZohaibHassan16) — distance state flows through Sigma reducer/theme pipeline instead of mutating raw graph attributes; `restoreNodeColors()` race eliminated by merging ego/heatmap `useEffect` hooks.
- **Distance Intelligence code review regressions** (PR #502 follow-up, @KaifAhmad1) — `top_k` param name fix; `include_distance_metadata` gated behind `False` default; `weakest_link` key standardized; temporal sampling uses `timedelta` not `timetuple`; O(E×L) decay replaced with O(E) index; `AgentContext._apply_proximity_metadata` stores `graph_node_id` separately; sweep animation `sweepGeneration` counter fix; HTTP 413 for >200 node subsets; upper-triangle distance matrix.
- **Knowledge Explorer blockers** (PR #420, @ZohaibHassan16):
  - `Dockerfile`: renamed `DockerFile` → `Dockerfile`; fixed `CMD` module path; added `app = create_app()` at module level.
  - CORS: default origins narrowed from `"*"` to `localhost:5173` only.
  - `get_ws_manager()` now raises HTTP 503 instead of unhandled `AttributeError`.
  - SPARQL: read-only enforcement — `INSERT`/`DELETE`/`UPDATE`/`LOAD`/`DROP` rejected.
  - Vocabulary: 10 MB upload cap; JSON-LD format auto-detection for `.jsonld`/`.json-ld`/`.json`.
  - Annotation `O(1)` lookup via `GraphSession.get_annotation(id)`.
  - Self-loop guard in `batchMergeEdges` prevents Graphology crash.
  - Static build artifacts removed from git; `semantica/static/` added to `.gitignore`.
- **Ontology Hub post-review hardening** (PR #518 follow-up, @KaifAhmad1):
  - Registry filter: `status` param removed from `fetchRegistry`; filtering applied client-side.
  - Toggle/refresh URI: removed `.removesuffix()` calls that corrupted URIs ending with those strings.
  - Format detector: `_detect_format()` ReDoS eliminated — `re.match` replaced with two O(1) string ops.
  - Broken `fmtMap` entries: added `xml`/`json` mappings; unknown-extension fallback changed from `|| "turtle"` to `?? ""`.
  - XML hardening: `_parse_rdf_sync()` now routes through `_safe_parse_rdf()` for consistent defusedxml XXE protection.
  - Search: replaced O(999 999) linear scan with `GraphSearchIndex`-backed `session.search()`.

### Security

- **12 vulnerability fixes** (PR security-enhancement, @KaifAhmad1):
  - **[CRITICAL — CWE-95]** Eval injection in `media_parser.py`: replaced `eval(ffprobe_output)` with `fractions.Fraction`.
  - **[CRITICAL — CWE-502]** Pickle deserialization in `agent_memory.py`: replaced with JSON; legacy `.pkl` files detected and refused with migration message.
  - **[HIGH — CWE-89]** SQL injection in `snowflake_ingestor.py`: `LIMIT`/`OFFSET` parameterized; `ORDER BY` regex-validated; `WHERE` clauses containing semicolons rejected.
  - **[HIGH — CWE-611]** XXE in `rdf_parser.py`: `defusedxml.defuse_stdlib()` before all RDF/XML parsing.
  - **[HIGH — CWE-346/200]** Missing security headers in `server.py`: `CORSMiddleware`, `X-Content-Type-Options`, `X-Frame-Options`, HSTS, generic 500 handler.
  - **[HIGH — CWE-346/400]** Overpermissive CORS in `explorer/app.py`: methods/headers narrowed; 64 KB WebSocket frame cap.
  - **[MEDIUM — CWE-20]** Algorithm param unconstrained in `graph.py`: enum-validated `bfs|dijkstra` only.
  - **[MEDIUM — CWE-434]** RDF upload without extension check in `vocabulary.py`: `.ttl/.rdf/.owl/.xml/.jsonld` allowlist enforced.
  - **[MEDIUM — CWE-1336]** Prompt injection in `llm_extraction.py`: user-supplied content wrapped in `json.dumps()`.
  - **[MEDIUM — CWE-95]** Dynamic `__import__()` in `pipeline_validator.py`: replaced with proper module-level import.
  - **[MEDIUM — CWE-1333]** ReDoS in `enrich.py`: whitespace-normalize then split on literal `" AND "`.
  - **[LOW — CWE-22]** Path traversal in `server.py` SPA route: `Path.resolve().relative_to()` guard; 400 on escape.
  - **[LOW — CWE-400]** Unbounded SPARQL in `sparql.py`: 5 000-row cap, 30 s `asyncio.wait_for` timeout, `Semaphore(4)` concurrency cap; `SparqlResponse.truncated` field added.
  - **[LOW — CWE-434]** Import upload in `export_import.py`: 50 MB cap; `{.json,.csv}` allowlist.
  - CodeQL `paths-ignore` for `cookbook/**/*.html` to suppress false-positive JS alerts #15–18.
- **SSRF in Ontology Hub** (PR #518 follow-up): `_validate_fetch_url()` rejects non-http/https schemes and resolves hostname via `socket.getaddrinfo`, blocking loopback/private/link-local/multicast addresses.

---

## [0.4.0] - 2026-04-08

### Added

**Temporal Intelligence** (@KaifAhmad1, PRs #396–#402)

- **Core Temporal Data Model** (PR #396) — `semantica.kg.temporal_model` with shared parsing/normalization/serialization helpers; `TemporalBound` and `BiTemporalFact` exported from `semantica.kg`; valid-time and transaction-time filtering; `TemporalValidationError` on invalid inputs; history-preserving revisions in `TemporalVersionManager.apply_revision()` with supersession semantics.
- **Point-in-Time Query Engine** (PR #397) — `TemporalGraphQuery.reconstruct_at_time(graph, at_time)` builds consistent point-in-time subgraphs without mutating source; `TemporalConsistencyReport` detects inverted intervals, relationships outside entity lifetimes, overlapping same-type relationships, and temporal gaps; sequence/cycle pattern detection; calendar-aligned evolution bucketing via `temporal_granularity`; causal ordering controls on `find_temporal_paths()` (strict/overlap/loose).
- **Deterministic Temporal Reasoning Engine** (PR #398) — `semantica.kg.temporal_reasoning`; full Allen interval algebra via `IntervalRelation` (all 13 relations); `TemporalReasoningEngine` with interval merging, gap analysis, coverage calculation, timelines, retroactive coverage; zero LLM calls; circular import risk between `semantica.reasoning` and `semantica.kg` eliminated.
- **Temporal Awareness in ContextGraph** (PR #399) — `Decision` dataclass gains `valid_from`/`valid_until`; superseded decisions remain in graph (immutable history); `find_precedents_by_scenario(include_superseded, as_of)`; `ContextGraph.state_at(timestamp)` serializable snapshot; `CausalChainAnalyzer.trace_at_time(event_id, at_time)`; `AgentContext.checkpoint(label)`, `diff_checkpoints()`, `flush_checkpoint()`.
- **Temporal Metadata Extraction from Text** (PR #400):
  - `extract_relations_llm(extract_temporal_bounds=True)` — each `Relation` gains `valid_from`, `valid_until`, `temporal_confidence` (0.0–1.0), `temporal_source_text`; default `False` is 100% backward-compatible.
  - Calibrated confidence anchors: 1.00 = full ISO date → 0.00 = no temporal signal.
  - `TemporalNormalizer` (zero LLM calls, pure regex + dateutil): `normalize(value)` → UTC datetime tuple or `None`; `normalize_phrase(phrase)` → metadata dict or `None`; 13-domain default phrase map; `TemporalAmbiguityWarning` for ambiguous DD/MM/YYYY inputs (never silently guesses locale).
- **Temporal Provenance & OWL-Time Export** (PR #401):
  - `ProvenanceTracker.track_entity()` auto-stamps `recorded_at` on every new record.
  - `query_recorded_between(start, end)`, `revision_history(fact_id)`, `export_audit_log(fact_ids, format)` (JSON/CSV).
  - `RDFExporter.export_to_rdf(include_temporal=True, time_axis="valid|transaction|both")` — emits OWL-Time triples for all temporally-annotated relationships.
  - `create_snapshot()` stamps `"format_version": "1.0"`; `validate_snapshot()` and `migrate_snapshot()` for stable snapshot lifecycle.
- **Temporal GraphRAG Integration** (PR #402) — `TemporalGraphRetriever` filters retrieved context to a point in time; `ContextRetriever.query_with_reasoning(at_time, header_template)` prepends structured temporal header; `TemporalQueryRewriter` extracts temporal intent (before/after/at/during/between) from natural language; regex-only by default, optional LLM-assisted mode.

**Ontology** (@KaifAhmad1 @ZohaibHassan16)

- **SHACL Shape Generation & Validation** (PR #318) — `SHACLGenerator` derives SHACL node/property shapes from any ontology dict; three quality tiers (basic/standard/strict); Turtle/JSON-LD/N-Triples output; iterative multi-level inheritance propagation, cycle-safe; `OntologyEngine.to_shacl()`, `export_shacl()`, `validate_graph(explain=True)`; `SHACLValidationReport` with plain-English explanations for all 7 constraint types. `pip install semantica[shacl]`.
- **SKOS Vocabulary Module** (PR #319) — `TripletStore.add_skos_concept()` / `get_skos_concepts(scheme_uri)`; `OntologyEngine.list_vocabularies()`, `list_concepts()`, `search_concepts()`; `NamespaceManager.get_skos_uri()` / `build_concept_scheme_uri()`; SPARQL injection hardened.
- **Ontology Alignment API** (PR #361) — `OntologyEngine.create_alignment()`, `get_alignments()`, `list_alignments()`; OWL/SKOS standard predicates (`owl:equivalentClass`, all five `skos:*Match`); `ReuseManager.suggest_alignments()`; `QueryEngine.expand_entity_uri(use_alignments=True)` with SPARQL `VALUES` clause injection; SPARQL injection hardened.
- **Ontology Diff & Migration** (PR #367) — `VersionManager.diff_ontologies()` covering classes/properties/individuals/axioms; `ChangeLogAnalyzer.analyze()` classifying CRITICAL/HIGH/MEDIUM/INFO impact; `ImpactReport`, `generate_change_report()`; `OntologyEngine.compare_versions()` end-to-end orchestrator with optional validation and graph-instance checks.

**Knowledge Explorer API** (@ZohaibHassan16 @KaifAhmad1)

- **Full FastAPI backend** (PR #384) — `semantica.explorer` package with graph, analytics, decisions, temporal, enrichment, export/import, annotations routes; 12 export formats; WebSocket progress for import; 99 integration tests. `pip install semantica[explorer]`; CLI: `semantica-explorer --graph my_graph.json`.
- **Thread safety** (PR #385) — `ContextGraph` and `GraphSession` protected with `threading.RLock`; 8 analytics components lazily initialized under lock.
- **In-memory fallbacks** (PR #386) — All 7 `DecisionQuery` and 4 `DecisionRecorder` methods have `ContextGraph` fallback paths for in-memory usage without a graph DB.
- **Snapshot schema compatibility** (PR #393) — accepts both `nodes`/`edges` and `entities`/`relationships` snapshot schemas transparently; metadata counts always accurate.
- **Audit trail & rollback protection** (PR #394) — mutation-level audit tracking, named version tags, `restore_snapshot()` requires explicit confirmation, `get_node_history()`, `diff()` Git-like alias.
- **SKOS Vocabulary REST API** (PR #426) — `GET /api/vocabulary/schemes`, `GET /api/vocabulary/hierarchy?scheme=<uri>` with cycle detection, `POST /api/vocabulary/import` (.ttl/.rdf/.owl; HTTP 422 on invalid).
- **O(N) → O(limit) Pagination** (PR #431) — `find_nodes`/`find_edges` use `itertools.islice` on generators; ghost-node fix (accepts `source_id`/`target_id` and `source`/`target` key names); deterministic page boundaries via `sorted()`; `stats()` applies same validity filters as pagination.
- **Named graph support** (PR #432, @Sameer6305) — `enable_named_graphs` flag forwarded correctly through `TripletStore.execute_query()`; duplicate `FROM`/`FROM NAMED` clauses prevented; graph URIs percent-encoded in DROP statements.

**Integrations**

- **Agno Agentic Framework** (Issue #249, @KaifAhmad1) — 5 components, all degrading gracefully when `agno` is not installed:
  - `AgnoContextStore` — graph-backed agent memory implementing `agno.memory.db.base.MemoryDb`.
  - `AgnoKnowledgeGraph` — multi-hop GraphRAG knowledge base implementing `agno.knowledge.base.AgentKnowledge`.
  - `AgnoDecisionKit` — 6 decision-intelligence tools (record_decision, find_precedents, trace_causal_chain, analyze_impact, check_policy, get_decision_summary).
  - `AgnoKGToolkit` — 7 KG pipeline tools (extract_entities, extract_relations, add_to_graph, query_graph, find_related, infer_facts, export_subgraph).
  - `AgnoSharedContext` — team coordinator with single shared `ContextGraph`; `bind_agent(role)` returns role-scoped view; thread-safe via `RLock`.
  - 110 integration tests; 3 cookbook notebooks. `pip install semantica[agno]`.
- **Novita AI Provider** (PR #374, @Alex-wuhu) — OpenAI-compatible; default model `deepseek/deepseek-v3.2`; `NOVITA_API_KEY`; `create_provider("novita")`.

**Reasoning**

- **Native Datalog Reasoning Engine** (PR #371, @ZohaibHassan16) — pure-Python bottom-up semi-naive fixpoint with guaranteed termination; recursive Horn clause rules (e.g. `ancestor(X,Y) :- parent(X,Z), ancestor(Z,Y).`); O(1) delta-index lookup; `load_from_graph(ContextGraph)`; `query("pred(?X, ?Y)")` with optional `bindings=`; `DatalogReasoner`, `DatalogFact`, `DatalogRule` exported from `semantica.reasoning`.

### Fixed

- **Pattern Matcher restored** (PR #387, @ZohaibHassan16) — dead code silently overwrote `_match_pattern` regex (pre-bound variable embedding, repeated-variable backreferences) with `re.escape`, breaking transitivity/symmetry/self-join rules; removed. `re.error` now surfaced instead of swallowed.
- **OllamaProvider base_url ignored** (PR #408, @AlexeyMyslin) — `ollama.Client(host=self.base_url)` instead of raw module assignment; remote Ollama servers now reachable.
- **spaCy runtime fallback** — `NERExtractor` now catches runtime initialization failures, not just missing-model errors.
- **CentralityCalculator crash** — `_build_adjacency()` handles both ContextGraph dataclass edges (`source_id`/`target_id`) and plain dicts.
- **`find_path` always used BFS** (PR #384) — algorithm query param now correctly dispatched to `dijkstra_shortest_path` or `bfs_shortest_path`.
- **Event loop blocked in `/api/enrich/links`** (PR #385) — `score_link` scoring loop wrapped in `asyncio.to_thread`.
- **Temp file leak in `export_graph`** (PR #384) — `try/finally` cleanup for all error paths.
- **`ChangeCategory` enum typo** (PR #367) — `"potenitally_breaking"` → `"potentially_breaking"`.
- **DecisionQuery/DecisionRecorder fallbacks** (PR #386) — `type()` guard instead of `isinstance()` for Mock safety; flat property storage in `_store_decision_node`; spurious `properties={}` kwarg removed; tz-aware/naive datetime mismatch resolved; `find_edges()` hoisted out of BFS loop (O(nodes×edges) → O(1) per call).
- **Snapshot schema** (PR #393) — silent restore failures when `nodes`/`edges` schema didn't match legacy `entities`/`relationships` expectations.
- **Context explainability** (@KaifAhmad1) — decision nodes now store full `scenario`/`reasoning` text; causal/precedent reconstruction returns enriched `Decision` objects; `PolicyEngine.get_affected_decisions()` consistent across Cypher and fallback branches.

### Security

- **CWE-312/359/532** — Removed `api_key` debug `print` blocks from `relation_extractor.py` and `triplet_extractor.py`.
- **CWE-20** — URL sanitization: `"url" in urls` replaced with `any(url == "url" for url in urls)`, eliminating substring match.
- **CI overpermissions** — `permissions: contents: read` added to `benchmark.yml` and `security.yml`.
- **SHACL path traversal** (PR #318) — replaced `len < 500 and "\n" not in s` heuristic with `os.path.exists()`.
- **SHACL inheritance mutation** (PR #318) — `_propagate_inheritance` uses `dataclasses.replace()` instead of appending parent `PropertyShape` objects by reference.
- **SPARQL injection** (PR #361) — `search_concepts`, `list_alignments`, `build_values_clause` fully hardened.

---

## [0.3.0] - 2026-03-10

### Added

- **Context Graph Feature Completeness** (@KaifAhmad1):
  - `ContextNode` / `ContextEdge` gain `valid_from` / `valid_until` with `is_active(at_time) -> bool`.
  - `ContextGraph.find_active_nodes(node_type, at_time)` — temporal node filtering.
  - `get_neighbors(min_weight)` — confidence-filtered BFS (default 0.0 passes all edges).
  - `link_graph()` / `navigate_to()` / `resolve_links(registry)` — cross-graph navigation with full save/load round-trip.
  - `graph_id` UUID field persisted to JSON.

### Fixed

- `is_active()` tz-aware/naive datetime normalization.
- `valid_from`/`valid_until` serialization in `add_nodes()`, `add_edges()`, `to_dict()`, `from_dict()`.
- Cross-graph link phantom-node prevention in `link_graph()`.
- `pipeline_builder.add_step()` return type annotation.
- `test_hybrid_search_performance` timing computation; threshold raised to < 5.0 s.
- **ProvenanceTracker** added to `semantica/kg/__init__.py` exports.
- Duplicate relation creation in `_parse_relation_result` — orphaned legacy block removed.
- `extraction_method` parameter added; typed path now correctly sets `"llm_typed"`.
- Cross-test cache pollution in `test_retry_logic.py` — `_result_cache.clear()` added to `setUp()`.
- 14 tests in `tests/context/test_cross_graph_navigation.py`; 85 real-world tests in `tests/test_030_realworld_comprehensive.py`.

---

## [0.3.0-beta] - 2026-03-07

### Added

- **Multi-Founder LLM Extraction** (PR #354, @KaifAhmad1):
  - `_parse_relation_result`: unmatched subjects/objects produce a synthetic `UNKNOWN` entity instead of being silently dropped.
  - `_match_pattern` rewritten: splits on `?var` placeholders, pre-bound variable resolution, repeated-variable backreferences.
- **TTL Export Aliases** (PR #355, @KaifAhmad1) — `format="ttl"/"nt"/"xml"/"rdf"/"json-ld"` resolve correctly before format validation; 8 tests in `tests/export/test_rdf_exporter.py`.
- **Incremental/Delta Processing** (PR #349, @ZohaibHassan16) — native delta computation between graph snapshots via SPARQL, delta-aware pipeline execution (`delta_mode`), snapshot retention with `prune_versions()`, significant performance improvements for near real-time pipelines.
- **Deduplication v2**:
  - **Candidate Generation v2** (PR #338, @ZohaibHassan16) — multi-key blocking, phonetic (Soundex) blocking, deterministic candidate budgeting; 63.6% faster (0.259 s → 0.094 s for 100 entities).
  - **Two-Stage Scoring Prefilter** (PR #339, @ZohaibHassan16) — type mismatch, length ratio, token overlap gates; 18–25% faster batch processing.
  - **Semantic Relationship Deduplication v2** (PR #340, @ZohaibHassan16) — predicate synonym mapping (`works_for` → `employed_by`), O(1) hash matching, weighted scoring (60% predicate + 40% object); 6.98x speedup (~83 ms vs ~579 ms).
  - **Migration Guide** (PR #344, @ZohaibHassan16) — comprehensive MIGRATION_V2.md; critical infinite recursion bug in `dedup_triplets()` fixed.
- **ArangoDB AQL Export** (PR #342, @tibisabau) — AQL INSERT generation, configurable collections, batch processing (default 1 000), `.aql` auto-detection, 17 tests.
- **Apache Parquet Export** (PR #343, @tibisabau) — columnar storage, configurable compression (snappy/gzip/brotli/zstd/lz4/none), explicit Arrow schemas, `.parquet` auto-detection, 25 tests.

### Fixed

- **Test Suite Fixes** (@KaifAhmad1):
  - Context: entity extraction gated on `use_hybrid_search=True`; `_extract_entities_from_query` uses `word[0].isupper()`; added `expand_context` BFS method; `hybrid_retrieval` and `multi_hop_context_assembly` corrected; vector result fallback to `metadata["content"]`.
  - KG: `calculate_pagerank` aliases; `community_detector._to_networkx` no longer silently loses edges; `_build_adjacency` handles both `"edges"` and `"relationships"` keys; 9 tracking methods added to `AlgorithmTrackerWithProvenance`.
  - Pipeline: retry loop honours `max_retries`; `FailureHandler.handle_failure()` added; `add_step` return type fixed; `validate` alias added; error message standardized.
  - Tests: emoji replaced with ASCII for Windows cp1252 compatibility.
- `NameError`: missing `Type` import in `utils/helpers.py`.

---

## [0.3.0-alpha] - 2026-02-19

### Added

- **Decision Tracking System** — complete lifecycle management (record → analyze → query → precedent → influence) with audit trails and provenance tracking.
- **Advanced KG Algorithms** — Node2Vec embeddings, centrality analysis, community detection for decision insights.
- **Enhanced Context Module** — unified `AgentContext` with granular feature flags for decision tracking, KG algorithms, and vector store features.
- **Vector Store Features** — hybrid search combining semantic, structural, and category similarity.
- **Policy Management** — versioning, compliance checking, and exception handling.
- **Context Engineering Enhancement** (PR #307, @KaifAhmad1) — full decision tracking, hybrid search, `PolicyException` model, `GraphStore` validation, explainable AI features, 9 critical bug fixes, 100% test coverage (9/9).
- **PgVector Store Support** (PR #303, @Sameer6305 @KaifAhmad1) — HNSW/IVFFlat indexing, JSONB metadata filtering, psycopg3/psycopg2 fallback, SQL injection protection via `psycopg_sql.SQL()`, 36+ tests.
- **Apache AGE Backend** (PR #311, @Sameer6305) — `AgeStore` with `GraphStore` API compatibility, SQL injection protection.
- **Improved Vector Store for Decision Tracking** (PR #293, @KaifAhmad1) — `DecisionEmbeddingPipeline`, `HybridSimilarityCalculator` (0.7 semantic + 0.3 structural), `DecisionContext`, `ContextRetriever` with multi-hop reasoning; 34+ tests.
- **Improved Graph Algorithms** (PR #292, @KaifAhmad1) — 30+ algorithms across 7 categories (Node2Vec, Dijkstra, A*, PageRank, Louvain, Leiden, etc.), unified provenance tracking with `GraphBuilderWithProvenance` / `AlgorithmTrackerWithProvenance`.
- **ResourceScheduler Deadlock Fix** (PRs #299 #301, @d4ndr4d3 @KaifAhmad1) — `threading.Lock` → `threading.RLock`; allocation validation; leak prevention on failure; 6 regression tests.
- **Dependabot & Security Automation** — bi-weekly security updates, automated Bandit/Safety/Semgrep scans, security-critical package grouping.

### Fixed

- Context Graphs decision tracking bugs (PR #315, @KaifAhmad1): empty/`None` decision ID, `None` metadata, causal chain depth logic, nonexistent node handling, `to_dict`/`from_dict` round-trip.
- `PolicyEngine` latest version selection; `AgentContext` fallback robustness and secure logging.
- Import issues in test suite (ProvenanceTracker location); causal analyzer `max_depth` bounds.

---

## [0.2.7] - 2026-02-09

### Added

- **Snowflake Connector** (PR #276, @Sameer6305) — multi-auth (password/OAuth/key-pair/SSO), table and query ingestion, SQL injection prevention, progress tracking, 24 tests. `pip install semantica[db-snowflake]`.
- **Apache Arrow Export** (PR #273, @Sameer6305) — explicit Arrow schemas, entity/relationship export, Pandas/DuckDB compatible, 20 tests.
- **Benchmark Suite** (PR #289, @ZohaibHassan16 @KaifAhmad1) — 137+ benchmarks across all 10 modules, Z-score statistical regression detection, GitHub Actions workflow. CLI: `python benchmarks/benchmark_runner.py`.

---

## [0.2.6] - 2026-02-03

### Added

- **W3C PROV-O Provenance Tracking** (Issues #254 #246, @KaifAhmad1):
  - Comprehensive provenance across all 17 Semantica modules; InMemory/SQLite backends; SHA-256 integrity.
  - FDA 21 CFR Part 11, SOX, HIPAA, TNFD compliance infrastructure.
  - 237 tests; opt-in (`provenance=False` by default).
- **Enhanced Change Management** (Issues #248 #243, @KaifAhmad1):
  - `TemporalVersionManager` and `OntologyVersionManager` with SQLite/in-memory backends; SHA-256 checksums; detailed diffs.
  - 104 tests; 17.6 ms for 10 k entities; 510+ ops/sec concurrent.
- **CSV Ingestion Enhancements** (PR #244, @saloni0318) — auto-detect encoding (chardet) and delimiter (csv.Sniffer); tolerant decoding; optional chunked reading.
- **Ingest Unit Tests** (Issues #239 #232, @Mohammed2372) — file, web, and feed ingestors; 998 lines of tests; 80–86% coverage.
- TextNormalizer comprehensive unit tests (PR #242, @ZohaibHassan16).

### Fixed

- **Temperature Compatibility** (Issues #256 #252, @F0rt1s @IGES-Institut) — `temperature=None` now omits parameter so APIs use model defaults; `_add_if_set` helper applied to all 5 providers; 10 tests.
- **JenaStore Empty Graph** (Issues #257 #258, @ZohaibHassan16) — `if self.graph is None:` replaces implicit falsy check in 5 methods.

---

## [0.2.5] - 2026-01-27

### Added

- **Pinecone Vector Store** (closes #219 #220) — serverless and pod-based indexes, namespace support, metadata filtering, unified `VectorStore` integration.
- **Configurable LLM Retry Logic** — `max_retries` parameter (default 3) in `NERExtractor`, `RelationExtractor`, `TripletExtractor`, and all `extract_*_llm` methods.
- **Bring Your Own Model (BYOM)** — custom HuggingFace models in all extractors; custom tokenizer support; runtime `model=` overrides config defaults.
- **Enhanced NER** — configurable aggregation strategies (simple/first/average/max); IOB/BILOU parsing for raw model outputs; confidence scoring.
- **Relation Extraction** — entity marker technique (`<subj>`/`<obj>` tags) for sequence classification models; structured output parsing.
- **Triplet Extraction** — Seq2Seq model support (REBEL) for direct structured triplet generation from text.

### Fixed

- LLM extraction: strict `max_retries` enforcement prevents infinite retry loops.
- Model parameter precedence: runtime arguments now correctly override config defaults in HuggingFace extractors.
- Circular imports in test suites.

---

## [0.2.4] - 2026-01-22

### Added

- **Ontology Ingestion Module** — `OntologyIngestor` for Turtle/RDF-XML/JSON-LD/N3 files; `ingest_ontology()` convenience function; recursive directory scanning; `OntologyData` dataclass; integrated into `ingest(source_type="ontology")`.

---

## [0.2.3] - 2026-01-20

### Added

- Amazon Neptune dev environment — CloudFormation template; `cfn-lint` in pre-commit.
- Vector Store high-performance ingestion — `VectorStore.add_documents()` with batching and parallel processing (`max_workers=6`); `VectorStore.embed_batch()` helper.
- LLM relation extraction tests (mocked and Groq integration).

### Changed

- Simplified relation extraction parameter interface; improved error handling and verbose logging.
- Standardized `VectorStore` concurrency defaults; implicit `max_workers=6` in examples.

### Fixed

- **LLM Relation Extraction Parsing** — normalized typed responses to consistent dict format before parsing; structured JSON fallback; extra kwargs removed from internals.
- **Pipeline Circular Import** (Issues #192 #193) — lazy-loaded `PipelineValidator` inside `PipelineBuilder.__init__`; `TYPE_CHECKING` guard.
- **JupyterLab Progress** (Issue #181) — `SEMANTICA_DISABLE_JUPYTER_PROGRESS` env var suppresses rich progress tables.

---

## [0.2.2] - 2026-01-15

### Added

- **Parallel Extraction Engine** — `concurrent.futures.ThreadPoolExecutor` across all extractors (`NERExtractor`, `RelationExtractor`, `TripletExtractor`, `EventDetector`, `SemanticNetworkExtractor`); `max_workers` parameter; thread-safe `ProgressTracker`.
- Semantic extract regression suite; real-use-case benchmark script.

### Changed

- **Gemini SDK Migration** — `google-genai` SDK with `google.generativeai` fallback.
- Pinned `opentelemetry-api`/`-sdk` to 1.37.0; updated `protobuf`/`grpcio` constraints.
- Entity filtering applied only to LLM prompt construction, not non-LLM flows.
- Raised global `optimization.max_workers` default to 8.

### Security

- **Credential sanitization** — hardcoded API keys removed from 8 notebooks; `ExtractionCache` excludes `api_key`/`token`/`password` from cache keys; cache key hashing upgraded MD5 → SHA-256.

### Performance

- ~1.89× speedup via parallel extraction (Groq `llama-3.3-70b-versatile`, standard datasets).
- Optimized entity matching: exact/substring/word-boundary fast paths before embedding similarity.

---

## [0.2.1] - 2026-01-12

### Fixed

- **LLM Output Stability** (Bug #176) — correct `max_tokens` propagation; automatic chunk-halving and retry on context/output limit errors.
- Removed hardcoded `max_length` constraints from `Entity`, `Relation`, `Triplet`.
- Orchestrator lazy property initialization and configuration normalization.
- `AssertionError` in orchestrator tests (mock alignment).
- Pinned `protobuf>=5.29.1,<7.0`, `grpcio>=1.71.2`; added `GitPython` and `chardet` to `pyproject.toml`.

### Changed

- Increased default `max_text_length` to 64 000 characters for all major providers.
- Standardized Groq defaults: `llama-3.3-70b-versatile`, 64 k context, native `max_tokens`/`max_completion_tokens`.

---

## [0.2.0] - 2026-01-10

### Added

- **Amazon Neptune Support** — `AmazonNeptuneStore` via Bolt/OpenCypher; `NeptuneAuthTokenManager` with AWS IAM SigV4 signing; retry/backoff. `pip install semantica[graph-amazon-neptune]`.
- **Docling Integration** — `DoclingParser` for PDF/DOCX/PPTX/XLSX/HTML/image parsing; OCR support; Markdown/HTML/JSON export.
- **Robust Extraction Fallbacks** — ML/LLM → Pattern → Last Resort chains across all extractors.
- **Provenance & Tracking** — `batch_index` and `document_id` metadata on all extracted items.
- **Semantic Extract** — auto-chunking for long text; `silent_fail` parameter; JSON parsing with 3-attempt exponential backoff.
- End-to-end KG pipeline integration tests; `TextEmbedder` model switching tests.

### Changed

- Removed internal dedup logic from extractors (deferred to `semantica/conflicts`).
- Standardized batch processing across all extractors using unified `extract`/`analyze`/`resolve` pattern.
- Clarified weighted confidence scoring (50% Method Confidence + 50% Type Similarity).

### Fixed

- `NameError` in `extraction_validator.py` (missing `Union` import).
- Extractors returning empty lists for valid input when primary methods fail.
- Model switching bug in `TextEmbedder` (state not cleared on model switch). (Issue #160)
- `TypeError: unhashable type: 'Entity'` in `GraphAnalyzer`. (Issue #159)
- Pinned `protobuf==4.25.3`, `grpcio==1.67.1`.
- `TripletExtractor.validate_triplets` shadowed by internal attribute.
- Incorrect `TextSplitter` import path.

---

## [0.1.1] - 2026-01-05

### Added

- Exported `DoclingParser` and `DoclingMetadata` from `semantica.parse`.
- Windows-specific troubleshooting note for PyTorch DLL issues.

### Fixed

- `DoclingParser` import/export across platforms (Windows, Linux, Google Colab).
- Error messaging when optional `docling` dependency is missing.
- Versioning inconsistencies across the framework.

---

## [0.1.0] - 2025-12-31

### Added

- Command-line interface (`semantica` CLI) with knowledge base building and info commands.
- FastAPI-based REST API server for remote access.
- Background worker component for scalable task processing.
- Framework-level versioning configuration for PyPI distribution.
- Automated release workflow with Trusted Publishing support.

### Changed

- Updated versioning across the framework to 0.1.0.
- Refined entry point configurations in `pyproject.toml`.
- Improved lazy module loading for core components.

---

## [0.0.5] - 2025-11-26

### Changed

- Configured Trusted Publishing for secure automated PyPI deployments.

---

## [0.0.4] - 2025-11-26

### Changed

- Fixed PyPI deployment issues from v0.0.3.

---

## [0.0.3] - 2025-11-25

### Added

- Comprehensive issue templates (Bug, Feature, Documentation, Support, Grant/Partnership).
- Updated pull request template with clear guidelines.
- Community support documentation (`SUPPORT.md`).
- Funding and sponsorship configuration (`FUNDING.yml`).
- 10+ domain-specific cookbook examples (Finance, Healthcare, Cybersecurity, etc.).

### Changed

- Simplified CI/CD workflows — removed failing tests and strict linting.
- Combined release and PyPI publishing into single workflow.
- Simplified security scanning to weekly pip-audit only.

### Removed

- Redundant scripts folder (8 shell/PowerShell scripts).
- Unnecessary automation workflows (label-issues, mark-answered).
- Excessive issue templates.

---

## [0.0.2] - 2025-11-25

### Changed

- Updated README with streamlined content and better examples.
- Added more notebooks to cookbook.
- Improved documentation structure.

---

## [0.0.1] - 2024-01-XX

### Added

- Core framework architecture.
- Universal data ingestion (multiple file formats).
- Semantic intelligence engine (NER, relation extraction, event detection).
- Knowledge graph construction with entity resolution.
- 6-stage ontology generation pipeline.
- GraphRAG engine for hybrid retrieval.
- Multi-agent system infrastructure.
- Production-ready quality assurance modules.
- Comprehensive documentation with MkDocs.
- Cookbook with interactive tutorials.
- Multiple vector store backends (Weaviate, Qdrant, FAISS).
- Multiple graph database backends (Neo4j, NetworkX, RDFLib).
- Temporal knowledge graph support.
- Conflict detection and resolution; deduplication and entity merging.
- Schema template enforcement; seed data management.
- Multi-format export (RDF, JSON-LD, CSV, GraphML).
- Visualization tools; pipeline orchestration.
- Streaming support (Kafka, RabbitMQ, Kinesis).
- Context engineering for AI agents; reasoning and inference engine.

---

## Types of Changes

| Label | Meaning |
|-------|---------|
| **Added** | New features |
| **Changed** | Changes in existing functionality |
| **Deprecated** | Soon-to-be removed features |
| **Removed** | Removed features |
| **Fixed** | Bug fixes |
| **Security** | Vulnerability fixes |
| **Performance** | Performance improvements |

---

For detailed release notes, see [GitHub Releases](https://github.com/Hawksight-AI/semantica/releases).
