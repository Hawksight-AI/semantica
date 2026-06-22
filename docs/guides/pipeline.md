---
title: "Pipeline Builder"
description: "Build end-to-end data processing workflows with the PipelineBuilder DSL — ingest, extract, normalize, embed, and store in a single declarative pipeline."
---

`PipelineBuilder` solves the glue problem between processing steps. Declare your steps, register handler functions, wire the connections, and hand control to `ExecutionEngine` — it handles topological ordering, passes output between steps, retries on failure with configurable backoff, and returns a structured `ExecutionResult` you can log or alert on.

<Info>
  `PipelineBuilder` and `ExecutionEngine` are in `semantica.pipeline`. Failure handling, retry policies, and parallelism management are separate classes you can import individually for fine-grained control. Custom step handlers are plain Python functions — no subclassing required.
</Info>

## Your First Pipeline

The minimum viable pipeline has three steps: ingest, extract, store. Define them, connect them, build, execute:

```python
from semantica.pipeline import PipelineBuilder, ExecutionEngine
from semantica.ingest import ingest_file
from semantica.context import AgentContext, ContextGraph
from semantica.vector_store import VectorStore

# --- Define handler functions ---
# The engine calls handler(data, **step_config), so the first positional
# argument is always the upstream data; step config arrives as kwargs.

def ingest_stix_bundles(data, **config):
    files = ingest_file(config["path"], method="directory")
    return [f.text for f in files if f.file_type == "json"]

def extract_entities(data, **config):
    # data is the output from the previous step
    threshold = config.get("confidence_threshold", 0.7)
    results = []
    for text in data:
        # Your NER logic here — simplified for illustration
        results.append({"text": text, "entities": [], "threshold": threshold})
    return results

def build_graph(data, **config):
    graph   = ContextGraph(advanced_analytics=True)
    context = AgentContext(
        vector_store    = VectorStore(backend="faiss", dimension=768),
        knowledge_graph = graph,
    )
    texts = [d["text"] for d in data]
    context.store(texts, extract_entities=True, extract_relationships=True)
    context.save(config["output_path"])
    return {"node_count": graph.stats()["node_count"],
            "edge_count": graph.stats()["edge_count"]}

# --- Build the pipeline ---
# Pass handler= directly in add_step() so each PipelineStep carries its callable.

builder = PipelineBuilder()

builder.add_step("ingest",  "stix_ingest",  handler=ingest_stix_bundles, path="./stix_bundles/")
builder.add_step("extract", "ner_extract",  handler=extract_entities,    confidence_threshold=0.75)
builder.add_step("store",   "kg_build",     handler=build_graph,         output_path="./cti_output/")

builder.connect_steps("ingest",  "extract")
builder.connect_steps("extract", "store")

pipeline = builder.build("cti_pipeline")

# --- Execute ---

engine = ExecutionEngine(max_workers=4, retry_on_failure=True)
result = engine.execute_pipeline(pipeline)

print(f"Success:  {result.success}")
print(f"Output:   {result.output}")   # {"node_count": 312, "edge_count": 847}
print(f"Duration: {result.metrics['execution_time']:.2f}s")
print(f"Steps completed: {result.metrics['steps_executed']}")
```

`ExecutionEngine` performs a topological sort of the step graph before executing, so even if you declare steps in the wrong order the execution sequence is always correct. Each step receives the previous step's return value as its `data` argument.

## Reading the ExecutionResult

Every `engine.execute_pipeline()` call returns an `ExecutionResult` dataclass. Check it before assuming success:

```python
result = engine.execute_pipeline(pipeline)

if not result.success:
    print("Pipeline failed. Errors:")
    for err in result.errors:
        print(f"  {err}")
else:
    print(f"Pipeline completed in {result.metrics['execution_time']:.1f}s")
    print(f"Steps run:    {result.metrics['steps_executed']}")
    print(f"Steps failed: {result.metrics['steps_failed']}")
    # result.output  — the return value of the final step
    # result.metadata — {"pipeline_id": "...", "execution_time": float}
```

