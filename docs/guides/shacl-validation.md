---
title: "SHACL Validation"
description: "Generate W3C SHACL shapes from OWL ontologies, validate RDF knowledge graphs against structural and semantic constraints, and surface structured violation reports."
icon: "shield-check"
---

`SHACLGenerator` produces W3C SHACL constraint shapes from an OWL ontology, and `_run_pyshacl` validates your knowledge graph against them, returning a structured violation report. Use this to gate graph data before analytics, ISAC sharing, or regulatory submission — catching missing required properties, datatype violations, and cardinality breaches before they propagate.

<Info>
SHACL shapes are produced from the same ontology dict that `OntologyGenerator` builds. The full workflow is: graph → ontology → SHACL shapes → validation report. Each stage is one function call. `NodeShape`, `PropertyShape`, and `SHACLGraph` import from `semantica.ontology`. `SHACLValidationReport`, `SHACLViolation`, and `_run_pyshacl` import from `semantica.ontology.ontology_validator`.
</Info>

---

## Step 1 — Build the ontology from your merged graph

SHACL shapes are derived from an ontology. If you already have one from a previous run, skip this step.

```python
from semantica.context import AgentContext, ContextGraph
from semantica.vector_store import VectorStore
from semantica.ontology import OntologyGenerator

graph = ContextGraph()
ctx   = AgentContext(
    vector_store=VectorStore(backend="faiss", dimension=768),
    knowledge_graph=graph,
    graph_expansion=True,
)

# Load the merged CTI data — in production this would be your full 12,000-node graph
ctx.store(
    [
        "APT29 is a Russian state-sponsored threat actor targeting NATO governments.",
        "CVE-2024-3400 is a critical vulnerability in PAN-OS exploited by APT29.",
        "HAMMERTOSS is a backdoor malware family used by APT29 for C2 over Twitter.",
        "PAN-OS is a network operating system developed by Palo Alto Networks.",
    ],
    extract_entities=True,
    extract_relationships=True,
)

ontology = (
    OntologyGenerator(base_uri="https://cti.example.org/ontology/", min_occurrences=1)
    .generate_from_graph(graph.to_dict(), name="CyberOntology")
)

print(f"Classes inferred: {len(ontology.get('classes', []))}")
# Classes inferred: 4  → ThreatActor, Vulnerability, Malware, Platform
```

---

## Step 2 — Generate SHACL shapes from the ontology

`SHACLGenerator` produces a `SHACLGraph` with one `NodeShape` per OWL class.

```python
from semantica.ontology import SHACLGenerator

shacl_gen = SHACLGenerator(
    base_uri="https://cti.example.org/shapes/",
    include_inherited=True,   # propagate parent-class constraints to sub-classes
    severity="Violation",     # default severity for all generated shapes
    quality_tier="standard",  # constraint strictness: "minimal" | "standard" | "strict"
)

shacl_graph = shacl_gen.generate(ontology)

print(f"Node shapes generated: {len(shacl_graph.node_shapes)}")
# Node shapes generated: 4  — one per class

for ns in shacl_graph.node_shapes:
    print(f"  {ns.target_class}  ({len(ns.property_shapes)} property constraints)")
# https://cti.example.org/ontology/ThreatActor   (2 property constraints)
# https://cti.example.org/ontology/Vulnerability  (3 property constraints)
# https://cti.example.org/ontology/Malware        (2 property constraints)
# https://cti.example.org/ontology/Platform       (1 property constraint)
```

The generated shapes tell you what the pipeline observed. They do not yet encode what your domain *requires*. The next section shows how to inject domain-specific mandatory constraints.

---

## Step 3 — Inject domain constraints

Add mandatory `PropertyShape` constraints the pipeline cannot infer from data alone.

