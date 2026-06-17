---
title: "Conflicts Module"
description: "Multi-source conflict detection and resolution: value, type, temporal, and logical conflicts with investigation guides."
icon: "triangle-exclamation"
---

**`semantica.conflicts`** detects and resolves **contradictions when multiple sources disagree** on the same fact:

- Five conflict types: value, type, temporal, logical, and relationship
- Seven resolution strategies: voting, credibility-weighted, most-recent, first-seen, highest-confidence, manual review, expert review
- `InvestigationGuideGenerator` produces step-by-step investigation instructions for manual resolution
- `SourceTracker` maps each property value to its contributing source for full attribution
- Conflicts are surfaced explicitly: never silently corrupting the knowledge graph


## Why Detect Conflicts?

When you ingest data from multiple sources, contradictions are inevitable. One annual report says Apple's revenue was $391B; a financial newswire says $383B. Without conflict detection, both values land in your graph and queries silently return inconsistent answers.

Semantica's conflict detection makes disagreements explicit and actionable:

- **Value conflicts**: SEC says revenue is $391B; Reuters says $383B
- **Type conflicts**: "Python" is a `ProgrammingLanguage` in one source, a `Snake` species in another
- **Temporal conflicts**: a CEO had two different employers during overlapping date ranges
- **Logical conflicts**: an entity simultaneously holds two mutually exclusive properties
- **Relationship conflicts**: the same relationship has inconsistent cardinality or properties across sources

## Exported Classes

| Class | Role |
| :--- | :--- |
| `ConflictDetector` | Detects value, type, and relationship conflicts across entity lists |
| `ConflictResolver` | Resolves conflicts with configurable strategy: `voting`, `credibility_weighted`, `most_recent`, `first_seen`, `highest_confidence`, `manual_review`, `expert_review` |
| `ConflictType` | Enum: `VALUE_CONFLICT`, `TYPE_CONFLICT`, `TEMPORAL_CONFLICT`, `LOGICAL_CONFLICT`, `RELATIONSHIP_CONFLICT` |
| `ResolutionStrategy` | Enum of available resolution strategies passed to `ConflictResolver` |
| `ResolutionResult` | Dataclass returned by `resolve_conflict` / `resolve_conflicts` |
| `SourceTracker` | Tracks which source contributed each property value on each entity |
| `SourceReference` | Source document reference with document, page, section, confidence |
| `PropertySource` | Aggregated property-level provenance: value + list of `SourceReference` objects |
| `ConflictAnalyzer` | Analyzes conflict patterns, severity distribution, and per-source statistics |
| `ConflictPattern` | Dataclass describing a detected conflict pattern |
| `InvestigationGuideGenerator` | Generates step-by-step investigation guides for conflicts requiring manual review |
| `InvestigationGuide` | Guide dataclass: `conflict_id`, `conflict_summary`, `severity`, `investigation_steps`, `recommended_actions` |
| `InvestigationStep` | Step dataclass: `step_number`, `description`, `action`, `expected_outcome` |

## What You Get

<CardGroup cols={2}>
  <Card title="ConflictDetector" icon="magnifying-glass">
    Value, type, and relationship conflict detection across entity and relationship lists.
  </Card>
  <Card title="ConflictResolver" icon="check">
    7 resolution strategies including voting, credibility-weighted, and temporal preference.
  </Card>
  <Card title="SourceTracker" icon="link">
    Track which source each conflicting fact came from, with per-source credibility scores.
  </Card>
  <Card title="ConflictAnalyzer" icon="chart-line">
    Pattern analysis, severity grouping, source-level statistics, and trend identification.
  </Card>
  <Card title="InvestigationGuideGenerator" icon="list-check">
    Auto-generate step-by-step investigation checklists for human and expert review.
  </Card>
  <Card title="Convenience Functions" icon="bolt">
    `detect_conflicts()` and `resolve_conflicts()` for one-call workflows.
  </Card>
</CardGroup>

## Quick Start

