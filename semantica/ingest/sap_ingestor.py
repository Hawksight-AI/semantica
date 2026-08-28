"""SAP OData ingestion module.

Pulls an Entity Set from a SAP OData service (S/4HANA and on-prem NetWeaver
REST surfaces) and flattens it into document dicts that the pipeline can feed
to ``GraphBuilder``.

Why this exists
---------------
Semantica ingests from many sources; SAP is the ERP backbone of finance and
regulated industries, and its master/transactional data (customers, vendors,
sales orders) is exactly the "context" a Context Graph wants. SAP exposes that
data over OData (v2 on many on-prem NetWeaver systems, v4 on BTP / S/4HANA
Cloud). This connector speaks the REST surface of OData only.

Design notes
------------
Three classes, matching the Snowflake/Databricks ingestors:
    - ``SAPODataEntity``: a collection fetch from one Entity Set (``records``,
      ``count``, ``service``, ``metadata``), flattened to document dicts for
      ``GraphBuilder`` via ``export_as_documents``.
    - ``SAPODataConnector``: auth (OAuth2 client-credentials or Basic) + the
      shared, SSRF-guarded :mod:`requests` session. *Every* outbound request,
      including the OAuth2 token exchange, goes through
      ``request_with_ssrf_guard`` so user-supplied endpoints can not reach
      private/loopback/link-local address space.
    - ``SAPIngestor``: the three methods the issue requested —
      ``discover_service``, ``ingest_entity_set`` and ``export_as_documents``
      (plus ``close`` for symmetry with the SQL connectors).

EDMX
----
``$metadata`` is plain CSDL XML in *both* OData v2 and v4, so we hand-roll a
minimal parser with :mod:`xml.etree` instead of pulling in ``pyodata``. That
keeps phase 1 ``requests``-only, exactly as scoped in the issue.

Pagination
----------
OData uses a server-driven "next link": OData v2 surfaces it as the atom
``__next`` element, OData v4 as the ``@odata.nextLink`` field on the JSON
payload. ``ingest_entity_set`` follows whichever it sees until the set is
exhausted.
"""

from __future__ import annotations

import base64
import os
import xml.etree.ElementTree as ET
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Dict, List, Optional
from urllib.parse import urljoin, urlparse

import requests
from requests.adapters import HTTPAdapter

try:
    from urllib3.util.retry import Retry
except (ImportError, OSError):  # pragma: no cover - old urllib3 layout
    from requests.packages.urllib3.util.retry import Retry  # type: ignore

from ..utils.exceptions import ProcessingError, ValidationError
from ..utils.logging import get_logger
from .ssrf import parse_bool, request_with_ssrf_guard

__all__ = [
    "SAPODataEntity",
    "SAPODataConnector",
    "SAPIngestor",
]

_logger = get_logger("sap_ingestor")


def _prop_is_nullable(prop: Any) -> bool:
    """CSDL structural properties default to nullable=True when omitted."""
    val = prop.get("Nullable", prop.get("nullable"))
    return True if val is None else val.strip().lower() == "true"


def _match(elem: Any, localname: str) -> bool:
    """True if *elem* has the given local name in any namespace."""
    return elem.tag.rsplit("}", 1)[-1] == localname


@dataclass
class SAPODataEntity:
    """A collection fetch from a SAP OData Entity Set.

    Holds the rows pulled from one Entity Set (all paging fan-in'd), with the
    shape the issue specifies: ``records`` (the row data), ``count``,
    ``service`` (the resolved service root), optional ``metadata`` (entity-set
    schema from ``$metadata``) and ``ingested_at``.
    """

    records: List[Dict[str, Any]]
    entity_set: str
    count: int
    service: str
    metadata: Optional[Dict[str, Any]] = None
    ingested_at: datetime = field(default_factory=datetime.now)

    def to_documents(self) -> List[Dict[str, Any]]:
        """Flatten each record to a document dict ``GraphBuilder`` can consume.

        GraphBuilder only treats a dict as an entity when it carries
        ``id``/``entity_id``/``name`` (or ``text``+``type``); SAP records have
        none of those, so they would be silently dropped. We inject an
        identifier resolved from each record's primary-key-like field, falling
        back to ``entity_set:index``, and expose it under both ``id`` and
        ``name``.
        """
        docs: List[Dict[str, Any]] = []
        for index, record in enumerate(self.records):
            doc = dict(record)
            key_value = self._id_value(record)
            doc.setdefault("id", key_value or f"{self.entity_set}:{index}")
            doc.setdefault("name", key_value or self.entity_set)
            doc.setdefault("source", self.service)
            docs.append(doc)
        return docs

    @staticmethod
    def _id_value(record: Dict[str, Any]) -> str:
        for key, value in record.items():
            if "id" in key.lower() and value not in (None, ""):
                return str(value)
        return ""


