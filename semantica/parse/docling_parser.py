"""
Docling Document Parser Module

This module provides a standalone document parser that uses Docling as its core dependency.
DoclingParser is completely independent from DocumentParser and uses only:
    - docling: Core document parsing library (DocumentConverter)
    - semantica utilities: Logging, progress tracking, exceptions

Key Features:
    - Multi-format document parsing (PDF, DOCX, PPTX, XLSX, HTML, images)
    - Superior table extraction accuracy
    - Enhanced document structure understanding
    - Markdown, HTML, and JSON export formats
    - Local execution support
    - OCR support for scanned documents
    - Standalone parser - no dependency on DocumentParser

Core Dependency:
    - docling: Required for all parsing functionality

Main Classes:
    - DoclingParser: Standalone Docling-based document parser

Example Usage:
    >>> from semantica.parse import DoclingParser
    >>> parser = DoclingParser()
    >>> result = parser.parse("document.pdf")
    >>> text = parser.extract_text("document.pdf")
    >>> tables = parser.extract_tables("document.pdf")

Author: Semantica Contributors
License: MIT
"""

import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional, Union

from ..utils.exceptions import ProcessingError, ValidationError
from ..utils.helpers import safe_import
from ..utils.logging import get_logger
from ..utils.progress_tracker import get_progress_tracker

# Try to import docling, handle gracefully if not available
DOCLING_AVAILABLE = False
DOCLING_IMPORT_ERROR = None
DocumentConverter = None
InputFormat = None
PdfPipelineOptions = None
PdfFormatOption = None

try:
    from docling.document_converter import DocumentConverter, PdfFormatOption
    from docling.datamodel.base_models import InputFormat
    from docling.datamodel.pipeline_options import PdfPipelineOptions
    DOCLING_AVAILABLE = True
    DOCLING_IMPORT_ERROR = None
except (ImportError, OSError) as e:
    DOCLING_AVAILABLE = False
    DOCLING_IMPORT_ERROR = str(e)


@dataclass
class DoclingMetadata:
    """Document metadata representation from Docling."""

    title: Optional[str] = None
    author: Optional[str] = None
    subject: Optional[str] = None
    creator: Optional[str] = None
    producer: Optional[str] = None
    creation_date: Optional[str] = None
    modification_date: Optional[str] = None
    page_count: int = 0
    format: Optional[str] = None


