import asyncio

import pytest


pytest.importorskip("google.adk")


from integrations.google_adk.session_service import (
    ADK_AVAILABLE,
    SemanticaSessionService,
)


def test_adk_available():
    assert ADK_AVAILABLE is True


def test_create_session():
    from semantica.context import ContextGraph

    graph = ContextGraph()
    service = SemanticaSessionService(graph)

    session = asyncio.run(
        service.create_session(
            app_name="test-app",
            user_id="test-user",
        )
    )

    assert session is not None
    assert session.app_name == "test-app"
    assert session.user_id == "test-user"
    assert session.id
    assert session.state == {}
    assert session.events == []


def test_create_session_with_state():
    from semantica.context import ContextGraph

    graph = ContextGraph()
    service = SemanticaSessionService(graph)

    state = {
        "topic": "knowledge graphs",
        "step": 1,
    }

    session = asyncio.run(
        service.create_session(
            app_name="test-app",
            user_id="test-user",
            state=state,
        )
    )

    assert session.state == state


def test_get_session():
    from semantica.context import ContextGraph

    graph = ContextGraph()
    service = SemanticaSessionService(graph)

    created = asyncio.run(
        service.create_session(
            app_name="test-app",
            user_id="test-user",
            state={"foo": "bar"},
        )
    )

    loaded = asyncio.run(
        service.get_session(
            app_name="test-app",
            user_id="test-user",
            session_id=created.id,
        )
    )

    assert loaded is not None
    assert loaded.id == created.id
    assert loaded.app_name == "test-app"
    assert loaded.user_id == "test-user"
    assert loaded.state == {"foo": "bar"}


def test_get_missing_session():
    from semantica.context import ContextGraph

    graph = ContextGraph()
    service = SemanticaSessionService(graph)

    session = asyncio.run(
        service.get_session(
            app_name="test-app",
            user_id="test-user",
            session_id="does-not-exist",
        )
    )

    assert session is None


def test_create_duplicate_session_fails():
    from semantica.context import ContextGraph

    graph = ContextGraph()
    service = SemanticaSessionService(graph)

    asyncio.run(
        service.create_session(
            app_name="test-app",
            user_id="test-user",
            session_id="fixed-session",
        )
    )

    with pytest.raises(ValueError):
        asyncio.run(
            service.create_session(
                app_name="test-app",
                user_id="test-user",
                session_id="fixed-session",
            )
        )


def test_append_event():
    from google.adk.events import Event
    from semantica.context import ContextGraph

    graph = ContextGraph()
    service = SemanticaSessionService(graph)

    session = asyncio.run(
        service.create_session(
            app_name="test-app",
            user_id="test-user",
        )
    )

    event = Event(
        author="test-agent",
        invocation_id="invocation-1",
    )

    returned = asyncio.run(
        service.append_event(
            session,
            event,
        )
    )

    assert returned is event


def test_append_event_persists():
    from google.adk.events import Event
    from semantica.context import ContextGraph

    graph = ContextGraph()
    service = SemanticaSessionService(graph)

    session = asyncio.run(
        service.create_session(
            app_name="test-app",
            user_id="test-user",
        )
    )

    event = Event(
        author="test-agent",
        invocation_id="invocation-1",
    )

    asyncio.run(
        service.append_event(
            session,
            event,
        )
    )

    loaded = asyncio.run(
        service.get_session(
            app_name="test-app",
            user_id="test-user",
            session_id=session.id,
        )
    )

    assert loaded is not None
    assert len(loaded.events) == 1
    assert loaded.events[0].author == "test-agent"
    assert loaded.events[0].invocation_id == "invocation-1"


def test_list_sessions():
    from semantica.context import ContextGraph

    graph = ContextGraph()
    service = SemanticaSessionService(graph)

    session1 = asyncio.run(
        service.create_session(
            app_name="test-app",
            user_id="test-user",
        )
    )

    session2 = asyncio.run(
        service.create_session(
            app_name="test-app",
            user_id="test-user",
        )
    )

    asyncio.run(
        service.create_session(
            app_name="other-app",
            user_id="test-user",
        )
    )

    sessions = asyncio.run(
        service.list_sessions(
            app_name="test-app",
            user_id="test-user",
        )
    )

    session_ids = {
        session.id
        for session in sessions
    }

    assert session1.id in session_ids
    assert session2.id in session_ids
    assert len(sessions) == 2


def test_session_state_is_persisted_in_graph():
    from semantica.context import ContextGraph

    graph = ContextGraph()
    service = SemanticaSessionService(graph)

    session = asyncio.run(
        service.create_session(
            app_name="test-app",
            user_id="test-user",
            state={
                "research_topic": "AI agents",
            },
        )
    )

    nodes = graph.find_nodes()

    session_nodes = [
        node
        for node in nodes
        if isinstance(node, dict)
        and node.get("type") == "ADKSession"
    ]

    assert len(session_nodes) == 1

    node = session_nodes[0]

    # ContextGraph.find_nodes() stores custom node attributes in metadata.
    assert node["metadata"]["session_id"] == session.id
    assert node["metadata"]["app_name"] == "test-app"
    assert node["metadata"]["user_id"] == "test-user"
    assert node["metadata"]["state"] == {
        "research_topic": "AI agents",
    }


def test_session_events_are_stored_as_graph_nodes():
    from google.adk.events import Event
    from semantica.context import ContextGraph

    graph = ContextGraph()
    service = SemanticaSessionService(graph)

    session = asyncio.run(
        service.create_session(
            app_name="test-app",
            user_id="test-user",
        )
    )

    event = Event(
        author="researcher",
        invocation_id="invocation-123",
    )

    asyncio.run(
        service.append_event(
            session,
            event,
        )
    )

    nodes = graph.find_nodes()

    event_nodes = [
        node
        for node in nodes
        if isinstance(node, dict)
        and node.get("type") == "ADKEvent"
    ]

    assert len(event_nodes) == 1

    event_node = event_nodes[0]

    # ContextGraph.find_nodes() stores custom node attributes in metadata.
    assert event_node["metadata"]["session_id"] == session.id
    assert event_node["metadata"]["author"] == "researcher"
    assert event_node["metadata"]["invocation_id"] == "invocation-123"


def test_session_and_event_are_connected():
    from google.adk.events import Event
    from semantica.context import ContextGraph

    graph = ContextGraph()
    service = SemanticaSessionService(graph)

    session = asyncio.run(
        service.create_session(
            app_name="test-app",
            user_id="test-user",
        )
    )

    event = Event(
        author="researcher",
        invocation_id="invocation-456",
    )

    asyncio.run(
        service.append_event(
            session,
            event,
        )
    )

    edges = graph.find_edges()

    has_event_edges = [
        edge
        for edge in edges
        if isinstance(edge, dict)
        and edge.get("type") == "HAS_EVENT"
    ]

    assert len(has_event_edges) == 1

    edge = has_event_edges[0]

    assert edge["source"] == f"adk-session:{session.id}"