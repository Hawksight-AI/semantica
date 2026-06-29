---
title: "GraphRAG — Graph-Augmented Retrieval"
description: "Go beyond vector search: retrieve facts, trace reasoning paths, and ground LLM responses in your knowledge graph."
---

GraphRAG combines vector similarity with knowledge graph traversal so retrieval finds structurally connected facts, not just text that sounds related. When a `ContextGraph` is attached to `AgentContext`, every retrieval call automatically blends semantic search with multi-hop graph expansion — and `query_with_reasoning()` returns an auditable reasoning path alongside the LLM answer.

## What Is GraphRAG?

GraphRAG (Graph-Augmented Retrieval-Augmented Generation) enhances traditional RAG by combining vector similarity search with knowledge graph traversal. Instead of retrieving only semantically similar text, GraphRAG follows relationships between entities to find connected evidence across multiple documents.

**GraphRAG vs. traditional vector-only RAG:** Vector RAG finds documents similar to your query text. GraphRAG finds documents similar to your query AND documents connected to those through entity relationships, even if they don't mention your query terms directly.

**The role of graph traversal:** Starting from entities found in vector-similar documents, GraphRAG expands outward through relationship edges to discover related facts. This reveals connections that pure text similarity would miss — like finding that a threat actor targets healthcare by following the path: Actor → Tool → Victim Organization → Industry Sector.

## Why Use GraphRAG?

**Multi-hop discovery.** Find facts that are 2-3 relationship steps away from your query. A question about "APT29 healthcare targeting" can surface evidence about specific hospitals by traversing: APT29 → HAMMERTOSS → LifeCare → Healthcare Sector.

**Connected evidence.** Instead of isolated document fragments, retrieve coherent chains of related entities and their relationships. This provides richer context for LLM responses and human analysis.

**Investigation workflows.** Follow evidence trails by expanding from known entities through their connections. Start with a suspicious IP and discover the full infrastructure chain, or trace a drug interaction through metabolic pathways.

**Richer retrieval context.** Graph expansion surfaces relevant context that keyword or semantic search alone would miss, leading to more complete and accurate LLM responses.

**Explainability.** GraphRAG provides audit trails showing exactly which entities and relationships led to each piece of retrieved evidence, making the retrieval process transparent and verifiable.

## When To Use / When Not To Use

**GraphRAG adds value when:**
- Your domain has rich entity relationships (threat intelligence, clinical data, regulatory documents)
- Questions require connecting facts across multiple documents
- Investigation workflows benefit from following entity connections
- Explainability and audit trails are important
- You have well-structured knowledge graphs with meaningful relationships

**Simple vector search may be sufficient for:**
- Document retrieval based on topic similarity
- Single-document question answering
- Exploratory search where you don't know what you're looking for
- Domains with few meaningful entity relationships

**Latency and complexity considerations:**
- GraphRAG adds computational overhead from graph traversal
- Multi-hop expansion increases retrieval time and token usage
- Graph quality directly impacts retrieval quality
- Setup requires entity extraction and relationship building

**GraphRAG may be overkill for:**
- Simple lookup queries with known answers in specific documents
- Real-time applications where latency is critical
- Domains where entity relationships don't provide additional value

## Typical GraphRAG Workflow

**Ingest → Build Graph → Retrieve → Expand Context → Reason → Answer**

1. **Ingest** your documents using `AgentContext.store()` with entity extraction enabled
2. **Build Graph** through Named Entity Recognition (NER) and relationship extraction to populate the `ContextGraph`
3. **Retrieve** semantically similar documents and identify seed entities for graph expansion
4. **Expand Context** by following entity relationships within your specified hop limit
5. **Reason** (optional) using the expanded context with reasoning engines
6. **Answer** by providing the enriched context to an LLM through `query_with_reasoning()`

<Info>
  **Graph Quality Dependency:** GraphRAG retrieval quality depends heavily on graph quality, consistent entity linking, and meaningful relationships. Poor entity extraction, duplicate entities, or weak relationships directly impact retrieval effectiveness.
</Info>

<Info>
  **Context Expansion Warning:** Larger hop counts exponentially increase the amount of retrieved context, which can significantly increase LLM token usage and processing time. Start with 2-3 hops and monitor context size for your use case.
