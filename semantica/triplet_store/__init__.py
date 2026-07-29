"""
Triplet Store Module

This module provides comprehensive triplet store integration and management
for RDF data storage and querying, supporting multiple triplet store backends
(Blazegraph, Jena, RDF4J, Anzo) with unified interfaces.

Key Features:
    - Unified triplet store interface
    - Multi-backend support (Blazegraph, Jena, RDF4J, Anzo)
    - CRUD operations for RDF triplets
    - SPARQL query execution and optimization
    - Bulk data loading with progress tracking
    - Configuration management

Main Classes:
    - TripletStore: Main triplet store interface
    - BulkLoader: High-volume data loading
    - QueryEngine: SPARQL query execution and optimization
    - BlazegraphStore: Blazegraph integration store
    - JenaStore: Apache Jena integration store
    - RDF4JStore: Eclipse RDF4J integration store
    - AnzoStore: Altair Anzo integration store

Example Usage:
    >>> from semantica.triplet_store import TripletStore
    >>> store = TripletStore(backend="blazegraph", endpoint="http://localhost:9999/blazegraph")
    >>> store.add_triplet(triplet)
    >>> results = store.execute_query("SELECT * WHERE { ?s ?p ?o } LIMIT 10")
"""

from .bulk_loader import BulkLoader
from .config import TripletStoreConfig, triplet_store_config
from .query_engine import QueryEngine
from .triplet_store import TripletStore
from .blazegraph_store import BlazegraphStore
from .jena_store import JenaStore
from .rdf4j_store import RDF4JStore
from .anzo_store import AnzoStore
from .methods import (
    register_store,
    add_triplet,
    add_triplets,
    get_triplets,
    delete_triplet,
    update_triplet,
    execute_query,
    optimize_query,
    plan_query,
    bulk_load,
    validate_triplets,
    list_available_methods
)

__all__ = [
    "TripletStore",
    "BulkLoader",
    "QueryEngine",
    "TripletStoreConfig",
    "triplet_store_config",
    "BlazegraphStore",
    "JenaStore",
    "RDF4JStore",
    "AnzoStore",
    "register_store",
    "add_triplet",
    "add_triplets",
    "get_triplets",
    "delete_triplet",
    "update_triplet",
    "execute_query",
    "optimize_query",
    "plan_query",
    "bulk_load",
    "validate_triplets",
    "list_available_methods",
]
