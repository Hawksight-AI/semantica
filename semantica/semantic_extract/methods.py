"""
Extraction Methods Module

This module provides all extraction methods as simple, reusable functions for
entities, relations, and triplets. It supports multiple extraction approaches
ranging from simple pattern matching to advanced LLM-based extraction.

Supported Methods:

Entity Extraction:
    - "pattern": Pattern-based entity extraction using regex
    - "regex": Advanced regex-based entity extraction with custom patterns
    - "rules": Rule-based entity extraction using linguistic rules
    - "ml": ML-based entity extraction using spaCy
    - "huggingface": HuggingFace NER model extraction
    - "llm": LLM-based entity extraction

Relation Extraction:
    - "pattern": Pattern-based relation extraction
    - "regex": Advanced regex-based relation extraction
    - "cooccurrence": Co-occurrence based relation detection
    - "similarity": Similarity-based relation extraction
    - "dependency": Dependency parsing-based relation extraction
    - "huggingface": HuggingFace relation extraction models
    - "llm": LLM-based relation extraction

Triplet Extraction:
    - "pattern": Pattern-based triplet extraction
    - "rules": Rule-based triplet extraction
    - "huggingface": HuggingFace triplet extraction models
    - "llm": LLM-based triplet extraction

Algorithms Used:

Entity Extraction:
    - Regular Expression Matching: Finite automata-based pattern matching
    - Rule-based NLP: Linguistic rule application and pattern matching
    - Neural NER: CNN/Transformer-based named entity recognition (spaCy)
    - Transformer Token Classification: BERT/RoBERTa for token-level classification
    - LLM Generation: Transformer-based language models for entity extraction

Relation Extraction:
    - Pattern Matching: Regex and string pattern matching algorithms
    - Co-occurrence Analysis: Proximity-based entity relationship detection
    - Dependency Parsing: Transition-based and graph-based parsing algorithms
    - Sequence Classification: Transformer-based relation classification
    - LLM Generation: Language model-based relation extraction

Triplet Extraction:
    - Pattern Matching: Subject-predicate-object pattern extraction
    - Rule-based Extraction: Linguistic rule application
    - Seq2Seq Models: Encoder-decoder transformer models for triplet generation
    - LLM Generation: Structured output generation from language models

Key Features:
    - Multiple extraction methods for entities:
        * Pattern-based: Simple regex pattern matching
        * Regex-based: Advanced regex with custom patterns
        * Rules-based: Linguistic rule-based extraction
        * ML-based: spaCy-based machine learning extraction
        * HuggingFace: Custom HuggingFace NER models
        * LLM-based: Large language model extraction
    - Multiple extraction methods for relations:
        * Pattern-based: Pattern matching for common relations
        * Regex-based: Advanced regex relation extraction
        * Co-occurrence: Proximity-based relation detection
        * Dependency: Dependency parsing-based extraction
        * HuggingFace: Custom HuggingFace relation models
        * LLM-based: LLM-powered relation extraction
    - Multiple extraction methods for triplets:
        * Pattern-based: Pattern matching for triplet extraction
        * Rules-based: Rule-based triplet extraction
        * HuggingFace: Custom HuggingFace triplet models
        * LLM-based: LLM-powered triplet extraction
    - Method dispatchers with registry support
    - Custom method registration capability
    - Consistent interface across all methods

Main Functions:
    - extract_entities_pattern: Pattern-based entity extraction
    - extract_entities_regex: Regex-based entity extraction
    - extract_entities_rules: Rule-based entity extraction
    - extract_entities_ml: ML-based (spaCy) entity extraction
    - extract_entities_huggingface: HuggingFace model entity extraction
    - extract_entities_llm: LLM-based entity extraction
    - extract_relations_pattern: Pattern-based relation extraction
    - extract_relations_regex: Regex-based relation extraction
    - extract_relations_cooccurrence: Co-occurrence relation extraction
    - extract_relations_dependency: Dependency parsing relation extraction
    - extract_relations_huggingface: HuggingFace relation extraction
    - extract_relations_llm: LLM-based relation extraction
    - extract_triplets_pattern: Pattern-based triplet extraction
    - extract_triplets_rules: Rule-based triplet extraction
    - extract_triplets_huggingface: HuggingFace triplet extraction
    - extract_triplets_llm: LLM-based triplet extraction
    - get_entity_method: Get entity extraction method by name
    - get_relation_method: Get relation extraction method by name
    - get_triplet_method: Get triplet extraction method by name

Example Usage:
    >>> from semantica.semantic_extract.methods import get_entity_method
    >>> extract_fn = get_entity_method("llm")
    >>> entities = extract_fn("Apple Inc. was founded in 1976.", provider="openai")

Author: Semantica Contributors
License: MIT
"""

import re
import difflib
import threading
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import Any, Dict, List, Optional, Tuple, Union

from ..utils.exceptions import ProcessingError
from ..utils.logging import get_logger
from .providers import HuggingFaceModelLoader, create_provider
from .registry import method_registry
from .cache import ExtractionCache
from .config import config
from .types import Entity, Relation, Triplet

try:
    from .schemas import (
        EntitiesResponse,
        RelationsResponse,
        RelationsWithTemporalResponse,
        TripletsResponse,
    )
    SCHEMAS_AVAILABLE = True
except ImportError:
    SCHEMAS_AVAILABLE = False

logger = get_logger("methods")

# Initialize global result cache
_result_cache = ExtractionCache(
    ttl=config.get("cache_ttl", 3600)
)
if not config.get("cache_enabled", True):
    _result_cache.enabled = False

# Try to import spaCy
from ..utils.helpers import safe_import

spacy, SPACY_AVAILABLE = safe_import("spacy")


# ============================================================================
# Scoring Helper Functions
# ============================================================================

# Global cache for spacy model and text embedder to avoid reloading
_nlp_cache = None
_embedder_cache = None

# Cache for models loaded by name, so extraction functions do not pay
# spacy.load() on every call. Entries record the spacy module they were loaded
# from: tests patch `methods.spacy` with a mock, and an entry produced by a
# different module object must not be handed back to a later caller.
_spacy_model_cache: Dict[str, Tuple[Any, Any]] = {}
_spacy_model_cache_lock = threading.Lock()


def load_spacy_model(name: str):
    """Load a spaCy model once per process, keyed by model name.

    Raises whatever ``spacy.load`` raises (``OSError`` for a missing model), so
    callers keep their existing fallback behavior.
    """
    cached = _spacy_model_cache.get(name)
    if cached is not None and cached[0] is spacy:
        return cached[1]

    with _spacy_model_cache_lock:
        cached = _spacy_model_cache.get(name)
        if cached is not None and cached[0] is spacy:
            return cached[1]
        nlp = spacy.load(name)
        _spacy_model_cache[name] = (spacy, nlp)
        return nlp


def clear_spacy_model_cache() -> None:
    """Drop every cached spaCy model. Intended for tests."""
    with _spacy_model_cache_lock:
        _spacy_model_cache.clear()


def get_text_embedder():
    """
    Get or load the TextEmbedder model for high-accuracy semantic similarity.
    """
    global _embedder_cache
    if _embedder_cache:
        return _embedder_cache
        
    try:
        from ..embeddings.text_embedder import TextEmbedder
        # Use a lightweight but effective model for speed/accuracy balance
        # BAAI/bge-small-en-v1.5 is excellent for semantic similarity
        # Enable caching within the embedder if supported, or use our own
        _embedder_cache = TextEmbedder(model_name="BAAI/bge-small-en-v1.5", normalize=True)
        logger.info("Loaded TextEmbedder for high-accuracy similarity")
        return _embedder_cache
    except Exception as e:
        logger.warning(f"Failed to load TextEmbedder: {e}")
        return None

def get_nlp_model():
    """
    Get or load a spaCy model for similarity calculations.
    Prioritizes larger models for better vectors.
    """
    global _nlp_cache
    if _nlp_cache:
        return _nlp_cache
    
    if not SPACY_AVAILABLE:
        return None
        
    try:
        # Prefer larger models for vectors
        # Note: 'en_core_web_lg' has true vectors. 'sm' only has context tensors.
        for model_name in ["en_core_web_lg", "en_core_web_md", "en_core_web_sm"]:
            if spacy.util.is_package(model_name):
                try:
                    # Disable parser/ner for speed if we only need vectors
                    _nlp_cache = spacy.load(model_name, disable=["parser", "ner", "lemmatizer"])
                    logger.info(f"Loaded spaCy model for similarity: {model_name}")
                    return _nlp_cache
                except Exception:
                    continue
        
        # Try loading generic if specific ones fail
        try:
            _nlp_cache = spacy.load("en_core_web_sm", disable=["parser", "ner", "lemmatizer"])
            return _nlp_cache
        except:
            pass
            
    except Exception as e:
        logger.warning(f"Failed to load spaCy model for similarity: {e}")
        pass
    return None

# Common synonyms for entity matching optimization
_ENTITY_SYNONYMS = {
    # Entity Types
    "person": ["people", "human", "name", "individual", "artist", "actor", "author", "politician"],
    "org": ["company", "organization", "business", "institution", "agency", "brand", "corporation"],
    "organization": ["company", "business", "institution", "agency", "brand", "corporation"],
    "gpe": ["location", "place", "city", "country", "state", "nation", "region"],
    "loc": ["location", "place", "region", "area"],
    "date": ["time", "year", "day", "month", "period", "duration"],
    "money": ["cost", "price", "value", "currency", "amount"],
    "product": ["item", "object", "commodity", "goods", "device", "tool", "vehicle", "software", "app"],
    "event": ["incident", "occasion", "activity", "happening", "ceremony"],
    "drug": ["medication", "medicine", "pharmaceutical", "chemical", "treatment", "therapy"],
    "chemical": ["drug", "substance", "compound", "element"],
    "disease": ["condition", "illness", "sickness", "disorder", "syndrome", "ailment"],
    
    # Relation Types
    "founded_by": ["founder", "creator", "established_by", "started_by", "originator"],
    "acquired": ["bought", "purchased", "acquisition", "takeover", "ownership", "merged_with"],
    "subsidiary_of": ["owned_by", "parent_company", "part_of", "division_of", "unit_of"],
    "works_for": ["employee_of", "employed_by", "staff_of", "team_member", "employs", "hired_by"],
    "located_in": ["based_in", "headquartered_in", "situated_in", "found_in", "operates_in"],
    "ceo_of": ["leader_of", "head_of", "director_of", "president_of", "chief_executive", "managed_by"],
    "invested_in": ["funded", "financed", "backed", "shareholder_of", "venture_capital"],
    "partner_with": ["collaborate_with", "joint_venture", "alliance", "deal_with", "partnership"],
    "competitor_of": ["rival", "competes_with", "opponent", "nemesis"],
    "manufacturer_of": ["producer_of", "maker_of", "creator_of", "builder_of"],
    "treats": ["cures", "heals", "remedy_for", "used_for", "prescribed_for"],
    "causes": ["leads_to", "results_in", "triggers", "produces", "creates"],
    "diagnosed_with": ["suffers_from", "has_condition", "patient_of", "victim_of"],
}