<Steps>
  <Step title="Set credibility scores before ingestion">
    ```python
    from semantica.conflicts import SourceTracker

    tracker = SourceTracker()
    tracker.set_source_credibility("sec_filings",   0.95)
    tracker.set_source_credibility("pubmed",        0.92)
    tracker.set_source_credibility("wikipedia",     0.80)
    tracker.set_source_credibility("news_articles", 0.65)
    ```
  </Step>
  <Step title="Detect conflicts after building the graph">
    ```python
    from semantica.conflicts import ConflictDetector

    detector = ConflictDetector()

    # Detect value conflicts on a specific property
    conflicts = detector.detect_value_conflicts(entities, "revenue")
    print("Found %d conflicts" % len(conflicts))

    for conflict in conflicts:
        print("[%s] entity='%s'  attr='%s'" % (
            conflict.conflict_type, conflict.entity_id, conflict.property_name))
        print("  Values: %s  Severity: %s" % (
            conflict.conflicting_values, conflict.severity))
    ```
  </Step>
  <Step title="Triage by severity">
    ```python
    from semantica.conflicts import ConflictAnalyzer

    analyzer  = ConflictAnalyzer()
    analysis  = analyzer.analyze_conflicts(conflicts)
    severity_counts = analysis["by_severity"]["counts"]
    severity_details = analysis["by_severity"]["details"]
    print("Critical: %d" % severity_counts.get("critical", 0))
    print("High:     %d" % severity_counts.get("high", 0))
    print("Low:      %d" % severity_counts.get("low", 0))
    ```
  </Step>
  <Step title="Auto-resolve low-severity, escalate critical">
    ```python
    from semantica.conflicts import ConflictResolver, InvestigationGuideGenerator, ResolutionStrategy

    resolver = ConflictResolver(source_tracker=tracker)

    # Auto-resolve low-severity conflicts
    low_conflicts = severity_details.get("low", [])
    # Re-fetch full Conflict objects if needed: severity_details contains dicts
    auto_resolved = resolver.resolve_conflicts(
        conflicts,
        strategy=ResolutionStrategy.CREDIBILITY_WEIGHTED,
    )

    # Generate investigation guides for critical conflicts
    critical_ids = {d["conflict_id"] for d in severity_details.get("critical", [])}
    critical_conflicts = [c for c in conflicts if c.conflict_id in critical_ids]

    generator = InvestigationGuideGenerator()
    for conflict in critical_conflicts:
        guide = generator.generate_guide(conflict)
        print("\n%s" % guide.title)
        for step in guide.investigation_steps:
            print("  [%d] %s" % (step.step_number, step.description))
            print("       Action: %s" % step.action)
    ```
  </Step>
</Steps>

## ConflictDetector

```python
from semantica.conflicts import ConflictDetector

detector = ConflictDetector()

# Detect value conflicts on a specific property
conflicts = detector.detect_value_conflicts(entities, "revenue")
```

### Detection Types

| Type | What It Detects | Example |
| :---- | :--------------- | :------- |
| `VALUE` | Same entity, same property, different values across sources | Revenue $391B vs $383B |
| `TYPE` | Same entity classified as different types | "Python" as Language vs Snake |
| `TEMPORAL` | Conflicting timestamps or validity windows | CEO at two companies simultaneously |
| `LOGICAL` | Logically inconsistent property combinations | `is_alive=True` but `death_date` set |
| `RELATIONSHIP` | Inconsistent relationship properties across sources | Edge weight 0.9 vs 0.3 from two sources |

Run targeted detection by type:

```python
# Detect value conflicts for a specific property
value_conflicts = detector.detect_value_conflicts(entities, "revenue")

# Detect type classification conflicts
type_conflicts = detector.detect_type_conflicts(entities)

# Detect relationship property conflicts (takes a list of relationship dicts)
relation_conflicts = detector.detect_relationship_conflicts(relationships)

# Detect conflicts across all properties of a set of entities
all_conflicts = detector.detect_entity_conflicts(entities)
```

### ConflictDetector Methods

