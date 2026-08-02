"""
Query Engine Module

This module provides comprehensive SPARQL query execution and optimization
for triplet store operations, including query planning, caching, and performance
monitoring.

Key Features:
    - SPARQL query execution and optimization
    - Query planning and caching
    - Result processing and formatting
    - Performance monitoring and profiling
    - Query validation
    - Multi-store query support
    - Query history tracking

Main Classes:
    - QueryEngine: Main query execution and optimization coordinator
    - QueryResult: SPARQL query result representation dataclass
    - QueryPlan: Query execution plan representation dataclass

Example Usage:
    >>> from semantica.triplet_store import QueryEngine
    >>> engine = QueryEngine(enable_caching=True, enable_optimization=True)
    >>> result = engine.execute_query(sparql_query, store_backend)
    >>> plan = engine.plan_query(sparql_query)
    >>> stats = engine.get_query_statistics()

Author: Semantica Contributors
License: MIT
"""

import time
import re
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Dict, List, Optional

from ..utils.exceptions import ProcessingError, ValidationError
from ..utils.logging import get_logger
from ..utils.progress_tracker import get_progress_tracker


@dataclass
class QueryResult:
    """SPARQL query result."""

    bindings: List[Dict[str, Any]]
    variables: List[str]
    execution_time: float = 0.0
    metadata: Dict[str, Any] = field(default_factory=dict)
    triples: List[tuple] = field(default_factory=list)
    """Populated only for CONSTRUCT queries. Each element is a (subject,
    predicate, object, metadata) 4-tuple, taken directly from the store
    backend's execute_sparql "triples" key (see BlazegraphStore.execute_sparql
    CONSTRUCT path). subject/predicate/object are strings; metadata is a dict
    that is empty ({}) for URIs and plain untyped/unlang-tagged literals, and
    otherwise carries "datatype" and/or "language" keys for literals that
    have that information, so it is not silently lost. Empty list for all
    SELECT/ASK/DESCRIBE queries and for backends without CONSTRUCT support."""


@dataclass
class QueryPlan:
    """Query execution plan."""

    query: str
    optimized_query: str
    estimated_cost: float = 0.0
    execution_steps: List[str] = field(default_factory=list)
    metadata: Dict[str, Any] = field(default_factory=dict)


