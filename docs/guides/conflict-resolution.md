---
title: "Conflict Detection & Resolution"
description: "Detect value, type, and relationship conflicts across multi-source knowledge graphs and resolve them automatically with seven configurable strategies."
icon: "code-merge"
---

`ConflictDetector` surfaces properties where multiple sources disagree on the same canonical entity, and `ConflictResolver` applies per-property strategies — credibility-weighted voting, most-recent, expert review, and others — to produce a single resolved value with a full audit trail. Run it after deduplication and before SHACL validation.

<Info>
Run conflict detection after deduplication and before SHACL validation. Deduplication removes duplicate nodes; conflict resolution reconciles disagreeing property values on the same canonical entity. Running them out of order — detecting conflicts before deduplication — will produce spurious conflicts between entities that should have been merged first.
</Info>

## Detecting the disagreement

Start by loading your multi-source records for the same entity. `ConflictDetector` groups them by entity ID, then compares the values each source reports for a given property. Any entity where two or more sources report different values for the same property produces a `Conflict` object.

```python
from semantica.conflicts import ConflictDetector, ConflictResolver, ResolutionStrategy

# Three authoritative sources on the same CVE — all credible, all disagreeing
cve_records = [
    {
        "id": "cve-2024-3400",
        "source": "nvd",
        "cvss_score": 10.0,
        "exploit_status": "unconfirmed",
        "vector": "AV:N/AC:L/PR:N/UI:N/S:C/C:H/I:H/A:H",
        "credibility_score": 0.98,
    },
    {
        "id": "cve-2024-3400",
        "source": "commercial_feed",
        "cvss_score": 9.1,
        "exploit_status": "in_wild",
        "vector": "AV:N/AC:L/PR:N/UI:N/S:U/C:H/I:H/A:H",
        "credibility_score": 0.91,
    },
    {
        "id": "cve-2024-3400",
        "source": "vendor_paloalto",
        "cvss_score": 9.5,
        "exploit_status": "in_wild",
        "vector": "AV:N/AC:H/PR:N/UI:N/S:C/C:H/I:H/A:H",
        "credibility_score": 0.87,
    },
]

detector = ConflictDetector()

# Detect disagreements on the CVSS score property
score_conflicts = detector.detect_value_conflicts(cve_records, property_name="cvss_score")
exploit_conflicts = detector.detect_value_conflicts(cve_records, property_name="exploit_status")

print(f"CVSS score conflicts  : {len(score_conflicts)}")
print(f"Exploit status conflicts: {len(exploit_conflicts)}")

for c in score_conflicts:
    print(f"\nConflict: {c.conflict_id}")
    print(f"  Entity   : {c.entity_id}")
    print(f"  Property : {c.property_name}")
    print(f"  Values   : {c.conflicting_values}")   # [10.0, 9.1, 9.5]
    print(f"  Severity : {c.severity}")              # 'medium' — numeric difference < 1000
    print(f"  Sources  : {[s['document'] for s in c.sources]}")
    print(f"  Action   : {c.recommended_action}")
```

```text
CVSS score conflicts  : 1
Exploit status conflicts: 1

Conflict: cve-2024-3400_cvss_score_conflict
  Entity   : cve-2024-3400
  Property : cvss_score
  Values   : [10.0, 9.1, 9.5]
  Severity : medium
  Sources  : ['nvd', 'commercial_feed', 'vendor_paloalto']
  Action   : Compare source documents and use most recent or authoritative source
```

Each `Conflict` captures the full picture: which entity, which property, every disagreeing value, and which source reported each. This is already enough to build a review queue — but the goal is to resolve these automatically according to rules you set.

## Setting per-property resolution rules

The key method is `set_resolution_rule(entity_id, property_name, strategy)`. It takes three arguments: which entity, which property, and which `ResolutionStrategy` to apply when that combination appears in a conflict. Rules are stored in the resolver and automatically applied when you call `resolve_conflicts()` without passing an explicit strategy.

```python
resolver = ConflictResolver()

# For this CVE, NVD is the most authoritative source on scoring.
# CREDIBILITY_WEIGHTED will use the credibility_score field on each source record
# to weight the vote — NVD at 0.98 will dominate over the commercial feed at 0.91.
resolver.set_resolution_rule(
    "cve-2024-3400",
    "cvss_score",
    ResolutionStrategy.CREDIBILITY_WEIGHTED,
)

# Exploitation status is time-sensitive: the commercial feed and vendor have both
# observed in-the-wild exploitation, which is more current than NVD's initial
# unconfirmed assessment. MOST_RECENT picks the value from the source with the
# latest timestamp in its metadata.
resolver.set_resolution_rule(
    "cve-2024-3400",
    "exploit_status",
    ResolutionStrategy.MOST_RECENT,
)
```

