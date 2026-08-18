"""
Semantica-backed Google ADK session service.

Session metadata, state, and event history are represented as nodes in a
Semantica ContextGraph instead of being kept only in ADK's in-memory store.

Google ADK is an optional dependency.
"""

from __future__ import annotations

from datetime import datetime
import copy
import threading
import uuid
from typing import Any, List, Optional


try:
    from google.adk.sessions import BaseSessionService
    from google.adk.sessions.session import Event
    from google.adk.sessions.session import Session

    ADK_AVAILABLE = True

except ImportError:
    BaseSessionService = object  # type: ignore
    Event = Any  # type: ignore
    Session = Any  # type: ignore
    ADK_AVAILABLE = False


class SemanticaSessionService(BaseSessionService):
    """
    Google ADK SessionService backed by a Semantica ContextGraph.

    Graph structure:

        ADKSession
            |
            +-- HAS_EVENT --> ADKEvent

    Session metadata and state are stored in the ContextGraph node metadata.
    """

    def __init__(self, graph: Optional[Any] = None) -> None:
        if not ADK_AVAILABLE:
            raise ImportError(
                "Google ADK is required for SemanticaSessionService. "
                "Install it with: pip install semantica[google-adk]"
            )

        super().__init__()

        if graph is None:
            from semantica.context import ContextGraph

            graph = ContextGraph()

        self.graph = graph
        self._lock = threading.RLock()


    # Graph helpers

    @staticmethod
    def _node_id(session_id: str) -> str:
        """Return the internal ContextGraph node ID for a session."""
        return f"adk-session:{session_id}"

    @staticmethod
    def _event_node_id(event: Any) -> str:
        """Return the internal ContextGraph node ID for an event."""
        event_id = getattr(event, "id", None)

        if event_id:
            return f"adk-event:{event_id}"

        return f"adk-event:{uuid.uuid4()}"

    @staticmethod
    def _safe_dict(value: Any) -> dict:
        """Convert common Python/Pydantic objects into a dictionary."""
        if value is None:
            return {}

        if isinstance(value, dict):
            return copy.deepcopy(value)

        if hasattr(value, "model_dump"):
            try:
                return copy.deepcopy(value.model_dump())
            except Exception:
                pass

        if hasattr(value, "dict"):
            try:
                return copy.deepcopy(value.dict())
            except Exception:
                pass

        try:
            return {
                key: copy.deepcopy(item)
                for key, item in vars(value).items()
                if not key.startswith("_")
            }
        except Exception:
            return {}

    @staticmethod
    def _node_properties(node: Any) -> dict:
        """
        Extract application properties from a ContextGraph node.

        ContextGraph.find_nodes() returns approximately:

            {
                "id": "...",
                "type": "...",
                "content": "...",
                "metadata": {...}
            }

        The graph-level ``content`` is intentionally NOT merged into the
        application properties. For ADK Event nodes, that field is merely
        Semantica's graph label and must not become Event.content.
        """
        if isinstance(node, dict):
            metadata = node.get("metadata")

            if isinstance(metadata, dict):
                return copy.deepcopy(metadata)

            properties = node.get("properties")

            if isinstance(properties, dict):
                return copy.deepcopy(properties)

            return {}

        metadata = getattr(node, "metadata", None)

        if isinstance(metadata, dict):
            return copy.deepcopy(metadata)

        properties = getattr(node, "properties", None)

        if isinstance(properties, dict):
            return copy.deepcopy(properties)

        return {}

    def _find_session_node(
        self,
        session_id: str,
    ) -> Optional[Any]:
        """Find a session node by its logical ADK session ID."""
        expected_node_id = self._node_id(session_id)

        for node in self.graph.find_nodes() or []:
            if not isinstance(node, dict):
                continue

            # Fast path: ContextGraph node ID.
            if str(node.get("id")) == expected_node_id:
                return node

            # Fallback: logical ID stored in metadata.
            metadata = node.get("metadata")

            if (
                isinstance(metadata, dict)
                and str(metadata.get("session_id"))
                == str(session_id)
            ):
                return node

        return None

    def _find_node_by_id(
        self,
        node_id: str,
    ) -> Optional[Any]:
        """Find a ContextGraph node by graph node ID."""
        for node in self.graph.find_nodes() or []:
            if (
                isinstance(node, dict)
                and str(node.get("id")) == str(node_id)
            ):
                return node

        return None

    # ------------------------------------------------------------------
    # Event helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _serialize_event(event: Any) -> dict:
        """Serialize an ADK Event into ContextGraph metadata."""
        data = SemanticaSessionService._safe_dict(event)

        for field in (
            "id",
            "invocation_id",
            "author",
            "timestamp",
            "partial",
            "turn_complete",
            "branch",
        ):
            if field not in data and hasattr(event, field):
                value = getattr(event, field)

                if isinstance(value, datetime):
                    value = value.isoformat()

                data[field] = copy.deepcopy(value)

        return data

    def _event_nodes(
        self,
        session_id: str,
    ) -> List[Any]:
        """Return all event nodes connected to a session."""
        session_node_id = self._node_id(session_id)

        events: List[Any] = []

        for edge in self.graph.find_edges() or []:
            if not isinstance(edge, dict):
                continue

            if edge.get("source") != session_node_id:
                continue

            if edge.get("type") != "HAS_EVENT":
                continue

            target = edge.get("target")

            if target is None:
                continue

            node = self._find_node_by_id(
                str(target)
            )

            if node is not None:
                events.append(node)

        return events

    @staticmethod
    def _event_timestamp(node: Any) -> str:
        """Return a sortable timestamp for an event node."""
        properties = SemanticaSessionService._node_properties(
            node
        )

        timestamp = properties.get("timestamp")

        if timestamp is None:
            return ""

        return str(timestamp)

    def _event_from_node(
        self,
        node: Any,
    ) -> Any:
        """
        Reconstruct an ADK Event from its stored metadata.

        Important: do not include the graph's top-level ``content`` field.
        It is Semantica's node label, not ADK Event.content.
        """
        properties = self._node_properties(node)

        graph_node_id = (
            node.get("id")
            if isinstance(node, dict)
            else None
        )

        event_id = properties.get("id")

        if not event_id and graph_node_id:
            graph_node_id = str(graph_node_id)

            if graph_node_id.startswith("adk-event:"):
                event_id = graph_node_id[
                    len("adk-event:")
                ]

        if event_id:
            properties["id"] = event_id

        # ContextGraph-specific values should never become Event fields.
        properties.pop("session_id", None)

        try:
            return Event(**properties)
        except Exception:
            # Preserve the event data if the installed ADK schema changes.
            return properties

    # ------------------------------------------------------------------
    # Session helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _session_kwargs(
        app_name: str,
        user_id: str,
        session_id: str,
        state: Optional[dict],
        events: Optional[List[Any]],
    ) -> dict:
        """Build kwargs for the ADK Session model."""
        return {
            "app_name": app_name,
            "user_id": user_id,
            "id": session_id,
            "state": copy.deepcopy(state or {}),
            "events": list(events or []),
        }

    def _session_from_node(
        self,
        node: Any,
    ) -> Session:
        """Reconstruct an ADK Session from a ContextGraph node."""
        properties = self._node_properties(node)

        session_id = str(
            properties.get("session_id")
            or ""
        )

        # Fallback to the graph node ID.
        if not session_id:
            graph_node_id = (
                node.get("id")
                if isinstance(node, dict)
                else None
            )

            if graph_node_id:
                graph_node_id = str(graph_node_id)

                if graph_node_id.startswith("adk-session:"):
                    session_id = graph_node_id[
                        len("adk-session:")
                    ]
                else:
                    session_id = graph_node_id

        app_name = str(
            properties.get("app_name")
            or ""
        )

        user_id = str(
            properties.get("user_id")
            or ""
        )

        state = properties.get("state") or {}

        if not isinstance(state, dict):
            state = {}

        event_nodes = self._event_nodes(
            session_id
        )

        event_nodes.sort(
            key=self._event_timestamp
        )

        events = [
            self._event_from_node(node)
            for node in event_nodes
        ]

        return Session(
            **self._session_kwargs(
                app_name=app_name,
                user_id=user_id,
                session_id=session_id,
                state=state,
                events=events,
            )
        )

    # ------------------------------------------------------------------
    # ADK SessionService implementation
    # ------------------------------------------------------------------

    async def create_session(
        self,
        *,
        app_name: str,
        user_id: str,
        state: Optional[dict[str, Any]] = None,
        session_id: Optional[str] = None,
    ) -> Session:
        """Create and persist an ADK session."""
        with self._lock:
            session_id = (
                session_id
                or str(uuid.uuid4())
            )

            if self._find_session_node(
                session_id
            ) is not None:
                raise ValueError(
                    f"Session already exists: {session_id}"
                )

            self.graph.add_node(
                node_id=self._node_id(
                    session_id
                ),
                node_type="ADKSession",
                app_name=app_name,
                user_id=user_id,
                session_id=session_id,
                state=copy.deepcopy(
                    state or {}
                ),
                created_at=datetime.now().isoformat(),
                updated_at=datetime.now().isoformat(),
            )

            return Session(
                **self._session_kwargs(
                    app_name=app_name,
                    user_id=user_id,
                    session_id=session_id,
                    state=state,
                    events=[],
                )
            )

    async def get_session(
        self,
        *,
        app_name: str,
        user_id: str,
        session_id: str,
        config: Optional[Any] = None,
    ) -> Optional[Session]:
        """Retrieve an ADK session from ContextGraph."""
        del config

        with self._lock:
            node = self._find_session_node(
                session_id
            )

            if node is None:
                return None

            properties = self._node_properties(node)

            if properties.get("app_name") != app_name:
                return None

            if properties.get("user_id") != user_id:
                return None

            return self._session_from_node(node)

    async def append_event(
        self,
        session: Session,
        event: Event,
    ) -> Event:
        """Persist an ADK event and associate it with a session."""
        with self._lock:
            session_id = str(session.id)

            session_node = self._find_session_node(
                session_id
            )

            if session_node is None:
                raise ValueError(
                    f"Session does not exist: {session_id}"
                )

            event_node_id = self._event_node_id(
                event
            )

            event_data = self._serialize_event(
                event
            )

            self.graph.add_node(
                node_id=event_node_id,
                node_type="ADKEvent",
                session_id=session_id,
                **event_data,
            )

            self.graph.add_edge(
                source_id=self._node_id(
                    session_id
                ),
                target_id=event_node_id,
                edge_type="HAS_EVENT",
            )

            # ContextGraph's supported mutation API is add_node_attribute().
            self.graph.add_node_attribute(
                self._node_id(session_id),
                {
                    "state": self._safe_dict(
                        getattr(
                            session,
                            "state",
                            {},
                        )
                    ),
                    "updated_at": (
                        datetime.now().isoformat()
                    ),
                },
            )

            return event

    async def delete_session(
        self,
        *,
        app_name: str,
        user_id: str,
        session_id: str,
    ) -> None:
        """Delete a session and all of its graph-backed events."""
        with self._lock:
            session_node = self._find_session_node(
                session_id
            )

            if session_node is None:
                return

            properties = self._node_properties(
                session_node
            )

            if (
                properties.get("app_name")
                != app_name
            ):
                return

            if (
                properties.get("user_id")
                != user_id
            ):
                return

            session_node_id = self._node_id(
                session_id
            )

            event_node_ids = []

            for edge in self.graph.find_edges() or []:
                if not isinstance(edge, dict):
                    continue

                if (
                    edge.get("source")
                    == session_node_id
                    and edge.get("type")
                    == "HAS_EVENT"
                    and edge.get("target")
                ):
                    event_node_ids.append(
                        str(edge["target"])
                    )

            # FIX: Use `purge_node` instead of `remove_node`
            for event_node_id in event_node_ids:
                self.graph.purge_node(
                    event_node_id
                )

            # FIX: Use `purge_node` instead of `remove_node`
            self.graph.purge_node(
                session_node_id
            )

    async def list_sessions(
        self,
        *,
        app_name: str,
        user_id: str,
    ) -> List[Session]:
        """List all sessions for an application/user pair."""
        with self._lock:
            sessions: List[Session] = []

            for node in self.graph.find_nodes(
                node_type="ADKSession"
            ) or []:
                if not isinstance(node, dict):
                    continue

                properties = self._node_properties(
                    node
                )

                if (
                    properties.get("app_name")
                    != app_name
                ):
                    continue

                if (
                    properties.get("user_id")
                    != user_id
                ):
                    continue

                if not properties.get(
                    "session_id"
                ):
                    continue

                sessions.append(
                    self._session_from_node(node)
                )

            return sessions


__all__ = [
    "ADK_AVAILABLE",
    "SemanticaSessionService",
]