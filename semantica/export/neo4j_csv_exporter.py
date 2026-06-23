"""
Neo4j bulk CSV export for ``neo4j-admin database import``.

This module writes Semantica knowledge graphs to the two CSV files expected by
Neo4j's offline bulk importer:

``nodes.csv``::

    :id,:LABEL,name,type
    1,Person;Engineer,Alice,user

``relationships.csv``::

    :START_ID,:END_ID,:TYPE,since
    1,2,KNOWS,2024

Example import command::

    neo4j-admin database import full \\
      --nodes=nodes.csv \\
      --relationships=relationships.csv \\
      neo4j

The exporter accepts the canonical Semantica ``{"entities": ..., "relationships": ...}``
shape, graph-style ``{"nodes": ..., "edges": ...}`` dictionaries, and objects exposing
``.entities``/``.relationships`` or ``.nodes``/``.edges`` attributes. Existing node IDs
are reused when present; otherwise deterministic IDs are derived from node contents.
"""

from __future__ import annotations

import csv
import hashlib
import json
from dataclasses import asdict, is_dataclass
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Sequence, Union

from ..utils.exceptions import ProcessingError, ValidationError
from ..utils.helpers import ensure_directory
from ..utils.logging import get_logger
from ..utils.progress_tracker import get_progress_tracker


