---
title: "Ontology Module"
description: "Automated ontology generation, SHACL validation, OWL/RDF export, namespace management, and LLM-powered ontology generation."
icon: "sitemap"
---

`semantica.ontology` provides the full lifecycle for knowledge graph schemas:

- Auto-generate ontologies from KG data via a 5-stage pipeline (Semantic Network → YAML → Types → Hierarchy → TTL)
- LLM-powered ontology generation for complex domains via `LLMOntologyGenerator`
- SHACL validation: generate shapes, validate graphs, and get violation reports
- OWL/RDF export in Turtle, RDF/XML, and JSON-LD formats
- Ontology Hub visual editor available in `semantica.explorer` (v0.5.0)


## Exported Classes

| Class | Role |
| :--- | :--- |
| `OntologyEngine` | Unified facade orchestrating the full ontology lifecycle |
| `OntologyGenerator` | Auto-generate ontologies from KG data (5-stage pipeline) |
| `LLMOntologyGenerator` | LLM-powered ontology generation for complex domains |
| `SHACLGenerator` | Generate SHACL shapes from an ontology or KG schema |
| `OntologyValidator` | Validate any graph against SHACL shapes — returns `SHACLValidationReport` |
| `OWLGenerator` | Serialize ontologies to Turtle, RDF/XML, JSON-LD |
| `NamespaceManager` | IRI generation, prefix management, and namespace binding |
| `OntologyEvaluator` | Coverage, completeness, and granularity quality metrics |
| `ClassInferrer` | Infer classes from entity type patterns |
| `PropertyGenerator` | Generate properties from entity attributes and relationships |
| `AssociativeClassBuilder` | Model N-ary relationships as intermediate OWL classes |


## Getting Started

**`OntologyEngine`** is your main entry point for the complete ontology workflow:

```python
from semantica.ontology import OntologyEngine

# Initialize with base URI for your domain
engine = OntologyEngine(base_uri="https://example.org/ontology/")

# Generate ontology from your knowledge graph data
ontology = engine.from_data({"entities": entities, "relationships": relationships})

# Validate a graph against the generated SHACL shapes
report = engine.validate_graph(kg, ontology=ontology)
if not report.conforms:
    for v in report.violations:
        print(f"{v.severity}: {v.message} on {v.focus_node}")

# Export to OWL Turtle
engine.export_owl(ontology, "ontology.ttl", format="turtle")
```

## OntologyEngine (Unified Facade)

**`OntologyEngine`** orchestrates the full ontology lifecycle — **generation, validation, export, and evaluation**:

```python
from semantica.ontology import OntologyEngine

engine = OntologyEngine(base_uri="https://example.org/ontology/")

# Generate ontology from KG data
ontology = engine.from_data({"entities": entities, "relationships": relationships})

# Validate a graph against the generated SHACL shapes
report = engine.validate_graph(kg, ontology=ontology)
if not report.conforms:
    for v in report.violations:
        print(f"{v.severity}: {v.message} on {v.focus_node}")

# Export to OWL Turtle
engine.export_owl(ontology, "ontology.ttl", format="turtle")
```

### OntologyEngine Methods

| Method | Description |
| :------ | :----------- |
| `from_data(data)` | Run the 5-stage pipeline on entity/relationship data |
| `validate_graph(kg, ontology=...)` | Check a knowledge graph against generated SHACL shapes |
| `export_owl(ontology, path, format)` | Serialize to `"turtle"`, `"xml"`, or `"json-ld"` |
| `evaluate(ontology, kg)` | Compute coverage, completeness, and granularity metrics |

## OntologyGenerator (5-Stage Pipeline)

**`OntologyGenerator`** auto-generates a formal ontology from your knowledge graph entities and relationships:

```python
from semantica.ontology import OntologyGenerator

generator = OntologyGenerator(base_uri="https://example.org/ontology/")
ontology  = generator.generate_ontology({
    "entities":      entities,
    "relationships": relationships,
})
```

<Steps>
  <Step title="Semantic Network Parsing">
    Extract concepts and patterns from entity types and relationship structures in the source data.
  </Step>
  <Step title="YAML-to-Definition">
    Transform the extracted patterns into intermediate class and property definitions.
  </Step>
  <Step title="Definition-to-Types">
    Map definitions to OWL constructs: `owl:Class`, `owl:ObjectProperty`, `owl:DatatypeProperty`.
  </Step>
  <Step title="Hierarchy Generation">
    Build taxonomy trees using transitive closure and cycle detection — produces `rdfs:subClassOf` chains.
  </Step>
  <Step title="TTL Generation">
    Serialize the final ontology to Turtle format using `rdflib`. Also available: RDF/XML and JSON-LD.
  </Step>
</Steps>

## SHACL Validation

Generate SHACL shapes from an ontology and validate any graph against them:

```python
from semantica.ontology import SHACLGenerator, OntologyValidator, SHACLValidationReport, SHACLViolation

# Generate shapes from ontology
generator  = SHACLGenerator()
shapes     = generator.generate(ontology)
shapes_ttl = shapes.serialize(format="turtle")

# Validate a graph against the shapes
validator = OntologyValidator()
report: SHACLValidationReport = validator.validate_graph(kg, ontology=ontology)

if not report.conforms:
    violation: SHACLViolation
    for violation in report.violations:
        print(f"{violation.severity}: {violation.message}")
        print(f"  Node: {violation.focus_node}")
        print(f"  Path: {violation.result_path}")
```

