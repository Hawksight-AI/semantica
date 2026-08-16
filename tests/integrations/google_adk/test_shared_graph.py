import asyncio

import pytest


pytest.importorskip("google.adk")


from google.adk.events import Event

from integrations.google_adk import (
    SemanticaSessionService,
    semantica_decision_tools,
    semantica_kg_tools,
)


def test_all_integrations_share_same_graph():
    from semantica.context import ContextGraph

    graph = ContextGraph()

    kg_tools = semantica_kg_tools(graph)
    decision_tools = semantica_decision_tools(graph)
    session_service = SemanticaSessionService(graph)

    assert session_service.graph is graph

    # FunctionTool closures capture the supplied shared graph.
    assert len(kg_tools) == 4
    assert len(decision_tools) == 2


def test_shared_graph_session_and_decision_state():
    from semantica.context import ContextGraph

    graph = ContextGraph()

    session_service = SemanticaSessionService(graph)

    # Record a decision using the same graph.
    from integrations.google_adk.decision_tools import _record_decision

    decision_result = _record_decision(
        category="shared-context",
        scenario="Multi-agent workflow",
        reasoning="Verify shared graph state.",
        outcome="Shared graph works",
        confidence=0.95,
        decision_maker="test-agent",
        entities=[],
        source_documents=[],
        graph=graph,
    )

    assert decision_result["decision_id"]

    # Create a session using the same graph.
    session = asyncio.run(
        session_service.create_session(
            app_name="shared-app",
            user_id="shared-user",
            state={
                "decision_id": decision_result["decision_id"],
            },
        )
    )

    assert session.id

    loaded = asyncio.run(
        session_service.get_session(
            app_name="shared-app",
            user_id="shared-user",
            session_id=session.id,
        )
    )

    assert loaded is not None
    assert loaded.state["decision_id"] == (
        decision_result["decision_id"]
    )


def test_shared_graph_event_and_knowledge_nodes():
    from semantica.context import ContextGraph

    graph = ContextGraph()

    session_service = SemanticaSessionService(graph)

    session = asyncio.run(
        session_service.create_session(
            app_name="shared-app",
            user_id="shared-user",
        )
    )

    event = Event(
        author="researcher",
        invocation_id="shared-invocation",
    )

    asyncio.run(
        session_service.append_event(
            session,
            event,
        )
    )

    nodes = graph.find_nodes()

    session_nodes = [
        node
        for node in nodes
        if isinstance(node, dict)
        and node.get("type") == "ADKSession"
    ]

    event_nodes = [
        node
        for node in nodes
        if isinstance(node, dict)
        and node.get("type") == "ADKEvent"
    ]

    assert len(session_nodes) == 1
    assert len(event_nodes) == 1

    assert (
        session_nodes[0]["metadata"]["session_id"]
        == session.id
    )

    assert (
        event_nodes[0]["metadata"]["session_id"]
        == session.id
    )


def test_shared_graph_supports_multiple_sessions():
    from semantica.context import ContextGraph

    graph = ContextGraph()

    service = SemanticaSessionService(graph)

    session1 = asyncio.run(
        service.create_session(
            app_name="multi-agent",
            user_id="user-1",
        )
    )

    session2 = asyncio.run(
        service.create_session(
            app_name="multi-agent",
            user_id="user-2",
        )
    )

    assert session1.id != session2.id

    sessions1 = asyncio.run(
        service.list_sessions(
            app_name="multi-agent",
            user_id="user-1",
        )
    )

    sessions2 = asyncio.run(
        service.list_sessions(
            app_name="multi-agent",
            user_id="user-2",
        )
    )

    assert len(sessions1) == 1
    assert len(sessions2) == 1

    assert sessions1[0].id == session1.id
    assert sessions2[0].id == session2.id