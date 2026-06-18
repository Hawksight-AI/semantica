---
title: "Temporal Intelligence"
description: "Bi-temporal facts, point-in-time snapshots, Allen interval algebra, temporal pattern detection, and natural-language temporal parsing for time-aware knowledge graphs."
icon: "clock"
---

Temporal Intelligence gives your knowledge graph a complete understanding of *when* — not just what is true, but when it was true in the real world, when it was recorded, and how facts have evolved over time.

Shipped across **v0.3.0** (context temporal validity) and **v0.4.0** (full temporal stack), the system covers five layers:

<div style={{display:"flex",flexWrap:"wrap",gap:"1.5rem",margin:"1.5rem 0"}}>
  <div style={{flex:"1 1 180px",padding:"1.25rem 1.5rem",borderRadius:"10px",border:"1px solid rgba(16,185,129,0.25)",background:"rgba(16,185,129,0.04)"}}>
    <div style={{fontSize:"1.1rem",fontWeight:700,color:"#10B981",marginBottom:"6px"}}>Bi-temporal model</div>
    <div style={{fontSize:"0.82rem",color:"rgba(255,255,255,0.6)",lineHeight:1.5}}>Valid time + transaction time on every fact</div>
  </div>
  <div style={{flex:"1 1 180px",padding:"1.25rem 1.5rem",borderRadius:"10px",border:"1px solid rgba(16,185,129,0.25)",background:"rgba(16,185,129,0.04)"}}>
    <div style={{fontSize:"1.1rem",fontWeight:700,color:"#10B981",marginBottom:"6px"}}>Point-in-time queries</div>
    <div style={{fontSize:"0.82rem",color:"rgba(255,255,255,0.6)",lineHeight:1.5}}>Reconstruct any historical graph state in one call</div>
  </div>
  <div style={{flex:"1 1 180px",padding:"1.25rem 1.5rem",borderRadius:"10px",border:"1px solid rgba(16,185,129,0.25)",background:"rgba(16,185,129,0.04)"}}>
    <div style={{fontSize:"1.1rem",fontWeight:700,color:"#10B981",marginBottom:"6px"}}>Allen interval algebra</div>
    <div style={{fontSize:"0.82rem",color:"rgba(255,255,255,0.6)",lineHeight:1.5}}>All 13 temporal relations, deterministic reasoning</div>
  </div>
  <div style={{flex:"1 1 180px",padding:"1.25rem 1.5rem",borderRadius:"10px",border:"1px solid rgba(16,185,129,0.25)",background:"rgba(16,185,129,0.04)"}}>
    <div style={{fontSize:"1.1rem",fontWeight:700,color:"#10B981",marginBottom:"6px"}}>NL temporal parsing</div>
    <div style={{fontSize:"0.82rem",color:"rgba(255,255,255,0.6)",lineHeight:1.5}}>Zero LLM calls — pure regex + dateutil</div>
  </div>
</div>


## Exported Classes

| Class | Role |
| :---- | :---- |
| `BiTemporalFact` | Dataclass wrapping `valid_from`, `valid_until`, `recorded_at`, `superseded_at`. Factory: `BiTemporalFact.from_relationship(rel_dict)` |
| `TemporalBound` | Enum sentinel for open-ended intervals. Single value: `TemporalBound.OPEN` |
| `TemporalInterval` | Frozen dataclass `(start: datetime, end: datetime \| TemporalBound, label?)` used by `TemporalReasoningEngine` |
| `IntervalRelation` | Enum of all 13 Allen relation labels (`BEFORE`, `AFTER`, `MEETS`, etc.) |
| `TemporalGraphQuery` | Point-in-time snapshots, range queries, pattern detection, evolution analysis, temporal path finding |
| `TemporalPatternDetector` | Sequence and cycle pattern detection over temporal edges |
| `TemporalReasoningEngine` | Allen interval algebra over `TemporalInterval` objects — pure Python, deterministic |
| `TemporalNormalizer` | Parse NL temporal expressions to `(datetime, datetime)` tuples — zero LLM calls |
| `TemporalQueryRewriter` | Extract temporal intent from free-text queries; returns `TemporalQueryResult` |
| `TemporalQueryResult` | Dataclass output of `TemporalQueryRewriter.rewrite()` |
| `TemporalVersionManager` | Create, list, compare, and apply revisions to versioned graph snapshots |


## Quick Start

