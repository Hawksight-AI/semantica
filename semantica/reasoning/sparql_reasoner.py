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

import json
import time
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

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
        """
        tracking_id = self.progress_tracker.start_tracking(
            module="reasoning",
            submodule="SPARQLReasoner",
            message="Inferring additional results from query results",
        )

        try:
            inferred_bindings = list(query_results.bindings)

            # Apply inference rules
            if self.enable_inference:
                self.progress_tracker.update_tracking(
                    tracking_id, message="Applying inference rules..."
                )
                rules = self.reasoner.rules

                for rule in rules:
                    # Check if rule can be applied to results
                    new_bindings = self._apply_rule_to_results(
                        rule, query_results.bindings
                    )
                    inferred_bindings.extend(new_bindings)

            # Remove duplicates
            self.progress_tracker.update_tracking(
                tracking_id, message="Removing duplicate bindings..."
            )
            unique_bindings = self._deduplicate_bindings(inferred_bindings)

            inferred_count = len(unique_bindings) - len(query_results.bindings)
            result = SPARQLQueryResult(
                bindings=unique_bindings,
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
        new_binding = binding.copy()

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

    def _deduplicate_bindings(
        self, bindings: List[Dict[str, Any]]
    ) -> List[Dict[str, Any]]:
        """Remove duplicate bindings."""
        seen = set()
        unique = []

        for binding in bindings:
            # Create hashable representation
            binding_key = tuple(sorted(binding.items()))
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
        parse. Inference is applied to the *results* instead, through
        ``infer_results()``.

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
        ``result``: the binding dicts and the metadata dict are copied
        one level deep, so mutating either object leaves the other
        intact.
        """
        metadata = dict(result.metadata)
        if cached is not None:
            metadata["cached"] = cached
        return SPARQLQueryResult(
            bindings=[dict(binding) for binding in result.bindings],
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
        """Normalize a store result (QueryResult or dict) into
        SPARQLQueryResult."""
        if isinstance(raw_result, SPARQLQueryResult):
            return raw_result

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
        from the store's triplets."""
        try:
            from rdflib import Graph, Literal, URIRef
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
            subject = self._triplet_value(triplet, "subject")
            predicate = self._triplet_value(triplet, "predicate")
            obj = self._triplet_value(triplet, "object")
            if not subject or not predicate or obj is None:
                continue
            if obj.startswith(
                ("http://", "https://", "urn:", "mailto:",
                 "ftp://", "file://", "tag:", "doi:")
            ):
                graph.add((URIRef(subject), URIRef(predicate), URIRef(obj)))
            else:
                graph.add((URIRef(subject), URIRef(predicate), Literal(obj)))

        try:
            raw_result = graph.query(query)
        except Exception as e:
            raise ValidationError(f"Invalid SPARQL query: {e}") from e

        execution_time = time.time() - start_time
        result = self._rdflib_result_to_sparql_result(raw_result)
        result.metadata["execution_time"] = execution_time
        return result

    @staticmethod
    def _triplet_value(triplet: Any, key: str) -> Optional[str]:
        """Read a field from a Triplet object or a plain dict.

        Missing fields return None; present values are coerced with
        ``str()`` so that non-string values (e.g. numeric IDs) are not
        silently dropped from the fallback graph.
        """
        getter = getattr(triplet, "get", None)
        if callable(getter):
            value = getter(key)
        else:
            value = getattr(triplet, key, None)
        return None if value is None else str(value)

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
