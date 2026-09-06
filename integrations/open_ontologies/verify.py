"""Verification of Semantica's RDF exports.

Three checks a generation pipeline cannot run on itself, in the order that a
failure in one makes the next meaningless:

1. **Syntax, strictly.** Whether the output is RDF 1.1 at all. rdflib is lenient
   by design and will resolve a relative reference like ``<Acme Corp>`` against
   the file location, producing a ``file://`` IRI and a warning rather than an
   error, so a graph can "load" and still be nothing like what was meant.
   Oxigraph refuses it, which is the answer you want before publishing.

2. **Vocabulary, closed-world.** Whether the terms used were declared. RDF is
   open-world, so an invented predicate is unknown rather than wrong and passes
   both parsing and SHACL untouched. Closing the world against a declared
   vocabulary is the only way to separate a real term from a plausible one, and
   it is exactly the check an extraction pipeline needs, because inventing
   plausible terms is what extractors do when they are unsure.

3. **Shapes, with an audit of what was examined.** Whether constraints held, and
   how many nodes they held over. A shapes graph whose targets are absent from
   the data reports conformance having checked nothing, and that report is
   indistinguishable from a real pass. Every verdict here carries the focus-node
   count behind it.

Runs on ``open-ontologies-lite``, a pure-Python package over the Oxigraph engine.
No Rust toolchain, no service to run, no network.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass
class VerificationReport:
    """What an independent engine says about an export."""

    parses: bool
    triples: int = 0
    parse_error: str | None = None

    undeclared_terms: list[str] = field(default_factory=list)
    vocabulary_checked: bool = False

    conforms: bool | None = None
    violations: list[dict] = field(default_factory=list)
    focus_nodes: int | None = None
    unmatched_shapes: list[dict] = field(default_factory=list)

    @property
    def ok(self) -> bool:
        """True only when every check that ran gave a positive answer.

        A withheld SHACL verdict (``conforms is None``) is not a pass. Nothing
        was examined, so there is nothing to pass.
        """
        if not self.parses:
            return False
        if self.undeclared_terms:
            return False
        if self.conforms is False or (self.conforms is None and self.unmatched_shapes):
            return False
        return True

    def summary(self) -> str:
        if not self.parses:
            return f"not valid RDF: {self.parse_error}"
        parts = [f"{self.triples} triples"]
        if self.undeclared_terms:
            parts.append(f"{len(self.undeclared_terms)} undeclared term(s)")
        elif self.vocabulary_checked:
            parts.append("vocabulary clean")
        if self.conforms is False:
            parts.append(f"{len(self.violations)} SHACL violation(s)")
        elif self.conforms is None and self.unmatched_shapes:
            parts.append(
                f"SHACL verdict withheld: {len(self.unmatched_shapes)} shape(s) "
                f"matched nothing"
            )
        elif self.conforms is True:
            parts.append(f"conforms over {self.focus_nodes} focus node(s)")
        return ", ".join(parts)

    def to_dict(self) -> dict[str, Any]:
        return {
            "ok": self.ok,
            "parses": self.parses,
            "triples": self.triples,
            "parse_error": self.parse_error,
            "undeclared_terms": self.undeclared_terms,
            "conforms": self.conforms,
            "focus_nodes": self.focus_nodes,
            "unmatched_shapes": self.unmatched_shapes,
            "violations": self.violations,
            "summary": self.summary(),
        }


class VerificationError(RuntimeError):
    """Raised when a verified export would have written something unsound."""

    def __init__(self, report: VerificationReport):
        self.report = report
        super().__init__(report.summary())


def verify_rdf(
    rdf: str,
    *,
    fmt: str = "turtle",
    ontology: str | None = None,
    shapes: str | None = None,
    policed_namespaces: list[str] | None = None,
) -> VerificationReport:
    """Verify an RDF string and report what an independent engine finds.

    `ontology` enables the closed-world vocabulary check. Without it, or without
    `policed_namespaces`, that check is skipped rather than passed: there is
    nothing to check against, and a green light from an empty vocabulary is the
    failure the check exists to prevent.

    `shapes` enables SHACL. It needs `open-ontologies-lite[shacl]`.
    """
    from open_ontologies_lite import OntologyEngine, vocab_check

    report = VerificationReport(parses=False)

    # 1. Strict RDF 1.1 syntax.
    result = OntologyEngine.validate(rdf, fmt)
    report.parses = result.ok
    report.triples = result.triples
    report.parse_error = result.error
    if not result.ok:
        # Nothing downstream can be trusted about a graph that did not parse.
        return report

    # 2. Closed-world vocabulary.
    if ontology or policed_namespaces:
        vocab = vocab_check(
            ontology or "",
            rdf,
            data_format=fmt,
            extra_namespaces=policed_namespaces,
        )
        report.vocabulary_checked = "warning" not in vocab
        report.undeclared_terms = vocab["undeclared_terms"]

    # 3. Shapes, with the focus-node audit.
    if shapes:
        from open_ontologies_lite.shacl import shacl_validate

        shacl = shacl_validate(rdf, shapes, data_format=fmt)
        report.conforms = shacl["conforms"]
        report.violations = shacl["violations"]
        report.focus_nodes = shacl["focus_nodes"]
        report.unmatched_shapes = shacl["unmatched_shapes"]

    return report
