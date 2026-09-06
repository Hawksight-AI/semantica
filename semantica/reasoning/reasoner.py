"""
Reasoner Module

This module provides a high-level Reasoner class that unifies various reasoning strategies
supported by the Semantica framework. It serves as a facade for different reasoning engines.
"""

import re
import uuid
from collections.abc import Mapping, Sequence, Set as AbstractSet
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Callable, Dict, List, Optional, Set, Tuple, Union

from ..utils.logging import get_logger
from ..utils.progress_tracker import get_progress_tracker


class RuleType(Enum):
    """Rule types."""
    IMPLICATION = "implication"
    EQUIVALENCE = "equivalence"
    CONSTRAINT = "constraint"
    TRANSFORMATION = "transformation"


def _substitute_variables(template: str, bindings: Dict[str, str]) -> str:
    """Substitute ``?var`` placeholders with their bound values, token-aware.

    A naive ``str.replace(f"?{var}", value)`` corrupts placeholders that share
    a prefix -- e.g. binding ``?x`` would also rewrite the ``?x`` inside ``?xy``.
    We replace every ``?word`` token in a single regex pass so that only whole
    variable names are matched (``\\w+`` never partially matches a longer name),
    leaving unbound placeholders untouched.
    """
    if not bindings:
        return template

    def _replace(match: "re.Match") -> str:
        var_name = match.group(1)
        # Preserve unbound placeholders verbatim.
        return str(bindings[var_name]) if var_name in bindings else match.group(0)

    return re.sub(r"\?(\w+)", _replace, template)


def _canonicalize_activation_value(
    value: Any, active_containers: Optional[Dict[int, int]] = None
) -> Tuple[Any, ...]:
    """Convert nested activation data into a deterministic, hashable value."""
    if active_containers is None:
        active_containers = {}

    value_type = (type(value).__module__, type(value).__qualname__)
    is_mapping = isinstance(value, Mapping)
    is_sequence = isinstance(value, Sequence) and not isinstance(
        value, (str, bytes, bytearray)
    )
    is_set = isinstance(value, AbstractSet) and not isinstance(
        value, (str, bytes, bytearray)
    )
    if not (is_mapping or is_sequence or is_set):
        return ("scalar", value_type, repr(value))

    object_id = id(value)
    if object_id in active_containers:
        return ("reference", active_containers[object_id])
    active_containers[object_id] = len(active_containers)

    try:
        if is_mapping:
            keyed_items = [
                (
                    _canonicalize_activation_value(key, active_containers),
                    item,
                )
                for key, item in value.items()
            ]
            keyed_items.sort(key=lambda entry: repr(entry[0]))
            entries = tuple(
                (
                    key,
                    _canonicalize_activation_value(item, active_containers),
                )
                for key, item in keyed_items
            )
            return ("mapping", value_type, entries)
        if is_sequence:
            return (
                "sequence",
                value_type,
                tuple(
                    _canonicalize_activation_value(item, active_containers)
                    for item in value
                ),
            )
        items = tuple(
            sorted(
                (
                    _canonicalize_activation_value(item, active_containers)
                    for item in value
                ),
                key=repr,
            )
        )
        return ("set", value_type, items)
    finally:
        del active_containers[object_id]


def _make_activation_key(
    rule_id: str, bindings: Dict[str, Any], fact_tokens: List[Any]
) -> Tuple[Any, ...]:
    """Return a stable identity for one concrete rule activation."""
    canonical_bindings = tuple(
        sorted(
            (str(name), _canonicalize_activation_value(value))
            for name, value in bindings.items()
        )
    )
    return (
        rule_id,
        canonical_bindings,
        tuple(
            sorted(
                (_canonicalize_activation_value(token) for token in fact_tokens),
                key=repr,
            )
        ),
    )


def _parse_fact(fact: str) -> Optional[Tuple[str, List[str]]]:
    """Parse a ``Predicate(arg1, arg2, ...)`` fact string.

    Returns ``(predicate, [args])`` or ``None`` when the fact is not in the
    canonical predicate form (e.g. a bare atom). Whitespace around args is
    stripped and empty arg lists are supported (``Foo()`` -> ``("Foo", [])``).
    """
    match = re.match(r"^\s*([^()\s]+)\s*\((.*)\)\s*$", fact)
    if not match:
        return None
    predicate = match.group(1)
    inner = match.group(2).strip()
    if not inner:
        return predicate, []
    args = [arg.strip() for arg in inner.split(",")]
    return predicate, args


