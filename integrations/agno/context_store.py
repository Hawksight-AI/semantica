"""
AgnoContextStore — Graph-backed agent memory storage for Agno 2.x.

Implements Agno's v2 ``agno.db.base.BaseDb`` interface backed by Semantica's
``AgentContext``, giving Agno agents hybrid vector + context-graph user memory
that persists across sessions.

Key behaviours
--------------
- ``upsert_user_memory()``  → stores text in ``AgentContext`` (vector + graph)
                              and extracts entities into the knowledge graph
- ``get_user_memories()``   → filtered / sorted / paginated memory reads
- ``delete_user_memory()``  → removes from cache and calls ``AgentContext.forget()``
- ``record_decision()``     → records a structured decision with reasoning & outcome
- ``find_precedents()``     → returns semantically similar historical decisions
- ``get_context_for_prompt()`` → formats precedents for system-prompt injection

Only the **UserMemory** group of ``BaseDb`` is backed by Semantica storage.
The remaining groups (sessions, metrics, evals, knowledge, traces, culture,
learnings, schema versions) raise ``NotImplementedError`` — the same
degradation pattern used by the CrewAI integration.  This is safe at runtime:
Agno wraps every ``db.*`` call in ``try/except`` (see ``agno.agent._storage``
and ``agno.memory.manager``), so an unsupported group degrades to a logged
warning instead of crashing the agent run.

Install
-------
    pip install semantica[agno]

Example
-------
    >>> from semantica.context import ContextGraph
    >>> from semantica.vector_store import VectorStore
    >>> from integrations.agno import AgnoContextStore
    >>> store = AgnoContextStore(
    ...     vector_store=VectorStore(backend="faiss"),
    ...     knowledge_graph=ContextGraph(advanced_analytics=True),
    ...     decision_tracking=True,
    ... )
    >>> from agno.agent import Agent
    >>> agent = Agent(db=store, update_memory_on_run=True)
"""

from __future__ import annotations

import time
import uuid
from typing import Any, Dict, List, Optional, Tuple, Union

from semantica.utils.logging import get_logger

from ._availability import AGNO_AVAILABLE

logger = get_logger(__name__)

# ---------------------------------------------------------------------------
# Optional: Agno v2 BaseDb base class + UserMemory schema
# ---------------------------------------------------------------------------
_BaseDbBase: Any = object  # fallback when agno is absent

if AGNO_AVAILABLE:
    from agno.db.base import BaseDb as _AgnoBaseDb  # type: ignore
    from agno.db.schemas.memory import UserMemory as _AgnoUserMemory  # type: ignore

    _BaseDbBase = _AgnoBaseDb


