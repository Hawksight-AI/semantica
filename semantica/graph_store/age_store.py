"""
Apache AGE Store Module

This module provides Apache AGE (PostgreSQL graph extension) integration for
property graph storage and Cypher querying in the Semantica framework, supporting
full CRUD operations, transactions, and graph analytics.

Apache AGE extends PostgreSQL with graph database functionality, enabling
hybrid relational + graph workloads using openCypher queries executed via SQL.

Key Features:
    - OpenCypher query language support via SQL wrapper
    - Node and relationship CRUD operations
    - Transaction support with explicit commit/rollback
    - Parameterized queries to prevent SQL injection
    - AGE internal ID / semantic ID separation
    - Multi-label emulation (one AGE label + property array)
    - Batch operations with progress tracking
    - Optional dependency handling (psycopg2)

Main Classes:
    - ApacheAgeStore: Main AGE store for graph operations

Example Usage:
    >>> from semantica.graph_store.age_store import ApacheAgeStore
    >>> store = ApacheAgeStore(
    ...     connection_string="host=localhost dbname=agedb user=postgres password=secret",
    ...     graph_name="semantica"
    ... )
    >>> store.connect()
    >>> node = store.create_node(labels=["Person"], properties={"name": "Alice"})
    >>> results = store.execute_query("MATCH (p:Person) RETURN p")
    >>> store.close()

Note:
    - AGE auto-generates internal vertex/edge IDs.
    - The ``node_id`` parameter in CRUD methods refers to the AGE internal ID.
    - Semantic IDs can be stored in the ``semantica_id`` property.
    - AGE supports exactly one label per vertex; additional labels are stored
      in a ``labels`` property array.

Author: Semantica Contributors
License: MIT
"""

import json
import re
from typing import Any, Dict, List, Optional, Union

from ..utils.exceptions import ProcessingError, ValidationError
from ..utils.logging import get_logger
from ..utils.progress_tracker import get_progress_tracker

# Optional psycopg2 import
try:
    import psycopg2
    import psycopg2.extras

    PSYCOPG2_AVAILABLE = True
except (ImportError, OSError):
    PSYCOPG2_AVAILABLE = False
    psycopg2 = None


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _sanitize_label(label: str) -> str:
    """
    Sanitize a Cypher label to prevent injection.

    Only allows alphanumeric characters and underscores.

    Args:
        label: Raw label string.

    Returns:
        Sanitized label string.

    Raises:
        ValidationError: If the label contains invalid characters.
    """
    if not re.match(r"^[A-Za-z_][A-Za-z0-9_]*$", label):
        raise ValidationError(
            f"Invalid label '{label}': must start with a letter or underscore "
            "and contain only alphanumeric characters and underscores."
        )
    return label


def _sanitize_rel_type(rel_type: str) -> str:
    """
    Sanitize a relationship type string.

    Args:
        rel_type: Raw relationship type.

    Returns:
        Sanitized relationship type.

    Raises:
        ValidationError: If the type contains invalid characters.
    """
    if not re.match(r"^[A-Za-z_][A-Za-z0-9_]*$", rel_type):
        raise ValidationError(
            f"Invalid relationship type '{rel_type}': must start with a letter or "
            "underscore and contain only alphanumeric characters and underscores."
        )
    return rel_type


def _props_to_cypher_literal(properties: Dict[str, Any]) -> str:
    """
    Convert a Python dict to an AGE-compatible Cypher map literal.

    AGE does not support ``$param`` style parameter binding inside
    ``cypher()`` calls, so property values must be inlined as literals
    with proper escaping.

    Args:
        properties: Dictionary of property key-value pairs.

    Returns:
        Cypher map literal string, e.g. ``{name: 'Alice', age: 30}``.
    """
    if not properties:
        return "{}"
    parts = []
    for key, value in properties.items():
        # Validate key
        if not re.match(r"^[A-Za-z_][A-Za-z0-9_]*$", key):
            raise ValidationError(f"Invalid property key: '{key}'")
        parts.append(f"{key}: {_value_to_cypher_literal(value)}")
    return "{" + ", ".join(parts) + "}"


def _value_to_cypher_literal(value: Any) -> str:
    """
    Convert a single Python value to a Cypher literal string.

    Args:
        value: Python value.

    Returns:
        Cypher literal representation.
    """
    if value is None:
        return "null"
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, int):
        return str(value)
    if isinstance(value, float):
        return repr(value)
    if isinstance(value, str):
        # Escape single quotes for Cypher strings
        escaped = value.replace("\\", "\\\\").replace("'", "\\'")
        return f"'{escaped}'"
    if isinstance(value, (list, tuple)):
        inner = ", ".join(_value_to_cypher_literal(v) for v in value)
        return f"[{inner}]"
    if isinstance(value, dict):
        return _props_to_cypher_literal(value)
    # Fallback: convert to string
    escaped = str(value).replace("\\", "\\\\").replace("'", "\\'")
    return f"'{escaped}'"


