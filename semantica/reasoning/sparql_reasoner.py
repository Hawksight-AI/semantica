"""
SPARQL Reasoner Module

This module provides SPARQL-based reasoning capabilities for knowledge graph
query answering, including query expansion, inference rule integration, and
query optimization.

Key Features:
    - SPARQL query reasoning and execution
    - Inference rule integration
    - Query optimization and caching
    - Query expansion
    - Performance optimization
    - Error handling and recovery
    - Triplet store integration

Main Classes:
    - SPARQLReasoner: SPARQL-based reasoning engine
    - SPARQLQueryResult: Dataclass for SPARQL query results

Example Usage:
    >>> from semantica.reasoning import SPARQLReasoner
    >>> reasoner = SPARQLReasoner()
    >>> query = "SELECT ?s ?p ?o WHERE { ?s ?p ?o }"
    >>> result = reasoner.query(query)
    >>> expanded = reasoner.expand_query(query, rules)

Author: Semantica Contributors
License: MIT
"""

import copy
import json
import time
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Tuple

from ..utils.exceptions import ProcessingError, ValidationError
from ..utils.logging import get_logger
from ..utils.progress_tracker import get_progress_tracker
from .reasoner import Reasoner, Rule


@dataclass
class SPARQLQueryResult:
    """SPARQL query result."""

    bindings: List[Dict[str, Any]]
    variables: List[str]
    metadata: Dict[str, Any] = field(default_factory=dict)


