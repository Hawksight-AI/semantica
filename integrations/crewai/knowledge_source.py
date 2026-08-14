"""
SemanticaKnowledgeSource — expose a Semantica ``ContextGraph`` as a CrewAI
knowledge source.

Lets a ``Crew`` load the current state of a knowledge graph (nodes, edges,
metadata) into its knowledge storage, so every agent gets retrieval access to
graph knowledge during the kickoff.

Install
-------
    pip install semantica[crewai]

Example
-------
    >>> from integrations.crewai import SemanticaKnowledgeSource
    >>> from semantica.context import ContextGraph
    >>> from crewai import Agent, Crew, Task
    >>> graph = ContextGraph()
    >>> graph.add_node(node_id="privacy", node_type="policy")
    >>> crew = Crew(
    ...     agents=[...],
    ...     tasks=[...],
    ...     knowledge_sources=[SemanticaKnowledgeSource(graph=graph)],
    ... )

Compatibility
-------------
Works with ``crewai >= 0.80.0``.  The ``BaseKnowledgeSource`` contract changed
between versions (``load_content`` → ``validate_content``/``aadd``), so this
source implements both legacy and current methods.  It degrades gracefully
when ``crewai`` is not installed: the class is still importable and carries the
full Semantica API, but cannot be passed to a ``Crew``.
"""

from __future__ import annotations

import asyncio
from typing import Any, Dict, List, Optional

from pydantic import Field

from semantica.utils.logging import get_logger

from ._availability import CREWAI_AVAILABLE

logger = get_logger(__name__)

# ---------------------------------------------------------------------------
# Optional: CrewAI BaseKnowledgeSource base class
# ---------------------------------------------------------------------------
_BaseKnowledgeSource: Any = object

if CREWAI_AVAILABLE:
    from crewai.knowledge.source.base_knowledge_source import (
        BaseKnowledgeSource as _BaseKnowledgeSource,  # type: ignore
    )


def _chunk_text_manual(text: str, chunk_size: int, chunk_overlap: int) -> List[str]:
    """Fallback plain-text chunker for when CrewAI helpers are unavailable."""
    if not text:
        return []
    if int(chunk_size) <= 0:
        return [text]
    size = max(1, int(chunk_size))
    overlap = max(0, int(chunk_overlap))
    if len(text) <= size:
        return [text]
    step = max(1, size - overlap)
    return [text[i : i + size] for i in range(0, len(text), step)]


