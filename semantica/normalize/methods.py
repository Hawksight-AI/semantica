"""
Data Normalization Methods Module

This module provides all normalization methods as simple, reusable functions for
text normalization, entity normalization, date/time normalization, number/quantity
normalization, data cleaning, language detection, and encoding handling. It supports
multiple approaches and integrates with the method registry for extensibility.

Supported Methods:

Text Normalization:
    - "default": Default text normalization using TextNormalizer
    - "unicode": Unicode-focused normalization
    - "whitespace": Whitespace-focused normalization
    - "case": Case-focused normalization

Entity Normalization:
    - "default": Default entity normalization using EntityNormalizer
    - "alias": Alias resolution only
    - "disambiguate": Disambiguation only
    - "link": Entity linking only

Date/Time Normalization:
    - "default": Default date normalization using DateNormalizer
    - "iso": ISO8601 format normalization
    - "relative": Relative date processing
    - "timezone": Timezone-focused normalization

Number/Quantity Normalization:
    - "default": Default number normalization using NumberNormalizer
    - "quantity": Quantity normalization with units
    - "currency": Currency processing
    - "scientific": Scientific notation handling

Data Cleaning:
    - "default": Default data cleaning using DataCleaner
    - "duplicates": Duplicate detection only
    - "validation": Validation only
    - "missing": Missing value handling only

Language Detection:
    - "default": Default language detection using LanguageDetector
    - "confidence": Detection with confidence scores
    - "batch": Batch language detection

Encoding Handling:
    - "default": Default encoding handling using EncodingHandler
    - "detect": Encoding detection only
    - "convert": Encoding conversion only

Algorithms Used:

Text Normalization:
    - Unicode Normalization: NFC, NFD, NFKC, NFKD forms using unicodedata.normalize()
    - Whitespace Normalization: Multiple space to single space (re.sub), line break normalization (\\r\\n, \\r, \\n)
    - Case Normalization: str.lower(), str.upper(), str.title() conversion
    - Special Character Processing: Diacritic normalization, punctuation handling, regex-based processing
    - Text Cleaning: HTML tag removal (BeautifulSoup/regex fallback), sanitization, special character removal

Entity Normalization:
    - Alias Resolution: Dictionary-based alias mapping, fuzzy string matching, entity type-based resolution
    - Entity Disambiguation: Context-aware disambiguation, confidence scoring, candidate ranking
    - Name Variant Handling: Title/honorific handling (Dr., Mr., etc.), format standardization, regex-based pattern matching
    - Entity Linking: Canonical form mapping, batch processing, similarity-based linking

Date/Time Normalization:
    - Date Parsing: dateutil.parser.parse() with fallback to datetime.fromisoformat(), ISO format parsing
    - Timezone Normalization: UTC conversion using datetime.astimezone(), timezone-aware datetime handling
    - Relative Date Processing: Natural language parsing ("yesterday", "3 days ago"), timedelta calculation, relativedelta for complex expressions
    - Temporal Expression Parsing: Complex temporal expressions, date range parsing, pattern matching

Number/Quantity Normalization:
    - Number Parsing: Comma/space removal (str.replace), percentage handling (value / 100), scientific notation parsing (float())
    - Unit Conversion: Unit normalization dictionary lookup, conversion factor calculation, unit compatibility checking
    - Currency Processing: Symbol/code normalization (regex-based), currency code extraction, amount parsing
    - Scientific Notation: Exponential notation parsing (float()), mantissa/exponent extraction

Data Cleaning:
    - Duplicate Detection: Similarity-based detection (threshold matching), key field comparison, hash-based exact matching
    - Data Validation: Schema-based validation, type checking, required field validation, constraint checking
    - Missing Value Handling: Removal (list filtering), filling (default value assignment), imputation (mean/median/mode calculation)

Language Detection:
    - Multi-language Detection: langdetect.detect() integration, 50+ languages supported, probability-based detection
    - Confidence Scoring: langdetect.detect_langs() for probability scores, confidence threshold filtering
    - Batch Processing: Multiple text language detection, result aggregation

Encoding Handling:
    - Encoding Detection: chardet.detect() integration, confidence scoring, byte analysis
    - UTF-8 Conversion: Fallback encoding chain (latin-1, cp1252, iso-8859-1), error handling strategies (ignore, replace, strict)
    - BOM Removal: UTF-8 BOM detection (\\xef\\xbb\\xbf), UTF-16 BOM detection (\\xff\\xfe, \\xfe\\xff), byte removal

Key Features:
    - Multiple normalization operation methods
    - Normalization with method dispatch
    - Method dispatchers with registry support
    - Custom method registration capability
    - Consistent interface across all methods

Main Functions:
    - normalize_text: Text normalization wrapper
    - clean_text: Text cleaning wrapper
    - normalize_entity: Entity normalization wrapper
    - resolve_aliases: Alias resolution wrapper
    - disambiguate_entity: Entity disambiguation wrapper
    - normalize_date: Date normalization wrapper
    - normalize_time: Time normalization wrapper
    - normalize_number: Number normalization wrapper
    - normalize_quantity: Quantity normalization wrapper
    - clean_data: Data cleaning wrapper
    - detect_duplicates: Duplicate detection wrapper
    - detect_language: Language detection wrapper
    - handle_encoding: Encoding handling wrapper
    - get_normalize_method: Get normalization method by name
    - list_available_methods: List registered methods

Example Usage:
    >>> from semantica.normalize.methods import normalize_text, normalize_entity, normalize_date
    >>> text = normalize_text("Hello   World", method="default")
    >>> entity = normalize_entity("John Doe", method="default")
    >>> date = normalize_date("2023-01-15", method="default")
"""

