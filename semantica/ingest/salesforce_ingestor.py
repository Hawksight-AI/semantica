"""
Salesforce Ingestion Module

This module provides Salesforce CRM data ingestion capabilities for the
Semantica framework, enabling extraction of records from Salesforce
sObjects (standard and custom) via the Salesforce REST API.

Key Features:
    - Username/password/security-token authentication
    - Session-ID + instance-URL authentication (for pre-existing OAuth sessions)
    - Sandbox and production domain support
    - Configurable API version
    - SOQL-based and sObject-based record ingestion
    - Automatic nextRecordsUrl pagination
    - sObject schema discovery
    - Progress tracking and structured error handling
    - Connection management with context-manager support

Main Classes:
    - SalesforceConnector: Manages the simple-salesforce client lifecycle
    - SalesforceData: Dataclass representing ingested Salesforce records
    - SalesforceIngestor: Orchestrates ingestion operations

Optional Dependency:
    Install via the ``db-salesforce`` extra::

        pip install "semantica[db-salesforce]"

    or directly::

        pip install simple-salesforce>=1.12.0

Example Usage::

    >>> import os
    >>> from semantica.ingest import SalesforceIngestor
    >>> ingestor = SalesforceIngestor(
    ...     username=os.getenv("SALESFORCE_USERNAME"),
    ...     password=os.getenv("SALESFORCE_PASSWORD"),
    ...     security_token=os.getenv("SALESFORCE_SECURITY_TOKEN"),
    ...     domain="login",        # "test" for sandbox
    ... )

Author: Semantica Contributors
License: MIT
"""

import os
import re
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Dict, List, Optional, Tuple

from ..utils.exceptions import ProcessingError, ValidationError
from ..utils.logging import get_logger
from ..utils.progress_tracker import get_progress_tracker

# ---------------------------------------------------------------------------
# Optional-dependency guard — mirrors the pattern in snowflake_ingestor and
# databricks_ingestor exactly.  The module always imports cleanly; the guard
# fires at instantiation time via the SALESFORCE_AVAILABLE check in __init__.
# ---------------------------------------------------------------------------
try:
    from simple_salesforce import Salesforce as _SimpleSalesforce
    from simple_salesforce.exceptions import (
        SalesforceAuthenticationFailed as _SalesforceAuthenticationFailed,
        SalesforceError as _SalesforceError,
        SalesforceExpiredSession as _SalesforceExpiredSession,
        SalesforceGeneralError as _SalesforceGeneralError,
        SalesforceMalformedRequest as _SalesforceMalformedRequest,
        SalesforceRefusedRequest as _SalesforceRefusedRequest,
        SalesforceResourceNotFound as _SalesforceResourceNotFound,
    )

    SALESFORCE_AVAILABLE = True
except (ImportError, OSError):
    _SimpleSalesforce = None  # type: ignore[assignment,misc]
    _SalesforceAuthenticationFailed = None  # type: ignore[assignment,misc]
    _SalesforceError = None  # type: ignore[assignment,misc]
    _SalesforceExpiredSession = None  # type: ignore[assignment,misc]
    _SalesforceGeneralError = None  # type: ignore[assignment,misc]
    _SalesforceMalformedRequest = None  # type: ignore[assignment,misc]
    _SalesforceRefusedRequest = None  # type: ignore[assignment,misc]
    _SalesforceResourceNotFound = None  # type: ignore[assignment,misc]
    SALESFORCE_AVAILABLE = False


# ---------------------------------------------------------------------------
# SOQL validation helpers
# ---------------------------------------------------------------------------

# sObject API names: start with a letter, contain letters/digits/underscores,
# and optionally end with a Salesforce namespace suffix (__c, __mdt, __e,
# __b, __x, __ka, __kav, __r).  The __r suffix is used for relationship
# traversal fields, not objects, but we accept it here so callers who pass
# a field-path component don't hit a false-positive error.
_SOBJECT_RE = re.compile(
    r"^[A-Za-z][A-Za-z0-9_]*(__c|__mdt|__e|__b|__x|__ka|__kav|__r)?$"
)

# Field API names: start with a letter, contain letters/digits/underscores.
# Dot-notation for relationship traversal (e.g. ``Owner.Name``) is allowed;
# each component must individually match the base pattern.
_FIELD_COMPONENT_RE = re.compile(r"^[A-Za-z][A-Za-z0-9_]*(__c|__r)?$")

# ORDER BY: one or more comma-separated ``FieldName [ASC|DESC] [NULLS FIRST|LAST]``
# clauses.  Relationship dot-notation is supported (e.g. ``Owner.Name ASC``).
_SAFE_ORDER_RE = re.compile(
    r"^[A-Za-z][A-Za-z0-9_.]*(\s+(ASC|DESC))?(\s+NULLS\s+(FIRST|LAST))?"
    r"(\s*,\s*[A-Za-z][A-Za-z0-9_.]*(\s+(ASC|DESC))?(\s+NULLS\s+(FIRST|LAST))?)*$",
    re.IGNORECASE,
)

# WHERE-clause fragment blocklist — reused from db_ingestor's approach.
# SOQL has no UNION, INSERT, DROP, etc., but we still block statement
# separators, comment markers, and SQL injection primitives defensively.
_SOQL_WHERE_BLOCKLIST_RE = re.compile(
    r";|--|/\*|\*/|\bunion\b|\binsert\b|\bupdate\b|\bdelete\b|\bdrop\b|"
    r"\balter\b|\bcreate\b|\bexec\b|\bexecute\b|\bgrant\b|\brevoke\b",
    re.IGNORECASE,
)

# SOQL single-quoted string literals — mask before blocklist check so a
# value like ``status = 'union'`` doesn't false-positive.
# SOQL escapes a single quote by doubling it (``''``), not with a backslash,
# so the pattern mirrors ``db_ingestor._SQL_STRING_LITERAL_RE`` exactly.
_SOQL_STRING_LITERAL_RE = re.compile(r"'(?:[^']|'')*'")