class QueryEngine:
    """
    SPARQL query execution and optimization engine.

    • SPARQL query execution and optimization
    • Query planning and caching
    • Result processing and formatting
    • Performance monitoring and profiling
    • Error handling and validation
    • Multi-store query support
    """

    def __init__(self, config: Optional[Dict[str, Any]] = None, **kwargs):
        """
        Initialize query engine.

        Args:
            config: Configuration dictionary
            **kwargs: Additional configuration options:
                - enable_caching: Enable query caching (default: True)
                - cache_size: Cache size limit
                - enable_optimization: Enable query optimization (default: True)
        """
        self.logger = get_logger("query_engine")
        self.config = config or {}
        self.config.update(kwargs)
        self.progress_tracker = get_progress_tracker()
        # Ensure progress tracker is enabled
        if not self.progress_tracker.enabled:
            self.progress_tracker.enabled = True

        self.enable_caching = self.config.get("enable_caching", True)
        self.enable_optimization = self.config.get("enable_optimization", True)
        self.cache_size = self.config.get("cache_size", 1000)

        self.query_cache: Dict[str, QueryResult] = {}
        self.query_history: List[Dict[str, Any]] = []

    def execute_query(self, query: str, store_backend: Any, **options) -> QueryResult:
        """
        Execute SPARQL query.

        Args:
            query: SPARQL query string
            store_backend: Triplet store backend instance
            **options: Additional options

        Returns:
            Query result
        """
        tracking_id = self.progress_tracker.start_tracking(
            module="triplet_store",
            submodule="QueryEngine",
            message="Executing SPARQL query",
        )

        try:
            start_time = time.time()

            supports_named_graphs = options.get("supports_named_graphs")
            if supports_named_graphs is None:
                supports_named_graphs = getattr(store_backend, "supports_named_graphs", True)

            prepared_query = self.prepare_query(
                query,
                graph=options.get("graph"),
                graphs=options.get("graphs"),
                supports_named_graphs=supports_named_graphs,
            )

            # Validate query
            self.progress_tracker.update_tracking(
                tracking_id, message="Validating query..."
            )
            if not self._validate_query(prepared_query):
                self.progress_tracker.stop_tracking(
                    tracking_id, status="failed", message="Invalid SPARQL query"
                )
                raise ValidationError("Invalid SPARQL query")

            # Check cache
            if self.enable_caching:
                self.progress_tracker.update_tracking(
                    tracking_id, message="Checking cache..."
                )
                cache_key = self._get_cache_key(prepared_query)
                if cache_key in self.query_cache:
                    self.logger.debug("Returning cached query result")
                    cached_result = self.query_cache[cache_key]
                    cached_result.metadata["cached"] = True
                    self.progress_tracker.stop_tracking(
                        tracking_id,
                        status="completed",
                        message="Returned cached result",
                    )
                    return cached_result

            # Optimize query
            if self.enable_optimization:
                self.progress_tracker.update_tracking(
                    tracking_id, message="Optimizing query..."
                )
                optimized_query = self.optimize_query(prepared_query, **options)
            else:
                optimized_query = prepared_query

            # Execute query
            self.progress_tracker.update_tracking(
                tracking_id, message="Executing query on store..."
            )
            if hasattr(store_backend, "execute_sparql"):
                result_data = store_backend.execute_sparql(optimized_query, **options)
            else:
                raise ProcessingError("Store backend does not support SPARQL execution")

            execution_time = time.time() - start_time

            result = QueryResult(
                bindings=result_data.get("bindings", []),
                variables=result_data.get("variables", []),
                execution_time=execution_time,
                triples=result_data.get("triples", []),
                metadata={
                    **result_data.get("metadata", {}),
                    "optimized": optimized_query != prepared_query,
                    "cached": False,
                    "graph": options.get("graph"),
                    "graphs": options.get("graphs") or [],
                },
            )

            # Cache result
            if self.enable_caching:
                self.progress_tracker.update_tracking(
                    tracking_id, message="Caching result..."
                )
                self._cache_result(prepared_query, result)

            # Record history
            self.query_history.append(
                {
                    "query": prepared_query,
                    "execution_time": execution_time,
                    "result_count": len(result.bindings),
                    "timestamp": datetime.now().isoformat(),
                }
            )

            self.progress_tracker.stop_tracking(
                tracking_id,
                status="completed",
                message=f"Query executed: {len(result.bindings)} results in {execution_time:.2f}s",
            )
            return result

        except (ValidationError, ProcessingError):
            raise
        except Exception as e:
            execution_time = (
                time.time() - start_time if "start_time" in locals() else 0.0
            )
            self.logger.error(f"Query execution failed: {e}")
            self.progress_tracker.stop_tracking(
                tracking_id, status="failed", message=str(e)
            )
            raise ProcessingError(f"Query execution failed: {e}")

    def prepare_query(
        self,
        query: str,
        graph: Optional[str] = None,
        graphs: Optional[List[str]] = None,
        supports_named_graphs: bool = True,
    ) -> str:
        """Prepare query with optional graph dataset clauses."""
        if not query:
            return ""

        resolved_graph = (
            graph
            or self.config.get("default_graph")
            or self.config.get("default_graph_uri")
        )
        resolved_graphs = graphs
        if resolved_graphs is None:
            resolved_graphs = self.config.get("default_graphs")

        if isinstance(resolved_graphs, str):
            resolved_graphs = [resolved_graphs]
        resolved_graphs = [g for g in (resolved_graphs or []) if g]

        if resolved_graph and resolved_graph in resolved_graphs:
            # Preserve graph as default dataset while avoiding duplicate URIs in FROM NAMED.
            resolved_graphs = [g for g in resolved_graphs if g != resolved_graph]

        if not supports_named_graphs and (resolved_graph or resolved_graphs):
            self.logger.warning(
                "Named graph options were provided but backend does not support named graphs; "
                "falling back to backend default dataset"
            )
            return query.strip()

        return self._inject_graph_clauses(
            query,
            graph=resolved_graph,
            graphs=resolved_graphs,
        )

    def _inject_graph_clauses(
        self,
        query: str,
        graph: Optional[str] = None,
        graphs: Optional[List[str]] = None,
    ) -> str:
        """Inject FROM/FROM NAMED clauses immediately before WHERE."""
        normalized_query = query.strip()
        graph_list = [g for g in (graphs or []) if g]

        if not graph and not graph_list:
            return normalized_query

        if re.search(r"\bFROM\b", normalized_query, flags=re.IGNORECASE):
            return normalized_query

        if not re.search(
            r"\b(SELECT|ASK|CONSTRUCT|DESCRIBE)\b",
            normalized_query,
            flags=re.IGNORECASE,
        ):
            return normalized_query

        where_match = re.search(r"\bWHERE\b", normalized_query, flags=re.IGNORECASE)
        if not where_match:
            return normalized_query

        dataset_clauses: List[str] = []
        if graph:
            safe_graph = self._sanitize_uri(graph)
            dataset_clauses.append(f"FROM <{safe_graph}>")

        for graph_uri in graph_list:
            safe_graph = self._sanitize_uri(graph_uri)
            dataset_clauses.append(f"FROM NAMED <{safe_graph}>")

        if not dataset_clauses:
            return normalized_query

        before_where = normalized_query[: where_match.start()].rstrip()
        where_and_after = normalized_query[where_match.start() :].lstrip()
        dataset_block = "\n".join(dataset_clauses)

        return f"{before_where}\n{dataset_block}\n{where_and_after}"

    def optimize_query(self, query: str, **options) -> str:
        """
        Optimize SPARQL query.

        Args:
            query: Original query
            **options: Optimization options

        Returns:
            Optimized query
        """
        optimized = query.strip()

        # Remove unnecessary whitespace
        optimized = " ".join(optimized.split())

        # Add LIMIT if SELECT query doesn't have one
        if "SELECT" in optimized.upper() and "LIMIT" not in optimized.upper():
            if options.get("add_limit", True):
                default_limit = options.get("default_limit", 1000)
                optimized += f" LIMIT {default_limit}"

        # Basic query rewriting
        # (More sophisticated optimization would require query parser)

        return optimized

    def plan_query(self, query: str, **options) -> QueryPlan:
        """
        Create query execution plan.

        Args:
            query: SPARQL query
            **options: Planning options

        Returns:
            Query execution plan
        """
        optimized_query = (
            self.optimize_query(query, **options) if self.enable_optimization else query
        )

        # Estimate cost (simplified)
        estimated_cost = self._estimate_query_cost(query)

        # Identify execution steps
        execution_steps = self._identify_execution_steps(query)

        return QueryPlan(
            query=query,
            optimized_query=optimized_query,
            estimated_cost=estimated_cost,
            execution_steps=execution_steps,
            metadata={"optimization_enabled": self.enable_optimization},
        )
    
    def expand_entity_uri(self, entity_uri: str, store_backend: Any, use_alignments: bool = False) -> List[str]:
        """
        Expand an entity URI to include all aligned/equivalent entities.

        Args:
            entity_uri: The original URI to expand
            store_backend: Triplet store backend to query
            use_alignments: If False, returns only the original URI

        Returns:
            List of URIs including the original and any aligned entities
        """
        if not use_alignments:
            return [entity_uri]

        tracking_id = self.progress_tracker.start_tracking(
            module="triplet_store",
            submodule="QueryEngine",
            message=f"Expanding alignments for: {entity_uri}"
        )

        # SPARQL query to find bidirectional alignments
        
        safe_uri = self._sanitize_uri(entity_uri)
        query = f"""
        SELECT DISTINCT ?aligned WHERE {{
            {{ <{safe_uri}> ?p ?aligned }}
            UNION
            {{ ?aligned ?p <{safe_uri}> }}
            
            FILTER (?p IN (
                <http://www.w3.org/2002/07/owl#equivalentClass>,
                <http://www.w3.org/2002/07/owl#equivalentProperty>,
                <http://www.w3.org/2002/07/owl#sameAs>,
                <http://www.w3.org/2004/02/skos/core#exactMatch>,
                <http://www.w3.org/2004/02/skos/core#closeMatch>,
                <http://www.w3.org/2004/02/skos/core#broadMatch>,
                <http://www.w3.org/2004/02/skos/core#narrowMatch>,
                <http://www.w3.org/2004/02/skos/core#relatedMatch>
            ))
        }}
        """

        expanded_uris = {entity_uri}
        try:
            if hasattr(store_backend, "execute_sparql"):
                result_data = store_backend.execute_sparql(query)
                for binding in result_data.get("bindings", []):
                    val = binding.get("aligned", {})
                    uri = val.get("value") if isinstance(val, dict) else val
                    if uri:
                        expanded_uris.add(uri)
            else:
                self.logger.warning(
                    "store_backend does not support execute_sparql; returning original URI only"
                )
            self.progress_tracker.stop_tracking(
                tracking_id,
                status="completed",
                message=f"Expanded to {len(expanded_uris)} URIs"
            )
        except Exception as e:
            self.logger.error(f"Failed to expand alignments for {entity_uri}: {e}")
            self.progress_tracker.stop_tracking(tracking_id, status="failed", message=str(e))

        return list(expanded_uris)

    def build_values_clause(self, variable_name: str, uris: List[str]) -> str:
        """
        Helper to generate a SPARQL VALUES clause for a list of URIs.
        Allows higher-level components to build alignment-aware queries.
        
        Example:
            uris = engine.expand_entity_uri("http://ex.org/Person", store, use_alignments=True)
            clause = engine.build_values_clause("subject", uris)
            # Returns: VALUES ?subject { <http://ex.org/Person> <http://other.org/Human> }
        """
        if not uris:
            return ""
        formatted_uris = " ".join([f"<{self._sanitize_uri(uri)}>" for uri in uris])
        return f"VALUES ?{variable_name} {{ {formatted_uris} }}"

    def _validate_query(self, query: str) -> bool:
        """Validate SPARQL query syntax (basic)."""
        if not query or not query.strip():
            return False

        query_upper = query.upper()

        # Check for valid SPARQL keywords
        valid_keywords = [
            "SELECT",
            "ASK",
            "CONSTRUCT",
            "DESCRIBE",
            "INSERT",
            "DELETE",
            "WHERE",
        ]
        if not any(keyword in query_upper for keyword in valid_keywords):
            return False

        return True

    def _estimate_query_cost(self, query: str) -> float:
        """Estimate query execution cost."""
        # Simple heuristic based on query complexity
        cost = 1.0

        # COUNT queries are more expensive
        if "COUNT" in query.upper():
            cost *= 2.0

        # Multiple joins increase cost
        join_count = query.upper().count("JOIN") + query.count(".")
        cost *= 1.0 + join_count * 0.1

        # DISTINCT increases cost
        if "DISTINCT" in query.upper():
            cost *= 1.5

        return cost

    def _identify_execution_steps(self, query: str) -> List[str]:
        """Identify query execution steps."""
        steps = []

        query_upper = query.upper()

        if "SELECT" in query_upper:
            steps.append("SELECT projection")
        if "WHERE" in query_upper:
            steps.append("Pattern matching")
        if "FILTER" in query_upper:
            steps.append("Filtering")
        if "ORDER BY" in query_upper:
            steps.append("Sorting")
        if "LIMIT" in query_upper or "OFFSET" in query_upper:
            steps.append("Pagination")

        return steps

    def _get_cache_key(self, query: str) -> str:
        """Generate cache key for query."""
        import hashlib

        normalized = " ".join(query.split())
        return hashlib.md5(normalized.encode()).hexdigest()  # nosec B324 - cache key, not security-sensitive

    def _cache_result(self, query: str, result: QueryResult) -> None:
        """Cache query result."""
        if len(self.query_cache) >= self.cache_size:
            # Remove oldest entry
            oldest_key = next(iter(self.query_cache))
            del self.query_cache[oldest_key]

        cache_key = self._get_cache_key(query)
        self.query_cache[cache_key] = result
    
    def _sanitize_uri(self, uri: str) -> str:
        """Prevent SPARQL injection by percent-encoding dangerous characters."""
        if not isinstance(uri, str):
            return ""
        return uri.replace("<", "%3C").replace(">", "%3E")

    def clear_cache(self) -> None:
        """Clear query cache."""
        self.query_cache.clear()

    def get_query_statistics(self) -> Dict[str, Any]:
        """Get query execution statistics."""
        if not self.query_history:
            return {
                "total_queries": 0,
                "average_execution_time": 0.0,
                "total_execution_time": 0.0,
            }

        execution_times = [q["execution_time"] for q in self.query_history]

        return {
            "total_queries": len(self.query_history),
            "average_execution_time": sum(execution_times) / len(execution_times),
            "total_execution_time": sum(execution_times),
            "min_execution_time": min(execution_times),
            "max_execution_time": max(execution_times),
            "cache_size": len(self.query_cache),
            "cache_hit_rate": 0.0,  # Would need to track hits/misses
        }
