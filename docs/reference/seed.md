---
title: "Seed Module"
description: "Bootstrap Knowledge Graphs from verified, structured sources: taxonomies, reference tables, product catalogs, and domain anchors."
icon: "database"
---

**`semantica.seed`** gives your knowledge graph a **reliable, verified starting point**:

- Load verified reference data first: ISO codes, employee rosters, product catalogs, domain taxonomies
- `SeedDataManager` merges freshly extracted data onto foundation nodes without creating duplicates
- Supports JSON, CSV, and programmatic registration of seed sources
- Deterministic test graph generation from structured seed data
- Anchors entity extraction to known entities, reducing hallucination and duplicate nodes


## Exported Classes

| Class | Role |
| :--- | :--- |
| `SeedDataManager` | Coordinator: `register_source`, `load_source`, `create_foundation_graph`, `integrate_with_extracted` |
| `SeedDataSource` | Config dataclass: `{name, format, location, entity_type, verified, version, metadata}` |
| `SeedData` | Container dataclass: `{entities, relationships, properties, metadata}` |

## What You Get

- **SeedDataManager** — Register sources, build a foundation graph, validate quality, and merge with extracted data.
- **SeedDataSource** — Typed source definition supporting CSV, JSON, SQL, and API with format-specific config.
- **Foundation Graph** — Build a foundation graph from all registered sources in one pass, ready to merge with extracted data.
- **Merge Strategies** — `seed_first`, `extracted_first`, and `merge` with property-level conflict detection.
- **Validation** — Required field checks, ID uniqueness, type consistency, reference integrity, and encoding validation before loading.
- **Versioning** — Track seed data versions across pipeline runs and diff changes between versions.

<Tip>
  **When to use the Seed Module:** Bootstrapping with structured reference data (taxonomies, user lists, product catalogs), loading immutable facts (ISO country codes, standard ontology terms) that extracted data should not override, ensuring test reproducibility with deterministic datasets, and anchoring entity disambiguation with canonical forms.
</Tip>

## Quick Start

<Steps>
  <Step title="Register your seed sources">
    ```python
    from semantica.seed import SeedDataManager

    manager = SeedDataManager()

    manager.register_source("countries",  "csv",  "data/countries.csv")
    manager.register_source("taxonomy",   "json", "data/taxonomy.json")
    manager.register_source("employees",  "csv",  "data/employees.csv")
    ```

    <Tip>
      **Register all sources before calling `create_foundation_graph()`.** `create_foundation_graph()` processes all registered sources in one pass. Registering a source after calling it means that source is silently excluded. Register all sources at the start of your script, then call `create_foundation_graph()` once.
    </Tip>
  </Step>
  <Step title="Build the foundation graph">
    ```python
    foundation_kg = manager.create_foundation_graph()
    print(f"Foundation nodes: {len(foundation_kg['entities'])}")
    print(f"Foundation edges: {len(foundation_kg['relationships'])}")
    ```
  </Step>
  <Step title="Validate before loading">
    ```python
    # Note: validate_quality expects a graph dict, but load_source returns a list.
    # For demonstration, validate the foundation graph instead.
    report = manager.validate_quality(foundation_kg)
    if not report["valid"]:
        for error in report["errors"]:
            print(f"Error: {error}")
        for warning in report["warnings"]:
            print(f"Warning: {warning}")
    else:
        print(f"Validated {report['metrics']['entity_count']} entities: no issues found")
    ```

    <Warning>
      **Validate before loading.** `manager.validate_quality(seed_data)` catches missing required fields, type inconsistencies, and duplicate IDs before they corrupt your graph. Running validation after loading means you'll need to roll back. Validation is fast: always run it first.
    </Warning>
  </Step>
  <Step title="Merge with extracted data">
    ```python
    from semantica.semantic_extract import NERExtractor

    extractor = NERExtractor(method="ml")
    new_entities = extractor.extract("Apple Inc. partners with Microsoft Corp.")
    
    # Merge with seed data - note the correct parameter names
    final_kg = manager.integrate_with_extracted(
        seed_data=foundation_kg,
        extracted_data={"entities": new_entities, "relationships": []},
        merge_strategy="merge"
    )
    ```

    <Warning>
      **Load seed data before extracted data.** Seed data is your ground truth: normalised, curated, and already de-duplicated. Load it first with `create_foundation_graph()`, then merge extracted entities on top. Merging in the wrong order lets noisy extracted data overwrite trusted reference values.
    </Warning>
  </Step>
</Steps>

## SeedDataSource Types

<Tabs>
  <Tab title="CSV">
    ```python
    from semantica.seed import SeedDataSource, SeedDataManager

    csv_source = SeedDataSource(
        name="employees",
        format="csv",
        location="data/employees.csv",
        entity_type="Person",
        verified=True,
        metadata={"description": "Company employee list with titles and departments"}
    )

    manager = SeedDataManager()
    manager.register_source(
        "employees", "csv", "data/employees.csv", entity_type="Person", verified=True
    )
    ```
  </Tab>
  <Tab title="JSON">
    ```python
    json_source = SeedDataSource(
        name="taxonomy",
        format="json",
        location="knowledge/taxonomy.json",
        entity_type="Concept",
        relationship_type="subclass_of",
        verified=True,
        metadata={"version": "2.1", "source": "domain_expert"}
    )

    manager.register_source(
        "taxonomy", "json", "knowledge/taxonomy.json",
        entity_type="Concept", relationship_type="subclass_of"
    )
    ```
  </Tab>
  <Tab title="Database">
    ```python
    db_source = SeedDataSource(
        name="geographic",
        format="database",
        location="postgresql://user:pass@host/geonames",
        entity_type="Location",
        verified=False,  # needs validation
        metadata={"table": "countries", "last_sync": "2024-01-15"}
    )

    manager.register_source(
        "geographic", "database", "postgresql://user:pass@host/geonames",
        entity_type="Location", verified=False
    )
    ```
  </Tab>
  <Tab title="API">
    ```python
    api_source = SeedDataSource(
        name="wikidata",
        format="api",
        location="https://wikidata.org/sparql",
        entity_type="Entity",
        metadata={"auth_required": False, "rate_limit": 60}
    )

    manager.register_source(
        "wikidata", "api", "https://wikidata.org/sparql",
        entity_type="Entity"
    )
    ```
  </Tab>
