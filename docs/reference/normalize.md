---
title: "Normalize Module"
description: "Text cleaning, entity canonicalization, date normalization, number conversion, language detection, and encoding repair: before extraction runs."
icon: "broom"
---

**`semantica.normalize`** standardizes raw data **before extraction and graph construction**:

- Text cleaning: Unicode NFC/NFKC, whitespace collapse, smart-quote and dash normalization
- Entity canonicalization: alias resolution and disambiguation via configurable alias maps
- Date normalization: any format → ISO 8601, including relative dates
- Number conversion: `"$1.2B"` → `1200000000.0` with unit and currency handling
- Language detection and encoding repair for inconsistent source data

All normalizers expose convenience functions (one-liners) and stateful class instances (full control).


## Why Normalize Before Extraction

Unstructured data is inconsistent by nature. Without normalization, the same real-world entity appears as dozens of variants in your graph:

- `"Apple Inc."`, `"Apple Computer Inc."`, `"APPLE INC."`: multiple nodes, one company
- `"Jan 1st, 2020"`, `"01/01/2020"`, `"2020-01-01"`: three formats, one date
- `"$1.2B"`, `"1,200,000,000"`, `"1.2 billion USD"`: three strings, one number
- `"Hello World"` vs `"Hello\u00a0World"`: a non-breaking space that breaks string matching

Normalization collapses these variants before any extractor, deduplicator, or graph builder sees the data.

## Exported Classes

| Class | Role |
| :--- | :--- |
| `TextNormalizer` | Unicode forms (NFC/NFKC), whitespace collapse, smart-quote and dash normalization |
| `EntityNormalizer` | Alias resolution and entity disambiguation using configurable alias maps |
| `DateNormalizer` | Parses any date string format to ISO 8601; handles relative dates |
| `NumberNormalizer` | `"$1.2B"` → `1200000000.0`; unit conversion; currency parsing |
| `DataCleaner` | Detect and remove duplicates, handle missing values, validate records |
| `LanguageDetector` | `detect(text)` → language code `str`; `detect_with_confidence(text)` → `(code, score)` tuple |
| `EncodingHandler` | `detect(bytes)` → `(encoding, confidence)` tuple; `convert_to_utf8(bytes)` → `str` |

## Getting Started

```python
from semantica.normalize import (
    TextNormalizer,
    DateNormalizer,
    NumberNormalizer,
    LanguageDetector,
    EncodingHandler,
)

# Text: normalize unicode, collapse whitespace, replace smart quotes
normalizer = TextNormalizer()
clean = normalizer.normalize_text("  Hello,\u00a0 World\u2026  ")
# → "Hello, World..."

# Date
date_norm = DateNormalizer()
date = date_norm.normalize_date("Jan 1st, 2020")
# → "2020-01-01T00:00:00+00:00"

# Number
num_norm = NumberNormalizer()
num = num_norm.normalize_number("$1.2B")
# → 1200000000.0

# Language: returns a language code string
detector = LanguageDetector()
lang = detector.detect("Bonjour le monde")
# → "fr"

# Encoding: returns (encoding_name, confidence) tuple
handler = EncodingHandler()
encoding, confidence = handler.detect(raw_bytes)
utf8_text = handler.convert_to_utf8(raw_bytes)
```

## Recommended Processing Order

<Steps>
  <Step title="EncodingHandler: fix encoding first">
    Broken bytes corrupt everything downstream. Always run this before anything else.

    ```python
    from semantica.normalize import EncodingHandler

    handler = EncodingHandler()
    # detect returns (encoding_name, confidence_score)
    encoding, confidence = handler.detect(raw_bytes)
    # convert_to_utf8 returns a str
    utf8_text = handler.convert_to_utf8(raw_bytes)
    ```
  </Step>
  <Step title="TextNormalizer: unicode, whitespace, special chars">
    ```python
    from semantica.normalize import TextNormalizer

    normalizer = TextNormalizer()
    # normalize_text takes per-call options, not constructor params
    clean_text = normalizer.normalize_text(
        utf8_text,
        unicode_form="NFC",
        case="preserve",
    )
    ```
  </Step>
  <Step title="EntityNormalizer: canonicalize entity names">
    ```python
    from semantica.normalize import EntityNormalizer

    # Provide aliases in config so the resolver can map variants
    normalizer = EntityNormalizer(alias_map={
        "apple computer inc.": "Apple Inc.",
        "apple computer, inc.": "Apple Inc.",
    })
    canonical = normalizer.normalize_entity(
        "Apple Computer, Inc.", entity_type="Organization"
    )
    # → "Apple Inc." (if the alias_map contains it, else title-cased input)
    ```
  </Step>
  <Step title="DateNormalizer and NumberNormalizer: parse structured values">
    ```python
    from semantica.normalize import DateNormalizer, NumberNormalizer

    date_norm = DateNormalizer()
    num_norm  = NumberNormalizer()

    # format and timezone are passed to normalize_date(), not to the constructor
    date = date_norm.normalize_date("Jan 1st, 2020", format="ISO8601", timezone="UTC")
    # → "2020-01-01T00:00:00+00:00"

    num = num_norm.normalize_number("$1.2B")
    # → 1200000000.0
    ```
  </Step>
  <Step title="LanguageDetector: detect language on clean text">
    ```python
    from semantica.normalize import LanguageDetector

    detector = LanguageDetector()

    # detect() returns a language code string
    lang = detector.detect("Bonjour le monde")
    # → "fr"

    # detect_with_confidence() returns (code, score) tuple
    lang, confidence = detector.detect_with_confidence("Bonjour le monde")
    # → ("fr", 0.98)
    ```
  </Step>
