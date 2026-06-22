---
title: "Multi-Agent Systems"
description: "Coordinate multiple AI agents through shared memory, knowledge graphs, and decision history — without a message broker."
---

Semantica coordinates multiple agents through a shared `ContextGraph` — agents read and write to the same graph, or hand off serialized state via `save()` and `load()`, with no message broker required. Use this pattern when splitting work across ingestion, enrichment, reasoning, and reporting roles that must share a single evidence base.

<Info>
  This guide covers multi-agent coordination. For the memory layer each agent uses internally, see [Agent Memory](agent-memory). For graph traversal and entity linking, see [Context Graphs](context-graphs). For decision recording and precedent matching, see [Decision Intelligence](decision-intelligence).
</Info>

## The Three Coordination Patterns

Before writing any code, choose the right coordination pattern for your pipeline.

**Shared graph** works when all agents run in the same process. They hold references to the same `ContextGraph` object — thread-safe by default — so every `store()` from one agent is immediately visible to every `retrieve()` from another. This is the lowest-latency option and the right default for in-process pipelines.

**Save / load handoff** works when agents run in different processes, on different machines, or at different times. Agent A finishes its work, calls `context.save(path)`, and Agent B calls `context.load(path)` to pick up exactly where A left off — full memory, full graph, full vector index. This is how you implement shift handoffs, async pipelines, and cross-service orchestration.

**Namespaced memories** works when you have a single `AgentContext` instance serving multiple logical agents, each scoping its reads and writes with a `conversation_id`. Agents are isolated by tag, not by instance — useful for lightweight role separation without the overhead of multiple contexts.

The pipeline in this guide uses all three.

## Pattern 1 — Shared Graph for Concurrent Ingestion

The OSINT collector and the enrichment agent run concurrently. They share a single `ContextGraph` and a single `VectorStore` — the graph's internal `RLock` makes concurrent writes safe.

```python
import threading
from semantica.context import AgentContext, ContextGraph
from semantica.vector_store import VectorStore

# One graph, one vector store — both agents write to these
shared_graph = ContextGraph(advanced_analytics=True)
shared_vs    = VectorStore(backend="faiss", dimension=768)

def make_agent() -> AgentContext:
    """Factory: each agent gets its own AgentContext wrapping the shared backing stores."""
    return AgentContext(
        vector_store=shared_vs,            # same VectorStore instance
        knowledge_graph=shared_graph,      # same ContextGraph instance
        graph_expansion=True,
        max_expansion_hops=2,
        decision_tracking=True,
    )

osint_agent      = make_agent()
enrichment_agent = make_agent()
reasoning_agent  = make_agent()
```

The OSINT collector's job is to ingest raw feeds and extract entities. It does not reason — it just ingests and lets the graph accumulate structure.

```python
def osint_collection():
    """Agent 1: ingest raw threat feeds and CVE data."""
    osint_agent.store(
        [
            {
                "content": "APT29 exploits CVE-2024-3400 in PAN-OS GlobalProtect — unauthenticated RCE, CVSS 10.0",
                "metadata": {"source": "nvd_feed", "cve": "CVE-2024-3400", "actor": "APT29"},
            },
            {
                "content": "Volexity confirms active exploitation of CVE-2024-3400 against NATO member networks",
                "metadata": {"source": "volexity_blog", "actor": "APT29", "target": "NATO"},
            },
            {
                "content": "PAN-OS GlobalProtect affected versions: < 10.2.9-h1, < 11.0.4-h1, < 11.1.2-h3",
                "metadata": {"source": "paloalto_advisory", "cve": "CVE-2024-3400", "product": "GlobalProtect"},
            },
        ],
        extract_entities=True,
        extract_relationships=True,
        conversation_id="osint-pipeline",
    )
```

While the OSINT collector is running, the enrichment agent is independently pulling actor-profile data and linking it into the same graph.

```python
def enrichment():
    """Agent 2: enrich the graph with actor profile and TTP context."""
    enrichment_agent.store(
        [
            {
                "content": "APT29 TTP profile: T1190 (Exploit Public-Facing Application), T1071.001 (Web Protocols C2), T1078 (Valid Accounts)",
                "metadata": {"source": "mitre_attck", "actor": "APT29", "type": "ttp_profile"},
            },
            {
                "content": "APT29 infrastructure fingerprint: use of Cloudflare Workers for C2 relay, certificate reuse across campaigns",
                "metadata": {"source": "recorded_future", "actor": "APT29", "type": "infrastructure"},
            },
        ],
        extract_entities=True,
        extract_relationships=True,
        conversation_id="enrichment-pipeline",
    )
```