`result.errors` is a `List[str]` — one entry per failed step, each containing the exception message. A pipeline with `retry_on_failure=True` attempts each failed step up to `max_retries` times (default: 3) before recording it as a failure and moving on.

## Handling Failures and Configuring Retry Policy

By default, `ExecutionEngine(retry_on_failure=True)` uses an exponential backoff policy: three retries, starting at 1 second, doubling each time, capped at 60 seconds. For steps that call external APIs or databases — where transient failures are expected — you can set per-step-type policies via `FailureHandler`:

```python
from semantica.pipeline import ExecutionEngine, FailureHandler, RetryPolicy, RetryStrategy

# Build a custom failure handler
handler = FailureHandler()

# Web/API steps: retry up to 5 times with exponential backoff
handler.set_retry_policy(
    "misp_fetch",
    RetryPolicy(
        max_retries    = 5,
        strategy       = RetryStrategy.EXPONENTIAL,
        backoff_factor = 2.0,
        initial_delay  = 2.0,
        max_delay      = 120.0,
    ),
)

# Database steps: fixed delay, fewer retries (connection pool usually recovers fast)
handler.set_retry_policy(
    "db_ingest",
    RetryPolicy(
        max_retries   = 3,
        strategy      = RetryStrategy.FIXED,
        initial_delay = 5.0,
    ),
)

# NER steps: don't retry — if the model crashes it needs human intervention
handler.set_retry_policy(
    "ner_extract",
    RetryPolicy(max_retries=0),
)

engine = ExecutionEngine(
    max_workers      = 4,
    retry_on_failure = True,
)
# The engine uses handler.get_retry_policy(step.step_type) when a step fails
```