</Steps>

## Convenience Functions

The fastest path: one import, one call:

```python
from semantica.normalize import (
    normalize_text, normalize_entity, normalize_date,
    normalize_number, clean_data, detect_language, handle_encoding,
)

clean  = normalize_text("  Hello,   World  ")
# → "Hello, World"

entity = normalize_entity("John Doe", entity_type="Person")
# → "John Doe" (title-cased; alias resolution requires alias_map)

date   = normalize_date("Jan 1st, 2020")
# → "2020-01-01T00:00:00+00:00"

num    = normalize_number("$1.2B")
# → 1200000000.0

# detect_language returns a language code string by default
lang   = detect_language("Bonjour le monde")
# → "fr"

# handle_encoding with operation="detect" returns (encoding, confidence) tuple
encoding, confidence = handle_encoding(raw_bytes, operation="detect")

# handle_encoding with operation="convert" returns a UTF-8 string
utf8_text = handle_encoding(raw_bytes, operation="convert")
```

## Normalizers

<Tabs>
  <Tab title="TextNormalizer">
    `TextNormalizer` takes `config=None, **kwargs` in its constructor. Normalization
    options are passed per-call to `normalize_text()`:

    ```python
    from semantica.normalize import TextNormalizer

    normalizer = TextNormalizer()

    # normalize_text options
    normalized = normalizer.normalize_text(
        raw_text,
        unicode_form="NFC",       # "NFC" | "NFD" | "NFKC" | "NFKD"
        case="preserve",          # "preserve" | "lower" | "upper" | "title"
        normalize_diacritics=False,
        line_break_type="unix",   # "unix" | "windows"
    )

    # HTML stripping and text cleaning: separate clean_text() method
    cleaned = normalizer.clean_text(html_text, remove_html=True)

    # Batch normalization
    results = normalizer.process_batch(
        ["  hello  ", "WORLD", "caf\u00e9"],
        unicode_form="NFKC",
        case="lower",
    )

    # normalize() accepts str or List[Dict] (parsed docs from DocumentParser)
    docs = [{"content": "Hello\u00a0world"}, {"content": "test text"}]
    normalized_docs = normalizer.normalize(docs)
    ```

    | `normalize_text()` parameter | Type | Default | Description |
    | :----------------------------- | :---- | :------- | :----------- |
    | `unicode_form` | `str` | `"NFC"` | Unicode form: `"NFC"` / `"NFD"` / `"NFKC"` / `"NFKD"` |
    | `case` | `str` | `"preserve"` | `"preserve"` / `"lower"` / `"upper"` / `"title"` |
    | `normalize_diacritics` | `bool` | `False` | Strip diacritical marks |
    | `line_break_type` | `str` | `"unix"` | `"unix"` (`\n`) or `"windows"` (`\r\n`) |

    **Unicode form guide:**

    | Form | Use When |
    | :---- | :-------- |
    | `NFC` | Default: best for storage and display |
    | `NFKC` | Search indexing: normalises ligatures, fullwidth chars, and fractions |
    | `NFD` | Stripping diacritics: split é → e + combining accent, then strip accents |
    | `NFKD` | Same as NFD but also decomposes compatibility characters |

    **Sub-normalizers for fine-grained control:**

    ```python
    from semantica.normalize import (
        UnicodeNormalizer, WhitespaceNormalizer, SpecialCharacterProcessor
    )

    unicode_norm = UnicodeNormalizer()
    text = unicode_norm.normalize_unicode("caf\u00e9", form="NFC")

    ws_norm = WhitespaceNormalizer()
    text    = ws_norm.normalize_whitespace("Hello\t\t World\n\n")
    # → "Hello  World\n\n"

    processor = SpecialCharacterProcessor()
    text      = processor.normalize_punctuation("\u2018Hello\u2019")
    # → "'Hello'"
    ```
  </Tab>
  <Tab title="EntityNormalizer">
    `EntityNormalizer` performs: whitespace cleanup, optional alias resolution
    (requires an explicit `alias_map`), and name format normalization.

    ```python
    from semantica.normalize import EntityNormalizer

    # With alias map: resolves exact matches (lowercase key lookup)
    normalizer = EntityNormalizer(alias_map={
        "apple computer inc.": "Apple Inc.",
        "ms": "Microsoft",
        "ml":  "Machine Learning",
    })

    normalizer.normalize_entity("Apple Computer Inc.", entity_type="Organization")
    # → "Apple Inc."

    # Without alias map: only whitespace/format cleanup
    normalizer2 = EntityNormalizer()
    normalizer2.normalize_entity("apple inc", entity_type="Organization")
    # → "apple inc"  (no built-in suffix expansion)

    # Person: title-cased
    normalizer2.normalize_entity("john doe", entity_type="Person")
    # → "John Doe"
    ```

    **Key behaviours:**
    - Alias map uses **lowercase key lookup**: register aliases in lowercase
    - `entity_type="Person"` activates `title()` casing on the name
    - There is no built-in corporate suffix normalization (Inc → Incorporated etc.)
     : add these mappings to `alias_map` manually if needed

    **Sub-normalizers:**

    ```python
    from semantica.normalize import AliasResolver, EntityDisambiguator, NameVariantHandler

    # alias_map keys must be lowercase
    resolver = AliasResolver(alias_map={
        "ml":  "Machine Learning",
        "nlp": "Natural Language Processing",
    })
    resolved = resolver.resolve_aliases("ml")
    # → "Machine Learning" or None if not in map

    disambiguator = EntityDisambiguator()
    result = disambiguator.disambiguate(
        "Apple",
        entity_type="Organization",
        context="Steve Jobs founded Apple in Cupertino in 1976",
    )
    # → {"entity_name": "Apple", "entity_type": "Organization", "confidence": 0.8, "candidates": ["Apple"]}

    handler   = NameVariantHandler()
    canonical = handler.normalize_name_format("Dr. JOHN P. SMITH Jr.")
    # → "John P. Smith Jr." (removes leading title)
    ```
  </Tab>
  <Tab title="DateNormalizer">
    `DateNormalizer` takes `config=None, **kwargs`. The `format` and `timezone`
    options are passed to `normalize_date()`, not the constructor:

    ```python
    from semantica.normalize import DateNormalizer

    normalizer = DateNormalizer()

    dates = [
        "January 1st, 2020",
        "01/01/2020",
        "2020-01-01T00:00:00Z",
        "yesterday",
        "3 weeks ago",
    ]

    for d in dates:
        print(normalizer.normalize_date(d, format="ISO8601", timezone="UTC"))
    ```

    Requires `python-dateutil`: `pip install python-dateutil`. Falls back to
    `datetime.fromisoformat()` if not installed.

    **Sub-normalizers:**

    ```python
    from semantica.normalize import TimeZoneNormalizer, RelativeDateProcessor, TemporalExpressionParser
    from datetime import datetime

    # TimeZoneNormalizer takes a datetime object, not a string
    tz_norm = TimeZoneNormalizer()
    dt_naive = datetime(2024, 1, 1, 9, 0)
    utc_dt = tz_norm.convert_to_utc(dt_naive)
    tz_dt  = tz_norm.normalize_timezone(dt_naive, target_timezone="America/New_York")

    # RelativeDateProcessor: reference_date is passed to process_relative_expression(),
    # not to the constructor
    processor = RelativeDateProcessor()
    ref = datetime(2025, 1, 15)
    result = processor.process_relative_expression("3 days ago", reference_date=ref)
    # → datetime(2025, 1, 12)

    parser = TemporalExpressionParser()
    result = parser.parse_temporal_expression("from January 2020 to March 2021")
    # → {"date": ..., "time": ..., "range": {"start": ..., "end": ...}, "relative": False}
    ```
  </Tab>
  <Tab title="NumberNormalizer">
    Converts number strings with units, currencies, and abbreviations to `int` or `float`:

    ```python
    from semantica.normalize import NumberNormalizer

    normalizer = NumberNormalizer()

    normalizer.normalize_number("$1,234.56")  # → 1234.56
    normalizer.normalize_number("42K")         # → 42000.0
    normalizer.normalize_number("$1.2B")       # → 1200000000.0
    normalizer.normalize_number("3.14e-2")     # → 0.0314
    normalizer.normalize_number("42%")         # → 0.42
    ```

    **Unit and currency conversion:**

    ```python
    from semantica.normalize import UnitConverter, CurrencyNormalizer

    converter = UnitConverter()
    result    = converter.convert_units(100, from_unit="kg", to_unit="pound")
    # → 220.46...

    normalized_unit = converter.normalize_unit("km")
    # → "kilometer"

    currency_norm = CurrencyNormalizer()
    result = currency_norm.normalize_currency("$42.50")
    # → {"amount": 42.50, "currency": "USD", "original": "$42.50"}
    ```
  </Tab>
  <Tab title="Language & Encoding">
    ### LanguageDetector

    Identify the language of a text string. Requires `langdetect`: `pip install langdetect`.

    ```python
    from semantica.normalize import LanguageDetector

    detector = LanguageDetector()

    # detect() returns a language code string
    lang = detector.detect("Bonjour le monde")
    # → "fr"

    # detect_with_confidence() returns (code, confidence) tuple
    lang, confidence = detector.detect_with_confidence("Bonjour le monde")
    # → ("fr", 0.98)

    # detect_multiple() returns List[(code, confidence)]
    results = detector.detect_multiple("This might be mixed", top_n=3)
    # → [("en", 0.85), ...]

    # Batch: returns List[str]
    codes = detector.detect_batch(["Hello", "Hola", "Bonjour", "Ciao"])

    # Check specific language
    is_english = detector.is_language(text, "en", min_confidence=0.8)
    ```

    <Note>
      `detect()` requires at least 10 characters for reliable detection. On shorter text it returns the `default_language` (default: `"en"`).
    </Note>

    ### EncodingHandler

    Detect and repair character encoding issues. Requires `chardet`: `pip install chardet`.

    ```python
    from semantica.normalize import EncodingHandler

    handler = EncodingHandler()

    # detect() returns (encoding_name, confidence_score) tuple
    encoding, confidence = handler.detect(raw_bytes)
    # → ("windows-1252", 0.73)

    # convert_to_utf8() returns a str
    utf8_text = handler.convert_to_utf8(raw_bytes)
    utf8_text = handler.convert_to_utf8(raw_bytes, source_encoding="cp1252")

    # remove_bom() returns same type as input (str or bytes) with BOM stripped
    clean = handler.remove_bom(text_with_bom)

    # Detect and convert a file on disk
    utf8_content = handler.convert_file_to_utf8("input.txt", output_path="output.txt")
    ```

    **Key behaviours:**
    - `detect()` uses `chardet` internally: accuracy improves with longer input
    - `convert_to_utf8()` auto-detects encoding if `source_encoding` is not provided,
      then falls back through `latin-1`, `cp1252`, `iso-8859-1`
    - Always run `EncodingHandler` first: broken bytes cause cascading failures
      in every downstream normalizer
  </Tab>