You can set rules before or after detection — the resolver applies them lazily when `resolve_conflicts()` is called.

## Resolving the batch

Pass all detected conflicts to `resolve_conflicts()`. For each conflict, the resolver looks up whether a property-specific rule is set for that entity and property combination. If one is found, it applies that strategy. If none is set, it falls back to the default strategy (voting, unless you override it in the constructor).

```python
all_conflicts = score_conflicts + exploit_conflicts

results = resolver.resolve_conflicts(all_conflicts)

for r in results:
    status = "RESOLVED" if r.resolved else "REVIEW REQUIRED"
    print(f"[{status}] {r.conflict_id}")
    print(f"  Resolved value : {r.resolved_value}")
    print(f"  Strategy used  : {r.resolution_strategy}")
    print(f"  Confidence     : {r.confidence:.0%}")
    print(f"  Sources used   : {r.sources_used}")
    print(f"  Notes          : {r.resolution_notes}")
    print()
```

```text
[RESOLVED] cve-2024-3400_cvss_score_conflict
  Resolved value : 10.0
  Strategy used  : credibility_weighted
  Confidence     : 72%
  Sources used   : ['nvd', 'commercial_feed', 'vendor_paloalto']
  Notes          : Resolved by credibility-weighted voting (weight: 0.98)

[RESOLVED] cve-2024-3400_exploit_status_conflict
  Resolved value : in_wild
  Strategy used  : most_recent
  Confidence     : 80%
  Sources used   : ['commercial_feed']
  Notes          : Resolved by most recent value
```

NVD wins the CVSS score — its credibility weight (0.98) edges out the commercial feed (0.91) and the vendor (0.87), so 10.0 becomes the canonical score. The exploitation status resolves to `in_wild` — the commercial feed and vendor advisory are both more recent than NVD's initial triage, and both report active exploitation.

## Handling conflicts that need human judgment

Not every conflict can be auto-resolved. A disagreement about the legal classification of a financial instrument, or about a patient's current medication list, is too consequential to resolve by algorithm. Flag these for review without blocking the rest of the batch:

```python
from semantica.conflicts import ConflictDetector, ConflictResolver, ResolutionStrategy

# Drug trial data: efficacy agreed, primary endpoint disputed
trial_records = [
    {"id": "dapagliflozin", "source": "declare_timi58",
     "primary_endpoint": "MACE",               "hba1c_reduction_pct": 0.54,
     "credibility_score": 0.92},
    {"id": "dapagliflozin", "source": "dapa_hf",
     "primary_endpoint": "HF_hospitalization", "hba1c_reduction_pct": 0.48,
     "credibility_score": 0.95},
    {"id": "dapagliflozin", "source": "meta_analysis",
     "primary_endpoint": "HbA1c_reduction",    "hba1c_reduction_pct": 0.52,
     "credibility_score": 0.88},
]

detector = ConflictDetector()
efficacy_conflicts  = detector.detect_value_conflicts(trial_records, "hba1c_reduction_pct")
endpoint_conflicts  = detector.detect_value_conflicts(trial_records, "primary_endpoint")

resolver = ConflictResolver()

# Efficacy: credibility-weighted across trials — the meta-analysis (0.88) and
# the two RCTs (0.92, 0.95) will produce a weighted resolution.
resolver.set_resolution_rule(
    "dapagliflozin", "hba1c_reduction_pct", ResolutionStrategy.CREDIBILITY_WEIGHTED
)

# Primary endpoint: each trial measured a different thing. This is not a conflict
# to auto-resolve — a clinician must decide which endpoint applies to the use case.
resolver.set_resolution_rule(
    "dapagliflozin", "primary_endpoint", ResolutionStrategy.EXPERT_REVIEW
)

all_conflicts = efficacy_conflicts + endpoint_conflicts
results = resolver.resolve_conflicts(all_conflicts)

auto_resolved = [r for r in results if r.resolved]
for_review    = [r for r in results if not r.resolved]

print(f"Auto-resolved : {len(auto_resolved)}")
print(f"Expert review : {len(for_review)}")

# Export the review queue for the clinical team
import json
review_queue = [
    {
        "conflict_id": r.conflict_id,
        "notes": r.resolution_notes,
        "metadata": r.metadata,
    }
    for r in for_review
]
with open("expert_review_queue.json", "w") as fh:
    json.dump(review_queue, fh, indent=2, default=str)
```