Run both concurrently — the graph handles the locking.

```python
t1 = threading.Thread(target=osint_collection)
t2 = threading.Thread(target=enrichment)
t1.start(); t2.start()
t1.join();  t2.join()

# The shared graph now contains entities and relationships from both agents.
# The reasoning agent can query across everything both agents stored.
```

## Pattern 2 — Save / Load Handoff to a Reasoning Agent

The reasoning agent runs after ingestion completes. In a production pipeline this might be a separate process, a different container, or a scheduled job. The ingestion agents save their shared state; the reasoning agent loads it.

```python
# After ingestion: save the combined graph and vector index
osint_agent.save("./pipeline/enriched_intel/")
# Writes:
#   pipeline/enriched_intel/agent_memory.json     — all MemoryItems
#   pipeline/enriched_intel/vector_store/         — FAISS index
#   pipeline/enriched_intel/knowledge_graph.json  — all nodes and edges

print("Ingestion complete. State saved for reasoning agent.")
```

The reasoning agent starts fresh, loads the state, and has full access to everything the ingestion agents built.

```python
from semantica.context import AgentContext, ContextGraph
from semantica.vector_store import VectorStore
from semantica.llms import LiteLLM

# Create a fresh context before loading — load() merges into the existing context
reasoning_vs    = VectorStore(backend="faiss", dimension=768)
reasoning_graph = ContextGraph(advanced_analytics=True)
reasoning_agent = AgentContext(
    vector_store=reasoning_vs,
    knowledge_graph=reasoning_graph,
    graph_expansion=True,
    max_expansion_hops=3,
    decision_tracking=True,
)

reasoning_agent.load("./pipeline/enriched_intel/")
# All memories, graph nodes, and vector embeddings from both ingestion agents are now available.

# Use a high-capability model for the synthesis step
llm = LiteLLM(model="anthropic/claude-sonnet-4-20250514")

synthesis = reasoning_agent.query_with_reasoning(
    "Summarize the APT29 exploitation of CVE-2024-3400: affected products, "
    "observed TTPs, targeted sectors, and recommended mitigations.",
    llm_provider=llm,
    max_results=15,
    max_hops=3,
)

print(synthesis["response"])
print("Confidence: {:.0%}".format(synthesis["confidence"]))

# Store the synthesis back into the graph — the reporting agent will retrieve it
reasoning_agent.store(
    "SYNTHESIS: " + synthesis["response"],
    metadata={"type": "synthesis", "agent": "reasoning", "confidence": synthesis["confidence"]},
    conversation_id="synthesis-output",
)

# Record the analytical judgment as a traceable decision
reasoning_agent.record_decision(
    category="threat_assessment",
    scenario="APT29 active exploitation of CVE-2024-3400 in PAN-OS",
    reasoning=synthesis["reasoning_path"],
    outcome="high_priority_patch_advisory",
    confidence=synthesis["confidence"],
    entities=["APT29", "CVE-2024-3400", "GlobalProtect", "NATO"],
    decision_maker="reasoning_agent_v2",
)

# Hand off to the reporting agent
reasoning_agent.save("./pipeline/synthesis_output/")
```

<Info>
  `load()` merges into the existing context — it does not wipe it first. Always create a fresh `AgentContext` before calling `load()` if you want a clean restore from a handoff checkpoint.
</Info>

## Pattern 3 — Namespaced Memories for Role Separation

The reporting agent does not need its own graph instance. It shares the reasoning agent's context but scopes its writes to its own namespace — the `conversation_id` acts as an agent identifier.