class SemanticaKnowledgeSource(_BaseKnowledgeSource):  # type: ignore[misc]
    """
    CrewAI knowledge source backed by a Semantica ``ContextGraph``.

    On ``add()`` the graph's nodes and edges are serialised into readable text
    and pushed through the standard CrewAI chunking / storage pipeline, making
    graph knowledge retrievable by every agent in the crew.

    Parameters
    ----------
    graph:
        A ``semantica.context.ContextGraph`` to expose.  A fresh in-memory
        graph is created when ``None``.
    name:
        Source name.  Defaults to ``"semantica_knowledge_graph"``.
    chunk_size:
        Max characters per chunk (default 4000).
    chunk_overlap:
        Character overlap between adjacent chunks (default 200).
    """

    name: str = "semantica_knowledge_graph"
    graph: Any = Field(default=None, exclude=True)
    chunk_size: int = 4000
    chunk_overlap: int = 200
    had_live_state: bool = False
    reconstructed_state: bool = Field(default=False, exclude=True)

    def __init__(
        self,
        graph: Any = None,
        name: Optional[str] = None,
        chunk_size: int = 4000,
        chunk_overlap: int = 200,
        **kwargs: Any,
    ) -> None:
        if CREWAI_AVAILABLE:
            # Do NOT eagerly build a graph here: pydantic calls this ``__init__``
            # during ``model_validate`` (checkpoint restore), and the eager
            # build would hide that a live graph was lost. ``model_post_init``
            # rebuilds defaults and flags ``reconstructed_state`` instead.
            super().__init__(
                graph=graph,
                name=name or "semantica_knowledge_graph",
                chunk_size=int(chunk_size),
                chunk_overlap=int(chunk_overlap),
                **kwargs,
            )
        else:
            if graph is None:
                from semantica.context import ContextGraph

                graph = ContextGraph()
            super().__init__()
            self.graph = graph
            self.name = name or "semantica_knowledge_graph"
            self.chunk_size = int(chunk_size)
            self.chunk_overlap = int(chunk_overlap)

        logger.info(
            "SemanticaKnowledgeSource initialised (crewai=%s, chunk_size=%d)",
            CREWAI_AVAILABLE,
            self.chunk_size,
        )
        self.had_live_state = True

    def model_post_init(self, __context: Any) -> None:
        """Re-create default state after validation/deserialisation.

        ``graph`` is excluded from JSON serialisation (CrewAI checkpoints
        serialise their models via ``model_dump(mode="json")``), so a source
        restored from a checkpoint has ``None`` state until this runs.
        """
        if self.graph is None:
            from semantica.context import ContextGraph

            self.graph = ContextGraph()
            if self.had_live_state:
                self.reconstructed_state = True
                logger.warning(
                    "SemanticaKnowledgeSource: the live graph was lost during "
                    "serialization/checkpoint restore — an EMPTY graph was "
                    "reconstructed; re-attach the original graph before "
                    "continuing"
                )
            else:
                logger.warning(
                    "SemanticaKnowledgeSource created a fresh in-memory "
                    "ContextGraph — sources sharing knowledge must be wired to "
                    "the same graph explicitly"
                )
        self.had_live_state = True
        super().model_post_init(__context)

    # ------------------------------------------------------------------
    # Content extraction
    # ------------------------------------------------------------------

    def load_content(self) -> Dict[str, str]:
        """
        Serialise the graph into ``{id: readable_text}`` pairs.

        Nodes are rendered with their type/content/metadata, edges with their
        source, relation type and target.  This satisfies the legacy CrewAI
        ``BaseKnowledgeSource.load_content`` contract.
        """
        content: Dict[str, str] = {}
        graph = self.graph
        if graph is None:
            return content

        try:
            for node in graph.find_nodes() or []:  # type: ignore[attr-defined]
                nid = node.get("id") or node.get("node_id") or ""
                if not nid:
                    continue
                parts = [
                    "Entity",
                    str(nid),
                    "type: " + str(node.get("type", "entity")),
                ]
                if node.get("content"):
                    parts.append("content: " + str(node["content"]))
                if node.get("metadata"):
                    try:
                        import json

                        parts.append("metadata: " + json.dumps(node["metadata"]))
                    except Exception:
                        parts.append("metadata: " + str(node["metadata"]))
                content[str(nid)] = " | ".join(parts)
        except Exception as exc:
            logger.warning(
                "SemanticaKnowledgeSource.load_content (nodes) failed: %s", exc
            )

        try:
            for idx, edge in enumerate(
                graph.find_edges() or []  # type: ignore[attr-defined]
            ):
                src = edge.get("source")
                tgt = edge.get("target")
                if not src or not tgt:
                    continue
                rel = edge.get("type") or edge.get("edge_type") or "related_to"
                weight = edge.get("weight")
                text = f"{src} -[{rel}]-> {tgt}"
                if weight is not None:
                    text += f" (weight: {weight})"
                content[f"edge-{idx}"] = text
        except Exception as exc:
            logger.warning(
                "SemanticaKnowledgeSource.load_content (edges) failed: %s", exc
            )

        return content

    def validate_content(self) -> Any:
        """
        Validate that a readable graph is attached.

        Satisfies the current CrewAI ``BaseKnowledgeSource.validate_content``
        contract.
        """
        if self.graph is None:
            raise ValueError("SemanticaKnowledgeSource requires a ContextGraph.")
        return True

    # ------------------------------------------------------------------
    # Chunking + storage (abstract in both CrewAI generations)
    # ------------------------------------------------------------------

    def _chunk(self, text: str) -> List[str]:
        """Chunk ``text`` using CrewAI's helper when available, else manual."""
        helper = getattr(self, "_chunk_text", None)
        if helper is not None:
            try:
                return list(helper(text) or [])
            except Exception as exc:
                logger.debug(
                    "SemanticaKnowledgeSource._chunk_text failed, falling back: %s", exc
                )
        return _chunk_text_manual(text, self.chunk_size, self.chunk_overlap)

    def add(self) -> None:
        """
        Process the graph into chunks and store them via CrewAI storage.

        Sets both ``chunks`` (current CrewAI) and ``_chunks`` (legacy CrewAI)
        so either ``_save_documents`` implementation picks them up.  If no
        storage has been wired (e.g. not yet attached to a ``Crew``), chunks
        are kept in memory.
        """
        content = self.load_content()
        if not content:
            logger.debug("SemanticaKnowledgeSource.add: empty graph — nothing to store")
            return

        chunks: List[str] = []
        for _, text in content.items():
            if text:
                chunks.extend(self._chunk(text))

        self.chunks = chunks
        self._chunks = chunks

        save = getattr(self, "_save_documents", None)
        if save is not None:
            if getattr(self, "storage", None) is None:
                logger.debug(
                    "SemanticaKnowledgeSource.add: storage not wired — "
                    "keeping chunks in memory"
                )
            else:
                try:
                    save()
                    logger.info(
                        "SemanticaKnowledgeSource.add: stored %d chunks", len(chunks)
                    )
                    return
                except Exception as exc:
                    logger.error(
                        "SemanticaKnowledgeSource.add: storage save FAILED (%s) — "
                        "chunks are only kept in memory and agents will retrieve "
                        "nothing. Configure the Crew embedder (e.g. an OpenAI "
                        "embedder with OPENAI_API_KEY, or a local embedder) before "
                        "running the crew.",
                        exc,
                    )

        logger.info(
            "SemanticaKnowledgeSource.add: %d chunks ready in memory", len(chunks)
        )

    async def aadd(self) -> None:
        """
        Asynchronous variant of ``add()`` (current CrewAI contract).

        The graph serialisation is CPU-bound, so it runs in a thread pool to
        avoid blocking the event loop.
        """
        loop = asyncio.get_running_loop()
        await loop.run_in_executor(None, self.add)

    # ------------------------------------------------------------------
    # Inspection helpers
    # ------------------------------------------------------------------

    def get_content_summary(self) -> Dict[str, Any]:
        """
        Summarise what the source exposes (helpful for debugging / testing).
        """
        content = self.load_content()
        return {
            "name": self.name,
            "source_count": len(content),
            "chunks": len(getattr(self, "chunks", []) or []),
            "crewai_available": CREWAI_AVAILABLE,
        }