```text
Auto-resolved : 1
Expert review : 1   # primary_endpoint — EXPERT_REVIEW means resolved=False
```

`EXPERT_REVIEW` sets `resolved=False` on the result. The conflict stays in the graph unresolved, the metadata field carries `requires_expert_review: True`, and the review queue JSON gives your clinical team exactly what they need to make the call.

## Reviewing the full audit trail

After a resolution run, `get_resolution_history()` returns every decision made since the resolver was instantiated. This is your compliance log:

```python
history = resolver.get_resolution_history()

print(f"Total resolutions logged: {len(history)}")
for r in history:
    status = "RESOLVED" if r.resolved else "PENDING"
    print(f"[{status}] {r.conflict_id}")
    print(f"  Strategy   : {r.resolution_strategy}")
    print(f"  Value      : {r.resolved_value}")
    print(f"  Confidence : {r.confidence:.0%}")
```

Pair this with the full conflict report from the detector to get aggregate statistics across all runs:

```python
report = detector.get_conflict_report()

print(f"Total conflicts detected  : {report['total_conflicts']}")
print(f"By type                   : {report['by_type']}")
print(f"By severity               : {report['by_severity']}")
# Total conflicts detected  : 2
# By type                   : {'value_conflict': 2}
# By severity               : {'medium': 2}
```

The report aggregates every conflict the detector has seen across its lifetime — useful for pipeline monitoring and for identifying which entity types or data sources generate the most disagreements.

## Detecting relationship conflicts

Value conflicts live on properties. Relationship conflicts live on edges — two sources asserting contradictory connections between the same node pair:

```python
# Two intelligence sources disagree about whether APT29 exploits this CVE
relationships = [
    {"source": "apt29", "target": "cve-2024-3400",
     "type": "EXPLOITS",     "origin": "mandiant"},
    {"source": "apt29", "target": "cve-2024-3400",
     "type": "UNRELATED_TO", "origin": "crowdstrike"},
]

rel_conflicts = detector.detect_relationship_conflicts(relationships)
for c in rel_conflicts:
    print(f"Relationship conflict: {c.conflict_id}")
    print(f"  Edge type values: {c.conflicting_values}")
    print(f"  Severity: {c.severity}")
```

Relationship conflicts typically require expert review rather than voting, because conflicting edge types often reflect genuinely different intelligence assessments rather than data entry errors.

## Domain examples

<Tabs>

<Tab title="Defense — CTI/Threat">

A threat intelligence platform merges actor profiles from Mandiant, CrowdStrike, and an open-source blog. The three sources agree that APT29 is Russian and espionage-motivated, but disagree on when it was first observed and — critically — one source attributes it to China. The low-credibility source (the blog, at 0.30) should lose to the high-credibility sources (Mandiant at 0.95, CrowdStrike at 0.92) when those sources are in agreement.

Credibility-weighted resolution handles this cleanly: the blog's misattribution is drowned out by the combined weight of the two authoritative vendors. The `first_seen` date disagreement (2008 vs 2009) is also resolved by credibility weight, giving Mandiant's 2008 date the win.

```python
from semantica.conflicts import ConflictDetector, ConflictResolver, ResolutionStrategy

actor_profiles = [
    {"id": "apt29", "source": "mandiant",    "nation_state": "Russia",
     "first_seen": "2008", "credibility_score": 0.95},
    {"id": "apt29", "source": "crowdstrike", "nation_state": "Russia",
     "first_seen": "2009", "credibility_score": 0.92},
    {"id": "apt29", "source": "oss_blog",    "nation_state": "China",  # wrong
     "first_seen": "2015", "credibility_score": 0.30},
]

detector = ConflictDetector()
nation_conflicts     = detector.detect_value_conflicts(actor_profiles, "nation_state")
first_seen_conflicts = detector.detect_value_conflicts(actor_profiles, "first_seen")

resolver = ConflictResolver()
resolver.set_resolution_rule("apt29", "nation_state", ResolutionStrategy.CREDIBILITY_WEIGHTED)
resolver.set_resolution_rule("apt29", "first_seen",   ResolutionStrategy.CREDIBILITY_WEIGHTED)

results = resolver.resolve_conflicts(nation_conflicts + first_seen_conflicts)
for r in results:
    print(f"{r.conflict_id}: {r.resolved_value!r}  [{r.confidence:.0%} confidence]")
    # apt29_nation_state_conflict: 'Russia'  [83% confidence]
    # apt29_first_seen_conflict:   '2008'    [73% confidence]
    # The blog's China attribution (weight 0.30) loses to Mandiant+CrowdStrike (0.95+0.92).

history = resolver.get_resolution_history()
print(f"Audit log entries: {len(history)}")
```

