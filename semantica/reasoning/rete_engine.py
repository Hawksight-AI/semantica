"""
Rete Algorithm Engine Module

This module provides Rete algorithm implementation for efficient rule-based
reasoning, using a network of alpha and beta nodes for pattern matching.

Key Features:
    - Rete algorithm implementation for efficient rule matching
    - Alpha node pattern matching
    - Beta node join operations
    - Terminal node activation
    - Incremental fact processing
    - Performance optimization for large rule sets

Main Classes:
    - ReteEngine: Rete algorithm implementation
    - ReteNode: Base Rete network node
    - AlphaNode: Alpha node for single condition matching
    - BetaNode: Beta node for join operations
    - TerminalNode: Terminal node for rule activation
    - Fact: Dataclass for fact representation
    - Match: Dataclass for pattern matches

Example Usage:
    >>> from semantica.reasoning import ReteEngine, Fact
    >>> engine = ReteEngine()
    >>> engine.add_rule(rule)
    >>> fact = Fact("f1", "Person", ["John"])
    >>> engine.add_fact(fact)
    >>> matches = engine.get_matches()

Author: Semantica Contributors
License: MIT
"""

import re
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Set, Tuple

from ..utils.logging import get_logger
from ..utils.progress_tracker import get_progress_tracker
from .reasoner import Fact, Rule, _make_activation_key


def _extract_bindings(condition: Any, fact: Fact) -> Dict[str, Any]:
    """Extract ``?var`` bindings by matching a condition pattern against a fact.

    ``condition`` is the pattern stored on the alpha node (typically a string
    like ``"Person(?x)"``); ``fact`` is the working-memory :class:`Fact`. The
    fact's canonical string form (``Predicate(arg1, arg2, ...)``) is matched
    against the pattern using the same ``?\\w+`` placeholder convention as the
    Reasoner, so downstream actions receive real bindings (e.g. ``{"x": "John"}``)
    instead of the empty dict that previously left ``?x`` placeholders
    unsubstituted.

    Returns an empty dict when the condition is not a string pattern or does
    not match -- callers treat that as "no bindings extracted".
    """
    if not isinstance(condition, str):
        return {}

    segments = re.split(r"(\?\w+)", condition)
    seen_vars: Set[str] = set()
    p_regex = ""
    for seg in segments:
        if seg.startswith("?"):
            var_name = seg[1:]
            if var_name in seen_vars:
                p_regex += f"(?P={var_name})"
            else:
                p_regex += f"(?P<{var_name}>.+?)"
                seen_vars.add(var_name)
        else:
            p_regex += re.escape(seg)
    p_regex = f"^{p_regex}$"

    try:
        match = re.match(p_regex, str(fact))
    except re.error:
        return {}
    if not match:
        return {}
    return {k: v for k, v in match.groupdict().items() if v is not None}


def _bindings_for_rule(rule: Rule, facts: List[Fact]) -> Dict[str, Any]:
    """Merge ``?var`` bindings from matching a rule's conditions against facts.

    Each fact is matched against every condition of the rule; the first
    condition that yields bindings for a fact contributes them. Bindings from
    all facts are merged so multi-condition (joined) rules receive the full
    variable environment. Later conflicting values do not overwrite earlier
    ones, preserving the binding that a join already validated.
    """
    bindings: Dict[str, Any] = {}
    for fact in facts:
        for condition in rule.conditions:
            extracted = _extract_bindings(condition, fact)
            if not extracted:
                continue
            for key, value in extracted.items():
                bindings.setdefault(key, value)
            break
    return bindings


@dataclass
class Match:
    """Pattern match."""

    rule: Rule
    facts: List[Fact]
    bindings: Dict[str, Any] = field(default_factory=dict)
    confidence: float = 1.0


class ReteNode:
    """Base Rete network node."""

    def __init__(self, node_id: str):
        self.node_id = node_id
        self.children: List[ReteNode] = []


class AlphaNode(ReteNode):
    """Alpha node for single condition matching."""

    def __init__(self, node_id: str, condition: Any):
        super().__init__(node_id)
        self.condition = condition
        self.matches: List[Fact] = []

    def add_fact(self, fact: Fact) -> bool:
        """Add fact if it matches condition."""
        if self._matches(fact):
            self.matches.append(fact)
            return True
        return False

    def _matches(self, fact: Fact) -> bool:
        """Check if fact matches condition."""
        # Simple matching - can be enhanced
        return True


class BetaNode(ReteNode):
    """Beta node for joining conditions."""

    def __init__(self, node_id: str, left: ReteNode, right: ReteNode):
        super().__init__(node_id)
        self.left = left
        self.right = right
        self.matches: List[Tuple[Fact, Fact]] = []

    def join(self, left_fact: Fact, right_fact: Fact) -> bool:
        """Join facts from left and right nodes."""
        if self._can_join(left_fact, right_fact):
            self.matches.append((left_fact, right_fact))
            return True
        return False

    def _can_join(self, left_fact: Fact, right_fact: Fact) -> bool:
        """Check if facts can be joined."""
        # Simple join logic - can be enhanced
        return True


