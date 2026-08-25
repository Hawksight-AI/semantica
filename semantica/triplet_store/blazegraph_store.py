"""
Blazegraph Store Module

This module provides Blazegraph integration for RDF storage and SPARQL
querying, enabling connection to Blazegraph instances with namespace
management and bulk loading capabilities.

Key Features:
    - Blazegraph connection and authentication
    - SPARQL query execution
    - Bulk data loading and management
    - Namespace and graph management
    - REST API integration
    - Performance optimization

Main Classes:
    - BlazegraphStore: Main Blazegraph integration store

Example Usage:
    >>> from semantica.triplet_store import BlazegraphStore
    >>> store = BlazegraphStore(endpoint="http://localhost:9999/blazegraph", namespace="kb")
    >>> result = store.execute_sparql(sparql_query)
    >>> load_result = store.bulk_load(triplets)
    >>> namespace_result = store.create_namespace("new_namespace")

Author: Semantica Contributors
License: MIT
"""

import re
from typing import Any, Dict, List, Optional
from urllib.parse import urljoin, urlparse

import requests
from rdflib import Graph, Literal

from ..semantic_extract.triplet_extractor import Triplet
from ..utils.exceptions import ProcessingError, ValidationError
from ..utils.logging import get_logger
from ..utils.progress_tracker import get_progress_tracker
from . import sparql_escaping

# _CONSTRUCT_QUERY_RE was moved to sparql_escaping.CONSTRUCT_QUERY_RE so both
# BlazegraphStore and RDF4JStore share a single canonical implementation.
# _is_construct_query below delegates to sparql_escaping.CONSTRUCT_QUERY_RE.