def _mask_soql_literals(fragment: str) -> str:
    """Replace quoted-literal contents with ``?`` so blocklist only sees syntax."""
    return _SOQL_STRING_LITERAL_RE.sub(
        lambda m: "'" + "?" * (len(m.group(0)) - 2) + "'", fragment
    )


def _validate_sobject_name(name: str) -> str:
    """Validate a Salesforce sObject API name used in SOQL interpolation.

    Args:
        name: The sObject API name to validate.

    Returns:
        The unchanged name if valid.

    Raises:
        ValidationError: If *name* contains characters that could escape
            a SOQL identifier context.
    """
    if not isinstance(name, str) or not _SOBJECT_RE.match(name):
        raise ValidationError(
            f"Invalid Salesforce sObject name: {name!r}. "
            "Must start with a letter, contain only letters, digits, and "
            "underscores, and may optionally end with a Salesforce suffix "
            "such as __c, __mdt, or __e."
        )
    return name


def _validate_field_name(name: str) -> str:
    """Validate a single Salesforce field API name (dot-notation allowed).

    Args:
        name: Field name or dot-separated relationship path, e.g. ``Owner.Name``.

    Returns:
        The unchanged name if valid.

    Raises:
        ValidationError: If any component is not a valid identifier.
    """
    if not isinstance(name, str) or not name:
        raise ValidationError(f"Field name must be a non-empty string; got {name!r}.")
    for component in name.split("."):
        if not _FIELD_COMPONENT_RE.match(component):
            raise ValidationError(
                f"Invalid Salesforce field name component: {component!r} "
                f"(in {name!r}). Each component must start with a letter "
                "and contain only letters, digits, and underscores."
            )
    return name


def _validate_soql_where(fragment: str) -> str:
    """Block known-dangerous constructs in a SOQL WHERE fragment.

    This is a blocklist, not a grammar parser.  It catches the common SQL
    injection primitives (statement separators, comment sequences, and DML /
    DDL keywords) without attempting to prove the fragment is fully safe.
    Callers should treat ``where`` as trusted/operator input and not pass
    raw end-user text here.

    Args:
        fragment: The raw WHERE clause fragment (without the ``WHERE`` keyword).

    Returns:
        The unchanged fragment if no blocked construct is found.

    Raises:
        ValidationError: If a blocked construct is detected.
    """
    if not isinstance(fragment, str):
        raise ValidationError("WHERE clause must be a string.")
    masked = _mask_soql_literals(fragment)
    if _SOQL_WHERE_BLOCKLIST_RE.search(masked):
        raise ValidationError(
            f"WHERE clause contains a disallowed keyword or character: "
            f"{fragment!r}. Do not pass untrusted user input as a WHERE clause."
        )
    return fragment


def _validate_order_by(fragment: str) -> str:
    """Validate a SOQL ORDER BY clause fragment.

    Args:
        fragment: The ORDER BY expression (without the ``ORDER BY`` keyword),
            e.g. ``Name ASC, CreatedDate DESC NULLS LAST``.

    Returns:
        The unchanged fragment if valid.

    Raises:
        ValidationError: If the fragment contains unexpected characters or
            keywords.
    """
    if not isinstance(fragment, str) or not fragment.strip():
        raise ValidationError("ORDER BY clause must be a non-empty string.")
    if not _SAFE_ORDER_RE.match(fragment.strip()):
        raise ValidationError(
            f"Invalid ORDER BY clause: {fragment!r}. "
            "Only field names (with optional dot-notation), ASC/DESC, and "
            "NULLS FIRST/LAST are permitted."
        )
    return fragment


# ---------------------------------------------------------------------------
# SalesforceData
# ---------------------------------------------------------------------------

@dataclass
class SalesforceData:
    """Records ingested from a Salesforce sObject or SOQL query.

    Attributes:
        data: List of cleaned record dictionaries.  The ``attributes`` key
            that ``simple-salesforce`` injects into every raw record has been
            stripped, along with any ``attributes`` keys on nested relationship
            sub-objects.
        row_count: Number of records in ``data`` — i.e. ``len(data)``.  When
            a *limit* was applied this is the number of records actually
            returned, not the total matching the query.  See ``total_size``
            for the unfiltered count.
        columns: Ordered list of field names present across all records in
            ``data``.
        sobject: Salesforce sObject API name (e.g. ``"Account"``,
            ``"My_Custom__c"``), or ``None`` for raw SOQL queries that span
            multiple objects.
        query: The SOQL query string that produced these records, or ``None``
            when not applicable.
        instance_url: Salesforce instance base URL used for the ingestion
            (e.g. ``"https://myorg.my.salesforce.com"``).
        total_size: The ``totalSize`` field from the Salesforce REST API
            response — the total number of records matching the query
            *before* any client-side ``limit`` or pagination truncation.
            ``None`` when not available (e.g. for schema-only calls).
            To check whether all records were retrieved: compare
            ``row_count == total_size``.
        metadata: Arbitrary extra metadata.  Ingestion methods populate
            ``metadata["query"]`` with the SOQL string used (defaults to
            ``{}``).
        ingested_at: Timestamp recorded when this object was created.
    """

    data: List[Dict[str, Any]]
    row_count: int
    columns: List[str]
    sobject: Optional[str] = None
    query: Optional[str] = None
    instance_url: Optional[str] = None
    total_size: Optional[int] = None
    metadata: Dict[str, Any] = field(default_factory=dict)
    ingested_at: datetime = field(default_factory=datetime.now)


# ---------------------------------------------------------------------------
# SalesforceConnector
# ---------------------------------------------------------------------------