def _write_fact_to_graph(graph: Any, fact: str, *, retract: bool = False) -> None:
    """Persist (or remove) a fact against a knowledge-graph-like target.

    Write-back follows an explicit, ordered protocol so that
    ``AssertAction(write_back=True)`` never silently no-ops:

    1. If the target exposes an explicit fact API (``add_fact`` / ``assert_fact``
       for asserts, ``remove_fact`` / ``retract_fact`` / ``discard_fact`` for
       retracts), that is used verbatim.
    2. Otherwise, if the target looks like the canonical
       :class:`~semantica.kg.knowledge_graph.KnowledgeGraph` (has ``entities``
       and ``relationships`` lists), the fact is translated into a node
       (single-arg predicate) or relationship (two-arg predicate) and
       added/removed accordingly.
    3. Any other target, or a fact that cannot be translated, raises
       :class:`ValueError` so the failure surfaces instead of being swallowed.
    """
    if retract:
        for method_name in ("retract_fact", "remove_fact", "discard_fact"):
            method = getattr(graph, method_name, None)
            if callable(method):
                method(fact)
                return
    else:
        for method_name in ("add_fact", "assert_fact"):
            method = getattr(graph, method_name, None)
            if callable(method):
                method(fact)
                return

    entities = getattr(graph, "entities", None)
    relationships = getattr(graph, "relationships", None)
    if isinstance(entities, list) and isinstance(relationships, list):
        parsed = _parse_fact(fact)
        if parsed is None:
            raise ValueError(
                f"Cannot translate fact {fact!r} into graph node/relationship: "
                "expected canonical Predicate(args) form."
            )
        predicate, args = parsed
        if len(args) == 1:
            node = {"id": args[0], "type": predicate}
            if retract:
                _remove_matching(
                    entities,
                    lambda e: e.get("id") == args[0] and e.get("type") == predicate,
                )
            elif node not in entities:
                entities.append(node)
            return
        if len(args) == 2:
            rel = {"source": args[0], "target": args[1], "type": predicate}
            if retract:
                _remove_matching(
                    relationships,
                    lambda r: r.get("source") == args[0]
                    and r.get("target") == args[1]
                    and r.get("type") == predicate,
                )
            elif rel not in relationships:
                relationships.append(rel)
            return
        raise ValueError(
            f"Cannot write fact {fact!r} to graph: only unary (node) and binary "
            "(relationship) predicates are supported by the default adapter."
        )

    raise ValueError(
        f"knowledge_graph target {type(graph).__name__!r} does not expose a "
        "supported write-back API (add_fact/assert_fact or entities/relationships)."
    )


def _remove_matching(items: List[Dict[str, Any]], predicate: Callable[[Dict[str, Any]], bool]) -> None:
    """Remove in place every dict in ``items`` for which ``predicate`` is True."""
    items[:] = [item for item in items if not predicate(item)]

class Action:
    """Base class for an action fired when a rule matches.

    Actions turn the reasoner from a pure inference engine into a
    production-rule system: when a rule's conditions match, its actions run
    with the match's variable bindings, allowing side effects (asserting or
    retracting facts, calling external tools, emitting events) rather than
    only deriving a new fact.

    Subclasses implement :meth:`execute`, which receives the substituted
    ``bindings`` and the owning ``reasoner`` and returns an optional
    description of what happened (used for provenance / explanation).
    """

    def execute(self, bindings: Dict[str, str], reasoner: "Reasoner") -> Optional[str]:
        raise NotImplementedError

    @staticmethod
    def _substitute(template: str, bindings: Dict[str, str]) -> str:
        return _substitute_variables(template, bindings)


@dataclass
class AssertAction(Action):
    """Assert a new fact when the rule fires.

    ``fact`` may contain ``?var`` placeholders that are substituted with the
    match bindings. If ``write_back`` is set and the reasoner exposes a
    knowledge graph, the fact is also written there.
    """

    fact: str
    write_back: bool = False

    def execute(self, bindings: Dict[str, str], reasoner: "Reasoner") -> Optional[str]:
        concrete = self._substitute(self.fact, bindings)
        reasoner.facts.add(concrete)
        if self.write_back and getattr(reasoner, "knowledge_graph", None) is not None:
            _write_fact_to_graph(reasoner.knowledge_graph, concrete)
        return f"assert {concrete}"