def find_best_match_index(text: str, candidates: List[str]) -> Tuple[int, float]:
    """
    Find the best matching candidate index and score.
    Uses hybrid similarity approach: Exact -> Synonym -> Substring -> Embeddings -> Vector -> Fuzzy.
    Optimized for batch processing to avoid redundant embedding calculations.
    
    Returns:
        Tuple[int, float]: (best_candidate_index, best_score). Index is -1 if no candidates.
    """
    if not candidates:
        return -1, 0.0
    
    if not text:
        return -1, 0.0
        
    text_lower = text.lower().strip()
    if not text_lower:
        return -1, 0.0
        
    candidates_lower = [c.lower().strip() for c in candidates]
    best_idx = -1
    best_score = 0.0
    
    # 1. Exact Match (Fastest)
    try:
        idx = candidates_lower.index(text_lower)
        return idx, 1.0
    except ValueError:
        pass

    # 1b. Common Synonyms (Fast Heuristic)
    # Use global _ENTITY_SYNONYMS dictionary
    synonyms = _ENTITY_SYNONYMS
    
    # Check text synonyms
    if text_lower in synonyms:
        for syn in synonyms[text_lower]:
            if syn in candidates_lower:
                return candidates_lower.index(syn), 0.95
    
    # Check if any candidate is a synonym of text
    for i, cand in enumerate(candidates_lower):
        if cand in synonyms:
            if text_lower in synonyms[cand]:
                if 0.95 > best_score:
                    best_score = 0.95
                    best_idx = i
    
    # 2. Substring Match (Fast)
    word_pat = None
    try:
        word_pat = re.compile(rf"\b{re.escape(text_lower)}\b")
    except Exception:
        word_pat = None

    for i, cand in enumerate(candidates_lower):
        if not cand: continue
        score = 0.0
        if text_lower in cand or cand in text_lower:
            # Calculate length ratio
            ratio = min(len(text_lower), len(cand)) / max(len(text_lower), len(cand))
            score = 0.9 * ratio + 0.1

            if word_pat and word_pat.search(cand):
                score = max(score, 0.88)
        
        if score > best_score:
            best_score = score
            best_idx = i

    # 3. Text Embeddings (High Accuracy Semantic) - Batch Optimized
    if best_score >= 0.85:
        return best_idx, float(best_score)

    embedder = get_text_embedder()
    embedding_idx = -1
    embedding_score = 0.0
    
    if embedder:
        try:
            # Batch embedding: [text, cand1, cand2, ...]
            # We filter out empty candidates to save compute, but need to map back to original indices
            valid_cands_with_idx = [(c, i) for i, c in enumerate(candidates) if c and c.strip()]
            
            if valid_cands_with_idx:
                texts_to_embed = [text] + [c for c, i in valid_cands_with_idx]
                embeddings = list(embedder.embed_batch(texts_to_embed))
                
                if embeddings and len(embeddings) > 1:
                    text_emb = embeddings[0]
                    cand_embs = embeddings[1:]
                    
                    import numpy as np
                    text_norm = np.linalg.norm(text_emb)
                    
                    if text_norm > 0:
                        # Vectorized cosine similarity
                        cand_matrix = np.array(cand_embs)
                        cand_norms = np.linalg.norm(cand_matrix, axis=1)
                        
                        # Avoid division by zero
                        cand_norms[cand_norms == 0] = 1e-10
                        
                        dot_products = np.dot(cand_matrix, text_emb)
                        sims = dot_products / (cand_norms * text_norm)
                        
                        max_sim_idx = np.argmax(sims)
                        max_sim = float(sims[max_sim_idx])
                        
                        if max_sim > embedding_score:
                            embedding_score = max_sim
                            # Map back to original index
                            embedding_idx = valid_cands_with_idx[max_sim_idx][1]
        except Exception as e:
            logger.debug(f"Embedding calculation failed: {e}")
            pass
            
    if embedding_score > best_score:
        best_score = embedding_score
        best_idx = embedding_idx

    # 4. Vector Similarity (Legacy/Fallback)
    if best_score < 0.9:
        nlp = get_nlp_model()
        vector_score = 0.0
        vector_idx = -1
        
        if nlp and nlp.vocab.vectors.shape[0] > 0:
            try:
                doc = nlp(text)
                if doc.vector_norm:
                    for i, candidate in enumerate(candidates):
                        if not candidate: continue
                        cand_doc = nlp(candidate)
                        if cand_doc.vector_norm:
                            score = doc.similarity(cand_doc)
                            if score > vector_score:
                                vector_score = score
                                vector_idx = i
            except Exception:
                pass
        
        if vector_score > best_score:
            best_score = vector_score
            best_idx = vector_idx

    # 5. Fuzzy Match (Fallback)
    if best_score < 0.9:
        for i, cand in enumerate(candidates_lower):
            if not cand: continue
            score = difflib.SequenceMatcher(None, text_lower, cand).ratio()
            if score > best_score:
                best_score = score
                best_idx = i
                
    return best_idx, float(best_score)


def calculate_similarity(text: str, candidates: List[str]) -> float:
    """
    Calculate the maximum similarity between text and a list of candidates.
    Wrapper around find_best_match_index.
    """
    _, score = find_best_match_index(text, candidates)
    return score


def match_entity(text: str, entities: List[Entity], threshold: float = 0.8) -> Optional[Entity]:
    """
    Find the best matching entity for the given text.
    Uses optimized batch similarity matching.
    """
    if not text or not entities:
        return None
        
    # Optimization: Check exact match first (case-insensitive)
    text_lower = text.lower().strip()
    for entity in entities:
        if entity.text.lower().strip() == text_lower:
            return entity

    # Use batch matcher
    candidates = [e.text for e in entities]
    best_idx, best_score = find_best_match_index(text, candidates)
    
    if best_idx >= 0 and best_score >= threshold:
        return entities[best_idx]
        
    return None


def filter_entities_for_text(
    text: str,
    entities: List[Entity],
    max_keep: int = 80,
) -> List[Entity]:
    if not text or not entities:
        return []

    if max_keep < 1:
        return []

    if len(entities) <= max_keep:
        return entities

    text_lower = text.lower()
    stop_tokens = {
        "inc",
        "incorporated",
        "corp",
        "corporation",
        "co",
        "company",
        "ltd",
        "llc",
        "plc",
        "group",
        "holdings",
        "limited",
        "the",
        "and",
        "or",
        "of",
        "in",
        "on",
        "at",
        "for",
        "to",
        "a",
        "an",
    }

    seen = set()
    matched: List[Entity] = []
    for entity in entities:
        ent_text = getattr(entity, "text", "")
        if not ent_text:
            continue

        key = ent_text.lower().strip()
        if not key or key in seen:
            continue
        seen.add(key)

        if key in text_lower:
            matched.append(entity)
            continue

        tokens = re.findall(r"[a-z0-9]+", key)
        keep = False
        for tok in tokens:
            if len(tok) < 2:
                continue
            if tok in stop_tokens:
                continue
            if tok in text_lower:
                keep = True
                break
        if keep:
            matched.append(entity)

    if matched:
        if len(matched) > max_keep:
            matched.sort(key=lambda e: len(getattr(e, "text", "")), reverse=True)
            return matched[:max_keep]
        return matched

    entities_sorted = sorted(entities, key=lambda e: len(getattr(e, "text", "")), reverse=True)
    return entities_sorted[:max_keep]


def calculate_weighted_confidence(
    item_type: str, 
    original_confidence: float, 
    valid_types: Optional[List[str]] = None,
    item_text: Optional[str] = None,
    weight_method: float = 0.5,
    weight_similarity: float = 0.5
) -> float:
    """
    Calculate weighted confidence score using both Label and Content similarity.
    Final Score = (weight_method * original_confidence) + (weight_similarity * max(label_sim, content_sim))
    
    Args:
        item_type: The extracted type/label/predicate (e.g., "PERSON", "founded_by")
        original_confidence: The confidence score from the extraction method (0.0-1.0)
        valid_types: List of valid/preferred types provided by user
        item_text: The actual text content extracted (e.g., "Steve Jobs", "acquired")
        weight_method: Weight for the original method confidence (default 0.5)
        weight_similarity: Weight for the similarity score (default 0.5)
        
    Returns:
        float: Weighted confidence score (0.0-1.0)
    """
    if not valid_types:
        return original_confidence
        
    # Similarity 1: Label vs Valid Types (e.g., "PERSON" vs "Artist")
    label_similarity = calculate_similarity(item_type, valid_types)
    
    # Similarity 2: Content vs Valid Types (e.g., "Picasso" vs "Artist")
    content_similarity = 0.0
    if item_text:
        content_similarity = calculate_similarity(item_text, valid_types)
        
    # Take the best similarity match
    best_similarity = max(label_similarity, content_similarity)
    
    # Normalize weights
    total_weight = weight_method + weight_similarity
    if total_weight <= 0:
        return original_confidence
        
    w_m = weight_method / total_weight
    w_s = weight_similarity / total_weight
    
    final_score = (w_m * original_confidence) + (w_s * best_similarity)
    
    return max(0.0, min(1.0, final_score))


# ============================================================================
# Entity Extraction Methods
# ============================================================================


def extract_entities_pattern(text: str, **kwargs) -> List[Entity]:
    """Pattern-based entity extraction using regex."""
    entities = []

    patterns = {
        "ORG": r"\b([A-Z][a-zA-Z]+(?:\s+[A-Z][a-zA-Z]+)*\s+(?:Inc|Corp|LLC|Ltd|Company)(?:\.|\b))",
        "PERSON": r"\b([A-Z][a-z]+(?:\s+(?!Inc|Corp|LLC|Ltd|Company)[A-Z][a-z]+)+)\b",
        "GPE": r"\b([A-Z][a-z]+\s*(?:City|State|Country|Nation))\b",
        "DATE": r"\b(\d{1,2}[/-]\d{1,2}[/-]\d{2,4}|\d{4})\b",
    }

    for label, pattern in patterns.items():
        for match in re.finditer(pattern, text):
            entities.append(
                Entity(
                    text=match.group(1) if match.groups() else match.group(0),
                    label=label,
                    start_char=match.start(),
                    end_char=match.end(),
                    confidence=0.7,
                    metadata={"extraction_method": "pattern"},
                )
            )

    return entities


def extract_entities_regex(
    text: str, patterns: Optional[Dict[str, str]] = None, **kwargs
) -> List[Entity]:
    """Advanced regex-based entity extraction with custom patterns."""
    entities = []

    if patterns is None:
        patterns = {
            "PERSON": r"\b([A-Z][a-z]+(?:\s+[A-Z][a-z]+)+)\b",
            "ORG": r"\b([A-Z][a-zA-Z]+(?:\s+[A-Z][a-zA-Z]+)*\s+(?:Inc|Corp|LLC|Ltd|Company|Corporation))\b",
            "GPE": r"\b([A-Z][a-z]+(?:\s+[A-Z][a-z]+)*)\b",
            "DATE": r"\b(\d{1,2}[/-]\d{1,2}[/-]\d{2,4}|\d{4})\b",
            "MONEY": r"\b(\$[\d,]+(?:\.\d{2})?)\b",
            "PERCENT": r"\b(\d+(?:\.\d+)?%)\b",
        }

    for label, pattern in patterns.items():
        for match in re.finditer(pattern, text, re.IGNORECASE):
            entities.append(
                Entity(
                    text=match.group(1) if match.groups() else match.group(0),
                    label=label,
                    start_char=match.start(),
                    end_char=match.end(),
                    confidence=0.75,
                    metadata={"extraction_method": "regex", "pattern": pattern},
                )
            )

    return entities


