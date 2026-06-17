---
title: "Docling Integration"
description: "Native Docling integration for high-fidelity PDF, DOCX, and PPTX parsing with table extraction and OCR."
icon: "file-lines"
---

> Parse complex documents: PDFs, DOCX, PPTX, HTML: with high-fidelity table extraction and built-in OCR.


## Overview

Docling is integrated into Semantica's `parse` module via the **`DoclingParser`**. Documents pass through Docling's **layout engine**, then feed directly into Semantica's extraction and KG pipeline.

- **Multi-format** — PDF, DOCX, PPTX, HTML, and more.
- **Table Extraction** — High-fidelity table parsing with header detection.
- **OCR Support** — Built-in OCR for scanned documents.
- **Markdown Export** — Clean Markdown output optimized for LLM consumption.


## Installation

```bash
pip install semantica
# Docling is included as an optional dependency
# or install separately:
pip install docling
```


## Basic Usage

```python
from semantica.parse import DoclingParser

parser = DoclingParser(enable_ocr=True)
result = parser.parse("financial_report.pdf")

print(result["full_text"][:200])
print(f"Found {len(result['tables'])} tables")
```


## Full Example

```python
from semantica.parse import DoclingParser

parser = DoclingParser(
    enable_ocr=True,
    export_format="markdown",
)

result = parser.parse("complex_invoice.pdf")

# Full text content
print(result["full_text"])

# Extracted tables
for i, table in enumerate(result["tables"]):
    print(f"Table {i+1} headers: {table.get('headers', [])}")
    for row in table.get("rows", [])[:3]:
        print(f"  Row: {row}")

# Metadata
metadata = result["metadata"]
print(f"Title: {metadata.get('title')}")
print(f"Pages: {result.get('total_pages')}")
```


## DoclingParser Parameters

| Parameter | Default | Description |
| :----------- | :--------- | :------------- |
| `enable_ocr` | `False` | Enable OCR for scanned pages |
| `export_format` | `"markdown"` | Output format: `"markdown"` or `"text"` |


## Parsed Result Structure

```python
{
    "full_text":    str,         # Clean document text
    "tables":       List[dict],  # Extracted tables (headers + rows)
    "metadata":     dict,        # Title, author, creation date, etc.
    "total_pages":  int,
}
```


## See Also

- [Parse Module](../reference/parse) — Full DocumentParser and DoclingParser reference.
- [Ingest Module](../reference/ingest) — Loading documents before parsing.
- [Semantic Extract](../reference/semantic_extract) — NER and relation extraction on parsed text.
- [Pipeline](../reference/pipeline) — Using DoclingParser in a full pipeline.
