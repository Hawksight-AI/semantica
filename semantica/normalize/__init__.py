"""
Data Normalization Module

This module provides comprehensive data normalization and cleaning capabilities
for the Semantica framework, enabling standardization and quality improvement
of various data types.

Algorithms Used:

Text Normalization:
    - Unicode Normalization: NFC, NFD, NFKC, NFKD forms using unicodedata.normalize()
    - Whitespace Normalization: Multiple space to single space (re.sub(r' +', ' ', text)), line break normalization (\\r\\n, \\r, \\n to \\n), tab replacement (\\t to space)
    - Case Normalization: str.lower(), str.upper(), str.title() conversion, case preservation
    - Special Character Processing: Diacritic normalization, punctuation handling, smart quote replacement (\\u2018, \\u2019, \\u201C, \\u201D), dash normalization (\\u2013, \\u2014), ellipsis replacement (\\u2026)
    - Text Cleaning: HTML tag removal (BeautifulSoup/regex fallback), sanitization, special character removal, regex-based pattern matching

Entity Normalization:
    - Alias Resolution: Dictionary-based alias mapping (lowercase key lookup), fuzzy string matching, entity type-based resolution, variant mapping
    - Entity Disambiguation: Context-aware disambiguation, confidence scoring (0.0 to 1.0), candidate ranking, entity type classification (heuristic-based: Person, Organization, Entity)
    - Name Variant Handling: Title/honorific handling (Dr., Mr., etc.), format standardization, regex-based pattern matching, cultural variation handling
    - Entity Linking: Canonical form mapping, batch processing, similarity-based linking, name format normalization (title case for Person entities)

Date/Time Normalization:
    - Date Parsing: dateutil.parser.parse() with fallback to datetime.fromisoformat(), ISO format parsing, multiple format support
    - Timezone Normalization: UTC conversion using datetime.astimezone(), timezone-aware datetime handling, ZoneInfo integration (Python 3.9+), DST transition handling
    - Relative Date Processing: Natural language parsing ("yesterday", "3 days ago", "2 weeks from now"), timedelta calculation, relativedelta for complex expressions, reference date-based calculation
    - Temporal Expression Parsing: Complex temporal expressions, date range parsing ("from X to Y"), pattern matching, relative/absolute date detection

Number/Quantity Normalization:
    - Number Parsing: Comma/space removal (str.replace(',', '').replace(' ', '')), percentage handling (value / 100), scientific notation parsing (float()), decimal point detection
    - Unit Conversion: Unit normalization dictionary lookup, conversion factor calculation (base unit conversion), unit compatibility checking (category validation: length, weight, volume), conversion formula: base_value = value * from_factor, converted_value = base_value / to_factor
    - Currency Processing: Symbol/code normalization (regex-based: $, €, £), currency code extraction (USD, EUR, GBP), amount parsing, default currency assignment
    - Scientific Notation: Exponential notation parsing (float()), mantissa/exponent extraction, 'e'/'E' detection

Data Cleaning:
    - Duplicate Detection: Similarity-based detection (threshold matching), key field comparison, hash-based exact matching, pairwise comparison algorithm, duplicate group formation, average similarity calculation
    - Data Validation: Schema-based validation, type checking (isinstance()), required field validation, constraint checking, error/warning collection
    - Missing Value Handling: Removal (list filtering: [r for r in dataset if all(v is not None for v in r.values())]), filling (default value assignment), imputation (mean/median/mode calculation), strategy-based processing

Language Detection:
    - Multi-language Detection: langdetect.detect() integration, 50+ languages supported, probability-based detection, text length validation
    - Confidence Scoring: langdetect.detect_langs() for probability scores, confidence threshold filtering, top N language detection
    - Batch Processing: Multiple text language detection, result aggregation, language code to name mapping

Encoding Handling:
    - Encoding Detection: chardet.detect() integration, confidence scoring, byte analysis, string-to-bytes conversion for detection
    - UTF-8 Conversion: Fallback encoding chain (latin-1, cp1252, iso-8859-1), error handling strategies (ignore, replace, strict), decode/encode chain: decode(source) -> encode(utf-8) -> decode(utf-8)
    - BOM Removal: UTF-8 BOM detection (\\xef\\xbb\\xbf), UTF-16 BOM detection (\\xff\\xfe, \\xfe\\xff), byte removal, file-based BOM handling

Key Features:
    - Text normalization and cleaning (Unicode, whitespace, special characters)
    - Entity name normalization (aliases, variants, disambiguation)
    - Date and time normalization (formats, timezones, relative dates)
    - Number and quantity normalization (formats, units, currency, scientific notation)
    - Data cleaning (duplicates, validation, missing values)
    - Language detection (multi-language support)
    - Encoding handling (detection, conversion, BOM removal)
    - Method registry for extensibility
    - Configuration management with environment variables and config files

Main Classes:
    - TextNormalizer: Text cleaning and normalization coordinator
    - UnicodeNormalizer: Unicode processing engine
    - WhitespaceNormalizer: Whitespace handling engine
    - SpecialCharacterProcessor: Special character processing engine
    - EntityNormalizer: Entity name normalization coordinator
    - AliasResolver: Entity alias resolution engine
    - EntityDisambiguator: Entity disambiguation engine
    - NameVariantHandler: Name variant processing engine
    - DateNormalizer: Date and time normalization coordinator
    - TimeZoneNormalizer: Time zone processing engine
    - RelativeDateProcessor: Relative date handling engine
    - TemporalExpressionParser: Temporal expression parser
    - NumberNormalizer: Number and quantity normalization coordinator
    - UnitConverter: Unit conversion engine
    - CurrencyNormalizer: Currency processing engine
    - ScientificNotationHandler: Scientific notation processor
    - DataCleaner: General data cleaning utilities coordinator
    - DuplicateDetector: Duplicate detection engine
    - DataValidator: Data validation engine
    - MissingValueHandler: Missing value handling engine
    - TextCleaner: Text cleaning utilities
    - LanguageDetector: Language detection coordinator
    - EncodingHandler: Encoding detection and conversion coordinator
    - MethodRegistry: Registry for custom normalization methods
    - NormalizeConfig: Configuration manager for normalize module

Convenience Functions:
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
    >>> from semantica.normalize import normalize_text, normalize_entity, normalize_date, TextNormalizer
    >>> # Using convenience functions
    >>> text = normalize_text("Hello   World", method="default")
    >>> entity = normalize_entity("John Doe", entity_type="Person", method="default")
    >>> date = normalize_date("2023-01-15", method="default")
    >>> # Using classes directly
    >>> from semantica.normalize import TextNormalizer, EntityNormalizer
    >>> text_norm = TextNormalizer()
    >>> normalized = text_norm.normalize_text("Hello   World")
    >>> entity_norm = EntityNormalizer()
    >>> canonical = entity_norm.normalize_entity("John Doe")

Author: Semantica Contributors
License: MIT
"""

