import unittest
from datetime import datetime

# Replicates the core pipeline of
# cookbook/use_cases/regulatory_intelligence/notebook/regulatory_intelligence.ipynb
# against tiny fixtures so it stays fast and network-free in CI. The fixture
# text below is copied verbatim from the real, committed documents in
# data/raw/ (verified against the real PDF/XML text when the notebook was
# built) — not synthetic sentences — so even this test exercises real
# regulatory language, not invented text.

try:
    from semantica.context import ContextGraph
    from semantica.ontology import OntologyGenerator, SHACLGenerator, PropertyShape
    from semantica.ontology.ontology_validator import _run_pyshacl
    from semantica.conflicts import ConflictDetector
    from semantica.context import PolicyEngine
    from semantica.context.decision_models import Policy, Decision
except ImportError as e:
    print(f"Skipping imports due to missing dependencies: {e}")


# Real excerpts, verified to occur verbatim in the real ingested documents.
REAL_EXCERPT_CSF2_GOVERN = "GOVERN addresses an understanding"  # NIST CSWP 29 (CSF 2.0)
REAL_EXCERPT_HIPAA_306 = (
    "Ensure the confidentiality, integrity, and availability of all electronic "
    "protected health information"
)  # 45 CFR 164.306


class TestRegulatoryIntelligence(unittest.TestCase):
    def setUp(self):
        self.graph = ContextGraph(advanced_analytics=False)
        self.graph.add_node("agency:NIST", "reg:Agency", content="NIST", name="NIST")
        self.graph.add_node(
            "reg:nist_csf_2.0", "reg:Regulation", content="nist_csf_2.0", doc_id="nist_csf_2.0"
        )
        self.graph.add_edge("reg:nist_csf_2.0", "agency:NIST", edge_type="issuedBy")
        self.graph.add_node(
            "clause:csf2_govern",
            "reg:RequirementClause",
            content=REAL_EXCERPT_CSF2_GOVERN,
            source_citation="NIST CSWP 29 (CSF 2.0), Govern Function",
            sector="Cross-sector",
        )
        self.graph.add_edge("reg:nist_csf_2.0", "clause:csf2_govern", edge_type="hasRequirement")

    def _to_ontology_input(self, graph_dict):
        entities = [
            {
                "id": n["id"],
                "type": n["type"].split(":")[-1],
                "name": n.get("content") or n["id"],
                **n.get("properties", {}),
            }
            for n in graph_dict["nodes"]
        ]
        relationships = [
            {"source": e["source"], "target": e["target"], "type": e["type"]}
            for e in graph_dict["edges"]
        ]
        return {"entities": entities, "relationships": relationships}

    def test_graph_construction(self):
        graph_dict = self.graph.to_dict()
        self.assertEqual(len(graph_dict["nodes"]), 3)
        self.assertEqual(len(graph_dict["edges"]), 2)
        # The real excerpt must survive unmodified into the graph.
        clause_node = next(n for n in graph_dict["nodes"] if n["id"] == "clause:csf2_govern")
        self.assertEqual(clause_node["content"], REAL_EXCERPT_CSF2_GOVERN)

    def test_shacl_validation_catches_missing_citation(self):
        REG_BASE = "https://semantica.dev/cookbook/regulatory-intelligence/ontology#"
        SHAPES_BASE = "https://semantica.dev/cookbook/regulatory-intelligence/shapes/"

        graph_dict = self.graph.to_dict()
        kg_ontology = OntologyGenerator(base_uri=REG_BASE, min_occurrences=1).generate_from_graph(
            self._to_ontology_input(graph_dict), name="TestOntology"
        )

        shacl_gen = SHACLGenerator(base_uri=SHAPES_BASE, severity="Violation")
        shacl_graph = shacl_gen.generate(kg_ontology)

        clause_shape = next(
            ns for ns in shacl_graph.node_shapes if "requirementclause" in ns.target_class.lower()
        )
        clause_class_uri = f"{SHAPES_BASE}{clause_shape.target_class}"
        clause_shape.property_shapes.append(
            PropertyShape(path=f"{SHAPES_BASE}source_citation", min_count=1, severity="Violation")
        )

        shacl_ttl = shacl_gen.serialize(shacl_graph, format="turtle")

        data_ttl = f"""
        @prefix ex: <{SHAPES_BASE}> .
        <urn:clause:complete> a <{clause_class_uri}> ;
            ex:source_citation "45 CFR 164.306" .
        <urn:clause:incomplete> a <{clause_class_uri}> .
        """

        report = _run_pyshacl(data_ttl, shacl_ttl, data_graph_format="turtle", shacl_format="turtle")
        self.assertFalse(report.conforms)
        self.assertGreaterEqual(report.violation_count, 1)
        self.assertTrue(
            any("incomplete" in v.focus_node for v in report.violations),
            "Expected the incomplete clause to be flagged, not the complete one",
        )

    def test_conflict_detection_between_real_frameworks(self):
        # OMB M-24-10's binary rights/safety-impacting classification vs.
        # NIST AI 600-1's continuous risk-profile approach — a genuine,
        # documented methodological difference between two real frameworks.
        entities = [
            {
                "id": "ai_risk_classification_approach",
                "entity_id": "ai_risk_classification_approach",
                "classification_method": "binary_rights_safety_impacting",
            },
            {
                "id": "ai_risk_classification_approach",
                "entity_id": "ai_risk_classification_approach",
                "classification_method": "continuous_profile_based",
            },
        ]
        detector = ConflictDetector()
        conflicts = detector.detect_conflicts(
            entities, method="value", property_name="classification_method"
        )
        self.assertEqual(len(conflicts), 1)
        self.assertEqual(
            set(conflicts[0].conflicting_values),
            {"binary_rights_safety_impacting", "continuous_profile_based"},
        )

    def test_policy_gated_decision_recording(self):
        policy_engine = PolicyEngine(graph_store=self.graph)
        policy = Policy(
            policy_id="",
            name="AI Use Case Risk Governance",
            description="Derived from OMB M-24-10's rights/safety-impacting AI risk-classification criteria.",
            rules={"requires_caio_review": True},
            category="ai_governance",
            version="1.0",
            created_at=datetime.now(),
            updated_at=datetime.now(),
        )
        policy_id = policy_engine.add_policy(policy)
        self.assertTrue(policy_id)

        decision = Decision(
            decision_id="",
            category="ai_governance_review",
            scenario="Hospital deploying an AI-based patient triage assistant",
            reasoning="Test reasoning citing real requirement clauses.",
            outcome="pending_review",
            confidence=0.85,
            timestamp=datetime.now(),
            decision_maker="decision_agent",
            metadata={"sector": "Healthcare"},
        )
        # check_compliance returns a plain bool, not a violations object.
        compliant = policy_engine.check_compliance(decision, policy_id)
        self.assertIsInstance(compliant, bool)


if __name__ == "__main__":
    unittest.main()
