"""
Data Parsing Methods Module

This module provides all parsing operations as simple, reusable functions for
document parsing, web content parsing, structured data parsing, email parsing,
code parsing, and media parsing. It supports multiple approaches and integrates
with the method registry for extensibility.

Supported Methods:

Document Parsing:
    - "default": Default document parsing using DocumentParser
    - "pdf": PDF-focused parsing
    - "docx": DOCX-focused parsing
    - "html": HTML-focused parsing
    - "docling": Docling-based parsing for enhanced table extraction (requires docling package)

Web Content Parsing:
    - "default": Default web parsing using WebParser
    - "html": HTML-focused parsing
    - "xml": XML-focused parsing
    - "javascript": JavaScript-rendered content parsing

Structured Data Parsing:
    - "default": Default structured data parsing using StructuredDataParser
    - "json": JSON-focused parsing
    - "csv": CSV-focused parsing
    - "xml": XML-focused parsing
    - "yaml": YAML-focused parsing

Email Parsing:
    - "default": Default email parsing using EmailParser
    - "headers": Header-only parsing
    - "body": Body-only parsing
    - "thread": Thread analysis parsing

Code Parsing:
    - "default": Default code parsing using CodeParser
    - "ast": AST-focused parsing
    - "comments": Comment-focused parsing
    - "dependencies": Dependency-focused parsing

Media Parsing:
    - "default": Default media parsing using MediaParser
    - "image": Image-focused parsing with OCR
    - "audio": Audio-focused parsing
    - "video": Video-focused parsing

Algorithms Used:

Document Parsing:
    - PDF Parsing: pdfplumber integration (pdfplumber.PDF()) for text extraction, table extraction (pdfplumber.extract_tables()), image extraction, metadata extraction (title, author, dates via pdf.metadata), page-level processing (page iteration)
    - DOCX Parsing: python-docx integration (docx.Document()), paragraph extraction (document.paragraphs), table extraction (docx.table.Table), section/heading detection (paragraph.style), metadata extraction (core_properties), formatting extraction
    - HTML Parsing: BeautifulSoup integration (BeautifulSoup(html, 'html.parser')), text extraction (soup.get_text()), link extraction (find_all('a')), metadata extraction (meta tags), structure analysis
    - Text Parsing: Plain text file reading (open().read()), encoding detection, line-by-line processing

Web Content Parsing:
    - HTML Parsing: BeautifulSoup integration, content cleaning (soup.get_text(separator=' ', strip=True)), link extraction (find_all('a', href=True)), media extraction (find_all('img', 'video', 'audio')), JavaScript rendering support (Selenium WebDriver, Playwright)
    - XML Parsing: xml.etree.ElementTree integration (ElementTree.parse()), element traversal (iter(), findall()), attribute extraction (element.attrib), namespace handling, XPath support
    - JavaScript Rendering: Selenium WebDriver integration (webdriver.Chrome()), Playwright integration, headless browser rendering, dynamic content extraction (driver.page_source)

Structured Data Parsing:
    - JSON Parsing: json.load()/json.loads() integration, nested structure handling (recursive traversal), JSON path extraction, structure flattening, type validation
    - CSV Parsing: csv.reader()/csv.DictReader() integration, delimiter detection (csv.Sniffer()), header detection, encoding handling, type conversion
    - XML Parsing: xml.etree.ElementTree integration, element traversal (iter(), findall()), attribute extraction, namespace handling, XPath support
    - YAML Parsing: yaml.safe_load() integration, nested structure handling, type preservation

Email Parsing:
    - MIME Parsing: email.message_from_string()/message_from_bytes() integration, multipart message handling (message.is_multipart()), header decoding (email.header.decode_header()), attachment extraction (message.get_payload())
    - Header Parsing: From/To/CC/BCC extraction (message.get('From')), Subject decoding, Date parsing (email.utils.parsedate_to_datetime), Message-ID extraction
    - Body Extraction: Plain text extraction (message.get_payload(decode=True)), HTML body extraction, multipart alternative handling
    - Thread Analysis: In-Reply-To tracking (message.get('In-Reply-To')), References header analysis (message.get('References')), conversation threading

Code Parsing:
    - AST Parsing: ast.parse() integration (Python), syntax tree traversal (ast.walk()), function/class extraction (ast.FunctionDef, ast.ClassDef), import statement parsing (ast.Import, ast.ImportFrom)
    - Comment Extraction: Regex-based comment detection (# for Python, // for JavaScript, /* */ for C-style), docstring extraction (ast.get_docstring()), inline/block comment distinction
    - Dependency Analysis: Import statement parsing, dependency graph construction, cross-file dependency tracking
    - Multi-Language Support: Language-specific parsers (Python, JavaScript, Java, etc.), syntax tree analysis per language

Media Parsing:
    - Image Parsing: PIL/Pillow integration (PIL.Image.open()), EXIF data extraction (PIL.ExifTags), metadata extraction (image.format, image.size, image.mode), image analysis
    - OCR Processing: Tesseract OCR integration (pytesseract.image_to_string()), text extraction from images, confidence scoring (pytesseract.image_to_data()), language support, bounding box extraction
    - Audio/Video Parsing: Metadata extraction (format, duration, codec), file information extraction (future support)

Format-Specific Parsers:
    - PDFParser: pdfplumber.PDF() for text/tables, page iteration (pdf.pages), metadata extraction
    - DOCXParser: docx.Document() for document loading, paragraph iteration, table extraction, core_properties access
    - JSONParser: json.load()/json.loads(), recursive structure traversal, path extraction
    - CSVParser: csv.DictReader() for row-by-row processing, delimiter detection, header handling
    - XMLParser: xml.etree.ElementTree.parse(), element iteration, attribute access
    - ImageParser: PIL.Image.open(), EXIF extraction, pytesseract.image_to_string() for OCR

Key Features:
    - Multiple parsing operation methods
    - Parsing operations with method dispatch
    - Method dispatchers with registry support
    - Custom method registration capability
    - Consistent interface across all methods

Main Functions:
    - parse_document: Document parsing wrapper
    - parse_web_content: Web content parsing wrapper
    - parse_structured_data: Structured data parsing wrapper
    - parse_email: Email parsing wrapper
    - parse_code: Code parsing wrapper
    - parse_media: Media parsing wrapper
    - parse_pdf: PDF parsing wrapper
    - parse_docx: DOCX parsing wrapper
    - parse_json: JSON parsing wrapper
    - parse_csv: CSV parsing wrapper
    - parse_xml: XML parsing wrapper
    - parse_image: Image parsing wrapper
    - get_parse_method: Get parsing method by name
    - list_available_methods: List registered methods

Example Usage:
    >>> from semantica.parse.methods import parse_document, parse_web_content, parse_json
    >>> doc = parse_document("document.pdf", method="default")
    >>> web = parse_web_content("https://example.com", method="default")
    >>> data = parse_json("data.json", method="default")
"""

