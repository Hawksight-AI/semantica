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

class TestExecuteQueryReviewFixes(unittest.TestCase):
    """Regression tests for the bot-review fixes on PR #1243."""

    RDF_TYPE = "http://www.w3.org/1999/02/22-rdf-syntax-ns#type"

    def _triplet(self, subject, predicate, obj, metadata=None):
        return SimpleNamespace(
            subject=subject, predicate=predicate, object=obj, metadata=metadata
        )

    def _store(self, triplets):
        class TripletOnlyStore:
            def get_triplets(self):
                return list(triplets)

        return TripletOnlyStore()

    def test_execute_query_coerces_list_of_binding_dicts(self):
        """Stores returning a list of binding rows keep their rows (Qodo)."""

        class ListStore:
            def execute_query(self, query, **options):
                return [{"x": "a"}, "junk", {"y": "b"}]

        reasoner = SPARQLReasoner(triplet_store=ListStore(), enable_inference=False)

        result = reasoner.execute_query("SELECT ?x ?y WHERE { ?x ?y ?z }")

        self.assertEqual(result.bindings, [{"x": "a"}, {"y": "b"}])
        self.assertEqual(result.variables, ["x", "y"])

    def test_execute_query_empty_fallback_graph_raises_processing_error(self):
        """An empty fallback graph must be refused, not read as 'no matches'."""
        reasoner = SPARQLReasoner(
            triplet_store=self._store([]), enable_inference=False
        )

        with self.assertRaises(ProcessingError):
            reasoner.execute_query("SELECT ?s ?p ?o WHERE { ?s ?p ?o }")

    def test_execute_query_fallback_graph_empty_after_invalid_triplets(self):
        """Triplets dropped for missing fields still leave a usable store:
        the empty graph must be refused the same way."""
        reasoner = SPARQLReasoner(
            triplet_store=self._store([self._triplet(None, "urn:p", "urn:v")]),
            enable_inference=False,
        )

        with self.assertRaises(ProcessingError):
            reasoner.execute_query("SELECT ?s WHERE { ?s ?p ?o }")

    def test_execute_query_fallback_preserves_typed_literals(self):
        """Typed literals answer typed-literal queries (Codex/Qodo)."""
        reasoner = SPARQLReasoner(
            triplet_store=self._store(
                [
                    self._triplet(
                        "urn:alice",
                        "urn:age",
                        "42",
                        metadata={"datatype": "xsd:integer"},
                    ),
                    self._triplet("urn:bob", "urn:age", "42"),
                ]
            ),
            enable_inference=False,
        )

        result = reasoner.execute_query(
            'SELECT ?s WHERE { ?s <urn:age> "42"^^xsd:integer }'
        )

        self.assertEqual(result.bindings, [{"s": "urn:alice"}])

    def test_execute_query_fallback_literal_datatype_key(self):
        """The ``literal_datatype`` metadata key types the literal too."""
        reasoner = SPARQLReasoner(
            triplet_store=self._store(
                [
                    self._triplet(
                        "urn:carol",
                        "urn:age",
                        "42",
                        metadata={"literal_datatype": "xsd:integer"},
                    )
                ]
            ),
            enable_inference=False,
        )

        result = reasoner.execute_query(
            'SELECT ?s WHERE { ?s <urn:age> "42"^^xsd:integer }'
        )

        self.assertEqual(result.bindings, [{"s": "urn:carol"}])

    def test_execute_query_fallback_unknown_datatype_degrades_to_plain_literal(self):
        """An unresolvable datatype degrades instead of failing the query."""
        reasoner = SPARQLReasoner(
            triplet_store=self._store(
                [
                    self._triplet(
                        "urn:alice",
                        "urn:age",
                        "42",
                        metadata={"datatype": "not-a-real-prefix:x"},
                    )
                ]
            ),
            enable_inference=False,
        )

        result = reasoner.execute_query('SELECT ?s WHERE { ?s <urn:age> "42" }')

        self.assertEqual(result.bindings, [{"s": "urn:alice"}])

    def test_execute_query_fallback_preserves_language_tags(self):
        """Language-tagged literals answer language-tagged queries."""
        reasoner = SPARQLReasoner(
            triplet_store=self._store(
                [
                    self._triplet(
                        "urn:alice",
                        "urn:label",
                        "hello",
                        metadata={"lang": "en"},
                    ),
                    self._triplet(
                        "urn:bob",
                        "urn:label",
                        "hello",
                        metadata={"language": "fr"},
                    ),
                ]
            ),
            enable_inference=False,
        )

        result = reasoner.execute_query(
            'SELECT ?s WHERE { ?s <urn:label> "hello"@en }'
        )

        self.assertEqual(result.bindings, [{"s": "urn:alice"}])

    def test_execute_query_fallback_supports_blank_node_subjects(self):
        reasoner = SPARQLReasoner(
            triplet_store=self._store(
                [self._triplet("_:b1", "urn:worksAt", "ACME")]
            ),
            enable_inference=False,
        )

        result = reasoner.execute_query("SELECT ?s WHERE { ?s <urn:worksAt> ?o }")

        self.assertEqual([b["s"] for b in result.bindings], ["b1"])

    def test_infer_results_preserves_duplicate_original_bindings(self):
        """Original rows keep SPARQL bag semantics (Qodo): duplicates in,
        duplicates out; only inferred rows are de-duplicated."""
        reasoner = SPARQLReasoner()
        reasoner.add_inference_rule("IF ?x is_a Person THEN ?x is_a Human")

        results = SPARQLQueryResult(
            bindings=[{"x": "John"}, {"x": "John"}], variables=["x"]
        )

        inferred = reasoner.infer_results(results)

        originals = [b for b in inferred.bindings if "x_type" not in b]
        self.assertEqual(originals, [{"x": "John"}, {"x": "John"}])
        self.assertEqual(inferred.metadata["original_count"], 2)
        self.assertEqual(inferred.metadata["inferred_count"], 1)

    def test_infer_results_handles_unhashable_binding_values(self):
        """Binding rows with dict values (SPARQL JSON form) must not crash
        the de-duplication with TypeError (Codex)."""
        reasoner = SPARQLReasoner()
        reasoner.add_inference_rule("IF ?x is_a Person THEN ?x is_a Human")

        results = SPARQLQueryResult(
            bindings=[{"x": {"nested": [1]}}], variables=["x"]
        )

        inferred = reasoner.infer_results(results)

        self.assertEqual(inferred.bindings[0]["x"], {"nested": [1]})
        self.assertEqual(inferred.metadata["inferred_count"], 1)
        # The inferred row must not share mutable state with the original.
        inferred.bindings[1]["x"]["nested"].append(99)
        self.assertEqual(inferred.bindings[0]["x"], {"nested": [1]})

    def test_execute_query_cache_isolates_nested_structures(self):
        """Cached results are deep-copied: nested binding values and
        metadata entries must never be shared (Qodo/Codex)."""

        class NestedStore:
            def execute_query(self, query, **options):
                return {
                    "bindings": [{"x": {"nested": [1]}}],
                    "variables": ["x"],
                    "metadata": {"triples": [("urn:s", "urn:p", "urn:o")]},
                }

        reasoner = SPARQLReasoner(
            triplet_store=NestedStore(), enable_inference=False
        )
        query = "SELECT ?x WHERE { ?x ?p ?o }"

        first = reasoner.execute_query(query)
        first.bindings[0]["x"]["nested"].append(99)
        first.metadata["triples"].append("junk")

        second = reasoner.execute_query(query)
        self.assertTrue(second.metadata.get("cached"))
        second.bindings[0]["x"]["nested"].append(99)
        second.metadata["triples"].append("junk")

        third = reasoner.execute_query(query)
        self.assertEqual(third.bindings, [{"x": {"nested": [1]}}])
        self.assertEqual(
            third.metadata["triples"], [("urn:s", "urn:p", "urn:o")]
        )

    def test_execute_query_fallback_materializes_is_a_rules(self):
        """Matches that only exist through inference satisfy the WHERE
        clause: rules are materialized before the query runs (Qodo)."""
        reasoner = SPARQLReasoner(
            triplet_store=self._store(
                [
                    self._triplet(
                        "urn:alice", self.RDF_TYPE, "http://example.org/Employee"
                    )
                ]
            ),
            enable_inference=True,
        )
        reasoner.add_inference_rule("IF ?x is_a Employee THEN ?x is_a Person")

        result = reasoner.execute_query(
            "SELECT ?s WHERE { ?s a <http://example.org/Person> }"
        )

        self.assertEqual(result.bindings, [{"s": "urn:alice"}])
        self.assertEqual(result.metadata.get("inferred_triples"), 1)

    def test_execute_query_fallback_materialization_reaches_fixpoint(self):
        """Rule chains fire through fixpoint iteration, one pass at a time."""
        reasoner = SPARQLReasoner(
            triplet_store=self._store(
                [
                    self._triplet(
                        "urn:alice", self.RDF_TYPE, "http://example.org/Employee"
                    )
                ]
            ),
            enable_inference=True,
        )
        reasoner.add_inference_rule("IF ?x is_a Employee THEN ?x is_a Manager")
        reasoner.add_inference_rule("IF ?x is_a Manager THEN ?x is_a Person")

        result = reasoner.execute_query(
            "SELECT ?s WHERE { ?s a <http://example.org/Person> }"
        )

        self.assertEqual(result.bindings, [{"s": "urn:alice"}])
        self.assertEqual(result.metadata.get("inferred_triples"), 2)

    def test_execute_query_fallback_skips_unmaterializable_rules(self):
        """Rules whose conditions are not plain ``is_a`` patterns cannot be
        materialized into triples; they are skipped instead of breaking the
        query (result-level inference still handles them)."""
        reasoner = SPARQLReasoner(
            triplet_store=self._store(
                [self._triplet("urn:alice", "urn:worksAt", "ACME")]
            ),
            enable_inference=True,
        )
        reasoner.add_inference_rule("IF ?x worksAt ACME THEN ?x is_a Employee")

        result = reasoner.execute_query(
            "SELECT ?s ?o WHERE { ?s <urn:worksAt> ?o }"
        )

        self.assertEqual(result.bindings, [{"s": "urn:alice", "o": "ACME"}])
        self.assertNotIn("inferred_triples", result.metadata)


if __name__ == "__main__":
    unittest.main()
