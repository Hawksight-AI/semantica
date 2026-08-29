"""
Reasoning Module

This module provides reasoning and inference capabilities for knowledge graph
analysis and query answering, supporting multiple reasoning strategies including
rule-based inference via Rete, SPARQL reasoning, abductive and deductive reasoning,
and native Datalog evaluation.
"""

from .reasoner import Reasoner, InferenceResult, Rule, Fact, RuleType
from .reasoner import (
    Action,
    AssertAction,
    RetractAction,
    CallAction,
    EmitEventAction,
)
from .graph_reasoner import GraphReasoner
from .explanation_generator import (
    Explanation,
    ExplanationGenerator,
    Justification,
    ReasoningPath,
    ReasoningStep,
)
from .rete_engine import (
    AlphaNode,
    BetaNode,
    Match,
    ReteEngine,
    ReteNode,
    TerminalNode,
)
from .sparql_reasoner import SPARQLQueryResult, SPARQLReasoner

from .datalog_reasoner import DatalogReasoner, DatalogFact, DatalogRule
from .temporal_reasoning import IntervalRelation, TemporalInterval, TemporalReasoningEngine

__all__ = [
    # Reasoner facade
    "Reasoner",
    "GraphReasoner",
    "InferenceResult",
    "Rule",
    "Fact",
    "RuleType",
    # Rule-driven actions
    "Action",
    "AssertAction",
    "RetractAction",
    "CallAction",
    "EmitEventAction",
    # Rete engine
    "ReteEngine",
    "ReteNode",
    "AlphaNode",
    "BetaNode",
    "TerminalNode",
    "Match",
    # SPARQL reasoning
    "SPARQLReasoner",
    "SPARQLQueryResult",
    # Datalog reasoning
    "DatalogReasoner",
    "DatalogFact",
    "DatalogRule",
    "TemporalInterval",
    "IntervalRelation",
    "TemporalReasoningEngine",
    # Explanation
    "ExplanationGenerator",
    "Explanation",
    "ReasoningStep",
    "ReasoningPath",
    "Justification",
]