def extract_entities_rules(text: str, **kwargs) -> List[Entity]:
    """Rule-based entity extraction using linguistic rules."""
    entities = []
    words = text.split()

    # Rule: Capitalized words at sentence start are likely entities
    sentences = re.split(r"[.!?]+", text)
    char_offset = 0

    for sentence in sentences:
        sentence = sentence.strip()
        if not sentence:
            char_offset += 1
            continue

        words_in_sent = sentence.split()
        if words_in_sent:
            first_word = words_in_sent[0]
            if first_word and first_word[0].isupper() and len(first_word) > 2:
                start = text.find(first_word, char_offset)
                if start >= 0:
                    entities.append(
                        Entity(
                            text=first_word,
                            label="PERSON",  # Default assumption
                            start_char=start,
                            end_char=start + len(first_word),
                            confidence=0.6,
                            metadata={
                                "extraction_method": "rules",
                                "rule": "sentence_start",
                            },
                        )
                    )

        char_offset += len(sentence) + 1

    return entities


def extract_entities_ml(
    text: str, model: str = "en_core_web_sm", **kwargs
) -> List[Entity]:
    """ML-based entity extraction using spaCy."""
    if not SPACY_AVAILABLE:
        logger.warning("spaCy not available, falling back to pattern extraction")
        return extract_entities_pattern(text, **kwargs)

    try:
        nlp = load_spacy_model(model)
    except OSError:
        logger.warning(f"spaCy model {model} not found, using en_core_web_sm")
        try:
            nlp = load_spacy_model("en_core_web_sm")
        except OSError:
            logger.warning(
                "spaCy model not available, falling back to pattern extraction"
            )
            return extract_entities_pattern(text, **kwargs)
        except Exception as exc:
            logger.warning(
                "spaCy fallback triggered because the default model failed to initialize. Falling back to pattern extraction.",
                exc_info=True,
            )
            return extract_entities_pattern(text, **kwargs)
    except Exception as exc:
        logger.warning(
            "spaCy model %s failed to initialize, falling back to pattern extraction.",
            model,
            exc_info=True,
        )
        return extract_entities_pattern(text, **kwargs)

    doc = nlp(text)
    entities = []

    for ent in doc.ents:
        confidence = 1.0
        if hasattr(ent, "confidence"):
            confidence = ent.confidence
        elif hasattr(ent, "score"):
            confidence = ent.score

        entities.append(
            Entity(
                text=ent.text,
                label=ent.label_,
                start_char=ent.start_char,
                end_char=ent.end_char,
                confidence=confidence,
                metadata={
                    "extraction_method": "ml",
                    "model": model,
                    "lemma": ent.lemma_ if hasattr(ent, "lemma_") else ent.text,
                },
            )
        )

    return entities


def extract_entities_huggingface(
    text: str,
    model: str = "dslim/bert-base-NER",
    device: Optional[str] = None,
    **kwargs,
) -> List[Entity]:
    """
    Extract entities using HuggingFace transformers.
    
    Args:
        text: Input text
        model: Model name or path
        device: Device to use (cpu, cuda, mps)
        **kwargs: Additional arguments passed to the pipeline (e.g., aggregation_strategy)
    """
    loader = HuggingFaceModelLoader(device=device)
    # Pass kwargs (like aggregation_strategy) to load_ner_model
    model_obj = loader.load_ner_model(model, **kwargs)
    results = loader.extract_entities(model_obj, text)

    entities = []
    
    # Check if manual aggregation is needed (raw IOB tags detected)
    needs_manual_aggregation = False
    if results and isinstance(results[0], dict):
        first_label = results[0].get("label", "")
        # If we see B- tags and no entity_group (which implies aggregation wasn't done), we aggregate manually
        if (first_label.startswith("B-") or first_label.startswith("I-")) and "entity_group" not in results[0]:
            needs_manual_aggregation = True

    if needs_manual_aggregation:
        current_entity = None
        for result in results:
            label = result.get("label", "")
            word = result.get("word", result.get("entity", ""))
            score = result.get("score", 1.0)
            start = result.get("start", 0)
            end = result.get("end", 0)
            
            # Clean word (handle BERT ## and RoBERTa Ġ)
            clean_word = word.replace("##", "").replace("Ġ", "")
            if not clean_word:
                continue

            # Determine tag type and entity type
            tag_prefix = label[:2] if len(label) > 2 else ""
            entity_type = label[2:] if len(label) > 2 else label

            if tag_prefix == "B-":
                # Save previous entity
                if current_entity:
                    entities.append(current_entity)
                
                # Start new entity
                current_entity = Entity(
                    text=clean_word,
                    label=entity_type,
                    start_char=start,
                    end_char=end,
                    confidence=score,
                    metadata={
                        "model": model, 
                        "extraction_method": "huggingface",
                        "source": "huggingface",
                        "raw_iob": True
                    },
                )
            
            elif tag_prefix == "I-" and current_entity:
                # Check if type matches (loose check allows for some noise, strict check enforces type)
                # We'll be lenient and allow continuation if it makes sense contextually, 
                # but ideally types should match.
                if current_entity.label == entity_type:
                    # Append text
                    # Use offsets to determine spacing
                    if start > current_entity.end_char:
                        # If there's a gap, add space (unless it was a subword that got split but has gap? Unlikely)
                        # Usually gap means space.
                        # However, for ## subwords, start usually equals end.
                        # For Ġ, it implies space.
                        current_entity.text += " " + clean_word
                    else:
                        current_entity.text += clean_word
                    
                    current_entity.end_char = end
                    # Update confidence (average)
                    current_entity.confidence = (current_entity.confidence + score) / 2
                else:
                    # Type mismatch - treat as new entity or ignore?
                    # Treating as new B- is safer to avoid losing data
                    if current_entity:
                        entities.append(current_entity)
                    
                    current_entity = Entity(
                        text=clean_word,
                        label=entity_type,
                        start_char=start,
                        end_char=end,
                        confidence=score,
                        metadata={
                            "model": model, 
                            "extraction_method": "huggingface",
                            "source": "huggingface",
                            "raw_iob": True
                        },
                    )
            
            else:
                # O tag or I- without B or other cases
                if current_entity:
                    entities.append(current_entity)
                    current_entity = None
        
        # Append last entity
        if current_entity:
            entities.append(current_entity)

    else:
        # Standard processing for aggregated results or simple output
        for result in results:
            if isinstance(result, dict):
                # Handle different output formats based on aggregation strategy
                label = result.get("entity_group", result.get("label", "UNKNOWN"))
                text_content = result.get("word", result.get("entity", ""))
                
                # Clean up text content (remove ## for subwords if raw)
                if "##" in text_content and "aggregation_strategy" not in kwargs:
                     text_content = text_content.replace("##", "")
                if "Ġ" in text_content: # RoBERTa
                     text_content = text_content.replace("Ġ", " ").strip()
                     
                entities.append(
                    Entity(
                        text=text_content,
                        label=label,
                        start_char=result.get("start", 0),
                        end_char=result.get("end", 0),
                        confidence=result.get("score", 1.0),
                        metadata={
                            "model": model, 
                            "extraction_method": "huggingface",
                            "source": "huggingface"
                        },
                    )
                )
            elif isinstance(result, list):
                 # Handle list of lists (sometimes returned by pipeline)
                 pass

    return entities


def extract_entities_llm(
    text: str,
    provider: str = "openai",
    model: Optional[str] = None,
    silent_fail: bool = False,
    max_text_length: Optional[int] = None,
    structured_output_mode: str = "typed",
    **kwargs,
) -> List[Entity]:
    """
    LLM-based entity extraction.
    
    Args:
        text: Input text
        provider: LLM provider
        model: LLM model
        silent_fail: If True, return empty list on error. If False (default), raise exception.
        max_text_length: Maximum text length before auto-chunking. None = provider default.
        **kwargs: Additional options
    """
    # Support llm_model parameter to disambiguate from ML model
    if "llm_model" in kwargs:
        model = kwargs.pop("llm_model")
    
    # Check cache
    cache_params = {
        "provider": provider,
        "model": model,
        "max_text_length": max_text_length,
        "structured_output_mode": structured_output_mode,
        "entity_types": kwargs.get("entity_types"),
    }
    cached_result = _result_cache.get("entities", text, **cache_params)
    if cached_result is not None:
        logger.debug(f"Cache hit for entity extraction ({len(cached_result)} entities)")
        return cached_result
    
    # 1. PRE-EXTRACTION VALIDATION
    if not text or not text.strip():
        error_msg = "Text is empty or whitespace only"
        logger.error(error_msg)
        if not silent_fail:
            raise ProcessingError(error_msg)
        return []

    # Pass api_key if provided in kwargs (needed for all providers)
    provider_kwargs = kwargs.copy()
    if "api_key" not in provider_kwargs or not provider_kwargs["api_key"]:
        # Try to get from environment as fallback for all providers
        import os
        env_key = f"{provider.upper()}_API_KEY"
        api_key = os.getenv(env_key)
        if api_key:
            provider_kwargs["api_key"] = api_key

    # 2. PROVIDER VALIDATION
    try:
        llm = create_provider(provider, model=model, **provider_kwargs)
        if not llm.is_available():
            error_msg = f"{provider} provider not available. Check API key and dependencies."
            logger.error(error_msg)
            if not silent_fail:
                raise ProcessingError(error_msg)
            return []
    except Exception as e:
        error_msg = f"Failed to create {provider} provider: {e}"
        logger.error(error_msg)
        if not silent_fail:
            raise ProcessingError(error_msg) from e
        return []

    # 3. TEXT LENGTH CHECK AND CHUNKING
    if max_text_length is None:
        # Provider-specific defaults
        max_text_length = {
            "groq": 64000,
            "openai": 64000,
            "gemini": 64000,
            "anthropic": 64000,
            "deepseek": 64000,
        }.get(provider.lower(), 32000)
    
    if len(text) > max_text_length:
        logger.info(f"Text length ({len(text)}) exceeds limit ({max_text_length}). Chunking...")
        return _extract_entities_chunked(
            text, 
            provider=provider, 
            model=model, 
            silent_fail=silent_fail,
            max_text_length=max_text_length,
            **kwargs
        )

    # Use custom entity types if provided, otherwise use defaults
    entity_types = kwargs.get("entity_types")
    if entity_types:
        entity_types_str = ", ".join(entity_types)
        entity_types_instruction = f"""Preferred entity types: {entity_types_str}.
You may also use related or similar entity types if they better match the context (e.g., variations, synonyms, or domain-specific types).
If an entity doesn't fit any of the preferred types, use the most appropriate type from the preferred list or a closely related type."""
    else:
        entity_types_instruction = """Entity types should be one of: 
- PERSON (People, names, roles)
- ORG (Companies, organizations, institutions, brands)
- GPE (Countries, cities, states, locations)
- DATE (Dates, years, time periods)
- EVENT (Named events, conferences)
- PRODUCT (Software, hardware, vehicles)
- CONCEPT (Abstract ideas, technologies)

Use the most appropriate type for each entity.
Examples:
- 'Microsoft' is an ORG
- 'Satya Nadella' is a PERSON
- Job titles/roles like 'CEO', 'CTO', 'President', 'Engineer' are CONCEPT unless part of a person's name
- 'Python' is a PRODUCT or CONCEPT depending on context."""

    if not SCHEMAS_AVAILABLE:
        raise ImportError("Pydantic schemas not available. Install pydantic/instructor to use LLM extraction.")

    try:
        prompt = f"""Extract named entities from the provided text.
Return the result as a JSON object with an "entities" key containing the list of entities.
Each entity should have 'text', 'label', and 'confidence' fields.

IMPORTANT: 
- Return a FLAT LIST of entities. 
- DO NOT group entities by type.
- The output structure must exactly match: {{ "entities": [ {{ "text": "...", "label": "...", "confidence": ... }}, ... ] }}

Example output (JSON format only):
{{
  "entities": [
    {{"text": "Entity Name", "label": "CATEGORY", "confidence": 0.95}},
    {{"text": "Another Entity", "label": "OTHER_CATEGORY", "confidence": 0.90}}
  ]
}}

Instructions:
1. Extract entities ONLY from the text provided below.
2. Do not include any entities from the example above.
3. {entity_types_instruction}

Text to extract from:
{text}"""
        
        # Use typed generation with Pydantic schema
        result_obj = llm.generate_typed(prompt, schema=EntitiesResponse, **kwargs)
        
        # Convert back to internal Entity format
        entities = []
        for e_out in result_obj.entities:
            entities.append(Entity(
                text=e_out.text,
                label=e_out.label,
                start_char=e_out.start if hasattr(e_out, "start") else 0, # Schema might not force these
                end_char=e_out.end if hasattr(e_out, "end") else 0,
                confidence=e_out.confidence,
                metadata={
                    "provider": provider, 
                    "model": model, 
                    "extraction_method": "llm_typed",
                }
            ))
        
        logger.info(f"Successfully extracted {len(entities)} entities using {provider}/{model} (typed)")
        _result_cache.set("entities", text, entities, **cache_params)
        return entities
        
    except Exception as e:
        # Check for length/token limit errors
        error_msg_str = str(e).lower()
        if "length" in error_msg_str or "max_tokens" in error_msg_str:
            logger.warning(f"LLM output truncated due to length limit. Reducing chunk size and retrying... ({e})")
            
            # Determine new chunk size (halve it)
            current_max = max_text_length or len(text)
            new_max = current_max // 2
            
            if new_max > 100: # Minimum viable chunk size check
                return _extract_entities_chunked(
                    text, 
                    provider=provider, 
                    model=model, 
                    silent_fail=silent_fail, 
                    max_text_length=new_max,
                    **kwargs
                )

        error_msg = f"LLM entity extraction failed ({provider}/{model}): {e}"
        logger.error(error_msg, exc_info=True)
        if not silent_fail:
            if isinstance(e, ProcessingError):
                raise
            raise ProcessingError(error_msg) from e
        return []