<Steps>
  <Step title="Build a time-aware graph">
    Attach `valid_from` / `valid_until` to any relationship at construction time:

    ```python
    from semantica.kg import GraphBuilder

    builder = GraphBuilder()
    kg = builder.build(sources=[{
        "entities": [
            {"id": "alice",     "type": "Person"},
            {"id": "acme_corp", "type": "Organization"},
            {"id": "beta_ltd",  "type": "Organization"},
        ],
        "relationships": [
            {
                "source": "alice", "target": "acme_corp", "type": "ceo_of",
                "valid_from":  "2018-01-01",
                "valid_until": "2022-06-01",
            },
            {
                "source": "alice", "target": "beta_ltd", "type": "ceo_of",
                "valid_from":  "2022-06-01",
                # No valid_until → open-ended (TemporalBound.OPEN)
            },
        ],
    }])
    ```
  </Step>
  <Step title="Query the graph at a point in time">
    `TemporalGraphQuery` takes constructor args; pass the graph into each query call:

    ```python
    from semantica.kg import TemporalGraphQuery

    query = TemporalGraphQuery(temporal_granularity="day")

    # query_at_time is the primary public API
    result_2020 = query.query_at_time(kg, query="", at_time="2020-06-15")
    result_2023 = query.query_at_time(kg, query="", at_time="2023-01-01")

    print(f"Rels active in 2020: {result_2020['num_relationships']}")
    print(f"Rels active in 2023: {result_2023['num_relationships']}")
    ```
  </Step>
  <Step title="Reconstruct a subgraph at a specific timestamp">
    `reconstruct_at_time()` is the low-level primitive — returns a full graph dict
    with only nodes and edges that were valid at the given moment:

    ```python
    snapshot = query.reconstruct_at_time(kg, "2021-06-15")
    # snapshot has "entities" and "relationships" keys
    # usable with all GraphAnalyzer, PathFinder, CommunityDetector calls
    ```
  </Step>
  <Step title="Create versioned snapshots">
    ```python
    from semantica.kg import TemporalVersionManager

    versioner = TemporalVersionManager()          # in-memory storage
    # versioner = TemporalVersionManager(storage_path="versions.db")  # SQLite

    versioner.create_snapshot(
        kg,
        version_label="2024-Q1",
        author="user@example.com",
        description="Q1 2024 snapshot after board restructure",
    )

    for v in versioner.list_versions():
        print(f"{v['label']:12s}  {v['author']}  {v['timestamp']}")
    ```
  </Step>
</Steps>


## The Bi-Temporal Model

Most systems track only one timeline: when something is currently true. Bi-temporal graphs track **two independent timelines** simultaneously:

<Tabs>
  <Tab title="Valid Time">
    *When was the fact true in the real world?*

    - `valid_from` — date the fact became true
    - `valid_until` — date the fact ceased to be true. Omit (or use `TemporalBound.OPEN`) for currently-active facts

    ```python
    from semantica.kg import BiTemporalFact, TemporalBound

    # Create from an existing relationship dict
    rel = {
        "source": "alice", "target": "acme_corp", "type": "ceo_of",
        "valid_from":  "2018-01-01",
        "valid_until": "2022-06-01",
    }
    fact = BiTemporalFact.from_relationship(rel)

    print(fact.valid_from)   # datetime(2018, 1, 1, tzinfo=utc)
    print(fact.valid_until)  # datetime(2022, 6, 1, tzinfo=utc)

    # Serialize back to dict fields
    fields = fact.to_relationship_fields()
    print(fields["valid_from"])   # "2018-01-01T00:00:00Z"
    print(fields["valid_until"])  # "2022-06-01T00:00:00Z"
    ```
  </Tab>
  <Tab title="Transaction Time">
    *When did we record this fact in the system?*

    - `recorded_at` — auto-stamped at ingestion time (defaults to `datetime.now(utc)`)
    - `superseded_at` — set when a later version replaces this record. `TemporalBound.OPEN` means still current

    ```python
    rel = {
        "source": "alice", "target": "acme_corp", "type": "ceo_of",
        "valid_from":    "2018-01-01",
        "valid_until":   "2022-06-01",
        "recorded_at":   "2018-01-05T09:32:00Z",
        "superseded_at": None,   # still the current record
    }
    fact = BiTemporalFact.from_relationship(rel)

    print(fact.recorded_at)    # datetime(2018, 1, 5, 9, 32, tzinfo=utc)
    print(fact.superseded_at)  # TemporalBound.OPEN
    ```
  </Tab>
  <Tab title="TemporalBound.OPEN">
    `TemporalBound.OPEN` is the single sentinel that represents an open-ended interval — a fact with no defined end date:

    ```python
    from semantica.kg import TemporalBound

    print(TemporalBound.OPEN)          # TemporalBound.OPEN
    print(TemporalBound.OPEN.value)    # "OPEN"

    # A relationship with no valid_until gets TemporalBound.OPEN automatically
    rel = {"source": "alice", "target": "beta_ltd", "type": "ceo_of",
           "valid_from": "2022-06-01"}
    fact = BiTemporalFact.from_relationship(rel)
    print(fact.valid_until)            # TemporalBound.OPEN
    ```

    <Note>
      `TemporalBound.OPEN` replaces both the start and end sentinels — there is only one value. The reasoning engine treats `OPEN` as `datetime.max` (far future) when comparing end bounds, and as `datetime.min` (far past) when used for `superseded_at`.
    </Note>
  </Tab>
