---
title: "Semantic Extraction"
description: "How Semantica extracts entities, relationships, events, and RDF triplets from unstructured text using pattern, ML, and LLM methods — with fallback chains, batch processing, and real-world pipelines for defense intelligence, cybersecurity, life science, and financial compliance."
icon: "magnifying-glass"
---

`semantica.semantic_extract` turns unstructured text into structured graph-ready output: it identifies named entities, extracts relationships between them, detects time-anchored events, resolves coreferences, and serialises everything as RDF triplets. Use it to populate a `ContextGraph` from raw documents — intelligence reports, clinical notes, regulatory filings, or any free-text corpus.

<Info>
  Extracted entities and relationships feed into `ContextGraph` via `AgentContext.store()`. For how they are attributed back to source documents, see the [Provenance Guide](provenance). For how the populated graph is queried and traversed, see [Context Graphs](context-graphs).
</Info>

## Step 1 — Named Entity Recognition: who and what is in the text

`NamedEntityRecognizer` extracts meaningful nouns from a document and lets you choose the underlying method depending on your latency budget and domain requirements:

```python
from semantica.semantic_extract import NamedEntityRecognizer

# A finished intelligence report excerpt
report = """
ASSESSMENT (SECRET//NOFORN): GAMMA-7 threat actor, assessed with HIGH confidence
to operate from COUNTRY_X, conducted OPERATION NIGHTFALL between Jan–Mar 2025.
The group deployed HAMMERTOSS malware targeting NATO logistics networks via
spear-phishing lures referencing Exercise STEADFAST DEFENDER 2025.
Infrastructure cluster 185.220.101.0/24 was active throughout the campaign.
A second actor, DELTA-3, provided GAMMA-7 with zero-day exploits (CVE-2025-1234,
CVE-2025-5678) for Ivanti Connect Secure VPN appliances.
"""

# LLM-backed NER handles custom intelligence entity types that spaCy won't know.
# Fallback chain: if llm returns nothing, try ml (spaCy), then pattern matching.
ner = NamedEntityRecognizer(
    methods=["llm", "ml", "pattern"],
    confidence_threshold=0.75,
    provider="anthropic",
    llm_model="claude-sonnet-4-6",
)
entities = ner.extract_entities(report)

for e in entities:
    print("[{:>5.2f}]  {:15s}  {}".format(e.confidence, e.label, e.text))

# Expected output (abbreviated):
# [ 0.94]  THREAT_ACTOR    GAMMA-7
# [ 0.91]  THREAT_ACTOR    DELTA-3
# [ 0.97]  MALWARE         HAMMERTOSS
# [ 0.99]  CVE             CVE-2025-1234
# [ 0.99]  CVE             CVE-2025-5678
# [ 0.88]  NETWORK         185.220.101.0/24
# [ 0.85]  ORG             NATO
```

The `confidence` field tells you how certain the extractor is. Values below your threshold (here 0.75) are filtered before they reach you. The `label` field uses either standard CoNLL types (PERSON, ORG, GPE) or domain-specific ones the LLM infers from context (THREAT_ACTOR, MALWARE, CVE, NETWORK).

Once you have the flat list of entities, group them by type to make the next steps easier:

```python
# classify_entities groups the flat list into a dict keyed by label
grouped = ner.classify_entities(entities)

print("Threat actors:", [e.text for e in grouped.get("THREAT_ACTOR", [])])
# Threat actors: ['GAMMA-7', 'DELTA-3']

print("Malware:      ", [e.text for e in grouped.get("MALWARE", [])])
# Malware:       ['HAMMERTOSS']

print("CVEs:         ", [e.text for e in grouped.get("CVE", [])])
# CVEs:          ['CVE-2025-1234', 'CVE-2025-5678']

# score_confidence re-scores with a statistical model — useful when your primary
# method doesn't return calibrated probabilities (e.g., pattern matching)
rescored = ner.score_confidence(entities)
high_conf = [e for e in rescored if e.confidence >= 0.85]
print("High-confidence entities: {}".format(len(high_conf)))
```

## Step 2 — Relation Extraction: how the entities connect