class BlazegraphStore:
    """
    Blazegraph triplet store backend.

    • Blazegraph connection and authentication
    • SPARQL query execution
    • Bulk data loading and management
    • Namespace and graph management
    • Performance optimization
    • Error handling and recovery
    """

    def __init__(self, endpoint: str, **config):
        """
        Initialize Blazegraph store.

        Args:
            endpoint: Blazegraph endpoint URL
            **config: Additional configuration:
                - namespace: Namespace name (default: "kb")
                - username: Username for authentication
                - password: Password for authentication
                - timeout: Request timeout (default: 30)
        """
        self.logger = get_logger("blazegraph_store")
        self.config = config
        self.progress_tracker = get_progress_tracker()
        # Ensure progress tracker is enabled
        if not self.progress_tracker.enabled:
            self.progress_tracker.enabled = True

        self.endpoint = endpoint.rstrip("/")
        self.namespace = config.get("namespace", "kb")
        self.username = config.get("username")
        self.password = config.get("password")
        self.timeout = config.get("timeout", 30)

        self.connected = False
        self._connect()

    def _connect(self) -> None:
        """Connect to Blazegraph instance."""
        try:
            # Test connection
            sparql_endpoint = self._get_sparql_endpoint()
            response = requests.get(
                sparql_endpoint,
                params={"query": "SELECT * WHERE { ?s ?p ?o } LIMIT 1"},
                timeout=self.timeout,
                auth=(self.username, self.password)
                if self.username and self.password
                else None,
            )

            if response.status_code == 200:
                self.connected = True
                self.logger.info(f"Connected to Blazegraph: {self.endpoint}")
            else:
                self.logger.warning(
                    f"Blazegraph connection test failed: {response.status_code}"
                )
        except Exception as e:
            self.logger.warning(f"Could not connect to Blazegraph: {e}")

    def _get_sparql_endpoint(self) -> str:
        """Get SPARQL endpoint URL."""
        return urljoin(self.endpoint, f"/blazegraph/namespace/{self.namespace}/sparql")

    def _get_update_endpoint(self) -> str:
        """Get SPARQL Update endpoint URL."""
        return urljoin(self.endpoint, f"/blazegraph/namespace/{self.namespace}/sparql")

    def _is_construct_query(self, query: str) -> bool:
        """
        Detect whether `query` is a SPARQL CONSTRUCT query.

        This is a dispatch helper local to BlazegraphStore, distinct from
        QueryEngine._validate_query (which already treats CONSTRUCT as one of
        its valid_keywords and therefore requires no change — CONSTRUCT
        queries already pass validation today). This helper only decides
        which HTTP Accept header and response parser execute_sparql uses; it
        does not gate query validity.

        Delegates to sparql_escaping.CONSTRUCT_QUERY_RE, which is the single
        canonical CONSTRUCT-detection regex shared with RDF4JStore.
        """
        return sparql_escaping.CONSTRUCT_QUERY_RE.search(query) is not None

    def execute_sparql(self, query: str, **options) -> Dict[str, Any]:
        """
        Execute SPARQL query.

        Args:
            query: SPARQL query string
            **options: Additional options:
                - result_format: Optional[Literal["bindings", "construct"]].
                  If omitted, auto-detected via _is_construct_query(query).

        Returns:
            Query results. For non-CONSTRUCT queries (or when result_format
            resolves to "bindings"), the existing shape is unchanged:
                {"success": bool, "bindings": [...], "variables": [...], "metadata": {...}}
            For CONSTRUCT queries (or result_format="construct"), the shape is:
                {"success": bool, "bindings": [], "variables": [], "triples": [...],
                 "metadata": {...}}
            where "triples" is a list of (subject, predicate, object, metadata)
            4-tuples parsed from the Turtle response via rdflib. subject and
            predicate are always plain strings. object is the literal's
            lexical value or the IRI string. metadata is a dict that is empty
            ({}) for URIs and plain untyped/unlang-tagged literals, and
            otherwise contains "datatype" (the datatype IRI as a string) and/
            or "language" (the RFC 5646 language tag) for literals that carry
            that information — preserving what would otherwise be lost by
            collapsing every rdflib term down to str(term).

        Raises:
            ProcessingError: if not connected, the HTTP request fails, or (for
                CONSTRUCT queries) the response body fails to parse as Turtle.
        """
        tracking_id = self.progress_tracker.start_tracking(
            module="triplet_store",
            submodule="BlazegraphStore",
            message="Executing SPARQL query on Blazegraph",
        )

        try:
            if not self.connected:
                self.progress_tracker.stop_tracking(
                    tracking_id, status="failed", message="Not connected to Blazegraph"
                )
                raise ProcessingError("Not connected to Blazegraph")

            sparql_endpoint = self._get_sparql_endpoint()

            result_format = options.get("result_format")
            if result_format is None:
                result_format = "construct" if self._is_construct_query(query) else "bindings"

            if result_format == "construct":
                self.progress_tracker.update_tracking(
                    tracking_id, message="Sending CONSTRUCT query to Blazegraph endpoint..."
                )
                response = requests.post(
                    sparql_endpoint,
                    data={"query": query},
                    headers={
                        "Content-Type": "application/x-www-form-urlencoded",
                        "Accept": "text/turtle",
                    },
                    timeout=self.timeout,
                    auth=(self.username, self.password)
                    if self.username and self.password
                    else None,
                )

                response.raise_for_status()

                self.progress_tracker.update_tracking(
                    tracking_id, message="Parsing CONSTRUCT response as Turtle..."
                )
                graph = Graph()
                try:
                    graph.parse(data=response.content, format="turtle")
                except Exception as parse_error:
                    raise ProcessingError(
                        f"Failed to parse CONSTRUCT response as Turtle: {parse_error}"
                    ) from parse_error

                triples = []
                for s, p, o in graph:
                    obj_metadata: Dict[str, Any] = {}
                    if isinstance(o, Literal):
                        if o.datatype is not None:
                            obj_metadata["datatype"] = str(o.datatype)
                        if o.language is not None:
                            obj_metadata["language"] = str(o.language)
                    triples.append((str(s), str(p), str(o), obj_metadata))

                result = {
                    "success": True,
                    "bindings": [],
                    "variables": [],
                    "triples": triples,
                    "metadata": {
                        "query": query,
                        "endpoint": sparql_endpoint,
                        "result_format": "construct",
                    },
                }

                self.progress_tracker.stop_tracking(
                    tracking_id,
                    status="completed",
                    message=f"CONSTRUCT query executed: {len(triples)} triples",
                )
                return result

            # Non-CONSTRUCT path — unchanged from prior behavior.
            self.progress_tracker.update_tracking(
                tracking_id, message="Sending query to Blazegraph endpoint..."
            )
            response = requests.post(
                sparql_endpoint,
                data={"query": query},
                headers={"Content-Type": "application/x-www-form-urlencoded"},
                timeout=self.timeout,
                auth=(self.username, self.password)
                if self.username and self.password
                else None,
            )

            response.raise_for_status()

            # Parse JSON response
            self.progress_tracker.update_tracking(
                tracking_id, message="Parsing query results..."
            )
            result_data = response.json()

            result = {
                "success": True,
                "bindings": result_data.get("results", {}).get("bindings", []),
                "variables": result_data.get("head", {}).get("vars", []),
                "metadata": {"query": query, "endpoint": sparql_endpoint},
            }

            self.progress_tracker.stop_tracking(
                tracking_id,
                status="completed",
                message=f"Query executed: {len(result['bindings'])} results",
            )
            return result
        except Exception as e:
            self.logger.error(f"SPARQL query failed: {e}")
            self.progress_tracker.stop_tracking(
                tracking_id, status="failed", message=str(e)
            )
            raise ProcessingError(f"SPARQL query failed: {e}")

    def bulk_load(self, triplets: List[Triplet], **options) -> Dict[str, Any]:
        """
        Load triplets in bulk.

        Args:
            triplets: List of triplets
            **options: Additional options:
                - format: RDF format (turtle, ntriples, rdfxml)
                - graph: Named graph URI

        Returns:
            Load status
        """
        if not self.connected:
            raise ProcessingError("Not connected to Blazegraph")

        # Convert triplets to RDF format
        format = options.get("format", "turtle")
        rdf_data = self._triplets_to_rdf(triplets, format)

        # Upload endpoint
        upload_endpoint = urljoin(
            self.endpoint, f"/blazegraph/namespace/{self.namespace}/sparql"
        )

        try:
            # Use SPARQL INSERT for bulk loading
            graph = options.get("graph", "")
            graph_clause = f"GRAPH <{sparql_escaping.validate_uri(graph)}>" if graph else ""

            # Build INSERT query
            insert_data = self._build_insert_data(triplets)
            query = f"INSERT DATA {graph_clause} {{ {insert_data} }}"

            response = requests.post(
                upload_endpoint,
                data={"update": query},
                headers={"Content-Type": "application/x-www-form-urlencoded"},
                timeout=self.timeout * 2,  # Longer timeout for bulk operations
                auth=(self.username, self.password)
                if self.username and self.password
                else None,
            )

            response.raise_for_status()

            return {
                "success": True,
                "triplets_loaded": len(triplets),
                "namespace": self.namespace,
            }
        except Exception as e:
            self.logger.error(f"Bulk load failed: {e}")
            raise ProcessingError(f"Bulk load failed: {e}")

    def _triplets_to_rdf(self, triplets: List[Triplet], format: str = "turtle") -> str:
        """Convert triplets to RDF format."""
        if format == "turtle":
            lines = []
            for triplet in triplets:
                subject = sparql_escaping.validate_uri(triplet.subject)
                predicate = sparql_escaping.validate_uri(triplet.predicate)
                lines.append(
                    f"<{subject}> <{predicate}> {self._format_object_for_sparql(triplet)} ."
                )
            return "\n".join(lines)
        else:
            # For other formats, use simple turtle conversion
            return self._triplets_to_rdf(triplets, "turtle")

    def _build_insert_data(self, triplets: List[Triplet]) -> str:
        """Build SPARQL INSERT DATA clause.

        Validates subject/predicate as safe IRIs via
        sparql_escaping.validate_uri before interpolation — unlike the
        object (handled by _format_object_for_sparql), subject/predicate
        can't be parameterized in a raw HTTP SPARQL Update POST, so an
        unvalidated value is a direct injection point (GHSA-8vgg-8mr4-r236).
        """
        lines = []
        for triplet in triplets:
            subject = sparql_escaping.validate_uri(triplet.subject)
            predicate = sparql_escaping.validate_uri(triplet.predicate)
            lines.append(
                f"<{subject}> <{predicate}> {self._format_object_for_sparql(triplet)} ."
            )
        return " ".join(lines)

    # Known prefix expansions for XSD and common RDF vocabularies
    _KNOWN_PREFIXES: Dict[str, str] = {
        "xsd": "http://www.w3.org/2001/XMLSchema#",
        "rdf": "http://www.w3.org/1999/02/22-rdf-syntax-ns#",
        "rdfs": "http://www.w3.org/2000/01/rdf-schema#",
        "owl": "http://www.w3.org/2002/07/owl#",
        "skos": "http://www.w3.org/2004/02/skos/core#",
    }

    # RFC 5646 language tag: primary subtag optionally followed by '-' + subtags
    _LANG_TAG_RE = re.compile(r"^[a-zA-Z]{1,8}(-[a-zA-Z0-9]{1,8})*$")

    def _format_object_for_sparql(self, triplet: Triplet) -> str:
        """Format triplet object as IRI or literal for SPARQL/N-Triples style syntax."""
        obj = triplet.object
        metadata = triplet.metadata or {}

        if self._is_uri_value(obj):
            if obj.startswith("<") and obj.endswith(">"):
                # Validate the inner IRI with the same disallowed-character
                # set as the unwrapped branch below — a narrower ad-hoc
                # check here previously let a pre-wrapped object bypass
                # validate_uri() entirely (GHSA-8vgg-8mr4-r236 follow-up).
                inner = sparql_escaping.validate_uri(obj[1:-1])
                return f"<{inner}>"
            validated_obj = sparql_escaping.validate_uri(obj)
            return f"<{validated_obj}>"

        escaped = self._escape_literal(obj)
        datatype = metadata.get("datatype") or metadata.get("literal_datatype")
        language = metadata.get("lang") or metadata.get("language")

        if datatype:
            datatype_iri = self._resolve_datatype_iri(datatype)
            return f"\"{escaped}\"^^{datatype_iri}"

        if language:
            if not self._LANG_TAG_RE.match(str(language)):
                raise ValueError(
                    f"Invalid language tag {language!r}: must match RFC 5646 "
                    f"(letters/digits and hyphens only, e.g. 'en', 'en-US')"
                )
            return f"\"{escaped}\"@{language}"

        return f"\"{escaped}\""

    def _resolve_datatype_iri(self, datatype: str) -> str:
        """Expand a datatype string to a validated SPARQL IRI token.

        Accepts:
        - Already-wrapped IRIs: ``<http://...>``
        - Full IRIs:            ``http://...`` / ``https://...`` / ``urn:...``
        - Known prefixed names: ``xsd:integer``, ``rdf:langString``, etc.

        Raises ValueError for anything else.

        Delegates to the shared sparql_escaping.resolve_datatype_iri so this
        logic has one canonical implementation shared with the CONSTRUCT
        template renderer (semantica/triplet_store/construct_templates.py).
        """
        return sparql_escaping.resolve_datatype_iri(datatype)

    def _is_uri_value(self, value: str) -> bool:
        """Detect if a value should be serialized as an IRI."""
        if not isinstance(value, str) or not value:
            return False
        if value.startswith("<") and value.endswith(">"):
            return True
        parsed = urlparse(value)
        if parsed.scheme not in {"http", "https", "urn"}:
            return False
        # Reject strings that only look like URIs (e.g. "http not a uri")
        return not re.search(r"\s", value)

    def _escape_literal(self, value: str) -> str:
        """Escape string literal for SPARQL.

        Delegates to the shared sparql_escaping.escape_literal so this logic
        has one canonical implementation shared with the CONSTRUCT template
        renderer (semantica/triplet_store/construct_templates.py).
        """
        return sparql_escaping.escape_literal(value)

    def add_triplet(self, triplet: Triplet, **options) -> Dict[str, Any]:
        """Add single triplet."""
        return self.bulk_load([triplet], **options)

    def add_triplets(self, triplets: List[Triplet], **options) -> Dict[str, Any]:
        """Add multiple triplets."""
        return self.bulk_load(triplets, **options)

    def get_triplets(
        self,
        subject: Optional[str] = None,
        predicate: Optional[str] = None,
        object: Optional[str] = None,
        **options,
    ) -> List[Triplet]:
        """Get triplets matching criteria."""
        # Build SPARQL query
        where_clauses = []
        if subject:
            where_clauses.append(f"?s = <{sparql_escaping.validate_uri(subject)}>")
        if predicate:
            where_clauses.append(f"?p = <{sparql_escaping.validate_uri(predicate)}>")
        if object:
            where_clauses.append(
                f"?o = {self._format_object_for_sparql(Triplet(subject='', predicate='', object=object))}"
            )

        where_clause = " ".join(where_clauses) if where_clauses else ""
        query = f"SELECT ?s ?p ?o WHERE {{ ?s ?p ?o {where_clause} }}"

        result = self.execute_sparql(query, **options)

        # Convert bindings to triplets
        triplets = []
        for binding in result["bindings"]:
            triplets.append(
                Triplet(
                    subject=binding.get("s", {}).get("value", ""),
                    predicate=binding.get("p", {}).get("value", ""),
                    object=binding.get("o", {}).get("value", ""),
                    metadata={"source": "blazegraph"},
                )
            )

        return triplets

    def delete_triplet(self, triplet: Triplet, **options) -> Dict[str, Any]:
        """Delete triplet."""
        if not self.connected:
            raise ProcessingError("Not connected to Blazegraph")

        update_endpoint = self._get_update_endpoint()

        subject = sparql_escaping.validate_uri(triplet.subject)
        predicate = sparql_escaping.validate_uri(triplet.predicate)
        query = (
            f"DELETE DATA {{ <{subject}> <{predicate}> "
            f"{self._format_object_for_sparql(triplet)} }}"
        )

        try:
            response = requests.post(
                update_endpoint,
                data={"update": query},
                headers={"Content-Type": "application/x-www-form-urlencoded"},
                timeout=self.timeout,
                auth=(self.username, self.password)
                if self.username and self.password
                else None,
            )

            response.raise_for_status()

            return {"success": True}
        except Exception as e:
            self.logger.error(f"Delete triplet failed: {e}")
            raise ProcessingError(f"Delete triplet failed: {e}")

    def create_namespace(self, namespace: str, **options) -> Dict[str, Any]:
        """
        Create new namespace.

        Args:
            namespace: Namespace name
            **options: Additional options

        Returns:
            Operation status
        """
        # Blazegraph namespace creation via REST API
        create_endpoint = urljoin(self.endpoint, "/blazegraph/namespace")

        try:
            response = requests.post(
                create_endpoint,
                json={"namespace": namespace, **options},
                timeout=self.timeout,
                auth=(self.username, self.password)
                if self.username and self.password
                else None,
            )

            response.raise_for_status()

            return {"success": True, "namespace": namespace}
        except Exception as e:
            self.logger.error(f"Create namespace failed: {e}")
            raise ProcessingError(f"Create namespace failed: {e}")
