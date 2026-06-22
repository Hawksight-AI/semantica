---
title: "Ontology Management"
description: "Generate OWL ontologies from your knowledge graph, validate class hierarchies, infer properties, and export to Turtle, RDF/XML, or JSON-LD."
---

`OntologyGenerator` derives a formal OWL ontology directly from the entities and relationships already in your knowledge graph — no schema design upfront. Use it to produce a machine-readable contract for your graph's classes and properties, then export to Turtle, OWL/XML, or JSON-LD for SHACL validation, reasoning engines, and STIX/TAXII toolchains.

<Info>
Semantica's ontology module derives formal OWL ontologies directly from entities and relationships already in your knowledge graph — no schema design upfront. A 6-stage pipeline infers classes, builds hierarchies, maps OWL types, and serialises to Turtle. The pipeline runs in memory; you do not need a running triple store.
</Info>

---

## The graph that has no schema

Populate a knowledge graph with CTI data to make the pipeline mechanics visible.

```python
from semantica.context import AgentContext, ContextGraph
from semantica.vector_store import VectorStore

vs    = VectorStore(backend="faiss", dimension=768)
graph = ContextGraph()
ctx   = AgentContext(vector_store=vs, knowledge_graph=graph, graph_expansion=True)

ctx.store(
    [
        "CVE-2024-3400 is a critical vulnerability in PAN-OS exploited by APT29.",
        "APT29 is a Russian state-sponsored threat actor targeting NATO governments.",
        "PAN-OS is a network operating system developed by Palo Alto Networks.",
        "HAMMERTOSS is a backdoor malware used by APT29 for command-and-control.",
    ],
    extract_entities=True,
    extract_relationships=True,
)

# At this point we have ~8 nodes and several edges, but no formal schema.
# "APT29" and a hypothetical "Lazarus Group" are both ThreatActors —
# but nothing enforces that both must have an attribution_confidence property.
print(f"Graph nodes: {len(graph.to_dict().get('nodes', []))}")
```

---

## Generating the ontology

`OntologyGenerator` reads your graph dict and runs the 6-stage pipeline.

```python
from semantica.ontology import OntologyGenerator

generator = OntologyGenerator(
    base_uri="https://cti.example.org/ontology/",
    min_occurrences=1,   # every entity type that appears at least once becomes a class
)

ontology = generator.generate_from_graph(
    graph.to_dict(),
    name="CyberThreatOntology",
    build_hierarchy=True,  # infer parent-child class relationships
)

# What the pipeline produced:
print(f"Classes   : {len(ontology.get('classes', []))}")
# Classes   : 4  → ThreatActor, Vulnerability, Software, Malware

print(f"Properties: {len(ontology.get('properties', []))}")
# Properties: 3  → exploits (object), targets (object), name (datatype)

# Inspect a class:
for cls in ontology.get("classes", []):
    print(f"  {cls['name']}  parent={cls.get('parent')}")
# ThreatActor   parent=None
# Vulnerability parent=None
# Software      parent=None
# Malware       parent=Software   ← hierarchy inferred because HAMMERTOSS was linked to PAN-OS (Software)
```

The hierarchy entry for `Malware` shows the pipeline detected that malware is a sub-type of software based on co-occurrence patterns in the relationship graph. You can override these inferences manually before exporting.

---

## Validating the schema

Run structural validation before exporting.

```python
from semantica.ontology import validate_ontology

result = validate_ontology(ontology)

print(f"Valid: {result.get('valid', False)}")
# Valid: True

for w in result.get("warnings", []):
    print(f"  WARN : {w}")
# WARN : Class 'Malware' has no declared datatype properties

for e in result.get("errors", []):
    print(f"  ERROR: {e}")
# (none — the ontology is structurally sound)
```

A warning about missing datatype properties is common at this stage. It means the inference pipeline found the class in your graph but none of the nodes carried explicit attribute values. You can add properties manually using `ClassInferrer` and `PropertyGenerator` before the next export cycle.

---

## Growing the ontology as new node types emerge