`RelationExtractor` produces the web of connections between entities — who deployed what, who supplied whom, which CVE targets which product:

```python
from semantica.semantic_extract import RelationExtractor

# dependency parsing picks up syntactic relations ("DELTA-3 provided GAMMA-7 with...")
# pattern matching catches explicit verb phrases as a fallback
rel = RelationExtractor(
    method=["dependency", "pattern"],
    relation_types=["operates_from", "deployed", "targets", "provided_to", "exploits"],
    bidirectional=True,      # also try object→subject direction
    confidence_threshold=0.65,
)

# extract_relations takes the original text plus the entities you already found.
# Passing entities avoids re-running NER and constrains the search space.
relations = rel.extract_relations(report, entities)

for r in relations:
    print("[{:.2f}]  {} --[{}]--> {}".format(
        r.confidence, r.subject.text, r.predicate, r.object.text
    ))

# Example output:
# [0.88]  GAMMA-7 --[deployed]--> HAMMERTOSS
# [0.82]  DELTA-3 --[provided_to]--> GAMMA-7
# [0.79]  CVE-2025-1234 --[exploits]--> Ivanti Connect Secure
# [0.85]  GAMMA-7 --[targets]--> NATO
```

The `context` field on each `Relation` stores the surrounding sentence. This lets you audit why the extractor made a given connection — essential when analysts need to verify that a link is grounded in the source text before acting on it.

## Step 3 — Event Detection: what happened, when, and to whom

`EventDetector` surfaces structured time-anchored events — discrete occurrences with participants, time windows, and locations:

```python
from semantica.semantic_extract import EventDetector

# method="llm" is the default and gives the best recall for implicit events.
# method="pattern" is appropriate for offline, high-throughput pipelines.
detector = EventDetector(method="llm", provider="anthropic")

events = detector.detect_events(report)

for ev in events:
    print("[{}]  time={}  location={}".format(
        ev.event_type, ev.time or "unknown", ev.location or "n/a"
    ))
    print("   participants: {}".format(ev.participants))
    print("   text: {}".format(ev.text[:80]))

# Example output:
# [campaign]  time=Jan–Mar 2025  location=n/a
#    participants: ['GAMMA-7', 'NATO']
#    text: GAMMA-7 conducted OPERATION NIGHTFALL between Jan–Mar 2025...
# [supply_chain]  time=unknown  location=n/a
#    participants: ['DELTA-3', 'GAMMA-7']
#    text: DELTA-3 provided GAMMA-7 with zero-day exploits...
```

For batch processing, pass a list of dicts to `extract()`. Each dict carries a `content` key and an optional `id` for provenance tracking:

```python
# extract() handles concurrent processing internally
batch_events = detector.extract([
    {"content": report, "id": "FINTEL_2025_0192"},
    {"content": advisory_2, "id": "FINTEL_2025_0193"},
    # ... up to 200 documents
])

# batch_events is List[List[Event]] — one inner list per document
for doc_idx, doc_events in enumerate(batch_events):
    print("Doc {}: {} events".format(doc_idx, len(doc_events)))
```

## Step 4 — Coreference Resolution: one entity, many names

`CoreferenceResolver` collapses references like "GAMMA-7", "the group", "they", and "the threat actor" into canonical chains so downstream extraction doesn't treat them as separate entities:

```python
from semantica.semantic_extract import CoreferenceResolver

resolver = CoreferenceResolver(method="llm", provider="anthropic")

# Pass the already-extracted entities so the resolver can anchor pronouns
# to the correct named entities rather than guessing from scratch
chains = resolver.resolve_coreferences(report, entities=entities)

for chain in chains:
    print("Representative: {}".format(chain.representative.text))
    mentions = [m.text for m in chain.mentions if m.text != chain.representative.text]
    print("   Also called: {}".format(mentions))

# Example output:
# Representative: GAMMA-7
#    Also called: ['the group', 'they', 'the threat actor']
```

With coreference resolved, you can now replace pronouns and aliases with canonical names before passing text to relation extraction — dramatically improving the quality of the relation graph.

## Step 5 — Triplet Extraction and RDF Serialisation: graph-ready output