from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Union

from ..utils.exceptions import ConfigurationError, ProcessingError
from ..utils.logging import get_logger
from .code_parser import CodeParser
from .config import parse_config
from .csv_parser import CSVParser
from .document_parser import DocumentParser
from .docx_parser import DOCXParser
from .email_parser import EmailParser
from .image_parser import ImageParser
from .json_parser import JSONParser
from .media_parser import MediaParser
from .pdf_parser import PDFParser
from .registry import method_registry
from .structured_data_parser import StructuredDataParser
from .web_parser import WebParser
from .xml_parser import XMLParser

logger = get_logger("parse_methods")


def parse_document(
    file_path: Union[str, Path],
    file_type: Optional[str] = None,
    method: str = "default",
    **kwargs,
) -> Dict[str, Any]:
    """
    Parse document of any supported format (convenience function).

    This is a user-friendly wrapper that parses documents using the specified method.

    Args:
        file_path: Path to document file
        file_type: Document type (auto-detected if None)
        method: Parsing method (default: "default")
            - "default": Use DocumentParser with default settings
            - "pdf": PDF-focused parsing
            - "docx": DOCX-focused parsing
            - "html": HTML-focused parsing
            - "docling": Docling-based parsing for enhanced table extraction (requires docling package)
        **kwargs: Additional options passed to DocumentParser
            - extract_text: Whether to extract text (default: True)
            - extract_tables: Whether to extract tables (default: True)
            - extract_images: Whether to extract images (default: False)

    Returns:
        dict: Parsed document data

    Examples:
        >>> from semantica.parse.methods import parse_document
        >>> doc = parse_document("document.pdf", method="default")
        >>> text = parse_document("document.pdf", method="default", extract_text=True)
    """
    custom_method = method_registry.get("document", method)
    if custom_method:
        try:
            return custom_method(file_path, file_type, **kwargs)
        except Exception as e:
            logger.warning(
                f"Custom method {method} failed: {e}, falling back to default"
            )

    try:
        config = parse_config.get_method_config("document")
        config.update(kwargs)

        parser = DocumentParser(**config)
        return parser.parse_document(file_path, file_type=file_type, **kwargs)

    except Exception as e:
        logger.error(f"Failed to parse document: {e}")
        raise


