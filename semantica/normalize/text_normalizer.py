"""
Text Normalization Module

This module provides comprehensive text normalization capabilities for the
Semantica framework, enabling standardization of text content across various
formats and encodings.

Key Features:
    - Text cleaning and sanitization
    - Unicode normalization (NFC, NFD, NFKC, NFKD)
    - Case normalization (lower, upper, title, preserve)
    - Whitespace handling (normalization, line breaks, indentation)
    - Special character processing (punctuation, diacritics)
    - Format standardization

Main Classes:
    - TextNormalizer: Main text normalization coordinator
    - UnicodeNormalizer: Unicode processing engine
    - WhitespaceNormalizer: Whitespace handling engine
    - SpecialCharacterProcessor: Special character processing engine

Example Usage:
    >>> from semantica.normalize import TextNormalizer
    >>> normalizer = TextNormalizer()
    >>> normalized = normalizer.normalize_text("Hello   World", case="lower")
    >>> cleaned = normalizer.clean_text(text, remove_html=True)

Author: Semantica Contributors
License: MIT
"""

import re
import unicodedata
from typing import Any, Dict, List, Optional, Union

from ..utils.exceptions import ProcessingError, ValidationError
from ..utils.logging import get_logger
from ..utils.progress_tracker import get_progress_tracker
from .text_cleaner import TextCleaner