def _parse_agtype(raw: Any) -> Any:
    """
    Parse an agtype value returned by AGE into a Python object.

    AGE returns results as ``agtype`` which may be a JSON-like string
    with an optional ``::vertex`` / ``::edge`` / ``::path`` suffix.

    Args:
        raw: Raw value from the cursor.

    Returns:
        Parsed Python object (dict, list, or scalar).
    """
    if raw is None:
        return None
    if not isinstance(raw, str):
        return raw

    text = raw.strip()

    # Strip AGE type suffixes
    for suffix in ("::vertex", "::edge", "::path", "::numeric",
                    "::integer", "::float", "::boolean", "::text"):
        if text.endswith(suffix):
            text = text[: -len(suffix)].strip()
            break

    # Try JSON parse
    try:
        return json.loads(text)
    except (json.JSONDecodeError, ValueError):
        pass

    # Boolean literals
    if text.lower() == "true":
        return True
    if text.lower() == "false":
        return False

    # Numeric
    try:
        if "." in text:
            return float(text)
        return int(text)
    except ValueError:
        pass

    return text


def _vertex_to_node_dict(vertex: Any) -> Dict[str, Any]:
    """
    Convert a parsed AGE vertex dict to the standard node return format.

    Expected vertex dict shape from AGE::

        {"id": <int>, "label": "<label>", "properties": {…}}

    The returned dict matches Neo4jStore output::

        {"id": <int>, "labels": [<str>, …], "properties": {…}}

    Args:
        vertex: Parsed vertex dict.

    Returns:
        Standardised node dict.
    """
    if not isinstance(vertex, dict):
        return {"id": None, "labels": [], "properties": {}}

    props = dict(vertex.get("properties", {}))
    primary_label = vertex.get("label", "")
    labels = [primary_label] if primary_label else []

    # Merge additional labels stored in the 'labels' property
    extra_labels = props.pop("labels", None)
    if extra_labels and isinstance(extra_labels, list):
        labels.extend(extra_labels)

    return {
        "id": vertex.get("id"),
        "labels": labels,
        "properties": props,
    }


def _edge_to_rel_dict(edge: Any) -> Dict[str, Any]:
    """
    Convert a parsed AGE edge dict to the standard relationship return format.

    Expected edge dict shape from AGE::

        {"id": <int>, "label": "<type>", "end_id": <int>,
         "start_id": <int>, "properties": {…}}

    The returned dict matches Neo4jStore output::

        {"id": <int>, "type": "<type>", "start_node_id": <int>,
         "end_node_id": <int>, "properties": {…}}

    Args:
        edge: Parsed edge dict.

    Returns:
        Standardised relationship dict.
    """
    if not isinstance(edge, dict):
        return {
            "id": None,
            "type": "",
            "start_node_id": None,
            "end_node_id": None,
            "properties": {},
        }
    return {
        "id": edge.get("id"),
        "type": edge.get("label", ""),
        "start_node_id": edge.get("start_id"),
        "end_node_id": edge.get("end_id"),
        "properties": dict(edge.get("properties", {})),
    }


# ---------------------------------------------------------------------------
# ApacheAgeStore
# ---------------------------------------------------------------------------