def _parse_entity_result(result: Any, provider: str, model: Optional[str]) -> List[Entity]:
    """Helper to parse raw LLM result into Entity objects."""
    entities = []
    items = []
    
    if isinstance(result, list):
        items = result
    elif isinstance(result, dict):
        # Handle cases where LLM wraps the list in a key
        for key in ["entities", "data", "results"]:
            if key in result and isinstance(result[key], list):
                items = result[key]
                break
        if not items and "text" in result: # Single object instead of list
            items = [result]

    for item in items:
        if not isinstance(item, dict):
            continue
            
        text = item.get("text", "")
        if not text:
            continue
            
        entities.append(
            Entity(
                text=text,
                label=item.get("label", "UNKNOWN"),
                start_char=item.get("start", 0),
                end_char=item.get("end", 0),
                confidence=item.get("confidence", 0.9),
                metadata={
                    "provider": provider,
                    "model": model,
                    "extraction_method": "llm",
                },
            )
        )
    return entities


def _extract_entities_chunked(
    text: str,
    provider: str,
    model: Optional[str],
    silent_fail: bool,
    max_text_length: int,
    structured_output_mode: str = "typed",
    **kwargs
) -> List[Entity]:
    """Internal helper to extract entities from long text by chunking."""
    from ..split import TextSplitter
    
    splitter = TextSplitter(
        method="recursive",
        chunk_size=max_text_length,
        chunk_overlap=int(max_text_length * 0.1) # 10% overlap
    )
    chunks = splitter.split(text)
    
    all_entities = []
    
    from .config import resolve_max_workers
    max_workers = resolve_max_workers(explicit=kwargs.get("max_workers"))
    
    with ThreadPoolExecutor(max_workers=max_workers) as executor:
        future_to_chunk = {}
        for i, chunk in enumerate(chunks):
            logger.debug(f"Scheduling entity extraction for chunk {i+1}/{len(chunks)}")
            # We recursively call extract_entities_llm with the chunk
            # but ensure we don't trigger re-chunking by setting max_text_length large
            future = executor.submit(
                extract_entities_llm,
                chunk.text,
                provider=provider,
                model=model,
                silent_fail=False, # We want to know if a chunk fails
                max_text_length=len(chunk.text) + 1,
                structured_output_mode=structured_output_mode,
                **kwargs
            )
            future_to_chunk[future] = (i, chunk)
            
        for future in as_completed(future_to_chunk):
            i, chunk = future_to_chunk[future]
            try:
                chunk_entities = future.result()
                
                # Adjust entity positions to account for chunk offset
                for entity in chunk_entities:
                    entity.start_char += chunk.start_index
                    entity.end_char += chunk.start_index
                    all_entities.append(entity)
                    
            except Exception as e:
                if not silent_fail:
                    logger.error(f"Chunk {i+1} failed: {e}")
                    raise
                logger.warning(f"Chunk {i+1} failed (silent): {e}")

    return all_entities





# ============================================================================
# Relation Extraction Methods
# ============================================================================


def extract_relations_pattern(
    text: str, entities: List[Entity], **kwargs
) -> List[Relation]:
    """Pattern-based relation extraction."""
    relations = []

    if not entities:
        return []

    # Create entity pattern from provided entities
    # Sort by length descending to match longest entities first (e.g. "Apple Inc." before "Apple")
    sorted_entities = sorted(entities, key=lambda e: len(e.text), reverse=True)
    
    # Escape entity texts and join with OR
    # We use a non-capturing group for the alternatives
    entity_texts = [re.escape(e.text) for e in sorted_entities]
    # Remove duplicates
    entity_texts = list(dict.fromkeys(entity_texts))
    
    if not entity_texts:
        return []
        
    ent_pat = f"(?:{'|'.join(entity_texts)})"
    
    # Use entity pattern for subject as well, since we require the subject to be a known entity
    # This prevents matching long strings of text that happen to end with a relation keyword
    subject_pat = ent_pat

    relation_patterns = {
        "founded_by": [
            fr"(?P<subject>{subject_pat})(?:[.,])?\s+(?:was\s+)?founded\s+by\s+(?P<object>{ent_pat})",
            fr"(?P<object>{ent_pat})(?:[.,])?\s+founded\s+(?P<subject>{ent_pat})",
            fr"(?P<subject>{subject_pat})(?:[.,])?\s+(?:was\s+)?established\s+by\s+(?P<object>{ent_pat})",
            fr"(?P<object>{ent_pat})(?:[.,])?\s+established\s+(?P<subject>{ent_pat})",
            fr"(?P<subject>{subject_pat})(?:[.,])?\s+(?:was\s+)?created\s+by\s+(?P<object>{ent_pat})",
            fr"(?P<object>{ent_pat})(?:[.,])?\s+created\s+(?P<subject>{ent_pat})",
            fr"(?P<subject>{subject_pat})(?:[.,])?\s+(?:was\s+)?started\s+by\s+(?P<object>{ent_pat})",
            fr"(?P<object>{ent_pat})(?:[.,])?\s+started\s+(?P<subject>{ent_pat})",
            fr"(?P<subject>{subject_pat})(?:[.,])?\s+(?:was\s+)?co-founded\s+by\s+(?P<object>{ent_pat})",
            fr"(?P<object>{ent_pat})(?:[.,])?\s+co-founded\s+(?P<subject>{ent_pat})",
            fr"(?P<object>{ent_pat})(?:[.,])?\s+is\s+(?:the\s+)?founder\s+of\s+(?P<subject>{ent_pat})",
        ],
        "located_in": [
            fr"(?P<subject>{subject_pat})\s+is\s+located\s+in\s+(?P<object>{ent_pat})",
            fr"(?P<subject>{subject_pat})\s+in\s+(?P<object>{ent_pat})",
            fr"(?P<subject>{subject_pat})\s+(?:is\s+)?headquartered\s+in\s+(?P<object>{ent_pat})",
            fr"(?P<subject>{subject_pat})\s+(?:is\s+)?based\s+in\s+(?P<object>{ent_pat})",
            fr"(?P<subject>{subject_pat})\s+has\s+(?:its\s+)?headquarters\s+in\s+(?P<object>{ent_pat})",
            fr"(?P<subject>{subject_pat})\s+operates\s+(?:out\s+of|from)\s+(?P<object>{ent_pat})",
            fr"(?P<subject>{subject_pat})\s+has\s+offices\s+in\s+(?P<object>{ent_pat})",
        ],
        "works_for": [
            fr"(?P<subject>{subject_pat})\s+works?\s+for\s+(?P<object>{ent_pat})",
            fr"(?P<subject>{subject_pat})\s+works?\s+at\s+(?P<object>{ent_pat})",
            fr"(?P<subject>{subject_pat})\s+is\s+an?\s+employee\s+of\s+(?P<object>{ent_pat})",
            fr"(?P<subject>{subject_pat})\s+is\s+(?:the\s+)?(?:CEO|CFO|CTO|COO|director|manager|president|founder)\s+of\s+(?P<object>{ent_pat})",
            fr"(?P<subject>{subject_pat})\s+joined\s+(?P<object>{ent_pat})",
            fr"(?P<subject>{subject_pat})\s+was\s+hired\s+by\s+(?P<object>{ent_pat})",
            fr"(?P<subject>{subject_pat})\s+serves\s+at\s+(?P<object>{ent_pat})",
        ],
        "born_in": [
            fr"(?P<subject>{subject_pat})\s+was\s+born\s+in\s+(?P<object>{ent_pat})",
            fr"(?P<subject>{subject_pat})\s+born\s+in\s+(?P<object>{ent_pat})",
            fr"(?P<subject>{subject_pat})\s+is\s+a\s+native\s+of\s+(?P<object>{ent_pat})",
            fr"(?P<subject>{subject_pat})\s+hails\s+from\s+(?P<object>{ent_pat})",
            fr"(?P<subject>{subject_pat})\s+is\s+originally\s+from\s+(?P<object>{ent_pat})",
        ],
        "acquired_by": [
            fr"(?P<subject>{subject_pat})\s+(?:was\s+)?acquired\s+by\s+(?P<object>{ent_pat})",
            fr"(?P<object>{ent_pat})\s+acquired\s+(?P<subject>{ent_pat})",
            fr"(?P<subject>{subject_pat})\s+(?:was\s+)?bought\s+by\s+(?P<object>{ent_pat})",
            fr"(?P<object>{ent_pat})\s+bought\s+(?P<subject>{ent_pat})",
            fr"(?P<subject>{subject_pat})\s+is\s+a\s+subsidiary\s+of\s+(?P<object>{ent_pat})",
        ],
    }

    entity_map = {e.text.lower(): e for e in entities}

    for relation_type, patterns in relation_patterns.items():
        for pattern in patterns:
            for match in re.finditer(pattern, text, re.IGNORECASE):
                subject_text = match.group("subject").strip()
                object_text = match.group("object").strip()
                
                subject_entity = entity_map.get(subject_text.lower())
                object_entity = entity_map.get(object_text.lower())
                
                if subject_entity and object_entity:
                    start = max(0, match.start() - 50)
                    end = min(len(text), match.end() + 50)
                    context = text[start:end]

                    relations.append(
                        Relation(
                            subject=subject_entity,
                            predicate=relation_type,
                            object=object_entity,
                            confidence=0.7,
                            context=context,
                            metadata={
                                "extraction_method": "pattern",
                                "pattern": pattern,
                            },
                        )
                    )

    return relations