class TextNormalizer:
    """
    Text normalization and cleaning coordinator.

    This class provides comprehensive text normalization capabilities, coordinating
    Unicode normalization, whitespace handling, special character processing,
    and text cleaning.

    Features:
        - Text cleaning and sanitization
        - Unicode normalization
        - Case normalization
        - Whitespace handling
        - Special character processing
        - Format standardization
        - Batch processing

    Example Usage:
        >>> normalizer = TextNormalizer()
        >>> normalized = normalizer.normalize_text("Hello   World", case="lower")
        >>> cleaned = normalizer.clean_text(text, remove_html=True)
        >>> batch = normalizer.process_batch(texts)
    """

    def __init__(self, config: Optional[Dict[str, Any]] = None, **kwargs):
        """
        Initialize text normalizer.

        Sets up the normalizer with text cleaner, Unicode normalizer, whitespace
        normalizer, and special character processor components.

        Args:
            config: Configuration dictionary (optional)
            **kwargs: Additional configuration options (merged into config)
        """
        self.logger = get_logger("text_normalizer")
        self.config = config or {}
        self.config.update(kwargs)

        self.text_cleaner = TextCleaner(**self.config)
        self.unicode_normalizer = UnicodeNormalizer(**self.config)
        self.whitespace_normalizer = WhitespaceNormalizer(**self.config)
        self.special_char_processor = SpecialCharacterProcessor(**self.config)

        # Initialize progress tracker
        self.progress_tracker = get_progress_tracker()
        # Ensure progress tracker is enabled
        if not self.progress_tracker.enabled:
            self.progress_tracker.enabled = True

        self.logger.debug("Text normalizer initialized")

    def normalize(
        self,
        source: Union[str, List[Dict[str, Any]]],
        **options,
    ) -> Union[str, List[Dict[str, Any]]]:
        """
        Normalize text content or a list of parsed documents.
        """
        if isinstance(source, list):
            # Handle list of parsed documents
            normalized_docs = []
            for doc in source:
                if isinstance(doc, dict) and "content" in doc:
                    new_doc = doc.copy()
                    new_doc["content"] = self.normalize_text(doc["content"], **options)
                    normalized_docs.append(new_doc)
                else:
                    # If it's just a string or unknown, try to normalize it directly or skip
                    try:
                        normalized_docs.append(self.normalize_text(str(doc), **options))
                    except Exception:
                        normalized_docs.append(doc)
            return normalized_docs
        else:
            return self.normalize_text(str(source), **options)

    def normalize_text(
        self,
        text: str,
        unicode_form: str = "NFC",
        case: str = "preserve",
        normalize_diacritics: bool = False,
        line_break_type: str = "unix",
        **options,
    ) -> str:
        """
        Normalize text content.

        This method performs comprehensive text normalization by applying
        Unicode normalization, whitespace normalization, special character
        processing, and case normalization in sequence.

        Args:
            text: Input text to normalize
            unicode_form: Unicode normalization form (default: "NFC"):
                - "NFC": Canonical composition
                - "NFD": Canonical decomposition
                - "NFKC": Compatibility composition
                - "NFKD": Compatibility decomposition
            case: Case normalization type (default: "preserve"):
                - "preserve": Keep original case
                - "lower": Convert to lowercase
                - "upper": Convert to uppercase
                - "title": Convert to title case
            normalize_diacritics: Whether to normalize diacritics (default: False)
            line_break_type: Line break type for whitespace normalization
                           (default: "unix")
            **options: Additional normalization options (passed to sub-processors)

        Returns:
            str: Normalized text
        """
        tracking_id = self.progress_tracker.start_tracking(
            message="Semantica: Normalizing text", file=None
        )
        try:
            if not text:
                self.progress_tracker.stop_tracking(tracking_id, status="completed")
                return ""

            normalized = text

            # Unicode normalization
            normalized = self.unicode_normalizer.normalize_unicode(
                normalized, form=unicode_form
            )

            # Whitespace normalization
            normalized = self.whitespace_normalizer.normalize_whitespace(
                normalized, line_break_type=line_break_type, **options
            )

            # Special character processing
            normalized = self.special_char_processor.process_special_chars(
                normalized, normalize_diacritics=normalize_diacritics, **options
            )

            # Case normalization
            if case == "lower":
                normalized = normalized.lower()
            elif case == "upper":
                normalized = normalized.upper()
            elif case == "title":
                normalized = normalized.title()

            self.progress_tracker.stop_tracking(tracking_id, status="completed")
            return normalized

        except Exception as e:
            self.progress_tracker.stop_tracking(
                tracking_id, status="failed", message=str(e)
            )
            raise

    def clean_text(self, text: str, **options) -> str:
        """
        Clean and sanitize text content.

        This method delegates to the text cleaner for comprehensive text cleaning.

        Args:
            text: Input text to clean
            **options: Cleaning options (passed to TextCleaner.clean)

        Returns:
            str: Cleaned text
        """
        return self.text_cleaner.clean(text, **options)

    def standardize_format(self, text: str, format_type: str = "standard") -> str:
        """
        Standardize text format.

        This method standardizes text format by applying format-specific
        transformations (compact, preserve, or standard).

        Args:
            text: Input text to standardize
            format_type: Format type (default: "standard"):
                - "standard": Apply standard formatting
                - "compact": Remove extra whitespace
                - "preserve": Preserve original formatting

        Returns:
            str: Formatted text
        """
        if format_type == "compact":
            # Remove extra whitespace
            text = re.sub(r"\s+", " ", text)
        elif format_type == "preserve":
            # Preserve original formatting
            pass

        return text.strip()

    def process_batch(self, texts: List[str], **options) -> List[str]:
        """
        Process multiple texts in batch.

        This method processes multiple texts in batch, applying the same
        normalization operations to each text.

        Args:
            texts: List of texts to process
            **options: Processing options (passed to normalize_text method)

        Returns:
            list: List of normalized texts (one per input text)
        """
        return [self.normalize_text(text, **options) for text in texts]