from typing import Any, Callable, Dict, List, Optional, Tuple, Union

from ..utils.exceptions import ConfigurationError, ProcessingError
from ..utils.logging import get_logger
from ..utils.custom_methods import CUSTOM_METHOD_FELL_BACK, call_custom_method
from .config import normalize_config
from .data_cleaner import DataCleaner
from .date_normalizer import DateNormalizer
from .encoding_handler import EncodingHandler
from .entity_normalizer import EntityNormalizer
from .language_detector import LanguageDetector
from .number_normalizer import NumberNormalizer
from .registry import method_registry
from .text_cleaner import TextCleaner
from .text_normalizer import TextNormalizer

logger = get_logger("normalize_methods")


def normalize_text(text: str, method: str = "default", **kwargs) -> str:
    """
    Normalize text content (convenience function).

    This is a user-friendly wrapper that normalizes text using the specified method.

    Args:
        text: Input text to normalize
        method: Normalization method (default: "default")
            - "default": Use TextNormalizer with default settings
            - "unicode": Unicode-focused normalization
            - "whitespace": Whitespace-focused normalization
            - "case": Case-focused normalization
        **kwargs: Additional options passed to TextNormalizer
            - unicode_form: Unicode normalization form (NFC, NFD, NFKC, NFKD)
            - case: Case normalization (preserve, lower, upper, title)
            - normalize_diacritics: Whether to normalize diacritics
            - line_break_type: Line break type (unix, windows, mac)

    Returns:
        str: Normalized text

    Examples:
        >>> from semantica.normalize.methods import normalize_text
        >>> normalized = normalize_text("Hello   World", method="default")
        >>> lower = normalize_text("Hello World", method="default", case="lower")
    """
    custom_method = method_registry.get("text", method)
    if custom_method:
        fallback = kwargs.pop("fallback_on_custom_error", False)
        result = call_custom_method(
            logger, method, custom_method, text, fallback_on_custom_error=fallback, **kwargs
        )
        if result is not CUSTOM_METHOD_FELL_BACK:
            return result

    try:
        config = normalize_config.get_method_config("text")
        config.update(kwargs)

        normalizer = TextNormalizer(**config)
        return normalizer.normalize_text(text, **kwargs)

    except Exception as e:
        logger.error(f"Failed to normalize text: {e}")
        raise


