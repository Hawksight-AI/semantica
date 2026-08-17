"""
Seed Data Manager Module

This module provides comprehensive seed data management for initial knowledge
graph construction, enabling the framework to build on existing verified
knowledge from multiple sources.

Key Features:
    - Multi-source seed data loading (CSV, JSON, Database, API)
    - Foundation graph creation from seed data
    - Seed data quality validation
    - Integration with extracted data using configurable merge strategies
    - Version management for seed sources
    - Export capabilities (JSON, CSV)
    - Schema template validation

Main Classes:
    - SeedDataManager: Main coordinator for seed data operations
    - SeedDataSource: Seed data source definition dataclass
    - SeedData: Seed data container dataclass

Example Usage:
    >>> from semantica.seed import SeedDataManager
    >>> manager = SeedDataManager()
    >>> manager.register_source("entities", "json", "data/entities.json", entity_type="Person")
    >>> records = manager.load_from_json("data/entities.json")
    >>> foundation = manager.create_foundation_graph()
    >>> validation = manager.validate_quality(foundation)

Author: Semantica Contributors
License: MIT
"""

import csv
import json
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional, Union

from ..utils.exceptions import ProcessingError, ValidationError
from ..utils.helpers import read_json_file, write_json_file
from ..utils.logging import get_logger
from ..utils.progress_tracker import get_progress_tracker
from ..utils.types import EntityDict, RelationshipDict
from ..ingest.ssrf import parse_bool, request_with_ssrf_guard


@dataclass
class SeedDataSource:
    """
    Seed data source definition.

    Represents a source of seed data with metadata about its format,
    location, and verification status.

    Attributes:
        name: Unique name for the source
        format: Data format ('csv', 'json', 'database', 'api')
        location: Source location (file path, DB connection string, API URL)
        entity_type: Optional entity type for entities in this source
        relationship_type: Optional relationship type for relationships in this source
        verified: Whether the data is verified (default: True)
        version: Source version string (default: "1.0")
        metadata: Additional metadata dictionary
    """

    name: str
    format: str  # csv, json, database, api
    location: Union[str, Path]
    entity_type: Optional[str] = None
    relationship_type: Optional[str] = None
    verified: bool = True
    version: str = "1.0"
    metadata: Dict[str, Any] = field(default_factory=dict)


@dataclass
class SeedData:
    """
    Seed data container.

    Holds entities, relationships, and metadata loaded from seed sources.

    Attributes:
        entities: List of entity dictionaries
        relationships: List of relationship dictionaries
        properties: Additional properties dictionary
        metadata: Metadata dictionary
    """

    entities: List[EntityDict] = field(default_factory=list)
    relationships: List[RelationshipDict] = field(default_factory=list)
    properties: Dict[str, Any] = field(default_factory=dict)
    metadata: Dict[str, Any] = field(default_factory=dict)


