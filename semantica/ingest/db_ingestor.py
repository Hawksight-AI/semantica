"""
Database Ingestion Module

This module provides comprehensive database ingestion capabilities for the
Semantica framework, enabling data extraction from various database systems.

Key Features:
    - Multiple database support (PostgreSQL, MySQL, SQLite, Oracle, SQL Server)
    - Database connection management with connection pooling
    - SQL query execution and result processing
    - Data export and transformation
    - Schema analysis and introspection
    - Data type handling and conversion
    - Large dataset processing with pagination

Main Classes:
    - DBIngestor: Main database ingestion class
    - DatabaseConnector: Database connection handler
    - DataExporter: Data export processor

Example Usage:
    >>> from semantica.ingest import DBIngestor
    >>> ingestor = DBIngestor()
    >>> data = ingestor.ingest_database("postgresql://user:pass@localhost/db")
    >>> table_data = ingestor.export_table("postgresql://...", "users", limit=100)

Author: Semantica Contributors
License: MIT
"""

import json
import re
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Dict, List, Optional
from urllib.parse import urlparse

from ..utils.exceptions import ProcessingError, ValidationError
from ..utils.logging import get_logger
from ..utils.progress_tracker import get_progress_tracker

_IDENTIFIER_RE = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")

# Fragments that turn a filter/order clause into a second statement, a
# data-exfiltration UNION, a time-based blind-injection oracle, or schema
# enumeration, rather than a boolean/ordering expression.
_SQL_FRAGMENT_BLOCKLIST_RE = re.compile(
    r";|--|/\*|\*/|\bunion\b|\binsert\b|\bupdate\b|\bdelete\b|\bdrop\b|"
    r"\balter\b|\bcreate\b|\bexec\b|\bexecute\b|\bgrant\b|\brevoke\b|"
    r"\battach\b|\bpragma\b|\bxp_\w+|\bsp_\w+|\binto\s+outfile\b|\bload_file\b|"
    r"\bsleep\s*\(|\bbenchmark\s*\(|\bpg_sleep\s*\(|\bwaitfor\b|"
    r"\bdbms_\w+|\butl_\w+|\binformation_schema\b|\bpg_catalog\b",
    re.IGNORECASE,
)

# SQL single-quoted string literals (''  is the standard escaped-quote) and
# double-quoted identifiers (""  likewise) — matched only when properly
# closed, so a malformed/unterminated quote sequence is left alone and
# still hits the blocklist above rather than being treated as "inside a
# literal" and skipped.
_SQL_STRING_LITERAL_RE = re.compile(r"'(?:[^']|'')*'")
_SQL_QUOTED_IDENTIFIER_RE = re.compile(r'"(?:[^"]|"")*"')


def _mask_sql_literals(fragment: str) -> str:
    """Blank the contents of quoted literals so they can't trip the blocklist.

    A legitimate value or quoted identifier that happens to contain a
    blocked word or character as *data* — e.g. ``status = 'union'`` or
    ``"my--column" = 1`` — is not SQL syntax and shouldn't be rejected as
    if it were. Only the quoted span's interior is replaced (with `?`,
    keeping the surrounding quotes and the fragment's length/positions
    intact for the error message); text outside any properly closed quote
    is passed through unchanged and still fully scrutinized.
    """
    fragment = _SQL_STRING_LITERAL_RE.sub(
        lambda m: "'" + "?" * (len(m.group(0)) - 2) + "'", fragment
    )
    fragment = _SQL_QUOTED_IDENTIFIER_RE.sub(
        lambda m: '"' + "?" * (len(m.group(0)) - 2) + '"', fragment
    )
    return fragment


def _validate_sql_identifier(name: str, kind: str) -> str:
    """Validate a table/schema name used as a raw SQL identifier.

    ``export_table_data`` interpolates *name* directly into the query text
    (SQLAlchemy has no bind-parameter syntax for identifiers), so anything
    outside a plain alphanumeric/underscore identifier is a potential
    breakout of the surrounding ``"..."`` quoting.
    """
    if not isinstance(name, str) or not _IDENTIFIER_RE.match(name):
        raise ValidationError(
            f"Invalid {kind}: {name!r}. Must start with a letter or "
            "underscore and contain only alphanumeric characters and "
            "underscores."
        )
    return name


