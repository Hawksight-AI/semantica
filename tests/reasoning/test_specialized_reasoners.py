import unittest
from semantica.reasoning.sparql_reasoner import SPARQLReasoner, SPARQLQueryResult
from semantica.reasoning.abductive_reasoner import AbductiveReasoner, Observation, HypothesisRanking
from semantica.reasoning.deductive_reasoner import DeductiveReasoner, Premise, Argument
from semantica.reasoning.reasoner import Rule

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

    def test_execute_query_raises_not_implemented(self):
        """Empty results must not pass as a valid answer (issue #1083).

        Both branches returned ``SPARQLQueryResult(bindings=[], variables=[])``
        -- with or without a triplet store -- so callers that trust an empty
        result as "no matches" silently drew wrong conclusions. Until a real
        execution path lands, refusing loudly is safer.
        """
        reasoner = SPARQLReasoner()
        with self.assertRaises(NotImplementedError):
            reasoner.execute_query("SELECT ?s ?p ?o WHERE { ?s ?p ?o }")

    def test_execute_query_with_triplet_store_raises_not_implemented(self):
        reasoner = SPARQLReasoner(triplet_store=object())
        with self.assertRaises(NotImplementedError):
            reasoner.execute_query("SELECT ?s ?p ?o WHERE { ?s ?p ?o }")

    def test_execute_query_error_explains_why_the_query_is_refused(self):
        reasoner = SPARQLReasoner()
        with self.assertRaises(NotImplementedError) as ctx:
            reasoner.execute_query("SELECT ?s WHERE { ?s ?p ?o }")
        self.assertIn("not implemented", str(ctx.exception))

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
