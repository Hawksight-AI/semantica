import unittest
from types import SimpleNamespace

from semantica.reasoning.abductive_reasoner import (
    AbductiveReasoner,
    Observation,
)
from semantica.reasoning.deductive_reasoner import DeductiveReasoner, Premise
from semantica.reasoning.sparql_reasoner import SPARQLQueryResult, SPARQLReasoner
from semantica.utils.exceptions import ProcessingError


class TestSpecializedReasoners(unittest.TestCase):
    def test_sparql_reasoner_expand_query(self):
        reasoner = SPARQLReasoner()
        reasoner.add_inference_rule("IF ?x is_a Person THEN ?x is_a Human")
        
        query = "SELECT ?x WHERE { ?x a :Person . }"
        expanded = reasoner.expand_query(query)
        
        self.assertIn("Inference: Rule 1", expanded)
        self.assertIn("?x a :Person . => ?x a :Human .", expanded)

    def test_sparql_reasoner_infer_results(self):
        reasoner = SPARQLReasoner()
        reasoner.add_inference_rule("IF ?x is_a Person THEN ?x is_a Human")
        
        results = SPARQLQueryResult(
            bindings=[{"x": "John"}],
            variables=["x"]
        )
        
        inferred = reasoner.infer_results(results)
        self.assertEqual(len(inferred.bindings), 2)
        # One original binding, one with type Human
        binding_types = [b.get("x_type") for b in inferred.bindings]
        self.assertIn("Human", binding_types)

    def test_execute_query_without_store_raises_processing_error(self):
        """Refuse loudly instead of returning empty results (issue #1083)."""
        reasoner = SPARQLReasoner()
        with self.assertRaises(ProcessingError):
            reasoner.execute_query("SELECT ?s ?p ?o WHERE { ?s ?p ?o }")

    def test_execute_query_with_unusable_store_raises_processing_error(self):
        reasoner = SPARQLReasoner(triplet_store=object())
        with self.assertRaises(ProcessingError):
            reasoner.execute_query("SELECT ?s ?p ?o WHERE { ?s ?p ?o }")

    def _fake_store(self):
        class FakeStore:
            def __init__(self):
                self.received = None

            def execute_query(self, query, **options):
                self.received = (query, options)
                return {
                    "bindings": [{"x": "John"}],
                    "variables": ["x"],
                    "metadata": {"optimized": True},
                }

        return FakeStore()

    def _triplet_only_store(self):
        class TripletOnlyStore:
            def get_triplets(self):
                return [
                    SimpleNamespace(
                        subject="urn:alice", predicate="urn:worksAt", object="ACME"
                    ),
                    SimpleNamespace(
                        subject="urn:bob", predicate="urn:worksAt", object="Globex"
                    ),
                ]

        return TripletOnlyStore()

    def test_execute_query_delegates_to_store(self):
        store = self._fake_store()
        reasoner = SPARQLReasoner(triplet_store=store, enable_inference=False)

        result = reasoner.execute_query("SELECT ?x WHERE { ?x a :Person }")

        self.assertEqual(result.bindings, [{"x": "John"}])
        self.assertEqual(result.variables, ["x"])
        self.assertEqual(store.received[0], "SELECT ?x WHERE { ?x a :Person }")
        self.assertTrue(result.metadata.get("optimized"))

    def test_execute_query_delegated_result_is_cached(self):
        reasoner = SPARQLReasoner(
            triplet_store=self._fake_store(), enable_inference=False
        )
        query = "SELECT ?x WHERE { ?x a :Person }"

        first = reasoner.execute_query(query)
        second = reasoner.execute_query(query)

        self.assertFalse(first.metadata.get("cached"))
        self.assertTrue(second.metadata.get("cached"))
        self.assertEqual(second.bindings, first.bindings)

    def test_execute_query_applies_result_level_inference(self):
        reasoner = SPARQLReasoner(
            triplet_store=self._fake_store(), enable_inference=True
        )
        reasoner.add_inference_rule("IF ?x is_a Person THEN ?x is_a Human")

        result = reasoner.execute_query("SELECT ?x WHERE { ?x a :Person }")

        binding_types = [b.get("x_type") for b in result.bindings]
        self.assertIn("Human", binding_types)

    def test_execute_query_falls_back_to_rdflib_memory_graph(self):
        reasoner = SPARQLReasoner(
            triplet_store=self._triplet_only_store(), enable_inference=False
        )

        result = reasoner.execute_query("SELECT ?s ?o WHERE { ?s <urn:worksAt> ?o }")

        self.assertEqual(
            result.bindings,
            [
                {"s": "urn:alice", "o": "ACME"},
                {"s": "urn:bob", "o": "Globex"},
            ],
        )
        self.assertEqual(result.metadata.get("executed_via"), "rdflib_in_memory")

    def test_execute_query_rdflib_fallback_ask(self):
        reasoner = SPARQLReasoner(
            triplet_store=self._triplet_only_store(), enable_inference=False
        )

        result = reasoner.execute_query("ASK { ?s <urn:worksAt> ?o }")

        self.assertTrue(result.metadata.get("boolean"))

    def test_execute_query_skips_delegation_when_backend_lacks_sparql(self):
        store = self._fake_store()
        store._store_backend = object()  # backend without execute_sparql
        reasoner = SPARQLReasoner(triplet_store=store, enable_inference=False)

        # No get_triplets either, so the rdflib fallback must refuse loudly
        # instead of silently executing on the store's backend.
        with self.assertRaises(ProcessingError):
            reasoner.execute_query("SELECT ?s ?p ?o WHERE { ?s ?p ?o }")

    def test_execute_query_cached_result_is_isolated_from_returned_result(self):
        """Mutating a returned result must not corrupt the cache."""
        store = self._fake_store()
        reasoner = SPARQLReasoner(
            triplet_store=store, enable_inference=False
        )
        query = "SELECT ?x WHERE { ?x a :Person }"

        first = reasoner.execute_query(query)
        first.bindings.append({"x": "Injected"})
        first.bindings[0]["x"] = "Mutated"
        first.metadata["cached"] = True

        second = reasoner.execute_query(query)

        self.assertTrue(second.metadata.get("cached"))
        self.assertEqual(second.bindings, [{"x": "John"}])

    def test_execute_query_cache_key_distinguishes_options(self):
        store = self._fake_store()
        reasoner = SPARQLReasoner(
            triplet_store=store, enable_inference=False
        )
        query = "SELECT ?x WHERE { ?x a :Person }"

        reasoner.execute_query(query, graph="urn:g1")
        second = reasoner.execute_query(query, graph="urn:g2")

        # Different options: the second call must hit the store again
        # with its own options instead of returning the cached result.
        self.assertFalse(second.metadata.get("cached"))
        self.assertEqual(store.received[1], {"graph": "urn:g2"})

    def test_execute_query_rdflib_fallback_coerces_non_string_values(self):
        """Non-string triplet values must not be silently dropped."""

        class MixedStore:
            def get_triplets(self):
                return [
                    SimpleNamespace(
                        subject="urn:alice", predicate="urn:age", object=42
                    )
                ]

        reasoner = SPARQLReasoner(
            triplet_store=MixedStore(), enable_inference=False
        )

        result = reasoner.execute_query(
            "SELECT ?o WHERE { ?s <urn:age> ?o }"
        )

        self.assertEqual(result.bindings, [{"o": "42"}])

    def test_execute_query_rdflib_fallback_construct(self):
        reasoner = SPARQLReasoner(
            triplet_store=self._triplet_only_store(), enable_inference=False
        )

        result = reasoner.execute_query(
            "CONSTRUCT { ?s <urn:employer> ?o } WHERE { ?s <urn:worksAt> ?o }"
        )

        self.assertEqual(result.metadata.get("result_type"), "CONSTRUCT")
        self.assertIn(
            ("urn:alice", "urn:employer", "ACME"),
            result.metadata.get("triples", []),
        )

    def test_abductive_reasoner_generate_hypotheses(self):
        reasoner = AbductiveReasoner()
        reasoner.reasoner.add_rule("IF Disease(Flu) THEN Symptom(Fever)")
        
        obs = Observation(observation_id="o1", description="Symptom(Fever)")
        hypotheses = reasoner.generate_hypotheses([obs])
        
        self.assertEqual(len(hypotheses), 1)
        self.assertEqual(hypotheses[0].premises, ["Disease(Flu)"])

    def test_abductive_reasoner_rank_hypotheses(self):
        reasoner = AbductiveReasoner(ranking_strategy="simplicity")
        
        h1 = reasoner.generate_hypotheses([Observation("o1", "Symptom(Fever)")]) # dummy, just to get objects
        # Create custom hypotheses for testing ranking
        from semantica.reasoning.abductive_reasoner import Hypothesis
        hyp1 = Hypothesis("h1", "Expl 1", premises=["P1"], simplicity=0.5)
        hyp2 = Hypothesis("h2", "Expl 2", premises=["P1", "P2"], simplicity=0.3)
        
        ranked = reasoner.rank_hypotheses([hyp1, hyp2])
        self.assertEqual(ranked[0].hypothesis_id, "h1") # simpler is better

    def test_deductive_reasoner_apply_logic(self):
        reasoner = DeductiveReasoner()
        reasoner.reasoner.add_rule("IF Person(?x) AND Parent(?x, ?y) THEN Child(?y, ?x)")
        
        premises = [
            Premise("p1", "Person(John)"),
            Premise("p2", "Parent(John, Jane)")
        ]
        
        conclusions = reasoner.apply_logic(premises)
        self.assertEqual(len(conclusions), 1)
        self.assertEqual(conclusions[0].statement, "Child(Jane, John)")

    def test_deductive_reasoner_prove_theorem(self):
        reasoner = DeductiveReasoner()
        reasoner.reasoner.add_rule("IF Person(?x) AND Parent(?x, ?y) THEN Child(?y, ?x)")
        reasoner.add_facts(["Person(John)", "Parent(John, Jane)"])
        
        proof = reasoner.prove_theorem("Child(Jane, John)")
        self.assertTrue(proof.valid)
        self.assertEqual(proof.theorem, "Child(Jane, John)")
        self.assertEqual(len(proof.steps), 1)
        self.assertEqual(proof.steps[0].statement, "Child(Jane, John)")

if __name__ == "__main__":
    unittest.main()
