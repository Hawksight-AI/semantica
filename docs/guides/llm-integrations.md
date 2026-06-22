---
title: "LLM Integrations"
description: "Connect Semantica to Groq, OpenAI, Anthropic, HuggingFace, Novita AI, and 100+ LLM providers through a unified interface."
---

Semantica exposes a unified provider interface — a single `.generate()` method — across Groq, OpenAI, Anthropic Claude, HuggingFace, Novita AI, and 100+ providers via LiteLLM. Use it when you need to swap providers for latency, accuracy, cost, or data-residency reasons without touching application code.

<Info>
  The providers in `semantica.llms` (`Groq`, `OpenAI`, `LiteLLM`, `HuggingFaceLLM`) are for text generation and `query_with_reasoning()`. For structured entity and relation extraction, `semantica.semantic_extract` accepts provider names as strings. Both patterns are covered here.
</Info>

## Choosing a Provider

Four factors drive provider selection. **Latency** matters most in real-time SOC triage loops where an analyst is waiting on a triage verdict — Groq's inference server typically returns 8B model responses in under 300ms. **Accuracy** matters most in high-stakes decisions: clinical contraindication checks, credit committee reasoning, and legal document analysis reward the frontier models available via `LiteLLM`. **Data residency** constraints eliminate cloud providers for classified or HIPAA-regulated workloads — `HuggingFaceLLM` with a local model path covers those cases. **Cost at scale** favors high-throughput open-model providers like Novita AI for bulk extraction pipelines where you are processing thousands of documents per hour.

The good news: because Semantica's interface is identical across providers, you can prototype with Groq for speed, validate accuracy with Claude, and deploy to Azure OpenAI for compliance — without changing a single line of your application code. Only the provider constructor changes.

## The Shared Interface

Every provider exposes the same two methods:

```python
provider.generate(prompt: str, **kwargs) -> str
provider.generate_structured(prompt: str, **kwargs) -> dict
provider.is_available() -> bool
```

`generate()` returns a plain string. `generate_structured()` instructs the model to respond in JSON and returns a parsed `dict`. `is_available()` lets you health-check the provider before committing to a call — useful in retry logic and warm-up checks.

This means every place in Semantica that accepts an LLM — `query_with_reasoning()`, semantic extraction, custom reasoning loops — accepts any of these providers interchangeably.

## Groq — Fast Inference for Real-Time Agents

Groq Cloud runs open models on purpose-built Language Processing Units that deliver sub-300ms latency for 8B parameter models. This makes Groq the right default for any agent loop where the LLM is in the hot path — SOC triage, real-time alert classification, conversational agents.

```python
from semantica.llms import Groq

# api_key falls back to the GROQ_API_KEY environment variable
groq = Groq(model="llama-3.1-8b-instant", api_key="YOUR_GROQ_KEY")

# Always health-check before the first call in a long-running process
if not groq.is_available():
    raise RuntimeError("Groq provider unreachable — check GROQ_API_KEY")

# Plain generation
verdict = groq.generate(
    "Alert: 4200 LDAP objects enumerated in 8s from ws-finance-03. "
    "True positive or false positive? One sentence.",
    temperature=0.1,    # low temperature for deterministic triage verdicts
)
print(verdict)
# "True positive — volume and speed are consistent with T1087.002 domain enumeration."

# Structured extraction — returns a parsed dict
entities = groq.generate_structured(
    "Extract threat actors and CVEs from: "
    "APT29 exploited CVE-2024-3400 in PAN-OS GlobalProtect."
)
# {"threat_actors": ["APT29"], "cves": ["CVE-2024-3400"], "products": ["PAN-OS GlobalProtect"]}
```

Groq model selection comes down to the speed-vs-capability tradeoff: `llama-3.1-8b-instant` for anything in the hot path, `llama-3.3-70b-versatile` when you need stronger reasoning but can afford slightly higher latency, `mixtral-8x7b-32768` for long-context summarisation tasks.

## OpenAI — Function Calling and Vision

The `OpenAI` provider wraps the OpenAI API. Use it when you need GPT-4o's function-calling precision, vision capabilities for document screenshots, or when your team already has an OpenAI contract and wants to stay there.