Use `ClassInferrer` to add new entity types incrementally without regenerating the full ontology.

```python
from semantica.ontology import ClassInferrer, PropertyGenerator

# Fine-grained control: infer classes from the new batch of entities
new_entities = [
    {"id": "kev-001", "name": "KEV-CVE-2024-3400", "type": "KEVEntry",
     "due_date": "2024-04-19", "ransomware_use": "Known"},
    {"id": "kev-002", "name": "KEV-CVE-2023-4966", "type": "KEVEntry",
     "due_date": "2023-11-14", "ransomware_use": "Unknown"},
]

inferrer = ClassInferrer()
new_classes = inferrer.infer_classes(new_entities)
# [{"id": "KEVEntry", "name": "KEVEntry", "parent": None, ...}]

# Manually set the parent to Vulnerability before merging
for cls in new_classes:
    if cls["name"] == "KEVEntry":
        cls["parent"] = "https://cti.example.org/ontology/Vulnerability"

# Inspect the hierarchy
hierarchy = inferrer.build_class_hierarchy(new_classes)
print(hierarchy)
# {"KEVEntry": {"parent": "...Vulnerability", "children": []}}

# Merge into the existing ontology
ontology["classes"].extend(new_classes)

# Infer properties from the new nodes
prop_gen = PropertyGenerator()
# PropertyGenerator reads entity attributes and relationship patterns
# to produce datatype properties (due_date: xsd:date) and object properties
```

The pattern here is incremental: you run `infer_classes` on each new batch, review the results, adjust parent assignments where the pipeline guessed wrong, and merge. The ontology grows with the graph rather than falling behind it.

---

## Generating an ontology from unstructured text

`LLMOntologyGenerator` extracts classes and properties from prose using an LLM — useful for bootstrapping when no structured graph exists yet.

```python
from semantica.ontology import LLMOntologyGenerator

llm_gen = LLMOntologyGenerator(provider="groq", model="llama-3.1-8b-instant")

ontology_from_text = llm_gen.generate_ontology_from_text(
    """
    APT29 (also known as Cozy Bear) is a Russian state-sponsored threat actor.
    They use spear-phishing emails to deliver HAMMERTOSS malware.
    HAMMERTOSS communicates over Twitter and GitHub to evade detection.
    The group has been observed exploiting CVE-2024-3400 in PAN-OS appliances.
    """
)

# The LLM identified: ThreatActor, Malware, Vulnerability, Platform, CommunicationChannel
print(f"Classes extracted: {len(ontology_from_text.get('classes', []))}")

# Supported providers: "groq", "openai", "anthropic", "novita"
```

<Info>
`LLMOntologyGenerator` is best for bootstrapping a new domain where no structured graph exists yet. Once you have a graph, prefer `OntologyGenerator.generate_from_graph()` — it is deterministic, reproducible, and does not consume LLM tokens on every run.
</Info>

---

## Exporting for downstream systems

Export in the format your downstream tools expect.

```python
from semantica.export import export_owl, export_rdf

# OWL/XML — for Protégé, OWL API, HermiT, Pellet
export_owl(ontology, "cyber_threat.owl", format="owl-xml")

# Turtle — compact, human-readable; preferred for SHACL toolchains
export_rdf(ontology, "cyber_threat.ttl", format="turtle")

# JSON-LD — for web APIs and linked-data applications
export_rdf(ontology, "cyber_threat.jsonld", format="jsonld")

# N-Triples — for bulk load into triple stores (GraphDB, Stardog, Oxigraph)
export_rdf(ontology, "cyber_threat.nt", format="ntriples")
```

The exported Turtle file is the input to Semantica's SHACL validation pipeline. See the [SHACL Validation](shacl-validation) guide for how to generate constraint shapes from this ontology and run them against live graph data.

---

## Domain Examples

<Tabs>

<Tab title="Defense — CTI/Threat">

A defense CTI team ingests raw OSINT reports each morning. The ontology must stay interoperable with STIX 2.1 and the NATO MISP taxonomy, so IRIs follow the DoD namespace and the ontology is exported to OWL/XML for the org's SIEM reasoning plugin.