def parse_document_docling(
    file_path: Union[str, Path],
    file_type: Optional[str] = None,
    **kwargs,
) -> Dict[str, Any]:
    """
    Parse document using Docling (convenience function).

    This function uses Docling for enhanced table extraction and better document
    structure understanding. Docling must be installed separately.

    Args:
        file_path: Path to document file (PDF, DOCX, PPTX, XLSX, HTML, images)
        file_type: Document type (auto-detected if None)
        **kwargs: Additional options passed to DoclingParser:
            - extract_text: Whether to extract text (default: True)
            - extract_tables: Whether to extract tables (default: True)
            - extract_images: Whether to extract images (default: False)
            - export_format: Export format ("markdown", "html", "json") (default: "markdown")
            - enable_ocr: Enable OCR for scanned documents (default: False)

    Returns:
        dict: Parsed document data

    Examples:
        >>> from semantica.parse.methods import parse_document_docling
        >>> doc = parse_document_docling("document.pdf")
        >>> tables = parse_document_docling("document.pdf", extract_tables=True)
    """
    try:
        from .docling_parser import DoclingParser
    except (ImportError, OSError):
        raise ImportError(
            "Docling is not installed. Install it with: pip install docling"
        )

    try:
        config = parse_config.get_method_config("document")
        config.update(kwargs)

        parser = DoclingParser(**config)
        return parser.parse(file_path, **kwargs)

    except Exception as e:
        logger.error(f"Failed to parse document with Docling: {e}")
        raise


# Register Docling method
try:
    from .docling_parser import DoclingParser
    method_registry.register("document", "docling", parse_document_docling)
except (ImportError, OSError):
    # Docling not available, skip registration
    pass


def parse_web_content(
    content: Union[str, Path],
    content_type: str = "html",
    base_url: Optional[str] = None,
    method: str = "default",
    **kwargs,
) -> Dict[str, Any]:
    """
    Parse web content (convenience function).

    This is a user-friendly wrapper that parses web content using the specified method.

    Args:
        content: Web content or file path
        content_type: Content type ("html", "xml")
        base_url: Base URL for resolving relative links
        method: Parsing method (default: "default")
            - "default": Use WebParser with default settings
            - "html": HTML-focused parsing
            - "xml": XML-focused parsing
            - "javascript": JavaScript-rendered content parsing
        **kwargs: Additional options passed to WebParser
            - render_javascript: Whether to render JavaScript (default: False)
            - clean: Whether to clean HTML (default: True)

    Returns:
        dict: Parsed web content data

    Examples:
        >>> from semantica.parse.methods import parse_web_content
        >>> web = parse_web_content("https://example.com", method="default")
        >>> html = parse_web_content("page.html", content_type="html", method="default")
    """
    custom_method = method_registry.get("web", method)
    if custom_method:
        try:
            return custom_method(content, content_type, base_url, **kwargs)
        except Exception as e:
            logger.warning(
                f"Custom method {method} failed: {e}, falling back to default"
            )

    try:
        config = parse_config.get_method_config("web")
        config.update(kwargs)

        parser = WebParser(**config)
        return parser.parse_web_content(
            content, content_type=content_type, base_url=base_url, **kwargs
        )

    except Exception as e:
        logger.error(f"Failed to parse web content: {e}")
        raise


