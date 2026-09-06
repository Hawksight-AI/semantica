---
title: "Deduplication & Entity Merging"
description: "Detect duplicate entities using multi-factor similarity, merge them with configurable strategies, and keep your knowledge graph clean at scale."
---

## What Is Deduplication?

Deduplication is the process of identifying entities that refer to the same real-world object but appear as separate records in your data, then merging them into a single canonical representation. This process resolves aliases, spelling variations, and formatting differences that occur when data comes from multiple sources.

**Key deduplication concepts:**

**Canonical entities** are the single, authoritative representation of a real-world object after merging all duplicate records. The canonical entity becomes the node that all relationships point to in your knowledge graph.

**Aliases** are alternative names or identifiers for the same entity. For example, "APT29", "Cozy Bear", and "Midnight Blizzard" are all aliases for the same threat actor.

**Entity resolution** is the broader process of determining when different records refer to the same entity, including the similarity calculation, duplicate detection, and merging steps.

**Similarity algorithms:**
- **Jaro-Winkler** measures string similarity with higher scores for shared prefixes, ideal for names with common beginnings
- **Levenshtein** distance counts character edits needed to transform one string into another, good for catching typos and variations

**Clustering** groups related duplicates together using algorithms like Union-Find, ensuring that if A matches B and B matches C, all three are grouped together even if A and C don't directly match.

## Why Use Deduplication?

**Data quality and consistency.** Eliminate duplicate nodes that fragment relationships and create inconsistent query results across different names for the same entity.

**Accurate analytics and metrics.** Get correct counts, centrality measures, and relationship analysis when entities aren't artificially split across multiple nodes due to naming variations.

**Relationship consolidation.** Merge scattered relationships onto single canonical entities, enabling complete analysis of connections and patterns that would be missed with fragmented data.

**Source integration.** Seamlessly combine data from multiple feeds, systems, and databases where the same entities appear under different identifiers and naming conventions.

**Graph efficiency.** Reduce graph size and improve query performance by eliminating redundant nodes while preserving all information through proper merging strategies.

**Provenance preservation.** Maintain complete audit trails showing which source contributed each piece of information to the final canonical entity.

## When To Use / When Not To Use

**Use deduplication for:**
- Multi-source data integration where entities appear under different names or identifiers
- Entity types prone to aliases and variations (organizations, people, products, geographic locations)
- Knowledge graphs where relationship accuracy depends on entity consolidation
- Data quality workflows requiring canonical entity management
- Analytics requiring accurate entity counts and relationship metrics
- Scenarios where the same real-world objects appear across multiple systems or databases

**Do NOT use deduplication for:**
- Single-source data with consistent entity identifiers and naming conventions
- High-throughput streaming scenarios where deduplication latency is unacceptable
- Data with reliable primary keys where duplicates are impossible by design
- Cases where entity variations should be preserved as separate nodes (different product versions, time-based entity states)
- Simple exact-match scenarios where basic database constraints handle uniqueness

**Be cautious with:**
- Large datasets where O(n²) pairwise comparison becomes computationally expensive
- Fuzzy matching when deterministic primary keys (LEI, CVE-ID, ISIN) are available
- Very low similarity thresholds that may merge genuinely different entities

## Typical Workflow

The deduplication workflow follows a systematic process from detection through merging:

**1. Detect** → Use `detect_duplicates()` or `DuplicateDetector` to identify potential matches using multi-factor similarity scoring

**2. Group** → Apply clustering algorithms to collect transitively related duplicates into groups (A matches B, B matches C → group A,B,C)

**3. Select Canonical** → Choose representative entity for each group based on completeness, source authority, or confidence scores

**4. Merge** → Combine duplicate entities using strategies like `keep_most_complete` or `merge_all` while preserving provenance

**5. Validate** → Review merge results and adjust thresholds or strategies based on precision/recall analysis

**6. Update Graph** → Replace duplicate nodes with canonical entities and transfer all relationships

This pipeline transforms fragmented multi-source data into clean, consolidated knowledge graphs ready for analytics and reasoning.

