"""
Ontology Ingestion Module

This module provides capabilities to ingest external ontologies from files (OWL, RDF, TTL, etc.)
and convert them into Semantica's internal ontology dictionary format.

Supported Formats:
    - Turtle (.ttl): Terse RDF Triple Language. A concise, human-readable
      format for representing RDF graphs. Commonly used for writing
      ontologies by hand.
    - RDF/XML (.rdf, .owl): The XML serialization of RDF. The standard
      format for OWL (Web Ontology Language) ontologies and often used
      for data interchange.
    - JSON-LD (.jsonld): JSON for Linked Data. A lightweight Linked Data
      format that is easy for humans to read and for machines to parse
      and generate. Ideal for web-based applications.
    - N-Triples (.nt): A line-based, plain text format for encoding an
      RDF graph. Each line represents a single triple. Very simple to
      parse but verbose.
    - Notation3 (.n3): A superset of Turtle that adds features like logic
      and rules.

Key Features:
    - Support for multiple RDF formats (Turtle, RDF/XML, JSON-LD, N3, NT)
    - Automatic parsing using rdflib
    - Conversion to Semantica ontology structure
    - Batch processing of ontology files
    - Extraction of classes, properties, and metadata

Example Usage:
    >>> from semantica.ingest import OntologyIngestor
    >>> ingestor = OntologyIngestor()
    >>> ontology = ingestor.ingest_ontology("my_ontology.ttl")
"""

import os
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional, Union

import rdflib
from rdflib import RDF, RDFS, OWL, Dataset, Graph

from ..utils.exceptions import ProcessingError, ValidationError
from ..utils.logging import get_logger
from ..utils.progress_tracker import get_progress_tracker


@dataclass
class OntologyData:
    """Ontology data representation."""

    data: Dict[str, Any]
    source_path: str
    format: str
    metadata: Dict[str, Any] = field(default_factory=dict)
    ingested_at: datetime = field(default_factory=datetime.now)