</Tabs>


## TemporalGraphQuery — Reference

Constructed once; the graph is passed into each method call:

```python
from semantica.kg import TemporalGraphQuery

query = TemporalGraphQuery(
    enable_temporal_reasoning=True,   # default
    temporal_granularity="day",       # second|minute|hour|day|week|month|year
    max_temporal_depth=None,          # optional max depth
)
```

### Core Methods

| Method | Returns | Description |
| :------ | :------- | :----------- |
| `query_at_time(graph, query, at_time, include_history=False, time_axis="valid")` | `Dict` | Primary API — filter graph to facts valid at `at_time`. Returns `entities`, `relationships`, `num_entities`, `num_relationships` |
| `reconstruct_at_time(graph, at_time, *, time_axis="valid")` | `Dict` | Low-level — returns a deep-copied subgraph valid at `at_time`. Usable with all analytics tools |
| `query_time_range(graph, query, start_time, end_time, temporal_aggregation="union", include_intervals=True, time_axis="valid")` | `Dict` | All relationships active during `[start, end]`. `temporal_aggregation`: `"union"` / `"intersection"` / `"evolution"` |
| `validate_temporal_consistency(graph)` | `TemporalConsistencyReport` | Detect inverted intervals, overlapping same-edge facts, and entity lifetime violations |
| `query_temporal_pattern(graph, pattern, time_window=None, min_support=1)` | `Dict` | Detect `"sequence"` or `"cycle"` patterns. Delegates to `TemporalPatternDetector` |
| `analyze_evolution(graph, entity=None, relationship=None, start_time=None, end_time=None, metrics=None)` | `Dict` | Track evolution metrics (`"count"`, `"diversity"`, `"stability"`) over time |
| `find_temporal_paths(graph, source, target, start_time=None, end_time=None, max_path_length=None, enforce_causal_ordering=True, ordering_strategy="strict")` | `Dict` | BFS paths respecting temporal validity. `ordering_strategy`: `"strict"` / `"overlap"` / `"loose"` |

### `time_axis` Parameter

All query methods accept a `time_axis` parameter controlling which timestamps are used for filtering:

| Value | Effect |
| :---- | :----- |
| `"valid"` (default) | Filter by `valid_from` / `valid_until` — when the fact was true |
| `"transaction"` | Filter by `recorded_at` / `superseded_at` — when we recorded it |
| `"both"` | Fact must be active on both axes simultaneously |

### Range Query Example

```python
# All relationships active at any point in 2021
result = query.query_time_range(kg, "", "2021-01-01", "2021-12-31")
for rel in result["relationships"]:
    print(f"  {rel['source']} --[{rel['type']}]--> {rel['target']}")

# Only relationships valid throughout the entire range (stricter)
result = query.query_time_range(
    kg, "", "2021-01-01", "2021-12-31",
    temporal_aggregation="intersection",
)

# Grouped by calendar period
result = query.query_time_range(
    kg, "", "2021-01-01", "2021-12-31",
    temporal_aggregation="evolution",
)
for period, rels in result["relationship_buckets"].items():
    print(f"  {period}: {len(rels)} relationships active")
```

### Evolution Analysis

```python
evolution = query.analyze_evolution(
    kg,
    entity="alice",            # track a specific entity (None = whole graph)
    relationship="ceo_of",     # track a specific edge type (None = all)
    start_time="2018-01-01",
    end_time="2024-12-31",
    metrics=["count", "diversity", "stability"],
)
print(f"Relationship count:    {evolution['count']}")
print(f"Relationship types:    {evolution['diversity']}")
```

### Temporal Path Finding

```python
paths = query.find_temporal_paths(
    kg,
    source="alice",
    target="beta_ltd",
    start_time="2022-01-01",
    end_time="2024-12-31",
    max_path_length=5,
    enforce_causal_ordering=True,
    ordering_strategy="strict",  # strict|overlap|loose
)
for p in paths["paths"]:
    print(f"  {' → '.join(p['path'])}  (length={p['length']})")
```

### Consistency Validation