</Tabs>

## DataCleaner

Cleans structured record sets: useful before loading into a vector store or graph:

```python
from semantica.normalize import DataCleaner, DataValidator, DuplicateDetector

cleaner = DataCleaner()

# clean_data: remove_duplicates, validate, and handle_missing in one pass
cleaned = cleaner.clean_data(
    records,
    remove_duplicates=True,
    validate=True,
    handle_missing=True,
    missing_strategy="remove",  # "remove" | "fill" | "impute"
)

# detect_duplicates: returns List[DuplicateGroup]
groups = cleaner.detect_duplicates(records, threshold=0.9)
for group in groups:
    print(f"Duplicate group: {len(group.records)} records, similarity={group.similarity_score:.2f}")
    print(f"  Canonical: {group.canonical_record}")

# handle_missing_values: standalone missing-value handling
processed = cleaner.handle_missing_values(records, strategy="fill", fill_value="")

# validate_data: validate against a schema dict
result = cleaner.validate_data(
    records,
    schema={"fields": {
        "name":   {"type": str,  "required": True},
        "age":    {"type": int,  "required": False},
        "active": {"type": bool, "required": False},
    }},
)
# ValidationResult has .valid (bool), .errors (list), .warnings (list)
print(f"Valid:    {result.valid}")
print(f"Errors:   {len(result.errors)}")
print(f"Warnings: {len(result.warnings)}")
```