</Info>

<Info>
GraphRAG activates automatically when you pass `knowledge_graph=` to `AgentContext`. There is no separate mode to switch on. The `hybrid_alpha` parameter and `proximity_weight` argument control how much influence graph structure has relative to vector similarity.
</Info>

## Building the graph and loading your intelligence

Before you can query the graph, you need to build it. The setup is three objects: a vector store for embedding-based retrieval, a `ContextGraph` for structural traversal, and an `AgentContext` that wires them together.

```python
from semantica.context import AgentContext, ContextGraph
from semantica.vector_store import VectorStore

# FAISS runs locally with no external dependencies
vs = VectorStore(backend="faiss", dimension=768, index_path="intel.faiss")
graph = ContextGraph(advanced_analytics=True)

context = AgentContext(
    vector_store=vs,
    knowledge_graph=graph,
    graph_expansion=True,     # enable multi-hop traversal from seed nodes
    max_expansion_hops=3,     # APT29 → infrastructure → victim → sector is 3 hops
    hybrid_alpha=0.6,         # 60% graph influence, 40% vector similarity
    decision_tracking=True,   # record analyst queries as auditable decisions
)
```

Now ingest your documents. `store()` with `extract_entities=True` runs the full extraction pipeline internally — Named Entity Recognition (NER), relation extraction, and entity linking — and populates both the vector index and the graph simultaneously:

```python
intel_documents = [
    {
        "content": "APT29 deployed HAMMERTOSS malware against NATO logistics networks in Jan–Mar 2025. "
                   "C2 infrastructure used Tor exit nodes in AS59796.",
        "metadata": {"source": "FINTEL_2025_0192", "classification": "SECRET//NOFORN"},
    },
    {
        "content": "HAMMERTOSS was subsequently observed on hosts in the LifeCare hospital network "
                   "(AS64496), suggesting lateral movement beyond the initial NATO targets.",
        "metadata": {"source": "FINTEL_2025_0211"},
    },
    {
        "content": "LifeCare operates 47 acute-care hospitals and is classified as Tier-1 "
                   "healthcare critical infrastructure under CISA Sector 6.",
        "metadata": {"source": "CISA_CI_REGISTRY_2025"},
    },
    {
        "content": "Healthcare critical infrastructure has been a high-priority targeting class "
                   "for Russian state-sponsored threat actors since 2022.",
        "metadata": {"source": "NCSC_ADVISORY_2024_12"},
    },
]

stats = context.store(
    intel_documents,
    extract_entities=True,
    extract_relationships=True,
    link_entities=True,    # merge duplicate entity mentions across documents
)

print("Graph built: {} nodes, {} edges".format(
    stats["graph_nodes"], stats["graph_edges"]
))
# Graph built: 18 nodes, 14 edges
# Nodes: APT29, HAMMERTOSS, NATO, LifeCare, AS59796, CISA Sector 6, ...
# Edges: deployed, observed_on, classified_as, targets, operates_in, ...
```

The graph now contains a connected subgraph linking APT29 to healthcare infrastructure across four document boundaries — something that would be invisible to a pure vector search.

## Retrieving the relevant subgraph

With the graph populated, a plain `retrieve()` call already does more than vector search. When `use_graph=True`, the retriever seeds the graph traversal from the top-k vector matches and expands outward by following edges, collecting connected facts within `max_hops`:

```python
results = context.retrieve(
    "APT29 tactics against healthcare",
    use_graph=True,
    max_results=10,
    expand_graph=True,
    max_hops=3,
)

for r in results:
    print("[score={:.3f}]  {}".format(
        r["score"],
        r["content"][:90],
    ))

# [score=0.921]  APT29 deployed HAMMERTOSS malware against NATO...
# [score=0.887]  HAMMERTOSS was subsequently observed on hosts in the LifeCare...
# [score=0.841]  LifeCare operates 47 acute-care hospitals...
# [score=0.798]  Healthcare critical infrastructure has been a high-priority...
```