@dataclass
class RetractAction(Action):
    """Retract a fact when the rule fires (basic truth maintenance).

    If ``write_back`` is set and the reasoner exposes a knowledge graph, the
    fact is also removed there using the graph's delete semantics (mirroring
    :class:`AssertAction`'s write-back).
    """

    fact: str
    write_back: bool = False

    def execute(self, bindings: Dict[str, str], reasoner: "Reasoner") -> Optional[str]:
        concrete = self._substitute(self.fact, bindings)
        reasoner.facts.discard(concrete)
        if self.write_back and getattr(reasoner, "knowledge_graph", None) is not None:
            _write_fact_to_graph(reasoner.knowledge_graph, concrete, retract=True)
        return f"retract {concrete}"


@dataclass
class CallAction(Action):
    """Call an external function/tool when the rule fires.

    Wraps an arbitrary callable, which is invoked as ``func(bindings,
    reasoner)``. This is the structured replacement for the previously
    unused ``Rule.handler`` callback.
    """

    func: Callable
    name: str = "call"

    def execute(self, bindings: Dict[str, str], reasoner: "Reasoner") -> Optional[str]:
        self.func(bindings, reasoner)
        return f"call {self.name}"


@dataclass
class EmitEventAction(Action):
    """Emit an event to the reasoner's registered event sink when fired.

    The event name may contain ``?var`` placeholders. Events are delivered to
    any callable registered via :meth:`Reasoner.on_event`.
    """

    event: str
    payload: Dict[str, Any] = field(default_factory=dict)

    def execute(self, bindings: Dict[str, str], reasoner: "Reasoner") -> Optional[str]:
        concrete = self._substitute(self.event, bindings)
        sink = getattr(reasoner, "_event_sink", None)
        if callable(sink):
            sink(concrete, {**self.payload, "bindings": dict(bindings)})
        return f"emit {concrete}"


@dataclass
class Rule:
    """Simplified rule definition."""
    rule_id: str
    name: str
    conditions: List[Any]
    conclusion: Any
    rule_type: RuleType = RuleType.IMPLICATION
    confidence: float = 1.0
    priority: int = 0
    handler: Optional[Callable] = None
    actions: List[Action] = field(default_factory=list)
    metadata: Dict[str, Any] = field(default_factory=dict)

@dataclass
class Fact:
    """Simple fact representation."""
    fact_id: str
    predicate: str
    arguments: List[Any]
    metadata: Dict[str, Any] = field(default_factory=dict)

    def __str__(self) -> str:
        return f"{self.predicate}({', '.join(map(str, self.arguments))})"

@dataclass
class InferenceResult:
    """Result of an inference step."""
    conclusion: str
    rule_used: Optional[Rule] = None
    premises: List[str] = field(default_factory=list)
    confidence: float = 1.0
    metadata: Dict[str, Any] = field(default_factory=dict)