| Method | Returns | Description |
| :------ | :------- | :----------- |
| `detect_value_conflicts(entities, property_name, entity_type=None)` | `List[Conflict]` | Detect value disagreements on a specific property across entity instances |
| `detect_type_conflicts(entities)` | `List[Conflict]` | Detect type classification conflicts |
| `detect_relationship_conflicts(relationships)` | `List[Conflict]` | Detect relationship property conflicts (takes a list of relationship dicts) |
| `detect_entity_conflicts(entities, entity_type=None)` | `List[Conflict]` | Detect conflicts across all monitored properties for a set of entities |
| `get_conflict_report()` | `Dict[str, Any]` | Generate a summary report of all detected conflicts |

## ConflictResolver

```python
from semantica.conflicts import ConflictResolver, ResolutionStrategy

resolver = ConflictResolver()
results  = resolver.resolve_conflicts(conflicts, strategy=ResolutionStrategy.VOTING)

for result in results:
    print("Resolved '%s' -> %s" % (result.conflict_id, result.resolved_value))
    print("  Strategy: %s  Confidence: %.2f" % (result.resolution_strategy, result.confidence))
```

### Choosing a Resolution Strategy

<Tabs>
  <Tab title="CREDIBILITY_WEIGHTED (recommended)">
    Weights each source's value by its assigned credibility score: favors authoritative sources automatically:

    ```python
    from semantica.conflicts import ConflictResolver, SourceTracker, ResolutionStrategy

    tracker = SourceTracker()
    tracker.set_source_credibility("sec_filings",   0.92)
    tracker.set_source_credibility("wikipedia",     0.80)
    tracker.set_source_credibility("news_articles", 0.65)

    resolver = ConflictResolver(source_tracker=tracker)
    results  = resolver.resolve_conflicts(
        conflicts,
        strategy=ResolutionStrategy.CREDIBILITY_WEIGHTED,
    )
    ```

    **Best for:** sources with known reliability rankings (SEC > blog).
  </Tab>
  <Tab title="VOTING">
    Majority vote: most common value across sources wins:

    ```python
    results = resolver.resolve_conflicts(conflicts, strategy=ResolutionStrategy.VOTING)
    ```

    **Best for:** 3+ sources with roughly equal credibility. When all sources have identical credibility scores, `CREDIBILITY_WEIGHTED` behaves identically to `VOTING`.
  </Tab>
  <Tab title="MOST_RECENT / FIRST_SEEN">
    ```python
    # Most recent source wins: for fast-changing facts
    results = resolver.resolve_conflicts(conflicts, strategy=ResolutionStrategy.MOST_RECENT)

    # First seen wins: for stable facts (founding date, original name)
    results = resolver.resolve_conflicts(conflicts, strategy=ResolutionStrategy.FIRST_SEEN)
    ```
  </Tab>
  <Tab title="MANUAL_REVIEW / EXPERT_REVIEW">
    ```python
    # Flag for human review: use with InvestigationGuideGenerator
    results   = resolver.resolve_conflicts(conflicts, strategy=ResolutionStrategy.MANUAL_REVIEW)
    generator = InvestigationGuideGenerator()

    for conflict in conflicts:
        guide = generator.generate_guide(conflict)
        print("%s" % guide.title)
        for step in guide.investigation_steps:
            print("  [%d] %s" % (step.step_number, step.description))
    ```

    **Best for:** high-stakes decisions (`severity == "critical"`), regulated data (HIPAA/SOX), and domain-specific ambiguity.
  </Tab>
  <Tab title="Strategy Comparison">

    | Strategy | Enum | When to Use |
    | :-------- | :---- | :----------- |
    | Majority vote | `VOTING` | 3+ sources with roughly equal credibility |
    | Credibility-weighted | `CREDIBILITY_WEIGHTED` | Sources have different authority levels |
    | Most recent | `MOST_RECENT` | Fast-changing facts: stock price, headcount, status |
    | First seen | `FIRST_SEEN` | Stable facts: founding date, original name |
    | Highest confidence | `HIGHEST_CONFIDENCE` | Extraction pipeline outputs confidence scores |
    | Manual review | `MANUAL_REVIEW` | High-stakes decisions, regulated data |
    | Expert review | `EXPERT_REVIEW` | Domain-specific ambiguity: escalate to a specialist |
  </Tab>