`TripletExtractor` converts everything into subject-predicate-object triplets and serialises them as RDF, ready for graph ingestion and SPARQL queries:

```python
from semantica.semantic_extract import TripletExtractor

tri = TripletExtractor(
    method="llm",
    provider="anthropic",
    llm_model="claude-sonnet-4-6",
    include_temporal=True,       # attach time context to triplets when available
    include_provenance=True,     # embed source document reference in each triplet
)

# Feed in the entities and relations you already extracted — the extractor
# uses them to constrain and validate what it produces
triplets = tri.extract_triplets(report, entities, relations)

# Filter malformed triplets before serialisation
valid = tri.validate_triplets(triplets)
print("Valid: {}/{}".format(len(valid), len(triplets)))

for t in valid:
    print("({}, {}, {})  conf={:.2f}".format(
        t.subject, t.predicate, t.object, t.confidence
    ))

# Serialise to Turtle RDF for graph ingestion or STIX export
turtle_rdf = tri.serialize_triplets(valid, format="turtle")
print(turtle_rdf[:600])

# formats: "turtle" | "ntriples" | "jsonld" | "xml"
```

A validated triplet like `(GAMMA-7, deployed, HAMMERTOSS)` with `include_temporal=True` will carry the time interval from the Event you detected in step 3 — keeping the graph queryable not just by what happened but by when.

## Putting it together: a reusable extraction pipeline

Chain all five steps into a single function you can call on every incoming document:

```python
from semantica.semantic_extract import (
    NamedEntityRecognizer, RelationExtractor,
    EventDetector, CoreferenceResolver, TripletExtractor,
)
from semantica.provenance import ProvenanceManager
from semantica.context import AgentContext, ContextGraph
from semantica.vector_store import VectorStore


def ingest_intel_report(
    text: str,
    doc_id: str,
    agent: AgentContext,
    prov: ProvenanceManager,
    method: str = "llm",
) -> dict:
    """
    Full extraction pipeline: NER → Coref → Relations → Events → Triplets → Graph.
    Returns a summary dict with counts for monitoring dashboards.
    """

    # 1. Named entity recognition
    ner = NamedEntityRecognizer(
        methods=[method, "pattern"],
        confidence_threshold=0.70,
        provider="anthropic",
        llm_model="claude-sonnet-4-6",
    )
    entities = ner.extract_entities(text)
    classified = ner.classify_entities(entities)

    # 2. Coreference resolution — before relation extraction
    resolver = CoreferenceResolver(method=method, provider="anthropic")
    chains = resolver.resolve_coreferences(text, entities=entities)

    # 3. Relation extraction
    rel = RelationExtractor(
        method=[method, "pattern"],
        relation_types=["deployed", "targets", "exploits", "operates_from", "provided_to"],
        confidence_threshold=0.65,
        provider="anthropic",
        llm_model="claude-sonnet-4-6",
    )
    relations = rel.extract_relations(text, entities)

    # 4. Event detection
    detector = EventDetector(method=method, provider="anthropic")
    events = detector.detect_events(text)

    # 5. Triplet extraction and RDF serialisation
    tri = TripletExtractor(
        method=method,
        provider="anthropic",
        llm_model="claude-sonnet-4-6",
        include_temporal=True,
        include_provenance=True,
    )
    triplets = tri.extract_triplets(text, entities, relations)
    valid    = tri.validate_triplets(triplets)
    turtle   = tri.serialize_triplets(valid, format="turtle")

    # 6. Store in agent memory + knowledge graph
    graph_stats = agent.store(
        [{"content": text, "metadata": {"source": doc_id, "classification": "SECRET//NOFORN"}}],
        extract_entities=True,
        extract_relationships=True,
        link_entities=True,
    )

    # 7. Provenance tracking — every entity linked back to its source document
    prov.track_entities_batch(
        [{"id": e.text.lower().replace(" ", "_"), "confidence": e.confidence}
         for e in entities],
        source=doc_id,
        activity_id="intel_extraction_pipeline",
    )

    return {
        "entities":       len(entities),
        "entity_types":   {k: len(v) for k, v in classified.items()},
        "coref_chains":   len(chains),
        "relations":      len(relations),
        "events":         len(events),
        "triplets_valid": len(valid),
        "graph_nodes":    graph_stats.get("graph_nodes", 0),
        "graph_edges":    graph_stats.get("graph_edges", 0),
        "rdf_turtle":     turtle,
    }


# Process all 200 reports
intel_graph = ContextGraph(advanced_analytics=True)
intel_agent = AgentContext(
    vector_store=VectorStore(backend="faiss", dimension=768, index_path="intel.faiss"),
    knowledge_graph=intel_graph,
    decision_tracking=True,
)
prov = ProvenanceManager(storage_path="intel_provenance.db")

# reports is a list of (text, doc_id) tuples loaded from your 200 documents
for text, doc_id in reports:
    summary = ingest_intel_report(text, doc_id, intel_agent, prov)
    print("{}: {} entities, {} relations, {} events, {}/{} triplets valid".format(
        doc_id,
        summary["entities"],
        summary["relations"],
        summary["events"],
        summary["triplets_valid"],
        len(summary["rdf_turtle"]),
    ))
```