def extract_relations_regex(
    text: str,
    entities: List[Entity],
    patterns: Optional[Dict[str, List[str]]] = None,
    **kwargs,
) -> List[Relation]:
    """Advanced regex-based relation extraction."""
    if patterns is None:
        patterns = {
            "founded_by": [
                r"(?P<subject>\w+)\s+(?:was\s+)?founded\s+by\s+(?P<object>\w+(?:\s+\w+)*)"
            ],
            "located_in": [r"(?P<subject>\w+)\s+is\s+located\s+in\s+(?P<object>\w+)"],
        }

    relations = []
    entity_map = {e.text.lower(): e for e in entities}

    for relation_type, pattern_list in patterns.items():
        for pattern in pattern_list:
            for match in re.finditer(pattern, text, re.IGNORECASE):
                subject_text = match.group("subject")
                object_text = match.group("object")

                subject_entity = entity_map.get(subject_text.lower())
                object_entity = entity_map.get(object_text.lower())

                if subject_entity and object_entity:
                    relations.append(
                        Relation(
                            subject=subject_entity,
                            predicate=relation_type,
                            object=object_entity,
                            confidence=0.75,
                            context=text[
                                max(0, match.start() - 30) : min(
                                    len(text), match.end() + 30
                                )
                            ],
                            metadata={"extraction_method": "regex"},
                        )
                    )

    return relations


def extract_relations_cooccurrence(
    text: str, entities: List[Entity], **kwargs
) -> List[Relation]:
    """Co-occurrence based relation extraction."""
    relations = []

    for i, entity1 in enumerate(entities):
        for entity2 in entities[i + 1 :]:
            distance = abs(entity1.end_char - entity2.start_char)
            if distance < 100:  # Within 100 characters
                start = min(entity1.start_char, entity2.start_char)
                end = max(entity1.end_char, entity2.end_char)
                context = text[max(0, start - 30) : min(len(text), end + 30)]

                relations.append(
                    Relation(
                        subject=entity1,
                        predicate="related_to",
                        object=entity2,
                        confidence=0.6,  # Meets default threshold
                        context=context,
                        metadata={
                            "extraction_method": "co_occurrence",
                            "distance": distance,
                        },
                    )
                )

    return relations


def extract_relations_similarity(
    text: str, entities: List[Entity], relation_types: Optional[List[str]] = None, **kwargs
) -> List[Relation]:
    """
    Similarity-based relation extraction.
    Uses semantic similarity to match the context between entities to provided relation types.
    """
    if not entities:
        return []

    # If no relation types provided, we can't do similarity matching against types
    if not relation_types:
        # Fallback to co-occurrence if no types to match against
        logger.warning("No relation types provided for similarity matching. Falling back to co-occurrence.")
        return extract_relations_cooccurrence(text, entities, **kwargs)

    relations = []
    
    # Try to load spaCy model with vectors
    nlp = None
    if SPACY_AVAILABLE:
        try:
            # Prefer larger models for vectors
            for model_name in ["en_core_web_lg", "en_core_web_md", "en_core_web_sm"]:
                if spacy.util.is_package(model_name):
                    nlp = load_spacy_model(model_name)
                    break
            if not nlp:
                 # Try loading what we have
                 try:
                     nlp = load_spacy_model("en_core_web_sm") 
                 except:
                     pass
        except Exception:
            pass

    # Pre-compute relation type vectors if possible
    relation_vectors = {}
    has_vectors = False
    if nlp:
        # Check if model has vectors
        if nlp.vocab.vectors.shape[0] > 0:
            has_vectors = True
            for rt in relation_types:
                relation_vectors[rt] = nlp(rt)
    
    for entity1 in entities:
        for entity2 in entities:
            if entity1 == entity2:
                continue
                
            # Check distance
            distance = abs(entity1.end_char - entity2.start_char)
            # Only consider entities reasonably close (e.g., within same sentence or clause)
            if distance > 100: 
                continue

            # Ensure correct order for extracting text between
            if entity1.end_char < entity2.start_char:
                start_pos = entity1.end_char
                end_pos = entity2.start_char
            else:
                start_pos = entity2.end_char
                end_pos = entity1.start_char
                
            between_text = text[start_pos:end_pos].strip()
            
            if not between_text:
                continue

            # Calculate similarity
            best_type = None
            best_score = 0.0

            if has_vectors and relation_vectors:
                # Vector similarity
                doc = nlp(between_text)
                if doc.vector_norm:
                    for rt, vec in relation_vectors.items():
                        if vec.vector_norm:
                            sim = doc.similarity(vec)
                            if sim > best_score:
                                best_score = sim
                                best_type = rt
            else:
                # String similarity / Keyword matching
                from difflib import SequenceMatcher
                for rt in relation_types:
                    # Check for direct keyword presence (strong signal)
                    if rt.lower() in between_text.lower():
                        score = 1.0
                    else:
                        # Fuzzy match
                        score = SequenceMatcher(None, rt.lower(), between_text.lower()).ratio()
                    
                    if score > best_score:
                        best_score = score
                        best_type = rt

            # Threshold
            threshold = kwargs.get("similarity_threshold", 0.4 if has_vectors else 0.6)
            
            if best_type and best_score >= threshold:
                relations.append(
                    Relation(
                        subject=entity1,
                        predicate=best_type,
                        object=entity2,
                        confidence=float(best_score),
                        context=text[max(0, min(entity1.start_char, entity2.start_char) - 20) : min(len(text), max(entity1.end_char, entity2.end_char) + 20)],
                        metadata={
                            "extraction_method": "similarity",
                            "similarity_score": float(best_score),
                            "between_text": between_text
                        },
                    )
                )

    return relations


def extract_relations_dependency(
    text: str, entities: List[Entity], model: str = "en_core_web_sm", **kwargs
) -> List[Relation]:
    """Dependency parsing based relation extraction."""
    if not SPACY_AVAILABLE:
        logger.warning("spaCy not available, falling back to pattern extraction")
        return extract_relations_pattern(text, entities, **kwargs)

    try:
        nlp = load_spacy_model(model)
    except OSError:
        logger.warning(f"spaCy model {model} not found")
        return extract_relations_pattern(text, entities, **kwargs)

    doc = nlp(text)
    relations = []
    
    # Map tokens to entities
    token_to_entity = {}
    for token in doc:
        for entity in entities:
            # Check if token is within entity span
            if token.idx >= entity.start_char and (token.idx + len(token)) <= entity.end_char:
                token_to_entity[token] = entity
                break
    
    # DEBUG: Print token to entity mapping
    # print(f"DEBUG: Token to entity mapping keys: {[t.text for t in token_to_entity.keys()]}")

    # DEBUG: Dump full dependency tree
    # print("DEBUG: Dependency Tree:")
    # for token in doc:
    #     print(f"  {token.i}: {token.text} ({token.dep_}) -> {token.head.text} ({token.head.i})")

    # Helper to find entity for a token (or its head chain)
    def find_subject_entity(token):
        # 1. If acl, check head
        if token.dep_ == "acl":
            head = token.head
            if head in token_to_entity:
                return token_to_entity[head]
            
            # 2. If head is attr/acomp, check its head's nsubj
            if head.dep_ in ["attr", "acomp", "dobj"] and head.head.pos_ in ["VERB", "AUX"]:
                copula = head.head
                for child in copula.children:
                    if child.dep_ in ["nsubj", "nsubjpass"] and child in token_to_entity:
                        return token_to_entity[child]
        return None

    # Helper to expand objects via conjunctions
    def expand_conjunctions(token):
        results = [token]
        for child in token.children:
            if child.dep_ == "conj":
                results.extend(expand_conjunctions(child))
        return results

    for token in doc:
        # Check if token is a potential predicate (Verb)
        # We process verbs that have nsubj OR are acl OR are ROOT/VERB
        
        subject_entity = None
        
        # Case 1: Token has nsubj/nsubjpass
        nsubj = next((c for c in token.children if c.dep_ in ["nsubj", "nsubjpass"]), None)
        if nsubj:
            subject_entity = token_to_entity.get(nsubj)
        
        # Case 2: Token is acl or other modifier, try to infer subject from context
        if not subject_entity:
             subject_entity = find_subject_entity(token)
             
        if not subject_entity:
            continue

        verb = token
        # DEBUG: Print found subject
        # print(f"DEBUG: Found subject {subject_entity.text} for verb {verb.text}")

        # Find objects
        potential_objects = []
        for child in verb.children:
            # Direct objects
            if child.dep_ in ["dobj", "attr", "acomp"]:
                potential_objects.extend(expand_conjunctions(child))
                # Check for "attr of object" pattern (e.g. "CEO of Apple")
                for grandchild in child.children:
                    if grandchild.dep_ == "prep":
                        for greatgrandchild in grandchild.children:
                            if greatgrandchild.dep_ == "pobj":
                                potential_objects.extend(expand_conjunctions(greatgrandchild))
                                
            # Prepositional objects (including agent)
            elif child.dep_ in ["prep", "agent"]:
                for grandchild in child.children:
                    if grandchild.dep_ == "pobj":
                        potential_objects.extend(expand_conjunctions(grandchild))
        
        # DEBUG: Print potential objects
        # print(f"DEBUG: Potential objects for verb {verb.text}: {[t.text for t in potential_objects]}")

        for obj_token in potential_objects:
            object_entity = token_to_entity.get(obj_token)
            
            # DEBUG: Print object checking
            # print(f"DEBUG: Checking object token: {obj_token.text}, Entity: {object_entity}")

            if object_entity and subject_entity != object_entity:
                relations.append(
                    Relation(
                        subject=subject_entity,
                        predicate=verb.lemma_,
                        object=object_entity,
                        confidence=0.8,
                        context=text[
                            max(0, token.idx - 30) : min(
                                len(text), obj_token.idx + len(obj_token.text) + 30
                            )
                        ],
                        metadata={
                            "extraction_method": "dependency",
                            "dependency_path": f"{token.dep_} -> ... -> {obj_token.dep_}",
                        },
                    )
                )

    return relations


def extract_relations_huggingface(
    text: str,
    entities: List[Entity],
    model: str,
    device: Optional[str] = None,
    **kwargs,
) -> List[Relation]:
    """HuggingFace relation extraction."""
    loader = HuggingFaceModelLoader(device=device)
    model_obj = loader.load_relation_model(model, **kwargs)

    # Pass kwargs (e.g. threshold)
    results = loader.extract_relations(model_obj, text, entities, **kwargs)

    relations = []
    for result in results:
        relations.append(
            Relation(
                subject=result["subject"],
                predicate=result["relation"],
                object=result["object"],
                confidence=result.get("score", 1.0),
                context=text,
                metadata={
                    "model": model,
                    "extraction_method": "huggingface"
                }
            )
        )
    return relations


