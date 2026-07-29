"""
Triplet Store Core Module

This module provides the core triplet store interface and management classes,
providing a unified interface across multiple RDF store backends
(Blazegraph, Jena, RDF4J).

Key Features:
    - Unified triplet store interface
    - Multi-backend support (Blazegraph, Jena, RDF4J)
    - CRUD operations for RDF triplets
    - SPARQL query execution
    - Bulk loading and batch processing
    - Configuration management

Main Classes:
    - TripletStore: Main triplet store interface

Example Usage:
    >>> from semantica.triplet_store import TripletStore
    >>> store = TripletStore(backend="blazegraph", endpoint="http://localhost:9999/blazegraph")
    >>> store.add_triplet(triplet)
    >>> results = store.execute_query("SELECT * WHERE { ?s ?p ?o } LIMIT 10")

Author: Semantica Contributors
License: MIT
"""

from typing import Any, Dict, List, Optional, Union

from ..semantic_extract.triplet_extractor import Triplet
from ..utils.exceptions import ProcessingError, ValidationError
from ..utils.logging import get_logger
from ..utils.progress_tracker import get_progress_tracker
from .bulk_loader import BulkLoader
from .config import triplet_store_config
from .query_engine import QueryEngine


class TripletStore:
    """
    Main triplet store interface.

    Provides a unified interface for working with RDF triple stores,
    supporting Blazegraph, Jena, and RDF4J backends.
    """

    SUPPORTED_BACKENDS = {"blazegraph", "jena", "rdf4j", "anzo"}
    NAMED_GRAPH_CAPABLE_BACKENDS = {"blazegraph", "rdf4j", "anzo"}

    def __init__(
        self,
        backend: str = "blazegraph",
        endpoint: Optional[str] = None,
        **config,
    ):
        """
        Initialize triplet store.

        Args:
            backend: Backend type ("blazegraph", "jena", "rdf4j")
            endpoint: Store endpoint URL
            **config: Backend-specific configuration
        """
        self.logger = get_logger("triplet_store")
        self.progress_tracker = get_progress_tracker()
        # Ensure progress tracker is enabled
        if not self.progress_tracker.enabled:
            self.progress_tracker.enabled = True

        # Validate backend
        if backend.lower() not in self.SUPPORTED_BACKENDS:
            raise ValueError(
                f"Unsupported backend: {backend}. "
                f"Supported backends are: {', '.join(sorted(self.SUPPORTED_BACKENDS))}"
            )

        self.backend_type = backend.lower()
        self.endpoint = endpoint
        self.config = {**triplet_store_config.get_all(), **config}

        # Initialize store backend
        self._store_backend = None
        self._initialize_store_backend()

        # Initialize components
        self.query_engine = QueryEngine(self.config)
        self.bulk_loader = BulkLoader()

    def _initialize_store_backend(self) -> None:
        """Initialize the appropriate store backend based on backend type."""
        try:
            if self.backend_type == "blazegraph":
                from .blazegraph_store import BlazegraphStore

                # Merge config with defaults
                backend_config = self.config.copy()
                if self.endpoint:
                    backend_config["endpoint"] = self.endpoint
                else:
                    backend_config["endpoint"] = triplet_store_config.get(
                        "blazegraph_endpoint", "http://localhost:9999/blazegraph"
                    )

                self._store_backend = BlazegraphStore(**backend_config)

            elif self.backend_type == "jena":
                from .jena_store import JenaStore

                backend_config = self.config.copy()
                if self.endpoint:
                    backend_config["endpoint"] = self.endpoint
                else:
                    backend_config["endpoint"] = triplet_store_config.get(
                        "jena_endpoint", "http://localhost:3030/ds"
                    )

                self._store_backend = JenaStore(**backend_config)

            elif self.backend_type == "rdf4j":
                from .rdf4j_store import RDF4JStore

                backend_config = self.config.copy()
                if self.endpoint:
                    backend_config["endpoint"] = self.endpoint
                else:
                    backend_config["endpoint"] = triplet_store_config.get(
                        "rdf4j_endpoint", "http://localhost:8080/rdf4j-server"
                    )

                self._store_backend = RDF4JStore(**backend_config)

            elif self.backend_type == "anzo":
                from .anzo_store import AnzoStore

                backend_config = self.config.copy()
                if self.endpoint:
                    backend_config["endpoint"] = self.endpoint
                else:
                    backend_config["endpoint"] = triplet_store_config.get(
                        "anzo_endpoint", "http://localhost:8080"
                    )

                self._store_backend = AnzoStore(**backend_config)

            self.logger.info(f"Initialized {self.backend_type} backend")

        except Exception as e:
            self.logger.error(f"Failed to initialize {self.backend_type} backend: {e}")
            raise ProcessingError(f"Failed to initialize backend: {e}")

    def store(
        self,
        knowledge_graph: Union[Dict[str, Any], Any],
        ontology: Union[Dict[str, Any], Any],
        **options,
    ) -> Dict[str, Any]:
        """
        Store knowledge graph and ontology in the triplet store.

        Args:
            knowledge_graph: Knowledge graph dictionary or object
            ontology: Ontology dictionary or object
            **options: Additional options

        Returns:
            Operation status
        """
        # Convert inputs to dictionaries if they are objects
        if hasattr(knowledge_graph, "to_dict"):
            knowledge_graph = knowledge_graph.to_dict()
        if hasattr(ontology, "to_dict"):
            ontology = ontology.to_dict()

        triplets = []

        # Standard Namespaces
        RDF_TYPE = "http://www.w3.org/1999/02/22-rdf-syntax-ns#type"
        RDFS_SUBCLASS = "http://www.w3.org/2000/01/rdf-schema#subClassOf"
        OWL_CLASS = "http://www.w3.org/2002/07/owl#Class"
        OWL_OBJECT_PROPERTY = "http://www.w3.org/2002/07/owl#ObjectProperty"
        OWL_DATATYPE_PROPERTY = "http://www.w3.org/2002/07/owl#DatatypeProperty"
        RDFS_DOMAIN = "http://www.w3.org/2000/01/rdf-schema#domain"
        RDFS_RANGE = "http://www.w3.org/2000/01/rdf-schema#range"

        # Resolve base URI from ontology — used to mint entity/class/property IRIs
        # that are reconcilable with the ontology's own namespace.
        ns = ontology.get("namespace") or {}
        if isinstance(ns, dict):
            base_uri = ns.get("base_uri") or ontology.get("uri") or ""
        else:
            base_uri = ontology.get("uri") or ""
        # Ensure trailing separator so "base_uri + local" is always a valid IRI path.
        if base_uri and not base_uri.endswith(("/", "#")):
            base_uri = base_uri + "/"

        # Known W3C vocabulary prefixes — expanded before base_uri is applied so
        # values like "owl:Thing" or "xsd:date" are never re-namespaced under
        # the ontology's own base URI.
        _KNOWN_PREFIXES = {
            "xsd":      "http://www.w3.org/2001/XMLSchema#",
            "rdf":      "http://www.w3.org/1999/02/22-rdf-syntax-ns#",
            "rdfs":     "http://www.w3.org/2000/01/rdf-schema#",
            "owl":      "http://www.w3.org/2002/07/owl#",
            "skos":     "http://www.w3.org/2004/02/skos/core#",
            "semantica": "https://semantica.dev/ontology/",
        }

        def _resolve_iri(local: object, kind: str) -> str:
            """Expand a bare local name to a full IRI.

            Accepts any type for *local* — non-strings are coerced via str()
            so integer/numeric IDs passed from graph builders do not crash.

            Resolution order:
            1. Already an absolute IRI (http / https / urn:) → return as-is.
            2. Known vocabulary prefix (xsd:, rdf:, rdfs:, owl:, skos:,
               semantica:) → expand to the canonical W3C IRI.
            3. base_uri is set → append local name to base_uri.
            4. Fallback → ``urn:<kind>:<local>``.
            """
            local = str(local) if local is not None else ""
            if not local:
                return f"urn:{kind}:unknown"
            if local.startswith(("http://", "https://", "urn:")):
                return local
            if ":" in local:
                prefix, name = local.split(":", 1)
                if prefix in _KNOWN_PREFIXES:
                    return f"{_KNOWN_PREFIXES[prefix]}{name}"
            if base_uri:
                return f"{base_uri}{local}"
            return f"urn:{kind}:{local}"

        # 1. Process Ontology
        classes = ontology.get("classes", [])
        properties = ontology.get("properties", [])

        for cls in classes:
            # Class definition
            cls_uri = cls.get("uri") or cls.get("id") or cls.get("name")
            if not cls_uri:
                continue

            cls_uri = _resolve_iri(cls_uri, "class")
            triplets.append(Triplet(cls_uri, RDF_TYPE, OWL_CLASS))

            # Hierarchy
            parent = cls.get("parent") or cls.get("subClassOf")
            if parent:
                parent_uri = _resolve_iri(parent, "class")
                triplets.append(Triplet(cls_uri, RDFS_SUBCLASS, parent_uri))

        for prop in properties:
            prop_uri = prop.get("uri") or prop.get("id") or prop.get("name")
            if not prop_uri:
                continue

            prop_uri = _resolve_iri(prop_uri, "property")

            # Determine property type (Object or Datatype)
            # Default to ObjectProperty if not specified
            prop_type = prop.get("type", OWL_OBJECT_PROPERTY)
            if prop_type == "datatype":
                prop_type = OWL_DATATYPE_PROPERTY
            elif prop_type == "object":
                prop_type = OWL_OBJECT_PROPERTY

            triplets.append(Triplet(prop_uri, RDF_TYPE, prop_type))

            if "domain" in prop:
                domains = prop["domain"]
                if isinstance(domains, str):
                    domains = [domains]

                for domain in domains:
                    domain_uri = _resolve_iri(domain, "class")
                    triplets.append(Triplet(prop_uri, RDFS_DOMAIN, domain_uri))

            if "range" in prop:
                ranges = prop["range"]
                if isinstance(ranges, str):
                    ranges = [ranges]

                for range_ in ranges:
                    range_uri = _resolve_iri(range_, "class")
                    triplets.append(Triplet(prop_uri, RDFS_RANGE, range_uri))

        # 2. Process Knowledge Graph
        entities = knowledge_graph.get("entities", [])
        relationships = knowledge_graph.get("relationships", [])

        entity_map = {}  # Map IDs to URIs

        for entity in entities:
            entity_id = entity.get("id")
            if not entity_id:
                continue

            entity_uri = entity.get("uri") or _resolve_iri(entity_id, "entity")
            entity_map[entity_id] = entity_uri

            # Entity Type
            entity_type = entity.get("type")
            if entity_type:
                type_uri = _resolve_iri(entity_type, "class")
                triplets.append(Triplet(entity_uri, RDF_TYPE, type_uri))

            # Entity Properties
            props = entity.get("properties", {})
            for k, v in props.items():
                prop_uri = _resolve_iri(k, "property")
                triplets.append(Triplet(entity_uri, prop_uri, str(v)))

        for rel in relationships:
            source_id = rel.get("source")
            target_id = rel.get("target")
            rel_type = rel.get("type") or rel.get("label")

            if not source_id or not target_id or not rel_type:
                continue

            source_uri = entity_map.get(source_id) or _resolve_iri(source_id, "entity")
            target_uri = entity_map.get(target_id) or _resolve_iri(target_id, "entity")
            rel_uri = _resolve_iri(rel_type, "property")

            triplets.append(Triplet(source_uri, rel_uri, target_uri))

        # Bulk load all triplets
        return self.add_triplets(triplets, **options)

    def add_triplet(self, triplet: Triplet, **options) -> Dict[str, Any]:
        """
        Add a single triplet to the store.

        Args:
            triplet: Triplet object to add
            **options: Additional options

        Returns:
            Operation status
        """
        if not self._validate_triplet(triplet):
            raise ValidationError("Invalid triplet structure or confidence")

        return self._store_backend.add_triplet(triplet, **options)

    def add_triplets(
        self, triplets: List[Triplet], batch_size: int = 1000, **options
    ) -> Dict[str, Any]:
        """
        Add multiple triplets to the store (bulk load).

        Args:
            triplets: List of Triplet objects
            batch_size: Batch size for processing
            **options: Additional options

        Returns:
            Operation status with stats
        """
        # Validate triplets first
        valid_triplets = [t for t in triplets if self._validate_triplet(t)]
        if len(valid_triplets) < len(triplets):
            self.logger.warning(
                f"Filtered {len(triplets) - len(valid_triplets)} invalid triplets"
            )

        # Use bulk loader for efficient processing
        progress = self.bulk_loader.load_triplets(
            valid_triplets, self._store_backend, batch_size=batch_size, **options
        )

        return {
            "success": progress.metadata.get("success", progress.failed_triplets == 0),
            "total": progress.total_triplets,
            "processed": progress.loaded_triplets,
            "failed": progress.failed_triplets,
            "batches": progress.total_batches,
        }

    def get_triplets(
        self,
        subject: Optional[str] = None,
        predicate: Optional[str] = None,
        object: Optional[str] = None,
        **options,
    ) -> List[Triplet]:
        """
        Retrieve triplets matching criteria.

        Args:
            subject: Subject URI
            predicate: Predicate URI
            object: Object URI
            **options: Additional options

        Returns:
            List of matching Triplet objects
        """
        return self._store_backend.get_triplets(
            subject=subject, predicate=predicate, object=object, **options
        )

    def delete_triplet(self, triplet: Triplet, **options) -> Dict[str, Any]:
        """
        Delete a triplet from the store.

        Args:
            triplet: Triplet to delete
            **options: Additional options

        Returns:
            Operation status
        """
        return self._store_backend.delete_triplet(triplet, **options)

    def update_triplet(
        self, old_triplet: Triplet, new_triplet: Triplet, **options
    ) -> Dict[str, Any]:
        """
        Update a triplet (atomic delete + add).

        Args:
            old_triplet: Triplet to remove
            new_triplet: Triplet to add
            **options: Additional options

        Returns:
            Operation status
        """
        # Simple implementation: delete then add
        # Some backends might support atomic updates
        self.delete_triplet(old_triplet, **options)
        return self.add_triplet(new_triplet, **options)

    def execute_query(
        self,
        query: str,
        parameters: Optional[Dict[str, Any]] = None,
        graph: Optional[str] = None,
        graphs: Optional[List[str]] = None,
        **options,
    ) -> Any:
        """
        Execute a SPARQL query.

        Args:
            query: SPARQL query string
            parameters: Query parameters
            graph: Optional default graph URI for dataset scoping
            graphs: Optional list of named graph URIs for dataset scoping
            **options: Additional options

        Returns:
            Query results (format depends on query type)
        """
        if graph is not None:
            options["graph"] = graph
        if graphs is not None:
            options["graphs"] = graphs

        enable_named_graphs = self.config.get("enable_named_graphs", True)
        options.setdefault(
            "supports_named_graphs",
            enable_named_graphs
            and self.backend_type in self.NAMED_GRAPH_CAPABLE_BACKENDS,
        )

        return self.query_engine.execute_query(query, self._store_backend, **options)

    def _validate_triplet(self, triplet: Triplet) -> bool:
        """Validate triplet structure."""
        if not triplet.subject or not triplet.predicate or not triplet.object:
            return False

        # Check confidence score if present
        if hasattr(triplet, "confidence"):
            if triplet.confidence is not None and (
                triplet.confidence < 0 or triplet.confidence > 1
            ):
                return False

        return True

    # ── SKOS helpers ─────────────────────────────────────────────────────────

    _SKOS = "http://www.w3.org/2004/02/skos/core#"
    _RDF_TYPE = "http://www.w3.org/1999/02/22-rdf-syntax-ns#type"

    def add_skos_concept(
        self,
        concept_uri: str,
        scheme_uri: str,
        pref_label: str,
        alt_labels: Optional[List[str]] = None,
        broader: Optional[List[str]] = None,
        narrower: Optional[List[str]] = None,
        related: Optional[List[str]] = None,
        definition: Optional[str] = None,
        notation: Optional[str] = None,
        **options,
    ) -> Dict[str, Any]:
        """
        Add a SKOS concept (and its scheme if not already present) to the store.

        Core triples added:

        * ``concept_uri  rdf:type             skos:Concept``
        * ``concept_uri  skos:inScheme        scheme_uri``
        * ``concept_uri  skos:prefLabel       pref_label``
        * ``scheme_uri   rdf:type             skos:ConceptScheme``  (auto-created)
        * Optional: altLabel, broader, narrower, related, definition, notation

        Args:
            concept_uri: Full URI for the concept.
            scheme_uri: Full URI for the parent ConceptScheme.
            pref_label: Preferred label string.
            alt_labels: Optional list of alternative label strings.
            broader: Optional list of broader concept URIs.
            narrower: Optional list of narrower concept URIs.
            related: Optional list of related concept URIs.
            definition: Optional human-readable definition string.
            notation: Optional notation / code string.
            **options: Forwarded to :meth:`add_triplets`.

        Returns:
            :meth:`add_triplets` status dict.
        """
        SKOS = self._SKOS
        RDF_TYPE = self._RDF_TYPE

        triplets: List[Triplet] = [
            # Scheme declaration
            Triplet(scheme_uri, RDF_TYPE, f"{SKOS}ConceptScheme"),
            # Concept core
            Triplet(concept_uri, RDF_TYPE, f"{SKOS}Concept"),
            Triplet(concept_uri, f"{SKOS}inScheme", scheme_uri),
            Triplet(concept_uri, f"{SKOS}prefLabel", pref_label),
        ]

        for lbl in (alt_labels or []):
            triplets.append(Triplet(concept_uri, f"{SKOS}altLabel", lbl))
        for uri in (broader or []):
            triplets.append(Triplet(concept_uri, f"{SKOS}broader", uri))
        for uri in (narrower or []):
            triplets.append(Triplet(concept_uri, f"{SKOS}narrower", uri))
        for uri in (related or []):
            triplets.append(Triplet(concept_uri, f"{SKOS}related", uri))
        if definition:
            triplets.append(Triplet(concept_uri, f"{SKOS}definition", definition))
        if notation:
            triplets.append(Triplet(concept_uri, f"{SKOS}notation", notation))

        return self.add_triplets(triplets, **options)

    def get_skos_concepts(
        self, scheme_uri: Optional[str] = None, **options
    ) -> List[Dict[str, Any]]:
        """
        Retrieve SKOS concepts from the store as plain dicts.

        Each returned dict has at minimum ``uri`` and ``pref_label``; optional
        keys ``alt_labels``, ``broader``, ``narrower``, and ``related`` are
        populated when available.

        Args:
            scheme_uri: When given, only concepts ``skos:inScheme`` this URI
                        are returned.  When omitted all concepts are returned.
            **options: Forwarded to :meth:`execute_query`.

        Returns:
            List of concept dicts.
        """
        SKOS = self._SKOS
        RDF_TYPE = self._RDF_TYPE

        scheme_filter = (
            f"?concept <{SKOS}inScheme> <{self.query_engine._sanitize_uri(scheme_uri)}> ."
            if scheme_uri
            else ""
        )

        query = f"""
        SELECT DISTINCT ?concept ?prefLabel ?altLabel ?broader ?narrower ?related
        WHERE {{
            ?concept <{RDF_TYPE}> <{SKOS}Concept> .
            {scheme_filter}
            OPTIONAL {{ ?concept <{SKOS}prefLabel> ?prefLabel }}
            OPTIONAL {{ ?concept <{SKOS}altLabel>  ?altLabel  }}
            OPTIONAL {{ ?concept <{SKOS}broader>   ?broader   }}
            OPTIONAL {{ ?concept <{SKOS}narrower>  ?narrower  }}
            OPTIONAL {{ ?concept <{SKOS}related>   ?related   }}
        }}
        """

        try:
            result = self.execute_query(query, **options)
        except Exception as e:
            self.logger.error(f"get_skos_concepts query failed: {e}")
            raise ProcessingError(f"Failed to retrieve SKOS concepts: {e}")

        # Collapse multi-valued properties per concept URI
        concepts: Dict[str, Dict[str, Any]] = {}
        for b in result.bindings:
            def _val(key: str) -> Optional[str]:
                v = b.get(key)
                return (v.get("value") if isinstance(v, dict) else v) if v else None

            uri = _val("concept")
            if not uri:
                continue
            if uri not in concepts:
                concepts[uri] = {
                    "uri": uri,
                    "pref_label": _val("prefLabel") or "",
                    "alt_labels": [],
                    "broader": [],
                    "narrower": [],
                    "related": [],
                }
            entry = concepts[uri]
            if not entry["pref_label"] and _val("prefLabel"):
                entry["pref_label"] = _val("prefLabel")
            for multi_key, sparql_key in [
                ("alt_labels", "altLabel"),
                ("broader", "broader"),
                ("narrower", "narrower"),
                ("related", "related"),
            ]:
                v = _val(sparql_key)
                if v and v not in entry[multi_key]:
                    entry[multi_key].append(v)

        return list(concepts.values())

    def get_stats(self) -> Dict[str, Any]:
        """Get store statistics."""
        if hasattr(self._store_backend, "get_stats"):
            return self._store_backend.get_stats()
        return {}
    
    def compute_delta(
        self, old_graph_uri: str, new_graph_uri: str, **options
    ) -> Dict[str, Any]:
        """
        Compute the delta (added and removed triples) between two graph snapshots.
        
        Args:
            old_graph_uri: URI of the baseline graph snapshot.
            new_graph_uri: URI of the target graph snapshot
            **options: Additional query execution options
        
        Returns:
            Dictionary containing added_triples, removed_triples, and counts.
        """
        
        tracking_id = self.progress_tracker.start_tracking(
            module="triplet_store",
            submodule="ComputeDelta",
            message=f"Computing delta: {old_graph_uri} -> {new_graph_uri}",
        )
        
        # SPARQL: Triples in the new graph that do not exist in the old graph
        added_query = f"""
        SELECT ?s ?p ?o WHERE {{
            GRAPH <{new_graph_uri} > {{ ?s ?p ?o }}
            FILTER NOT EXISTS {{ GRAPH <{old_graph_uri}> {{ ?s ?p ?o}} }}
        }}
        """
        
        # // : Triples in the old graph that do not exist in the new graph
        removed_query = f"""
        SELECT ?s ?p ?o WHERE {{
            GRAPH <{old_graph_uri}> {{ ?s ?p ?o }}
            FILTER NOT EXISTS {{ GRAPH <{new_graph_uri}> {{ ?s ?p ?o }} }}
        }}
        """
        
        try:
            self.progress_tracker.update_tracking(tracking_id, message="Executing added triples query...")
            added_res = self.execute_query(added_query, **options)
            
            self.progress_tracker.update_tracking(tracking_id, message="Executing removed triples query...")
            removed_res = self.execute_query(removed_query, **options)
            
            def extract_triplets(bindings):
                triplets = []
                for b in bindings:
                    s = b.get("s", {}).get("value") if isinstance(b.get("s"), dict) else b.get("s")
                    p = b.get("p", {}).get("value") if isinstance(b.get("p"), dict) else b.get("p")
                    o = b.get("o", {}).get("value") if isinstance(b.get("o"), dict) else b.get("o")

                    if s and p and o:
                        triplets.append(Triplet(s, p, o))

                return triplets
            
            added_triples = extract_triplets(added_res.bindings)
            removed_triples = extract_triplets(removed_res.bindings)
            
            self.progress_tracker.stop_tracking(
                tracking_id,
                status="completed",
                message=f"Delta computed: +{len(added_triples)} / -{len(removed_triples)}"
            )
            
            return {
                "old_graph_uri": old_graph_uri,
                "new_graph_uri": new_graph_uri,
                "added_triples": added_triples,
                "removed_triples": removed_triples,
                "added_count": len(added_triples),
                "removed_count": len(removed_triples),
            }
            
        except Exception as e:
            self.logger.error(f"Failed to compute delta: {e}")
            self.progress_tracker.stop_tracking(tracking_id, status="failed", message=str(e))
            raise ProcessingError(f"Delta computation failed: {e}")
        
            