def clean_text(text: str, method: str = "default", **kwargs) -> str:
    """
    Clean and sanitize text content (convenience function).

    This is a user-friendly wrapper that cleans text using the specified method.

    Args:
        text: Input text to clean
        method: Cleaning method (default: "default")
        **kwargs: Additional options passed to TextCleaner
            - remove_html: Whether to remove HTML tags
            - normalize_whitespace: Whether to normalize whitespace
            - normalize_unicode: Whether to normalize Unicode
            - remove_special_chars: Whether to remove special characters
            - unicode_form: Unicode normalization form

    Returns:
        str: Cleaned text

    Examples:
        >>> from semantica.normalize.methods import clean_text
        >>> cleaned = clean_text("<p>Hello World</p>", method="default", remove_html=True)
    """
    custom_method = method_registry.get("clean", method)
    if custom_method:
        fallback = kwargs.pop("fallback_on_custom_error", False)
        result = call_custom_method(
            logger, method, custom_method, text, fallback_on_custom_error=fallback, **kwargs
        )
        if result is not CUSTOM_METHOD_FELL_BACK:
            return result

    try:
        config = normalize_config.get_method_config("clean")
        config.update(kwargs)

        cleaner = TextCleaner(**config)
        return cleaner.clean(text, **kwargs)

    except Exception as e:
        logger.error(f"Failed to clean text: {e}")
        raise


def normalize_entity(
    entity_name: str,
    entity_type: Optional[str] = None,
    method: str = "default",
    **kwargs,
) -> str:
    """
    Normalize entity name to standard form (convenience function).

    This is a user-friendly wrapper that normalizes entity names using the specified method.

    Args:
        entity_name: Entity name to normalize
        entity_type: Optional entity type (e.g., "Person", "Organization")
        method: Normalization method (default: "default")
            - "default": Use EntityNormalizer with default settings
            - "alias": Alias resolution only
            - "disambiguate": Disambiguation only
            - "link": Entity linking only
        **kwargs: Additional options passed to EntityNormalizer
            - resolve_aliases: Whether to resolve aliases

    Returns:
        str: Normalized entity name in standard form

    Examples:
        >>> from semantica.normalize.methods import normalize_entity
        >>> normalized = normalize_entity("John Doe", entity_type="Person", method="default")
    """
    custom_method = method_registry.get("entity", method)
    if custom_method:
        fallback = kwargs.pop("fallback_on_custom_error", False)
        result = call_custom_method(
            logger, method, custom_method, entity_name, entity_type, fallback_on_custom_error=fallback, **kwargs
        )
        if result is not CUSTOM_METHOD_FELL_BACK:
            return result

    try:
        config = normalize_config.get_method_config("entity")
        config.update(kwargs)

        normalizer = EntityNormalizer(**config)
        return normalizer.normalize_entity(
            entity_name, entity_type=entity_type, **kwargs
        )

    except Exception as e:
        logger.error(f"Failed to normalize entity: {e}")
        raise


