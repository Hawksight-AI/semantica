"""
Altair Anzo Store Module

This module provides Altair Anzo (formerly Cambridge Semantics Anzo, now
"Altair Graph Studio") integration for RDF storage and SPARQL querying.
Anzo speaks plain SPARQL 1.1 over HTTP, so this backend follows the same
request/response contract as BlazegraphStore and RDF4JStore — the one real
structural difference is that Anzo addresses data by a dataset/graphmart
*URI* rather than a short namespace/repository name, so that URI has to be
percent-encoded into the endpoint path.

Key Features:
    - Anzo SPARQL endpoint connection and HTTP Basic authentication
    - SPARQL query execution (SELECT/ASK/CONSTRUCT)
    - Bulk data loading via SPARQL INSERT DATA
    - Dataset/graphmart URI resolution and percent-encoding

Main Classes:
    - AnzoStore: Main Anzo integration store

Example Usage:
    >>> from semantica.triplet_store import AnzoStore
    >>> store = AnzoStore(
    ...     endpoint="http://localhost:8080",
    ...     dataset_uri="http://cambridgesemantics.com/Graphmart/abc123",
    ... )
    >>> result = store.execute_sparql(sparql_query)
    >>> load_result = store.bulk_load(triplets)

Author: Semantica Contributors
License: MIT
"""

import re
from typing import Any, Dict, List, Optional
from urllib.parse import quote, urlparse

import requests
from rdflib import Graph, Literal

from ..semantic_extract.triplet_extractor import Triplet
from ..utils.exceptions import ProcessingError, ValidationError
from ..utils.logging import get_logger
from ..utils.progress_tracker import get_progress_tracker
from . import sparql_escaping