def _validate_sql_fragment(fragment: str, kind: str) -> str:
    """Reject WHERE/ORDER BY fragments that smuggle a second statement.

    These clauses can't be bound as query parameters (they're arbitrary
    boolean/ordering expressions, not values), so this blocks the concrete
    injection primitives (statement separators, comments, UNION, DML/DDL
    keywords, time-based blind oracles, schema enumeration) rather than
    parameterizing.

    This is a blocklist, not a grammar: it cannot exhaustively prove
    *fragment* is safe, only reject known-dangerous constructs, so a
    boolean-blind subquery expressed with none of the blocked keywords
    (e.g. ``id = (SELECT 1 FROM t WHERE ...)``) still passes. ``where``/
    ``order_by`` are a raw-SQL-fragment API by design (see
    ``export_table_data``'s docstring); treat them as trusted/operator
    input, not something to expose directly to untrusted end users.
    """
    if not isinstance(fragment, str):
        raise ValidationError(f"Invalid {kind}: must be a string")
    # Check the blocklist against literal-masked text so a blocked word
    # appearing only as quoted data (not as SQL syntax) doesn't false-
    # positive; the original, unmodified fragment is still what's returned
    # and used in the query.
    if _SQL_FRAGMENT_BLOCKLIST_RE.search(_mask_sql_literals(fragment)):
        raise ValidationError(
            f"Invalid {kind}: {fragment!r} contains disallowed SQL "
            "keywords or statement-boundary characters"
        )
    return fragment


@dataclass
class TableData:
    """Table data representation."""

    table_name: str
    columns: List[Dict[str, Any]]
    rows: List[Dict[str, Any]]
    row_count: int
    schema: Optional[str] = None
    metadata: Dict[str, Any] = field(default_factory=dict)


class DatabaseConnector:
    """
    Database connection management.

    This class manages connections to various database systems, handles
    connection pooling and reuse, and provides a unified interface for
    different database types.

    Supported Databases:
        - PostgreSQL (postgresql, postgres)
        - MySQL/MariaDB (mysql, mariadb)
        - SQLite (sqlite)
        - Oracle (oracle)
        - SQL Server (mssql, sqlserver)

    Example Usage:
        >>> connector = DatabaseConnector("postgresql")
        >>> engine = connector.connect("postgresql://user:pass@localhost/db")
        >>> connector.disconnect()
    """

    SUPPORTED_DATABASES = {
        "postgresql": "postgresql",
        "postgres": "postgresql",
        "mysql": "mysql+pymysql",
        "mariadb": "mysql+pymysql",
        "sqlite": "sqlite",
        "oracle": "oracle",
        "mssql": "mssql+pyodbc",
        "sqlserver": "mssql+pyodbc",
    }

    def __init__(self, db_type: str = "", **config):
        """
        Initialize database connector.

        Sets up the connector with database type and configuration. Database
        type can be auto-detected from connection string if not provided.

        Args:
            db_type: Database type (postgresql, mysql, sqlite, etc.) (optional)
            **config: Connection configuration options
        """
        self.logger = get_logger("database_connector")
        self.db_type = db_type.lower() if db_type else ""
        self.config = config
        self.engine: Optional[Any] = None

        self.logger.debug(
            f"Database connector initialized: db_type={db_type or 'auto-detect'}"
        )

    def connect(self, connection_string: str) -> Any:
        """
        Establish database connection.

        This method creates a SQLAlchemy engine for the database connection
        string, auto-detects database type if not specified, and tests the
        connection to ensure it's working.

        Args:
            connection_string: Database connection string (SQLAlchemy format)
                              Examples:
                              - "postgresql://user:pass@localhost/db"
                              - "mysql+pymysql://user:pass@localhost/db"
                              - "sqlite:///path/to/db.sqlite"

        Returns:
            Engine: SQLAlchemy engine object for database operations

        Raises:
            ProcessingError: If connection fails or database type is unsupported
        """
        try:
            try:
                from sqlalchemy import create_engine, text
            except ImportError:
                raise ProcessingError(
                    "sqlalchemy is required for database ingestion. "
                    "Install with: pip install sqlalchemy"
                )

            # Parse connection string to detect database type
            parsed = urlparse(connection_string)

            # Determine database type from connection string if not provided
            if parsed.scheme:
                db_type = parsed.scheme.split("+")[
                    0
                ]  # Remove driver prefix (e.g., mysql+pymysql -> mysql)
                if db_type in self.SUPPORTED_DATABASES:
                    self.db_type = db_type
                    self.logger.debug(f"Auto-detected database type: {db_type}")

            # Validate database type
            if self.db_type and self.db_type not in self.SUPPORTED_DATABASES:
                raise ValidationError(
                    f"Unsupported database type: {self.db_type}. "
                    f"Supported types: {list(self.SUPPORTED_DATABASES.keys())}"
                )

            # Create SQLAlchemy engine
            self.engine = create_engine(connection_string, echo=False)

            # Test connection with a simple query
            with self.engine.connect() as conn:
                conn.execute(text("SELECT 1"))

            self.logger.info(f"Connected to {self.db_type or 'database'}")
            return self.engine

        except Exception as e:
            self.logger.error(f"Failed to connect to database: {e}")
            raise ProcessingError(f"Failed to connect to database: {e}") from e

    def disconnect(self):
        """
        Close database connection.

        This method disposes of the SQLAlchemy engine and closes all connections
        in the connection pool. Should be called when done with database operations.
        """
        if self.engine:
            self.engine.dispose()
            self.engine = None
            self.logger.info("Disconnected from database")

    def test_connection(self, connection_string: str) -> bool:
        """
        Test database connection without creating a persistent connection.

        This method creates a temporary connection, tests it with a simple query,
        and immediately closes it. Useful for connection validation.

        Args:
            connection_string: Database connection string to test

        Returns:
            bool: True if connection successful, False otherwise
        """
        try:
            from sqlalchemy import create_engine, text
            engine = create_engine(connection_string)
            with engine.connect() as conn:
                conn.execute(text("SELECT 1"))
            engine.dispose()
            return True
        except Exception as e:
            self.logger.debug(f"Connection test failed: {e}")
            return False