</Tab>

<Tab title="Security — SOC/Incident">

A vulnerability management system ingests CVSS scores from NVD, MITRE, and a vendor advisory for the same CVE. NVD and MITRE are both authoritative; the vendor has self-interest in scoring conservatively. Credibility-weighted resolution gives NVD (0.98) and MITRE (0.96) dominance over the vendor (0.90), producing a canonical score that reflects the consensus of independent authorities.

The CVSS vector string also conflicts — the scope field (`S:C` vs `S:U`) reflects a genuine interpretive disagreement that affects whether the CVE is classified as a network pivot risk. Both conflicts get the same credibility-weighted treatment.

```python
from semantica.conflicts import ConflictDetector, ConflictResolver, ResolutionStrategy

cve_records = [
    {"id": "cve-2024-3400", "source": "nvd",
     "cvss_score": 10.0, "vector": "AV:N/AC:L/PR:N/UI:N/S:C/C:H/I:H/A:H",
     "credibility_score": 0.98},
    {"id": "cve-2024-3400", "source": "mitre",
     "cvss_score": 9.8,  "vector": "AV:N/AC:L/PR:N/UI:N/S:U/C:H/I:H/A:H",
     "credibility_score": 0.96},
    {"id": "cve-2024-3400", "source": "paloalto",
     "cvss_score": 9.5,  "vector": "AV:N/AC:H/PR:N/UI:N/S:C/C:H/I:H/A:H",
     "credibility_score": 0.90},
]

detector = ConflictDetector()
score_conflicts  = detector.detect_value_conflicts(cve_records, "cvss_score")
vector_conflicts = detector.detect_value_conflicts(cve_records, "vector")

resolver = ConflictResolver()
resolver.set_resolution_rule(
    "cve-2024-3400", "cvss_score", ResolutionStrategy.CREDIBILITY_WEIGHTED
)
resolver.set_resolution_rule(
    "cve-2024-3400", "vector", ResolutionStrategy.CREDIBILITY_WEIGHTED
)

results = resolver.resolve_conflicts(score_conflicts + vector_conflicts)
for r in results:
    if r.resolved:
        print(f"Canonical {r.conflict_id.split('_')[2]}: {r.resolved_value}  "
              f"({r.confidence:.0%} confidence)")
    # Canonical cvss_score: 10.0   (72% confidence)  — NVD wins
    # Canonical vector: AV:N/AC:L/PR:N/UI:N/S:C/C:H/I:H/A:H  (54% confidence)
```

</Tab>

<Tab title="Life Science — Clinical/Pharma">

A drug safety knowledge graph merges dapagliflozin trial data from three studies: DECLARE-TIMI 58, DAPA-HF, and a meta-analysis. The HbA1c reduction values differ across trials because each enrolled a different population. The primary endpoint differs because each trial was designed to answer a different clinical question — a genuine scientific distinction, not a data error.

Efficacy numbers can be credibility-weighted; disputed endpoints must go to expert review. This split handling — auto-resolve what you can, escalate what you can't — is the pattern for regulated data environments.

```python
from semantica.conflicts import ConflictDetector, ConflictResolver, ResolutionStrategy

drug_records = [
    {"id": "dapagliflozin", "source": "declare_timi58",
     "hba1c_reduction_pct": 0.54, "primary_endpoint": "MACE",
     "credibility_score": 0.92},
    {"id": "dapagliflozin", "source": "dapa_hf",
     "hba1c_reduction_pct": 0.48, "primary_endpoint": "HF_hospitalization",
     "credibility_score": 0.95},
    {"id": "dapagliflozin", "source": "meta_analysis",
     "hba1c_reduction_pct": 0.52, "primary_endpoint": "HbA1c_reduction",
     "credibility_score": 0.88},
]

detector = ConflictDetector()
efficacy_conflicts = detector.detect_value_conflicts(drug_records, "hba1c_reduction_pct")
endpoint_conflicts = detector.detect_value_conflicts(drug_records, "primary_endpoint")

resolver = ConflictResolver()
resolver.set_resolution_rule(
    "dapagliflozin", "hba1c_reduction_pct", ResolutionStrategy.CREDIBILITY_WEIGHTED
)
resolver.set_resolution_rule(
    "dapagliflozin", "primary_endpoint", ResolutionStrategy.EXPERT_REVIEW
    # resolved=False — queued for clinician review, not auto-resolved
)

results = resolver.resolve_conflicts(efficacy_conflicts + endpoint_conflicts)
auto   = [r for r in results if r.resolved]
review = [r for r in results if not r.resolved]

print(f"Auto-resolved  : {len(auto)}")
for r in auto:
    print(f"  {r.conflict_id}: {r.resolved_value}  [{r.confidence:.0%}]")
    # dapagliflozin_hba1c_reduction_pct_conflict: 0.48  [38%]

print(f"Expert queue   : {len(review)}")
for r in review:
    print(f"  {r.conflict_id} — {r.resolution_notes}")
    # dapagliflozin_primary_endpoint_conflict — Flagged for expert review
```

