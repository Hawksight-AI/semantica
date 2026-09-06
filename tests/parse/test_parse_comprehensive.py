import unittest
from unittest.mock import MagicMock, patch, mock_open
import tempfile
import os
import json
import csv
import sys
from pathlib import Path

import pytest

from semantica.parse.document_parser import DocumentParser, PDFParser, DOCXParser, HTMLParser
from semantica.parse.pptx_parser import PPTXParser
from semantica.parse.excel_parser import ExcelParser
from semantica.parse.structured_data_parser import StructuredDataParser, JSONParser, CSVParser, XMLParser
from semantica.parse.email_parser import EmailParser
from semantica.parse.code_parser import CodeParser
from semantica.parse.media_parser import MediaParser, ImageParser
from semantica.parse.web_parser import WebParser
from semantica.parse.registry import MethodRegistry
from semantica.parse.config import ParseConfig

pytestmark = pytest.mark.integration

class TestParseComprehensive(unittest.TestCase):

    def setUp(self):
        # Common mocks
        self.mock_logger = MagicMock()
        self.mock_tracker = MagicMock()
        
        # Patch loggers and trackers
        self.patchers = []
        modules_to_patch = [
            'semantica.parse.document_parser',
            'semantica.parse.structured_data_parser',
            'semantica.parse.email_parser',
            'semantica.parse.code_parser',
            'semantica.parse.media_parser',
            'semantica.parse.web_parser',
            'semantica.parse.pdf_parser',
            'semantica.parse.docx_parser',
            'semantica.parse.pptx_parser',
            'semantica.parse.excel_parser',
            'semantica.parse.html_parser',
            'semantica.parse.json_parser',
            'semantica.parse.csv_parser',
            'semantica.parse.xml_parser',
            'semantica.parse.image_parser'
        ]
        
        for module_name in modules_to_patch:
            # Patch get_logger
            try:
                p1 = patch(f'{module_name}.get_logger', return_value=self.mock_logger)
                p1.start()
                self.patchers.append(p1)
            except AttributeError:
                pass

            # Patch get_progress_tracker
            # Check if module has get_progress_tracker before patching to avoid AttributeError
            try:
                # We need to import the module to check attributes
                mod = __import__(module_name, fromlist=['get_progress_tracker'])
                if hasattr(mod, 'get_progress_tracker'):
                    p2 = patch(f'{module_name}.get_progress_tracker', return_value=self.mock_tracker)
                    p2.start()
                    self.patchers.append(p2)
            except ImportError:
                pass

    def tearDown(self):
        for p in self.patchers:
            p.stop()

    # --- Structured Data Parser Tests ---

    def test_json_parser(self):
        parser = JSONParser()
        data = {'key': 'value', 'list': [1, 2, 3]}
        
        with tempfile.NamedTemporaryFile(mode='w', delete=False, suffix='.json') as tmp:
            json.dump(data, tmp)
            tmp_path = tmp.name
            
        try:
            result = parser.parse(tmp_path)
            self.assertEqual(result.data['key'], 'value')
            self.assertEqual(result.data['list'], [1, 2, 3])
            # Metadata depends on implementation, source/type are likely keys
            self.assertIn('source', result.metadata)
            self.assertIn('type', result.metadata)
        finally:
            os.remove(tmp_path)

    def test_csv_parser(self):
        parser = CSVParser()
        rows = [['name', 'age'], ['Alice', '30'], ['Bob', '25']]
        
        with tempfile.NamedTemporaryFile(mode='w', delete=False, suffix='.csv', newline='') as tmp:
            writer = csv.writer(tmp)
            writer.writerows(rows)
            tmp_path = tmp.name
            
        try:
            result = parser.parse(tmp_path)
            # CSVData has rows attribute
            self.assertEqual(len(result.rows), 2) # Header is not data
            self.assertEqual(result.rows[0]['name'], 'Alice')
            self.assertEqual(result.rows[1]['age'], '25')
        finally:
            os.remove(tmp_path)

    def test_xml_parser(self):
        parser = XMLParser()
        xml_content = """<?xml version="1.0"?>
        <root>
            <person>
                <name>Alice</name>
                <age>30</age>
            </person>
        </root>
        """
        
        with tempfile.NamedTemporaryFile(mode='w', delete=False, suffix='.xml') as tmp:
            tmp.write(xml_content)
            tmp_path = tmp.name
            
        try:
            result = parser.parse(tmp_path)
            # XMLData has root attribute
            self.assertIsNotNone(result.root)
            self.assertEqual(result.root.tag, 'root')
            # Check children if accessible or logic
        finally:
            os.remove(tmp_path)

    # --- Document Parser Tests ---
    
    def test_pdf_parser(self):
        parser = PDFParser()
        # pdfplumber is imported inside PDFParser.parse, so inject a fake
        # module into sys.modules instead of patching a module attribute
        mock_pdfplumber = MagicMock()
        mock_pdf = MagicMock()
        mock_page = MagicMock()
        mock_page.extract_text.return_value = "Page text"
        mock_pdf.pages = [mock_page]
        # Ensure metadata is a dict, not a property object if that's an issue
        mock_pdf.metadata = {"Title": "Test PDF"}

        # Setup the context manager
        mock_context_manager = MagicMock()
        mock_context_manager.__enter__.return_value = mock_pdf
        mock_context_manager.__exit__.return_value = None
        mock_pdfplumber.open.return_value = mock_context_manager

        # We don't need a real file if we mock open, but the parser likely checks file existence
        with tempfile.NamedTemporaryFile(mode='wb', delete=False, suffix='.pdf') as tmp:
            tmp.write(b"dummy pdf content")
            tmp_path = tmp.name

        try:
            with patch.dict(sys.modules, {"pdfplumber": mock_pdfplumber}):
                result = parser.parse(tmp_path)
            # Returns dict with full_text
            self.assertIn("Page text", result["full_text"])
            self.assertEqual(result["metadata"].get("title"), "Test PDF")
        finally:
            os.remove(tmp_path)

    @patch('semantica.parse.docx_parser.Document')
    def test_docx_parser(self, mock_document_cls):
        parser = DOCXParser()
        mock_doc = MagicMock()
        p1 = MagicMock()
        p1.text = "Paragraph 1"
        p2 = MagicMock()
        p2.text = "Paragraph 2"
        mock_doc.paragraphs = [p1, p2]
        mock_doc.core_properties.title = "Test DOCX"
        mock_document_cls.return_value = mock_doc
        
        with tempfile.NamedTemporaryFile(mode='wb', delete=False, suffix='.docx') as tmp:
            tmp.write(b"dummy docx")
            tmp_path = tmp.name
            
        try:
            result = parser.parse(tmp_path)
            # Returns dict with full_text
            self.assertIn("Paragraph 1", result["full_text"])
            self.assertIn("Paragraph 2", result["full_text"])
            self.assertEqual(result["metadata"].get("title"), "Test DOCX")
        finally:
            os.remove(tmp_path)

    # --- Code Parser Tests ---

    def test_code_parser_python(self):
        parser = CodeParser()
        code_content = """
def hello():
    print("Hello")
    
class MyClass:
    pass
"""
        
        with tempfile.NamedTemporaryFile(mode='w', delete=False, suffix='.py') as tmp:
            tmp.write(code_content)
            tmp_path = tmp.name
            
        try:
            # CodeParser has parse_code method
            result = parser.parse_code(tmp_path)
            # Result is a dict containing structure dict
            structure = result['structure']
            self.assertTrue(any(f['name'] == 'hello' for f in structure['functions']))
            self.assertTrue(any(c['name'] == 'MyClass' for c in structure['classes']))
        finally:
            os.remove(tmp_path)

    # --- Email Parser Tests ---

    def test_email_parser(self):
        parser = EmailParser()
        email_content = """From: sender@example.com
To: recipient@example.com
Subject: Test Email

This is the body.
"""
        with tempfile.NamedTemporaryFile(mode='w', delete=False, suffix='.eml') as tmp:
            tmp.write(email_content)
            tmp_path = tmp.name
            
        try:
            # EmailParser has parse_email method
            result = parser.parse_email(tmp_path)
            self.assertEqual(result.headers.subject, "Test Email")
            self.assertEqual(result.headers.from_address, "sender@example.com")
            # Body text might be None if not found, but simple case should find it
            self.assertIn("This is the body", result.body.text)
        finally:
            os.remove(tmp_path)

    # --- HTML Parser Tests ---

    def test_html_parser(self):
        parser = HTMLParser()
        html_content = """<html>
        <head><title>Test HTML</title></head>
        <body><p>Hello World</p></body>
        </html>"""
        
        with tempfile.NamedTemporaryFile(mode='w', delete=False, suffix='.html') as tmp:
            tmp.write(html_content)
            tmp_path = tmp.name
            
        try:
            result = parser.parse(tmp_path)
            # Returns HTMLData (dataclass) - I modified it to return HTMLData with metadata as dict
            self.assertEqual(result.metadata.get('title'), 'Test HTML')
            self.assertIn('Hello World', result.text)
        finally:
            os.remove(tmp_path)

    # --- Document Parser Tests (General) ---

    def test_document_parser_txt(self):
        parser = DocumentParser()
        content = "Simple text file."
        with tempfile.NamedTemporaryFile(mode='w', delete=False, suffix='.txt') as tmp:
            tmp.write(content)
            tmp_path = tmp.name
            
        try:
            text = parser.extract_text(tmp_path)
            self.assertEqual(text, content)
        finally:
            os.remove(tmp_path)

    # --- Structured Data Parser Tests (Delegation) ---

    def test_structured_data_parser_json_delegation(self):
        parser = StructuredDataParser()
        data = {'key': 'value'}
        with tempfile.NamedTemporaryFile(mode='w', delete=False, suffix='.json') as tmp:
            json.dump(data, tmp)
            tmp_path = tmp.name
            
        try:
            result = parser.parse_data(tmp_path, data_format='json')
            # Returns dict (JSONData.__dict__)
            # JSONData has .data field
            self.assertEqual(result['data']['key'], 'value')
        finally:
            os.remove(tmp_path)

if __name__ == '__main__':
    unittest.main()