```python
from semantica.kg import TemporalGraphQuery

report = TemporalGraphQuery().validate_temporal_consistency(kg)

print(f"Errors:   {len(report.errors)}")
print(f"Warnings: {len(report.warnings)}")

for err in report.errors:
    print(f"  [{err['issue_type']}] fact_id={err['fact_id']}: {err['message']}")
```

Error types reported: `inverted_interval`, `invalid_temporal_fields`, `missing_source_entity`, `missing_target_entity`, `source_lifetime_mismatch`, `target_lifetime_mismatch`.
Warning types: `overlapping_same_edge`, `gap_after_restart`.


## TemporalPatternDetector

Detect recurring temporal patterns across graph edges. Accessed directly or via `TemporalGraphQuery.query_temporal_pattern()`:

```python
from semantica.kg import TemporalPatternDetector

detector = TemporalPatternDetector()

# Find sequential edge patterns (A→B→C where edges are back-to-back)
sequences = detector.detect_temporal_patterns(
    kg,
    pattern_type="sequence",
    min_frequency=2,
    time_window=None,
)

for seq in sequences:
    print(f"Sequence: {seq['signature']}  (occurs {seq['frequency']} times)")
    for occ in seq["occurrences"]:
        print(f"  nodes={occ['nodes']}  {occ['start_time']} → {occ['end_time']}")

# Find cyclic patterns (A→B→C→A)
cycles = detector.detect_temporal_patterns(
    kg,
    pattern_type="cycle",
    min_frequency=1,
)
```

| Parameter | Type | Default | Description |
| :--------- | :---- | :------- | :----------- |
| `pattern_type` | `str` | `"sequence"` | `"sequence"` or `"cycle"` |
| `min_frequency` | `int` | `2` | Minimum occurrences for a pattern to be returned |
| `time_window` | `Any` | `None` | Optional time constraint on pattern window |

Each pattern dict has: `pattern_type`, `signature` (tuple of node IDs), `frequency`, `occurrences` (list with `nodes`, `edges`, `start_time`, `end_time`).


## Allen Interval Algebra

`TemporalReasoningEngine` operates on `TemporalInterval` objects — a frozen dataclass with `start: datetime` and `end: datetime | TemporalBound`:

```python
from semantica.kg import (
    TemporalReasoningEngine, TemporalInterval, IntervalRelation, TemporalBound
)
from datetime import datetime, timezone

def dt(year, month, day):
    return datetime(year, month, day, tzinfo=timezone.utc)

engine = TemporalReasoningEngine()

h1_2020 = TemporalInterval(start=dt(2020, 1, 1), end=dt(2020, 6, 30))
q2_q4   = TemporalInterval(start=dt(2020, 4, 1), end=dt(2020, 12, 31))

relation = engine.relation(h1_2020, q2_q4)
print(relation)                          # IntervalRelation.OVERLAPS
print(relation.value)                    # "overlaps"

print(engine.overlaps(h1_2020, q2_q4))  # True
print(engine.contains(q2_q4, h1_2020))  # False
```

### All 13 Relations

| `IntervalRelation` | `.value` | Inverse | Description |
| :--- | :--- | :--- | :--- |
| `BEFORE` | `"before"` | `AFTER` | A ends strictly before B starts |
| `AFTER` | `"after"` | `BEFORE` | A starts strictly after B ends |
| `MEETS` | `"meets"` | `MET_BY` | A ends exactly when B starts |
| `MET_BY` | `"met_by"` | `MEETS` | A starts exactly when B ends |
| `OVERLAPS` | `"overlaps"` | `OVERLAPPED_BY` | A and B share a period; A starts and ends first |
| `OVERLAPPED_BY` | `"overlapped_by"` | `OVERLAPS` | B starts and ends before A, they share a period |
| `STARTS` | `"starts"` | `STARTED_BY` | Same start time; A ends before B |
| `STARTED_BY` | `"started_by"` | `STARTS` | Same start time; B ends before A |
| `DURING` | `"during"` | `CONTAINS` | A is entirely inside B |
| `CONTAINS` | `"contains"` | `DURING` | B is entirely inside A |
| `FINISHES` | `"finishes"` | `FINISHED_BY` | Same end time; A started after B |
| `FINISHED_BY` | `"finished_by"` | `FINISHES` | Same end time; B started after A |
| `EQUALS` | `"equals"` | *(self-inverse)* | Identical interval |

### Additional Engine Methods