## Domain examples

<Tabs>
  <Tab title="Defense — CTI/Threat">
    Finished intelligence reports contain threat actors, malware, CVEs, infrastructure clusters, and operation timelines. LLM-backed NER handles custom entity labels (THREAT_ACTOR, OPERATION) that spaCy's off-the-shelf models miss, while RDF serialisation produces Turtle output compatible with STIX 2.1 object types.

```python
from semantica.semantic_extract import (
    NamedEntityRecognizer, RelationExtractor, TripletExtractor,
)

ner = NamedEntityRecognizer(
    methods=["llm", "pattern"],
    confidence_threshold=0.75,
    provider="anthropic",
    llm_model="claude-sonnet-4-6",
)
entities = ner.extract_entities(fintel_text)
grouped  = ner.classify_entities(entities)

print("Threat actors:", [e.text for e in grouped.get("THREAT_ACTOR", [])])
# ['APT29', 'COZY BEAR']
print("Malware:      ", [e.text for e in grouped.get("MALWARE", [])])
# ['HAMMERTOSS', 'SUNBURST']
print("CVEs:         ", [e.text for e in grouped.get("CVE", [])])
# ['CVE-2025-1234', 'CVE-2025-5678']

rel = RelationExtractor(
    method=["llm", "dependency"],
    relation_types=["operates_from", "deployed", "targets", "exploits"],
    confidence_threshold=0.70,
    provider="anthropic",
    llm_model="claude-sonnet-4-6",
)
relations = rel.extract_relations(fintel_text, entities)

tri = TripletExtractor(
    method="llm",
    provider="anthropic",
    llm_model="claude-sonnet-4-6",
    include_temporal=True,
    include_provenance=True,
)
triplets = tri.extract_triplets(fintel_text, entities, relations)
valid    = tri.validate_triplets(triplets)
turtle   = tri.serialize_triplets(valid, format="turtle")
# turtle now contains RDF triples for (APT29, deployed, HAMMERTOSS),
# (APT29, targets, NATO_logistics), etc. — ready for STIX graph ingest
```

  </Tab>

  <Tab title="Security — SOC/Incident">
    Vulnerability advisories and SIEM alerts contain CVEs, IP addresses, domain indicators, malware families, and affected software versions. Offline NER with the `["ml", "pattern"]` chain gives sub-200ms latency, critical for real-time triage pipelines where LLM latency is unacceptable.