```python
from semantica.ontology import PropertyShape

BASE = "https://cti.example.org/ontology/"

for node_shape in shacl_graph.node_shapes:

    if "Malware" in node_shape.target_class:
        # family is required — missing it causes a Violation
        node_shape.property_shapes.append(
            PropertyShape(
                path=f"{BASE}family",
                min_count=1,
                severity="Violation",
            )
        )
        # attribution_confidence is recommended — missing it causes a Warning
        node_shape.property_shapes.append(
            PropertyShape(
                path=f"{BASE}attribution_confidence",
                min_count=1,
                datatype="http://www.w3.org/2001/XMLSchema#float",
                severity="Warning",
            )
        )

    if "Vulnerability" in node_shape.target_class:
        # cvss_score is required by your detection rules
        node_shape.property_shapes.append(
            PropertyShape(
                path=f"{BASE}cvss_score",
                min_count=1,
                datatype="http://www.w3.org/2001/XMLSchema#float",
                severity="Violation",
            )
        )

    if "ThreatActor" in node_shape.target_class:
        # name is required; nation_state classification is recommended
        node_shape.property_shapes.append(
            PropertyShape(path=f"{BASE}name",         min_count=1, severity="Violation")
        )
        node_shape.property_shapes.append(
            PropertyShape(path=f"{BASE}nation_state",  min_count=1, severity="Warning")
        )

# Serialise the final shape graph to Turtle for reuse and version control
shacl_ttl = shacl_gen.serialize(shacl_graph, format="turtle")

with open("cti_shapes.ttl", "w") as f:
    f.write(shacl_ttl)

print("Shapes written to cti_shapes.ttl")
```

You can also construct shapes manually from scratch — useful when you need to express constraints the generator would never infer, such as a regex pattern on a CVE ID field:

```python
from semantica.ontology import NodeShape, PropertyShape, SHACLGraph

# Require CVE IDs to match the canonical NIST format
cve_id_shape = NodeShape(
    target_class="https://cti.example.org/ontology/Vulnerability",
    name="VulnerabilityShape",
    closed=False,
    severity="Violation",
    property_shapes=[
        PropertyShape(
            path="https://cti.example.org/ontology/cve_id",
            min_count=1,
            pattern=r"^CVE-\d{4}-\d{4,}$",   # e.g. CVE-2024-3400
            severity="Violation",
        ),
    ],
)
# Inject into the existing shacl_graph or build a standalone SHACLGraph
```

---

## Step 4 — Run validation and read the report

Serialize the graph to RDF, then run `_run_pyshacl` against the shapes.

```python
from semantica.ontology.ontology_validator import _run_pyshacl
from semantica.export import export_rdf
import tempfile, os

# Serialise the graph to a temporary Turtle file
tmp = tempfile.NamedTemporaryFile(suffix=".ttl", delete=False, mode="w")
export_rdf(graph.to_dict(), tmp.name, format="turtle")
with open(tmp.name) as f:
    data_ttl = f.read()
os.unlink(tmp.name)

# Run SHACL validation
report = _run_pyshacl(
    data_ttl,
    shacl_ttl,
    data_graph_format="turtle",
    shacl_format="turtle",
)

# High-level summary
print(f"Conforms   : {report.conforms}")
# Conforms   : False   ← at least one Violation found

print(f"Violations : {report.violation_count}")
# Violations : 3

print(f"Warnings   : {report.warning_count}")
# Warnings   : 2

print(report.summary())
# Graph does NOT conform: 3 violation(s).
```

The summary tells you something is wrong. Now drill into the details.

---

## Step 5 — Understand the violations

Each `SHACLViolation` identifies the node, property path, and fix required.

```python
if not report.conforms:
    # Print plain-English explanations for every violation
    report.explain_violations()
    # Node <https://cti.example.org/data/malware-002> is missing required property
    #   <https://cti.example.org/ontology/family>. At least 1 value(s) are required.
    # Node <https://cti.example.org/data/vuln-003> is missing required property
    #   <https://cti.example.org/ontology/cvss_score>. At least 1 value(s) are required.
    # Node <https://cti.example.org/data/vuln-003> has value 'CVE24-3400' for
    #   <https://cti.example.org/ontology/cve_id> which does not match the required pattern.

    # Iterate for programmatic triage
    for v in report.violations:
        print(f"VIOLATION  node={v.focus_node}")
        print(f"           path={v.result_path}")
        print(f"           rule={v.constraint}")
        print(f"           msg ={v.message}")
        if v.value:
            print(f"           val ={v.value}")
        if v.explanation:
            print(f"           fix ={v.explanation}")
        print()

    # Warnings are lower severity — review but do not block
    for w in report.warnings:
        print(f"WARNING  {w.focus_node}  {w.result_path}  {w.message}")
```

The output maps directly to remediation tasks: `malware-002` needs a `family` property added; `vuln-003` needs a `cvss_score` and its `cve_id` corrected to the canonical format.

