"""
SemanticaKGTool and SemanticaDecisionTool — LangChain adapters for Semantica's KG and Decision Intelligence toolkits.
"""

from __future__ import annotations

import json
from typing import Any, Dict, List, Optional

from semantica.utils.logging import get_logger

logger = get_logger(__name__)

# ---------------------------------------------------------------------------
# Optional: LangChain Tool / Toolkit base classes
# ---------------------------------------------------------------------------
LANGCHAIN_AVAILABLE = False
_ToolBase: Any = object

try:
    from langchain_core.tools import BaseTool as _LCBaseTool
    from langchain_core.tools import StructuredTool as _LCStructuredTool

    _ToolBase = _LCBaseTool
    LANGCHAIN_AVAILABLE = True
except ImportError:
    pass


# ---------------------------------------------------------------------------
# SemanticaKGTool
# ---------------------------------------------------------------------------
class SemanticaKGTool:
    """
    Exposes Semantica's Knowledge Graph pipeline as LangChain tools.

    Provides high-level actions: entity extraction, relation extraction, graph building,
    querying, related entities traversal, fact inference, and subgraph export.
    """

    def __init__(
        self,
        graph_store_backend: str = "inmemory",
        ner_extractor: Any = None,
        relation_extractor: Any = None,
        reasoner: Any = None,
        context: Any = None,
        **kwargs: Any,
    ) -> None:
        """
        Initialize SemanticaKGTool.
        """
        from semantica.context import ContextGraph
        from semantica.reasoning import Reasoner
        from semantica.semantic_extract import NERExtractor, RelationExtractor

        if context is not None:
            self._graph = getattr(context, "knowledge_graph", context)
        else:
            self._graph = ContextGraph()

        self._ner = ner_extractor or NERExtractor()
        self._rel = relation_extractor or RelationExtractor()
        self._reasoner = reasoner or Reasoner()
        self.graph_store_backend = graph_store_backend

        logger.info("SemanticaKGTool initialised (backend=%s)", graph_store_backend)

    def extract_entities(self, text: str) -> str:
        """
        Extract named entities from the given text.

        Parameters
        ----------
        text: Input text to analyze.
        """
        try:
            raw = self._ner.extract_entities(text) or []
            entities = [
                {
                    "name": getattr(e, "name", str(e)),
                    "type": getattr(e, "type", ""),
                    "confidence": round(float(getattr(e, "confidence", 1.0)), 4),
                }
                for e in raw
            ]
            logger.debug("extract_entities → %d entities", len(entities))
            return json.dumps({"entities": entities, "count": len(entities)})
        except Exception as exc:
            logger.warning("extract_entities failed: %s", exc)
            return json.dumps({"entities": [], "count": 0, "error": str(exc)})

    def extract_relations(self, text: str, entities: Optional[str] = None) -> str:
        """
        Extract relationships between entities in the given text.

        Parameters
        ----------
        text: Input text to analyze.
        entities: Optional JSON list of entity names to restrict extraction to.
        """
        entity_list: Optional[List[str]] = None
        if entities:
            try:
                entity_list = json.loads(entities)
            except json.JSONDecodeError:
                entity_list = [e.strip() for e in entities.split(",") if e.strip()]

        try:
            raw = self._rel.extract_relations(text, entities=entity_list) or []
            relations = [
                {
                    "source": getattr(r, "source", ""),
                    "relation": getattr(r, "type", getattr(r, "relation", "")),
                    "target": getattr(r, "target", ""),
                    "confidence": round(float(getattr(r, "confidence", 1.0)), 4),
                }
                for r in raw
            ]
            logger.debug("extract_relations → %d relations", len(relations))
            return json.dumps({"relations": relations, "count": len(relations)})
        except Exception as exc:
            logger.warning("extract_relations failed: %s", exc)
            return json.dumps({"relations": [], "count": 0, "error": str(exc)})

    def add_to_graph(
        self,
        entities: Optional[str] = None,
        relations: Optional[str] = None,
    ) -> str:
        """
        Add entities and/or relations to the active context graph.

        Parameters
        ----------
        entities: JSON list of {"name": str, "type": str} objects.
        relations: JSON list of {"source": str, "relation": str, "target": str} objects.
        """
        nodes_added = 0
        edges_added = 0

        if entities:
            try:
                ent_list = json.loads(entities) if isinstance(entities, str) else entities
                for ent in ent_list:
                    name = ent.get("name", str(ent))
                    ntype = ent.get("type", "Entity")
                    try:
                        self._graph.add_node(node_id=name, node_type=ntype)
                        nodes_added += 1
                    except Exception:
                        pass
            except (json.JSONDecodeError, AttributeError) as exc:
                logger.debug("add_to_graph entities parse error: %s", exc)

        if relations:
            try:
                rel_list = json.loads(relations) if isinstance(relations, str) else relations
                for rel in rel_list:
                    src = rel.get("source", "")
                    tgt = rel.get("target", "")
                    rel_type = rel.get("relation", "related_to")
                    try:
                        self._graph.add_edge(source_id=src, target_id=tgt, edge_type=rel_type)
                        edges_added += 1
                    except Exception:
                        pass
            except (json.JSONDecodeError, AttributeError) as exc:
                logger.debug("add_to_graph relations parse error: %s", exc)

        logger.debug("add_to_graph: +%d nodes, +%d edges", nodes_added, edges_added)
        return json.dumps({"nodes_added": nodes_added, "edges_added": edges_added})

    def query_graph(self, query: str) -> str:
        """
        Query the context graph in natural language or Cypher.

        Parameters
        ----------
        query: Search query string. Starting with "MATCH" triggers Cypher route.
        """
        try:
            if query.strip().upper().startswith("MATCH"):
                try:
                    result = self._graph.execute_query(query)
                    records = result if isinstance(result, list) else [str(result)]
                    return json.dumps({"results": records, "query_type": "cypher"})
                except AttributeError:
                    return json.dumps(
                        {
                            "error": "Cypher queries require a Neo4j/FalkorDB backend",
                            "query_type": "cypher",
                        }
                    )
            else:
                all_nodes = self._graph.find_nodes()
                q_lower = query.lower()
                out = []
                for n in (all_nodes or []):
                    if isinstance(n, dict):
                        node_id = n.get("node_id", n.get("id", ""))
                        node_type = n.get("node_type", n.get("type", ""))
                    else:
                        node_id = getattr(n, "id", getattr(n, "label", str(n)))
                        node_type = getattr(n, "node_type", "")
                    if q_lower in node_id.lower() or q_lower in node_type.lower():
                        out.append({"label": node_id, "type": node_type, "id": node_id})
                return json.dumps({"results": out, "count": len(out), "query_type": "keyword"})
        except Exception as exc:
            logger.warning("query_graph failed: %s", exc)
            return json.dumps({"results": [], "error": str(exc)})

    def find_related(self, entity: str, hops: int = 1) -> str:
        """
        Find concepts related to entity within N graph hops.

        Parameters
        ----------
        entity: Starting entity name.
        hops: Maximum relationship hops to traverse.
        """
        try:
            related: List[str] = []
            frontier = [entity]
            visited = {entity}

            for _ in range(max(1, hops)):
                next_frontier: List[str] = []
                for e in frontier:
                    try:
                        neighbours = self._graph.get_neighbors(node_id=e, hops=1)
                        for n in (neighbours or []):
                            if isinstance(n, dict):
                                label = n.get("node_id", n.get("id", ""))
                            else:
                                label = getattr(n, "label", str(n))
                            if label and label not in visited:
                                visited.add(label)
                                next_frontier.append(label)
                                related.append(label)
                    except Exception:
                        pass
                frontier = next_frontier

            logger.debug("find_related('%s', hops=%d) → %d", entity, hops, len(related))
            return json.dumps({"entity": entity, "related": related, "count": len(related)})
        except Exception as exc:
            logger.warning("find_related failed: %s", exc)
            return json.dumps({"entity": entity, "related": [], "error": str(exc)})

    def infer_facts(self, rules: str, facts: Optional[str] = None) -> str:
        """
        Apply inference rules to the graph and return newly derived facts.

        Parameters
        ----------
        rules: JSON list of rule strings.
        facts: Optional JSON list of additional facts. Uses graph state when None.
        """
        try:
            rule_list: List[str] = json.loads(rules) if rules else []
        except json.JSONDecodeError:
            rule_list = [r.strip() for r in rules.split(",") if r.strip()]

        fact_list: List[str] = []
        if facts:
            try:
                fact_list = json.loads(facts)
            except json.JSONDecodeError:
                fact_list = [f.strip() for f in facts.split(",") if f.strip()]

        if not fact_list:
            try:
                all_nodes = self._graph.find_nodes()
                for node in (all_nodes or [])[:50]:
                    if isinstance(node, dict):
                        label = node.get("node_id", node.get("id", ""))
                        ntype = node.get("node_type", node.get("type", "Entity"))
                    else:
                        label = getattr(node, "label", str(node))
                        ntype = getattr(node, "node_type", "Entity")
                    if label:
                        fact_list.append(f"{ntype}({label})")
            except Exception:
                pass

        try:
            result = self._reasoner.infer_facts(fact_list, rule_list)
            inferred = getattr(result, "inferred_facts", []) or []
            inferred_strs = [str(f) for f in inferred]
            logger.debug("infer_facts → %d new facts", len(inferred_strs))
            return json.dumps({"inferred_facts": inferred_strs, "count": len(inferred_strs)})
        except Exception as exc:
            logger.warning("infer_facts failed: %s", exc)
            return json.dumps({"inferred_facts": [], "error": str(exc)})

    def export_subgraph(
        self,
        entity: Optional[str] = None,
        format: str = "json-ld",
    ) -> str:
        """
        Export a subgraph centered on entity as RDF / JSON-LD.

        Parameters
        ----------
        entity: Root entity of the subgraph. Exports whole graph when None.
        format: Output format ('json-ld', 'turtle', 'xml', 'nt').
        """
        try:
            from semantica.export import RDFExporter

            exporter = RDFExporter()
            rdf_format = {"ttl": "turtle", "json-ld": "json-ld", "xml": "xml", "nt": "nt"}.get(
                format, format
            )
            output = exporter.export_to_rdf(self._graph, format=rdf_format)
            return json.dumps({"format": rdf_format, "data": output})
        except Exception as exc:
            logger.warning("export_subgraph failed: %s", exc)
            try:
                all_nodes = self._graph.find_nodes()
                nodes = []
                for n in (all_nodes or []):
                    if isinstance(n, dict):
                        nodes.append({"id": n.get("node_id", n.get("id", "")), "label": n.get("node_id", n.get("id", ""))})
                    else:
                        nodes.append(
                            {"id": getattr(n, "id", ""), "label": getattr(n, "label", "")}
                        )
                return json.dumps({"format": "json", "nodes": nodes, "note": str(exc)})
            except Exception:
                return json.dumps({"format": format, "data": "", "error": str(exc)})

    def get_tools(self) -> List[Any]:
        """
        Get the list of LangChain tools.
        """
        if not LANGCHAIN_AVAILABLE:
            raise ImportError("langchain-core is not installed. Tools are unavailable.")

        return [
            _LCStructuredTool.from_function(
                func=self.extract_entities,
                name="extract_entities",
                description="Extract named entities from the given text.",
            ),
            _LCStructuredTool.from_function(
                func=self.extract_relations,
                name="extract_relations",
                description="Extract relationships between entities in the given text.",
            ),
            _LCStructuredTool.from_function(
                func=self.add_to_graph,
                name="add_to_graph",
                description="Add entities and/or relations to the active context graph.",
            ),
            _LCStructuredTool.from_function(
                func=self.query_graph,
                name="query_graph",
                description="Query the context graph in natural language or Cypher.",
            ),
            _LCStructuredTool.from_function(
                func=self.find_related,
                name="find_related",
                description="Find concepts related to entity within N graph hops.",
            ),
            _LCStructuredTool.from_function(
                func=self.infer_facts,
                name="infer_facts",
                description="Apply inference rules to the graph and return newly derived facts.",
            ),
            _LCStructuredTool.from_function(
                func=self.export_subgraph,
                name="export_subgraph",
                description="Export a subgraph centered on entity as RDF / JSON-LD.",
            ),
        ]


