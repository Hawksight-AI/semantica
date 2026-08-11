"""
RDF4J Store Module

This module provides Eclipse RDF4J integration for RDF storage and SPARQL
querying, supporting repository management and transaction operations.

Key Features:
    - RDF4J connection and repository management
    - SPARQL query execution
    - Repository configuration and setup
    - Transaction support
    - REST API integration
    - Bulk operations

Main Classes:
    - RDF4JStore: Main RDF4J integration store

Example Usage:
    >>> from semantica.triplet_store import RDF4JStore
    >>> store = RDF4JStore(endpoint="http://localhost:8080/rdf4j-server", repository_id="repo1")
    >>> result = store.execute_sparql(sparql_query)
    >>> tx_id = store.begin_transaction()
    >>> result = store.add_triplets(triplets)

Author: Semantica Contributors
License: MIT
"""

import re
from typing import Any, Dict, List, Optional
from urllib.parse import urlparse

import requests
from rdflib import Graph, Literal

from ..semantic_extract.triplet_extractor import Triplet
from ..utils.exceptions import ProcessingError, ValidationError
from ..utils.logging import get_logger
from ..utils.progress_tracker import get_progress_tracker
from . import sparql_escaping


class RDF4JStore:
    """
    Eclipse RDF4J store for triplet store operations.

    This class provides integration with Eclipse RDF4J, supporting
    remote repositories, transactions, and high-performance querying.
    """

    def __init__(
        self, endpoint: Optional[str] = None, repository_id: Optional[str] = None, **config
    ):
        """
        Initialize RDF4J store.

        Args:
            endpoint: RDF4J server URL
            repository_id: Repository identifier
            **config: Additional configuration options
        """
        self.logger = get_logger("rdf4j_store")
        self.config = config
        self.progress_tracker = get_progress_tracker()
        # Ensure progress tracker is enabled
        if not self.progress_tracker.enabled:
            self.progress_tracker.enabled = True

        self.endpoint = endpoint.rstrip("/")
        self.repository_id = config.get("repository_id", "default")
        self.username = config.get("username")
        self.password = config.get("password")
        self.timeout = config.get("timeout", 30)

        self.connected = False
        self._connect()

    def _connect(self) -> None:
        """Connect to RDF4J server."""
        try:
            # Test connection
            test_url = f"{self.endpoint}/repositories/{self.repository_id}"
            response = requests.get(
                test_url,
                timeout=self.timeout,
                auth=(self.username, self.password)
                if self.username and self.password
                else None,
            )

            if response.status_code == 200:
                self.connected = True
                self.logger.info(f"Connected to RDF4J: {self.endpoint}")
            else:
                self.logger.warning(
                    f"RDF4J connection test failed: {response.status_code}"
                )
        except Exception as e:
            self.logger.warning(f"Could not connect to RDF4J: {e}")

    def _get_sparql_endpoint(self) -> str:
        """Get SPARQL query endpoint."""
        return f"{self.endpoint}/repositories/{self.repository_id}"

    def _get_update_endpoint(self) -> str:
        """Get SPARQL Update endpoint."""
        return f"{self.endpoint}/repositories/{self.repository_id}/statements"

    def _is_construct_query(self, query: str) -> bool:
        """
        Detect whether `query` is a SPARQL CONSTRUCT query.

        Delegates to sparql_escaping.CONSTRUCT_QUERY_RE, the single canonical
        CONSTRUCT-detection regex shared with BlazegraphStore.
        """
        return sparql_escaping.CONSTRUCT_QUERY_RE.search(query) is not None

    def create_repository(
        self, repository_config: Dict[str, Any], **options
    ) -> Dict[str, Any]:
        """
        Create and configure repository.

        Args:
            repository_config: Repository configuration
            **options: Additional options

        Returns:
            Repository information
        """
        # RDF4J repository creation via REST API
        create_url = f"{self.endpoint}/repositories"

        try:
            response = requests.post(
                create_url,
                json=repository_config,
                timeout=self.timeout,
                auth=(self.username, self.password)
                if self.username and self.password
                else None,
            )

            response.raise_for_status()

            return {
                "success": True,
                "repository_id": repository_config.get("id", "new_repository"),
            }
        except Exception as e:
            self.logger.error(f"Create repository failed: {e}")
            raise ProcessingError(f"Create repository failed: {e}")

    def begin_transaction(self, **options) -> str:
        """
        Start transaction for batch operations.

        Args:
            **options: Transaction options

        Returns:
            Transaction ID
        """
        # RDF4J transaction support
        transaction_url = (
            f"{self.endpoint}/repositories/{self.repository_id}/transactions"
        )

        try:
            response = requests.post(
                transaction_url,
                timeout=self.timeout,
                auth=(self.username, self.password)
                if self.username and self.password
                else None,
            )

            response.raise_for_status()
            transaction_id = response.headers.get("Location", "").split("/")[-1]

            return transaction_id
        except Exception as e:
            self.logger.error(f"Begin transaction failed: {e}")
            raise ProcessingError(f"Begin transaction failed: {e}")

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
            that information.

        Raises:
            ProcessingError: if not connected, the HTTP request fails, or (for
                CONSTRUCT queries) the response body fails to parse as Turtle.
        """
        tracking_id = self.progress_tracker.start_tracking(
            module="triplet_store",
            submodule="RDF4JStore",
            message="Executing SPARQL query on RDF4J",
        )

        try:
            if not self.connected:
                self.progress_tracker.stop_tracking(
                    tracking_id, status="failed", message="Not connected to RDF4J"
                )
                raise ProcessingError("Not connected to RDF4J")

            sparql_endpoint = self._get_sparql_endpoint()

            result_format = options.get("result_format")
            if result_format is None:
                result_format = "construct" if self._is_construct_query(query) else "bindings"
            elif result_format not in ("construct", "bindings"):
                raise ValidationError(f"Invalid result_format: {result_format!r}")

            if result_format == "construct":
                self.progress_tracker.update_tracking(
                    tracking_id, message="Sending CONSTRUCT query to RDF4J endpoint..."
                )
                # result_format is a load-bearing internal detail of this
                # function; pop it from a local copy so a caller-supplied
                # result_format in **options cannot crash with
                # "got multiple values for keyword argument".
                execute_options = dict(options)
                execute_options.pop("result_format", None)

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

            # Non-CONSTRUCT path — unchanged from prior behavior, including the
            # explicit Accept: application/sparql-results+json header.
            self.progress_tracker.update_tracking(
                tracking_id, message="Sending query to RDF4J endpoint..."
            )
            response = requests.post(
                sparql_endpoint,
                data={"query": query},
                headers={"Accept": "application/sparql-results+json"},
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

    def add_triplets(self, triplets: List[Triplet], **options) -> Dict[str, Any]:
        """
        Add triplets to repository.

        Args:
            triplets: List of triplets
            **options: Additional options:
                - graph: Optional[str] — named graph URI. When provided, the
                  request appends a ``context`` query parameter to the
                  /statements endpoint, formatted as an N-Triples-encoded IRI
                  (angle-bracket-wrapped, e.g. ``<http://example.org/g>``).
                  The ``requests`` library URL-encodes this automatically, so
                  the wire value is ``?context=%3Chttp%3A%2F%2F...%3E``.
                  When graph is None or omitted, no context parameter is sent
                  and writes go to the default/all graphs as before.

        Returns:
            Operation status
        """
        tracking_id = self.progress_tracker.start_tracking(
            module="triplet_store",
            submodule="RDF4JStore",
            message=f"Adding {len(triplets)} triplets to RDF4J repository",
        )

        try:
            if not self.connected:
                self.progress_tracker.stop_tracking(
                    tracking_id, status="failed", message="Not connected to RDF4J"
                )
                raise ProcessingError("Not connected to RDF4J")

            update_endpoint = self._get_update_endpoint()

            # Convert triplets to RDF format
            self.progress_tracker.update_tracking(
                tracking_id, message="Converting triplets to RDF format..."
            )
            rdf_data = self._triplets_to_ntriples(triplets)

            # Build the context (named graph) query parameter if requested.
            # RDF4J REST API requires the value to be N-Triples-encoded:
            # the IRI must be wrapped in angle brackets, e.g. <http://...>.
            # requests.post with params= URL-encodes the value automatically,
            # so the wire value becomes ?context=%3Chttp%3A...%3E.
            # When graph is None, send no context parameter at all — do NOT
            # default to context=null, which would change "all graphs" semantics
            # to "default graph only" and is a behavior change from today.
            graph = options.get("graph")
            if graph is not None:
                sparql_escaping.validate_uri(graph)
                context_params = {"context": f"<{graph}>"}
            else:
                context_params = None

            self.progress_tracker.update_tracking(
                tracking_id, message="Sending triplets to RDF4J repository..."
            )
            response = requests.post(
                update_endpoint,
                data=rdf_data,
                headers={"Content-Type": "application/n-triples"},
                params=context_params,
                timeout=self.timeout * 2,
                auth=(self.username, self.password)
                if self.username and self.password
                else None,
            )

            response.raise_for_status()

            self.progress_tracker.stop_tracking(
                tracking_id,
                status="completed",
                message=f"Added {len(triplets)} triplets to repository",
            )

            return {"success": True, "triplets_added": len(triplets)}
        except ValidationError:
            self.progress_tracker.stop_tracking(
                tracking_id, status="failed", message="Validation error"
            )
            raise
        except Exception as e:
            self.logger.error(f"Add triplets failed: {e}")
            self.progress_tracker.stop_tracking(
                tracking_id, status="failed", message=str(e)
            )
            raise ProcessingError(f"Add triplets failed: {e}")

    def add_triplet(self, triplet: Triplet, **options) -> Dict[str, Any]:
        """Add single triplet."""
        return self.add_triplets([triplet], **options)

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
            where_clauses.append(f"?o = <{sparql_escaping.validate_uri(object)}>")

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
                    metadata={"source": "rdf4j"},
                )
            )

        return triplets

    def delete_triplet(self, triplet: Triplet, **options) -> Dict[str, Any]:
        """Delete triplet."""
        if not self.connected:
            raise ProcessingError("Not connected to RDF4J")

        update_endpoint = self._get_update_endpoint()

        # Use SPARQL DELETE.
        # subject/predicate must be IRIs — validate_uri enforces that and
        # blocks injection through '>' or other SPARQL metacharacters.
        # object can be an IRI *or* a literal, so it is routed through
        # _format_object_for_ntriples (which internally calls validate_uri
        # for URI-shaped values and escape_literal for strings), matching
        # the same object-handling semantics used by the add path and by
        # BlazegraphStore.delete_triplet (GHSA-8vgg-8mr4-r236 regression fix).
        subject = sparql_escaping.validate_uri(triplet.subject)
        predicate = sparql_escaping.validate_uri(triplet.predicate)
        obj_str = self._format_object_for_ntriples(triplet)
        query = f"DELETE DATA {{ <{subject}> <{predicate}> {obj_str} }}"

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

    def _is_uri_value(self, value: str) -> bool:
        """
        Detect if a value should be serialized as an IRI.

        Byte-for-byte copy of BlazegraphStore._is_uri_value, so both backends
        agree on which triplet objects are IRIs vs. literals.
        """
        if not isinstance(value, str) or not value:
            return False
        if value.startswith("<") and value.endswith(">"):
            return True
        parsed = urlparse(value)
        if parsed.scheme not in {"http", "https", "urn"}:
            return False
        # Reject strings that only look like URIs (e.g. "http not a uri")
        return not re.search(r"\s", value)

    def _format_object_for_ntriples(self, triplet: Triplet) -> str:
        """Format triplet object as IRI or literal based on metadata."""
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

        escaped = sparql_escaping.escape_literal(obj)
        datatype = metadata.get("datatype") or metadata.get("literal_datatype")
        language = metadata.get("lang") or metadata.get("language")

        if datatype:
            datatype_iri = sparql_escaping.resolve_datatype_iri(datatype)
            return f'"{escaped}"^^{datatype_iri}'
        if language:
            if not sparql_escaping.LANG_TAG_RE.match(str(language)):
                raise ValueError(f"Invalid language tag {language!r}: must match RFC 5646")
            return f'"{escaped}"@{language}'

        return f'"{escaped}"'

    def _triplets_to_ntriples(self, triplets: List[Triplet]) -> str:
        """Convert triplets to N-Triples format.

        Validates subject/predicate via sparql_escaping.validate_uri: an
        unvalidated value containing '>' or a newline could terminate the
        current triple line early and splice extra triples into the
        upload stream (GHSA-8vgg-8mr4-r236).
        """
        lines = []
        for triplet in triplets:
            subject = sparql_escaping.validate_uri(triplet.subject)
            predicate = sparql_escaping.validate_uri(triplet.predicate)
            obj_str = self._format_object_for_ntriples(triplet)
            lines.append(f"<{subject}> <{predicate}> {obj_str} .")
        return "\n".join(lines)