class OntologyIngestor:
    """
    Ontology ingestion handler.

    This class parses OWL/RDF files and converts them to Semantica's ontology dictionary format.
    """

    def __init__(self, config: Optional[Dict[str, Any]] = None, **kwargs):
        """
        Initialize ontology ingestor.

        Args:
            config: Optional configuration dictionary
            **kwargs: Additional configuration parameters
        """
        self.logger = get_logger("ontology_ingestor")
        self.progress = get_progress_tracker()
        self.config = config or {}
        self.config.update(kwargs)

    def ingest_ontology(self, file_path: Union[str, Path], format: Optional[str] = None, **kwargs) -> OntologyData:
        """
        Ingest an ontology file.

        Args:
            file_path: Path to the ontology file (string or Path object)
            format: Optional format hint (e.g., 'turtle', 'xml'). If None, rdflib guesses.
            **kwargs: Additional arguments for rdflib parsing

        Returns:
            OntologyData object containing the parsed ontology and metadata
        """
        file_path = Path(file_path)

        # Track file ingestion
        tracking_id = self.progress.start_tracking(
            file=str(file_path),
            module="ingest",
            submodule="OntologyIngestor",
            message=f"Ontology: {file_path.name}",
        )

        try:
            # Validate file exists
            if not file_path.exists():
                raise ValidationError(f"File not found: {file_path}")

            self.progress.update_tracking(tracking_id, message="Parsing RDF graph...")
            # `Dataset`, not `Graph`: a JSON-LD document with a top-level `@id` *and*
            # `@graph` places its terms in a NAMED graph. `Graph.parse()` loads only the
            # default graph and discards the rest without an error, so every class and
            # property in such a document was dropped while the load reported success.
            # Same migration #757 made for JenaStore; the ingest path was not covered by it.
            # `default_union=True` makes the Dataset itself present triples from every
            # graph as one merged view (it is an rdflib.Graph subclass, so it satisfies
            # _convert_to_dict()'s Graph-typed contract directly) instead of copying every
            # quad into a second in-memory Graph.
            ds = Dataset(default_union=True)

            # Use provided format or let rdflib guess based on extension
            parse_kwargs = kwargs.copy()
            if format:
                parse_kwargs['format'] = format

            try:
                ds.parse(file_path, **parse_kwargs)
            except Exception as e:
                # Fallback: try to guess format from extension if not provided and initial parse failed
                if not format:
                    ext = os.path.splitext(file_path)[1].lower()
                    fmt_map = {
                        '.ttl': 'turtle',
                        '.owl': 'xml', # OWL is often XML
                        '.rdf': 'xml',
                        '.jsonld': 'json-ld',
                        '.n3': 'n3',
                        '.nt': 'nt'
                    }
                    guessed_fmt = fmt_map.get(ext)
                    if guessed_fmt:
                        self.logger.info(f"Retrying with guessed format: {guessed_fmt}")
                        ds.parse(file_path, format=guessed_fmt, **kwargs)
                    else:
                        raise e
                else:
                    raise e

            g = ds

            self.progress.update_tracking(tracking_id, message="Converting to internal format...")
            
            # Determine format for metadata
            used_format = format
            if not used_format:
                ext = os.path.splitext(file_path)[1].lower()
                fmt_map = {
                    '.ttl': 'turtle',
                    '.owl': 'xml',
                    '.rdf': 'xml',
                    '.jsonld': 'json-ld',
                    '.n3': 'n3',
                    '.nt': 'nt'
                }
                used_format = fmt_map.get(ext, 'unknown')

            ontology_dict = self._convert_to_dict(g, source_path=str(file_path), format=used_format)

            ontology_data = OntologyData(
                data=ontology_dict,
                source_path=str(file_path),
                format=used_format,
                metadata=ontology_dict.get("metadata", {}).copy()
            )

            self.progress.stop_tracking(
                tracking_id,
                status="completed",
                message=f"Successfully ingested ontology from {file_path}",
            )
            
            return ontology_data

        except Exception as e:
            self.logger.error(f"Failed to ingest ontology: {str(e)}")
            self.progress.stop_tracking(
                tracking_id, status="failed", message=str(e)
            )
            raise ProcessingError(f"Failed to ingest ontology: {str(e)}") from e

    def ingest_directory(self, directory_path: Union[str, Path], recursive: bool = True, **kwargs) -> List[OntologyData]:
        """
        Ingest all ontology files in a directory.

        Args:
            directory_path: Path to the directory (string or Path object)
            recursive: Whether to search recursively
            **kwargs: Additional arguments

        Returns:
            List of OntologyData objects
        """
        directory_path = Path(directory_path)
        ontologies = []
        extensions = {'.ttl', '.owl', '.rdf', '.jsonld', '.n3', '.nt'}
        
        # Track directory ingestion
        tracking_id = self.progress.start_tracking(
            file=str(directory_path),
            module="ingest",
            submodule="OntologyIngestor",
            message=f"Directory: {directory_path.name}",
        )

        try:
            if not directory_path.exists():
                raise ValidationError(f"Directory not found: {directory_path}")
                
            if not directory_path.is_dir():
                raise ValidationError(f"Path is not a directory: {directory_path}")

            files_to_process = []
            for root, _, files in os.walk(directory_path):
                for file in files:
                    ext = os.path.splitext(file)[1].lower()
                    if ext in extensions:
                        files_to_process.append(os.path.join(root, file))
                
                if not recursive:
                    break
            
            total_files = len(files_to_process)
            self.progress.update_tracking(
                tracking_id, message=f"Processing {total_files} ontology files"
            )

            for idx, file_path in enumerate(files_to_process, 1):
                try:
                    ont_data = self.ingest_ontology(file_path, **kwargs)
                    ontologies.append(ont_data)
                    
                    self.progress.update_progress(
                        tracking_id,
                        processed=idx,
                        total=total_files,
                        message=f"Processing {idx}/{total_files}: {Path(file_path).name}"
                    )
                except Exception as e:
                    self.logger.warning(f"Skipping {file_path}: {e}")
            
            self.progress.stop_tracking(
                tracking_id,
                status="completed",
                message=f"Ingested {len(ontologies)} ontologies",
            )
            return ontologies

        except Exception as e:
            self.progress.stop_tracking(
                tracking_id, status="failed", message=str(e)
            )
            raise

    def _convert_to_dict(self, graph: Graph, source_path: str, format: str = "unknown") -> Dict[str, Any]:
        """
        Convert rdflib Graph to Semantica ontology dictionary.

        Args:
            graph: Parsed rdflib Graph
            source_path: Source file path
            format: Format of the ontology file

        Returns:
            Ontology dictionary
        """
        ontology = {
            "uri": "",
            "name": os.path.basename(source_path),
            "version": "1.0",
            "classes": [],
            "properties": [],
            "metadata": {
                "source_path": source_path,
                "ingested_at": datetime.now().isoformat(),
                "format": format
            }
        }

        # 1. Extract Ontology Metadata
        for s, p, o in graph.triples((None, RDF.type, OWL.Ontology)):
            ontology["uri"] = str(s)
            
            # Try to find label/comment/versionInfo
            for _, _, label in graph.triples((s, RDFS.label, None)):
                ontology["name"] = str(label)
                
            for _, _, comment in graph.triples((s, RDFS.comment, None)):
                ontology["description"] = str(comment)
                
            for _, _, version in graph.triples((s, OWL.versionInfo, None)):
                ontology["version"] = str(version)
            
            # Break after first ontology definition found (usually only one per file)
            break
            
        # 2. Extract Classes
        classes = {}
        # Union of owl:Class and rdfs:Class
        class_types = [OWL.Class, RDFS.Class]
        for c_type in class_types:
            for s, p, o in graph.triples((None, RDF.type, c_type)):
                if isinstance(s, rdflib.BNode):
                    continue # Skip blank nodes for now
                    
                uri = str(s)
                if uri not in classes:
                    cls_def = {
                        "uri": uri,
                        "name": self._get_local_name(uri),
                        "type": "class"
                    }
                    
                    # Add label/comment
                    label = graph.value(s, RDFS.label)
                    if label:
                        cls_def["label"] = str(label)
                        cls_def["name"] = str(label) # Prefer label as name if available? Or keep URI fragment? 
                        # Keeping local name from URI is safer for internal IDs, label for display. 
                        # But Semantica seems to use "name" for the identifier in some examples.
                        # Let's keep name as local name or label if simple.
                    
                    comment = graph.value(s, RDFS.comment)
                    if comment:
                        cls_def["description"] = str(comment)
                        
                    # Superclasses
                    parents = []
                    for _, _, parent in graph.triples((s, RDFS.subClassOf, None)):
                        if isinstance(parent, rdflib.URIRef):
                            parents.append(str(parent))
                    if parents:
                        cls_def["parents"] = parents
                        
                    classes[uri] = cls_def
        
        ontology["classes"] = list(classes.values())

        # 3. Extract Properties
        properties = {}
        # Object Properties
        for s, p, o in graph.triples((None, RDF.type, OWL.ObjectProperty)):
            self._add_property(graph, s, "object", properties)
            
        # Datatype Properties
        for s, p, o in graph.triples((None, RDF.type, OWL.DatatypeProperty)):
            self._add_property(graph, s, "data", properties)
            
        # RDF Properties (generic)
        for s, p, o in graph.triples((None, RDF.type, RDF.Property)):
            if str(s) not in properties: # Don't overwrite if already found as specific type
                self._add_property(graph, s, "annotation", properties) # Default to annotation or generic
        
        ontology["properties"] = list(properties.values())
        
        return ontology

    def _add_property(self, graph: Graph, subject: rdflib.term.Node, prop_type: str, properties_dict: Dict):
        if isinstance(subject, rdflib.BNode):
            return

        uri = str(subject)
        if uri in properties_dict:
            return
            
        prop_def = {
            "uri": uri,
            "name": self._get_local_name(uri),
            "type": prop_type
        }
        
        label = graph.value(subject, RDFS.label)
        if label:
            prop_def["label"] = str(label)
            
        comment = graph.value(subject, RDFS.comment)
        if comment:
            prop_def["description"] = str(comment)
            
        # Domain and Range
        domain = graph.value(subject, RDFS.domain)
        if domain and isinstance(domain, rdflib.URIRef):
            prop_def["domain"] = str(domain)
            
        range_val = graph.value(subject, RDFS.range)
        if range_val and isinstance(range_val, rdflib.URIRef):
            prop_def["range"] = str(range_val)
            
        properties_dict[uri] = prop_def

    def _get_local_name(self, uri: str) -> str:
        """Extract local name from URI."""
        if '#' in uri:
            return uri.split('#')[-1]
        return uri.split('/')[-1]
