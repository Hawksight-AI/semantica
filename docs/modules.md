---
title: "Modules"
description: "Every Semantica module works independently: use only what you need."
icon: "puzzle-piece"
---

<Info>
  Jump to the [Module Index](#module-index) for a quick reference.
</Info>

<Tip>
  The [Choose the Right Module](/choose-your-module) guide maps 35+ developer goals to modules with code examples; start there if you're orienting for the first time.
</Tip>

Semantica is organized into **27 modules** across six logical layers. Each module is independently importable: you never pay for what you don't use.

## Architecture Overview

- **Input Layer**: data ingestion and preparation. Modules: `ingest`, `parse`, `split`, `normalize`
- **Core Processing**: intelligence and understanding. Modules: `semantic_extract`, `kg`, `ontology`, `reasoning`
- **Storage**: persistent data storage. Modules: `embeddings`, `vector_store`, `graph_store`, `triplet_store`
- **Quality Assurance**: data quality and consistency. Modules: `deduplication`, `conflicts`
- **Context & Memory**: agent memory and decision tracking. Modules: `context`, `provenance`, `change_management`
- **Output & Orchestration**: export, visualization, and workflows. Modules: `export`, `visualization`, `pipeline`, `explorer`


## Input Layer

### Ingest

Loads data from files, web, databases, and streams. Each ingestor returns its own
result type (`FileIngestor` → `FileObject`, `WebIngestor` → `WebContent`, …);
document-oriented ones expose a `.text` payload and `.metadata`.

```python
from semantica.ingest import FileIngestor, WebIngestor, ParquetIngestor, XMLIngestor, DatabricksIngestor

# Files: PDF, DOCX, CSV, Excel, PPTX, JSON, HTML, archives
ingestor = FileIngestor()
documents = ingestor.ingest_directory("data/")

# Web page: returns a WebContent with .text, .title, .links, .metadata
web_ingestor = WebIngestor()
page = web_ingestor.ingest_url("https://example.com")

# Parquet: single file, partitioned directory, Hive-style (v0.5.0)
parquet = ParquetIngestor()
sources = parquet.ingest("data/events.parquet")

# XML with XSD/DTD validation, namespace handling (v0.5.0)
xml = XMLIngestor()
sources = xml.ingest("data/records/", schema_path="schema.xsd")

# Enterprise lakehouse/warehouse: Unity Catalog + Delta Lake, or a Snowflake warehouse
databricks = DatabricksIngestor(host="...", token="...", http_path="...")
customers   = databricks.ingest_table("customers")
```

**Available ingestors:** `FileIngestor`, `WebIngestor`, `ParquetIngestor`, `XMLIngestor`, `RESTIngestor`, `PublicAPIIngestor`, `DBIngestor`, `DatabricksIngestor`, `SnowflakeIngestor`, `EmailIngestor`, `FeedIngestor`, `MCPIngestor`, `OntologyIngestor`, `RepoIngestor`, `StreamIngestor`, `ArrowIngestor`, `CloudStorageIngestor`

<Note>
  `DuckDBIngestor`, `ElasticIngestor`, `GDriveIngestor`, `HuggingFaceIngestor`, `MongoIngestor`, and `PandasIngestor` also ship but aren't re-exported from the top-level `semantica.ingest` namespace yet; import them directly, e.g. `from semantica.ingest.duckdb_ingestor import DuckDBIngestor`.
</Note>

### Parse

Extracts structured text and layout metadata from raw documents.

```python
from semantica.parse import DocumentParser, DoclingParser

# Standard parser: all common formats. parse() takes a path, returns a dict
parser = DocumentParser()
parsed = parser.parse("document.pdf")   # {"full_text": ..., "metadata": ..., ...}

# Advanced parser (pip install semantica[parse-docling]): tables, OCR, layout
parser = DoclingParser(export_format="markdown", enable_ocr=True)
parsed = parser.parse("data/annual_report.pdf")   # dict with full_text, tables, pages
```

**Available parsers:** `DocumentParser`, `DoclingParser`, `CodeParser`, `CSVParser`, `DocxParser`, `EmailParser`, `ExcelParser`, `HTMLParser`, `ImageParser`, `JSONParser`, `MCPParser`, `MediaParser`, `PDFParser`, `PPTXParser`, `StructuredDataParser`, `WebParser`, `XMLParser`

### Split

Chunks text for embedding and RAG pipelines with awareness of semantic boundaries.

```python
from semantica.split import TextSplitter

# chunk_size / chunk_overlap are constructor arguments
splitter = TextSplitter(method="semantic_transformer", chunk_size=1000, chunk_overlap=200)
chunks = splitter.split(text)
```

**Chunking methods:** `recursive`, `token`, `sentence`, `paragraph`, `semantic_transformer`, `entity_aware`, `relation_aware`, `graph_based`, `ontology_aware`, `hierarchical`, `community_detection`, `centrality_based`, `llm`

### Normalize

Cleans and standardizes text before semantic processing.

```python
from semantica.normalize import TextNormalizer, normalize_text, normalize_date

normalizer = TextNormalizer()
clean_text        = normalizer.normalize_text(text)
standardized_date = normalize_date("Jan 1st, 2020")
```

**Normalizers available:** text cleaning, entity canonicalization, date normalization, number normalization, encoding handling, language detection


## Core Processing

### Semantic Extract

Named entity recognition, relation extraction, and triplet generation.

```python
from semantica.semantic_extract import NERExtractor, RelationExtractor, TripletExtractor

# LLM method: provider + llm_model select the backend; the API key comes from the env
ner = NERExtractor(method="llm", provider="groq", llm_model="llama-3.3-70b-versatile")
entities = ner.extract("Apple Inc. was founded by Steve Jobs.")   # list[Entity]

rel = RelationExtractor(method="llm", provider="groq", llm_model="llama-3.3-70b-versatile")
relationships = rel.extract(text, entities=entities)              # list[Relation]

trip = TripletExtractor(method="pattern")
triplets = trip.extract(text)                                     # list[Triplet]
```

**Extraction methods:** `"pattern"` (no API key), `"ml"` (local spaCy model), `"llm"` (any of the 9 supported providers)

**Additional extractors:** `CoreferenceResolver`, `EventDetector`, `SemanticAnalyzer`, `SemanticNetworkExtractor`

### Knowledge Graph

Graph construction, graph algorithms, temporal model, and distance intelligence.

```python
from semantica.kg import GraphBuilder, GraphAnalyzer, TemporalGraphQuery, SimilarityCalculator
from datetime import datetime

# Build: build() takes a {"entities": ..., "relationships": ...} dict
builder = GraphBuilder(merge_entities=True)
kg = builder.build({"entities": entities, "relationships": relationships})

# Temporal graphs (v0.4.0)
query_engine = TemporalGraphQuery(enable_temporal_reasoning=True)
snapshot = query_engine.query_at_time(kg, query="", at_time=datetime(2021, 6, 15))

# Semantic similarity (v0.5.0): operates on embedding vectors
calc = SimilarityCalculator(method="cosine")
score = calc.cosine_similarity(vec_a, vec_b)
```

**Graph algorithms available:** centrality calculation, community detection, connectivity analysis, entity resolution, link prediction, path finding, similarity calculation

### Ontology

Schema management including SHACL, SKOS, alignments, diff/migration, auto-generation, and the visual Ontology Hub (v0.5.0).

```python
from semantica.ontology import OntologyGenerator, SHACLGenerator

generator = OntologyGenerator()
ontology  = generator.generate_from_graph(kg)

shacl  = SHACLGenerator()
shapes = shacl.generate(ontology)
```

**Components:** `OntologyGenerator`, `SHACLGenerator`, `OntologyValidator`, `OntologyEvaluator`, `LLMOntologyGenerator`, `OWLGenerator`, `PropertyGenerator`, `DomainOntologies`, `NamespaceManager`

### Reasoning

Derives new facts from existing knowledge using multiple inference strategies.

```python
from semantica.reasoning import Reasoner, DatalogReasoner

# Forward chaining: facts and rules as predicate(args) / IF-THEN strings
engine = Reasoner()
engine.add_fact("Manager(Alice)")
engine.add_rule("IF Manager(?x) THEN HasAuthority(?x)")
results = engine.forward_chain()          # list[InferenceResult] with .conclusion, .rule_used

# Datalog: recursive Horn clause rules (v0.4.0)
datalog = DatalogReasoner()
datalog.add_fact("parent(tom, bob)")
datalog.add_fact("parent(bob, ann)")
datalog.add_rule("ancestor(X, Y) :- parent(X, Y).")
datalog.add_rule("ancestor(X, Z) :- parent(X, Y), ancestor(Y, Z).")
datalog.derive_all()
results = datalog.query("ancestor(tom, ?Z)")   # [{"Z": "bob"}, {"Z": "ann"}], order not guaranteed
```

**Engines:** `Reasoner` (forward/backward chaining), `ReteEngine`, `SPARQLReasoner`, `DatalogReasoner`, `TemporalReasoningEngine`, `GraphReasoner` (LLM)


## Storage

### Embeddings

Generates and manages vector embeddings for semantic similarity.

```python
from semantica.embeddings import EmbeddingGenerator

generator  = EmbeddingGenerator()
embeddings = generator.generate_embeddings(["text1", "text2"])   # np.ndarray
similarity = generator.compare_embeddings(embeddings[0], embeddings[1])
```

**Supported models:** Sentence-Transformers, FastEmbed, OpenAI, BGE

**Components:** `EmbeddingGenerator`, `TextEmbedder`, `VectorEmbeddingManager`, `GraphEmbeddingManager`, `PoolingStrategies`

### Vector Store

Multi-backend vector database with hybrid search support.

```python
from semantica.vector_store import VectorStore

store = VectorStore(backend="faiss", dimension=768)

# Raw vectors
ids     = store.store_vectors(embeddings)                 # returns generated ids
hits    = store.search_vectors(query_vector, k=10)

# Or store text and let the store embed it
store.add_documents(["Apple was founded in 1976.", "Google was founded in 1998."])
results = store.search("tech company founding dates", limit=10)
```

**Backends:** FAISS, Pinecone, Weaviate, Qdrant, Milvus, PgVector, SQLite, in-memory

**Search modes:** semantic top-k, hybrid (vector + keyword), metadata-filtered

### Graph Store

Connects to graph databases for persistent, query-able storage.

```python
from semantica.graph_store import GraphStore

store = GraphStore(backend="neo4j")
store.add_nodes([{"id": "acme", "type": "Organization", "properties": {"name": "Acme"}}])
store.add_edges([{"source": "alice", "target": "acme", "type": "works_for"}])
results = store.query("MATCH (n)-[r]->(m) RETURN n, r, m")
```

**Backends:** Neo4j, FalkorDB, Apache AGE, Amazon Neptune

### Triplet Store

RDF triple-based storage with SPARQL query support.

```python
from semantica.triplet_store import TripletStore

store = TripletStore(backend="oxigraph")
store.add_triplets(triplets)                 # list of Triplet objects (or add_triplet for one)
results = store.execute_query("SELECT ?s ?p ?o WHERE { ?s ?p ?o }")
```

**Backends:** Oxigraph (embedded), Blazegraph, Apache Jena, RDF4J


## Quality Assurance

### Deduplication

Detects, scores, and merges duplicate entities across sources.

```python
from semantica.deduplication import DuplicateDetector, EntityMerger

detector   = DuplicateDetector(similarity_threshold=0.85)
candidates = detector.detect_duplicates(entities)

merger     = EntityMerger()
operations = merger.merge_duplicates(entities, strategy="keep_most_complete")
```

**v2 candidate-generation modes** (`blocking_v2`, `hybrid_v2`, `semantic_v2`) are up to 7x faster than v1.

**Components:** `DuplicateDetector`, `EntityMerger`, `ClusterBuilder`, `MergeStrategyManager`

**`DuplicateDetector` options:** `max_results`, `top_k_per_entity`, `min_similarity`, `sort_by`

### Conflicts

Detects and resolves fact conflicts across overlapping knowledge sources.

```python
from semantica.conflicts import ConflictDetector, ConflictResolver

conflicts = ConflictDetector().detect_conflicts(entities)   # list of entity dicts
resolved  = ConflictResolver().resolve_conflicts(conflicts, strategy="most_recent")
```

**Detection types:** value conflicts, type conflicts, relationship conflicts, temporal conflicts, logical conflicts

**Resolution strategies:** prefer most recent, prefer most reliable source, majority vote, flag for manual review


## Context & Memory

### Context

Agent context graphs, decision tracking, causal chains, and precedent search.

```python
from semantica.context import AgentContext, ContextGraph
from semantica.vector_store import VectorStore

context = AgentContext(
    vector_store=VectorStore(backend="faiss", dimension=768),
    knowledge_graph=ContextGraph(advanced_analytics=True),
    decision_tracking=True,
)

context.store("GPT-4 outperforms GPT-3.5 on reasoning benchmarks by 40%")

decision_id = context.record_decision(
    category="model_selection",
    scenario="...",
    reasoning="...",
    outcome="...",
    confidence=0.9,
)

precedents = context.find_precedents("model selection", limit=5)
```

**Components:** `AgentContext`, `ContextGraph`, `AgentMemory`, `DecisionRecorder`, `CausalAnalyzer`, `EntityLinker`, `PolicyEngine`

### Provenance

W3C PROV-O compliant lineage tracking across all modules.

```python
from semantica.provenance import ProvenanceManager

manager = ProvenanceManager()
manager.track_entity("entity_1", source="document.pdf", metadata={"type": "person"})
lineage = manager.get_lineage("entity_1")
```

**Components:** `ProvenanceManager`, `IntegrityChecker`, `BridgeAxiom`, `ProvenanceStorage`

### Change Management

Version control with SHA-256 checksums, diffs, and rollback.

```python
from semantica.change_management import TemporalVersionManager

manager  = TemporalVersionManager(storage_path="versions.db")
snapshot = manager.create_snapshot(kg, "v1.0", "user@example.com", "Initial version")
diff     = manager.diff("v1.0", "v1.1")
```

**Components:** `TemporalVersionManager`, `ChangeLog`, `OntologyVersionManager`, `VersionStorage`


## Output & Orchestration

### Export

Serializes graphs to downstream formats for analytics, semantic web, or graph databases.

```python
from semantica.export import RDFExporter, ParquetExporter, ArangoAQLExporter

# RDF formats
RDFExporter().export(graph, file_path="graph.ttl", format="turtle")

# Analytics
ParquetExporter().export(graph, file_path="output/graph.parquet")

# ArangoDB: writes AQL INSERT statements to the given path
ArangoAQLExporter().export(graph, file_path="graph.aql")
```

**Export formats:** RDF (Turtle, JSON-LD, N-Triples, XML), Parquet, ArangoDB AQL, CSV, OWL, Arrow, LPG, YAML, distance matrices

### Visualization

Renders interactive and static knowledge graph visualizations.

```python
from semantica.visualization import KGVisualizer

viz = KGVisualizer()
viz.visualize_network(graph, output="html", file_path="graph.html")
```

**Visualizers:** `KGVisualizer`, `OntologyVisualizer`, `EmbeddingVisualizer`, `SemanticNetworkVisualizer`, `TemporalVisualizer`, `AnalyticsVisualizer`

**Layout algorithms:** force-directed, hierarchical, circular

### Pipeline

Pipeline DSL with parallel workers, retry policies, and failure handling.

```python
from semantica.pipeline import PipelineBuilder, ExecutionEngine
from semantica.ingest import FileIngestor
from semantica.semantic_extract import NERExtractor

builder = PipelineBuilder()

# Each step type dispatches to a handler you register (or supply explicitly)
builder.register_step_handler("ingest",  lambda data, **c: FileIngestor().ingest(c["source"]))
builder.register_step_handler("extract", lambda docs, **c: NERExtractor(method="pattern").extract(docs[0].text))

builder.add_step("ingest",  step_type="ingest", source="data/")
builder.add_step("extract", step_type="extract")

pipeline = builder.connect_steps("ingest", "extract").build(name="docs_to_entities")
result   = ExecutionEngine().execute_pipeline(pipeline)
```

**Components:** `PipelineBuilder`, `Pipeline`, `ExecutionEngine`, `FailureHandler`, `PipelineValidator`, `ParallelismManager`, `ResourceScheduler`

### Explorer

FastAPI Knowledge Explorer with Ontology Hub, WebSocket progress, bidirectional path finding, and indexed search (0.004ms on 118k nodes).

```bash
semantica-explorer --graph my_graph.json
```

**Routes:** graph, ontology, provenance, decisions, analytics, SPARQL, temporal, annotations, export/import, vocabulary


## Utilities

### LLM Providers

Unified interface to all supported LLM providers.

```python
from semantica.llms import Groq, OpenAI, LiteLLM
import os

llm = Groq(model="llama-3.3-70b-versatile", api_key=os.getenv("GROQ_API_KEY"))
llm = OpenAI(model="gpt-4o", api_key=os.getenv("OPENAI_API_KEY"))
# Anthropic, Gemini, Ollama, DeepSeek via LiteLLM:
llm = LiteLLM(model="anthropic/claude-opus-4-7", api_key=os.getenv("ANTHROPIC_API_KEY"))
```

**Supported providers:** OpenAI, Anthropic, Google Gemini, Groq, Ollama, DeepSeek, Novita AI, HuggingFace, plus LiteLLM (100+ models via one interface)

### MCP Server

Exposes Semantica as an MCP stdio server for IDE and agent integrations.

```bash
python -m semantica.mcp_server
```

**Integrations:** Claude Desktop, VS Code, Cursor, Windsurf, Cline. 15 MCP tools are exposed.

### Seed

Bootstrap knowledge graphs from verified structured sources: fixed-point reference data, controlled vocabularies, and domain anchors.

```python
from semantica.seed import SeedDataManager

seed = SeedDataManager()

# Load trusted reference data from CSV / JSON / a database / an API
seed_data = seed.load_from_csv("seed_data/industries.csv", entity_type="Industry")

# Merge seed data with extraction output (seed values win on conflict by default)
combined = seed.integrate_with_extracted(
    {"entities": seed_data, "relationships": []},
    {"entities": extracted_entities, "relationships": extracted_relationships},
    merge_strategy="seed_first",
)
```

**Use cases:** anchoring extraction with known entities, pre-populating ontology classes, deterministic test graph generation.

### Evals

Scores decision-intelligence outputs (decision records, audit trails, reasoning
text) with a registry of deterministic and model-backed evaluators plus a small
run harness.

```python
from semantica.evals import evaluate, list_evaluators

list_evaluators()
# ['decision_scores', 'exact_match', 'keyword_check', 'length_range',
#  'levenshtein', 'llm_as_judge', 'numeric_range', 'regex_match', 'rouge',
#  'temporal_range']

cases = [("apple", "aple"), ("night", "nacht")]
summary = evaluate(cases, evaluators=["levenshtein"])
print(summary.total, summary.passed, summary.pass_rate)
```

**Public API:** `evaluate(cases, evaluators, config=None)`, `list_evaluators()`, `get_evaluator(name)`, and the `EvalMetric` / `CaseResult` / `EvalSummary` result types. See the [Evals reference](/reference/evals).

### Core

Base classes, shared data models, and the plugin registry used across all modules.

```python
from semantica.core import Semantica, PluginRegistry, ConfigManager

# ConfigManager loads a Config; Config.get() does dotted lookups
config = ConfigManager().load_from_file("config.yaml")
batch  = config.get("processing.batch_size", default=32)

# Top-level orchestrator: pass the Config object (or a dict), not a path
sem = Semantica(config=config)
sem.initialize()

# Plugin registry: register custom components under a name
registry = PluginRegistry()
registry.register_plugin("my_ingestor", MyCustomIngestor, version="1.0.0")
```

**Components:** `Semantica`, `PluginRegistry`, `ConfigManager`, `Config`, `LifecycleManager`, `HealthStatus`, `MethodRegistry`

### Utils

Shared utilities for ID generation, date parsing, validation, and logging.

```python
from semantica.utils import helpers, validators, logging
```

**Components:** `helpers`, `validators`, `constants`, `types`, `exceptions`, `logging`, `ProgressTracker`


## Common Module Chains

<Tabs>
  <Tab title="Document → KG">
    Load documents from any source and turn them into a queryable knowledge graph.

    **Pipeline:** `Ingest` → `Parse` → `Normalize` → `Semantic Extract` → `GraphBuilder` → `KG`

```python
from semantica.ingest import FileIngestor
from semantica.parse import DocumentParser
from semantica.semantic_extract import NERExtractor, RelationExtractor
from semantica.kg import GraphBuilder

sources       = FileIngestor().ingest("data/")
text          = DocumentParser().parse(sources[0].path)["full_text"]
ner           = NERExtractor(method="llm", provider="groq", llm_model="llama-3.3-70b-versatile")
rel           = RelationExtractor(method="llm", provider="groq", llm_model="llama-3.3-70b-versatile")
entities      = ner.extract(text)
relationships = rel.extract(text, entities=entities)
graph         = GraphBuilder(merge_entities=True).build(
                    {"entities": entities, "relationships": relationships}
                )
```

    **Best for:** research pipelines, enterprise data extraction, document intelligence
  </Tab>

  <Tab title="GraphRAG">
    Ground every LLM response in a knowledge graph: structured retrieval with source attribution.

    **Pipeline:** `KG` + `VectorStore` → `AgentContext` → GraphRAG query → grounded answer

```python
from semantica.context import AgentContext, ContextGraph
from semantica.vector_store import VectorStore

context = AgentContext(
    vector_store=VectorStore(backend="faiss", dimension=768),
    knowledge_graph=ContextGraph(advanced_analytics=True),
    graph_expansion=True,
)

# store() extracts entities and populates the graph + vector index
context.store([{"content": "Steve Wozniak co-founded Apple with Steve Jobs."}])

# retrieve() blends vector similarity with multi-hop graph traversal
results = context.retrieve(
    "What companies did Apple alumni found?",
    use_graph=True,
    expand_graph=True,
)
for r in results:
    print(f"[{r['score']:.3f}]  {r['content']}  (source: {r['source']})")
```

    **Best for:** question-answering systems, RAG with source attribution, research assistants
  </Tab>

  <Tab title="AI Agent">
    Give your agent persistent memory, decision tracking, and policy enforcement.

    **Pipeline:** `AgentContext` → decision recording → precedent search → policy check → causal analysis

```python
from semantica.context import AgentContext, ContextGraph
from semantica.vector_store import VectorStore

context = AgentContext(
    vector_store=VectorStore(backend="faiss", dimension=768),
    knowledge_graph=ContextGraph(advanced_analytics=True),
    decision_tracking=True,
)
context.store("GPT-4 outperforms GPT-3.5 on reasoning by 40%")

decision_id = context.record_decision(
    category="model_selection",
    scenario="Choose LLM for production",
    reasoning="Benchmark advantage justifies cost",
    outcome="selected_gpt4",
    confidence=0.91,
)
precedents = context.find_precedents("model selection", limit=5)
```

    **Best for:** autonomous agents, AI copilots, decision-support systems
  </Tab>

  <Tab title="Compliance Pipeline">
    Full provenance from raw data to final inference: W3C PROV-O, SHA-256 checksums, audit trail.

    **Pipeline:** `Ingest` → `Parse` → `Extract` → `KG` → `Provenance` → `ChangeManagement` → `Export`

```python
from semantica.ingest import FileIngestor
from semantica.parse import DocumentParser
from semantica.semantic_extract import NERExtractor
from semantica.kg import GraphBuilder
from semantica.provenance import ProvenanceManager
from semantica.export import RDFExporter

sources  = FileIngestor().ingest("records/")
ner      = NERExtractor(method="llm", provider="groq", llm_model="llama-3.3-70b-versatile")
entities = ner.extract(DocumentParser().parse(sources[0].path)["full_text"])
graph    = GraphBuilder(merge_entities=True).build({"entities": entities, "relationships": []})

prov     = ProvenanceManager()
prov.track_entity("entity_id", source="records/filing.pdf", metadata={"extractor": "llm"})
lineage  = prov.get_lineage("entity_id")

RDFExporter().export(graph, file_path="audit.ttl", format="turtle")
```

    **Best for:** HIPAA, SOX, GDPR, FDA 21 CFR Part 11 deployments
  </Tab>

  <Tab title="Web Scraping → Graph">
    Crawl websites, normalize text, and extract knowledge directly from the web.

    **Pipeline:** `WebIngestor` → `Normalize` → `Semantic Extract` → `GraphStore`

```python
from semantica.ingest import WebIngestor
from semantica.normalize import TextNormalizer
from semantica.semantic_extract import NERExtractor, RelationExtractor
from semantica.graph_store import GraphStore
from semantica.kg import GraphBuilder

ingestor   = WebIngestor()
normalizer = TextNormalizer()
ner        = NERExtractor(method="pattern")
rel        = RelationExtractor(method="pattern")

# The generic GraphStore wrapper exposes the add_nodes/add_edges interface
# GraphBuilder persists through; a raw Neo4jStore does not
store   = GraphStore(backend="neo4j", uri="bolt://localhost:7687", user="neo4j", password="password")
builder = GraphBuilder(merge_entities=True, graph_store=store)

for url in ["https://example.com/a", "https://example.com/b"]:
    page          = ingestor.ingest_url(url)          # WebContent, has .text
    text          = normalizer.normalize_text(page.text)
    entities      = ner.extract(text)
    relationships = rel.extract(text, entities=entities)
    builder.build({"entities": entities, "relationships": relationships})
```

    **Best for:** competitive intelligence, news monitoring, research aggregation
  </Tab>

  <Tab title="Temporal Analysis">
    Track how facts change over time: point-in-time queries, snapshots, and versioning.

    **Pipeline:** `KG (Temporal)` → `TemporalGraphQuery` → `VersionManager` → `ChangeManagement`

```python
from semantica.kg import GraphBuilder, TemporalGraphQuery, TemporalVersionManager

builder = GraphBuilder()
kg      = builder.build(sources=[{
    "entities": [{"id": "alice", "type": "Person"}],
    "relationships": [{"source": "alice", "target": "acme", "type": "ceo_of",
                       "valid_from": "2020-01-01", "valid_until": "2023-06-01"}]
}])

query         = TemporalGraphQuery()
snapshot_2021 = query.reconstruct_at_time(kg, "2021-06-15")

versioner = TemporalVersionManager()
versioner.create_snapshot(kg, "2024-Q1", author="user@example.com", description="Q1 snapshot")
```

    **Best for:** financial history, regulatory timelines, organizational change tracking
  </Tab>
</Tabs>


## Module Index

| Module | Purpose | Key Classes |
| :------ | :------- | :----------- |
| [ingest](/reference/ingest) | Data ingestion | `FileIngestor`, `WebIngestor`, `ParquetIngestor`, `XMLIngestor` |
| [parse](/reference/parse) | Document parsing | `DocumentParser`, `DoclingParser` |
| [split](/reference/split) | Text chunking | `TextSplitter` |
| [normalize](/reference/normalize) | Data cleaning | `TextNormalizer`, `EntityNormalizer`, `LanguageDetector` |
| [semantic_extract](/reference/semantic_extract) | NER & relation extraction | `NERExtractor`, `RelationExtractor`, `TripletExtractor`, `SemanticAnalyzer`, `SemanticNetworkExtractor`, `ExtractionValidator` |
| [kg](/reference/kg) | Graph construction | `GraphBuilder`, `TemporalGraphQuery`, `SimilarityCalculator` |
| [ontology](/reference/ontology) | Schema management | `OntologyGenerator`, `SHACLGenerator` |
| [reasoning](/reference/reasoning) | Logical inference | `Reasoner`, `DatalogReasoner` |
| [embeddings](/reference/embeddings) | Vector embeddings | `EmbeddingGenerator` |
| [vector_store](/reference/vector_store) | Vector database | `VectorStore` |
| [graph_store](/reference/graph_store) | Graph database | `GraphStore` |
| [triplet_store](/reference/triplet_store) | RDF triple store | `TripletStore` |
| [deduplication](/reference/deduplication) | Entity resolution | `DuplicateDetector`, `EntityMerger`, `ClusterBuilder`, `MergeStrategyManager` |
| [conflicts](/reference/conflicts) | Conflict resolution | `ConflictDetector`, `ConflictResolver`, `SourceTracker` |
| [context](/reference/context) | Agent context & decisions | `AgentContext`, `ContextGraph` |
| [provenance](/reference/provenance) | W3C PROV-O lineage | `ProvenanceManager` |
| [change_management](/reference/change_management) | Version control | `TemporalVersionManager` |
| [export](/reference/export) | Data export | `RDFExporter`, `ParquetExporter` |
| [visualization](/reference/visualization) | Graph visualization | `KGVisualizer` |
| [pipeline](/reference/pipeline) | Workflow orchestration | `Pipeline`, `PipelineBuilder` |
| [explorer](/reference/explorer) | Knowledge Explorer UI | `semantica-explorer --graph <file>` |
| [llms](/reference/llms) | LLM providers | `Groq`, `OpenAI`, `create_provider` |
| [mcp_server](/reference/mcp_server) | MCP stdio server | `python -m semantica.mcp_server` |
| [seed](/reference/seed) | KG bootstrapping from structured sources | `SeedDataManager` |
| [evals](/reference/evals) | Decision-intelligence evaluation | `evaluate`, `list_evaluators`, `EvalSummary` |
| [core](/reference/core) | Base classes & registry | `Semantica`, `ConfigManager`, `PluginRegistry`, `LifecycleManager` |
| [utils](/reference/utils) | Shared utilities | `helpers`, `validators` |

- [Getting Started](/getting-started): your first knowledge graph in 5 minutes.
- [Cookbook](/cookbook): 40+ domain notebooks with real-world examples.
- [API Reference](/reference/context): full technical documentation.
