"""
SemanticaDecisionTool — a CrewAI ``BaseTool`` exposing Semantica's decision
intelligence (``AgentContext``) to agents.

Lets agents record decisions with reasoning, retrieve past precedents, trace
causal chains, analyse downstream impact, and validate proposed decisions
against policy rules.

Install
-------
    pip install semantica[crewai]

Example
-------
    >>> from integrations.crewai import SemanticaDecisionTool
    >>> from crewai import Agent, Crew, Task
    >>> tool = SemanticaDecisionTool()
    >>> crew = Crew(
    ...     agents=[Agent(role="...", goal="...", backstory="...", tools=[tool])],
    ...     tasks=[...],
    ... )

Tools exposed
-------------
record_decision   — Record a decision with reasoning and outcome
find_precedents   — Search past decisions similar to a scenario
trace_causal_chain— Trace the causal chain from a decision node
analyze_impact    — Assess downstream influence of a decision
check_policy      — Validate a proposed decision against policy rules
"""

from __future__ import annotations

import json
import re
from typing import Any, Dict, List, Literal, Optional, Type

from pydantic import BaseModel, Field

from semantica.utils.logging import get_logger

from ._availability import CREWAI_AVAILABLE

logger = get_logger(__name__)

# ---------------------------------------------------------------------------
# Optional: CrewAI BaseTool base class
# ---------------------------------------------------------------------------
_BaseTool: Any = object

if CREWAI_AVAILABLE:
    from crewai.tools import BaseTool as _BaseTool  # type: ignore


# ---------------------------------------------------------------------------
# Input schema
# ---------------------------------------------------------------------------
class SemanticaDecisionToolInput(BaseModel):
    """
    Input schema for ``SemanticaDecisionTool``.

    Exactly one action is dispatched per call; the remaining fields are only
    used by the actions that need them.
    """

    action: Literal[
        "record_decision",
        "find_precedents",
        "trace_causal_chain",
        "analyze_impact",
        "check_policy",
    ] = Field(
        ...,
        description=(
            "Which decision-intelligence operation to run. One of: "
            "'record_decision', 'find_precedents', 'trace_causal_chain', "
            "'analyze_impact', 'check_policy'."
        ),
    )
    category: Optional[str] = Field(
        None,
        description="Domain category, e.g. 'loan_approval'. Used by 'record_decision'.",
    )
    scenario: Optional[str] = Field(
        None,
        description=(
            "Short description of the situation. Used by 'record_decision' and "
            "'find_precedents'."
        ),
    )
    reasoning: Optional[str] = Field(
        None, description="Why this outcome was chosen. Used by 'record_decision'."
    )
    outcome: Optional[str] = Field(
        None, description="The decision result. Used by 'record_decision'."
    )
    confidence: float = Field(
        0.8,
        ge=0.0,
        le=1.0,
        description="Confidence score in [0, 1]. Used by 'record_decision'.",
    )
    entities: Optional[str] = Field(
        None,
        description="Comma-separated entity names. Used by 'record_decision'.",
    )
    decision_id: Optional[str] = Field(
        None,
        description=(
            "Identifier of a decision. Used by 'trace_causal_chain' and "
            "'analyze_impact'."
        ),
    )
    depth: int = Field(
        3,
        ge=1,
        le=20,
        description="Maximum chain depth. Used by 'trace_causal_chain'.",
    )
    decision_data: Optional[str] = Field(
        None,
        description=(
            "JSON object describing a proposed decision. Used by 'check_policy'."
        ),
    )
    policy_rules: Optional[str] = Field(
        None,
        description=(
            "JSON list of rule strings like 'confidence >= 0.7'. Used by "
            "'check_policy'."
        ),
    )