def resolve_aliases(
    entity_name: str,
    entity_type: Optional[str] = None,
    method: str = "default",
    **kwargs,
) -> Optional[str]:
    """
    Resolve entity aliases and variants (convenience function).

    This is a user-friendly wrapper that resolves aliases using the specified method.

    Args:
        entity_name: Entity name to resolve
        entity_type: Optional entity type
        method: Resolution method (default: "default")
        **kwargs: Additional options passed to EntityNormalizer

    Returns:
        Optional[str]: Resolved canonical form if found, None otherwise

    Examples:
        >>> from semantica.normalize.methods import resolve_aliases
        >>> canonical = resolve_aliases("J. Doe", entity_type="Person", method="default")
    """
    custom_method = method_registry.get("entity", method)
    if custom_method:
        fallback = kwargs.pop("fallback_on_custom_error", False)
        result = call_custom_method(
            logger, method, custom_method, entity_name, entity_type, fallback_on_custom_error=fallback, **kwargs
        )
        if result is not CUSTOM_METHOD_FELL_BACK:
            return result

    try:
        config = normalize_config.get_method_config("entity")
        config.update(kwargs)

        normalizer = EntityNormalizer(**config)
        return normalizer.resolve_aliases(
            entity_name, entity_type=entity_type, **kwargs
        )

    except Exception as e:
        logger.error(f"Failed to resolve aliases: {e}")
        raise


def disambiguate_entity(
    entity_name: str, method: str = "default", **context
) -> Dict[str, Any]:
    """
    Disambiguate entity when multiple candidates exist (convenience function).

    This is a user-friendly wrapper that disambiguates entities using the specified method.

    Args:
        entity_name: Entity name to disambiguate
        method: Disambiguation method (default: "default")
        **context: Context information (e.g., entity_type, context_text)

    Returns:
        dict: Disambiguation result containing:
            - entity_name: Original entity name
            - entity_type: Detected entity type
            - confidence: Confidence score (0.0 to 1.0)
            - candidates: List of candidate entity names

    Examples:
        >>> from semantica.normalize.methods import disambiguate_entity
        >>> result = disambiguate_entity("John Smith", entity_type="Person", method="default")
    """
    custom_method = method_registry.get("entity", method)
    if custom_method:
        fallback = context.pop("fallback_on_custom_error", False)
        result = call_custom_method(
            logger, method, custom_method, entity_name, fallback_on_custom_error=fallback, **context
        )
        if result is not CUSTOM_METHOD_FELL_BACK:
            return result

    try:
        config = normalize_config.get_method_config("entity")
        config.update(context)

        normalizer = EntityNormalizer(**config)
        return normalizer.disambiguate_entity(entity_name, **context)

    except Exception as e:
        logger.error(f"Failed to disambiguate entity: {e}")
        raise


def normalize_date(
    date_input: Any,
    format: str = "ISO8601",
    timezone: str = "UTC",
    method: str = "default",
    **kwargs,
) -> str:
    """
    Normalize date to standard format (convenience function).

    This is a user-friendly wrapper that normalizes dates using the specified method.

    Args:
        date_input: Date input (string or datetime object)
        format: Output format (default: "ISO8601")
            - "ISO8601": ISO 8601 format
            - "date": Date only
            - Custom format string (strftime format)
        timezone: Target timezone (default: "UTC")
        method: Normalization method (default: "default")
            - "default": Use DateNormalizer with default settings
            - "iso": ISO8601 format normalization
            - "relative": Relative date processing
            - "timezone": Timezone-focused normalization
        **kwargs: Additional options passed to DateNormalizer

    Returns:
        str: Normalized date string in specified format

    Examples:
        >>> from semantica.normalize.methods import normalize_date
        >>> normalized = normalize_date("2023-01-15", method="default")
        >>> relative = normalize_date("yesterday", method="relative")
    """
    custom_method = method_registry.get("date", method)
    if custom_method:
        fallback = kwargs.pop("fallback_on_custom_error", False)
        result = call_custom_method(
            logger, method, custom_method, date_input, format, timezone, fallback_on_custom_error=fallback, **kwargs
        )
        if result is not CUSTOM_METHOD_FELL_BACK:
            return result

    try:
        config = normalize_config.get_method_config("date")
        config.update(kwargs)

        normalizer = DateNormalizer(**config)
        return normalizer.normalize_date(
            date_input, format=format, timezone=timezone, **kwargs
        )

    except Exception as e:
        logger.error(f"Failed to normalize date: {e}")
        raise