---

## Step 6 — Auto-remediate common violations

Flag or patch nodes missing required properties, then re-validate to confirm.

```python
# Parse the report into a dict for programmatic processing
report_dict = report.to_dict()

# Collect nodes missing the 'family' property
missing_family = [
    v["focus_node"]
    for v in report_dict.get("violations", [])
    if "family" in (v.get("result_path") or "")
]

print(f"Malware nodes missing 'family': {len(missing_family)}")
# In production: queue these for analyst enrichment or apply a default
# e.g. graph.update_node(node_id, {"family": "UNKNOWN — requires triage"})

# After remediation, re-run validation to confirm the fix
# (re-export the patched graph to Turtle first, then call _run_pyshacl again)
report2 = _run_pyshacl(patched_data_ttl, shacl_ttl)
print(f"Violations after remediation: {report2.violation_count}")
# Violations after remediation: 0
```

---

## Domain Examples

<Tabs>

<Tab title="Defense — CTI/Threat">

A DoD CTI team enforces STIX-compatible constraints on a threat graph before sharing it with ISAC partners. Every `ThreatActor` must declare a `name` and every `Vulnerability` must carry a `cvss_score`. The validation gate runs automatically on each nightly sync.

```python
from semantica.context import AgentContext, ContextGraph
from semantica.vector_store import VectorStore
from semantica.ontology import OntologyGenerator, SHACLGenerator, PropertyShape
from semantica.ontology.ontology_validator import _run_pyshacl
from semantica.export import export_rdf
import tempfile, os

graph = ContextGraph()
ctx   = AgentContext(
    vector_store=VectorStore(backend="faiss", dimension=768),
    knowledge_graph=graph,
    graph_expansion=True,
)

ctx.store([
    "APT29 is a Russian state-sponsored threat actor targeting NATO governments.",
    "CVE-2024-3400 is a critical PAN-OS vulnerability with CVSS 10.0, exploited by APT29.",
    "HAMMERTOSS is a backdoor malware family used by APT29 for C2 over Twitter and GitHub.",
], extract_entities=True, extract_relationships=True)

ontology  = (
    OntologyGenerator(base_uri="https://cti.dod.mil/ontology/", min_occurrences=1)
    .generate_from_graph(graph.to_dict(), name="CTIOntology")
)

shacl_gen   = SHACLGenerator(
    base_uri="https://cti.dod.mil/shapes/",
    include_inherited=True,
    severity="Violation",
)
shacl_graph = shacl_gen.generate(ontology)

# STIX-aligned mandatory fields
for ns in shacl_graph.node_shapes:
    if "ThreatActor" in ns.target_class:
        ns.property_shapes.append(
            PropertyShape(path="https://cti.dod.mil/ontology/name",         min_count=1, severity="Violation")
        )
        ns.property_shapes.append(
            PropertyShape(path="https://cti.dod.mil/ontology/nation_state",  min_count=1, severity="Warning")
        )
    if "Vulnerability" in ns.target_class:
        ns.property_shapes.append(
            PropertyShape(path="https://cti.dod.mil/ontology/cvss_score",   min_count=1, severity="Violation")
        )

shacl_ttl = shacl_gen.serialize(shacl_graph, format="turtle")

tmp = tempfile.NamedTemporaryFile(suffix=".ttl", delete=False, mode="w")
export_rdf(graph.to_dict(), tmp.name, format="turtle")
with open(tmp.name) as f:
    data_ttl = f.read()
os.unlink(tmp.name)

report = _run_pyshacl(data_ttl, shacl_ttl)
print(f"CTI graph conforms : {report.conforms}")
print(f"Violations         : {report.violation_count}")
print(f"Warnings           : {report.warning_count}")

if not report.conforms:
    report.explain_violations()
    # Blocks the nightly ISAC share until violations are resolved
```

</Tab>

<Tab title="Security — SOC/Incident">

A SOC team validates zero-trust policy nodes before publishing them to the policy enforcement point. Every `Policy` node must carry a `version` (semver format) and an `effective_date`. A node missing either field is a Violation that blocks publication.