def parse_structured_data(
    data: Union[str, Path],
    data_format: Optional[str] = None,
    method: str = "default",
    **kwargs,
) -> Dict[str, Any]:
    """
    Parse structured data (convenience function).

    This is a user-friendly wrapper that parses structured data using the specified method.

    Args:
        data: Data content or file path
        data_format: Data format (auto-detected if None)
        method: Parsing method (default: "default")
            - "default": Use StructuredDataParser with default settings
            - "json": JSON-focused parsing
            - "csv": CSV-focused parsing
            - "xml": XML-focused parsing
            - "yaml": YAML-focused parsing
        **kwargs: Additional options passed to StructuredDataParser
            - encoding: File encoding (default: 'utf-8')
            - delimiter: CSV delimiter (for CSV parsing)
            - flatten: Whether to flatten nested structures (for JSON)

    Returns:
        dict: Parsed data

    Examples:
        >>> from semantica.parse.methods import parse_structured_data
        >>> json_data = parse_structured_data("data.json", method="default")
        >>> csv_data = parse_structured_data("data.csv", data_format="csv", method="default")
    """
    custom_method = method_registry.get("structured", method)
    if custom_method:
        try:
            return custom_method(data, data_format, **kwargs)
        except Exception as e:
            logger.warning(
                f"Custom method {method} failed: {e}, falling back to default"
            )

    try:
        config = parse_config.get_method_config("structured")
        config.update(kwargs)

        parser = StructuredDataParser(**config)
        return parser.parse_data(data, data_format=data_format, **kwargs)

    except Exception as e:
        logger.error(f"Failed to parse structured data: {e}")
        raise


def parse_email(
    email_content: Union[str, bytes, Path], method: str = "default", **kwargs
) -> Any:
    """
    Parse email message (convenience function).

    This is a user-friendly wrapper that parses emails using the specified method.

    Args:
        email_content: Email content (string, bytes, or file path)
        method: Parsing method (default: "default")
            - "default": Use EmailParser with default settings
            - "headers": Header-only parsing
            - "body": Body-only parsing
            - "thread": Thread analysis parsing
        **kwargs: Additional options passed to EmailParser
            - extract_attachments: Whether to extract attachments (default: True)

    Returns:
        EmailData: Parsed email data

    Examples:
        >>> from semantica.parse.methods import parse_email
        >>> email = parse_email("email.eml", method="default")
        >>> headers = parse_email("email.eml", method="headers")
    """
    custom_method = method_registry.get("email", method)
    if custom_method:
        try:
            return custom_method(email_content, **kwargs)
        except Exception as e:
            logger.warning(
                f"Custom method {method} failed: {e}, falling back to default"
            )

    try:
        config = parse_config.get_method_config("email")
        config.update(kwargs)

        parser = EmailParser(**config)
        return parser.parse_email(email_content, **kwargs)

    except Exception as e:
        logger.error(f"Failed to parse email: {e}")
        raise


def parse_code(
    file_path: Union[str, Path],
    language: Optional[str] = None,
    method: str = "default",
    **kwargs,
) -> Dict[str, Any]:
    """
    Parse source code file (convenience function).

    This is a user-friendly wrapper that parses code using the specified method.

    Args:
        file_path: Path to code file
        language: Programming language (auto-detected if None)
        method: Parsing method (default: "default")
            - "default": Use CodeParser with default settings
            - "ast": AST-focused parsing
            - "comments": Comment-focused parsing
            - "dependencies": Dependency-focused parsing
        **kwargs: Additional options passed to CodeParser

    Returns:
        dict: Parsed code data

    Examples:
        >>> from semantica.parse.methods import parse_code
        >>> code = parse_code("script.py", method="default")
        >>> structure = parse_code("script.py", method="ast")
    """
    custom_method = method_registry.get("code", method)
    if custom_method:
        try:
            return custom_method(file_path, language, **kwargs)
        except Exception as e:
            logger.warning(
                f"Custom method {method} failed: {e}, falling back to default"
            )

    try:
        config = parse_config.get_method_config("code")
        config.update(kwargs)

        parser = CodeParser(**config)
        return parser.parse_code(file_path, language=language, **kwargs)

    except Exception as e:
        logger.error(f"Failed to parse code: {e}")
        raise


def parse_media(
    file_path: Union[str, Path],
    media_type: Optional[str] = None,
    method: str = "default",
    **kwargs,
) -> Dict[str, Any]:
    """
    Parse media file (convenience function).

    This is a user-friendly wrapper that parses media using the specified method.

    Args:
        file_path: Path to media file
        media_type: Media type (auto-detected if None)
        method: Parsing method (default: "default")
            - "default": Use MediaParser with default settings
            - "image": Image-focused parsing with OCR
            - "audio": Audio-focused parsing
            - "video": Video-focused parsing
        **kwargs: Additional options passed to MediaParser
            - extract_text: Whether to extract text using OCR (for images, default: False)
            - extract_metadata: Whether to extract metadata (default: True)
            - ocr_language: OCR language code (for images, default: "eng")

    Returns:
        dict: Parsed media data

    Examples:
        >>> from semantica.parse.methods import parse_media
        >>> image = parse_media("image.jpg", method="default", extract_text=True)
        >>> video = parse_media("video.mp4", method="default")
    """
    custom_method = method_registry.get("media", method)
    if custom_method:
        try:
            return custom_method(file_path, media_type, **kwargs)
        except Exception as e:
            logger.warning(
                f"Custom method {method} failed: {e}, falling back to default"
            )

    try:
        config = parse_config.get_method_config("media")
        config.update(kwargs)

        parser = MediaParser(**config)
        return parser.parse_media(file_path, media_type=media_type, **kwargs)

    except Exception as e:
        logger.error(f"Failed to parse media: {e}")
        raise