class UnicodeNormalizer:
    """
    Unicode normalization engine.

    This class provides Unicode normalization capabilities, handling different
    Unicode forms and special character processing.

    Features:
        - Unicode normalization (NFC, NFD, NFKC, NFKD)
        - Character encoding conversion
        - Special Unicode character processing
        - Support for various scripts and languages

    Example Usage:
        >>> normalizer = UnicodeNormalizer()
        >>> normalized = normalizer.normalize_unicode(text, form="NFC")
        >>> processed = normalizer.process_special_chars(text)
    """

    def __init__(self, **config):
        """
        Initialize Unicode normalizer.

        Sets up the normalizer with configuration options.

        Args:
            **config: Configuration options (currently unused)
        """
        self.logger = get_logger("unicode_normalizer")
        self.config = config

        self.logger.debug("Unicode normalizer initialized")

    def normalize_unicode(self, text: str, form: str = "NFC") -> str:
        """
        Normalize Unicode text.

        This method normalizes Unicode characters using the specified
        normalization form.

        Args:
            text: Input text to normalize
            form: Unicode normalization form (default: "NFC"):
                - "NFC": Canonical composition
                - "NFD": Canonical decomposition
                - "NFKC": Compatibility composition
                - "NFKD": Compatibility decomposition

        Returns:
            str: Unicode-normalized text (returns original text if normalization fails)
        """
        if not text:
            return ""

        try:
            return unicodedata.normalize(form, text)
        except Exception as e:
            self.logger.warning(f"Unicode normalization failed: {e}")
            return text

    def handle_encoding(
        self, text: str, source_encoding: str, target_encoding: str = "utf-8"
    ) -> str:
        """
        Handle text encoding conversion.

        This method converts text from one encoding to another, handling
        both string and bytes input.

        Args:
            text: Input text (string or bytes)
            source_encoding: Source encoding name (e.g., "latin-1", "cp1252")
            target_encoding: Target encoding name (default: "utf-8")

        Returns:
            str: Converted text in target encoding (falls back to UTF-8 with
                 error replacement if conversion fails)
        """
        if isinstance(text, bytes):
            try:
                return (
                    text.decode(source_encoding)
                    .encode(target_encoding)
                    .decode(target_encoding)
                )
            except Exception:
                return text.decode("utf-8", errors="replace")
        else:
            return text

    def process_special_chars(self, text: str) -> str:
        """
        Process special Unicode characters.

        This method replaces common special Unicode characters (smart quotes,
        dashes, ellipsis) with their ASCII equivalents.

        Args:
            text: Input text containing special Unicode characters

        Returns:
            str: Text with special Unicode characters replaced with ASCII equivalents
        """
        # Replace common special characters
        replacements = {
            "\u2018": "'",  # Left single quotation mark
            "\u2019": "'",  # Right single quotation mark
            "\u201C": '"',  # Left double quotation mark
            "\u201D": '"',  # Right double quotation mark
            "\u2013": "-",  # En dash
            "\u2014": "--",  # Em dash
            "\u2026": "...",  # Horizontal ellipsis
        }

        for old, new in replacements.items():
            text = text.replace(old, new)

        return text


