---
title: "Glossary"
description: "Reference definitions for terms and concepts used throughout Semantica."
icon: "book"
---

<Info>
  Use Ctrl+F / Cmd+F to search this page for a specific term.
</Info>

A quick-reference dictionary of every concept, data structure, algorithm, and standard referenced in Semantica's documentation and codebase.


## Core Concepts

**Agent**
An autonomous AI system that perceives its environment, reasons about information, and takes actions to achieve goals. In Semantica, agents use knowledge graphs for structured memory and context, with every decision recorded as a first-class object.

**Context Graph**
A persistent, queryable graph of everything an agent knows, decides, and reasons about: entities, relationships, decisions, and their causal links. The core data structure of `semantica.context`.

**Decision**
A first-class object in Semantica: a recorded agent choice with category, scenario, reasoning, outcome, confidence score, causal chain, and source provenance. Stored and searchable via `context.record_decision()`.

**Entity**
A distinct object or concept in the real world: a person, organization, location, event, or abstract concept. Entities are nodes in a knowledge graph, each with typed properties and a source provenance record.

**Knowledge Graph (KG)**
A structured representation of knowledge using entities (nodes) and relationships (edges). Knowledge graphs enable reasoning, querying, semantic search, and traceable inference: unlike flat vector stores.

**Relationship**
A directed, typed connection between two entities: e.g., `works_for`, `located_in`, `founded_by`. Relationships carry confidence scores and provenance back to the source document.

**Semantic**
Relating to meaning in language or logic. Semantic understanding captures context and intent: going beyond keyword matching to understand what text *means*.


## Data Processing

**Chunking**
Splitting large documents into smaller pieces while preserving semantic context. Semantica supports recursive, semantic boundary, entity-aware, relation-aware, sliding window, structural, and table-aware chunking strategies.

**Ingestion**
Loading data from external sources: files, databases, APIs, streams: into the pipeline as a unified `SourceDocument`. The first stage in every Semantica pipeline.

**Normalization**
Standardizing data into a consistent canonical form: converting dates to ISO format, canonicalizing entity names, fixing encoding issues, stripping noise. Ensures downstream extraction works on clean, consistent text.

**Parsing**
Extracting structured text, layout, and metadata from unstructured or semi-structured documents: PDFs, Word files, HTML, PPTX. `DoclingParser` additionally handles multi-column layouts, merged-cell tables, and OCR.


## Artificial Intelligence

**Abductive Reasoning**
Inference to the most plausible explanation for observed facts. One of six reasoning engines in `semantica.reasoning`: returns the most likely hypothesis given available evidence.

**Datalog**
A declarative logic programming language for knowledge base queries. Semantica's `DatalogEngine` supports recursive Horn clause rules with bottom-up semi-naive fixpoint semantics. Added in v0.4.0.

**GraphRAG (Graph-Augmented Retrieval Augmented Generation)**
An advanced RAG approach that combines vector similarity search with knowledge graph traversal. Every LLM response is grounded in structured graph context, with each claim traceable to a source node. Eliminates hallucination without source attribution.

**Inference**
Deriving new facts or conclusions from existing knowledge using logical rules: without the derived facts being explicitly present in the source data.

**LLM (Large Language Model)**
An AI model trained on large text corpora, capable of understanding and generating natural language. Semantica integrates with 8+ LLM providers for entity extraction, relation extraction, and reasoning.

**RAG (Retrieval Augmented Generation)**
A technique that enhances LLM outputs by retrieving relevant context from a knowledge base before generating a response. GraphRAG extends this with graph traversal for more precise, structured retrieval.


## Knowledge Graph Components

**Allen Interval Algebra**
A system of 13 relations for describing how two time intervals relate: before, after, meets, overlaps, during, starts, finishes, equals, and their inverses. Supported in `TemporalKnowledgeGraph` since v0.4.0.

**BiTemporalFact**
A fact with two independent time dimensions: *valid time* (when it was true in the world) and *transaction time* (when it was recorded in the system). Enables full audit trails for slowly changing data.

**Edge**
A directed connection between two nodes in a graph, representing a typed relationship. Edges carry type, confidence score, and provenance metadata.

**Node**
A vertex in a knowledge graph representing an entity or concept. Nodes carry typed properties, a confidence score, and provenance linking back to the source document.

**Property**
An attribute or characteristic of an entity or relationship: name, date, URI, confidence score, source URL.

**Temporal Graph**
A knowledge graph where nodes and edges carry `valid_from` / `valid_until` time windows, enabling point-in-time queries and historical state reconstruction.

**Triplet**
The atomic unit of knowledge: a `(subject, predicate, object)` triple: e.g., `(Apple_Inc, founded_by, Steve_Jobs)`. The building block of RDF and SPARQL-based storage.


## Entity Recognition & Extraction

**Coreference Resolution**
Determining when multiple expressions in text refer to the same entity: e.g., "Apple" and "the company" both referring to Apple Inc. Handled by `CoreferenceResolver` in `semantica.semantic_extract`.

**Entity Resolution**
Determining when two entity mentions across different documents refer to the same real-world entity. Also called entity linking or deduplication. Uses similarity scoring, blocking, and semantic embeddings.

**Event Detection**
Identifying and classifying events in text: acquisitions, partnerships, product launches, regulatory decisions. Handled by `EventDetector` in `semantica.semantic_extract`.