```python
# The reporting agent loads the synthesis output
reporting_vs    = VectorStore(backend="faiss", dimension=768)
reporting_graph = ContextGraph()
reporting_agent = AgentContext(
    vector_store=reporting_vs,
    knowledge_graph=reporting_graph,
    graph_expansion=True,
)
reporting_agent.load("./pipeline/synthesis_output/")

# Retrieve everything the reasoning agent produced
synthesis_items = reporting_agent.retrieve(
    "APT29 CVE-2024-3400 threat assessment synthesis",
    max_results=10,
    conversation_id="synthesis-output",   # scoped to reasoning agent's output
)

# Build the finished brief
brief_sections = []
for item in synthesis_items:
    brief_sections.append(item["content"])

# Store the final report under the reporting agent's own namespace
reporting_agent.store(
    "\n\n".join(brief_sections),
    metadata={"type": "finished_report", "classification": "TLP:GREEN"},
    conversation_id="reporting-output",    # reporting agent's namespace
    user_id="reporting_agent",
)

# The full pipeline audit trail: retrieve across all namespaces
full_trail = reporting_agent.retrieve("APT29 CVE-2024-3400", max_results=25)
print("Pipeline produced {} traceable context items".format(len(full_trail)))
```

Each agent's contributions are retrievable individually by filtering on `conversation_id`, or collectively by querying without a filter.

## Domain Examples

<Tabs>
<Tab title="Defense — CTI/Threat">
A three-agent intelligence fusion cell: an OSINT collector ingests public feeds, a HUMINT analyst loads classified summaries, and a fusion officer synthesizes both streams into a Priority Intelligence Requirement answer. The OSINT and HUMINT agents run concurrently on a shared graph; the fusion officer loads the combined state in a separate process on an air-gapped network segment.

```python
import threading
from semantica.context import AgentContext, ContextGraph
from semantica.vector_store import VectorStore
from semantica.llms import HuggingFaceLLM

# Shared graph for concurrent multi-INT collection
shared_graph = ContextGraph(advanced_analytics=True)
shared_vs    = VectorStore(backend="faiss", dimension=768)

osint_agent  = AgentContext(vector_store=shared_vs, knowledge_graph=shared_graph, graph_expansion=True)
humint_agent = AgentContext(vector_store=shared_vs, knowledge_graph=shared_graph, graph_expansion=True)

def osint_collection():
    osint_agent.store(
        [
            {"content": "CVE-2024-3400 confirmed exploited by APT29 against NATO member VPN gateways",
             "metadata": {"source": "NVD", "classification": "UNCLASSIFIED", "actor": "APT29"}},
            {"content": "Palo Alto PSIRT: GlobalProtect OS command injection via crafted SESSID cookie",
             "metadata": {"source": "PAN-SA-2024-0006", "classification": "UNCLASSIFIED"}},
        ],
        extract_entities=True,
        extract_relationships=True,
        conversation_id="osint-collector",
    )

def humint_analysis():
    # In a cleared environment, HUMINT docs come from a local classified store
    humint_agent.store(
        [
            {"content": "[S//NF] APT29 operator tradecraft: deploy WARPWIRE credential harvester post-exploitation of perimeter VPNs",
             "metadata": {"source": "HUMINT_Q4_2024", "classification": "SECRET//NOFORN", "actor": "APT29"}},
            {"content": "[S//NF] Target selection pattern: APT29 prioritizes Foreign Ministry and Defense Attache networks within NATO",
             "metadata": {"source": "HUMINT_Q4_2024", "classification": "SECRET//NOFORN", "actor": "APT29"}},
        ],
        extract_entities=True,
        extract_relationships=True,
        conversation_id="humint-analyst",
    )

# Concurrent multi-INT collection — graph handles thread safety
t1 = threading.Thread(target=osint_collection)
t2 = threading.Thread(target=humint_analysis)
t1.start(); t2.start()
t1.join();  t2.join()

# Save combined intelligence base for the air-gapped fusion officer
osint_agent.save("./fusion/combined_intel/")

# --- Fusion Officer (air-gapped segment, separate process) ---
fusion_vs    = VectorStore(backend="faiss", dimension=768)
fusion_graph = ContextGraph(advanced_analytics=True)
fusion_officer = AgentContext(
    vector_store=fusion_vs,
    knowledge_graph=fusion_graph,
    graph_expansion=True,
    decision_tracking=True,
)
fusion_officer.load("./fusion/combined_intel/")

# Air-gapped inference: local model on NFS share
llm = HuggingFaceLLM(model="/opt/models/llama-3.1-70b-instruct")

pir_answer = fusion_officer.query_with_reasoning(
    "PIR: What is APT29's current exploitation methodology against NATO perimeter VPNs "
    "and what post-exploitation capabilities have they deployed in Q4 2024?",
    llm_provider=llm,
    max_results=20,
    max_hops=3,
)
print(pir_answer["response"])
fusion_officer.save("./fusion/pir_report/")
```

