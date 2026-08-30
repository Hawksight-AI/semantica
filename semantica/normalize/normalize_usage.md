# Normalize Module Usage Guide

Use the normalize module to clean, standardize, and prepare text and data for downstream processing. This guide only references classes and functions implemented in the module.

## Contents

1. [Quick Start](#quick-start)
2. [Text](#text)
3. [Entities](#entities)
4. [Dates & Time](#dates--time)
5. [Numbers & Quantities](#numbers--quantities)
6. [Data Cleaning](#data-cleaning)
7. [Language](#language)
8. [Encoding](#encoding)
9. [Methods Registry](#methods-registry)
10. [Configuration](#configuration)
11. [Workflows](#workflows)

## Quick Start

### Main Classes

```python
from semantica.normalize import TextNormalizer, EntityNormalizer, DateNormalizer

# Create normalizers
text_norm = TextNormalizer()
entity_norm = EntityNormalizer()
date_norm = DateNormalizer()

# Normalize text
normalized_text = text_norm.normalize_text("Hello   World", case="lower")

# Normalize entity
normalized_entity = entity_norm.normalize_entity("John Doe", entity_type="Person")

# Normalize date
normalized_date = date_norm.normalize_date("2023-01-15", format="ISO8601")
```

## Text

### Normalize Text

```python
from semantica.normalize import TextNormalizer

normalizer = TextNormalizer()
normalized = normalizer.normalize_text("Hello   World", case="lower")
```

### Unicode

```python
from semantica.normalize import UnicodeNormalizer

unicode_norm = UnicodeNormalizer()
normalized = unicode_norm.normalize_unicode("café", form="NFC")
```

### Whitespace

```python
from semantica.normalize import WhitespaceNormalizer

whitespace_norm = WhitespaceNormalizer()
normalized = whitespace_norm.normalize_whitespace(
    "Hello   World\n\nTest",
    line_break_type="unix"
)
```

### Case

```python
from semantica.normalize import TextNormalizer

normalizer = TextNormalizer()

# Lowercase
lower = normalizer.normalize_text("Hello World", case="lower")

# Uppercase
upper = normalizer.normalize_text("Hello World", case="upper")

# Title case
title = normalizer.normalize_text("hello world", case="title")

# Preserve case
preserved = normalizer.normalize_text("Hello World", case="preserve")
```

### Special Characters

```python
from semantica.normalize import SpecialCharacterProcessor

char_processor = SpecialCharacterProcessor()
processed = char_processor.process_special_chars("Hello—World")
```

### Cleaning

```python
from semantica.normalize import TextCleaner

cleaner = TextCleaner()
cleaned = cleaner.clean(
    "<p>Hello World</p>",
    remove_html=True,
    normalize_unicode=True
)
```

### Batch

```python
from semantica.normalize import TextNormalizer

normalizer = TextNormalizer()

texts = [
    "Hello   World",
    "Test   Text",
    "Another   Example"
]

# Process batch
normalized_texts = normalizer.process_batch(texts, case="lower")
for text in normalized_texts:
    print(text)
```

## Entities

### Normalize Entity

```python
from semantica.normalize import EntityNormalizer

normalizer = EntityNormalizer()
normalized = normalizer.normalize_entity("John Doe", entity_type="Person")
```

### Aliases

```python
from semantica.normalize import AliasResolver

resolver = AliasResolver(alias_map={"j. doe": "John Doe"})
canonical = resolver.resolve_aliases("J. Doe", entity_type="Person")
```

### Disambiguation

```python
from semantica.normalize import EntityDisambiguator

disambiguator = EntityDisambiguator()
result = disambiguator.disambiguate("Apple", entity_type="Organization")
```

### Linking

```python
from semantica.normalize import EntityNormalizer

normalizer = EntityNormalizer()

entities = [
    "John Doe",
    "J. Doe",
    "Johnny Doe"
]

# Link entities to canonical forms
linked = normalizer.link_entities(entities, entity_type="Person")
for original, canonical in linked.items():
    print(f"{original} -> {canonical}")
```

### Name Variants

```python
from semantica.normalize import EntityNormalizer, NameVariantHandler

normalizer = EntityNormalizer()

# Normalize with variant handling
normalized = normalizer.normalize_entity(
    "Dr. John Doe",
    entity_type="Person"
)

# Using NameVariantHandler directly
variant_handler = NameVariantHandler()
normalized = variant_handler.normalize_name_format(
    "Dr. John Doe",
    format_type="standard"
)
```

## Dates & Time

### Normalize Date

```python
from semantica.normalize import DateNormalizer

normalizer = DateNormalizer()
normalized = normalizer.normalize_date("2023-01-15", format="ISO8601")
```

### Formats

```python
from semantica.normalize import DateNormalizer

normalizer = DateNormalizer()
iso_date = normalizer.normalize_date("2023-01-15", format="ISO8601")
date_only = normalizer.normalize_date("2023-01-15", format="date")
custom = normalizer.normalize_date("2023-01-15", format="%Y-%m-%d")
```

### Timezone

```python
from semantica.normalize import TimeZoneNormalizer

tz_norm = TimeZoneNormalizer()
from datetime import datetime
dt = datetime(2023, 1, 15, 10, 30, 0)
utc_dt = tz_norm.convert_to_utc(dt)
```

### Relative Dates

```python
from semantica.normalize import RelativeDateProcessor

relative_processor = RelativeDateProcessor()
dt = relative_processor.process_relative_expression("3 days ago")
```

### Time

```python
from semantica.normalize import DateNormalizer

normalizer = DateNormalizer()
normalized = normalizer.normalize_time("10:30 AM")
```

### Temporal Expressions

```python
from semantica.normalize import DateNormalizer, TemporalExpressionParser

normalizer = DateNormalizer()

# Parse temporal expressions
result = normalizer.parse_temporal_expression("from January to March")
print(f"Date range: {result.get('range')}")

# Using TemporalExpressionParser directly
parser = TemporalExpressionParser()
result = parser.parse_temporal_expression("last week")
```

## Numbers & Quantities

### Normalize Number

```python
from semantica.normalize import NumberNormalizer

normalizer = NumberNormalizer()
number = normalizer.normalize_number("1,234.56")
```

### Percentages

```python
from semantica.normalize import NumberNormalizer

normalizer = NumberNormalizer()
percentage = normalizer.normalize_number("50%")
print(f"Percentage as decimal: {percentage}")  # 0.5
```

### Scientific Notation

```python
from semantica.normalize import ScientificNotationHandler

sci_handler = ScientificNotationHandler()
parsed = sci_handler.parse_scientific_notation("1.5e3")
```

### Quantities

```python
from semantica.normalize import NumberNormalizer

normalizer = NumberNormalizer()
quantity = normalizer.normalize_quantity("10 meters")
print(f"Value: {quantity['value']}, Unit: {quantity['unit']}")
```

### Unit Conversion

```python
from semantica.normalize import NumberNormalizer, UnitConverter

normalizer = NumberNormalizer()

# Convert units
converted = normalizer.convert_units(100, "kg", "pound")
print(f"100 kg = {converted} pounds")

# Using UnitConverter directly
converter = UnitConverter()
converted = converter.convert_units(1, "kilometer", "mile")
```

### Currency

```python
from semantica.normalize import NumberNormalizer, CurrencyNormalizer

normalizer = NumberNormalizer()

# Process currency
currency = normalizer.process_currency("$100", default_currency="USD")
print(f"Amount: {currency['amount']}, Currency: {currency['currency']}")

# Using CurrencyNormalizer directly
currency_norm = CurrencyNormalizer()
currency = currency_norm.normalize_currency("€50", default_currency="EUR")
```

## Data Cleaning

### Clean Data

```python
from semantica.normalize import DataCleaner

dataset = [
    {"id": 1, "name": "Alice", "age": 30},
    {"id": 2, "name": "Bob", "age": None},
    {"id": 1, "name": "Alice", "age": 30},  # Duplicate
]

cleaner = DataCleaner()
cleaned = cleaner.clean_data(
    dataset,
    remove_duplicates=True,
    handle_missing=True
)
```

### Duplicates

```python
from semantica.normalize import DuplicateDetector

dataset = [
    {"id": 1, "name": "Alice"},
    {"id": 2, "name": "Bob"},
    {"id": 1, "name": "Alice"},  # Duplicate
]

detector = DuplicateDetector(similarity_threshold=0.8)
duplicates = detector.detect_duplicates(dataset, key_fields=["id", "name"]) 
for group in duplicates:
    print(f"Duplicate group: {len(group.records)} records")
    print(f"Similarity: {group.similarity_score}")
```

### Validation

```python
from semantica.normalize import DataCleaner, DataValidator

schema = {
    "fields": {
        "id": {"type": int, "required": True},
        "name": {"type": str, "required": True},
        "age": {"type": int, "required": False}
    }
}

dataset = [
    {"id": 1, "name": "Alice", "age": 30},
    {"id": 2, "name": "Bob"},  # Missing age (optional)
    {"id": None, "name": "Charlie"},  # Missing required id
]

# Validate data
cleaner = DataCleaner()
validation = cleaner.validate_data(dataset, schema)

if not validation.valid:
    print(f"Validation errors: {len(validation.errors)}")
    for error in validation.errors:
        print(f"  {error}")

# Using DataValidator directly
validator = DataValidator()
validation = validator.validate_dataset(dataset, schema)
```

### Missing Values

```python
from semantica.normalize import DataCleaner, MissingValueHandler

dataset = [
    {"id": 1, "name": "Alice", "age": 30},
    {"id": 2, "name": "Bob", "age": None},
    {"id": 3, "name": None, "age": 25},
]

# Handle missing values with different strategies
cleaner = DataCleaner()

# Remove records with missing values
cleaned_remove = cleaner.handle_missing_values(dataset, strategy="remove")

# Fill missing values
cleaned_fill = cleaner.handle_missing_values(
    dataset,
    strategy="fill",
    fill_value="Unknown"
)

# Impute missing values
cleaned_impute = cleaner.handle_missing_values(
    dataset,
    strategy="impute",
    method="mean"
)

# Using MissingValueHandler directly
handler = MissingValueHandler()
cleaned = handler.handle_missing_values(dataset, strategy="remove")
```

## Language

### Detect

```python
from semantica.normalize import LanguageDetector

detector = LanguageDetector()
language = detector.detect("Bonjour le monde")
```

Inputs whose stripped length is below `min_text_length` (default: 10) are not
detected; the configured `default_language` is returned as a fallback (with a
`0.0` confidence in the confidence-returning APIs). Lower the threshold for
language mixes where short inputs carry enough signal, e.g. CJK text:

```python
from semantica.normalize import LanguageDetector

detector = LanguageDetector(min_text_length=5)
language = detector.detect("你好，这是中文文本")  # zh-cn

# Or override per call
detector = LanguageDetector()
language = detector.detect("你好，这是中文文本", min_text_length=5)
```

### Confidence

```python
from semantica.normalize import LanguageDetector

detector = LanguageDetector()
lang, confidence = detector.detect_with_confidence("Bonjour le monde")
print(f"Language: {lang}, Confidence: {confidence:.2f}")
```

### Top-N

```python
from semantica.normalize import LanguageDetector

detector = LanguageDetector()

# Detect top N languages
languages = detector.detect_multiple(
    "Hello world. Bonjour le monde.",
    top_n=3
)

for lang, conf in languages:
    print(f"{lang}: {conf:.2f}")
```

### Validation

```python
from semantica.normalize import LanguageDetector

detector = LanguageDetector()

# Check if text is in specific language
is_english = detector.is_language("Hello world", "en")
is_french = detector.is_language("Bonjour", "fr")

print(f"Is English: {is_english}")
print(f"Is French: {is_french}")
```

## Encoding

### Detect

```python
from semantica.normalize import EncodingHandler

handler = EncodingHandler()
encoding, confidence = handler.detect(data)
print(f"Encoding: {encoding}, Confidence: {confidence:.2f}")
```

### Convert to UTF-8

```python
from semantica.normalize import EncodingHandler

handler = EncodingHandler()
utf8_text = handler.convert_to_utf8(data, source_encoding="latin-1")
```

### BOM Removal

```python
from semantica.normalize import EncodingHandler

handler = EncodingHandler()
cleaned = handler.remove_bom(data)
```

### File Encoding

```python
from semantica.normalize import EncodingHandler

handler = EncodingHandler()

# Convert file to UTF-8
handler.convert_file_to_utf8("input.txt", "output.txt")

# Detect file encoding
encoding, confidence = handler.detect_file("input.txt")
print(f"File encoding: {encoding}")
```

## Methods Registry

### List & Get

```python
from semantica.normalize.methods import get_normalize_method, list_available_methods

# List all available methods
all_methods = list_available_methods()
print("Available methods:", all_methods)

# List methods for specific task
text_methods = list_available_methods("text")
print("Text normalization methods:", text_methods)

# Get specific method
normalize_method = get_normalize_method("text", "default")
if normalize_method:
    result = normalize_method("Hello   World")
```

### Examples


## Register Custom Methods

### Register

```python
from semantica.normalize.registry import method_registry

# Custom text normalization method
def custom_text_normalization(text, **kwargs):
    """Custom normalization logic."""
    # Your custom normalization code
    return text.upper().strip()

# Register custom method
method_registry.register("text", "custom_upper", custom_text_normalization)

# Use custom method
from semantica.normalize.methods import get_normalize_method
custom_method = get_normalize_method("text", "custom_upper")
result = custom_method("hello world")
```

### List

```python
from semantica.normalize.registry import method_registry

# List all registered methods
all_methods = method_registry.list_all()
print("Registered methods:", all_methods)

# List methods for specific task
text_methods = method_registry.list_all("text")
print("Text methods:", text_methods)

entity_methods = method_registry.list_all("entity")
print("Entity methods:", entity_methods)
```

### Unregister

```python
from semantica.normalize.registry import method_registry

# Unregister a method
method_registry.unregister("text", "custom_upper")

# Clear all methods for a task
method_registry.clear("text")

# Clear all methods
method_registry.clear()
```

## Configuration

### Config Manager

```python
from semantica.normalize.config import normalize_config

# Get configuration values
unicode_form = normalize_config.get("unicode_form", default="NFC")
case = normalize_config.get("case", default="preserve")
date_format = normalize_config.get("date_format", default="ISO8601")
timezone = normalize_config.get("timezone", default="UTC")

# Set configuration values
normalize_config.set("unicode_form", "NFKC")
normalize_config.set("case", "lower")

# Method-specific configuration
normalize_config.set_method_config("text", unicode_form="NFC", case="lower")
text_config = normalize_config.get_method_config("text")

# Get all configuration
all_config = normalize_config.get_all()
print("All config:", all_config)
```

### Environment Variables

```bash
# Set environment variables
export NORMALIZE_UNICODE_FORM=NFC
export NORMALIZE_CASE=lower
export NORMALIZE_DATE_FORMAT=ISO8601
export NORMALIZE_TIMEZONE=UTC
export NORMALIZE_DEFAULT_LANGUAGE=en
export NORMALIZE_DEFAULT_ENCODING=utf-8
```

### Config File

```yaml
# config.yaml
normalize:
  unicode_form: NFC
  case: lower
  date_format: ISO8601
  timezone: UTC
  default_language: en
  default_encoding: utf-8

normalize_methods:
  text:
    unicode_form: NFC
    case: lower
  entity:
    resolve_aliases: true
  date:
    format: ISO8601
    timezone: UTC
```

```python
from semantica.normalize.config import NormalizeConfig

# Load from config file
config = NormalizeConfig(config_file="config.yaml")
unicode_form = config.get("unicode_form")
```

## Workflows

### Complete Pipeline

```python
from semantica.normalize import (
    TextNormalizer,
    EntityNormalizer,
    DateNormalizer,
    NumberNormalizer,
    DataCleaner
)

# Create normalizers
text_norm = TextNormalizer()
entity_norm = EntityNormalizer()
date_norm = DateNormalizer()
number_norm = NumberNormalizer()
cleaner = DataCleaner()

# Step 1: Normalize text
text = text_norm.normalize_text("Hello   World", case="lower")

# Step 2: Normalize entities
entities = ["John Doe", "J. Doe", "Johnny Doe"]
normalized_entities = [
    entity_norm.normalize_entity(e, entity_type="Person")
    for e in entities
]

# Step 3: Normalize dates
dates = ["2023-01-15", "yesterday", "3 days ago"]
normalized_dates = [
    date_norm.normalize_date(d)
    for d in dates
]

# Step 4: Normalize numbers
numbers = ["1,234.56", "50%", "1.5e3"]
normalized_numbers = [
    number_norm.normalize_number(n)
    for n in numbers
]

# Step 5: Clean dataset
dataset = [
    {"id": 1, "name": "Alice", "date": "2023-01-15"},
    {"id": 2, "name": "Bob", "date": "yesterday"},
]
cleaned = cleaner.clean_data(dataset, remove_duplicates=True)
```

### Custom Workflow

```python
from semantica.normalize import (
    TextNormalizer,
    EntityNormalizer,
    DateNormalizer,
    NumberNormalizer,
    DataCleaner
)

# Create normalizers with custom config
text_norm = TextNormalizer(unicode_form="NFKC", case="lower")
entity_norm = EntityNormalizer(alias_map={"j. doe": "John Doe"})
date_norm = DateNormalizer()
number_norm = NumberNormalizer()
cleaner = DataCleaner(similarity_threshold=0.85)

# Normalize text
text = text_norm.normalize_text("Hello   World")

# Normalize entities
entity = entity_norm.normalize_entity("J. Doe", entity_type="Person")

# Normalize dates
date = date_norm.normalize_date("2023-01-15", format="ISO8601")

# Normalize numbers
number = number_norm.normalize_number("1,234.56")

# Clean data
cleaned = cleaner.clean_data(dataset, remove_duplicates=True)
```

### Batch Processing

```python
from semantica.normalize import TextNormalizer, EntityNormalizer

text_norm = TextNormalizer()
entity_norm = EntityNormalizer()

# Batch text normalization
texts = ["Hello   World", "Test   Text", "Another   Example"]
normalized_texts = text_norm.process_batch(texts, case="lower")

# Batch entity normalization
entities = ["John Doe", "Jane Smith", "Bob Johnson"]
normalized_entities = [
    entity_norm.normalize_entity(e, entity_type="Person")
    for e in entities
]
```

### Integration

```python
from semantica.normalize import TextNormalizer, EntityNormalizer
from semantica.kg import build

text_norm = TextNormalizer()
entity_norm = EntityNormalizer()

# Normalize text before KG building
text = text_norm.normalize_text("Apple Inc. was founded by Steve Jobs")

# Normalize entities before adding to KG
entities = [
    entity_norm.normalize_entity("Apple Inc.", entity_type="Organization"),
    entity_norm.normalize_entity("Steve Jobs", entity_type="Person")
]

# Build knowledge graph with normalized data
kg = build(sources=[{"entities": entities, "relationships": []}])
```

### Custom Validation

```python
from semantica.normalize import DataCleaner, DataValidator

cleaner = DataCleaner()

# Custom validation schema
schema = {
    "fields": {
        "id": {"type": int, "required": True},
        "name": {"type": str, "required": True, "min_length": 2},
        "age": {"type": int, "required": False, "min": 0, "max": 150}
    }
}

dataset = [
    {"id": 1, "name": "Alice", "age": 30},
    {"id": 2, "name": "B", "age": 200},  # Invalid: name too short, age out of range
]

# Validate
validation = cleaner.validate_data(dataset, schema)
if not validation.valid:
    for error in validation.errors:
        print(f"Error: {error}")
```

### Language-Aware

```python
from semantica.normalize import TextNormalizer, LanguageDetector

detector = LanguageDetector()
normalizer = TextNormalizer()

text = "Bonjour le monde"
language, confidence = detector.detect_with_confidence(text)

if language == "fr":
    normalized = normalizer.normalize_text(text, case="preserve")
else:
    normalized = normalizer.normalize_text(text, case="lower")
```

### Encoding-Aware

```python
from semantica.normalize import TextNormalizer, EncodingHandler

handler = EncodingHandler()
text_norm = TextNormalizer()

data = b'\xff\xfeH\x00e\x00l\x00l\x00o\x00'  # UTF-16 LE with BOM
encoding, confidence = handler.detect(data)
utf8_text = handler.convert_to_utf8(data, source_encoding=encoding)

normalized = text_norm.normalize_text(utf8_text)
```

### Cleaning Pipeline

```python
from semantica.normalize import TextNormalizer, DateNormalizer, DataCleaner

# Raw dataset
raw_dataset = [
    {"id": 1, "name": "  Alice  ", "date": "2023-01-15"},
    {"id": 2, "name": "Bob", "date": "yesterday"},
    {"id": 1, "name": "Alice", "date": "2023-01-15"},  # Duplicate
    {"id": 3, "name": None, "date": "2023-01-20"},  # Missing name
]

text_norm = TextNormalizer()
date_norm = DateNormalizer()

# Step 1: Normalize text fields
for record in raw_dataset:
    if record.get("name"):
        record["name"] = text_norm.normalize_text(record["name"]) 

# Step 2: Normalize dates
for record in raw_dataset:
    if record.get("date"):
        record["date"] = date_norm.normalize_date(record["date"]) 

# Step 3: Clean data
cleaner = DataCleaner()
cleaned = cleaner.clean_data(
    raw_dataset,
    remove_duplicates=True,
    handle_missing=True,
    missing_strategy="remove"
)

print(f"Cleaned {len(raw_dataset)} -> {len(cleaned)} records")
```

## Best Practices

1. **Unicode Normalization**: Always use NFC form for most use cases, NFKC for compatibility
2. **Case Handling**: Preserve case when possible, normalize only when necessary
3. **Entity Normalization**: Provide entity_type when available for better normalization
4. **Date Parsing**: Use ISO8601 format for consistency, handle timezones explicitly
5. **Number Parsing**: Be aware of locale-specific formatting (commas vs periods)
6. **Data Cleaning**: Validate data before cleaning, use appropriate strategies
7. **Language Detection**: Ensure minimum text length (10+ characters) for reliable detection
8. **Encoding Handling**: Always detect encoding before conversion, use fallback chain
9. **Batch Processing**: Use batch methods for large datasets to improve performance
10. **Configuration**: Use configuration files for consistent settings across environments
11. **Error Handling**: Always handle ValidationError and ProcessingError exceptions
12. **Method Registry**: Register custom methods for domain-specific normalization needs

