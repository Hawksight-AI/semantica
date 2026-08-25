"""Embedded RDF storage backed by Oxigraph.

This backend provides an in-process SPARQL 1.1 store for development, tests,
and workloads that do not need a separately managed graph database server.
It can run entirely in memory or persist its data to a local directory.
"""

import importlib
import os
import re
from pathlib import Path
from typing import Any, Dict, List, Optional, Union
from urllib.parse import urlparse

from ..semantic_extract.triplet_extractor import Triplet
from ..utils.exceptions import ProcessingError, ValidationError
from ..utils.logging import get_logger
from . import sparql_escaping


class OxigraphStore:
    """Embedded, optionally persistent RDF store powered by PyOxigraph."""

    supports_named_graphs = True
    _XSD_STRING = "http://www.w3.org/2001/XMLSchema#string"

    def __init__(
        self,
        path: Optional[Union[str, os.PathLike]] = None,
        **config,
    ):
        """Initialize an in-memory or on-disk Oxigraph store.

        Args:
            path: Directory used for persistent storage. If omitted, the store
                is kept in memory.
            **config: Backend configuration. ``path`` may also be supplied in
                this mapping.

        Raises:
            ImportError: If the optional ``pyoxigraph`` package is missing.
            ProcessingError: If the store cannot be opened.
        """
        self.logger = get_logger("oxigraph_store")
        # Accept storage_path as an alias for path (matches the convention used
        # by other Semantica stores). Pop it so it isn't left in self.config.
        if path is None and "storage_path" in config:
            path = config.pop("storage_path")
        self.config = config
        self.path = path if path is not None else config.get("path")

        try:
            self._oxigraph = importlib.import_module("pyoxigraph")
        except (ImportError, OSError) as exc:
            raise ImportError(
                "PyOxigraph is required for the 'oxigraph' backend. "
                'Install it with: pip install "semantica[tripletstore-oxigraph]"'
            ) from exc

        store_path = None
        if self.path is not None:
            path_obj = Path(self.path).expanduser()
            try:
                path_obj.mkdir(parents=True, exist_ok=True)
            except OSError as exc:
                raise ProcessingError(
                    f"Failed to create Oxigraph store directory {path_obj}: {exc}"
                ) from exc
            store_path = str(path_obj)
            self.path = store_path

        try:
            self.store = self._oxigraph.Store(store_path)
        except Exception as exc:
            location = store_path or "memory"
            raise ProcessingError(
                f"Failed to initialize Oxigraph store at {location}: {exc}"
            ) from exc

    def add_triplet(self, triplet: Triplet, **options) -> Dict[str, Any]:
        """Add one triplet to the default graph or ``options['graph']``.

        The write is committed to the store's in-memory state immediately.
        pyoxigraph's background threads will persist it to disk shortly
        afterward; call :meth:`flush` explicitly if you need a synchronous
        durability guarantee before reopening or crashing.
        """
        try:
            graph_name = self._graph_name(options.get("graph"))
            self.store.extend([self._to_quad(triplet, graph_name)])
            return {
                "success": True,
                "triplets_loaded": 1,
                "graph": options.get("graph"),
            }
        except Exception as exc:
            self.logger.error(f"Oxigraph load failed: {exc}")
            raise ProcessingError(f"Oxigraph load failed: {exc}") from exc

    def add_triplets(self, triplets: List[Triplet], **options) -> Dict[str, Any]:
        """Add triplets in one native Oxigraph batch.

        The batch is written transactionally and then explicitly flushed to
        disk before returning.  This makes the full batch durable without
        requiring a separate :meth:`flush` call.  In-memory stores skip the
        flush (there is nothing to sync).

        For high-volume imports the :class:`~.bulk_loader.BulkLoader` splits
        work into chunks and calls this method once per chunk, so each chunk
        lands as one atomic, durable unit.
        """
        try:
            graph_name = self._graph_name(options.get("graph"))
            quads = [self._to_quad(triplet, graph_name) for triplet in triplets]
            self.store.extend(quads)
        except Exception as exc:
            self.logger.error(f"Oxigraph load failed: {exc}")
            raise ProcessingError(f"Oxigraph load failed: {exc}") from exc

        # Flush is kept outside the write try/except so that a flush I/O error
        # does not produce a misleading "load failed" message when extend()
        # already committed the batch successfully.
        if self.path is not None:
            try:
                self.flush()
            except OSError as exc:
                self.logger.warning(
                    f"Oxigraph flush failed after successful write: {exc}"
                )
                raise ProcessingError(
                    f"Oxigraph flush failed after successful write: {exc}"
                ) from exc

        return {
            "success": True,
            "triplets_loaded": len(triplets),
            "graph": options.get("graph"),
        }

    def bulk_load(self, triplets: List[Triplet], **options) -> Dict[str, Any]:
        """Load a batch of triplets using Oxigraph's native bulk operation."""
        return self.add_triplets(triplets, **options)

    def get_triplets(
        self,
        subject: Optional[str] = None,
        predicate: Optional[str] = None,
        object: Optional[str] = None,
        **options,
    ) -> List[Triplet]:
        """Return triplets matching a pattern in one graph.

        The default graph is queried unless ``graph`` is provided, matching
        the behavior of the other graph-aware triplet-store backends.
        """
        try:
            ox = self._oxigraph
            subject_term = ox.NamedNode(subject) if subject is not None else None
            predicate_term = ox.NamedNode(predicate) if predicate is not None else None
            object_term = (
                self._object_from_value(object) if object is not None else None
            )
            graph_name = self._graph_name(options.get("graph"))
            quads = self.store.quads_for_pattern(
                subject_term, predicate_term, object_term, graph_name
            )
            return [self._quad_to_triplet(quad) for quad in quads]
        except Exception as exc:
            self.logger.error(f"Failed to get Oxigraph triplets: {exc}")
            raise ProcessingError(f"Failed to get Oxigraph triplets: {exc}") from exc

    def delete_triplet(self, triplet: Triplet, **options) -> Dict[str, Any]:
        """Delete one triplet from the default graph or ``options['graph']``."""
        try:
            graph_name = self._graph_name(options.get("graph"))
            self.store.remove(self._to_quad(triplet, graph_name))
            return {"success": True}
        except Exception as exc:
            self.logger.error(f"Failed to delete Oxigraph triplet: {exc}")
            raise ProcessingError(f"Failed to delete Oxigraph triplet: {exc}") from exc

    def execute_sparql(self, query: str, **options) -> Dict[str, Any]:
        """Execute a SPARQL query and return the shared backend result shape."""
        result_format = options.get("result_format")
        if result_format not in (None, "bindings", "construct"):
            raise ValidationError(f"Invalid result_format: {result_format!r}")

        try:
            result = self.store.query(query)

            if isinstance(result, self._oxigraph.QuerySolutions):
                if result_format == "construct":
                    raise ValidationError(
                        "result_format='construct' requires a CONSTRUCT or "
                        "DESCRIBE query"
                    )
                variables = [variable.value for variable in result.variables]
                bindings = []
                for solution in result:
                    binding = {}
                    for variable in variables:
                        term = solution[variable]
                        if term is not None:
                            binding[variable] = self._term_to_binding(term)
                    bindings.append(binding)
                return {
                    "success": True,
                    "bindings": bindings,
                    "variables": variables,
                    "metadata": {"query": query},
                }

            if isinstance(result, self._oxigraph.QueryBoolean):
                if result_format == "construct":
                    raise ValidationError(
                        "result_format='construct' requires a CONSTRUCT or "
                        "DESCRIBE query"
                    )
                return {
                    "success": True,
                    "bindings": [],
                    "variables": [],
                    "metadata": {"query": query, "boolean": bool(result)},
                }

            if isinstance(result, self._oxigraph.QueryTriples):
                if result_format == "bindings":
                    raise ValidationError(
                        "result_format='bindings' cannot be used with a "
                        "CONSTRUCT or DESCRIBE query"
                    )
                triples = []
                for triple in result:
                    metadata = self._literal_metadata(triple.object)
                    triples.append(
                        (
                            self._term_value(triple.subject),
                            self._term_value(triple.predicate),
                            self._term_value(triple.object),
                            metadata,
                        )
                    )
                return {
                    "success": True,
                    "bindings": [],
                    "variables": [],
                    "triples": triples,
                    "metadata": {
                        "query": query,
                        "result_format": "construct",
                    },
                }

            raise ProcessingError(
                f"Unsupported Oxigraph query result: {type(result).__name__}"
            )
        except (ValidationError, ProcessingError):
            raise
        except Exception as exc:
            self.logger.error(f"Oxigraph SPARQL query failed: {exc}")
            raise ProcessingError(f"Oxigraph SPARQL query failed: {exc}") from exc

    def flush(self) -> None:
        """Flush pending writes to disk for persistent stores."""
        self.store.flush()

    def _to_quad(self, triplet: Triplet, graph_name: Any) -> Any:
        ox = self._oxigraph
        return ox.Quad(
            ox.NamedNode(triplet.subject),
            ox.NamedNode(triplet.predicate),
            self._object_from_triplet(triplet),
            graph_name,
        )

    def _object_from_triplet(self, triplet: Triplet) -> Any:
        if self._is_uri_value(triplet.object):
            return self._oxigraph.NamedNode(self._unwrap_iri(triplet.object))

        metadata = triplet.metadata or {}
        language = metadata.get("lang") or metadata.get("language")
        datatype = metadata.get("datatype") or metadata.get("literal_datatype")
        if language:
            return self._oxigraph.Literal(str(triplet.object), language=str(language))
        if datatype:
            datatype_iri = self._unwrap_iri(
                sparql_escaping.resolve_datatype_iri(str(datatype))
            )
            return self._oxigraph.Literal(
                str(triplet.object),
                datatype=self._oxigraph.NamedNode(datatype_iri),
            )
        return self._oxigraph.Literal(str(triplet.object))

    def _object_from_value(self, value: str) -> Any:
        if self._is_uri_value(value):
            return self._oxigraph.NamedNode(self._unwrap_iri(value))
        return self._oxigraph.Literal(str(value))

    def _graph_name(self, graph: Optional[str]) -> Any:
        if graph is None:
            return self._oxigraph.DefaultGraph()
        return self._oxigraph.NamedNode(str(graph))

    def _quad_to_triplet(self, quad: Any) -> Triplet:
        metadata = {"source": "oxigraph"}
        metadata.update(self._literal_metadata(quad.object))
        return Triplet(
            subject=self._term_value(quad.subject),
            predicate=self._term_value(quad.predicate),
            object=self._term_value(quad.object),
            metadata=metadata,
        )

    def _term_to_binding(self, term: Any) -> Dict[str, str]:
        if isinstance(term, self._oxigraph.NamedNode):
            return {"type": "uri", "value": term.value}
        if isinstance(term, self._oxigraph.BlankNode):
            return {"type": "bnode", "value": term.value}
        if isinstance(term, self._oxigraph.Literal):
            binding = {"type": "literal", "value": term.value}
            if term.language is not None:
                binding["xml:lang"] = term.language
            elif term.datatype.value != self._XSD_STRING:
                binding["datatype"] = term.datatype.value
            return binding
        return {"type": "literal", "value": str(term)}

    def _literal_metadata(self, term: Any) -> Dict[str, str]:
        if not isinstance(term, self._oxigraph.Literal):
            return {}
        metadata = {}
        if term.language is not None:
            metadata["language"] = term.language
        elif term.datatype.value != self._XSD_STRING:
            metadata["datatype"] = term.datatype.value
        return metadata

    def _term_value(self, term: Any) -> str:
        if isinstance(
            term,
            (
                self._oxigraph.NamedNode,
                self._oxigraph.BlankNode,
                self._oxigraph.Literal,
            ),
        ):
            return term.value
        return str(term)

    @staticmethod
    def _unwrap_iri(value: str) -> str:
        if value.startswith("<") and value.endswith(">"):
            return value[1:-1]
        return value

    @staticmethod
    def _is_uri_value(value: str) -> bool:
        if not isinstance(value, str) or not value:
            return False
        if value.startswith("<") and value.endswith(">"):
            return True
        parsed = urlparse(value)
        return parsed.scheme in {"http", "https", "urn"} and not re.search(r"\s", value)