def normalize_time(time_input: Any, method: str = "default", **kwargs) -> str:
    """
    Normalize time to standard format (convenience function).

    This is a user-friendly wrapper that normalizes time using the specified method.

    Args:
        time_input: Time input (string or datetime object)
        method: Normalization method (default: "default")
        **kwargs: Additional options passed to DateNormalizer

    Returns:
        str: Normalized time string in ISO format (HH:MM:SS)

    Examples:
        >>> from semantica.normalize.methods import normalize_time
        >>> normalized = normalize_time("10:30:00", method="default")
    """
    custom_method = method_registry.get("date", method)
    if custom_method:
        fallback = kwargs.pop("fallback_on_custom_error", False)
        result = call_custom_method(
            logger, method, custom_method, time_input, fallback_on_custom_error=fallback, **kwargs
        )
        if result is not CUSTOM_METHOD_FELL_BACK:
            return result

    try:
        config = normalize_config.get_method_config("date")
        config.update(kwargs)

        normalizer = DateNormalizer(**config)
        return normalizer.normalize_time(time_input, **kwargs)

    except Exception as e:
        logger.error(f"Failed to normalize time: {e}")
        raise


def normalize_number(
    number_input: Union[str, int, float], method: str = "default", **kwargs
) -> Union[int, float]:
    """
    Normalize number to standard format (convenience function).

    This is a user-friendly wrapper that normalizes numbers using the specified method.

    Args:
        number_input: Number input (string, int, or float)
        method: Normalization method (default: "default")
            - "default": Use NumberNormalizer with default settings
            - "quantity": Quantity normalization with units
            - "currency": Currency processing
            - "scientific": Scientific notation handling
        **kwargs: Additional options passed to NumberNormalizer

    Returns:
        Union[int, float]: Normalized number (int if no decimal, float otherwise)

    Examples:
        >>> from semantica.normalize.methods import normalize_number
        >>> number = normalize_number("1,234.56", method="default")
        >>> percentage = normalize_number("50%", method="default")
    """
    custom_method = method_registry.get("number", method)
    if custom_method:
        fallback = kwargs.pop("fallback_on_custom_error", False)
        result = call_custom_method(
            logger, method, custom_method, number_input, fallback_on_custom_error=fallback, **kwargs
        )
        if result is not CUSTOM_METHOD_FELL_BACK:
            return result

    try:
        config = normalize_config.get_method_config("number")
        config.update(kwargs)

        normalizer = NumberNormalizer(**config)
        return normalizer.normalize_number(number_input, **kwargs)

    except Exception as e:
        logger.error(f"Failed to normalize number: {e}")
        raise


def normalize_quantity(
    quantity_input: str, method: str = "default", **kwargs
) -> Dict[str, Any]:
    """
    Normalize quantity with units (convenience function).

    This is a user-friendly wrapper that normalizes quantities using the specified method.

    Args:
        quantity_input: Quantity string (e.g., "5 kg", "10 meters")
        method: Normalization method (default: "default")
        **kwargs: Additional options passed to NumberNormalizer

    Returns:
        dict: Normalized quantity dictionary containing:
            - value: Numeric value (float)
            - unit: Normalized unit name (str)
            - original: Original quantity string (str)

    Examples:
        >>> from semantica.normalize.methods import normalize_quantity
        >>> quantity = normalize_quantity("5 kg", method="default")
    """
    custom_method = method_registry.get("number", method)
    if custom_method:
        fallback = kwargs.pop("fallback_on_custom_error", False)
        result = call_custom_method(
            logger, method, custom_method, quantity_input, fallback_on_custom_error=fallback, **kwargs
        )
        if result is not CUSTOM_METHOD_FELL_BACK:
            return result

    try:
        config = normalize_config.get_method_config("number")
        config.update(kwargs)

        normalizer = NumberNormalizer(**config)
        return normalizer.normalize_quantity(quantity_input, **kwargs)

    except Exception as e:
        logger.error(f"Failed to normalize quantity: {e}")
        raise


