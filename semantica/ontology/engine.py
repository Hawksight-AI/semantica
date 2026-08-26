from typing import Any, Dict, List, Optional

from ..utils.exceptions import ProcessingError
from ..utils.logging import get_logger
from ..utils.progress_tracker import get_progress_tracker
from .ontology_generator import OntologyGenerator
from .class_inferrer import ClassInferrer
from .property_generator import PropertyGenerator
from .owl_generator import OWLGenerator
from .ontology_evaluator import OntologyEvaluator
from .ontology_validator import OntologyValidator
from .llm_generator import LLMOntologyGenerator
from ..semantic_extract.triplet_extractor import Triplet


class OntologyEngine:
    def __init__(self, **config):
        self.logger = get_logger("ontology_engine")
        self.progress = get_progress_tracker()
        self.config = config

        self.generator = OntologyGenerator(**config)
        self.inferrer = ClassInferrer(**config)
        self.propgen = PropertyGenerator(**config)
        self.owl = OWLGenerator(**config)
        self.evaluator = OntologyEvaluator(**config)
        self.validator = OntologyValidator(**config)
        self.llm = LLMOntologyGenerator(**config)
        self.store = config.get("store")

        # Deferred to avoid circular import: change_management → ontology → change_management
        from ..change_management.ontology_version_manager import VersionManager
        self.version_manager = config.get("version_manager") or VersionManager(**config)

    def from_data(self, data: Dict[str, Any], **options) -> Dict[str, Any]:
        tracking_id = self.progress.start_tracking(
            module="ontology",
            submodule="OntologyEngine",
            message="Generating ontology from data",
        )
        try:
            ontology = self.generator.generate_ontology(data, **options)
            self.progress.update_tracking(tracking_id, message="Ontology generated")
            return ontology
        except Exception as e:
            self.progress.update_tracking(tracking_id, message="Generation failed")
            raise

    def from_text(self, text: str, provider: Optional[str] = None, model: Optional[str] = None, **options) -> Dict[str, Any]:
        if provider:
            self.llm.set_provider(provider, model=model)
        return self.llm.generate_ontology_from_text(text, **options)

    def infer_classes(self, entities: List[Dict[str, Any]], **options) -> List[Dict[str, Any]]:
        return self.inferrer.infer_classes(entities, **options)

    def infer_properties(
        self,
        entities: List[Dict[str, Any]],
        relationships: List[Dict[str, Any]],
        classes: List[Dict[str, Any]],
        **options,
    ) -> List[Dict[str, Any]]:
        return self.propgen.infer_properties(entities, relationships, classes, **options)
    
    def _sanitize_uri(self, uri: str) -> str:
        """Prevent SPARQL injection by percent-encoding dangerous characters."""
        if not isinstance(uri, str):
            return ""
        return uri.replace("<", "%3C").replace(">", "%3E")
    
    def create_alignment(self, source_uri: str, target_uri: str, predicate: str, **options) -> None:
        """
        Creates an alignment between two ontology entities and stores it.
        """
        if not self.store:
            raise ProcessingError("TripletStore instance not configured in OntologyEngine.")

        if not predicate.startswith(("http://", "https://")):
            raise ProcessingError(
                f"predicate must be a full URI (e.g. 'http://www.w3.org/2002/07/owl#equivalentClass'), "
                f"not a CURIE: '{predicate}'"
            )

        tracking_id = self.progress.start_tracking(
            module="ontology",
            submodule="OntologyEngine",
            message=f"Creating alignment: {source_uri} -> {target_uri}"
        )
        try:
            triplet = Triplet(subject=source_uri, predicate=predicate, object=target_uri)
            self.store.add_triplet(triplet, **options)
            
            self.progress.stop_tracking(tracking_id, status="completed", message="Alignment created")
        except Exception as e:
            self.progress.stop_tracking(tracking_id, status="failed", message=str(e))
            self.logger.error(f"Failed to create alignment: {e}")
            raise ProcessingError(f"Alignment creation failed: {e}")

    def get_alignments(self, entity_uri: str, **options) -> List[Dict[str, Any]]:
        """
        Retrieves all alignments for a specific entity URI (bidirectional).
        """
        if not self.store:
            raise ProcessingError("TripletStore instance not configured in OntologyEngine.")
        
        safe_uri = self._sanitize_uri(entity_uri)

        query = f"""
        SELECT ?s ?p ?o WHERE {{
            {{ <{safe_uri}> ?p ?o . BIND(<{safe_uri}> AS ?s) }}
            UNION
            {{ ?s ?p <{safe_uri}> . BIND(<{safe_uri}> AS ?o) }}
            
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
        try:
            results = self.store.execute_query(query, **options)

            alignments = []
            if hasattr(results, 'bindings'):
                for b in results.bindings:
                    alignments.append({
                        "source": b.get("s", {}).get("value") if isinstance(b.get("s"), dict) else b.get("s"),
                        "predicate": b.get("p", {}).get("value") if isinstance(b.get("p"), dict) else b.get("p"),
                        "target": b.get("o", {}).get("value") if isinstance(b.get("o"), dict) else b.get("o")
                    })
            return alignments
        except Exception as e:
            self.logger.error(f"Failed to get alignments for {entity_uri}: {e}")
            raise ProcessingError(f"Failed to get alignments: {e}")

    def list_alignments(self, ontology_uri: Optional[str] = None, **options) -> List[Dict[str, Any]]:
        """
        Lists all alignments, optionally filtered by an ontology URI.
        """
        if not self.store:
            raise ProcessingError("TripletStore instance not configured in OntologyEngine.")

        filter_clause = ""
        if ontology_uri:
            # Sanitize characters that could break out of the SPARQL string literal or WHERE block
            safe_ontology_uri = (
                ontology_uri
                .replace("\\", "%5C")
                .replace('"', '%22')
                .replace("{", "%7B")
                .replace("}", "%7D")
            )
            filter_clause = f'FILTER(STRSTARTS(STR(?s), "{safe_ontology_uri}") || STRSTARTS(STR(?o), "{safe_ontology_uri}"))'

        query = f"""
        SELECT ?s ?p ?o WHERE {{
            ?s ?p ?o .
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
            {filter_clause}
        }}
        """
        try:
            results = self.store.execute_query(query, **options)
            
            alignments = []
            if hasattr(results, 'bindings'):
                for b in results.bindings:
                    alignments.append({
                        "source": b.get("s", {}).get("value") if isinstance(b.get("s"), dict) else b.get("s"),
                        "predicate": b.get("p", {}).get("value") if isinstance(b.get("p"), dict) else b.get("p"),
                        "target": b.get("o", {}).get("value") if isinstance(b.get("o"), dict) else b.get("o")
                    })
            return alignments
        except Exception as e:
            self.logger.error(f"Failed to list alignments: {e}")
            raise ProcessingError(f"Failed to list alignments: {e}")
            
    # ── SHACL Phase 1: Generation ─────────────────────────────────────────────

    def to_shacl(
        self,
        ontology: Dict[str, Any],
        *,
        format: str = "turtle",
        base_uri: Optional[str] = None,
        shapes_uri: Optional[str] = None,
        include_inherited: bool = True,
        severity: str = "Violation",
        quality_tier: str = "standard",
        target_namespace: Optional[str] = None,
        attach_domainless_properties: bool = False,
        validate_output: bool = False,
        **options,
    ) -> str:
        """
        Auto-derive SHACL node shapes and property shapes from a Semantica ontology dict.

        Args:
            ontology: Ontology dict from any OntologyEngine generation method.
            format: Output format — "turtle" (default), "json-ld", or "n-triples".
            base_uri: Base URI for generated shape URIs (inferred from ontology if omitted).
            shapes_uri: URI for the shapes graph declaration.
            include_inherited: Propagate parent class property shapes to child shapes.
            severity: Default severity — "Violation", "Warning", or "Info".
            quality_tier: Constraint completeness — "basic", "standard" (default), "strict".
            target_namespace: Namespace sh:targetClass and sh:path are expanded in,
                when the ontology supplies no absolute IRIs. Separate from base_uri,
                which says where the shape resources themselves live.
            attach_domainless_properties: Attach properties with no declared domain
                to every node shape. Off by default: it states a constraint the
                ontology does not.
            validate_output: Syntax-check output via rdflib before returning.

        Returns:
            Serialized SHACL shapes string.
        """
        from .ontology_generator import SHACLGenerator

        tracking_id = self.progress.start_tracking(
            module="ontology",
            submodule="OntologyEngine",
            message="Generating SHACL shapes",
        )
        try:
            ns = ontology.get("namespace", {}) if isinstance(ontology, dict) else {}
            resolved_base = (
                base_uri
                or (ns.get("base_uri") if isinstance(ns, dict) else None)
                or "https://semantica.dev/shapes/"
            )
            # These two are constructor-only on SHACLGenerator, so forwarding
            # them through generate(**options) silently dropped them.
            generator = SHACLGenerator(
                base_uri=resolved_base,
                shapes_uri=shapes_uri,
                include_inherited=include_inherited,
                severity=severity,
                quality_tier=quality_tier,
                target_namespace=target_namespace,
                attach_domainless_properties=attach_domainless_properties,
            )
            graph = generator.generate(ontology, **options)
            self.progress.update_tracking(tracking_id, message="Serializing SHACL graph")
            result = generator.serialize(graph, format=format)
            if validate_output:
                try:
                    import rdflib
                    _fmt_map = {
                        "turtle": "turtle", "ttl": "turtle",
                        "json-ld": "json-ld", "jsonld": "json-ld", "json_ld": "json-ld",
                        "n-triples": "nt", "ntriples": "nt", "nt": "nt",
                    }
                    rdflib_fmt = _fmt_map.get(format.lower().strip(), format)
                    g = rdflib.Graph()
                    g.parse(data=result, format=rdflib_fmt)
                except Exception as e:
                    self.logger.warning(f"SHACL output syntax check failed: {e}")
            self.progress.stop_tracking(
                tracking_id, status="completed", message="SHACL generation complete"
            )
            return result
        except Exception as e:
            self.progress.stop_tracking(tracking_id, status="failed", message=str(e))
            raise

    def export_shacl(
        self,
        ontology: Dict[str, Any],
        path,
        format: str = "turtle",
        encoding: str = "utf-8",
        **options,
    ) -> None:
        """
        Generate SHACL shapes from ontology and write to a file.

        Args:
            ontology: Ontology dict.
            path: Output file path (str or Path). Parent directories are created if needed.
            format: Output format — "turtle", "json-ld", or "n-triples".
            encoding: File encoding (default "utf-8").
        """
        from pathlib import Path

        shacl_str = self.to_shacl(ontology, format=format, **options)
        p = Path(path)
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(shacl_str, encoding=encoding)
        self.logger.info(f"SHACL shapes exported to {path}")

    # ── SHACL Phase 2: Runtime Validation ────────────────────────────────────

    def validate_graph(
        self,
        data_graph,
        shacl=None,
        *,
        ontology: Optional[Dict[str, Any]] = None,
        data_graph_format: str = "turtle",
        shacl_format: str = "turtle",
        explain: bool = True,
        abort_on_first: bool = False,
        **options,
    ):
        """
        Validate a data graph against SHACL shapes.

        Args:
            data_graph: The graph to validate — RDF string or rdflib.Graph.
            shacl: Pre-built SHACL string or file Path (mutually exclusive with ontology).
            ontology: Ontology dict — SHACL is auto-generated before validation
                      (mutually exclusive with shacl).
            data_graph_format: RDF format of data_graph when passed as a string.
            shacl_format: RDF format of the shacl argument when it is a string or file
                          — "turtle" (default), "json-ld", or "n-triples". Ignored when
                          ontology is provided (auto-generated shapes are always Turtle).
            explain: Populate plain-English explanation on each violation.
            abort_on_first: Stop after the first violation.

        Returns:
            SHACLValidationReport with structured violations and optional explanations.

        Raises:
            ValueError: If both or neither of shacl/ontology are provided.
            ImportError: If pyshacl is not installed.
        """
        from .ontology_validator import _run_pyshacl

        if (shacl is None) == (ontology is None):
            raise ValueError(
                "Exactly one of 'shacl' or 'ontology' must be provided, not both or neither."
            )

        tracking_id = self.progress.start_tracking(
            module="ontology",
            submodule="OntologyEngine",
            message="Preparing graph validation",
        )
        try:
            if ontology is not None:
                self.progress.update_tracking(
                    tracking_id, message="Generating SHACL from ontology"
                )
                shacl_str = self.to_shacl(ontology, **options)
                shacl_format = "turtle"  # auto-generated shapes are always Turtle
            else:
                import os
                from pathlib import Path

                if isinstance(shacl, Path) or (
                    isinstance(shacl, str) and os.path.exists(shacl)
                ):
                    shacl_str = Path(shacl).read_text(encoding="utf-8")
                else:
                    shacl_str = str(shacl)

            if isinstance(data_graph, str):
                data_graph_str = data_graph
            else:
                data_graph_str = data_graph.serialize(format=data_graph_format)

            self.progress.update_tracking(tracking_id, message="Running pyshacl validator")
            report = _run_pyshacl(
                data_graph_str,
                shacl_str,
                data_graph_format=data_graph_format,
                shacl_format=shacl_format,
            )

            if explain:
                self.progress.update_tracking(
                    tracking_id, message="Generating violation explanations"
                )
                report.explain_violations()

            self.progress.stop_tracking(
                tracking_id, status="completed", message="Validation complete"
            )
            return report
        except Exception as e:
            self.progress.stop_tracking(tracking_id, status="failed", message=str(e))
            raise

    # ── SKOS Vocabulary Management ────────────────────────────────────────────

    _SKOS = "http://www.w3.org/2004/02/skos/core#"
    _RDF_TYPE = "http://www.w3.org/1999/02/22-rdf-syntax-ns#type"

    def list_vocabularies(self, **options) -> List[Dict[str, Any]]:
        """
        List all SKOS ConceptSchemes stored in the triplet store.

        Returns:
            List of dicts with keys ``uri`` and ``label`` (may be empty string
            when no ``skos:prefLabel`` is present).

        Raises:
            ProcessingError: If no store is configured or the query fails.
        """
        if not self.store:
            raise ProcessingError("TripletStore instance not configured in OntologyEngine.")

        SKOS = self._SKOS
        RDF_TYPE = self._RDF_TYPE

        query = f"""
        SELECT DISTINCT ?scheme ?label WHERE {{
            ?scheme <{RDF_TYPE}> <{SKOS}ConceptScheme> .
            OPTIONAL {{ ?scheme <{SKOS}prefLabel> ?label }}
        }}
        """
        tracking_id = self.progress.start_tracking(
            module="ontology", submodule="OntologyEngine", message="Listing SKOS vocabularies"
        )
        try:
            result = self.store.execute_query(query, **options)
            vocabs = []
            if hasattr(result, "bindings"):
                seen: set = set()
                for b in result.bindings:
                    def _v(key):
                        val = b.get(key)
                        return (val.get("value") if isinstance(val, dict) else val) if val else None
                    uri = _v("scheme")
                    if uri and uri not in seen:
                        seen.add(uri)
                        vocabs.append({"uri": uri, "label": _v("label") or ""})
            self.progress.stop_tracking(tracking_id, status="completed",
                                        message=f"Found {len(vocabs)} vocabularies")
            return vocabs
        except Exception as e:
            self.progress.stop_tracking(tracking_id, status="failed", message=str(e))
            raise ProcessingError(f"list_vocabularies failed: {e}")

    def list_concepts(self, scheme_uri: str, **options) -> List[Dict[str, Any]]:
        """
        List all SKOS concepts that belong to the given ConceptScheme.

        Args:
            scheme_uri: Full URI of the ``skos:ConceptScheme`` to inspect.

        Returns:
            List of dicts with keys ``uri``, ``pref_label``, and
            ``alt_labels`` (list, may be empty).

        Raises:
            ProcessingError: If no store is configured or the query fails.
        """
        if not self.store:
            raise ProcessingError("TripletStore instance not configured in OntologyEngine.")

        SKOS = self._SKOS
        RDF_TYPE = self._RDF_TYPE
        safe_scheme = self._sanitize_uri(scheme_uri)

        query = f"""
        SELECT DISTINCT ?concept ?prefLabel ?altLabel WHERE {{
            ?concept <{RDF_TYPE}> <{SKOS}Concept> .
            ?concept <{SKOS}inScheme> <{safe_scheme}> .
            OPTIONAL {{ ?concept <{SKOS}prefLabel> ?prefLabel }}
            OPTIONAL {{ ?concept <{SKOS}altLabel>  ?altLabel  }}
        }}
        """
        tracking_id = self.progress.start_tracking(
            module="ontology", submodule="OntologyEngine",
            message=f"Listing concepts in {scheme_uri}"
        )
        try:
            result = self.store.execute_query(query, **options)
            concepts: Dict[str, Dict[str, Any]] = {}
            if hasattr(result, "bindings"):
                for b in result.bindings:
                    def _v(key):
                        val = b.get(key)
                        return (val.get("value") if isinstance(val, dict) else val) if val else None
                    uri = _v("concept")
                    if not uri:
                        continue
                    if uri not in concepts:
                        concepts[uri] = {"uri": uri, "pref_label": _v("prefLabel") or "", "alt_labels": []}
                    if not concepts[uri]["pref_label"] and _v("prefLabel"):
                        concepts[uri]["pref_label"] = _v("prefLabel")
                    lbl = _v("altLabel")
                    if lbl and lbl not in concepts[uri]["alt_labels"]:
                        concepts[uri]["alt_labels"].append(lbl)
            self.progress.stop_tracking(tracking_id, status="completed",
                                        message=f"Found {len(concepts)} concepts")
            return list(concepts.values())
        except Exception as e:
            self.progress.stop_tracking(tracking_id, status="failed", message=str(e))
            raise ProcessingError(f"list_concepts failed: {e}")

    def search_concepts(
        self,
        query: str,
        scheme_uri: Optional[str] = None,
        **options,
    ) -> List[Dict[str, Any]]:
        """
        Search SKOS concepts by matching ``skos:prefLabel`` or ``skos:altLabel``.

        The search is case-insensitive substring matching performed at the
        SPARQL level via ``CONTAINS(LCASE(…))``.

        Args:
            query: Substring to search for.
            scheme_uri: When given, restrict results to this ConceptScheme.

        Returns:
            List of dicts with keys ``uri`` and ``label`` (the matching label).

        Raises:
            ProcessingError: If no store is configured or the query fails.
        """
        if not self.store:
            raise ProcessingError("TripletStore instance not configured in OntologyEngine.")

        SKOS = self._SKOS
        RDF_TYPE = self._RDF_TYPE

        # Sanitize user query for embedding in a SPARQL string literal
        safe_query = (
            query
            .replace("\\", "\\\\")
            .replace('"', '\\"')
            .replace("\n", " ")
            .replace("\r", " ")
        )

        scheme_filter = ""
        if scheme_uri:
            safe_scheme = self._sanitize_uri(scheme_uri)
            scheme_filter = f"?concept <{SKOS}inScheme> <{safe_scheme}> ."

        sparql = f"""
        SELECT DISTINCT ?concept ?label WHERE {{
            ?concept <{RDF_TYPE}> <{SKOS}Concept> .
            {scheme_filter}
            {{
                ?concept <{SKOS}prefLabel> ?label
            }} UNION {{
                ?concept <{SKOS}altLabel> ?label
            }}
            FILTER(CONTAINS(LCASE(STR(?label)), LCASE("{safe_query}")))
        }}
        """
        tracking_id = self.progress.start_tracking(
            module="ontology", submodule="OntologyEngine",
            message=f"Searching SKOS concepts: '{query}'"
        )
        try:
            result = self.store.execute_query(sparql, **options)
            matches = []
            seen: set = set()
            if hasattr(result, "bindings"):
                for b in result.bindings:
                    def _v(key):
                        val = b.get(key)
                        return (val.get("value") if isinstance(val, dict) else val) if val else None
                    uri = _v("concept")
                    lbl = _v("label")
                    if uri and uri not in seen:
                        seen.add(uri)
                        matches.append({"uri": uri, "label": lbl or ""})
            self.progress.stop_tracking(tracking_id, status="completed",
                                        message=f"Found {len(matches)} matches")
            return matches
        except Exception as e:
            self.progress.stop_tracking(tracking_id, status="failed", message=str(e))
            raise ProcessingError(f"search_concepts failed: {e}")

    # ── Ontology Evaluation / Validation ─────────────────────────────────────

    def evaluate(self, ontology: Dict[str, Any], **options):
        return self.evaluator.evaluate_ontology(ontology, **options)

    def validate(self, ontology: Dict[str, Any], **options):
        return self.validator.validate(ontology, **options)

    def to_owl(self, ontology: Dict[str, Any], format: str = "turtle", **options):
        return self.owl.generate_owl(ontology, format=format, **options)

    def export_owl(self, ontology: Dict[str, Any], path: str, format: str = "turtle"):
        return self.owl.export_owl(ontology, path, format=format)

    def get_ontology_version_dict(self, version_id: str) -> Dict[str, Any]:
        """Utility to load an ontology version as plain dict ready for diffing."""
        version_record = self.version_manager.get_version(version_id)
        if not version_record:
            raise ProcessingError(f"Version {version_id} not found.")
        return version_record.metadata.get("structure", {"classes": [], "properties": []})

    def compare_versions(self, base_id: str, target_id: str, **options) -> Dict[str, Any]:
        """
        Orchestrates version loading, diff computation, and report generation.

        Args:
            base_id: Version ID of the old ontology
            target_id: Version ID of the new ontology
            **options: Can pass 'base_dict' and 'target_dict' directly to bypass loading.
                       Can pass 'run_validation=True' to validate schema.
                       Can pass 'graph_data' to validate instances against new schema.

        Returns:
            A structured dictionary containing the impact report and machine-readable diff.
        """
        tracking_id = self.progress.start_tracking(
            module="ontology",
            submodule="OntologyEngine",
            message=f"Comparing ontology versions: {base_id} -> {target_id}"
        )

        try:
            # Deferred to avoid circular import
            from ..change_management.change_log import generate_change_report
            from ..kg.graph_validator import GraphValidator

            base_dict = options.get("base_dict") or self.get_ontology_version_dict(base_id)
            target_dict = options.get("target_dict") or self.get_ontology_version_dict(target_id)

            diff_result = self.version_manager.diff_ontologies(base_dict, target_dict)
            report = generate_change_report(diff_result)
            report["diff"] = diff_result

            if options.get("run_validation"):
                self.progress.update_tracking(tracking_id, message="Running validation on target schema...")
                val_res = self.validate(target_dict, **options)
                report["validation_results"] = {
                    "valid": getattr(val_res, "valid", getattr(val_res, "is_valid", False)),
                    "consistent": getattr(val_res, "consistent", True),
                    "satisfiable": getattr(val_res, "satisfiable", True),
                    "errors": getattr(val_res, "errors", []),
                    "warnings": getattr(val_res, "warnings", [])
                }

                if "graph_data" in options:
                    self.progress.update_tracking(tracking_id, message="Running graph data validation...")
                    kg_validator = GraphValidator(**self.config)
                    kg_res = kg_validator.validate(options["graph_data"], ontology=target_dict, **options)
                    report["graph_validation"] = {
                        "valid": getattr(kg_res, "valid", getattr(kg_res, "is_valid", False)),
                        "errors": getattr(kg_res, "errors", []),
                        "warnings": getattr(kg_res, "warnings", [])
                    }

            self.progress.stop_tracking(tracking_id, status="completed", message="Comparison complete")
            return report

        except Exception as e:
            self.progress.stop_tracking(tracking_id, status="failed", message=str(e))
            self.logger.error(f"Failed to compare versions: {e}")
            raise ProcessingError(f"Version comparison failed: {e}") from e