| Method | Returns | Description |
| :------ | :------- | :----------- |
| `active_at(interval, timestamp, granularity=None)` | `bool` | Is `timestamp` within `interval`? |
| `merge_intervals(intervals)` | `List[TemporalInterval]` | Merge overlapping/touching intervals |
| `gap_analysis(intervals, domain_start, domain_end)` | `List[TemporalInterval]` | Find uncovered gaps within a domain |
| `coverage_percentage(intervals, domain_start, domain_end)` | `float` | Fraction of domain covered by intervals |
| `timeline_of(entity_id, graph)` | `List[Dict]` | Sorted event timeline for an entity |
| `retroactive_coverage(revision, original_facts)` | `Dict` | Classify facts as `affected`, `partial`, or `unaffected` by a revision |
| `normalize_timestamp(timestamp, granularity)` | `datetime` | Truncate timestamp to granularity |
| `normalize_interval(start, end, granularity)` | `TemporalInterval` | Parse and expand interval to granularity boundaries |

### Advanced: Interval Operations

```python
from datetime import datetime, timezone

def dt(y, m, d): return datetime(y, m, d, tzinfo=timezone.utc)

intervals = [
    TemporalInterval(start=dt(2020, 1, 1), end=dt(2020, 6, 30)),
    TemporalInterval(start=dt(2020, 4, 1), end=dt(2020, 12, 31)),
    TemporalInterval(start=dt(2021, 3, 1), end=TemporalBound.OPEN),
]

# Merge overlapping intervals
merged = engine.merge_intervals(intervals)
print(f"Merged into {len(merged)} intervals")

# Find gaps in coverage across 2020
gaps = engine.gap_analysis(intervals, dt(2020, 1, 1), dt(2020, 12, 31))
print(f"Uncovered gaps: {len(gaps)}")

# Coverage fraction
pct = engine.coverage_percentage(intervals, dt(2020, 1, 1), dt(2021, 12, 31))
print(f"Coverage: {pct:.1%}")

# Entity timeline (all add/modify/remove events sorted by time)
timeline = engine.timeline_of("alice", kg)
for event in timeline:
    print(f"  {event['timestamp'].date()}  {event['change_type']}")
```


## TemporalNormalizer — NL Temporal Parsing

Converts natural-language temporal phrases into `(valid_from, valid_until)` datetime tuples. **Zero LLM calls.** Pure regex + `dateutil.relativedelta`.

```python
from semantica.kg import TemporalNormalizer
from datetime import datetime, timezone

norm = TemporalNormalizer(
    reference_date=datetime(2024, 6, 15, tzinfo=timezone.utc)
)
```

### `normalize(value)` → `Optional[Tuple[datetime, datetime]]`

```python
# ISO 8601 → point interval
result = norm.normalize("2022-03-15")
print(result)
# (datetime(2022, 3, 15, tzinfo=utc), datetime(2022, 3, 15, tzinfo=utc))

# Year → full year span
result = norm.normalize("2022")
print(result)
# (datetime(2022, 1, 1, tzinfo=utc), datetime(2022, 12, 31, tzinfo=utc))

# Quarter → quarter span
result = norm.normalize("Q2 2021")
print(result)
# (datetime(2021, 4, 1, tzinfo=utc), datetime(2021, 6, 30, tzinfo=utc))

# Month + year
result = norm.normalize("January 2022")
print(result)
# (datetime(2022, 1, 1, tzinfo=utc), datetime(2022, 1, 31, tzinfo=utc))

# YYYY-MM (ISO partial)
result = norm.normalize("2022-03")
print(result)
# (datetime(2022, 3, 1, tzinfo=utc), datetime(2022, 3, 31, tzinfo=utc))

# Relative phrases (requires reference_date)
result = norm.normalize("last quarter")
print(result)
# (datetime(2024, 1, 1, tzinfo=utc), datetime(2024, 3, 31, tzinfo=utc))

result = norm.normalize("last year")
# (datetime(2023, 1, 1, tzinfo=utc), datetime(2023, 12, 31, tzinfo=utc))

# Unparseable → None (never raises, logs debug)
result = norm.normalize("recently")
print(result)   # None
```

<Warning>
  `normalize()` returns `None` for unparseable input — it **never raises** an exception. For relative phrases (`"last quarter"`, `"this year"`, etc.), `reference_date` **must** be set at construction time, otherwise `ValueError` is raised at call time.
</Warning>

### `normalize_phrase(phrase)` → `Optional[Dict]`

Look up a domain-specific temporal phrase in the phrase map:

```python
meta = norm.normalize_phrase("expiry date")
print(meta)
# {"maps_to": "valid_until", "type": "end", "domain": ["Healthcare", "Supply Chain"]}

meta = norm.normalize_phrase("retroactive to")
print(meta)
# {"maps_to": "valid_from", "type": "start", "retroactive": True, "domain": ["Regulatory", "Finance"]}

meta = norm.normalize_phrase("unknown phrase")
print(meta)   # None
```