def clean_data(
    dataset: List[Dict[str, Any]],
    remove_duplicates: bool = True,
    validate: bool = True,
    handle_missing: bool = True,
    method: str = "default",
    **kwargs,
) -> List[Dict[str, Any]]:
    """
    Clean dataset with various cleaning operations (convenience function).

    This is a user-friendly wrapper that cleans data using the specified method.

    Args:
        dataset: List of data record dictionaries
        remove_duplicates: Whether to remove duplicate records (default: True)
        validate: Whether to validate data against schema (default: True)
        handle_missing: Whether to handle missing values (default: True)
        method: Cleaning method (default: "default")
            - "default": Use DataCleaner with default settings
            - "duplicates": Duplicate detection only
            - "validation": Validation only
            - "missing": Missing value handling only
        **kwargs: Additional options passed to DataCleaner
            - missing_strategy: Strategy for missing values ("remove", "fill", "impute")
            - schema: Validation schema dictionary
            - duplicate_criteria: Criteria for duplicate detection

    Returns:
        list: Cleaned dataset (list of record dictionaries)

    Examples:
        >>> from semantica.normalize.methods import clean_data
        >>> cleaned = clean_data(dataset, method="default", remove_duplicates=True)
    """
    custom_method = method_registry.get("clean", method)
    if custom_method:
        fallback = kwargs.pop("fallback_on_custom_error", False)
        result = call_custom_method(
            logger, method, custom_method, dataset, remove_duplicates, validate, handle_missing, fallback_on_custom_error=fallback, **kwargs
        )
        if result is not CUSTOM_METHOD_FELL_BACK:
            return result

    try:
        config = normalize_config.get_method_config("clean")
        config.update(kwargs)

        cleaner = DataCleaner(**config)
        return cleaner.clean_data(
            dataset,
            remove_duplicates=remove_duplicates,
            validate=validate,
            handle_missing=handle_missing,
            **kwargs,
        )

    except Exception as e:
        logger.error(f"Failed to clean data: {e}")
        raise


def detect_duplicates(
    dataset: List[Dict[str, Any]],
    threshold: Optional[float] = None,
    key_fields: Optional[List[str]] = None,
    method: str = "default",
    **kwargs,
) -> List[Any]:
    """
    Detect duplicate records in dataset (convenience function).

    This is a user-friendly wrapper that detects duplicates using the specified method.

    Args:
        dataset: List of data record dictionaries
        threshold: Similarity threshold for duplicates (0.0 to 1.0, optional)
        key_fields: List of field names to use for comparison (optional)
        method: Detection method (default: "default")
        **kwargs: Additional options passed to DataCleaner

    Returns:
        list: List of DuplicateGroup objects

    Examples:
        >>> from semantica.normalize.methods import detect_duplicates
        >>> duplicates = detect_duplicates(dataset, method="default", threshold=0.8)
    """
    custom_method = method_registry.get("clean", method)
    if custom_method:
        fallback = kwargs.pop("fallback_on_custom_error", False)
        result = call_custom_method(
            logger, method, custom_method, dataset, threshold, key_fields, fallback_on_custom_error=fallback, **kwargs
        )
        if result is not CUSTOM_METHOD_FELL_BACK:
            return result

    try:
        config = normalize_config.get_method_config("clean")
        config.update(kwargs)

        cleaner = DataCleaner(**config)
        return cleaner.detect_duplicates(
            dataset, threshold=threshold, key_fields=key_fields, **kwargs
        )

    except Exception as e:
        logger.error(f"Failed to detect duplicates: {e}")
        raise


