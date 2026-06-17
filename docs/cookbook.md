---
title: "Cookbook"
description: "Interactive Jupyter notebooks covering everything from your first knowledge graph to production GraphRAG systems."
icon: "flask"
---

<Tip>
  **Where to start:**
  - **New to Semantica**: begin with [Core Tutorials](#core-tutorials)
  - **Building an application**: see [Advanced Concepts](#advanced-concepts)
  - **Need installation help**: see the [Installation Guide](installation)
</Tip>

<Note>
  Prerequisites: Python 3.8+, Jupyter, and an API key for your preferred LLM provider.
</Note>


## Featured Recipe

- **[Your First Knowledge Graph](https://github.com/semantica-agi/semantica/blob/main/cookbook/introduction/08_Your_First_Knowledge_Graph.ipynb)** — Go from raw text to a queryable knowledge graph in 20 minutes. Topics: Extraction, Graph Construction, Visualization · *Beginner*


## Core Tutorials

Essential guides to master the Semantica framework.

- **[Welcome to Semantica](https://github.com/semantica-agi/semantica/blob/main/cookbook/introduction/01_Welcome_to_Semantica.ipynb)** — Interactive introduction to the framework's core philosophy and all modules. Topics: Framework Overview, Architecture · *Beginner*
- **[Data Ingestion](https://github.com/semantica-agi/semantica/blob/main/cookbook/introduction/02_Data_Ingestion.ipynb)** — Loading data from files, web, databases, streams, feeds, repositories, email, and MCP. Topics: FileIngestor, WebIngestor, DBIngestor · *Beginner*
- **[Document Parsing](https://github.com/semantica-agi/semantica/blob/main/cookbook/introduction/03_Document_Parsing.ipynb)** — Extracting clean text from complex formats like PDF, DOCX, and HTML. Topics: OCR, PDF Parsing, Text Extraction · *Beginner*
- **[Data Normalization](https://github.com/semantica-agi/semantica/blob/main/cookbook/introduction/04_Data_Normalization.ipynb)** — Pipelines for cleaning, normalizing, and preparing text. Topics: Text Cleaning, Unicode, Formatting · *Beginner*
- **[Entity Extraction](https://github.com/semantica-agi/semantica/blob/main/cookbook/introduction/05_Entity_Extraction.ipynb)** — Using NER to identify people, organizations, and custom entities. Topics: NER, spaCy, LLM Extraction · *Beginner*
- **[Relation Extraction](https://github.com/semantica-agi/semantica/blob/main/cookbook/introduction/06_Relation_Extraction.ipynb)** — Discovering and classifying relationships between entities. Topics: Relation Classification, Dependency Parsing · *Beginner*
- **[Embedding Generation](https://github.com/semantica-agi/semantica/blob/main/cookbook/introduction/12_Embedding_Generation.ipynb)** — Creating and managing vector embeddings for semantic search. Topics: Embeddings, OpenAI, HuggingFace · *Intermediate*
- **[Vector Store](https://github.com/semantica-agi/semantica/blob/main/cookbook/introduction/13_Vector_Store.ipynb)** — Setting up vector stores for similarity search and retrieval. *Intermediate*
- **[Graph Store](https://github.com/semantica-agi/semantica/blob/main/cookbook/introduction/09_Graph_Store.ipynb)** — Persisting knowledge graphs in Neo4j or FalkorDB. Topics: Neo4j, Cypher, Persistence · *Intermediate*
- **[Ontology](https://github.com/semantica-agi/semantica/blob/main/cookbook/introduction/14_Ontology.ipynb)** — Defining domain schemas and ontologies to structure your data. Topics: OWL, RDF, Schema Design · *Intermediate*


## Advanced Concepts

Deep dive into advanced features, customization, and complex workflows.

- **[Advanced Extraction](https://github.com/semantica-agi/semantica/blob/main/cookbook/advanced/01_Advanced_Extraction.ipynb)** — Custom extractors, LLM-based extraction, and complex pattern matching. Topics: Custom Models, Regex, LLMs · *Advanced*
- **[Advanced Graph Analytics](https://github.com/semantica-agi/semantica/blob/main/cookbook/advanced/02_Advanced_Graph_Analytics.ipynb)** — Centrality, community detection, and pathfinding algorithms. Topics: PageRank, Louvain, Shortest Path · *Advanced*
- **[Advanced Context Engineering](https://github.com/semantica-agi/semantica/blob/main/cookbook/advanced/11_Advanced_Context_Engineering.ipynb)** — Production-grade memory system for AI agents using FAISS and Neo4j. Topics: Agent Memory, GraphRAG, Entity Injection · *Advanced*
- **[Complete Visualization Suite](https://github.com/semantica-agi/semantica/blob/main/cookbook/advanced/03_Complete_Visualization_Suite.ipynb)** — Interactive, publication-ready visualizations of your graphs. Topics: PyVis, NetworkX, D3.js · *Intermediate*
- **[Conflict Resolution](https://github.com/semantica-agi/semantica/blob/main/cookbook/introduction/17_Conflict_Detection_and_Resolution.ipynb)** — Strategies for handling contradictory information from multiple sources. Topics: Truth Discovery, Voting, Confidence · *Advanced*
- **[Multi-Format Export](https://github.com/semantica-agi/semantica/blob/main/cookbook/advanced/05_Multi_Format_Export.ipynb)** — Exporting to RDF, OWL, JSON-LD, and NetworkX formats. Topics: Serialization, Interoperability · *Intermediate*
- **[Multi-Source Integration](https://github.com/semantica-agi/semantica/blob/main/cookbook/advanced/06_Multi_Source_Data_Integration.ipynb)** — Merging data from disparate sources into a unified graph. Topics: Entity Resolution, Merging, Fusion · *Advanced*
- **[Pipeline Orchestration](https://github.com/semantica-agi/semantica/blob/main/cookbook/advanced/07_Pipeline_Orchestration.ipynb)** — Building robust, automated data processing pipelines. Topics: Workflows, Automation, Error Handling · *Advanced*
- **[Reasoning and Inference](https://github.com/semantica-agi/semantica/blob/main/cookbook/advanced/08_Reasoning_and_Inference.ipynb)** — Using logical reasoning to infer new knowledge from existing facts. Topics: Logic Rules, Inference Engines · *Advanced*
- **[Temporal Knowledge Graphs](https://github.com/semantica-agi/semantica/blob/main/cookbook/advanced/10_Temporal_Knowledge_Graphs.ipynb)** — Modeling and querying data that changes over time. Topics: Time Series, Temporal Logic, Allen Algebra · *Advanced*


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
  docker run -p 8888:8888 hawksight/semantica-cookbook
  ```
</Tip>