class SAPODataConnector:
    """Connection + authentication management for a SAP OData REST service.

    Supports the two auth landscapes called out in the issue:

    - **OAuth2 client-credentials** (BTP / S/4HANA Cloud). The token URL is
      user supplied; both the token exchange *and* every subsequent data
      request are validated through the SSRF guard.
    - **Basic** (on-prem NetWeaver). Username/password passed through as an
      ``Authorization: Basic`` header, also through the guard.

    Example usage::

        >>> connector = SAPODataConnector(
        ...     base_url="https://myhost/sap/opu/odata/sap/",
        ...     token_url="https://myhost/oauth/token",
        ...     client_id="cid", client_secret="secret",
        ... )
        >>> session = connector.get_session()
    """

    def __init__(
        self,
        base_url: Optional[str] = None,
        *,
        auth: Optional[str] = None,
        token_url: Optional[str] = None,
        client_id: Optional[str] = None,
        client_secret: Optional[str] = None,
        username: Optional[str] = None,
        password: Optional[str] = None,
        allow_private_ips: bool = False,
        **config: Any,
    ) -> None:
        """Initialize the SAP OData connector.

        Args:
            base_url: Base OData service URL, e.g. ``https://host/sap/opu
                /odata/sap/``. The issue's ``service`` value.
            auth: Explicit auth flow, ``"oauth2"`` or ``"basic"``. When
                omitted, the flow is inferred from which credentials are set.
            token_url: OAuth2 token endpoint. Required only for OAuth2 flow.
            client_id: OAuth2 client id (OAuth2 flow).
            client_secret: OAuth2 client secret (OAuth2 flow).
            username: Basic-auth username (on-prem flow).
            password: Basic-auth password (on-prem flow).
            allow_private_ips: Opt into private/loopback/link-local endpoints.
                Defaults to False (SSRF-safe).
            **config: Extra options, notably ``timeout``, ``max_retries``,
                ``backoff_factor``, ``headers``.
        """
        self.logger = _logger
        self.base_url = base_url or os.getenv("SAP_BASE_URL")
        self.auth = (auth or os.getenv("SAP_AUTH") or "").lower()
        self.token_url = token_url or os.getenv("SAP_TOKEN_URL")
        self.client_id = client_id or os.getenv("SAP_CLIENT_ID")
        self.client_secret = client_secret or os.getenv("SAP_CLIENT_SECRET")
        self.username = username or os.getenv("SAP_USERNAME")
        self.password = password or os.getenv("SAP_PASSWORD")
        self.allow_private_ips = parse_bool(
            config.pop("allow_private_ips", allow_private_ips), default=False
        )
        self.config = config

        if not self.base_url:
            raise ValidationError(
                "SAP base_url is required. Provide via 'base_url' or "
                "SAP_BASE_URL environment variable."
            )
        oauth_configured = bool(self.client_id or self.client_secret or self.token_url)
        if self.auth in ("oauth2", "oauth"):
            if not (self.client_id and self.client_secret and self.token_url):
                raise ValidationError(
                    "SAP OAuth2 flow requires client_id, client_secret and "
                    "token_url all set."
                )
        elif self.auth == "basic":
            if not (self.username and self.password):
                raise ValidationError("SAP Basic flow requires username and password.")
        elif oauth_configured:
            if not (self.client_id and self.client_secret and self.token_url):
                raise ValidationError(
                    "SAP OAuth2 flow requires client_id, client_secret and "
                    "token_url all set."
                )
        elif not self.username:
            raise ValidationError(
                "SAP authentication requires either (username/password) or "
                "(client_id/client_secret + token_url)."
            )

        self.session = requests.Session()
        retry_strategy = Retry(
            total=self.config.get("max_retries", 3),
            backoff_factor=self.config.get("backoff_factor", 1),
            status_forcelist=[429, 500, 502, 503, 504],
        )
        adapter = HTTPAdapter(max_retries=retry_strategy)
        self.session.mount("http://", adapter)
        self.session.mount("https://", adapter)
        default_headers = self.config.get("headers", {})
        if default_headers:
            self.session.headers.update(default_headers)

        self._token: Optional[str] = None
        self.logger.debug(
            "SAP OData connector initialized (base_url=%s, allow_private_ips=%s)",
            self.base_url,
            self.allow_private_ips,
        )

    def get_session(self) -> requests.Session:
        """Return an authenticated session for data requests.

        For the Basic flow the credentials are attached eagerly; for the
        OAuth2 flow a token is fetched (and cached) on first use. The token
        is never refreshed, so a job that runs past the token TTL (typically
        3600s on SAP) will fail with 401 -- re-create the connector instead.
        """
        if self.username:
            self.session.headers["Authorization"] = "Basic " + self._basic_header()
            return self.session
        if self._token is None:
            self._token = self._fetch_token()
        self.session.headers["Authorization"] = "Bearer " + self._token
        return self.session

    def _basic_header(self) -> str:
        pair = f"{self.username}:{self.password or ''}".encode("utf-8")
        return base64.b64encode(pair).decode("ascii")

    def _fetch_token(self) -> str:
        """Perform the OAuth2 client-credentials token exchange (SSRF-guarded)."""
        if not self.token_url or not self.client_id:
            raise ProcessingError("OAuth2 flow requires token_url and client_id.")
        body = {
            "grant_type": "client_credentials",
            "client_id": self.client_id,
            "client_secret": self.client_secret or "",
        }
        resp = request_with_ssrf_guard(
            "POST",
            self.token_url,
            session=self.session,
            allow_private_ips=self.allow_private_ips,
            data=body,
            timeout=self.config.get("timeout", 30),
        )
        try:
            resp.raise_for_status()
        except requests.exceptions.RequestException as exc:
            raise ProcessingError(f"SAP OAuth2 token exchange failed: {exc}") from exc
        try:
            payload = resp.json()
        except ValueError as exc:
            raise ProcessingError(
                "SAP OAuth2 token endpoint did not return JSON."
            ) from exc
        token = payload.get("access_token")
        if not token:
            raise ProcessingError("SAP OAuth2 token response missing 'access_token'.")
        return str(token)

    def close(self) -> None:
        """Close the underlying :mod:`requests` session."""
        self.session.close()


