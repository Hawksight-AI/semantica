"""
PDF Document Parser Module

This module handles PDF document parsing using pdfplumber for text,
table, and image extraction, including metadata and page-level processing.

Key Features:
    - PDF text extraction
    - Table extraction from PDFs
    - Image extraction
    - Metadata extraction (title, author, dates)
    - Page-level processing
    - Multi-page document support

Main Classes:
    - PDFParser: PDF document parser
    - PDFPage: Dataclass for PDF page representation
    - PDFMetadata: Dataclass for PDF metadata representation

Example Usage:
    >>> from semantica.parse import PDFParser
    >>> parser = PDFParser()
    >>> text = parser.parse("document.pdf")
    >>> pages = parser.extract_pages("document.pdf")
    >>> metadata = parser.extract_metadata("document.pdf")

Author: Semantica Contributors
License: MIT
"""

import io
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional, Union

from ..utils.exceptions import ProcessingError, ValidationError
from ..utils.logging import get_logger
from ..utils.progress_tracker import get_progress_tracker


@dataclass
class PDFPage:
    """PDF page representation."""

    page_number: int
    text: str
    width: float
    height: float
    images: List[Dict[str, Any]] = field(default_factory=list)
    tables: List[Dict[str, Any]] = field(default_factory=list)


@dataclass
class PDFMetadata:
    """PDF metadata representation."""

    title: Optional[str] = None
    author: Optional[str] = None
    subject: Optional[str] = None
    creator: Optional[str] = None
    producer: Optional[str] = None
    creation_date: Optional[str] = None
    modification_date: Optional[str] = None
    page_count: int = 0


