"""
SemanticaKGTool — a CrewAI ``BaseTool`` exposing Semantica's knowledge-graph
pipeline (``NERExtractor``, ``RelationExtractor``, ``ContextGraph``) to agents.

Lets agents build and query a shared ``ContextGraph`` as part of their
reasoning loop.

Install
-------
    pip install semantica[crewai]

Example
-------
    >>> from integrations.crewai import SemanticaKGTool
    >>> from semantica.context import ContextGraph
    >>> from crewai import Agent, Crew, Task
    >>> graph = ContextGraph()
    >>> tool = SemanticaKGTool(graph=graph)
    >>> crew = Crew(
    ...     agents=[Agent(role="...", goal="...", backstory="...", tools=[tool])],
    ...     tasks=[...],
    ... )

Tools exposed
-------------
extract_entities   — Extract named entities from text
extract_relations  — Extract relationships between entities
add_to_graph       — Extract entities/relations from text and add them to the graph
query_graph        — Query the graph by keyword
find_related       — Find concepts related to a given entity within ``hops``
"""

from __future__ import annotations

import json
from typing import Any, List, Literal, Optional, Sequence, Type

from pydantic import BaseModel, Field

from semantica.utils.logging import get_logger

logger = get_logger(__name__)

# ---------------------------------------------------------------------------
# Optional: CrewAI BaseTool base class
# ---------------------------------------------------------------------------
CREWAI_AVAILABLE = False
CREWAI_IMPORT_ERROR: Optional[str] = None

_BaseTool: Any = object

try:
    from crewai.tools import BaseTool as _CrewAIBaseTool  # type: ignore

    _BaseTool = _CrewAIBaseTool
    CREWAI_AVAILABLE = True
except ImportError as exc:
    CREWAI_IMPORT_ERROR = str(exc)


# ---------------------------------------------------------------------------
# Input schema
# ---------------------------------------------------------------------------
class SemanticaKGToolInput(BaseModel):
    """
    Input schema for ``SemanticaKGTool``.

    Exactly one action is dispatched per call; the remaining fields are only
    used by the actions that need them.
    """

    action: Literal[
        "extract_entities",
        "extract_relations",
        "add_to_graph",
        "query_graph",
        "find_related",
    ] = Field(
        ...,
        description=(
            "Which graph operation to run. One of: 'extract_entities', "
            "'extract_relations', 'add_to_graph', 'query_graph', 'find_related'."
        ),
    )
    text: Optional[str] = Field(
        None,
        description=(
            "Input text. Used by 'extract_entities', 'extract_relations' and "
            "'add_to_graph'."
        ),
    )
    query: Optional[str] = Field(
        None, description="Search query. Used by 'query_graph'."
    )
    entity: Optional[str] = Field(
        None,
        description="Root entity name. Used by 'find_related'.",
    )
    hops: int = Field(
        1,
        ge=1,
        le=10,
        description="Maximum relationship hops. Used by 'find_related'.",
    )