class SAPIngestor:
    """Ingest an Entity Set from a SAP OData service.

    Example usage::

        >>> from semantica.ingest import SAPIngestor
        >>> ing = SAPIngestor(
        ...     base_url="https://host/sap/opu/odata/sap/",
        ...     username="u", password="p",   # or client_id/client_secret/token_url
        ... )
        >>> sets = ing.discover_service()
        ... # -> [{"name": "SalesOrderSet", "fields": [...]}, ...]
        >>> docs = ing.export_as_documents(
        ...     ing.ingest_entity_set(entity_set="SalesOrderSet", expand="to_Item"))
    """

    def __init__(
        self,
        base_url: Optional[str] = None,
        connector: Optional[SAPODataConnector] = None,
        **config: Any,
    ) -> None:
        """Initialize the SAP ingestor.

        Args:
            base_url: Base OData service URL. Mutually exclusive with
                ``connector``; ignored if a connector is given.
            connector: An existing :class:`SAPODataConnector`. When provided,
                its session and base URL are reused.
            **config: Passed to :class:`SAPODataConnector` when one is created.
        """
        self.logger = _logger
        self.connector = connector or SAPODataConnector(base_url=base_url, **config)
        # urljoin() replaces the last path segment unless the base ends in '/',
        # so normalize once here: .../API_BUSINESS_PARTNER -> .../$metadata would
        # silently drop the service segment.
        self._base_url = self.connector.base_url
        if not self._base_url.endswith("/"):
            self._base_url += "/"

    def discover_service(self, service: Optional[str] = None) -> List[Dict[str, Any]]:
        """Fetch and parse ``$metadata`` into the service's entity sets.

        Args:
            service: Service root URL (absolute) or path suffix resolved
                against the base URL. Defaults to the base URL. ``$metadata``
                is appended automatically — same meaning as in
                :meth:`ingest_entity_set`.

        Returns:
            List of dicts, one per EntitySet, each with ``name`` and ``fields``
            (a list of ``{name, type, nullable}`` parsed from the CSDL).
        """
        metadata_url = self._metadata_url(service)
        session = self.connector.get_session()
        resp = request_with_ssrf_guard(
            "GET",
            metadata_url,
            session=session,
            allow_private_ips=self.connector.allow_private_ips,
            headers={"Accept": "application/xml"},
            timeout=self.connector.config.get("timeout", 30),
        )
        try:
            resp.raise_for_status()
        except requests.exceptions.RequestException as exc:
            self.logger.error("Failed to fetch SAP metadata %s: %s", metadata_url, exc)
            raise ProcessingError(f"Failed to fetch SAP $metadata: {exc}") from exc

        return self._parse_metadata(resp.text)

    def _metadata_url(self, service: Optional[str]) -> str:
        """Build the ``$metadata`` URL for a service root.

        ``service`` has the same meaning as in :meth:`ingest_entity_set` —
        a service root (absolute URL or path suffix resolved against the
        base URL). ``$metadata`` is appended here, so callers pass the root
        the same way for both discovery and ingestion. A value already
        ending in ``$metadata`` is used as-is.
        """
        if not service:
            return urljoin(self._base_url, "$metadata")
        if "://" not in service:
            service = urljoin(self._base_url, service)
        if service.endswith("$metadata"):
            return service
        if not service.endswith("/"):
            service += "/"
        return urljoin(service, "$metadata")

    def _parse_metadata(self, metadata_xml: str) -> List[Dict[str, Any]]:
        """Minimal CSDL/EDMX parser -> entity set name + property fields.

        Element local names (``Schema``/``EntitySet``/``EntityType``/
        ``Property``) are stable across OData v2 (Microsoft ns) and v4 (OASIS
        ns), so we match them by local name instead of hard-coding one
        namespace. Entity-Type references are resolved per-schema, so
        same-named types in different schemas cannot bleed fields into each
        other.
        """
        try:
            root = ET.fromstring(metadata_xml)
        except ET.ParseError as exc:
            raise ProcessingError(f"SAP $metadata is not valid XML: {exc}") from exc

        # Index fully-qualified type name -> property fields, per schema.
        schema_types: Dict[str, List[Dict[str, Any]]] = {}
        for schema in (e for e in root.iter() if _match(e, "Schema")):
            ns = (schema.get("Namespace") or schema.get("namespace") or "").rstrip(".")
            for entity_type in (e for e in schema.iter() if _match(e, "EntityType")):
                tname = entity_type.get("Name") or entity_type.get("name")
                if not tname:
                    continue
                fq = f"{ns}.{tname}" if ns else tname
                schema_types[fq] = [
                    {
                        "name": prop.get("Name") or prop.get("name"),
                        "type": prop.get("Type") or prop.get("type"),
                        "nullable": _prop_is_nullable(prop),
                    }
                    for prop in (e for e in entity_type.iter() if _match(e, "Property"))
                ]

        entity_sets: List[Dict[str, Any]] = []
        for schema in (e for e in root.iter() if _match(e, "Schema")):
            ns = (schema.get("Namespace") or schema.get("namespace") or "").rstrip(".")
            for entity_set in (e for e in schema.iter() if _match(e, "EntitySet")):
                name = entity_set.get("Name") or entity_set.get("name")
                ref = entity_set.get("EntityType") or entity_set.get("entityType") or ""
                qualified = ref if "." in ref else (f"{ns}.{ref}" if ns else ref)
                fields = schema_types.get(qualified) or schema_types.get(ref) or []
                entity_sets.append({"name": name, "fields": fields})
        return entity_sets

    def ingest_entity_set(
        self,
        service: Optional[str] = None,
        entity_set: Optional[str] = None,
        *,
        select: Optional[str] = None,
        filter: Optional[str] = None,
        expand: Optional[str] = None,
        top: Optional[int] = None,
        skip: Optional[int] = None,
        batch_size: int = 100,
    ) -> SAPODataEntity:
        """Fetch pages of *entity_set* from the OData service.

        Args:
            service: Service root URL (absolute) or path suffix resolved
                against the base URL. Defaults to the base URL. Same meaning
                as in :meth:`discover_service`.
            entity_set: Entity set name, e.g. ``"SalesOrderSet"``.
            select: Optional ``$select`` comma string.
            filter: Optional ``$filter`` expression.
            expand: Optional ``$expand`` expression (e.g. ``"to_Item"`` for
                use case 2's sales-order headers -> line items).
            top: Maximum number of rows to return.
            skip: Number of leading rows to skip.
            batch_size: ``$top`` pagination size per request.

        Returns:
            A single :class:`SAPODataEntity` holding every fetched record
            (server-driven pagination is followed to completion).
        """
        if service is None:
            base = self._base_url
        elif "://" in service:
            base = service
        else:
            base = urljoin(self._base_url, service)
        if not base.endswith("/"):
            base += "/"
        if not entity_set:
            raise ValidationError("SAP 'entity_set' is required.")

        session = self.connector.get_session()
        records: List[Dict[str, Any]] = []
        next_link: Optional[str] = urljoin(base, entity_set)
        params = self._query_params(select, filter, expand, top, skip, batch_size)

        if top is not None and top < 0:
            raise ValidationError("SAP 'top' must be >= 0 (got %r)" % top)
        if top == 0:
            return SAPODataEntity(
                records=[], entity_set=entity_set, count=0, service=base
            )
        original_host = (urlparse(base).hostname or "").lower()

        while next_link:
            # Server-provided next links may point anywhere; never send the
            # session credentials (Basic/Bearer) to a different origin than
            # the service root. Legit SAP pagination stays on the same host.
            next_host = (urlparse(next_link).hostname or "").lower()
            if next_host != original_host:
                raise ProcessingError(
                    f"SAP next link '{next_link}' points to a different host "
                    f"than service root '{base}'"
                )
            resp = request_with_ssrf_guard(
                "GET",
                next_link,
                session=session,
                allow_private_ips=self.connector.allow_private_ips,
                headers={"Accept": "application/json"},
                params=params,
                timeout=self.connector.config.get("timeout", 30),
            )
            try:
                resp.raise_for_status()
            except requests.exceptions.RequestException as exc:
                self.logger.error(
                    "Failed to fetch SAP entity set %s: %s", entity_set, exc
                )
                raise ProcessingError(
                    f"Failed to fetch SAP entity set {entity_set}: {exc}"
                ) from exc

            payload = self._parse_page(resp)
            rows, next_link = payload["rows"], payload["next_link"]

            for raw_row in rows:
                records.append(self._flatten_row(raw_row))

            self.logger.debug(
                "Fetched %d rows from %s (next=%s)",
                len(rows),
                entity_set,
                bool(next_link),
            )
            if top is not None and len(records) >= top:
                break

            params = None  # query params already baked into the server next link
            # Refresh next_link against base in case it's a relative pointer.
            if next_link and not next_link.startswith("http"):
                next_link = urljoin(resp.url, next_link)

        return SAPODataEntity(
            records=records,
            entity_set=entity_set,
            count=len(records),
            service=base,
        )

    def _query_params(
        self,
        select: Optional[str],
        filter: Optional[str],
        expand: Optional[str],
        top_value: Optional[int],
        skip: Optional[int],
        batch_size: int,
    ) -> Dict[str, str]:
        params: Dict[str, str] = {}
        if batch_size > 0:
            if top_value is not None:
                params["$top"] = str(min(batch_size, top_value))
            else:
                params["$top"] = str(batch_size)
        if select:
            params["$select"] = select
        if filter:
            params["$filter"] = filter
        if expand:
            params["$expand"] = expand
        if skip is not None:
            params["$skip"] = str(skip)
        return params

    def _parse_page(self, resp: requests.Response) -> Dict[str, Any]:
        try:
            payload = resp.json()
        except ValueError as exc:
            raise ProcessingError(f"SAP OData response is not JSON: {exc}") from exc

        rows: Any
        next_link: Optional[str] = None
        if isinstance(payload, list):
            rows = payload
        elif isinstance(payload, dict):
            d = payload.get("d")
            if isinstance(d, dict):
                # OData v2 atom: {"d": {"results": [...], "__next": ...}}
                rows = d.get("results")
                nxt = d.get("__next") or payload.get("@odata.nextLink")
            else:
                # OData v4 JSON: {"value": [...], "@odata.nextLink": ...}
                rows = payload.get("value", d)
                nxt = payload.get("@odata.nextLink")
            if isinstance(nxt, dict):
                nxt = nxt.get("__deferred", {}).get("uri")
            next_link = nxt
        else:
            rows = None

        if not isinstance(rows, list):
            raise ProcessingError(
                "SAP OData payload has no list of rows (got %s)" % type(rows).__name__
            )
        return {"rows": rows, "next_link": next_link}

    def _flatten_row(self, row: Any) -> Dict[str, Any]:
        if isinstance(row, dict):
            # v2 wraps items in "__metadata"; keep it but expose plain keys.
            return {k: v for k, v in row.items() if k != "__metadata"}
        return {"value": row}

    def export_as_documents(self, data: SAPODataEntity) -> List[Dict[str, Any]]:
        """Convert an ingested entity set to flat document dicts.

        Normalizes every records held by ``data`` into a list of dicts with an
        injected ``id``/``name``/``source``, ready to hand to ``GraphBuilder``.
        """
        return data.to_documents()

    def close(self) -> None:
        """Close the underlying connector's session."""
        self.connector.close()