def extract_relations_llm(
    text: str,
    entities: List[Entity],
    provider: str = "openai",
    model: Optional[str] = None,
    silent_fail: bool = False,
    max_text_length: Optional[int] = None,
    structured_output_mode: str = "typed",
    max_retries: int = 3,
    extract_temporal_bounds: bool = False,
    **kwargs,
) -> List[Relation]:
    """
    LLM-based relation extraction.

    Args:
        text: Input text
        entities: Pre-extracted entities
        provider: LLM provider
        model: LLM model
        silent_fail: If True, return empty list on error. If False (default), raise exception.
        max_text_length: Maximum text length before auto-chunking. None = provider default.
        max_retries: Maximum number of retries for LLM calls (default: 3)
        extract_temporal_bounds: If True, extend the prompt to extract temporal validity
            per relation. Each relation's metadata gains: valid_from, valid_until,
            temporal_confidence (0.0–1.0), and temporal_source_text. Low confidence (<0.5)
            produces a warning log but is not suppressed. Default False.
        **kwargs: Additional options
    """
    # Support llm_model parameter to disambiguate from ML model
    if "llm_model" in kwargs:
        model = kwargs.pop("llm_model")
    
    # Check cache
    cache_params = {
        "provider": provider,
        "model": model,
        "max_text_length": max_text_length,
        "structured_output_mode": structured_output_mode,
        "max_retries": max_retries,
        "relation_types": kwargs.get("relation_types"),
        "extract_temporal_bounds": extract_temporal_bounds,
        # Include entities hash/str in cache key implicitly via **cache_params
        "entities_hash": hash(tuple(sorted([e.text for e in entities]))) if entities else 0
    }
    cached_result = _result_cache.get("relations", text, **cache_params)
    if cached_result is not None:
        logger.debug(f"Cache hit for relation extraction ({len(cached_result)} relations)")
        return cached_result
    
    # 1. PRE-EXTRACTION VALIDATION
    if not text or not text.strip():
        error_msg = "Text is empty or whitespace only"
        logger.error(error_msg)
        if not silent_fail:
            raise ProcessingError(error_msg)
        return []

    if not entities:
        error_msg = "No entities provided for relation extraction. Relations require existing entities."
        logger.error(error_msg)
        if not silent_fail:
            raise ProcessingError(error_msg)
        return []

    # Pass api_key if provided in kwargs
    provider_kwargs = kwargs.copy()
    
    # Check if api_key is provided but empty, or not provided at all
    if "api_key" not in provider_kwargs or not provider_kwargs["api_key"]:
        import os
        env_key = f"{provider.upper()}_API_KEY"
        api_key = os.getenv(env_key)
        if api_key:
            provider_kwargs["api_key"] = api_key
            
    # Remove None/empty API key if still present to avoid provider errors
    if "api_key" in provider_kwargs and not provider_kwargs["api_key"]:
        del provider_kwargs["api_key"]

    # 2. PROVIDER VALIDATION
    try:
        llm = create_provider(provider, model=model, **provider_kwargs)
        if not llm.is_available():
            error_msg = f"{provider} provider not available for relation extraction (key missing?)."
            logger.error(error_msg)
            if not silent_fail:
                raise ProcessingError(error_msg)
            return []
    except Exception as e:
        error_msg = f"Failed to create {provider} provider for relations: {e}"
        logger.error(error_msg)
        if not silent_fail:
            raise ProcessingError(error_msg) from e
        return []

    # 3. TEXT LENGTH CHECK AND CHUNKING
    if max_text_length is None:
        # Default limits for chunking only - NOT for LLM generation
        max_text_length = {
            "groq": 64000,
            "openai": 64000,
            "gemini": 64000,
            "anthropic": 64000,
            "deepseek": 64000,
        }.get(provider.lower(), 32000)
    
    if len(text) > max_text_length:
        logger.info(f"Text length ({len(text)}) exceeds limit for relations. Chunking...")
        return _extract_relations_chunked(
            text, entities, provider=provider, model=model,
            silent_fail=silent_fail, max_text_length=max_text_length,
            max_retries=max_retries,
            extract_temporal_bounds=extract_temporal_bounds,
            **kwargs
        )

    original_entities = entities
    # Use a fixed internal default for prompt entity cap (do not accept overrides from kwargs)
    max_entities_prompt = 80
    prompt_entities = original_entities
    if max_entities_prompt > 0 and len(original_entities) > max_entities_prompt:
        prompt_entities = filter_entities_for_text(
            text,
            original_entities,
            max_keep=max_entities_prompt,
        )

    entities_str = ", ".join([f"{e.text} ({e.label})" for e in prompt_entities])

    # Use custom relation types if provided
    relation_types = kwargs.get("relation_types")
    if relation_types:
        relation_types_str = ", ".join(relation_types)
        relation_types_instruction = f"""
Preferred relation types: {relation_types_str}.
You may also use related or similar relation types if they better capture the relationship (e.g., variations, synonyms, or domain-specific relations).
If a relation doesn't fit any of the preferred types, use the most appropriate type from the preferred list or a closely related type that accurately describes the relationship."""
    else:
        relation_types_instruction = """
Extract meaningful relationships between entities. Use appropriate relation types that accurately describe how entities are connected.
Common relation types include: related_to, part_of, located_in, created_by, uses, depends_on, interacts_with, and similar variations."""

    verbose_mode = kwargs.get("verbose", False)
    if verbose_mode:
        logger.debug(
            "[methods.extract_relations_llm] Constructing prompt for %d entities...",
            len(prompt_entities),
        )

    if not SCHEMAS_AVAILABLE:
        raise ImportError("Pydantic schemas not available. Install pydantic/instructor to use LLM extraction.")

    # ── Base prompt (always included) ───────────────────────────────────────
    if not extract_temporal_bounds:
        prompt = f"""Extract relations between entities from the provided text.
Return the result as a JSON object with a "relations" key containing the list of relations.
Each relation must have 'subject', 'predicate', and 'object' fields.

Example output (JSON format only):
{{
  "relations": [
    {{"subject": "Entity A", "predicate": "related_to", "object": "Entity B", "confidence": 0.95}},
    {{"subject": "Subject Entity", "predicate": "action_verb", "object": "Object Entity", "confidence": 0.90}}
  ]
}}

Instructions:
1. Extract relations ONLY from the text provided below.
2. Do not include any relations from the example above.
3. Use the provided entities list as a reference for subjects and objects.
4. {relation_types_instruction}

Text to extract from:
{text}
Entities found in text: {entities_str}"""
    else:
        # ── Temporal-extended prompt ─────────────────────────────────────────
        prompt = f"""Extract relations between entities from the provided text, along with temporal validity information for each relation.
Return the result as a JSON object with a "relations" key. Each relation must have:
'subject', 'predicate', 'object', 'confidence', 'valid_from', 'valid_until', 'temporal_confidence', 'temporal_source_text'.

TEMPORAL EXTRACTION RULES:
- valid_from: ISO 8601 date or exact phrase from the text for when this relation became valid. Set to null if no temporal signal is present.
- valid_until: ISO 8601 date or exact phrase for when this relation ceased. Set to null if open-ended or absent.
- temporal_confidence (float 0.0–1.0) — calibrated as follows:
    1.00 = full ISO date ("2022-03-15", "March 15, 2022")
    0.90 = explicit year + month ("March 2022", "2022-03")
    0.85 = explicit year only ("in 2022", "since 2021", "from 2019")
    0.75 = quarter ("Q3 2023", "Q2 2021")
    0.65 = named season or approximate range ("summer 2022", "early 2020s", "mid-2022")
    0.50 = vague relative with computable anchor ("last year", "three months ago")
    0.35 = highly vague relative ("recently", "years ago", "in the past")
    0.00 = no temporal signal present for this relation
- temporal_source_text: the EXACT verbatim substring from the source text that contains the temporal signal. Set to null when temporal_confidence is 0.0.

IMPORTANT: Do NOT invent or guess dates. If the text contains no temporal signal for a relation, set valid_from and valid_until to null and temporal_confidence to 0.0.

Few-shot examples (do NOT include these in your output):
  Text: "Apple acquired Beats in May 2014."
  → valid_from: "2014-05-01", valid_until: null, temporal_confidence: 0.90, temporal_source_text: "May 2014"

  Text: "The CEO has led the company since Q3 2020."
  → valid_from: "Q3 2020", valid_until: null, temporal_confidence: 0.75, temporal_source_text: "since Q3 2020"

  Text: "Last year, Google partnered with Samsung."
  → valid_from: "last year", valid_until: null, temporal_confidence: 0.50, temporal_source_text: "Last year"

  Text: "The firm was under enhanced supervision between Q2 and Q4 2021."
  → valid_from: "Q2 2021", valid_until: "Q4 2021", temporal_confidence: 0.75, temporal_source_text: "between Q2 and Q4 2021"

  Text: "Microsoft develops Windows."
  → valid_from: null, valid_until: null, temporal_confidence: 0.00, temporal_source_text: null

Example JSON output format:
{{
  "relations": [
    {{
      "subject": "Apple", "predicate": "acquired", "object": "Beats",
      "confidence": 0.97,
      "valid_from": "2014-05-01", "valid_until": null,
      "temporal_confidence": 0.90, "temporal_source_text": "May 2014"
    }}
  ]
}}

Instructions:
1. Extract relations ONLY from the text provided below.
2. Do not include any relations from the examples above.
3. Use the provided entities list as a reference for subjects and objects.
4. {relation_types_instruction}

Text to extract from:
{text}
Entities found in text: {entities_str}"""

    try:
        # Use typed generation with Pydantic schema
        if verbose_mode:
            logger.debug(
                "[methods.extract_relations_llm] Calling llm.generate_typed (%s/%s)...",
                provider, model,
            )
        # Only forward minimal, safe parameters to provider calls
        call_kwargs = {}
        if "temperature" in kwargs:
            call_kwargs["temperature"] = kwargs["temperature"]
        if "verbose" in kwargs:
            call_kwargs["verbose"] = kwargs["verbose"]

        call_kwargs["max_retries"] = max_retries

        # Select schema based on whether temporal extraction is requested
        active_schema = RelationsWithTemporalResponse if extract_temporal_bounds else RelationsResponse
        result_obj = llm.generate_typed(prompt, schema=active_schema, **call_kwargs)
        if verbose_mode:
            logger.debug(
                "[methods.extract_relations_llm] Received response from %s.", provider
            )

        # Convert back to internal Relation format (robust across providers)
        # Normalize typed result to a plain dict compatible with _parse_relation_result
        try:
            if hasattr(result_obj, "model_dump"):
                parsed = result_obj.model_dump()
            elif isinstance(result_obj, dict):
                parsed = result_obj
            elif hasattr(result_obj, "relations"):
                # Instructor may return objects for each relation; convert where possible
                rel_items = []
                for r in getattr(result_obj, "relations", []):
                    if hasattr(r, "model_dump"):
                        rel_items.append(r.model_dump())
                    elif isinstance(r, dict):
                        rel_items.append(r)
                    else:
                        # Best-effort attribute access — include temporal fields when present
                        rel_items.append({
                            "subject": getattr(r, "subject", ""),
                            "object": getattr(r, "object", ""),
                            "predicate": getattr(r, "predicate", "related_to"),
                            "confidence": getattr(r, "confidence", 0.9),
                            "valid_from": getattr(r, "valid_from", None),
                            "valid_until": getattr(r, "valid_until", None),
                            "temporal_confidence": getattr(r, "temporal_confidence", 0.0),
                            "temporal_source_text": getattr(r, "temporal_source_text", None),
                        })
                parsed = {"relations": rel_items}
            else:
                parsed = result_obj
        except Exception:
            parsed = result_obj

        # Use common parser to build internal Relation objects
        relations = _parse_relation_result(
            parsed, original_entities, text, provider, model,
            extraction_method="llm_typed",
            extract_temporal_bounds=extract_temporal_bounds,
        )

        # If typed path returned no relations, attempt a structured JSON fallback
        if not relations:
            try:
                if verbose_mode:
                    logger.debug(
                        "[methods.extract_relations_llm] Typed result empty, attempting structured JSON fallback..."
                    )
                raw_json = llm.generate_structured(prompt, **call_kwargs)
                relations = _parse_relation_result(
                    raw_json, original_entities, text, provider, model,
                    extraction_method="llm_typed",
                    extract_temporal_bounds=extract_temporal_bounds,
                )
            except Exception as _e:
                # Keep relations as empty if fallback fails
                pass

        logger.info(f"Successfully extracted {len(relations)} relations using {provider}/{model} (typed)")
        _result_cache.set("relations", text, relations, **cache_params)
        return relations

    except Exception as e:
        # Check for length/token limit errors
        error_msg_str = str(e).lower()
        if "length" in error_msg_str or "max_tokens" in error_msg_str:
            logger.warning(f"LLM output truncated due to length limit. Reducing chunk size and retrying... ({e})")

            # Determine new chunk size (halve it)
            current_max = max_text_length or len(text)
            new_max = current_max // 2

            if new_max > 100:  # Minimum viable chunk size check
                return _extract_relations_chunked(
                    text, entities, provider=provider, model=model,
                    silent_fail=silent_fail, max_text_length=new_max,
                    structured_output_mode=structured_output_mode,
                    extract_temporal_bounds=extract_temporal_bounds,
                    **kwargs
                )

        error_msg = f"LLM relation extraction failed ({provider}/{model}): {e}"
        logger.error(error_msg, exc_info=True)
        if not silent_fail:
            if isinstance(e, ProcessingError):
                raise
            raise ProcessingError(error_msg) from e
        return []