</Tab>

<Tab title="Security — SOC/Incident">
A three-tier SOC pipeline: Tier 1 triages the alert with a fast Groq model, Tier 2 escalates with a deep Claude analysis if Tier 1 confidence is low, and a manager agent reads the full incident thread across all tiers. All three tiers share one `ContextGraph` — each tier namespaces its findings with a tier-scoped `conversation_id`.

```python
from semantica.context import AgentContext, ContextGraph
from semantica.vector_store import VectorStore
from semantica.llms import Groq, LiteLLM

shared_graph = ContextGraph()
shared_vs    = VectorStore(backend="faiss", dimension=768)

def make_soc_agent() -> AgentContext:
    return AgentContext(
        vector_store=shared_vs,
        knowledge_graph=shared_graph,
        graph_expansion=True,
        decision_tracking=True,
    )

tier1   = make_soc_agent()
tier2   = make_soc_agent()
manager = make_soc_agent()

incident_id = "INC-2025-110342"

# --- Tier 1: fast triage with Groq (target < 500ms) ---
fast_llm = Groq(model="llama-3.1-8b-instant", api_key="YOUR_GROQ_KEY")

alert = (
    "Host: ws-finance-03  User: jsmith  Event: Scheduled task — base64-encoded PowerShell\n"
    "Sigma: T1053.005  Parent: wmiprvse.exe  Time: 2025-06-21T09:14:32Z"
)
tier1.store(alert, metadata={"tier": 1, "incident": incident_id})

triage = tier1.query_with_reasoning(
    "Is this a true positive? One-line verdict.",
    llm_provider=fast_llm,
    max_results=5,
)
tier1.store(
    "TIER1 VERDICT: " + triage["response"],
    metadata={"tier": 1, "incident": incident_id, "confidence": triage["confidence"]},
    conversation_id="{}-tier1".format(incident_id),
)

# --- Tier 2: deep investigation when Tier 1 confidence is low ---
if triage["confidence"] < 0.90:
    deep_llm = LiteLLM(model="anthropic/claude-sonnet-4-20250514")

    investigation = tier2.query_with_reasoning(
        "Full MITRE ATT&CK analysis of incident {}. "
        "Identify attack chain, affected systems, blast radius, and recommended containment.".format(incident_id),
        llm_provider=deep_llm,
        max_results=15,
        max_hops=3,
    )
    tier2.store(
        "TIER2 ANALYSIS: " + investigation["response"],
        metadata={"tier": 2, "incident": incident_id},
        conversation_id="{}-tier2".format(incident_id),
    )
    tier2.record_decision(
        category="escalation",
        scenario="Escalate {} — Tier 1 confidence {:.0%}".format(incident_id, triage["confidence"]),
        reasoning=investigation["reasoning_path"],
        outcome="escalated_to_tier3",
        confidence=investigation["confidence"],
        entities=["ws-finance-03", "jsmith", "wmiprvse.exe"],
        decision_maker="tier2_analyst",
    )

# --- Manager: read the full incident thread across all tiers ---
full_thread = manager.retrieve(
    "incident {}".format(incident_id),
    use_graph=True,
    max_results=25,
)
print("Full incident thread ({} items):".format(len(full_thread)))
for item in full_thread:
    tier = item.get("metadata", {}).get("tier", "?")
    print("  [Tier {}] {}".format(tier, item["content"][:100]))

# Per-tier history for post-incident review
t1_history = manager.conversation("{}-tier1".format(incident_id))
t2_history = manager.conversation("{}-tier2".format(incident_id))
```

</Tab>

<Tab title="Life Science — Clinical/Pharma">
A three-agent drug discovery pipeline: a literature agent ingests PubMed papers, an experimental agent loads validated assay results, and a chief agent synthesizes both to identify lead compounds. The literature and experimental agents run in parallel on a shared graph; the chief agent queries across both after ingestion completes.