Notice the top results: while pure vector search might rank connected facts lower because they lack keyword overlap, GraphRAG boosts their final `score` because they are structurally adjacent to the seed nodes in the graph. The returned `score` is a transparent blend of vector relevance and graph connectivity.

When you know specifically which entity you want to anchor the traversal to, pass `anchor_node`:

```python
# Anchor on APT29 explicitly — proximity scores are calculated from this node
apt29_intel = context.retrieve(
    "C2 infrastructure beaconing patterns",
    use_graph=True,
    anchor_node="APT29",
    proximity_weight=0.7,   # strongly favour nodes close to APT29
    max_hops=3,
    max_results=8,
)
```

## Getting a grounded LLM answer with a reasoning path

`retrieve()` gives you the grounded context. `query_with_reasoning()` goes one step further: it passes that subgraph context to an LLM and returns the answer together with the multi-hop path the retrieval system traced through the graph. That path is your audit trail.

```python
from semantica.llms import LiteLLM

llm = LiteLLM(model="anthropic/claude-sonnet-4-20250514")

result = context.query_with_reasoning(
    "What are APT29's known TTPs against healthcare infrastructure, "
    "and what is the evidence chain connecting them?",
    llm_provider=llm,
    max_results=12,
    max_hops=3,
)

# The LLM answer — grounded in graph-retrieved context, not training memory
print(result["response"])

# The multi-hop trace: APT29 → deployed → HAMMERTOSS → observed_on → LifeCare → ...
print("\n--- Reasoning Path ---")
print(result["reasoning_path"])

# Confidence reflects how well the retrieved context supports the answer
print("\nConfidence: {:.1%}".format(result["confidence"]))

# Inspect every source the LLM was given
print("\nSources ({} total):".format(result["num_sources"]))
for src in result["sources"]:
    print("  [{:.3f}] {}".format(src["score"], src["content"][:80]))
```

The `reasoning_path` field is what separates GraphRAG from a black-box LLM call. When an analyst asks "how do you know APT29 targeted healthcare?", you can show them the exact traversal the system made across your own documents — not a claim the model generated from training data.

The full return structure from `query_with_reasoning()`:

```python
{
    "response":             str,   # LLM-generated answer, grounded in retrieved subgraph
    "reasoning_path":       str,   # multi-hop traversal narrative
    "sources":              list,  # list of retrieved context dicts with scores
    "confidence":           float, # 0–1 aggregate confidence
    "num_sources":          int,
    "num_reasoning_paths":  int,
}
```

## Domain examples

<Tabs>

<Tab title="Defense — CTI/Threat">

Multi-INT intelligence fusion: OSINT threat feeds, NVD CVE data, and HUMINT summaries ingested into a single graph, then queried with multi-hop reasoning to trace C2 infrastructure chains and attribute campaigns to specific actors.

In classified environments the graph can be partitioned by data handling caveat — each `AgentContext` operates over the subset of documents cleared for the querying user. The `reasoning_path` output doubles as a sanitisable audit trail for downgraded reporting.

```python
from semantica.context import AgentContext, ContextGraph
from semantica.vector_store import VectorStore
from semantica.llms import LiteLLM

vs    = VectorStore(backend="faiss", dimension=768)
graph = ContextGraph()

context = AgentContext(
    vector_store=vs,
    knowledge_graph=graph,
    graph_expansion=True,
    max_expansion_hops=3,  # actor → infra → victim → attribution chain
    hybrid_alpha=0.6,      # graph-heavy: structured intel benefits from topology
    decision_tracking=True,
)

# Ingest multi-INT corpus
humint_summary = """
HUMINT-2025-Q1-007: Source BRAVO-9 confirms APT29 operating from
infrastructure in AS59796. C2 beacons use Tor exit nodes in DE/NL.
Targets: ITAR-controlled defense contractors in aerospace sector.
"""
cti_report_text = "APT29 exploited CVE-2025-3400 in PAN-OS GlobalProtect to gain initial access..."

context.store(
    [
        {"content": humint_summary,    "metadata": {"source": "HUMINT-2025-Q1-007"}},
        {"content": cti_report_text,   "metadata": {"source": "CTI_RPT_APT29_2025"}},
    ],
    extract_entities=True,
    extract_relationships=True,
    link_entities=True,
)

llm    = LiteLLM(model="anthropic/claude-sonnet-4-20250514")
result = context.query_with_reasoning(
    "Trace the C2 infrastructure chain for APT29 operations targeting "
    "ITAR-controlled contractors in 2025. Include IP ranges, ASNs, and TTPs.",
    llm_provider=llm,
    max_results=15,
    max_hops=3,
)

print(result["response"])
print("\n--- Reasoning Path ---")
print(result["reasoning_path"])
print("Confidence: {:.1%}".format(result["confidence"]))

# Anchor retrieval on APT29 for a proximity-weighted follow-up
proximate = context.retrieve(
    "C2 beaconing patterns Tor exit nodes",
    use_graph=True,
    anchor_node="APT29",
    proximity_weight=0.7,
    max_hops=3,
    max_results=10,
)
```