```python
from semantica.llms import OpenAI

oai = OpenAI(model="gpt-4o", api_key="YOUR_OAI_KEY")
# api_key falls back to OPENAI_API_KEY environment variable

response = oai.generate(
    "Under CRR2 Article 92, what is the minimum total capital ratio "
    "for a G-SIB subject to a 2% GSIB buffer surcharge?"
)
print(response)

# Structured output — useful for deterministic data extraction
risk_data = oai.generate_structured(
    "Extract all counterparty names and exposure amounts from: "
    "Counterparty A: 45M EUR notional, Counterparty B: 12M EUR notional, "
    "Counterparty C: 89M EUR notional."
)
# {"counterparties": [{"name": "Counterparty A", "exposure_eur": 45000000}, ...]}
```

The default model `gpt-3.5-turbo` is fine for classification and light extraction. Switch to `gpt-4o` for complex multi-step regulatory reasoning or document understanding.

## LiteLLM — One Interface, 100+ Providers

`LiteLLM` is the Swiss Army knife. It wraps the `litellm` library, which speaks to every major provider using a unified completion API. The model string encodes both provider and model name: `"anthropic/claude-sonnet-4-20250514"`, `"azure/gpt-4o"`, `"bedrock/anthropic.claude-3-5-sonnet-20241022-v2:0"`, `"ollama/llama3.2"`. Change the string, change the provider — no other code changes needed.

```python
from semantica.llms import LiteLLM

# Anthropic Claude — highest accuracy for complex reasoning
llm = LiteLLM(model="anthropic/claude-sonnet-4-20250514")
# Reads ANTHROPIC_API_KEY from environment

# Azure OpenAI — compliance and data-residency requirements
llm = LiteLLM(model="azure/gpt-4o", api_key="YOUR_AZURE_KEY")

# AWS Bedrock — existing cloud agreement, no new vendor
llm = LiteLLM(model="bedrock/anthropic.claude-3-5-sonnet-20241022-v2:0")

# Google Vertex AI
llm = LiteLLM(model="vertex_ai/gemini-1.5-pro")

# Ollama — fully local, no network calls
llm = LiteLLM(model="ollama/llama3.2")

# All of them: same call
response = llm.generate("Summarise the ICH E6(R2) GCP guideline key requirements.")
```

The environment-variable convention for each provider: `ANTHROPIC_API_KEY`, `AZURE_API_KEY`, `OPENAI_API_KEY`, `GOOGLE_APPLICATION_CREDENTIALS`, etc. LiteLLM picks them up automatically. For a provider switch driven by deployment environment, you can keep provider selection in a config dict and inject it at startup — no `if/else` branches in application code:

```python
import os

PROVIDER_MAP = {
    "prod":    "anthropic/claude-sonnet-4-20250514",
    "staging": "openai/gpt-4o-mini",
    "local":   "ollama/llama3.2",
    "azure":   "azure/gpt-4o",
}

env = os.getenv("DEPLOY_ENV", "local")
llm = LiteLLM(model=PROVIDER_MAP[env])
# The rest of the application never touches provider names
```

## HuggingFaceLLM — Air-Gapped and On-Premise

`HuggingFaceLLM` loads a model from the HuggingFace Hub or from a local directory path. No network calls during inference. This is the only option for classified environments, HIPAA-constrained clinical deployments, and any network segment without outbound internet access.

```python
from semantica.llms import HuggingFaceLLM

# HuggingFace Hub — authentication via HF_TOKEN environment variable
hf = HuggingFaceLLM(model="mistralai/Mistral-7B-Instruct-v0.3")

# Biomedical fine-tuned model for clinical entity extraction
bio_llm = HuggingFaceLLM(model="aaditya/Llama3-OpenBioLLM-70B")

# Air-gapped deployment — model on local NFS share or mounted volume
# Both `model` and `model_name` are accepted as constructor parameters
air_gapped_llm = HuggingFaceLLM(model="/opt/models/llama-3.1-70b-instruct")

response = air_gapped_llm.generate(
    "Summarise SIGINT collection window 2024-Q3 for APT29 C2 infrastructure.",
    max_length=512,
)
```