### DataCleaner Methods

| Method | Returns | Description |
| :------ | :------- | :----------- |
| `clean_data(dataset, remove_duplicates, validate, handle_missing, **options)` | `List[Dict]` | Combined cleaning pipeline |
| `detect_duplicates(dataset, threshold, key_fields)` | `List[DuplicateGroup]` | Return duplicate groups above similarity threshold |
| `validate_data(dataset, schema)` | `ValidationResult` | Validate records against a schema dict |
| `handle_missing_values(dataset, strategy)` | `List[Dict]` | Remove, fill, or impute missing values |

## Pipeline Integration

```python
from semantica.pipeline import PipelineBuilder, ExecutionEngine
from semantica.ingest import FileIngestor
from semantica.normalize import TextNormalizer
from semantica.semantic_extract import NERExtractor

ingestor   = FileIngestor()
normalizer = TextNormalizer()
extractor  = NERExtractor(method="ml")

builder = PipelineBuilder()
# TextNormalizer.normalize() accepts both str and List[Dict] from DocumentParser
builder.add_step("ingest",    "file_ingest",    handler=ingestor.ingest_file)
builder.add_step("normalize", "text_normalize", handler=normalizer.normalize)
builder.add_step("extract",   "ner_extract",    handler=extractor.extract)
builder.connect_steps("ingest",    "normalize")
builder.connect_steps("normalize", "extract")

pipeline = builder.build("normalize_pipeline")
result   = ExecutionEngine().execute_pipeline(pipeline, data="data/documents/")
```