Built-in domain phrases cover: General/Policy, Healthcare, Cybersecurity, Supply Chain, Finance, and Energy.

### Custom Phrase Map

```python
from datetime import datetime, timezone

def my_grant_window(ref: datetime):
    return (
        datetime(ref.year, 10, 1, tzinfo=timezone.utc),
        datetime(ref.year, 10, 31, tzinfo=timezone.utc),
    )

norm = TemporalNormalizer(
    reference_date=datetime(2024, 1, 1, tzinfo=timezone.utc),
    phrase_map={"grant application window": my_grant_window},
)
start, end = norm.normalize("grant application window")
```

### Supported Expressions

| Pattern | Example | Return type |
| :------- | :------- | :---------- |
| ISO 8601 full date/datetime | `"2022-03-15"`, `"2022-03-15T10:00:00Z"` | Point interval |
| Year only | `"2022"` | Full year span |
| Month + year (word) | `"January 2022"`, `"Jan 2022"` | Full month span |
| YYYY-MM (ISO partial) | `"2022-03"` | Full month span |
| Quarter + year | `"Q2 2021"` | Quarter span |
| Relative (built-in) | `"last year"`, `"last quarter"`, `"this month"`, `"three months ago"`, `"six months ago"`, `"two years ago"` | Computed span |
| Ambiguous slash date | `"03/04/2022"` | `None` + `TemporalAmbiguityWarning` |
| Domain phrase | `"expiry date"`, `"retroactive to"` | Only via `normalize_phrase()` |


## TemporalQueryRewriter

Extract temporal intent from a natural-language query so downstream retrieval can apply deterministic temporal filtering.

**Two modes:** regex-only (no LLM) or LLM-assisted for free-form phrasing.

```python
from semantica.kg import TemporalQueryRewriter

# Regex-only (default — no dependencies beyond standard library)
rewriter = TemporalQueryRewriter()

# LLM-assisted for more complex phrasings
from semantica.llms import Groq
rewriter = TemporalQueryRewriter(
    llm_provider=Groq(model="llama-3.1-8b-instant"),
    reference_date=datetime.now(timezone.utc),
)
```

### `rewrite(query, context=None)` → `TemporalQueryResult`

```python
# "before" intent
r = rewriter.rewrite("which suppliers were certified before 2021?")
print(r.temporal_intent)    # "before"
print(r.at_time.year)       # 2021
print(r.rewritten_query)    # "which suppliers were certified?"
print(r.confidence)         # 0.85

# "between" intent
r = rewriter.rewrite("revenue between Q1 2022 and Q3 2022")
print(r.temporal_intent)    # "between"
print(r.start_time)         # datetime(2022, 1, 1, tzinfo=utc)
print(r.end_time)           # datetime(2022, 9, 30, tzinfo=utc)

# "during" intent
r = rewriter.rewrite("what decisions were made during Q2 2023?")
print(r.temporal_intent)    # "during"
print(r.at_time)            # datetime(2023, 4, 1, tzinfo=utc)

# No temporal phrase
r = rewriter.rewrite("list all active suppliers")
print(r.temporal_intent)    # None
print(r.rewritten_query)    # "list all active suppliers"
print(r.has_temporal_context())  # False
```

### `TemporalQueryResult` Fields

| Field | Type | Description |
| :---- | :---- | :----------- |
| `rewritten_query` | `str` | Original query with the temporal phrase stripped and whitespace normalised |
| `at_time` | `Optional[datetime]` | Point-in-time bound for `before`, `after`, `at`, `during` intents |
| `start_time` | `Optional[datetime]` | Lower bound for `between` queries |
| `end_time` | `Optional[datetime]` | Upper bound for `between` queries |
| `temporal_intent` | `Optional[str]` | One of `"before"`, `"after"`, `"at"`, `"during"`, `"between"`, or `None` |
| `confidence` | `float` | `0.85` for regex extraction; LLM-propagated confidence or `0.75` fallback |

| Method | Returns | Description |
| :------ | :------- | :----------- |
| `has_temporal_context()` | `bool` | `True` if any temporal parameter was extracted |

Supported intent keywords: `before` / `prior to` / `until` / `up to`, `after` / `since` / `following`, `during` / `in` / `within`, `as of` / `at` / `on`, `between … and …`.


## TemporalVersionManager

Create and manage versioned graph snapshots with SHA-256 integrity checking. Supports both **in-memory** (default) and **SQLite persistent** storage.

```python
from semantica.kg import TemporalVersionManager

# In-memory (default)
versioner = TemporalVersionManager()

# SQLite-backed (persists across process restarts)
versioner = TemporalVersionManager(
    storage_path="graph_versions.db",
    version_strategy="timestamp",   # timestamp | incremental | semantic
)
```

