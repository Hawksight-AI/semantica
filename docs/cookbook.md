---
title: "Cookbook"
description: "Interactive Jupyter notebooks covering everything from your first knowledge graph to production GraphRAG systems."
icon: "flask"
---

<Tip>
  **Where to start:**
  - **New to Semantica**: begin with [Core Tutorials](#core-tutorials)
  - **Building an application**: see [Advanced Concepts](#advanced-concepts)
  - **Need installation help**: see the [Installation Guide](/installation)
</Tip>

<Note>
  Prerequisites: Python 3.8+, Jupyter, and an API key for your preferred LLM provider.
</Note>


## Featured Recipe

- **[Your First Knowledge Graph](https://github.com/semantica-agi/semantica/blob/main/cookbook/introduction/08_Your_First_Knowledge_Graph.ipynb)**: go from raw text to a queryable knowledge graph in 20 minutes. Topics: Extraction, Graph Construction, Visualization · *Beginner*


## Core Tutorials

Essential guides to master the Semantica framework.

- **[Welcome to Semantica](https://github.com/semantica-agi/semantica/blob/main/cookbook/introduction/01_Welcome_to_Semantica.ipynb)**: interactive introduction to the framework's core philosophy and all modules. Topics: Framework Overview, Architecture · *Beginner*
- **[Data Ingestion](https://github.com/semantica-agi/semantica/blob/main/cookbook/introduction/02_Data_Ingestion.ipynb)**: loading data from files, web, databases, streams, feeds, repositories, email, and MCP. Topics: FileIngestor, WebIngestor, DBIngestor · *Beginner*
- **[Document Parsing](https://github.com/semantica-agi/semantica/blob/main/cookbook/introduction/03_Document_Parsing.ipynb)**: extracting clean text from complex formats like PDF, DOCX, and HTML. Topics: OCR, PDF Parsing, Text Extraction · *Beginner*
- **[Data Normalization](https://github.com/semantica-agi/semantica/blob/main/cookbook/introduction/04_Data_Normalization.ipynb)**: pipelines for cleaning, normalizing, and preparing text. Topics: Text Cleaning, Unicode, Formatting · *Beginner*
- **[Entity Extraction](https://github.com/semantica-agi/semantica/blob/main/cookbook/introduction/05_Entity_Extraction.ipynb)**: using NER to identify people, organizations, and custom entities. Topics: NER, spaCy, LLM Extraction · *Beginner*
- **[Relation Extraction](https://github.com/semantica-agi/semantica/blob/main/cookbook/introduction/06_Relation_Extraction.ipynb)**: discovering and classifying relationships between entities. Topics: Relation Classification, Dependency Parsing · *Beginner*
- **[Embedding Generation](https://github.com/semantica-agi/semantica/blob/main/cookbook/introduction/12_Embedding_Generation.ipynb)**: creating and managing vector embeddings for semantic search. Topics: Embeddings, OpenAI, HuggingFace · *Intermediate*
- **[Vector Store](https://github.com/semantica-agi/semantica/blob/main/cookbook/introduction/13_Vector_Store.ipynb)**: setting up vector stores for similarity search and retrieval. *Intermediate*
- **[Graph Store](https://github.com/semantica-agi/semantica/blob/main/cookbook/introduction/09_Graph_Store.ipynb)**: persisting knowledge graphs in Neo4j or FalkorDB. Topics: Neo4j, Cypher, Persistence · *Intermediate*
- **[Ontology](https://github.com/semantica-agi/semantica/blob/main/cookbook/introduction/14_Ontology.ipynb)**: defining domain schemas and ontologies to structure your data. Topics: OWL, RDF, Schema Design · *Intermediate*
- **[Seed Data](https://github.com/semantica-agi/semantica/blob/main/cookbook/introduction/25_Seed_Data.ipynb)**: bootstrapping a knowledge graph from trusted CSV, JSON, database, and API sources before extraction runs. Topics: SeedDataManager, Foundation Graphs · *Intermediate*
- **[Semantic Layer Basics](https://github.com/semantica-agi/semantica/blob/main/cookbook/introduction/26_Semantic_Layer_Basics.ipynb)**: capstone tutorial that combines a knowledge graph, generated ontology, explicit mappings, ontology-aligned RDF, and a SPARQL query. Topics: Semantic Layer, Ontology Mapping, Oxigraph, SPARQL · *Intermediate*


## Advanced Concepts

Deep dive into advanced features, customization, and complex workflows.

- **[Advanced Extraction](https://github.com/semantica-agi/semantica/blob/main/cookbook/advanced/01_Advanced_Extraction.ipynb)**: custom extractors, LLM-based extraction, and complex pattern matching. Topics: Custom Models, Regex, LLMs · *Advanced*
- **[Advanced Graph Analytics](https://github.com/semantica-agi/semantica/blob/main/cookbook/advanced/02_Advanced_Graph_Analytics.ipynb)**: centrality, community detection, and pathfinding algorithms. Topics: PageRank, Louvain, Shortest Path · *Advanced*
- **[Advanced Context Engineering](https://github.com/semantica-agi/semantica/blob/main/cookbook/advanced/11_Advanced_Context_Engineering.ipynb)**: persistent memory system for AI agents using FAISS and Neo4j. Topics: Agent Memory, GraphRAG, Entity Injection · *Advanced*
- **[Complete Visualization Suite](https://github.com/semantica-agi/semantica/blob/main/cookbook/advanced/03_Complete_Visualization_Suite.ipynb)**: interactive network, analytics, and temporal visualizations for graphs. Topics: PyVis, NetworkX, D3.js · *Intermediate*
- **[Conflict Resolution](https://github.com/semantica-agi/semantica/blob/main/cookbook/introduction/17_Conflict_Detection_and_Resolution.ipynb)**: strategies for handling contradictory information from multiple sources. Topics: Truth Discovery, Voting, Confidence · *Advanced*
- **[Multi-Format Export](https://github.com/semantica-agi/semantica/blob/main/cookbook/advanced/05_Multi_Format_Export.ipynb)**: exporting to RDF, OWL, JSON-LD, and NetworkX formats. Topics: Serialization, Interoperability · *Intermediate*
- **[Multi-Source Integration](https://github.com/semantica-agi/semantica/blob/main/cookbook/advanced/06_Multi_Source_Data_Integration.ipynb)**: merging data from disparate sources into a unified graph. Topics: Entity Resolution, Merging, Fusion · *Advanced*
- **[Reasoning and Inference](https://github.com/semantica-agi/semantica/blob/main/cookbook/advanced/08_Reasoning_and_Inference.ipynb)**: using logical reasoning to infer new knowledge from existing facts. Topics: Logic Rules, Inference Engines · *Advanced*
- **[Temporal Knowledge Graphs](https://github.com/semantica-agi/semantica/blob/main/cookbook/advanced/10_Temporal_Knowledge_Graphs.ipynb)**: modeling and querying data that changes over time. Topics: Time Series, Temporal Logic, Allen Algebra · *Advanced*
- **[Provenance Tracking](https://github.com/semantica-agi/semantica/blob/main/cookbook/introduction/22_Provenance_Tracking.ipynb)**: W3C PROV-O-aligned lineage tracking and checksum verification for entities, relationships, and chunks. Topics: PROV-O, Lineage, Checksums, Invalidation · *Advanced*
- **[Reasoning Module](https://github.com/semantica-agi/semantica/blob/main/cookbook/introduction/23_Reasoning.ipynb)**: deriving new knowledge from existing facts with forward chaining, backward chaining, and Datalog strategies. Topics: Reasoner, Datalog, Explanations · *Advanced*
- **[Change Management](https://github.com/semantica-agi/semantica/blob/main/cookbook/introduction/24_Change_Management.ipynb)**: versioning, audit trails, and data-integrity checks for knowledge graphs and ontologies. Topics: ChangeLogEntry, Version Storage, Data Integrity · *Advanced*


## How to Run

<Steps>
  <Step title="Install Semantica">
    ```bash
    pip install semantica[all]
    pip install jupyter
    ```
  </Step>
  <Step title="Clone the repository (optional, for source install)">
    ```bash
    git clone https://github.com/semantica-agi/semantica.git
    cd semantica
    pip install -e ".[all]"
    pip install jupyter
    ```
  </Step>
  <Step title="Launch Jupyter">
    ```bash
    jupyter notebook
    ```
  </Step>
</Steps>

<Tip>
  You can also run the cookbook using Docker:

  ```bash
  docker run -p 8888:8888 semantica/semantica-cookbook
  ```
</Tip>
