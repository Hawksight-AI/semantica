---
title: "Deduplication & Entity Merging"
description: "Detect duplicate entities using multi-factor similarity, merge them with configurable strategies, and keep your knowledge graph clean at scale."
---

The deduplication module detects duplicate entities across multi-source knowledge graphs using six complementary similarity algorithms — exact match, Levenshtein, Jaro-Winkler, cosine, property comparison, and vector embedding — then merges them into a single canonical entity while preserving full provenance. Use it to collapse alias clusters (e.g. "APT29", "Cozy Bear", "Midnight Blizzard") before running graph analytics or conflict resolution.

<Info>
Run deduplication after ingestion and before conflict resolution. Deduplication collapses duplicate nodes into one canonical entity. Conflict resolution then reconciles disagreeing property values on that canonical entity. The pipeline order matters: deduplicate first, then resolve conflicts, then validate with SHACL.
</Info>

## Finding your duplicates: the first scan

Start with `detect_duplicates()`. Point it at your threat actor entities and let the pairwise algorithm compare every pair. For a dataset of a few thousand nodes this runs in seconds — the O(n²) cost only matters above ten thousand entities.

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

The scores tell a clear story. "APT29" and "APT-29" score 0.89 — the hyphen is the only difference, pure edit-distance signal. "Cozy Bear" and "The Dukes" score lower (0.61) because the names are completely dissimilar, but the property signal fires because both records carry `"APT29"` in their aliases list. "APT28" never appears in the results because it shares only the country field — not enough to cross the 0.6 threshold.

## Understanding the candidate object

Each `DuplicateCandidate` carries the two entities, their scores, and a `reasons` list explaining which signals fired. This is your audit trail for the detection decision:

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

The property component (0.94) is doing most of the work here. "Cozy Bear"'s record carries `aliases: ["APT29"]`, which creates an almost-definitive signal. When you see a pattern like this — a weak name score but a strong property score — you're looking at a real alias relationship, not a false positive.

## Grouping duplicates before merging

For a small dataset you can merge pairs directly. For a larger graph where the same entity might appear under six different names across twelve feeds, use `detect_duplicate_groups()`. It runs Union-Find clustering to collect all aliases of the same underlying entity into a single group, regardless of whether every pair individually crosses the threshold:

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

The group result shows the problem clearly: five separate nodes that should be one. The `representative` field is the entity the merger will use as the base — the one with the most filled properties, in this case "APT29" from the MISP feed which carries the fullest attribute set.

## Merging: collapsing the group without losing data

Now merge. The `keep_most_complete` strategy keeps the entity with the highest property count as the canonical node and fills in any missing fields from the other sources. With `preserve_provenance=True`, the merge operation records which source contributed every field in the merged result:

```python
merger = EntityMerger(preserve_provenance=True)

for group in groups:
    if len(group.entities) < 2:
        continue

    operations = merger.merge_duplicates(group.entities, strategy="keep_most_complete")

    for op in operations:
        canonical = op.merged_entity
        source_ids = [e["id"] for e in op.source_entities]
        print(f"Merged {len(op.source_entities)} entities → canonical: {canonical['name']!r}")
        print(f"  Source IDs retired : {source_ids}")
        print(f"  Merge strategy     : {op.merge_result}")
        print(f"  Timestamp          : {op.timestamp}")
```

```text
Merged 5 entities → canonical: 'APT29'
  Source IDs retired : ['ta-nvd-001', 'ta-of-002', 'ta-rf-003', 'ta-sx-004', 'ta-ms-005']
  Merge strategy     : MergeResult.KEPT_MOST_COMPLETE
  Timestamp          : 2026-06-21T09:14:02.443Z
```

The five source entities are replaced by one. Every relationship those five nodes carried — to campaigns, malware families, TTPs, infrastructure — now attaches to the canonical "APT29" node. Nothing is lost; the provenance records show exactly which feed contributed which attribute.

## Reviewing merge history for audit

After a batch merge, pull the full history to review every decision made:

```python
history = merger.get_merge_history()

print(f"Total merge operations: {len(history)}")
for op in history:
    print(f"  {op.merged_entity['name']!r} ← {len(op.source_entities)} sources")
    print(f"    strategy: {op.merge_result}")
```

This history is what you present when a feed owner asks why their entity was merged into another one. Every decision is recorded.

## Streaming ingestion: incremental deduplication

When your pipeline is ingesting continuously — new STIX bundles arriving hourly — you don't want to re-run pairwise comparison over the entire graph on every batch. Use `incremental_detect()` to compare only the new entities against the existing set:

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

NOBELIUM goes to the merge queue. Scattered Spider scores below threshold against every existing actor and gets added to the graph as a new node.

## Scaling to large entity sets

For graphs above ten thousand nodes, pairwise comparison becomes too slow. Use `build_clusters()` to run vectorized batch comparison, then merge each cluster:

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
        merger.merge_duplicates(cluster.entities, strategy="keep_most_complete")
```

For even larger sets, switch to `method="hierarchical"` which uses agglomerative bottom-up clustering and scales to hundreds of thousands of entities at the cost of some precision.

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
- [Context Graphs](context-graphs) — store deduplicated entities directly in the knowledge graph
- [Conflict Resolution](conflict-resolution) — after merging, reconcile disagreeing property values on the canonical entity
- [Provenance](provenance) — track merge lineage so every canonical entity traces back to its original sources
- [Pipeline](pipeline) — chain ingest, deduplicate, and store as a `PipelineBuilder` workflow