```python
import threading
from semantica.context import AgentContext, ContextGraph
from semantica.vector_store import VectorStore
from semantica.llms import LiteLLM

shared_graph = ContextGraph(advanced_analytics=True)
shared_vs    = VectorStore(backend="faiss", dimension=768)

def make_agent() -> AgentContext:
    return AgentContext(
        vector_store=shared_vs,
        knowledge_graph=shared_graph,
        graph_expansion=True,
        max_expansion_hops=3,
        retention_days=None,      # unlimited retention for research data
    )

lit_agent = make_agent()
exp_agent = make_agent()
chief     = make_agent()

def literature_review():
    # Ingest PubMed abstracts for KRAS G12C inhibitors
    lit_agent.store(
        [
            {"content": "Sotorasib (AMG-510) achieves 37.1% ORR in KRAS G12C NSCLC (CodeBreaK 100, NEJM 2021)",
             "metadata": {"source": "CodeBreaK100", "target": "KRAS_G12C", "compound": "sotorasib"}},
            {"content": "Adagrasib (MRTX849) ORR 42.9% in KRAS G12C NSCLC with CNS activity (KRYSTAL-1, NEJM 2022)",
             "metadata": {"source": "KRYSTAL-1", "target": "KRAS_G12C", "compound": "adagrasib"}},
            {"content": "Resistance to KRAS G12C inhibitors frequently driven by Y96D mutation in switch-II pocket",
             "metadata": {"source": "Tanaka_CancerCell_2021", "target": "KRAS_G12C", "mechanism": "resistance"}},
        ],
        extract_entities=True,
        extract_relationships=True,
        conversation_id="literature-agent",
    )

def experimental_results():
    # Load validated in-vitro and in-vivo assay data
    exp_agent.store(
        [
            {"content": "Compound RMC-6291: IC50=0.6nM KRAS G12C, selectivity index 480, in-vivo efficacy 82%, toxicity grade 1",
             "metadata": {"source": "internal_assay", "compound": "RMC-6291", "source_type": "experimental"}},
            {"content": "Compound BI-7273: IC50=1.4nM KRAS G12C, selectivity index 310, in-vivo efficacy 71%, toxicity grade 2",
             "metadata": {"source": "internal_assay", "compound": "BI-7273", "source_type": "experimental"}},
            {"content": "Compound GDC-6036: IC50=0.9nM KRAS G12C, active against Y96D resistance mutation, toxicity grade 1",
             "metadata": {"source": "internal_assay", "compound": "GDC-6036", "source_type": "experimental"}},
        ],
        extract_entities=True,
        conversation_id="experimental-agent",
    )

# Parallel ingestion — graph handles concurrency
t1 = threading.Thread(target=literature_review)
t2 = threading.Thread(target=experimental_results)
t1.start(); t2.start()
t1.join();  t2.join()

# Chief agent synthesizes across literature and experimental data
llm = LiteLLM(model="anthropic/claude-sonnet-4-20250514")

synthesis = chief.query_with_reasoning(
    "Identify the top two candidate compounds for KRAS G12C NSCLC that show "
    "both strong experimental IC50 selectivity and clinical/literature support "
    "for the target pathway, including any coverage of resistance mechanisms.",
    llm_provider=llm,
    max_results=20,
    max_hops=3,
)
print(synthesis["response"])
chief.save("./drug_discovery/kras_g12c_checkpoint/")
```

</Tab>

<Tab title="Banking — Risk/Compliance">
A four-agent credit committee: a risk desk agent computes PD/LGD, a compliance desk agent checks Basel III and EBA requirements, a credit officer agent applies policy, and a committee chair agent reads across all three desks to produce the final decision with a complete audit trail. Each desk namespaces its findings; the chair reads across all namespaces.

