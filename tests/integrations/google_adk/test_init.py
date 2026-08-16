import pytest


pytest.importorskip("google.adk")


from integrations.google_adk import (
    ADK_AVAILABLE,
    SemanticaSessionService,
    __version__,
    semantica_decision_tools,
    semantica_kg_tools,
)


def test_adk_available():
    assert ADK_AVAILABLE is True


def test_version_exists():
    assert isinstance(__version__, str)
    assert __version__


def test_public_exports():
    from integrations import google_adk

    assert hasattr(google_adk, "semantica_kg_tools")
    assert hasattr(google_adk, "semantica_decision_tools")
    assert hasattr(google_adk, "SemanticaSessionService")
    assert hasattr(google_adk, "ADK_AVAILABLE")
    assert hasattr(google_adk, "__version__")


def test_kg_tools_export():
    from semantica.context import ContextGraph

    graph = ContextGraph()

    tools = semantica_kg_tools(graph)

    assert isinstance(tools, list)
    assert len(tools) == 4


def test_decision_tools_export():
    from semantica.context import ContextGraph

    graph = ContextGraph()

    tools = semantica_decision_tools(graph)

    assert isinstance(tools, list)
    assert len(tools) == 2


def test_session_service_export():
    from semantica.context import ContextGraph

    graph = ContextGraph()

    service = SemanticaSessionService(graph)

    assert service is not None
    assert service.graph is graph