Set `HF_TOKEN` in your environment for Hub access to gated or private models. For local paths, no token is needed — the model directory must contain the standard HuggingFace checkpoint files.

## Swapping Providers Without Changing Application Code

The real payoff of the unified interface is in `query_with_reasoning()`. This is the call that drives graph-grounded reasoning in every `AgentContext`. Because it accepts any provider object, you can slot in a different LLM at any tier of your pipeline with zero changes to the surrounding code.

```python
from semantica.context import AgentContext, ContextGraph
from semantica.vector_store import VectorStore
from semantica.llms import Groq, LiteLLM

vs    = VectorStore(backend="faiss", dimension=768)
graph = ContextGraph(advanced_analytics=True)
context = AgentContext(vector_store=vs, knowledge_graph=graph, graph_expansion=True)

# Load your knowledge base once
context.store(
    [
        {"content": "APT29 exploits CVE-2024-3400 in PAN-OS GlobalProtect — CVSS 10.0",
         "metadata": {"source": "nvd", "actor": "APT29"}},
        {"content": "NOBELIUM (APT29) leverages OAuth token theft against Azure AD tenants",
         "metadata": {"source": "msft_blog_2023", "actor": "APT29", "technique": "T1528"}},
    ],
    extract_entities=True,
    extract_relationships=True,
)

query = "What is APT29's current exploitation methodology and what cloud services are targeted?"

# Tier 1: fast answer with Groq (< 300ms)
fast_llm = Groq(model="llama-3.1-8b-instant", api_key="YOUR_GROQ_KEY")
fast_result = context.query_with_reasoning(query, llm_provider=fast_llm, max_results=5)
print("FAST: {}  (conf={:.0%})".format(fast_result["response"], fast_result["confidence"]))

# Tier 2: deep answer with Claude if confidence is below threshold
if fast_result["confidence"] < 0.85:
    deep_llm = LiteLLM(model="anthropic/claude-sonnet-4-20250514")
    deep_result = context.query_with_reasoning(
        query, llm_provider=deep_llm, max_results=15, max_hops=3
    )
    print("DEEP: {}  (conf={:.0%})".format(deep_result["response"], deep_result["confidence"]))
```

The `context`, the graph, the retrieval logic — none of it changes. Only the `llm_provider` argument differs between the two tiers.

## Using Providers for Semantic Extraction

For NER, relation extraction, and triplet extraction, Semantica's `semantica.semantic_extract` module accepts provider names as strings rather than class instances. The module handles provider instantiation internally.

```python
from semantica.semantic_extract import NamedEntityRecognizer, EventDetector
from semantica.semantic_extract.methods import (
    extract_entities_llm,
    extract_relations_llm,
    extract_triplets_llm,
)

# NER with Groq — provider name as a string
ner = NamedEntityRecognizer(
    methods=["llm"],
    provider="groq",
    llm_model="llama-3.1-8b-instant",
)
entities = ner.extract_entities(
    "APT29 exploited CVE-2024-3400 in PAN-OS GlobalProtect to compromise NATO member networks."
)
for e in entities:
    # Entity fields: .text, .label, .confidence
    print("{} ({}) — conf={:.2f}".format(e.text, e.label, e.confidence))
# APT29 (THREAT_ACTOR) — conf=0.96
# CVE-2024-3400 (CVE) — conf=0.99
# PAN-OS GlobalProtect (PRODUCT) — conf=0.94
# NATO (ORGANIZATION) — conf=0.91

# Event detection with the same provider pattern
detector = EventDetector(method="llm", provider="groq")
events = detector.detect_events(
    "ENISA published the Threat Landscape 2024 report on October 22nd, "
    "covering 11 primary threat categories including ransomware and supply-chain attacks."
)

# Triplet extraction — returns (subject, predicate, object) triples
text = "Warfarin inhibits VKORC1 enzyme activity, reducing vitamin K-dependent clotting factor synthesis."
triplets = extract_triplets_llm(text, provider="groq", model="llama-3.1-8b-instant")
for t in triplets:
    print("{} -> {} -> {}".format(t.subject, t.predicate, t.object))
# warfarin -> inhibits -> VKORC1 enzyme activity
# warfarin -> reduces -> vitamin K-dependent clotting factor synthesis
```