```python
from semantica.context import AgentContext, ContextGraph
from semantica.vector_store import VectorStore
from semantica.llms import LiteLLM

shared_graph = ContextGraph(advanced_analytics=True)
shared_vs    = VectorStore(backend="faiss", dimension=768)

def make_desk_agent() -> AgentContext:
    return AgentContext(
        vector_store=shared_vs,
        knowledge_graph=shared_graph,
        graph_expansion=True,
        decision_tracking=True,
        retention_days=2555,    # 7-year Basel III retention
        kg_algorithms=True,
    )

risk_desk       = make_desk_agent()
compliance_desk = make_desk_agent()
credit_officer  = make_desk_agent()
committee_chair = make_desk_agent()

app_id = "LOAN-2025-88421"
llm    = LiteLLM(model="anthropic/claude-sonnet-4-20250514")

# --- Risk Desk: PD/LGD/EL analysis ---
risk_desk.store(
    "Risk analysis {}: PD=2.3%, LGD=45%, EL=89k GBP, DSCR=1.12, LTV=78%. "
    "Stress test +300bps: DSCR falls to 0.98 — marginal but within policy floor of 0.95.".format(app_id),
    metadata={"desk": "risk", "application": app_id},
    conversation_id="{}-risk".format(app_id),
)
risk_desk.record_decision(
    category="credit_risk",
    scenario="Risk assessment {}".format(app_id),
    reasoning="PD 2.3% within 3% internal threshold; LTV 78% marginal — LMI required; stress test passes",
    outcome="conditional_approval_lmi_required",
    confidence=0.78,
    entities=[app_id, "LTV_78pct", "PD_2pct"],
    decision_maker="risk_model_v6",
)

# --- Compliance Desk: Basel III / EBA GL 2020/06 check ---
compliance_desk.store(
    [
        {"content": "Basel III CRR2 Art. 92: total capital ratio minimum 8% + 2.5% conservation buffer",
         "metadata": {"source": "CRR2_Art92", "category": "capital_requirement"}},
        {"content": "EBA GL 2020/06: DSTI > 40% requires enhanced creditworthiness assessment and senior credit officer sign-off",
         "metadata": {"source": "EBA_GL_2020_06", "category": "affordability"}},
        {"content": "CRE20: LTV > 80% for residential mortgages requires LMI or equivalent credit enhancement",
         "metadata": {"source": "Basel_CRE20", "category": "collateral"}},
    ],
    extract_entities=True,
    extract_relationships=True,
)

compliance_check = compliance_desk.query_with_reasoning(
    "Does application {} (residential mortgage, LTV 78%, DSTI 35%) satisfy "
    "Basel III CRE20, EBA GL 2020/06 affordability requirements, and CRR2 Art. 92?".format(app_id),
    llm_provider=llm,
    max_results=10,
)
compliance_desk.store(
    "COMPLIANCE FINDING: " + compliance_check["response"],
    metadata={"desk": "compliance", "application": app_id, "confidence": compliance_check["confidence"]},
    conversation_id="{}-compliance".format(app_id),
)

# --- Committee Chair: cross-desk synthesis and final decision ---
committee_decision = committee_chair.query_with_reasoning(
    "Summarize all desk findings for application {} and produce the final "
    "credit committee decision with all conditions stated explicitly.".format(app_id),
    llm_provider=llm,
    max_results=25,
    max_hops=3,
)
print(committee_decision["response"])

# Record the final decision — this is what the regulator sees
committee_chair.record_decision(
    category="credit_committee",
    scenario="Final committee decision {}".format(app_id),
    reasoning=committee_decision["reasoning_path"],
    outcome="approved_with_conditions_lmi",
    confidence=committee_decision["confidence"],
    entities=[app_id, "LTV_78pct", "DSTI_35pct"],
    decision_maker="credit_committee_2025",
)

# Per-desk audit retrieval
risk_thread       = committee_chair.conversation("{}-risk".format(app_id))
compliance_thread = committee_chair.conversation("{}-compliance".format(app_id))

committee_chair.save("./credit_files/{}/context/".format(app_id))
```

</Tab>
</Tabs>

## Memory Isolation Reference

When multiple agents write to a shared context, use `conversation_id` to isolate their streams and retrieve them individually.

```python
# Tag a memory to an agent's namespace
context.store("Finding: lateral movement confirmed", conversation_id="tier2-ir")

# Retrieve only that agent's memories
tier2_history = context.retrieve("lateral movement", conversation_id="tier2-ir")

# Get the full ordered history for a namespace
full_history = context.conversation("tier2-ir", max_items=100)

# Delete an agent's entire namespace
context.forget(conversation_id="tier2-ir")
```

The same pattern works for user-scoped isolation — replace `conversation_id` with `user_id`:

```python
context.store("...", user_id="analyst-jsmith")
context.retrieve("...", user_id="analyst-jsmith")
```

## Related Guides

- [Agent Memory](agent-memory) — memory storage, retrieval, persistence, and the working memory window each agent uses internally
- [Context Graphs](context-graphs) — build and traverse the shared `ContextGraph` directly; temporal interval reasoning; entity deduplication before node insertion
- [Decision Intelligence](decision-intelligence) — record and trace decisions across agent handoffs with causal chain analysis
- [LLM Integrations](llm-integrations) — configure the LLM provider passed to `query_with_reasoning()` in each agent
