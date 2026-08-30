"""
Language Detection Module

This module provides comprehensive language detection capabilities for the
Semantica framework, enabling identification of text language using the
langdetect library.

Key Features:
    - Multi-language detection (50+ languages)
    - Confidence scoring
    - Batch processing
    - Top N language detection
    - Language code to name mapping

Main Classes:
    - LanguageDetector: Language detection coordinator

Example Usage:
    >>> from semantica.normalize import LanguageDetector
    >>> detector = LanguageDetector()
    >>> language = detector.detect("Hello world")
    >>> lang, confidence = detector.detect_with_confidence("Bonjour le monde")
    >>> languages = detector.detect_multiple(text, top_n=3)

Author: Semantica Contributors
License: MIT
"""

from typing import Any, Dict, List, Optional, Tuple, Union

try:
    from langdetect import detect_langs
    from langdetect.lang_detect_exception import LangDetectException

    LANGDETECT_AVAILABLE = True
except (ImportError, OSError):
    LANGDETECT_AVAILABLE = False
    LangDetectException = Exception

from ..utils.exceptions import ProcessingError
from ..utils.logging import get_logger
from ..utils.progress_tracker import get_progress_tracker

# Returned when no detection was performed (text too short, langdetect
# unavailable) or detection failed. Distinct from every ISO language code,
# so callers can never mistake a fallback for a detected language.
#
# Design note: unlike entity confidence (see semantic_extract.types, where
# missing measurements are represented as None), the unknown language is an
# out-of-band *string* rather than None. Language codes flow into dict keys,
# file names and other string operations throughout the pipeline, so None
# would trade one ambiguity for a crash surface; "unknown" stays inside the
# str domain while remaining impossible to confuse with a real code. For
# confidence there is no out-of-band float — every number is a plausible
# score — hence None is the only honest representation there.
UNKNOWN_LANGUAGE = "unknown"

DEFAULT_MIN_TEXT_LENGTH = 10

# Per-call options accepted by the detection APIs. Anything else is almost
# certainly a typo (e.g. min_text_len) and is reported instead of being
# silently ignored.
KNOWN_DETECTION_OPTIONS = frozenset({"min_text_length"})


