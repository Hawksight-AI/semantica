"""
Vendors the real external ontologies used by the Regulatory Intelligence
Platform use case, byte-for-byte (content), into external/. Each file is
fetched directly from its official W3C (or W3C-affiliated) namespace/
repository URL, verified interactively at implementation time: several
"obvious" canonical URLs turned out to be dead links or HTML redirect pages,
so every URL below is one that was actually confirmed to return real
Turtle/RDF-XML content before being added here.

Run:
    python download_ontologies.py

Vendoring (rather than fetching at notebook run time) keeps the notebook
runnable offline after first setup and avoids notebook failures caused by
transient network issues.
"""

import sys
from datetime import datetime, timezone
from pathlib import Path

import requests

EXTERNAL_DIR = Path(__file__).parent / "external"

HEADERS_TURTLE = {
    "User-Agent": "Semantica-Cookbook/1.0 (+https://github.com/semantica-agi/semantica; educational use)",
    "Accept": "text/turtle, application/rdf+xml;q=0.9, */*;q=0.5",
}

# Each entry: (filename, url, format, description)
# format: "ttl" (Turtle) or "rdf" (RDF/XML): determines how the source
# header comment is embedded without breaking parseability.
ONTOLOGIES = [
    (
        "org.ttl",
        "https://www.w3.org/ns/org.ttl",
        "ttl",
        "W3C Organization Ontology (ORG)",
    ),
    (
        "prov-o.ttl",
        "https://www.w3.org/ns/prov.ttl",
        "ttl",
        "W3C PROV-O: The PROV Ontology",
    ),
    (
        "skos-core.rdf",
        "https://www.w3.org/2009/08/skos-reference/skos.rdf",
        "rdf",
        "W3C SKOS: Simple Knowledge Organization System, Core Vocabulary "
        "(no Turtle serialization is served at a stable URL; this is the "
        "official RDF/XML file, which OntologyIngestor also supports)",
    ),
    (
        "dcat.ttl",
        "https://www.w3.org/ns/dcat.ttl",
        "ttl",
        "W3C DCAT: Data Catalog Vocabulary",
    ),
    (
        "time.ttl",
        "https://www.w3.org/2006/time",
        "ttl",
        "W3C OWL-Time: Time Ontology in OWL (content-negotiated Turtle)",
    ),
    (
        "frbr.ttl",
        "https://sparontologies.github.io/frbr/current/frbr.ttl",
        "ttl",
        "FRBR Core (SPAR OWL 2 DL edition): Functional Requirements for Bibliographic Records",
    ),
]


def _header_comment(url: str, description: str, fmt: str) -> str:
    retrieved = datetime.now(timezone.utc).isoformat()
    if fmt == "rdf":
        return (
            f"<!-- Vendored from {url}\n"
            f"     Retrieved: {retrieved}\n"
            f"     Description: {description}\n"
            f"     License: see the publishing organization's terms (W3C Document License) -->\n"
        )
    return (
        f"# Vendored from {url}\n"
        f"# Retrieved: {retrieved}\n"
        f"# Description: {description}\n"
        f"# License: see the publishing organization's terms (W3C Document License / SPAR Ontologies)\n\n"
    )


def download(filename: str, url: str, fmt: str, description: str) -> None:
    print(f"Fetching {description} ...")
    print(f"  {url}")
    response = requests.get(url, headers=HEADERS_TURTLE, timeout=60, allow_redirects=True)
    response.raise_for_status()
    content = response.text

    dest = EXTERNAL_DIR / filename
    header = _header_comment(url, description, fmt)

    if fmt == "rdf" and content.lstrip().startswith("<?xml"):
        # XML declaration must stay the first thing in the document:
        # insert the header comment immediately after it instead of before.
        decl_end = content.index("?>") + 2
        content = content[:decl_end] + "\n" + header + content[decl_end:]
    else:
        content = header + content

    # newline="" disables Windows newline translation: several of these
    # sources already use \r\n, and translating would double it to \r\r\n
    # and corrupt the file for rdflib's parser.
    dest.write_text(content, encoding="utf-8", newline="")

    size_kb = len(content) / 1024
    print(f"  -> saved {dest.name} ({size_kb:.1f} KB)")


def main() -> None:
    EXTERNAL_DIR.mkdir(parents=True, exist_ok=True)

    for filename, url, fmt, description in ONTOLOGIES:
        try:
            download(filename, url, fmt, description)
        except requests.RequestException as exc:
            print(f"ERROR: failed to fetch {url}: {exc}", file=sys.stderr)
            raise

    print(f"\nVendored {len(ONTOLOGIES)} real ontology files to {EXTERNAL_DIR}")


if __name__ == "__main__":
    main()