```python
from semantica.context import ContextGraph
from semantica.ontology import OntologyGenerator, SHACLGenerator, PropertyShape
from semantica.ontology.ontology_validator import _run_pyshacl
from semantica.export import export_rdf
import tempfile, os

graph = ContextGraph()
graph.add_node("policy-001", "Policy", "MFA Required for Tier-1 Resources",
               version="1.0.0", effective_date="2025-01-01", owner="security_team")
graph.add_node("policy-002", "Policy", "Admin Access Requires PAM Checkout")
# policy-002 has no version or effective_date — Violations expected

ontology = (
    OntologyGenerator(base_uri="https://zerotrust.corp/ontology/", min_occurrences=1)
    .generate_from_graph(graph.to_dict(), name="ZeroTrustOntology")
)

shacl_gen   = SHACLGenerator(base_uri="https://zerotrust.corp/shapes/", severity="Violation")
shacl_graph = shacl_gen.generate(ontology)

BASE = "https://zerotrust.corp/ontology/"
for ns in shacl_graph.node_shapes:
    if "Policy" in ns.target_class:
        ns.property_shapes += [
            PropertyShape(
                path=f"{BASE}version",
                min_count=1,
                pattern=r"^\d+\.\d+\.\d+$",   # semver
                severity="Violation",
            ),
            PropertyShape(
                path=f"{BASE}effective_date",
                min_count=1,
                datatype="http://www.w3.org/2001/XMLSchema#date",
                severity="Violation",
            ),
        ]

shacl_ttl = shacl_gen.serialize(shacl_graph, format="turtle")

tmp = tempfile.NamedTemporaryFile(suffix=".ttl", delete=False, mode="w")
export_rdf(graph.to_dict(), tmp.name, format="turtle")
with open(tmp.name) as f:
    data_ttl = f.read()
os.unlink(tmp.name)

report = _run_pyshacl(data_ttl, shacl_ttl)
print(f"Policy graph conforms: {report.conforms}")
# Policy graph conforms: False

for v in report.violations:
    print(f"  VIOLATION: {v.focus_node}  —  {v.result_path}  —  {v.message}")
# VIOLATION: ...policy-002 — ...version       — Less than 1 values on ...version
# VIOLATION: ...policy-002 — ...effective_date — Less than 1 values on ...effective_date
```

</Tab>

<Tab title="Life Science — Clinical/Pharma">

A clinical informatics team validates trial ontology nodes before loading them into the trial registry system. Every `ClinicalTrial` node must declare a `phase` (one of Phase I–IV), a `primary_endpoint`, and a `principal_investigator`. Missing any of these blocks registry submission.

```python
from semantica.ontology import LLMOntologyGenerator, SHACLGenerator, PropertyShape
from semantica.ontology.ontology_validator import _run_pyshacl
from semantica.export import export_rdf
import tempfile, os

llm_gen  = LLMOntologyGenerator(provider="openai", model="gpt-4o")
ontology = llm_gen.generate_ontology_from_text(
    """
    A phase II oncology trial studies the efficacy of Compound XR-401 in NSCLC patients.
    The trial is led by Principal Investigator Dr. Sarah Chen at Memorial Sloan Kettering.
    Primary endpoint: overall response rate at 24 weeks.
    Secondary endpoint: progression-free survival.
    """
)

shacl_gen   = SHACLGenerator(base_uri="https://purl.obolibrary.org/obo/TRIAL_shapes/")
shacl_graph = shacl_gen.generate(ontology)

TRIAL = "https://purl.obolibrary.org/obo/TRIAL_"
for ns in shacl_graph.node_shapes:
    if "ClinicalTrial" in ns.target_class or "Trial" in ns.target_class:
        ns.property_shapes += [
            PropertyShape(
                path=f"{TRIAL}phase",
                min_count=1,
                in_values=["Phase I", "Phase II", "Phase III", "Phase IV"],
                severity="Violation",
            ),
            PropertyShape(
                path=f"{TRIAL}primary_endpoint",
                min_count=1,
                severity="Violation",
            ),
            PropertyShape(
                path=f"{TRIAL}principal_investigator",
                min_count=1,
                severity="Warning",
            ),
        ]

shacl_ttl = shacl_gen.serialize(shacl_graph, format="turtle")
print(f"SHACL shapes generated — {len(shacl_graph.node_shapes)} node shapes")
# SHACL shapes generated — 5 node shapes

# Validate trial data
tmp = tempfile.NamedTemporaryFile(suffix=".ttl", delete=False, mode="w")
export_rdf(ontology, tmp.name, format="turtle")
with open(tmp.name) as f:
    data_ttl = f.read()
os.unlink(tmp.name)

report = _run_pyshacl(data_ttl, shacl_ttl)
print(f"Trial data conforms: {report.conforms}")
print(f"Warnings           : {report.warning_count}")
```