## API Patterns: Functional vs Class-Based

Semantica provides both simple functional wrappers and comprehensive class APIs for different use cases:

**Functional wrappers for simple workflows:**
- `detect_duplicates()` — one-shot duplicate detection with minimal configuration
- `calculate_similarity()` — compare two entities with detailed similarity breakdown
- `merge_entities()` — convenience wrapper around merge_duplicates() for quick merging

**Class APIs for complex workflows:**
- `DuplicateDetector` — configurable duplicate detection with clustering, incremental processing, and advanced similarity options
- `EntityMerger` — sophisticated merging with multiple strategies, provenance tracking, and merge history

**Usage guidelines:**
- Use `merge_duplicates()` when you have a raw collection of entities and need automatic duplicate detection
- Use `merge_entity_group()` when you already know which entities are duplicates and just need to merge a pre-determined group
- Don't mix functional wrappers with class APIs in the same workflow—choose one approach and stick with it

The deduplication module detects duplicate entities across multi-source knowledge graphs using six complementary similarity algorithms — exact match, Levenshtein, Jaro-Winkler, cosine, property comparison, and vector embedding — then merges them into a single canonical entity while preserving full provenance. Use it to collapse alias clusters (e.g. "APT29", "Cozy Bear", "Midnight Blizzard") before running graph analytics or conflict resolution.

<Info>
Run deduplication after ingestion and before conflict resolution. Deduplication collapses duplicate nodes into one canonical entity. Conflict resolution then reconciles disagreeing property values on that canonical entity. The pipeline order matters: deduplicate first, then resolve conflicts, then validate with SHACL.
</Info>

## Finding your duplicates: the first scan

Start with `detect_duplicates()` for straightforward duplicate detection on smaller datasets. Point it at your entities and let the pairwise algorithm compare every pair using multiple similarity signals.

**Scaling consideration:** For datasets of a few thousand nodes, this runs in seconds. The O(n²) pairwise comparison cost only becomes problematic above ten thousand entities—for larger sets, see the clustering section below.

```python
from semantica.deduplication import detect_duplicates

# Threat actors ingested from four different CTI feeds — same actors, different names
threat_actors = [
    {"id": "ta-nvd-001",  "name": "APT29",            "type": "ThreatActor",
     "country": "Russia",  "source": "MISP"},
    {"id": "ta-of-002",   "name": "APT-29",            "type": "ThreatActor",
     "country": "Russia",  "source": "OpenCTI"},
    {"id": "ta-rf-003",   "name": "Cozy Bear",         "type": "ThreatActor",
     "aliases": ["APT29"], "country": "Russia", "source": "RecordedFuture"},
    {"id": "ta-sx-004",   "name": "The Dukes",         "type": "ThreatActor",
     "aliases": ["APT29", "Cozy Bear"], "country": "Russia", "source": "STIX-partner"},
    {"id": "ta-ms-005",   "name": "Midnight Blizzard", "type": "ThreatActor",
     "aliases": ["NOBELIUM", "APT29"], "country": "Russia", "source": "Microsoft"},
    {"id": "ta-ap-006",   "name": "APT28",             "type": "ThreatActor",
     "country": "Russia",  "source": "MISP"},  # different actor — should NOT match
]

candidates = detect_duplicates(
    threat_actors,
    method="pairwise",          # compare every pair
    similarity_threshold=0.6,   # minimum score to flag as a candidate
    confidence_threshold=0.5,   # minimum confidence in the match
)

for c in candidates:
    print(f"{c.entity1['name']!r}  ~  {c.entity2['name']!r}")
    print(f"  similarity={c.similarity_score:.2f}  confidence={c.confidence:.2f}")
    print(f"  signals: {c.reasons}")
    print()
```

