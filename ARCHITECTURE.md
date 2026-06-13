# Semantica — Architecture

Complete data flow from every source type to every final output, and the decision intelligence lifecycle.

---

## Full Data Pipeline

Every source, every processing step, every final artifact — in one diagram.

```mermaid
flowchart TD
    %% ── SOURCES ──────────────────────────────────────────────────────
    subgraph SRC["🗂️ Sources  (semantica.ingest)"]
        direction LR
        F["📄 Files\nPDF · DOCX · PPTX · HTML\nTXT · CSV · JSON · Excel · XML"]
        W["🌐 Web\nPages · RSS/Atom Feeds\nPublic REST APIs"]
        DB["🗃️ Databases\nPostgreSQL · MySQL · SQLite\nOracle · DuckDB · MongoDB"]
        CL["☁️ Cloud\nSnowflake · Google Drive\nElasticsearch · HuggingFace"]
        RT["⚡ Streams\nKafka · RabbitMQ\nAWS Kinesis · Pulsar"]
        DV["🛠️ Dev\nGit Repos · Email IMAP/POP3\nMCP Resources · Parquet · Pandas"]
    end

    %% ── INGEST ───────────────────────────────────────────────────────
    F  --> FI["FileIngestor"]
    W  --> WI["WebIngestor"]
    DB --> DI["DBIngestor"]
    CL --> PI["ParquetIngestor\nSnowflakeIngestor"]
    RT --> SI["StreamIngestor"]
    DV --> RI["RepoIngestor\nEmailIngestor · MCPIngestor"]

    FI & WI & DI & PI & SI & RI --> RAW[/"📦 Raw Documents"/]

    %% ── PARSE ────────────────────────────────────────────────────────
    RAW --> PRS["🔍 Parse  (semantica.parse)\nDocumentParser · StructuredDataParser\nCodeParser · WebParser · EmailParser"]

    PRS --> NRM["🧹 Normalize  (semantica.normalize)\nTextNormalizer · EntityNormalizer\nDateNormalizer · NumberNormalizer · DataCleaner"]

    NRM --> SPL["✂️ Split  (semantica.split)\nentity_aware · relation_aware\ngraph_based · ontology_aware · hierarchical"]

    %% ── EXTRACT ──────────────────────────────────────────────────────
    SPL --> EXT["🔬 Extract  (semantica.semantic_extract)\nNamedEntityRecognizer · RelationExtractor\nEventDetector · TripletExtractor · CoreferenceResolver"]

    EXT --> CFT["⚠️ Conflict Detection  (semantica.conflicts)\nConflictDetector · ConflictResolver · SourceTracker"]

    CFT --> DDP["🔁 Deduplication  (semantica.deduplication)\nDuplicateDetector · EntityMerger"]

    DDP --> KGB["🕸️ KG Construction  (semantica.kg)\nGraphBuilder · EntityResolver\nBiTemporalFact · TemporalGraphQuery"]

    KGB --> KG[/"🗺️ Knowledge Graph\nnodes · edges · temporal facts · provenance"/]

    %% ── INTELLIGENCE LAYER ───────────────────────────────────────────
    KG --> ONT["Ontology  (semantica.ontology)\nOntologyGenerator · OntologyValidator\nOWL · SHACL · SKOS"]
    KG --> RSN["Reasoning  (semantica.reasoning)\nReteEngine · DatalogReasoner\nSPARQLReasoner · ExplanationGenerator"]
    KG --> PRV["Provenance  (semantica.provenance)\nProvenanceManager · W3C PROV-O"]
    KG --> CTX["Context & Decisions  (semantica.context)\nContextGraph · AgentContext\nDecisionRecorder · CausalChainAnalyzer · PolicyEngine"]

    ONT & RSN & PRV & CTX --> EKG[/"🗃️ Enriched KG\n+ ontology · inferences · provenance · decisions"/]

    %% ── STORAGE ──────────────────────────────────────────────────────
    EKG --> VS["Vector Store  (semantica.vector_store)\nFAISS · Qdrant · Weaviate · Milvus · Pinecone · PgVector\nHybrid Search · RRF Fusion"]
    EKG --> GS["Graph Store  (semantica.graph_store)\nNeo4j · FalkorDB · Apache AGE · Amazon Neptune"]

    %% ── OUTPUTS ──────────────────────────────────────────────────────
    VS & GS --> EXP["📦 Export  (semantica.export)\nRDF Turtle · JSON-LD · N-Triples · OWL · SHACL\nParquet · Cypher · ArangoDB AQL · GraphML · CSV · HTML"]
    VS & GS --> VIZ["📊 Visualize  (semantica.visualization)\nKGVisualizer · OntologyVisualizer\nEmbeddingVisualizer · TemporalVisualizer"]
    EKG --> SVC["🔌 Services\nREST API 100+ endpoints · MCP Server 10+ tools\nCLI 50+ commands · Knowledge Explorer"]
```

---

## Decision Intelligence Lifecycle

```mermaid
flowchart LR
    subgraph RECORD["1️⃣  Record"]
        R1["record_decision()\ncategory · scenario\nreasoning · outcome\nconfidence · metadata"]
    end

    subgraph LINK["2️⃣  Link"]
        L1["add_causal_relationship()\ntriggers · enables\ncauses · precedes"]
    end

    subgraph QUERY["3️⃣  Query"]
        Q1["find_similar_decisions()\nSemantic precedent search"]
        Q2["trace_decision_chain()\nFull causal ancestry"]
        Q3["analyze_decision_impact()\nDownstream influence map"]
    end

    subgraph GOVERN["4️⃣  Govern"]
        G1["check_decision_rules()\nPolicy evaluation\nCompliance gate"]
    end

    subgraph AUDIT["5️⃣  Audit Export"]
        A1["W3C PROV-O  ·  CSV  ·  JSON\nRegulator-ready audit trail"]
    end

    RECORD -->|decision_id| LINK
    LINK   -->|causal graph| QUERY
    QUERY  -->|results| GOVERN
    GOVERN -->|signed-off decisions| AUDIT
```

---

*→ [README](README.md) · [Docs](https://docs.getsemantica.ai/) · [Cookbook](https://github.com/semantica-agi/semantica/tree/main/cookbook)*

> Note: `Docs` and `Cookbook` are external resources maintained outside this file and may change over time. If a link is unavailable, refer to the repository `README.md` and in-repo documentation as canonical fallbacks.