```python
from semantica.semantic_extract import (
    NamedEntityRecognizer, RelationExtractor, TripletExtractor,
)

advisory = """
CVE-2025-44228 (CVSS 10.0): Critical RCE in Apache Log4j2 versions 2.0–2.14.1.
Threat actor WIZARD SPIDER exploiting via Cobalt Strike beacons since 2025-03-14.
Indicators: 203.0.113.45, c2-update[.]ru. Mitigate: upgrade to Log4j2 >= 2.17.1.
"""

# Offline stack — no API key required, latency < 200 ms
ner = NamedEntityRecognizer(
    methods=["ml", "pattern"],
    confidence_threshold=0.60,
)
entities = ner.extract_entities(advisory)
grouped  = ner.classify_entities(entities)

print("CVEs:    ", [e.text for e in grouped.get("CVE", [])])
# ['CVE-2025-44228']
print("IPs:     ", [e.text for e in grouped.get("IP", [])])
# ['203.0.113.45']
print("Domains: ", [e.text for e in grouped.get("DOMAIN", [])])
# ['c2-update[.]ru']
print("Actors:  ", [e.text for e in grouped.get("THREAT_ACTOR", [])])
# ['WIZARD SPIDER']

rel = RelationExtractor(
    method=["dependency", "pattern"],
    relation_types=["exploits", "delivers", "targets", "mitigated_by"],
    confidence_threshold=0.60,
)
relations = rel.extract_relations(advisory, entities)

tri = TripletExtractor(method="pattern", include_temporal=True)
triplets = tri.extract_triplets(advisory, entities, relations)
valid    = tri.validate_triplets(triplets)
ntriples = tri.serialize_triplets(valid, format="ntriples")
print("Valid triplets: {}".format(len(valid)))
# Valid triplets: 7
# Each triple encodes one structured fact: (CVE-2025-44228, exploited_by, WIZARD_SPIDER), etc.
```

  </Tab>

  <Tab title="Life Science — Clinical/Pharma">
    Clinical trial reports contain drugs, diseases, efficacy outcomes, adverse events, and trial identifiers. The `d4data/biomedical-ner-all` HuggingFace model is trained on PubMed and returns biomedical-specific labels (DRUG, DISEASE, GENE, OUTCOME) that general-purpose models miss. RDF serialisation in Turtle can be submitted in EMA XEVMPD and FDA SPL compatible formats.

```python
from semantica.semantic_extract import (
    NamedEntityRecognizer, RelationExtractor, TripletExtractor,
)
from semantica.provenance import ProvenanceManager
from semantica.provenance.schemas import SourceReference

paper = """
Phase III trial NCT04368728: BNT162b2 (Pfizer-BioNTech) evaluated in 43,448
participants aged >= 16 years. Vaccine efficacy: 95.0% (95% CI 90.3–97.6;
p<0.0001) against symptomatic COVID-19. Bell's palsy observed in 4 vaccine
vs 0 placebo participants (not statistically significant).
"""

ner = NamedEntityRecognizer(
    method="huggingface",
    huggingface_model="d4data/biomedical-ner-all",
    confidence_threshold=0.75,
)
entities = ner.extract_entities(paper)
grouped  = ner.classify_entities(entities)

print("Drugs:    ", [e.text for e in grouped.get("DRUG", [])])
# ['BNT162b2']
print("Diseases: ", [e.text for e in grouped.get("DISEASE", [])])
# ['COVID-19', "Bell's palsy"]
print("Outcomes: ", [e.text for e in grouped.get("OUTCOME", [])])
# ['vaccine efficacy 95.0%']

rel = RelationExtractor(
    method=["llm", "dependency"],
    relation_types=["treats", "causes_adverse_event", "has_efficacy", "evaluated_in"],
    confidence_threshold=0.65,
    provider="anthropic",
    llm_model="claude-sonnet-4-6",
)
relations = rel.extract_relations(paper, entities)

tri = TripletExtractor(
    method="llm",
    provider="anthropic",
    llm_model="claude-sonnet-4-6",
    triplet_types=["treats", "has_efficacy", "causes_adverse_event"],
    include_temporal=True,
    include_provenance=True,
)
triplets = tri.extract_triplets(paper, entities, relations)
turtle   = tri.serialize_triplets(tri.validate_triplets(triplets), format="turtle")

# Provenance: track the efficacy figure to its exact source for ICH E6(R2) compliance
prov = ProvenanceManager(storage_path="pharma_provenance.db")
prov.track_property_source(
    "BNT162b2", "vaccine_efficacy_pct", "95.0",
    SourceReference(
        document="DOI:10.1056/NEJMoa2034577",
        page=9,
        section="Table 2",
        confidence=0.99,
        metadata={"study_id": "C4591001", "n_participants": 43448},
    )
)
```

  </Tab>

  <Tab title="Banking — Risk/Compliance">
    Loan agreements, regulatory filings, and credit memos contain legal entities, financial instruments, counterparty relationships, and risk classifications. Pattern-based NER is fast enough for real-time loan origination workflows, while LLM extraction handles the dense legalese in regulatory documents where dependency parsing often fails.