```text
'APT29'  ~  'APT-29'
  similarity=0.89  confidence=0.81
  signals: ['levenshtein', 'jaro_winkler']

'APT29'  ~  'Cozy Bear'
  similarity=0.63  confidence=0.71
  signals: ['property', 'relationship']   # alias field matched

'Cozy Bear'  ~  'The Dukes'
  similarity=0.61  confidence=0.68
  signals: ['property']                   # shared alias "APT29"

'APT29'  ~  'Midnight Blizzard'
  similarity=0.65  confidence=0.73
  signals: ['property']                   # alias "APT29" in Midnight Blizzard record
```

The scores tell a clear story. "APT29" and "APT-29" score 0.89 — the hyphen is the only difference, producing strong string similarity signals. "Cozy Bear" and "The Dukes" score lower (0.61) because the names are completely dissimilar, but the property signal fires because both records carry `"APT29"` in their aliases list. "APT28" never appears in the results because it shares only the country field — not enough to cross the 0.6 threshold.

## Understanding the candidate object

Each `DuplicateCandidate` carries the two entities, their similarity scores, and a detailed breakdown of which similarity algorithms contributed to the match. This provides full transparency for audit and threshold tuning:

```python
from semantica.deduplication import calculate_similarity

# Inspect a single pair in detail before committing to a merge
e1 = threat_actors[0]   # APT29
e2 = threat_actors[2]   # Cozy Bear

result = calculate_similarity(e1, e2, method="multi_factor")

print(f"Overall score : {result.score:.2f}")
print(f"Method        : {result.method}")
print(f"Components    :")
for algo, score in result.components.items():
    print(f"  {algo:<20} {score:.2f}")
```

```text
Overall score : 0.63
Method        : multi_factor
Components    :
  exact                0.00   # names are completely different strings
  levenshtein          0.12   # high edit distance between "APT29" and "Cozy Bear"
  jaro_winkler         0.21   # no shared prefix
  property             0.94   # alias match is nearly definitive
  relationship         0.71   # share relationships to overlapping malware families
  embedding            0.78   # semantic vectors land in the same cluster
```

The property component (0.94) is doing most of the work here. "Cozy Bear"'s record carries `aliases: ["APT29"]`, which creates an almost-definitive signal that these entities refer to the same threat actor. When you see a pattern like this — weak name similarity but strong property matching — you're typically looking at a genuine alias relationship rather than a false positive.

## Grouping duplicates before merging

For small datasets, you can merge candidate pairs directly. For larger graphs where the same entity might appear under six different names across twelve feeds, use duplicate grouping with Union-Find clustering. This ensures that if A matches B and B matches C, all three entities are grouped together even if A and C don't directly meet the similarity threshold:

```python
from semantica.deduplication import DuplicateDetector, EntityMerger

detector = DuplicateDetector(
    similarity_threshold=0.6,
    confidence_threshold=0.5,
    use_clustering=True,      # enable Union-Find grouping
)

groups = detector.detect_duplicate_groups(threat_actors)

print(f"Found {len(groups)} duplicate groups:")
for group in groups:
    names = [e["name"] for e in group.entities]
    print(f"  Group (confidence={group.confidence:.2f}): {names}")
    if group.representative:
        print(f"  Representative: {group.representative['name']!r}")
```

```text
Found 2 duplicate groups:
  Group (confidence=0.74): ['APT29', 'APT-29', 'Cozy Bear', 'The Dukes', 'Midnight Blizzard']
  Representative: 'APT29'   # highest completeness score in the group

  Group (confidence=0.81): ['APT28', 'Fancy Bear']
  Representative: 'APT28'
```

The group result shows the consolidation clearly: five separate nodes that should be one canonical entity. The `representative` field identifies the entity the merger will use as the base — typically the one with the most complete attribute set, in this case "APT29" from the MISP feed.

## Merging: collapsing the group without losing data

Once you have identified duplicate groups, the merging process consolidates them into canonical entities. The `keep_most_complete` strategy selects the entity with the highest property count as the canonical node and enriches it with any missing fields from the other sources:

```python
merger = EntityMerger(preserve_provenance=True)

for group in groups:
    if len(group.entities) < 2:
        continue

    # merge_entity_group() skips duplicate detection since `group.entities`
    # is already a confirmed group from detect_duplicate_groups()
    op = merger.merge_entity_group(group.entities, strategy="keep_most_complete")

    canonical = op.merged_entity
    source_ids = [e["id"] for e in op.source_entities]
    print(f"Merged {len(op.source_entities)} entities → canonical: {canonical['name']!r}")
    print(f"  Source IDs retired : {source_ids}")
    print(f"  Merge strategy     : {op.merge_result.metadata.get('strategy')}")
```

```text
Merged 5 entities → canonical: 'APT29'
  Source IDs retired : ['ta-nvd-001', 'ta-of-002', 'ta-rf-003', 'ta-sx-004', 'ta-ms-005']
  Merge strategy     : keep_most_complete
```

The five source entities are replaced by one canonical representation. Every relationship those five nodes carried — to campaigns, malware families, TTPs, infrastructure — now attaches to the canonical "APT29" node. The merge operation preserves all information while eliminating redundancy, and the provenance records show exactly which feed contributed each attribute.

## Reviewing merge history for audit

After batch merging operations, you can retrieve the complete history to review every decision made. This audit trail is essential for understanding merge decisions and explaining them to stakeholders:

```python
history = merger.get_merge_history()

print(f"Total merge operations: {len(history)}")
for op in history:
    print(f"  {op.merged_entity['name']!r} ← {len(op.source_entities)} sources")
    print(f"    strategy: {op.merge_result.metadata.get('strategy')}")
```

This history provides complete transparency about merge decisions. When a feed owner asks why their entity was merged into another one, you have the documented evidence and reasoning for the decision.

## Streaming ingestion: incremental deduplication

When your pipeline processes continuous data streams — new threat intelligence arriving hourly — you don't want to re-run pairwise comparison over the entire graph on every batch. Use incremental detection to compare only new entities against the existing canonical set:

```python
# Existing graph entities (already deduplicated)
existing_actors = [
    {"id": "ta-nvd-001", "name": "APT29", "type": "ThreatActor", "country": "Russia"},
]

# New batch arriving from a fresh feed
new_batch = [
    {"id": "ta-new-007", "name": "NOBELIUM",      "type": "ThreatActor",
     "aliases": ["APT29"], "country": "Russia", "source": "MSTIC-2026-06"},
    {"id": "ta-new-008", "name": "Scattered Spider", "type": "ThreatActor",
     "country": "Unknown",  "source": "CrowdStrike"},
]

incremental = detector.incremental_detect(new_batch, existing_actors)

print(f"New duplicates found in this batch: {len(incremental)}")
for c in incremental:
    print(f"  {c.entity1['name']!r} matches existing {c.entity2['name']!r}")
    print(f"  score={c.similarity_score:.2f}")
```

```text
New duplicates found in this batch: 1
  'NOBELIUM' matches existing 'APT29'
  score=0.67        # alias field carries "APT29" — property signal fires
```

NOBELIUM gets queued for merging with the existing APT29 canonical entity. Scattered Spider scores below threshold against every existing actor and gets added to the graph as a new, unique node.

## Scaling to large entity sets

For graphs above ten thousand nodes, pairwise comparison becomes computationally expensive due to its O(n²) complexity. Use `build_clusters()` to run more efficient vectorized batch comparison, then merge each resulting cluster:

**Performance warning:** Always profile your similarity operations on representative data sizes. What works for 1,000 entities may become unacceptably slow at 10,000+ entities without appropriate scaling strategies.

```python
from semantica.deduplication import build_clusters

# Ten thousand CVE entities from NVD, Vulhub, and vendor feeds
# (not shown — assume `all_vulns` is a list of 10k+ dicts)

cluster_result = build_clusters(
    all_vulns,
    method="graph_based",        # Union-Find over similarity graph
    similarity_threshold=0.75,
)

print(f"Clusters found   : {len(cluster_result.clusters)}")
print(f"Unclustered      : {len(cluster_result.unclustered)}")
print(f"Quality metrics  : {cluster_result.quality_metrics}")

# Merge each cluster
merger = EntityMerger(preserve_provenance=True)
for cluster in cluster_result.clusters:
    if len(cluster.entities) > 1:
        # Use merge_entity_group() since clustering already determined these are duplicates
        merger.merge_entity_group(cluster.entities, strategy="keep_most_complete")
```