class PDFParser:
    """PDF document parser."""

    def __init__(self, **config):
        """
        Initialize PDF parser.

        Args:
            **config: Parser configuration
        """
        self.logger = get_logger("pdf_parser")
        self.config = config
        self.progress_tracker = get_progress_tracker()
        # Ensure progress tracker is enabled
        if not self.progress_tracker.enabled:
            self.progress_tracker.enabled = True

    def parse(self, file_path: Union[str, Path], pipeline_id: Optional[str] = None, **options) -> Dict[str, Any]:
        """
        Parse PDF document.

        Args:
            file_path: Path to PDF file
            pipeline_id: Optional pipeline ID for progress tracking
            **options: Parsing options:
                - extract_text: Whether to extract text (default: True)
                - extract_tables: Whether to extract tables (default: True)
                - extract_images: Whether to extract images (default: False)
                - pages: Specific page numbers to parse (None = all pages)

        Returns:
            dict: Parsed PDF data
        """
        file_path = Path(file_path)

        # Track PDF parsing
        tracking_id = self.progress_tracker.start_tracking(
            file=str(file_path),
            module="parse",
            submodule="PDFParser",
            message=f"PDF: {file_path.name}",
            pipeline_id=pipeline_id,
        )

        try:
            if not file_path.exists():
                raise ValidationError(f"PDF file not found: {file_path}")

            if not file_path.suffix.lower() == ".pdf":
                raise ValidationError(f"File is not a PDF: {file_path}")

            try:
                try:
                    import pdfplumber
                except ImportError:
                    raise ProcessingError(
                        "pdfplumber is required for PDF parsing. "
                        "Install with: pip install pdfplumber"
                    )
                with pdfplumber.open(str(file_path)) as pdf:
                    # Extract metadata
                    metadata = self._extract_metadata(pdf)
                    metadata.page_count = len(pdf.pages)

                    # Extract pages
                    pages = []
                    page_numbers = options.get("pages", range(len(pdf.pages)))

                    self.progress_tracker.update_tracking(
                        tracking_id, message=f"Parsing {len(pdf.pages)} pages"
                    )

                    for page_num in page_numbers:
                        if page_num < len(pdf.pages):
                            page_data = self._parse_page(
                                pdf.pages[page_num], page_num + 1, options
                            )
                            pages.append(page_data)

                    self.progress_tracker.stop_tracking(
                        tracking_id,
                        status="completed",
                        message=f"Parsed {len(pages)} pages",
                    )
                    return {
                        "metadata": metadata.__dict__,
                        "pages": [page.__dict__ for page in pages],
                        "full_text": "\n\n".join(page.text for page in pages),
                        "total_pages": len(pdf.pages),
                    }

            except Exception as e:
                self.progress_tracker.stop_tracking(
                    tracking_id, status="failed", message=str(e)
                )
                self.logger.error(f"Failed to parse PDF {file_path}: {e}")
                raise ProcessingError(f"Failed to parse PDF: {e}")

        except Exception as e:
            self.progress_tracker.stop_tracking(
                tracking_id, status="failed", message=str(e)
            )
            raise

    def extract_text(
        self, file_path: Union[str, Path], pages: Optional[List[int]] = None
    ) -> str:
        """
        Extract text from PDF.

        Args:
            file_path: Path to PDF file
            pages: Specific page numbers (None = all pages)

        Returns:
            str: Extracted text
        """
        result = self.parse(
            file_path, extract_tables=False, extract_images=False, pages=pages
        )
        return result["full_text"]

    def extract_tables(
        self, file_path: Union[str, Path], pages: Optional[List[int]] = None
    ) -> List[Dict[str, Any]]:
        """
        Extract tables from PDF.

        Args:
            file_path: Path to PDF file
            pages: Specific page numbers (None = all pages)

        Returns:
            list: Extracted tables
        """
        result = self.parse(
            file_path, extract_text=False, extract_images=False, pages=pages
        )

        all_tables = []
        for page in result["pages"]:
            for table in page.get("tables", []):
                table["page_number"] = page["page_number"]
                all_tables.append(table)

        return all_tables

    def extract_images(
        self, file_path: Union[str, Path], output_dir: Optional[Path] = None
    ) -> List[Dict[str, Any]]:
        """
        Extract images from PDF.

        Args:
            file_path: Path to PDF file
            output_dir: Directory to save extracted images

        Returns:
            list: Extracted image information
        """
        result = self.parse(
            file_path, extract_text=False, extract_tables=False, extract_images=True
        )

        all_images = []
        for page in result["pages"]:
            for img in page.get("images", []):
                img["page_number"] = page["page_number"]
                all_images.append(img)

        return all_images

    def _parse_page(self, page, page_number: int, options: Dict[str, Any]) -> PDFPage:
        """Parse individual PDF page."""
        page_data = PDFPage(
            page_number=page_number, text="", width=page.width, height=page.height
        )

        # Extract text
        if options.get("extract_text", True):
            page_data.text = page.extract_text() or ""

        # Extract tables
        if options.get("extract_tables", True):
            tables = page.extract_tables()
            if tables:
                page_data.tables = [
                    {
                        "data": table,
                        "bbox": None,  # pdfplumber doesn't provide bbox for tables directly
                    }
                    for table in tables
                ]

        # Extract images
        if options.get("extract_images", False):
            images = page.images
            if images:
                page_data.images = [
                    {
                        "x0": img.get("x0", 0),
                        "y0": img.get("y0", 0),
                        "x1": img.get("x1", 0),
                        "y1": img.get("y1", 0),
                        "width": img.get("width", 0),
                        "height": img.get("height", 0),
                    }
                    for img in images
                ]

        return page_data

    def _extract_metadata(self, pdf) -> PDFMetadata:
        """Extract PDF metadata."""
        metadata = pdf.metadata or {}

        return PDFMetadata(
            title=metadata.get("Title"),
            author=metadata.get("Author"),
            subject=metadata.get("Subject"),
            creator=metadata.get("Creator"),
            producer=metadata.get("Producer"),
            creation_date=str(metadata.get("CreationDate", "")),
            modification_date=str(metadata.get("ModDate", "")),
        )