# ---------------------------------------------------------------------------
# SemanticaKGTool
# ---------------------------------------------------------------------------
class SemanticaKGTool(_BaseTool):  # type: ignore[misc]
    """
    CrewAI tool that surfaces Semantica's KG pipeline as agent actions.

    Parameters
    ----------
    graph:
        A ``semantica.context.ContextGraph`` to read/write.  A fresh in-memory
        graph is used when ``None``.
    ner_extractor:
        A ``semantica.semantic_extract.NERExtractor`` instance; auto-created
        when ``None``.
    relation_extractor:
        A ``semantica.semantic_extract.RelationExtractor`` instance; auto-
        created when ``None``.
    """

    name: str = "semantica_knowledge_graph"
    description: str = (
        "Build and query a semantic knowledge graph. Actions: "
        "'extract_entities' (extract named entities from 'text'), "
        "'extract_relations' (extract relationships from 'text'), "
        "'add_to_graph' (extract entities/relations from 'text' and add them "
        "to the shared graph), 'query_graph' (keyword search using 'query'), "
        "'find_related' (find concepts related to 'entity' within 'hops' "
        "hops). Returns JSON."
    )
    args_schema: Type[BaseModel] = SemanticaKGToolInput
    graph: Any = None
    ner_extractor: Any = None
    relation_extractor: Any = None

    def __init__(
        self,
        graph: Any = None,
        ner_extractor: Any = None,
        relation_extractor: Any = None,
        **kwargs: Any,
    ) -> None:
        if CREWAI_AVAILABLE:
            super().__init__(
                graph=graph,
                ner_extractor=ner_extractor,
                relation_extractor=relation_extractor,
                **kwargs,
            )
        else:
            super().__init__()
            self.graph = graph
            self.ner_extractor = ner_extractor
            self.relation_extractor = relation_extractor

        # Lazy imports keep the module importable without heavy deps
        if self.graph is None:
            from semantica.context import ContextGraph

            self.graph = ContextGraph()
        if self.ner_extractor is None:
            from semantica.semantic_extract import NERExtractor

            self.ner_extractor = NERExtractor()
        if self.relation_extractor is None:
            from semantica.semantic_extract import RelationExtractor

            self.relation_extractor = RelationExtractor()

        logger.info("SemanticaKGTool initialised (crewai=%s)", CREWAI_AVAILABLE)

    # ------------------------------------------------------------------
    # CrewAI entry points
    # ------------------------------------------------------------------

    def _run(
        self,
        action: str,
        text: Optional[str] = None,
        query: Optional[str] = None,
        entity: Optional[str] = None,
        hops: int = 1,
        **kwargs: Any,
    ) -> str:
        """
        Dispatch a graph action.  Always returns a JSON string so the agent
        receives a structured, parseable result.
        """
        valid = {
            "extract_entities",
            "extract_relations",
            "add_to_graph",
            "query_graph",
            "find_related",
        }
        if action not in valid:
            return json.dumps(
                {
                    "error": f"Unknown action '{action}'. Valid actions: "
                    + ", ".join(sorted(valid))
                }
            )

        if action == "extract_entities":
            return self._extract_entities(text or "")
        if action == "extract_relations":
            return self._extract_relations(text or "")
        if action == "add_to_graph":
            return self._add_from_text(text or "")
        if action == "query_graph":
            return self._query_graph(query or "")
        return self._find_related(entity or "", hops=hops)

    async def _arun(
        self,
        action: str,
        text: Optional[str] = None,
        query: Optional[str] = None,
        entity: Optional[str] = None,
        hops: int = 1,
        **kwargs: Any,
    ) -> str:
        """
        Async variant of ``_run`` for CrewAI's async tool path.
        """
        return self._run(
            action=action, text=text, query=query, entity=entity, hops=hops, **kwargs
        )

    # ------------------------------------------------------------------
    # Entity/relation field access (handles both Semantica dataclasses and
    # third-party shapes like MagicMock/plain dicts in stubs)
    # ------------------------------------------------------------------

    @staticmethod
    def _first_str(obj: Any, attrs: Sequence[str]) -> str:
        """Return the first attribute value that is a non-empty string."""
        for attr in attrs:
            value = getattr(obj, attr, None)
            if isinstance(value, str) and value:
                return value
        if isinstance(obj, dict):
            for key in attrs:
                value = obj.get(key)
                if isinstance(value, str) and value:
                    return value
        return ""

    @classmethod
    def _entity_name(cls, e: Any) -> str:
        """Best-effort name for an entity-like object."""
        return cls._first_str(e, ("name", "text", "label", "node_id", "id")) or str(e)

    @classmethod
    def _entity_type(cls, e: Any) -> str:
        """Best-effort type/label for an entity-like object."""
        return cls._first_str(e, ("type", "label")) or "Entity"

    @classmethod
    def _relation_source(cls, r: Any) -> str:
        """Best-effort source of a relation-like object."""
        src = cls._first_str(r, ("source",))
        if not src:
            src = cls._entity_name(getattr(r, "subject", None))
        return src

    @classmethod
    def _relation_target(cls, r: Any) -> str:
        """Best-effort target of a relation-like object."""
        tgt = cls._first_str(r, ("target",))
        if not tgt:
            tgt = cls._entity_name(getattr(r, "object", None))
        return tgt

    @classmethod
    def _relation_type(cls, r: Any) -> str:
        """Best-effort relation type of a relation-like object."""
        rtype = cls._first_str(r, ("type", "relation", "predicate"))
        return rtype or "related_to"

    # ------------------------------------------------------------------
    # Actions
    # ------------------------------------------------------------------

    def _extract_entities(self, text: str) -> str:
        """Extract named entities from ``text``."""
        try:
            raw = self.ner_extractor.extract_entities(text) or []
            entities = [
                {
                    "name": self._entity_name(e),
                    "type": self._entity_type(e),
                    "confidence": round(float(getattr(e, "confidence", 1.0)), 4),
                }
                for e in raw
            ]
            logger.debug("extract_entities → %d entities", len(entities))
            return json.dumps({"entities": entities, "count": len(entities)})
        except Exception as exc:
            logger.warning("extract_entities failed: %s", exc)
            return json.dumps({"entities": [], "count": 0, "error": str(exc)})

    def _extract_relations(self, text: str) -> str:
        """Extract relationships between entities in ``text``."""
        try:
            raw = self.relation_extractor.extract_relations(text) or []
            relations = [
                {
                    "source": self._relation_source(r),
                    "relation": self._relation_type(r),
                    "target": self._relation_target(r),
                    "confidence": round(float(getattr(r, "confidence", 1.0)), 4),
                }
                for r in raw
            ]
            logger.debug("extract_relations → %d relations", len(relations))
            return json.dumps({"relations": relations, "count": len(relations)})
        except Exception as exc:
            logger.warning("extract_relations failed: %s", exc)
            return json.dumps({"relations": [], "count": 0, "error": str(exc)})

    def _add_from_text(self, text: str) -> str:
        """
        Extract entities and relations from ``text`` and add them to the graph.

        Duplicate nodes/edges (same id, or same source/type/target) are
        skipped so repeated calls are idempotent.  Returns JSON with the
        number of nodes/edges added.
        """
        nodes_added = 0
        edges_added = 0
        try:
            existing_nodes = {
                n.get("id") or n.get("node_id")
                for n in (self.graph.find_nodes() or [])  # type: ignore[attr-defined]
                if n.get("id") or n.get("node_id")
            }
            existing_edges = {
                (e.get("source"), e.get("type") or "related_to", e.get("target"))
                for e in (self.graph.find_edges() or [])  # type: ignore[attr-defined]
                if e.get("source") and e.get("target")
            }

            raw_entities = self.ner_extractor.extract_entities(text) or []
            entities: List[Any] = []
            seen: set = set()
            for e in raw_entities:
                name = self._entity_name(e)
                ntype = self._entity_type(e)
                if not name or name in seen:
                    continue
                seen.add(name)
                entities.append(e)
                if name in existing_nodes:
                    continue
                try:
                    if self.graph.add_node(node_id=name, node_type=ntype):
                        nodes_added += 1
                        existing_nodes.add(name)
                except Exception:
                    pass

            raw_relations = (
                self.relation_extractor.extract_relations(text, entities=entities) or []
            )
            for r in raw_relations:
                src = self._relation_source(r)
                tgt = self._relation_target(r)
                rtype = self._relation_type(r)
                if not src or not tgt:
                    continue
                key = (src, rtype, tgt)
                if key in existing_edges:
                    continue
                try:
                    if self.graph.add_edge(
                        source_id=src, target_id=tgt, edge_type=rtype
                    ):
                        edges_added += 1
                        existing_edges.add(key)
                except Exception:
                    pass
            logger.debug("add_to_graph: +%d nodes, +%d edges", nodes_added, edges_added)
            return json.dumps({"nodes_added": nodes_added, "edges_added": edges_added})
        except Exception as exc:
            logger.warning("add_to_graph failed: %s", exc)
            return json.dumps({"nodes_added": 0, "edges_added": 0, "error": str(exc)})

    def _query_graph(self, query: str) -> str:
        """Keyword-search all graph nodes for ``query``."""
        try:
            all_nodes = self.graph.find_nodes()  # type: ignore[attr-defined]
            q_lower = query.lower()
            out: List[dict] = []
            for n in all_nodes or []:
                if isinstance(n, dict):
                    node_id = n.get("id", "") or n.get("node_id", "")
                    node_type = n.get("type", "") or n.get("node_type", "")
                else:
                    node_id = getattr(n, "id", getattr(n, "label", str(n)))
                    node_type = getattr(n, "node_type", "")
                if q_lower in str(node_id).lower() or q_lower in str(node_type).lower():
                    out.append({"id": node_id, "type": node_type, "label": node_id})
            return json.dumps({"results": out, "count": len(out)})
        except Exception as exc:
            logger.warning("query_graph failed: %s", exc)
            return json.dumps({"results": [], "count": 0, "error": str(exc)})

    def _find_related(self, entity: str, hops: int = 1) -> str:
        """Find concepts related to ``entity`` within ``hops`` graph hops."""
        try:
            related: List[str] = []
            frontier = [entity]
            visited = {entity}

            g = self.graph
            for _ in range(max(1, hops)):
                next_frontier: List[str] = []
                for e in frontier:
                    try:
                        neighbours = g.get_neighbors(  # type: ignore[attr-defined]
                            node_id=e,
                            hops=1,
                        )
                        for n in neighbours or []:
                            if isinstance(n, dict):
                                label = n.get("node_id", "") or n.get("id", "")
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
            return json.dumps(
                {"entity": entity, "related": related, "count": len(related)}
            )
        except Exception as exc:
            logger.warning("find_related failed: %s", exc)
            return json.dumps(
                {"entity": entity, "related": [], "count": 0, "error": str(exc)}
            )