</Tab>

<Tab title="Security — SOC/Incident">

Security operations: real-time alert triage against a graph containing hosts, CVEs, user accounts, runbooks, and historical incidents. GraphRAG retrieves the relevant runbook and similar past incidents in a single call, reducing mean-time-to-respond.

The `decision_tracking=True` flag records every triage query as an auditable decision, with the full context that was provided to the LLM — essential for post-incident review and SOC metrics.

```python
from semantica.context import AgentContext, ContextGraph
from semantica.vector_store import VectorStore
from semantica.llms import LiteLLM

vs    = VectorStore(backend="faiss", dimension=768)
graph = ContextGraph()

soc_context = AgentContext(
    vector_store=vs,
    knowledge_graph=graph,
    graph_expansion=True,
    max_expansion_hops=2,
    hybrid_alpha=0.5,
    decision_tracking=True,
    retention_days=365,
)

runbooks = [
    "RB-001: Lateral movement — isolate source host, collect memory dump, "
    "escalate if EDR alert on LSASS access.",
    "RB-002: Ransomware precursor — block C2 range, snapshot affected volumes, "
    "engage IR team within 15 minutes.",
    "RB-003: Scheduled task persistence — review parent process, check Sigma "
    "T1053.005, quarantine if encoded payload confirmed.",
]
soc_context.store(runbooks, extract_entities=True)

alert_text = """
ALERT-2025-110342 [CRITICAL]
Host: dc01.corp.internal (10.10.1.5)
User: svc_backup (DOMAIN\\svc_backup)
Event: Scheduled task created — cmd.exe /c powershell -enc <base64>
Parent: wmiprvse.exe
Sigma match: T1053.005 Scheduled Task/Job
"""

llm    = LiteLLM(model="anthropic/claude-sonnet-4-20250514")
triage = soc_context.query_with_reasoning(
    "Triage this SIEM alert and identify the correct response runbook:\n{}".format(alert_text),
    llm_provider=llm,
    max_results=8,
    max_hops=2,
)

print("TRIAGE: {}".format(triage["response"]))
# TRIAGE: Based on the wmiprvse.exe parent spawning an encoded PowerShell scheduled task,
# this matches the persistence pattern in RB-003. Recommended action: review parent process
# chain, confirm encoded payload, quarantine dc01.corp.internal if confirmed...
print("Confidence: {:.1%}".format(triage["confidence"]))

# Also pull similar historical incidents for analyst context
similar = soc_context.retrieve(
    "wmiprvse.exe encoded powershell scheduled task persistence",
    use_graph=True,
    max_results=5,
)
for inc in similar:
    print("[{:.3f}] {}".format(inc["score"], inc["content"][:100]))
```

</Tab>

<Tab title="Life Science — Clinical/Pharma">

Clinical decision support: FDA drug labels, clinical guidelines, and trial summaries ingested into a graph where drug-enzyme-metabolite-interaction chains become traversable paths. A three-hop query (drug → enzyme → metabolite → contraindication) surfaces interaction risks that no single document would make explicit.

Setting `max_expansion_hops=3` is deliberate: the pharmacokinetic chain from amiodarone to elevated warfarin plasma levels runs drug → CYP2C9 inhibition → warfarin metabolism reduced → bleeding risk, which is exactly three structural hops.