class LanguageDetector:
    """
    Language detection coordinator.

    This class provides language detection capabilities using the langdetect
    library, supporting detection with confidence scores and batch processing.

    Features:
        - Multi-language detection (50+ languages)
        - Confidence scoring
        - Batch processing
        - Top N language detection
        - Language code to name mapping

    Example Usage:
        >>> detector = LanguageDetector()
        >>> language = detector.detect("Hello world")
        >>> lang, confidence = detector.detect_with_confidence("Bonjour")
        >>> is_english = detector.is_language(text, "en")
    """

    def __init__(self, **config):
        """
        Initialize language detector.

        Sets up the detector with default language and minimum confidence threshold.

        Args:
            **config: Configuration options:
                - default_language: Language code returned when no detection
                  was performed or detection failed (default:
                  ``UNKNOWN_LANGUAGE``, i.e. ``"unknown"``). Set to a language
                  code such as ``"en"`` to assume that language instead.
                - min_confidence: Minimum confidence threshold (default: 0.5)
                - min_text_length: Minimum stripped-text length required to run
                  detection (default: 10). Inputs shorter than this return the
                  fallback (``default_language``) instead of a detected
                  language. Lower this for language mixes where short inputs
                  carry enough signal (e.g. CJK text).
        """
        self.logger = get_logger("language_detector")
        self.config = config
        self.default_language = config.get("default_language", UNKNOWN_LANGUAGE)
        self.min_confidence = config.get("min_confidence", 0.5)
        self.min_text_length = self._normalize_min_text_length(
            config.get("min_text_length", DEFAULT_MIN_TEXT_LENGTH),
            DEFAULT_MIN_TEXT_LENGTH,
        )
        self._warned_options: set = set()

        if not LANGDETECT_AVAILABLE:
            self.logger.warning(
                "langdetect library not available, language detection will be limited"
            )

        # Initialize progress tracker
        self.progress_tracker = get_progress_tracker()
        # Ensure progress tracker is enabled
        if not self.progress_tracker.enabled:
            self.progress_tracker.enabled = True

        self.logger.debug(
            f"Language detector initialized (default={self.default_language})"
        )

    def _normalize_min_text_length(self, value: Any, fallback: int) -> int:
        """Coerce a min_text_length value to a non-negative int.

        Invalid values (None, non-numeric strings, ...) must degrade to the
        fallback instead of raising during the length comparison, where no
        detection exception handler protects the caller.
        """
        try:
            return max(0, int(value))
        except (TypeError, ValueError):
            self.logger.warning(
                f"Invalid min_text_length {value!r}, using {fallback}"
            )
            return fallback

    def _resolve_min_text_length(self, options: Dict[str, Any]) -> int:
        """Resolve the minimum text length, allowing per-call override."""
        if "min_text_length" not in options:
            return self.min_text_length
        return self._normalize_min_text_length(
            options["min_text_length"], self.min_text_length
        )

    def _cannot_detect(self, text: str, options: Dict[str, Any]) -> bool:
        """True when detection cannot run for this input.

        Detection is skipped when the stripped text is shorter than
        ``min_text_length`` or when the langdetect library is unavailable;
        callers must return the ``default_language`` fallback in that case.
        """
        if not text or len(text.strip()) < self._resolve_min_text_length(options):
            return True
        return not LANGDETECT_AVAILABLE

    def _warn_unknown_options(self, options: Dict[str, Any]) -> None:
        """Report option names that no detection API understands.

        **options would otherwise swallow typos silently (e.g. min_text_len),
        making the caller believe an override took effect when nothing
        happened. Warns once per unknown name per detector instance so batch
        calls do not flood the log.
        """
        unknown = set(options) - KNOWN_DETECTION_OPTIONS - self._warned_options
        if unknown:
            self._warned_options |= unknown
            self.logger.warning(
                f"Ignoring unknown detection option(s) {sorted(unknown)}; "
                f"supported options: {sorted(KNOWN_DETECTION_OPTIONS)}"
            )

    def detect(self, text: str, **options) -> str:
        """
        Detect language of text.

        Returns the most likely language code regardless of confidence; use
        detect_with_confidence() to apply the min_confidence threshold.

        Args:
            text: Input text to analyze
            **options: Detection options:
                - min_text_length: Override the instance-level minimum text
                  length for this call

        Returns:
            str: Detected language code (e.g., "en", "fr", "de")

        Note:
            Inputs whose stripped length is below ``min_text_length``
            (default: 10) never reach the underlying detector; the configured
            ``default_language`` (``"unknown"`` unless overridden) is returned
            as a fallback. The same fallback is returned if detection fails.
        """
        return self.detect_multiple(text, top_n=1, **options)[0][0]

    def detect_with_confidence(self, text: str, **options) -> Tuple[str, float]:
        """
        Detect language with confidence score.

        This method detects the language of text and returns both the language
        code and confidence score. Only returns detected language if confidence
        meets the minimum threshold; otherwise the configured
        ``default_language`` is returned with the observed confidence.

        Args:
            text: Input text to analyze
            **options: Detection options:
                - min_text_length: Override the instance-level minimum text
                  length for this call

        Returns:
            tuple: (language_code, confidence_score) where:
                - language_code: Detected language code
                - confidence_score: Confidence score between 0.0 and 1.0

        Note:
            Inputs whose stripped length is below ``min_text_length`` return
            ``(default_language, 0.0)`` as a fallback; the 0.0 confidence
            signals that no detection was performed.
        """
        language, confidence = self.detect_multiple(text, top_n=1, **options)[0]
        if confidence >= self.min_confidence:
            return (language, confidence)
        return (self.default_language, confidence)

    def detect_multiple(
        self, text: str, top_n: int = 3, **options
    ) -> List[Tuple[str, float]]:
        """
        Detect top N languages with confidence scores.

        This is the single detection core: detect() and
        detect_with_confidence() delegate here, so guard, fallback and
        error-handling semantics live in exactly one place.

        Args:
            text: Input text to analyze
            top_n: Number of top languages to return (default: 3)
            **options: Detection options:
                - min_text_length: Override the instance-level minimum text
                  length for this call

        Returns:
            list: List of (language_code, confidence_score) tuples, sorted by
                  confidence (highest first)

        Note:
            Inputs whose stripped length is below ``min_text_length`` return
            ``[(default_language, 0.0)]`` as a fallback; the 0.0 confidence
            signals that no detection was performed.
        """
        self._warn_unknown_options(options)

        if self._cannot_detect(text, options):
            return [(self.default_language, 0.0)]

        try:
            languages = detect_langs(text)
            if languages:
                return [(lang.lang, lang.prob) for lang in languages[:top_n]]
            else:
                return [(self.default_language, 0.0)]
        except LangDetectException:
            self.logger.warning(
                f"Failed to detect languages, using default: {self.default_language}"
            )
            return [(self.default_language, 0.0)]
        except Exception as e:
            self.logger.error(f"Language detection error: {e}")
            return [(self.default_language, 0.0)]

    def detect_batch(self, texts: List[str], **options) -> List[str]:
        """
        Detect languages for multiple texts in batch.

        This method processes multiple texts in batch, detecting the language
        for each text.

        Args:
            texts: List of texts to analyze
            **options: Detection options (passed to detect method)

        Returns:
            list: List of detected language codes (one per input text)
        """
        return [self.detect(text, **options) for text in texts]

    def detect_batch_with_confidence(
        self, texts: List[str], **options
    ) -> List[Tuple[str, float]]:
        """
        Detect languages with confidence for multiple texts.

        This method processes multiple texts in batch, detecting the language
        and confidence score for each text.

        Args:
            texts: List of texts to analyze
            **options: Detection options (passed to detect_with_confidence method)

        Returns:
            list: List of (language_code, confidence_score) tuples (one per input text)
        """
        return [self.detect_with_confidence(text, **options) for text in texts]

    def is_language(
        self,
        text: str,
        target_language: str,
        min_confidence: Optional[float] = None,
        **options,
    ) -> bool:
        """
        Check if text is in target language.

        This method checks whether the detected language matches the target
        language and meets the minimum confidence threshold.

        Args:
            text: Input text to check
            target_language: Target language code (e.g., "en", "fr")
            min_confidence: Minimum confidence threshold (optional, uses
                          instance min_confidence if not provided)
            **options: Detection options (unused)

        Returns:
            bool: True if text is in target language with sufficient confidence,
                 False otherwise
        """
        detected, confidence = self.detect_with_confidence(text, **options)
        threshold = (
            min_confidence if min_confidence is not None else self.min_confidence
        )
        return detected == target_language and confidence >= threshold

    def get_language_name(self, language_code: str) -> str:
        """
        Get language name from code.

        This method converts a language code to its human-readable name.

        Args:
            language_code: Language code (e.g., "en", "fr", "de")

        Returns:
            str: Language name (e.g., "English", "French", "German").
                 Returns uppercase code if name not found.
        """
        language_names = {
            UNKNOWN_LANGUAGE: "Unknown",
            "en": "English",
            "fr": "French",
            "de": "German",
            "es": "Spanish",
            "it": "Italian",
            "pt": "Portuguese",
            "ru": "Russian",
            "zh": "Chinese",
            "ja": "Japanese",
            "ko": "Korean",
            "ar": "Arabic",
            "hi": "Hindi",
            "nl": "Dutch",
            "sv": "Swedish",
            "da": "Danish",
            "no": "Norwegian",
            "fi": "Finnish",
            "pl": "Polish",
            "tr": "Turkish",
            "cs": "Czech",
            "hu": "Hungarian",
            "ro": "Romanian",
            "th": "Thai",
            "vi": "Vietnamese",
        }
        return language_names.get(language_code, language_code.upper())