## Novita AI — Cost-Efficient Bulk Extraction

Novita AI exposes an OpenAI-compatible API and is available as a built-in provider for the extraction layer. It is accessed differently from the `semantica.llms` classes — through `create_provider` from `semantica.semantic_extract.providers` — making it the right choice for high-volume NER pipelines where per-call cost matters.

```python
from semantica.semantic_extract.providers import create_provider
from semantica.semantic_extract import NamedEntityRecognizer

# create_provider pools instances — same key reuses the same object
provider = create_provider(
    "novita",
    api_key="YOUR_NOVITA_KEY",       # or set NOVITA_API_KEY env var
    model="deepseek/deepseek-v3.2",  # default model
)

if provider.is_available():
    # Plain generation
    response = provider.generate("Summarise the Basel III leverage ratio requirement.")

    # Structured extraction — returns parsed dict
    data = provider.generate_structured(
        "Extract drug names and dosages from: "
        "Patient received warfarin 5mg daily, aspirin 75mg daily, metformin 500mg twice daily."
    )

# Use Novita through the NER interface — provider name as string
ner = NamedEntityRecognizer(
    methods=["llm"],
    provider="novita",
    llm_model="deepseek/deepseek-v3.2",
)
entities = ner.extract_entities(
    "CVE-2024-3400 is exploited by UNC3886 targeting PAN-OS GlobalProtect."
)
for e in entities:
    print("{} ({}) — conf={:.2f}".format(e.text, e.label, e.confidence))
```

Novita requires the `openai` Python client under the hood — install with `pip install "semantica[llm-openai]"` or `pip install openai`.

## Domain Examples

<Tabs>
<Tab title="Defense — CTI/Threat">
A classified threat-intelligence analysis unit needs to run entirely air-gapped — no outbound network traffic of any kind. The extraction model and the reasoning model both load from a local NFS share. The knowledge graph accumulates over the analysis session; all inference happens on-premise.

```python
from semantica.llms import HuggingFaceLLM
from semantica.semantic_extract import NamedEntityRecognizer
from semantica.context import AgentContext, ContextGraph
from semantica.vector_store import VectorStore

# Both models load from the air-gapped NFS share — no Hub calls
extraction_llm = HuggingFaceLLM(model="/opt/models/mistral-7b-instruct")
reasoning_llm  = HuggingFaceLLM(model="/opt/models/llama-3.1-70b-instruct")

# NER with local model — provider pattern still works for local paths
# (use extract_entities_llm directly with the provider instance)
from semantica.semantic_extract.methods import extract_entities_llm

sigint_text = (
    "[S//NF] APT29 operator observed deploying WARPWIRE credential harvester "
    "via CVE-2024-3400 on perimeter VPN gateways of target BRAVO-7."
)

# For fully local models, call the provider's generate method directly
raw_entities = extraction_llm.generate(
    "Extract all threat actors, CVEs, malware names, and target identifiers "
    "from the following text as a JSON list:\n\n" + sigint_text
)

# Build the graph and run reasoning
vs    = VectorStore(backend="faiss", dimension=768)
graph = ContextGraph(advanced_analytics=True)
context = AgentContext(
    vector_store=vs,
    knowledge_graph=graph,
    graph_expansion=True,
    decision_tracking=True,
)

context.store(
    sigint_text,
    metadata={"source": "SIGINT_Q4_2024", "classification": "SECRET//NOFORN"},
    conversation_id="op-analysis-q4",
)

result = context.query_with_reasoning(
    "What credential-harvesting capabilities has APT29 deployed against "
    "perimeter VPN gateways and what CVEs enable initial access?",
    llm_provider=reasoning_llm,   # fully local — no network calls
    max_results=10,
    max_hops=3,
)
print(result["response"])
print("Confidence: {:.0%}".format(result["confidence"]))

context.save("./classified_output/q4_analysis/")
```

</Tab>