def _parse_relation_result(
    result: Any,
    entities: List[Entity],
    text: str,
    provider: str,
    model: Optional[str],
    extraction_method: str = "llm",
    extract_temporal_bounds: bool = False,
) -> List[Relation]:
    """Helper to parse raw LLM result into Relation objects."""
    relations = []
    items = []

    if isinstance(result, list):
        items = result
    elif isinstance(result, dict):
        for key in ["relations", "data", "results"]:
            if key in result and isinstance(result[key], list):
                items = result[key]
                break
        if not items and "subject" in result:
            items = [result]

    for item in items:
        if not isinstance(item, dict):
            continue

        subject_text = item.get("subject", "")
        object_text = item.get("object", "")

        if not subject_text or not object_text:
            continue

        # Ensure they are strings
        subject_text = str(subject_text)
        object_text = str(object_text)

        # Find matching entities using hybrid similarity; fall back to a
        # synthetic entity so multi-value results are never silently dropped.
        subject_entity = match_entity(subject_text, entities)
        object_entity = match_entity(object_text, entities)

        if not subject_entity:
            subject_entity = Entity(
                text=subject_text, label="UNKNOWN",
                start_char=0, end_char=len(subject_text),
                confidence=0.8, metadata={"synthetic": True},
            )
        if not object_entity:
            object_entity = Entity(
                text=object_text, label="UNKNOWN",
                start_char=0, end_char=len(object_text),
                confidence=0.8, metadata={"synthetic": True},
            )

        metadata: dict = {
            "provider": provider,
            "model": model,
            "extraction_method": extraction_method,
        }

        if extract_temporal_bounds:
            temporal_confidence = float(item.get("temporal_confidence") or 0.0)
            valid_from = item.get("valid_from")
            valid_until = item.get("valid_until")
            temporal_source_text = item.get("temporal_source_text")

            metadata["valid_from"] = valid_from
            metadata["valid_until"] = valid_until
            metadata["temporal_confidence"] = temporal_confidence
            metadata["temporal_source_text"] = temporal_source_text

            if temporal_confidence < 0.5 and (valid_from is not None or valid_until is not None):
                logger.warning(
                    "Low temporal confidence (%.2f) for '%s' (%s → %s). Source: %r",
                    temporal_confidence,
                    item.get("predicate", ""),
                    item.get("subject", ""),
                    item.get("object", ""),
                    temporal_source_text,
                )

        relations.append(
            Relation(
                subject=subject_entity,
                predicate=item.get("predicate", "related_to"),
                object=object_entity,
                confidence=item.get("confidence", 0.9),
                context=text,
                metadata=metadata,
            )
        )
    return relations


def _extract_relations_chunked(
    text: str,
    entities: List[Entity],
    provider: str,
    model: Optional[str],
    silent_fail: bool,
    max_text_length: int,
    structured_output_mode: str = "typed",
    max_retries: int = 3,
    extract_temporal_bounds: bool = False,
    **kwargs
) -> List[Relation]:
    """Internal helper to extract relations from long text by chunking."""
    from ..split import TextSplitter
    
    splitter = TextSplitter(
        method="recursive",
        chunk_size=max_text_length,
        chunk_overlap=int(max_text_length * 0.1)
    )
    chunks = splitter.split(text)
    
    all_relations = []
    
    from .config import resolve_max_workers
    max_workers = resolve_max_workers(explicit=kwargs.get("max_workers"))
    
    with ThreadPoolExecutor(max_workers=max_workers) as executor:
        future_to_chunk = {}
        for i, chunk in enumerate(chunks):
            # Only include entities that appear in this chunk (or close to it)
            chunk_entities = [
                e for e in entities 
                if e.start_char >= chunk.start_index - 100 and e.end_char <= chunk.end_index + 100
            ]
            
            if not chunk_entities:
                continue
                
            logger.debug(f"Scheduling relation extraction for chunk {i+1}/{len(chunks)} with {len(chunk_entities)} entities")
            
            # Only pass minimal kwargs downstream
            limited_kwargs = {k: kwargs[k] for k in ("relation_types", "temperature", "verbose") if k in kwargs}
            future = executor.submit(
                extract_relations_llm,
                chunk.text,
                entities=chunk_entities,
                provider=provider,
                model=model,
                silent_fail=False,
                max_text_length=len(chunk.text) + 1,
                structured_output_mode=structured_output_mode,
                max_retries=max_retries,
                extract_temporal_bounds=extract_temporal_bounds,
                **limited_kwargs
            )
            future_to_chunk[future] = i
            
        for future in as_completed(future_to_chunk):
            i = future_to_chunk[future]
            try:
                chunk_rels = future.result()
                all_relations.extend(chunk_rels)
            except Exception as e:
                if not silent_fail:
                    logger.error(f"Chunk {i+1} failed: {e}")
                    raise
                logger.warning(f"Chunk {i+1} failed (silent): {e}")
        
    return all_relations





# ============================================================================
# Triplet Extraction Methods
# ============================================================================


def extract_triplets_pattern(
    text: str,
    entities: Optional[List[Entity]] = None,
    relations: Optional[List[Relation]] = None,
    **kwargs,
) -> List[Triplet]:
    """Pattern-based triplet extraction."""
    triplets = []

    if relations:
        # Convert relations to triplets
        for relation in relations:
            triplets.append(
                Triplet(
                    subject=relation.subject.text,
                    predicate=relation.predicate,
                    object=relation.object.text,
                    confidence=relation.confidence,
                    metadata={"extraction_method": "pattern", **relation.metadata},
                )
            )
    elif entities:
        # Simple triplet extraction from entities
        # Look for subject-verb-object patterns
        pattern = r"(?P<subject>\w+)\s+(?P<predicate>\w+)\s+(?P<object>\w+)"
        for match in re.finditer(pattern, text):
            subject_text = match.group("subject")
            predicate_text = match.group("predicate")
            object_text = match.group("object")

            subject_entity = match_entity(subject_text, entities)
            object_entity = match_entity(object_text, entities)

            if subject_entity and object_entity:
                triplets.append(
                    Triplet(
                        subject=subject_entity.text,
                        predicate=predicate_text,
                        object=object_entity.text,
                        confidence=0.7,
                        metadata={"extraction_method": "pattern"},
                    )
                )

    return triplets


def extract_triplets_rules(
    text: str, entities: Optional[List[Entity]] = None, **kwargs
) -> List[Triplet]:
    """Rule-based triplet extraction."""
    triplets = []

    if not entities:
        return triplets

    # Rule: Look for verb patterns between entities
    sentences = re.split(r"[.!?]+", text)
    for sentence in sentences:
        words = sentence.split()
        for i, word in enumerate(words):
            if word.lower() in ["is", "was", "has", "founded", "located"]:
                # Look for entities before and after
                if i > 0 and i < len(words) - 1:
                    before = " ".join(words[:i])
                    after = " ".join(words[i + 1 :])

                    subject_entity = next(
                        (e for e in entities if e.text.lower() in before.lower()), None
                    )
                    object_entity = next(
                        (e for e in entities if e.text.lower() in after.lower()), None
                    )

                    if subject_entity and object_entity:
                        triplets.append(
                            Triplet(
                                subject=subject_entity.text,
                                predicate=word,
                                object=object_entity.text,
                                confidence=0.7,
                                metadata={"extraction_method": "rules"},
                            )
                        )

    return triplets


def extract_triplets_huggingface(
    text: str, model: str, device: Optional[str] = None, **kwargs
) -> List[Triplet]:
    """HuggingFace triplet extraction."""
    loader = HuggingFaceModelLoader(device=device)
    model_obj = loader.load_triplet_model(model, **kwargs)
    
    # REBEL needs special tokens to be preserved
    if "skip_special_tokens" not in kwargs:
        kwargs["skip_special_tokens"] = False
        
    results = loader.extract_triplets(model_obj, text, **kwargs)

    triplets = []
    for result in results:
        if "triplet" in result:
            decoded_text = result["triplet"]
            
            # Clean up common special tokens that might interfere or are noise
            decoded_text = decoded_text.replace("<s>", "").replace("</s>", "").replace("<pad>", "")
            
            # Parse REBEL format: <triplet> subject <subj> predicate <obj> object
            # We use a non-greedy match and lookahead for next triplet or end of string
            import re
            pattern = r"<triplet>(?P<head>.*?)<subj>(?P<relation>.*?)<obj>(?P<tail>.*?)(?=<triplet>|$)"
            
            matches = re.finditer(pattern, decoded_text)
            for match in matches:
                head = match.group("head").strip()
                relation = match.group("relation").strip()
                tail = match.group("tail").strip()
                
                if head and relation and tail:
                    triplets.append(
                        Triplet(
                            subject=head,
                            predicate=relation,
                            object=tail,
                            confidence=0.9, # Model generation doesn't provide per-triplet confidence
                            metadata={
                                "model": model,
                                "extraction_method": "huggingface_rebel"
                            }
                        )
                    )

    return triplets