class ApacheAgeStore:
    """
    Apache AGE store for property graph storage and Cypher querying.

    Provides the same backend interface as Neo4jStore / FalkorDBStore so it
    can be used transparently via the ``GraphStore`` facade.

    Key capabilities:

    - PostgreSQL + Apache AGE graph operations
    - Node and relationship CRUD
    - Cypher query execution wrapped in ``SELECT * FROM cypher(…)``
    - Transaction support with explicit commit / rollback
    - Multi-label emulation
    - ID separation (AGE internal vs semantic ``semantica_id``)
    """

    def __init__(
        self,
        connection_string: Optional[str] = None,
        graph_name: Optional[str] = None,
        **config,
    ):
        """
        Initialize Apache AGE store.

        Args:
            connection_string: PostgreSQL connection string
                (e.g. ``"host=localhost dbname=agedb user=postgres password=secret"``).
            graph_name: Name of the AGE graph to use.
            **config: Additional configuration options.
        """
        self.logger = get_logger("age_store")
        self.config = config
        self.progress_tracker = get_progress_tracker()
        if not self.progress_tracker.enabled:
            self.progress_tracker.enabled = True

        self.connection_string = connection_string or config.get(
            "connection_string",
            "host=localhost dbname=agedb user=postgres password=postgres",
        )
        self.graph_name = graph_name or config.get("graph_name", "semantica")
        # SECURITY: Sanitize graph_name to prevent SQL injection in cypher() calls.
        # The graph_name is interpolated into SQL: cypher('{graph_name}', $$ ... $$)
        if not re.match(r"^[A-Za-z_][A-Za-z0-9_]*$", self.graph_name):
            raise ValidationError(
                f"Invalid graph_name '{self.graph_name}': must contain only "
                "alphanumeric characters and underscores."
            )

        self._conn = None

        if not PSYCOPG2_AVAILABLE:
            self.logger.warning(
                "psycopg2 not available. Install with: pip install psycopg2-binary"
            )

    # ------------------------------------------------------------------
    # Connection management
    # ------------------------------------------------------------------

    def connect(self, **options) -> bool:
        """
        Connect to PostgreSQL and initialise the AGE extension & graph.

        Performs idempotent setup:
        1. ``CREATE EXTENSION IF NOT EXISTS age``
        2. ``LOAD 'age'``
        3. ``SET search_path = ag_catalog, "$user", public``
        4. ``SELECT create_graph('<graph_name>')`` if not exists.

        Args:
            **options: Additional connection options (currently unused).

        Returns:
            True if connected and initialised successfully.
        """
        if not PSYCOPG2_AVAILABLE:
            raise ProcessingError(
                "psycopg2 is not available. Install with: pip install psycopg2-binary"
            )

        conn_str = options.get("connection_string", self.connection_string)

        try:
            self._conn = psycopg2.connect(conn_str)
            self._conn.autocommit = False

            # Idempotent AGE setup
            with self._conn.cursor() as cur:
                cur.execute("CREATE EXTENSION IF NOT EXISTS age;")
                cur.execute("LOAD 'age';")
                cur.execute(
                    'SET search_path = ag_catalog, "$user", public;'
                )
                # Create graph if not exists
                cur.execute(
                    "SELECT count(*) FROM ag_catalog.ag_graph "
                    "WHERE name = %s;",
                    (self.graph_name,),
                )
                (count,) = cur.fetchone()
                if count == 0:
                    cur.execute(
                        "SELECT create_graph(%s);", (self.graph_name,)
                    )
            self._conn.commit()
            self.logger.info(
                f"Connected to PostgreSQL/AGE, graph '{self.graph_name}'"
            )
            return True

        except Exception as e:
            if self._conn:
                self._conn.rollback()
            raise ProcessingError(f"Failed to connect to AGE: {str(e)}")

    def close(self) -> None:
        """Close the PostgreSQL connection."""
        if self._conn:
            try:
                self._conn.close()
            except Exception:
                pass
            self._conn = None
        self.logger.info("Disconnected from PostgreSQL/AGE")

    def _ensure_connection(self) -> None:
        """Ensure the database connection is available."""
        if self._conn is None or self._conn.closed:
            self.connect()

    # ------------------------------------------------------------------
    # Low-level Cypher execution
    # ------------------------------------------------------------------

    def _execute_cypher(
        self,
        cypher: str,
        cols: str = "result agtype",
    ) -> List[Any]:
        """
        Execute a Cypher query via AGE's ``cypher()`` SQL function.

        Wraps the query in::

            SELECT * FROM cypher('{graph_name}', $$ {cypher} $$)
            AS ({cols});

        Args:
            cypher: OpenCypher query string.
            cols: Column definition for the ``AS`` clause. Defaults to
                ``"result agtype"``.

        Returns:
            List of raw row tuples from the cursor.

        Raises:
            ValidationError: If the query contains ``$$`` which could break
                out of the AGE dollar-quoted string delimiter.
        """
        # SECURITY: Reject queries containing $$ to prevent breakout from
        # AGE's dollar-quoted string delimiter. An attacker who injects $$
        # into the Cypher query can terminate the cypher() argument and
        # append arbitrary SQL.
        if "$$" in cypher:
            raise ValidationError(
                "Query contains forbidden '$$' sequence. "
                "Dollar-quoted delimiters are not allowed in Cypher queries."
            )
        self._ensure_connection()
        sql = (
            f"SELECT * FROM cypher('{self.graph_name}', $$ {cypher} $$) "
            f"AS ({cols});"
        )
        try:
            with self._conn.cursor() as cur:
                cur.execute(sql)
                rows = cur.fetchall()
            self._conn.commit()
            return rows
        except Exception as e:
            self._conn.rollback()
            raise ProcessingError(f"Cypher execution failed: {str(e)}")

    # ------------------------------------------------------------------
    # Node CRUD
    # ------------------------------------------------------------------

    def create_node(
        self,
        labels: List[str],
        properties: Dict[str, Any],
        **options,
    ) -> Dict[str, Any]:
        """
        Create a node in the graph.

        AGE supports a single label per vertex.  ``labels[0]`` is used as the
        primary AGE label; any additional labels are stored in a ``labels``
        property array.

        If ``semantica_id`` is present in *properties* it is preserved as-is;
        otherwise no synthetic semantic ID is generated.

        Args:
            labels: Node labels (first is primary AGE label, rest stored as property).
            properties: Node properties.
            **options: Additional options.

        Returns:
            Created node information: ``{"id": <int>, "labels": [...], "properties": {…}}``.
        """
        tracking_id = self.progress_tracker.start_tracking(
            module="graph_store",
            submodule="ApacheAgeStore",
            message=f"Creating node with labels {labels}",
        )

        try:
            if not labels:
                raise ValidationError("At least one label is required")

            primary_label = _sanitize_label(labels[0])
            props = dict(properties)

            # Store additional labels in property
            if len(labels) > 1:
                props["labels"] = [_sanitize_label(l) for l in labels[1:]]

            cypher = (
                f"CREATE (n:{primary_label} {_props_to_cypher_literal(props)}) "
                f"RETURN n"
            )
            rows = self._execute_cypher(cypher)

            if rows:
                vertex = _parse_agtype(rows[0][0])
                node_data = _vertex_to_node_dict(vertex)
                self.progress_tracker.stop_tracking(
                    tracking_id,
                    status="completed",
                    message=f"Created node with ID {node_data['id']}",
                )
                return node_data

            raise ProcessingError("Failed to create node - no result returned")

        except (ProcessingError, ValidationError):
            self.progress_tracker.stop_tracking(
                tracking_id, status="failed", message="create_node failed"
            )
            raise
        except Exception as e:
            self.progress_tracker.stop_tracking(
                tracking_id, status="failed", message=str(e)
            )
            raise ProcessingError(f"Failed to create node: {str(e)}")

    def create_nodes(
        self,
        nodes: List[Dict[str, Any]],
        **options,
    ) -> List[Dict[str, Any]]:
        """
        Create multiple nodes in batch.

        Args:
            nodes: List of dicts with ``"labels"`` and ``"properties"`` keys.
            **options: Additional options.

        Returns:
            List of created node dicts.
        """
        tracking_id = self.progress_tracker.start_tracking(
            module="graph_store",
            submodule="ApacheAgeStore",
            message=f"Creating {len(nodes)} nodes in batch",
        )

        try:
            created: List[Dict[str, Any]] = []
            for node in nodes:
                node_labels = node.get("labels", ["Node"])
                node_props = node.get("properties", {})
                created.append(self.create_node(node_labels, node_props))

            self.progress_tracker.stop_tracking(
                tracking_id,
                status="completed",
                message=f"Created {len(created)} nodes",
            )
            return created

        except Exception as e:
            self.progress_tracker.stop_tracking(
                tracking_id, status="failed", message=str(e)
            )
            raise ProcessingError(f"Failed to create nodes: {str(e)}")

    def get_node(
        self,
        node_id: int,
        **options,
    ) -> Optional[Dict[str, Any]]:
        """
        Get a node by its AGE internal ID.

        Args:
            node_id: AGE internal vertex ID.
            **options: Additional options.

        Returns:
            Node dict or ``None`` if not found.
        """
        try:
            cypher = (
                f"MATCH (n) WHERE id(n) = {int(node_id)} RETURN n"
            )
            rows = self._execute_cypher(cypher)

            if rows:
                vertex = _parse_agtype(rows[0][0])
                return _vertex_to_node_dict(vertex)
            return None

        except Exception as e:
            raise ProcessingError(f"Failed to get node: {str(e)}")

    def get_nodes(
        self,
        labels: Optional[List[str]] = None,
        properties: Optional[Dict[str, Any]] = None,
        limit: int = 100,
        **options,
    ) -> List[Dict[str, Any]]:
        """
        Get nodes matching criteria.

        Args:
            labels: Filter by labels (matches against primary AGE label).
            properties: Filter by property values.
            limit: Maximum number of nodes to return.
            **options: Additional options.

        Returns:
            List of matching node dicts.
        """
        try:
            if labels:
                primary = _sanitize_label(labels[0])
                match = f"MATCH (n:{primary})"
            else:
                match = "MATCH (n)"

            where_parts: List[str] = []
            if properties:
                for key, value in properties.items():
                    if not re.match(r"^[A-Za-z_][A-Za-z0-9_]*$", key):
                        raise ValidationError(f"Invalid property key: '{key}'")
                    where_parts.append(
                        f"n.{key} = {_value_to_cypher_literal(value)}"
                    )

            where_clause = ""
            if where_parts:
                where_clause = " WHERE " + " AND ".join(where_parts)

            cypher = f"{match}{where_clause} RETURN n LIMIT {int(limit)}"
            rows = self._execute_cypher(cypher)

            nodes: List[Dict[str, Any]] = []
            for row in rows:
                vertex = _parse_agtype(row[0])
                nodes.append(_vertex_to_node_dict(vertex))
            return nodes

        except (ProcessingError, ValidationError):
            raise
        except Exception as e:
            raise ProcessingError(f"Failed to get nodes: {str(e)}")

    def update_node(
        self,
        node_id: int,
        properties: Dict[str, Any],
        merge: bool = True,
        **options,
    ) -> Dict[str, Any]:
        """
        Update a node's properties.

        Args:
            node_id: AGE internal vertex ID.
            properties: Properties to set.
            merge: If ``True``, merge (``+=``); if ``False``, replace (``=``).
            **options: Additional options.

        Returns:
            Updated node dict.
        """
        try:
            props_lit = _props_to_cypher_literal(properties)
            op = "+=" if merge else "="
            cypher = (
                f"MATCH (n) WHERE id(n) = {int(node_id)} "
                f"SET n {op} {props_lit} "
                f"RETURN n"
            )
            rows = self._execute_cypher(cypher)

            if rows:
                vertex = _parse_agtype(rows[0][0])
                return _vertex_to_node_dict(vertex)

            raise ProcessingError(f"Node with ID {node_id} not found")

        except ProcessingError:
            raise
        except Exception as e:
            raise ProcessingError(f"Failed to update node: {str(e)}")

    def delete_node(
        self,
        node_id: int,
        detach: bool = True,
        **options,
    ) -> bool:
        """
        Delete a node by its AGE internal ID.

        Args:
            node_id: AGE internal vertex ID.
            detach: If ``True``, delete connected relationships as well.
            **options: Additional options.

        Returns:
            ``True`` if deleted successfully.
        """
        try:
            delete_kw = "DETACH DELETE" if detach else "DELETE"
            cypher = (
                f"MATCH (n) WHERE id(n) = {int(node_id)} "
                f"{delete_kw} n"
            )
            self._execute_cypher(cypher, cols="v agtype")
            return True

        except Exception as e:
            raise ProcessingError(f"Failed to delete node: {str(e)}")

    # ------------------------------------------------------------------
    # Relationship CRUD
    # ------------------------------------------------------------------

    def create_relationship(
        self,
        start_node_id: int,
        end_node_id: int,
        rel_type: str,
        properties: Optional[Dict[str, Any]] = None,
        **options,
    ) -> Dict[str, Any]:
        """
        Create a relationship between two nodes.

        Args:
            start_node_id: Start vertex AGE internal ID.
            end_node_id: End vertex AGE internal ID.
            rel_type: Relationship type.
            properties: Relationship properties.
            **options: Additional options.

        Returns:
            Created relationship dict.
        """
        tracking_id = self.progress_tracker.start_tracking(
            module="graph_store",
            submodule="ApacheAgeStore",
            message=f"Creating relationship [{rel_type}]",
        )

        try:
            safe_type = _sanitize_rel_type(rel_type)
            props = properties or {}
            props_lit = _props_to_cypher_literal(props)

            cypher = (
                f"MATCH (a), (b) "
                f"WHERE id(a) = {int(start_node_id)} AND id(b) = {int(end_node_id)} "
                f"CREATE (a)-[r:{safe_type} {props_lit}]->(b) "
                f"RETURN r"
            )
            rows = self._execute_cypher(cypher)

            if rows:
                edge = _parse_agtype(rows[0][0])
                rel_data = _edge_to_rel_dict(edge)
                self.progress_tracker.stop_tracking(
                    tracking_id,
                    status="completed",
                    message=f"Created relationship with ID {rel_data['id']}",
                )
                return rel_data

            raise ProcessingError(
                "Failed to create relationship - nodes not found"
            )

        except (ProcessingError, ValidationError):
            self.progress_tracker.stop_tracking(
                tracking_id, status="failed", message="create_relationship failed"
            )
            raise
        except Exception as e:
            self.progress_tracker.stop_tracking(
                tracking_id, status="failed", message=str(e)
            )
            raise ProcessingError(f"Failed to create relationship: {str(e)}")

    def get_relationships(
        self,
        node_id: Optional[int] = None,
        rel_type: Optional[str] = None,
        direction: str = "both",
        limit: int = 100,
        **options,
    ) -> List[Dict[str, Any]]:
        """
        Get relationships matching criteria.

        Args:
            node_id: Filter by vertex AGE internal ID.
            rel_type: Filter by relationship type.
            direction: ``"in"``, ``"out"``, or ``"both"``.
            limit: Maximum number of results.
            **options: Additional options.

        Returns:
            List of relationship dicts.
        """
        try:
            type_filter = f":{_sanitize_rel_type(rel_type)}" if rel_type else ""

            if node_id is not None:
                nid = int(node_id)
                if direction == "out":
                    cypher = (
                        f"MATCH (a)-[r{type_filter}]->(b) "
                        f"WHERE id(a) = {nid} "
                        f"RETURN r LIMIT {int(limit)}"
                    )
                elif direction == "in":
                    cypher = (
                        f"MATCH (a)<-[r{type_filter}]-(b) "
                        f"WHERE id(a) = {nid} "
                        f"RETURN r LIMIT {int(limit)}"
                    )
                else:
                    cypher = (
                        f"MATCH (a)-[r{type_filter}]-(b) "
                        f"WHERE id(a) = {nid} "
                        f"RETURN r LIMIT {int(limit)}"
                    )
            else:
                cypher = (
                    f"MATCH (a)-[r{type_filter}]->(b) "
                    f"RETURN r LIMIT {int(limit)}"
                )

            rows = self._execute_cypher(cypher)

            relationships: List[Dict[str, Any]] = []
            for row in rows:
                edge = _parse_agtype(row[0])
                relationships.append(_edge_to_rel_dict(edge))
            return relationships

        except (ProcessingError, ValidationError):
            raise
        except Exception as e:
            raise ProcessingError(f"Failed to get relationships: {str(e)}")

    def delete_relationship(
        self,
        rel_id: int,
        **options,
    ) -> bool:
        """
        Delete a relationship by its AGE internal ID.

        Args:
            rel_id: Relationship AGE internal ID.
            **options: Additional options.

        Returns:
            ``True`` if deleted successfully.
        """
        try:
            cypher = (
                f"MATCH ()-[r]->() WHERE id(r) = {int(rel_id)} DELETE r"
            )
            self._execute_cypher(cypher, cols="v agtype")
            return True

        except Exception as e:
            raise ProcessingError(f"Failed to delete relationship: {str(e)}")

    # ------------------------------------------------------------------
    # Query execution
    # ------------------------------------------------------------------

    def execute_query(
        self,
        query: str,
        parameters: Optional[Dict[str, Any]] = None,
        **options,
    ) -> Dict[str, Any]:
        """
        Execute an arbitrary Cypher query.

        If ``parameters`` are provided they are substituted into the query
        string using safe Cypher literal escaping (AGE does not support
        ``$param`` style binding inside ``cypher()`` calls).

        Args:
            query: OpenCypher query string.
            parameters: Optional parameter mapping.
            **options: Additional options. Use ``cols`` to override the
                default ``AS`` clause columns.

        Returns:
            Query result dict matching Neo4jStore format::

                {
                    "success": True,
                    "records": [<row dicts>],
                    "keys": [<column names>],
                    "metadata": {"query": <str>},
                }
        """
        tracking_id = self.progress_tracker.start_tracking(
            module="graph_store",
            submodule="ApacheAgeStore",
            message="Executing Cypher query",
        )

        try:
            final_query = query
            if parameters:
                for param_key, param_value in parameters.items():
                    placeholder = f"${param_key}"
                    literal = _value_to_cypher_literal(param_value)
                    final_query = final_query.replace(placeholder, literal)

            # Determine column spec
            cols = options.get("cols", None)
            if cols is None:
                # Attempt to infer columns from RETURN clause
                cols = self._infer_return_cols(final_query)

            self._ensure_connection()
            sql = (
                f"SELECT * FROM cypher('{self.graph_name}', $$ {final_query} $$) "
                f"AS ({cols});"
            )

            with self._conn.cursor() as cur:
                cur.execute(sql)
                if cur.description:
                    keys = [desc[0] for desc in cur.description]
                else:
                    keys = []
                raw_rows = cur.fetchall()
            self._conn.commit()

            records = []
            for raw_row in raw_rows:
                row: Dict[str, Any] = {}
                for i, key in enumerate(keys):
                    parsed = _parse_agtype(raw_row[i])
                    # Convert vertex / edge dicts to standard shape
                    if isinstance(parsed, dict):
                        if "label" in parsed and "properties" in parsed:
                            if "start_id" in parsed:
                                parsed = _edge_to_rel_dict(parsed)
                            else:
                                parsed = _vertex_to_node_dict(parsed)
                    row[key] = parsed
                records.append(row)

            self.progress_tracker.stop_tracking(
                tracking_id,
                status="completed",
                message=f"Query returned {len(records)} records",
            )

            return {
                "success": True,
                "records": records,
                "keys": keys,
                "metadata": {"query": query},
            }

        except ProcessingError:
            self.progress_tracker.stop_tracking(
                tracking_id, status="failed", message="query failed"
            )
            raise
        except Exception as e:
            if self._conn and not self._conn.closed:
                self._conn.rollback()
            self.progress_tracker.stop_tracking(
                tracking_id, status="failed", message=str(e)
            )
            raise ProcessingError(f"Query execution failed: {str(e)}")

    @staticmethod
    def _infer_return_cols(cypher: str) -> str:
        """
        Attempt to infer the ``AS (...)`` column definitions from the
        ``RETURN`` clause of a Cypher query.

        Falls back to ``"result agtype"`` if inference is not possible.

        Args:
            cypher: Cypher query string.

        Returns:
            Column definition string for the SQL ``AS`` clause.
        """
        match = re.search(r"\bRETURN\b\s+(.+?)(?:\s+ORDER\s+|\s+LIMIT\s+|\s+SKIP\s+|$)",
                          cypher, re.IGNORECASE | re.DOTALL)
        if not match:
            return "result agtype"

        return_body = match.group(1).strip()
        # Split on commas not inside parentheses
        depth = 0
        parts: List[str] = []
        current: List[str] = []
        for ch in return_body:
            if ch == "(":
                depth += 1
            elif ch == ")":
                depth -= 1
            elif ch == "," and depth == 0:
                parts.append("".join(current).strip())
                current = []
                continue
            current.append(ch)
        if current:
            parts.append("".join(current).strip())

        col_defs: List[str] = []
        for part in parts:
            # Check for alias via AS
            alias_match = re.search(r"\bAS\s+(\w+)\s*$", part, re.IGNORECASE)
            if alias_match:
                col_defs.append(f"{alias_match.group(1)} agtype")
            else:
                # Use sanitised expression name
                clean = re.sub(r"[^A-Za-z0-9_]", "_", part.strip())
                clean = re.sub(r"_+", "_", clean).strip("_") or "col"
                col_defs.append(f"{clean} agtype")

        return ", ".join(col_defs) if col_defs else "result agtype"

    # ------------------------------------------------------------------
    # Graph traversal / analytics
    # ------------------------------------------------------------------

    def get_neighbors(
        self,
        node_id: int,
        rel_type: Optional[str] = None,
        direction: str = "both",
        depth: int = 1,
        **options,
    ) -> List[Dict[str, Any]]:
        """
        Get neighboring nodes.

        Args:
            node_id: Starting vertex AGE internal ID.
            rel_type: Filter by relationship type.
            direction: ``"in"``, ``"out"``, or ``"both"``.
            depth: Traversal depth.
            **options: Additional options.

        Returns:
            List of neighbouring node dicts.
        """
        try:
            type_filter = f":{_sanitize_rel_type(rel_type)}" if rel_type else ""

            if direction == "out":
                pattern = f"-[r{type_filter}*1..{int(depth)}]->"
            elif direction == "in":
                pattern = f"<-[r{type_filter}*1..{int(depth)}]-"
            else:
                pattern = f"-[r{type_filter}*1..{int(depth)}]-"

            cypher = (
                f"MATCH (start){pattern}(neighbor) "
                f"WHERE id(start) = {int(node_id)} "
                f"RETURN DISTINCT neighbor"
            )

            rows = self._execute_cypher(cypher, cols="neighbor agtype")

            neighbors: List[Dict[str, Any]] = []
            for row in rows:
                vertex = _parse_agtype(row[0])
                neighbors.append(_vertex_to_node_dict(vertex))
            return neighbors

        except Exception as e:
            raise ProcessingError(f"Failed to get neighbors: {str(e)}")

    def shortest_path(
        self,
        start_node_id: int,
        end_node_id: int,
        rel_type: Optional[str] = None,
        max_depth: int = 10,
        **options,
    ) -> Optional[Dict[str, Any]]:
        """
        Find the shortest path between two nodes.

        Args:
            start_node_id: Start vertex AGE internal ID.
            end_node_id: End vertex AGE internal ID.
            rel_type: Filter by relationship type.
            max_depth: Maximum path length.
            **options: Additional options.

        Returns:
            Path dict with ``length``, ``nodes``, ``relationships``
            or ``None`` if no path found.
        """
        try:
            type_filter = f":{_sanitize_rel_type(rel_type)}" if rel_type else ""

            cypher = (
                f"MATCH path = shortestPath("
                f"(s)-[r{type_filter}*..{int(max_depth)}]-(e)) "
                f"WHERE id(s) = {int(start_node_id)} AND id(e) = {int(end_node_id)} "
                f"RETURN path"
            )

            rows = self._execute_cypher(cypher, cols="path agtype")

            if not rows:
                return None

            path_data = _parse_agtype(rows[0][0])

            # AGE returns a path as a list [vertex, edge, vertex, edge, …]
            nodes: List[Dict[str, Any]] = []
            relationships: List[Dict[str, Any]] = []

            if isinstance(path_data, list):
                for i, element in enumerate(path_data):
                    if not isinstance(element, dict):
                        continue
                    if "start_id" in element:
                        relationships.append(_edge_to_rel_dict(element))
                    elif "label" in element and "properties" in element:
                        nodes.append(_vertex_to_node_dict(element))
            elif isinstance(path_data, dict):
                # Single hop — may be returned as dict with vertices/edges
                for v in path_data.get("vertices", []):
                    nodes.append(_vertex_to_node_dict(v))
                for e in path_data.get("edges", []):
                    relationships.append(_edge_to_rel_dict(e))

            return {
                "length": len(relationships),
                "nodes": nodes,
                "relationships": relationships,
            }

        except Exception as e:
            raise ProcessingError(f"Failed to find shortest path: {str(e)}")

    # ------------------------------------------------------------------
    # Index and stats
    # ------------------------------------------------------------------

    def create_index(
        self,
        label: str,
        property_name: str,
        index_type: str = "btree",
        **options,
    ) -> bool:
        """
        Create a PostgreSQL index on a vertex property.

        Since AGE stores vertex properties in a JSONB column, this creates
        a PostgreSQL index on the underlying table using a JSONB expression.

        Args:
            label: Vertex label (used for table name resolution).
            property_name: Property to index.
            index_type: Index type (``"btree"``, ``"gin"``, ``"hash"``).
            **options: Additional options (e.g. ``index_name``).

        Returns:
            ``True`` if the index was created successfully.
        """
        try:
            self._ensure_connection()
            safe_label = _sanitize_label(label)
            if not re.match(r"^[A-Za-z_][A-Za-z0-9_]*$", property_name):
                raise ValidationError(f"Invalid property name: '{property_name}'")

            index_name = options.get(
                "index_name", f"idx_{self.graph_name}_{safe_label}_{property_name}"
            )
            # Sanitise index name
            index_name = re.sub(r"[^A-Za-z0-9_]", "_", index_name)

            # AGE stores vertex data in schema-qualified tables
            table_name = f'"{self.graph_name}"."{safe_label}"'

            sql = (
                f"CREATE INDEX IF NOT EXISTS {index_name} ON {table_name} "
                f"USING {index_type} ((properties->>'{property_name}'));"
            )

            with self._conn.cursor() as cur:
                cur.execute(sql)
            self._conn.commit()
            self.logger.info(
                f"Created index {index_name} on {safe_label}.{property_name}"
            )
            return True

        except (ProcessingError, ValidationError):
            raise
        except Exception as e:
            if self._conn and not self._conn.closed:
                self._conn.rollback()
            raise ProcessingError(f"Failed to create index: {str(e)}")

    def get_stats(self) -> Dict[str, Any]:
        """
        Get graph statistics.

        Returns:
            Dict with ``node_count``, ``relationship_count``,
            ``label_counts``, and ``relationship_type_counts``.
        """
        try:
            stats: Dict[str, Any] = {}

            # Node count
            rows = self._execute_cypher(
                "MATCH (n) RETURN count(n)",
                cols="count agtype",
            )
            stats["node_count"] = _parse_agtype(rows[0][0]) if rows else 0

            # Relationship count
            rows = self._execute_cypher(
                "MATCH ()-[r]->() RETURN count(r)",
                cols="count agtype",
            )
            stats["relationship_count"] = _parse_agtype(rows[0][0]) if rows else 0

            # Label counts — query the AGE catalog
            stats["label_counts"] = {}
            try:
                self._ensure_connection()
                with self._conn.cursor() as cur:
                    cur.execute(
                        "SELECT name FROM ag_catalog.ag_label "
                        "WHERE graph = (SELECT graphid FROM ag_catalog.ag_graph WHERE name = %s) "
                        "AND kind = 'v' AND name != '_ag_label_vertex';",
                        (self.graph_name,),
                    )
                    label_rows = cur.fetchall()
                self._conn.commit()

                for (lbl_name,) in label_rows:
                    try:
                        cnt_rows = self._execute_cypher(
                            f"MATCH (n:{lbl_name}) RETURN count(n)",
                            cols="count agtype",
                        )
                        stats["label_counts"][lbl_name] = (
                            _parse_agtype(cnt_rows[0][0]) if cnt_rows else 0
                        )
                    except Exception:
                        stats["label_counts"][lbl_name] = 0
            except Exception:
                pass

            # Relationship type counts
            stats["relationship_type_counts"] = {}
            try:
                self._ensure_connection()
                with self._conn.cursor() as cur:
                    cur.execute(
                        "SELECT name FROM ag_catalog.ag_label "
                        "WHERE graph = (SELECT graphid FROM ag_catalog.ag_graph WHERE name = %s) "
                        "AND kind = 'e' AND name != '_ag_label_edge';",
                        (self.graph_name,),
                    )
                    edge_label_rows = cur.fetchall()
                self._conn.commit()

                for (etype,) in edge_label_rows:
                    try:
                        cnt_rows = self._execute_cypher(
                            f"MATCH ()-[r:{etype}]->() RETURN count(r)",
                            cols="count agtype",
                        )
                        stats["relationship_type_counts"][etype] = (
                            _parse_agtype(cnt_rows[0][0]) if cnt_rows else 0
                        )
                    except Exception:
                        stats["relationship_type_counts"][etype] = 0
            except Exception:
                pass

            return stats

        except Exception as e:
            self.logger.warning(f"Failed to get stats: {str(e)}")
            return {"status": "error", "message": str(e)}