# ---------------------------------------------------------------------------
# Lightweight UserMemory stand-in when agno is not installed
# ---------------------------------------------------------------------------
class _UserMemory:
    """Minimal stand-in for ``agno.db.schemas.memory.UserMemory``."""

    def __init__(
        self,
        memory: str,
        memory_id: Optional[str] = None,
        topics: Optional[List[str]] = None,
        user_id: Optional[str] = None,
        input: Optional[str] = None,
        created_at: Optional[int] = None,
        updated_at: Optional[int] = None,
        feedback: Optional[str] = None,
        agent_id: Optional[str] = None,
        team_id: Optional[str] = None,
    ) -> None:
        self.memory = memory
        self.memory_id = memory_id
        self.topics = topics
        self.user_id = user_id
        self.input = input
        self.created_at = created_at
        self.updated_at = updated_at
        self.feedback = feedback
        self.agent_id = agent_id
        self.team_id = team_id

    def to_dict(self) -> Dict[str, Any]:
        return {
            k: v
            for k, v in {
                "memory": self.memory,
                "memory_id": self.memory_id,
                "topics": self.topics,
                "user_id": self.user_id,
                "input": self.input,
                "created_at": self.created_at,
                "updated_at": self.updated_at,
                "feedback": self.feedback,
                "agent_id": self.agent_id,
                "team_id": self.team_id,
            }.items()
            if v is not None
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "_UserMemory":
        return cls(**data)


UserMemory = _AgnoUserMemory if AGNO_AVAILABLE else _UserMemory  # type: ignore


# ---------------------------------------------------------------------------
# AgnoContextStore
# ---------------------------------------------------------------------------
class AgnoContextStore(_BaseDbBase):  # type: ignore[misc]
    """
    Graph-backed agent memory store implementing Agno's v2 ``BaseDb``.

    Parameters
    ----------
    vector_store:
        A ``semantica.vector_store.VectorStore`` instance (or ``None`` to use
        an in-memory FAISS store created automatically).
    knowledge_graph:
        A ``semantica.context.ContextGraph`` instance (or ``None`` for a fresh
        in-memory graph).
    decision_tracking:
        Automatically record every ``upsert_user_memory`` call as a lightweight
        decision entry.
    graph_expansion:
        Reserved flag — hybrid retrieval in ``retrieve()`` already combines
        vector similarity with graph context.
    session_id:
        Logical session identifier used for node scoping in the context graph.
    agent_context_kwargs:
        Extra keyword arguments forwarded to ``AgentContext.__init__``.
    """

    def __init__(
        self,
        vector_store: Any = None,
        knowledge_graph: Any = None,
        decision_tracking: bool = True,
        graph_expansion: bool = True,
        session_id: Optional[str] = None,
        **agent_context_kwargs: Any,
    ) -> None:
        # Call agno's base init only when the real base class is available.
        if AGNO_AVAILABLE:
            super().__init__()  # type: ignore[call-arg]

        self.decision_tracking = decision_tracking
        self.graph_expansion = graph_expansion
        self.session_id = session_id or str(uuid.uuid4())
        self._memories: Dict[str, Any] = {}  # memory_id → UserMemory

        # ------------------------------------------------------------------
        # Build AgentContext from provided components
        # ------------------------------------------------------------------
        from semantica.context import AgentContext, ContextGraph  # lazy import
        from semantica.vector_store import VectorStore  # lazy import

        if knowledge_graph is None:
            knowledge_graph = ContextGraph()

        if vector_store is None:
            vector_store = VectorStore(backend="faiss")

        self._context = AgentContext(
            vector_store=vector_store,
            knowledge_graph=knowledge_graph,
            decision_tracking=decision_tracking,
            **agent_context_kwargs,
        )

        logger.info(
            "AgnoContextStore initialised",
            extra={"session_id": self.session_id, "decision_tracking": decision_tracking},
        )

    # ------------------------------------------------------------------
    # BaseDb — UserMemory group (fully implemented)
    # ------------------------------------------------------------------

    def table_exists(self, table_name: str) -> bool:
        """The in-memory graph store is always ready."""
        return True

    def clear_memories(self) -> None:
        """Delete all user memories."""
        self._memories.clear()
        try:
            self._context.forget()
        except Exception as exc:
            logger.debug("clear_memories forget() failed: %s", exc)

    def delete_user_memory(self, memory_id: str, user_id: Optional[str] = None) -> None:
        """Delete a single user memory, optionally verifying ownership."""
        existing = self._memories.get(memory_id)
        if existing is None:
            return
        if user_id is not None and getattr(existing, "user_id", None) != user_id:
            return
        self._memories.pop(memory_id, None)
        try:
            self._context.forget(memory_id=memory_id)
        except Exception as exc:
            logger.debug("forget(%s) failed: %s", memory_id, exc)
        logger.debug("delete_user_memory id=%s", memory_id)

    def delete_user_memories(
        self, memory_ids: List[str], user_id: Optional[str] = None
    ) -> None:
        """Delete multiple user memories."""
        for memory_id in memory_ids:
            self.delete_user_memory(memory_id, user_id=user_id)

    def get_all_memory_topics(self, user_id: Optional[str] = None) -> List[str]:
        """Return the union of topics across all (optionally filtered) memories."""
        topics = set()
        for memory in self._memories.values():
            if user_id is not None and getattr(memory, "user_id", None) != user_id:
                continue
            memory_topics = getattr(memory, "topics", None) or []
            topics.update(memory_topics)
        return sorted(topics)

    def get_user_memory(
        self,
        memory_id: str,
        deserialize: Optional[bool] = True,
        user_id: Optional[str] = None,
    ) -> Optional[Union[Any, Dict[str, Any]]]:
        """Return a single memory (or its dict form), honouring ``user_id``."""
        memory = self._memories.get(memory_id)
        if memory is None:
            return None
        if user_id is not None and getattr(memory, "user_id", None) != user_id:
            return None
        if not deserialize:
            return memory.to_dict() if hasattr(memory, "to_dict") else dict(memory.__dict__)
        return memory

    def get_user_memories(
        self,
        user_id: Optional[str] = None,
        agent_id: Optional[str] = None,
        team_id: Optional[str] = None,
        topics: Optional[List[str]] = None,
        search_content: Optional[str] = None,
        limit: Optional[int] = None,
        page: Optional[int] = None,
        sort_by: Optional[str] = None,
        sort_order: Optional[str] = None,
        deserialize: Optional[bool] = True,
    ) -> Union[List[Any], Tuple[List[Dict[str, Any]], int]]:
        """
        Return stored memories with filtering, sorting and pagination.

        Matches the semantics of Agno's own ``InMemoryDb``: when
        ``deserialize`` is false a ``(list_of_dicts, total_count)`` tuple is
        returned, otherwise a plain list of ``UserMemory`` objects.
        """
        filtered = []
        for memory in self._memories.values():
            if user_id is not None and getattr(memory, "user_id", None) != user_id:
                continue
            if agent_id is not None and getattr(memory, "agent_id", None) != agent_id:
                continue
            if team_id is not None and getattr(memory, "team_id", None) != team_id:
                continue
            if topics is not None:
                memory_topics = getattr(memory, "topics", None) or []
                if not any(t in memory_topics for t in topics):
                    continue
            if search_content is not None:
                if search_content.lower() not in str(getattr(memory, "memory", "")).lower():
                    continue
            filtered.append(memory)

        total_count = len(filtered)

        # Sort: newest first by default
        sort_key = sort_by or "updated_at"
        reverse = (sort_order or "desc").lower() != "asc"
        filtered.sort(key=lambda m: getattr(m, sort_key, None) or 0, reverse=reverse)

        # Paginate
        if limit is not None:
            start = (page - 1) * limit if page is not None else 0
            filtered = filtered[start : start + limit]

        if not deserialize:
            return (
                [m.to_dict() if hasattr(m, "to_dict") else dict(m.__dict__) for m in filtered],
                total_count,
            )
        return filtered

    def get_user_memory_stats(
        self,
        limit: Optional[int] = None,
        page: Optional[int] = None,
        user_id: Optional[str] = None,
    ) -> Tuple[List[Dict[str, Any]], int]:
        """Return per-user memory statistics and the total user count."""
        stats: Dict[str, Dict[str, Any]] = {}
        for memory in self._memories.values():
            uid = getattr(memory, "user_id", None)
            if user_id is not None and uid != user_id:
                continue
            entry = stats.setdefault(
                uid or "",
                {"user_id": uid, "total_memories": 0, "topics": set()},
            )
            entry["total_memories"] += 1
            entry["topics"].update(getattr(memory, "topics", None) or [])

        rows = [
            {**entry, "topics": sorted(entry["topics"])}
            for entry in stats.values()
        ]
        total_count = len(rows)

        if limit is not None:
            start = (page - 1) * limit if page is not None else 0
            rows = rows[start : start + limit]
        return rows, total_count

    def upsert_user_memory(
        self, memory: Any, deserialize: Optional[bool] = True
    ) -> Optional[Union[Any, Dict[str, Any]]]:
        """
        Persist ``memory`` into both the vector store and the context graph.

        Entity extraction is performed so the knowledge graph is populated
        with nodes for the stored content.  If ``decision_tracking`` is enabled
        a lightweight decision entry is also recorded.
        """
        mem_id = getattr(memory, "memory_id", None) or str(uuid.uuid4())
        mem_text = getattr(memory, "memory", str(memory))
        user_id = getattr(memory, "user_id", None)

        now = int(time.time())
        if getattr(memory, "created_at", None) is None:
            memory.created_at = now
        memory.updated_at = now

        # Persist in AgentContext (vector + graph)
        try:
            self._context.store(
                mem_text,
                conversation_id=user_id or self.session_id,
            )
        except Exception as exc:  # pragma: no cover
            logger.warning("AgentContext.store() failed: %s", exc)

        # Extract entities and index them into the knowledge graph
        try:
            from semantica.semantic_extract import NERExtractor

            ner = NERExtractor()
            entities = ner.extract_entities(mem_text) or []
            kg = getattr(self._context, "knowledge_graph", None)
            if kg is not None:
                for ent in entities:
                    name = getattr(ent, "name", str(ent))
                    ntype = getattr(ent, "type", "Entity")
                    try:
                        kg.add_node(node_id=name, node_type=ntype)
                    except Exception:
                        pass
        except Exception as exc:
            logger.debug("NER/graph indexing skipped: %s", exc)

        # Optional decision tracking
        if self.decision_tracking:
            try:
                self._context.record_decision(
                    category="memory",
                    scenario=mem_text[:200],
                    reasoning="Stored via AgnoContextStore.upsert_user_memory()",
                    outcome="stored",
                    confidence=1.0,
                )
            except Exception as exc:  # pragma: no cover
                logger.debug("Decision tracking skipped: %s", exc)

        # Update in-process cache
        if hasattr(memory, "memory_id"):
            memory.memory_id = mem_id
        self._memories[mem_id] = memory
        logger.debug("upsert_user_memory id=%s", mem_id)

        if not deserialize:
            return memory.to_dict() if hasattr(memory, "to_dict") else dict(memory.__dict__)
        return memory

    def upsert_memories(
        self,
        memories: List[Any],
        deserialize: Optional[bool] = True,
        preserve_updated_at: bool = False,
    ) -> List[Union[Any, Dict[str, Any]]]:
        """Bulk upsert — delegates to ``upsert_user_memory`` per memory."""
        results: List[Union[Any, Dict[str, Any]]] = []
        for memory in memories:
            if memory is None:
                continue
            if preserve_updated_at:
                # Keep the caller-provided timestamps untouched.
                created_at = getattr(memory, "created_at", None)
                updated_at = getattr(memory, "updated_at", None)
                result = self.upsert_user_memory(memory, deserialize=deserialize)
                memory.created_at = created_at
                memory.updated_at = updated_at
            else:
                result = self.upsert_user_memory(memory, deserialize=deserialize)
            if result is not None:
                results.append(result)
        return results

    # ------------------------------------------------------------------
    # BaseDb — remaining groups (not backed by Semantica storage)
    # ------------------------------------------------------------------
    # Agno wraps every db call in try/except (agno.agent._storage,
    # agno.memory.manager), so NotImplementedError here degrades to a logged
    # warning instead of crashing the agent run.  Only the UserMemory group
    # above is wired to Semantica's hybrid store.

    def _unsupported(self, method: str) -> None:
        raise NotImplementedError(
            f"AgnoContextStore does not implement BaseDb.{method} — "
            "only the UserMemory group is backed by Semantica storage."
        )

    # --- Sessions ---
    def get_session(self, *args: Any, **kwargs: Any) -> None:
        self._unsupported("get_session")

    def get_sessions(self, *args: Any, **kwargs: Any) -> None:
        self._unsupported("get_sessions")

    def upsert_session(self, *args: Any, **kwargs: Any) -> None:
        self._unsupported("upsert_session")

    def upsert_sessions(self, *args: Any, **kwargs: Any) -> None:
        self._unsupported("upsert_sessions")

    def delete_session(self, *args: Any, **kwargs: Any) -> None:
        self._unsupported("delete_session")

    def delete_sessions(self, *args: Any, **kwargs: Any) -> None:
        self._unsupported("delete_sessions")

    def rename_session(self, *args: Any, **kwargs: Any) -> None:
        self._unsupported("rename_session")

    # --- Metrics ---
    def get_metrics(self, *args: Any, **kwargs: Any) -> None:
        self._unsupported("get_metrics")

    def calculate_metrics(self, *args: Any, **kwargs: Any) -> None:
        self._unsupported("calculate_metrics")

    # --- Evals ---
    def create_eval_run(self, *args: Any, **kwargs: Any) -> None:
        self._unsupported("create_eval_run")

    def get_eval_run(self, *args: Any, **kwargs: Any) -> None:
        self._unsupported("get_eval_run")

    def get_eval_runs(self, *args: Any, **kwargs: Any) -> None:
        self._unsupported("get_eval_runs")

    def delete_eval_runs(self, *args: Any, **kwargs: Any) -> None:
        self._unsupported("delete_eval_runs")

    def rename_eval_run(self, *args: Any, **kwargs: Any) -> None:
        self._unsupported("rename_eval_run")

    # --- Knowledge contents ---
    def get_knowledge_content(self, *args: Any, **kwargs: Any) -> None:
        self._unsupported("get_knowledge_content")

    def get_knowledge_contents(self, *args: Any, **kwargs: Any) -> None:
        self._unsupported("get_knowledge_contents")

    def upsert_knowledge_content(self, *args: Any, **kwargs: Any) -> None:
        self._unsupported("upsert_knowledge_content")

    def delete_knowledge_content(self, *args: Any, **kwargs: Any) -> None:
        self._unsupported("delete_knowledge_content")

    # --- Cultural knowledge ---
    def get_cultural_knowledge(self, *args: Any, **kwargs: Any) -> None:
        self._unsupported("get_cultural_knowledge")

    def get_all_cultural_knowledge(self, *args: Any, **kwargs: Any) -> None:
        self._unsupported("get_all_cultural_knowledge")

    def upsert_cultural_knowledge(self, *args: Any, **kwargs: Any) -> None:
        self._unsupported("upsert_cultural_knowledge")

    def delete_cultural_knowledge(self, *args: Any, **kwargs: Any) -> None:
        self._unsupported("delete_cultural_knowledge")

    def clear_cultural_knowledge(self, *args: Any, **kwargs: Any) -> None:
        self._unsupported("clear_cultural_knowledge")

    # --- Learnings ---
    def get_learning(self, *args: Any, **kwargs: Any) -> None:
        self._unsupported("get_learning")

    def get_learnings(self, *args: Any, **kwargs: Any) -> None:
        self._unsupported("get_learnings")

    def upsert_learning(self, *args: Any, **kwargs: Any) -> None:
        self._unsupported("upsert_learning")

    def delete_learning(self, *args: Any, **kwargs: Any) -> None:
        self._unsupported("delete_learning")

    # --- Traces & spans ---
    def upsert_trace(self, *args: Any, **kwargs: Any) -> None:
        self._unsupported("upsert_trace")

    def get_trace(self, *args: Any, **kwargs: Any) -> None:
        self._unsupported("get_trace")

    def get_traces(self, *args: Any, **kwargs: Any) -> None:
        self._unsupported("get_traces")

    def get_trace_stats(self, *args: Any, **kwargs: Any) -> None:
        self._unsupported("get_trace_stats")

    def create_span(self, *args: Any, **kwargs: Any) -> None:
        self._unsupported("create_span")

    def create_spans(self, *args: Any, **kwargs: Any) -> None:
        self._unsupported("create_spans")

    def get_span(self, *args: Any, **kwargs: Any) -> None:
        self._unsupported("get_span")

    def get_spans(self, *args: Any, **kwargs: Any) -> None:
        self._unsupported("get_spans")

    # --- Schema versions ---
    def get_latest_schema_version(self, *args: Any, **kwargs: Any) -> None:
        self._unsupported("get_latest_schema_version")

    def upsert_schema_version(self, *args: Any, **kwargs: Any) -> None:
        self._unsupported("upsert_schema_version")

    # ------------------------------------------------------------------
    # Extended Semantica API (usable from application code directly)
    # ------------------------------------------------------------------

    def record_decision(
        self,
        category: str,
        scenario: str,
        reasoning: str,
        outcome: str,
        confidence: float = 0.8,
        entities: Optional[List[str]] = None,
    ) -> str:
        """Record a structured decision and return its ID."""
        return self._context.record_decision(
            category=category,
            scenario=scenario,
            reasoning=reasoning,
            outcome=outcome,
            confidence=confidence,
            entities=entities,
        )

    def find_precedents(
        self,
        scenario: str,
        category: Optional[str] = None,
        limit: int = 5,
    ) -> List[Dict[str, Any]]:
        """Search for similar historical decisions."""
        try:
            return self._context.find_precedents_advanced(
                scenario=scenario,
                category=category,
                limit=limit,
            )
        except Exception as exc:
            logger.warning("find_precedents failed: %s", exc)
            return []

    def retrieve(self, query: str, limit: int = 5) -> List[Dict[str, Any]]:
        """Hybrid retrieval: vector similarity + optional graph expansion."""
        try:
            return self._context.retrieve(query, max_results=limit)
        except Exception as exc:
            logger.warning("retrieve failed: %s", exc)
            return []

    def get_context_for_prompt(self, scenario: str, max_precedents: int = 3) -> str:
        """
        Return formatted precedents suitable for injection into a system prompt.

        Call this before each LLM invocation to surface relevant past decisions
        automatically.

        Parameters
        ----------
        scenario:
            Description of the current situation.
        max_precedents:
            Maximum number of precedents to include.

        Returns
        -------
        str
            Multi-line string ready to prepend to a system prompt, or an
            empty string when no relevant precedents exist.
        """
        try:
            precedents = self.find_precedents(scenario, limit=max_precedents)
            if not precedents:
                return ""
            lines = ["Relevant past decisions:"]
            for i, p in enumerate(precedents[:max_precedents], 1):
                if isinstance(p, dict):
                    sc = p.get("scenario", "")
                    outcome = p.get("outcome", "")
                    conf = p.get("confidence", "")
                else:
                    sc = getattr(p, "scenario", str(p))
                    outcome = getattr(p, "outcome", "")
                    conf = getattr(p, "confidence", "")
                lines.append(
                    f"{i}. Scenario: {sc} → Outcome: {outcome}"
                    + (f" (confidence: {conf})" if conf != "" else "")
                )
            return "\n".join(lines)
        except Exception as exc:
            logger.warning("get_context_for_prompt failed: %s", exc)
            return ""

    @property
    def context(self) -> Any:
        """Direct access to the underlying ``AgentContext``."""
        return self._context