</Tabs>

Use the convenience aliases for shorter code:

```python
from semantica.conflicts import voting, credibility_weighted, most_recent, highest_confidence

results = resolver.resolve_conflicts(conflicts, strategy=voting)
```

## SourceTracker

```python
from semantica.conflicts import SourceTracker, SourceReference

tracker = SourceTracker()
tracker.set_source_credibility("sec_10k",   0.92)
tracker.set_source_credibility("wikipedia", 0.80)

source_ref = SourceReference(
    document="sec_10k_2023",
    page=12,
    confidence=0.95,
)
tracker.track_property_source(
    entity_id="apple_inc",
    property_name="revenue",
    value="$391B",
    source=source_ref,
)

# Returns a PropertySource object with .value and .sources (List[SourceReference])
prop_source = tracker.get_property_sources("apple_inc", "revenue")
if prop_source:
    print("Value: %s" % prop_source.value)
    for s in prop_source.sources:
        credibility = tracker.get_source_credibility(s.document)
        print("  %s (confidence: %.2f, credibility: %.2f)" % (
            s.document, s.confidence, credibility))

chain = tracker.get_traceability_chain("apple_inc")
```

**Key behaviours:**
- Credibility scores default to 0.50 for any source not explicitly set
- `SourceTracker` stores property-level provenance: so you can trace exactly which source contributed each value

## ConflictAnalyzer

```python
from semantica.conflicts import ConflictAnalyzer

analyzer = ConflictAnalyzer()

analysis     = analyzer.analyze_conflicts(conflicts)
patterns     = analysis["patterns"]
severity_counts = analysis["by_severity"]["counts"]
source_stats = analysis["by_source"]
trends       = analyzer.analyze_trends(conflicts)

# analyze_trends returns a list of dicts, one per time period
for t in trends:
    print("Period: %s  Count: %d  Trend: %s" % (
        t["period"], t["conflict_count"], t["trend"]))
```

**Key behaviours:**
- `analyze_conflicts()["patterns"]` returns a list of `ConflictPattern` objects: use `pattern.pattern_type` and `pattern.frequency` to find systemic data quality issues
- `analyze_conflicts()["by_source"]` includes `counts` and `top_sources`: sources appearing in many conflicts may have upstream data quality problems
- `analyze_trends()` returns a list of per-period dicts (`period`, `conflict_count`, `trend`, `trend_direction`): `trend` is `"increasing"`, `"decreasing"`, or `"stable"`

## InvestigationGuideGenerator

Auto-generate human-readable investigation checklists for conflicts requiring manual or expert review:

```python
from semantica.conflicts import InvestigationGuideGenerator

generator = InvestigationGuideGenerator()
guide     = generator.generate_guide(conflict)

print("Title:   %s" % guide.title)
print("Summary: %s" % guide.conflict_summary)

for step in guide.investigation_steps:
    print("  [%d] %s" % (step.step_number, step.description))
    print("       Action: %s" % step.action)
    if step.expected_outcome:
        print("       Expected: %s" % step.expected_outcome)
```

## Schemas

<AccordionGroup>
  <Accordion title="Conflict schema">

```python
@dataclass
class Conflict:
    conflict_id:        str
    conflict_type:      ConflictType        # VALUE_CONFLICT | TYPE_CONFLICT | ...
    entity_id:          Optional[str]       # entity involved (None for relationship conflicts)
    property_name:      Optional[str]       # the conflicting property name
    relationship_id:    Optional[str]       # relationship involved (for RELATIONSHIP_CONFLICT)
    conflicting_values: List[Any]           # conflicting values (one per source)
    sources:            List[Dict[str, Any]]# source dicts for each value
    confidence:         float               # detection confidence 0–1 (default: 1.0)
    severity:           str                 # "low" | "medium" | "high" | "critical"
    recommended_action: Optional[str]
    metadata:           Dict[str, Any]
```

  </Accordion>
  <Accordion title="ResolutionResult schema">

