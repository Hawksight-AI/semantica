from types import SimpleNamespace

import pytest

from semantica.ontology import (
    OntologyEngine,
    OntologyQualityGate,
    QualitySeverity,
    ontology_quality_check,
)


def _ontology():
    return {
        "classes": [
            {"name": "Person", "uri": "https://example.org/Person"},
            {"name": "Company", "uri": "https://example.org/Company"},
        ],
        "properties": [
            {
                "name": "worksFor",
                "type": "object",
                "domain": ["Person"],
                "range": ["Company"],
            },
            {
                "name": "name",
                "type": "data",
                "domain": ["Person"],
                "range": "string",
            },
        ],
    }


def test_quality_gate_reports_a_healthy_ontology():
    report = ontology_quality_check(_ontology())

    assert report.passed
    assert report.metrics["coverage"] == 1.0
    assert report.error_count == 0
    assert report.to_dict()["stats"]["properties"] == 2


def test_quality_gate_finds_schema_and_endpoint_problems():
    ontology = {
        "classes": [{"name": "Person"}, {"name": "Unused"}],
        "properties": [
            {
                "name": "worksFor",
                "type": "object",
                "domain": ["Person"],
                "range": ["MissingCompany"],
            },
            {"name": "unattached", "type": "data"},
        ],
    }
    graph = {
        "entities": [{"id": "p1", "type": "Person"}],
        "relationships": [
            {"source_id": "p1", "target_id": "missing", "type": "worksFor"}
        ],
    }

    report = OntologyQualityGate().check(ontology, graph_data=graph)
    codes = {issue.code for issue in report.issues}

    assert not report.passed
    assert "UNKNOWN_RANGE" in codes
    assert "UNRESOLVED_RELATIONSHIP_ENDPOINT" in codes
    assert "ORPHAN_CLASS" in codes
    assert "MISSING_RANGE" in codes
    assert any(issue.severity == QualitySeverity.WARNING for issue in report.issues)


def test_quality_gate_supports_thresholds_and_legacy_endpoint_keys():
    ontology = {
        "classes": [{"name": "Person"}],
        "properties": [
            {
                "name": "name",
                "type": "data",
                "domain": "Person",
                "range": "xsd:string",
            }
        ],
    }
    graph = {
        "entities": [{"entity_id": "p1", "type": "Person", "name": "Alice"}],
        "relationships": [{"source": "p1", "target": "p1", "type": "knows"}],
    }

    report = ontology_quality_check(
        ontology,
        graph_data=graph,
        thresholds={"min_coverage": 1.0},
    )

    assert report.passed
    assert report.threshold_failures == []
    assert report.stats["relationships"] == 1


def test_quality_gate_can_fail_on_warnings():
    report = ontology_quality_check(
        {"classes": [{"name": "Person"}], "properties": []},
        fail_on_warnings=True,
    )

    assert not report.passed
    assert "fail_on_warnings" in report.threshold_failures


def test_engine_exposes_quality_check():
    report = OntologyEngine().quality_check(_ontology())

    assert report.passed


def test_quality_gate_accepts_canonical_context_graph_entities_without_mutation():
    graph = {
        "entities": [
            {"id": "p1", "text": "Alice", "type": "Person"},
            {"id": "c1", "text": "Acme", "type": "Company"},
        ],
        "relationships": [{"source_id": "p1", "target_id": "c1", "type": "worksFor"}],
    }

    report = OntologyQualityGate().check(_ontology(), graph_data=graph)

    assert report.passed
    assert "name" not in graph["entities"][0]


def test_quality_gate_returns_structured_findings_for_malformed_graph_members():
    report = OntologyQualityGate().check(
        _ontology(), graph_data={"entities": [None], "relationships": [None]}
    )
    codes = {issue.code for issue in report.issues}

    assert not report.passed
    assert {"INVALID_ENTITY", "INVALID_RELATIONSHIP"} <= codes


def test_quality_gate_returns_structured_finding_for_invalid_graph_containers():
    report = OntologyQualityGate().check(
        _ontology(), graph_data={"entities": None, "relationships": []}
    )

    assert not report.passed
    assert any(issue.code == "INVALID_GRAPH" for issue in report.issues)


