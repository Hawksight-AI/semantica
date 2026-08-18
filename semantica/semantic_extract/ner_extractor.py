"""
Named Entity Recognition Extractor Module

This module provides comprehensive NER capabilities with multiple extraction methods,
ranging from simple pattern matching to advanced LLM-based extraction, with support
for fallback chains and ensemble voting.

Supported Methods:
    - "pattern": Pattern-based extraction using simple regex patterns
    - "regex": Advanced regex-based extraction with custom patterns
    - "rules": Rule-based extraction using linguistic rules
    - "ml": ML-based extraction using spaCy (default)
    - "huggingface": Custom HuggingFace NER models
    - "llm": LLM-based extraction using various providers (OpenAI, Gemini, Groq, etc.)

Algorithms Used:
    - Regular Expression Matching: Pattern matching using finite automata
    - Rule-based Extraction: Linguistic rule application and pattern matching
    - Neural Named Entity Recognition: spaCy's CNN/Transformer-based NER models
    - Transformer Models: BERT, RoBERTa, DistilBERT for token classification
    - Large Language Models: GPT, Claude, Gemini for zero-shot/few-shot extraction
    - Ensemble Voting: Majority voting and confidence-weighted aggregation
    - Weighted Confidence Scoring:
        * Formula: Score = (0.5 * Method_Confidence) + (0.5 * Type_Similarity_Score)
        * Method_Confidence: Confidence score from the extraction algorithm
        * Type_Similarity_Score: Semantic match with user-provided entity types (Exact=1.0, Synonym=0.95, Embedding=Cosine_Sim)
    - Hybrid Similarity Matching: Exact -> Synonym -> Substring -> Semantic Embedding (Batch Optimized)
    - Last Resort Fallback: Capitalized word heuristic when all other methods fail

Key Features:
    - Multiple extraction methods:
        * Pattern-based: Simple regex pattern matching
        * Regex-based: Advanced regex with custom patterns
        * Rules-based: Linguistic rule-based extraction
        * ML-based: spaCy-based machine learning extraction (default)
        * HuggingFace: Custom HuggingFace NER models
        * LLM-based: Large language model extraction
    - Fallback chain support: Try methods in order until one succeeds
    - Robust Fallbacks: Prevents empty results via ML -> Pattern -> Last Resort chain
    - Ensemble voting: Combine results from multiple methods
    - Post-processing: Entity boundary validation
    - Multiple entity type support (PERSON, ORG, GPE, DATE, etc.)
    - Confidence scoring and filtering
    - Batch processing capabilities
    - Entity classification and grouping

Main Classes:
    - NERExtractor: Core NER extractor with method selection
    - Entity: Entity representation dataclass

Example Usage:
    >>> from semantica.semantic_extract import NERExtractor
    >>> # Using ML method (default)
    >>> extractor = NERExtractor(method="ml", model="en_core_web_sm")
    >>> entities = extractor.extract_entities("Apple Inc. was founded in 1976.")
    >>> 
    >>> # Using LLM method
    >>> extractor = NERExtractor(method="llm", provider="openai", llm_model="gpt-4")
    >>> entities = extractor.extract_entities("Apple Inc. was founded in 1976.")
    >>> 
    >>> # Using HuggingFace model
    >>> extractor = NERExtractor(method="huggingface", huggingface_model="dslim/bert-base-NER")
    >>> entities = extractor.extract_entities("Apple Inc. was founded in 1976.")
    >>> 
    >>> # Using fallback chain
    >>> extractor = NERExtractor(method=["llm", "ml", "pattern"], ensemble_voting=True)
    >>> entities = extractor.extract_entities("Apple Inc. was founded in 1976.")

Author: Semantica Contributors
License: MIT
"""

from typing import Any, Dict, List, Optional, Tuple, Union

from ..utils.exceptions import ProcessingError
from ..utils.helpers import safe_import
from ..utils.logging import get_logger
from ..utils.progress_tracker import get_progress_tracker
from .types import Entity

spacy, SPACY_AVAILABLE = safe_import("spacy")