class SPARQLReasoner:
    """
    SPARQL-based reasoning engine.

    • SPARQL query reasoning and execution
    • Inference rule integration
    • Query optimization and caching
    • Performance optimization
    • Error handling and recovery
    • Advanced SPARQL features
    """

    def __init__(self, config: Optional[Dict[str, Any]] = None, **kwargs):
        """
        Initialize SPARQL reasoner.

        Args:
            config: Configuration dictionary
            **kwargs: Additional configuration options:
                - triplet_store: Triplet store connection
                - enable_inference: Enable inference rules
        """
        self.logger = get_logger("sparql_reasoner")
        self.config = config or {}
        self.config.update(kwargs)

        # Initialize progress tracker
        self.progress_tracker = get_progress_tracker()
        # Ensure progress tracker is enabled
        if not self.progress_tracker.enabled:
            self.progress_tracker.enabled = True

        self.reasoner = Reasoner(**self.config)
        self.triplet_store = self.config.get("triplet_store")
        self.enable_inference = self.config.get("enable_inference", True)

        # Cache for executed queries, keyed by (query, options) and
        # populated by execute_query(); cleared via clear_cache().
        self.query_cache: Dict[str, Any] = {}

    def expand_query(self, query: str, **options) -> str:
        """
        Expand SPARQL query with inference rules.

        Args:
            query: Original SPARQL query
            **options: Additional options

        Returns:
            Expanded query
        """
        tracking_id = self.progress_tracker.start_tracking(
            module="reasoning",
            submodule="SPARQLReasoner",
            message="Expanding SPARQL query with inference rules",
        )

        try:
            if not self.enable_inference:
                self.progress_tracker.stop_tracking(
                    tracking_id,
                    status="completed",
                    message="Inference disabled, returning original query",
                )
                return query

            # Parse query to find patterns
            self.progress_tracker.update_tracking(
                tracking_id, message="Parsing query patterns..."
            )
            expanded_query = query

            # Get inference rules
            self.progress_tracker.update_tracking(
                tracking_id, message="Getting inference rules..."
            )
            rules = self.reasoner.rules

            # Add inferred patterns based on rules
            self.progress_tracker.update_tracking(
                tracking_id,
                message=f"Converting {len(rules)} rules to SPARQL patterns...",
            )
            for rule in rules:
                # Convert rule to SPARQL pattern
                sparql_pattern = self._rule_to_sparql(rule)
                if sparql_pattern:
                    # Add to query (basic implementation)
                    expanded_query += f"\n# Inference: {rule.name}\n{sparql_pattern}"

            self.progress_tracker.stop_tracking(
                tracking_id,
                status="completed",
                message=f"Expanded query with {len(rules)} inference rules",
            )
            return expanded_query

        except Exception as e:
            self.progress_tracker.stop_tracking(
                tracking_id, status="failed", message=str(e)
            )
            raise

    def _rule_to_sparql(self, rule: Rule) -> Optional[str]:
        """Convert rule to SPARQL pattern."""
        # Basic conversion - can be enhanced
        try:
            # Extract conditions as SPARQL patterns
            patterns = []
            for condition in rule.conditions:
                # Simple pattern matching
                if " is_a " in condition:
                    parts = condition.split(" is_a ")
                    if len(parts) == 2:
                        var = parts[0].strip()
                        if var.startswith("?"):
                            var = var[1:]
                        class_type = parts[1].strip()
                        patterns.append(f"?{var} a :{class_type} .")

            # Conclusion
            if " is_a " in rule.conclusion:
                parts = rule.conclusion.split(" is_a ")
                if len(parts) == 2:
                    var = parts[0].strip()
                    if var.startswith("?"):
                        var = var[1:]
                    class_type = parts[1].strip()
                    conclusion_pattern = f"?{var} a :{class_type} ."

                    # Combine into SPARQL pattern
                    if patterns:
                        return f"{' '.join(patterns)} => {conclusion_pattern}"

        except Exception as e:
            self.logger.warning(f"Could not convert rule to SPARQL: {e}")

        return None

    def infer_results(
        self, query_results: SPARQLQueryResult, **options
    ) -> SPARQLQueryResult:
        """
        Infer additional results from query results.

        Args:
            query_results: Original query results
            **options: Additional options

        Returns:
            Results with inferences

        Note:
            The original bindings are preserved verbatim, in order and
            with their duplicates: SPARQL result rows form a bag, and a
            query without DISTINCT keeps repeated solutions. Only the
            *newly inferred* rows are de-duplicated (against each other
            and against the originals) before being appended. This also
            guarantees ``inferred_count`` reflects what inference added,
            rather than shrinking (even below zero) when the original
            rows contained duplicates.
        """
        tracking_id = self.progress_tracker.start_tracking(
            module="reasoning",
            submodule="SPARQLReasoner",
            message="Inferring additional results from query results",
        )

        try:
            original_bindings = list(query_results.bindings)
            new_bindings: List[Dict[str, Any]] = []

            # Apply inference rules
            if self.enable_inference:
                self.progress_tracker.update_tracking(
                    tracking_id, message="Applying inference rules..."
                )
                rules = self.reasoner.rules

                for rule in rules:
                    # Check if rule can be applied to results
                    rule_bindings = self._apply_rule_to_results(
                        rule, query_results.bindings
                    )
                    new_bindings.extend(rule_bindings)

            # De-duplicate only the inferred rows, against each other
            # and against the originals (which are kept as-is).
            self.progress_tracker.update_tracking(
                tracking_id, message="Removing duplicate bindings..."
            )
            seen = {self._binding_key(b) for b in original_bindings}
            added_bindings = []
            for binding in new_bindings:
                key = self._binding_key(binding)
                if key not in seen:
                    seen.add(key)
                    added_bindings.append(binding)

            final_bindings = original_bindings + added_bindings
            inferred_count = len(added_bindings)
            result = SPARQLQueryResult(
                bindings=final_bindings,
                variables=query_results.variables,
                metadata={
                    **query_results.metadata,
                    "original_count": len(query_results.bindings),
                    "inferred_count": inferred_count,
                },
            )

            self.progress_tracker.stop_tracking(
                tracking_id,
                status="completed",
                message=f"Inferred {inferred_count} additional results",
            )
            return result

        except Exception as e:
            self.progress_tracker.stop_tracking(
                tracking_id, status="failed", message=str(e)
            )
            raise

    def _apply_rule_to_results(
        self, rule: Rule, bindings: List[Dict[str, Any]]
    ) -> List[Dict[str, Any]]:
        """Apply rule to query results."""
        new_bindings = []

        for binding in bindings:
            # Check if rule conditions match
            if self._match_rule_conditions(rule, binding):
                # Generate new binding from conclusion
                new_binding = self._generate_binding_from_conclusion(rule, binding)
                if new_binding:
                    new_bindings.append(new_binding)

        return new_bindings

    def _match_rule_conditions(self, rule: Rule, binding: Dict[str, Any]) -> bool:
        """Check if rule conditions match binding."""
        for condition in rule.conditions:
            # Simple matching - can be enhanced
            if " is_a " in condition:
                parts = condition.split(" is_a ")
                if len(parts) == 2:
                    var = parts[0].strip().replace("?", "")
                    class_type = parts[1].strip()

                    # Check if binding has matching type
                    if var in binding:
                        value = binding[var]
                        # Check type (simplified)
                        if not self._has_type(value, class_type):
                            return False

        return True

    def _has_type(self, value: Any, class_type: str) -> bool:
        """Check if value has type (simplified)."""
        # This is a placeholder - in practice would check against knowledge graph
        return True

    def _generate_binding_from_conclusion(
        self, rule: Rule, binding: Dict[str, Any]
    ) -> Optional[Dict[str, Any]]:
        """Generate new binding from rule conclusion."""
        # Deep copy: binding values may themselves be mutable dicts
        # (SPARQL JSON result rows), which must not be shared with the
        # inferred row.
        new_binding = copy.deepcopy(binding)

        # Parse conclusion
        if " is_a " in rule.conclusion:
            parts = rule.conclusion.split(" is_a ")
            if len(parts) == 2:
                var = parts[0].strip().replace("?", "")
                class_type = parts[1].strip()

                # Add type information
                if var in new_binding:
                    new_binding[f"{var}_type"] = class_type

        return new_binding

    @staticmethod
    def _binding_key(binding: Dict[str, Any]) -> Tuple:
        """Build a hashable key for a binding row.

        Binding values are not guaranteed to be hashable: stores that
        follow the SPARQL JSON results format return nested dicts
        (``{"type": ..., "value": ...}``) for each value. Such values
        are normalized to ``repr()`` so they can participate in the
        deduplication key (issue: unhashable-dict TypeError).
        """
        normalized = tuple(
            (str(name), repr(binding[name])) for name in sorted(binding, key=str)
        )
        return normalized

    def _deduplicate_bindings(
        self, bindings: List[Dict[str, Any]]
    ) -> List[Dict[str, Any]]:
        """Remove duplicate bindings."""
        seen = set()
        unique = []

        for binding in bindings:
            binding_key = self._binding_key(binding)
            if binding_key not in seen:
                seen.add(binding_key)
                unique.append(binding)

        return unique

    def execute_query(self, query: str, **options) -> SPARQLQueryResult:
        """
        Execute SPARQL query with reasoning.

        The query is executed against the configured triplet store via its
        ``execute_query`` method (validation and optimization are handled
        by the store's query engine). When the store cannot execute SPARQL
        natively -- no ``execute_query`` method, or a backend without
        ``execute_sparql`` -- the triplets are pulled via ``get_triplets``
        into an in-memory rdflib graph and the query is executed locally.

        Without a triplet store the query is refused loudly instead of
        returning an empty result set that callers would read as "no
        matches" (issue #1083).

        Note: the *original* query is executed, not the output of
        ``expand_query()``: that output annotates the query with rule
        comments and ``=>`` pseudo-patterns that no SPARQL engine can
        parse. Inference still runs without rewriting the query:

        * on the rdflib fallback path, ``is_a`` rules are materialized
          into the in-memory graph *before* the query executes, so
          inferred triples participate in pattern matching;
        * afterwards, ``infer_results()`` applies the rules to the
          *results* as well (rules that could not be materialized are
          covered by this step).

        Args:
            query: SPARQL query string
            **options: Additional options forwarded to the triplet
                store (e.g. ``graph``, ``graphs``). They only apply
                on the native execution path; the rdflib fallback
                always queries the full triplet set (a warning is
                logged when options are dropped).

        Returns:
            SPARQLQueryResult with bindings and variables

        Raises:
            ProcessingError: No triplet store configured, or the store
                supports neither SPARQL execution nor triplet retrieval
            ValidationError: The query is not valid SPARQL

        Note:
            Results are cached per ``(query, options)``. The cache has
            no invalidation: it does not observe changes to the store's
            triplets or to the inference rules, so call
            ``clear_cache()`` after mutating either.
        """
        tracking_id = self.progress_tracker.start_tracking(
            module="reasoning",
            submodule="SPARQLReasoner",
            message="Executing SPARQL query",
        )

        try:
            if self.triplet_store is None:
                raise ProcessingError(
                    "SPARQLReasoner.execute_query() requires a triplet "
                    "store: pass triplet_store=... when constructing the "
                    "reasoner. Returning an empty result set would be "
                    "misread as 'no matches', so the query is refused "
                    "instead."
                )

            cache_key = self._cache_key(query, options)
            if cache_key in self.query_cache:
                cached_result = self.query_cache[cache_key]
                self.progress_tracker.stop_tracking(
                    tracking_id,
                    status="completed",
                    message="Returned cached result",
                )
                return self._copy_result(cached_result, cached=True)
            self.progress_tracker.update_tracking(
                tracking_id, message="Executing query on triplet store..."
            )
            result = self._execute_on_store(query, **options)

            if self.enable_inference and self.reasoner.rules:
                self.progress_tracker.update_tracking(
                    tracking_id, message="Applying inference rules..."
                )
                result = self.infer_results(result)

            result.metadata.setdefault("cached", False)
            # Store a private copy: mutating the returned result (or the
            # cached one) must never corrupt the other.
            self.query_cache[cache_key] = self._copy_result(result)

            self.progress_tracker.stop_tracking(
                tracking_id,
                status="completed",
                message=f"Query executed: {len(result.bindings)} results",
            )
            return result

        except (ValidationError, ProcessingError) as e:
            self.progress_tracker.stop_tracking(
                tracking_id, status="failed", message=str(e)
            )
            raise
        except Exception as e:
            self.progress_tracker.stop_tracking(
                tracking_id, status="failed", message=str(e)
            )
            raise ProcessingError(f"Query execution failed: {e}") from e

    def clear_cache(self) -> None:
        """Clear the query cache populated by execute_query()."""
        self.query_cache.clear()

    # ── Execution-path helpers ────────────────────────────────────────────

    def _cache_key(self, query: str, options: Dict[str, Any]) -> str:
        """Build a deterministic cache key from the query and its options."""
        try:
            options_part = json.dumps(options, sort_keys=True, default=str)
        except (TypeError, ValueError):
            options_part = str(sorted(options.items(), key=str))
        return f"{query}\n{options_part}"

    @staticmethod
    def _copy_result(
        result: SPARQLQueryResult, cached: Optional[bool] = None
    ) -> SPARQLQueryResult:
        """Return a copy whose mutable containers are not shared with
        ``result``.

        The copy is deep: binding values and metadata entries can be
        arbitrarily nested containers themselves (SPARQL JSON results
        use ``{"type": ..., "value": ...}`` dicts per value, and
        ``metadata["triples"]`` holds lists of lists). A shallow copy
        would leave those nested structures shared, so mutation of
        one result could still reach the other through them.
        ``cached`` (when given) is recorded on the copy only.
        """
        metadata = copy.deepcopy(result.metadata)
        if cached is not None:
            metadata["cached"] = cached
        return SPARQLQueryResult(
            bindings=[copy.deepcopy(binding) for binding in result.bindings],
            variables=list(result.variables),
            metadata=metadata,
        )

    def _execute_on_store(self, query: str, **options) -> SPARQLQueryResult:
        """Execute the query through the triplet store, with fallback."""
        store = self.triplet_store
        execute = getattr(store, "execute_query", None)

        # Only fall back when we can positively determine that the store
        # backend cannot execute SPARQL; duck-typed stores without a
        # ``_store_backend`` attribute are trusted to handle the query.
        backend = getattr(store, "_store_backend", None)
        backend_blocks_sparql = backend is not None and not callable(
            getattr(backend, "execute_sparql", None)
        )

        if callable(execute) and not backend_blocks_sparql:
            raw_result = execute(query, **options)
            return self._coerce_query_result(raw_result)

        self.logger.info(
            "Triplet store has no native SPARQL execution path; falling "
            "back to an in-memory rdflib graph."
        )
        if options:
            self.logger.warning(
                "Falling back to the in-memory rdflib graph, where query "
                "options %s are not applied: the fallback always queries "
                "the full triplet set." % (options,)
            )
        return self._execute_on_rdflib_graph(query)

    def _coerce_query_result(self, raw_result: Any) -> SPARQLQueryResult:
        """Normalize a store result (QueryResult, dict, or list of
        binding rows) into SPARQLQueryResult."""
        if isinstance(raw_result, SPARQLQueryResult):
            return raw_result

        if isinstance(raw_result, (list, tuple)):
            # Some stores hand back the raw solution sequence as a list
            # of binding dicts (the ``bindings`` rows of the SPARQL JSON
            # results format). Without this branch the list would fall
            # through to the generic object path below, where
            # ``getattr(result, "bindings")`` finds nothing and the rows
            # are silently coerced into an empty result.
            bindings = [
                dict(item) for item in raw_result if isinstance(item, dict)
            ]
            if len(bindings) != len(raw_result):
                self.logger.warning(
                    "Triplet store execute_query() returned a sequence "
                    "with %d non-dict items; they were dropped while "
                    "coercing the result to SPARQLQueryResult.",
                    len(raw_result) - len(bindings),
                )
            variables: List[str] = []
            for binding in bindings:
                for name in binding:
                    name = str(name)
                    if name not in variables:
                        variables.append(name)
            return SPARQLQueryResult(
                bindings=bindings,
                variables=variables,
            )

        if isinstance(raw_result, dict):
            bindings = raw_result.get("bindings") or []
            variables = raw_result.get("variables") or []
            metadata = dict(raw_result.get("metadata") or {})
            triples = raw_result.get("triples") or []
            execution_time = raw_result.get("execution_time") or 0.0
        else:
            bindings = getattr(raw_result, "bindings", None) or []
            variables = getattr(raw_result, "variables", None) or []
            metadata = dict(getattr(raw_result, "metadata", None) or {})
            triples = getattr(raw_result, "triples", None) or []
            execution_time = (
                getattr(raw_result, "execution_time", 0.0) or 0.0
            )

        result = SPARQLQueryResult(
            bindings=list(bindings),
            variables=list(variables),
            metadata=metadata,
        )
        if execution_time:
            result.metadata["execution_time"] = execution_time
        if triples:
            result.metadata["triples"] = [tuple(t) for t in triples]
        return result

    def _execute_on_rdflib_graph(self, query: str) -> SPARQLQueryResult:
        """Execute the query locally on an in-memory rdflib graph built
        from the store's triplets.

        Inference (``is_a`` rules) is materialized into the graph
        *before* the query runs, so triples that only exist through
        inference can still satisfy the query's patterns. Rules that
        cannot be expressed as ``is_a`` triples are left to
        ``infer_results()``, which runs on the *results* instead.
        """
        try:
            from rdflib import Graph
        except ImportError as e:
            raise ProcessingError(
                "rdflib is required for the in-memory SPARQL fallback."
            ) from e

        get_triplets = getattr(self.triplet_store, "get_triplets", None)
        if not callable(get_triplets):
            raise ProcessingError(
                "Triplet store supports neither SPARQL execution "
                "(execute_query) nor triplet retrieval (get_triplets); "
                "cannot execute the query."
            )

        start_time = time.time()
        graph = Graph()
        for triplet in get_triplets():
            subject = self._subject_term(triplet)
            predicate = self._predicate_term(triplet)
            obj = self._object_term(triplet)
            if subject is None or predicate is None or obj is None:
                continue
            graph.add((subject, predicate, obj))

        if len(graph) == 0:
            # An empty graph yields a result set ("no bindings", or
            # false for ASK) that callers would misread as "no
            # matches" when it really means "no data": refuse loudly
            # instead, mirroring the no-store behaviour (issue #1083).
            raise ProcessingError(
                "The in-memory rdflib fallback graph is empty: "
                "get_triplets() returned no usable triples. Executing "
                "the query would return a result set misread as 'no "
                "matches', so the query is refused instead."
            )

        inferred_triples = 0
        if self.enable_inference and self.reasoner.rules:
            inferred_triples = self._materialize_inference(graph)

        try:
            raw_result = graph.query(query)
        except Exception as e:
            raise ValidationError(f"Invalid SPARQL query: {e}") from e

        execution_time = time.time() - start_time
        result = self._rdflib_result_to_sparql_result(raw_result)
        result.metadata["execution_time"] = execution_time
        if inferred_triples:
            result.metadata["inferred_triples"] = inferred_triples
        return result

    # ── rdflib term construction ───────────────────────────────────────

    _URI_PREFIXES = (
        "http://",
        "https://",
        "urn:",
        "mailto:",
        "ftp://",
        "file://",
        "tag:",
        "doi:",
    )

    @classmethod
    def _triplet_field(cls, triplet: Any, key: str) -> Any:
        """Read a field from a Triplet object or a plain dict, *without*
        coercing it to ``str``.

        Values that are already native RDF terms (``URIRef`` /
        ``BNode`` / ``Literal``) must survive untouched so the fallback
        graph keeps their types; ``str()`` here would degrade them to
        plain literals. ``str()`` coercion is applied later, only for
        values that genuinely need it.
        """
        getter = getattr(triplet, "get", None)
        if callable(getter):
            value = getter(key)
        else:
            value = getattr(triplet, key, None)
        return value

    @classmethod
    def _triplet_metadata(cls, triplet: Any) -> Dict[str, Any]:
        """Return the triplet's metadata dict (empty when absent)."""
        metadata = cls._triplet_field(triplet, "metadata")
        return metadata if isinstance(metadata, dict) else {}

    @classmethod
    def _node_term(cls, triplet: Any, key: str, blank_prefix_ok: bool = False):
        """Build the subject or predicate term for the fallback graph.

        Native RDF terms pass through; strings become ``URIRef`` (a
        ``_:``-prefixed string becomes a blank node when
        ``blank_prefix_ok`` -- blank nodes are only legal as subjects
        or objects, not predicates). Non-string values are coerced to
        their string form, mirroring the previous ``str()`` behaviour.
        """
        from rdflib import BNode, Literal, URIRef

        value = cls._triplet_field(triplet, key)
        if value is None or isinstance(value, (URIRef, BNode)):
            return value
        if isinstance(value, Literal):
            # Literals are not legal subjects/predicates; degrade to a
            # URIRef of the literal's text.
            return URIRef(str(value))
        if blank_prefix_ok and isinstance(value, str) and value.startswith("_:"):
            return BNode(value[2:])
        return URIRef(str(value))

    @classmethod
    def _subject_term(cls, triplet: Any):
        """Build the subject term (blank-node prefix allowed)."""
        return cls._node_term(triplet, "subject", blank_prefix_ok=True)

    @classmethod
    def _predicate_term(cls, triplet: Any):
        """Build the predicate term (always a URIRef/term, no blanks)."""
        return cls._node_term(triplet, "predicate")

    @classmethod
    def _object_term(cls, triplet: Any):
        """Build the object term, preserving RDF typing information.

        Values that are already native RDF terms pass through
        unchanged. Otherwise the term is chosen by:

        * ``_:``-prefixed string -> blank node
        * URI-looking string (known scheme prefixes) -> ``URIRef``
        * triplet metadata ``lang``/``language`` -> language-tagged
          ``Literal``
        * triplet metadata ``datatype``/``literal_datatype`` -> typed
          ``Literal`` (resolved through ``resolve_datatype_iri``)
        * anything else -> plain ``Literal`` of ``str(value)``

        This mirrors the triplet-store behaviour (see
        ``oxigraph_store._object_from_triplet``) so the fallback graph
        answers typed-literal and language-tag queries the same way
        the native backend would, instead of flattening every object
        to an untyped literal.
        """
        from rdflib import BNode, Literal, URIRef

        value = cls._triplet_field(triplet, "object")
        if value is None or isinstance(value, (URIRef, BNode, Literal)):
            return value
        if isinstance(value, str) and value.startswith("_:"):
            return BNode(value[2:])
        if isinstance(value, str) and value.startswith(cls._URI_PREFIXES):
            return URIRef(value)

        metadata = cls._triplet_metadata(triplet)
        language = metadata.get("lang") or metadata.get("language")
        datatype = metadata.get("datatype") or metadata.get("literal_datatype")
        text = str(value)
        if language:
            return Literal(text, lang=str(language))
        if datatype:
            datatype_iri = cls._resolve_datatype_iri(str(datatype))
            if datatype_iri:
                return Literal(text, datatype=URIRef(datatype_iri))
        return Literal(text)

    @staticmethod
    def _resolve_datatype_iri(datatype: str) -> Optional[str]:
        """Resolve a datatype name/IRI (e.g. ``xsd:integer``) to a bare
        IRI string, or ``None`` when it cannot be resolved (the value
        then stays an untyped literal instead of failing the query)."""
        try:
            from ..triplet_store.sparql_escaping import resolve_datatype_iri
        except ImportError:
            return None
        try:
            iri = resolve_datatype_iri(datatype)
        except (ValueError, TypeError):
            return None
        return iri.strip("<>") if isinstance(iri, str) else None

    # ── inference materialization (fallback path) ─────────────────────

    @staticmethod
    def _parse_is_a(pattern: Any) -> Optional[Tuple[str, str]]:
        """Parse ``"?x is_a Class"`` into ``(var, class)``; None when the
        pattern does not follow that form."""
        if not isinstance(pattern, str):
            return None
        if " is_a " not in pattern:
            return None
        var, class_name = pattern.split(" is_a ", 1)
        var = var.strip().lstrip("?").strip()
        class_name = class_name.strip()
        if not var or not class_name:
            return None
        return var, class_name

    def _materialize_inference(self, graph: Any) -> int:
        """Materialize ``is_a`` inference rules into ``graph``.

        Rules of the form ``IF ?x is_a Sub THEN ?x is_a Super`` are
        turned into extra ``rdf:type``-style triples *before* the query
        runs, so matches that only exist through inference can satisfy
        the query's WHERE clause (the query itself is never rewritten:
        ``expand_query`` output is not executable SPARQL). Rules whose
        conditions or conclusion do not fit the ``is_a`` form, or whose
        variables do not line up, are skipped -- they are still handled
        at the result level by ``infer_results()``.

        Returns the number of inferred triples added.
        """
        rules = list(self.reasoner.rules)
        added_total = 0
        # Fixpoint iteration: a rule chain (A is_a B, B is_a C) may only
        # enable another rule after the first one fires. At most one
        # productive pass per rule is needed.
        for _ in range(max(1, len(rules))):
            added_this_pass = 0
            for rule in rules:
                added_this_pass += self._materialize_rule(graph, rule)
            added_total += added_this_pass
            if added_this_pass == 0:
                break
        return added_total

    def _materialize_rule(self, graph: Any, rule: Rule) -> int:
        """Add the triples inferred by one ``is_a`` rule; 0 when the
        rule cannot be materialized."""
        conclusion = self._parse_is_a(rule.conclusion)
        if conclusion is None:
            return 0
        conclusion_var, conclusion_class = conclusion

        # All conditions must be ``is_a`` constraints on the conclusion
        # variable for the rule to be expressible as triple rewrites.
        constraints = []
        for condition in rule.conditions or []:
            parsed = self._parse_is_a(condition)
            if parsed is None or parsed[0] != conclusion_var:
                return 0
            constraints.append(parsed[1])
        if not constraints:
            return 0

        added = 0
        for subject, predicate, obj in list(graph):
            if not all(
                self._term_matches_class(obj, class_name)
                for class_name in constraints
            ):
                continue
            if self._term_matches_class(obj, conclusion_class):
                continue
            inferred = (subject, predicate, self._term_for_class(obj, conclusion_class))
            if inferred not in graph:
                graph.add(inferred)
                added += 1
        return added

    @staticmethod
    def _term_matches_class(term: Any, class_name: str) -> bool:
        """Whether ``term`` denotes ``class_name`` (exact text, or a
        URI whose local name is ``class_name``)."""
        text = str(term)
        if text == class_name:
            return True
        for separator in ("#", "/"):
            index = text.rfind(separator)
            if index != -1 and text[index + 1:] == class_name:
                return True
        return False

    @staticmethod
    def _term_for_class(term: Any, class_name: str) -> Any:
        """Build the term for ``class_name`` in the namespace of
        ``term`` when possible, else a bare ``URIRef``/``Literal``."""
        from rdflib import Literal, URIRef

        if isinstance(term, Literal):
            return Literal(class_name)
        text = str(term)
        for separator in ("#", "/"):
            index = text.rfind(separator)
            if index != -1:
                return URIRef(text[: index + 1] + class_name)
        return URIRef(class_name)

    @staticmethod
    def _rdflib_result_to_sparql_result(
        raw_result: Any,
    ) -> SPARQLQueryResult:
        """Convert an rdflib query result into SPARQLQueryResult."""
        result_type = getattr(raw_result, "type", None) or "SELECT"
        metadata = {"executed_via": "rdflib_in_memory"}

        if result_type in ("CONSTRUCT", "DESCRIBE"):
            triples_graph = getattr(raw_result, "graph", None) or raw_result
            triples = [(str(s), str(p), str(o)) for s, p, o in triples_graph]
            return SPARQLQueryResult(
                bindings=[],
                variables=[],
                metadata={
                    **metadata,
                    "result_type": result_type,
                    "triples": triples,
                },
            )

        if result_type == "ASK":
            ask_value = getattr(raw_result, "askAnswer", None)
            if ask_value is None:
                ask_value = getattr(raw_result, "boolean", None)
            if ask_value is None:
                ask_value = bool(raw_result)
            return SPARQLQueryResult(
                bindings=[],
                variables=[],
                metadata={
                    **metadata,
                    "result_type": "ASK",
                    "boolean": bool(ask_value),
                },
            )

        # SELECT
        variables = [
            str(var) for var in (getattr(raw_result, "vars", None) or [])
        ]
        bindings = []
        for row in raw_result:
            binding = {}
            for var in (getattr(raw_result, "vars", None) or []):
                value = row.get(var) if hasattr(row, "get") else None
                if value is not None:
                    binding[str(var)] = str(value)
            bindings.append(binding)
        return SPARQLQueryResult(
            bindings=bindings,
            variables=variables,
            metadata={**metadata, "result_type": "SELECT"},
        )

    def add_inference_rule(self, rule_definition: str, **options) -> Rule:
        """Add inference rule."""
        return self.reasoner.add_rule(rule_definition)