### Validation Report Fields

| Field | Type | Description |
| :----- | :---- | :----------- |
| `conforms` | `bool` | `True` if the graph passes all SHACL constraints |
| `violations` | `List[SHACLViolation]` | Detailed failure records |
| `focus_node` | `str` | IRI of the violating graph node |
| `result_path` | `str` | IRI of the violating property path |
| `severity` | `str` | `"Violation"`, `"Warning"`, or `"Info"` |
| `message` | `str` | Human-readable constraint failure description |

## LLM-Powered Ontology Generation

For complex or novel domains where schema patterns are hard to infer statistically:

```python
from semantica.ontology import LLMOntologyGenerator

# Initialize with your preferred LLM provider
generator = LLMOntologyGenerator(provider="openai")  # or "anthropic", "groq", etc.
ontology  = generator.generate_ontology_from_text(
    text="A biomedical ontology for clinical trial protocols involving patients, trials, interventions, and outcomes."
)
```
```

## OWL / RDF Export

```python
from semantica.ontology import OWLGenerator

generator = OWLGenerator()
generator.export_owl(ontology, path="ontology.ttl",  format="turtle")
generator.export_owl(ontology, path="ontology.owl",  format="xml")
generator.export_owl(ontology, path="ontology.json", format="json-ld")
```

## Namespace Management

```python
from semantica.ontology import NamespaceManager

ns = NamespaceManager(base_uri="https://example.org/")
ns.register("ex",     "https://example.org/")
ns.register("schema", "https://schema.org/")
ns.register("owl",    "http://www.w3.org/2002/07/owl#")

# Generate IRIs for classes and properties
class_iri    = ns.generate_class_iri("Person")
property_iri = ns.generate_property_iri("worksFor")
```

## Ontology Evaluation

Measure coverage, completeness, and granularity of a generated ontology:

```python
from semantica.ontology import OntologyEvaluator

evaluator = OntologyEvaluator()
result    = evaluator.evaluate_ontology(ontology, kg)

print(f"Class coverage:    {result.class_coverage:.2f}")
print(f"Property coverage: {result.property_coverage:.2f}")
print(f"Completeness:      {result.completeness:.2f}")
print(f"Granularity:       {result.granularity:.2f}")

for gap in result.gaps:
    print(f"Gap: {gap.description}")
```

## Common Workflows

<Tabs>
  <Tab title="Quick Start">
    **Generate and validate an ontology in 3 steps:**

    ```python
    from semantica.ontology import OntologyEngine

    # 1. Initialize engine
    engine = OntologyEngine(base_uri="https://yourcompany.com/ontology/")

    # 2. Generate from your data
    ontology = engine.from_data({"entities": entities, "relationships": relationships})

    # 3. Validate against a knowledge graph
    report = engine.validate_graph(kg, ontology=ontology)
    if report.conforms:
        print("✓ Graph conforms to ontology")
    else:
        print(f"✗ Found {len(report.violations)} violations")
    ```
  </Tab>
  <Tab title="LLM-Powered Generation">
    **Generate ontologies from text descriptions:**

    ```python
    from semantica.ontology import LLMOntologyGenerator

    generator = LLMOntologyGenerator(provider="openai")
    ontology = generator.generate_ontology_from_text("""
        Create an e-commerce ontology with products, customers, orders, 
        categories, reviews, and payment methods.
    """)

    # Refine with additional constraints
    engine = OntologyEngine()
    validated = engine.validate(ontology)
    ```
  </Tab>
  <Tab title="Export and Integration">
    **Export ontologies in multiple formats:**

    ```python
    from semantica.ontology import OntologyEngine

    engine = OntologyEngine()

    # Export as OWL/Turtle for Protégé
    engine.export_owl(ontology, "schema.ttl", format="turtle")

    # Export as JSON-LD for web applications
    engine.export_owl(ontology, "schema.jsonld", format="json-ld")

    # Generate SHACL shapes for validation
    engine.export_shacl(ontology, "shapes.ttl")
    ```
  </Tab>
</Tabs>

## Ingest an Existing Ontology

Load and parse an ontology file for downstream use:

```python
from semantica.ontology import ingest_ontology

ontology_data = ingest_ontology("schema.ttl")     # Turtle
ontology_data = ingest_ontology("schema.owl")     # OWL/XML
ontology_data = ingest_ontology("schema.jsonld")  # JSON-LD
```

<Note>
  Ontology versioning (`VersionManager`, `OntologyVersion`) has moved to `semantica.change_management`. Import from there: `from semantica.change_management import VersionManager`.
</Note>

<CardGroup cols={2}>
  <Card title="Reasoning" icon="microchip" href="reasoning">
    Apply inference rules over ontology axioms.
  </Card>
  <Card title="Knowledge Graph" icon="diagram-project" href="kg">
    The graph being modeled by the ontology.
  </Card>
  <Card title="Export" icon="file-export" href="export">
    Export ontologies as RDF, OWL, or JSON-LD.
  </Card>
  <Card title="Conflicts" icon="triangle-exclamation" href="conflicts">
    Detect ontology constraint violations.
  </Card>
</CardGroup>