</Tab>

<Tab title="Banking — Risk/Compliance">

A credit risk graph merges corporate client data from a CRM, the global LEI registry, and a credit bureau. The LEI registry is the legal authority on entity names and industry codes — its credibility should be set to 1.0 (or treated as definitive). The CRM and bureau may have stale or abbreviated names; the LEI registry has the officially registered legal name.

Setting `CREDIBILITY_WEIGHTED` resolution for `legal_name` and `sic_code` with the LEI registry carrying a 0.99 credibility score ensures the legally authoritative value always wins, with full audit evidence for the next regulatory examination.

```python
from semantica.conflicts import ConflictDetector, ConflictResolver, ResolutionStrategy

client_records = [
    {"id": "corp-acme-uk", "source": "crm",
     "legal_name": "ACME UK Ltd",                "sic_code": "7372",
     "credibility_score": 0.75},
    {"id": "corp-acme-uk", "source": "lei_registry",
     "legal_name": "ACME United Kingdom Limited", "sic_code": "7371",
     "credibility_score": 0.99},                  # LEI registry is authoritative
    {"id": "corp-acme-uk", "source": "credit_bureau",
     "legal_name": "ACME UK Ltd",                "sic_code": "7372",
     "credibility_score": 0.85},
]

detector = ConflictDetector()
name_conflicts = detector.detect_value_conflicts(client_records, "legal_name")
sic_conflicts  = detector.detect_value_conflicts(client_records, "sic_code")

resolver = ConflictResolver()
resolver.set_resolution_rule(
    "corp-acme-uk", "legal_name", ResolutionStrategy.CREDIBILITY_WEIGHTED
)
resolver.set_resolution_rule(
    "corp-acme-uk", "sic_code", ResolutionStrategy.CREDIBILITY_WEIGHTED
)

results = resolver.resolve_conflicts(name_conflicts + sic_conflicts)
for r in results:
    print(f"Canonical {r.conflict_id.split('_')[2]}: {r.resolved_value!r}  "
          f"[{r.confidence:.0%}]")
    # Canonical legal_name: 'ACME United Kingdom Limited'  [53%]  — LEI registry wins
    # Canonical sic_code:   '7371'                         [53%]  — LEI registry wins

# Aggregate conflict statistics for the compliance report
report = detector.get_conflict_report()
print(f"\nConflict audit:")
print(f"  Total detected : {report['total_conflicts']}")
print(f"  By severity    : {report['by_severity']}")
```

</Tab>

</Tabs>

## Resolution strategies at a glance

| Strategy | How it decides | Best when |
| :--- | :--- | :--- |
| `VOTING` | Most frequent value wins | 3+ independent sources; no clear authority |
| `CREDIBILITY_WEIGHTED` | Values weighted by source `credibility_score` | Sources have known reliability rankings |
| `MOST_RECENT` | Value from the source with the latest timestamp | Data decays quickly — threat intel, market prices |
| `FIRST_SEEN` | Value from the first source to assert it | Primary sources are more reliable than derivatives |
| `HIGHEST_CONFIDENCE` | Value from the source with the highest `confidence` field | Automated extractors emit per-record confidence scores |
| `MANUAL_REVIEW` | Flags the conflict; `resolved=False` | Low-volume, high-stakes decisions |
| `EXPERT_REVIEW` | Flags for domain expert queue; `resolved=False` | Scientific or legal disambiguation required |

## Related Guides

- [Deduplication](deduplication) — remove duplicate nodes before running conflict detection
- [Provenance](provenance) — track which source each resolved value came from, and verify the audit trail cryptographically
- [SHACL Validation](shacl-validation) — enforce structural constraints after conflicts are resolved
- [Change Management](change-management) — snapshot the graph before and after conflict resolution runs
- [Ontology Management](ontology) — align entity types to a shared vocabulary to reduce type conflicts at the schema level
