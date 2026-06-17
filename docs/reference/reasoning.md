---
title: "Reasoning Module"
description: "Forward chaining, Rete, deductive, abductive, SPARQL, Datalog, and temporal reasoning with explainable inference paths."
icon: "microchip"
---

`semantica.reasoning` derives new knowledge from existing facts using logical rules:

- Six reasoning engines: forward chaining, Rete, SPARQL, Datalog, temporal, and LLM-powered GraphReasoner
- Every engine produces explainable inference paths: traceable chains of rules and facts
- `DatalogReasoner` guarantees termination via semi-naive fixpoint evaluation
- `TemporalReasoningEngine` implements all 13 Allen interval algebra relations
- `ExplanationGenerator` produces step-by-step natural-language justifications


## Exported Classes

| Class | Role |
| :--- | :--- |
| `Reasoner` | Forward-chaining inference: `add_fact`, `add_rule`, `forward_chain`, `backward_chain`, `infer_facts` |
| `GraphReasoner` | LLM-powered reasoning over a KG dict: answers natural language queries via `reason(graph, query)` |
| `ReteEngine` | Rete pattern matching: `build_network`, `add_fact`, `match_patterns`, `execute_matches` |
| `SPARQLReasoner` | Rule-based SPARQL query expansion via `execute_query`, `expand_query`, `infer_results` |
| `DatalogReasoner` | Recursive Horn clause rules with semi-naive fixpoint: `add_fact`, `add_rule`, `derive_all`, `query` |
| `TemporalReasoningEngine` | All 13 Allen interval algebra relations: `relation(a, b)`, `overlaps`, `contains`, `active_at` |
| `ExplanationGenerator` | Step-by-step explanations via `generate_explanation(inference_result)` |
| `Rule` | IF/THEN rule: `{rule_id, name, conditions, conclusion, rule_type, confidence, priority}` |
| `Fact` | Working-memory fact: `{fact_id, predicate, arguments}` |
| `InferenceResult` | Single derived conclusion: `{conclusion, rule_used, premises, confidence}` |


## Which Engine Should I Use?

<CardGroup cols={2}>
  <Card title="Reasoner" icon="arrow-right-arrow-left" href="#reasoner-forwardbackward-chaining">
    IF/THEN rules, forward and backward chaining. **Start here**: covers 90% of use cases. No query language required.
  </Card>
  <Card title="GraphReasoner" icon="robot" href="#graphreasoner">
    Natural language queries over a knowledge graph via LLM. No SPARQL or rules: just ask a question.
  </Card>
  <Card title="DatalogReasoner" icon="code" href="#datalogreasoner">
    Recursive Horn clause rules with guaranteed termination. Use for complex multi-hop transitive rules.
  </Card>
  <Card title="ReteEngine" icon="bolt" href="#reteengine">
    Rete pattern matching for high-frequency inference. Use when you need to match many facts against many rules simultaneously.
  </Card>
  <Card title="SPARQLReasoner" icon="database" href="#sparqlreasoner">
    SPARQL query expansion and rule-based inference. Use when you're working with RDF/OWL data.
  </Card>
  <Card title="TemporalReasoningEngine" icon="clock" href="#temporalreasoningengine">
    All 13 Allen interval algebra relations. Use for time-aware reasoning: overlaps, before/after, during, contains.
  </Card>
</CardGroup>


## Getting Started

The most common pattern is the `Reasoner` for IF/THEN forward-chaining:

```python
from semantica.reasoning import Reasoner, Rule, RuleType

reasoner = Reasoner()

# Add facts as strings in predicate(args) form
reasoner.add_fact("Manager(Alice)")
reasoner.add_fact("Employee(Alice)")

# Add an IF-THEN rule using the string form
reasoner.add_rule("IF Manager(?x) THEN HasAuthority(?x)")

# Run forward chaining: returns List[InferenceResult]
results = reasoner.forward_chain()
for r in results:
    print(r.conclusion)         # "HasAuthority(Alice)"
    print(r.confidence)         # 1.0
    if r.rule_used:
        print(r.rule_used.name) # name of the rule applied
```

