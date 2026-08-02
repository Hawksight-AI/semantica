"""
Data Parsing Module

This module provides comprehensive data parsing capabilities for various file formats,
enabling extraction of text, metadata, and structured data from documents, web content,
emails, code files, and media files.

Algorithms Used:

Document Parsing:
    - PDF Parsing: pdfplumber integration (pdfplumber.PDF()) for text extraction, table extraction (pdfplumber.extract_tables()), image extraction, metadata extraction (title, author, dates via pdf.metadata), page-level processing (page iteration)
    - DOCX Parsing: python-docx integration (docx.Document()), paragraph extraction (document.paragraphs), table extraction (docx.table.Table), section/heading detection (paragraph.style), metadata extraction (core_properties), formatting extraction
    - Docling Parsing: Docling integration (DocumentConverter.convert()) for enhanced table extraction and document structure understanding, supports PDF, DOCX, PPTX, XLSX, HTML, images, markdown/HTML/JSON export formats, OCR support (optional dependency)
    - PPTX Parsing: python-pptx integration (pptx.Presentation()), slide extraction (presentation.slides), shape extraction, notes extraction, metadata extraction
    - Excel Parsing: openpyxl integration (openpyxl.load_workbook()), pandas integration (pandas.read_excel()), sheet iteration, cell value extraction, formula extraction, metadata extraction
    - HTML Parsing: BeautifulSoup integration (BeautifulSoup(html, 'html.parser')), text extraction (soup.get_text()), link extraction (find_all('a')), metadata extraction (meta tags), structure analysis
    - Text Parsing: Plain text file reading (open().read()), encoding detection, line-by-line processing

Web Content Parsing:
    - HTML Parsing: BeautifulSoup integration, content cleaning (soup.get_text(separator=' ', strip=True)), link extraction (find_all('a', href=True)), media extraction (find_all('img', 'video', 'audio')), JavaScript rendering support (Selenium WebDriver, Playwright)
    - XML Parsing: xml.etree.ElementTree integration (ElementTree.parse()), lxml integration (lxml.etree.parse()), element traversal (iter(), findall()), attribute extraction (element.attrib), namespace handling, XPath support
    - JavaScript Rendering: Selenium WebDriver integration (webdriver.Chrome()), Playwright integration, headless browser rendering, dynamic content extraction (driver.page_source)

Structured Data Parsing:
    - JSON Parsing: json.load()/json.loads() integration, nested structure handling (recursive traversal), JSON path extraction, structure flattening, type validation
    - CSV Parsing: csv.reader()/csv.DictReader() integration, delimiter detection (csv.Sniffer()), header detection, encoding handling, type conversion
    - XML Parsing: xml.etree.ElementTree integration, lxml integration, element traversal (iter(), findall()), attribute extraction, namespace handling, XPath support
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
    - DoclingParser: DocumentConverter.convert() for multi-format parsing with enhanced table extraction, supports PDF/DOCX/PPTX/XLSX/HTML/images, markdown/HTML/JSON export (optional dependency)
    - PPTXParser: pptx.Presentation() for presentation loading, slide iteration, shape extraction
    - ExcelParser: openpyxl.load_workbook() for workbook loading, pandas.read_excel() for data extraction, sheet iteration
    - HTMLParser: BeautifulSoup() for HTML parsing, element traversal, metadata extraction
    - JSONParser: json.load()/json.loads(), recursive structure traversal, path extraction
    - CSVParser: csv.DictReader() for row-by-row processing, delimiter detection, header handling
    - XMLParser: xml.etree.ElementTree.parse(), lxml.etree.parse(), element iteration, attribute access
    - ImageParser: PIL.Image.open(), EXIF extraction, pytesseract.image_to_string() for OCR

Key Features:
    - Document format parsing (PDF, DOCX, PPTX, HTML, TXT)
    - Web content parsing (HTML, XML, JavaScript-rendered content)
    - Structured data parsing (JSON, CSV, XML, YAML)
    - Email content parsing (headers, body, attachments, threads)
    - Source code parsing (multi-language, syntax trees, dependencies)
    - Media content parsing (images with OCR, audio, video metadata)
    - Batch processing support
    - Metadata extraction
    - Content structure analysis
    - Method registry for custom parsing methods
    - Configuration management via environment variables and config files

Main Classes:
    - DocumentParser: Document format parsing (PDF, DOCX, PPTX, HTML, TXT)
    - WebParser: Web content parsing (HTML, XML, JavaScript-rendered)
    - StructuredDataParser: Structured data parsing (JSON, CSV, XML, YAML)
    - EmailParser: Email content parsing (headers, body, attachments, threads)
    - CodeParser: Source code parsing (multi-language, AST, comments, dependencies)
    - MediaParser: Media content parsing (images, audio, video)
    - PDFParser: PDF document parser with text, table, and image extraction
    - DOCXParser: Word document parser with structure and metadata extraction
    - PPTXParser: PowerPoint parser with slide and notes extraction
    - DoclingParser: Docling-based parser for enhanced table extraction (optional, requires docling package)
    - ExcelParser: Excel spreadsheet parser with multi-sheet support
    - HTMLParser: HTML document parser with metadata and link extraction
    - JSONParser: JSON data parser with nested structure handling
    - CSVParser: CSV data parser with delimiter detection and type conversion
    - XMLParser: XML document parser with namespace and XPath support
    - ImageParser: Image file parser with OCR and metadata extraction
    - MethodRegistry: Registry for custom parsing methods
    - ParseConfig: Configuration manager for parsing operations

Convenience Functions:
    - parse_document: Parse any document format (PDF, DOCX, HTML, TXT)
    - parse_web_content: Parse web content (HTML, XML, JavaScript-rendered)
    - parse_structured_data: Parse structured data (JSON, CSV, XML, YAML)
    - parse_email: Parse email messages (headers, body, attachments)
    - parse_code: Parse source code files (multi-language, AST, comments)
    - parse_media: Parse media files (images with OCR, audio, video)
    - parse_pdf: Parse PDF documents
    - parse_docx: Parse DOCX documents
    - parse_json: Parse JSON files
    - parse_csv: Parse CSV files
    - parse_xml: Parse XML files
    - parse_image: Parse image files with OCR
    - get_parse_method: Get parsing method by task and name
    - list_available_methods: List registered parsing methods

Example Usage:
    >>> from semantica.parse import parse_document, parse_web_content, parse_json
    >>> doc = parse_document("document.pdf", method="default")
    >>> web = parse_web_content("https://example.com", method="default")
    >>> data = parse_json("data.json", method="default")
    
    >>> from semantica.parse import DocumentParser, WebParser, StructuredDataParser
    >>> doc_parser = DocumentParser()
    >>> text = doc_parser.parse_document("document.pdf")
    >>> web_parser = WebParser()
    >>> content = web_parser.parse_html("https://example.com")
    >>> data_parser = StructuredDataParser()
    >>> data = data_parser.parse_json("data.json")

Author: Semantica Contributors
License: MIT
"""