```python
from semantica.context import AgentContext, ContextGraph
from semantica.vector_store import VectorStore
from semantica.llms import LiteLLM

vs    = VectorStore(backend="faiss", dimension=768)
graph = ContextGraph()

clinical_context = AgentContext(
    vector_store=vs,
    knowledge_graph=graph,
    graph_expansion=True,
    max_expansion_hops=3,  # drug → enzyme → metabolite → interaction
    hybrid_alpha=0.55,
    retention_days=None,   # clinical records: no expiry
)

fda_label_text = (
    "Warfarin sodium: narrow therapeutic index anticoagulant. CYP2C9 is the "
    "primary metabolic pathway. Amiodarone is a potent CYP2C9 inhibitor..."
)

guideline_text = (
    "ESC 2023 AF Guidelines: bridging therapy with heparin is not recommended "
    "for most patients with AF undergoing elective procedures..."
)

clinical_context.store(
    [
        {"content": fda_label_text,  "metadata": {"source": "FDA_WARFARIN_LABEL_2024"}},
        {"content": guideline_text,  "metadata": {"source": "ESC_AF_GUIDELINE_2023"}},
    ],
    extract_entities=True,
    extract_relationships=True,
    link_entities=True,
)

patient_context = """
Patient: 68F, AF, CKD stage 3b (eGFR 32). On warfarin (INR target 2.0–3.0).
Presenting for elective hip replacement. Concurrent: amiodarone 200mg, atorvastatin 40mg.
"""

llm    = LiteLLM(model="anthropic/claude-sonnet-4-20250514")
answer = clinical_context.query_with_reasoning(
    "What is the evidence-based warfarin bridging protocol for this patient "
    "given CKD and amiodarone interaction risk?\n\n{}".format(patient_context),
    llm_provider=llm,
    max_results=12,
    max_hops=3,
)

print(answer["response"])
print("Evidence sources: {}".format(answer["num_sources"]))
print("Reasoning hops:   {}".format(answer["num_reasoning_paths"]))

# Pull the contraindication chain explicitly
contra_chain = clinical_context.retrieve(
    "CYP2C9 inhibition amiodarone warfarin bleeding risk",
    use_graph=True,
    anchor_node="warfarin",
    proximity_weight=0.65,
    max_hops=3,
    max_results=6,
)
```

</Tab>

<Tab title="Banking — Risk/Compliance">

Regulatory compliance: Basel III (CRE20), BCBS 239, SR 11-7, and EBA IRRBB guidelines ingested as a graph where regulation articles cross-reference each other as edges. Multi-hop queries traverse those cross-references automatically, so a question about commercial real estate RWA pulls the relevant CRE20 paragraphs and the BCBS 239 data quality requirements that govern their calculation in a single call.

The `reasoning_path` output serves directly as the audit trail required by regulators to demonstrate that a capital calculation was grounded in cited regulatory text.

```python
from semantica.context import AgentContext, ContextGraph
from semantica.vector_store import VectorStore
from semantica.llms import LiteLLM

vs    = VectorStore(backend="faiss", dimension=768)
graph = ContextGraph()

compliance_context = AgentContext(
    vector_store=vs,
    knowledge_graph=graph,
    graph_expansion=True,
    max_expansion_hops=2,
    hybrid_alpha=0.5,
    retention_days=2555,   # 7-year regulatory retention
)

# In production these come from ingest_file() — shown as strings here for brevity
basel_cre20_text  = "CRE20.32: For income-producing real estate where repayment depends on "
                    "property cash flows, RWA = exposure × risk weight, where risk weight "
                    "is determined by LTV bucket per Table CRE20.3..."
bcbs239_text      = "Principle 3: Risk data should be accurate and have a single authoritative source. "
                    "Where data is aggregated across systems, reconciliation must be documented..."

compliance_context.store(
    [
        {"content": basel_cre20_text, "metadata": {"source": "BCBS_CRE20_2024"}},
        {"content": bcbs239_text,     "metadata": {"source": "BCBS239_2013"}},
    ],
    extract_entities=True,
    extract_relationships=True,
)

llm    = LiteLLM(model="anthropic/claude-sonnet-4-20250514")
answer = compliance_context.query_with_reasoning(
    "Under Basel III CRE20, what are the RWA calculation requirements for "
    "commercial real estate exposures with LTV > 80%? "
    "Cross-reference with BCBS 239 data quality requirements.",
    llm_provider=llm,
    max_results=12,
    max_hops=2,
)

print(answer["response"])
print("Regulatory sources cited: {}".format(answer["num_sources"]))
print("Confidence: {:.1%}".format(answer["confidence"]))

# The reasoning path is the audit log — show it to the regulator
print("\n--- Reasoning Path (audit log) ---")
print(answer["reasoning_path"])
```