class TerminalNode(ReteNode):
    """Terminal node representing rule activation."""

    def __init__(self, node_id: str, rule: Rule):
        super().__init__(node_id)
        self.rule = rule
        self.activations: List[Match] = []

    def activate(self, match: Match) -> None:
        """Activate rule."""
        self.activations.append(match)


class ReteEngine:
    """
    Rete algorithm implementation for efficient rule matching.

    • Rete algorithm implementation
    • Rule network construction and optimization
    • Pattern matching and conflict resolution
    • Performance optimization
    • Error handling and recovery
    • Advanced Rete features
    """

    def __init__(self, config: Optional[Dict[str, Any]] = None, **kwargs):
        """
        Initialize Rete engine.

        Args:
            config: Configuration dictionary
            **kwargs: Additional configuration options
        """
        self.logger = get_logger("rete_engine")
        self.config = config or {}
        self.config.update(kwargs)

        # Initialize progress tracker
        self.progress_tracker = get_progress_tracker()
        # Ensure progress tracker is enabled
        if not self.progress_tracker.enabled:
            self.progress_tracker.enabled = True

        self.network: Dict[str, ReteNode] = {}
        self.facts: List[Fact] = []
        self.fact_counter = 0
        self.node_counter = 0
        self._executed_activations: Set[Tuple[Any, ...]] = set()
        # Optional Reasoner used to fire rule-driven actions on match. When
        # set, execute_matches() runs each matched rule's ``actions`` (and any
        # legacy ``handler``) through the Reasoner's action machinery so that
        # Rete-based matching benefits from the same production-rule behaviour
        # as forward_chain(). Left None keeps the pure-matching mode.
        self.reasoner: Optional[Any] = self.config.get("reasoner")

    def bind_reasoner(self, reasoner: Any) -> None:
        """Attach a Reasoner so matched rules can fire their actions."""
        self.reasoner = reasoner

    def build_network(self, rules: List[Rule]) -> None:
        """
        Build Rete network from rules.

        Args:
            rules: List of rules
        """
        tracking_id = self.progress_tracker.start_tracking(
            module="reasoning",
            submodule="ReteEngine",
            message=f"Building Rete network from {len(rules)} rules",
        )

        try:
            self.reset_action_history()
            self.network.clear()

            self.progress_tracker.update_tracking(
                tracking_id, message=f"Adding {len(rules)} rules to network..."
            )
            for rule in rules:
                self._add_rule_to_network(rule)

            self.logger.info(
                f"Built Rete network with {len(self.network)} nodes for {len(rules)} rules"
            )
            self.progress_tracker.stop_tracking(
                tracking_id,
                status="completed",
                message=f"Built Rete network with {len(self.network)} nodes for {len(rules)} rules",
            )

        except Exception as e:
            self.progress_tracker.stop_tracking(
                tracking_id, status="failed", message=str(e)
            )
            raise

    def _add_rule_to_network(self, rule: Rule) -> None:
        """Add rule to Rete network."""
        # Create alpha nodes for each condition
        alpha_nodes = []
        for condition in rule.conditions:
            node_id = f"alpha_{self.node_counter}"
            self.node_counter += 1
            alpha_node = AlphaNode(node_id, condition)
            alpha_nodes.append(alpha_node)
            self.network[node_id] = alpha_node

        # Create beta nodes for joining
        if len(alpha_nodes) > 1:
            current = alpha_nodes[0]
            for i in range(1, len(alpha_nodes)):
                node_id = f"beta_{self.node_counter}"
                self.node_counter += 1
                beta_node = BetaNode(node_id, current, alpha_nodes[i])
                self.network[node_id] = beta_node
                current = beta_node
            final_node = current
        else:
            final_node = alpha_nodes[0] if alpha_nodes else None

        # Create terminal node
        if final_node:
            node_id = f"terminal_{self.node_counter}"
            self.node_counter += 1
            terminal_node = TerminalNode(node_id, rule)
            final_node.children.append(terminal_node)
            self.network[node_id] = terminal_node

    def add_fact(self, fact: Fact) -> None:
        """
        Add fact to working memory.

        Args:
            fact: Fact to add
        """
        self.facts.append(fact)

        # Propagate through network
        self._propagate_fact(fact)

    def _propagate_fact(self, fact: Fact) -> None:
        """Propagate fact through Rete network."""
        # Find matching alpha nodes
        for node_id, node in self.network.items():
            if isinstance(node, AlphaNode):
                if node.add_fact(fact):
                    # Propagate to children
                    self._propagate_from_alpha(node, fact)

    def _propagate_from_alpha(self, alpha_node: AlphaNode, fact: Fact) -> None:
        """Propagate from alpha node to children."""
        for child in alpha_node.children:
            if isinstance(child, BetaNode):
                # Join with matches from left side
                for left_fact in alpha_node.matches:
                    if child.join(left_fact, fact):
                        # Propagate to children
                        for grandchild in child.children:
                            if isinstance(grandchild, TerminalNode):
                                facts = [left_fact, fact]
                                match = Match(
                                    rule=grandchild.rule,
                                    facts=facts,
                                    bindings=_bindings_for_rule(
                                        grandchild.rule, facts
                                    ),
                                    confidence=1.0,
                                )
                                grandchild.activate(match)
            elif isinstance(child, TerminalNode):
                # Direct activation
                match = Match(
                    rule=child.rule,
                    facts=[fact],
                    bindings=_bindings_for_rule(child.rule, [fact]),
                    confidence=1.0,
                )
                child.activate(match)

    def match_patterns(self, facts: Optional[List[Fact]] = None) -> List[Match]:
        """
        Match patterns using Rete algorithm.

        Args:
            facts: Optional facts to match (uses working memory if not provided)

        Returns:
            List of matches
        """
        tracking_id = self.progress_tracker.start_tracking(
            module="reasoning",
            submodule="ReteEngine",
            message="Matching patterns using Rete algorithm",
        )

        try:
            if facts:
                # Add facts to working memory
                self.progress_tracker.update_tracking(
                    tracking_id,
                    message=f"Adding {len(facts)} facts to working memory...",
                )
                for fact in facts:
                    self.add_fact(fact)

            # Collect all activations
            self.progress_tracker.update_tracking(
                tracking_id, message="Collecting pattern matches..."
            )
            matches = []
            for node_id, node in self.network.items():
                if isinstance(node, TerminalNode):
                    matches.extend(node.activations)

            self.progress_tracker.stop_tracking(
                tracking_id,
                status="completed",
                message=f"Found {len(matches)} pattern matches",
            )
            return matches

        except Exception as e:
            self.progress_tracker.stop_tracking(
                tracking_id, status="failed", message=str(e)
            )
            raise

    def execute_matches(self, matches: Optional[List[Match]] = None) -> List[Any]:
        """
        Execute matched rules.

        Args:
            matches: Optional matches to execute (uses current matches if not provided)

        Returns:
            List of inference results
        """
        tracking_id = self.progress_tracker.start_tracking(
            module="reasoning",
            submodule="ReteEngine",
            message="Executing matched rules",
        )

        try:
            if matches is None:
                self.progress_tracker.update_tracking(
                    tracking_id, message="Matching patterns..."
                )
                matches = self.match_patterns()

            self.progress_tracker.update_tracking(
                tracking_id, message=f"Executing {len(matches)} matched rules..."
            )
            results = []
            for match in matches:
                # Conclusions are the pure inference result and remain
                # independent from optional side-effect execution below.
                results.append(match.rule.conclusion)
                try:
                    # Fire the rule's actions (and any legacy handler) through
                    # the bound Reasoner so Rete matching produces the same
                    # side effects / provenance as forward_chain(). Falls back
                    # to just recording the conclusion when no Reasoner is bound.
                    if self.reasoner is not None and (
                        match.rule.actions or match.rule.handler is not None
                    ):
                        activation_key = _make_activation_key(
                            match.rule.rule_id,
                            match.bindings,
                            [
                                (fact.fact_id, fact.predicate, fact.arguments)
                                for fact in match.facts
                            ],
                        )
                        if activation_key not in self._executed_activations:
                            self._executed_activations.add(activation_key)
                            self.reasoner._fire_actions(match.rule, match.bindings)
                except Exception as e:
                    self.logger.error(f"Error executing match: {e}")

            self.progress_tracker.stop_tracking(
                tracking_id,
                status="completed",
                message=f"Executed {len(matches)} matches: {len(results)} results",
            )
            return results

        except Exception as e:
            self.progress_tracker.stop_tracking(
                tracking_id, status="failed", message=str(e)
            )
            raise

    def reset_action_history(self) -> None:
        """Allow previously executed activations to fire their actions again."""
        self._executed_activations.clear()

    def reset(self) -> None:
        """Reset Rete working memory and action activation history."""
        self.facts.clear()
        self.reset_action_history()
        for node in self.network.values():
            if isinstance(node, AlphaNode) or isinstance(node, BetaNode):
                node.matches.clear()
            elif isinstance(node, TerminalNode):
                node.activations.clear()

    def get_network_stats(self) -> Dict[str, Any]:
        """Get network statistics."""
        alpha_count = sum(1 for n in self.network.values() if isinstance(n, AlphaNode))
        beta_count = sum(1 for n in self.network.values() if isinstance(n, BetaNode))
        terminal_count = sum(
            1 for n in self.network.values() if isinstance(n, TerminalNode)
        )

        return {
            "total_nodes": len(self.network),
            "alpha_nodes": alpha_count,
            "beta_nodes": beta_count,
            "terminal_nodes": terminal_count,
            "facts": len(self.facts),
        }
