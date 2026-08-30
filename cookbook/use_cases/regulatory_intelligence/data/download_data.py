"""
Downloads the real source documents used by the Regulatory Intelligence
use case. Every URL below is an official government publication (NIST, GovInfo,
Federal Register, eCFR, whitehouse.gov, home.treasury.gov) verified at plan time.

Run:
    python download_data.py

Writes each document into raw/ and a source_manifest.json recording the exact
URL and retrieval timestamp for every file: this manifest is what the
notebook's PROV-O step cites as the source of each ingested requirement clause.

If any URL has moved, this script fails loudly (HTTPError / non-2xx) rather
than silently writing placeholder content, so a broken source is caught
immediately instead of masked.
"""

import json
import sys
from datetime import datetime, timezone
from pathlib import Path

import requests

RAW_DIR = Path(__file__).parent / "raw"

HEADERS = {
    "User-Agent": "Semantica-Cookbook/1.0 (+https://github.com/semantica-agi/semantica; educational use)"
}

# Each entry: (filename, url, doc_type, description)
# doc_type: "pdf" -> saved and later ingested via PDFParser
#           "xml" -> saved and later ingested via WebIngestor/ContentExtractor (eCFR versioner API)
# url == "ECFR_API" is resolved dynamically in resolve_ecfr_subpart_url() below.
DOCUMENTS = [
    (
        "nist_ai_rmf_1.0.pdf",
        "https://nvlpubs.nist.gov/nistpubs/ai/NIST.AI.100-1.pdf",
        "pdf",
        "NIST AI Risk Management Framework (AI RMF 1.0), NIST AI 100-1",
    ),
    (
        "nist_csf_1.1.pdf",
        "https://nvlpubs.nist.gov/nistpubs/cswp/nist.cswp.04162018.pdf",
        "pdf",
        "NIST Cybersecurity Framework, Version 1.1 (April 2018)",
    ),
    (
        "nist_csf_2.0.pdf",
        "https://nvlpubs.nist.gov/nistpubs/CSWP/NIST.CSWP.29.pdf",
        "pdf",
        "The NIST Cybersecurity Framework (CSF) 2.0, NIST CSWP 29 (February 2024)",
    ),
    (
        "nist_sp800-66r2_hipaa_security.pdf",
        "https://nvlpubs.nist.gov/nistpubs/SpecialPublications/NIST.SP.800-66r2.pdf",
        "pdf",
        "NIST SP 800-66 Rev. 2: Implementing the HIPAA Security Rule: A Cybersecurity Resource Guide",
    ),
    (
        "hipaa_security_rule_45cfr164_subpart_c.xml",
        "ECFR_API",  # resolved dynamically in download_ecfr_subpart() below
        "xml",
        "HIPAA Security Rule, 45 CFR Part 164 Subpart C (current eCFR text, via the public eCFR versioner API)",
    ),
    (
        "eo_14110_safe_secure_trustworthy_ai.pdf",
        "https://www.govinfo.gov/content/pkg/FR-2023-11-01/pdf/2023-24283.pdf",
        "pdf",
        "Executive Order 14110: Safe, Secure, and Trustworthy Development and Use of AI (Federal Register, Nov 1, 2023)",
    ),
    (
        "omb_m24-10_ai_governance.pdf",
        "https://www.whitehouse.gov/wp-content/uploads/2024/03/M-24-10-Advancing-Governance-Innovation-and-Risk-Management-for-Agency-Use-of-Artificial-Intelligence.pdf",
        "pdf",
        "OMB Memorandum M-24-10: Advancing Governance, Innovation, and Risk Management for Agency Use of Artificial Intelligence (March 2024)",
    ),
    (
        "nist_ai_600-1_genai_profile.pdf",
        "https://nvlpubs.nist.gov/nistpubs/ai/NIST.AI.600-1.pdf",
        "pdf",
        "NIST AI 600-1: Artificial Intelligence Risk Management Framework: Generative Artificial Intelligence Profile (2024)",
    ),
    (
        "fed_compliance_plan_omb_m24-10.pdf",
        "https://www.federalreserve.gov/publications/files/compliance-plan-for-omb-memorandum-m-24-10-202409.pdf",
        "pdf",
        "Board of Governors of the Federal Reserve System: Compliance Plan for OMB Memorandum M-24-10 (September 2024)",
    ),
]


def resolve_ecfr_subpart_url() -> str:
    """
    eCFR's regular HTML pages (www.ecfr.gov/current/...) sit behind a bot
    challenge that blocks plain HTTP clients. Its public versioner API does
    not, and is the officially documented way to fetch eCFR text
    programmatically. This resolves the *current* date dynamically instead
    of hardcoding one, so the script keeps working as time passes.
    """
    titles_resp = requests.get(
        "https://www.ecfr.gov/api/versioner/v1/titles.json", headers=HEADERS, timeout=30
    )
    titles_resp.raise_for_status()
    title_45 = next(t for t in titles_resp.json()["titles"] if t["number"] == 45)
    as_of = title_45["up_to_date_as_of"]
    return f"https://www.ecfr.gov/api/versioner/v1/full/{as_of}/title-45.xml?part=164&subpart=C"


def download(filename: str, url: str, doc_type: str, description: str) -> dict:
    print(f"Fetching {description} ...")
    print(f"  {url}")
    response = requests.get(url, headers=HEADERS, timeout=60)
    response.raise_for_status()

    dest = RAW_DIR / filename
    dest.write_bytes(response.content)

    size_kb = len(response.content) / 1024
    print(f"  -> saved {dest.name} ({size_kb:.1f} KB)")

    return {
        "filename": filename,
        "url": url,
        "type": doc_type,
        "description": description,
        "retrieved_at": datetime.now(timezone.utc).isoformat(),
        "size_bytes": len(response.content),
        "status_code": response.status_code,
    }


def main() -> None:
    RAW_DIR.mkdir(parents=True, exist_ok=True)

    manifest_entries = []
    for filename, url, doc_type, description in DOCUMENTS:
        if url == "ECFR_API":
            url = resolve_ecfr_subpart_url()
        try:
            manifest_entries.append(download(filename, url, doc_type, description))
        except requests.RequestException as exc:
            print(f"ERROR: failed to fetch {url}: {exc}", file=sys.stderr)
            raise

    manifest_path = RAW_DIR / "source_manifest.json"
    manifest_path.write_text(json.dumps(manifest_entries, indent=2), encoding="utf-8")
    print(f"\nWrote manifest for {len(manifest_entries)} documents to {manifest_path}")


if __name__ == "__main__":
    main()