</Tab>

</Tabs>

## Common Pitfalls

**Excessive hop counts.** Setting `max_expansion_hops` too high (>4) creates exponentially large context that overwhelms LLMs and increases costs. Start with 2-3 hops and increase only if needed.

**Poor graph quality.** GraphRAG amplifies graph quality issues. Duplicate entities, inconsistent naming, and weak relationships produce poor retrieval results. Clean your graph data before relying on GraphRAG for important queries.

**Duplicate entities.** Having "APT-29", "APT29", and "Cozy Bear" as separate nodes breaks relationship traversal. Entity linking during ingestion helps, but manual deduplication may be necessary.

**Using GraphRAG for simple lookup queries.** If you know the answer exists in a specific document and just need to retrieve it, traditional vector search is faster and simpler than GraphRAG.

**Assuming graph expansion is always beneficial.** More context isn't always better. Sometimes precise, focused retrieval outperforms broad graph expansion. Test both approaches for your specific use cases.

## Tuning the vector-graph balance

The `hybrid_alpha` parameter set in the `AgentContext` constructor establishes a default blend between vector similarity and graph influence. `0.0` is pure vector retrieval; `1.0` is pure graph traversal. The recommended starting point is `0.5`.

When targeting a specific `anchor_node`, you can apply `proximity_weight` in `retrieve()` to dynamically blend structural distance from the anchor into the final score:

```python
# Anchor node provided — let vector semantics lead, graph proximity only slightly boosts
results = context.retrieve(
    query, use_graph=True, anchor_node="APT29", proximity_weight=0.2
)

# Known-entity tracing — topology drives the retrieval
results = context.retrieve(
    query, use_graph=True, anchor_node="APT29", proximity_weight=0.8
)
```

Each additional hop in `max_hops` exponentially increases the subgraph size. Practical defaults by domain:

```text
General Q&A             max_expansion_hops=2  (95% of useful facts within 2 hops)
Threat intel (APT)      max_expansion_hops=3  (actor → infra → victim → attribution)
Drug interactions       max_expansion_hops=3  (drug → enzyme → metabolite → interaction)
Regulatory cross-ref    max_expansion_hops=2  (rule → article → article)
```

Set globally in the constructor; override per call with the `max_hops` argument to `retrieve()`.

## How GraphRAG works internally

```text
Query text
    |
    v
Vector embedding  ─────────────────────────────────────┐
    |                                                   |
    v                                                   v
Semantic search                         Graph traversal (BFS)
(FAISS / Qdrant)                        from anchor / top-k seeds
    |                                                   |
    └──────────┐                ┌──────────────────────┘
               v                v
         Score fusion (proximity_weight blend)
               |
               v
          Ranked subgraph
               |
               v
         LLM grounding  <── query_with_reasoning()
               |
               v
     {response, reasoning_path, sources, confidence}
```

The vector search and graph traversal run independently, then their scores are fused. The graph traversal uses breadth-first expansion from the seed nodes identified by the vector search, so the graph component is always anchored in semantic relevance rather than exploring the entire graph blindly.

## Related Guides

- [Semantic Extraction](semantic-extraction) — build the graph from raw unstructured text
- [Agent Memory](agent-memory) — store, retrieve, and persist agent memories
- [Context Graphs](context-graphs) — build and traverse the knowledge graph directly
- [Reasoning](reasoning) — derive new facts and run inference rules over the graph
- [Decision Intelligence](decision-intelligence) — causal chains, policy enforcement, decision tracking
- [LLM Integrations](llm-integrations) — connect Groq, OpenAI, Anthropic, HuggingFace, and 100+ more