For even larger sets, switch to `method="hierarchical"` which uses agglomerative bottom-up clustering and scales to hundreds of thousands of entities at the cost of some precision.

## A Simple Example: Customer Deduplication

Before exploring domain-specific cases, let's walk through a straightforward customer deduplication scenario. A company's CRM system has accumulated duplicate customer records from web signups, sales team entries, and support tickets:

```python
from semantica.deduplication import detect_duplicates, merge_entities

customers = [
    {"id": "cust-001", "name": "John Smith", "email": "john.smith@email.com", 
     "company": "Acme Corp", "source": "web_signup"},
    {"id": "cust-002", "name": "J. Smith", "email": "john.smith@email.com",
     "company": "Acme Corporation", "source": "sales_team"},
    {"id": "cust-003", "name": "John Smith", "phone": "+1-555-0123",
     "company": "Acme Corp", "source": "support_ticket"},
    {"id": "cust-004", "name": "Jane Doe", "email": "jane.doe@email.com",
     "company": "Beta Inc", "source": "web_signup"},
]

# Step 1: Find potential duplicates
candidates = detect_duplicates(
    customers,
    method="pairwise",
    similarity_threshold=0.6,  # 60% similarity required
    confidence_threshold=0.5,
)

print("Potential duplicates found:")
for c in candidates:
    print(f"  {c.entity1['name']} ~ {c.entity2['name']} (score: {c.similarity_score:.2f})")
    print(f"    Matching signals: {c.reasons}")

# Expected output:
# John Smith ~ J. Smith (score: 0.82)
#   Matching signals: ['exact', 'property']  # same email
# John Smith ~ John Smith (score: 0.78)  
#   Matching signals: ['exact', 'property']  # same name and company

# Step 2: Merge the duplicates
john_smith_records = [customers[0], customers[1], customers[2]]  # All John Smith variants
merged_ops = merge_entities(john_smith_records, method="keep_most_complete")

for op in merged_ops:
    canonical = op.merged_entity
    print(f"\nCanonical customer: {canonical['name']}")
    print(f"  Email: {canonical.get('email', 'N/A')}")
    print(f"  Phone: {canonical.get('phone', 'N/A')}")
    print(f"  Company: {canonical['company']}")
    print(f"  Merged from {len(op.source_entities)} records")
    
# Result: One John Smith record with email, phone, and company information
# from all three original records, with full provenance tracking
```

This example demonstrates the core concepts: similarity detection finds related records, and merging consolidates them into canonical entities that preserve all available information.

## Common Pitfalls

**Threshold tuning without validation.** Setting thresholds too low creates false positive merges between genuinely different entities. Always manually review a sample of detected duplicates before running large-scale merging operations.

**Pairwise scaling problems.** The O(n²) cost of comparing every entity pair becomes prohibitive above 10,000 entities. Use clustering methods (`build_clusters`) or switch to vectorized similarity for large datasets.

**Using fuzzy matching when primary keys exist.** If your entities have reliable unique identifiers (LEI codes, CVE IDs, ISBN numbers), use exact matching on those fields instead of computationally expensive similarity algorithms.

**Mixing wrapper and class APIs inconsistently.** Don't call `detect_duplicates()` then manually instantiate `EntityMerger`—choose either the functional approach or class-based approach and use it consistently throughout your workflow.

**Ignoring merge strategy implications.** `keep_first` overwrites later records completely, `merge_all` can introduce conflicting values, and `keep_most_complete` may not respect source authority. Choose the strategy that matches your data quality requirements.

**Skipping provenance tracking.** Without `preserve_provenance=True`, you lose visibility into which source contributed each field in the canonical entity, making audit trails impossible.