class Reasoner:
    """
    High-level Reasoner class for knowledge graph inference.
    
    This class provides a unified interface for applying reasoning rules to facts
    or knowledge graphs.
    """
    
    def __init__(self, **kwargs):
        """
        Initialize the Reasoner.
        
        Args:
            **kwargs: Additional configuration options
        """
        self.logger = get_logger("reasoner")
        self.progress_tracker = get_progress_tracker()
        # Ensure progress tracker is enabled
        if not self.progress_tracker.enabled:
            self.progress_tracker.enabled = True
        self.config = kwargs
        
        self.rules: List[Rule] = []
        self.facts: Set[str] = set()
        self.rule_counter = 0
        self._fired_activations: Set[Tuple[Any, ...]] = set()

        # Optional knowledge graph for AssertAction(write_back=True) targets.
        self.knowledge_graph = kwargs.get("knowledge_graph")
        # Optional event sink for EmitEventAction; register via on_event().
        self._event_sink: Optional[Callable] = None
        # When True, action-induced fact changes are recorded for provenance
        # via _record_action() -> self.action_log.
        self.provenance: bool = bool(kwargs.get("provenance", False))
        self.action_log: List[Dict[str, Any]] = []

    def on_event(self, sink: Callable) -> None:
        """Register a callable ``sink(event_name, payload)`` for EmitEventAction."""
        self._event_sink = sink

    def _record_action(
        self, rule: "Rule", action: "Action", description: Optional[str], bindings: Dict[str, str]
    ) -> None:
        """Record a fired action for provenance / explanation when enabled.

        Each entry is a structured dict carrying an ISO-8601 ``timestamp`` and a
        parsed ``operation``/``fact`` split (when the description follows the
        ``"<op> <fact>"`` convention used by the built-in actions) so that
        downstream consumers such as :class:`ExplanationGenerator` and the
        provenance layer can reason about *what changed* without re-parsing the
        free-text description.
        """
        if not self.provenance or description is None:
            return
        operation, _, subject = description.partition(" ")
        self.action_log.append(
            {
                "action_id": uuid.uuid4().hex[:8],
                "rule_id": rule.rule_id,
                "action": type(action).__name__,
                "operation": operation or None,
                "fact": subject or None,
                "description": description,
                "bindings": dict(bindings),
                "confidence": rule.confidence,
                "timestamp": datetime.now(timezone.utc).isoformat(),
            }
        )

    def _fire_actions(self, rule: "Rule", bindings: Dict[str, str]) -> None:
        """Run a fired rule's actions (and legacy handler) with match bindings.

        Backward compatible: a rule with an old-style ``handler`` but no
        ``actions`` still has its handler invoked, so pre-existing rules keep
        working while new rules use the structured Action layer.
        """
        actions = list(rule.actions)
        if rule.handler is not None:
            actions.append(CallAction(rule.handler, name=f"handler:{rule.rule_id}"))
        for action in actions:
            try:
                description = action.execute(bindings, self)
                self._record_action(rule, action, description, bindings)
            except Exception as exc:  # noqa: BLE001
                self.logger.error(
                    f"Error executing action {type(action).__name__} "
                    f"for rule '{rule.rule_id}': {exc}"
                )

    def add_rule(self, rule_def: Union[str, Rule]) -> Rule:
        """Add a rule to the reasoner.

        Rules with the same conditions and conclusion as an already-added
        rule are not re-appended -- this keeps re-running the same setup
        code (e.g. a Jupyter cell that calls add_rule() + add_fact() on an
        existing Reasoner) idempotent instead of silently duplicating rules
        on every rerun (#732).

        On dedup, the ORIGINAL rule's confidence, priority, and metadata are
        retained; the incoming rule's differing fields are discarded, not
        merged or upserted -- except for priority, where self.rules is
        re-sorted to reflect any change made directly on the retained Rule
        object after it was first added (see the re-sort below). If the
        incoming rule's confidence differs from the retained rule's, a
        warning is logged so the discrepancy isn't silently swallowed.
        """
        if isinstance(rule_def, Rule):
            rule = rule_def
        else:
            rule = self._parse_rule_definition(rule_def)

        for existing in self.rules:
            if (
                existing.rule_type == rule.rule_type
                and existing.conditions == rule.conditions
                and existing.conclusion == rule.conclusion
            ):
                self.logger.warning(
                    f"Skipping duplicate rule (same conditions/conclusion as '{existing.rule_id}'): "
                    f"IF {' AND '.join(map(str, rule.conditions))} THEN {rule.conclusion}"
                )
                if existing.confidence != rule.confidence:
                    self.logger.warning(
                        f"Duplicate rule '{existing.rule_id}' was re-added with a different "
                        f"confidence ({rule.confidence}); the existing confidence "
                        f"({existing.confidence}) is retained and the new value is discarded."
                    )
                # Rule is a mutable dataclass, so `existing.priority` may have
                # changed since it was added -- re-sort so the dedup path
                # keeps the same self-healing ordering the append path has,
                # rather than leaving self.rules stale relative to priority.
                self.rules.sort(key=lambda r: r.priority, reverse=True)
                return existing

        self.rules.append(rule)
        # Sort rules by priority
        self.rules.sort(key=lambda r: r.priority, reverse=True)
        return rule
        
    def add_fact(self, fact: Union[str, Dict[str, Any]]) -> None:
        """Add a fact to working memory."""
        if isinstance(fact, str):
            self.facts.add(fact.strip())
        elif isinstance(fact, dict):
            # Convert KG-style dict to fact strings
            if "type" in fact and ("name" in fact or "id" in fact):
                name = fact.get("name", fact.get("id"))
                etype = fact.get("type", "Entity")
                self.facts.add(f"{etype}({name})")
            elif "source_id" in fact or "source_name" in fact:
                source = fact.get("source_name", fact.get("source_id"))
                target = fact.get("target_name", fact.get("target_id"))
                rtype = fact.get("type", "Relationship")
                self.facts.add(f"{rtype}({source}, {target})")

    def infer_facts(
        self, 
        facts: Union[List[Any], Dict[str, Any]], 
        rules: Optional[List[Union[str, Rule]]] = None
    ) -> List[Any]:
        """
        Infer new facts from existing facts or a knowledge graph.
        
        Args:
            facts: List of initial facts or a knowledge graph dictionary.
            rules: List of rules to apply (strings or Rule objects)
            
        Returns:
            List of inferred facts (conclusions)
        """
        return [result.conclusion for result in self.infer_with_results(facts, rules)]

    def infer_with_results(
        self,
        facts: Union[List[Any], Dict[str, Any]],
        rules: Optional[List[Union[str, Rule]]] = None,
    ) -> List[InferenceResult]:
        """Infer new facts and return the full :class:`InferenceResult` objects.

        Unlike :meth:`infer_facts` (which returns only conclusion strings for
        backward compatibility), this preserves each result's ``rule_used``,
        ``premises`` and ``confidence`` so callers such as the provenance
        wrapper can record real confidence values instead of ``None``.
        """
        tracking_id = self.progress_tracker.start_tracking(
            module="reasoning",
            submodule="Reasoner",
            message="Inferring facts"
        )
        
        try:
            if isinstance(facts, list):
                for f in facts:
                    self.add_fact(f)
            else:
                self.add_fact(facts)

            if rules:
                for rule in rules:
                    self.add_rule(rule)
            
            # Perform inference
            results = self.forward_chain()
            
            self.progress_tracker.stop_tracking(
                tracking_id,
                status="completed",
                message=f"Inferred {len(results)} new facts"
            )
            
            return results
            
        except Exception as e:
            self.progress_tracker.stop_tracking(
                tracking_id, 
                status="failed", 
                message=str(e)
            )
            self.logger.error(f"Inference failed: {e}")
            raise

    def forward_chain(self) -> List[InferenceResult]:
        """Derive all possible new facts using forward chaining."""
        tracking_id = self.progress_tracker.start_tracking(
            module="reasoning",
            submodule="Reasoner",
            message="Performing forward chaining"
        )
        
        results = []
        new_facts_added = True
        max_iterations = self.config.get("max_iterations", 50)
        iteration = 0
        # Activations (rule + concrete bindings + matched facts) whose actions
        # have already fired. Actions are side-effecting and must
        # fire exactly once per distinct match, decoupled from whether the
        # rule's *conclusion* is new. This fixes two failure modes:
        #   * A valid binding whose conclusion is already known (or duplicated
        #     within a pass) previously never fired its actions.
        #   * A RetractAction that removes a premise of its own rule previously
        #     re-fired every pass, iterating to max_iterations. Recording the
        #     activation means it fires once and stops driving iterations.
        while new_facts_added and iteration < max_iterations:
            new_facts_added = False
            iteration += 1
            
            # Snapshot facts that existed before this pass, so we can tell a
            # fact that was already known apart from one newly derived during
            # this same pass. Newly derived conclusions are added to
            # self.facts immediately (not deferred to the end of the pass) so
            # that later rules in this same pass can chain off facts inferred
            # earlier in the pass -- e.g. "IF A THEN B" firing lets
            # "IF B THEN C" fire in the same pass rather than requiring an
            # extra outer iteration.
            pre_pass_facts = frozenset(self.facts)
            # Tracks conclusions newly derived in this pass, keyed to the
            # InferenceResult already appended to `results`, so multiple
            # derivations of the identical conclusion (different bindings
            # and/or different rules within the same pass) merge their
            # premises into one result instead of creating duplicates or
            # silently dropping premises (the #733 fix).
            pass_results: Dict[str, InferenceResult] = {}
            
            for rule in self.rules:
                for conclusion, matched_facts, bindings in self._match_rule(rule):
                    # Fire this activation's actions exactly once, independent
                    # of the conclusion-dedup below. Keyed by rule id + the
                    # concrete bindings so distinct matches each fire, but a
                    # repeated match (same bindings across passes) does not.
                    if rule.actions or rule.handler is not None:
                        activation_key = _make_activation_key(
                            rule.rule_id,
                            bindings,
                            matched_facts,
                        )
                        if activation_key not in self._fired_activations:
                            self._fired_activations.add(activation_key)
                            self._fire_actions(rule, bindings)

                    if conclusion in pass_results:
                        # Another derivation of a conclusion already produced
                        # earlier in this same pass: merge premises, dedup.
                        existing = pass_results[conclusion]
                        for fact in matched_facts:
                            if fact not in existing.premises:
                                existing.premises.append(fact)
                        continue
                    if conclusion in pre_pass_facts:
                        # Already known before this pass started -- not a
                        # new derivation.
                        continue
                    
                    self.facts.add(conclusion)
                    inference_result = InferenceResult(
                        conclusion=conclusion,
                        rule_used=rule,
                        premises=list(matched_facts),
                        confidence=rule.confidence
                    )
                    pass_results[conclusion] = inference_result
                    results.append(inference_result)
                    new_facts_added = True
                        
        self.progress_tracker.stop_tracking(
            tracking_id,
            status="completed",
            message=f"Forward chaining completed: {len(results)} new facts inferred"
        )
        return results

    def backward_chain(self, goal: str, max_depth: int = 10) -> Optional[InferenceResult]:
        """
        Prove a goal using backward chaining.
        
        Args:
            goal: The fact string to prove
            max_depth: Maximum recursion depth
            
        Returns:
            InferenceResult if proven, None otherwise
        """
        tracking_id = self.progress_tracker.start_tracking(
            module="reasoning",
            submodule="Reasoner",
            message="Performing backward chaining"
        )
        
        try:
            result = self._prove_goal(goal, depth=0, max_depth=max_depth)
            
            status = "completed" if result else "not_proven"
            self.progress_tracker.stop_tracking(
                tracking_id,
                status=status,
                message=f"Backward chaining finished: {'Proven' if result else 'Not proven'}"
            )
            return result
        except Exception as e:
            self.progress_tracker.stop_tracking(tracking_id, status="failed", message=str(e))
            raise

    def _prove_goal(self, goal: str, depth: int, max_depth: int) -> Optional[InferenceResult]:
        """Recursive goal prover."""
        if depth > max_depth:
            return None
            
        # 1. Check if goal is already in facts
        if goal in self.facts:
            return InferenceResult(conclusion=goal, premises=[goal])
            
        # 2. Check if goal matches a known fact pattern (unification)
        for fact in self.facts:
            if self._match_pattern(goal, fact, {}) is not None:
                return InferenceResult(conclusion=fact, premises=[fact])
                
        # 3. Try to prove via rules
        for rule in self.rules:
            # Check if rule conclusion can match the goal
            initial_bindings = self._match_pattern(rule.conclusion, goal, {})
            if initial_bindings is not None:
                # Try to prove all conditions
                all_conditions_proven = True
                premises = []
                current_bindings = initial_bindings.copy()
                
                for condition in rule.conditions:
                    instantiated_cond = self._substitute(condition, current_bindings)
                    cond_result = self._prove_goal(instantiated_cond, depth + 1, max_depth)
                    
                    if cond_result:
                        premises.append(cond_result.conclusion)
                        # Update bindings from the actual fact that matched
                        new_bindings = self._match_pattern(condition, cond_result.conclusion, current_bindings)
                        if new_bindings:
                            current_bindings = new_bindings
                    else:
                        all_conditions_proven = False
                        break
                        
                if all_conditions_proven:
                    instantiated_conclusion = self._substitute(rule.conclusion, current_bindings)
                    return InferenceResult(
                        conclusion=instantiated_conclusion,
                        rule_used=rule,
                        premises=premises,
                        confidence=rule.confidence
                    )
                    
        return None

    def _parse_rule_definition(self, definition: str) -> Rule:
        """Parse IF-THEN rule strings."""
        definition = definition.strip()
        if_match = re.match(r"IF\s+(.+?)\s+THEN\s+(.+)$", definition, re.IGNORECASE | re.DOTALL)
        
        if not if_match:
            # Fallback or error
            self.rule_counter += 1
            return Rule(f"rule_{self.rule_counter}", f"Rule {self.rule_counter}", [], definition)
            
        conditions_str = if_match.group(1)
        conclusion_str = if_match.group(2)
        
        # Split conditions by AND
        conditions = [c.strip() for c in re.split(r"\s+AND\s+", conditions_str, flags=re.IGNORECASE)]
        
        self.rule_counter += 1
        return Rule(
            rule_id=f"rule_{self.rule_counter}",
            name=f"Rule {self.rule_counter}",
            conditions=conditions,
            conclusion=conclusion_str.strip()
        )
        
    def _match_rule(self, rule: Rule) -> List[Tuple[str, List[str], Dict[str, str]]]:
        """
        Match rule conditions against facts and return instantiated conclusions
        paired with the facts that satisfied each condition and the variable
        bindings that produced them.

        Returns:
            List of (conclusion, matched_facts, bindings) tuples, where
            matched_facts is the ordered list of facts bound to this rule's
            conditions and bindings maps variable name -> matched value (used
            to fire the rule's actions).
        """
        if not rule.conditions:
            return []
            
        # self.facts is not mutated anywhere within this method, so sort it
        # once here rather than re-sorting on every (bindings, condition)
        # pair below -- sorted() was previously called once per inner-loop
        # entry, which re-allocates and re-sorts the full fact set repeatedly
        # and is a hot spot for larger fact sets.
        sorted_facts = sorted(self.facts)
        
        # Each entry pairs a set of variable bindings with the facts that were
        # matched to produce those bindings, so the facts survive alongside
        # the bindings as conditions accumulate.
        bindings_list: List[Tuple[Dict[str, str], List[str]]] = [({}, [])]
        
        for condition in rule.conditions:
            new_bindings_list = []
            for bindings, matched_facts in bindings_list:
                for fact in sorted_facts:
                    match_bindings = self._match_pattern(condition, fact, bindings)
                    if match_bindings is not None:
                        new_bindings_list.append((match_bindings, matched_facts + [fact]))
            bindings_list = new_bindings_list
            if not bindings_list:
                break
                
        results = []
        for bindings, matched_facts in bindings_list:
            instantiated_conclusion = self._substitute(rule.conclusion, bindings)
            results.append((instantiated_conclusion, matched_facts, bindings))
            
        return results
        
    def _match_pattern(self, pattern: str, fact: str, initial_bindings: Dict[str, str]) -> Optional[Dict[str, str]]:
        """Match a pattern against a fact with initial bindings."""
        # Split on ?var placeholders first, then escape only the literal segments.
        # This avoids re.escape() mangling the surrounding parentheses and ?
        # before the variable substitution step.
        segments = re.split(r"(\?\w+)", pattern)
        seen_vars: set = set()
        p_regex = ""
        for seg in segments:
            if seg.startswith("?"):
                var_name = seg[1:]
                if var_name in initial_bindings:
                    # Already bound — require the exact literal value
                    p_regex += re.escape(initial_bindings[var_name])
                elif var_name in seen_vars:
                    # Same variable used twice — use a backreference
                    p_regex += f"(?P={var_name})"
                else:
                    p_regex += f"(?P<{var_name}>.+?)"
                    seen_vars.add(var_name)
            else:
                p_regex += re.escape(seg)
        p_regex = f"^{p_regex}$"

        # Simple regex-based matcher for patterns like "Person(?x)" and facts like "Person(John)"
        
        try:
            match = re.match(p_regex, fact)
            if match:
                new_bindings = initial_bindings.copy()
                for var, value in match.groupdict().items():
                    if var in new_bindings and new_bindings[var] != value:
                        return None  # Binding conflict
                    new_bindings[var] = value
                return new_bindings
        except Exception as e:
            self.logger.warning(f"Error matching pattern '{pattern}' (regex: '{p_regex}') against fact '{fact}': {e}")
            
        return None
        
    def _substitute(self, pattern: str, bindings: Dict[str, str]) -> str:
        """Substitute variables in a pattern with bound values."""
        return _substitute_variables(pattern, bindings)
        
    def reset_action_history(self) -> None:
        """Allow previously fired rule activations to execute their actions again."""
        self._fired_activations.clear()

    def clear(self) -> None:
        """Clear facts, rules, and action activation history."""
        self.facts.clear()
        self.rules.clear()
        self.rule_counter = 0
        self.reset_action_history()

    def reset(self) -> None:
        """Alias for clear()."""
        self.clear()