```python
from semantica.context import AgentContext, ContextGraph
from semantica.vector_store import VectorStore
from semantica.ingest import ingest_file, ingest_web
from semantica.ontology import OntologyGenerator, validate_ontology
from semantica.export import export_owl, export_rdf

vs    = VectorStore(backend="faiss", dimension=768)
graph = ContextGraph()
ctx   = AgentContext(vector_store=vs, knowledge_graph=graph, graph_expansion=True)

# Ingest a campaign PDF and NVD advisory page
cti_report = ingest_file("apt29_cozycar_2024.pdf", method="file")
nvd_entry  = ingest_web("https://nvd.nist.gov/vuln/detail/CVE-2024-3400", method="url")

ctx.store(
    [cti_report.text, nvd_entry.text],
    extract_entities=True,
    extract_relationships=True,
)

generator = OntologyGenerator(
    base_uri="https://ontology.dod.mil/cyber/",
    min_occurrences=1,
)
ontology = generator.generate_from_graph(
    graph.to_dict(),
    name="CyberThreatOntology",
    build_hierarchy=True,
)

result = validate_ontology(ontology)
print(f"Ontology valid: {result.get('valid')}")
# Ontology valid: True

# OWL/XML for the SIEM reasoning plugin; Turtle for the SHACL pipeline
export_owl(ontology, "./ontologies/cyber_threat.owl", format="owl-xml")
export_rdf(ontology, "./ontologies/cyber_threat.ttl", format="turtle")

print(f"Classes    : {len(ontology.get('classes', []))}")
print(f"Properties : {len(ontology.get('properties', []))}")
# Classes    : 7  (ThreatActor, Vulnerability, Malware, Platform, Campaign, ...)
# Properties : 9  (exploits, targets, uses, name, cvss_score, ...)
```

</Tab>

<Tab title="Security — SOC/Incident">

A SOC team models zero-trust identity entities — users, service accounts, resources, and policies — as an OWL ontology so their policy evaluation engine can use a shared formal vocabulary instead of hard-coded strings.

```python
from semantica.ontology import OntologyGenerator, ClassInferrer
from semantica.export import export_owl

# Hand-specify the identity graph — in production this comes from your IAM export
data = {
    "entities": [
        {"id": "u-1",  "name": "alice",      "type": "User"},
        {"id": "u-2",  "name": "svc-scanner","type": "ServiceAccount"},
        {"id": "r-1",  "name": "kube-api",   "type": "Resource"},
        {"id": "r-2",  "name": "s3-prod",    "type": "Resource"},
        {"id": "p-1",  "name": "ReadOnly",   "type": "Policy"},
        {"id": "p-2",  "name": "AdminAccess","type": "Policy"},
    ],
    "relationships": [
        {"source_id": "u-1", "target_id": "p-1", "type": "BOUND_TO"},
        {"source_id": "u-2", "target_id": "p-2", "type": "BOUND_TO"},
        {"source_id": "p-1", "target_id": "r-1", "type": "ALLOWS_ACCESS"},
        {"source_id": "p-2", "target_id": "r-2", "type": "ALLOWS_ACCESS"},
    ],
}

generator = OntologyGenerator(
    base_uri="https://zerotrust.corp/ontology/",
    min_occurrences=1,
)
ontology = generator.generate_ontology(data, name="ZeroTrustOntology")

# Inspect what the pipeline inferred
inferrer = ClassInferrer()
classes  = inferrer.infer_classes(data["entities"])
for cls in classes:
    print(f"  Class: {cls.get('name')}")
# Class: User
# Class: ServiceAccount
# Class: Resource
# Class: Policy

export_owl(ontology, "./ontologies/zero_trust.owl", format="owl-xml")
print("Ontology exported for policy evaluation engine")
```

</Tab>

<Tab title="Life Science — Clinical/Pharma">

