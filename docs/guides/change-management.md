---
title: "Change Management & Versioning"
description: "Snapshot, version, diff, and migrate knowledge graphs and ontologies over time — with SQLite persistence, checksum verification, and structured change logs."
icon: "clock-rotate-left"
---

Knowledge graphs change constantly — threat actors get re-attributed, CVE scores update when exploits drop, clinical trial endpoints shift between phases. `TemporalVersionManager` gives your graph a verifiable history: named snapshots before every consequential change, diffs between any two states, one-call rollback, and SHA-256 checksum verification before publishing downstream.

<Info>
  `TemporalVersionManager` integrates with `AgentContext.flush_checkpoint()` — agent checkpoints and manual snapshots share the same storage format, so diffs work across both.
</Info>

## Creating Snapshots

Take a snapshot before any consequential change: an ingestion sweep, a partner feed merge, or an automated enrichment run.

```python
from semantica.change_management import TemporalVersionManager
from semantica.context import ContextGraph

graph = ContextGraph()
graph.add_node("apt29",         "ThreatActor",   "APT29 / NOBELIUM")
graph.add_node("cve-2024-3400", "Vulnerability", "CVE-2024-3400 PAN-OS RCE")
graph.add_edge("apt29", "cve-2024-3400", "exploits", weight=0.97)

vm = TemporalVersionManager(storage_path="cti_versions.db")

snap_pre = vm.create_snapshot(
    graph         = graph.to_dict(),
    version_label = "q3_2025_baseline",
    author        = "analyst_zhang",
    description   = "CTI baseline before Q3 OSINT sweep",
)

print(snap_pre["label"])        # "q3_2025_baseline"
print(snap_pre["checksum"])     # SHA-256 of the serialized graph
print(snap_pre["timestamp"])    # ISO datetime
print(snap_pre["author"])       # "analyst_zhang"
print(len(snap_pre["nodes"]))   # node count at snapshot time
print(len(snap_pre["edges"]))   # edge count at snapshot time
```

After running the ingestion, snapshot again to mark the post-change state:

```python
graph.add_node("cve-2024-21412", "Vulnerability", "CVE-2024-21412 Windows SmartScreen bypass")
graph.add_node("apt40",          "ThreatActor",   "APT40 / BRONZE MOHAWK")
graph.add_edge("apt40", "cve-2024-21412", "exploits", weight=0.88)

snap_post = vm.create_snapshot(
    graph         = graph.to_dict(),
    version_label = "q3_2025_post_nvd_sweep",
    author        = "osint_pipeline",
    description   = "After NVD weekly sweep — 2025-07-14",
)
```

## Comparing Two Snapshots

`compare_versions` returns a precise diff — nodes and edges added, removed, or modified — between any two named snapshots.

```python
diff = vm.compare_versions("q3_2025_baseline", "q3_2025_post_nvd_sweep")

s = diff["summary"]
print("Nodes added   :", s["nodes_added"])    # 2
print("Nodes removed :", s["nodes_removed"])  # 0
print("Edges added   :", s["edges_added"])    # 1

for node in diff["nodes_added"]:
    print(" +", node.get("id"), "/", node.get("content"))

for edge in diff["edges_added"]:
    print(" +", edge.get("source"), "→", edge.get("target"), "[" + edge.get("type", "") + "]")
```

You can also pass snapshot dicts directly instead of labels:

```python
diff = vm.compare_versions(snap_pre, snap_post)
```

## Verifying Integrity

Before publishing a snapshot to a downstream system — SIEM, partner feed, regulatory submission — verify the SHA-256 checksum to confirm nothing was modified after the snapshot was written.

```python
snap = vm.get_version("q3_2025_post_nvd_sweep")

if not vm.verify_checksum(snap):
    raise RuntimeError("Checksum mismatch on q3_2025_post_nvd_sweep — aborting publish.")

print("Integrity verified — safe to publish.")
```

## Rolling Back

Pass the target label and `require_confirmation=False` (an explicit safety gate) to restore the graph to any prior snapshot.

