---
title: "LLM Integrations"
description: "Connect Semantica to Groq, OpenAI, Anthropic, HuggingFace, Novita AI, and 100+ LLM providers through a unified interface."
---

Semantica exposes a unified provider interface — a single `.generate()` method — across Groq, OpenAI, Anthropic Claude, HuggingFace, Novita AI, and 100+ providers via LiteLLM. Use it when you need to swap providers for latency, accuracy, cost, or data-residency reasons without touching application code.

## What Are LLM Integrations?

The `semantica.llms` module provides a unified interface for connecting to Large Language Model providers. Instead of learning different APIs for each provider, you use the same methods (`.generate()`, `.generate_structured()`) regardless of whether you're calling Groq, OpenAI, Anthropic, or local HuggingFace models.

**Unified interface across providers:** All LLM providers in Semantica expose identical methods, so switching from OpenAI to Anthropic requires changing only the provider constructor, not your application code.

**Provider wrappers vs semantic extraction provider strings:** The `semantica.llms` classes (`Groq`, `OpenAI`, `LiteLLM`, `HuggingFaceLLM`) are Python objects for text generation. The `semantica.semantic_extract` module accepts provider names as strings for entity and relationship extraction. Both approaches are covered in this guide.

## Why Use LLM Integrations?

**Provider portability.** Test with one provider, deploy with another. Switch from Groq for prototyping to Anthropic for production without code changes.

**Reduced vendor lock-in.** Avoid tying your application to a single LLM provider's API. If pricing changes or service availability issues arise, switching providers is straightforward.

**Consistent APIs.** Use the same `.generate()` and `.generate_structured()` methods across all providers instead of learning provider-specific interfaces.

**Multi-provider workflows.** Run fast models for initial classification and expensive frontier models for complex reasoning in the same pipeline.

**Local vs cloud deployment flexibility.** Use cloud providers during development and switch to local HuggingFace models for air-gapped production environments.

## When To Use / When Not To Use

**Use LLM integrations for:**

- Text generation, summarization, and question-answering tasks
- Complex reasoning that requires natural language understanding
- Structured data extraction from unstructured text
- Multi-step analysis requiring interpretation and synthesis
- Tasks where context, ambiguity, or domain knowledge matter

**Deterministic tools may be better for:**

- Pattern matching that regular expressions can handle
- Simple rule-based classification with clear criteria
- Mathematical calculations or statistical analysis
- Graph traversal and relationship queries
- Data transformations with known logic

**A full LLM may be unnecessary for:**

- Simple keyword search or exact string matching
- Deterministic workflows with predefined decision trees
- High-frequency, low-latency operations where inference overhead matters
- Tasks where explainability requires transparent rule-based logic

<Info>
  The providers in `semantica.llms` (`Groq`, `OpenAI`, `LiteLLM`, `HuggingFaceLLM`) are for text generation and `query_with_reasoning()`. For structured entity and relation extraction, `semantica.semantic_extract` accepts provider names as strings. Both patterns are covered here.
</Info>

## Choosing a Provider

Four factors drive provider selection, each optimized for different use cases:

**Latency** matters most in real-time SOC triage loops where an analyst is waiting on a triage verdict. Groq's inference infrastructure typically returns 8B model responses in under 300ms, making it ideal for interactive workflows.

**Accuracy** matters most in high-stakes decisions: clinical contraindication checks, credit committee reasoning, and legal document analysis. Frontier models like Claude or GPT-4 available through `LiteLLM` provide the strongest reasoning capabilities.

**Data residency** constraints eliminate cloud providers for classified or HIPAA-regulated workloads. `HuggingFaceLLM` with local model paths, or `Ollama` pointed at a local server, both enable fully air-gapped deployments without network calls.

**Cost at scale** favors high-throughput providers like Novita AI for bulk extraction pipelines processing thousands of documents per hour where per-token costs accumulate quickly.

The unified interface means you can prototype with Groq for speed, validate accuracy with Claude, and deploy to Azure OpenAI for compliance — without changing application code.

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

