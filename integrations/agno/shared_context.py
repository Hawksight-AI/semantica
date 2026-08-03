"""
AgnoSharedContext — Shared ContextGraph for Agno multi-agent teams.

A single ``ContextGraph`` is shared across all agents in an Agno ``Team``.
Each agent gets a **role-scoped view** via ``bind_agent()``, which returns an
``AgnoContextStore`` namespaced to that agent's role.  This prevents
contradictory decisions and enables knowledge reuse without coupling agent
implementations.

Install
-------
    pip install semantica[agno]

Example
-------
    >>> from semantica.context import ContextGraph
    >>> from semantica.vector_store import VectorStore
    >>> from integrations.agno import AgnoSharedContext, AgnoDecisionKit, AgnoKGToolkit
    >>> shared = AgnoSharedContext(
    ...     vector_store=VectorStore(backend="faiss"),
    ...     knowledge_graph=ContextGraph(advanced_analytics=True),
    ...     decision_tracking=True,
    ... )
    >>> from agno.agent import Agent
    >>> from agno.team import Team
    >>> researcher = Agent(
    ...     name="Researcher",
    ...     memory=shared.bind_agent("researcher"),
    ...     tools=[AgnoKGToolkit(context=shared)],
    ... )
    >>> analyst = Agent(
    ...     name="Analyst",
    ...     memory=shared.bind_agent("analyst"),
    ...     tools=[AgnoDecisionKit(context=shared)],
    ... )
    >>> team = Team(agents=[researcher, analyst], mode="coordinate")
"""

from __future__ import annotations

import threading
from typing import Any, Dict, List, Optional

from semantica.utils.logging import get_logger

from .context_store import AgnoContextStore

logger = get_logger(__name__)


class _AgentScopedStore(AgnoContextStore):
    """
    An ``AgnoContextStore`` bound to a specific agent role.

    All operations are delegated to the parent ``AgnoSharedContext``'s
    ``AgentContext`` but tagged with the agent's ``role`` for filtering.
    """

    def __init__(self, shared: "AgnoSharedContext", role: str) -> None:
        # Re-use the parent's context rather than creating a new one.
        # We skip the normal __init__ and wire all required parent attributes
        # directly so that inherited methods (record_decision, find_precedents,
        # retrieve, get_context_for_prompt) work correctly via self._context.
        self._role = role
        self._shared = shared
        self._memories: Dict[str, Any] = {}
        self.decision_tracking = shared.decision_tracking
        self.graph_expansion = shared.graph_expansion
        self.session_id = f"{shared.session_id}::{role}"
        # Use the attribute name the parent class expects.
        self._context = shared._context  # type: ignore[attr-defined]

    # ------------------------------------------------------------------
    # Override upsert / record to tag with role
    # ------------------------------------------------------------------

    def upsert_memory(self, memory: Any) -> Optional[Any]:  # type: ignore[override]
        import uuid

        mem_id = getattr(memory, "id", None) or str(uuid.uuid4())
        mem_text = getattr(memory, "memory", str(memory))

        try:
            self._context.store(mem_text, conversation_id=self.session_id)
        except Exception as exc:
            logger.warning("[%s] store failed: %s", self._role, exc, exc_info=True)

        if self.decision_tracking:
            try:
                self._context.record_decision(
                    category=f"memory:{self._role}",
                    scenario=mem_text[:200],
                    reasoning=f"Stored by agent role='{self._role}'",
                    outcome="stored",
                    confidence=1.0,
                )
            except Exception as exc:
                logger.warning("[%s] record_decision failed: %s", self._role, exc, exc_info=True)

        if hasattr(memory, "id"):
            memory.id = mem_id
        self._memories[mem_id] = memory

        # Also push into the shared registry so all agents can read it
        self._shared._shared_memories[mem_id] = memory

        return memory

    def read_memories(  # type: ignore[override]
        self,
        user_id: Optional[str] = None,
        limit: Optional[int] = None,
        sort: Optional[str] = None,
    ) -> List[Any]:
        # Return own memories + shared memories from all agents
        combined = dict(self._shared._shared_memories)
        combined.update(self._memories)

        rows = list(combined.values())
        if user_id:
            rows = [r for r in rows if getattr(r, "user_id", None) == user_id]

        reverse = sort != "asc"
        rows.sort(key=lambda r: getattr(r, "last_updated", 0), reverse=reverse)

        if limit is not None:
            rows = rows[:limit]
        return rows