from typing import Any, Dict, List, Optional, Tuple, Union

from .config import NormalizeConfig, normalize_config
from .data_cleaner import (
    DataCleaner,
    DataValidator,
    DuplicateDetector,
    DuplicateGroup,
    MissingValueHandler,
    ValidationResult,
)
from .date_normalizer import (
    DateNormalizer,
    RelativeDateProcessor,
    TemporalExpressionParser,
    TimeZoneNormalizer,
)
from .encoding_handler import EncodingHandler
from .entity_normalizer import (
    AliasResolver,
    EntityDisambiguator,
    EntityNormalizer,
    NameVariantHandler,
)
from .language_detector import UNKNOWN_LANGUAGE, LanguageDetector
from .methods import (
    clean_data,
    clean_text,
    detect_duplicates,
    detect_language,
    disambiguate_entity,
    get_normalize_method,
    handle_encoding,
    list_available_methods,
    normalize_date,
    normalize_entity,
    normalize_number,
    normalize_quantity,
    normalize_text,
    normalize_time,
    resolve_aliases,
)
from .number_normalizer import (
    CurrencyNormalizer,
    NumberNormalizer,
    ScientificNotationHandler,
    UnitConverter,
)
from .registry import MethodRegistry, method_registry
from .text_cleaner import TextCleaner
from .text_normalizer import (
    SpecialCharacterProcessor,
    TextNormalizer,
    UnicodeNormalizer,
    WhitespaceNormalizer,
)

__all__ = [
    # Text normalization
    "TextNormalizer",
    "UnicodeNormalizer",
    "WhitespaceNormalizer",
    "SpecialCharacterProcessor",
    # Entity normalization
    "EntityNormalizer",
    "AliasResolver",
    "EntityDisambiguator",
    "NameVariantHandler",
    # Date/time normalization
    "DateNormalizer",
    "TimeZoneNormalizer",
    "RelativeDateProcessor",
    "TemporalExpressionParser",
    # Number/quantity normalization
    "NumberNormalizer",
    "UnitConverter",
    "CurrencyNormalizer",
    "ScientificNotationHandler",
    # Data cleaning
    "DataCleaner",
    "DuplicateDetector",
    "DataValidator",
    "MissingValueHandler",
    "DuplicateGroup",
    "ValidationResult",
    # Text cleaning
    "TextCleaner",
    # Language detection
    "LanguageDetector",
    "UNKNOWN_LANGUAGE",
    # Encoding handling
    "EncodingHandler",
    # Registry and Methods
    "MethodRegistry",
    "method_registry",
    "normalize_text",
    "clean_text",
    "normalize_entity",
    "resolve_aliases",
    "disambiguate_entity",
    "normalize_date",
    "normalize_time",
    "normalize_number",
    "normalize_quantity",
    "clean_data",
    "detect_duplicates",
    "detect_language",
    "handle_encoding",
    "get_normalize_method",
    "list_available_methods",
    # Configuration
    "NormalizeConfig",
    "normalize_config",
]