`handler.classify_error()` distinguishes `ValidationError` (low severity, usually don't retry), `ProcessingError` (high severity), and timeout/connection errors (medium severity, always retry). You can inspect the classification:

```python
try:
    result = engine.execute_pipeline(pipeline)
except Exception as e:
    classification = handler.classify_error(e)
    print(f"Severity: {classification['severity'].value}")   # "high" / "medium" / "low"
    print(f"Message: {classification['message']}")
```

## Running Steps in Parallel

When two steps don't depend on each other — for example, NER extraction and triplet extraction both reading from the same ingest output — declare them as parallel branches by connecting both to the same upstream step:

```python
builder = PipelineBuilder()
builder.register_step_handler("file_ingest",     ingest_stix_bundles)
builder.register_step_handler("ner_extract",     run_ner)
builder.register_step_handler("triplet_extract", run_triplets)
builder.register_step_handler("kg_merge",        merge_into_graph)

builder.add_step("ingest",   "file_ingest",     handler=ingest_stix_bundles, path="./stix_bundles/")
builder.add_step("ner",      "ner_extract",     handler=run_ner,             confidence_threshold=0.75)
builder.add_step("triplets", "triplet_extract", handler=run_triplets,        include_temporal=True)
builder.add_step("store",    "kg_merge",        handler=merge_into_graph,    output_path="./cti_output/")

# ingest feeds both ner and triplets in parallel
builder.connect_steps("ingest",   "ner")
builder.connect_steps("ingest",   "triplets")
# both converge into store
builder.connect_steps("ner",      "store")
builder.connect_steps("triplets", "store")

builder.set_parallelism(2)   # run ner and triplets concurrently

pipeline = builder.build("parallel_extraction")
engine   = ExecutionEngine(max_workers=2, retry_on_failure=True)
result   = engine.execute_pipeline(pipeline)
```

`set_parallelism(n)` tells the engine how many steps it may run simultaneously. The topological sort guarantees that only steps whose dependencies are all completed are eligible for concurrent execution — you cannot accidentally run a step before its inputs are ready.

## Delta / Incremental Processing

Your STIX bundle directory grows by 20–30 new files each night. Re-processing all 4,000 historical files every morning wastes time and compute. `delta_mode=True` on the ingest step tells the pipeline to process only files that have changed since the last version snapshot:

```python
builder = PipelineBuilder()
builder.register_step_handler("stix_ingest", ingest_stix_bundles)
builder.register_step_handler("ner_extract", run_ner)
builder.register_step_handler("kg_append",   append_to_graph)

builder.add_step(
    "ingest", "stix_ingest",
    handler           = ingest_stix_bundles,
    path              = "./stix_bundles/",
    delta_mode        = True,
    base_version_id   = "2024-11-30",   # last successful run
    target_version_id = "2024-12-01",   # today's snapshot
)
builder.add_step("extract", "ner_extract", handler=run_ner)
builder.add_step("store",   "kg_append",   handler=append_to_graph, output_path="./cti_output/")

builder.connect_steps("ingest",  "extract")
builder.connect_steps("extract", "store")

pipeline = builder.build("delta_pipeline")
result   = ExecutionEngine(max_workers=4, retry_on_failure=True).execute_pipeline(pipeline)

print(f"Delta run: {result.output}")
```

The `base_version_id` and `target_version_id` are stored on the `PipelineStep` dataclass and passed through to your handler via `config` — your handler is responsible for using them to filter its input. A typical pattern is to check file modification timestamps against the base version date.

## Building from a Config Dict

For pipelines defined in config files — useful when different environments (dev, staging, prod) run the same pipeline with different paths and thresholds — pass a dict to `build_pipeline()` instead of calling `add_step()` manually:

```python
from semantica.pipeline import PipelineBuilder, ExecutionEngine

pipeline_config = {
    "name": "cti_pipeline",
    "parallelism": 4,
    "steps": [
        {
            "name": "ingest",
            "type": "stix_ingest",
            "config": {"path": "./stix_bundles/"},
        },
        {
            "name": "extract",
            "type": "ner_extract",
            "config": {"confidence_threshold": 0.8},
        },
        {
            "name": "store",
            "type": "kg_build",
            "config": {"output_path": "./cti_output/"},
        },
    ],
}

builder = PipelineBuilder()
# Register handlers as before, then:
pipeline = builder.build_pipeline(pipeline_config)

engine = ExecutionEngine(max_workers=4, retry_on_failure=True)
result = engine.execute_pipeline(pipeline)
```

Note that `build_pipeline()` reads step connections from the `"dependencies"` key inside each step's config dict (not from `connect_steps()` calls). Add dependencies explicitly if you use this path:

```python
{
    "name": "extract",
    "type": "ner_extract",
    "config": {"confidence_threshold": 0.8, "dependencies": ["ingest"]},
},
```

## Monitoring Progress

`ExecutionEngine` integrates with Semantica's progress tracker automatically — every step start, update, and completion is recorded. To observe progress during a long-running pipeline, inspect step status on the `Pipeline` object after execution:

```python
from semantica.pipeline import StepStatus

result   = engine.execute_pipeline(pipeline)
for step in pipeline.steps:
    status_str = step.status.value   # "completed" / "failed" / "skipped"
    print(f"  {step.name:20s}  {status_str}")
    if step.status == StepStatus.FAILED and step.error:
        print(f"    Error: {step.error}")
```

`result.metrics` gives the aggregate view:

```python
print(f"Total time:      {result.metrics['execution_time']:.2f}s")
print(f"Steps completed: {result.metrics['steps_executed']}")
print(f"Steps failed:    {result.metrics['steps_failed']}")
```

## Domain Examples

<Tabs>
  <Tab title="Defense — CTI/Threat">
    A SOC threat intelligence team needs an end-to-end pipeline that ingests STIX bundles from a classified directory, runs entity extraction with custom threat-actor labels, and builds a `ContextGraph` ready for analyst queries. The pipeline runs every six hours; failed steps retry automatically so a transient filesystem error doesn't drop an ingestion cycle.

```python
from semantica.pipeline import PipelineBuilder, ExecutionEngine, RetryPolicy, RetryStrategy
from semantica.ingest import ingest_file
from semantica.semantic_extract import NamedEntityRecognizer
from semantica.context import AgentContext, ContextGraph
from semantica.vector_store import VectorStore

def ingest_classified_stix(data, **config):
    files = ingest_file(config["path"], method="directory")
    return [
        {"text": f.text, "source": f.name, "classification": config["classification"]}
        for f in files if f.file_type == "json"
    ]

def extract_cti_entities(data, **config):
    ner = NamedEntityRecognizer(
        methods=["pattern", "ml"],
        custom_labels=["THREAT_ACTOR", "MALWARE", "CVE", "C2_DOMAIN", "CAMPAIGN"],
        confidence_threshold=config.get("confidence_threshold", 0.80),
    )
    results = []
    for doc in data:
        entities = ner.extract_entities(doc["text"])
        results.append({**doc, "entities": [e.__dict__ for e in entities]})
    return results

def build_cti_graph(data, **config):
    graph   = ContextGraph(advanced_analytics=True, community_detection=True)
    context = AgentContext(
        vector_store    = VectorStore(backend="faiss", dimension=768),
        knowledge_graph = graph,
        graph_expansion = True,
    )
    texts = [d["text"] for d in data]
    context.store(texts, extract_entities=True, extract_relationships=True)
    context.save(config["output_path"])
    return graph.stats()

builder = PipelineBuilder()
builder.register_step_handler("classified_ingest", ingest_classified_stix)
builder.register_step_handler("cti_ner",           extract_cti_entities)
builder.register_step_handler("cti_graph",         build_cti_graph)

builder.add_step("ingest",  "classified_ingest",
                 handler=ingest_classified_stix,
                 path="./classified/stix/",
                 classification="SECRET//REL TO USA FVEY")
builder.add_step("extract", "cti_ner", handler=extract_cti_entities, confidence_threshold=0.85)
builder.add_step("store",   "cti_graph", handler=build_cti_graph, output_path="./cti_state/")

builder.connect_steps("ingest",  "extract")
builder.connect_steps("extract", "store")
builder.set_parallelism(2)

pipeline = builder.build("cti_pipeline")
engine   = ExecutionEngine(max_workers=2, retry_on_failure=True)
result   = engine.execute_pipeline(pipeline)

print(f"CTI pipeline: success={result.success}, "
      f"nodes={result.output.get('node_count')}, "
      f"time={result.metrics['execution_time']:.1f}s")
```

  </Tab>

  <Tab title="Security — SOC/Incident">
    During an active P1 incident, the SOC needs a 15-minute pipeline that pulls fresh SIEM alert CSVs, cross-references CVEs from the internal database, and updates the incident knowledge graph. The pipeline runs on a tight cycle — NER failures must not block the graph update, so steps are configured to not retry on NER errors but to retry aggressively on database timeouts.

```python
from semantica.pipeline import (
    PipelineBuilder, ExecutionEngine, FailureHandler,
    RetryPolicy, RetryStrategy,
)
from semantica.ingest import ingest_file, DBIngestor
from semantica.context import AgentContext, ContextGraph
from semantica.vector_store import VectorStore

def ingest_siem_alerts(data, **config):
    files = ingest_file(config["path"], method="directory")
    return [{"text": f.text, "source": f.name}
            for f in files if f.file_type == "csv"]

def enrich_with_cves(data, **config):
    db = DBIngestor()
    cve_rows = db.execute_query(config["db_url"], config["query"])
    cve_lookup = {r["cve_id"]: r for r in cve_rows}
    for doc in data:
        doc["cve_enrichment"] = cve_lookup
    return data

def update_incident_graph(data, **config):
    graph   = ContextGraph(advanced_analytics=True)
    context = AgentContext(
        vector_store    = VectorStore(backend="faiss", dimension=768),
        knowledge_graph = graph,
    )
    texts = [d["text"] for d in data]
    context.store(texts, extract_entities=True, extract_relationships=True)
    context.save(config["output_path"])
    return graph.stats()

handler = FailureHandler()
handler.set_retry_policy("db_enrich",
    RetryPolicy(max_retries=5, strategy=RetryStrategy.EXPONENTIAL,
                initial_delay=2.0, max_delay=30.0))
handler.set_retry_policy("cti_ner", RetryPolicy(max_retries=0))

builder = PipelineBuilder()
builder.register_step_handler("siem_ingest",  ingest_siem_alerts)
builder.register_step_handler("db_enrich",    enrich_with_cves)
builder.register_step_handler("graph_update", update_incident_graph)

builder.add_step("ingest",  "siem_ingest",  handler=ingest_siem_alerts, path="./siem_exports/")
builder.add_step("enrich",  "db_enrich",
                 handler=enrich_with_cves,
                 db_url="postgresql://ro:pass@cvedb:5432/nvd",
                 query="SELECT cve_id, description, cvss_v3_score FROM cve_records "
                       "WHERE cve_id = ANY(ARRAY['CVE-2024-3400','CVE-2024-21762'])")
builder.add_step("store",   "graph_update", handler=update_incident_graph, output_path="./incident_state/")

builder.connect_steps("ingest",  "enrich")
builder.connect_steps("enrich",  "store")

pipeline = builder.build("incident_pipeline")
engine   = ExecutionEngine(max_workers=4, retry_on_failure=True)
result   = engine.execute_pipeline(pipeline)

print(f"Incident update: {result.success}, "
      f"nodes={result.output.get('node_count')}, "
      f"errors={result.errors}")
```

  </Tab>

  <Tab title="Life Science — Clinical/Pharma">
    A clinical NLP pipeline processes EHR exports after each trial month closes: ingest patient notes from a shared directory, run biomedical NER using a HuggingFace model to extract drug/disease/dosage entities, record ICH E6(R2)-compliant provenance, and append to the trial graph. The pipeline uses delta mode so only notes added since the last run are processed.

```python
from semantica.pipeline import PipelineBuilder, ExecutionEngine
from semantica.ingest import ingest_file
from semantica.semantic_extract import NamedEntityRecognizer
from semantica.provenance import ProvenanceManager, SourceReference
from semantica.context import AgentContext, ContextGraph
from semantica.vector_store import VectorStore

def ingest_ehr_notes(data, **config):
    files = ingest_file(config["path"], method="directory")
    return [
        {"text": f.text, "patient_id": f.name.split("_")[0], "source": f.name}
        for f in files
    ]

def run_biomedical_ner(data, **config):
    ner = NamedEntityRecognizer(
        methods=["huggingface"],
        huggingface_model="d4data/biomedical-ner-all",
        confidence_threshold=config.get("confidence_threshold", 0.80),
        custom_labels=["DRUG", "DISEASE", "DOSAGE", "GENE", "BIOMARKER"],
    )
    results = []
    for doc in data:
        entities = ner.extract_entities(doc["text"])
        results.append({**doc, "entities": entities})
    return results

def track_provenance_and_store(data, **config):
    manager = ProvenanceManager(storage_path=config["provenance_db"])
    graph   = ContextGraph(advanced_analytics=True)
    context = AgentContext(
        vector_store    = VectorStore(backend="faiss", dimension=768),
        knowledge_graph = graph,
        retention_days  = None,
    )
    for doc in data:
        for entity in doc.get("entities", []):
            source = SourceReference(
                document=doc["patient_id"],
                section="clinical_note",
                confidence=getattr(entity, "confidence", 1.0),
            )
            manager.track_entity(
                entity_id=f"{doc['patient_id']}_{getattr(entity, 'text', '')}",
                source=source.document,
                metadata={"entity_type": getattr(entity, "label", ""),
                           "confidence": getattr(entity, "confidence", 1.0)},
            )
    context.store([d["text"] for d in data], extract_entities=True)
    context.save(config["output_path"])
    return graph.stats()

builder = PipelineBuilder()
builder.register_step_handler("ehr_ingest",    ingest_ehr_notes)
builder.register_step_handler("bio_ner",       run_biomedical_ner)
builder.register_step_handler("prov_store",    track_provenance_and_store)

builder.add_step("ingest",  "ehr_ingest",
                 handler=ingest_ehr_notes,
                 path="./ehr_exports/month_12/",
                 delta_mode=True,
                 base_version_id="2024-11",
                 target_version_id="2024-12")
builder.add_step("extract", "bio_ner", handler=run_biomedical_ner, confidence_threshold=0.82)
builder.add_step("store",   "prov_store",
                 handler=track_provenance_and_store,
                 provenance_db="./provenance/trial_Q4.db",
                 output_path="./trial_state/")

builder.connect_steps("ingest",  "extract")
builder.connect_steps("extract", "store")
builder.set_parallelism(4)

pipeline = builder.build("clinical_nlp_pipeline")
engine   = ExecutionEngine(max_workers=4, retry_on_failure=True)
result   = engine.execute_pipeline(pipeline)

print(f"Clinical pipeline: {result.success}, "
      f"nodes={result.output.get('node_count')}")
```

  </Tab>

  <Tab title="Banking — Risk/Compliance">
    A compliance team runs a monthly incremental pipeline: ingest new BIS publications from the sitemap, extract capital-ratio and threshold entities, and append them to the existing compliance knowledge graph that already holds three years of regulatory history. Delta mode ensures only pages published since the last run are processed.

```python
from semantica.pipeline import PipelineBuilder, ExecutionEngine
from semantica.ingest import ingest_web
from semantica.semantic_extract import NamedEntityRecognizer, TripletExtractor
from semantica.context import AgentContext, ContextGraph
from semantica.vector_store import VectorStore

def ingest_bis_pages(data, **config):
    pages = ingest_web(config["sitemap"], method="sitemap")
    return [
        {"text": p.text, "url": p.url}
        for p in pages
        if p.text.strip() and any(
            kw in p.url.lower() for kw in ["bcbs", "capital", "liquidity"]
        )
    ]

def extract_regulatory_entities(data, **config):
    ner = NamedEntityRecognizer(
        methods=["pattern", "ml"],
        custom_labels=["REGULATION", "CAPITAL_RATIO", "RISK_WEIGHT", "THRESHOLD"],
        confidence_threshold=config.get("confidence_threshold", 0.75),
    )
    extractor = TripletExtractor(
        method="pattern", include_temporal=True, include_provenance=True,
    )
    results = []
    for doc in data:
        entities = ner.extract_entities(doc["text"])
        triplets = extractor.extract_triplets(doc["text"], entities=entities)
        results.append({**doc, "entities": entities, "triplets": triplets})
    return results

def append_to_compliance_graph(data, **config):
    graph = ContextGraph(advanced_analytics=True)
    graph.load_from_file(config["existing_graph"])
    context = AgentContext(
        vector_store    = VectorStore(backend="faiss", dimension=768),
        knowledge_graph = graph,
        retention_days  = 2555,   # 7-year regulatory requirement
    )
    context.store([d["text"] for d in data],
                  extract_entities=True, extract_relationships=True)
    context.save(config["output_path"])
    return {"added_docs": len(data), "graph": graph.stats()}

builder = PipelineBuilder()
builder.register_step_handler("bis_ingest",   ingest_bis_pages)
builder.register_step_handler("rule_extract", extract_regulatory_entities)
builder.register_step_handler("graph_append", append_to_compliance_graph)

builder.add_step("ingest",  "bis_ingest",
                 handler=ingest_bis_pages,
                 sitemap="https://www.bis.org/sitemap.xml",
                 delta_mode=True,
                 base_version_id="2024-11",
                 target_version_id="2024-12")
builder.add_step("extract", "rule_extract", handler=extract_regulatory_entities, confidence_threshold=0.75)
builder.add_step("store",   "graph_append",
                 handler=append_to_compliance_graph,
                 existing_graph="./compliance_graph/knowledge_graph.json",
                 output_path="./compliance_graph/")

builder.connect_steps("ingest",  "extract")
builder.connect_steps("extract", "store")
builder.set_parallelism(4)

pipeline = builder.build("regulatory_pipeline")
engine   = ExecutionEngine(max_workers=4, retry_on_failure=True)
result   = engine.execute_pipeline(pipeline)

print(f"Compliance delta update: {result.output}")
```

  </Tab>
</Tabs>

## Related Guides

- [Ingest](ingest) — all source types for the ingest step: PDFs, APIs, databases, RSS feeds, STIX directories, and streams
- [Semantic Extraction](semantic-extraction) — NER, relation extraction, triplet extraction, and event detection for the extract step
- [Context Graphs](context-graphs) — building and querying the `ContextGraph` that the store step populates
- [Provenance](provenance) — tracking the origin document, confidence score, and pipeline run ID for every extracted entity
