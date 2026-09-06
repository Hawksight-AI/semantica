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
    - Explicit merge strategies: fallback, union, and consensus
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
    >>> # Require agreement between multiple extraction methods
    >>> extractor = NERExtractor(
    ...     method=["llm", "ml"], merge_strategy="consensus", min_votes=2
    ... )
    >>> entities = extractor.extract_entities("Apple Inc. was founded in 1976.")

Author: Semantica Contributors
License: MIT
"""

import math
import re
import warnings
from typing import Any, Dict, List, Optional, Sequence, Tuple, Union

from ..utils.exceptions import ProcessingError
from ..utils.helpers import safe_import
from ..utils.logging import get_logger
from ..utils.progress_tracker import get_progress_tracker
from .types import Entity

spacy, SPACY_AVAILABLE = safe_import("spacy")


class NERExtractor:
    """Named Entity Recognition extractor."""

    _VALID_MERGE_STRATEGIES = {"fallback", "union", "consensus"}
    _MERGE_OPTION_KEYS = (
        "merge_strategy",
        "min_votes",
        "min_agreement",
        "method_weights",
        "eligible_methods",
    )
    _MIN_SPAN_IOU = 0.5
    _LABEL_ALIASES = {
        "PER": "PERSON",
        "PERSON": "PERSON",
        "ORGANIZATION": "ORG",
        "ORG": "ORG",
        "LOCATION": "GPE",
        "LOC": "GPE",
        "GPE": "GPE",
        "TIME": "DATE",
        "DATE": "DATE",
        "CURRENCY": "MONEY",
        "MONEY": "MONEY",
        "PERCENTAGE": "PERCENT",
        "PERCENT": "PERCENT",
    }

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
                - merge_strategy: "fallback" (default), "union", or "consensus"
                - min_votes: Required supporting methods for consensus (default: 2)
                - min_agreement: Optional minimum support ratio for consensus
                - method_weights: Optional method weights for exact-span
                  cross-label tie-breaking
                - eligible_methods: Optional subset of configured methods to count
                  as consensus voters
                - ensemble_voting: Deprecated alias for merge_strategy="union"
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
        self.merge_strategy = self._resolve_merge_strategy(config)
        self.min_votes = self._validate_min_votes(config.get("min_votes", 2))
        self.min_agreement = self._validate_min_agreement(
            config.get("min_agreement")
        )
        self.method_weights = self._validate_method_weights(
            config.get("method_weights")
        )
        self.eligible_methods = config.get("eligible_methods")
        self.post_process = config.get("post_process", False)
        self.progress_tracker = get_progress_tracker()
        # Ensure progress tracker is enabled
        if not self.progress_tracker.enabled:
            self.progress_tracker.enabled = True

        # Validate the spaCy runtime up front if ML method is used. The model
        # itself is loaded lazily by extract_entities_ml() through the
        # process-level cache in methods.py; this instance only tracks whether
        # ML dispatch should be attempted at all.
        self._ml_runtime_usable = True
        if "ml" in self.method and SPACY_AVAILABLE:
            try:
                # Deferred import: keeps semantic_extract.methods out of the
                # module-level import graph and routes validation through the
                # process-level cache so repeated NERExtractor constructions
                # never pay the ~120 ms spacy.load() cost more than once.
                from .methods import load_spacy_model
                load_spacy_model(self.model_name)
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

    def _resolve_merge_strategy(self, config: Dict[str, Any]) -> str:
        """Resolve the explicit merge strategy and the deprecated legacy flag."""
        configured_strategy = config.get("merge_strategy")
        if configured_strategy is None:
            if self.ensemble_voting:
                warnings.warn(
                    "ensemble_voting is deprecated because it historically "
                    "performed a union, not voting. Use merge_strategy='union' "
                    "or merge_strategy='consensus' explicitly.",
                    DeprecationWarning,
                    stacklevel=3,
                )
                return "union"
            return "fallback"

        strategy = self._validate_merge_strategy(configured_strategy)
        if self.ensemble_voting:
            warnings.warn(
                "ensemble_voting is deprecated and ignored when merge_strategy "
                "is provided.",
                DeprecationWarning,
                stacklevel=3,
            )
        return strategy

    @classmethod
    def _validate_merge_strategy(cls, strategy: Any) -> str:
        """Return a normalized merge strategy or raise a useful configuration error."""
        if not isinstance(strategy, str):
            raise ValueError(
                "merge_strategy must be one of: fallback, union, consensus"
            )

        normalized = strategy.lower()
        if normalized not in cls._VALID_MERGE_STRATEGIES:
            raise ValueError(
                "merge_strategy must be one of: fallback, union, consensus"
            )
        return normalized

    @staticmethod
    def _validate_min_votes(min_votes: Any) -> int:
        """Validate the number of method votes required for consensus."""
        if isinstance(min_votes, bool) or not isinstance(min_votes, int):
            raise ValueError("min_votes must be a positive integer")
        if min_votes < 1:
            raise ValueError("min_votes must be a positive integer")
        return min_votes

    @staticmethod
    def _validate_min_agreement(min_agreement: Any) -> Optional[float]:
        """Validate an optional consensus support ratio."""
        if min_agreement is None:
            return None

        try:
            normalized = float(min_agreement)
        except (TypeError, ValueError):
            raise ValueError("min_agreement must be a number between 0 and 1")

        if not math.isfinite(normalized) or not 0.0 <= normalized <= 1.0:
            raise ValueError("min_agreement must be a number between 0 and 1")
        return normalized

    @classmethod
    def _validate_method_weights(cls, method_weights: Any) -> Dict[str, float]:
        """Validate optional positive method weights used for deterministic ties."""
        if method_weights is None:
            return {}
        if not isinstance(method_weights, dict):
            raise ValueError("method_weights must be a mapping of method names to weights")

        normalized = {}
        for method_name, weight in method_weights.items():
            if not isinstance(method_name, str):
                raise ValueError("method_weights keys must be method names")
            try:
                numeric_weight = float(weight)
            except (TypeError, ValueError):
                raise ValueError("method_weights values must be positive numbers")
            if not math.isfinite(numeric_weight) or numeric_weight <= 0:
                raise ValueError("method_weights values must be positive numbers")
            identity = cls._method_identity(method_name)
            existing_weight = normalized.get(identity)
            if existing_weight is not None and existing_weight != numeric_weight:
                raise ValueError(
                    "method_weights assigns conflicting values to aliases for "
                    f"backend '{identity}'"
                )
            normalized[identity] = numeric_weight
        return normalized

    @staticmethod
    def _method_identity(method_name: str) -> str:
        """Normalize aliases that share one extraction backend for vote counting."""
        normalized = method_name.lower()
        return "ml" if normalized in {"ml", "spacy"} else method_name

    def _resolve_eligible_methods(
        self,
        methods: Sequence[str],
        configured_methods: Any = None,
    ) -> List[str]:
        """Resolve the configured method names that are eligible consensus voters."""
        available = []
        seen = set()
        for method_name in methods:
            identity = self._method_identity(method_name)
            if identity not in seen:
                available.append((identity, method_name))
                seen.add(identity)

        configured = (
            self.eligible_methods
            if configured_methods is None
            else configured_methods
        )
        if configured is None:
            return [method_name for _, method_name in available]
        if isinstance(configured, str):
            configured = [configured]

        try:
            configured = list(configured)
        except TypeError:
            raise ValueError("eligible_methods must be a sequence of method names")

        requested_identities = set()
        for method_name in configured:
            if not isinstance(method_name, str):
                raise ValueError("eligible_methods must be a sequence of method names")
            requested_identities.add(self._method_identity(method_name))

        available_identities = {identity for identity, _ in available}
        unknown_methods = [
            method_name
            for method_name in configured
            if self._method_identity(method_name) not in available_identities
        ]
        if unknown_methods:
            raise ValueError(
                "eligible_methods contains methods not configured for extraction: "
                + ", ".join(unknown_methods)
            )

        return [
            method_name
            for identity, method_name in available
            if identity in requested_identities
        ]

    def _align_entities_to_text(
        self, entities: List[Entity], text: str
    ) -> List[Entity]:
        """Resolve missing offsets before span-based methods are merged.

        Some providers, notably typed LLM extraction, can return text and
        labels without offsets. For a single method that is harmless, but a
        span-based merge needs document locations. Missing spans are therefore
        aligned by a deterministic, per-label text search. Valid provider
        offsets are preserved; candidates that cannot be aligned are excluded
        because union and consensus cannot safely merge them.
        """
        next_offsets = {}
        occupied_offsets = {}
        aligned = []

        for entity in entities:
            needle = entity.text
            if not isinstance(needle, str) or not needle:
                continue

            key = (needle.casefold(), self._canonical_label(entity.label))
            start_char = entity.start_char
            end_char = entity.end_char
            has_valid_span = (
                isinstance(start_char, int)
                and isinstance(end_char, int)
                and 0 <= start_char < end_char <= len(text)
                and text[start_char:end_char].casefold() == needle.casefold()
            )
            if has_valid_span:
                aligned.append(entity)
                next_offsets[key] = max(next_offsets.get(key, 0), end_char)
                occupied_offsets.setdefault(key, set()).add((start_char, end_char))
                continue

            prior_offset = next_offsets.get(key, 0)
            hinted_start = start_char if isinstance(start_char, int) else 0
            search_start = max(prior_offset, min(max(hinted_start, 0), len(text)))
            occupied = occupied_offsets.setdefault(key, set())
            match = None
            match_offset = 0
            left_boundary = (
                r"(?<!\w)" if needle[0].isalnum() or needle[0] == "_" else ""
            )
            right_boundary = (
                r"(?!\w)" if needle[-1].isalnum() or needle[-1] == "_" else ""
            )
            pattern = re.compile(
                left_boundary + re.escape(needle) + right_boundary,
                re.IGNORECASE,
            )
            for segment, offset in ((text[search_start:], search_start), (text, 0)):
                for candidate in pattern.finditer(segment):
                    candidate_start = offset + candidate.start()
                    candidate_end = offset + candidate.end()
                    if (candidate_start, candidate_end) not in occupied:
                        match = candidate
                        match_offset = offset
                        break
                if match is not None:
                    break

            if match is None:
                continue

            resolved_start = match_offset + match.start()
            resolved_end = match_offset + match.end()
            aligned.append(
                Entity(
                    text=entity.text,
                    label=entity.label,
                    start_char=resolved_start,
                    end_char=resolved_end,
                    confidence=entity.confidence,
                    metadata=dict(entity.metadata or {}),
                )
            )
            next_offsets[key] = resolved_end
            occupied.add((resolved_start, resolved_end))

        return aligned

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

            # Use method from options if provided, otherwise use instance method.
            # Keep the requested list separate from the executable list: in
            # consensus mode, a configured method with no result is still an
            # eligible non-supporting vote.
            requested_methods = options.get("method", self.method)
            if isinstance(requested_methods, str):
                requested_methods = [requested_methods]

            merge_strategy = self._validate_merge_strategy(
                options.get("merge_strategy", self.merge_strategy)
            )
            if merge_strategy == "consensus":
                eligible_methods = self._resolve_eligible_methods(
                    requested_methods,
                    options.get("eligible_methods", self.eligible_methods),
                )
            else:
                # eligible_methods is a consensus-only setting. Union should
                # retain every configured method's complementary output.
                eligible_methods = self._resolve_eligible_methods(
                    requested_methods, requested_methods
                )
            methods = self._filter_unusable_methods(requested_methods)

            min_votes = self._validate_min_votes(
                options.get("min_votes", self.min_votes)
            )
            min_agreement = self._validate_min_agreement(
                options.get("min_agreement", self.min_agreement)
            )
            method_weights = self._validate_method_weights(
                options.get("method_weights", self.method_weights)
            )

            min_confidence = options.get("min_confidence", self.min_confidence)
            entity_types = options.get("entity_types", self.entity_types)

            # Merge config with options
            all_options = {**self.config, **options}
            if entity_types:
                all_options["entity_types"] = entity_types

            # Try each method in order. Fallback returns the first non-empty
            # result; union and consensus keep empty method results so their
            # denominators retain configured method provenance.
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
                    for merge_option in self._MERGE_OPTION_KEYS:
                        method_options.pop(merge_option, None)
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
                    if merge_strategy != "fallback":
                        entities = self._align_entities_to_text(entities, text)

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
                    
                    if merge_strategy == "fallback":
                        if filtered:
                            # Ensure default metadata
                            for e in filtered:
                                if e.metadata is None:
                                    e.metadata = {}
                                if "batch_index" not in e.metadata:
                                    e.metadata["batch_index"] = 0

                            self.progress_tracker.stop_tracking(
                                tracking_id,
                                status="completed",
                                message=f"Extracted {len(filtered)} entities using {method_name}",
                            )
                            return filtered
                    else:
                        all_entities.append((method_name, filtered))

                except Exception as e:
                    self.logger.warning(
                        "Method %s failed: %s", method_name, e, exc_info=True
                    )
                    continue

            if merge_strategy == "consensus":
                entities = self._vote_entities(
                    all_entities,
                    eligible_methods=eligible_methods,
                    min_votes=min_votes,
                    min_agreement=min_agreement,
                    method_weights=method_weights,
                )
            elif merge_strategy == "union":
                entities = self._union_entities(
                    all_entities,
                    eligible_methods=eligible_methods,
                    method_weights=method_weights,
                )
            else:
                # Only the explicit fallback strategy may introduce its own
                # pattern candidates after every configured method fails.
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
        self,
        results: Sequence[Union[List[Entity], Tuple[str, List[Entity]]]],
        threshold: Optional[float] = None,
        *,
        eligible_methods: Optional[Sequence[str]] = None,
        min_votes: Optional[int] = None,
        min_agreement: Optional[float] = None,
        method_weights: Optional[Dict[str, float]] = None,
    ) -> List[Entity]:
        """Merge method results using span-aligned cross-method consensus.

        ``results`` accepts the historical ``List[List[Entity]]`` shape as
        well as ``(method_name, entities)`` pairs. The latter retains method
        provenance, while anonymous historical inputs receive stable generated
        names. ``threshold`` remains a compatibility alias for
        ``min_agreement``; confidence is never used as a substitute for votes.
        """
        resolved_min_votes = self._validate_min_votes(
            self.min_votes if min_votes is None else min_votes
        )
        if min_agreement is None:
            min_agreement = threshold if threshold is not None else self.min_agreement
        resolved_min_agreement = self._validate_min_agreement(min_agreement)
        resolved_method_weights = self._validate_method_weights(
            self.method_weights if method_weights is None else method_weights
        )

        return self._merge_method_results(
            results,
            merge_strategy="consensus",
            eligible_methods=eligible_methods,
            min_votes=resolved_min_votes,
            min_agreement=resolved_min_agreement,
            method_weights=resolved_method_weights,
        )

    def _union_entities(
        self,
        results: Sequence[Union[List[Entity], Tuple[str, List[Entity]]]],
        *,
        eligible_methods: Optional[Sequence[str]] = None,
        method_weights: Optional[Dict[str, float]] = None,
    ) -> List[Entity]:
        """Merge all method results while retaining single-method candidates."""
        resolved_method_weights = self._validate_method_weights(
            self.method_weights if method_weights is None else method_weights
        )
        return self._merge_method_results(
            results,
            merge_strategy="union",
            eligible_methods=eligible_methods,
            min_votes=1,
            min_agreement=None,
            method_weights=resolved_method_weights,
        )

    def _merge_method_results(
        self,
        results: Sequence[Union[List[Entity], Tuple[str, List[Entity]]]],
        *,
        merge_strategy: str,
        eligible_methods: Optional[Sequence[str]],
        min_votes: int,
        min_agreement: Optional[float],
        method_weights: Dict[str, float],
    ) -> List[Entity]:
        """Align overlapping mentions and merge them with a named strategy."""
        method_results = self._normalize_method_results(results)
        eligible_methods = self._normalize_eligible_method_names(
            eligible_methods, method_results
        )
        if not eligible_methods:
            return []

        eligible_identities = {
            self._method_identity(method_name) for method_name in eligible_methods
        }
        clusters = self._cluster_entities(method_results, eligible_identities)
        merged = []

        for cluster in clusters:
            entity = self._build_merged_entity(
                cluster,
                eligible_methods=eligible_methods,
                merge_strategy=merge_strategy,
                min_votes=min_votes,
                min_agreement=min_agreement,
            )
            if entity is None:
                continue

            merged.append(entity)

        if merge_strategy == "consensus":
            merged = self._resolve_consensus_label_conflicts(
                merged, method_weights
            )

        return sorted(
            merged,
            key=lambda entity: (
                entity.start_char,
                entity.end_char,
                entity.label,
                entity.text.casefold(),
            ),
        )

    def _normalize_method_results(
        self,
        results: Sequence[Union[List[Entity], Tuple[str, List[Entity]]]],
    ) -> List[Tuple[str, List[Entity]]]:
        """Coalesce alias methods so one backend cannot cast two votes."""
        normalized = {}
        for index, result in enumerate(results):
            if (
                isinstance(result, tuple)
                and len(result) == 2
                and isinstance(result[0], str)
            ):
                method_name, entities = result
            else:
                method_name, entities = f"method_{index + 1}", result

            identity = self._method_identity(method_name)
            if identity not in normalized:
                normalized[identity] = {"name": method_name, "entities": []}
            if entities:
                normalized[identity]["entities"].extend(entities)

        return [
            (data["name"], data["entities"])
            for data in normalized.values()
        ]

    def _normalize_eligible_method_names(
        self,
        eligible_methods: Optional[Sequence[str]],
        method_results: Sequence[Tuple[str, List[Entity]]],
    ) -> List[str]:
        """Keep configured failed methods in the consensus denominator."""
        if eligible_methods is None:
            eligible_methods = [method_name for method_name, _ in method_results]

        known_names = {
            self._method_identity(method_name): method_name
            for method_name, _ in method_results
        }
        normalized = []
        seen = set()
        for method_name in eligible_methods:
            identity = self._method_identity(method_name)
            if identity in seen:
                continue
            normalized.append(known_names.get(identity, method_name))
            seen.add(identity)
        return normalized

    def _cluster_entities(
        self,
        method_results: Sequence[Tuple[str, List[Entity]]],
        eligible_identities: set,
    ) -> List[List[Tuple[str, Entity]]]:
        """Align same-label mentions with deterministic one-to-one matching.

        Each method is matched to existing candidates as a batch, ordered by
        descending span IoU. This prevents an early, weaker boundary variant
        from consuming a method's only vote before its exact match is seen.
        Different labels stay separate here and are reconciled only after
        each label's independent support has been counted.
        """
        clusters_by_label = {}
        ordered_results = sorted(
            method_results,
            key=lambda result: (
                self._method_identity(result[0]),
                result[0],
            ),
        )

        for method_name, entities in ordered_results:
            method_identity = self._method_identity(method_name)
            if method_identity not in eligible_identities:
                continue

            unique_entities = {}
            for entity in entities:
                label = self._canonical_label(entity.label)
                key = (label, entity.start_char, entity.end_char)
                existing = unique_entities.get(key)
                if existing is None or self._entity_order_key(
                    entity
                ) < self._entity_order_key(existing):
                    unique_entities[key] = entity

            entities_by_label = {}
            for entity in unique_entities.values():
                label = self._canonical_label(entity.label)
                entities_by_label.setdefault(label, []).append(entity)

            for label in sorted(entities_by_label):
                candidates = sorted(
                    entities_by_label[label], key=self._entity_order_key
                )
                label_clusters = clusters_by_label.setdefault(label, [])
                edges = []
                for candidate_index, candidate in enumerate(candidates):
                    for cluster_index, cluster in enumerate(label_clusters):
                        if any(
                            self._method_identity(cluster_method) == method_identity
                            for cluster_method, _ in cluster
                        ):
                            continue
                        # A cluster represents one consensus mention, so a
                        # candidate must overlap *every* vote already in it.
                        # Using a best-pair score here would let A~B and B~C
                        # turn into a false A/B/C consensus when A !~ C.
                        scores = [
                            self._span_iou(candidate, clustered_entity)
                            for _, clustered_entity in cluster
                        ]
                        score = min(scores)
                        if score >= self._MIN_SPAN_IOU:
                            edges.append((score, candidate_index, cluster_index))

                matched_candidates = set()
                matched_clusters = set()
                for _, candidate_index, cluster_index in sorted(
                    edges,
                    key=lambda item: (
                        -item[0],
                        self._entity_order_key(candidates[item[1]]),
                        item[2],
                    ),
                ):
                    if (
                        candidate_index in matched_candidates
                        or cluster_index in matched_clusters
                    ):
                        continue
                    label_clusters[cluster_index].append(
                        (method_name, candidates[candidate_index])
                    )
                    matched_candidates.add(candidate_index)
                    matched_clusters.add(cluster_index)

                for candidate_index, candidate in enumerate(candidates):
                    if candidate_index not in matched_candidates:
                        label_clusters.append([(method_name, candidate)])

        return [
            cluster
            for label in sorted(clusters_by_label)
            for cluster in clusters_by_label[label]
        ]

    def _resolve_consensus_label_conflicts(
        self,
        entities: Sequence[Entity],
        method_weights: Dict[str, float],
    ) -> List[Entity]:
        """Choose one deterministic label when candidates share one span.

        Cross-label candidates only conflict when their final document spans
        are identical. Nested entities at different spans remain distinct.
        """
        resolved = {}

        def conflict_order_key(entity: Entity) -> Tuple[Any, ...]:
            metadata = entity.metadata or {}
            support_weight = sum(
                self._method_weight(method_name, method_weights)
                for method_name in metadata.get("supporting_methods", [])
            )
            confidence = self._numeric_confidence(entity.confidence)
            confidence_key = -confidence if confidence is not None else float("inf")
            return (
                -support_weight,
                -metadata.get("vote_count", 0),
                confidence_key,
                entity.label,
                entity.text.casefold(),
            )

        for entity in entities:
            key = (entity.start_char, entity.end_char)
            existing = resolved.get(key)
            if existing is None or conflict_order_key(entity) < conflict_order_key(
                existing
            ):
                resolved[key] = entity

        return list(resolved.values())

    @staticmethod
    def _span_iou(first: Entity, second: Entity) -> float:
        """Return overlap-over-union for two document spans."""
        intersection = max(
            0,
            min(first.end_char, second.end_char)
            - max(first.start_char, second.start_char),
        )
        if not intersection:
            return 0.0
        union = max(first.end_char, second.end_char) - min(
            first.start_char, second.start_char
        )
        return intersection / union if union else 0.0

    @classmethod
    def _canonical_label(cls, label: str) -> str:
        """Normalize common NER aliases and BIO prefixes before label voting."""
        normalized = str(label).strip().upper()
        if "-" in normalized:
            prefix, remainder = normalized.split("-", 1)
            if prefix in {"B", "I", "L", "U", "E", "S"}:
                normalized = remainder
        return cls._LABEL_ALIASES.get(normalized, normalized)

    @staticmethod
    def _numeric_confidence(confidence: Any) -> Optional[float]:
        """Convert a usable confidence score without treating missing scores as zero."""
        if confidence is None:
            return None
        try:
            normalized = float(confidence)
        except (TypeError, ValueError):
            return None
        return normalized if math.isfinite(normalized) else None

    @classmethod
    def _entity_order_key(cls, entity: Entity) -> Tuple[Any, ...]:
        """Provide a deterministic winner for boundary and confidence variants."""
        confidence = cls._numeric_confidence(entity.confidence)
        confidence_key = -confidence if confidence is not None else float("inf")
        return (
            confidence_key,
            -(entity.end_char - entity.start_char),
            entity.start_char,
            entity.end_char,
            entity.text.casefold(),
            entity.label.casefold(),
        )

    def _method_weight(
        self,
        method_name: str,
        method_weights: Dict[str, float],
    ) -> float:
        """Read a weight using the canonical backend name."""
        identity = self._method_identity(method_name)
        return method_weights.get(identity, 1.0)

    def _build_merged_entity(
        self,
        cluster: Sequence[Tuple[str, Entity]],
        *,
        eligible_methods: Sequence[str],
        merge_strategy: str,
        min_votes: int,
        min_agreement: Optional[float],
    ) -> Optional[Entity]:
        """Resolve one same-label, offset-aligned candidate."""
        selected_by_method = {}
        for method_name, entity in cluster:
            identity = self._method_identity(method_name)
            existing = selected_by_method.get(identity)
            if existing is None or (
                self._entity_order_key(entity)
                < self._entity_order_key(existing[1])
            ):
                selected_by_method[identity] = (method_name, entity)

        eligible_records = []
        seen = set()
        for method_name in eligible_methods:
            identity = self._method_identity(method_name)
            if identity not in seen:
                eligible_records.append((identity, method_name))
                seen.add(identity)
        if not eligible_records:
            return None

        if not selected_by_method:
            return None

        supporting_entries = [
            (identity, method_name, entity)
            for identity, (method_name, entity) in selected_by_method.items()
        ]
        vote_count = len(supporting_entries)
        agreement = vote_count / len(eligible_records)
        if merge_strategy == "consensus" and (
            vote_count < min_votes
            or (min_agreement is not None and agreement < min_agreement)
        ):
            return None

        representative = min(
            (entity for _, _, entity in supporting_entries), key=self._entity_order_key
        )
        canonical_label = self._canonical_label(representative.label)

        supporting_by_identity = {
            identity: (method_name, entity)
            for identity, method_name, entity in supporting_entries
        }
        supporting_methods = [
            method_name
            for identity, method_name in eligible_records
            if identity in supporting_by_identity
        ]
        method_scores = {
            method_name: (
                self._numeric_confidence(supporting_by_identity[identity][1].confidence)
                if identity in supporting_by_identity
                else None
            )
            for identity, method_name in eligible_records
        }

        confidence_scores = []
        for identity, method_name in eligible_records:
            if identity not in supporting_by_identity:
                continue
            score = self._numeric_confidence(
                supporting_by_identity[identity][1].confidence
            )
            if score is not None:
                confidence_scores.append(score)

        if confidence_scores:
            confidence = sum(confidence_scores) / len(confidence_scores)
        else:
            confidence = representative.confidence

        metadata = dict(representative.metadata or {})
        metadata.update(
            {
                "merge_strategy": merge_strategy,
                "supporting_methods": supporting_methods,
                "vote_count": len(supporting_methods),
                "eligible_method_count": len(eligible_records),
                "agreement": agreement,
                "method_scores": method_scores,
            }
        )

        return Entity(
            text=representative.text,
            label=(
                canonical_label
                if merge_strategy == "consensus"
                else representative.label
            ),
            start_char=representative.start_char,
            end_char=representative.end_char,
            confidence=confidence,
            metadata=metadata,
        )

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