class DataExporter:
    """
    Database data export and transformation.

    This class exports data from database tables, transforms data to standard
    formats, handles different data types, and manages large dataset exports
    with pagination support.

    Example Usage:
        >>> exporter = DataExporter()
        >>> table_data = exporter.export_table_data(engine, "users", limit=100)
        >>> schema = exporter.export_schema(engine)
    """

    def __init__(self, **config):
        """
        Initialize data exporter.

        Sets up the exporter with configuration options.

        Args:
            **config: Exporter configuration options (currently unused)
        """
        self.logger = get_logger("data_exporter")
        self.config = config

    def export_table_data(
        self,
        connection: Any,
        table_name: str,
        schema: Optional[str] = None,
        limit: Optional[int] = None,
        offset: Optional[int] = None,
        where: Optional[str] = None,
        order_by: Optional[str] = None,
        **options,
    ) -> TableData:
        """
        Export data from database table.

        This method exports data from a database table with optional filtering,
        pagination, and ordering. Converts database types to JSON-serializable
        formats (e.g., datetime to ISO format strings).

        Args:
            connection: SQLAlchemy database connection engine
            table_name: Name of the table to export
            schema: Schema name (for databases with schema support, optional)
            limit: Maximum number of rows to export (optional)
            offset: Row offset for pagination (optional)
            where: WHERE clause for filtering (optional, e.g., "age > 18").
                Raw SQL, checked against a keyword/character blocklist (see
                ``_validate_sql_fragment``) but not fully sanitized — treat
                as trusted/operator input, never pass untrusted end-user
                text here directly.
            order_by: ORDER BY clause for sorting (optional, e.g., "name ASC").
                Same trust requirement as ``where``.
            **options: Additional export options (unused)

        Returns:
            TableData: Exported table data object containing:
                - table_name: Table name
                - columns: List of column information dictionaries
                - rows: List of row dictionaries
                - row_count: Total number of rows (or exported count if limit applied)
                - schema: Schema name (if provided)

        Raises:
            ProcessingError: If table export fails
        """
        try:
            from sqlalchemy import inspect, text

            _validate_sql_identifier(table_name, "table_name")
            if schema:
                _validate_sql_identifier(schema, "schema")
            if where:
                _validate_sql_fragment(where, "where")
            if order_by:
                _validate_sql_fragment(order_by, "order_by")

            inspector = inspect(connection)

            # Get column information
            columns = inspector.get_columns(table_name, schema=schema)
            column_info = [
                {
                    "name": col["name"],
                    "type": str(col["type"]),
                    "nullable": col.get("nullable", True),
                    "default": str(col.get("default")) if col.get("default") else None,
                }
                for col in columns
            ]

            self.logger.debug(
                f"Exporting table {table_name}: {len(column_info)} column(s), "
                f"schema={schema}, limit={limit}"
            )

            # Build SQL query with optional clauses
            table_ref = f'{f"{schema}." if schema else ""}"{table_name}"'
            query = f"SELECT * FROM {table_ref}"

            if where:
                query += f" WHERE {where}"

            if order_by:
                query += f" ORDER BY {order_by}"

            if limit:
                query += f" LIMIT {limit}"

            if offset:
                query += f" OFFSET {offset}"

            # Execute query and process results
            with connection.connect() as conn:
                result = conn.execute(text(query))
                rows = []
                for row in result:
                    row_dict = {}
                    for col_name, value in row._mapping.items():
                        # Convert datetime and other types to JSON-serializable format
                        if isinstance(value, datetime):
                            row_dict[col_name] = value.isoformat()
                        elif hasattr(value, "__dict__"):
                            # Complex types - convert to string
                            row_dict[col_name] = str(value)
                        else:
                            row_dict[col_name] = value
                    rows.append(row_dict)

                # Get total row count if limit not applied
                row_count = len(rows)
                if not limit:
                    count_query = f"SELECT COUNT(*) FROM {table_ref}"
                    if where:
                        count_query += f" WHERE {where}"
                    count_result = conn.execute(text(count_query))
                    row_count = count_result.scalar()

            self.logger.debug(
                f"Exported {len(rows)} row(s) from table {table_name} "
                f"(total: {row_count})"
            )

            return TableData(
                table_name=table_name,
                columns=column_info,
                rows=rows,
                row_count=row_count,
                schema=schema,
            )

        except ValidationError:
            raise
        except Exception as e:
            self.logger.error(f"Failed to export table {table_name}: {e}")
            raise ProcessingError(f"Failed to export table: {e}") from e

    def transform_data(
        self, raw_data: List[Dict[str, Any]], schema_info: Dict[str, Any]
    ) -> List[Dict[str, Any]]:
        """
        Transform raw database data.

        This method applies transformations to raw database rows, including
        string cleaning and normalization. Can be extended with custom
        transformation logic.

        Args:
            raw_data: List of raw database row dictionaries
            schema_info: Schema information dictionary (currently unused,
                        reserved for schema-aware transformations)

        Returns:
            list: List of transformed row dictionaries
        """
        transformed = []

        for row in raw_data:
            transformed_row = {}
            for col_name, value in row.items():
                # Apply transformations
                if value is None:
                    transformed_row[col_name] = None
                elif isinstance(value, str):
                    # Clean and normalize strings (strip whitespace)
                    transformed_row[col_name] = value.strip()
                else:
                    transformed_row[col_name] = value

            transformed.append(transformed_row)

        return transformed

    def export_schema(
        self, connection: Any, schema: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        Export database schema information.

        This method introspects the database schema and exports comprehensive
        information about tables, columns, primary keys, indexes, foreign keys,
        and views.

        Args:
            connection: SQLAlchemy database connection engine
            schema: Schema name (for databases with schema support, optional)

        Returns:
            dict: Schema information dictionary containing:
                - tables: List of table information dictionaries with:
                    - name: Table name
                    - columns: List of column information
                    - primary_keys: List of primary key column names
                    - indexes: List of index names
                - views: List of view names
                - foreign_keys: List of foreign key constraint dictionaries

        Raises:
            ProcessingError: If schema export fails
        """
        try:
            from sqlalchemy import inspect
            inspector = inspect(connection)

            schema_info = {"tables": [], "views": [], "foreign_keys": []}

            # Get all tables in schema
            tables = inspector.get_table_names(schema=schema)
            self.logger.debug(
                f"Found {len(tables)} table(s) in schema: {schema or 'default'}"
            )

            for table_name in tables:
                table_info = {
                    "name": table_name,
                    "columns": [],
                    "primary_keys": [],
                    "indexes": [],
                }

                # Get column information
                columns = inspector.get_columns(table_name, schema=schema)
                for col in columns:
                    table_info["columns"].append(
                        {
                            "name": col["name"],
                            "type": str(col["type"]),
                            "nullable": col.get("nullable", True),
                            "primary_key": col.get("primary_key", False),
                        }
                    )

                # Get primary key constraints
                try:
                    pk = inspector.get_pk_constraint(table_name, schema=schema)
                    if pk:
                        table_info["primary_keys"] = pk.get("constrained_columns", [])
                except Exception:
                    pass

                # Get indexes
                try:
                    indexes = inspector.get_indexes(table_name, schema=schema)
                    table_info["indexes"] = [idx["name"] for idx in indexes]
                except Exception:
                    pass

                schema_info["tables"].append(table_info)

            # Get views (if supported)
            try:
                views = inspector.get_view_names(schema=schema)
                schema_info["views"] = views
                self.logger.debug(f"Found {len(views)} view(s) in schema")
            except Exception:
                # Views may not be supported by all databases
                pass

            # Get foreign key constraints
            for table_name in tables:
                try:
                    foreign_keys = inspector.get_foreign_keys(table_name, schema=schema)
                    schema_info["foreign_keys"].extend(foreign_keys)
                except Exception:
                    pass

            self.logger.debug(
                f"Exported schema: {len(schema_info['tables'])} table(s), "
                f"{len(schema_info['views'])} view(s), "
                f"{len(schema_info['foreign_keys'])} foreign key(s)"
            )

            return schema_info

        except Exception as e:
            self.logger.error(f"Failed to export schema: {e}")
            raise ProcessingError(f"Failed to export schema: {e}") from e


class DBIngestor:
    """
    Database ingestion handler.

    This class provides comprehensive database ingestion capabilities, connecting
    to various database systems, executing SQL queries, exporting data, and
    analyzing database schemas.

    Features:
        - Multiple database support (PostgreSQL, MySQL, SQLite, Oracle, SQL Server)
        - Database connection management
        - SQL query execution
        - Table and schema export
        - Data transformation
        - Large dataset handling with pagination

    Example Usage:
        >>> ingestor = DBIngestor()
        >>> data = ingestor.ingest_database("postgresql://user:pass@localhost/db")
        >>> table_data = ingestor.export_table("postgresql://...", "users", limit=100)
        >>> schema = ingestor.analyze_schema("postgresql://...")
    """

    def __init__(self, config: Optional[Dict[str, Any]] = None, **kwargs):
        """
        Initialize database ingestor.

        Sets up the ingestor with data exporter and configuration.

        Args:
            config: Optional database ingestion configuration dictionary
            **kwargs: Additional configuration parameters (merged into config)
        """
        self.logger = get_logger("db_ingestor")
        self.config = config or {}
        self.config.update(kwargs)

        # Initialize connectors dictionary (for connection reuse)
        self.connectors: Dict[str, DatabaseConnector] = {}

        # Initialize data exporter
        self.exporter = DataExporter(**self.config)

        # Supported databases
        self.supported_databases = list(DatabaseConnector.SUPPORTED_DATABASES.keys())

        # Initialize progress tracker
        self.progress_tracker = get_progress_tracker()

        self.logger.debug(
            f"DB ingestor initialized with support for: {', '.join(self.supported_databases)}"
        )

    def ingest_database(
        self,
        connection_string: str,
        include_tables: Optional[List[str]] = None,
        exclude_tables: Optional[List[str]] = None,
        max_rows_per_table: Optional[int] = None,
        **options,
    ) -> Dict[str, Any]:
        """
        Ingest data from entire database.

        This method connects to a database, analyzes the schema, and exports
        data from all tables (or a filtered subset). Useful for full database
        ingestion and backup scenarios.

        Args:
            connection_string: Database connection string
            include_tables: List of specific table names to include (optional,
                           if provided, only these tables are exported)
            exclude_tables: List of table names to exclude (optional,
                           default: empty list)
            max_rows_per_table: Maximum number of rows to export per table
                              (optional, for large tables)
            **options: Additional processing options (unused)

        Returns:
            dict: Database content dictionary containing:
                - schema: Database schema information
                - tables: Dictionary mapping table names to table data
                - total_tables: Total number of tables exported
                - connection_string: Connection string used
        """
        # Track database ingestion
        tracking_id = self.progress_tracker.start_tracking(
            file=connection_string.split("@")[-1]
            if "@" in connection_string
            else connection_string,
            module="ingest",
            submodule="DBIngestor",
            message=f"Database: {connection_string.split('@')[-1] if '@' in connection_string else 'database'}",
        )

        try:
            # Connect to database
            connector = DatabaseConnector("", **self.config)
            engine = connector.connect(connection_string)

            try:
                # Analyze schema first
                self.progress_tracker.update_tracking(
                    tracking_id, message="Analyzing schema..."
                )
                schema = self.analyze_schema(connection_string)

                # Get all table names
                from sqlalchemy import inspect
                inspector = inspect(engine)
                all_tables = inspector.get_table_names()

                self.logger.debug(f"Found {len(all_tables)} table(s) in database")

                # Apply table filters
                if include_tables:
                    tables = [t for t in all_tables if t in include_tables]
                    self.logger.debug(
                        f"Filtered to {len(tables)} table(s) via include_tables"
                    )
                else:
                    exclude_tables = exclude_tables or []
                    tables = [t for t in all_tables if t not in exclude_tables]
                    if exclude_tables:
                        self.logger.debug(
                            f"Filtered to {len(tables)} table(s) via exclude_tables"
                        )

                self.progress_tracker.update_tracking(
                    tracking_id, message=f"Exporting {len(tables)} tables..."
                )

                # Export data from each table
                table_data = {}

                for table_name in tables:
                    try:
                        # Export table with optional row limit
                        table_info = self.exporter.export_table_data(
                            engine, table_name, limit=max_rows_per_table
                        )
                        table_data[table_name] = {
                            "columns": table_info.columns,
                            "row_count": table_info.row_count,
                            "rows": table_info.rows,
                        }
                        self.logger.debug(
                            f"Exported table {table_name}: {table_info.row_count} row(s)"
                        )
                    except Exception as e:
                        self.logger.error(f"Failed to export table {table_name}: {e}")
                        if self.config.get("fail_fast", False):
                            raise ProcessingError(
                                f"Failed to export table {table_name}: {e}"
                            ) from e

                self.progress_tracker.stop_tracking(
                    tracking_id,
                    status="completed",
                    message=f"Exported {len(table_data)} tables",
                )
                self.logger.info(
                    f"Database ingestion completed: {len(table_data)} table(s) exported"
                )

                return {
                    "schema": schema,
                    "tables": table_data,
                    "total_tables": len(table_data),
                    "connection_string": connection_string,
                }

            except Exception as e:
                self.progress_tracker.stop_tracking(
                    tracking_id, status="failed", message=str(e)
                )
                raise

        except Exception as e:
            self.progress_tracker.stop_tracking(
                tracking_id, status="failed", message=str(e)
            )
            raise
        finally:
            connector.disconnect()

    def execute_query(
        self, connection_string: str, query: str, **params
    ) -> List[Dict[str, Any]]:
        """
        Execute SQL query and return results.

        This method executes a SQL query with optional parameters and returns
        results as a list of dictionaries. Converts database types to
        JSON-serializable formats.

        Args:
            connection_string: Database connection string
            query: SQL query to execute (can include parameter placeholders)
            **params: Query parameters (for parameterized queries)

        Returns:
            list: List of row dictionaries, each representing a query result row

        Raises:
            ProcessingError: If query execution fails

        Example:
            >>> results = ingestor.execute_query(
            ...     "postgresql://...",
            ...     "SELECT * FROM users WHERE age > :min_age",
            ...     min_age=18
            ... )
        """
        connector = DatabaseConnector("", **self.config)
        engine = connector.connect(connection_string)

        try:
            with engine.connect() as conn:
                # Execute query with parameters (parameterized queries for safety)
                result = conn.execute(text(query), params)

                # Convert results to list of dictionaries
                rows = []
                for row in result:
                    row_dict = {}
                    for col_name, value in row._mapping.items():
                        # Convert datetime to ISO format
                        if isinstance(value, datetime):
                            row_dict[col_name] = value.isoformat()
                        elif hasattr(value, "__dict__"):
                            # Complex types - convert to string
                            row_dict[col_name] = str(value)
                        else:
                            row_dict[col_name] = value
                    rows.append(row_dict)

                self.logger.debug(f"Query executed: {len(rows)} row(s) returned")
                return rows

        except Exception as e:
            self.logger.error(f"Failed to execute query: {e}")
            raise ProcessingError(f"Failed to execute query: {e}") from e
        finally:
            connector.disconnect()

    def export_table(
        self,
        connection_string: str,
        table_name: str,
        schema: Optional[str] = None,
        limit: Optional[int] = None,
        offset: Optional[int] = None,
        where: Optional[str] = None,
        order_by: Optional[str] = None,
        transform: bool = False,
        **filters,
    ) -> TableData:
        """
        Export data from specific table.

        This method exports data from a single database table with optional
        filtering, pagination, ordering, and transformation.

        Args:
            connection_string: Database connection string
            table_name: Name of the table to export
            schema: Schema name (for databases with schema support, optional)
            limit: Maximum number of rows to export (optional)
            offset: Row offset for pagination (optional)
            where: WHERE clause for filtering (optional, e.g., "status = 'active'").
                Raw SQL passed through to ``export_table_data`` — same trust
                requirement documented there: not for untrusted end-user text.
            order_by: ORDER BY clause for sorting (optional, e.g., "created_at DESC").
                Same trust requirement as ``where``.
            transform: Whether to apply data transformations (default: False)
            **filters: Additional filtering options (merged with above parameters)

        Returns:
            TableData: Table data object with columns, rows, and metadata
        """
        connector = DatabaseConnector("", **self.config)
        engine = connector.connect(connection_string)

        try:
            # Merge filters with explicit parameters
            export_options = {
                "limit": limit or filters.get("limit"),
                "offset": offset or filters.get("offset"),
                "where": where or filters.get("where"),
                "order_by": order_by or filters.get("order_by"),
            }
            # Remove None values
            export_options = {k: v for k, v in export_options.items() if v is not None}

            # Export table data
            table_data = self.exporter.export_table_data(
                engine, table_name, schema=schema, **export_options
            )

            # Transform data if requested
            if transform or filters.get("transform", False):
                schema_info = {"columns": table_data.columns}
                table_data.rows = self.exporter.transform_data(
                    table_data.rows, schema_info
                )
                self.logger.debug(f"Applied transformations to table {table_name}")

            return table_data

        finally:
            connector.disconnect()

    def analyze_schema(
        self, connection_string: str, schema: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        Analyze database schema and structure.

        This method exports the database schema and performs additional analysis
        including table counts, view counts, and foreign key relationships.

        Args:
            connection_string: Database connection string
            schema: Schema name (for databases with schema support, optional)

        Returns:
            dict: Schema analysis dictionary containing:
                - tables: List of table information
                - views: List of view names
                - foreign_keys: List of foreign key constraints
                - analysis: Analysis summary with counts and statistics
        """
        connector = DatabaseConnector("", **self.config)
        engine = connector.connect(connection_string)

        try:
            # Export base schema information
            schema_info = self.exporter.export_schema(engine, schema=schema)

            # Perform additional analysis
            schema_info["analysis"] = {
                "total_tables": len(schema_info["tables"]),
                "total_views": len(schema_info["views"]),
                "total_foreign_keys": len(schema_info["foreign_keys"]),
                "tables_with_foreign_keys": len(
                    set(
                        fk.get("referred_table", "")
                        for fk in schema_info["foreign_keys"]
                        if fk.get("referred_table")
                    )
                ),
            }

            self.logger.info(
                f"Schema analysis completed: {schema_info['analysis']['total_tables']} table(s), "
                f"{schema_info['analysis']['total_views']} view(s)"
            )

            return schema_info

        finally:
            connector.disconnect()
