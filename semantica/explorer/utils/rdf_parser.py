"""
RDF / SKOS parsing utility for the knowledge Explorer

Parses `.ttl` and `.rdf` files, extracting skos:Concept and skos:ConceptScheme entities into flat dicts 
compatible with ContextGraph.
"""

from typing import Any, Dict, List, Tuple
import importlib.util
import rdflib
from rdflib.namespace import RDF, RDFS, SKOS

_HAS_DEFUSEDXML = importlib.util.find_spec("defusedxml") is not None


def _safe_parse_rdf(g: rdflib.Graph, data: bytes, rdf_format: str) -> None:
    """Parse RDF bytes into *g*, guarding against XXE for XML-based formats.

    Raises:
        ImportError: If ``defusedxml`` is not installed and the format is XML-based.
    """
    xml_formats = {"xml", "rdf", "rdf/xml", "application/rdf+xml"}
    if rdf_format.lower() in xml_formats:
        if not _HAS_DEFUSEDXML:
            # Fail closed: refuse to parse untrusted XML without XXE protection.
            raise ImportError(
                "defusedxml is required to safely parse RDF/XML content but is "
                "not installed. Install it with: pip install defusedxml  "
                "(or install semantica with the explorer extra: "
                "pip install 'semantica[explorer]')"
            )
        import defusedxml
        defusedxml.defuse_stdlib()
    g.parse(data=data, format=rdf_format)

def _get_best_label(graph: rdflib.Graph, subject: rdflib.URIRef, predicate: rdflib.URIRef) -> str:
    """
    Extracts the best available string label for a given predicate.
    Prioritizes English tags ('en'), then untagged strings, then falls back to whatever
    is available. Strips language tags in the process.
    """
    
    labels = list(graph.objects(subject, predicate))
    if not labels:
        return ""
    
    # priority 1: English match exact
    for lbl in labels:
        if getattr(lbl, "language", None) == "en":
            return str(lbl)
    
    # priority 2: English variants
    for lbl in labels:
        lang = getattr(lbl, "language", "")
        if lang and lang.startswith("en"):
            return str(lbl)
    
    # priority 3: No lang tag
    for lbl in labels:
        if getattr(lbl, "language", None) is None:
            return str(lbl)
    
    # whatever is first if not any of the three above
    return str(labels[0])

def _get_all_labels(graph: rdflib.Graph, subject: rdflib.URIRef, predicate: rdflib.URIRef) -> List[str]:
    """ Returns a list of all string values for a predicate, stripping lang tags."""
    return list({str(lbl) for lbl in graph.objects(subject, predicate)})

def parse_skos_file(file_bytes: bytes, rdf_format: str = "turtle") -> Tuple[List[Dict[str, Any]], List[Dict[str, Any]]]:
    """
    Parses RDF data and extracts SKOS concepts and relationships.

    Args:
        file_bytes: The raw bytes of the uploaded file.
        rdf_format: The rdflib parse format (e.g., "turtle" for .ttl, "xml" for .rdf).

    Returns:
        A tuple of (nodes_list, edges_list) formatted for ContextGraph ingestion.

    Note:
        Edges are only emitted when both endpoints exist in the parsed file.
        Relationships pointing to external URIs not declared as skos:Concept or
        skos:ConceptScheme (e.g. cross-vocabulary broader links) are silently dropped.
    """

    g = rdflib.Graph()

    try:
        _safe_parse_rdf(g, file_bytes, rdf_format)
    except Exception as e:
        raise ValueError(f"Failed to parse RDF file as {rdf_format}. Ensure the file is valid. Details: {str(e)}") from e
    
    nodes_dict: Dict[str, Dict[str, Any]] = {}
    edges: List[Dict[str, Any]] = []
    
    # extract concept schemas
    for scheme in g.subjects(RDF.type, SKOS.ConceptScheme):
        uri = str(scheme)
    
        # if no prefLabel
        
        pref_label = _get_best_label(g, scheme, SKOS.prefLabel)
        if not pref_label:
            pref_label = uri.split("/")[-1].split("#")[-1]
        
        nodes_dict[uri] = {
            "id": uri,
            "type": "skos:ConceptScheme",
            "properties": {
                "content": pref_label,
                "alt_labels": _get_all_labels(g, scheme, SKOS.altLabel),
                "description": _get_best_label(g, scheme, SKOS.definition)
            }
        }
    
    # Extract concepts
    for concept in g.subjects(RDF.type, SKOS.Concept):
        uri = str(concept)
        
        pref_label = _get_best_label(g, concept, SKOS.prefLabel)
        if not pref_label:
            pref_label = uri.split("/")[-1].split("#")[-1]
        
        nodes_dict[uri] = {
            "id": uri,
            "type": "skos:Concept",
            "properties": {
                "content": pref_label,
                "alt_labels": _get_all_labels(g, concept, SKOS.altLabel),
                "description": _get_best_label(g, concept, SKOS.definition)
            }
        }
        
    
    # Extract Relationships aka edges
    
    structural_preds = {
        SKOS.broader: "skos:broader",
        SKOS.narrower: "skos:narrower",
        SKOS.inScheme: "skos:inScheme",
        SKOS.related: "skos:related",
        SKOS.topConceptOf: "skos:topConceptOf",
        SKOS.hasTopConcept: "skos:hasTopConcept"
    }
    
    for pred, edge_type in structural_preds.items():
        for source, target in g.subject_objects(pred):
            # Only track edges where nodes were successfully extracted
            if str(source) in nodes_dict and str(target) in nodes_dict:
                edges.append({
                    "source_id": str(source),
                    "target_id": str(target),
                    "type": edge_type,
                    "weight": 1.0,
                    "properties": {}
                })
    
    
    return list(nodes_dict.values()), edges
    
    