```python
from semantica.semantic_extract import (
    NamedEntityRecognizer, RelationExtractor, TripletExtractor,
)

credit_memo = """
Borrower: ACME Manufacturing Ltd (registered UK). Guarantor: ACME Group PLC.
Facility: GBP 25M revolving credit at SONIA + 175bps, maturing 2028-03-31.
Collateral: first-ranking charge over ACME Manufacturing's UK fixed assets.
LTV: 67%. PD: 1.8%. LGD: 42%. RWA bucket: Standard (CRE20).
Exposure to counterparty sector: industrial manufacturing, risk tier 2.
"""

ner = NamedEntityRecognizer(
    methods=["llm", "ml", "pattern"],
    confidence_threshold=0.70,
    provider="anthropic",
    llm_model="claude-sonnet-4-6",
)
entities = ner.extract_entities(credit_memo)
grouped  = ner.classify_entities(entities)

print("Orgs:        ", [e.text for e in grouped.get("ORG", [])])
# ['ACME Manufacturing Ltd', 'ACME Group PLC']
print("Money:       ", [e.text for e in grouped.get("MONEY", [])])
# ['GBP 25M']
print("Dates:       ", [e.text for e in grouped.get("DATE", [])])
# ['2028-03-31']

rel = RelationExtractor(
    method=["llm", "dependency"],
    relation_types=["guaranteed_by", "secured_by", "classified_as", "exposed_to"],
    confidence_threshold=0.65,
    provider="anthropic",
    llm_model="claude-sonnet-4-6",
)
relations = rel.extract_relations(credit_memo, entities)

tri = TripletExtractor(
    method="llm",
    provider="anthropic",
    llm_model="claude-sonnet-4-6",
    include_temporal=True,
    include_provenance=True,
)
triplets = tri.extract_triplets(credit_memo, entities, relations)
valid    = tri.validate_triplets(triplets)
jsonld   = tri.serialize_triplets(valid, format="jsonld")
# JSON-LD output can be loaded directly into a compliance graph
# for Basel III RWA reporting and BCBS 239 data lineage requirements
```

  </Tab>
</Tabs>

## Choosing your extraction method

The six extraction methods trade off speed, accuracy, and infrastructure:

- `"pattern"` and `"regex"` — no dependencies, under 5 ms, ideal as the last fallback in any method chain. Reliable for narrow, predictable domains like CVE identifiers or IP addresses.
- `"rules"` — linguistic rule-based detection, also offline, under 10 ms.
- `"ml"` / `"spacy"` — general English NER at 50–200 ms with no API calls. Install with `pip install spacy && python -m spacy download en_core_web_sm`. The best default for production pipelines where LLM cost is a concern.
- `"huggingface"` — domain-specific fine-tuned models at 200 ms–2 s. Use `d4data/biomedical-ner-all` for pharma, `dslim/bert-base-NER` for general high-accuracy NER. Install with `pip install "semantica[huggingface]"`.
- `"llm"` — highest recall for implicit entities and custom label schemas, 1–10 s per document. Always pair with a fallback: `methods=["llm", "ml", "pattern"]`.

The fallback behaviour is automatic: if the primary method returns an empty list, the framework walks down the chain until it finds results or exhausts the list. Pattern matching is always the implicit last resort.

## Related Guides

- [Provenance Guide](provenance) — track every extracted entity and chunk back to its source document
- [Agent Memory Guide](agent-memory) — store extracted knowledge as searchable agent memories with graph enrichment
- [Context Graphs Guide](context-graphs) — how extracted entities populate `ContextGraph` nodes and edges
- [GraphRAG Guide](graphrag) — retrieve facts from the populated graph to ground LLM responses
- [Reasoning Guide](reasoning) — derive new facts, run SPARQL queries, and apply inference rules over the extracted graph
- [Semantic Extract Reference](../reference/semantic_extract) — full API for all extractor classes, providers, and validators