```python
vm.restore_snapshot(
    graph                = graph,
    target_version       = "q3_2025_baseline",
    require_confirmation = False,
)

# Record the rollback event as a new snapshot
vm.create_snapshot(
    graph         = graph.to_dict(),
    version_label = "q3_2025_rollback",
    author        = "analyst_zhang",
    description   = "Rolled back to baseline after corrupted OSINT batch",
)
```

<Info>
  `restore_snapshot` raises `ProcessingError` if `require_confirmation` is not explicitly `False`, preventing accidental rollbacks from automated scripts.
</Info>

## Building an Audit Changelog

List all snapshots in chronological order and diff each one against its predecessor to produce a human-readable change log.

```python
versions = sorted(vm.list_versions(), key=lambda v: v["timestamp"])

print("Graph Change Log")
print("=" * 60)

for i, v in enumerate(versions):
    print("\n[{}] {}  (by {})".format(v["timestamp"][:10], v["label"], v["author"]))
    print("  " + v["description"])

    if i > 0:
        diff = vm.compare_versions(versions[i - 1]["label"], v["label"])
        s    = diff["summary"]
        print("  Changes: +{} nodes  -{} nodes  +{} edges  -{} edges".format(
            s["nodes_added"], s["nodes_removed"],
            s["edges_added"], s["edges_removed"],
        ))
```

Sample output:

```text
Graph Change Log
============================================================

[2025-07-01] q3_2025_baseline  (by analyst_zhang)
  CTI baseline before Q3 OSINT sweep

[2025-07-14] q3_2025_post_nvd_sweep  (by osint_pipeline)
  After NVD weekly sweep — 2025-07-14
  Changes: +2 nodes  -0 nodes  +1 edges  -0 edges

[2025-07-14] q3_2025_rollback  (by analyst_zhang)
  Rolled back to baseline after corrupted OSINT batch
  Changes: -2 nodes  +0 nodes  -1 edges  +0 edges
```

## Tagging Milestones

Attach a named tag to any snapshot to mark review gates, approved states, or regulatory submissions.

```python
vm.tag_version("q3_2025_post_nvd_sweep", "q3-approved")

for tag_name, version_label in vm.list_tags().items():
    print(f"{tag_name:20s} → {version_label}")
# q3-approved          → q3_2025_post_nvd_sweep
```

## Node History

Attach `TemporalVersionManager` to a live `ContextGraph` to automatically record every individual mutation — every `add_node`, `add_edge`, and update call — not just snapshot-level diffs.

```python
vm.attach_to_graph(graph)

graph.add_node("apt29-alias", "ThreatActor", "NOBELIUM (rebranding 2021)")
graph.add_edge("apt29", "apt29-alias", "alias_of", weight=1.0)

for record in vm.get_node_history("apt29"):
    print("[{}] {} on {}  payload={}".format(
        record["timestamp"], record["operation"], record["entity_id"],
        str(record["payload"])[:60],
    ))
```

## AgentContext Integration

Pass the version manager at `AgentContext` construction. Agent checkpoints and manual snapshots share the same storage, giving you one unified history.

```python
from semantica.context import AgentContext, ContextGraph
from semantica.vector_store import VectorStore
from semantica.change_management import TemporalVersionManager

graph = ContextGraph()
vm    = TemporalVersionManager(storage_path="agent_versions.db")

context = AgentContext(
    vector_store             = VectorStore(backend="faiss", dimension=768),
    knowledge_graph          = graph,
    temporal_version_manager = vm,
)

context.store("APT29 targeting NATO infrastructure in Q3 2025")
context.checkpoint("pre_analysis")

# ... agent reasoning loop ...

context.checkpoint("post_analysis")
context.flush_checkpoint("post_analysis")   # persists via vm

diff = context.diff_checkpoints("pre_analysis", "post_analysis")
print("Decisions added    :", len(diff["decisions_added"]))
print("Relationships added:", len(diff["relationships_added"]))
```

## Domain Examples