class DoclingParser:
    """Docling-based document parser for enhanced table extraction."""

    def __init__(self, **config):
        """
        Initialize Docling parser.

        Args:
            **config: Parser configuration:
                - export_format: Export format ("markdown", "html", "json") (default: "markdown")
                - enable_ocr: Enable OCR for scanned documents (default: False)
                  Note: OCR is handled via PdfPipelineOptions if needed
        """
        self.logger = get_logger("docling_parser")
        self.config = config
        self.progress_tracker = get_progress_tracker()
        # Ensure progress tracker is enabled
        if not self.progress_tracker.enabled:
            self.progress_tracker.enabled = True

        # Store config for lazy initialization
        self.export_format = config.get("export_format", "markdown")
        self.enable_ocr = config.get("enable_ocr", False)
        self._converter = None

    def parse(self, file_path: Union[str, Path], **options) -> Dict[str, Any]:
        """
        Parse document using Docling.

        Args:
            file_path: Path to document file (PDF, DOCX, PPTX, XLSX, HTML, images)
            **options: Parsing options:
                - extract_text: Whether to extract text (default: True)
                - extract_tables: Whether to extract tables (default: True)
                - extract_images: Whether to extract images (default: False)
                - export_format: Export format ("markdown", "html", "json") (default: from config)
                - pages: Specific page numbers to parse (None = all pages) - PDF only

        Returns:
            dict: Parsed document data matching Semantica format
        """
        file_path = Path(file_path)

        # Get pipeline_id from options if provided
        pipeline_id = options.get("pipeline_id", None)
        
        # Track document parsing
        tracking_id = self.progress_tracker.start_tracking(
            file=str(file_path),
            module="parse",
            submodule="DoclingParser",
            message=f"Docling: {file_path.name}",
            pipeline_id=pipeline_id,
        )

        try:
            if not file_path.exists():
                raise ValidationError(f"Document file not found: {file_path}")

            # Check if docling is available and initialize converter lazily
            if not DOCLING_AVAILABLE:
                if DOCLING_IMPORT_ERROR:
                    raise ImportError(DOCLING_IMPORT_ERROR)
                else:
                    raise ImportError("Docling is not installed")

            # Stage 1: Initialization (0-10%)
            self.progress_tracker.update_progress(
                tracking_id,
                processed=1,
                total=10,
                message="Initializing Docling converter..."
            )

            # Lazy initialization of converter
            if self._converter is None:
                # Initialize with proper format_options if OCR is needed
                if self.enable_ocr:
                    # Configure PDF pipeline options for OCR
                    pipeline_options = PdfPipelineOptions()
                    # OCR will be automatically used when needed
                    self._converter = DocumentConverter(
                        format_options={
                            InputFormat.PDF: PdfFormatOption(pipeline_options=pipeline_options)
                        }
                    )
                else:
                    # Use default converter without special options
                    self._converter = DocumentConverter()

            # Determine export format
            export_format = options.get("export_format", self.export_format)

            # Stage 2: Document conversion (10-70%) - This is the longest step
            # Note: This is a blocking operation, but we'll update progress after it completes
            # Emphasize Docling as core dependency in message
            self.progress_tracker.update_progress(
                tracking_id,
                processed=2,
                total=10,
                message=f"Converting document with Docling (this may take a while for large PDFs)..."
            )

            # Convert document using Docling (blocking operation)
            # Store start time for ETA calculation
            conversion_start = time.time()
            result = self._converter.convert(str(file_path))
            conversion_elapsed = time.time() - conversion_start
            
            # Stage 3: Document conversion complete (70%)
            # Update progress immediately after conversion completes with timing info
            self.progress_tracker.update_progress(
                tracking_id,
                processed=7,
                total=10,
                message=f"Document conversion complete ({conversion_elapsed:.1f}s), extracting content..."
            )

            # Extract content based on export format
            extract_text = options.get("extract_text", True)
            extract_tables = options.get("extract_tables", True)
            extract_images = options.get("extract_images", False)

            # Stage 4: Text extraction (70-80%)
            if extract_text:
                self.progress_tracker.update_progress(
                    tracking_id,
                    processed=8,
                    total=10,
                    message=f"Extracting text content ({export_format} format)..."
                )

            # Get document content
            if export_format == "markdown":
                full_text = result.document.export_to_markdown()
            elif export_format == "html":
                full_text = result.document.export_to_html()
            elif export_format == "json":
                # JSON export returns structured data
                doc_dict = result.document.export_to_dict()
                full_text = self._extract_text_from_dict(doc_dict)
            else:
                full_text = result.document.export_to_markdown()

            # Stage 5: Metadata extraction (80-85%)
            self.progress_tracker.update_progress(
                tracking_id,
                processed=8,
                total=10,
                message="Extracting document metadata..."
            )
            metadata = self._extract_metadata(result, file_path)

            # Stage 6: Table extraction (85-95%)
            tables = []
            if extract_tables:
                self.progress_tracker.update_progress(
                    tracking_id,
                    processed=9,
                    total=10,
                    message="Extracting tables from document..."
                )
                tables = self._extract_tables(result, export_format)

            # Stage 7: Page extraction (95-98%)
            self.progress_tracker.update_progress(
                tracking_id,
                processed=9,
                total=10,
                message="Extracting page structure..."
            )
            pages = self._extract_pages(result, options)

            # Stage 8: Image extraction (98-100%)
            images = []
            if extract_images:
                self.progress_tracker.update_progress(
                    tracking_id,
                    processed=9,
                    total=10,
                    message="Extracting images from document..."
                )
                images = self._extract_images(result)

            # Prepare extraction counts and metadata
            extraction_counts = {
                "tables": len(tables),
                "images": len(images),
                "pages": len(pages) or metadata.page_count or 0,
            }
            
            # Build completion message with Docling emphasis
            count_parts = []
            if extraction_counts["tables"] > 0:
                count_parts.append(f"{extraction_counts['tables']} tables")
            if extraction_counts["images"] > 0:
                count_parts.append(f"{extraction_counts['images']} images")
            if extraction_counts["pages"] > 0:
                count_parts.append(f"{extraction_counts['pages']} pages")
            
            if count_parts:
                completion_message = f"Parsed document (Docling): {', '.join(count_parts)} extracted"
            else:
                completion_message = f"Parsed document (Docling): 0 tables, 0 images, {extraction_counts['pages']} pages extracted"
            
            # Store metadata with extraction counts and core dependency
            metadata_dict = {
                "extraction_counts": extraction_counts,
                "core_dependency": "docling",
            }
            
            self.progress_tracker.stop_tracking(
                tracking_id,
                status="completed",
                message=completion_message,
                metadata=metadata_dict,
            )

            return {
                "metadata": metadata.__dict__,
                "pages": pages,
                "full_text": full_text if extract_text else "",
                "tables": tables,
                "images": images,
                "total_pages": metadata.page_count,
                "export_format": export_format,
            }

        except (ImportError, OSError):
            self.progress_tracker.stop_tracking(
                tracking_id, status="failed", message="Docling not installed"
            )
            raise
        except Exception as e:
            self.progress_tracker.stop_tracking(
                tracking_id, status="failed", message=str(e)
            )
            self.logger.error(f"Failed to parse document with Docling {file_path}: {e}")
            raise ProcessingError(f"Failed to parse document with Docling: {e}")

    def extract_text(
        self, file_path: Union[str, Path], export_format: str = "markdown"
    ) -> str:
        """
        Extract text from document.

        Args:
            file_path: Path to document file
            export_format: Export format ("markdown", "html", "json")

        Returns:
            str: Extracted text
        """
        result = self.parse(
            file_path,
            extract_tables=False,
            extract_images=False,
            export_format=export_format,
        )
        return result["full_text"]

    def extract_tables(
        self, file_path: Union[str, Path], export_format: str = "markdown"
    ) -> List[Dict[str, Any]]:
        """
        Extract tables from document.

        Args:
            file_path: Path to document file
            export_format: Export format for table extraction

        Returns:
            list: Extracted tables
        """
        result = self.parse(
            file_path,
            extract_text=False,
            extract_images=False,
            export_format=export_format,
        )
        return result["tables"]

    def _extract_text_from_dict(self, doc_dict: Dict[str, Any]) -> str:
        """Extract text content from Docling dict structure."""
        text_parts = []

        def extract_from_item(item: Dict[str, Any]):
            if isinstance(item, dict):
                if item.get("type") == "text":
                    text_parts.append(item.get("text", ""))
                elif item.get("type") == "paragraph":
                    if "content" in item:
                        for content_item in item["content"]:
                            extract_from_item(content_item)
                elif "content" in item:
                    for content_item in item["content"]:
                        extract_from_item(content_item)

        if isinstance(doc_dict, dict) and "content" in doc_dict:
            for item in doc_dict["content"]:
                extract_from_item(item)

        return "\n\n".join(text_parts)

    def _extract_tables(
        self, result: Any, export_format: str
    ) -> List[Dict[str, Any]]:
        """Extract tables from Docling result using direct API access."""
        tables = []

        try:
            # Use direct API access to tables
            doc = result.document
            
            # Iterate through tables directly
            for table in doc.tables:
                try:
                    # Get table data
                    table_data_obj = table.data
                    
                    # Extract rows and columns
                    rows = []
                    
                    # Try to get table as markdown to parse rows (most reliable method)
                    try:
                        table_md = table.export_to_markdown(doc=doc)
                        
                        # Parse markdown table into rows
                        for line in table_md.strip().split('\n'):
                            if '|' in line and not line.strip().startswith('|---'):
                                # Parse markdown table row
                                cells = [cell.strip() for cell in line.split('|')[1:-1]]
                                if cells:
                                    rows.append(cells)
                    except Exception as e:
                        self.logger.debug(f"Could not extract table via markdown: {e}")
                    
                    # If markdown parsing didn't work, try dataframe export (requires pandas)
                    if not rows:
                        try:
                            import pandas as pd
                            df = table.export_to_dataframe(doc=doc)
                            rows = df.values.tolist()
                            # Convert to strings
                            rows = [[str(cell) for cell in row] for row in rows]
                        except ImportError:
                            self.logger.debug("Pandas not available for table extraction")
                        except Exception as e:
                            self.logger.debug(f"Could not extract table via dataframe: {e}")
                    
                    # If still no rows, create empty structure
                    if not rows:
                        rows = []
                    
                    # Determine page number from table provenance
                    page_number = 1
                    if hasattr(table, 'prov') and table.prov:
                        if hasattr(table.prov, 'page_no'):
                            page_number = table.prov.page_no
                        elif isinstance(table.prov, dict) and 'page_no' in table.prov:
                            page_number = table.prov['page_no']
                    
                    table_data = {
                        "rows": rows,
                        "row_count": len(rows),
                        "col_count": max(len(row) for row in rows) if rows else 0,
                        "data": rows,
                        "page_number": page_number,
                    }
                    
                    tables.append(table_data)
                    
                except Exception as e:
                    self.logger.warning(f"Error extracting table: {e}")
                    continue

        except Exception as e:
            self.logger.warning(f"Could not extract tables from Docling result: {e}")

        return tables


    def _extract_pages(self, result: Any, options: Dict[str, Any]) -> List[Dict[str, Any]]:
        """Extract pages from Docling result using direct API access."""
        pages = []

        try:
            doc = result.document
            
            # Use direct API access to pages
            # DoclingDocument.pages is a dict-like object
            if hasattr(doc, 'pages') and doc.pages:
                for page_no, page in doc.pages.items():
                    try:
                        # Extract text from page - iterate through items on this page
                        page_text_parts = []
                        page_tables = []
                        
                        # Iterate through document items to find those on this page
                        for item, level in doc.iterate_items():
                            # Check if item is on this page
                            item_page = 1
                            if hasattr(item, 'prov') and item.prov:
                                if hasattr(item.prov, 'page_no'):
                                    item_page = item.prov.page_no
                                elif isinstance(item.prov, dict) and 'page_no' in item.prov:
                                    item_page = item.prov['page_no']
                            
                            if item_page == page_no:
                                # Extract text from text items
                                if hasattr(item, 'text'):
                                    page_text_parts.append(item.text)
                                elif hasattr(item, 'export_to_markdown'):
                                    try:
                                        page_text_parts.append(item.export_to_markdown(doc=doc))
                                    except Exception:
                                        pass  # export failure degrades to skipping this text item
                                
                                # Extract tables on this page
                                from docling_core.types.doc import TableItem
                                if isinstance(item, TableItem):
                                    # Get table data for this page
                                    table_data = self._extract_single_table(item, doc, page_no)
                                    if table_data:
                                        page_tables.append(table_data)
                        
                        # Get page dimensions
                        width = 0
                        height = 0
                        if hasattr(page, 'size'):
                            if hasattr(page.size, 'width'):
                                width = page.size.width
                            if hasattr(page.size, 'height'):
                                height = page.size.height
                        
                        pages.append({
                            "page_number": page_no,
                            "text": "\n".join(page_text_parts).strip(),
                            "width": width,
                            "height": height,
                            "tables": page_tables,
                            "images": [],
                        })
                    except Exception as e:
                        self.logger.warning(f"Error extracting page {page_no}: {e}")
                        continue
            
            # Fallback: if no pages found, use ConversionResult.pages or create single page
            if not pages:
                # Try to use result.pages (list of Page objects)
                if hasattr(result, 'pages') and result.pages:
                    for page_obj in result.pages:
                        pages.append({
                            "page_number": getattr(page_obj, 'page_no', len(pages) + 1),
                            "text": "",
                            "width": getattr(page_obj.size, 'width', 0) if hasattr(page_obj, 'size') else 0,
                            "height": getattr(page_obj.size, 'height', 0) if hasattr(page_obj, 'size') else 0,
                            "tables": [],
                            "images": [],
                        })
                
                # If still no pages, create a single page from full content
                if not pages:
                    try:
                        full_text = doc.export_to_markdown()
                        pages.append({
                            "page_number": 1,
                            "text": full_text,
                            "width": 0,
                            "height": 0,
                            "tables": [],
                            "images": [],
                        })
                    except:
                        pages.append({
                            "page_number": 1,
                            "text": "",
                            "width": 0,
                            "height": 0,
                            "tables": [],
                            "images": [],
                        })

        except Exception as e:
            self.logger.warning(f"Could not extract pages from Docling result: {e}")
            # Fallback: create single page
            try:
                full_text = result.document.export_to_markdown()
                pages.append({
                    "page_number": 1,
                    "text": full_text,
                    "width": 0,
                    "height": 0,
                    "tables": [],
                    "images": [],
                })
            except:
                pages.append({
                    "page_number": 1,
                    "text": "",
                    "width": 0,
                    "height": 0,
                    "tables": [],
                    "images": [],
                })

        return pages
    
    def _extract_single_table(self, table_item: Any, doc: Any, page_no: int) -> Optional[Dict[str, Any]]:
        """Extract a single table item to dict format."""
        try:
            # Get table data
            table_data_obj = table_item.data
            
            # Extract rows
            rows = []
            try:
                # Try markdown export first (most reliable)
                table_md = table_item.export_to_markdown(doc=doc)
                for line in table_md.strip().split('\n'):
                    if '|' in line and not line.strip().startswith('|---'):
                        cells = [cell.strip() for cell in line.split('|')[1:-1]]
                        if cells:
                            rows.append(cells)
            except Exception as e:
                self.logger.debug(f"Could not extract table via markdown: {e}")
                # Fallback: try dataframe export (requires pandas)
                try:
                    import pandas as pd
                    df = table_item.export_to_dataframe(doc=doc)
                    rows = df.values.tolist()
                    rows = [[str(cell) for cell in row] for row in rows]
                except ImportError:
                    self.logger.debug("Pandas not available for table extraction")
                except Exception as e2:
                    self.logger.debug(f"Could not extract table via dataframe: {e2}")
            
            if rows:
                return {
                    "rows": rows,
                    "row_count": len(rows),
                    "col_count": max(len(row) for row in rows) if rows else 0,
                    "data": rows,
                    "page_number": page_no,
                }
        except Exception as e:
            self.logger.warning(f"Error extracting single table: {e}")
        
        return None

    def _extract_images(self, result: Any) -> List[Dict[str, Any]]:
        """Extract images/pictures from Docling result using direct API access."""
        images = []

        try:
            doc = result.document
            
            # Use direct API access to pictures
            # DoclingDocument.pictures is iterable
            if hasattr(doc, 'pictures') and doc.pictures:
                for picture in doc.pictures:
                    try:
                        # Get page number from provenance
                        page_number = 1
                        if hasattr(picture, 'prov') and picture.prov:
                            if hasattr(picture.prov, 'page_no'):
                                page_number = picture.prov.page_no
                            elif isinstance(picture.prov, dict) and 'page_no' in picture.prov:
                                page_number = picture.prov['page_no']
                        
                        # Get bounding box
                        x0, y0, x1, y1 = 0, 0, 0, 0
                        width, height = 0, 0
                        
                        if hasattr(picture, 'bbox'):
                            bbox = picture.bbox
                            if hasattr(bbox, 'x0'):
                                x0 = bbox.x0
                            if hasattr(bbox, 'y0'):
                                y0 = bbox.y0
                            if hasattr(bbox, 'x1'):
                                x1 = bbox.x1
                            if hasattr(bbox, 'y1'):
                                y1 = bbox.y1
                        elif isinstance(picture.bbox, dict):
                            x0 = picture.bbox.get('x0', 0)
                            y0 = picture.bbox.get('y0', 0)
                            x1 = picture.bbox.get('x1', 0)
                            y1 = picture.bbox.get('y1', 0)
                        
                        # Get dimensions
                        if hasattr(picture, 'size'):
                            if hasattr(picture.size, 'width'):
                                width = picture.size.width
                            if hasattr(picture.size, 'height'):
                                height = picture.size.height
                        elif hasattr(picture, 'width'):
                            width = picture.width
                        elif hasattr(picture, 'height'):
                            height = picture.height
                        
                        img_data = {
                            "page_number": page_number,
                            "x0": x0,
                            "y0": y0,
                            "x1": x1,
                            "y1": y1,
                            "width": width,
                            "height": height,
                        }
                        images.append(img_data)
                    except Exception as e:
                        self.logger.warning(f"Error extracting picture: {e}")
                        continue

        except Exception as e:
            self.logger.warning(f"Could not extract images from Docling result: {e}")

        return images

    def _extract_metadata(self, result: Any, file_path: Path) -> DoclingMetadata:
        """Extract metadata from Docling result using direct API access."""
        metadata = DoclingMetadata()

        try:
            doc = result.document
            
            # Extract format
            metadata.format = file_path.suffix.lower().lstrip('.')

            # Extract page count using direct API
            if hasattr(doc, 'pages') and doc.pages:
                metadata.page_count = len(doc.pages)
            elif hasattr(result, 'pages') and result.pages:
                metadata.page_count = len(result.pages)
            else:
                metadata.page_count = 1

            # Try to extract other metadata if available
            # Docling may not provide all metadata fields directly
            # These would need to be extracted from the original document if available
            if hasattr(doc, 'name'):
                metadata.title = doc.name

        except Exception as e:
            self.logger.warning(f"Could not extract metadata from Docling result: {e}")
            metadata.page_count = 1
            metadata.format = file_path.suffix.lower().lstrip('.')

        return metadata