class SalesforceConnector:
    """Manages the ``simple-salesforce`` client lifecycle.

    Responsibilities:

    * Reads credentials from constructor arguments, falling back to
      environment variables in the same way as ``SnowflakeConnector`` and
      ``DatabricksConnector``.
    * Validates that a usable authentication path is configured *before* any
      network call is made.
    * Exposes :py:meth:`connect`, :py:meth:`disconnect`, and
      :py:meth:`test_connection` so the ingestor (and tests) can control the
      client lifecycle explicitly.
    * **Connection reuse**: if a client is already open :py:meth:`connect`
      returns it immediately, preventing redundant authentication calls and
      resource leaks when the ingestor is used as a context manager.

    Supported Authentication Modes
    --------------------------------
    **Username / Password / Security Token** (standard server-side flow)::

        import os
        from semantica.ingest import SalesforceConnector

        connector = SalesforceConnector(
            username=os.getenv("SALESFORCE_USERNAME"),
            password=os.getenv("SALESFORCE_PASSWORD"),
            security_token=os.getenv("SALESFORCE_SECURITY_TOKEN"),
            domain="login",     # or "test" for sandbox
        )

    **Session ID + Instance URL** (pre-authenticated OAuth session)::

        import os
        from semantica.ingest import SalesforceConnector

        SalesforceConnector(
            session_id=os.getenv("SALESFORCE_SESSION_ID"),
            instance_url=os.getenv("SALESFORCE_INSTANCE_URL"),
        )

    .. note::
        **JWT Bearer authentication** (``consumer_key`` + ``privatekey`` /
        ``privatekey_file``) is supported by ``simple-salesforce`` but is not
        implemented in this connector.  It requires a separate key-management
        flow and will be added in a later stage when the full lifecycle
        (key loading, passphrase handling, token refresh) can be validated
        end-to-end.  Until then, pass ``session_id`` + ``instance_url`` if
        you already hold a JWT-derived token from your own auth layer.

    Environment Variables
    ----------------------
    Every constructor parameter has an environment-variable fallback:

    * ``SALESFORCE_USERNAME``
    * ``SALESFORCE_PASSWORD``
    * ``SALESFORCE_SECURITY_TOKEN``
    * ``SALESFORCE_DOMAIN``      (default: ``"login"``)
    * ``SALESFORCE_INSTANCE_URL``
    * ``SALESFORCE_SESSION_ID``
    * ``SALESFORCE_API_VERSION``

    Raises:
        ImportError: If ``simple-salesforce`` is not installed.
        ValidationError: If no usable credential set is provided.
    """

    def __init__(
        self,
        username: Optional[str] = None,
        password: Optional[str] = None,
        security_token: Optional[str] = None,
        domain: Optional[str] = None,
        instance_url: Optional[str] = None,
        session_id: Optional[str] = None,
        api_version: Optional[str] = None,
        **config: Any,
    ) -> None:
        """Initialise the connector and validate credentials.

        Args:
            username: Salesforce login username.
            password: Salesforce login password.
            security_token: Salesforce security token appended to the password
                during SOAP authentication.
            domain: Login domain — ``"login"`` for production (default),
                ``"test"`` for sandbox, or a custom My Domain value.
            instance_url: Full Salesforce instance URL for session-based auth
                (e.g. ``"https://myorg.my.salesforce.com"``).
            session_id: Pre-existing Salesforce session / OAuth access token.
            api_version: Salesforce REST API version string, e.g. ``"59.0"``.
                Defaults to ``simple-salesforce``'s built-in default (currently
                ``"59.0"``).
            **config: Extra keyword arguments forwarded verbatim to
                ``simple_salesforce.Salesforce()`` (e.g. ``proxies``,
                ``session``).

        Raises:
            ImportError: If ``simple-salesforce`` is not installed.
            ValidationError: If the provided credentials are insufficient for
                any supported authentication mode.
        """
        if not SALESFORCE_AVAILABLE:
            raise ImportError(
                "simple-salesforce is required for SalesforceConnector. "
                'Install it with: pip install "semantica[db-salesforce]" '
                "or: pip install simple-salesforce>=1.12.0"
            )

        self.logger = get_logger("salesforce_connector")

        # ------------------------------------------------------------------
        # Resolve credentials: explicit args take precedence over env vars.
        # Passwords, tokens, and session IDs are stored on the instance so
        # they can be forwarded to simple-salesforce on connect().  They are
        # NEVER included in log messages or exception messages raised here.
        # ------------------------------------------------------------------
        self.username: Optional[str] = username or os.getenv("SALESFORCE_USERNAME")
        self._password: Optional[str] = password or os.getenv("SALESFORCE_PASSWORD")
        self._security_token: Optional[str] = (
            security_token or os.getenv("SALESFORCE_SECURITY_TOKEN")
        )
        self.domain: str = (
            domain or os.getenv("SALESFORCE_DOMAIN") or "login"
        )
        self.instance_url: Optional[str] = (
            instance_url or os.getenv("SALESFORCE_INSTANCE_URL")
        )
        self._session_id: Optional[str] = (
            session_id or os.getenv("SALESFORCE_SESSION_ID")
        )
        self.api_version: Optional[str] = (
            api_version or os.getenv("SALESFORCE_API_VERSION")
        )

        # Extra kwargs forwarded to simple-salesforce (e.g. proxies, session)
        self._extra_config: Dict[str, Any] = config

        # Internal client reference — None until connect() is called.
        self._client: Optional[Any] = None

        # Validate that at least one viable auth path is fully configured.
        self._validate_auth()

        # Safe to log: username (not a secret) and domain.
        self.logger.debug(
            "Salesforce connector initialised: username=%s domain=%s",
            self.username or "<session-id auth>",
            self.domain,
        )

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _validate_auth(self) -> None:
        """Raise :class:`~semantica.utils.exceptions.ValidationError` if no
        usable authentication path is present.

        Two valid modes are recognised:

        1. **Username / password / security token** — all three required.
        2. **Session ID + instance URL** — both required.

        Raises:
            ValidationError: When neither mode has all required fields.
        """
        has_upw = bool(
            self.username and self._password and self._security_token
        )
        has_session = bool(self._session_id and self.instance_url)

        if not has_upw and not has_session:
            raise ValidationError(
                "Salesforce authentication is required. Provide either:\n"
                "  (a) username + password + security_token "
                "(env: SALESFORCE_USERNAME / SALESFORCE_PASSWORD / "
                "SALESFORCE_SECURITY_TOKEN), or\n"
                "  (b) session_id + instance_url "
                "(env: SALESFORCE_SESSION_ID / SALESFORCE_INSTANCE_URL)."
            )

    def _build_client_kwargs(self) -> Dict[str, Any]:
        """Assemble the keyword arguments for ``simple_salesforce.Salesforce()``.

        Credentials are passed to the underlying library here and nowhere
        else.  They are not logged.

        Returns:
            Keyword argument dictionary ready to pass to
            ``simple_salesforce.Salesforce(**kwargs)``.
        """
        kwargs: Dict[str, Any] = {}

        # API version maps to simple-salesforce's ``version`` parameter.
        if self.api_version:
            kwargs["version"] = self.api_version

        if self._session_id and self.instance_url:
            # Direct / pre-authenticated session — no network call during init.
            kwargs["session_id"] = self._session_id
            kwargs["instance_url"] = self.instance_url
        else:
            # Username + password + security token (SOAP login).
            kwargs["username"] = self.username
            kwargs["password"] = self._password
            kwargs["security_token"] = self._security_token
            kwargs["domain"] = self.domain

        # Forward any extra config (proxies, custom requests.Session, etc.)
        kwargs.update(self._extra_config)
        return kwargs

    # ------------------------------------------------------------------
    # Public properties
    # ------------------------------------------------------------------

    @property
    def client(self) -> Optional[Any]:
        """The active ``simple_salesforce.Salesforce`` instance, or ``None``."""
        return self._client

    @property
    def connection(self) -> Optional[Any]:
        """Alias for :attr:`client` — used by tests that follow the
        Databricks/Snowflake ``connector.connection`` naming convention."""
        return self._client

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------

    def connect(self) -> Any:
        """Create and return the ``simple_salesforce.Salesforce`` client.

        If a client is already open (e.g. because the ingestor is being used
        as a context manager) the existing instance is returned without
        re-authenticating, preventing duplicate SOAP/OAuth round-trips and
        resource leaks.

        .. important::
            For username/password/security-token authentication,
            ``simple-salesforce`` performs a live SOAP login call inside its
            constructor.  Any network or authentication failure will therefore
            be raised here, not at ``SalesforceConnector.__init__`` time.

        Returns:
            The ``simple_salesforce.Salesforce`` client instance.

        Raises:
            ProcessingError: If the connection attempt fails — wraps
                ``SalesforceAuthenticationFailed``, ``SalesforceError``,
                ``TypeError`` (invalid credential combination), or any
                other unexpected exception, preserving the original as the
                chained cause.
        """
        if self._client is not None:
            return self._client

        try:
            kwargs = self._build_client_kwargs()
            self._client = _SimpleSalesforce(**kwargs)

            # Resolve a clean instance URL from the connected client so that
            # SalesforceData and callers can reference it without re-reading
            # config.  simple-salesforce stores the hostname in sf_instance;
            # we reconstruct the full HTTPS URL from it.
            if self.instance_url is None:
                sf_instance = getattr(self._client, "sf_instance", None)
                if sf_instance:
                    self.instance_url = f"https://{sf_instance}"

            # Log only non-sensitive information.
            self.logger.info(
                "Connected to Salesforce: instance=%s",
                self.instance_url or "<unknown>",
            )
            return self._client

        except (_SalesforceAuthenticationFailed,) if SALESFORCE_AVAILABLE else ():
            # Authentication failure — safe to surface the error code /
            # server message; the password is never included in SF's response.
            raise ProcessingError(
                "Salesforce authentication failed. "
                "Check username, password, security token, and domain."
            ) from None  # suppress the original — it may contain the username

        except (_SalesforceError,) if SALESFORCE_AVAILABLE else ():
            # Other Salesforce API errors during initial connection.
            raise ProcessingError(
                "Salesforce connection error. "
                "Verify the instance URL and API access permissions."
            ) from None

        except TypeError as exc:
            # simple-salesforce raises TypeError when no valid credential
            # combination is recognised — should not happen if _validate_auth
            # passed, but guard defensively.
            raise ProcessingError(
                "Salesforce connection failed: invalid credential combination."
            ) from exc

        except Exception as exc:
            # Unexpected error (network timeout, DNS failure, etc.).
            # Log without credentials; re-raise with a generic message.
            self.logger.error(
                "Unexpected error connecting to Salesforce: %s",
                type(exc).__name__,
            )
            raise ProcessingError(
                f"Failed to connect to Salesforce: {type(exc).__name__}"
            ) from exc

    def disconnect(self) -> None:
        """Release the Salesforce client and its underlying requests session.

        ``simple-salesforce`` uses a ``requests.Session`` internally.  Setting
        the reference to ``None`` allows the session to be garbage-collected.
        There is no "logout" endpoint in the Salesforce REST API for
        username/password flows; session-ID tokens can be revoked server-side
        separately if required.
        """
        if self._client is not None:
            # Release the requests.Session inside the SF client.
            session = getattr(self._client, "session", None)
            if session is not None:
                try:
                    session.close()
                except Exception:  # noqa: BLE001
                    pass
            self._client = None
            self.logger.info("Disconnected from Salesforce.")

    def test_connection(self) -> bool:
        """Verify connectivity by authenticating and calling ``/limits/``.

        Opens a transient connection (or reuses an existing one), calls the
        lightweight ``limits`` endpoint that requires valid authentication but
        reads no CRM data, then closes the connection if it was opened here.

        Returns:
            ``True`` if authentication and the API call succeed, ``False``
            for any failure (auth error, network error, etc.).
        """
        already_connected = self._client is not None
        try:
            client = self.connect()
            # ``limits()`` is a cheap, read-only call that proves the
            # session is valid without touching any CRM data.
            client.limits()
            return True
        except Exception as exc:
            # Log the exception type only — no credentials in the message.
            self.logger.debug(
                "Salesforce connection test failed: %s", type(exc).__name__
            )
            return False
        finally:
            # Close only if we opened the connection in this call.
            if not already_connected:
                self.disconnect()