### Methods

| Method | Returns | Description |
| :------ | :------- | :----------- |
| `create_snapshot(graph, version_label, author, description)` | `Dict` | Create snapshot with SHA-256 checksum. `author` and `description` are required |
| `create_version(graph, version_label=None, timestamp=None, metadata=None)` | `Dict` | Lightweight version without checksum or mandatory author |
| `list_versions()` | `List[Dict]` | List all stored snapshots |
| `get_version(label)` | `Optional[Dict]` | Retrieve snapshot by label |
| `compare_versions(v1, v2, comparison_metrics=None)` | `Dict` | Detailed entity + relationship diff between two versions or labels |
| `apply_revision(snapshot, revision)` | `Dict` | Temporal revision: supersede matching facts without deleting originals |
| `validate_snapshot(snapshot)` | `bool` | Validate against v1.0 schema (required fields + types) |
| `migrate_snapshot(snapshot)` | `Dict` | Upgrade old-format snapshot to v1.0 |
| `verify_checksum(snapshot)` | `bool` | Integrity check via SHA-256 |

### Snapshot & Diff Example

```python
# Create a snapshot (author and description are required)
snap = versioner.create_snapshot(
    kg,
    version_label="v1.0",
    author="analyst@example.com",
    description="Initial baseline",
)
print(snap["checksum"])  # SHA-256 hex string

# List versions
for v in versioner.list_versions():
    print(f"{v['label']:12s}  {v['author']}  {v['timestamp']}")

# Get a specific version
past = versioner.get_version("v1.0")

# Diff: compare two versions (pass labels or snapshot dicts)
diff = versioner.compare_versions("v1.0", "v2.0")
print(f"Entities added:          {diff['summary']['entities_added']}")
print(f"Entities removed:        {diff['summary']['entities_removed']}")
print(f"Relationships added:     {diff['summary']['relationships_added']}")
print(f"Relationships removed:   {diff['summary']['relationships_removed']}")

# Field-level changes on each modified entity
for change in diff["entities_modified"]:
    print(f"  {change['id']}: {change['changes']}")
```

### Temporal Revision

Apply a revision to specific fact IDs — the originals are **superseded** (not deleted), preserving full audit history:

```python
revision = {
    "fact_ids":       ["alice|ceo_of|acme_corp"],   # relationship key: src|type|target
    "new_valid_from": "2018-03-01",
    "new_valid_until": None,    # None = TemporalBound.OPEN
    "revision_type":  "correction",                  # correction | retroactive
    "author":         "analyst@example.com",
    "reason":         "Original start date was incorrect",
}

revised_snapshot = versioner.apply_revision(snap, revision)
# original fact is preserved with superseded_at set
# replacement fact has new_valid_from, superseded_at = OPEN
```

### Integrity & Migration

```python
# Validate snapshot schema
is_valid = versioner.validate_snapshot(snap)

# Verify checksum integrity
is_intact = versioner.verify_checksum(snap)

# Upgrade old-format snapshot (no format_version field)
upgraded = versioner.migrate_snapshot(old_snap)
```


## Context Graph Temporal Features (v0.3.0)

The `ContextGraph` exposes temporal awareness directly on graph nodes and decisions, available since v0.3.0:

```python
from semantica.context import ContextGraph
from datetime import datetime, timezone

graph = ContextGraph(advanced_analytics=True)

# Add time-bounded nodes
graph.add_node("policy_v1", "policy",
               properties={"text": "All transactions require dual approval"},
               valid_from="2021-01-01",
               valid_until="2023-06-30")

graph.add_node("policy_v2", "policy",
               properties={"text": "Transactions > $50k require dual approval"},
               valid_from="2023-07-01")

# Find nodes active at a specific timestamp
current_policies = graph.find_active_nodes(
    node_type="policy",
    at_time=datetime.now(timezone.utc),
)
for p in current_policies:
    print(p["properties"]["text"])
# → "Transactions > $50k require dual approval"

# Historical query
past_policies = graph.find_active_nodes(
    node_type="policy",
    at_time=datetime(2022, 6, 1, tzinfo=timezone.utc),
)
for p in past_policies:
    print(p["properties"]["text"])
# → "All transactions require dual approval"
```

### Temporal Decision Windows