**Named Entity Recognition (NER)**
Identifying and classifying named entities in text into predefined categories: persons, organizations, locations, dates, products, and custom types. Three modes: pattern-based, ML-based, and LLM-based.

**Relationship Extraction**
Identifying and extracting typed semantic relationships between entities: e.g., `(Google, acquired, DeepMind)`: from raw text.


## Ontology & Schema

**Axiom**
A statement accepted as true in an ontology, used to define logical constraints: e.g., "every Person must have a name", "Organization can have at most one CEO at a time".

**Class**
A category or type of entity in an ontology: `Person`, `Organization`, `Location`. Classes form a hierarchy and carry constraints validated by SHACL.

**Ontology**
A formal specification of domain concepts, relationships, and constraints: typically expressed in OWL. Semantica can auto-generate ontologies from knowledge graphs or import existing OWL/RDF/Turtle files.

**Ontology Hub**
Semantica's v0.5.0 visual browser UI for the full ontology lifecycle: visual class editor, SHACL Studio, alignment authoring, health dashboard, and version-controlled diffs.

**OWL (Web Ontology Language)**
The W3C standard language for defining and instantiating ontologies. Semantica can generate, import, and export OWL ontologies.

**SHACL (Shapes Constraint Language)**
The W3C standard for validating RDF graphs against a set of shape constraints. Semantica auto-generates SHACL shapes from ontologies and validates graphs against them.

**SKOS (Simple Knowledge Organization System)**
A W3C standard for representing controlled vocabularies, taxonomies, and thesauri. Used in Semantica for domain vocabulary management.


## Storage & Retrieval

**Embedding**
A dense numerical vector that represents text, images, or other data in a continuous semantic space. Entities with similar meaning produce vectors that are close together: enabling similarity search and semantic matching.

**Graph Database**
A database optimized for storing and querying graph-structured data using node and edge primitives. Semantica supports Neo4j, FalkorDB, Apache AGE, and Amazon Neptune.

**Hybrid Search**
A retrieval strategy combining vector similarity search with keyword or metadata filtering: higher accuracy than either approach alone.

**Triplet Store**
A database designed specifically for storing and querying RDF `(subject, predicate, object)` triples. Semantica supports Blazegraph, Apache Jena, and RDF4J.

**Vector Store**
A database optimized for storing and searching high-dimensional embedding vectors by similarity. Semantica supports FAISS, Pinecone, Weaviate, Qdrant, Milvus, and PgVector.


## Graph Analytics

**Centrality**
A measure of a node's importance in the graph. Common metrics: PageRank (link-based importance), betweenness centrality (bridge nodes), closeness centrality (average distance to all others).

**Community Detection**
Identifying groups of densely connected nodes: clusters that share more internal links than external ones. Used for finding subject communities, fraud rings, and organizational clusters.

**Distance Band**
A classification of a node's semantic proximity to a target: `near`, `mid`, or `far`, based on embedding distance thresholds. Part of Distance Intelligence (v0.5.0).

**Distance Intelligence**
Semantica's v0.5.0 feature for semantic neighborhood exploration: N×N distance matrices, ego-mode visualization centered on a single entity, and distance band classification across the graph.

**PageRank**
An algorithm measuring node importance based on the structure of incoming relationships: originally designed for web pages, applicable to any directed graph.


## Query Languages & Standards

**Cypher**
The declarative graph query language used by Neo4j and FalkorDB. Analogous to SQL for relational databases.

**Datalog**
A subset of Prolog used for deductive database queries. Semantica's `DatalogEngine` supports recursive Horn clause rules with guaranteed termination via bottom-up semi-naive fixpoint evaluation.

**RDF (Resource Description Framework)**
The W3C standard for representing information as subject-predicate-object triples. The basis of the semantic web and Semantica's triplet store.

**SPARQL**
The W3C query language for RDF data. Semantica's `SparqlReasoner` uses SPARQL for query-based inference over RDF graphs.


## Data Quality

**Conflict Resolution**
Handling contradictory facts from multiple sources in the same knowledge graph. Semantica's `ConflictDetector` surfaces conflicts; resolution strategies include prefer-most-recent, prefer-most-reliable, majority-vote, and flag-for-review.

**Data Provenance**
Complete information about the origin, history, and lineage of every fact: source document, extraction method, timestamp, confidence score. W3C PROV-O compliant in Semantica.

**Deduplication**
Identifying and merging duplicate entity records. Semantica v2 strategies (`blocking_v2`, `hybrid_v2`, `semantic_v2`) are up to 7x faster than v1.

**W3C PROV-O**
The W3C provenance ontology standard. Semantica tracks lineage across all modules in PROV-O compliant format: suitable for HIPAA, SOX, GDPR, and FDA 21 CFR Part 11 compliance.


## Security Terms

**SSRF (Server-Side Request Forgery)**
A vulnerability where a server is induced to make requests to unintended destinations. Semantica validates `base_url` at construction time to prevent SSRF in LLM gateway configurations.

**XXE (XML External Entity)**
A vulnerability in XML parsers that allows attackers to read arbitrary files or trigger SSRF. Semantica's `XMLIngestor` (v0.5.0) uses an XXE-safe lxml backend.


## See Also

- [Core Concepts](concepts) — Deeper explanation of key ideas with code examples.
- [Getting Started](getting-started) — First working examples: no prior graph experience required.
- [Modules Guide](modules) — All 27 modules explained with code and pipeline chains.
- [API Reference](reference/context) — Complete technical reference for every class and method.
