"""
AgnoKnowledgeGraph — Relational agent knowledge backed by Semantica's KG pipeline.

Subclasses Agno's v2 ``agno.knowledge.knowledge.Knowledge`` so that Agno
agents can query a structured ``ContextGraph`` instead of a flat vector
document store.

Ingested documents pass through the full Semantica extraction pipeline:

    parse → split → NER → relation extract → graph build

and search uses multi-hop GraphRAG: vector retrieval + graph traversal +
context injection.

Install
-------
    pip install semantica[agno]

Example
-------
    >>> from integrations.agno import AgnoKnowledgeGraph
    >>> from semantica.kg import GraphBuilder
    >>> from semantica.semantic_extract import NERExtractor, RelationExtractor
    >>> kg = AgnoKnowledgeGraph(
    ...     graph_builder=GraphBuilder(),
    ...     ner_extractor=NERExtractor(),
    ...     relation_extractor=RelationExtractor(),
    ... )
    >>> kg.insert(path="regulatory_docs/", include=["*.txt"])
    >>> from agno.agent import Agent
    >>> agent = Agent(knowledge=kg, search_knowledge=True)
"""

from __future__ import annotations

from pathlib import Path
from typing import Any, Dict, List, Optional, Union

from semantica.utils.logging import get_logger

from ._availability import AGNO_AVAILABLE

logger = get_logger(__name__)

# ---------------------------------------------------------------------------
# Optional: Agno v2 Knowledge base class + Document schema
# ---------------------------------------------------------------------------
_KnowledgeBase: Any = object

if AGNO_AVAILABLE:
    from agno.knowledge.knowledge import Knowledge as _AgnoKnowledge  # type: ignore

    _KnowledgeBase = _AgnoKnowledge


# ---------------------------------------------------------------------------
# Lightweight document stand-in (used when agno is absent)
# ---------------------------------------------------------------------------
class _Document:
    """Minimal stand-in for ``agno.knowledge.document.base.Document``."""

    __slots__ = ("id", "content", "meta_data", "name")

    def __init__(
        self,
        content: str,
        id: Optional[str] = None,
        name: Optional[str] = None,
        meta_data: Optional[Dict[str, Any]] = None,
    ) -> None:
        self.id = id
        self.content = content
        self.name = name
        self.meta_data = meta_data or {}


if AGNO_AVAILABLE:
    from agno.knowledge.document.base import Document as AgnoDocument  # type: ignore
else:
    AgnoDocument = _Document  # type: ignore