Or build rules programmatically using the `Rule` dataclass:

```python
from semantica.reasoning import Rule, RuleType

rule = Rule(
    rule_id="rule_001",
    name="manager_authority",
    conditions=["Manager(?x)"],
    conclusion="HasAuthority(?x)",
    rule_type=RuleType.IMPLICATION,
    confidence=0.9,
)
reasoner.add_rule(rule)
```


## Reasoner (Forward/Backward Chaining)

**`Reasoner`** is the unified entry point for rule-based inference: iterates facts and rules to a **fixpoint**, then optionally proves a specific goal via backward chaining:

```python
from semantica.reasoning import Reasoner, Rule, RuleType, InferenceResult

reasoner = Reasoner()

# Facts can be strings, KG entity dicts, or KG relationship dicts
reasoner.add_fact("Manager(John)")
reasoner.add_fact("Employee(John)")

# IF-THEN string form
reasoner.add_rule("IF Manager(?x) AND Employee(?x) THEN SeniorStaff(?x)")

# Forward chaining: iterates until fixpoint
results = reasoner.forward_chain()
for r in results:
    print(r.conclusion)   # e.g. "SeniorStaff(John)"
    print(r.premises)     # list of premise strings matched
    print(r.confidence)   # float

# Backward chaining: prove a specific goal
result = reasoner.backward_chain("SeniorStaff(John)", max_depth=10)
if result:
    print(f"Proven: {result.conclusion}")
    print(f"Premises: {result.premises}")

# infer_facts() loads facts and rules in one call, returns conclusion strings
conclusions = reasoner.infer_facts(
    facts=["Manager(Alice)", "Employee(Alice)"],
    rules=["IF Manager(?x) THEN HasAuthority(?x)"],
)
# → ["HasAuthority(Alice)"]
```

### Reasoner Methods

| Method | Returns | Description |
| :------ | :------- | :----------- |
| `add_fact(fact)` | `None` | Add a string, entity dict, or relationship dict to working memory |
| `add_rule(rule)` | `Rule` | Add a `Rule` object or IF-THEN string; rules are sorted by `priority` descending |
| `forward_chain()` | `List[InferenceResult]` | Derive all possible conclusions iteratively until fixpoint |
| `backward_chain(goal, max_depth)` | `InferenceResult \| None` | Prove a specific goal string, returns `None` if unprovable |
| `infer_facts(facts, rules)` | `List[str]` | Load facts and rules then run `forward_chain()`, returns conclusion strings |
| `clear()` | `None` | Clear all facts and rules |
| `reset()` | `None` | Alias for `clear()` |

### Rule and Fact dataclass fields

```python
from semantica.reasoning import Rule, Fact, RuleType

# Rule: all fields
rule = Rule(
    rule_id="rule_001",            # required: unique identifier
    name="manager_authority",      # required: display name
    conditions=["Manager(?x)"],    # list of condition strings
    conclusion="HasAuthority(?x)", # conclusion string
    rule_type=RuleType.IMPLICATION, # IMPLICATION | EQUIVALENCE | CONSTRAINT | TRANSFORMATION
    confidence=1.0,                 # default 1.0
    priority=0,                     # higher priority rules run first
)

# Fact: for working with the Rete engine directly
from semantica.reasoning import Fact
fact = Fact(
    fact_id="f001",                # required: unique identifier
    predicate="Manager",
    arguments=["John"],
    metadata={},
)
```


## GraphReasoner

**`GraphReasoner`** uses an LLM to answer **natural language queries** over a knowledge graph dict: no SPARQL or rule authoring required:

```python
from semantica.reasoning import GraphReasoner

# Initialize: uses openai by default; override via kwargs
reasoner = GraphReasoner(provider="openai", model="gpt-4o-mini")

kg = {
    "entities": [
        {"id": "alice",   "name": "Alice",   "type": "Person",       "properties": {"role": "CEO"}},
        {"id": "acme",    "name": "Acme Inc", "type": "Organization"},
    ],
    "relationships": [
        {"source": "alice", "target": "acme", "type": "leads"}
    ],
}

answer: str = reasoner.reason(
    graph=kg,
    query="Who leads Acme Inc. and what is their role?"
)
print(answer)
```

`reason()` converts the graph to a text context and calls the LLM with a structured prompt. Returns a plain string answer.


## ReteEngine

High-performance Rete pattern matching for large rule sets:

```python
from semantica.reasoning import ReteEngine, Rule, Fact, RuleType

engine = ReteEngine()

# Build the Rete network from a list of Rule objects
rules = [
    Rule(
        rule_id="r1",
        name="manager_authority",
        conditions=["Manager(?x)"],
        conclusion="HasAuthority(?x)",
    )
]
engine.build_network(rules)

# Add facts to working memory
engine.add_fact(Fact(fact_id="f1", predicate="Manager", arguments=["Alice"]))

# Match patterns and execute
matches = engine.match_patterns()
results = engine.execute_matches(matches)
# results is a list of conclusion values from matched rules

# Network statistics
stats = engine.get_network_stats()
# → {"total_nodes": N, "alpha_nodes": A, "beta_nodes": B, "terminal_nodes": T, "facts": F}

engine.reset()
```

### ReteEngine Methods

| Method | Returns | Description |
| :------ | :------- | :----------- |
| `build_network(rules)` | `None` | Build the Rete network from a list of `Rule` objects |
| `add_fact(fact)` | `None` | Add a `Fact` to working memory and propagate through the network |
| `match_patterns(facts)` | `List[Match]` | Match all patterns; optionally add facts before matching |
| `execute_matches(matches)` | `List[Any]` | Execute matched rules and return their conclusion values |
| `reset()` | `None` | Clear facts and all node activation state |
| `get_network_stats()` | `dict` | Return counts of alpha, beta, terminal nodes and facts |


## SPARQLReasoner

**`SPARQLReasoner`** extends SPARQL with **inference rule expansion**: add IF-THEN rules and they are automatically woven into queries before execution:

```python
from semantica.reasoning import SPARQLReasoner

reasoner = SPARQLReasoner()

# Add an inference rule (IF-THEN string form)
reasoner.add_inference_rule("IF is_a(?x, Manager) THEN has_authority(?x)")

# Execute a query: returns SPARQLQueryResult
result = reasoner.execute_query("""
    PREFIX ex: <http://example.org/>
    SELECT ?person ?company WHERE {
        ?person ex:founded ?company .
        ?company ex:located_in ex:SiliconValley .
    }
""")

for row in result.bindings:
    print(row)   # each row is a dict of variable → {"value": ..., "type": ...}

# Expand a query with inference rules (returns modified query string)
expanded = reasoner.expand_query("SELECT ?x WHERE { ?x a :Manager }")

# Infer additional bindings from existing results
enriched = reasoner.infer_results(result)
```

### SPARQLReasoner Constructor

```python
SPARQLReasoner(
    config=None,         # optional config dict
    triplet_store=None,  # optional TripletStore instance for live query execution
    enable_inference=True,
)
```

<Note>
  `execute_query()` returns empty bindings when no `triplet_store` is configured. Pass a `TripletStore` instance via the `triplet_store=` kwarg to execute queries against a live backend.
</Note>


## DatalogReasoner

Pure-Python bottom-up semi-naive fixpoint evaluation for recursive Horn clause rules. Termination is **guaranteed**: the engine detects fixpoint convergence and stops:

```python
from semantica.reasoning import DatalogReasoner, DatalogFact

datalog = DatalogReasoner()

# Add base facts: string form is the simplest
datalog.add_fact("parent(alice, bob)")
datalog.add_fact("parent(bob, charlie)")

# Or use DatalogFact directly (args is a tuple of strings)
datalog.add_fact(DatalogFact(predicate="parent", args=("charlie", "dave")))

# Add recursive rules using Horn clause syntax
datalog.add_rule("ancestor(X, Y) :- parent(X, Y).")
datalog.add_rule("ancestor(X, Z) :- parent(X, Y), ancestor(Y, Z).")

# Evaluate to fixpoint: returns all derived fact strings
all_facts = datalog.derive_all()
# e.g. ["parent(alice, bob)", "parent(bob, charlie)", ..., "ancestor(alice, bob)", ...]

# Query with variable pattern: variables start with uppercase or ?
results = datalog.query("ancestor(alice, ?Z)")
# → [{"Z": "bob"}, {"Z": "charlie"}, {"Z": "dave"}]

# Clear and start over
datalog.clear()
```

### DatalogFact, DatalogRule fields

```python
from semantica.reasoning import DatalogFact, DatalogRule

# DatalogFact: ground fact; args must all be constants (lowercase start)
fact = DatalogFact(predicate="parent", args=("alice", "bob"))

# DatalogRule: parsed from string; head and body are set by the parser
# Use add_rule("head(X, Y) :- body(X, Z), body2(Z, Y)."): do not construct directly
```

### DatalogReasoner Methods

| Method | Returns | Description |
| :------ | :------- | :----------- |
| `add_fact(fact)` | `None` | Add string, dict, or `DatalogFact`; constants must be lowercase-starting |
| `add_rule(rule_str)` | `None` | Parse and add a Horn clause string like `"ancestor(X,Y) :- parent(X,Y)."` |
| `derive_all()` | `List[str]` | Run semi-naive fixpoint evaluation; returns all facts as strings |
| `query(pattern)` | `List[dict]` | Query derived facts: auto-runs `derive_all()` if needed |
| `load_from_graph(graph)` | `int` | Load a ContextGraph's nodes/edges as Datalog facts; returns count added |
| `clear()` | `None` | Clear all facts and rules |


## TemporalReasoningEngine

Pure-Python Allen interval algebra: all 13 relations, no LLM calls:

```python
from datetime import datetime
from semantica.reasoning import TemporalReasoningEngine, TemporalInterval, IntervalRelation

engine = TemporalReasoningEngine()

ceo_tenure   = TemporalInterval(start=datetime(1997, 9, 16), end=datetime(2011, 8, 24))
board_member = TemporalInterval(start=datetime(2000, 1,  1), end=datetime(2012, 6,  1))

# Compute Allen relation: method is relation(), not get_relation()
rel = engine.relation(ceo_tenure, board_member)
# → IntervalRelation.DURING  (ceo_tenure is fully inside board_member)

# Other helpers
engine.overlaps(ceo_tenure, board_member)   # bool
engine.contains(board_member, ceo_tenure)   # bool

# Is a given point in time inside an interval?
engine.active_at(ceo_tenure, datetime(2005, 6, 1))   # True
```

All 13 Allen interval algebra relations:

| Relation | Meaning |
| :-------- | :------- |
| `BEFORE` | A ends before B starts |
| `MEETS` | A ends exactly when B starts |
| `OVERLAPS` | A starts before B, ends inside B |
| `DURING` | A is fully inside B |
| `STARTS` | A and B start together, A ends first |
| `FINISHES` | A and B end together, A starts later |
| `EQUALS` | Identical intervals |
| `AFTER` | Inverse of BEFORE |
| `MET_BY` | Inverse of MEETS |
| `OVERLAPPED_BY` | Inverse of OVERLAPS |
| `CONTAINS` | Inverse of DURING |
| `STARTED_BY` | Inverse of STARTS |
| `FINISHED_BY` | Inverse of FINISHES |

<Note>
  `TemporalInterval.start` expects a `datetime` object, not a string. Import `datetime` from the standard library and construct intervals with `datetime(year, month, day)`.
</Note>


## ExplanationGenerator

Generate structured explanations for any `InferenceResult`:

```python
from semantica.reasoning import ExplanationGenerator, Reasoner, Rule

reasoner = Reasoner()
reasoner.add_fact("Manager(John)")
reasoner.add_rule("IF Manager(?x) THEN HasAuthority(?x)")
results = reasoner.forward_chain()

# ExplanationGenerator takes no positional args
generator = ExplanationGenerator()

# Pass an InferenceResult object: not a dict
explanation = generator.generate_explanation(results[0])

print(f"Type:       {explanation.explanation_type}")   # "inference"
print(f"Conclusion: {explanation.conclusion}")
print(f"NL:         {explanation.natural_language}")

if explanation.reasoning_path:
    for step in explanation.reasoning_path.steps:
        print(f"  Step {step.step_id}: {step.description}")
        if step.rule_applied:
            print(f"    Rule: {step.rule_applied.name}")

# Justify a conclusion with a reasoning path
path = generator.show_reasoning_path(results[0])
justification = generator.justify_conclusion(results[0].conclusion, path)
print(justification.explanation_text)
```

### ExplanationGenerator Methods

| Method | Returns | Description |
| :------ | :------- | :----------- |
| `generate_explanation(reasoning)` | `Explanation` | Generate structured explanation for an `InferenceResult`, `Proof`, or abductive result |
| `show_reasoning_path(reasoning)` | `ReasoningPath` | Extract and return the reasoning path from any result |
| `justify_conclusion(conclusion, path)` | `Justification` | Build a `Justification` with evidence and NL text for a conclusion |

### Key dataclass fields

```python
# Explanation
explanation.explanation_id    # str
explanation.explanation_type  # "inference" | "proof" | "abductive" | "generic"
explanation.conclusion        # conclusion value
explanation.reasoning_path    # ReasoningPath | None
explanation.natural_language  # NL string (when generate_nl=True, the default)

# ReasoningStep
step.step_id        # str
step.description    # str
step.rule_applied   # Rule | None  (NOT rule_name)
step.input_facts    # List[Any]
step.output_fact    # Any
step.confidence     # float
```


## Engine Selection Guide

| Engine | Best For | Termination | Key Method |
| :------ | :-------- | :----------- | :---------- |
| `Reasoner` | Simple IF/THEN rules | Always (with `max_iterations` cap) | `forward_chain()` |
| `GraphReasoner` | NL queries over a KG via LLM | Always | `reason(graph, query)` |
| `ReteEngine` | Large rule sets with many facts | Always | `match_patterns()` |
| `SPARQLReasoner` | Rule-augmented SPARQL queries | Always | `execute_query()` |
| `DatalogReasoner` | Recursive rules (ancestry, reachability) | Guaranteed fixpoint | `derive_all()` / `query()` |
| `TemporalReasoningEngine` | Time interval relationships | Always | `relation(a, b)` |

<Tip>
  For recursive rules (e.g. ancestor, reachability, transitivity), use `DatalogReasoner`: it guarantees termination via semi-naive bottom-up fixpoint evaluation. `Reasoner.forward_chain()` has a `max_iterations` cap (default 50) and will silently stop early with deep recursion.
</Tip>

<Warning>
  `GraphReasoner` requires a configured LLM provider. If the provider fails to initialize, `reason()` returns an error string instead of raising. Check `reasoner.provider is not None` before calling if you need to surface failures explicitly.
</Warning>

<CardGroup cols={2}>
  <Card title="Knowledge Graph" icon="diagram-project" href="kg">
    The knowledge graph being reasoned over.
  </Card>
  <Card title="Ontology" icon="sitemap" href="ontology">
    Ontology axioms and SHACL constraints for logical reasoning.
  </Card>
  <Card title="Triplet Store" icon="table" href="triplet_store">
    RDF backend for SPARQL-based reasoning.
  </Card>
  <Card title="Context" icon="brain" href="context">
    Reasoning integrated into agent decision intelligence.
  </Card>
</CardGroup>
