"""Shared runtime assembly for Explorer entry points."""

import asyncio
from typing import Dict, Optional

from fastapi import FastAPI

from ..context.agent_memory import AgentMemory
from .session import GraphSession


def explorer_capabilities(agent_memory: Optional[AgentMemory]) -> Dict[str, bool]:
    """Describe optional Explorer features exposed by the current host."""
    return {"agent_memory": agent_memory is not None}


def install_mutation_bridge(app: FastAPI, session: GraphSession) -> None:
    """Keep Explorer indexes and WebSocket clients in sync with graph writes."""
    if getattr(app.state, "_semantica_mutation_bridge_session", None) is session:
        return
    previous_callback = getattr(session.graph, "mutation_callback", None)

    def on_mutation(event_type: str, entity_id: str, payload: dict) -> None:
        session.handle_graph_mutation(event_type, entity_id, payload)
        if callable(previous_callback):
            previous_callback(event_type, entity_id, payload)
        loop = getattr(app.state, "event_loop", None)
        manager = getattr(app.state, "ws_manager", None)
        if loop is None or manager is None or loop.is_closed():
            return
        asyncio.run_coroutine_threadsafe(
            manager.broadcast(
                "graph_mutation",
                {
                    "event_type": event_type,
                    "entity_id": entity_id,
                    "payload": payload,
                },
            ),
            loop,
        )

    session.graph.mutation_callback = on_mutation
    app.state._semantica_mutation_bridge = on_mutation
    app.state._semantica_mutation_bridge_session = session