**Inadequate similarity algorithm selection.** Pure string similarity fails for alias relationships ("APT29" vs "Cozy Bear"), while property matching may be too aggressive for entities with shared attributes but different identities.

## Domain examples

<Tabs>

<Tab title="Defense — CTI/Threat">

A threat intelligence platform ingests actor profiles from Mandiant, CrowdStrike, MITRE ATT&CK, and partner ISAC feeds. The same actors appear under vendor-specific names: "Cozy Bear" (CrowdStrike), "APT29" (MITRE), "Midnight Blizzard" (Microsoft), "The Dukes" (F-Secure). Before any analyst query runs, these aliases must collapse to a single canonical node so that relationships — malware used, infrastructure operated, campaigns attributed — all attach to one place.

The alias field is the key signal here. Property-based similarity will fire strongly when any record carries the canonical name in its `aliases` list. Setting a moderate threshold (0.6) catches alias-based matches that name similarity alone would miss.

```python
from semantica.deduplication import DuplicateDetector, EntityMerger

actors = [
    {"id": "ta-cs-001",  "name": "Cozy Bear",         "type": "ThreatActor",
     "aliases": ["APT29", "The Dukes"],  "country": "Russia", "source": "CrowdStrike"},
    {"id": "ta-mt-002",  "name": "APT29",              "type": "ThreatActor",
     "aliases": [],                       "country": "Russia", "source": "MITRE"},
    {"id": "ta-ms-003",  "name": "Midnight Blizzard",  "type": "ThreatActor",
     "aliases": ["NOBELIUM", "APT29"],   "country": "Russia", "source": "Microsoft"},
    {"id": "ta-fs-004",  "name": "The Dukes",          "type": "ThreatActor",
     "aliases": ["APT29", "Cozy Bear"],  "country": "Russia", "source": "F-Secure"},
    {"id": "ta-mt-005",  "name": "APT28",              "type": "ThreatActor",
     "aliases": ["Fancy Bear"],           "country": "Russia", "source": "MITRE"},
]

detector = DuplicateDetector(similarity_threshold=0.6, confidence_threshold=0.5)
groups = detector.detect_duplicate_groups(actors)

merger = EntityMerger(preserve_provenance=True)
for group in groups:
    if len(group.entities) < 2:
        continue
    ops = merger.merge_duplicates(group.entities, strategy="keep_most_complete")
    for op in ops:
        feeds = [e["source"] for e in op.source_entities]
        print(f"Canonical: {op.merged_entity['name']!r}  (merged from: {feeds})")
        # Canonical: 'APT29'  (merged from: ['CrowdStrike', 'MITRE', 'Microsoft', 'F-Secure'])
        # All four actor nodes collapse to one — every relationship they held now
        # attaches to the canonical APT29 node.
```

</Tab>

<Tab title="Security — SOC/Incident">

A SOC vulnerability management database ingests CVEs from NVD, Vulhub, CISA KEV, and vendor advisories. The same CVE often arrives as "CVE-2024-3400" from NVD, "PAN-OS GlobalProtect RCE" from a Tenable plugin, and "Critical PAN-OS 0day" from a blog post aggregator. Name similarity alone won't match these — the CVE ID in the `cve_id` field is the definitive signal.