def test_quality_gate_does_not_undercount_identical_dangling_edges():
    graph = {
        "entities": [{"id": "p1", "name": "Alice", "type": "Person"}],
        "relationships": [
            {"source": "p1", "target": "missing", "type": "knows"},
            {"source": "p1", "target": "missing", "type": "knows"},
        ],
    }

    report = OntologyQualityGate().check(
        _ontology(), graph_data=graph, thresholds={"max_errors": 1}
    )

    endpoint_errors = [
        issue
        for issue in report.issues
        if issue.code == "UNRESOLVED_RELATIONSHIP_ENDPOINT"
    ]
    assert len(endpoint_errors) == 2
    assert not report.passed
    assert "max_errors" in report.threshold_failures


def test_quality_gate_indexes_all_class_identifier_aliases():
    ontology = {
        "classes": [{"name": "Person", "uri": "https://example.org/PersonType"}],
        "properties": [
            {
                "name": "name",
                "type": "data",
                "domain": "https://example.org/PersonType",
                "range": "string",
            }
        ],
    }

    report = OntologyQualityGate().check(ontology)
    codes = {issue.code for issue in report.issues}

    assert "UNKNOWN_DOMAIN" not in codes


def test_quality_gate_recognizes_subclass_of_hierarchies():
    ontology = {
        "classes": [
            {"name": "Person"},
            {"name": "Employee", "subclassOf": "Person"},
        ],
        "properties": [
            {
                "name": "name",
                "type": "data",
                "domain": "Employee",
                "range": "string",
            }
        ],
    }

    report = OntologyQualityGate().check(ontology)

    assert not any(issue.code == "ORPHAN_CLASS" for issue in report.issues)


def test_quality_gate_keeps_competency_evaluation_safe_for_malformed_members():
    ontology = {
        "classes": [None, {"uri": "https://example.org/Person"}],
        "properties": [
            None,
            {
                "uri": "https://example.org/name",
                "type": "data",
                "domain": "Person",
                "range": "string",
            },
        ],
    }

    report = OntologyQualityGate().check(
        ontology, competency_questions=["What is a person's name?"]
    )

    assert isinstance(report.metrics["competency_question_coverage"], float)


def test_quality_gate_reports_validator_warnings_and_can_fail_on_them():
    class WarningValidator:
        def validate(self, ontology):
            return SimpleNamespace(valid=True, errors=[], warnings=["review me"])

    report = OntologyQualityGate(
        validator=WarningValidator(), fail_on_warnings=True
    ).check(_ontology())

    assert report.warning_count == 1
    assert "VALIDATOR_WARNING" in {issue.code for issue in report.issues}
    assert "fail_on_warnings" in report.threshold_failures


def test_quality_gate_isolates_competency_questions_between_checks():
    engine = OntologyEngine()

    first = engine.quality_check(_ontology(), competency_questions=["Who is a Person?"])
    second = engine.quality_check(
        _ontology(), competency_questions=["What is a location?"]
    )

    assert first.metrics["competency_question_coverage"] == 1.0
    assert second.metrics["competency_question_coverage"] == 0.0


def test_quality_gate_treats_null_property_type_as_missing():
    ontology = {
        "classes": [{"name": "Person"}],
        "properties": [
            {
                "name": "value",
                "type": None,
                "domain": "Person",
                "range": "string",
            }
        ],
    }

    report = OntologyQualityGate().check(ontology)

    assert "MISSING_PROPERTY_TYPE" in {issue.code for issue in report.issues}
    assert report.error_count >= 1


def test_quality_gate_normalizes_orphan_ids_for_deterministic_reports():
    graph = {
        "entities": [
            {"id": "p2", "name": "Bob", "type": "Person"},
            {"id": "p1", "name": "Alice", "type": "Person"},
        ],
        "relationships": [],
    }

    report = OntologyQualityGate().check(_ontology(), graph_data=graph)
    orphan = next(issue for issue in report.issues if issue.code == "ORPHAN_ENTITY")

    assert orphan.details["ids"] == ["p1", "p2"]


@pytest.mark.parametrize(
    "thresholds",
    [
        {"min_coverage": float("nan")},
        {"max_errors": float("inf")},
        {"max_warnings": float("-inf")},
    ],
)
def test_quality_gate_rejects_non_finite_thresholds(thresholds):
    with pytest.raises(ValueError, match="finite"):
        OntologyQualityGate().check(_ontology(), thresholds=thresholds)
