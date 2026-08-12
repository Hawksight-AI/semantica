"""
Amazon Neptune Store Module

This module provides Amazon Neptune graph database integration with IAM authentication
using the Neo4j Bolt driver for property graph storage and OpenCypher querying
in the Semantica framework.

Key Features:
    - IAM authentication using AWS SigV4 signing via AuthManager
    - OpenCypher query language support via Bolt protocol
    - Node and relationship CRUD operations
    - Graph analytics
    - Batch operations with progress tracking
    - Automatic retry with backoff for transient errors
    - Connection recovery and token refresh

Main Classes:
    - AmazonNeptuneStore: Main Neptune store for graph operations
    - NeptuneAuthTokenManager: IAM authentication handler using AuthManager interface

Example Usage:
    >>> from semantica.graph_store import AmazonNeptuneStore
    >>> store = AmazonNeptuneStore(
    ...     endpoint="your-neptune-cluster.region.neptune.amazonaws.com",
    ...     port=8182,
    ...     region="us-east-1",
    ...     iam_auth=True
    ... )
    >>> store.connect()
    >>> node_id = store.create_node(labels=["Person"], properties={"name": "Alice"})
    >>> results = store.execute_query("MATCH (p:Person) RETURN p.name")
    >>> store.close()

Note: Amazon Neptune uses the Bolt protocol for OpenCypher queries.
      The endpoint is: bolt://<cluster-endpoint>:8182

Author: Semantica Contributors
License: MIT
"""

import json
import os
import sys
import uuid
from typing import Any, Dict, List, Optional, Union

from ..utils.exceptions import ProcessingError, ValidationError
from ..utils.logging import get_logger
from ..utils.progress_tracker import get_progress_tracker
from .query_sanitize import sanitize_identifier

# Optional boto3 for AWS credentials and SigV4 signing
try:
    from types import SimpleNamespace

    import boto3
    from botocore.auth import SigV4Auth, _host_from_url
    from botocore.awsrequest import AWSRequest

    BOTO3_AVAILABLE = True
except (ImportError, OSError):
    BOTO3_AVAILABLE = False
    boto3 = None
    SigV4Auth = None
    AWSRequest = None
    SimpleNamespace = None
    _host_from_url = None

# Optional Neo4j driver for Bolt protocol
try:
    from neo4j import GraphDatabase
    from neo4j.api import basic_auth
    from neo4j.auth_management import AuthManager
    from neo4j.exceptions import ClientError, DatabaseError, ServiceUnavailable

    NEO4J_AVAILABLE = True
except (ImportError, OSError):
    NEO4J_AVAILABLE = False
    GraphDatabase = None
    AuthManager = None
    basic_auth = None
    ServiceUnavailable = Exception
    DatabaseError = Exception
    ClientError = Exception

# Optional backoff for retry logic
try:
    import backoff

    BACKOFF_AVAILABLE = True
except (ImportError, OSError):
    BACKOFF_AVAILABLE = False
    backoff = None


# Retry configuration
NUM_RETRIES = 3
RETRIABLE_ERROR_MESSAGES = [
    "Signature expired",
    "Invalid authentication parameters",
    "Operation terminated (out of memory)",
    "Operation terminated (deadline exceeded)",
    "Operation terminated (cancelled by user)",
    "Database reset is in progress",
    "Operation failed due to conflicting concurrent operations",
    "Max number of request have breached",
    "Max connection limit breached",
    "Operation terminated (internal error)",
    "Connection is closed",
]
NETWORK_ERRORS = (OSError,)
if NEO4J_AVAILABLE:
    NETWORK_ERRORS = (OSError, ClientError)


# Module-level logger for NeptuneAuthTokenManager (kept outside class to avoid
# serialization issues when Neo4j driver inspects the AuthManager object)
_auth_logger = get_logger("neptune_auth_token_manager")


# Use AuthManager base class if available, otherwise just use object
_AuthManagerBase = AuthManager if NEO4J_AVAILABLE and AuthManager else object