```python
from semantica.deduplication import detect_duplicates, merge_entities

vulns = [
    {"id": "v-nvd-001",  "name": "CVE-2024-3400",
     "description": "PAN-OS GlobalProtect command injection RCE",
     "cvss": 10.0, "source": "NVD",      "type": "Vulnerability"},
    {"id": "v-cisa-002", "name": "CVE-2024-3400",
     "description": "Critical PAN-OS vulnerability in active exploitation",
     "cvss": 10.0, "source": "CISA-KEV", "type": "Vulnerability"},
    {"id": "v-ten-003",  "name": "PAN-OS GlobalProtect RCE",
     "cve_id": "CVE-2024-3400",
     "cvss": 10.0, "source": "Tenable",  "type": "Vulnerability"},
    {"id": "v-nvd-004",  "name": "CVE-2023-44487",
     "description": "HTTP/2 Rapid Reset DDoS amplification",
     "cvss": 7.5,  "source": "NVD",      "type": "Vulnerability"},
]

# Low threshold because name similarity between "CVE-2024-3400" and
# "PAN-OS GlobalProtect RCE" is near zero — we need property signals to fire
candidates = detect_duplicates(
    vulns,
    method="pairwise",
    similarity_threshold=0.5,
    confidence_threshold=0.4,
)

for c in candidates:
    print(f"{c.entity1['name']!r}  ~  {c.entity2['name']!r}")
    print(f"  score={c.similarity_score:.2f}  signals={c.reasons}")
    # 'CVE-2024-3400'  ~  'PAN-OS GlobalProtect RCE'
    #   score=0.61  signals=['property', 'exact']   # cve_id field match

# Merge the three CVE-2024-3400 variants
cve_group = [v for v in vulns if "3400" in v["name"] or v.get("cve_id") == "CVE-2024-3400"]
ops = merge_entities(cve_group, method="keep_most_complete", preserve_provenance=True)
for op in ops:
    print(f"Canonical CVE: {op.merged_entity['name']}  CVSS={op.merged_entity.get('cvss')}")
    # Canonical CVE: CVE-2024-3400  CVSS=10.0
    # One node now carries all three source records' provenance.
```

</Tab>

<Tab title="Life Science — Clinical/Pharma">

A clinical trial knowledge graph ingests drug entities from the WHO INN list, PubChem, brand name databases, and trial registries. Warfarin appears as "warfarin" (INN), "Coumadin" (brand, Bristol-Myers Squibb), "warfarin sodium" (PubChem chemical form), and "81-81-2" (CAS number). The CAS number is the ground truth — if two records share a CAS number, they are the same compound regardless of what name they carry.

```python
from semantica.deduplication import DuplicateDetector, EntityMerger, calculate_similarity

compounds = [
    {"id": "c-inn-001", "name": "warfarin",         "type": "Drug",
     "cas": "81-81-2",   "source": "WHO-INN"},
    {"id": "c-bms-002", "name": "Coumadin",         "type": "Drug",
     "cas": "81-81-2",   "source": "BMS-brand"},
    {"id": "c-pc-003",  "name": "warfarin sodium",  "type": "Drug",
     "source": "PubChem"},                            # no CAS — less complete record
    {"id": "c-inn-004", "name": "metoprolol",       "type": "Drug",
     "cas": "37350-58-6","source": "WHO-INN"},
    {"id": "c-nov-005", "name": "Lopressor",        "type": "Drug",
     "cas": "37350-58-6","source": "Novartis-brand"},
]

# The property method scores CAS number matches extremely high
sim = calculate_similarity(compounds[0], compounds[1], method="property")
print(f"warfarin vs Coumadin: {sim.score:.2f}")
# warfarin vs Coumadin: 0.91  — CAS match dominates

detector = DuplicateDetector(similarity_threshold=0.6, confidence_threshold=0.5)
groups = detector.detect_duplicate_groups(compounds)

merger = EntityMerger(preserve_provenance=True)
for group in groups:
    if len(group.entities) < 2:
        continue
    ops = merger.merge_duplicates(group.entities, strategy="keep_most_complete")
    for op in ops:
        print(f"Canonical: {op.merged_entity['name']!r}  CAS={op.merged_entity.get('cas')}")
        print(f"  Sources: {[e['source'] for e in op.source_entities]}")
        # Canonical: 'warfarin'  CAS=81-81-2
        #   Sources: ['WHO-INN', 'BMS-brand', 'PubChem']
        # All three warfarin records merge; WHO-INN record wins as most complete.
```

</Tab>

<Tab title="Banking — Risk/Compliance">

A risk management system resolves corporate clients across CRM, KYC, and trading systems before building the counterparty exposure graph. The Legal Entity Identifier (LEI) is the definitive identifier — a 20-character ISO 17442 code that uniquely identifies every legal entity globally. If two records share an LEI, they are the same legal entity regardless of how the name is formatted.