def parse_pdf(
    file_path: Union[str, Path], method: str = "default", **kwargs
) -> Dict[str, Any]:
    """
    Parse PDF document (convenience function).

    This is a user-friendly wrapper that parses PDFs using the specified method.

    Args:
        file_path: Path to PDF file
        method: Parsing method (default: "default")
        **kwargs: Additional options passed to PDFParser
            - extract_text: Whether to extract text (default: True)
            - extract_tables: Whether to extract tables (default: True)
            - extract_images: Whether to extract images (default: False)
            - pages: Specific page numbers to parse (None = all pages)

    Returns:
        dict: Parsed PDF data

    Examples:
        >>> from semantica.parse.methods import parse_pdf
        >>> pdf = parse_pdf("document.pdf", method="default")
        >>> pages = parse_pdf("document.pdf", method="default", pages=[1, 2, 3])
    """
    custom_method = method_registry.get("document", method)
    if custom_method:
        try:
            return custom_method(file_path, **kwargs)
        except Exception as e:
            logger.warning(
                f"Custom method {method} failed: {e}, falling back to default"
            )

    try:
        config = parse_config.get_method_config("document")
        config.update(kwargs)

        parser = PDFParser(**config)
        return parser.parse(file_path, **kwargs)

    except Exception as e:
        logger.error(f"Failed to parse PDF: {e}")
        raise


def parse_docx(
    file_path: Union[str, Path], method: str = "default", **kwargs
) -> Dict[str, Any]:
    """
    Parse DOCX document (convenience function).

    This is a user-friendly wrapper that parses DOCX files using the specified method.

    Args:
        file_path: Path to DOCX file
        method: Parsing method (default: "default")
        **kwargs: Additional options passed to DOCXParser
            - extract_formatting: Whether to extract formatting (default: False)
            - extract_tables: Whether to extract tables (default: True)
            - extract_comments: Whether to extract comments (default: False)

    Returns:
        dict: Parsed DOCX data

    Examples:
        >>> from semantica.parse.methods import parse_docx
        >>> docx = parse_docx("document.docx", method="default")
    """
    custom_method = method_registry.get("document", method)
    if custom_method:
        try:
            return custom_method(file_path, **kwargs)
        except Exception as e:
            logger.warning(
                f"Custom method {method} failed: {e}, falling back to default"
            )

    try:
        config = parse_config.get_method_config("document")
        config.update(kwargs)

        parser = DOCXParser(**config)
        return parser.parse(file_path, **kwargs)

    except Exception as e:
        logger.error(f"Failed to parse DOCX: {e}")
        raise


def parse_json(file_path: Union[str, Path], method: str = "default", **kwargs) -> Any:
    """
    Parse JSON file (convenience function).

    This is a user-friendly wrapper that parses JSON using the specified method.

    Args:
        file_path: Path to JSON file or JSON string
        method: Parsing method (default: "default")
        **kwargs: Additional options passed to JSONParser
            - encoding: File encoding (default: 'utf-8')
            - flatten: Whether to flatten nested structures (default: False)
            - extract_paths: Whether to extract JSON paths (default: False)

    Returns:
        JSONData: Parsed JSON data

    Examples:
        >>> from semantica.parse.methods import parse_json
        >>> json_data = parse_json("data.json", method="default")
        >>> flattened = parse_json("data.json", method="default", flatten=True)
    """
    custom_method = method_registry.get("structured", method)
    if custom_method:
        try:
            return custom_method(file_path, **kwargs)
        except Exception as e:
            logger.warning(
                f"Custom method {method} failed: {e}, falling back to default"
            )

    try:
        config = parse_config.get_method_config("structured")
        config.update(kwargs)

        parser = JSONParser(**config)
        return parser.parse(file_path, **kwargs)

    except Exception as e:
        logger.error(f"Failed to parse JSON: {e}")
        raise