class SeedDataManager:
    """
    Seed data manager for initial knowledge graph construction.

    Manages loading, validation, and integration of seed data from multiple
    sources to create a foundation knowledge graph. Supports CSV, JSON,
    database, and API sources.

    Attributes:
        logger: Logger instance for operations
        config: Configuration dictionary
        sources: Dictionary of registered seed data sources
        seed_data: Current seed data container
        versions: Version tracking for sources
    """

    def __init__(self, config: Optional[Dict[str, Any]] = None, **kwargs):
        """
        Initialize seed data manager.

        Args:
            config: Optional configuration dictionary
            **kwargs: Additional configuration options merged into config

        Example:
            >>> manager = SeedDataManager()
            >>> manager = SeedDataManager(config={"auto_validate": True})
        """
        self.logger = get_logger("seed_manager")
        self.config = config or {}
        self.config.update(kwargs)
        self.progress_tracker = get_progress_tracker()
        # Ensure progress tracker is enabled
        if not self.progress_tracker.enabled:
            self.progress_tracker.enabled = True

        self.sources: Dict[str, SeedDataSource] = {}
        self.seed_data: SeedData = SeedData()
        self.versions: Dict[str, List[str]] = {}  # source_name -> versions

    def register_source(
        self,
        name: str,
        format: str,
        location: Union[str, Path],
        entity_type: Optional[str] = None,
        relationship_type: Optional[str] = None,
        verified: bool = True,
        **metadata,
    ) -> bool:
        """
        Register a seed data source.

        Registers a new source or updates an existing one. The source can be
        loaded later using load_source().

        Args:
            name: Unique source name identifier
            format: Data format ('csv', 'json', 'database', 'api')
            location: Source location (file path, DB connection string, API URL)
            entity_type: Optional entity type for entities in this source
            relationship_type: Optional relationship type for relationships in this source
            verified: Whether data is verified (default: True)
            **metadata: Additional metadata to store with the source

        Returns:
            True if registration successful

        Raises:
            ProcessingError: If source registration fails

        Example:
            >>> manager.register_source("people", "json", "data/people.json", entity_type="Person")
            >>> manager.register_source("companies", "csv", "data/companies.csv", entity_type="Organization")
        """
        if name in self.sources:
            self.logger.warning(f"Source '{name}' already registered, updating")

        source = SeedDataSource(
            name=name,
            format=format,
            location=location,
            entity_type=entity_type,
            relationship_type=relationship_type,
            verified=verified,
            metadata=metadata,
        )

        self.sources[name] = source

        # Track versions
        if name not in self.versions:
            self.versions[name] = []

        self.logger.info(f"Registered seed data source: {name} ({format})")
        return True

    def load_from_csv(
        self,
        file_path: Union[str, Path],
        entity_type: Optional[str] = None,
        relationship_type: Optional[str] = None,
        source_name: Optional[str] = None,
        delimiter: Optional[str] = None,
    ) -> List[Dict[str, Any]]:
        """
        Load seed data from CSV file.

        Reads a CSV file and converts rows to dictionaries. Automatically
        adds entity_type, relationship_type, and source metadata if provided.
        Supports automatic delimiter detection if not provided.

        Args:
            file_path: Path to CSV file
            entity_type: Optional entity type to add to all records
            relationship_type: Optional relationship type to add to all records
            source_name: Optional source name for tracking
            delimiter: Optional CSV delimiter. If None, attempts to detect it.

        Returns:
            List of loaded data records as dictionaries

        Raises:
            ProcessingError: If file not found or CSV parsing fails

        Example:
            >>> records = manager.load_from_csv("data/entities.csv", entity_type="Person")
            >>> records = manager.load_from_csv("data/data.csv", delimiter=";")
        """
        tracking_id = self.progress_tracker.start_tracking(
            module="seed",
            submodule="SeedDataManager",
            message=f"Loading seed data from CSV: {file_path}",
        )

        try:
            file_path = Path(file_path)
            if not file_path.exists():
                self.progress_tracker.stop_tracking(
                    tracking_id,
                    status="failed",
                    message=f"CSV file not found: {file_path}",
                )
                raise ProcessingError(f"CSV file not found: {file_path}")

            records = []

            self.progress_tracker.update_tracking(
                tracking_id, message="Reading CSV file..."
            )
            with open(file_path, "r", encoding="utf-8") as f:
                # Detect delimiter if not provided
                if delimiter is None:
                    try:
                        sample = f.read(1024)
                        f.seek(0)
                        dialect = csv.Sniffer().sniff(sample)
                        delimiter = dialect.delimiter
                        self.logger.debug(f"Detected CSV delimiter: '{delimiter}'")
                    except csv.Error:
                        # Fallback to comma if sniffing fails
                        f.seek(0)
                        delimiter = ","
                        self.logger.debug("Could not detect delimiter, defaulting to ','")
                
                reader = csv.DictReader(f, delimiter=delimiter)
                for row in reader:
                    # Clean up row data
                    record = {k: v for k, v in row.items() if v}

                    if entity_type:
                        record["entity_type"] = entity_type
                    if relationship_type:
                        record["relationship_type"] = relationship_type
                    if source_name:
                        record["source"] = source_name

                    records.append(record)

            self.logger.info(f"Loaded {len(records)} records from CSV: {file_path}")
            self.progress_tracker.stop_tracking(
                tracking_id,
                status="completed",
                message=f"Loaded {len(records)} records from CSV",
            )
            return records

        except Exception as e:
            self.progress_tracker.stop_tracking(
                tracking_id, status="failed", message=str(e)
            )
            raise ProcessingError(f"Failed to load CSV: {e}") from e

    def load_from_json(
        self,
        file_path: Union[str, Path],
        entity_type: Optional[str] = None,
        relationship_type: Optional[str] = None,
        source_name: Optional[str] = None,
    ) -> List[Dict[str, Any]]:
        """
        Load seed data from JSON file.

        Reads a JSON file and handles various structures (list, dict with
        'entities', 'data', 'records' keys, or single object). Automatically
        adds entity_type, relationship_type, and source metadata if provided.

        Args:
            file_path: Path to JSON file
            entity_type: Optional entity type to add to all records
            relationship_type: Optional relationship type to add to all records
            source_name: Optional source name for tracking

        Returns:
            List of loaded data records as dictionaries

        Raises:
            ProcessingError: If file not found or JSON parsing fails

        Example:
            >>> records = manager.load_from_json("data/entities.json", entity_type="Person")
            >>> print(f"Loaded {len(records)} records")
        """
        file_path = Path(file_path)
        if not file_path.exists():
            raise ProcessingError(f"JSON file not found: {file_path}")

        try:
            data = read_json_file(file_path)

            # Handle different JSON structures
            if isinstance(data, list):
                records = data
            elif isinstance(data, dict):
                # Try common keys
                if "entities" in data:
                    records = data["entities"]
                elif "data" in data:
                    records = data["data"]
                elif "records" in data:
                    records = data["records"]
                else:
                    self.logger.warning(
                        f"JSON file {file_path} is a dictionary but contains none of the "
                        "expected keys: 'entities', 'data', 'records'. "
                        "Treating entire object as a single record."
                    )
                    records = [data]
            else:
                records = []

            # Add metadata
            for record in records:
                if entity_type and "entity_type" not in record:
                    record["entity_type"] = entity_type
                if relationship_type and "relationship_type" not in record:
                    record["relationship_type"] = relationship_type
                if source_name and "source" not in record:
                    record["source"] = source_name

            self.logger.info(f"Loaded {len(records)} records from JSON: {file_path}")
            return records

        except Exception as e:
            raise ProcessingError(f"Failed to load JSON: {e}") from e

    def load_from_database(
        self,
        connection_string: str,
        query: Optional[str] = None,
        table_name: Optional[str] = None,
        entity_type: Optional[str] = None,
        relationship_type: Optional[str] = None,
        source_name: Optional[str] = None,
    ) -> List[Dict[str, Any]]:
        """
        Load seed data from database.

        Connects to a database and executes a query or exports a table.
        Uses the DBIngestor module for database operations. Automatically
        adds entity_type, relationship_type, and source metadata if provided.

        Args:
            connection_string: Database connection string
            query: Optional SQL query to execute
            table_name: Optional table name to export (if no query provided)
            entity_type: Optional entity type to add to all records
            relationship_type: Optional relationship type to add to all records
            source_name: Optional source name for tracking

        Returns:
            List of loaded data records as dictionaries

        Raises:
            ProcessingError: If database connection fails, query fails, or
                DBIngestor module is not available

        Example:
            >>> records = manager.load_from_database(
            ...     "postgresql://user:pass@localhost/db",
            ...     query="SELECT * FROM entities",
            ...     entity_type="Person"
            ... )
        """
        try:
            from ..ingest.db_ingestor import DBIngestor
        except ImportError as e:
            raise ProcessingError(
                "Database ingestion module not available. Install required dependencies."
            ) from e

        try:
            # Initialize DB ingestor
            db_ingestor = DBIngestor(config={"connection_string": connection_string})

            # Execute query or export table. Both ingestor methods take the
            # connection string as their first argument — the constructor's
            # config is not a substitute for it (#973).
            if query:
                # Execute custom query
                result = db_ingestor.execute_query(connection_string, query)
                records = result if isinstance(result, list) else [result]
            elif table_name:
                # Export table
                table_data = db_ingestor.export_table(connection_string, table_name)
                records = table_data.rows if hasattr(table_data, "rows") else []
            else:
                raise ProcessingError("Either 'query' or 'table_name' must be provided")

            # Add metadata
            for record in records:
                if entity_type and "entity_type" not in record:
                    record["entity_type"] = entity_type
                if relationship_type and "relationship_type" not in record:
                    record["relationship_type"] = relationship_type
                if source_name and "source" not in record:
                    record["source"] = source_name

            self.logger.info(f"Loaded {len(records)} records from database")
            return records

        except ProcessingError:
            raise
        except Exception as e:
            # OSError here is a real connection/driver failure, not a missing
            # module — report the actual cause and keep the chain (#973).
            raise ProcessingError(f"Failed to load from database: {e}") from e

    def load_from_api(
        self,
        api_url: str,
        endpoint: Optional[str] = None,
        entity_type: Optional[str] = None,
        relationship_type: Optional[str] = None,
        source_name: Optional[str] = None,
        api_key: Optional[str] = None,
        headers: Optional[Dict[str, str]] = None,
    ) -> List[Dict[str, Any]]:
        """
        Load seed data from API.

        Makes an HTTP GET request to an API endpoint and parses the JSON
        response. Handles various response structures (list, dict with
        'entities', 'data', 'results', 'items' keys). Automatically adds
        entity_type, relationship_type, and source metadata if provided.

        SSRF protection is enabled by default: URLs resolving to private,
        loopback, link-local (including cloud metadata endpoints such as
        169.254.169.254), or other blocked addresses are rejected, and every
        redirect hop is re-validated before being followed. For trusted
        internal deployments, pass ``allow_private_ips=True`` in the manager
        config to opt in (documented for internal use only).

        Args:
            api_url: Base API URL
            endpoint: Optional API endpoint path (appended to api_url)
            entity_type: Optional entity type to add to all records
            relationship_type: Optional relationship type to add to all records
            source_name: Optional source name for tracking
            api_key: Optional API key (added as Bearer token in Authorization header)
            headers: Optional request headers dictionary

        Returns:
            List of loaded data records as dictionaries

        Raises:
            ProcessingError: If API request fails, response parsing fails, or
                requests library is not available

        Example:
            >>> records = manager.load_from_api(
            ...     "https://api.example.com",
            ...     endpoint="entities",
            ...     api_key="your-api-key",
            ...     entity_type="Person"
            ... )
        """
        try:
            import requests

            # Build full URL
            if endpoint:
                full_url = f"{api_url.rstrip('/')}/{endpoint.lstrip('/')}"
            else:
                full_url = api_url

            # Prepare headers — copy the caller's dict so we never mutate it in-place.
            # Without the copy, adding "Authorization" here would silently modify the
            # caller's original dict and potentially leak the key to subsequent calls
            # that reuse the same dict without expecting it to contain credentials.
            request_headers = dict(headers) if headers else {}
            if api_key:
                request_headers["Authorization"] = f"Bearer {api_key}"

            # SSRF guard: reject private/loopback/link-local targets by default.
            # Trusted internal deployments can opt in via config
            # (allow_private_ips=True) — see issue #943.
            allow_private = parse_bool(self.config.get("allow_private_ips", False))

            # Make API request (request_with_ssrf_guard validates the URL and
            # every redirect before each hop)
            response = request_with_ssrf_guard(
                "GET",
                full_url,
                headers=request_headers,
                timeout=30,
                allow_private_ips=allow_private,
            )
            response.raise_for_status()

            # Parse response
            data = response.json()

            # Handle different response structures
            if isinstance(data, list):
                records = data
            elif isinstance(data, dict):
                # Try common keys
                if "entities" in data:
                    records = data["entities"]
                elif "data" in data:
                    records = data["data"]
                elif "results" in data:
                    records = data["results"]
                elif "items" in data:
                    records = data["items"]
                else:
                    records = [data]
            else:
                records = []

            # Add metadata
            for record in records:
                if not isinstance(record, dict):
                    continue
                if entity_type and "entity_type" not in record:
                    record["entity_type"] = entity_type
                if relationship_type and "relationship_type" not in record:
                    record["relationship_type"] = relationship_type
                if source_name and "source" not in record:
                    record["source"] = source_name

            self.logger.info(f"Loaded {len(records)} records from API: {full_url}")
            return records

        except (ImportError, OSError):
            raise ProcessingError(
                "requests library not available. Install with: pip install requests"
            )
        except Exception as e:
            raise ProcessingError(f"Failed to load from API: {e}") from e

    def load_source(self, source_name: str) -> List[Dict[str, Any]]:
        """
        Load data from registered source.

        Loads data from a previously registered source using the source's
        format and location. Automatically routes to the appropriate loader
        method based on the source format.

        Args:
            source_name: Name of the registered source

        Returns:
            List of loaded data records as dictionaries

        Raises:
            ProcessingError: If source not registered or unsupported format

        Example:
            >>> manager.register_source("entities", "json", "data/entities.json")
            >>> records = manager.load_source("entities")
        """
        if source_name not in self.sources:
            raise ProcessingError(f"Source '{source_name}' not registered")

        source = self.sources[source_name]

        if source.format == "csv":
            return self.load_from_csv(
                source.location,
                entity_type=source.entity_type,
                relationship_type=source.relationship_type,
                source_name=source_name,
            )
        elif source.format == "json":
            return self.load_from_json(
                source.location,
                entity_type=source.entity_type,
                relationship_type=source.relationship_type,
                source_name=source_name,
            )
        elif source.format == "database":
            return self.load_from_database(
                source.location,
                entity_type=source.entity_type,
                relationship_type=source.relationship_type,
                source_name=source_name,
            )
        elif source.format == "api":
            return self.load_from_api(
                source.location,
                entity_type=source.entity_type,
                relationship_type=source.relationship_type,
                source_name=source_name,
            )
        else:
            raise ProcessingError(f"Unsupported source format: {source.format}")

    def create_foundation_graph(
        self, schema_template: Optional[Any] = None
    ) -> Dict[str, Any]:
        """
        Create foundation graph from seed data.

        Loads data from all registered sources and creates a foundation
        knowledge graph with entities and relationships. Optionally validates
        against a schema template.

        Args:
            schema_template: Optional schema template for validation

        Returns:
            Foundation graph dictionary with:
                - entities: List of entity dictionaries
                - relationships: List of relationship dictionaries
                - metadata: Graph metadata including creation timestamp,
                  source count, and verification status

        Example:
            >>> manager.register_source("people", "json", "data/people.json")
            >>> foundation = manager.create_foundation_graph()
            >>> print(f"Created graph with {len(foundation['entities'])} entities")
        """
        tracking_id = self.progress_tracker.start_tracking(
            module="seed",
            submodule="SeedDataManager",
            message="Creating foundation graph from seed data",
        )

        try:
            foundation = {
                "entities": [],
                "relationships": [],
                "metadata": {
                    "created_at": datetime.now().isoformat(),
                    "source_count": len(self.sources),
                    "verified": True,
                },
            }

            # Load data from all sources
            self.progress_tracker.update_tracking(
                tracking_id, message=f"Loading data from {len(self.sources)} sources..."
            )
            for source_name in self.sources:
                try:
                    self.progress_tracker.update_tracking(
                        tracking_id, message=f"Loading source: {source_name}"
                    )
                    records = self.load_source(source_name)

                    for record in records:
                        # Extract entities
                        if "entity_type" in record or "id" in record:
                            entity = self._record_to_entity(record)
                            if entity:
                                foundation["entities"].append(entity)

                        # Extract relationships
                        if "relationship_type" in record or (
                            "source_id" in record and "target_id" in record
                        ):
                            relationship = self._record_to_relationship(record)
                            if relationship:
                                foundation["relationships"].append(relationship)

                except Exception as e:
                    self.logger.warning(f"Failed to load source '{source_name}': {e}")

            # Validate against schema template if provided
            if schema_template:
                self.progress_tracker.update_tracking(
                    tracking_id, message="Validating against schema template..."
                )
                foundation = self._validate_against_template(
                    foundation, schema_template
                )

            self.logger.info(
                f"Created foundation graph: {len(foundation['entities'])} entities, "
                f"{len(foundation['relationships'])} relationships"
            )
            self.progress_tracker.stop_tracking(
                tracking_id,
                status="completed",
                message=f"Created foundation graph: {len(foundation['entities'])} entities, {len(foundation['relationships'])} relationships",
            )
            return foundation

        except Exception as e:
            self.progress_tracker.stop_tracking(
                tracking_id, status="failed", message=str(e)
            )
            raise

    def integrate_with_extracted(
        self,
        seed_data: Dict[str, Any],
        extracted_data: Dict[str, Any],
        merge_strategy: str = "seed_first",
    ) -> Dict[str, Any]:
        """
        Integrate seed data with extracted data.

        Merges seed data with extracted data using a configurable merge strategy.
        Handles both entities and relationships, resolving conflicts based on
        the selected strategy.

        Args:
            seed_data: Seed data dictionary with 'entities' and 'relationships' keys
            extracted_data: Extracted data dictionary with 'entities' and 'relationships' keys
            merge_strategy: Merge strategy:
                - 'seed_first': Seed data takes precedence, extracted data fills gaps
                - 'extracted_first': Extracted data takes precedence, seed data fills gaps
                - 'merge': Merge properties, seed takes precedence for conflicts

        Returns:
            Integrated data dictionary with:
                - entities: Merged list of entities
                - relationships: Merged list of relationships
                - metadata: Merge metadata including timestamp, strategy, and counts

        Example:
            >>> integrated = manager.integrate_with_extracted(
            ...     seed_data, extracted_data, merge_strategy="merge"
            ... )
        """
        integrated = {
            "entities": [],
            "relationships": [],
            "metadata": {
                "merged_at": datetime.now().isoformat(),
                "merge_strategy": merge_strategy,
                "seed_count": len(seed_data.get("entities", [])),
                "extracted_count": len(extracted_data.get("entities", [])),
            },
        }

        seed_entities = {e.get("id"): e for e in seed_data.get("entities", [])}
        extracted_entities = {
            e.get("id"): e for e in extracted_data.get("entities", [])
        }

        # Merge entities based on strategy
        if merge_strategy == "seed_first":
            # Seed data takes precedence
            integrated["entities"] = list(seed_entities.values())
            for eid, entity in extracted_entities.items():
                if eid not in seed_entities:
                    integrated["entities"].append(entity)

        elif merge_strategy == "extracted_first":
            # Extracted data takes precedence
            integrated["entities"] = list(extracted_entities.values())
            for eid, entity in seed_entities.items():
                if eid not in extracted_entities:
                    integrated["entities"].append(entity)

        elif merge_strategy == "merge":
            # Merge properties, seed takes precedence for conflicts
            all_entity_ids = set(seed_entities.keys()) | set(extracted_entities.keys())
            for eid in all_entity_ids:
                seed_entity = seed_entities.get(eid, {})
                extracted_entity = extracted_entities.get(eid, {})

                merged = {**extracted_entity, **seed_entity}
                integrated["entities"].append(merged)

        # Merge relationships
        seed_rels = {
            (r.get("source_id"), r.get("target_id"), r.get("type")): r
            for r in seed_data.get("relationships", [])
        }
        extracted_rels = {
            (r.get("source_id"), r.get("target_id"), r.get("type")): r
            for r in extracted_data.get("relationships", [])
        }

        if merge_strategy == "seed_first":
            integrated["relationships"] = list(seed_rels.values())
            for key, rel in extracted_rels.items():
                if key not in seed_rels:
                    integrated["relationships"].append(rel)
        else:
            integrated["relationships"] = list(seed_rels.values())
            for key, rel in extracted_rels.items():
                if key not in seed_rels:
                    integrated["relationships"].append(rel)

        self.logger.info(
            f"Integrated data: {len(integrated['entities'])} entities, "
            f"{len(integrated['relationships'])} relationships"
        )

        return integrated

    def validate_quality(self, seed_data: Dict[str, Any], **options) -> Dict[str, Any]:
        """
        Validate seed data quality.

        Performs comprehensive quality checks on seed data including required
        fields, duplicate detection, and consistency validation.

        Args:
            seed_data: Seed data dictionary with 'entities' and 'relationships' keys
            **options: Validation options:
                - check_required_fields: Check required fields (default: True)
                - check_types: Validate data types (default: True)
                - check_consistency: Check consistency (default: True)

        Returns:
            Validation result dictionary with:
                - valid: Boolean indicating if data is valid
                - errors: List of error messages
                - warnings: List of warning messages
                - metrics: Dictionary with entity_count, relationship_count,
                  unique_entity_ids, duplicate_entities

        Example:
            >>> validation = manager.validate_quality(foundation)
            >>> if not validation["valid"]:
            ...     print(f"Found {len(validation['errors'])} errors")
        """
        tracking_id = self.progress_tracker.start_tracking(
            module="seed",
            submodule="SeedDataManager",
            message="Validating seed data quality",
        )

        try:
            results = {"valid": True, "errors": [], "warnings": [], "metrics": {}}

            entities = seed_data.get("entities", [])
            relationships = seed_data.get("relationships", [])

            # Check entities
            self.progress_tracker.update_tracking(
                tracking_id, message=f"Validating {len(entities)} entities..."
            )
            entity_ids = []
            for entity in entities:
                if "id" not in entity:
                    results["errors"].append("Entity missing 'id' field")
                    results["valid"] = False
                else:
                    if entity["id"] in entity_ids:
                        results["warnings"].append(
                            f"Duplicate entity ID: {entity['id']}"
                        )
                    entity_ids.append(entity["id"])

                if "type" not in entity:
                    results["warnings"].append(
                        f"Entity {entity.get('id')} missing 'type' field"
                    )

            # Check relationships
            self.progress_tracker.update_tracking(
                tracking_id, message=f"Validating {len(relationships)} relationships..."
            )
            for rel in relationships:
                if "source_id" not in rel or "target_id" not in rel:
                    results["errors"].append(
                        "Relationship missing source_id or target_id"
                    )
                    results["valid"] = False

                if "type" not in rel:
                    results["warnings"].append("Relationship missing 'type' field")

            # Calculate metrics
            results["metrics"] = {
                "entity_count": len(entities),
                "relationship_count": len(relationships),
                "unique_entity_ids": len(set(entity_ids)),
                "duplicate_entities": len(entities) - len(set(entity_ids)),
            }

            self.progress_tracker.stop_tracking(
                tracking_id,
                status="completed",
                message=f"Validation complete: {len(results['errors'])} errors, {len(results['warnings'])} warnings",
            )
            return results

        except Exception as e:
            self.progress_tracker.stop_tracking(
                tracking_id, status="failed", message=str(e)
            )
            raise

    def _record_to_entity(self, record: Dict[str, Any]) -> Optional[EntityDict]:
        """
        Convert record to entity dictionary.

        Converts a data record to a standardized entity dictionary format.
        Extracts id, text/name/label, type, confidence, and metadata.

        Args:
            record: Source data record dictionary

        Returns:
            Entity dictionary or None if record lacks required 'id' field
        """
        if "id" not in record:
            return None

        entity = {
            "id": record["id"],
            "text": record.get("text") or record.get("name") or record.get("label", ""),
            "type": record.get("entity_type") or record.get("type", "UNKNOWN"),
            "confidence": record.get("confidence", 1.0),
            "metadata": {
                k: v
                for k, v in record.items()
                if k
                not in [
                    "id",
                    "text",
                    "name",
                    "label",
                    "type",
                    "entity_type",
                    "confidence",
                ]
            },
        }

        return entity

    def _record_to_relationship(
        self, record: Dict[str, Any]
    ) -> Optional[RelationshipDict]:
        """
        Convert record to relationship dictionary.

        Converts a data record to a standardized relationship dictionary format.
        Extracts source_id, target_id, type, confidence, and metadata.

        Args:
            record: Source data record dictionary

        Returns:
            Relationship dictionary or None if record lacks required fields
        """
        if "source_id" not in record or "target_id" not in record:
            return None

        relationship = {
            "id": record.get("id") or f"{record['source_id']}_{record['target_id']}",
            "source_id": record["source_id"],
            "target_id": record["target_id"],
            "type": record.get("relationship_type") or record.get("type", "RELATED_TO"),
            "confidence": record.get("confidence", 1.0),
            "metadata": {
                k: v
                for k, v in record.items()
                if k
                not in [
                    "id",
                    "source_id",
                    "target_id",
                    "type",
                    "relationship_type",
                    "confidence",
                ]
            },
        }

        return relationship

    def _validate_against_template(
        self, foundation: Dict[str, Any], schema_template: Any
    ) -> Dict[str, Any]:
        """
        Validate foundation against schema template.

        Validates the foundation graph against a provided schema template.
        Currently a placeholder for future schema validation functionality.

        Args:
            foundation: Foundation graph dictionary
            schema_template: Schema template object

        Returns:
            Validated foundation graph dictionary
        """
        # This would use schema template validation if available
        # For now, just return the foundation
        return foundation

    def export_seed_data(
        self, file_path: Union[str, Path], format: str = "json"
    ) -> None:
        """
        Export seed data to file.

        Exports the current seed data to a file in the specified format.
        For CSV format, creates separate files for entities and relationships.

        Args:
            file_path: Output file path
            format: Export format ('json', 'csv')

        Raises:
            ProcessingError: If export fails

        Example:
            >>> manager.export_seed_data("output/seed_data.json", format="json")
            >>> manager.export_seed_data("output/seed_data", format="csv")
        """
        file_path = Path(file_path)

        if format == "json":
            export_data = {
                "entities": self.seed_data.entities,
                "relationships": self.seed_data.relationships,
                "metadata": {
                    **self.seed_data.metadata,
                    "exported_at": datetime.now().isoformat(),
                },
            }
            write_json_file(export_data, file_path)

        elif format == "csv":
            # Export entities to CSV
            entities_file = file_path.parent / f"{file_path.stem}_entities.csv"
            if self.seed_data.entities:
                with open(entities_file, "w", newline="", encoding="utf-8") as f:
                    writer = csv.DictWriter(
                        f, fieldnames=self.seed_data.entities[0].keys()
                    )
                    writer.writeheader()
                    writer.writerows(self.seed_data.entities)

            # Export relationships to CSV
            relationships_file = (
                file_path.parent / f"{file_path.stem}_relationships.csv"
            )
            if self.seed_data.relationships:
                with open(relationships_file, "w", newline="", encoding="utf-8") as f:
                    writer = csv.DictWriter(
                        f, fieldnames=self.seed_data.relationships[0].keys()
                    )
                    writer.writeheader()
                    writer.writerows(self.seed_data.relationships)

        self.logger.info(f"Exported seed data to: {file_path}")