Three BlackRock records — "BlackRock Inc." (CRM), "BlackRock, Inc." (KYC, with comma), "Blackrock" (trading system, lowercase b) — must collapse to one canonical counterparty before credit exposure is aggregated. The property similarity method, which scores LEI matches near 1.0, handles this even when name similarity is moderate.

```python
from semantica.deduplication import build_clusters, EntityMerger

clients = [
    {"id": "crm-001", "name": "BlackRock Inc.",           "type": "Client",
     "lei": "549300HLPTRASHS0E726", "source": "CRM"},
    {"id": "kyc-001", "name": "BlackRock, Inc.",          "type": "Client",
     "lei": "549300HLPTRASHS0E726", "source": "KYC"},
    {"id": "trd-001", "name": "Blackrock",                "type": "Client",
     "lei": "549300HLPTRASHS0E726", "source": "TradeOps"},
    {"id": "crm-002", "name": "Vanguard Group",           "type": "Client",
     "lei": "549300IH7BVXP9VN3J07", "source": "CRM"},
    {"id": "kyc-002", "name": "The Vanguard Group, Inc.", "type": "Client",
     "lei": "549300IH7BVXP9VN3J07", "source": "KYC"},
]

cluster_result = build_clusters(
    clients,
    method="graph_based",
    similarity_threshold=0.65,   # LEI match alone scores above this
)

merger = EntityMerger(preserve_provenance=True)
for cluster in cluster_result.clusters:
    if len(cluster.entities) < 2:
        continue
    ops = merger.merge_duplicates(cluster.entities, strategy="keep_most_complete")
    for op in ops:
        sources = [e["source"] for e in op.source_entities]
        print(f"Canonical: {op.merged_entity['name']!r}  (from {sources})")
        # Canonical: 'BlackRock Inc.'  (from ['CRM', 'KYC', 'TradeOps'])
        # Canonical: 'Vanguard Group'  (from ['CRM', 'KYC'])

print(f"\nBefore: {len(clients)} client records")
print(f"After : {len(cluster_result.clusters)} canonical counterparties")
print(f"Quality: {cluster_result.quality_metrics}")
```

</Tab>

</Tabs>

## Choosing the right threshold

The similarity threshold controls sensitivity. Start at 0.7 and examine false positives before adjusting:

- **0.95 and above** — near-exact string matches only. Use for codes and IDs (LEI, CAS, CVE-ID) where name format is consistent across feeds.
- **0.80–0.95** — catches typographic variants: "Apple Inc." vs "Apple, Inc.", "BlackRock" vs "BlackRock Inc."
- **0.65–0.80** — catches abbreviations and short forms. Necessary for organization names that appear in both long and short forms across feeds.
- **0.50–0.65** — semantic similarity territory. Requires property or embedding signals to compensate for weak name similarity. Use this range for alias-based matching where names may be completely different strings referring to the same entity.

## Choosing a merge strategy

| Strategy | Use when |
| :--- | :--- |
| `keep_most_complete` | You don't have a designated authoritative source; maximize information density. Default choice. |
| `keep_first` | Your first source is a golden-record system (MDM, LEI registry) whose data should never be overwritten. |
| `keep_highest_confidence` | Your entities carry explicit confidence scores and you trust them as a quality signal. |
| `merge_all` | You want a superset of all properties; acceptable when you'll run conflict resolution afterwards to reconcile disagreements. |

## Related Guides

- [Ingest Anything](ingest) — multi-source ingestion creates the duplicates this module resolves
- [Context Graphs](/guides/context-graphs) — store deduplicated entities directly in the knowledge graph
- [Conflict Resolution](/guides/conflict-resolution) — after merging, reconcile disagreeing property values on the canonical entity
- [Provenance](provenance) — track merge lineage so every canonical entity traces back to its original sources
- [Pipeline](pipeline) — chain ingest, deduplicate, and store as a `PipelineBuilder` workflow