## Custom Normalizers

Register a custom normalizer in the method registry:

```python
from semantica.normalize.registry import method_registry

def my_normalizer(text, **kwargs):
    return text.replace("Inc.", "Incorporated")

method_registry.register("text", "expand_suffixes", my_normalizer)

from semantica.normalize import normalize_text
normalized = normalize_text("Apple Inc.", method="expand_suffixes")
# → "Apple Incorporated"
```

## Tips and Common Pitfalls

<Warning>
  **Run encoding repair before anything else.** A single cp1252 character in a UTF-8 stream silently corrupts the surrounding text. Call `handler.convert_to_utf8(raw_bytes)` first, before any other normalizer sees the data.
</Warning>

<Warning>
  **Don't lowercase before NER.** `normalize_text(text, case="lower")` before entity extraction destroys capitalization signals that NER relies on. Apply case normalization only after extraction if needed.
</Warning>

<Warning>
  **`EntityNormalizer` has no built-in corporate suffix expansion.** There is no automatic mapping of `"Apple Computer Inc."` → `"Apple Inc."`. To canonicalize corporate names, provide an explicit `alias_map` with lowercase keys: `EntityNormalizer(alias_map={"apple computer inc.": "Apple Inc."})`.
</Warning>

<Tip>
  **`AliasResolver` uses lowercase key lookup.** Register aliases with lowercase keys even if the canonical form is title-cased. The resolver converts the input to lowercase before lookup.
</Tip>

<Warning>
  **`LanguageDetector.detect()` returns a `str`, not a dict.** Use `detect_with_confidence()` for `(language_code, confidence)` tuple, or `detect_multiple()` for `List[(code, confidence)]`.
</Warning>

<Warning>
  **`EncodingHandler.detect()` returns a `(str, float)` tuple, not a dict.** Unpack with `encoding, confidence = handler.detect(data)`.
</Warning>

<Tip>
  **`DataCleaner.remove_duplicates()` does not exist as a standalone method.** Use `detect_duplicates()` to get `DuplicateGroup` objects, or call `clean_data(records, remove_duplicates=True)` to remove them in-place.
</Tip>

<Tip>
  **`DataCleaner` operates on flat records, not graph entities.** For entity-level semantic deduplication, use `DuplicateDetector` from the Deduplication module instead.
</Tip>

<CardGroup cols={2}>
  <Card title="Parse" icon="file-lines" href="parse">
    Parse documents before normalization.
  </Card>
  <Card title="Split" icon="scissors" href="split">
    Chunk normalized text for embedding.
  </Card>
  <Card title="Deduplication" icon="copy" href="deduplication">
    Resolve duplicate entities after normalization.
  </Card>
  <Card title="Pipeline" icon="gear" href="pipeline">
    Include normalization as a named pipeline step.
  </Card>
</CardGroup>