def extract_triplets_llm(
    text: str,
    entities: Optional[List[Entity]] = None,
    relations: Optional[List[Relation]] = None,
    provider: str = "openai",
    model: Optional[str] = None,
    silent_fail: bool = False,
    max_text_length: Optional[int] = None,
    structured_output_mode: str = "typed",
    max_retries: int = 3,
    **kwargs,
) -> List[Triplet]:
    """
    LLM-based triplet extraction.
    
    Args:
        text: Input text
        entities: Pre-extracted entities (optional)
        relations: Pre-extracted relations (optional)
        provider: LLM provider
        model: LLM model
        silent_fail: If True, return empty list on error. If False (default), raise exception.
        max_text_length: Maximum text length before auto-chunking. None = provider default.
        max_retries: Maximum number of retries for LLM calls (default: 3)
        **kwargs: Additional options
    """
    # Support llm_model parameter to disambiguate from ML model
    if "llm_model" in kwargs:
        model = kwargs.pop("llm_model")
    
    # Check cache
    cache_params = {
        "provider": provider,
        "model": model,
        "max_text_length": max_text_length,
        "structured_output_mode": structured_output_mode,
        "max_retries": max_retries,
        "triplet_types": kwargs.get("triplet_types"),
        # Include entities/relations hash in cache key implicitly via **cache_params
        "entities_hash": hash(tuple(sorted([e.text for e in entities]))) if entities else 0,
        "relations_hash": hash(tuple(sorted([str(r) for r in relations]))) if relations else 0
    }
    cached_result = _result_cache.get("triplets", text, **cache_params)
    if cached_result is not None:
        logger.debug(f"Cache hit for triplet extraction ({len(cached_result)} triplets)")
        return cached_result
    
    # 1. PRE-EXTRACTION VALIDATION
    if not text or not text.strip():
        error_msg = "Text is empty or whitespace only"
        logger.error(error_msg)
        if not silent_fail:
            raise ProcessingError(error_msg)
        return []

    # Pass api_key if provided in kwargs
    provider_kwargs = kwargs.copy()
    
    # Check if api_key is provided but empty, or not provided at all
    if "api_key" not in provider_kwargs or not provider_kwargs["api_key"]:
        import os
        env_key = f"{provider.upper()}_API_KEY"
        api_key = os.getenv(env_key)
        if api_key:
            provider_kwargs["api_key"] = api_key
            
    # Remove None/empty API key if still present to avoid provider errors
    if "api_key" in provider_kwargs and not provider_kwargs["api_key"]:
        del provider_kwargs["api_key"]

    # 2. PROVIDER VALIDATION
    try:
        llm = create_provider(provider, model=model, **provider_kwargs)
        if not llm.is_available():
            error_msg = f"{provider} provider not available for triplet extraction."
            logger.error(error_msg)
            if not silent_fail:
                raise ProcessingError(error_msg)
            return []
    except Exception as e:
        error_msg = f"Failed to create {provider} provider for triplets: {e}"
        logger.error(error_msg)
        if not silent_fail:
            raise ProcessingError(error_msg) from e
        return []

    # 3. TEXT LENGTH CHECK AND CHUNKING
    if max_text_length is None:
        # Default limits for chunking only - NOT for LLM generation
        max_text_length = {
            "groq": 64000,
            "openai": 64000,
            "gemini": 64000,
            "anthropic": 64000,
            "deepseek": 64000,
        }.get(provider.lower(), 32000)
    
    if len(text) > max_text_length:
        logger.info(f"Text length ({len(text)}) exceeds limit for triplets. Chunking...")
        return _extract_triplets_chunked(
            text, provider=provider, model=model, 
            silent_fail=silent_fail, max_text_length=max_text_length, 
            max_retries=max_retries,
            **kwargs
        )
    
    # Use custom triplet types if provided
    triplet_types = kwargs.get("triplet_types")
    if triplet_types:
        triplet_types_str = ", ".join(triplet_types)
        triplet_types_instruction = f"""
Preferred triplet predicates: {triplet_types_str}.
You may also use related or similar predicates if they better capture the relationship (e.g., variations, synonyms, or domain-specific predicates).
If a predicate doesn't fit any of the preferred types, use the most appropriate type from the preferred list or a closely related type that accurately describes the relationship."""
    else:
        triplet_types_instruction = """
Extract meaningful triplets (subject-predicate-object). Use appropriate predicates that accurately describe the relationship.
Common predicates include: is_a, part_of, has_property, related_to, caused_by, etc."""

    if not SCHEMAS_AVAILABLE:
        raise ImportError("Pydantic schemas not available. Install pydantic/instructor to use LLM extraction.")

    prompt = f"""Extract RDF triplets (subject-predicate-object) from the provided text.
Return the result as a JSON object with a "triplets" key containing the list of triplets.
Each triplet must have 'subject', 'predicate', and 'object' fields.

Example output (JSON format only):
{{
  "triplets": [
    {{"subject": "Subject", "predicate": "predicate_relation", "object": "Object", "confidence": 0.99}},
    {{"subject": "Concept A", "predicate": "is_a", "object": "Concept B", "confidence": 0.95}}
  ]
}}

Instructions:
1. Extract triplets ONLY from the text provided below.
2. Do not include any triplets from the example above.
3. Ensure subjects and objects are substrings from the text.
4. {triplet_types_instruction}

Text to extract from:
{text}"""

    try:
        # Use typed generation with Pydantic schema
        call_kwargs = kwargs.copy()
        call_kwargs["max_retries"] = max_retries
        result_obj = llm.generate_typed(prompt, schema=TripletsResponse, **call_kwargs)
        
        # Convert back to internal Triplet format
        triplets = []
        for t_out in result_obj.triplets:
            triplets.append(Triplet(
                subject=t_out.subject,
                predicate=t_out.predicate,
                object=t_out.object,
                confidence=t_out.confidence,
                metadata={
                    "provider": provider, 
                    "model": model, 
                    "extraction_method": "llm_typed"
                }
            ))
        
        logger.info(f"Successfully extracted {len(triplets)} triplets using {provider}/{model} (typed)")
        _result_cache.set("triplets", text, triplets, **cache_params)
        return triplets
        
    except Exception as e:
        # Check for length/token limit errors
        error_msg_str = str(e).lower()
        if "length" in error_msg_str or "max_tokens" in error_msg_str:
            logger.warning(f"LLM output truncated due to length limit. Reducing chunk size and retrying... ({e})")
            
            # Determine new chunk size (halve it)
            current_max = max_text_length or len(text)
            new_max = current_max // 2
            
            if new_max > 100: # Minimum viable chunk size check
                return _extract_triplets_chunked(
                    text, provider=provider, model=model, 
                    silent_fail=silent_fail, max_text_length=new_max, 
                    **kwargs
                )

        error_msg = f"LLM triplet extraction failed ({provider}/{model}): {e}"
        logger.error(error_msg, exc_info=True)
        if not silent_fail:
            if isinstance(e, ProcessingError):
                raise
            raise ProcessingError(error_msg) from e
        return []


def _parse_triplet_result(result: Any, provider: str, model: Optional[str]) -> List[Triplet]:
    """Helper to parse raw LLM result into Triplet objects."""
    triplets = []
    items = []
    
    if isinstance(result, list):
        items = result
    elif isinstance(result, dict):
        for key in ["triplets", "data", "results"]:
            if key in result and isinstance(result[key], list):
                items = result[key]
                break
        if not items and "subject" in result:
            items = [result]

    for item in items:
        if not isinstance(item, dict):
            continue
            
        subject = item.get("subject", "")
        predicate = item.get("predicate", "")
        obj = item.get("object", "")
        
        if not subject or not predicate or not obj:
            continue
            
        triplets.append(
            Triplet(
                subject=str(subject),
                predicate=str(predicate),
                object=str(obj),
                confidence=item.get("confidence", 0.9),
                metadata={
                    "provider": provider,
                    "model": model,
                    "extraction_method": "llm",
                },
            )
        )
    return triplets


def _extract_triplets_chunked(
    text: str,
    provider: str,
    model: Optional[str],
    silent_fail: bool,
    max_text_length: int,
    structured_output_mode: str = "typed",
    **kwargs
) -> List[Triplet]:
    """Internal helper to extract triplets from long text by chunking."""
    from ..split import TextSplitter
    
    splitter = TextSplitter(
        method="recursive",
        chunk_size=max_text_length,
        chunk_overlap=int(max_text_length * 0.1)
    )
    chunks = splitter.split(text)
    
    all_triplets = []
    
    from .config import resolve_max_workers
    max_workers = resolve_max_workers(explicit=kwargs.get("max_workers"))
    
    with ThreadPoolExecutor(max_workers=max_workers) as executor:
        future_to_chunk = {}
        for i, chunk in enumerate(chunks):
            logger.debug(f"Scheduling triplet extraction for chunk {i+1}/{len(chunks)}")
            future = executor.submit(
                extract_triplets_llm,
                chunk.text,
                provider=provider,
                model=model,
                silent_fail=False,
                max_text_length=len(chunk.text) + 1,
                structured_output_mode=structured_output_mode,
                **kwargs
            )
            future_to_chunk[future] = i
        
        for future in as_completed(future_to_chunk):
            i = future_to_chunk[future]
            try:
                chunk_triplets = future.result()
                all_triplets.extend(chunk_triplets)
            except Exception as e:
                if not silent_fail:
                    logger.error(f"Chunk {i+1} failed: {e}")
                    raise
                logger.warning(f"Chunk {i+1} failed (silent): {e}")
                
    return all_triplets




# ============================================================================
# Method Dispatchers
# ============================================================================


def get_entity_method(method_name: str):
    """Get entity extraction method - checks registry for custom methods."""
    # Check registry first
    custom_method = method_registry.get("entity", method_name)
    if custom_method:
        return custom_method

    # Built-in methods
    builtin = {
        "pattern": extract_entities_pattern,
        "regex": extract_entities_regex,
        "rules": extract_entities_rules,
        "ml": extract_entities_ml,
        "spacy": extract_entities_ml,  # Alias for ml
        "huggingface": extract_entities_huggingface,
        "llm": extract_entities_llm,
    }

    method_func = builtin.get(method_name)
    if not method_func:
        raise ValueError(
            f"Unknown method: {method_name}. Register custom method or use built-in: {list(builtin.keys())}"
        )

    return method_func


def get_relation_method(method_name: str):
    """Get relation extraction method - checks registry for custom methods."""
    # Check registry first
    custom_method = method_registry.get("relation", method_name)
    if custom_method:
        return custom_method

    # Built-in methods
    builtin = {
        "pattern": extract_relations_pattern,
        "regex": extract_relations_regex,
        "cooccurrence": extract_relations_cooccurrence,
        "similarity": extract_relations_similarity,
        "dependency": extract_relations_dependency,
        "ml": extract_relations_dependency,  # Alias for dependency
        "spacy": extract_relations_dependency,  # Alias for dependency
        "huggingface": extract_relations_huggingface,
        "llm": extract_relations_llm,
    }

    method_func = builtin.get(method_name)
    if not method_func:
        raise ValueError(
            f"Unknown method: {method_name}. Register custom method or use built-in: {list(builtin.keys())}"
        )

    return method_func


def get_triplet_method(method_name: str):
    """Get triplet extraction method - checks registry for custom methods."""
    # Check registry first
    custom_method = method_registry.get("triplet", method_name)
    if custom_method:
        return custom_method

    # Built-in methods
    builtin = {
        "pattern": extract_triplets_pattern,
        "rules": extract_triplets_rules,
        "huggingface": extract_triplets_huggingface,
        "llm": extract_triplets_llm,
    }

    method_func = builtin.get(method_name)
    if not method_func:
        raise ValueError(
            f"Unknown method: {method_name}. Register custom method or use built-in: {list(builtin.keys())}"
        )

    return method_func