<Tab title="Security — SOC/Incident">
A SOC pipeline uses two providers at different tiers: Groq for sub-500ms initial triage that keeps the analyst in flow, and Anthropic Claude for deep ATT&CK analysis when Tier 1 confidence falls below the escalation threshold. The provider switch is determined programmatically — no manual handoff required.

```python
from semantica.llms import Groq, LiteLLM
from semantica.context import AgentContext, ContextGraph
from semantica.vector_store import VectorStore

vs    = VectorStore(backend="faiss", dimension=768)
graph = ContextGraph()
context = AgentContext(
    vector_store=vs,
    knowledge_graph=graph,
    graph_expansion=True,
    decision_tracking=True,
)

# Preload MITRE ATT&CK runbook knowledge
context.store([
    "T1087.002 (Domain Account Discovery): anomalous LDAP enumeration — isolate source host, reset service account passwords",
    "T1053.005 (Scheduled Task/Job): encoded PowerShell via wmiprvse.exe — collect task XML, check persistence keys, notify IR",
    "T1021.002 (SMB/Windows Admin Shares): PsExec lateral movement to DC — immediate host isolation, reset service accounts",
])

alert = (
    "SIEM Alert: host ws-finance-03, user jsmith — scheduled task with base64-encoded PowerShell. "
    "Parent process: wmiprvse.exe. Sigma: T1053.005. Time: 2025-06-21T09:14:32Z."
)
context.store(alert, metadata={"type": "alert", "severity": "high"})

# Tier 1: fast triage with Groq — target < 500ms end-to-end
fast_llm = Groq(model="llama-3.1-8b-instant", api_key="YOUR_GROQ_KEY")
triage = context.query_with_reasoning(
    "Is this alert a true positive? One sentence verdict and confidence.",
    llm_provider=fast_llm,
    max_results=5,
)
print("TRIAGE: {} (conf={:.0%})".format(triage["response"], triage["confidence"]))

# Tier 2: escalate to Claude for deep analysis if Tier 1 is uncertain
if triage["confidence"] < 0.88:
    deep_llm = LiteLLM(model="anthropic/claude-sonnet-4-20250514")
    deep = context.query_with_reasoning(
        "Full MITRE ATT&CK analysis of this alert: identify the attack chain, "
        "blast radius, affected systems, and recommended containment steps.",
        llm_provider=deep_llm,
        max_results=15,
        max_hops=3,
    )
    print("DEEP ANALYSIS: {}".format(deep["response"]))

    context.record_decision(
        category="escalation",
        scenario="Scheduled task T1053.005 on ws-finance-03 — Tier 1 conf {:.0%}".format(triage["confidence"]),
        reasoning=deep["reasoning_path"],
        outcome="escalated_tier2",
        confidence=deep["confidence"],
        entities=["ws-finance-03", "jsmith", "T1053.005"],
        decision_maker="soc_pipeline_v3",
    )
```

</Tab>

<Tab title="Life Science — Clinical/Pharma">
A clinical NLP pipeline uses a domain-specific biomedical NER model from HuggingFace for entity extraction, then switches to Anthropic Claude for structured oncology report synthesis. The same `LiteLLM` wrapper handles the Claude call — switching to Azure OpenAI for HIPAA compliance is a one-line change.

```python
from semantica.llms import LiteLLM
from semantica.semantic_extract import NamedEntityRecognizer

# Biomedical NER — HuggingFace extractor for clinical entities
# (Note: HuggingFace NER uses method="huggingface", not the LLM generation interface)
ner = NamedEntityRecognizer(
    methods=["huggingface"],
    huggingface_model="d4data/biomedical-ner-all",
    confidence_threshold=0.75,
)

clinical_note = (
    "Patient presents with HER2+ breast cancer (T2N1M0, Stage IIB). "
    "Recommended: trastuzumab 8mg/kg loading then 6mg/kg q3w + pertuzumab 840mg loading "
    "then 420mg q3w + docetaxel 75mg/m2 q3w (THP regimen) for 6 cycles. "
    "eGFR 78 mL/min/1.73m2, LVEF 62%. Monitor for cardiotoxicity."
)

entities = ner.extract_entities(clinical_note)
# Entity fields: .text, .label (not .type), .confidence
drugs     = [e for e in entities if e.label == "DRUG"]
diagnoses = [e for e in entities if e.label in ("DISEASE", "CANCER")]

print("Drugs identified:")
for d in drugs:
    print("  {} (conf={:.2f})".format(d.text, d.confidence))
# trastuzumab (conf=0.98), pertuzumab (conf=0.97), docetaxel (conf=0.96)

# Report synthesis with Claude — switch to azure/gpt-4o for HIPAA by changing one string
report_llm = LiteLLM(model="anthropic/claude-sonnet-4-20250514")
# For HIPAA-constrained Azure deployment:
# report_llm = LiteLLM(model="azure/gpt-4o", api_key="YOUR_AZURE_KEY")

oncology_summary = report_llm.generate(
    "Write a structured oncology treatment summary for the following note. "
    "Include: diagnosis, staging, treatment regimen, monitoring parameters, "
    "and key safety considerations.\n\n" + clinical_note
)
print(oncology_summary)
```