```python
@dataclass
class ResolutionResult:
    conflict_id:        str
    resolved:           bool
    resolved_value:     Any                 # None if unresolved or flagged for review
    resolution_strategy: Optional[str]      # e.g. "voting", "credibility_weighted"
    confidence:         float               # 0.0–1.0
    sources_used:       List[str]           # document IDs that contributed
    resolution_notes:   Optional[str]
    metadata:           Dict[str, Any]
```

  </Accordion>

  <Accordion title="ConflictType enum">

```python
from semantica.conflicts import ConflictType

ConflictType.VALUE_CONFLICT         # revenue is $391B in source A, $383B in source B
ConflictType.TYPE_CONFLICT          # "Apple" is ORGANIZATION in one source, PRODUCT in another
ConflictType.TEMPORAL_CONFLICT      # overlapping validity windows with contradictory states
ConflictType.LOGICAL_CONFLICT       # fact violates an ontology axiom or SHACL constraint
ConflictType.RELATIONSHIP_CONFLICT  # inconsistent relationship properties across sources
```

  </Accordion>
  <Accordion title="InvestigationGuide and InvestigationStep schemas">

```python
@dataclass
class InvestigationGuide:
    conflict_id:         str
    conflict_summary:    str                      # generated summary of the disagreement
    severity:            str                      # "low" | "medium" | "high" | "critical"
    conflicting_sources: List[Dict[str, Any]]
    investigation_steps: List[InvestigationStep]
    recommended_actions: List[str]
    context:             Dict[str, Any]
    generated_at:        str                      # ISO timestamp
    # title is a @property: "Investigation: <conflict_id>"

@dataclass
class InvestigationStep:
    step_number:      int
    description:      str   # what to do
    action:           str   # specific action to take
    expected_outcome: Optional[str]
```

  </Accordion>
</AccordionGroup>

## Tips and Common Pitfalls

<Warning>
  **Detect before you merge, not after.** Run conflict detection on raw entity data before deduplication and graph construction. Detecting conflicts in a live graph that already contains merged entities is harder: you lose the original source attribution.
</Warning>

<Warning>
  **Always set credibility scores.** The default credibility is 0.50 for all sources. Without explicit scores, `CREDIBILITY_WEIGHTED` behaves identically to `VOTING`. The power of this strategy is in the differentiation.
</Warning>

<Tip>
  **Don't auto-resolve everything.** Use `MANUAL_REVIEW` for conflicts with `severity == "critical"` or `severity == "high"`: high severity means the disagreement is large and the stakes of getting it wrong are high.
</Tip>

<Warning>
  **`TEMPORAL` and `LOGICAL` conflict detection is not implemented on `ConflictDetector` directly.** The `ConflictType` enum includes these types for use in custom pipelines, but the detector class only implements `detect_value_conflicts`, `detect_type_conflicts`, `detect_relationship_conflicts`, and `detect_entity_conflicts`.
</Warning>

<Tip>
  **Use `analyze_conflicts()["by_source"]["top_sources"]` to identify bad data feeds.** A single source appearing in many conflicts is a data quality problem upstream, not a conflict to resolve record by record. Flag it and investigate the source pipeline.
</Tip>

<Tip>
  **Severity is a string label, not a score.** `ConflictDetector` assigns `"critical"`, `"high"`, or `"medium"` based on property importance and value differences. Critical fields (`id`, `name`, `type`, `revenue`) always yield `"critical"`. Domain context determines what to prioritize.
</Tip>

<Tip>
  **Combine with provenance.** The `SourceTracker` feeds directly into the [Provenance](provenance) module's audit trail. If you need to explain how a resolved value was chosen, provenance records give you the full chain.
</Tip>

<CardGroup cols={2}>
  <Card title="Deduplication" icon="copy" href="deduplication">
    Resolve duplicate entities before conflict detection.
  </Card>
  <Card title="Ontology" icon="sitemap" href="ontology">
    Logical conflicts use SHACL shapes and ontology axioms.
  </Card>
  <Card title="Provenance" icon="link" href="provenance">
    Track which source each conflicting fact came from.
  </Card>
  <Card title="Knowledge Graph" icon="diagram-project" href="kg">
    The graph being checked for conflicts.
  </Card>
</CardGroup>