class WhitespaceNormalizer:
    """
    Whitespace normalization engine.

    This class provides whitespace normalization capabilities, handling
    different whitespace types, line breaks, and indentation.

    Features:
        - Whitespace character normalization
        - Line break handling (Unix, Windows, Mac)
        - Indentation processing
        - Multiple whitespace collapse

    Example Usage:
        >>> normalizer = WhitespaceNormalizer()
        >>> normalized = normalizer.normalize_whitespace(text, line_break_type="unix")
        >>> processed = normalizer.process_indentation(text, indent_type="spaces")
    """

    def __init__(self, **config):
        """
        Initialize whitespace normalizer.

        Sets up the normalizer with configuration options.

        Args:
            **config: Configuration options (currently unused)
        """
        self.logger = get_logger("whitespace_normalizer")
        self.config = config

        self.logger.debug("Whitespace normalizer initialized")

    @staticmethod
    def _split_code_blocks(text: str) -> List[tuple]:
        """
        Split text into alternating non-code and code segments.

        Fenced code blocks are delimited by lines starting with three or more
        backticks (```) or tildes (~~~), optionally followed by a language tag.
        The opening fence must appear at the start of a line (allowing leading
        whitespace).  The block ends at the next closing fence line with the
        same fence character and at least as many repetitions.

        If a fence is opened but never closed, everything from the opening
        fence to the end of the text is treated as code.

        Returns:
            List of (is_code, segment_text) tuples where is_code is True for
            fenced code block content (including the fence lines themselves).
        """
        fence_re = re.compile(r"^[ \t]*([`]{3,}|[~]{3,})(.*)$", re.MULTILINE)

        fence_starts: List[tuple] = []
        for m in fence_re.finditer(text):
            fence_starts.append((m.start(), m.group(1), m.group(2), m.end()))

        segments: List[tuple] = []
        last_end = 0
        in_fence = False
        fence_char: Optional[str] = None
        fence_len = 0

        for start, chars, rest, match_end in fence_starts:
            cur_char = chars[0]
            cur_len = len(chars)

            if not in_fence:
                # Opening fence
                if start > last_end:
                    segments.append((False, text[last_end:start]))
                in_fence = True
                fence_char = cur_char
                fence_len = cur_len
                # Include the opening fence line in the code segment
                line_end = text.find("\n", match_end)
                if line_end == -1:
                    line_end = len(text)
                else:
                    line_end += 1  # include the newline
                segments.append((True, text[start:line_end]))
                last_end = line_end
            else:
                # Are we looking for a closing fence?
                if (
                    cur_char == fence_char
                    and cur_len >= fence_len
                    and rest.strip() == ""
                ):
                    # Closing fence found – emit code up to and including it
                    line_end = text.find("\n", match_end)
                    if line_end == -1:
                        line_end = len(text)
                    else:
                        line_end += 1
                    if start > last_end:
                        segments.append((True, text[last_end:start]))
                    segments.append((True, text[start:line_end]))
                    last_end = line_end
                    in_fence = False
                    fence_char = None
                    fence_len = 0

        # Handle unclosed fence – everything from last_end is code
        if in_fence:
            if last_end < len(text):
                segments.append((True, text[last_end:]))
            last_end = len(text)
        elif last_end < len(text):
            segments.append((False, text[last_end:]))

        return segments

    def normalize_whitespace(
        self, text: str, line_break_type: str = "unix", **options
    ) -> str:
        """
        Normalize whitespace in text.

        This method normalizes whitespace by collapsing multiple spaces and
        excess blank lines in prose.  Content inside fenced code blocks
        (delimited by ``` or ~~~) is preserved exactly as-is, including tabs,
        so that indentation is not lost.  Line endings are normalized to LF
        internally for processing and restored to their original form at the
        end, so ``\\r\\n`` input is never mangled into ``\\r\\r\\n\\n``.

        Args:
            text: Input text with potentially irregular whitespace
            line_break_type: Line break type (default: "unix"):
                - "unix": Unix-style line breaks (\\n)
                - "windows": Windows-style line breaks (\\r\\n)
            **options: Additional normalization options (unused)

        Returns:
            str: Text with normalized whitespace
        """
        if not text:
            return ""

        # Detect original line-endings so we can restore them at the end,
        # avoiding regex mangling of \\r\\n into \\r\\r\\n\\n.
        original_ending = "\n"
        if "\r\n" in text:
            original_ending = "\r\n"
        elif "\r" in text and "\r\n" not in text:
            original_ending = "\r"

        # Normalise to LF internally for all processing.
        text = text.replace("\r\n", "\n").replace("\r", "\n")

        # Split into code / non-code segments BEFORE touching tabs.
        segments = self._split_code_blocks(text)

        result_parts: List[str] = []
        for idx, (is_code, segment) in enumerate(segments):
            if is_code:
                # Preserve code block content exactly (tabs included).
                result_parts.append(segment)
            else:
                # Replace tabs with a single space (prose only).
                segment = segment.replace("\t", " ")
                # Collapse multiple spaces.
                segment = re.sub(r" +", " ", segment)
                if idx > 0:
                    # A prose chunk that follows a code block starts at a line
                    # boundary; the code block already contributes the first
                    # newline, so collapse any leading blank lines here to one.
                    segment = re.sub(r"^\n+", "\n", segment)
                # Collapse excess blank lines within this prose chunk only.
                segment = re.sub(r"\n{3,}", "\n\n", segment)
                result_parts.append(segment)

        result = "".join(result_parts)

        # Only strip leading whitespace if the first segment is prose (non-code),
        # and only strip trailing whitespace if the last segment is prose (non-code).
        # This preserves indentation on fence lines at the boundaries.
        if segments:
            if not segments[0][0]:  # first segment is prose
                result = result.lstrip()
            if not segments[-1][0]:  # last segment is prose
                result = result.rstrip()

        # Restore original line endings.
        if original_ending != "\n":
            result = result.replace("\n", original_ending)

        return result

    def handle_line_breaks(self, text: str, line_break_type: str = "unix") -> str:
        """
        Normalize line breaks.

        This method normalizes line breaks to the specified type (Unix, Windows,
        or Mac).

        Args:
            text: Input text with potentially mixed line breaks
            line_break_type: Line break type (default: "unix"):
                - "unix": Unix-style (\n)
                - "windows": Windows-style (\r\n)
                - "mac": Mac-style (\r)

        Returns:
            str: Text with normalized line breaks
        """
        if line_break_type == "unix":
            text = text.replace("\r\n", "\n")
            text = text.replace("\r", "\n")
        elif line_break_type == "windows":
            text = text.replace("\r\n", "\r\n")
            text = text.replace("\r", "\r\n")
            text = text.replace("\n", "\r\n")

        return text

    def process_indentation(self, text: str, indent_type: str = "spaces") -> str:
        """
        Normalize text indentation.

        This method normalizes text indentation by converting between tabs
        and spaces.

        Args:
            text: Input text with potentially mixed indentation
            indent_type: Indentation type (default: "spaces"):
                - "spaces": Convert tabs to 4 spaces
                - "tabs": Convert 4 spaces to tabs

        Returns:
            str: Text with normalized indentation
        """
        if indent_type == "spaces":
            text = text.replace("\t", "    ")  # Convert tabs to 4 spaces
        elif indent_type == "tabs":
            text = re.sub(r"    ", "\t", text)  # Convert 4 spaces to tabs

        return text


