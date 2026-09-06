"""
Semantica × Open Ontologies Integration
=======================================

Verified RDF export: write the graph, then have an independent engine read it
back before the file is trusted.

Public surface
--------------
verify_rdf            — check an RDF string, return a ``VerificationReport``
verified_export_rdf   — export, verify, and refuse to leave an unsound file
VerificationReport    — what the independent engine found
VerificationError     — raised when a verified export would have written junk
register              — install the ``"verified"`` method in the export registry

Quick start
-----------
    pip install semantica[open-ontologies]

    >>> from integrations.open_ontologies import register
    >>> register()
    >>> from semantica.export.methods import export_rdf
    >>> export_rdf(kg, "graph.ttl", method="verified", ontology=vocab_ttl)

Nothing in the core changes. The method is registered through Semantica's own
``method_registry`` and is opt-in per call, so an existing pipeline behaves
exactly as it did until it asks for ``method="verified"``.

Why an independent engine
-------------------------
A generator cannot check its own output: it shares the assumptions that
produced the bug. If the code that writes an identifier has the wrong idea of
what a valid IRI is, the code that reads it back has the same wrong idea, and
the tests pass.

Concretely, and this is why the check earns its place. rdflib is lenient by
design: given a subject written as ``<Acme Corp>``, which the IRI grammar
forbids, it resolves the reference against the current working directory,
yields ``file:///…/Acme%20Corp``, and logs a warning. Oxigraph refuses the
file outright. One reader hands you a graph whose identifiers depend on which
directory the job ran in and reports success; the other tells you there is no
graph. This integration puts the strict reader after the export.

Three checks run in the order in which a failure in one makes the next
meaningless:

1. **Syntax, strictly.** Is it RDF 1.1 at all.
2. **Vocabulary, closed-world.** Which terms were used and declared nowhere.
   RDF is open-world, so an invented predicate is unknown rather than wrong and
   passes both parsing and SHACL untouched. Closing the world against a
   declared vocabulary is the only way to tell a real term from a plausible
   one, which matters here because inventing plausible terms is what an
   extractor does when it is unsure.
3. **Shapes, with an audit of what was examined.** Not only whether constraints
   held, but over how many nodes. A shapes graph whose targets are absent from
   the data reports conformance having checked nothing, and that report is
   indistinguishable from a real pass.

Compatibility
-------------
Requires ``open-ontologies-lite >= 0.4.0``, a pure-Python package over the
Oxigraph engine. No Rust toolchain, no service to run, no network. SHACL needs
the ``open-ontologies-lite[shacl]`` extra. Every symbol imports without it
installed; the import happens inside the call.

This integration depends on #1108, fixed in #1127. Before that, a custom method
could not refuse anything: ``method_registry`` caught every exception and fell
back to the default, so a gate that rejected invalid RDF and deleted the file
was followed by the fallback writing it straight back.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any, Optional

from .verify import VerificationError, VerificationReport, verify_rdf

__all__ = [
    "VerificationError",
    "VerificationReport",
    "verify_rdf",
    "verified_export_rdf",
    "register",
]


def verified_export_rdf(
    data: Any,
    file_path: str,
    format: str = "turtle",
    *,
    ontology: Optional[str] = None,
    shapes: Optional[str] = None,
    policed_namespaces: Optional[list] = None,
    raise_on_failure: bool = True,
    **kwargs: Any,
) -> VerificationReport:
    """Export RDF, then verify it before the file is trusted.

    Returns the :class:`VerificationReport`. With ``raise_on_failure`` (the
    default) an export that produced something unsound raises
    :class:`VerificationError` and the file is removed, so a failed run leaves
    no artifact that looks like a successful one.

    Pass ``raise_on_failure=False`` to keep the file and inspect the report,
    which is the right mode for a survey of an existing corpus.
    """
    from semantica.export.rdf_exporter import RDFExporter

    path = Path(file_path)
    RDFExporter().export(data, path, format=format, **kwargs)

    report = verify_rdf(
        path.read_text(encoding="utf-8"),
        fmt=format,
        ontology=ontology,
        shapes=shapes,
        policed_namespaces=policed_namespaces,
    )

    if raise_on_failure and not report.ok:
        path.unlink(missing_ok=True)
        raise VerificationError(report)

    return report


def register() -> None:
    """Register the ``"verified"`` method with Semantica's export registry."""
    from semantica.export.registry import method_registry

    method_registry.register("rdf", "verified", verified_export_rdf)