class AnzoStore:
    """
    Altair Anzo triplet store backend.

    • Anzo connection and HTTP Basic authentication
    • SPARQL query execution
    • Bulk data loading via SPARQL Update
    • Dataset/graphmart URI addressing
    • Error handling and recovery
    """

    def __init__(self, endpoint: str, **config):
        """
        Initialize Anzo store.

        Args:
            endpoint: Anzo host URL, e.g. "http://localhost:8080" (scheme +
                host + port only — the ``/sparql/<store_type>/<dataset_uri>``
                path is appended by this class).
            **config: Additional configuration:
                - dataset_uri: Full URI identifying the Anzo dataset or
                  graphmart (required). Unlike Blazegraph's namespace or
                  RDF4J's repository ID, this is a full URI, not a short
                  name, and is percent-encoded into the endpoint path.
                - store_type: "graphmart" or "lds" (Anzo's Linked Data Set
                  store type; default: "graphmart").
                - username: Username for HTTP Basic authentication.
                - password: Password for HTTP Basic authentication.
                - timeout: Request timeout in seconds (default: 30).

        Raises:
            ValidationError: if dataset_uri is not provided.
        """
        self.logger = get_logger("anzo_store")
        self.config = config
        self.progress_tracker = get_progress_tracker()
        # Ensure progress tracker is enabled
        if not self.progress_tracker.enabled:
            self.progress_tracker.enabled = True

        self.endpoint = endpoint.rstrip("/")

        dataset_uri = config.get("dataset_uri")
        if not dataset_uri:
            raise ValidationError(
                "AnzoStore requires 'dataset_uri' — the full URI of the "
                "Anzo dataset or graphmart to connect to."
            )
        self.dataset_uri = dataset_uri
        self.store_type = config.get("store_type", "graphmart")
        self.username = config.get("username")
        self.password = config.get("password")
        self.timeout = config.get("timeout", 30)

        self.connected = False
        self._connect()

    def _connect(self) -> None:
        """Connect to Anzo instance."""
        try:
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
                self.logger.info(f"Connected to Anzo: {self.endpoint}")
            else:
                self.logger.warning(
                    f"Anzo connection test failed: {response.status_code}"
                )
        except Exception as e:
            self.logger.warning(f"Could not connect to Anzo: {e}")

    def _get_sparql_endpoint(self) -> str:
        """
        Get SPARQL endpoint URL.

        Anzo's endpoint shape is ``<host>:<port>/sparql/<store_type>/<url-
        encoded_dataset_or_graphmart_uri>`` — the dataset/graphmart is
        identified by a full URI rather than a short name, so it must be
        percent-encoded (including "/" and ":") to remain a single path
        segment.
        """
        encoded_dataset = quote(self.dataset_uri, safe="")
        return f"{self.endpoint}/sparql/{self.store_type}/{encoded_dataset}"

    def _get_update_endpoint(self) -> str:
        """Get SPARQL Update endpoint URL (same endpoint as query, per Anzo's SPARQL 1.1 protocol)."""
        return self._get_sparql_endpoint()

    def _is_construct_query(self, query: str) -> bool:
        """
        Detect whether `query` is a SPARQL CONSTRUCT query.

        Delegates to sparql_escaping.CONSTRUCT_QUERY_RE, the single canonical
        CONSTRUCT-detection regex shared with BlazegraphStore and RDF4JStore.
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
            resolves to "bindings"):
                {"success": bool, "bindings": [...], "variables": [...], "metadata": {...}}
            For CONSTRUCT queries (or result_format="construct"):
                {"success": bool, "bindings": [], "variables": [], "triples": [...],
                 "metadata": {...}}
            where "triples" is a list of (subject, predicate, object, metadata)
            4-tuples parsed from the Turtle response via rdflib.

        Raises:
            ProcessingError: if not connected, the HTTP request fails, or (for
                CONSTRUCT queries) the response body fails to parse as Turtle.
        """
        tracking_id = self.progress_tracker.start_tracking(
            module="triplet_store",
            submodule="AnzoStore",
            message="Executing SPARQL query on Anzo",
        )

        try:
            if not self.connected:
                self.progress_tracker.stop_tracking(
                    tracking_id, status="failed", message="Not connected to Anzo"
                )
                raise ProcessingError("Not connected to Anzo")

            sparql_endpoint = self._get_sparql_endpoint()

            result_format = options.get("result_format")
            if result_format is None:
                result_format = "construct" if self._is_construct_query(query) else "bindings"
            elif result_format not in ("construct", "bindings"):
                raise ValidationError(f"Invalid result_format: {result_format!r}")

            if result_format == "construct":
                self.progress_tracker.update_tracking(
                    tracking_id, message="Sending CONSTRUCT query to Anzo endpoint..."
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

            # Non-CONSTRUCT path.
            self.progress_tracker.update_tracking(
                tracking_id, message="Sending query to Anzo endpoint..."
            )
            response = requests.post(
                sparql_endpoint,
                data={"query": query},
                headers={
                    "Content-Type": "application/x-www-form-urlencoded",
                    "Accept": "application/sparql-results+json",
                },
                timeout=self.timeout,
                auth=(self.username, self.password)
                if self.username and self.password
                else None,
            )

            response.raise_for_status()

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
        except ValidationError:
            self.progress_tracker.stop_tracking(
                tracking_id, status="failed", message="Validation error"
            )
            raise
        except Exception as e:
            self.logger.error(f"SPARQL query failed: {e}")
            self.progress_tracker.stop_tracking(
                tracking_id, status="failed", message=str(e)
            )
            raise ProcessingError(f"SPARQL query failed: {e}")

    def bulk_load(self, triplets: List[Triplet], **options) -> Dict[str, Any]:
        """
        Load triplets in bulk via SPARQL INSERT DATA.

        Args:
            triplets: List of triplets
            **options: Additional options:
                - graph: Named graph URI

        Returns:
            Load status
        """
        if not self.connected:
            raise ProcessingError("Not connected to Anzo")

        update_endpoint = self._get_update_endpoint()

        try:
            graph = options.get("graph", "")
            if graph:
                sparql_escaping.validate_uri(graph)

            insert_data = self._build_insert_data(triplets)
            # The GRAPH block must be nested *inside* the INSERT DATA braces
            # per the SPARQL 1.1 Update grammar (INSERT DATA { GRAPH <g> { ... } }),
            # not appended before them.
            if graph:
                query = f"INSERT DATA {{ GRAPH <{graph}> {{ {insert_data} }} }}"
            else:
                query = f"INSERT DATA {{ {insert_data} }}"

            response = requests.post(
                update_endpoint,
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
                "dataset_uri": self.dataset_uri,
            }
        except ValidationError:
            raise
        except Exception as e:
            self.logger.error(f"Bulk load failed: {e}")
            raise ProcessingError(f"Bulk load failed: {e}")

    def _build_insert_data(self, triplets: List[Triplet]) -> str:
        """Build SPARQL INSERT DATA clause.

        Validates subject/predicate as safe IRIs via sparql_escaping.validate_uri
        before interpolating them into the query string, so a value containing
        e.g. ``>`` cannot terminate the intended ``<...>`` token and inject
        additional SPARQL Update tokens.
        """
        lines = []
        for triplet in triplets:
            sparql_escaping.validate_uri(triplet.subject)
            sparql_escaping.validate_uri(triplet.predicate)
            lines.append(
                f"<{triplet.subject}> <{triplet.predicate}> {self._format_object_for_sparql(triplet)} ."
            )
        return " ".join(lines)

    def _format_object_for_sparql(self, triplet: Triplet) -> str:
        """Format triplet object as IRI or literal for SPARQL/N-Triples style syntax."""
        obj = triplet.object
        metadata = triplet.metadata or {}

        if self._is_uri_value(obj):
            if obj.startswith("<") and obj.endswith(">"):
                inner = obj[1:-1]
                if " " in inner or ">" in inner:
                    raise ValueError(f"IRI contains invalid characters: {obj!r}")
                return obj
            return f"<{obj}>"

        escaped = sparql_escaping.escape_literal(obj)
        datatype = metadata.get("datatype") or metadata.get("literal_datatype")
        language = metadata.get("lang") or metadata.get("language")

        if datatype:
            datatype_iri = sparql_escaping.resolve_datatype_iri(datatype)
            return f"\"{escaped}\"^^{datatype_iri}"

        if language:
            if not sparql_escaping.LANG_TAG_RE.match(str(language)):
                raise ValueError(
                    f"Invalid language tag {language!r}: must match RFC 5646 "
                    f"(letters/digits and hyphens only, e.g. 'en', 'en-US')"
                )
            return f"\"{escaped}\"@{language}"

        return f"\"{escaped}\""

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
        # Constraints are expressed via FILTER(...) rather than appended as bare
        # equality expressions inside the group graph pattern — the latter
        # (e.g. "?s ?p ?o ?s = <...>") is not a valid SPARQL graph pattern and
        # is rejected by standards-compliant SPARQL engines. subject/predicate
        # are also validated as safe IRIs before interpolation.
        filters = []
        if subject:
            filters.append(f"?s = <{sparql_escaping.validate_uri(subject)}>")
        if predicate:
            filters.append(f"?p = <{sparql_escaping.validate_uri(predicate)}>")
        if object:
            filters.append(
                f"?o = {self._format_object_for_sparql(Triplet(subject='', predicate='', object=object))}"
            )

        filter_clause = f" FILTER({' && '.join(filters)})" if filters else ""
        query = f"SELECT ?s ?p ?o WHERE {{ ?s ?p ?o .{filter_clause} }}"

        result = self.execute_sparql(query, **options)

        triplets = []
        for binding in result["bindings"]:
            triplets.append(
                Triplet(
                    subject=binding.get("s", {}).get("value", ""),
                    predicate=binding.get("p", {}).get("value", ""),
                    object=binding.get("o", {}).get("value", ""),
                    metadata={"source": "anzo"},
                )
            )

        return triplets

    def delete_triplet(self, triplet: Triplet, **options) -> Dict[str, Any]:
        """Delete triplet."""
        if not self.connected:
            raise ProcessingError("Not connected to Anzo")

        update_endpoint = self._get_update_endpoint()

        try:
            sparql_escaping.validate_uri(triplet.subject)
            sparql_escaping.validate_uri(triplet.predicate)

            query = (
                f"DELETE DATA {{ <{triplet.subject}> <{triplet.predicate}> "
                f"{self._format_object_for_sparql(triplet)} }}"
            )

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
        except ValidationError:
            raise
        except Exception as e:
            self.logger.error(f"Delete triplet failed: {e}")
            raise ProcessingError(f"Delete triplet failed: {e}")
