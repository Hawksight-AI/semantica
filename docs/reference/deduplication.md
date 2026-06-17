---
title: "Deduplication Module"
description: "Entity deduplication — similarity scoring, blocking, merging, and cluster-based batch processing."
icon: "copy"
---

**`semantica.deduplication`** detects and merges duplicate entities across sources to produce a **clean, single-source-of-truth** knowledge graph:

- Four v2 strategies up to 7× faster than v1: `blocking_v2`, `hybrid_v2`, `semantic_v2`
- `ClusterBuilder` uses Union-Find and hierarchical clustering for batch deduplication at scale
- `EntityMerger` preserves original source provenance on every merged entity
- `MergeStrategyManager` supports per-property rules and conflict resolution
- All workflows operate on plain Python dicts — no ORM or schema required


## Exported Classes

| Class | Role |
| :--- | :--- |
| `DuplicateDetector` | Pairwise and batch detection — returns `DuplicateCandidate` or `DuplicateGroup` lists |
| `EntityMerger` | Merge duplicate groups — returns `List[MergeOperation]` |
| `SimilarityCalculator` | Multi-factor similarity: string, property, relationship, and embedding |
| `ClusterBuilder` | Union-Find and hierarchical clustering for large-scale batch deduplication |
| `MergeStrategy` | Enum of merge strategies: `KEEP_FIRST`, `KEEP_LAST`, `KEEP_MOST_COMPLETE`, `KEEP_HIGHEST_CONFIDENCE`, `MERGE_ALL` |
| `PropertyMergeRule` | Dataclass holding per-property merge rule: `{property_name, strategy, conflict_resolution, priority}` |
| `MergeStrategyManager` | Manage and apply named merge strategies; accepts per-property rules |
| `detect_duplicates()` | Convenience function — `detect_duplicates(entities, method="pairwise", similarity_threshold=0.7)` |
| `merge_entities()` | Convenience function — `merge_entities(entities, method="keep_most_complete")` |
| `calculate_similarity()` | Convenience function — `calculate_similarity(entity_a, entity_b, method="multi_factor")` |

## What You Get

<CardGroup cols={2}>
  <Card title="DuplicateDetector" icon="copy">
    Pairwise, batch, incremental, and group detection modes. Returns scored candidates with reasons.
  </Card>
  <Card title="EntityMerger" icon="code-merge">
    Five merge strategies — keep first, last, most complete, highest confidence, or merge all fields.
  </Card>
  <Card title="SimilarityCalculator" icon="equals">
    Multi-factor scoring across string edit distance, property overlap, relationship overlap, and embeddings.
  </Card>
  <Card title="ClusterBuilder" icon="diagram-project">
    Union-Find and hierarchical clustering for batch deduplication at scale — handles 100k+ entity sets.
  </Card>
  <Card title="MergeStrategyManager" icon="sliders">
    Per-property merge rules with conflict resolution priorities. Apply different strategies to different fields.
  </Card>
  <Card title="v2 Strategies" icon="bolt">
    `blocking_v2`, `hybrid_v2`, `semantic_v2` — up to 7× faster than v1 for large entity sets.
  </Card>
</CardGroup>


## Getting Started

```python
from semantica.deduplication import DuplicateDetector, EntityMerger

entities = [
    {"id": "1", "name": "Apple Inc.",   "type": "Company"},
    {"id": "2", "name": "Apple",        "type": "Company"},
    {"id": "3", "name": "Microsoft",    "type": "Company"},
]

# 1. Detect duplicates — returns List[DuplicateCandidate]
detector   = DuplicateDetector(similarity_threshold=0.7)
candidates = detector.detect_duplicates(entities)

for dup in candidates:
    print(
        "{} vs {} — sim: {:.2f}, confidence: {:.2f}".format(
            dup.entity1.get("name"),
            dup.entity2.get("name"),
            dup.similarity_score,
            dup.confidence,
        )
    )

# 2. Merge duplicates — returns List[MergeOperation]
merger     = EntityMerger()
operations = merger.merge_duplicates(entities, strategy="keep_most_complete")

for op in operations:
    print("Merged {} entities → {}".format(
        len(op.source_entities), op.merged_entity.get("name")
    ))
```

## DuplicateDetector

Find duplicate entity pairs:

```python
from semantica.deduplication import DuplicateDetector

detector = DuplicateDetector(
    similarity_threshold=0.7,    # default 0.7 — minimum score to include a candidate
    confidence_threshold=0.6,    # default 0.6 — minimum confidence to include a candidate
    max_results=100,             # optional — hard cap on total candidates returned
    top_k_per_entity=3,          # optional — max candidates per entity
    min_similarity=0.75,         # optional — additional floor applied after sorting
    sort_by="confidence",        # "confidence" (default) | "similarity_score"
)

# Returns List[DuplicateCandidate]
candidates = detector.detect_duplicates(entities)

for c in candidates:
    print(c.entity1.get("name"), "vs", c.entity2.get("name"))
    print("  similarity_score:", c.similarity_score)
    print("  confidence:      ", c.confidence)
    print("  reasons:         ", c.reasons)

# Detect duplicate groups with union-find (returns List[DuplicateGroup])
groups = detector.detect_duplicate_groups(entities)
for g in groups:
    print("Group of {} — confidence: {:.2f} — representative: {}".format(
        len(g.entities), g.confidence, g.representative and g.representative.get("name")
    ))

# Incremental — compare new entities against existing (returns List[DuplicateCandidate])
new_entities = [{"id": "4", "name": "Apple Corp.", "type": "Company"}]
candidates   = detector.incremental_detect(new_entities, entities)
```

### `detect_duplicates()` detection methods

The `method=` parameter of the `detect_duplicates()` convenience function controls how
the comparison is performed. These are independent of the `SimilarityCalculator` string
method used internally:

| `method=` | Algorithm | Returns |
| :--------- | :--------- | :------- |
| `"pairwise"` (default) | O(n²) all-pairs comparison | `List[DuplicateCandidate]` |
| `"batch"` | Batch similarity calculation | `List[DuplicateCandidate]` |
| `"incremental"` | New vs existing entities | `List[DuplicateCandidate]` |
| `"group"` | Union-find group formation | `List[DuplicateGroup]` |

### DuplicateCandidate fields

| Field | Type | Description |
| :----- | :---- | :----------- |
| `entity1` | `Dict` | First entity |
| `entity2` | `Dict` | Second entity |
| `similarity_score` | `float` | Similarity score (0–1) |
| `confidence` | `float` | Confidence score (0–1) |
| `reasons` | `List[str]` | Why they are considered duplicates |
| `metadata` | `Dict` | Additional metadata |

### DuplicateGroup fields

| Field | Type | Description |
| :----- | :---- | :----------- |
| `entities` | `List[Dict]` | All entities in the group |
| `similarity_scores` | `Dict` | Pair → score mapping |
| `representative` | `Optional[Dict]` | Most complete entity in group |
| `confidence` | `float` | Group confidence score |
| `metadata` | `Dict` | Additional metadata |

## EntityMerger

Merges detected duplicate groups into canonical entities:

```python
from semantica.deduplication import EntityMerger, MergeStrategy

# Basic usage
merger     = EntityMerger(preserve_provenance=True)
operations = merger.merge_duplicates(entities, strategy="keep_most_complete")

# operations is List[MergeOperation]
for op in operations:
    merged = op.merged_entity         # the resulting merged entity dict
    sources = op.source_entities      # list of original entities that were merged
    conflicts = op.merge_result.conflicts  # unresolved conflicts, if any

# Merge a known group directly (no duplicate detection)
pair = [
    {"id": "1", "name": "Apple Inc.", "type": "Company"},
    {"id": "2", "name": "Apple",      "type": "Company"},
]
op = merger.merge_entity_group(pair, strategy="keep_most_complete")
print(op.merged_entity)

# Retrieve full merge history
history = merger.get_merge_history()
print("Total merges performed:", len(history))
```

### Merge strategies

Pass as a string to `strategy=` on `merge_duplicates()` or `merge_entity_group()`:

| Strategy | Behavior |
| :-------- | :-------- |
| `"keep_first"` | Keep the first entity in each duplicate group |
| `"keep_last"` | Keep the most recently seen entity |
| `"keep_most_complete"` | Keep the entity with the most non-null properties + relationships |
| `"keep_highest_confidence"` | Keep the entity with the highest `.confidence` value |
| `"merge_all"` | Combine all properties — conflicts resolved to lists |

### Per-property merge rules

Per-property rules are set on `EntityMerger.merge_strategy_manager` using
`add_property_rule()`. Rules take a `MergeStrategy` enum value:

```python
from semantica.deduplication import EntityMerger, MergeStrategy

merger = EntityMerger()

# Add per-property rules
merger.merge_strategy_manager.add_property_rule(
    "name", MergeStrategy.KEEP_FIRST
)
merger.merge_strategy_manager.add_property_rule(
    "aliases", MergeStrategy.MERGE_ALL
)

# Custom conflict resolution function
def keep_longest(val1, val2):
    return val1 if len(str(val1)) >= len(str(val2)) else val2

merger.merge_strategy_manager.add_property_rule(
    "description", MergeStrategy.KEEP_FIRST, conflict_resolution=keep_longest
)

operations = merger.merge_duplicates(entities)
```

### MergeOperation fields