</Tab>

<Tab title="Banking — Risk/Compliance">
A regulatory Q&A system runs the same Basel III question through two providers and picks the answer with higher confidence — a simple consensus pattern for high-stakes regulatory interpretation where a wrong answer carries legal risk.

```python
from semantica.llms import OpenAI, LiteLLM
from semantica.context import AgentContext, ContextGraph
from semantica.vector_store import VectorStore

vs    = VectorStore(backend="faiss", dimension=768)
graph = ContextGraph(advanced_analytics=True)
context = AgentContext(
    vector_store=vs,
    knowledge_graph=graph,
    graph_expansion=True,
    retention_days=2555,
)

# Load Basel III / CRR2 regulatory corpus
context.store(
    [
        {"content": "CRR2 Art. 92: minimum total capital ratio 8% + 2.5% conservation buffer + GSIB surcharge",
         "metadata": {"source": "CRR2_Art92", "category": "capital_requirement"}},
        {"content": "Basel III leverage ratio: Tier 1 capital / total exposure >= 3% (Art. 429 CRR2)",
         "metadata": {"source": "CRR2_Art429", "category": "leverage"}},
        {"content": "GSIB buffer surcharges: bucket 1=1%, bucket 2=1.5%, bucket 3=2%, bucket 4=2.5%, bucket 5=3.5%",
         "metadata": {"source": "BCBS_GSIB_2022", "category": "gsib_buffer"}},
    ],
    extract_entities=True,
    extract_relationships=True,
)

question = (
    "Under CRR2 Article 92 and the BCBS GSIB framework, what is the minimum "
    "total capital ratio for a bucket-2 G-SIB? Show the component breakdown."
)

# Two-provider consensus — same query, same graph, different LLMs
gpt4o  = OpenAI(model="gpt-4o", api_key="YOUR_OAI_KEY")
claude = LiteLLM(model="anthropic/claude-sonnet-4-20250514")

answer_a = context.query_with_reasoning(question, llm_provider=gpt4o,  max_results=10)
answer_b = context.query_with_reasoning(question, llm_provider=claude, max_results=10)

# Pick higher-confidence answer for the audit trail
best = answer_a if answer_a["confidence"] >= answer_b["confidence"] else answer_b
winner = "GPT-4o" if best is answer_a else "Claude"

print("Selected: {} (conf={:.0%})".format(winner, best["confidence"]))
print(best["response"])
# Expected: 8% (minimum) + 2.5% (conservation) + 1.5% (bucket-2 GSIB) = 12.0% total

# Sources the answer is grounded in
for src in best["sources"]:
    print("  - [{}] {}".format(src.get("metadata", {}).get("source", "?"), src["content"][:60]))
```

</Tab>
</Tabs>

## Related Guides

- [Agent Memory](agent-memory) — using `query_with_reasoning()` with any LLM provider for graph-grounded retrieval
- [Multi-Agent Systems](multi-agent) — wiring different LLM providers to different agent tiers in a shared-graph pipeline
- [Semantic Extraction](semantic-extraction) — LLM-powered NER, relation extraction, event detection, and triplet extraction
- [GraphRAG](graphrag) — multi-hop graph reasoning with `query_with_reasoning()`