**Groq** is a cloud provider that specializes in ultra-fast language model inference using custom hardware called Language Processing Units (LPUs). Their infrastructure delivers sub-300ms response times for smaller models, making them ideal for real-time applications where speed matters more than maximum reasoning capability.

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

**OpenAI** provides access to the GPT model family, including GPT-4o with advanced capabilities like function calling (structured tool use) and vision processing for images and documents. OpenAI models are well-suited for complex reasoning tasks that require strong language understanding and generation capabilities.

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

## Anthropic — Complex Reasoning and Structured Extraction

**Anthropic** provides the Claude model family, built with an emphasis on careful, instruction-following behavior and strong performance on multi-step reasoning, long-document analysis, and code-related tasks. Claude models tend to be more cautious about ambiguous instructions than other providers. That matters when the cost of a confidently wrong answer is high.

The `Anthropic` provider wraps the Claude API. Reach for it when the task involves reasoning through several dependent steps (not just single-turn extraction), when you're processing long source documents that need to stay in context, or when you need schema-validated structured output rather than best-effort JSON.

Install with `pip install "semantica[llm-anthropic]"` (or just `pip install anthropic`) before using this provider.

```python
from semantica.llms import Anthropic

claude = Anthropic(model="claude-sonnet-4-6", api_key="YOUR_ANTHROPIC_KEY")
# api_key falls back to the ANTHROPIC_API_KEY environment variable

# is_available() only confirms a client was constructed from some key.
# It does not validate the key or check network reachability - an
# invalid or expired key still passes this check and fails at generate().
if not claude.is_available():
    raise RuntimeError("Anthropic provider not configured - set ANTHROPIC_API_KEY")

# Plain generation - multi-step reasoning over a contract clause
verdict = claude.generate(
    "A vendor contract has a 30-day termination-for-convenience clause "
    "but a 90-day data-return obligation that survives termination. "
    "If the customer terminates on day 1, when must vendor-held data "
    "be returned? Answer with the date basis only.",
    temperature=0.1,
)
print(verdict)
# "Day 120 from termination notice. The 90-day return period runs from
#  the termination date (day 30), not from the notice date."

# Structured, schema-validated output
from pydantic import BaseModel

class ContractRisk(BaseModel):
    clause: str
    risk_level: str
    days_to_deadline: int

risk = claude.generate_typed(
    "Extract the termination clause risk from: vendor contract, "
    "30-day termination for convenience, 90-day post-termination "
    "data return obligation.",
    schema=ContractRisk,
)
print(risk.risk_level, risk.days_to_deadline)
# "medium" 90
```

Model selection follows the same tier structure as the other providers: a Haiku model for high-volume classification where cost matters more than depth, a Sonnet model as the default for most extraction and reasoning tasks, an Opus model when a task genuinely needs the deepest reasoning available and latency/cost are secondary. Check Anthropic's docs for the current model identifiers, since they're versioned and change over time.

## Gemini — Long Context and Multimodal Input

**Gemini** is Google's model family, with a context window large enough to hold entire codebases or long regulatory filings in a single call, and native support for image and document input alongside text. Reach for it when a task needs to reference a large amount of source material at once, or when the input isn't plain text.

The `Gemini` provider tries the newer `google-genai` SDK first and falls back to the older `google-generativeai` package if that's what's installed. Install with `pip install "semantica[llm-gemini]"` (or `pip install google-genai`) before using this provider.

```python
from semantica.llms import Gemini

gemini = Gemini(model="gemini-pro", api_key="YOUR_GEMINI_KEY")
# api_key falls back to the GEMINI_API_KEY environment variable

if not gemini.is_available():
    raise RuntimeError("Gemini provider not configured - set GEMINI_API_KEY")

response = gemini.generate(
    "Summarize the key obligations in a standard NDA in three bullet points."
)
print(response)

data = gemini.generate_structured(
    "Extract the party names and effective date from: "
    "This Agreement is entered into between Acme Corp and Globex LLC, "
    "effective January 1, 2026."
)
print(data)
```

## Ollama — Local, Air-Gapped Inference