```python
from semantica.context import AgentContext, ContextGraph
from semantica.vector_store import VectorStore

context = AgentContext(
    vector_store=VectorStore(backend="faiss", dimension=768),
    knowledge_graph=ContextGraph(),
    decision_tracking=True,
)

# Decision superseded after policy change
old_id = context.record_decision(
    category="data_retention", scenario="Set retention window for user PII",
    reasoning="GDPR Article 5(1)(e) limits storage",
    outcome="retain_90_days", confidence=0.98,
    valid_from="2023-01-01", valid_until="2023-06-30",
)

new_id = context.record_decision(
    category="data_retention", scenario="Set retention window for user PII",
    reasoning="Legal confirmed 60-day window after new DPA amendment",
    outcome="retain_60_days", confidence=0.99,
    valid_from="2023-07-01",
)

# Temporal precedent search
old_prec = context.find_precedents("data retention PII", as_of="2023-03-01", limit=3)
new_prec = context.find_precedents("data retention PII", as_of="2024-01-01", limit=3)
```


## Real-World Patterns

<Tabs>
  <Tab title="Personnel & Org Structure">
    ```python
    from semantica.kg import GraphBuilder, TemporalGraphQuery

    builder = GraphBuilder()
    kg = builder.build(sources=[{
        "entities": [
            {"id": "alice",   "type": "Person"},
            {"id": "finteam", "type": "Team"},
        ],
        "relationships": [
            {"source": "alice", "target": "finteam", "type": "leads",
             "valid_from": "2020-01-01", "valid_until": "2022-12-31"},
        ],
    }])

    query = TemporalGraphQuery()

    # Incident in Nov 2022 → who was responsible?
    result = query.query_at_time(kg, "", "2022-11-15")
    leads = [r for r in result["relationships"] if r["type"] == "leads"]
    print(f"Team lead at incident: {leads[0]['source']}")
    ```
  </Tab>
  <Tab title="Policy Evolution">
    ```python
    from semantica.kg import TemporalVersionManager, TemporalGraphQuery

    versioner = TemporalVersionManager(storage_path="policy_history.db")
    versioner.create_snapshot(kg_before, version_label="2023-H1",
                              author="compliance@org.com",
                              description="Pre-July policy baseline")
    versioner.create_snapshot(kg_after, version_label="2023-H2",
                              author="compliance@org.com",
                              description="Post-July amendment")

    diff = versioner.compare_versions("2023-H1", "2023-H2")
    print(f"Policy changes: {diff['summary']['relationships_modified']}")
    ```
  </Tab>
  <Tab title="Consistency Audit">
    ```python
    from semantica.kg import TemporalGraphQuery

    report = TemporalGraphQuery().validate_temporal_consistency(kg)

    if report.errors:
        print("ERRORS (must fix):")
        for e in report.errors:
            print(f"  [{e['issue_type']}] {e['message']} (fact: {e['fact_id']})")

    if report.warnings:
        print("WARNINGS (review):")
        for w in report.warnings:
            print(f"  [{w['issue_type']}] {w['message']} (fact: {w['fact_id']})")
    ```
  </Tab>
  <Tab title="NL Query Rewriting">
    ```python
    from semantica.kg import TemporalQueryRewriter, TemporalGraphQuery

    rewriter = TemporalQueryRewriter()
    query    = TemporalGraphQuery()

    user_query = "Who was responsible for compliance before the 2022 audit?"
    result = rewriter.rewrite(user_query)

    if result.has_temporal_context():
        # Use point-in-time filtering
        snapshot = query.reconstruct_at_time(kg, result.at_time)
    else:
        snapshot = kg

    # Now run your retrieval over snapshot with result.rewritten_query
    print(f"Intent: {result.temporal_intent}")
    print(f"Query:  {result.rewritten_query}")
    ```
  </Tab>
</Tabs>


## Configuration

```yaml
kg:
  temporal:
    enabled: true
    default_validity: infinite        # OPEN when valid_until is omitted
    recorded_at_auto_stamp: true      # auto-fill recorded_at on every ingested fact
    reasoning:
      enabled: true
      granularity: day                # second|minute|hour|day|week|month|year
      engine: allen                   # allen | point_in_time_only
```

- [Knowledge Graph Module](kg) — Core graph construction, `GraphBuilder`, analytics.
- [Context Module](context) — Decision temporal windows and `find_active_nodes()`.
- [Provenance](provenance) — W3C PROV-O lineage stamped alongside temporal metadata.
- [Export](export) — OWL, Turtle, JSON-LD, and Parquet export with temporal annotations.

- [Temporal Knowledge Graphs](https://github.com/semantica-agi/semantica/blob/main/cookbook/advanced/10_Temporal_Knowledge_Graphs.ipynb) — Temporal reasoning and Allen algebra · Advanced
- [Context Module](https://github.com/semantica-agi/semantica/blob/main/cookbook/introduction/19_Context_Module.ipynb) — Including temporal decision windows · Intermediate