| Field | Type | Description |
| :----- | :---- | :----------- |
| `source_entities` | `List[Dict]` | Original entities that were merged |
| `merged_entity` | `Dict` | Resulting merged entity |
| `merge_result` | `MergeResult` | Detailed result with conflicts |
| `metadata` | `Dict` | Group confidence, similarity scores, strategy used |

## SimilarityCalculator

Compute multi-factor similarity scores between entity pairs:

```python
from semantica.deduplication import SimilarityCalculator

calc = SimilarityCalculator(
    string_weight=0.6,        # default 0.6
    property_weight=0.2,      # default 0.2
    relationship_weight=0.2,  # default 0.2
    embedding_weight=0.0,     # default 0.0 (used only when "embedding" key is present)
    similarity_threshold=0.7,
)

result = calc.calculate_similarity(entity_a, entity_b)
# result is a SimilarityResult
print(result.score)                         # overall score 0.0–1.0
print(result.method)                        # e.g. "multi_factor"
print(result.components["string"])          # string similarity component
print(result.components["property"])        # property overlap component
print(result.components["relationship"])    # relationship jaccard component
# result.components["embedding"] is present only when embeddings are supplied

# String similarity methods — method= accepts "levenshtein", "jaro_winkler", "cosine"
lev  = calc.calculate_string_similarity("Apple Inc.", "Apple Inc",  method="levenshtein")
jaro = calc.calculate_string_similarity("Steve Jobs", "Steven Jobs", method="jaro_winkler")
cos  = calc.calculate_string_similarity("apple",     "apples",      method="cosine")

# Embedding cosine similarity (vector inputs)
emb_score = calc.calculate_embedding_similarity(embedding_a, embedding_b)

# Property and relationship similarity (entity dict inputs)
prop_score = calc.calculate_property_similarity(entity_a, entity_b)
rel_score  = calc.calculate_relationship_similarity(entity_a, entity_b)
```

### SimilarityResult fields

| Field | Type | Description |
| :----- | :---- | :----------- |
| `score` | `float` | Overall weighted similarity score (0–1) |
| `method` | `str` | Method used (e.g. `"multi_factor"`, `"levenshtein"`) |
| `components` | `Dict[str, float]` | Per-component scores: `"string"`, `"property"`, `"relationship"`, `"embedding"` |
| `metadata` | `Dict` | Weights used and optional score breakdown |

## ClusterBuilder

Build entity clusters for large-scale batch deduplication:

```python
from semantica.deduplication import ClusterBuilder

builder = ClusterBuilder(
    similarity_threshold=0.8,  # minimum similarity to be in same cluster
    min_cluster_size=2,         # minimum entities per valid cluster
    max_cluster_size=100,       # maximum entities per cluster
    use_hierarchical=False,     # True for hierarchical, False (default) for union-find
)
result = builder.build_clusters(entities)

print("Clusters found:", len(result.clusters))
for cluster in result.clusters:
    print("  [{}] {} entities — quality: {:.2f}".format(
        cluster.cluster_id,
        len(cluster.entities),
        cluster.quality_score,
    ))

print("Unclustered:   ", len(result.unclustered))
print("Quality metrics:", result.quality_metrics)
# {"average_size": ..., "average_quality": ..., "total_clusters": ..., "high_quality_clusters": ...}
```

### Cluster fields

| Field | Type | Description |
| :----- | :---- | :----------- |
| `cluster_id` | `str` | Unique cluster identifier |
| `entities` | `List[Dict]` | Entities in the cluster |
| `centroid` | `Optional[Dict]` | Representative entity (optional) |
| `quality_score` | `float` | Intra-cluster average similarity |
| `metadata` | `Dict` | Similarity scores and other metadata |

## Convenience Functions

```python
from semantica.deduplication import detect_duplicates, merge_entities, calculate_similarity

# Detect — method= accepts "pairwise" (default), "batch", "incremental", "group"
candidates = detect_duplicates(
    entities,
    method="pairwise",
    similarity_threshold=0.8,
    confidence_threshold=0.6,
)

# Merge — method= accepts the strategy strings, same as EntityMerger
operations = merge_entities(entities, method="keep_most_complete", preserve_provenance=True)
# Returns List[MergeOperation]; access .merged_entity on each

# Similarity — method= accepts "exact", "levenshtein", "jaro_winkler", "cosine",
#              "property", "relationship", "embedding", "multi_factor" (default)
result = calculate_similarity(entity_a, entity_b, method="multi_factor")
print(result.score)
```

## Custom Similarity Functions

Register domain-specific similarity logic and use it via the method registry:

```python
from semantica.deduplication import method_registry, SimilarityResult

def drug_name_similarity(entity_a, entity_b, **kwargs):
    """Match drug names by active compound prefix."""
    name_a = entity_a.get("name", "").lower()
    name_b = entity_b.get("name", "").lower()
    score = 1.0 if name_a[:5] == name_b[:5] else 0.0
    return SimilarityResult(score=score, method="drug_name")

method_registry.register("similarity", "drug_name", drug_name_similarity)

# Now callable via calculate_similarity
from semantica.deduplication import calculate_similarity
result = calculate_similarity(entity_a, entity_b, method="drug_name")
```

## Common Workflows

<Tabs>
  <Tab title="Basic Deduplication">
    ```python
    from semantica.deduplication import DuplicateDetector, EntityMerger

    detector   = DuplicateDetector(similarity_threshold=0.8)
    candidates = detector.detect_duplicates(entities)

    print("Duplicate pairs found:", len(candidates))

    merger     = EntityMerger(preserve_provenance=True)
    operations = merger.merge_duplicates(entities, strategy="keep_most_complete")

    merged_entities = [op.merged_entity for op in operations]
    ```
  </Tab>
  <Tab title="Group-based Batch">
    ```python
    from semantica.deduplication import DuplicateDetector, EntityMerger

    detector = DuplicateDetector(similarity_threshold=0.75)
    # detect_duplicate_groups uses union-find internally
    groups   = detector.detect_duplicate_groups(entities)

    merger = EntityMerger()
    for group in groups:
        op = merger.merge_entity_group(group.entities, strategy="keep_most_complete")
        print("Merged into:", op.merged_entity.get("name"))
    ```
  </Tab>
  <Tab title="Large-scale Clustering">
    ```python
    from semantica.deduplication import ClusterBuilder, EntityMerger

    # Build clusters first — more efficient for large entity sets
    builder = ClusterBuilder(similarity_threshold=0.8, min_cluster_size=2)
    result  = builder.build_clusters(entities)

    merger = EntityMerger()
    for cluster in result.clusters:
        op = merger.merge_entity_group(cluster.entities, strategy="keep_most_complete")
        print("Cluster merged into:", op.merged_entity.get("name"))
    ```
  </Tab>
  <Tab title="Incremental">
    ```python
    from semantica.deduplication import EntityMerger

    existing_entities = [...]  # already in the graph
    new_entities      = [...]  # arriving in a batch

    merger     = EntityMerger()
    operations = merger.incremental_merge(new_entities, existing_entities)

    print("New merges performed:", len(operations))
    ```
  </Tab>
</Tabs>

## Tips and Common Pitfalls

<Warning>
  **`DuplicateCandidate` fields are `entity1`, `entity2`, `similarity_score` — not `entity_a`, `entity_b`, `similarity`.** Accessing the wrong field names raises `AttributeError`.
</Warning>

<Warning>
  **`merge_entities()` and `EntityMerger.merge_duplicates()` return `List[MergeOperation]`, not a list of entity dicts.** Access `.merged_entity` on each operation to get the merged dict.
</Warning>

<Warning>
  **`PropertyMergeRule` is a dataclass, not an Enum.** The merge strategy Enum is `MergeStrategy` (`KEEP_FIRST`, `KEEP_LAST`, `KEEP_MOST_COMPLETE`, `KEEP_HIGHEST_CONFIDENCE`, `MERGE_ALL`). Per-property rules are added via `merger.merge_strategy_manager.add_property_rule(name, strategy)`.
</Warning>

<Tip>
  **Tune `similarity_threshold` before `confidence_threshold`.** The similarity threshold gates which entity pairs are even considered. The confidence threshold further filters those pairs based on multi-factor scoring. Start with `similarity_threshold=0.7` and raise it to reduce false positives.
</Tip>

<Tip>
  **Use `detect_duplicate_groups()` when you need to merge.** The `"group"` detection strategy uses union-find to form transitive clusters — if A≈B and B≈C, all three land in the same group. Plain `detect_duplicates()` returns individual pairs without transitivity.
</Tip>

<Tip>
  **Normalize entity names before deduplication.** Canonical forms such as `"Apple Inc."` vs `"apple inc"` may score below threshold due to case alone. Run `EntityNormalizer` or `TextNormalizer` first for reliable matching.
</Tip>

<CardGroup cols={2}>
  <Card title="Conflicts" icon="triangle-exclamation" href="conflicts">
    Detect value conflicts between non-duplicate entities.
  </Card>
  <Card title="Knowledge Graph" icon="diagram-project" href="kg">
    GraphBuilder uses deduplication during construction.
  </Card>
  <Card title="Normalize" icon="broom" href="normalize">
    Normalize entity names before deduplication.
  </Card>
  <Card title="Provenance" icon="link" href="provenance">
    Track merged entity lineage.
  </Card>
</CardGroup>
