---
title: "Use Cases"
description: "Real-world applications of Semantica across domains, with linked cookbook notebooks for each."
icon: "briefcase"
---

Semantica is purpose-built for environments where AI outputs must be explainable, auditable, and traceable. Every use case below includes linked Jupyter notebooks you can run today.

## Browse by Sector

<Tabs>
  <Tab title="Research & Science">

<CardGroup cols={2}>
  <Card title="Biomedical Knowledge Graphs" icon="heart-pulse" href="https://github.com/semantica-agi/semantica/blob/main/cookbook/use_cases/biomedical/01_Drug_Discovery_Pipeline.ipynb">
    Connect genes, proteins, drugs, and diseases from scientific literature to accelerate drug discovery and understand disease mechanisms.

    **Key modules:** `ingest` (PubMed RSS), `semantic_extract`, `kg`, `deduplication`, `context`

    **Notebooks:**
    - [Drug Discovery Pipeline](https://github.com/semantica-agi/semantica/blob/main/cookbook/use_cases/biomedical/01_Drug_Discovery_Pipeline.ipynb) — Intermediate
    - [Genomic Variant Analysis](https://github.com/semantica-agi/semantica/blob/main/cookbook/use_cases/biomedical/02_Genomic_Variant_Analysis.ipynb) — Intermediate
  </Card>
  <Card title="GraphRAG for Research" icon="magnifying-glass" href="https://github.com/semantica-agi/semantica/blob/main/cookbook/use_cases/advanced_rag/01_GraphRAG_Complete.ipynb">
    Ground LLM answers in structured scientific literature with hybrid retrieval, logical inference, and source attribution on every claim.

    **Key modules:** `context`, `vector_store`, `kg`, `reasoning`, `llms`

    **Notebooks:**
    - [GraphRAG Complete](https://github.com/semantica-agi/semantica/blob/main/cookbook/use_cases/advanced_rag/01_GraphRAG_Complete.ipynb) — Advanced
    - [RAG vs. GraphRAG Comparison](https://github.com/semantica-agi/semantica/blob/main/cookbook/use_cases/advanced_rag/02_RAG_vs_GraphRAG_Comparison.ipynb) — Advanced
  </Card>
</CardGroup>

  </Tab>

  <Tab title="Finance & Trading">

<CardGroup cols={2}>
  <Card title="Financial Data Integration" icon="chart-line" href="https://github.com/semantica-agi/semantica/blob/main/cookbook/use_cases/finance/01_Financial_Data_Integration_MCP.ipynb">
    Unify financial data from APIs, MCP servers, and real-time streams into a single queryable knowledge graph — with conflict detection when sources disagree.

    **Key modules:** `ingest` (API, MCP, stream), `normalize`, `kg`, `conflicts`, `provenance`

    **Notebooks:**
    - [Financial Data Integration (MCP)](https://github.com/semantica-agi/semantica/blob/main/cookbook/use_cases/finance/01_Financial_Data_Integration_MCP.ipynb) — Intermediate
  </Card>
  <Card title="Fraud Detection" icon="shield-halved" href="https://github.com/semantica-agi/semantica/blob/main/cookbook/use_cases/finance/02_Fraud_Detection.ipynb">
    Detect complex fraud rings using temporal graphs and pattern detection over transaction, device, and user data. Temporal edges let you query: "what connections existed during this window?"

    **Key modules:** `kg` (temporal), `conflicts`, `reasoning`, `visualization`

    **Notebooks:**
    - [Fraud Detection](https://github.com/semantica-agi/semantica/blob/main/cookbook/use_cases/finance/02_Fraud_Detection.ipynb) — Advanced
  </Card>
  <Card title="Blockchain Analytics" icon="link" href="https://github.com/semantica-agi/semantica/blob/main/cookbook/use_cases/blockchain/01_DeFi_Protocol_Intelligence.ipynb">
    Map transaction flows, analyze DeFi protocols, and detect illicit activity. Graph algorithms (centrality, community detection) surface high-risk actors that linear transaction analysis misses.

    **Key modules:** `kg`, `reasoning`, `visualization`

    **Notebooks:**
    - [DeFi Protocol Intelligence](https://github.com/semantica-agi/semantica/blob/main/cookbook/use_cases/blockchain/01_DeFi_Protocol_Intelligence.ipynb) — Intermediate
    - [Transaction Network Analysis](https://github.com/semantica-agi/semantica/blob/main/cookbook/use_cases/blockchain/02_Transaction_Network_Analysis.ipynb) — Intermediate
  </Card>
</CardGroup>

  </Tab>

  <Tab title="Security & Intelligence">

<CardGroup cols={2}>
  <Card title="Cybersecurity Threat Intelligence" icon="shield" href="https://github.com/semantica-agi/semantica/blob/main/cookbook/use_cases/cybersecurity/01_Real_Time_Anomaly_Detection.ipynb">
    Ingest threat feeds (CVE databases, security RSS), detect anomalies in streaming data, and build threat intelligence knowledge graphs for proactive defense.

    **Key modules:** `ingest` (stream, feed), `kg` (temporal), `context`, `reasoning`, `export`

    **Notebooks:**
    - [Real-Time Anomaly Detection](https://github.com/semantica-agi/semantica/blob/main/cookbook/use_cases/cybersecurity/01_Real_Time_Anomaly_Detection.ipynb) — Advanced
    - [Threat Intelligence Hybrid RAG](https://github.com/semantica-agi/semantica/blob/main/cookbook/use_cases/cybersecurity/02_Threat_Intelligence_Hybrid_RAG.ipynb) — Advanced
  </Card>
  <Card title="Criminal Network Analysis" icon="users" href="https://github.com/semantica-agi/semantica/blob/main/cookbook/use_cases/intelligence/01_Criminal_Network_Analysis.ipynb">
    Build knowledge graphs from police reports, court records, and OSINT feeds to identify key players, communities, and suspicious patterns. Network centrality surfaces actors text search alone would miss.

    **Key modules:** `ingest`, `semantic_extract`, `kg`, `visualization` (community detection)

    **Notebooks:**
    - [Criminal Network Analysis](https://github.com/semantica-agi/semantica/blob/main/cookbook/use_cases/intelligence/01_Criminal_Network_Analysis.ipynb) — Intermediate
  </Card>
  <Card title="Intelligence Analysis Orchestrator" icon="network-wired" href="https://github.com/semantica-agi/semantica/blob/main/cookbook/use_cases/intelligence/02_Intelligence_Analysis_Orchestrator_Worker.ipynb">
    Process multiple intelligence sources in parallel with an orchestrator-worker pipeline. Multi-source conflict detection flags disagreements rather than silently discarding minority reports.

    **Key modules:** `pipeline`, `ingest`, `conflicts`, `provenance`, `export`

    **Notebooks:**
    - [Intelligence Analysis Orchestrator-Worker](https://github.com/semantica-agi/semantica/blob/main/cookbook/use_cases/intelligence/02_Intelligence_Analysis_Orchestrator_Worker.ipynb) — Intermediate
  </Card>
</CardGroup>

  </Tab>

  <Tab title="Industry & Operations">

<CardGroup cols={2}>
  <Card title="Supply Chain Optimization" icon="truck" href="https://github.com/semantica-agi/semantica/blob/main/cookbook/use_cases/supply_chain/01_Supply_Chain_Data_Integration.ipynb">
    Map suppliers, logistics routes, inventory levels, and delivery relationships to identify bottlenecks and optimize global supply chains. Graph path-finding reveals indirect dependencies spreadsheets miss.

    **Key modules:** `ingest`, `kg`, `reasoning`, `visualization`, `export` (Parquet for analytics)

    **Notebooks:**
    - [Supply Chain Data Integration](https://github.com/semantica-agi/semantica/blob/main/cookbook/use_cases/supply_chain/01_Supply_Chain_Data_Integration.ipynb) — Intermediate
  </Card>
  <Card title="Renewable Energy Management" icon="bolt" href="https://github.com/semantica-agi/semantica/blob/main/cookbook/use_cases/renewable_energy/01_Energy_Market_Analysis.ipynb">
    Connect sensor data, weather forecasts, and maintenance logs to predict equipment failures and optimize grid operations. Temporal graphs track asset states over time and correlate maintenance events with performance degradation.

    **Key modules:** `ingest` (stream, API), `kg` (temporal), `reasoning`, `visualization`

    **Notebooks:**
    - [Energy Market Analysis](https://github.com/semantica-agi/semantica/blob/main/cookbook/use_cases/renewable_energy/01_Energy_Market_Analysis.ipynb) — Intermediate
  </Card>
</CardGroup>

  </Tab>
</Tabs>


## Compliance Footprint by Domain

<AccordionGroup>

<Accordion title="Healthcare & Life Sciences" icon="heart-pulse">

**Regulatory requirements:** HIPAA, FDA 21 CFR Part 11

| Semantica capability | Compliance role |
| :-------------------- | :-------------- |
| W3C PROV-O provenance | Full lineage from raw data to inference — required for FDA audit trails |
| SHA-256 checksums | Tamper detection on every snapshot — supports electronic record integrity |
| Decision tracking | Every AI-assisted recommendation is recorded with causal chain and confidence |
| Temporal graphs | Point-in-time queries for retrospective safety analysis |
| SHACL validation | Schema enforcement before data enters the knowledge graph |

</Accordion>

<Accordion title="Finance & Banking" icon="chart-line">

**Regulatory requirements:** SOX, MiFID II, GDPR, Basel III

| Semantica capability | Compliance role |
| :-------------------- | :-------------- |
| Decision audit trail | Full record of model decisions with reasoning — required for model risk management |
| Conflict detection | Flags when two sources disagree on a valuation or risk figure |
| Version control | SHA-256 snapshot history — supports point-in-time reconstruction for audits |
| Provenance export | RDF with PROV-O inline — submittable to regulatory bodies as structured evidence |

</Accordion>

<Accordion title="Government & Defense" icon="building-columns">

**Operational requirements:** Air-gap capability, chain-of-custody, information provenance

| Semantica capability | Operational role |
| :-------------------- | :--------------- |
| Local LLM support | `HuggingFaceLLM` and Ollama via LiteLLM — fully air-gapped deployments |
| Provenance chains | Every intelligence claim traceable to source document and extraction event |
| Conflict resolution | Multiple-source disagreement resolved with auditable strategy |
| Temporal intelligence | Historical queries over evolving intelligence graphs |

</Accordion>

<Accordion title="Legal & Compliance" icon="scale-balanced">

**Requirements:** Evidence integrity, chain of custody, regulatory change tracking

| Semantica capability | Legal role |
| :-------------------- | :--------- |
| Source attribution | Every extracted fact links to document, page, and section |
| PROV-O export | Structured provenance acceptable as supporting evidence |
| Change management | Version-controlled knowledge bases with diff and rollback |
| Reasoning paths | Explainable inference chains for contested conclusions |

</Accordion>

</AccordionGroup>


## Difficulty Reference

| Level | What it means | Typical time |
| :---- | :------------ | :----------- |
| **Beginner** | Basic Semantica knowledge only, no domain expertise needed | 30–60 min |
| **Intermediate** | Some domain knowledge helpful, uses 2–4 Semantica modules | 1–2 hours |
| **Advanced** | Domain expertise expected, uses temporal graphs, multi-source pipelines, or reasoning | 2–3 hours |

<CardGroup cols={3}>
  <Card title="Cookbook" icon="flask" href="cookbook">
    Full notebook catalog organized by topic and difficulty.
  </Card>
  <Card title="Modules Guide" icon="puzzle-piece" href="modules">
    Every module with code examples.
  </Card>
  <Card title="API Reference" icon="code" href="reference/context">
    Complete technical documentation.
  </Card>
</CardGroup>

<Info>
  Have a use case to add? [Open a PR](https://github.com/semantica-agi/semantica) or start a discussion on GitHub.
</Info>