# ---------------------------------------------------------------------------
# SalesforceIngestor
# ---------------------------------------------------------------------------

class SalesforceIngestor:
    """Salesforce CRM data ingestor for the Semantica framework.

    Wraps :class:`SalesforceConnector` and will provide high-level methods
    for pulling records from sObjects and SOQL queries into the Semantica
    ingestion pipeline.

    Full ingestion methods (``ingest_sobject``, ``ingest_query``,
    ``list_sobjects``, ``get_sobject_schema``, ``export_as_documents``) are
    implemented in this class.

    Args:
        username: Salesforce login username.
        password: Salesforce login password.
        security_token: Salesforce security token.
        domain: Login domain — ``"login"`` (production, default) or ``"test"``
            (sandbox).
        instance_url: Instance URL for session-based authentication.
        session_id: Pre-existing Salesforce session / access token.
        api_version: REST API version string (e.g. ``"59.0"``).
        config: Optional extra configuration forwarded to the connector.
        **kwargs: Additional keyword arguments merged into ``config``.

    Example::

        import os
        from semantica.ingest import SalesforceIngestor

        # Standalone
        ingestor = SalesforceIngestor(
            username=os.getenv("SALESFORCE_USERNAME"),
            password=os.getenv("SALESFORCE_PASSWORD"),
            security_token=os.getenv("SALESFORCE_SECURITY_TOKEN"),
        )

        # Context manager — preferred for long-running jobs
        with SalesforceIngestor(
            username=os.getenv("SALESFORCE_USERNAME"),
            password=os.getenv("SALESFORCE_PASSWORD"),
            security_token=os.getenv("SALESFORCE_SECURITY_TOKEN"),
            domain="test",      # sandbox
        ) as sf:
            pass  # ingest_sobject() etc. available in Stage 2
    """

    def __init__(
        self,
        username: Optional[str] = None,
        password: Optional[str] = None,
        security_token: Optional[str] = None,
        domain: Optional[str] = None,
        instance_url: Optional[str] = None,
        session_id: Optional[str] = None,
        api_version: Optional[str] = None,
        config: Optional[Dict[str, Any]] = None,
        **kwargs: Any,
    ) -> None:
        self.logger = get_logger("salesforce_ingestor")

        self.config: Dict[str, Any] = config or {}
        self.config.update(kwargs)

        # Instantiate the connector — raises ImportError if simple-salesforce
        # is absent, or ValidationError if credentials are incomplete.
        self.connector = SalesforceConnector(
            username=username,
            password=password,
            security_token=security_token,
            domain=domain,
            instance_url=instance_url,
            session_id=session_id,
            api_version=api_version,
            **self.config,
        )

        # Progress tracker — consistent with all other ingestors.
        self.progress_tracker = get_progress_tracker()
        if not self.progress_tracker.enabled:
            self.progress_tracker.enabled = True

        self.logger.debug("Salesforce ingestor initialised.")

    # ------------------------------------------------------------------
    # Context-manager support
    # ------------------------------------------------------------------

    def __enter__(self) -> "SalesforceIngestor":
        """Open the Salesforce connection on context entry."""
        self.connector.connect()
        return self

    def __exit__(
        self,
        exc_type: Any,
        exc_val: Any,
        exc_tb: Any,
    ) -> None:
        """Close the Salesforce connection on context exit."""
        self.close()

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------

    def close(self) -> None:
        """Disconnect from Salesforce and release the client."""
        self.connector.disconnect()

    # ------------------------------------------------------------------
    # Ingestion methods
    # ------------------------------------------------------------------

    def ingest_sobject(
        self,
        sobject_name: str,
        fields: Optional[List[str]] = None,
        where: Optional[str] = None,
        order_by: Optional[str] = None,
        limit: Optional[int] = None,
        **options: Any,
    ) -> "SalesforceData":
        """Fetch records from a Salesforce sObject via SOQL.

        Builds a ``SELECT ... FROM <sobject> [WHERE ...] [ORDER BY ...]
        [LIMIT ...]`` query, executes it, and follows all ``nextRecordsUrl``
        pagination links until every matching record (up to *limit*) has been
        collected.

        Args:
            sobject_name: Salesforce sObject API name, e.g. ``"Account"``,
                ``"Contact"``, ``"My_Custom__c"``.
            fields: Field API names to retrieve.  Dot-notation for relationship
                traversal is supported (e.g. ``["Id", "Name", "Owner.Name"]``).
                When ``None``, all fields from the object's ``describe()``
                response are used (one additional API call).
            where: SOQL ``WHERE`` clause fragment without the ``WHERE`` keyword,
                e.g. ``"Type = 'Customer' AND AnnualRevenue > 1000000"``.
                **Trusted input only** — do not pass raw end-user text here.
            order_by: SOQL ``ORDER BY`` clause fragment without the keyword,
                e.g. ``"Name ASC, CreatedDate DESC NULLS LAST"``.
                **Trusted input only.**
            limit: Maximum number of records to return across all pages.  When
                ``None``, all matching records are returned (use with care on
                large objects).
            **options: Reserved for future use.

        Returns:
            :class:`SalesforceData` with ``data``, ``row_count``, ``columns``,
            ``sobject``, ``query``, ``instance_url``, and ``total_size``
            populated.

        Raises:
            ValidationError: If *sobject_name*, any field name, *where*, or
                *order_by* fails the injection-safety check.
            ProcessingError: If the Salesforce API call fails.
        """
        _validate_sobject_name(sobject_name)

        # Validate WHERE and ORDER BY early — before connecting — so bad
        # input raises ValidationError without making any network call.
        if where:
            _validate_soql_where(where)
        if order_by:
            _validate_order_by(order_by)

        # limit=0 is a valid, well-defined request: "give me no records".
        # Returning immediately avoids generating an invalid ``LIMIT 0`` SOQL
        # clause (Salesforce requires LIMIT ≥ 1) and saves a round-trip.
        if limit is not None and limit <= 0:
            self.logger.debug(
                "ingest_sobject called with limit=%d — returning empty result.", limit
            )
            return SalesforceData(
                data=[],
                row_count=0,
                columns=[],
                sobject=sobject_name,
                instance_url=self.connector.instance_url,
                total_size=0,
            )

        tracking_id = self.progress_tracker.start_tracking(
            file=sobject_name,
            module="ingest",
            submodule="SalesforceIngestor",
            message=f"sObject: {sobject_name}",
        )

        try:
            already_connected = self.connector._client is not None
            client = self.connector.connect()

            try:
                # Resolve field list — fetch from describe() when not provided.
                if fields is None:
                    self.progress_tracker.update_tracking(
                        tracking_id, message="Fetching sObject schema…"
                    )
                    fields = self._get_all_field_names(client, sobject_name)
                else:
                    for f in fields:
                        _validate_field_name(f)

                soql = self._build_soql(
                    sobject_name=sobject_name,
                    fields=fields,
                    where=where,
                    order_by=order_by,
                    limit=limit,
                )

                self.progress_tracker.update_tracking(
                    tracking_id, message="Executing SOQL query…"
                )

                records, total_size = self._query_all(client, soql, limit)

                self.progress_tracker.update_tracking(
                    tracking_id, message=f"Fetched {len(records)} records…"
                )

                data = self._convert_rows(records)
                columns = list(dict.fromkeys(
                    k for row in data for k in row
                ))

                self.progress_tracker.stop_tracking(
                    tracking_id,
                    status="completed",
                    message=f"Ingested {len(data)} records",
                )
                self.logger.info(
                    "sObject ingestion completed: %s — %d record(s)",
                    sobject_name,
                    len(data),
                )

                return SalesforceData(
                    data=data,
                    row_count=len(data),
                    columns=columns,
                    sobject=sobject_name,
                    query=soql,
                    instance_url=self.connector.instance_url,
                    total_size=total_size,
                    metadata={"query": soql},
                )

            finally:
                if not already_connected:
                    self.connector.disconnect()

        except (ValidationError, ProcessingError):
            self.progress_tracker.stop_tracking(
                tracking_id, status="failed", message="Query failed"
            )
            raise
        except Exception as exc:
            self.progress_tracker.stop_tracking(
                tracking_id, status="failed", message=str(exc)
            )
            self.logger.error(
                "Failed to ingest sObject %s: %s", sobject_name, type(exc).__name__
            )
            raise ProcessingError(
                f"Failed to ingest Salesforce sObject '{sobject_name}': "
                f"{type(exc).__name__}"
            ) from exc

    def ingest_query(
        self,
        soql: str,
        batch_size: Optional[int] = None,  # noqa: ARG002 — reserved for future chunked progress
        **options: Any,
    ) -> "SalesforceData":
        """Execute a raw SOQL query and return all matching records.

        Follows ``nextRecordsUrl`` pagination automatically until ``done``
        is ``True`` or the result set is exhausted.

        Args:
            soql: A complete, valid SOQL query string, e.g.
                ``"SELECT Id, Name FROM Account WHERE Type = 'Customer'"``.
                The query is passed verbatim to the Salesforce REST API — the
                caller is responsible for correctness and safety.
            batch_size: Accepted for API compatibility but currently unused;
                Salesforce controls the page size.  Reserved for future
                progress-reporting granularity.
            **options: Reserved for future use.

        Returns:
            :class:`SalesforceData` with all records collected across pages.

        Raises:
            ProcessingError: If the Salesforce API call fails.
        """
        tracking_id = self.progress_tracker.start_tracking(
            file="soql_query",
            module="ingest",
            submodule="SalesforceIngestor",
            message="Executing SOQL query…",
        )

        try:
            already_connected = self.connector._client is not None
            client = self.connector.connect()

            try:
                records, total_size = self._query_all(client, soql, limit=None)

                self.progress_tracker.update_tracking(
                    tracking_id, message=f"Fetched {len(records)} records…"
                )

                data = self._convert_rows(records)
                columns = list(dict.fromkeys(
                    k for row in data for k in row
                ))

                self.progress_tracker.stop_tracking(
                    tracking_id,
                    status="completed",
                    message=f"Query returned {len(data)} records",
                )
                self.logger.info(
                    "SOQL query completed: %d record(s)", len(data)
                )

                return SalesforceData(
                    data=data,
                    row_count=len(data),
                    columns=columns,
                    query=soql,
                    instance_url=self.connector.instance_url,
                    total_size=total_size,
                    metadata={"query": soql},
                )

            finally:
                if not already_connected:
                    self.connector.disconnect()

        except (ValidationError, ProcessingError):
            self.progress_tracker.stop_tracking(
                tracking_id, status="failed", message="Query failed"
            )
            raise
        except Exception as exc:
            self.progress_tracker.stop_tracking(
                tracking_id, status="failed", message=str(exc)
            )
            self.logger.error(
                "Failed to execute SOQL query: %s", type(exc).__name__
            )
            raise ProcessingError(
                f"Failed to execute SOQL query: {type(exc).__name__}"
            ) from exc

    def list_sobjects(self) -> List[str]:
        """Return the API names of all accessible sObjects in the connected org.

        Uses ``sf.describe()`` (``GET /services/data/vXX.0/sobjects``) which
        returns global metadata for every sObject the current user can access.

        Returns:
            Sorted list of sObject API name strings (e.g.
            ``["Account", "Contact", "My_Custom__c", ...]``).

        Raises:
            ProcessingError: If the Salesforce API call fails.
        """
        try:
            already_connected = self.connector._client is not None
            client = self.connector.connect()

            try:
                result = client.describe()
                sobjects = [
                    obj["name"]
                    for obj in (result.get("sobjects") or [])
                    if obj.get("name")
                ]
                sobjects.sort()
                self.logger.debug(
                    "list_sobjects: found %d sObjects", len(sobjects)
                )
                return sobjects

            finally:
                if not already_connected:
                    self.connector.disconnect()

        except (ProcessingError, ValidationError):
            raise
        except Exception as exc:
            self.logger.error(
                "Failed to list sObjects: %s", type(exc).__name__
            )
            raise ProcessingError(
                f"Failed to list Salesforce sObjects: {type(exc).__name__}"
            ) from exc

    def get_sobject_schema(self, sobject_name: str) -> Dict[str, Any]:
        """Return field metadata for a Salesforce sObject.

        Calls ``sf.<SObjectName>.describe()`` (``GET
        /services/data/vXX.0/sobjects/<SObjectName>/describe``) and returns a
        normalised schema dictionary mirroring the structure used by
        ``SnowflakeIngestor.get_table_schema()``.

        Args:
            sobject_name: sObject API name to introspect, e.g. ``"Account"``.

        Returns:
            Dictionary with the following keys:

            ``"name"``
                sObject API name.
            ``"label"``
                Human-readable label.
            ``"fields"``
                List of field dictionaries, each with ``"name"``, ``"type"``,
                ``"label"``, ``"nillable"``, and ``"length"``.
            ``"queryable"``
                Whether the sObject supports SOQL queries.

        Raises:
            ValidationError: If *sobject_name* is not a valid identifier.
            ProcessingError: If the Salesforce API call fails.
        """
        _validate_sobject_name(sobject_name)

        try:
            already_connected = self.connector._client is not None
            client = self.connector.connect()

            try:
                sftype = getattr(client, sobject_name)
                result = sftype.describe()

                fields = [
                    {
                        "name": f.get("name"),
                        "type": f.get("type"),
                        "label": f.get("label"),
                        "nillable": f.get("nillable", True),
                        "length": f.get("length"),
                    }
                    for f in (result.get("fields") or [])
                ]

                self.logger.debug(
                    "get_sobject_schema: %s — %d field(s)",
                    sobject_name,
                    len(fields),
                )

                return {
                    "name": result.get("name", sobject_name),
                    "label": result.get("label", sobject_name),
                    "fields": fields,
                    "queryable": result.get("queryable", True),
                }

            finally:
                if not already_connected:
                    self.connector.disconnect()

        except (ValidationError, ProcessingError):
            raise
        except Exception as exc:
            self.logger.error(
                "Failed to get schema for %s: %s", sobject_name, type(exc).__name__
            )
            raise ProcessingError(
                f"Failed to get Salesforce sObject schema for "
                f"'{sobject_name}': {type(exc).__name__}"
            ) from exc

    def export_as_documents(
        self,
        data: "SalesforceData",
        id_field: str = "Id",
        text_fields: Optional[List[str]] = None,
    ) -> List[Dict[str, Any]]:
        """Convert :class:`SalesforceData` to the Semantica document format.

        Produces the same ``{"id", "text", "metadata"}`` shape used by
        ``SnowflakeIngestor.export_as_documents`` and
        ``DatabricksIngestor.export_as_documents``, making
        :class:`SalesforceData` directly usable with ``GraphBuilder``.

        Args:
            data: A :class:`SalesforceData` object returned by
                :py:meth:`ingest_sobject` or :py:meth:`ingest_query`.
            id_field: Record field to use as the document ``"id"``.  Defaults
                to ``"Id"`` — Salesforce's canonical 18-character record ID.
            text_fields: List of field names whose string values are
                space-joined to form the document ``"text"`` key.  When
                ``None``, all non-``None`` string-valued fields are joined.

        Returns:
            List of document dictionaries::

                [
                    {
                        "id": str,
                        "text": str,
                        "metadata": {
                            "source": "salesforce",
                            "sobject": "Account",
                            "instance_url": "https://myorg.salesforce.com",
                            "row_data": {...},
                        },
                    },
                    ...
                ]
        """
        documents = []

        for idx, row in enumerate(data.data):
            doc_id = str(row.get(id_field, idx))

            if text_fields:
                text_parts = [
                    str(row[f])
                    for f in text_fields
                    if f in row and row[f] is not None
                ]
            else:
                text_parts = [
                    str(v)
                    for v in row.values()
                    if isinstance(v, str) and v
                ]

            documents.append({
                "id": doc_id,
                "text": " ".join(text_parts),
                "metadata": {
                    "source": "salesforce",
                    "sobject": data.sobject,
                    "instance_url": data.instance_url,
                    "row_data": row,
                },
            })

        self.logger.debug(
            "export_as_documents: exported %d document(s)", len(documents)
        )
        return documents

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _build_soql(
        self,
        sobject_name: str,
        fields: List[str],
        where: Optional[str],
        order_by: Optional[str],
        limit: Optional[int],
    ) -> str:
        """Build a SOQL SELECT statement from validated components.

        All identifiers have already been validated by the caller.  This
        method only assembles the string — it does not validate.

        Args:
            sobject_name: Validated sObject API name.
            fields: List of validated field API names.
            where: Optional validated WHERE clause fragment (no ``WHERE``
                keyword).
            order_by: Optional validated ORDER BY fragment (no keyword).
            limit: Optional integer row cap.  When *limit* is ``None``,
                no ``LIMIT`` clause is emitted (Salesforce paginates
                automatically).  When *limit* ≤ 2000, it is safe to embed
                directly in SOQL; for larger values the pagination loop in
                :py:meth:`_query_all` will stop early.

        Returns:
            A complete SOQL query string.
        """
        field_list = ", ".join(fields)
        soql = f"SELECT {field_list} FROM {sobject_name}"

        if where:
            soql += f" WHERE {where}"

        if order_by:
            soql += f" ORDER BY {order_by}"

        # Embed LIMIT in SOQL only when 1 ≤ limit ≤ 2000.
        # - limit=0 is handled upstream (returns early before _build_soql is called).
        # - limit > 2000: no LIMIT clause; _query_all enforces the cap via slicing.
        if limit is not None and 1 <= limit <= 2000:
            soql += f" LIMIT {int(limit)}"

        return soql

    def _query_all(
        self,
        client: Any,
        soql: str,
        limit: Optional[int],
    ) -> Tuple[List[Dict[str, Any]], Optional[int]]:
        """Execute *soql* and follow all ``nextRecordsUrl`` pagination links.

        Args:
            client: An authenticated ``simple_salesforce.Salesforce`` instance.
            soql: Complete SOQL query string.
            limit: Maximum number of raw records to collect.  ``None`` means
                collect everything.

        Returns:
            A ``(records, total_size)`` tuple where *records* is the full
            list of raw record dicts (``attributes`` still present at this
            stage — they are stripped by :py:meth:`_convert_rows`) and
            *total_size* is the ``totalSize`` value from the first response
            (the number of records matching the query before any limit).

        Raises:
            ProcessingError: If the Salesforce API raises any exception
                during pagination.
        """
        try:
            result = client.query(soql)
        except Exception as exc:
            raise ProcessingError(
                f"Salesforce SOQL query failed: {type(exc).__name__}"
            ) from exc

        total_size: Optional[int] = result.get("totalSize")
        records: List[Dict[str, Any]] = list(result.get("records") or [])

        # Follow nextRecordsUrl pages until done or limit reached.
        while not result.get("done", True):
            if limit is not None and len(records) >= limit:
                break

            next_url = result.get("nextRecordsUrl")
            if not next_url:
                break

            self.logger.debug(
                "_query_all: fetching next page (%d records so far)…",
                len(records),
            )

            try:
                # identifier_is_url=True: pass the full path from nextRecordsUrl
                result = client.query_more(next_url, identifier_is_url=True)
            except Exception as exc:
                raise ProcessingError(
                    f"Salesforce pagination (query_more) failed: "
                    f"{type(exc).__name__}"
                ) from exc

            records.extend(result.get("records") or [])

        # Apply client-side limit cap (covers the limit > 2000 case where we
        # did not embed LIMIT in SOQL).
        if limit is not None:
            records = records[:limit]

        return records, total_size

    def _get_all_field_names(self, client: Any, sobject_name: str) -> List[str]:
        """Return all *selectable* field API names for *sobject_name* via describe().

        Compound field types ``address`` and ``location`` are excluded because
        Salesforce rejects them in a ``SELECT`` clause with ``INVALID_FIELD``
        — their component fields (e.g. ``BillingStreet``, ``BillingCity``) are
        returned separately and are individually selectable.

        Args:
            client: Connected simple_salesforce client.
            sobject_name: Already-validated sObject API name.

        Returns:
            List of selectable field name strings.

        Raises:
            ProcessingError: If the describe call fails.
        """
        # Compound field types that Salesforce rejects when placed in SELECT.
        _NON_SELECTABLE_TYPES = frozenset({"address", "location"})

        try:
            sftype = getattr(client, sobject_name)
            result = sftype.describe()
            return [
                f["name"]
                for f in (result.get("fields") or [])
                if f.get("type") not in _NON_SELECTABLE_TYPES
            ]
        except Exception as exc:
            raise ProcessingError(
                f"Failed to describe Salesforce sObject '{sobject_name}': "
                f"{type(exc).__name__}"
            ) from exc

    def _convert_rows(
        self, rows: List[Dict[str, Any]]
    ) -> List[Dict[str, Any]]:
        """Normalise raw Salesforce records to JSON-serialisable dicts.

        Performs three transformations:

        1. Strips the ``attributes`` key that ``simple-salesforce`` injects
           into every record (and into nested relationship sub-objects).
        2. Recursively flattens nested relationship objects — e.g.
           ``{"Owner": {"attributes": {...}, "Name": "Alice"}}`` becomes
           ``{"Owner": {"Name": "Alice"}}``.
        3. Converts ``datetime`` objects to ISO-8601 strings; other
           non-serialisable types are converted via ``str()``.

        Args:
            rows: Raw record dicts as returned by ``sf.query()`` /
                ``sf.query_more()``.

        Returns:
            Cleaned list of record dicts ready for :class:`SalesforceData`.
        """
        converted = []
        for row in rows:
            converted.append(self._clean_record(row))
        return converted

    def _clean_record(self, record: Any) -> Any:
        """Recursively clean a single record or nested value.

        Args:
            record: A raw value from a Salesforce API response — may be a
                dict (record or sub-object), a list, a scalar, or ``None``.

        Returns:
            The cleaned value.
        """
        if isinstance(record, dict):
            cleaned: Dict[str, Any] = {}
            for key, value in record.items():
                if key == "attributes":
                    # Drop the simple-salesforce internal metadata dict.
                    continue
                cleaned[key] = self._clean_record(value)
            return cleaned

        if isinstance(record, list):
            return [self._clean_record(item) for item in record]

        if isinstance(record, datetime):
            return record.isoformat()

        # simple-salesforce returns Salesforce datetime strings as Python
        # strings already; other numeric/bool/None scalars pass through.
        return record