def detect_language(
    text: str, method: str = "default", **kwargs
) -> Union[str, Tuple[str, float]]:
    """
    Detect language of text (convenience function).

    This is a user-friendly wrapper that detects language using the specified method.

    Args:
        text: Input text to analyze
        method: Detection method (default: "default")
            - "default": Use LanguageDetector with default settings
            - "confidence": Detection with confidence scores
            - "batch": Batch language detection
        **kwargs: Additional options passed to LanguageDetector

    Returns:
        str or tuple: Language code, or (language_code, confidence_score) if method="confidence"

    Examples:
        >>> from semantica.normalize.methods import detect_language
        >>> language = detect_language("Hello world", method="default")
        >>> lang, conf = detect_language("Bonjour", method="confidence")
    """
    custom_method = method_registry.get("language", method)
    if custom_method:
        fallback = kwargs.pop("fallback_on_custom_error", False)
        result = call_custom_method(
            logger, method, custom_method, text, fallback_on_custom_error=fallback, **kwargs
        )
        if result is not CUSTOM_METHOD_FELL_BACK:
            return result

    try:
        config = normalize_config.get_method_config("language")
        config.update(kwargs)

        detector = LanguageDetector(**config)

        if method == "confidence":
            return detector.detect_with_confidence(text, **kwargs)
        else:
            return detector.detect(text, **kwargs)

    except Exception as e:
        logger.error(f"Failed to detect language: {e}")
        raise


def handle_encoding(
    data: Union[str, bytes],
    operation: str = "detect",
    method: str = "default",
    **kwargs,
) -> Union[Tuple[str, float], str, bytes]:
    """
    Handle encoding detection and conversion (convenience function).

    This is a user-friendly wrapper that handles encoding using the specified method.

    Args:
        data: Input data (string or bytes)
        operation: Operation to perform (default: "detect")
            - "detect": Detect encoding
            - "convert": Convert to UTF-8
            - "remove_bom": Remove BOM
        method: Handling method (default: "default")
            - "default": Use EncodingHandler with default settings
            - "detect": Encoding detection only
            - "convert": Encoding conversion only
        **kwargs: Additional options passed to EncodingHandler
            - source_encoding: Source encoding for conversion
            - target_encoding: Target encoding (default: "utf-8")

    Returns:
        tuple, str, or bytes: Result depends on operation:
            - "detect": (encoding_name, confidence_score)
            - "convert": UTF-8 string or bytes
            - "remove_bom": Data with BOM removed

    Examples:
        >>> from semantica.normalize.methods import handle_encoding
        >>> encoding, confidence = handle_encoding(data, operation="detect", method="default")
        >>> utf8_text = handle_encoding(data, operation="convert", method="default")
    """
    custom_method = method_registry.get("encoding", method)
    if custom_method:
        fallback = kwargs.pop("fallback_on_custom_error", False)
        result = call_custom_method(
            logger, method, custom_method, data, operation, fallback_on_custom_error=fallback, **kwargs
        )
        if result is not CUSTOM_METHOD_FELL_BACK:
            return result

    try:
        config = normalize_config.get_method_config("encoding")
        config.update(kwargs)

        handler = EncodingHandler(**config)

        if operation == "detect":
            return handler.detect(data, **kwargs)
        elif operation == "convert":
            source_encoding = kwargs.get("source_encoding")
            return handler.convert_to_utf8(
                data, source_encoding=source_encoding, **kwargs
            )
        elif operation == "remove_bom":
            return handler.remove_bom(data, **kwargs)
        else:
            raise ValueError(f"Unknown operation: {operation}")

    except Exception as e:
        logger.error(f"Failed to handle encoding: {e}")
        raise


def get_normalize_method(task: str, name: str) -> Optional[Callable]:
    """Get normalization method by task and name."""
    return method_registry.get(task, name)


def list_available_methods(task: Optional[str] = None) -> Dict[str, List[str]]:
    """List all registered normalization methods."""
    return method_registry.list_all(task)


# Register default methods
# Note: We do not register the convenience functions as defaults to avoid recursion.
# The convenience functions have built-in fallback to the default implementations
# (using the classes directly) when no custom method is found in the registry.