from .code_parser import (
    CodeComment,
    CodeParser,
    CodeStructure,
    CommentExtractor,
    DependencyAnalyzer,
    SyntaxTreeParser,
)
from .config import ParseConfig, parse_config
from .csv_parser import CSVData, CSVParser
from .document_parser import DocumentParser
from .docx_parser import DocxMetadata, DOCXParser, DocxSection
from .email_parser import (
    EmailBody,
    EmailData,
    EmailHeaders,
    EmailParser,
    EmailThreadAnalyzer,
    MIMEParser,
)
from .excel_parser import ExcelData, ExcelParser, ExcelSheet
from .html_parser import HTMLElement, HTMLMetadata, HTMLParser
from .image_parser import ImageMetadata, ImageParser, OCRResult
from .json_parser import JSONData, JSONParser
from .mcp_parser import MCPParser
from .media_parser import MediaParser
from .methods import (
    get_parse_method,
    list_available_methods,
    parse_code,
    parse_csv,
    parse_document,
    parse_docx,
    parse_email,
    parse_image,
    parse_json,
    parse_media,
    parse_pdf,
    parse_structured_data,
    parse_web_content,
    parse_xml,
)
from .pdf_parser import PDFMetadata, PDFPage, PDFParser
from .pptx_parser import PPTXData, PPTXParser, SlideContent

# Try to import DoclingParser (optional dependency)
# First check if docling_parser module can be imported and get DOCLING_AVAILABLE
DOCLING_AVAILABLE = False
DoclingParser = None
DoclingMetadata = None
DOCLING_IMPORT_ERROR = None