<Tabs>
  <Tab title="Defense — CTI Pipeline">
    Daily NVD and ISAC feed ingestion with pre/post snapshots, a SOC change bulletin, and an integrity gate before publishing to the SIEM.

```python
from semantica.change_management import TemporalVersionManager
from semantica.context import ContextGraph
import datetime

graph = ContextGraph()
vm    = TemporalVersionManager(storage_path="cti_versions.db")
today = datetime.date.today().isoformat()

snap_pre = vm.create_snapshot(
    graph         = graph.to_dict(),
    version_label = f"pre_nvd_{today}",
    author        = "osint_pipeline",
    description   = "CTI baseline before NVD sweep",
)

# Ingestion
graph.add_node("cve-2025-1337",    "Vulnerability", "CVE-2025-1337 critical RCE")
graph.add_node("apt29-q3-cluster", "ThreatActor",   "APT29 Q3 2025 campaign cluster")
graph.add_edge("apt29-q3-cluster", "cve-2025-1337", "weaponizes", weight=0.91)

snap_post = vm.create_snapshot(
    graph         = graph.to_dict(),
    version_label = f"post_nvd_{today}",
    author        = "osint_pipeline",
    description   = "After NVD sweep",
)

diff = vm.compare_versions(snap_pre["label"], snap_post["label"])
s    = diff["summary"]
print(f"SOC Bulletin: +{s['nodes_added']} threat nodes, +{s['edges_added']} relationships")
for n in diff["nodes_added"]:
    print(f"  + [{n.get('type')}] {n.get('content')}")

if not vm.verify_checksum(snap_post):
    raise RuntimeError("Checksum mismatch — aborting SIEM publish")
print("Snapshot verified — publishing to SIEM feed.")
```

  </Tab>

  <Tab title="Security — Incident Response">
    Snapshot the incident graph at each major discovery during a live IR engagement so the post-mortem can replay exactly how the investigation evolved.

```python
from semantica.change_management import TemporalVersionManager
from semantica.context import ContextGraph

graph = ContextGraph()
vm    = TemporalVersionManager(storage_path="incident_ir042.db")

# T+0: Initial triage
graph.add_node("wkstn-047",   "Host",    "Compromised workstation WKSTN-047")
graph.add_node("attacker-ip", "Network", "Attacker ingress 185.220.101.47")
graph.add_edge("attacker-ip", "wkstn-047", "initial_access", weight=0.95)

vm.create_snapshot(
    graph         = graph.to_dict(),
    version_label = "ir042_t0_triage",
    author        = "analyst_chen",
    description   = "T+0 — one compromised host identified",
)

# T+2h: Lateral movement confirmed
graph.add_node("dc01",       "Host",    "Domain controller DC01")
graph.add_node("svc-backup", "Account", "Stolen service account SVC-BACKUP")
graph.add_edge("wkstn-047",  "svc-backup", "credential_theft", weight=0.88)
graph.add_edge("svc-backup", "dc01",       "lateral_move",     weight=0.82)

vm.create_snapshot(
    graph         = graph.to_dict(),
    version_label = "ir042_t2h_lateral",
    author        = "analyst_chen",
    description   = "T+2h — lateral movement to DC01 via stolen SVC-BACKUP",
)

diff = vm.compare_versions("ir042_t0_triage", "ir042_t2h_lateral")
s    = diff["summary"]
print(f"Post-mortem T+0→T+2h: +{s['nodes_added']} hosts/accounts, +{s['edges_added']} attack paths")
for edge in diff["edges_added"]:
    print(f"  + {edge.get('source')} → {edge.get('target')} [{edge.get('type')}]")
```

  </Tab>

  <Tab title="Life Science — Clinical Trial">
    Version the trial knowledge graph across phases to produce a machine-verifiable diff between Phase II and Phase III submissions for regulatory review.