class NeptuneAuthTokenManager(_AuthManagerBase):
    """
    Custom AuthManager for Amazon Neptune using SigV4 signing.
    Compatible with Neo4j Python Driver 5.x+

    This class implements the AuthManager interface to provide automatic
    token refresh and handling of security exceptions for Neptune IAM authentication.

    Note: This class intentionally does NOT store a logger as an instance
    attribute because the Neo4j driver inspects AuthManager objects and
    cannot serialize Logger types.
    """

    # Constants for SigV4 authentication
    SCHEME = "basic"
    REALM = "realm"
    SERVICE_NAME = "neptune-db"
    HTTP_METHOD_HDR = "HttpMethod"
    DUMMY_USERNAME = "username"
    AUTHORIZATION = "Authorization"
    HOST = "Host"
    X_AMZ_DATE = "X-Amz-Date"
    X_AMZ_SECURITY_TOKEN = "X-Amz-Security-Token"

    def __init__(
        self,
        neptune_endpoint: str,
        aws_region: str,
        access_key: Optional[str] = None,
        secret_key: Optional[str] = None,
        session_token: Optional[str] = None,
    ):
        """
        Initialize Neptune Auth Token Manager.

        Args:
            neptune_endpoint: Neptune endpoint URL (bolt://...)
            aws_region: AWS region
            access_key: AWS access key ID (optional, uses boto3 credentials
                if not provided)
            secret_key: AWS secret access key (optional, uses boto3
                credentials if not provided)
            session_token: AWS session token for temporary credentials (optional)

        Note: This class intentionally stores only simple types (str, None) as instance
        attributes because the Neo4j driver inspects AuthManager objects and cannot
        serialize complex types like Logger or boto3.Session.
        """
        if not BOTO3_AVAILABLE:
            raise ProcessingError(
                "boto3 is required for IAM authentication. "
                "Install with: pip install boto3"
            )

        # Replace bolt protocol with https for signing
        # Only store simple serializable types as instance attributes!
        self.neptune_endpoint = neptune_endpoint.replace("bolt", "https")
        self.aws_region = aws_region
        self.cached_auth = None

        # Store credential strings (can be None - will use default chain)
        self._access_key = access_key
        self._secret_key = secret_key
        self._session_token = session_token

    def get_auth(self):
        """
        Return the current authentication information.
        Uses caching to avoid regenerating SigV4 signatures unnecessarily.

        Returns:
            Basic auth token containing SigV4 signature information
        """
        cached = "None" if self.cached_auth is None else "cached"
        _auth_logger.debug(f"get_auth() called, cached_auth is {cached}")
        if self.cached_auth is None:
            _auth_logger.info("Generating new SigV4 signed auth token...")
            self.cached_auth = self._generate_sigv4_auth_token()
        else:
            _auth_logger.debug("Using cached SigV4 token")

        return self.cached_auth

    def handle_security_exception(self, auth, error) -> bool:
        """
        Handle security exceptions by refreshing the token.

        Args:
            auth: The authentication token that caused the exception
            error: The security exception that occurred

        Returns:
            True to retry with new token, False to propagate exception
        """
        error_msg = str(error) if error else "Unknown error"
        _auth_logger.warning(
            f"Caught SecurityException: {error_msg} - regenerating token"
        )

        # Force token regeneration
        self.refresh_token()
        return True

    def refresh_token(self):
        """
        Force refresh of the authentication token.
        Invalidates cached token to force regeneration on next request.
        """
        self.cached_auth = None
        _auth_logger.info("Auth token forcibly refreshed due to signature expiration")

    def update_context(self, context):
        """
        Update execution context for logging purposes.

        Note: We don't store the context as an instance attribute because
        the Neo4j driver cannot serialize complex objects.

        Args:
            context: Execution context (e.g., from serverless environment)
        """
        # Note: Don't store context - Neo4j can't serialize it
        # Instead, just log that we received it
        _auth_logger.debug(
            "Execution context received (not stored due to serialization constraints)"
        )

    def _generate_sigv4_auth_token(self):
        """
        Generate a new SigV4 signed authentication token for Neptune.

        Returns:
            Basic auth token containing SigV4 signature information
        """
        if not BOTO3_AVAILABLE:
            raise ProcessingError(
                "boto3 is required for IAM authentication. "
                "Install with: pip install boto3"
            )

        try:
            _auth_logger.info(
                f"Generating SigV4 token for endpoint: {self.neptune_endpoint}"
            )

            # Create AWS request for signing
            request = AWSRequest(method="GET", url=self.neptune_endpoint, data=None)
            host_value = _host_from_url(request.url)
            _auth_logger.debug(f"Host header value: {host_value}")
            request.headers.add_header("Host", host_value)

            # Get AWS credentials - match the sample implementation exactly
            # Create fresh session each time (not stored as instance attribute)
            credentials = boto3.Session().get_credentials()
            if not credentials:
                raise ProcessingError(
                    "AWS credentials not found. Configure credentials via "
                    "environment variables, ~/.aws/credentials, IAM role, "
                    "or provide explicitly."
                )

            # Create credentials namespace for SigV4Auth
            # (matching sample implementation)
            creds = SimpleNamespace(
                access_key=credentials.access_key,
                secret_key=credentials.secret_key,
                token=credentials.token,
                region=self.aws_region,
            )

            # Sign the request
            SigV4Auth(creds, self.SERVICE_NAME, self.aws_region).add_auth(request)

            # Create auth info JSON from signed headers
            auth_info_json = self._get_auth_info_json(request)
            _auth_logger.info(f"Auth info JSON: {auth_info_json}")

            # Return basic auth token with dummy username and signed headers as password
            return basic_auth(self.DUMMY_USERNAME, auth_info_json)

        except Exception as e:
            raise ProcessingError(
                f"Failed to generate SigV4 auth token for Neptune: {str(e)}"
            ) from e

    def _get_auth_info_json(self, request) -> str:
        """
        Convert signed request headers into JSON string for authentication.

        Args:
            request: The signed AWS HTTP request

        Returns:
            JSON string containing authentication information
        """
        auth_info = {
            self.AUTHORIZATION: request.headers.get(self.AUTHORIZATION),
            self.HTTP_METHOD_HDR: request.method,
            self.X_AMZ_DATE: request.headers.get(self.X_AMZ_DATE),
            self.HOST: request.headers.get(self.HOST),
            self.X_AMZ_SECURITY_TOKEN: request.headers.get(self.X_AMZ_SECURITY_TOKEN),
        }

        return json.dumps(auth_info)


class NeptuneDriver:
    """Neptune driver wrapper (analogous to Neo4jDriver)."""

    def __init__(self, driver: Any):
        """Initialize Neptune driver wrapper."""
        self.driver = driver
        self.logger = get_logger("neptune_driver")

    def session(self, database: Optional[str] = None) -> "NeptuneSession":
        """
        Create a new session.

        Args:
            database: Database name (ignored for Neptune, included for
                API compatibility)

        Returns:
            NeptuneSession instance
        """
        if not NEO4J_AVAILABLE:
            raise ProcessingError("Neo4j driver not available")

        try:
            # Neptune doesn't support multiple databases, but accepts
            # database parameter
            session = self.driver.session()
            return NeptuneSession(session)
        except Exception as e:
            raise ProcessingError(f"Failed to create session: {str(e)}")

    def verify_connectivity(self) -> bool:
        """Verify connectivity to Neptune server."""
        if not NEO4J_AVAILABLE:
            return False

        try:
            # Simple query to verify connectivity
            with self.driver.session() as session:
                session.run("RETURN 1")
            return True
        except Exception as e:
            self.logger.warning(f"Connectivity check failed: {e}")
            return False

    def close(self) -> None:
        """Close the driver."""
        if self.driver:
            self.driver.close()


class NeptuneSession:
    """Neptune session wrapper (analogous to Neo4jSession)."""

    def __init__(self, session: Any):
        """Initialize Neptune session wrapper."""
        self.session = session
        self.logger = get_logger("neptune_session")

    def run(self, query: str, parameters: Optional[Dict[str, Any]] = None) -> Any:
        """
        Run an OpenCypher query.

        Args:
            query: OpenCypher query string
            parameters: Query parameters

        Returns:
            Query result
        """
        if not NEO4J_AVAILABLE:
            raise ProcessingError("Neo4j driver not available")

        try:
            result = self.session.run(query, parameters or {})
            return result
        except Exception as e:
            raise ProcessingError(f"Query execution failed: {str(e)}")

    def begin_transaction(self) -> "NeptuneTransaction":
        """Begin a new transaction."""
        if not NEO4J_AVAILABLE:
            raise ProcessingError("Neo4j driver not available")

        try:
            tx = self.session.begin_transaction()
            return NeptuneTransaction(tx)
        except Exception as e:
            raise ProcessingError(f"Failed to begin transaction: {str(e)}")

    def read_transaction(self, func: Any, **kwargs) -> Any:
        """Execute a read transaction."""
        return self.session.execute_read(func, **kwargs)

    def write_transaction(self, func: Any, **kwargs) -> Any:
        """Execute a write transaction."""
        return self.session.execute_write(func, **kwargs)

    def close(self) -> None:
        """Close the session."""
        if self.session:
            self.session.close()

    def __enter__(self):
        """Context manager entry."""
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        """Context manager exit."""
        self.close()