class SpecialCharacterProcessor:
    """
    Special character processing engine.

    This class provides special character processing capabilities, including
    punctuation normalization and diacritic handling.

    Features:
        - Punctuation normalization (quotes, dashes, ellipsis)
        - Diacritic processing (normalization or removal)
        - Special character replacement

    Example Usage:
        >>> processor = SpecialCharacterProcessor()
        >>> processed = processor.process_special_chars(text, normalize_diacritics=True)
        >>> normalized = processor.normalize_punctuation(text)
    """

    def __init__(self, **config):
        """
        Initialize special character processor.

        Sets up the processor with configuration options.

        Args:
            **config: Configuration options (currently unused)
        """
        self.logger = get_logger("special_char_processor")
        self.config = config

        self.logger.debug("Special character processor initialized")

    def process_special_chars(
        self, text: str, normalize_diacritics: bool = False, **options
    ) -> str:
        """
        Process special characters in text.

        This method processes special characters by normalizing punctuation
        and optionally processing diacritics.

        Args:
            text: Input text to process
            normalize_diacritics: Whether to normalize diacritics (default: False)
            **options: Additional processing options (passed to process_diacritics)

        Returns:
            str: Text with special characters processed
        """
        # Normalize punctuation
        text = self.normalize_punctuation(text)

        # Process diacritics if requested
        if normalize_diacritics:
            text = self.process_diacritics(text, **options)

        return text

    def normalize_punctuation(self, text: str) -> str:
        """
        Normalize punctuation marks.

        This method normalizes various Unicode punctuation marks to their
        ASCII equivalents (quotes, dashes, ellipsis).

        Args:
            text: Input text with potentially mixed punctuation

        Returns:
            str: Text with normalized punctuation marks
        """
        # Replace common smart punctuation with ASCII equivalents
        replacements = {
            "\u2018": "'",   # Left single quotation mark
            "\u2019": "'",   # Right single quotation mark
            "\u201C": '"',   # Left double quotation mark
            "\u201D": '"',   # Right double quotation mark
            "\u2013": "-",   # En dash
            "\u2014": "--",  # Em dash
            "\u2026": "...", # Ellipsis
        }

        for old, new in replacements.items():
            text = text.replace(old, new)

        return text

    def process_diacritics(
        self, text: str, remove_diacritics: bool = False, **options
    ) -> str:
        """
        Process diacritical marks.

        This method processes diacritical marks by either normalizing them
        (NFC) or removing them entirely.

        Args:
            text: Input text with diacritical marks
            remove_diacritics: Whether to remove diacritics (default: False):
                - True: Remove all diacritical marks
                - False: Normalize diacritics using NFC
            **options: Additional processing options (unused)

        Returns:
            str: Text with diacritics processed (normalized or removed)
        """
        if remove_diacritics:
            # Remove diacritics
            nfd = unicodedata.normalize("NFD", text)
            return "".join(c for c in nfd if unicodedata.category(c) != "Mn")
        else:
            # Normalize diacritics
            return unicodedata.normalize("NFC", text)