```python
from semantica.change_management import TemporalVersionManager
from semantica.context import ContextGraph

graph_ph2 = ContextGraph()
graph_ph2.add_node("compound-xr401", "Compound", "XR-401")
graph_ph2.add_node("endpoint-orr",   "Endpoint", "Overall Response Rate")
graph_ph2.add_node("disease-nsclc",  "Disease",  "NSCLC")

graph_ph3 = ContextGraph()
graph_ph3.add_node("compound-xr401",  "Compound",   "XR-401")
graph_ph3.add_node("endpoint-orr",    "Endpoint",   "Overall Response Rate")
graph_ph3.add_node("endpoint-pfs",    "Endpoint",   "Progression-Free Survival")
graph_ph3.add_node("disease-nsclc",   "Disease",    "NSCLC")
graph_ph3.add_node("comparator-doce", "Comparator", "Docetaxel")

vm = TemporalVersionManager(storage_path="trial_xr401.db")

vm.create_snapshot(
    graph=graph_ph2.to_dict(), version_label="phase_ii_v1.0",
    author="clinical_data_team", description="Phase II — ORR primary, NSCLC",
)
vm.create_snapshot(
    graph=graph_ph3.to_dict(), version_label="phase_iii_v2.0",
    author="clinical_data_team", description="Phase III — PFS co-primary, Docetaxel added",
)

diff = vm.compare_versions("phase_ii_v1.0", "phase_iii_v2.0")
print("Regulatory diff Phase II → Phase III:")
for n in diff["nodes_added"]:
    print(f"  + [{n.get('type')}] {n.get('content')}")

snap = vm.get_version("phase_iii_v2.0")
assert vm.verify_checksum(snap), "Checksum failed — cannot attach to dossier"
print("Phase III snapshot verified — safe for regulatory submission.")
```

  </Tab>

  <Tab title="Banking — Model Governance">
    Version the Basel III credit risk model graph on each regulatory update and produce a machine-verifiable diff for the model governance committee before production deployment.

```python
from semantica.change_management import TemporalVersionManager
from semantica.context import ContextGraph

graph = ContextGraph()
graph.add_node("metric-cet1",      "CapitalMetric", "CET1 Capital Ratio")
graph.add_node("metric-ltv",       "RiskParameter", "LTV Ratio")
graph.add_node("metric-pd",        "RiskParameter", "Probability of Default")
graph.add_node("metric-lgd",       "RiskParameter", "Loss Given Default")
graph.add_node("regulation-cre20", "Regulation",    "Basel III CRE20")

vm = TemporalVersionManager(storage_path="credit_risk_versions.db")

vm.create_snapshot(
    graph=graph.to_dict(), version_label="basel_v1.0",
    author="risk_model_team", description="Basel III CRE20 initial graph",
)

# Regulatory update — DSCR becomes mandatory
graph.add_node("metric-dscr", "RiskParameter", "Debt Service Coverage Ratio")
graph.add_edge("regulation-cre20", "metric-dscr", "requires", weight=1.0)

vm.create_snapshot(
    graph=graph.to_dict(), version_label="basel_v1.1",
    author="risk_model_team", description="DSCR added per EBA GL 2020/06",
)

diff = vm.compare_versions("basel_v1.0", "basel_v1.1")
s    = diff["summary"]
print(f"Model governance diff v1.0→v1.1: +{s['nodes_added']} params, +{s['edges_added']} rules")
for n in diff["nodes_added"]:
    print(f"  + [{n.get('type')}] {n.get('content')}")

snap = vm.get_version("basel_v1.1")
assert vm.verify_checksum(snap), "Checksum failed — aborting model deployment"
print("Model v1.1 verified and approved for production.")
```

  </Tab>
</Tabs>

## Related Guides

- [Context Graphs](context-graphs) — `ContextGraph.to_dict()` feeds `create_snapshot()`
- [Ontology Management](ontology) — pair ontology versioning with graph versioning for a complete schema + data audit trail
- [SHACL Validation](shacl-validation) — validate graph data at each version gate before snapshotting
- [Provenance](provenance) — combine change management with W3C PROV-O lineage for a full audit trail
- [Visualization](visualization) — `TemporalVisualizer.visualize_snapshot_comparison()` and `visualize_metrics_evolution()` render version diffs as interactive charts