class AgnoSharedContext:
    """
    Shared context graph coordinator for Agno multi-agent teams.

    Maintains a single ``AgentContext`` and ``ContextGraph`` that all agents
    access concurrently.  Thread-safety is ensured via a reentrant lock.

    Parameters
    ----------
    vector_store:
        Shared ``semantica.vector_store.VectorStore`` instance.
    knowledge_graph:
        Shared ``semantica.context.ContextGraph`` instance.
    decision_tracking:
        Enable decision recording for all bound agents.
    graph_expansion:
        Enable graph-hop expansion in all bound agents' ``read_memories``.
    session_id:
        Team-level session identifier (auto-generated when ``None``).
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
        import uuid

        from semantica.context import AgentContext, ContextGraph
        from semantica.vector_store import VectorStore

        self.decision_tracking = decision_tracking
        self.graph_expansion = graph_expansion
        self.session_id = session_id or str(uuid.uuid4())

        if knowledge_graph is None:
            knowledge_graph = ContextGraph(advanced_analytics=True)

        if vector_store is None:
            vector_store = VectorStore(backend="faiss")

        self._context = AgentContext(
            vector_store=vector_store,
            knowledge_graph=knowledge_graph,
            decision_tracking=decision_tracking,
            **agent_context_kwargs,
        )
        self._knowledge_graph = knowledge_graph

        # Shared memory pool (all agents read from this)
        self._shared_memories: Dict[str, Any] = {}
        self._lock = threading.RLock()
        self._bound_agents: Dict[str, _AgentScopedStore] = {}

        logger.info(
            "AgnoSharedContext initialised (session=%s, decision_tracking=%s)",
            self.session_id,
            decision_tracking,
        )

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def bind_agent(self, role: str) -> _AgentScopedStore:
        """
        Return a role-scoped ``AgnoContextStore`` for the given agent role.

        Multiple calls with the same ``role`` return the **same** store
        instance (idempotent).

        Parameters
        ----------
        role:
            Agent role name, e.g. ``"researcher"``, ``"analyst"``.

        Returns
        -------
        _AgentScopedStore
            An ``AgnoContextStore`` scoped to ``role`` backed by this shared
            context.
        """
        with self._lock:
            if role not in self._bound_agents:
                store = _AgentScopedStore(shared=self, role=role)
                self._bound_agents[role] = store
                logger.info("Bound agent role='%s' to shared context", role)
            return self._bound_agents[role]

    def record_decision(
        self,
        category: str,
        scenario: str,
        reasoning: str,
        outcome: str,
        confidence: float = 0.8,
        entities: Optional[List[str]] = None,
        agent_role: Optional[str] = None,
    ) -> str:
        """
        Record a decision into the shared context graph.

        Parameters
        ----------
        agent_role:
            If provided, the decision is tagged with this agent's role.
        """
        tagged_category = f"{category}:{agent_role}" if agent_role else category
        with self._lock:
            return self._context.record_decision(
                category=tagged_category,
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
        """Search all agents' decision history for similar precedents."""
        try:
            return self._context.find_precedents_advanced(
                scenario=scenario,
                category=category,
                limit=limit,
            )
        except Exception as exc:
            logger.warning("find_precedents failed: %s", exc)
            return []

    def get_shared_insights(self) -> Dict[str, Any]:
        """Return analytics over the full shared decision graph."""
        try:
            return self._context.get_context_insights()
        except Exception as exc:
            logger.warning("get_shared_insights failed: %s", exc)
            return {}

    @property
    def knowledge_graph(self) -> Any:
        """Direct access to the shared ``ContextGraph``."""
        return self._knowledge_graph

    @property
    def bound_roles(self) -> List[str]:
        """List of agent roles currently bound to this shared context."""
        return list(self._bound_agents.keys())

    def __repr__(self) -> str:  # pragma: no cover
        return (
            f"AgnoSharedContext(session={self.session_id!r}, "
            f"agents={self.bound_roles})"
        )