# ---------------------------------------------------------------------------
# AgnoKnowledgeGraph
# ---------------------------------------------------------------------------
class AgnoKnowledgeGraph(_KnowledgeBase):  # type: ignore[misc]
    """
    Relational agent knowledge store backed by Semantica's KG pipeline.

    Parameters
    ----------
    graph_builder:
        A ``semantica.kg.GraphBuilder`` instance.  Created automatically if
        ``None``.
    ner_extractor:
        A ``semantica.semantic_extract.NERExtractor`` instance.  Created
        automatically if ``None``.
    relation_extractor:
        A ``semantica.semantic_extract.RelationExtractor`` instance.  Created
        automatically if ``None``.
    context_graph:
        An existing ``semantica.context.ContextGraph`` to use as the backing
        store.  A fresh in-memory graph is created when ``None``.
    graph_store_backend:
        Passed to ``ContextGraph`` when ``context_graph`` is ``None``.
        Supported values: ``"inmemory"`` (default), ``"neo4j"``,
        ``"falkordb"``.
    graph_store_uri:
        Connection URI for the chosen graph store backend.
    num_documents:
        Default number of documents returned by ``search()`` — mapped to
        ``max_results`` on the Agno v2 ``Knowledge`` base class.
    chunk_size:
        Maximum characters per text chunk during ingestion.
    """

    def __init__(
        self,
        graph_builder: Any = None,
        ner_extractor: Any = None,
        relation_extractor: Any = None,
        context_graph: Any = None,
        graph_store_backend: str = "inmemory",
        graph_store_uri: Optional[str] = None,
        num_documents: int = 5,
        chunk_size: int = 1000,
        name: Optional[str] = None,
        **kwargs: Any,
    ) -> None:
        if AGNO_AVAILABLE:
            super().__init__(  # type: ignore[call-arg]
                name=name or "semantica_knowledge_graph",
                max_results=num_documents,
                **kwargs,
            )
        else:
            self.name = name or "semantica_knowledge_graph"
            self.max_results = num_documents

        # Backwards-compatible alias for the Semantica-side API.
        self.num_documents = num_documents
        self.chunk_size = chunk_size
        self._graph_store_backend = graph_store_backend

        # Lazy imports to keep semantica core optional at import time
        from semantica.context import AgentContext, ContextGraph
        from semantica.kg import GraphBuilder
        from semantica.semantic_extract import NERExtractor, RelationExtractor
        from semantica.vector_store import VectorStore

        self._graph = context_graph or ContextGraph()

        # Connect GraphBuilder to the ContextGraph so build() persists content.
        self._graph_builder = graph_builder or GraphBuilder()
        self._graph_builder.graph_store = self._graph

        self._ner = ner_extractor or NERExtractor()
        self._rel = relation_extractor or RelationExtractor()

        # Internal AgentContext for vector-based retrieval (shares same graph).
        self._agent_context = AgentContext(
            vector_store=VectorStore(backend="faiss"),
            knowledge_graph=self._graph,
            decision_tracking=False,
        )

        # In-process document store for keyword-search fallback
        self._docs: List[Dict[str, Any]] = []

        logger.info(
            "AgnoKnowledgeGraph initialised",
            extra={"backend": graph_store_backend},
        )

    # ------------------------------------------------------------------
    # Knowledge v2 protocol — search
    # ------------------------------------------------------------------

    def search(
        self,
        query: str,
        max_results: Optional[int] = None,
        filters: Optional[Any] = None,
        search_type: Optional[str] = None,
    ) -> List[Any]:
        """
        Multi-hop GraphRAG search.

        1. Vector retrieval via ``AgentContext.retrieve()``.
        2. Graph hop expansion for entities found in top results.
        3. Returns a list of Agno ``Document`` objects.

        Falls back to keyword scoring over the in-process ``_docs`` cache
        when vector retrieval is unavailable.
        """
        k = max_results or self.num_documents
        results: List[Any] = []

        # Primary: vector similarity retrieval
        try:
            retrieved = self._agent_context.retrieve(query, max_results=k)
            for item in retrieved:
                if isinstance(item, dict):
                    content = item.get("content", item.get("text", str(item)))
                    entities = item.get("entities", [])
                    meta = {k2: v for k2, v in item.items() if k2 not in ("content", "text")}
                else:
                    content = str(item)
                    entities = []
                    meta = {}
                extra = self._graph_context_for(entities) if entities else ""
                if extra:
                    content = content + "\n\n[Graph context]\n" + extra
                results.append(AgnoDocument(content=content, meta_data=meta))
            if results:
                logger.debug("search('%s') → %d documents (vector)", query, len(results))
                return results
        except Exception as exc:
            logger.debug("Vector retrieval failed, using keyword fallback: %s", exc)

        # Fallback: keyword / substring scoring over in-process cache
        q_lower = query.lower()
        scored = [
            (doc, sum(1 for w in q_lower.split() if w in doc["text"].lower()))
            for doc in self._docs
        ]
        scored.sort(key=lambda t: t[1], reverse=True)
        top = [d for d, _ in scored[:k]]

        for doc in top:
            extra = self._graph_context_for(doc.get("entities", []))
            content = doc["text"]
            if extra:
                content += "\n\n[Graph context]\n" + extra
            results.append(
                AgnoDocument(
                    content=content,
                    id=doc.get("id"),
                    name=doc.get("source"),
                    meta_data=doc.get("metadata", {}),
                )
            )

        logger.debug("search('%s') → %d documents (keyword)", query, len(results))
        return results

    async def asearch(
        self,
        query: str,
        max_results: Optional[int] = None,
        filters: Optional[Any] = None,
        search_type: Optional[str] = None,
    ) -> List[Any]:
        """Async variant — delegates to the synchronous GraphRAG search."""
        return self.search(
            query=query,
            max_results=max_results,
            filters=filters,
            search_type=search_type,
        )

    # ------------------------------------------------------------------
    # Knowledge v2 protocol — insert
    # ------------------------------------------------------------------

    def insert(
        self,
        name: Optional[str] = None,
        description: Optional[str] = None,
        path: Optional[str] = None,
        url: Optional[str] = None,
        text_content: Optional[str] = None,
        metadata: Optional[Dict[str, Any]] = None,
        topics: Optional[List[str]] = None,
        remote_content: Optional[Any] = None,
        reader: Optional[Any] = None,
        include: Optional[List[str]] = None,
        exclude: Optional[List[str]] = None,
        upsert: bool = True,
        skip_if_exists: bool = False,
        auth: Optional[Any] = None,
    ) -> None:
        """
        Ingest content into the knowledge graph via the Semantica pipeline.

        Supports ``path`` (file, directory, or glob), ``url`` (http/https
        only), and ``text_content``.  ``remote_content``, ``reader`` and
        ``auth`` are accepted for signature compatibility with Agno v2 but
        are not used — ingestion always runs through Semantica's
        parse → NER → relation extract → graph build pipeline.
        """
        if remote_content is not None or reader is not None or auth is not None:
            logger.warning(
                "AgnoKnowledgeGraph.insert: remote_content/reader/auth are not "
                "supported by the Semantica pipeline and will be ignored."
            )

        if text_content:
            self._ingest_text(text_content, source=name or "<inline>")

        if path is not None:
            self._ingest_path(Path(path), include=include, exclude=exclude)

        if url is not None:
            self.load_urls([url])

    def load(
        self,
        path: Union[str, Path, None] = None,
        urls: Optional[List[str]] = None,
        texts: Optional[List[str]] = None,
        recursive: bool = False,
        recreate: bool = False,
    ) -> None:
        """
        Ingest documents into the knowledge graph (Semantica-side convenience
        wrapper around ``insert()``).

        Parameters
        ----------
        path:
            A file path, directory path, or glob pattern.
        urls:
            List of URLs to fetch and ingest.
        texts:
            Raw text strings to ingest directly.
        recursive:
            When ``path`` points to a directory, walk subdirectories.
        recreate:
            Drop all previously loaded documents before ingesting.
        """
        if recreate:
            self._docs.clear()

        if texts:
            for text in texts:
                self._ingest_text(text, source="<inline>")

        if path is not None:
            p = Path(path)
            if p.is_dir():
                pattern = "**/*" if recursive else "*"
                self._ingest_path(p, include=[pattern])
            else:
                self._ingest_path(p)

        if urls:
            self.load_urls(urls)

    def load_urls(self, urls: List[str]) -> None:
        """Fetch each URL and ingest the response body.

        Only ``http`` and ``https`` schemes are permitted to prevent SSRF.
        """
        import urllib.request
        from urllib.parse import urlparse

        for url in urls:
            parsed = urlparse(url)
            if parsed.scheme not in ("http", "https"):
                logger.warning(
                    "Skipping URL with disallowed scheme '%s': %s",
                    parsed.scheme,
                    url,
                )
                continue
            try:
                with urllib.request.urlopen(url, timeout=10) as resp:  # noqa: S310
                    text = resp.read().decode("utf-8", errors="replace")
                self._ingest_text(text, source=url)
                logger.info("Loaded URL: %s", url)
            except Exception as exc:
                logger.warning("Failed to fetch %s: %s", url, exc)

    def load_documents(
        self,
        documents: List[Any],
        upsert: bool = False,
    ) -> None:
        """Ingest a list of Agno ``Document`` objects."""
        for doc in documents:
            text = getattr(doc, "content", None) or getattr(doc, "text", str(doc))
            source = getattr(doc, "name", None) or getattr(doc, "id", "<document>")
            self._ingest_text(text, source=source)

    def get_graph_context(self, entity: str) -> str:
        """
        Return a structured text representation of an entity's subgraph
        (neighbours and edge types), suitable for structured reasoning.

        Parameters
        ----------
        entity:
            Root entity name (must have been added to the graph).

        Returns
        -------
        str
            Multi-line text with nodes and labelled edge types.
        """
        lines = [f"Entity: {entity}"]
        try:
            neighbours = self._graph.get_neighbors(node_id=entity, hops=1)
            for n in (neighbours or [])[:10]:
                if isinstance(n, dict):
                    node_id = n.get("node_id", "")
                    ntype = n.get("node_type", "")
                    edge_type = n.get("edge_type", "related_to")
                    suffix = f" (type: {ntype})" if ntype else ""
                    lines.append(f"  --[{edge_type}]--> {node_id}{suffix}")
                else:
                    lines.append(f"  --> {getattr(n, 'label', str(n))}")
        except Exception:
            pass
        return "\n".join(lines)

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _chunk_text(self, text: str) -> List[str]:
        """Split text into chunks at paragraph boundaries."""
        paragraphs = [p.strip() for p in text.split("\n\n") if p.strip()]
        if not paragraphs:
            return [text] if text.strip() else []

        chunks: List[str] = []
        current: List[str] = []
        current_len = 0

        for para in paragraphs:
            if current_len + len(para) > self.chunk_size and current:
                chunks.append("\n\n".join(current))
                current = []
                current_len = 0
            current.append(para)
            current_len += len(para)

        if current:
            chunks.append("\n\n".join(current))

        return chunks or [text]

    def _ingest_text(self, text: str, source: str = "<text>") -> None:
        """Run the full extraction pipeline and store in graph + doc list."""
        import uuid

        chunks = self._chunk_text(text)
        all_entities: List[str] = []
        all_relations: List[Any] = []

        for chunk in chunks:
            # NER
            ner_result: List[Any] = []
            try:
                ner_result = self._ner.extract_entities(chunk) or []
                chunk_entities = [getattr(e, "name", str(e)) for e in ner_result]
                all_entities.extend(chunk_entities)
            except Exception as exc:
                logger.debug("NER failed for chunk in '%s': %s", source, exc)

            # Relation extraction
            try:
                chunk_relations = self._rel.extract_relations(chunk, entities=ner_result) or []
                all_relations.extend(chunk_relations)
            except Exception as exc:
                logger.debug("RelationExtractor failed for chunk in '%s': %s", source, exc)

        # Graph build — graph_store is wired to self._graph in __init__
        try:
            sources = [
                {
                    "text": text,
                    "entities": all_entities,
                    "relations": all_relations,
                    "source": source,
                }
            ]
            self._graph_builder.build(sources)
        except Exception as exc:
            logger.debug("GraphBuilder.build() failed for '%s': %s", source, exc)

        # Vector index for AgentContext.retrieve()
        try:
            self._agent_context.store(text, conversation_id=source)
        except Exception as exc:
            logger.debug("AgentContext.store() failed for '%s': %s", source, exc)

        # Cache document for keyword-search fallback
        self._docs.append(
            {
                "id": str(uuid.uuid4()),
                "text": text,
                "source": source,
                "entities": all_entities,
                "metadata": {"source": source},
            }
        )
        logger.debug(
            "Ingested '%s' — %d entities, %d relations, %d chunks",
            source,
            len(all_entities),
            len(all_relations),
            len(chunks),
        )

    def _ingest_path(
        self,
        path: Path,
        include: Optional[List[str]] = None,
        exclude: Optional[List[str]] = None,
    ) -> None:
        """Walk a file or directory and ingest all matching files."""
        if path.is_file():
            self._ingest_file(path)
        elif path.is_dir():
            patterns = include or ["*"]
            excluded: set = set()
            for pattern in exclude or []:
                excluded.update(path.glob(pattern))
            for pattern in patterns:
                for child in sorted(path.glob(pattern)):
                    if child.is_file() and child not in excluded:
                        self._ingest_file(child)
        else:
            logger.warning("Path not found: %s", path)

    def _ingest_file(self, filepath: Path) -> None:
        try:
            text = filepath.read_text(encoding="utf-8", errors="replace")
            self._ingest_text(text, source=str(filepath))
        except Exception as exc:
            logger.warning("Could not read %s: %s", filepath, exc)

    def _graph_context_for(self, entities: List[str]) -> str:
        """Build a short text summary of graph neighbours for a set of entities."""
        if not entities:
            return ""
        lines: List[str] = []
        for entity in entities[:3]:  # limit to avoid context bloat
            try:
                neighbours = self._graph.get_neighbors(node_id=entity, hops=1)
                for n in (neighbours or [])[:3]:
                    if isinstance(n, dict):
                        node_id = n.get("node_id", "")
                        ntype = n.get("node_type", "")
                        edge_type = n.get("edge_type", "related_to")
                        lines.append(
                            f"- {entity} --[{edge_type}]--> {node_id}"
                            + (f" ({ntype})" if ntype else "")
                        )
                    else:
                        lines.append(f"- {entity} --> {getattr(n, 'label', str(n))}")
            except Exception:
                pass
        return "\n".join(lines)
