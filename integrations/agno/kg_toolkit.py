"""
AgnoKGToolkit — Knowledge Graph Toolkit for Agno agents.

Lets agents actively build and query the context graph as part of their
reasoning loop.  Backed by Semantica's ``NERExtractor``, ``RelationExtractor``,
``Reasoner``, and ``ContextGraph``.

Install
-------
    pip install semantica[agno]

Example
-------
    >>> from integrations.agno import AgnoKGToolkit
    >>> from agno.agent import Agent
    >>> agent = Agent(tools=[AgnoKGToolkit()], show_tool_calls=True)

Tools exposed
-------------
extract_entities   — Extract named entities from text
extract_relations  — Extract relationships between entities
add_to_graph       — Add entities / relations to the context graph
query_graph        — Query the graph (natural-language keyword or Cypher)
find_related       — Find concepts related to a given entity
infer_facts        — Apply rules to infer new facts from the graph
export_subgraph    — Export a subgraph as JSON-LD / RDF Turtle
"""

from __future__ import annotations

import json
from typing import Any, Dict, List, Optional

from semantica.utils.logging import get_logger

from ._availability import AGNO_AVAILABLE, AGNO_IMPORT_ERROR  # noqa: F401

logger = get_logger(__name__)

# ---------------------------------------------------------------------------
# Optional: Agno Toolkit base class
# ---------------------------------------------------------------------------
_ToolkitBase: Any = object

if AGNO_AVAILABLE:
    from agno.tools.toolkit import Toolkit as _AgnoToolkit  # type: ignore

    _ToolkitBase = _AgnoToolkit


