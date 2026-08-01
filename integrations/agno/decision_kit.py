"""
AgnoDecisionKit — Decision Intelligence Toolkit for Agno agents.

Exposes Semantica's decision intelligence as native Agno tools so that agents
can actively record, query, and validate decisions during their reasoning loop.

Follows Agno's ``Toolkit`` pattern — each method decorated with ``@register``
(or manually registered via ``self.register()``) becomes a tool the LLM can
call.

Install
-------
    pip install semantica[agno]

Example
-------
    >>> from semantica.context import AgentContext
    >>> from integrations.agno import AgnoDecisionKit
    >>> ctx = AgentContext(decision_tracking=True)
    >>> from agno.agent import Agent
    >>> agent = Agent(tools=[AgnoDecisionKit(context=ctx)], show_tool_calls=True)

Tools exposed
-------------
record_decision      — Record a decision with reasoning and outcome
find_precedents      — Search for similar past decisions
trace_causal_chain   — Trace causal chain of a decision node
analyze_impact       — Assess downstream influence of a decision
check_policy         — Validate a decision against policy rules
get_decision_summary — Summarise decision history by category
"""

from __future__ import annotations

import json
import re
from typing import Any, Dict, List, Optional

from semantica.utils.logging import get_logger

logger = get_logger(__name__)

# ---------------------------------------------------------------------------
# Optional: Agno Toolkit base class
# ---------------------------------------------------------------------------
AGNO_AVAILABLE = False
AGNO_IMPORT_ERROR: Optional[str] = None

_ToolkitBase: Any = object

try:
    from agno.tools.toolkit import Toolkit as _AgnoToolkit  # type: ignore

    _ToolkitBase = _AgnoToolkit
    AGNO_AVAILABLE = True
except ImportError as exc:
    AGNO_IMPORT_ERROR = str(exc)