class NeptuneTransaction:
    """Neptune transaction wrapper (analogous to Neo4jTransaction)."""

    def __init__(self, transaction: Any):
        """Initialize Neptune transaction wrapper."""
        self.transaction = transaction
        self.logger = get_logger("neptune_transaction")

    def run(self, query: str, parameters: Optional[Dict[str, Any]] = None) -> Any:
        """
        Run an OpenCypher query within the transaction.

        Args:
            query: OpenCypher query string
            parameters: Query parameters

        Returns:
            Query result
        """
        if not NEO4J_AVAILABLE:
            raise ProcessingError("Neo4j driver not available")

        try:
            result = self.transaction.run(query, parameters or {})
            return result
        except Exception as e:
            raise ProcessingError(f"Transaction query failed: {str(e)}")

    def commit(self) -> None:
        """Commit the transaction."""
        if self.transaction:
            self.transaction.commit()

    def rollback(self) -> None:
        """Rollback the transaction."""
        if self.transaction:
            self.transaction.rollback()

    def __enter__(self):
        """Context manager entry."""
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        """Context manager exit."""
        if exc_type is not None:
            self.rollback()
        else:
            self.commit()


class AmazonNeptuneStore:
    """
    Amazon Neptune store for property graph storage and OpenCypher querying
    using the Neo4j Bolt driver.

    Features:
    • IAM authentication using AWS SigV4 signing via AuthManager
    • OpenCypher query language support via Bolt protocol
    • Node and relationship CRUD operations
    • Transaction support with commit/rollback
    • Graph analytics
    • Automatic retry with backoff for transient errors
    • Connection recovery and token refresh
    • Performance optimization

    Note: Amazon Neptune uses the Bolt protocol for OpenCypher queries.
    The endpoint is: bolt://<cluster-endpoint>:8182
    """

    def __init__(
        self,
        endpoint: Optional[str] = None,
        port: int = 8182,
        region: Optional[str] = None,
        iam_auth: bool = True,
        access_key: Optional[str] = None,
        secret_key: Optional[str] = None,
        session_token: Optional[str] = None,
        use_ssl: bool = True,
        max_connection_pool_size: int = 50,
        connection_timeout: float = 30.0,
        **config,
    ):
        """
        Initialize Amazon Neptune store.

        Args:
            endpoint: Neptune cluster endpoint
                (e.g., 'cluster.region.neptune.amazonaws.com')
            port: Neptune Bolt port (default: 8182)
            region: AWS region (e.g., 'us-east-1')
            iam_auth: Use IAM authentication (default: True)
            access_key: AWS access key ID (optional)
            secret_key: AWS secret access key (optional)
            session_token: AWS session token for temporary credentials (optional)
            use_ssl: Use SSL/TLS connection (default: True, required for Neptune)
            max_connection_pool_size: Maximum number of connections in the pool
            connection_timeout: Connection timeout in seconds
            **config: Additional configuration options
        """
        self.logger = get_logger("amazon_neptune_store")
        self.config = config
        self.progress_tracker = get_progress_tracker()

        # Ensure progress tracker is enabled
        if not self.progress_tracker.enabled:
            self.progress_tracker.enabled = True

        # Check dependencies
        if not NEO4J_AVAILABLE:
            raise ProcessingError(
                "neo4j driver is required. Install with: pip install neo4j"
            )

        # Connection settings
        self.endpoint = endpoint or config.get("endpoint")
        self.port = int(port) if port else config.get("port", 8182)
        self.region = (
            region
            or config.get("region")
            or os.getenv("AWS_REGION")
            or os.getenv("AWS_DEFAULT_REGION", "us-east-1")
        )
        self.iam_auth = iam_auth
        self.use_ssl = use_ssl
        self.max_connection_pool_size = max_connection_pool_size
        self.connection_timeout = connection_timeout

        # IAM credentials
        self._access_key = access_key
        self._secret_key = secret_key
        self._session_token = session_token

        # Driver and auth manager
        self._driver = None
        self._auth_manager: Optional[NeptuneAuthTokenManager] = None
        self._connected = False

    @property
    def bolt_uri(self) -> str:
        """Get the Bolt URI for Neptune connection."""
        return f"bolt://{self.endpoint}:{self.port}/opencypher"

    def _is_retriable_error(self, e: Exception) -> bool:
        """
        Determine if an exception is retriable based on error message patterns.

        Args:
            e: Exception to evaluate

        Returns:
            True if error should be retried, False otherwise
        """
        is_retriable = False
        err_msg = str(e)

        # Check for DatabaseError with authentication issues
        if NEO4J_AVAILABLE and isinstance(e, DatabaseError):
            is_retriable = any(
                retriable_msg in err_msg for retriable_msg in RETRIABLE_ERROR_MESSAGES
            )
        elif isinstance(e, NETWORK_ERRORS):
            is_retriable = True
        else:
            is_retriable = any(
                retriable_msg in err_msg for retriable_msg in RETRIABLE_ERROR_MESSAGES
            )

        type_name = type(e).__name__
        self.logger.debug(
            f"Retry evaluation: [{type_name}] {err_msg} -> "
            f"is_retriable={is_retriable}"
        )
        return is_retriable

    def _is_non_retriable_error(self, e: Exception) -> bool:
        """
        Determine if an exception is non-retriable (inverse of is_retriable_error).

        Args:
            e: Exception to evaluate

        Returns:
            True if error should not be retried, False otherwise
        """
        return not self._is_retriable_error(e)

    def _reset_connection_if_needed(self, details: Dict = None):
        """
        Reset the driver connection if the current exception indicates a
        connection issue. Called by backoff decorator when retrying failed
        operations.

        Args:
            details: Backoff details dictionary (optional)
        """
        e = sys.exc_info()[1]
        if e is None:
            return

        err_msg = str(e)
        is_reconnectable = False

        if isinstance(e, NETWORK_ERRORS):
            is_reconnectable = True
        else:
            is_reconnectable = any(msg in err_msg for msg in RETRIABLE_ERROR_MESSAGES)

        self.logger.info(
            f"Connection issue detected: is_reconnectable={is_reconnectable}"
        )

        if is_reconnectable:
            self.logger.info("Resetting connection due to connection issue")
            self._recreate_driver()

    def _recreate_driver(self):
        """Recreate the Neo4j driver."""
        if self._driver:
            try:
                self._driver.close()
            except Exception as close_err:
                self.logger.warning(f"Error closing driver: {close_err}")
        self._driver = self._create_driver()

    def _create_driver(self):
        """
        Create and configure Neo4j driver for Neptune connection.
        Uses IAM authentication if iam_auth is True.

        Returns:
            Configured Neo4j GraphDatabase driver instance

        Raises:
            ProcessingError: If driver creation fails
        """
        self.logger.info("Creating Neo4j driver for Neptune")

        try:
            bolt_uri = self.bolt_uri
            self.logger.info(f"Connecting to: {bolt_uri}")

            if self.iam_auth:
                if not self.region:
                    raise ValidationError(
                        "AWS region is required for IAM authentication. "
                        "Set via 'region' parameter or AWS_REGION environment variable."
                    )

                # Create auth manager for IAM authentication
                self._auth_manager = NeptuneAuthTokenManager(
                    neptune_endpoint=bolt_uri,
                    aws_region=self.region,
                    access_key=self._access_key,
                    secret_key=self._secret_key,
                    session_token=self._session_token,
                )

                driver = GraphDatabase.driver(
                    bolt_uri,
                    auth=self._auth_manager,
                    encrypted=self.use_ssl,
                    max_connection_pool_size=self.max_connection_pool_size,
                    connection_timeout=self.connection_timeout,
                )
            else:
                driver = GraphDatabase.driver(
                    bolt_uri,
                    auth=None,
                    encrypted=self.use_ssl,
                    max_connection_pool_size=self.max_connection_pool_size,
                    connection_timeout=self.connection_timeout,
                )

            return driver

        except Exception as e:
            self.logger.error(f"Failed to create driver: {str(e)}")
            raise ProcessingError(f"Failed to create Neptune driver: {str(e)}") from e

    def _execute_with_retry(self, operation_func, *args, **kwargs):
        """
        Execute an operation with retry logic.

        Args:
            operation_func: Function to execute
            *args: Arguments to pass to the function
            **kwargs: Keyword arguments to pass to the function

        Returns:
            Result of the operation
        """
        if BACKOFF_AVAILABLE:
            # Use backoff decorator for retry logic
            @backoff.on_exception(
                backoff.constant,
                (
                    (ServiceUnavailable, DatabaseError, OSError)
                    if NEO4J_AVAILABLE
                    else (OSError,)
                ),
                max_tries=NUM_RETRIES,
                jitter=None,
                giveup=self._is_non_retriable_error,
                on_backoff=lambda details: self._reset_connection_if_needed(details),
                interval=1,
            )
            def _execute():
                return operation_func(*args, **kwargs)

            return _execute()
        else:
            # Simple retry without backoff library
            last_error = None
            for attempt in range(NUM_RETRIES):
                try:
                    return operation_func(*args, **kwargs)
                except Exception as e:
                    last_error = e
                    if self._is_non_retriable_error(e):
                        raise
                    self.logger.warning(
                        f"Attempt {attempt + 1}/{NUM_RETRIES} failed: {e}"
                    )
                    self._reset_connection_if_needed()
            raise last_error

    def _run_query(
        self, query: str, parameters: Optional[Dict[str, Any]] = None
    ) -> List[Dict[str, Any]]:
        """
        Execute an OpenCypher query against Neptune.

        Args:
            query: OpenCypher query string
            parameters: Query parameters dictionary (optional)

        Returns:
            List of dictionaries containing query results
        """

        def _execute():
            try:
                with self._driver.session() as session:
                    result = session.run(query, parameters or {})
                    return [dict(record) for record in result]

            # In some cases, a generic AttributeError is thrown prior to
            # the Neo4j specific exception. This throws the root context
            # of the AttributeError for more specific error handling.
            except AttributeError as e:
                self.logger.error(f"AttributeError caught: {str(e)}")
                if e.__context__:
                    raise e.__context__ from e
                raise
            except (
                (DatabaseError, ServiceUnavailable) if NEO4J_AVAILABLE else Exception
            ) as e:
                self.logger.error(f"Query error: {str(e)}")
                raise

        return self._execute_with_retry(_execute)

    def connect(self, **options) -> bool:
        """
        Connect to Amazon Neptune (initializes Bolt driver).

        Args:
            **options: Connection options

        Returns:
            True if connected successfully
        """
        if not self.endpoint:
            raise ValidationError("Neptune endpoint is required")

        try:
            # Create driver
            self._driver = self._create_driver()

            # Test connectivity with a simple query
            self._run_query("RETURN 1 as test")

            self._connected = True
            self.logger.info(f"Connected to Amazon Neptune at {self.endpoint}")
            return True

        except Exception as e:
            self._connected = False
            raise ProcessingError(f"Failed to connect to Neptune: {str(e)}") from e

    def close(self) -> None:
        """Close connection to Neptune."""
        if self._driver:
            try:
                self._driver.close()
            except Exception as e:
                self.logger.warning(f"Error closing driver: {e}")
            self._driver = None
        self._connected = False
        self.logger.info("Disconnected from Amazon Neptune")

    def _ensure_connected(self):
        """Ensure the driver is connected, connecting if necessary."""
        if self._driver is None or not self._connected:
            self.connect()

    def get_session(self, database: Optional[str] = None) -> NeptuneSession:
        """
        Get or create a session.

        Args:
            database: Database name (ignored for Neptune, included for
                API compatibility)

        Returns:
            NeptuneSession instance
        """
        self._ensure_connected()
        return NeptuneSession(self._driver.session())

    def _generate_id(self) -> str:
        """Generate a unique node/relationship ID."""
        return str(uuid.uuid4())

    def _parse_record_value(self, value: Any) -> Any:
        """
        Parse a value from a Neo4j record.

        Args:
            value: Value from Neo4j record

        Returns:
            Parsed value
        """
        if value is None:
            return None

        # Check if it's a Neo4j Node
        if hasattr(value, "id") and hasattr(value, "labels"):
            # It's a Node
            return {
                "id": value.get("~id", str(value.id) if hasattr(value, "id") else None),
                "labels": list(value.labels) if hasattr(value, "labels") else [],
                "properties": dict(value) if value else {},
            }

        # Check if it's a Neo4j Relationship
        if hasattr(value, "type") and hasattr(value, "start_node"):
            return {
                "id": value.get("~id", str(value.id) if hasattr(value, "id") else None),
                "type": value.type,
                "start_node_id": (
                    str(value.start_node.id)
                    if hasattr(value.start_node, "id")
                    else None
                ),
                "end_node_id": (
                    str(value.end_node.id) if hasattr(value.end_node, "id") else None
                ),
                "properties": dict(value) if value else {},
            }

        # Check if it's a dict (Neptune returns dicts for nodes/relationships)
        if isinstance(value, dict):
            if "~id" in value or "~entityType" in value:
                # This is a Neptune node or relationship
                properties = {k: v for k, v in value.items() if not k.startswith("~")}
                parsed = {
                    "id": value.get("~id"),
                    "labels": value.get("~labels", []),
                    "properties": properties,
                }
                # Handle relationships
                if "~type" in value:
                    parsed["type"] = value.get("~type")
                if "~start" in value:
                    parsed["start_node_id"] = value.get("~start")
                if "~end" in value:
                    parsed["end_node_id"] = value.get("~end")
                return parsed
            return value

        return value

    def _parse_results(self, records: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """
        Parse Neptune/Neo4j query results.

        Args:
            records: List of record dictionaries

        Returns:
            List of parsed records
        """
        parsed_records = []
        for record in records:
            parsed_record = {}
            for key, value in record.items():
                parsed_record[key] = self._parse_record_value(value)
            parsed_records.append(parsed_record)
        return parsed_records

    def create_node(
        self,
        labels: List[str],
        properties: Dict[str, Any],
        **options,
    ) -> Dict[str, Any]:
        """
        Create a node in the graph.

        Uses Neptune's native ~id for node identification. If 'id' is provided
        in properties, it will be used as the Neptune ~id. Otherwise, a UUID
        is generated.

        If a node with the same ID already exists:
        - By default (merge=True), uses MERGE to return existing node or create new
        - With merge=False, uses CREATE which will fail if ID exists

        Args:
            labels: Node labels
            properties: Node properties (may include 'id' for custom ~id)
            **options: Additional options including:
                - merge (bool): If True (default), use MERGE; if False, use CREATE

        Returns:
            Created node information including ID
        """
        tracking_id = self.progress_tracker.start_tracking(
            module="graph_store",
            submodule="AmazonNeptuneStore",
            message=f"Creating node with labels {labels}",
        )

        try:
            self._ensure_connected()

            # Extract ID from properties or generate one
            props_copy = dict(properties)
            node_id = props_copy.pop("id", None) or self._generate_id()
            use_merge = options.get("merge", True)

            label_str = ":".join(sanitize_identifier(l, "label") for l in labels) if labels else "Node"
            safe_keys = [sanitize_identifier(k, "property key") for k in props_copy.keys()]

            # Build parameters
            params = {"node_id": str(node_id)}
            for key, value in props_copy.items():
                params[key] = value

            if use_merge:
                # MERGE: Return existing node if ID matches, or create new
                set_parts = [f"n.{key} = ${key}" for key in safe_keys]

                if set_parts:
                    set_clause = ", ".join(set_parts)
                    query = (
                        f"MERGE (n:{label_str} {{`~id`: $node_id}}) "
                        f"ON CREATE SET {set_clause} "
                        f"ON MATCH SET {set_clause} RETURN n"
                    )
                else:
                    query = f"MERGE (n:{label_str} {{`~id`: $node_id}}) RETURN n"
            else:
                # CREATE: Will fail if node with same ID exists
                prop_parts = ["`~id`: $node_id"] + [f"{key}: ${key}" for key in safe_keys]
                prop_assignments = ", ".join(prop_parts)
                query = f"CREATE (n:{label_str} {{{prop_assignments}}}) RETURN n"

            records = self._run_query(query, params)
            parsed = self._parse_results(records)

            if parsed:
                node_data = parsed[0].get("n", {})
                if isinstance(node_data, dict):
                    if "id" not in node_data:
                        node_data["id"] = node_id
                    if "labels" not in node_data:
                        node_data["labels"] = labels

                    self.progress_tracker.stop_tracking(
                        tracking_id,
                        status="completed",
                        message=f"Created node with ID {node_id}",
                    )
                    return node_data

            # Node was created but not returned - return what we know
            self.progress_tracker.stop_tracking(
                tracking_id,
                status="completed",
                message=f"Created node with ID {node_id}",
            )
            return {
                "id": node_id,
                "labels": labels,
                "properties": props_copy,
            }

        except Exception as e:
            self.progress_tracker.stop_tracking(
                tracking_id, status="failed", message=str(e)
            )
            raise ProcessingError(f"Failed to create node: {str(e)}") from e

    def create_nodes(
        self,
        nodes: List[Dict[str, Any]],
        **options,
    ) -> List[Dict[str, Any]]:
        """
        Create multiple nodes in batch.

        Args:
            nodes: List of node dictionaries with 'labels' and 'properties'
            **options: Additional options

        Returns:
            List of created node information
        """
        tracking_id = self.progress_tracker.start_tracking(
            module="graph_store",
            submodule="AmazonNeptuneStore",
            message=f"Creating {len(nodes)} nodes in batch",
        )

        try:
            created_nodes = []

            for node in nodes:
                labels = node.get("labels", [])
                properties = node.get("properties", {})

                result = self.create_node(labels, properties, **options)
                created_nodes.append(result)

            self.progress_tracker.stop_tracking(
                tracking_id,
                status="completed",
                message=f"Created {len(created_nodes)} nodes",
            )
            return created_nodes

        except Exception as e:
            self.progress_tracker.stop_tracking(
                tracking_id, status="failed", message=str(e)
            )
            raise ProcessingError(f"Failed to create nodes: {str(e)}") from e

    def get_node(
        self,
        node_id: Union[int, str],
        **options,
    ) -> Optional[Dict[str, Any]]:
        """
        Get a node by ID (using Neptune's native ~id).

        Args:
            node_id: Node ID (Neptune's ~id value)
            **options: Additional options

        Returns:
            Node information or None if not found
        """
        try:
            self._ensure_connected()

            # Use id(n) function to match and return Neptune's native ~id
            query = (
                "MATCH (n) WHERE id(n) = $id "
                "RETURN n, labels(n) as labels, id(n) as node_id"
            )

            records = self._run_query(query, {"id": str(node_id)})
            parsed = self._parse_results(records)

            if parsed:
                record = parsed[0]
                node_data = record.get("n", {})
                # Use node_id from query (the ~id we set) as primary ID
                returned_id = record.get("node_id", node_id)
                properties = (
                    node_data.get("properties", {})
                    if isinstance(node_data, dict)
                    else {}
                )
                return {
                    "id": returned_id,
                    "labels": record.get("labels", []),
                    "properties": properties,
                }
            return None

        except Exception as e:
            raise ProcessingError(f"Failed to get node: {str(e)}") from e

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
            labels: Filter by labels
            properties: Filter by properties
            limit: Maximum number of nodes to return
            **options: Additional options

        Returns:
            List of matching nodes
        """
        try:
            self._ensure_connected()

            # Build query
            if labels:
                label_str = ":".join(sanitize_identifier(l, "label") for l in labels)
                query = f"MATCH (n:{label_str})"
            else:
                query = "MATCH (n)"

            # Add property filters
            params = {}
            if properties:
                conditions = []
                for key, value in properties.items():
                    safe_key = sanitize_identifier(key, "property key")
                    param_key = f"prop_{safe_key}"
                    conditions.append(f"n.{safe_key} = ${param_key}")
                    params[param_key] = value
                query += " WHERE " + " AND ".join(conditions)

            # Include id(n) to get Neptune's native ~id
            query += (
                f" RETURN n, labels(n) as labels, id(n) as node_id " f"LIMIT {limit}"
            )

            records = self._run_query(query, params)
            parsed = self._parse_results(records)

            nodes = []
            for record in parsed:
                node = record.get("n", {})
                # Use node_id from query (the ~id we set) as primary ID
                returned_id = record.get("node_id")
                properties_data = (
                    node.get("properties", {}) if isinstance(node, dict) else {}
                )
                nodes.append(
                    {
                        "id": returned_id,
                        "labels": record.get("labels", []),
                        "properties": properties_data,
                    }
                )

            return nodes

        except Exception as e:
            raise ProcessingError(f"Failed to get nodes: {str(e)}") from e

    def update_node(
        self,
        node_id: Union[int, str],
        properties: Dict[str, Any],
        merge: bool = True,
        **options,
    ) -> Dict[str, Any]:
        """
        Update a node's properties (using Neptune's native ~id).

        Args:
            node_id: Node ID (Neptune's ~id value)
            properties: Properties to update
            merge: If True, merge properties; if False, replace
            **options: Additional options

        Returns:
            Updated node information
        """
        try:
            self._ensure_connected()

            if merge:
                # SET n += $props merges properties
                query = (
                    "MATCH (n) WHERE id(n) = $id SET n += $props "
                    "RETURN n, labels(n) as labels, id(n) as node_id"
                )
            else:
                # SET n = $props replaces all properties
                query = (
                    "MATCH (n) WHERE id(n) = $id SET n = $props "
                    "RETURN n, labels(n) as labels, id(n) as node_id"
                )

            records = self._run_query(query, {"id": str(node_id), "props": properties})
            parsed = self._parse_results(records)

            if parsed:
                record = parsed[0]
                node_data = record.get("n", {})
                # Use node_id from query (the ~id we set) as primary ID
                returned_id = record.get("node_id", node_id)
                properties_data = (
                    node_data.get("properties", {})
                    if isinstance(node_data, dict)
                    else {}
                )
                return {
                    "id": returned_id,
                    "labels": record.get("labels", []),
                    "properties": properties_data,
                }
            else:
                raise ProcessingError(f"Node with ID {node_id} not found")

        except Exception as e:
            raise ProcessingError(f"Failed to update node: {str(e)}") from e

    def delete_node(
        self,
        node_id: Union[int, str],
        detach: bool = True,
        **options,
    ) -> bool:
        """
        Delete a node (using Neptune's native ~id).

        Args:
            node_id: Node ID (Neptune's ~id value)
            detach: If True, delete relationships as well
            **options: Additional options

        Returns:
            True if deleted successfully
        """
        try:
            self._ensure_connected()

            if detach:
                query = "MATCH (n) WHERE id(n) = $id DETACH DELETE n"
            else:
                query = "MATCH (n) WHERE id(n) = $id DELETE n"

            self._run_query(query, {"id": str(node_id)})
            return True

        except Exception as e:
            raise ProcessingError(f"Failed to delete node: {str(e)}") from e

    def create_relationship(
        self,
        start_node_id: Union[int, str],
        end_node_id: Union[int, str],
        rel_type: str,
        properties: Optional[Dict[str, Any]] = None,
        **options,
    ) -> Dict[str, Any]:
        """
        Create a relationship between two nodes (using Neptune's native ~id).

        Uses Neptune's native ~id for relationship identification. If 'id' is
        provided in properties, it will be used as the Neptune ~id.

        Args:
            start_node_id: Start node ID (Neptune's ~id value)
            end_node_id: End node ID (Neptune's ~id value)
            rel_type: Relationship type
            properties: Relationship properties (may include 'id' for custom ~id)
            **options: Additional options

        Returns:
            Created relationship information
        """
        tracking_id = self.progress_tracker.start_tracking(
            module="graph_store",
            submodule="AmazonNeptuneStore",
            message=f"Creating relationship [{rel_type}]",
        )

        try:
            self._ensure_connected()

            properties = properties or {}
            props_copy = dict(properties)
            rel_id = props_copy.pop("id", None) or self._generate_id()

            # Build query using id() function for node matching and ~id for relationship
            params = {
                "start_id": str(start_node_id),
                "end_id": str(end_node_id),
                "rel_id": str(rel_id),
            }

            # Build property assignments including ~id
            safe_rel_type = sanitize_identifier(rel_type, "relationship type")
            prop_parts = ["`~id`: $rel_id"]
            for key, value in props_copy.items():
                prop_parts.append(f"{sanitize_identifier(key, 'property key')}: ${key}")
                params[key] = value

            prop_assignments = ", ".join(prop_parts)
            query = (
                f"MATCH (a), (b) WHERE id(a) = $start_id AND id(b) = $end_id "
                f"CREATE (a)-[r:{safe_rel_type} {{{prop_assignments}}}]->(b) RETURN r"
            )

            records = self._run_query(query, params)
            parsed = self._parse_results(records)

            rel_data = {
                "id": rel_id,
                "type": rel_type,
                "start_node_id": start_node_id,
                "end_node_id": end_node_id,
                "properties": props_copy,
            }

            if parsed:
                returned_rel = parsed[0].get("r", {})
                if isinstance(returned_rel, dict) and returned_rel.get("id"):
                    rel_data["id"] = returned_rel["id"]

            self.progress_tracker.stop_tracking(
                tracking_id,
                status="completed",
                message=f"Created relationship with ID {rel_id}",
            )
            return rel_data

        except Exception as e:
            self.progress_tracker.stop_tracking(
                tracking_id, status="failed", message=str(e)
            )
            raise ProcessingError(f"Failed to create relationship: {str(e)}") from e

    def get_relationships(
        self,
        node_id: Optional[Union[int, str]] = None,
        rel_type: Optional[str] = None,
        direction: str = "both",
        limit: int = 100,
        **options,
    ) -> List[Dict[str, Any]]:
        """
        Get relationships matching criteria (using Neptune's native ~id).

        Args:
            node_id: Filter by node ID (Neptune's ~id value)
            rel_type: Filter by relationship type
            direction: Direction ("in", "out", "both")
            limit: Maximum number of relationships
            **options: Additional options

        Returns:
            List of matching relationships
        """
        try:
            self._ensure_connected()

            type_filter = f":{sanitize_identifier(rel_type, 'relationship type')}" if rel_type else ""
            params = {}

            if node_id is not None:
                params["node_id"] = str(node_id)
                if direction == "out":
                    query = (
                        f"MATCH (a)-[r{type_filter}]->(b) "
                        f"WHERE id(a) = $node_id "
                        f"RETURN r, id(a) as start_id, id(b) as end_id "
                        f"LIMIT {limit}"
                    )
                elif direction == "in":
                    query = (
                        f"MATCH (a)<-[r{type_filter}]-(b) "
                        f"WHERE id(a) = $node_id "
                        f"RETURN r, id(b) as start_id, id(a) as end_id "
                        f"LIMIT {limit}"
                    )
                else:
                    query = (
                        f"MATCH (a)-[r{type_filter}]-(b) "
                        f"WHERE id(a) = $node_id "
                        f"RETURN r, id(a) as start_id, id(b) as end_id "
                        f"LIMIT {limit}"
                    )
            else:
                query = (
                    f"MATCH (a)-[r{type_filter}]->(b) "
                    f"RETURN r, id(a) as start_id, id(b) as end_id "
                    f"LIMIT {limit}"
                )

            records = self._run_query(query, params)
            parsed = self._parse_results(records)

            relationships = []
            for record in parsed:
                rel = record.get("r", {})
                relationships.append(
                    {
                        "id": rel.get("id") if isinstance(rel, dict) else None,
                        "type": (
                            rel.get("type", rel_type)
                            if isinstance(rel, dict)
                            else rel_type
                        ),
                        "start_node_id": record.get("start_id"),
                        "end_node_id": record.get("end_id"),
                        "properties": (
                            rel.get("properties", {}) if isinstance(rel, dict) else {}
                        ),
                    }
                )

            return relationships

        except Exception as e:
            raise ProcessingError(f"Failed to get relationships: {str(e)}") from e

    def delete_relationship(
        self,
        rel_id: Union[int, str],
        **options,
    ) -> bool:
        """
        Delete a relationship (using Neptune's native ~id).

        Args:
            rel_id: Relationship ID (Neptune's ~id value)
            **options: Additional options

        Returns:
            True if deleted successfully
        """
        try:
            self._ensure_connected()

            # Use id(r) function to match Neptune's native ~id
            query = "MATCH ()-[r]->() WHERE id(r) = $id DELETE r"

            self._run_query(query, {"id": str(rel_id)})
            return True

        except Exception as e:
            raise ProcessingError(f"Failed to delete relationship: {str(e)}") from e

    def execute_query(
        self,
        query: str,
        parameters: Optional[Dict[str, Any]] = None,
        **options,
    ) -> Dict[str, Any]:
        """
        Execute an OpenCypher query.

        Args:
            query: OpenCypher query string
            parameters: Query parameters
            **options: Additional options

        Returns:
            Query results
        """
        tracking_id = self.progress_tracker.start_tracking(
            module="graph_store",
            submodule="AmazonNeptuneStore",
            message="Executing OpenCypher query",
        )

        try:
            self._ensure_connected()

            records = self._run_query(query, parameters or {})
            parsed = self._parse_results(records)

            self.progress_tracker.stop_tracking(
                tracking_id,
                status="completed",
                message=f"Query returned {len(parsed)} records",
            )

            return {
                "success": True,
                "records": parsed,
                "keys": list(parsed[0].keys()) if parsed else [],
                "metadata": {"query": query},
            }

        except Exception as e:
            self.progress_tracker.stop_tracking(
                tracking_id, status="failed", message=str(e)
            )
            raise ProcessingError(f"Query execution failed: {str(e)}") from e

    def get_neighbors(
        self,
        node_id: Union[int, str],
        rel_type: Optional[str] = None,
        direction: str = "both",
        depth: int = 1,
        **options,
    ) -> List[Dict[str, Any]]:
        """
        Get neighboring nodes (using Neptune's native ~id).

        Args:
            node_id: Starting node ID (Neptune's ~id value)
            rel_type: Filter by relationship type
            direction: Direction ("in", "out", "both")
            depth: Traversal depth
            **options: Additional options

        Returns:
            List of neighboring nodes
        """
        try:
            self._ensure_connected()

            type_filter = f":{sanitize_identifier(rel_type, 'relationship type')}" if rel_type else ""
            depth = int(depth)

            if direction == "out":
                pattern = f"-[r{type_filter}*1..{depth}]->"
            elif direction == "in":
                pattern = f"<-[r{type_filter}*1..{depth}]-"
            else:
                pattern = f"-[r{type_filter}*1..{depth}]-"

            # Include id(neighbor) to get the ~id we set when creating node
            query = (
                f"MATCH (start){pattern}(neighbor) "
                f"WHERE id(start) = $node_id "
                f"RETURN DISTINCT neighbor, labels(neighbor) as labels, "
                f"id(neighbor) as neighbor_id"
            )

            records = self._run_query(query, {"node_id": str(node_id)})
            parsed = self._parse_results(records)

            neighbors = []
            for record in parsed:
                node = record.get("neighbor", {})
                # Use neighbor_id from query (the ~id we set) as primary ID
                neighbor_id = record.get("neighbor_id")
                neighbors.append(
                    {
                        "id": neighbor_id
                        or (node.get("id") if isinstance(node, dict) else None),
                        "labels": record.get("labels", []),
                        "properties": (
                            node.get("properties", {})
                            if isinstance(node, dict)
                            else node if isinstance(node, dict) else {}
                        ),
                    }
                )

            return neighbors

        except Exception as e:
            raise ProcessingError(f"Failed to get neighbors: {str(e)}") from e

    def shortest_path(
        self,
        start_node_id: Union[int, str],
        end_node_id: Union[int, str],
        rel_type: Optional[str] = None,
        max_depth: int = 10,
        **options,
    ) -> Optional[Dict[str, Any]]:
        """
        Find shortest path between two nodes (using Neptune's native ~id).

        Note: Neptune OpenCypher has limited support for shortestPath syntax.
        This implementation uses a BFS-style approach compatible with Neptune.

        Args:
            start_node_id: Starting node ID (Neptune's ~id value)
            end_node_id: Ending node ID (Neptune's ~id value)
            rel_type: Filter by relationship type
            max_depth: Maximum path length
            **options: Additional options

        Returns:
            Shortest path information or None if not found
        """
        try:
            self._ensure_connected()

            type_filter = f":{sanitize_identifier(rel_type, 'relationship type')}" if rel_type else ""

            # Neptune doesn't support named path patterns in shortestPath
            # Use iterative depth search instead
            for depth in range(1, max_depth + 1):
                # Include id(start) and id(end) to get ~id we set
                query = (
                    f"MATCH (start)-[r{type_filter}*{depth}]-(end) "
                    f"WHERE id(start) = $start_id AND id(end) = $end_id "
                    f"RETURN start, end, {depth} as length, "
                    f"id(start) as start_node_id, id(end) as end_node_id, "
                    f"labels(start) as start_labels, "
                    f"labels(end) as end_labels LIMIT 1"
                )

                records = self._run_query(
                    query,
                    {
                        "start_id": str(start_node_id),
                        "end_id": str(end_node_id),
                    },
                )
                parsed = self._parse_results(records)

                if parsed:
                    record = parsed[0]
                    start_node = record.get("start", {})
                    end_node = record.get("end", {})

                    # Use the ~id from id() function as primary ID
                    return {
                        "length": depth,
                        "start_node": {
                            "id": record.get("start_node_id")
                            or (
                                start_node.get("id")
                                if isinstance(start_node, dict)
                                else None
                            ),
                            "labels": record.get("start_labels", []),
                            "properties": (
                                start_node.get("properties", {})
                                if isinstance(start_node, dict)
                                else start_node if isinstance(start_node, dict) else {}
                            ),
                        },
                        "end_node": {
                            "id": record.get("end_node_id")
                            or (
                                end_node.get("id")
                                if isinstance(end_node, dict)
                                else None
                            ),
                            "labels": record.get("end_labels", []),
                            "properties": (
                                end_node.get("properties", {})
                                if isinstance(end_node, dict)
                                else end_node if isinstance(end_node, dict) else {}
                            ),
                        },
                        "found": True,
                    }

            # No path found within max_depth
            return None

        except Exception as e:
            self.logger.warning(f"Shortest path search failed: {str(e)}")
            return None

    def create_index(
        self,
        label: str,
        property_name: str,
        index_type: str = "btree",
        **options,
    ) -> bool:
        """
        Create an index on a property.

        Note: Neptune manages indexes differently than Neo4j.
        This logs a message about Neptune's index management.

        Args:
            label: Node label
            property_name: Property to index
            index_type: Index type
            **options: Additional options

        Returns:
            True (acknowledgement)
        """
        self.logger.info(
            f"Index creation for {label}.{property_name}: "
            "Neptune manages indexes automatically. Consider using Neptune's "
            "management console or AWS CLI for advanced index management."
        )
        return True

    def get_stats(self) -> Dict[str, Any]:
        """Get database statistics."""
        try:
            self._ensure_connected()

            stats = {}

            # Node count
            records = self._run_query("MATCH (n) RETURN count(n) as count")
            stats["node_count"] = records[0]["count"] if records else 0

            # Relationship count
            records = self._run_query("MATCH ()-[r]->() RETURN count(r) as count")
            stats["relationship_count"] = records[0]["count"] if records else 0

            stats["backend"] = "amazon_neptune"
            stats["endpoint"] = self.endpoint
            stats["protocol"] = "bolt"

            return stats

        except Exception as e:
            self.logger.warning(f"Failed to get stats: {str(e)}")
            return {"status": "error", "message": str(e)}

    def get_status(self) -> Dict[str, Any]:
        """
        Get Neptune connection status.

        Returns:
            Status information
        """
        return {
            "backend": "amazon_neptune",
            "endpoint": self.endpoint,
            "port": self.port,
            "region": self.region,
            "iam_auth": self.iam_auth,
            "use_ssl": self.use_ssl,
            "protocol": "bolt",
            "connected": self._connected,
        }

    def update_auth_context(self, context) -> None:
        """
        Update the authentication context for logging purposes.

        This is useful in serverless environments to update logging context.

        Args:
            context: Execution context object
        """
        if self._auth_manager:
            self._auth_manager.update_context(context)

    def refresh_auth_token(self) -> None:
        """
        Force refresh of the authentication token.

        Useful when you know the token is about to expire or has expired.
        """
        if self._auth_manager:
            self._auth_manager.refresh_token()
