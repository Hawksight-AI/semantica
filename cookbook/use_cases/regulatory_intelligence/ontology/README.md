# Ontology

Six real, external ontologies are vendored byte-for-byte, with content preserved exactly as fetched and a small header comment recording the source URL and retrieval date. Nothing here is invented. Two small hand-authored files add just enough domain schema to connect them. They are schema, not data, and every term in them is grounded in text that actually appears in the 9 real documents under `../data/raw/`.

Run `python download_ontologies.py` to fetch the six external files into `external/`.

## Vendored real ontologies (`external/`)

| File | Ontology | Source | Used for |
|---|---|---|---|
| `org.ttl` | W3C Organization Ontology (ORG) | [w3.org/ns/org.ttl](https://www.w3.org/ns/org.ttl) | Modeling NIST, OMB, HHS, and the Fed as `org:Organization`; entity resolution |
| `prov-o.ttl` | W3C PROV-O | [w3.org/ns/prov.ttl](https://www.w3.org/ns/prov.ttl) | Provenance: every requirement clause traces back to its real source document |
| `skos-core.rdf` | W3C SKOS Core | [w3.org/2009/08/skos-reference/skos.rdf](https://www.w3.org/2009/08/skos-reference/skos.rdf) | The controlled vocabulary in `skos/regulatory_taxonomy.ttl` |
| `dcat.ttl` | W3C DCAT | [w3.org/ns/dcat.ttl](https://www.w3.org/ns/dcat.ttl) | Cataloging each ingested document as a `dcat:Dataset` with its real source URL |
| `time.ttl` | W3C OWL-Time | [w3.org/2006/time](https://www.w3.org/2006/time) (content-negotiated Turtle) | Modeling each requirement's effective and validity window as a formal `time:Interval` |
| `frbr.ttl` | FRBR Core (SPAR OWL 2 DL edition) | [sparontologies.github.io](https://sparontologies.github.io/frbr/current/frbr.ttl) | Modeling "the NIST Cybersecurity Framework" and "the NIST AI RMF" as an `frbr:Work` with each version as an `frbr:Expression`, for the temporal-diff step |

**Note on formats**: `skos-core.rdf` is RDF/XML, not Turtle. No stable Turtle serialization of the canonical SKOS core vocabulary is served by W3C, so the official RDF/XML file is used instead (`OntologyIngestor` supports both). Every other file is genuine Turtle, confirmed by parsing each with `rdflib` before committing.

**A note on dead ends**: several "obvious" canonical URLs for these ontologies turned out to be broken or redirect-only when actually tested. For example, `w3.org/2004/02/skos/core.ttl` returns an HTML "300 Multiple Choices" page, not Turtle, and the original OWL-Time GitHub raw URL 404s. The URLs above are the ones that were interactively verified to return real, parseable RDF before being added to `download_ontologies.py`.

## Hand-authored schema extension

- **`regulatory_extension.ttl`**: adds `reg:Regulation` (a subclass of `dcat:Dataset` and `prov:Entity`), `reg:RequirementClause` (a subclass of `prov:Entity`), and `reg:Agency` (a subclass of `org:Organization`), plus properties (`issuedBy`, `hasRequirement`, `appliesToSector`, `supersedes`, `amends`, `implements`, `conflictsWith`, `effectiveInterval`, `sourceCitation`) that connect ingested documents to the vendored ontologies above rather than duplicating what they already model.
- **`skos/regulatory_taxonomy.ttl`**: about 22 SKOS concepts. Every one is a term verified, by text-searching the real PDFs and XML before writing the file, to actually appear in a specific source document. `Govern`, `Identify`, `Protect`, `Detect`, `Respond`, and `Recover` are CSF 2.0's own six Function names. `Administrative Safeguards`, `Physical Safeguards`, `Technical Safeguards`, and `Organizational Requirements` are 45 CFR 164's own subsection headings. `Confabulation` and `Content Provenance` are NIST AI 600-1's own terms. Each concept's `skos:scopeNote` names its source.

## Why reuse instead of inventing

Every capability this use case demonstrates (organizations, provenance, taxonomy, dataset cataloging, temporal versioning) already has a mature, real W3C or W3C-affiliated ontology. Reusing them, rather than building bespoke equivalents, is both less work and a more honest demonstration of Semantica's ontology-alignment capabilities. `OntologyIngestor.ingest_ontology()` imports each file as-is, and `regulatory_extension.ttl` is intentionally the smallest possible bridge between them.