**Ollama** runs models entirely on your own machine, with no API key and no outbound network call. It's the right choice for air-gapped environments, offline development, or any workload where the source data can't leave the local network.

Unlike the other providers here, `Ollama` takes a `base_url` instead of an `api_key`. It talks to a local Ollama server over HTTP. Start the server with `ollama serve` and pull a model with `ollama pull llama2` before using this provider. Install the Python client with `pip install "semantica[llm-ollama]"` (or `pip install ollama`).

```python
from semantica.llms import Ollama

llm = Ollama(model="llama2", base_url="http://localhost:11434")

if not llm.is_available():
    raise RuntimeError("Ollama provider not configured - is 'ollama serve' running?")

response = llm.generate("Explain the difference between a hash map and a tree map.")
print(response)
```

`is_available()` for Ollama does a real connectivity check (it calls the server's `list()` endpoint), unlike the API-key-based providers above, so a `False` here usually means the server isn't running rather than a missing credential.

## DeepSeek — Budget Reasoning at Scale

**DeepSeek** exposes an OpenAI-compatible API at a fraction of the cost of the larger US providers, with reasoning quality that holds up well for extraction and classification work. It's a reasonable default when you're processing a large volume of documents and don't need the deepest reasoning tier.

Install with `pip install "semantica[llm-deepseek]"` (or `pip install openai`, since DeepSeek is accessed through the OpenAI client pointed at a different base URL).

```python
from semantica.llms import DeepSeek

llm = DeepSeek(model="deepseek-chat", api_key="YOUR_DEEPSEEK_KEY")
# api_key falls back to the DEEPSEEK_API_KEY environment variable

if not llm.is_available():
    raise RuntimeError("DeepSeek provider not configured - set DEEPSEEK_API_KEY")

response = llm.generate("List three risks of using a floating IP in a Kubernetes ingress.")
print(response)

data = llm.generate_structured(
    "Extract the CVE ID and affected product from: "
    "CVE-2024-3400 affects PAN-OS GlobalProtect gateways."
)
print(data)
```

## LiteLLM — One Interface, 100+ Providers

**LiteLLM** is a universal adapter that provides a single interface to over 100 different LLM providers, including Anthropic Claude, Azure OpenAI, AWS Bedrock, Google Vertex AI, and local Ollama instances. It acts as a translation layer, converting your unified API calls into provider-specific requests, enabling easy switching between providers without code changes.

`LiteLLM` is the Swiss Army knife. It wraps the `litellm` library, which speaks to every major provider using a unified completion API. The model string encodes both provider and model name: `"anthropic/claude-sonnet-5"`, `"azure/gpt-4o"`, `"bedrock/anthropic.claude-sonnet-4-5-20250929-v1:0"`, `"ollama/llama3.2"`. Change the string, change the provider — no other code changes needed.

```python
from semantica.llms import LiteLLM

# Anthropic Claude — highest accuracy for complex reasoning
llm = LiteLLM(model="anthropic/claude-sonnet-5")
# Reads ANTHROPIC_API_KEY from environment

# Azure OpenAI — compliance and data-residency requirements
llm = LiteLLM(model="azure/gpt-4o", api_key="YOUR_AZURE_KEY")

# AWS Bedrock — existing cloud agreement, no new vendor
llm = LiteLLM(model="bedrock/anthropic.claude-sonnet-4-5-20250929-v1:0")

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
    "prod":    "anthropic/claude-sonnet-5",
    "staging": "openai/gpt-4o-mini",
    "local":   "ollama/llama3.2",
    "azure":   "azure/gpt-4o",
}

env = os.getenv("DEPLOY_ENV", "local")
llm = LiteLLM(model=PROVIDER_MAP[env])
# The rest of the application never touches provider names
```

## HuggingFaceLLM — Air-Gapped and On-Premise

**HuggingFaceLLM** provides access to open-source models from the HuggingFace ecosystem, either downloaded from the HuggingFace Hub or loaded from local file paths. This is the only option for completely offline deployments where no network access is available during inference, such as classified environments or air-gapped systems.

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
    deep_llm = LiteLLM(model="anthropic/claude-sonnet-5")
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

**Novita AI** exposes an OpenAI-compatible API at low per-call cost, making it a reasonable choice for high-volume NER pipelines where cost matters more than getting the single best answer.

Install with `pip install "semantica[llm-novita]"` (or `pip install openai`, since Novita is accessed through the OpenAI client pointed at a different base URL).

```python
from semantica.llms import Novita

llm = Novita(model="deepseek/deepseek-v3.2", api_key="YOUR_NOVITA_KEY")
# api_key falls back to the NOVITA_API_KEY environment variable

if not llm.is_available():
    raise RuntimeError("Novita provider not configured - set NOVITA_API_KEY")

response = llm.generate("Summarize the Basel III leverage ratio requirement.")

data = llm.generate_structured(
    "Extract drug names and dosages from: "
    "Patient received warfarin 5mg daily, aspirin 75mg daily, metformin 500mg twice daily."
)
```

Novita is also reachable as a provider name string for the NER interface, without going through the `Novita` class directly:

```python
from semantica.semantic_extract import NamedEntityRecognizer

ner = NamedEntityRecognizer(
    methods=["llm"],
    provider="novita",
    llm_model="deepseek/deepseek-v3.2",
)
entities = ner.extract_entities(
    "CVE-2024-3400 is exploited by UNC3886 targeting PAN-OS GlobalProtect."
)
for e in entities:
    print("{} ({}) conf={:.2f}".format(e.text, e.label, e.confidence))
```

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

# The llms module wrappers can also be used directly for raw prompt generation
# when you want to bypass the semantic extraction layer entirely

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
    deep_llm = LiteLLM(model="anthropic/claude-sonnet-5")
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
report_llm = LiteLLM(model="anthropic/claude-sonnet-5")
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
claude = LiteLLM(model="anthropic/claude-sonnet-5")

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
    print("  - [{}] {}".format(src.get("source", "?"), src["content"][:60]))
```

</Tab>
</Tabs>

## Common Pitfalls

**Choosing expensive frontier models for simple extraction tasks.** GPT-4o or Claude Sonnet for basic entity extraction is overkill — Groq's Llama models handle straightforward NER and classification at a fraction of the cost and latency. Reserve frontier models for complex reasoning that requires nuanced interpretation.

**Ignoring latency differences between providers.** Groq typically responds in under 300ms, while Anthropic Claude can take 2-3 seconds for the same query. For real-time agents or interactive workflows, latency differences compound across multiple LLM calls. Profile your provider performance under realistic load.

**Using LLMs for deterministic pattern matching that regex can handle.** If your task is extracting email addresses, phone numbers, or other pattern-based entities, regular expressions are faster, cheaper, and more reliable than LLM extraction. Use LLMs when context, ambiguity, or domain knowledge matter for correct interpretation.

**Not validating structured outputs.** The `generate_structured()` method returns parsed JSON, but LLMs can still produce malformed or incomplete structures. Always validate the returned dictionary against your expected schema before using the data downstream.

**Switching providers without testing prompt behavior.** Different models respond differently to the same prompt. A prompt optimized for GPT-4 may produce poor results with Llama or Claude. When switching providers, test your prompts and adjust temperature, instructions, or examples as needed.

**Overusing local HuggingFace models for tasks requiring latest knowledge.** Local models have a knowledge cutoff from their training date and cannot access current information. For tasks requiring up-to-date knowledge (recent CVEs, current regulations, latest threat intelligence), cloud providers with more recent training data may be necessary.

## Related Guides

- [Agent Memory](/guides/agent-memory) — using `query_with_reasoning()` with any LLM provider for graph-grounded retrieval
- [Multi-Agent Systems](/guides/multi-agent) — wiring different LLM providers to different agent tiers in a shared-graph pipeline
- [Semantic Extraction](/guides/semantic-extraction) — LLM-powered NER, relation extraction, event detection, and triplet extraction
- [GraphRAG](/guides/graphrag) — multi-hop graph reasoning with `query_with_reasoning()`