def parse_csv(
    file_path: Union[str, Path], delimiter: str = ",", method: str = "default", **kwargs
) -> Any:
    """
    Parse CSV file (convenience function).

    This is a user-friendly wrapper that parses CSV using the specified method.

    Args:
        file_path: Path to CSV file
        delimiter: CSV delimiter (default: ',')
        method: Parsing method (default: "default")
        **kwargs: Additional options passed to CSVParser
            - has_header: Whether CSV has header row (default: True)
            - encoding: File encoding (default: 'utf-8')
            - skip_rows: Number of rows to skip
            - max_rows: Maximum number of rows to read

    Returns:
        CSVData: Parsed CSV data

    Examples:
        >>> from semantica.parse.methods import parse_csv
        >>> csv_data = parse_csv("data.csv", method="default")
        >>> tab_separated = parse_csv("data.tsv", delimiter="\t", method="default")
    """
    custom_method = method_registry.get("structured", method)
    if custom_method:
        try:
            return custom_method(file_path, delimiter, **kwargs)
        except Exception as e:
            logger.warning(
                f"Custom method {method} failed: {e}, falling back to default"
            )

    try:
        config = parse_config.get_method_config("structured")
        config.update(kwargs)

        parser = CSVParser(**config)
        return parser.parse(file_path, delimiter=delimiter, **kwargs)

    except Exception as e:
        logger.error(f"Failed to parse CSV: {e}")
        raise


def parse_xml(file_path: Union[str, Path], method: str = "default", **kwargs) -> Any:
    """
    Parse XML file (convenience function).

    This is a user-friendly wrapper that parses XML using the specified method.

    Args:
        file_path: Path to XML file or XML string
        method: Parsing method (default: "default")
        **kwargs: Additional options passed to XMLParser

    Returns:
        XMLData: Parsed XML data

    Examples:
        >>> from semantica.parse.methods import parse_xml
        >>> xml_data = parse_xml("data.xml", method="default")
    """
    custom_method = method_registry.get("structured", method)
    if custom_method:
        try:
            return custom_method(file_path, **kwargs)
        except Exception as e:
            logger.warning(
                f"Custom method {method} failed: {e}, falling back to default"
            )

    try:
        config = parse_config.get_method_config("structured")
        config.update(kwargs)

        parser = XMLParser(**config)
        return parser.parse(file_path, **kwargs)

    except Exception as e:
        logger.error(f"Failed to parse XML: {e}")
        raise


def parse_image(
    file_path: Union[str, Path], method: str = "default", **kwargs
) -> Dict[str, Any]:
    """
    Parse image file with OCR support (convenience function).

    This is a user-friendly wrapper that parses images using the specified method.

    Args:
        file_path: Path to image file
        method: Parsing method (default: "default")
        **kwargs: Additional options passed to ImageParser
            - extract_text: Whether to extract text using OCR (default: False)
            - ocr_language: OCR language code (default: "eng")
            - extract_metadata: Whether to extract metadata (default: True)

    Returns:
        dict: Parsed image data containing:
            - metadata: ImageMetadata object
            - ocr_result: OCRResult object (if extract_text=True)
            - text: Extracted text (if extract_text=True)

    Examples:
        >>> from semantica.parse.methods import parse_image
        >>> image = parse_image("image.jpg", method="default", extract_text=True)
        >>> ocr_text = image.get("ocr_result", {}).get("text", "")
    """
    custom_method = method_registry.get("media", method)
    if custom_method:
        try:
            return custom_method(file_path, **kwargs)
        except Exception as e:
            logger.warning(
                f"Custom method {method} failed: {e}, falling back to default"
            )

    try:
        config = parse_config.get_method_config("media")
        config.update(kwargs)

        parser = ImageParser(**config)
        return parser.parse(file_path, **kwargs)

    except Exception as e:
        logger.error(f"Failed to parse image: {e}")
        raise


def get_parse_method(task: str, name: str) -> Optional[Callable]:
    """Get parsing method by task and name."""
    return method_registry.get(task, name)


def list_available_methods(task: Optional[str] = None) -> Dict[str, List[str]]:
    """List all registered parsing methods."""
    return method_registry.list_all(task)


# Register default methods
method_registry.register("document", "default", parse_document)
method_registry.register("web", "default", parse_web_content)
method_registry.register("structured", "default", parse_structured_data)
method_registry.register("email", "default", parse_email)
method_registry.register("code", "default", parse_code)
method_registry.register("media", "default", parse_media)