</Tabs>

## SeedDataManager Reference

| Method | Description |
| :------ | :----------- |
| `register_source(name, format, location, **config)` | Add a new data source to the manager |
| `load_source(source_name)` | Load and return raw data from a registered source |
| `create_foundation_graph()` | Build the initial graph from all registered sources |
| `integrate_with_extracted(seed_data, extracted_data, merge_strategy)` | Merge seed data with newly extracted entities/relationships |
| `validate_quality(seed_data)` | Check data integrity and return validation report |
| `export_seed_data(path, format)` | Save processed seed data to file |

Different strategies for resolving conflicts during `integrate_with_extracted()`:

<Tabs>
  <Tab title="seed_first">
    **Seed data wins conflicts**: preserves curated relationships over extracted ones.

    ```python
    final_kg = manager.integrate_with_extracted(
        seed_data=foundation_kg,
        extracted_data=new_data,
        merge_strategy="seed_first"
    )
    ```

    Use when seed data is high-confidence and extraction is exploratory.
  </Tab>
  <Tab title="extracted_first">
    **Extracted data wins conflicts**: overwrites seed with fresh information.

    ```python
    final_kg = manager.integrate_with_extracted(
        seed_data=foundation_kg,
        extracted_data=new_data,
        merge_strategy="extracted_first"
    )
    ```

    Use for rapid prototyping when extraction quality is known to be good.
  </Tab>
  <Tab title="merge">
    **Intelligent conflict resolution**: merges complementary attributes, deduplicates entities.

    ```python
    final_kg = manager.integrate_with_extracted(
        seed_data=foundation_kg,
        extracted_data=new_data,
        merge_strategy="merge"
    )
    ```

    Use for production pipelines when both seed and extracted data are valuable.
  </Tab>
</Tabs>

<Tip>
  **Use `seed_first` merge strategy for reference data.** When seed data encodes authoritative facts (official company names, canonical taxonomy IDs, employee records), `merge_strategy="seed_first"` ensures those values win over extracted values. Use `merge` only when extracted data may be more current than the seed.
</Tip>

## Full Pipeline Example

```python
from semantica.seed import SeedDataManager
from semantica.parse import DocumentParser
from semantica.split import TextSplitter
from semantica.semantic_extract import NERExtractor, RelationExtractor

# Initialize components
manager   = SeedDataManager()
parser    = DocumentParser()
splitter  = TextSplitter(method="sentence", chunk_size=200)
ner       = NERExtractor(method="ml")
rel_ext   = RelationExtractor(method="ml")

# Register seed sources
manager.register_source("taxonomy", "json", "seeds/domain_taxonomy.json")
manager.register_source("entities", "csv",  "seeds/known_entities.csv")

# Create foundation
foundation_kg = manager.create_foundation_graph()
print(f"Foundation: {len(foundation_kg['entities'])} entities, {len(foundation_kg['relationships'])} relationships")

# Process new document
parsed = parser.parse("research_paper.pdf")
chunks = splitter.split(parsed["full_text"])

# Extract from each chunk
all_entities = []
all_relations = []
for chunk in chunks:
    entities = ner.extract(chunk.text)
    relations = rel_ext.extract(chunk.text)
    all_entities.extend(entities)
    all_relations.extend(relations)

# Merge with foundation
extracted_data = {"entities": all_entities, "relationships": all_relations}
final_kg = manager.integrate_with_extracted(
    seed_data=foundation_kg,
    extracted_data=extracted_data,
    merge_strategy="merge"
)

print(f"Final graph: {len(final_kg['entities'])} entities, {len(final_kg['relationships'])} relationships")

# Export for downstream use
manager.export_seed_data("output/enriched_kg.json", format="json")
```

## YAML Configuration

Define sources in YAML for production deployments: no code changes needed to switch environments:

```yaml
seed:
  sources:
    - name: "employees"
      format: "csv"
      location: "./data/employees.csv"
      config:
        id_column: "employee_id"
        type: "Person"
    - name: "taxonomy"
      format: "json"
      location: "./data/taxonomy.json"
    - name: "products"
      format: "sql"
      location: "${DATABASE_URL}"
      config:
        query: "SELECT id, name, category FROM products WHERE active = true"
  merge:
    strategy: "merge"
  validation:
    strict: true
    required_fields: ["id", "type"]
```

Environment variable overrides:

```bash
export SEMANTICA_SEED_DATA_DIR=./data/seed
export SEMANTICA_SEED_MERGE_STRATEGY=seed_first
```

<Tip>
  **Use YAML configuration for production deployments.** Hard-coding source paths in Python scripts makes environment-switching (dev → staging → prod) fragile. Declare sources in `config.yaml` under the `seed:` key and override paths with `SEMANTICA_SEED_DATA_DIR`. This way, the same code runs in every environment.
</Tip>

- [Ingest](ingest) — Load unstructured data alongside seed data.
- [Knowledge Graph](kg) — The target graph that seed data populates.
- [Deduplication](deduplication) — Handle duplicates during seed-extracted merge.
- [Pipeline](pipeline) — Incorporate seed loading as a named pipeline step.