try:
    # Import the module first to check DOCLING_AVAILABLE
    from . import docling_parser
    DOCLING_AVAILABLE = getattr(docling_parser, 'DOCLING_AVAILABLE', False)
    DOCLING_IMPORT_ERROR = getattr(docling_parser, 'DOCLING_IMPORT_ERROR', None)
    
    # Only import classes if docling is available
    if DOCLING_AVAILABLE:
        from .docling_parser import DoclingParser, DoclingMetadata
    else:
        # Create placeholder classes that raise helpful errors
        import_error_msg = DOCLING_IMPORT_ERROR
        
        class DoclingParser:
            """Placeholder for DoclingParser when docling is not available."""
            def __init__(self, **config):
                error_msg = "DoclingParser requires the 'docling' package to be installed and working."
                if import_error_msg:
                    error_msg += f"\n\nError: {import_error_msg}"
                error_msg += "\n\nInstall it with: pip install docling"
                raise ImportError(error_msg)
        
        class DoclingMetadata:
            """Placeholder for DoclingMetadata when docling is not available."""
            def __init__(self, **kwargs):
                error_msg = "DoclingMetadata requires the 'docling' package to be installed and working."
                if import_error_msg:
                    error_msg += f"\n\nError: {import_error_msg}"
                error_msg += "\n\nInstall it with: pip install docling"
                raise ImportError(error_msg)
except (ImportError, OSError, AttributeError) as e:
    # If import fails, docling is not available
    DOCLING_AVAILABLE = False
    import_error_msg = str(e)
    DOCLING_IMPORT_ERROR = import_error_msg
    
    # Create placeholder classes that raise helpful errors
    class DoclingParser:
        """Placeholder for DoclingParser when docling is not available."""
        def __init__(self, **config):
            error_msg = "DoclingParser requires the 'docling' package to be installed and working."
            if import_error_msg:
                error_msg += f"\n\nError: {import_error_msg}"
            error_msg += "\n\nInstall it with: pip install docling"
            raise ImportError(error_msg)
    
    class DoclingMetadata:
        """Placeholder for DoclingMetadata when docling is not available."""
        def __init__(self, **kwargs):
            error_msg = "DoclingMetadata requires the 'docling' package to be installed and working."
            if import_error_msg:
                error_msg += f"\n\nError: {import_error_msg}"
            error_msg += "\n\nInstall it with: pip install docling"
            raise ImportError(error_msg)
from .registry import MethodRegistry, method_registry
from .structured_data_parser import StructuredDataParser
from .web_parser import HTMLContentParser, JavaScriptRenderer, WebParser
from .xml_parser import XMLData, XMLElement, XMLParser

__all__ = [
    # Main parsers
    "DocumentParser",
    "WebParser",
    "HTMLContentParser",
    "JavaScriptRenderer",
    "StructuredDataParser",
    "EmailParser",
    "EmailHeaders",
    "EmailBody",
    "EmailData",
    "MIMEParser",
    "EmailThreadAnalyzer",
    "CodeParser",
    "CodeStructure",
    "CodeComment",
    "SyntaxTreeParser",
    "CommentExtractor",
    "DependencyAnalyzer",
    "MediaParser",
    # Format-specific parsers
    "PDFParser",
    "PDFPage",
    "PDFMetadata",
    "DOCXParser",
    "DocxSection",
    "DocxMetadata",
    "PPTXParser",
    "SlideContent",
    "PPTXData",
    "ExcelParser",
    "ExcelSheet",
    "ExcelData",
    "HTMLParser",
    "HTMLMetadata",
    "HTMLElement",
    "JSONParser",
    "JSONData",
    "CSVParser",
    "CSVData",
    "XMLParser",
    "XMLElement",
    "XMLData",
    "ImageParser",
    "ImageMetadata",
    "OCRResult",
    # MCP parsing
    "MCPParser",
    # Registry and config
    "MethodRegistry",
    "method_registry",
    "ParseConfig",
    "parse_config",
    # Convenience functions
    "parse_document",
    "parse_web_content",
    "parse_structured_data",
    "parse_email",
    "parse_code",
    "parse_media",
    "parse_pdf",
    "parse_docx",
    "parse_json",
    "parse_csv",
    "parse_xml",
    "parse_image",
    "get_parse_method",
    "list_available_methods",
]

# Conditionally add DoclingParser to exports if available
# Always add to __all__ so import doesn't fail, but classes will be None if not available
__all__.extend(["DoclingParser", "DoclingMetadata"])