</Tab>

<Tab title="Banking — Risk/Compliance">

A credit risk team validates every `LoanApplication` node against Basel III CRE20 mandatory fields (`ltv`, `pd`, `lgd`, `asset_class`) before the application enters the credit model. Any missing field is a Violation that rejects the record.

```python
from semantica.context import ContextGraph
from semantica.ontology import OntologyGenerator, SHACLGenerator, PropertyShape
from semantica.ontology.ontology_validator import _run_pyshacl
from semantica.export import export_rdf
import tempfile, os

graph = ContextGraph()
graph.add_node("loan-001", "LoanApplication", "Prime mortgage APP-2025-88421",
               ltv=0.78, pd=0.023, lgd=0.45, asset_class="CRE")
graph.add_node("loan-002", "LoanApplication", "SME working capital facility",
               ltv=0.65)
# loan-002 is missing pd, lgd, asset_class — three Violations expected

ontology = (
    OntologyGenerator(base_uri="https://basel.eba.eu/ontology/", min_occurrences=1)
    .generate_from_graph(graph.to_dict(), name="BaselRiskOntology")
)

shacl_gen   = SHACLGenerator(base_uri="https://basel.eba.eu/shapes/", severity="Violation")
shacl_graph = shacl_gen.generate(ontology)

BASE = "https://basel.eba.eu/ontology/"
for ns in shacl_graph.node_shapes:
    if "LoanApplication" in ns.target_class:
        for field in ["ltv", "pd", "lgd", "asset_class"]:
            ns.property_shapes.append(
                PropertyShape(
                    path=f"{BASE}{field}",
                    min_count=1,
                    severity="Violation",
                )
            )

shacl_ttl = shacl_gen.serialize(shacl_graph, format="turtle")

tmp = tempfile.NamedTemporaryFile(suffix=".ttl", delete=False, mode="w")
export_rdf(graph.to_dict(), tmp.name, format="turtle")
with open(tmp.name) as f:
    data_ttl = f.read()
os.unlink(tmp.name)

report = _run_pyshacl(data_ttl, shacl_ttl)
print(f"Loan portfolio conforms: {report.conforms}")
# Loan portfolio conforms: False

print(f"Violations             : {report.violation_count}")
# Violations             : 3

for v in report.violations:
    print(f"  [{v.severity}]  {v.focus_node.split('/')[-1]}  —  {v.result_path.split('/')[-1]}")
# [Violation]  loan-002 — pd
# [Violation]  loan-002 — lgd
# [Violation]  loan-002 — asset_class

# Export violation report for regulatory audit trail
report_dict = report.to_dict()
```

</Tab>

</Tabs>

---

## Using SHACL validation as a CI/CD gate

Call this function as a pre-publish gate; exit code 1 blocks the pipeline.

```python
import sys
from semantica.ontology import OntologyGenerator, SHACLGenerator
from semantica.ontology.ontology_validator import _run_pyshacl

def validate_before_publish(data_graph_str: str, ontology: dict) -> None:
    shacl_gen   = SHACLGenerator(base_uri="https://example.org/shapes/")
    shacl_graph = shacl_gen.generate(ontology)
    shacl_ttl   = shacl_gen.serialize(shacl_graph, format="turtle")

    report = _run_pyshacl(data_graph_str, shacl_ttl)

    if not report.conforms:
        print(f"Graph validation FAILED — {report.violation_count} violation(s)")
        report.explain_violations()
        sys.exit(1)

    print(f"Graph validation PASSED ({report.warning_count} warning(s))")
```

---

## Related Guides

- [Ontology Management](ontology) — generate the OWL ontology that SHACL shapes are derived from
- [Reasoning & Rules](reasoning) — complement SHACL structural constraints with logical inference rules
- [Export & Serialization](export) — serialize graph data to Turtle/RDF/XML for `_run_pyshacl` input
- [Conflict Resolution](conflict-resolution) — detect and resolve data conflicts before SHACL validation
- [Change Management](change-management) — version-gate SHACL shapes alongside ontology versions