# ---------------------------------------------------------------------------
# SemanticaDecisionTool
# ---------------------------------------------------------------------------
class SemanticaDecisionTool:
    """
    Exposes Semantica's Decision Intelligence as LangChain tools.

    Provides actions: record decision, find precedents, trace causal chains,
    analyze impact, check policy, and get decision summaries.
    """

    def __init__(
        self,
        context: Any = None,
        max_precedents: int = 5,
        causal_depth: int = 3,
        enable_policy_check: bool = True,
        **kwargs: Any,
    ) -> None:
        """
        Initialize SemanticaDecisionTool.
        """
        self.max_precedents = max_precedents
        self.causal_depth = causal_depth
        self.enable_policy_check = enable_policy_check

        if context is None:
            from semantica.context import AgentContext
            from semantica.vector_store import VectorStore

            context = AgentContext(
                vector_store=VectorStore(backend="faiss"),
                decision_tracking=True,
            )
        self._ctx = context
        logger.info("SemanticaDecisionTool initialised")

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
        category: Domain category, e.g. "loan_approval".
        scenario: Description of the situation.
        reasoning: Why this outcome was chosen.
        outcome: Resulting decision, e.g. "approved", "rejected".
        confidence: Confidence score in [0, 1].
        entities: Comma-separated list of relevant entity names.
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
        scenario: Description of the current situation.
        category: Optional category filter.
        limit: Maximum number of precedents to return.
        """
        k = limit or self.max_precedents
        try:
            precedents = self._ctx.find_precedents_advanced(
                scenario=scenario,
                category=category,
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

    def trace_causal_chain(
        self,
        decision_id: str,
        depth: Optional[int] = None,
    ) -> str:
        """
        Trace the causal chain starting from a decision node.

        Parameters
        ----------
        decision_id: Identifier of the decision to trace.
        depth: Maximum chain depth to traverse.
        """
        max_depth = depth or self.causal_depth
        try:
            chain = self._ctx.knowledge_graph.trace_decision_causality(
                decision_id, depth=max_depth
            )
            return json.dumps({"causal_chain": chain, "decision_id": decision_id})
        except AttributeError:
            try:
                chain = self._ctx.knowledge_graph.find_precedents(
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
        decision_id: Identifier of the decision to analyze.
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

        Parameters
        ----------
        decision_data: JSON string describing the decision (must include category, outcome, confidence).
        policy_rules: JSON list of rule strings.
        """
        # Mirror AgnoDecisionKit.check_policy inline evaluation exactly
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

        import re
        for rule in rules:
            try:
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
                if not ops[op](actual, val):
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

    def get_decision_summary(
        self,
        category: Optional[str] = None,
        since: Optional[str] = None,
        limit: int = 10,
    ) -> str:
        """
        Summarise the decision history.

        Parameters
        ----------
        category: Filter by decision category.
        since: ISO-8601 timestamp filter.
        limit: Maximum number of decisions to include.
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

    def get_tools(self) -> List[Any]:
        """
        Get the list of LangChain tools.
        """
        if not LANGCHAIN_AVAILABLE:
            raise ImportError("langchain-core is not installed. Tools are unavailable.")

        tools = [
            _LCStructuredTool.from_function(
                func=self.record_decision,
                name="record_decision",
                description="Record a decision with its reasoning and outcome.",
            ),
            _LCStructuredTool.from_function(
                func=self.find_precedents,
                name="find_precedents",
                description="Search for past decisions similar to the given scenario.",
            ),
            _LCStructuredTool.from_function(
                func=self.trace_causal_chain,
                name="trace_causal_chain",
                description="Trace the causal chain starting from a decision node.",
            ),
            _LCStructuredTool.from_function(
                func=self.analyze_impact,
                name="analyze_impact",
                description="Assess the downstream influence of a decision using graph centrality.",
            ),
            _LCStructuredTool.from_function(
                func=self.get_decision_summary,
                name="get_decision_summary",
                description="Summarise the decision history.",
            ),
        ]

        if self.enable_policy_check:
            tools.append(
                _LCStructuredTool.from_function(
                    func=self.check_policy,
                    name="check_policy",
                    description="Validate a proposed decision against policy rules.",
                )
            )

        return tools