# ---------------------------------------------------------------------------
# SemanticaDecisionTool
# ---------------------------------------------------------------------------
class SemanticaDecisionTool(_BaseTool):  # type: ignore[misc]
    """
    CrewAI tool that surfaces Semantica's decision intelligence as agent actions.

    Parameters
    ----------
    context:
        A ``semantica.context.AgentContext`` (or compatible object exposing
        ``record_decision``, ``find_precedents_advanced``,
        ``analyze_decision_influence``).  A fresh in-memory context is created
        when ``None``.
    max_precedents:
        Default number of precedents returned by ``find_precedents``.
    causal_depth:
        Default chain depth used by ``trace_causal_chain``.
    """

    name: str = "semantica_decision"
    description: str = (
        "Decision intelligence toolkit. Actions: 'record_decision' (record a "
        "decision with category, scenario, reasoning, outcome, confidence), "
        "'find_precedents' (search past decisions similar to 'scenario'), "
        "'trace_causal_chain' (trace the causal chain from 'decision_id'), "
        "'analyze_impact' (assess downstream influence of 'decision_id'), "
        "'check_policy' (validate 'decision_data' JSON against 'policy_rules' "
        "rules like 'confidence >= 0.7'). Returns JSON."
    )
    args_schema: Type[BaseModel] = SemanticaDecisionToolInput
    context: Any = Field(default=None, exclude=True)
    max_precedents: int = 5
    causal_depth: int = 3
    had_live_state: bool = False
    reconstructed_state: bool = Field(default=False, exclude=True)

    def __init__(
        self,
        context: Any = None,
        max_precedents: int = 5,
        causal_depth: int = 3,
        **kwargs: Any,
    ) -> None:
        if CREWAI_AVAILABLE:
            super().__init__(
                context=context,
                max_precedents=max_precedents,
                causal_depth=causal_depth,
                **kwargs,
            )
        else:
            super().__init__()
            self.context = context
            self.max_precedents = max_precedents
            self.causal_depth = causal_depth
            # Degraded mode is a plain class — no model_post_init lifecycle.
            self._ensure_defaults()

        logger.info("SemanticaDecisionTool initialised (crewai=%s)", CREWAI_AVAILABLE)

    def model_post_init(self, __context: Any) -> None:
        """Re-create default state after validation/deserialisation.

        ``context`` is excluded from JSON serialisation (CrewAI checkpoints
        serialise every tool via ``model_dump(mode="json")``), so a tool
        restored from a checkpoint has ``None`` state until this runs.
        """
        self._ensure_defaults()
        super().model_post_init(__context)

    def _ensure_defaults(self) -> None:
        """Lazy-import and build a real AgentContext when none is wired."""
        if self.context is None:
            from semantica.context import AgentContext, ContextGraph
            from semantica.vector_store import VectorStore

            self.context = AgentContext(
                vector_store=VectorStore(backend="faiss"),
                decision_tracking=True,
                knowledge_graph=ContextGraph(),
            )
            if self.had_live_state:
                self.reconstructed_state = True
                logger.warning(
                    "SemanticaDecisionTool: the live decision context was lost "
                    "during serialization/checkpoint restore — an EMPTY "
                    "context was reconstructed; re-attach the original context "
                    "before continuing"
                )
            else:
                logger.warning(
                    "SemanticaDecisionTool created a fresh in-memory "
                    "AgentContext — agents sharing decision state must be "
                    "wired to the same context"
                )
        self.had_live_state = True

    # ------------------------------------------------------------------
    # CrewAI entry points
    # ------------------------------------------------------------------

    def _run(
        self,
        action: str,
        category: Optional[str] = None,
        scenario: Optional[str] = None,
        reasoning: Optional[str] = None,
        outcome: Optional[str] = None,
        confidence: float = 0.8,
        entities: Optional[str] = None,
        decision_id: Optional[str] = None,
        depth: int = 3,
        decision_data: Optional[str] = None,
        policy_rules: Optional[str] = None,
        **kwargs: Any,
    ) -> str:
        valid = {
            "record_decision",
            "find_precedents",
            "trace_causal_chain",
            "analyze_impact",
            "check_policy",
        }
        if action not in valid:
            return json.dumps(
                {
                    "error": f"Unknown action '{action}'. Valid actions: "
                    + ", ".join(sorted(valid))
                }
            )

        if action == "record_decision":
            return self._record_decision(
                category=category or "general",
                scenario=scenario or "decision recorded",
                reasoning=reasoning or "agent decision",
                outcome=outcome or "recorded",
                confidence=confidence,
                entities=entities,
            )
        if action == "find_precedents":
            return self._find_precedents(scenario=scenario or "", category=category)
        if action == "trace_causal_chain":
            return self._trace_causal_chain(decision_id or "", depth=depth)
        if action == "analyze_impact":
            return self._analyze_impact(decision_id or "")
        return self._check_policy(decision_data or "", policy_rules)

    async def _arun(self, action: str, **kwargs: Any) -> str:
        """Async variant of ``_run`` for CrewAI's async tool path."""
        return self._run(action=action, **kwargs)

    # ------------------------------------------------------------------
    # Actions
    # ------------------------------------------------------------------

    def _record_decision(
        self,
        category: str,
        scenario: str,
        reasoning: str,
        outcome: str,
        confidence: float = 0.8,
        entities: Optional[str] = None,
    ) -> str:
        entity_list: Optional[List[str]] = None
        if entities:
            entity_list = [e.strip() for e in entities.split(",") if e.strip()]

        try:
            decision_id = self.context.record_decision(
                category=category,
                scenario=scenario,
                reasoning=reasoning,
                outcome=outcome,
                confidence=float(confidence),
                entities=entity_list,
            )
            result = {"decision_id": str(decision_id), "status": "recorded"}
            logger.info("record_decision → %s", decision_id)
        except Exception as exc:
            result = {"error": str(exc), "status": "failed"}
            logger.warning("record_decision failed: %s", exc)

        return json.dumps(result)

    def _find_precedents(
        self,
        scenario: str,
        category: Optional[str] = None,
        limit: Optional[int] = None,
    ) -> str:
        k = limit if limit is not None else self.max_precedents
        try:
            precedents = self.context.find_precedents_advanced(
                scenario=scenario,
                category=category,
                limit=k,
            )
            out: List[Dict[str, Any]] = []
            for p in (precedents or [])[:k]:
                if isinstance(p, dict):
                    out.append(p)
                else:
                    out.append(
                        {
                            "scenario": getattr(p, "scenario", str(p)),
                            "outcome": getattr(p, "outcome", ""),
                            "confidence": getattr(p, "confidence", 0.0),
                            "category": getattr(p, "category", ""),
                        }
                    )
            logger.info("find_precedents('%s') → %d results", scenario, len(out))
            return json.dumps({"precedents": out, "count": len(out)})
        except Exception as exc:
            logger.warning("find_precedents failed: %s", exc)
            return json.dumps({"precedents": [], "count": 0, "error": str(exc)})

    def _trace_causal_chain(self, decision_id: str, depth: Optional[int] = None) -> str:
        if not decision_id:
            return json.dumps(
                {
                    "error": "decision_id is required for trace_causal_chain",
                    "causal_chain": [],
                    "decision_id": "",
                }
            )
        max_depth = depth or self.causal_depth
        try:
            graph = getattr(self.context, "knowledge_graph", None)
            if graph is None:
                return json.dumps(
                    {
                        "error": (
                            "causal tracing is not available on this knowledge "
                            "graph (the decision context has no knowledge_graph)"
                        ),
                        "causal_chain": [],
                        "decision_id": decision_id,
                    }
                )
            trace = getattr(graph, "trace_decision_causality", None)
            if trace is None:
                return json.dumps(
                    {
                        "error": (
                            "causal tracing is not available on this knowledge graph "
                            "(graph.trace_decision_causality is not implemented)"
                        ),
                        "causal_chain": [],
                        "decision_id": decision_id,
                    }
                )
            chain = trace(decision_id, max_depth=max_depth)
            return json.dumps({"causal_chain": chain, "decision_id": decision_id})
        except Exception as exc:
            logger.warning("trace_causal_chain failed: %s", exc)
            return json.dumps(
                {"error": str(exc), "causal_chain": [], "decision_id": decision_id}
            )

    def _analyze_impact(self, decision_id: str) -> str:
        try:
            influence = self.context.analyze_decision_influence(decision_id)
            if not isinstance(influence, dict):
                influence = {"influence": str(influence)}
            influence["decision_id"] = decision_id
            return json.dumps(influence)
        except Exception as exc:
            logger.warning("analyze_impact failed: %s", exc)
            return json.dumps({"error": str(exc), "decision_id": decision_id})

    def _check_policy(
        self,
        decision_data: str,
        policy_rules: Optional[str] = None,
    ) -> str:
        try:
            data = (
                json.loads(decision_data)
                if isinstance(decision_data, str)
                else decision_data
            )
        except json.JSONDecodeError as exc:
            return json.dumps(
                {
                    "compliant": False,
                    "violations": [f"Invalid decision_data JSON: {exc}"],
                    "warnings": [],
                }
            )

        if not isinstance(data, dict):
            return json.dumps(
                {
                    "compliant": False,
                    "violations": [
                        f"decision_data must decode to a JSON object, "
                        f"got {type(data).__name__}: {data!r}"
                    ],
                    "warnings": [],
                }
            )

        violations: List[str] = []
        warnings: List[str] = []

        rules: List[str] = []
        if policy_rules:
            try:
                parsed_rules = json.loads(policy_rules)
            except json.JSONDecodeError:
                rules = [r.strip() for r in policy_rules.split(",") if r.strip()]
            else:
                if isinstance(parsed_rules, str):
                    rules = [parsed_rules]
                elif isinstance(parsed_rules, list):
                    for item in parsed_rules:
                        if isinstance(item, str):
                            rules.append(item)
                        else:
                            warnings.append(
                                f"Ignoring non-string policy rule entry: {item!r}"
                            )
                else:
                    warnings.append(
                        f"policy_rules must decode to a JSON list of rule strings, "
                        f"got {type(parsed_rules).__name__}: {parsed_rules!r}"
                    )

        for rule in rules:
            try:
                if not self._eval_rule(rule, data):
                    violations.append(f"Rule violated: {rule}")
            except Exception as exc:
                warnings.append(f"Could not evaluate rule '{rule}': {exc}")

        compliant = len(violations) == 0
        logger.debug(
            "check_policy: compliant=%s, violations=%d", compliant, len(violations)
        )
        return json.dumps(
            {
                "compliant": compliant,
                "violations": violations,
                "warnings": warnings,
            }
        )

    def _eval_rule(self, rule: str, data: Dict[str, Any]) -> bool:
        """Evaluate a simple comparison rule (``field op value``) against data.

        This is a small standalone evaluator for the tool's ``check_policy``
        action — it is intentionally independent of Semantica's policy engine
        so agents get a bounded, side-effect-free rule check. Rules are
        ``<field> <op> <value>`` comparisons only; there is no expression
        evaluation (no ``eval``), so untrusted rule strings are safe to pass.

        Values are coerced type-aware: ``true``/``false`` (and ``1``/``0``)
        become booleans, numeric literals become numbers, and string values
        that parse as numbers are compared numerically, so ``score == 0.9``
        holds for ``score: "0.90"`` and ``enabled == false`` holds for
        ``enabled: false``. Field names may contain hyphens, dots and spaces
        (e.g. ``risk-score >= 0.9``); they are matched against ``data`` keys
        as-is.
        """
        m = re.match(r"(.+?)\s*(>=|<=|!=|==|>|<)\s*(.+)$", rule.strip())
        if not m:
            raise ValueError(f"unrecognised rule format: {rule!r}")
        field, op, val_str = m.group(1), m.group(2), m.group(3).strip().strip("\"'")
        if field not in data:
            raise ValueError(f"rule references undefined field {field!r}")
        actual = data[field]
        if actual is None:
            raise ValueError(f"field {field!r} is null — cannot evaluate rule")
        val = self._coerce_value(val_str)
        if isinstance(actual, str):
            actual = self._coerce_value(actual)
        ops = {
            ">=": lambda a, b: a >= b,
            "<=": lambda a, b: a <= b,
            "!=": lambda a, b: a != b,
            "==": lambda a, b: a == b,
            ">": lambda a, b: a > b,
            "<": lambda a, b: a < b,
        }
        return ops[op](actual, val)

    @staticmethod
    def _coerce_value(value: str) -> Any:
        """Parse a rule literal into its most specific Python type."""
        text = value.strip()
        lowered = text.lower()
        if lowered in ("true", "1"):
            return True
        if lowered in ("false", "0"):
            return False
        try:
            return int(text)
        except ValueError:
            pass
        try:
            return float(text)
        except ValueError:
            pass
        return text

    # When crewai is absent there is no BaseTool to provide the public
    # ``run``/``arun`` entry points, so expose them directly.  With crewai
    # installed these are left untouched so crewai's own implementations
    # (usage tracking, ``result_as_answer``) win.
    if not CREWAI_AVAILABLE:

        def run(self, *args: Any, **kwargs: Any) -> str:
            """Run the tool synchronously (degraded mode, no crewai)."""
            return self._run(*args, **kwargs)

        async def arun(self, *args: Any, **kwargs: Any) -> str:
            """Run the tool asynchronously (degraded mode, no crewai)."""
            return self._run(*args, **kwargs)