A pharma team needs an ontology aligned to OBO Foundry conventions (GO, CHEBI, HP) to describe Phase II/III oncology trial protocols. Because the source data lives in a PostgreSQL trials database — not a knowledge graph — they use `LLMOntologyGenerator` to bootstrap from prose descriptions.

```python
from semantica.ontology import LLMOntologyGenerator, OntologyGenerator, validate_ontology
from semantica.export import export_owl, export_rdf
from semantica.ingest import DBIngestor

# Load trial records from the clinical database
db = DBIngestor()
trial_rows = db.execute_query(
    "postgresql://readonly@clindb:5432/trials",
    """
        SELECT compound, target_protein, disease_indication,
               mechanism_of_action, primary_endpoint
        FROM trial_protocols WHERE phase IN ('II','III')
    """,
)

# Construct a natural-language summary for the LLM
protocol_text = "\n".join(
    f"Compound {r['compound']} targets {r['target_protein']} "
    f"in {r['disease_indication']} via {r['mechanism_of_action']}. "
    f"Primary endpoint: {r['primary_endpoint']}."
    for r in trial_rows
)

# LLM extracts classes: Compound, TargetProtein, DiseaseIndication,
#   MechanismOfAction, ClinicalEndpoint, ClinicalTrial
llm_gen  = LLMOntologyGenerator(provider="openai", model="gpt-4o")
ontology = llm_gen.generate_ontology_from_text(protocol_text)

result = validate_ontology(ontology)
print(f"Valid: {result.get('valid')}")
for w in result.get("warnings", []):
    print(f"  WARN: {w}")

# Export aligned to OBO Foundry URI convention
export_owl(ontology, "./ontologies/clinical_trial.owl", format="owl-xml")
export_rdf(ontology, "./ontologies/clinical_trial.ttl", format="turtle")
print("Ontology ready for Protégé review and OBO alignment check")
```

</Tab>

<Tab title="Banking — Risk/Compliance">

A risk team formalises Basel III / BCBS 239 concepts as an OWL ontology so automated compliance rules can reason over credit risk entities with a shared vocabulary — replacing hard-coded field-name checks in Python scripts.

```python
from semantica.ontology import LLMOntologyGenerator, validate_ontology
from semantica.export import export_owl, export_rdf
from semantica.ingest import ingest_file

# Ingest regulatory source documents
regs = [
    ingest_file("basel3_cre20.pdf", method="file"),
    ingest_file("sr_11_7.pdf",      method="file"),
    ingest_file("bcbs239.pdf",      method="file"),
]

# Use an LLM to extract the conceptual model from regulatory prose
llm_gen  = LLMOntologyGenerator(provider="anthropic", model="claude-sonnet-4-20250514")
ontology = llm_gen.generate_ontology_from_text(
    "\n\n".join(r.text[:8000] for r in regs)  # token-safe excerpt per document
)

result = validate_ontology(ontology)
if not result.get("valid"):
    for err in result.get("errors", []):
        print(f"ERROR: {err}")
    # Fix errors before publishing to the compliance rule engine
else:
    print("Ontology valid — publishing to compliance registry")
    # Turtle for SHACL shapes; OWL/XML for HermiT reasoning; JSON-LD for the API
    export_owl(ontology, "./ontologies/regulatory.owl",    format="owl-xml")
    export_rdf(ontology, "./ontologies/regulatory.ttl",    format="turtle")
    export_rdf(ontology, "./ontologies/regulatory.jsonld", format="jsonld")
```

</Tab>

</Tabs>

---

## Related Guides

- [SHACL Validation](shacl-validation) — generate W3C SHACL constraint shapes from your ontology and validate live graph data against them
- [Reasoning & Rules](reasoning) — apply forward/backward-chaining rules over your ontology to derive new facts
- [Export & Serialization](export) — export graphs to RDF, GraphML, CSV, and Neo4j Cypher
- [Semantic Extraction](semantic-extraction) — extract entities and relationships that feed ontology generation
- [Context Graphs](context-graphs) — the knowledge graph that ontology generation reads from
