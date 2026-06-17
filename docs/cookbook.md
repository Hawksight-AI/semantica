---
title: "Cookbook"
description: "Interactive Jupyter notebooks covering everything from your first knowledge graph to production GraphRAG systems."
icon: "flask"
---

<Tip>
  **Where to start:**
  - **New to Semantica** — begin with [Core Tutorials](#core-tutorials)
  - **Building an application** — see [Advanced Concepts](#advanced-concepts) or [Industry Use Cases](#industry-use-cases)
  - **Need installation help** — see the [Installation Guide](installation)
</Tip>

<Note>
  Prerequisites: Python 3.8+, Jupyter, and an API key for your preferred LLM provider.
</Note>


## Featured Recipes

<CardGroup cols={2}>
  <Card title="Your First Knowledge Graph" icon="diagram-project" href="https://github.com/semantica-agi/semantica/blob/main/cookbook/introduction/08_Your_First_Knowledge_Graph.ipynb">
    Go from raw text to a queryable knowledge graph in 20 minutes.

    **Topics:** Extraction, Graph Construction, Visualization · **Difficulty:** Beginner
  </Card>
  <Card title="GraphRAG Complete" icon="robot" href="https://github.com/semantica-agi/semantica/blob/main/cookbook/use_cases/advanced_rag/01_GraphRAG_Complete.ipynb">
    Build a production-ready Graph Retrieval Augmented Generation system with hybrid retrieval and logical inference.

    **Topics:** RAG, LLMs, Vector Search, Graph Traversal · **Difficulty:** Advanced
  </Card>
  <Card title="RAG vs. GraphRAG Comparison" icon="scale-balanced" href="https://github.com/semantica-agi/semantica/blob/main/cookbook/use_cases/advanced_rag/02_RAG_vs_GraphRAG_Comparison.ipynb">
    Side-by-side benchmark of standard RAG vs. GraphRAG on real-world data.

    **Topics:** RAG, GraphRAG, Benchmarking · **Difficulty:** Intermediate
  </Card>
  <Card title="Real-Time Anomaly Detection" icon="shield-halved" href="https://github.com/semantica-agi/semantica/blob/main/cookbook/use_cases/cybersecurity/01_Real_Time_Anomaly_Detection.ipynb">
    Detect anomalies in streaming data using dynamic knowledge graphs.

    **Topics:** Streaming, Security, Dynamic Graphs · **Difficulty:** Advanced
  </Card>
</CardGroup>


## Core Tutorials

Essential guides to master the Semantica framework.

<CardGroup cols={2}>
  <Card title="Welcome to Semantica" icon="hands" href="https://github.com/semantica-agi/semantica/blob/main/cookbook/introduction/01_Welcome_to_Semantica.ipynb">
    An interactive introduction to the framework's core philosophy and all modules.

    **Topics:** Framework Overview, Architecture · **Difficulty:** Beginner
  </Card>
  <Card title="Data Ingestion" icon="database" href="https://github.com/semantica-agi/semantica/blob/main/cookbook/introduction/02_Data_Ingestion.ipynb">
    Loading data from files, web, databases, streams, feeds, repositories, email, and MCP.

    **Topics:** FileIngestor, WebIngestor, DBIngestor, Streams · **Difficulty:** Beginner
  </Card>
  <Card title="Document Parsing" icon="file-lines" href="https://github.com/semantica-agi/semantica/blob/main/cookbook/introduction/03_Document_Parsing.ipynb">
    Extracting clean text from complex formats like PDF, DOCX, and HTML.

    **Topics:** OCR, PDF Parsing, Text Extraction · **Difficulty:** Beginner
  </Card>
  <Card title="Data Normalization" icon="broom" href="https://github.com/semantica-agi/semantica/blob/main/cookbook/introduction/04_Data_Normalization.ipynb">
    Pipelines for cleaning, normalizing, and preparing text.

    **Topics:** Text Cleaning, Unicode, Formatting · **Difficulty:** Beginner
  </Card>
  <Card title="Entity Extraction" icon="magnifying-glass" href="https://github.com/semantica-agi/semantica/blob/main/cookbook/introduction/05_Entity_Extraction.ipynb">
    Using NER to identify people, organizations, and custom entities.

    **Topics:** NER, spaCy, LLM Extraction · **Difficulty:** Beginner
  </Card>
  <Card title="Relation Extraction" icon="arrows-split-up-and-left" href="https://github.com/semantica-agi/semantica/blob/main/cookbook/introduction/06_Relation_Extraction.ipynb">
    Discovering and classifying relationships between entities.

    **Topics:** Relation Classification, Dependency Parsing · **Difficulty:** Beginner
  </Card>
  <Card title="Embedding Generation" icon="vector-square" href="https://github.com/semantica-agi/semantica/blob/main/cookbook/introduction/12_Embedding_Generation.ipynb">
    Creating and managing vector embeddings for semantic search.

    **Topics:** Embeddings, OpenAI, HuggingFace · **Difficulty:** Intermediate
  </Card>
  <Card title="Vector Store" icon="database" href="https://github.com/semantica-agi/semantica/blob/main/cookbook/introduction/13_Vector_Store.ipynb">
    Setting up vector stores for similarity search and retrieval.

    **Difficulty:** Intermediate
  </Card>
  <Card title="Graph Store" icon="server" href="https://github.com/semantica-agi/semantica/blob/main/cookbook/introduction/09_Graph_Store.ipynb">
    Persisting knowledge graphs in Neo4j or FalkorDB.

    **Topics:** Neo4j, Cypher, Persistence · **Difficulty:** Intermediate
  </Card>
  <Card title="Ontology" icon="sitemap" href="https://github.com/semantica-agi/semantica/blob/main/cookbook/introduction/14_Ontology.ipynb">
    Defining domain schemas and ontologies to structure your data.

    **Topics:** OWL, RDF, Schema Design · **Difficulty:** Intermediate
  </Card>
</CardGroup>


## Advanced Concepts

Deep dive into advanced features, customization, and complex workflows.

<CardGroup cols={2}>
  <Card title="Advanced Extraction" icon="flask" href="https://github.com/semantica-agi/semantica/blob/main/cookbook/advanced/01_Advanced_Extraction.ipynb">
    Custom extractors, LLM-based extraction, and complex pattern matching.

    **Topics:** Custom Models, Regex, LLMs · **Difficulty:** Advanced
  </Card>
  <Card title="Advanced Graph Analytics" icon="chart-network" href="https://github.com/semantica-agi/semantica/blob/main/cookbook/advanced/02_Advanced_Graph_Analytics.ipynb">
    Centrality, community detection, and pathfinding algorithms.

    **Topics:** PageRank, Louvain, Shortest Path · **Difficulty:** Advanced
  </Card>
  <Card title="Advanced Context Engineering" icon="brain" href="https://github.com/semantica-agi/semantica/blob/main/cookbook/advanced/11_Advanced_Context_Engineering.ipynb">
    Production-grade memory system for AI agents using FAISS and Neo4j.

    **Topics:** Agent Memory, GraphRAG, Entity Injection · **Difficulty:** Advanced
  </Card>
  <Card title="Complete Visualization Suite" icon="chart-bar" href="https://github.com/semantica-agi/semantica/blob/main/cookbook/advanced/03_Complete_Visualization_Suite.ipynb">
    Interactive, publication-ready visualizations of your graphs.

    **Topics:** PyVis, NetworkX, D3.js · **Difficulty:** Intermediate
  </Card>
  <Card title="Conflict Resolution" icon="scale-balanced" href="https://github.com/semantica-agi/semantica/blob/main/cookbook/introduction/17_Conflict_Detection_and_Resolution.ipynb">
    Strategies for handling contradictory information from multiple sources.

    **Topics:** Truth Discovery, Voting, Confidence · **Difficulty:** Advanced
  </Card>
  <Card title="Multi-Format Export" icon="file-export" href="https://github.com/semantica-agi/semantica/blob/main/cookbook/advanced/05_Multi_Format_Export.ipynb">
    Exporting to RDF, OWL, JSON-LD, and NetworkX formats.

    **Topics:** Serialization, Interoperability · **Difficulty:** Intermediate
  </Card>
  <Card title="Multi-Source Integration" icon="code-merge" href="https://github.com/semantica-agi/semantica/blob/main/cookbook/advanced/06_Multi_Source_Data_Integration.ipynb">
    Merging data from disparate sources into a unified graph.

    **Topics:** Entity Resolution, Merging, Fusion · **Difficulty:** Advanced
  </Card>
  <Card title="Pipeline Orchestration" icon="gear" href="https://github.com/semantica-agi/semantica/blob/main/cookbook/advanced/07_Pipeline_Orchestration.ipynb">
    Building robust, automated data processing pipelines.

    **Topics:** Workflows, Automation, Error Handling · **Difficulty:** Advanced
  </Card>
  <Card title="Reasoning and Inference" icon="brain" href="https://github.com/semantica-agi/semantica/blob/main/cookbook/advanced/08_Reasoning_and_Inference.ipynb">
    Using logical reasoning to infer new knowledge from existing facts.

    **Topics:** Logic Rules, Inference Engines · **Difficulty:** Advanced
  </Card>
  <Card title="Temporal Knowledge Graphs" icon="clock" href="https://github.com/semantica-agi/semantica/blob/main/cookbook/advanced/10_Temporal_Knowledge_Graphs.ipynb">
    Modeling and querying data that changes over time.

    **Topics:** Time Series, Temporal Logic, Allen Algebra · **Difficulty:** Advanced
  </Card>
</CardGroup>


## Industry Use Cases

### Biomedical

<CardGroup cols={2}>
  <Card title="Drug Discovery Pipeline" icon="pills" href="https://github.com/semantica-agi/semantica/blob/main/cookbook/use_cases/biomedical/01_Drug_Discovery_Pipeline.ipynb">
    Accelerating drug discovery by connecting genes, proteins, and drugs using PubMed RSS feeds, entity-aware chunking, GraphRAG, and vector similarity search.

    **Topics:** Bioinformatics, KG Construction, GraphRAG · **Difficulty:** Advanced
  </Card>
  <Card title="Genomic Variant Analysis" icon="dna" href="https://github.com/semantica-agi/semantica/blob/main/cookbook/use_cases/biomedical/02_Genomic_Variant_Analysis.ipynb">
    Analyzing genomic variants and their implications using bioRxiv RSS feeds, temporal KGs, deduplication, and pathway analysis.

    **Topics:** Genomics, Temporal KGs, Graph Analytics · **Difficulty:** Advanced
  </Card>
</CardGroup>

### Finance

<CardGroup cols={2}>
  <Card title="Financial Data Integration (MCP)" icon="chart-line" href="https://github.com/semantica-agi/semantica/blob/main/cookbook/use_cases/finance/01_Financial_Data_Integration_MCP.ipynb">
    Merging financial data from Alpha Vantage API, MCP servers, RSS feeds, and market feeds.

    **Topics:** Finance, Data Fusion, MCP Integration · **Difficulty:** Intermediate
  </Card>
  <Card title="Fraud Detection" icon="user-secret" href="https://github.com/semantica-agi/semantica/blob/main/cookbook/use_cases/finance/02_Fraud_Detection.ipynb">
    Identifying fraudulent activities in transaction networks using temporal KGs, conflict detection, and pattern recognition.

    **Topics:** Anomaly Detection, Graph Mining, Temporal Analysis · **Difficulty:** Advanced
  </Card>
</CardGroup>

### Blockchain

<CardGroup cols={2}>
  <Card title="DeFi Protocol Intelligence" icon="bitcoin-sign" href="https://github.com/semantica-agi/semantica/blob/main/cookbook/use_cases/blockchain/01_DeFi_Protocol_Intelligence.ipynb">
    Analyzing decentralized finance protocols and transaction flows using CoinDesk RSS feeds, ontology-aware chunking, and conflict detection.

    **Topics:** Blockchain, DeFi, Smart Contracts, Ontology · **Difficulty:** Advanced
  </Card>
  <Card title="Transaction Network Analysis" icon="network-wired" href="https://github.com/semantica-agi/semantica/blob/main/cookbook/use_cases/blockchain/02_Transaction_Network_Analysis.ipynb">
    Mapping and analyzing blockchain transaction networks using deduplication and network pattern detection.

    **Topics:** Blockchain Analytics, Network Analysis · **Difficulty:** Advanced
  </Card>
</CardGroup>

### Cybersecurity

<CardGroup cols={2}>
  <Card title="Real-Time Anomaly Detection" icon="shield-halved" href="https://github.com/semantica-agi/semantica/blob/main/cookbook/use_cases/cybersecurity/01_Real_Time_Anomaly_Detection.ipynb">
    Detecting anomalies in real-time network traffic streams using CVE RSS feeds, Kafka streams, and temporal KGs.

    **Topics:** Network Security, Streaming, Temporal KGs · **Difficulty:** Advanced
  </Card>
  <Card title="Threat Intelligence Hybrid RAG" icon="robot" href="https://github.com/semantica-agi/semantica/blob/main/cookbook/use_cases/cybersecurity/02_Threat_Intelligence_Hybrid_RAG.ipynb">
    Combining enhanced GraphRAG with threat intelligence for security insights.

    **Topics:** Threat Intelligence, GraphRAG, Hybrid Retrieval · **Difficulty:** Advanced
  </Card>
</CardGroup>

### Intelligence

<CardGroup cols={2}>
  <Card title="Criminal Network Analysis" icon="users" href="https://github.com/semantica-agi/semantica/blob/main/cookbook/use_cases/intelligence/01_Criminal_Network_Analysis.ipynb">
    Analyze criminal networks with graph analytics and key player detection using OSINT RSS feeds and network centrality analysis.

    **Topics:** Forensics, Social Network Analysis · **Difficulty:** Advanced
  </Card>
  <Card title="Intelligence Analysis Orchestrator" icon="file-magnifying-glass" href="https://github.com/semantica-agi/semantica/blob/main/cookbook/use_cases/intelligence/02_Intelligence_Analysis_Orchestrator_Worker.ipynb">
    Comprehensive intelligence analysis using pipeline orchestrator with multiple RSS feeds and multi-source integration.

    **Topics:** Intelligence Analysis, Pipeline Orchestration · **Difficulty:** Advanced
  </Card>
</CardGroup>

### Renewable Energy & Supply Chain

<CardGroup cols={2}>
  <Card title="Energy Market Analysis" icon="wind" href="https://github.com/semantica-agi/semantica/blob/main/cookbook/use_cases/renewable_energy/01_Energy_Market_Analysis.ipynb">
    Analyzing trends and pricing in the renewable energy market using EIA API, temporal KGs, and TemporalPatternDetector.

    **Topics:** Energy, Time Series, Temporal Analysis · **Difficulty:** Intermediate
  </Card>
  <Card title="Supply Chain Data Integration" icon="truck" href="https://github.com/semantica-agi/semantica/blob/main/cookbook/use_cases/supply_chain/01_Supply_Chain_Data_Integration.ipynb">
    Integrating supply chain data to optimize logistics and reduce risk.

    **Topics:** Logistics, Risk Management, Deduplication · **Difficulty:** Advanced
  </Card>
</CardGroup>


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