class NERExtractor:
    """Named Entity Recognition extractor."""

    def __init__(
        self, 
        method: Union[str, List[str]] = "ml", 
        entity_types: Optional[List[str]] = None,
        **config
    ):
        """
        Initialize NER extractor.

        Args:
            method: Extraction method(s). Can be:
                - "pattern": Pattern-based extraction
                - "regex": Regex-based extraction
                - "rules": Rule-based extraction
                - "ml": ML-based (spaCy) - default
                - "huggingface": HuggingFace model
                - "llm": LLM-based extraction
                - List of methods for fallback chain
            entity_types: List of entity types to extract (e.g., ["PERSON", "ORG"]).
                          If provided, extraction methods will try to limit/focus on these types.
            **config: Configuration options:
                - model: Model name (for ML/HuggingFace methods)
                - huggingface_model: HuggingFace model name
                - provider: LLM provider (for LLM method)
                - llm_model: LLM model name
                - base_url: Custom base URL for OpenAI-compatible endpoints
                    (e.g. ``"https://my-gateway/v1"``).  When set, the
                    provider automatically switches to ``Mode.JSON`` so that
                    third-party servers (Qwen, LLaMA gateways, etc.) that do
                    not implement the full function-calling protocol still
                    return correctly structured results.
                - device: Device for HuggingFace models ("cuda" or "cpu")
                - min_confidence: Minimum confidence threshold
                - ensemble_voting: Enable ensemble voting (default: False)
                - post_process: Enable post-processing (default: False)
        """
        self.logger = get_logger("ner_extractor")
        self.config = config
        self.entity_types = entity_types

        # Method configuration
        self.method = method if isinstance(method, list) else [method]
        self.model_name = config.get("model", "en_core_web_sm")
        self.huggingface_model = config.get(
            "huggingface_model", config.get("model", "dslim/bert-base-NER")
        )
        self.language = config.get("language", "en")
        self.min_confidence = config.get("min_confidence", 0.5)
        self.ensemble_voting = config.get("ensemble_voting", False)
        self.post_process = config.get("post_process", False)
        self.progress_tracker = get_progress_tracker()
        # Ensure progress tracker is enabled
        if not self.progress_tracker.enabled:
            self.progress_tracker.enabled = True

        # Initialize spaCy model if ML method is used
        self.nlp = None
        self._ml_runtime_usable = True
        if "ml" in self.method and SPACY_AVAILABLE:
            try:
                # Deferred import: keeps semantic_extract.methods out of the
                # module-level import graph and routes loading through the
                # process-level cache so repeated NERExtractor constructions
                # never pay the ~120 ms spacy.load() cost more than once.
                from .methods import load_spacy_model
                self.nlp = load_spacy_model(self.model_name)
            except OSError:
                self.logger.warning(
                    f"spaCy model {self.model_name} not found. ML method will fallback."
                )
            except Exception as exc:
                self._ml_runtime_usable = False
                self.logger.warning(
                    "spaCy model %s failed to initialize and will be disabled for this extractor instance. ML method will fallback.",
                    self.model_name,
                    exc_info=True,
                )

    def extract(self, text: Union[str, List[Dict[str, Any]], List[str]], pipeline_id: Optional[str] = None, **kwargs) -> Union[List[Entity], List[List[Entity]]]:
        """
        Alias for extract_entities.
        Handles both single string and list of documents.
        
        Args:
            text: Input text or list of documents
            pipeline_id: Optional pipeline ID for progress tracking
            **kwargs: Extraction options
            
        Returns:
            Union[List[Entity], List[List[Entity]]]: Extracted entities
        """
        if isinstance(text, list):
            # Handle batch extraction with progress tracking
            tracking_id = self.progress_tracker.start_tracking(
                module="semantic_extract",
                submodule="NERExtractor",
                message=f"Batch extracting entities from {len(text)} documents",
                pipeline_id=pipeline_id,
            )
            
            try:
                results = [None] * len(text)
                total_items = len(text)
                total_entities_count = 0
                processed_count = 0
                
                # Update more frequently: every 1% or at least every 10 items, but always update for small datasets
                if total_items <= 10:
                    update_interval = 1  # Update every item for small datasets
                else:
                    update_interval = max(1, min(10, total_items // 100))
                
                # Initial progress update - ALWAYS show this
                self.progress_tracker.update_progress(
                    tracking_id,
                    processed=0,
                    total=total_items,
                    message=f"Starting batch extraction... 0/{total_items}"
                )
                
                from .config import resolve_max_workers
                max_workers = resolve_max_workers(
                    explicit=kwargs.get("max_workers"),
                    local_config=self.config,
                    methods=self.method,
                )
                
                # Helper function for single item processing
                def process_item(idx, item):
                    try:
                        current_entities = []
                        if isinstance(item, dict) and "content" in item:
                            current_entities = self.extract_entities(item["content"], **kwargs)
                        elif isinstance(item, str):
                            current_entities = self.extract_entities(item, **kwargs)
                        else:
                            # Try converting to string
                            try:
                                current_entities = self.extract_entities(str(item), **kwargs)
                            except Exception:
                                current_entities = []
                        
                        # Add provenance metadata
                        for ent in current_entities:
                            if ent.metadata is None:
                                ent.metadata = {}
                            ent.metadata["batch_index"] = idx
                            if isinstance(item, dict) and "id" in item:
                                ent.metadata["document_id"] = item["id"]
                        
                        return idx, current_entities
                    except Exception as e:
                        self.logger.warning(f"Failed to process item {idx}: {e}")
                        return idx, []

                if max_workers > 1:
                    import concurrent.futures
                    
                    with concurrent.futures.ThreadPoolExecutor(max_workers=max_workers) as executor:
                        # Submit all tasks
                        future_to_idx = {
                            executor.submit(process_item, idx, item): idx 
                            for idx, item in enumerate(text)
                        }
                        
                        for future in concurrent.futures.as_completed(future_to_idx):
                            idx, entities = future.result()
                            results[idx] = entities
                            total_entities_count += len(entities)
                            processed_count += 1
                            
                            # Update progress
                            should_update = (
                                processed_count % update_interval == 0 or 
                                processed_count == total_items or 
                                processed_count == 1 or
                                total_items <= 10
                            )
                            if should_update:
                                remaining = total_items - processed_count
                                self.progress_tracker.update_progress(
                                    tracking_id,
                                    processed=processed_count,
                                    total=total_items,
                                    message=f"Processing documents... {processed_count}/{total_items} (remaining: {remaining}) - Extracted {total_entities_count} entities so far"
                                )
                else:
                    # Sequential processing
                    for idx, item in enumerate(text):
                        _, entities = process_item(idx, item)
                        results[idx] = entities
                        total_entities_count += len(entities)
                        processed_count += 1
                        
                        # Update progress
                        should_update = (
                            processed_count % update_interval == 0 or 
                            processed_count == total_items or 
                            processed_count == 1 or
                            total_items <= 10
                        )
                        if should_update:
                            remaining = total_items - processed_count
                            self.progress_tracker.update_progress(
                                tracking_id,
                                processed=processed_count,
                                total=total_items,
                                message=f"Processing documents... {processed_count}/{total_items} (remaining: {remaining}) - Extracted {total_entities_count} entities so far"
                            )
                
                self.progress_tracker.stop_tracking(
                    tracking_id,
                    status="completed",
                    message=f"Batch extraction completed. Processed {len(results)} documents, extracted {total_entities_count} entities.",
                )
                return results
            except Exception as e:
                self.progress_tracker.stop_tracking(
                    tracking_id, status="failed", message=str(e)
                )
                raise
        else:
            return self.extract_entities(text, **kwargs)

    def extract_entities(
        self,
        text: Union[str, List[Dict[str, Any]], List[str]],
        pipeline_id: Optional[str] = None,
        **options,
    ) -> Union[List[Entity], List[List[Entity]]]:
        """
        Extract named entities from text.

        Args:
            text: Input text
            pipeline_id: Optional pipeline ID for progress tracking (batch mode)
            **options: Extraction options:
                - entity_types: Filter by entity types (list)
                - min_confidence: Minimum confidence threshold
                - method: Override method (if not set in __init__)

        Returns:
            list: List of extracted entities
        """
        if isinstance(text, list):
            return self.extract(text, pipeline_id=pipeline_id, **options)

        tracking_id = self.progress_tracker.start_tracking(
            module="semantic_extract",
            submodule="NERExtractor",
            message="Extracting named entities from text",
        )

        try:
            from .methods import get_entity_method
            if not text:
                self.progress_tracker.stop_tracking(
                    tracking_id, status="completed", message="No text provided"
                )
                return []

            # Use method from options if provided, otherwise use instance method
            methods = options.get("method", self.method)
            if isinstance(methods, str):
                methods = [methods]
            methods = self._filter_unusable_methods(methods)

            min_confidence = options.get("min_confidence", self.min_confidence)
            entity_types = options.get("entity_types", self.entity_types)

            # Merge config with options
            all_options = {**self.config, **options}
            if entity_types:
                all_options["entity_types"] = entity_types

            # Try each method in order (fallback chain)
            all_entities = []
            for method_name in methods:
                try:
                    self.progress_tracker.update_tracking(
                        tracking_id,
                        message=f"Extracting entities using {method_name}...",
                    )
                    method_func = get_entity_method(method_name)

                    # Prepare method-specific options
                    method_options = all_options.copy()
                    if method_name == "huggingface":
                        # Prioritize runtime options over config/defaults
                        method_options["model"] = (
                            options.get("huggingface_model") 
                            or options.get("model") 
                            or self.huggingface_model
                        )
                        method_options["device"] = all_options.get("device")
                    elif method_name == "llm":
                        method_options["provider"] = all_options.get(
                            "provider", "openai"
                        )
                        method_options["model"] = all_options.get(
                            "llm_model", all_options.get("model")
                        )
                        # Ensure api_key is populated: check explicitly provided or fallback to env
                        current_key = method_options.get("api_key")
                        if not current_key:
                            # Not found or empty/None, try environment
                            import os
                            provider_name = method_options.get("provider", "openai")
                            env_key = f"{provider_name.upper()}_API_KEY"
                            api_key = os.getenv(env_key)
                            if api_key:
                                method_options["api_key"] = api_key

                    entities = method_func(text, **method_options)

                    # Apply weighted scoring if entity_types are provided
                    if entity_types:
                        try:
                            from .methods import calculate_weighted_confidence
                            for e in entities:
                                e.confidence = calculate_weighted_confidence(
                                    item_type=e.label,
                                    original_confidence=e.confidence,
                                    valid_types=entity_types,
                                    item_text=e.text
                                )
                        except ImportError:
                            pass

                    # Filter by confidence
                    filtered = [e for e in entities if e.confidence >= min_confidence]
                    
                    if filtered:
                        all_entities.append((method_name, filtered))

                        # If not using ensemble, return first successful result
                        if not self.ensemble_voting:
                            # Ensure default metadata
                            for e in filtered:
                                if e.metadata is None: e.metadata = {}
                                if "batch_index" not in e.metadata: e.metadata["batch_index"] = 0

                            self.progress_tracker.stop_tracking(
                                tracking_id,
                                status="completed",
                                message=f"Extracted {len(filtered)} entities using {method_name}",
                            )
                            return filtered

                except Exception as e:
                    self.logger.warning(
                        "Method %s failed: %s", method_name, e, exc_info=True
                    )
                    continue

            # Ensemble voting if enabled
            if self.ensemble_voting and len(all_entities) > 1:
                entities = self._vote_entities(
                    [entities for _, entities in all_entities]
                )
            elif all_entities:
                entities = all_entities[0][1]  # Use first successful method
            else:
                # Fallback to pattern-based extraction if all models fail
                entities = self._extract_fallback(text)

            # Post-processing if enabled
            if self.post_process and entities:
                entities = self._post_process_entities(entities, text)

            self.progress_tracker.stop_tracking(
                tracking_id,
                status="completed",
                message=f"Extracted {len(entities)} entities",
            )
            return entities

        except Exception as e:
            self.progress_tracker.stop_tracking(
                tracking_id, status="failed", message=str(e)
            )
            raise

    def _filter_unusable_methods(self, methods: List[str]) -> List[str]:
        """Skip ML dispatch after a known spaCy runtime initialization failure."""
        filtered = []
        skipped_ml = False

        for method_name in methods:
            if method_name in {"ml", "spacy"} and not self._ml_runtime_usable:
                skipped_ml = True
                continue
            filtered.append(method_name)

        if skipped_ml:
            self.logger.debug(
                "Skipping ML entity extraction because spaCy runtime initialization previously failed for this extractor."
            )

        return filtered

    def _vote_entities(
        self, results: List[List[Entity]], threshold: float = 0.5
    ) -> List[Entity]:
        """Vote on entities across methods."""
        entity_counts = {}
        total_methods = len(results)

        for entities in results:
            for entity in entities:
                key = (entity.text.lower(), entity.label)
                if key not in entity_counts:
                    entity_counts[key] = {"entity": entity, "score": 0.0, "count": 0}
                entity_counts[key]["score"] += entity.confidence
                entity_counts[key]["count"] += 1

        # Return entities that meet threshold
        voted = []
        for key, data in entity_counts.items():
            avg_score = data["score"] / data["count"]
            if avg_score >= threshold:
                entity = data["entity"]
                entity.confidence = avg_score
                voted.append(entity)

        return voted

    def _post_process_entities(self, entities: List[Entity], text: str) -> List[Entity]:
        """Post-process entities for refinement."""
        processed = []

        for entity in entities:
            # Check boundaries
            if entity.start_char < 0 or entity.end_char > len(text):
                continue

            # Validate entity text matches
            actual_text = text[entity.start_char : entity.end_char]
            if actual_text.lower() != entity.text.lower():
                # Try to find correct boundaries
                start = text.lower().find(
                    entity.text.lower(), max(0, entity.start_char - 10)
                )
                if start >= 0:
                    entity.start_char = start
                    entity.end_char = start + len(entity.text)

            processed.append(entity)

        return processed

    def _extract_with_spacy(
        self, text: str, min_confidence: float, entity_types: Optional[List[str]]
    ) -> List[Entity]:
        """Extract entities using spaCy."""
        entities = []

        doc = self.nlp(text)

        for ent in doc.ents:
            # Filter by entity types if specified
            if entity_types and ent.label_ not in entity_types:
                continue

            # Get confidence if available
            confidence = 1.0
            if hasattr(ent, "confidence"):
                confidence = ent.confidence
            elif hasattr(ent, "score"):
                confidence = ent.score

            if confidence >= min_confidence:
                entities.append(
                    Entity(
                        text=ent.text,
                        label=ent.label_,
                        start_char=ent.start_char,
                        end_char=ent.end_char,
                        confidence=confidence,
                        metadata={
                            "lemma": ent.lemma_ if hasattr(ent, "lemma_") else ent.text
                        },
                    )
                )

        return entities

    def _extract_fallback(self, text: str) -> List[Entity]:
        """Fallback entity extraction using simple patterns."""
        entities = []
        import re

        # Simple patterns for common entity types
        patterns = {
            "PERSON": r"\b([A-Z][a-z]+(?:\s+[A-Z][a-z]+)+)\b",
            "ORG": r"\b([A-Z][a-zA-Z]+(?:\s+[A-Z][a-zA-Z]+)*\s+(?:Inc|Corp|LLC|Ltd|Company))\b",
            "GPE": r"\b([A-Z][a-z]+\s*(?:City|State|Country|Nation))\b",
            "DATE": r"\b(\d{1,2}[/-]\d{1,2}[/-]\d{2,4}|\d{4})\b",
        }

        # Track covered ranges to avoid overlaps
        covered_ranges = set()

        for label, pattern in patterns.items():
            for match in re.finditer(pattern, text):
                start, end = match.start(), match.end()
                # Check overlap
                is_overlap = any(r_start < end and r_end > start for r_start, r_end in covered_ranges)
                if not is_overlap:
                    # Use group 1 if available, else group 0
                    text_val = match.group(1) if match.lastindex and match.lastindex >= 1 else match.group(0)
                    
                    entities.append(
                        Entity(
                            text=text_val,
                            label=label,
                            start_char=start,
                            end_char=end,
                            confidence=0.7,  # Lower confidence for pattern-based
                            metadata={"extraction_method": "pattern"},
                        )
                    )
                    covered_ranges.add((start, end))

        # Last Resort: If no entities found, try single capitalized words as generic entities
        if not entities:
            # Match any capitalized word of length > 2
            cap_pattern = r"\b[A-Z][a-z]{2,}\b"
            for match in re.finditer(cap_pattern, text):
                start, end = match.start(), match.end()
                is_overlap = any(r_start < end and r_end > start for r_start, r_end in covered_ranges)
                if not is_overlap:
                    entities.append(
                        Entity(
                            text=match.group(0),
                            label="UNKNOWN",
                            start_char=start,
                            end_char=end,
                            confidence=0.5,
                            metadata={"extraction_method": "last_resort_pattern"},
                        )
                    )
                    covered_ranges.add((start, end))

        return entities

    def extract_entities_batch(self, texts: List[str], **options) -> List[List[Entity]]:
        """
        Extract entities from multiple texts.

        Args:
            texts: List of input texts
            **options: Extraction options

        Returns:
            list: List of entity lists for each text
        """
        return self.extract(texts, **options)

    def classify_entities(self, entities: List[Entity]) -> Dict[str, List[Entity]]:
        """
        Classify entities by type.

        Args:
            entities: List of entities

        Returns:
            dict: Entities grouped by type
        """
        classified = {}
        for entity in entities:
            if entity.label not in classified:
                classified[entity.label] = []
            classified[entity.label].append(entity)

        return classified

    def filter_by_confidence(
        self, entities: List[Entity], min_confidence: float
    ) -> List[Entity]:
        """
        Filter entities by confidence score.

        Args:
            entities: List of entities
            min_confidence: Minimum confidence threshold

        Returns:
            list: Filtered entities
        """
        return [e for e in entities if e.confidence >= min_confidence]