# ---------------------------------------------------------------------------
# AgnoDecisionKit
# ---------------------------------------------------------------------------
class AgnoDecisionKit(_ToolkitBase):  # type: ignore[misc]
    """
    Agno Toolkit that surfaces Semantica's decision intelligence as agent tools.

    Parameters
    ----------
    context:
        A ``semantica.context.AgentContext`` (or ``AgentContext``-compatible
        object with ``record_decision``, ``find_precedents_advanced``,
        ``analyze_decision_influence`` methods).  A fresh in-memory context is
        created when ``None``.
    max_precedents:
        Default number of precedents returned by ``find_precedents``.
    causal_depth:
        Default chain depth used by ``trace_causal_chain``.
    enable_policy_check:
        Register the ``check_policy`` tool (default: ``True``).
    """

    def __init__(
        self,
        context: Any = None,
        max_precedents: int = 5,
        causal_depth: int = 3,
        enable_policy_check: bool = True,
        **kwargs: Any,
    ) -> None:
        if AGNO_AVAILABLE:
            super().__init__(name="decision_kit", **kwargs)  # type: ignore[call-arg]

        # Always initialise _tools so the attribute exists regardless of agno
        if not hasattr(self, "_tools"):
            self._tools: list = []

        self.max_precedents = max_precedents
        self.causal_depth = causal_depth

        # Build or reuse AgentContext
        if context is None:
            from semantica.context import AgentContext
            from semantica.vector_store import VectorStore

            context = AgentContext(
                vector_store=VectorStore(backend="faiss"),
                decision_tracking=True,
            )
        self._ctx = context

        # Register tools.
        # _tools is always kept as a plain list so callers can inspect registered
        # tools regardless of whether agno is installed.  When agno IS available
        # we also call Toolkit.register() so the real agno runtime picks them up.
        tools_to_register = [
            self.record_decision,
            self.find_precedents,
            self.trace_causal_chain,
            self.analyze_impact,
            self.get_decision_summary,
        ]
        if enable_policy_check:
            tools_to_register.append(self.check_policy)

        for fn in tools_to_register:
            if AGNO_AVAILABLE:
                self.register(fn)
            if fn not in self._tools:
                self._tools.append(fn)

        logger.info("AgnoDecisionKit initialised")

    # ------------------------------------------------------------------
    # Tools
    # ------------------------------------------------------------------

    def record_decision(
        self,
        category: str,
        scenario: str,
        reasoning: str,
        outcome: str,
        confidence: float = 0.8,
        entities: Optional[str] = None,
    ) -> str:
        """
        Record a decision with its reasoning and outcome.

        Parameters
        ----------
        category:
            Domain category, e.g. ``"loan_approval"``, ``"content_moderation"``.
        scenario:
            Short description of the situation being decided.
        reasoning:
            Why this outcome was chosen.
        outcome:
            The decision result, e.g. ``"approved"``, ``"rejected"``.
        confidence:
            Confidence score in [0, 1].
        entities:
            Comma-separated list of entity names relevant to the decision.

        Returns
        -------
        str
            JSON with ``{"decision_id": "<id>", "status": "recorded"}``.
        """
        entity_list: Optional[List[str]] = None
        if entities:
            entity_list = [e.strip() for e in entities.split(",") if e.strip()]

        try:
            decision_id = self._ctx.record_decision(
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

    def find_precedents(
        self,
        scenario: str,
        category: Optional[str] = None,
        limit: Optional[int] = None,
    ) -> str:
        """
        Search for past decisions similar to the given scenario.

        Parameters
        ----------
        scenario:
            Description of the current situation.
        category:
            Optional category filter.
        limit:
            Maximum number of precedents to return.

        Returns
        -------
        str
            JSON list of precedent summaries.
        """
        k = limit or self.max_precedents
        try:
            precedents = self._ctx.find_precedents_advanced(
                scenario=scenario,
                category=category,
            )
            # Normalise to a serialisable list
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

    def trace_causal_chain(
        self,
        decision_id: str,
        depth: Optional[int] = None,
    ) -> str:
        """
        Trace the causal chain starting from a decision node.

        Parameters
        ----------
        decision_id:
            Identifier of the decision to trace.
        depth:
            Maximum chain depth to traverse.

        Returns
        -------
        str
            JSON representation of the causal chain.
        """
        max_depth = depth or self.causal_depth
        try:
            chain = self._ctx.knowledge_graph.trace_decision_causality(  # type: ignore[attr-defined]
                decision_id, depth=max_depth
            )
            return json.dumps({"causal_chain": chain, "decision_id": decision_id})
        except AttributeError:
            # Fallback if the graph doesn't expose trace_decision_causality
            try:
                chain = self._ctx.knowledge_graph.find_precedents(  # type: ignore[attr-defined]
                    category="decision", limit=max_depth
                )
                return json.dumps({"causal_chain": chain, "decision_id": decision_id})
            except Exception as exc:
                return json.dumps({"error": str(exc), "decision_id": decision_id})
        except Exception as exc:
            logger.warning("trace_causal_chain failed: %s", exc)
            return json.dumps({"error": str(exc), "decision_id": decision_id})

    def analyze_impact(self, decision_id: str) -> str:
        """
        Assess the downstream influence of a decision using graph centrality.

        Parameters
        ----------
        decision_id:
            Identifier of the decision to analyse.

        Returns
        -------
        str
            JSON with influence metrics.
        """
        try:
            influence = self._ctx.analyze_decision_influence(decision_id)
            if not isinstance(influence, dict):
                influence = {"influence": str(influence)}
            influence["decision_id"] = decision_id
            return json.dumps(influence)
        except Exception as exc:
            logger.warning("analyze_impact failed: %s", exc)
            return json.dumps({"error": str(exc), "decision_id": decision_id})

    def check_policy(
        self,
        decision_data: str,
        policy_rules: Optional[str] = None,
    ) -> str:
        """
        Validate a proposed decision against policy rules.

        Rules are evaluated inline using simple comparison expressions.  This
        avoids misuse of ``PolicyEngine.check_compliance`` (which requires a
        stored ``Decision`` + ``policy_id``) and ensures exceptions never
        silently return ``compliant=True``.  A rule that references a field
        missing from ``decision_data``, a field whose value is JSON ``null``,
        or a rule that doesn't match the expected ``<field> <op> <value>``
        format, cannot be evaluated — it is recorded in ``warnings`` (not
        ``violations``) since we don't know whether it would have passed or
        failed.  These are reported as distinct messages (missing key vs.
        null value) so the warning is actionable.

        Parameters
        ----------
        decision_data:
            JSON string describing the decision (must include ``category``,
            ``outcome``, ``confidence`` keys at minimum).  Must decode to a
            JSON object — any other shape (list, number, string, bool) is
            rejected with a single ``violations`` entry, the same as
            malformed JSON, rather than being passed through to per-rule
            evaluation where it would produce confusing internal errors.
        policy_rules:
            JSON list of rule strings, e.g.
            ``'["confidence >= 0.7", "category != \\"test\\""]'``.
            Each rule is a simple comparison: ``<field> <op> <value>``
            where op is one of ``>=``, ``<=``, ``!=``, ``==``, ``>``, ``<``.
            A JSON-encoded bare string (e.g. ``'"confidence >= 0.7"'``) is
            treated as a single rule.  Any other decoded JSON shape (e.g. a
            number or object), or a non-string list element, is recorded as
            one ``warnings`` entry and otherwise ignored rather than being
            iterated character-by-character.

        Returns
        -------
        str
            JSON with ``{"compliant": bool, "violations": [...], "warnings": [...]}``
        """
        try:
            data = json.loads(decision_data) if isinstance(decision_data, str) else decision_data
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
                    # A single rule encoded as a bare JSON string, e.g.
                    # policy_rules='"confidence >= 0.7"'. Treat it as one
                    # rule rather than iterating it character-by-character.
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
        logger.debug("check_policy: compliant=%s, violations=%d", compliant, len(violations))
        return json.dumps(
            {
                "compliant": compliant,
                "violations": violations,
                "warnings": warnings,
            }
        )

    def _eval_rule(self, rule: str, data: Dict[str, Any]) -> bool:
        """
        Evaluate a simple comparison rule (``field op value``) against data.

        Raises ``ValueError`` when the rule cannot be evaluated (unrecognised
        format, the referenced field is absent from ``data``, or the field's
        value is JSON ``null``) so that ``check_policy`` records it as a
        ``warnings`` entry instead of silently treating it as passed.
        """
        m = re.match(r"(\w+)\s*(>=|<=|!=|==|>|<)\s*(.+)", rule.strip())
        if not m:
            raise ValueError(f"unrecognised rule format: {rule!r}")
        field, op, val_str = m.group(1), m.group(2), m.group(3).strip().strip("\"'")
        if field not in data:
            raise ValueError(f"rule references undefined field {field!r}")
        actual = data[field]
        if actual is None:
            raise ValueError(f"field {field!r} is null — cannot evaluate rule")
        try:
            val: Any = type(actual)(val_str)
        except (ValueError, TypeError):
            val = val_str
        ops = {
            ">=": lambda a, b: a >= b,
            "<=": lambda a, b: a <= b,
            "!=": lambda a, b: a != b,
            "==": lambda a, b: a == b,
            ">": lambda a, b: a > b,
            "<": lambda a, b: a < b,
        }
        return ops[op](actual, val)

    def get_decision_summary(
        self,
        category: Optional[str] = None,
        since: Optional[str] = None,
        limit: int = 10,
    ) -> str:
        """
        Summarise the decision history, optionally filtered by category.

        Parameters
        ----------
        category:
            Filter to a specific decision category.
        since:
            ISO-8601 timestamp — only include decisions after this time.
        limit:
            Maximum number of decisions to include.

        Returns
        -------
        str
            JSON summary of recent decisions.
        """
        try:
            insights = self._ctx.get_context_insights()
            if not isinstance(insights, dict):
                insights = {"raw": str(insights)}
            insights["category_filter"] = category
            return json.dumps(insights)
        except Exception as exc:
            logger.warning("get_decision_summary failed: %s", exc)
            return json.dumps({"error": str(exc)})