# ---------------------------------------------------------------------------
# AgnoKGToolkit
# ---------------------------------------------------------------------------
class AgnoKGToolkit(_ToolkitBase):  # type: ignore[misc]
    """
    Agno Toolkit that surfaces Semantica's KG pipeline as agent tools.

    Parameters
    ----------
    graph_store_backend:
        Storage backend for the internal ``ContextGraph``.  One of
        ``"inmemory"`` (default), ``"neo4j"``, ``"falkordb"``.
    ner_extractor:
        A ``semantica.semantic_extract.NERExtractor`` instance; auto-created
        when ``None``.
    relation_extractor:
        A ``semantica.semantic_extract.RelationExtractor`` instance; auto-
        created when ``None``.
    reasoner:
        A ``semantica.reasoning.Reasoner`` instance; auto-created when
        ``None``.
    context:
        An existing ``AgentContext`` or ``ContextGraph`` to attach to.  A
        fresh in-memory ``ContextGraph`` is used when ``None``.
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
        if AGNO_AVAILABLE:
            super().__init__(name="kg_toolkit", **kwargs)  # type: ignore[call-arg]

        # Always initialise _tools so the attribute exists regardless of agno
        if not hasattr(self, "_tools"):
            self._tools: list = []

        # Lazy imports
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

        # Register tools.
        # _tools is always kept as a plain list so callers can inspect registered
        # tools regardless of whether agno is installed.  When agno IS available
        # we also call Toolkit.register() so the real agno runtime picks them up.
        tools_to_register = [
            self.extract_entities,
            self.extract_relations,
            self.add_to_graph,
            self.query_graph,
            self.find_related,
            self.infer_facts,
            self.export_subgraph,
        ]
        for fn in tools_to_register:
            if AGNO_AVAILABLE:
                self.register(fn)
            if fn not in self._tools:
                self._tools.append(fn)

        logger.info("AgnoKGToolkit initialised (backend=%s)", graph_store_backend)

    # ------------------------------------------------------------------
    # Tools
    # ------------------------------------------------------------------

    def extract_entities(self, text: str) -> str:
        """
        Extract named entities from the given text.

        Parameters
        ----------
        text:
            Input text to analyse.

        Returns
        -------
        str
            JSON list of ``{"name": str, "type": str, "confidence": float}``.
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
        text:
            Input text to analyse.
        entities:
            Optional JSON list of entity names to restrict extraction to.

        Returns
        -------
        str
            JSON list of ``{"source": str, "relation": str, "target": str, "confidence": float}``.
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
        entities:
            JSON list of ``{"name": str, "type": str}`` objects.
        relations:
            JSON list of ``{"source": str, "relation": str, "target": str}`` objects.

        Returns
        -------
        str
            JSON summary of nodes and edges added.
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
                        # ContextGraph.add_node(node_id, node_type, content=None, **props)
                        self._graph.add_node(node_id=name, node_type=ntype)  # type: ignore[attr-defined]
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
                        # ContextGraph.add_edge(source_id, target_id, edge_type, **props)
                        self._graph.add_edge(source_id=src, target_id=tgt, edge_type=rel_type)  # type: ignore[attr-defined]
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

        For natural-language queries all nodes are retrieved and filtered by
        whether ``query`` appears in their ``node_id``.  Pass a string starting
        with ``"MATCH"`` for raw Cypher execution (requires a Neo4j / FalkorDB
        backend).

        Parameters
        ----------
        query:
            Search query string.

        Returns
        -------
        str
            JSON list of matching nodes / records.
        """
        try:
            if query.strip().upper().startswith("MATCH"):
                # Cypher path
                try:
                    result = self._graph.execute_query(query)  # type: ignore[attr-defined]
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
                # Natural-language keyword lookup — ContextGraph.find_nodes() → List[Dict]
                all_nodes = self._graph.find_nodes()  # type: ignore[attr-defined]
                q_lower = query.lower()
                out = []
                for n in (all_nodes or []):
                    if isinstance(n, dict):
                        node_id = n.get("node_id", "")
                        node_type = n.get("node_type", "")
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
        Find concepts related to ``entity`` within ``hops`` graph hops.

        Parameters
        ----------
        entity:
            The entity name to start from.
        hops:
            Maximum number of relationship hops to traverse.

        Returns
        -------
        str
            JSON list of related entity names.
        """
        try:
            related: List[str] = []
            frontier = [entity]
            visited = {entity}

            for _ in range(max(1, hops)):
                next_frontier: List[str] = []
                for e in frontier:
                    try:
                        # ContextGraph.get_neighbors(node_id, hops=1, ...) → List[Dict]
                        neighbours = self._graph.get_neighbors(node_id=e, hops=1)  # type: ignore[attr-defined]
                        for n in (neighbours or []):
                            if isinstance(n, dict):
                                label = n.get("node_id", "")
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
        rules:
            JSON list of rule strings, e.g.
            ``'["IF Person(?x) THEN Human(?x)"]'``
        facts:
            Optional JSON list of additional fact strings to load before
            inference.  When ``None``, the current graph state is used.

        Returns
        -------
        str
            JSON list of inferred fact strings.
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
            # Derive facts from graph nodes via the public API
            try:
                all_nodes = self._graph.find_nodes()  # type: ignore[attr-defined]
                for node in (all_nodes or [])[:50]:
                    if isinstance(node, dict):
                        label = node.get("node_id", "")
                        ntype = node.get("node_type", "Entity")
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
        Export a subgraph centred on ``entity`` as RDF / JSON-LD.

        Parameters
        ----------
        entity:
            Root entity of the subgraph.  The whole graph is exported when
            ``None``.
        format:
            Output format: ``"json-ld"`` (default), ``"turtle"`` / ``"ttl"``,
            ``"xml"``, ``"nt"``.

        Returns
        -------
        str
            Serialised subgraph in the requested format (JSON string wrapper).
        """
        try:
            from semantica.export import RDFExporter  # lazy import

            exporter = RDFExporter()
            rdf_format = {"ttl": "turtle", "json-ld": "json-ld", "xml": "xml", "nt": "nt"}.get(
                format, format
            )
            output = exporter.export_to_rdf(self._graph, format=rdf_format)  # type: ignore[arg-type]
            return json.dumps({"format": rdf_format, "data": output})
        except Exception as exc:
            logger.warning("export_subgraph failed: %s", exc)
            # Fallback: return graph nodes via the public API
            try:
                all_nodes = self._graph.find_nodes()  # type: ignore[attr-defined]
                nodes = []
                for n in (all_nodes or []):
                    if isinstance(n, dict):
                        nodes.append({"id": n.get("node_id", ""), "label": n.get("node_id", "")})
                    else:
                        nodes.append(
                            {"id": getattr(n, "id", ""), "label": getattr(n, "label", "")}
                        )
                return json.dumps({"format": "json", "nodes": nodes, "note": str(exc)})
            except Exception:
                return json.dumps({"format": format, "data": "", "error": str(exc)})