class Neo4jCSVExporter:
    """
    Export knowledge graphs to Neo4j bulk-import CSV files.

    The exporter creates deterministic ``nodes.csv`` and ``relationships.csv`` files
    under the requested output directory. Node property columns and relationship
    property columns are generated from the graph data and sorted alphabetically.

    Args:
        node_file_name: File name for node rows (default: ``nodes.csv``).
        relationship_file_name: File name for relationship rows
            (default: ``relationships.csv``).
        encoding: Output file encoding (default: ``utf-8``).
        delimiter: CSV delimiter (default: ``,``).
        label_separator: Neo4j label separator for ``:LABEL`` values
            (default: ``;``).
        strict: If true, raise on relationships that cannot be connected to an
            exported node. If false, unresolved endpoint values are written as-is.
        config: Optional configuration dictionary, merged with keyword overrides.

    Example:
        >>> from semantica.export import Neo4jCSVExporter
        >>> kg = {
        ...     "entities": [{"id": "1", "labels": ["Person"], "name": "Alice"}],
        ...     "relationships": [],
        ... }
        >>> Neo4jCSVExporter().export_knowledge_graph(kg, "neo4j_import")
    """

    NODE_ID_HEADER = ":id"
    NODE_LABEL_HEADER = ":LABEL"
    REL_START_HEADER = ":START_ID"
    REL_END_HEADER = ":END_ID"
    REL_TYPE_HEADER = ":TYPE"

    _NODE_ID_KEYS = ("id", "entity_id", "node_id", "_id", "key", "uid")
    _REL_ID_KEYS = ("id", "relationship_id", "edge_id", "_id", "key", "uid")
    _SOURCE_KEYS = (
        "source",
        "source_id",
        "from",
        "from_id",
        "subject",
        "start",
        "start_id",
    )
    _TARGET_KEYS = (
        "target",
        "target_id",
        "to",
        "to_id",
        "object",
        "end",
        "end_id",
    )
    _REL_TYPE_KEYS = (
        "type",
        "relationship_type",
        "relation_type",
        "predicate",
        "label",
    )
    _NODE_LABEL_KEYS = ("labels", "node_labels")

    _NODE_STRUCTURAL_KEYS = set(_NODE_ID_KEYS) | set(_NODE_LABEL_KEYS)
    _REL_STRUCTURAL_KEYS = (
        set(_REL_ID_KEYS) | set(_SOURCE_KEYS) | set(_TARGET_KEYS) | set(_REL_TYPE_KEYS)
    )

    def __init__(
        self,
        node_file_name: str = "nodes.csv",
        relationship_file_name: str = "relationships.csv",
        encoding: str = "utf-8",
        delimiter: str = ",",
        label_separator: str = ";",
        strict: bool = True,
        config: Optional[Dict[str, Any]] = None,
        **kwargs: Any,
    ) -> None:
        self.logger = get_logger("neo4j_csv_exporter")
        self.config = config or {}
        self.config.update(kwargs)

        self.node_file_name = self.config.get("node_file_name", node_file_name)
        self.relationship_file_name = self.config.get(
            "relationship_file_name", relationship_file_name
        )
        self.encoding = self.config.get("encoding", encoding)
        self.delimiter = self.config.get("delimiter", delimiter)
        self.label_separator = self.config.get("label_separator", label_separator)
        self.strict = bool(self.config.get("strict", strict))

        self._validate_file_name(self.node_file_name, "node_file_name")
        self._validate_file_name(self.relationship_file_name, "relationship_file_name")
        if not self.label_separator:
            raise ValueError("label_separator cannot be empty")
        if not self.delimiter:
            raise ValueError("delimiter cannot be empty")

        self.progress_tracker = get_progress_tracker()
        if not self.progress_tracker.enabled:
            self.progress_tracker.enabled = True

        self.logger.debug(
            "Neo4j CSV exporter initialized: nodes=%s, relationships=%s",
            self.node_file_name,
            self.relationship_file_name,
        )

    def export(
        self,
        knowledge_graph: Any,
        output_dir: Union[str, Path],
        validate: bool = False,
        **options: Any,
    ) -> Dict[str, Path]:
        """
        Export a graph to Neo4j bulk CSV files.

        Args:
            knowledge_graph: Graph dictionary or object with graph attributes.
            output_dir: Directory where ``nodes.csv`` and ``relationships.csv``
                will be written.
            validate: If true, validate written files and raise ``ValidationError``
                if they do not meet basic Neo4j import expectations.
            **options: Optional overrides for ``node_file_name``,
                ``relationship_file_name``, ``strict``, or CSV writer options.

        Returns:
            Mapping with ``"nodes"`` and ``"relationships"`` output paths.
        """
        output_dir = Path(output_dir)
        ensure_directory(output_dir)

        node_file_name = options.pop("node_file_name", self.node_file_name)
        relationship_file_name = options.pop(
            "relationship_file_name", self.relationship_file_name
        )
        strict = bool(options.pop("strict", self.strict))
        self._validate_file_name(node_file_name, "node_file_name")
        self._validate_file_name(relationship_file_name, "relationship_file_name")

        nodes_path = output_dir / node_file_name
        relationships_path = output_dir / relationship_file_name

        tracking_id = self.progress_tracker.start_tracking(
            file=str(output_dir),
            module="export",
            submodule="Neo4jCSVExporter",
            message=f"Exporting graph to Neo4j CSV directory: {output_dir}",
        )

        try:
            prepared = self._prepare_export(knowledge_graph, strict=strict)

            self._write_csv(
                nodes_path,
                [self.NODE_ID_HEADER, self.NODE_LABEL_HEADER]
                + prepared["node_columns"],
                prepared["node_rows"],
                **options,
            )
            self._write_csv(
                relationships_path,
                [
                    self.REL_START_HEADER,
                    self.REL_END_HEADER,
                    self.REL_TYPE_HEADER,
                ]
                + prepared["relationship_columns"],
                prepared["relationship_rows"],
                **options,
            )

            exported = {"nodes": nodes_path, "relationships": relationships_path}
            if validate:
                validation = self.validate_export(
                    output_dir,
                    node_file_name=node_file_name,
                    relationship_file_name=relationship_file_name,
                )
                if not validation["valid"]:
                    raise ValidationError(
                        "Neo4j CSV export validation failed",
                        errors=validation["errors"],
                    )

            self.progress_tracker.stop_tracking(
                tracking_id,
                status="completed",
                message=(
                    f"Exported {len(prepared['node_rows'])} node row(s) and "
                    f"{len(prepared['relationship_rows'])} relationship row(s)"
                ),
            )
            self.logger.info("Exported Neo4j CSV files to: %s", output_dir)
            return exported

        except Exception as exc:
            self.progress_tracker.stop_tracking(
                tracking_id, status="failed", message=str(exc)
            )
            if isinstance(exc, (ValidationError, ProcessingError)):
                raise
            raise ProcessingError(f"Failed to export Neo4j CSV files: {exc}") from exc

    def export_knowledge_graph(
        self,
        knowledge_graph: Any,
        output_dir: Union[str, Path],
        **options: Any,
    ) -> Dict[str, Path]:
        """Convenience wrapper around :meth:`export`."""
        return self.export(knowledge_graph, output_dir, **options)

    def export_nodes(
        self,
        nodes: Sequence[Any],
        output_dir: Union[str, Path],
        **options: Any,
    ) -> Dict[str, Path]:
        """Export node rows with an empty relationship file."""
        return self.export(
            {"entities": list(nodes), "relationships": []}, output_dir, **options
        )

    def export_relationships(
        self,
        relationships: Sequence[Any],
        output_dir: Union[str, Path],
        nodes: Optional[Sequence[Any]] = None,
        **options: Any,
    ) -> Dict[str, Path]:
        """Export relationship rows, optionally with the node rows they reference."""
        return self.export(
            {"entities": list(nodes or []), "relationships": list(relationships)},
            output_dir,
            **options,
        )

    def dry_run(self, knowledge_graph: Any, **options: Any) -> Dict[str, Any]:
        """
        Prepare and validate CSV content without writing files.

        Returns a summary containing headers, row counts, and validation errors.
        This is useful in CI or before running ``neo4j-admin database import``.
        """
        strict = bool(options.pop("strict", self.strict))
        prepared = self._prepare_export(knowledge_graph, strict=strict)
        validation = self._validate_prepared(prepared)
        return {
            "valid": validation["valid"],
            "errors": validation["errors"],
            "node_header": [self.NODE_ID_HEADER, self.NODE_LABEL_HEADER]
            + prepared["node_columns"],
            "relationship_header": [
                self.REL_START_HEADER,
                self.REL_END_HEADER,
                self.REL_TYPE_HEADER,
            ]
            + prepared["relationship_columns"],
            "node_count": len(prepared["node_rows"]),
            "relationship_count": len(prepared["relationship_rows"]),
        }

    def validate_export(
        self,
        output_dir: Union[str, Path],
        node_file_name: Optional[str] = None,
        relationship_file_name: Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        Validate written CSV files against core Neo4j import expectations.

        The validation checks required headers, consistent row widths, unique node
        IDs, non-empty relationship endpoints/types, and relationship endpoint
        references to exported node IDs.
        """
        output_dir = Path(output_dir)
        nodes_path = output_dir / (node_file_name or self.node_file_name)
        relationships_path = output_dir / (
            relationship_file_name or self.relationship_file_name
        )

        errors: List[str] = []
        node_ids: set = set()

        if not nodes_path.exists():
            errors.append(f"Missing node CSV file: {nodes_path}")
        else:
            try:
                with open(
                    nodes_path, "r", encoding=self.encoding, newline=""
                ) as handle:
                    reader = csv.reader(handle, delimiter=self.delimiter)
                    rows = list(reader)
                if not rows:
                    errors.append("Node CSV is empty")
                else:
                    header = rows[0]
                    if len(header) < 2 or header[:2] != [
                        self.NODE_ID_HEADER,
                        self.NODE_LABEL_HEADER,
                    ]:
                        errors.append("Node CSV header must start with ':id,:LABEL'")
                    for row_number, row in enumerate(rows[1:], start=2):
                        if len(row) != len(header):
                            errors.append(
                                f"Node row {row_number} has {len(row)} columns; "
                                f"expected {len(header)}"
                            )
                            continue
                        node_id = row[0]
                        if not node_id:
                            errors.append(f"Node row {row_number} has an empty :id")
                        elif node_id in node_ids:
                            errors.append(f"Duplicate node :id {node_id!r}")
                        else:
                            node_ids.add(node_id)
            except csv.Error as exc:
                errors.append(f"Node CSV parse error: {exc}")

        if not relationships_path.exists():
            errors.append(f"Missing relationship CSV file: {relationships_path}")
        else:
            try:
                with open(
                    relationships_path,
                    "r",
                    encoding=self.encoding,
                    newline="",
                ) as handle:
                    reader = csv.reader(handle, delimiter=self.delimiter)
                    rows = list(reader)
                if not rows:
                    errors.append("Relationship CSV is empty")
                else:
                    header = rows[0]
                    expected = [
                        self.REL_START_HEADER,
                        self.REL_END_HEADER,
                        self.REL_TYPE_HEADER,
                    ]
                    if len(header) < 3 or header[:3] != expected:
                        errors.append(
                            "Relationship CSV header must start with "
                            "':START_ID,:END_ID,:TYPE'"
                        )
                    for row_number, row in enumerate(rows[1:], start=2):
                        if len(row) != len(header):
                            errors.append(
                                f"Relationship row {row_number} has {len(row)} "
                                f"columns; expected {len(header)}"
                            )
                            continue
                        start_id, end_id, rel_type = row[:3]
                        if not start_id or not end_id:
                            errors.append(
                                f"Relationship row {row_number} has an empty endpoint"
                            )
                        if not rel_type:
                            errors.append(
                                f"Relationship row {row_number} has an empty :TYPE"
                            )
                        if node_ids and start_id and start_id not in node_ids:
                            errors.append(
                                f"Relationship row {row_number} references unknown "
                                f":START_ID {start_id!r}"
                            )
                        if node_ids and end_id and end_id not in node_ids:
                            errors.append(
                                f"Relationship row {row_number} references unknown "
                                f":END_ID {end_id!r}"
                            )
            except csv.Error as exc:
                errors.append(f"Relationship CSV parse error: {exc}")

        return {"valid": not errors, "errors": errors}

    def _prepare_export(self, graph: Any, strict: bool) -> Dict[str, Any]:
        normalized = self._normalize_graph(graph)
        node_infos = self._prepare_nodes(normalized["nodes"])

        node_columns = sorted(
            {key for node in node_infos for key in node["properties"].keys()}
        )

        alias_lookup = self._build_alias_lookup(node_infos)
        node_id_set = {node["id"] for node in node_infos}

        relationship_infos = self._prepare_relationships(
            normalized["relationships"],
            alias_lookup=alias_lookup,
            node_id_set=node_id_set,
            strict=strict,
        )
        relationship_columns = sorted(
            {
                key
                for relationship in relationship_infos
                for key in relationship["properties"].keys()
            }
        )

        node_rows = []
        for node in sorted(node_infos, key=lambda item: item["id"]):
            node_rows.append(
                [node["id"], self.label_separator.join(node["labels"])]
                + [
                    self._serialize_value(node["properties"].get(column))
                    for column in node_columns
                ]
            )

        relationship_rows = []
        for relationship in sorted(
            relationship_infos,
            key=lambda item: (
                item["start_id"],
                item["end_id"],
                item["type"],
                self._canonical_json(item["properties"]),
            ),
        ):
            relationship_rows.append(
                [
                    relationship["start_id"],
                    relationship["end_id"],
                    relationship["type"],
                ]
                + [
                    self._serialize_value(relationship["properties"].get(column))
                    for column in relationship_columns
                ]
            )

        prepared = {
            "node_rows": node_rows,
            "relationship_rows": relationship_rows,
            "node_columns": node_columns,
            "relationship_columns": relationship_columns,
        }
        validation = self._validate_prepared(prepared)
        if not validation["valid"]:
            raise ValidationError(
                "Neo4j CSV export data is invalid",
                errors=validation["errors"],
            )
        return prepared

    def _normalize_graph(self, graph: Any) -> Dict[str, List[Dict[str, Any]]]:
        if isinstance(graph, dict):
            nodes = graph.get("nodes") or graph.get("entities") or []
            relationships = graph.get("edges") or graph.get("relationships") or []
        else:
            nodes = getattr(graph, "nodes", None)
            if nodes is None:
                nodes = getattr(graph, "entities", None)
            relationships = getattr(graph, "edges", None)
            if relationships is None:
                relationships = getattr(graph, "relationships", None)
            if nodes is None and relationships is None:
                raise ProcessingError(
                    f"Cannot export object of type '{type(graph).__name__}': "
                    "expected a dict with 'entities'/'relationships' or "
                    "'nodes'/'edges', or an object exposing equivalent attributes."
                )

        return {
            "nodes": [self._record_to_dict(node) for node in list(nodes or [])],
            "relationships": [
                self._record_to_dict(relationship)
                for relationship in list(relationships or [])
            ],
        }

    def _prepare_nodes(self, nodes: Sequence[Dict[str, Any]]) -> List[Dict[str, Any]]:
        explicit_ids: Dict[str, int] = {}
        node_infos: List[Dict[str, Any]] = []

        for index, node in enumerate(nodes):
            explicit_id = self._first_value(node, self._NODE_ID_KEYS)
            has_explicit_id = explicit_id is not None and str(explicit_id) != ""
            base_id = (
                str(explicit_id) if has_explicit_id else self._derived_node_id(node)
            )

            if has_explicit_id:
                if base_id in explicit_ids:
                    raise ValidationError(
                        f"Duplicate node ID {base_id!r}",
                        first_index=explicit_ids[base_id],
                        duplicate_index=index,
                    )
                explicit_ids[base_id] = index

            node_infos.append(
                {
                    "base_id": base_id,
                    "has_explicit_id": has_explicit_id,
                    "original_index": index,
                    "record": node,
                    "canonical": self._canonical_json(node),
                    "labels": self._extract_node_labels(node),
                    "properties": self._extract_properties(
                        node, structural_keys=self._NODE_STRUCTURAL_KEYS
                    ),
                }
            )

        used_ids = set(explicit_ids.keys())
        generated_counts: Dict[str, int] = {}

        for node in sorted(
            node_infos,
            key=lambda item: (
                item["base_id"],
                item["canonical"],
                item["original_index"],
            ),
        ):
            if node["has_explicit_id"]:
                node["id"] = node["base_id"]
                continue

            base_id = node["base_id"]
            generated_counts[base_id] = generated_counts.get(base_id, 0) + 1
            suffix = generated_counts[base_id]
            candidate = base_id if suffix == 1 else f"{base_id}_{suffix}"
            while candidate in used_ids:
                suffix += 1
                generated_counts[base_id] = suffix
                candidate = f"{base_id}_{suffix}"
            used_ids.add(candidate)
            node["id"] = candidate

        return node_infos

    def _prepare_relationships(
        self,
        relationships: Sequence[Dict[str, Any]],
        alias_lookup: Dict[str, str],
        node_id_set: set,
        strict: bool,
    ) -> List[Dict[str, Any]]:
        relationship_infos = []

        for index, relationship in enumerate(relationships):
            raw_start = self._first_value(relationship, self._SOURCE_KEYS)
            raw_end = self._first_value(relationship, self._TARGET_KEYS)
            if raw_start is None or raw_end is None:
                raise ValidationError(
                    f"Relationship {index} is missing source or target",
                    relationship=relationship,
                )

            start_id = self._resolve_endpoint(raw_start, alias_lookup)
            end_id = self._resolve_endpoint(raw_end, alias_lookup)
            rel_type = self._extract_relationship_type(relationship)

            unresolved = [
                endpoint
                for endpoint in (start_id, end_id)
                if endpoint not in node_id_set
            ]
            if unresolved and strict:
                raise ValidationError(
                    f"Relationship {index} references unknown node ID(s): "
                    f"{', '.join(repr(endpoint) for endpoint in unresolved)}",
                    relationship=relationship,
                )

            relationship_infos.append(
                {
                    "start_id": start_id,
                    "end_id": end_id,
                    "type": rel_type,
                    "properties": self._extract_properties(
                        relationship, structural_keys=self._REL_STRUCTURAL_KEYS
                    ),
                }
            )

        return relationship_infos

    def _build_alias_lookup(
        self, node_infos: Sequence[Dict[str, Any]]
    ) -> Dict[str, str]:
        aliases: Dict[str, str] = {}
        ambiguous = set()

        for node in node_infos:
            for alias in self._node_aliases(node["record"], node["id"]):
                if alias in aliases and aliases[alias] != node["id"]:
                    ambiguous.add(alias)
                else:
                    aliases[alias] = node["id"]

        for alias in ambiguous:
            aliases.pop(alias, None)

        return aliases

    def _node_aliases(self, node: Dict[str, Any], stable_id: str) -> Iterable[str]:
        raw_aliases: List[Any] = [stable_id]
        raw_aliases.extend(node.get(key) for key in self._NODE_ID_KEYS)
        raw_aliases.extend(
            node.get(key)
            for key in ("name", "text", "label")
            if not isinstance(node.get(key), (list, tuple, set, dict))
        )

        nested_properties = node.get("properties")
        if isinstance(nested_properties, dict):
            raw_aliases.extend(
                nested_properties.get(key)
                for key in self._NODE_ID_KEYS + ("name", "text", "label")
            )

        for alias in raw_aliases:
            if alias is not None and str(alias) != "":
                yield str(alias)

    def _extract_node_labels(self, node: Dict[str, Any]) -> List[str]:
        label_values: List[Any] = []

        for key in self._NODE_LABEL_KEYS:
            if key in node:
                label_values.extend(self._coerce_sequence(node[key]))

        label_field = node.get("label")
        if isinstance(label_field, (list, tuple, set)):
            label_values.extend(self._coerce_sequence(label_field))

        if not label_values:
            node_type = node.get("type") or node.get("entity_type")
            label_values.extend(self._coerce_sequence(node_type))

        labels: List[str] = []
        seen = set()
        for label in label_values:
            token = self._sanitize_token(str(label), fallback="")
            if token and token not in seen:
                labels.append(token)
                seen.add(token)

        return labels or ["Entity"]

    def _extract_relationship_type(self, relationship: Dict[str, Any]) -> str:
        rel_type = self._first_value(relationship, self._REL_TYPE_KEYS)
        return self._sanitize_token(str(rel_type or ""), fallback="RELATED_TO")

    def _extract_properties(
        self, record: Dict[str, Any], structural_keys: set
    ) -> Dict[str, Any]:
        properties: Dict[str, Any] = {}

        nested_properties = record.get("properties")
        if isinstance(nested_properties, dict):
            for key, value in nested_properties.items():
                properties[str(key)] = value

        for key, value in record.items():
            if key in structural_keys or key == "properties":
                continue
            properties[str(key)] = value

        return properties

    def _resolve_endpoint(self, value: Any, alias_lookup: Dict[str, str]) -> str:
        if isinstance(value, dict) or is_dataclass(value):
            endpoint_record = self._record_to_dict(value)
            endpoint_id = self._first_value(endpoint_record, self._NODE_ID_KEYS)
            if endpoint_id is None:
                endpoint_id = (
                    endpoint_record.get("name")
                    or endpoint_record.get("text")
                    or endpoint_record.get("label")
                )
            if endpoint_id is None:
                endpoint_id = self._derived_node_id(endpoint_record)
            value = endpoint_id
        elif not isinstance(value, str) and hasattr(value, "__dict__"):
            return self._resolve_endpoint(self._record_to_dict(value), alias_lookup)

        endpoint = str(value)
        return alias_lookup.get(endpoint, endpoint)

    def _first_value(self, record: Dict[str, Any], keys: Sequence[str]) -> Any:
        for key in keys:
            if key in record and record[key] is not None:
                return record[key]
        return None

    def _record_to_dict(self, record: Any) -> Dict[str, Any]:
        if isinstance(record, dict):
            return dict(record)
        if is_dataclass(record):
            return asdict(record)
        if hasattr(record, "__dict__"):
            return {
                key: value
                for key, value in vars(record).items()
                if not key.startswith("_")
            }
        raise ValidationError(
            f"Expected graph records to be dictionaries or objects, got "
            f"{type(record).__name__}"
        )

    def _derived_node_id(self, node: Dict[str, Any]) -> str:
        digest = hashlib.sha256(self._canonical_json(node).encode("utf-8")).hexdigest()
        return f"n_{digest[:16]}"

    def _canonical_json(self, value: Any) -> str:
        return json.dumps(
            self._to_jsonable(value),
            sort_keys=True,
            ensure_ascii=False,
            separators=(",", ":"),
        )

    def _to_jsonable(self, value: Any) -> Any:
        if isinstance(value, dict):
            return {str(key): self._to_jsonable(val) for key, val in value.items()}
        if isinstance(value, (list, tuple)):
            return [self._to_jsonable(item) for item in value]
        if isinstance(value, set):
            return sorted(self._to_jsonable(item) for item in value)
        if is_dataclass(value):
            return self._to_jsonable(asdict(value))
        if isinstance(value, (str, int, float, bool)) or value is None:
            return value
        return str(value)

    def _serialize_value(self, value: Any) -> str:
        if value is None:
            return ""
        if isinstance(value, bool):
            return "true" if value else "false"
        if isinstance(value, (dict, list, tuple, set)) or is_dataclass(value):
            return self._canonical_json(value)
        return str(value)

    def _coerce_sequence(self, value: Any) -> List[Any]:
        if value is None:
            return []
        if isinstance(value, str):
            if self.label_separator in value:
                return [part for part in value.split(self.label_separator) if part]
            return [value]
        if isinstance(value, set):
            return sorted(value)
        if isinstance(value, (list, tuple)):
            return list(value)
        return [value]

    def _sanitize_token(self, value: str, fallback: str) -> str:
        token = value.strip()
        if not token:
            return fallback

        sanitized = []
        for char in token:
            if char.isalnum() or char == "_":
                sanitized.append(char)
            else:
                sanitized.append("_")

        result = "".join(sanitized).strip("_")
        if not result:
            return fallback
        if not (result[0].isalpha() or result[0] == "_"):
            result = f"_{result}"
        return result

    # Valid csv.writer dialect params other than delimiter/lineterminator/quoting
    # (those three are always supplied explicitly below).
    _CSV_WRITER_PARAMS = frozenset(
        {"quotechar", "doublequote", "skipinitialspace", "escapechar", "strict"}
    )

    def _write_csv(
        self,
        file_path: Path,
        header: List[str],
        rows: List[List[str]],
        **options: Any,
    ) -> None:
        lineterminator = options.get("lineterminator", "\n")
        quoting = options.get("quoting", csv.QUOTE_MINIMAL)
        # Only forward recognised csv.writer dialect params so that arbitrary
        # caller kwargs (e.g. encoding, validate, node_file_name) do not
        # trigger TypeError: csv.writer() got unexpected keyword argument.
        writer_options = {
            key: value
            for key, value in options.items()
            if key in self._CSV_WRITER_PARAMS
        }

        with open(file_path, "w", encoding=self.encoding, newline="") as handle:
            writer = csv.writer(
                handle,
                delimiter=self.delimiter,
                lineterminator=lineterminator,
                quoting=quoting,
                **writer_options,
            )
            writer.writerow(header)
            writer.writerows(rows)

    def _validate_prepared(self, prepared: Dict[str, Any]) -> Dict[str, Any]:
        errors: List[str] = []
        node_ids = [row[0] for row in prepared["node_rows"]]
        node_id_set = set(node_ids)

        if len(node_ids) != len(node_id_set):
            errors.append("Node rows contain duplicate :id values")

        for row_number, row in enumerate(prepared["node_rows"], start=2):
            expected = 2 + len(prepared["node_columns"])
            if len(row) != expected:
                errors.append(
                    f"Node row {row_number} has {len(row)} columns; expected {expected}"
                )
            if not row[0]:
                errors.append(f"Node row {row_number} has an empty :id")

        for row_number, row in enumerate(prepared["relationship_rows"], start=2):
            expected = 3 + len(prepared["relationship_columns"])
            if len(row) != expected:
                errors.append(
                    f"Relationship row {row_number} has {len(row)} columns; "
                    f"expected {expected}"
                )
                continue
            start_id, end_id, rel_type = row[:3]
            if not start_id or not end_id:
                errors.append(f"Relationship row {row_number} has an empty endpoint")
            if not rel_type:
                errors.append(f"Relationship row {row_number} has an empty :TYPE")
            if node_id_set and start_id and start_id not in node_id_set:
                errors.append(
                    f"Relationship row {row_number} references unknown :START_ID "
                    f"{start_id!r}"
                )
            if node_id_set and end_id and end_id not in node_id_set:
                errors.append(
                    f"Relationship row {row_number} references unknown :END_ID "
                    f"{end_id!r}"
                )

        return {"valid": not errors, "errors": errors}

    def _validate_file_name(self, file_name: str, param_name: str) -> None:
        if not file_name:
            raise ValueError(f"{param_name} cannot be empty")
        path = Path(file_name)
        if path.name != file_name:
            raise ValueError(f"{param_name} must be a file name, not a path")
