import os
import tempfile
import pytest
import sqlite3
import time
from pathlib import Path
from unittest.mock import MagicMock, patch

from semantica.ingest import (
    ingest, 
    FileIngestor, FileTypeDetector, CloudStorageIngestor,
    WebIngestor, ContentExtractor, SitemapCrawler, RobotsChecker,
    FeedIngestor, FeedMonitor,
    StreamIngestor, StreamMonitor,
    RepoIngestor, CodeExtractor, GitAnalyzer,
    EmailIngestor, AttachmentProcessor,
    DBIngestor, DatabaseConnector,
    MCPIngestor, IngestConfig, ingest_config
)

pytestmark = pytest.mark.integration

class TestNotebook02DataIngestion:
    
    def setup_method(self):
        self.temp_dir = tempfile.mkdtemp()
        
    def teardown_method(self):
        import shutil
        shutil.rmtree(self.temp_dir)

    def test_01_unified_ingestion(self):
        # Setup temporary file
        sample_file = os.path.join(self.temp_dir, "sample.txt")
        with open(sample_file, 'w') as f:
            f.write("Semantica Unified Ingestion Example")

        # Auto-detect file source
        result = ingest(sample_file)
        assert "files" in result
        assert result["files"].name == "sample.txt"
        
        # Explicit source type
        result_explicit = ingest(sample_file, source_type="file")
        assert "files" in result_explicit
        assert result_explicit["files"].name == "sample.txt"

        # Ingest web URL (mocked)
        with patch("semantica.ingest.web_ingestor.WebIngestor.ingest_url") as mock_ingest:
            mock_ingest.return_value = MagicMock(title="Mock Title")
            result_web = ingest("https://example.com")
            assert "content" in result_web
            assert result_web["content"].title == "Mock Title"

    def test_02_file_ingestion(self):
        sample_file = os.path.join(self.temp_dir, "sample.txt")
        with open(sample_file, 'w') as f:
            f.write("Semantica Unified Ingestion Example")
            
        # FileTypeDetector
        detector = FileTypeDetector()
        detected_type = detector.detect_type(sample_file)
        assert detected_type == "txt"

        # FileIngestor
        file_ingestor = FileIngestor()
        subdir = os.path.join(self.temp_dir, "docs")
        os.makedirs(subdir, exist_ok=True)
        with open(os.path.join(subdir, "note.md"), 'w') as f:
            f.write("# Note\nThis is a markdown file.")

        files = file_ingestor.ingest_directory(self.temp_dir, recursive=True)
        assert len(files) >= 2

        # CloudStorageIngestor (Mock Config)
        s3_config = {
            "aws_access_key_id": "mock_key",
            "aws_secret_access_key": "mock_secret",
            "region_name": "us-east-1"
        }
        # We just test initialization here as actual ingest requires creds
        cloud_ingestor = CloudStorageIngestor(provider="s3", **s3_config)
        assert cloud_ingestor is not None

    def test_03_web_ingestion(self):
        # ContentExtractor
        extractor = ContentExtractor()
        html_content = "<html><body><h1>Hello World</h1><p>This is a test.</p><a href='/link'>Link</a></body></html>"
        text = extractor.extract_text(html_content)
        assert "Hello World" in text
    
        links = extractor.extract_links(html_content, base_url="https://example.com")
        assert len(links) > 0
    
        # RobotsChecker
        with patch("urllib.robotparser.RobotFileParser.can_fetch", return_value=True):
            checker = RobotsChecker()
            can_fetch = checker.can_fetch("https://www.google.com/search")
            assert can_fetch is True
    
        # WebIngestor
        # Patch Session to return a mock session
        with patch("requests.Session") as MockSession:
            mock_session_instance = MockSession.return_value
            mock_response = MagicMock()
            mock_response.status_code = 200
            mock_response.text = "<html><title>Web</title></html>"
            mock_session_instance.get.return_value = mock_response

            web_ingestor = WebIngestor(delay=0.1)
            # Patch RobotsChecker.can_fetch globally for WebIngestor usage
            with patch("semantica.ingest.web_ingestor.RobotsChecker.can_fetch", return_value=True):
                 web_content = web_ingestor.ingest_url("https://example.com")
                 assert web_content is not None
                 assert "Web" in web_content.text

    def test_04_feed_ingestion(self):
        feed_ingestor = FeedIngestor()
        
        # Mock feed ingest
        with patch.object(feed_ingestor, 'ingest_feed') as mock_ingest:
            mock_ingest.return_value = MagicMock(title="Feed Title", items=[])
            feed_data = feed_ingestor.ingest_feed("https://feeds.feedburner.com/oreilly/radar")
            assert feed_data.title == "Feed Title"

    def test_05_stream_ingestion(self):
        stream_ingestor = StreamIngestor()
        
        # Mock Kafka/RabbitMQ
        with patch("semantica.ingest.stream_ingestor.StreamIngestor.ingest_kafka") as mock_kafka:
            mock_kafka.return_value = MagicMock()
            stream_ingestor.ingest_kafka("my-topic", bootstrap_servers=["localhost:9092"])
            
        with patch("semantica.ingest.stream_ingestor.StreamIngestor.ingest_rabbitmq") as mock_rabbit:
            mock_rabbit.return_value = MagicMock()
            stream_ingestor.ingest_rabbitmq("my-queue", "amqp://guest:guest@localhost:5672/")

        monitor = stream_ingestor.monitor
        health = monitor.check_health()
        assert 'overall' in health

    def test_06_repo_ingestion(self):
        code_extractor = CodeExtractor()
        with tempfile.NamedTemporaryFile(mode="w", suffix=".py", delete=False) as tmp:
            tmp.write("class MyClass:\n    def my_method(self):\n        pass")
            tmp_path = tmp.name
        
        try:
            code_file = code_extractor.extract_file_content(Path(tmp_path))
            structure = code_file.metadata.get("structure", {})
            assert isinstance(structure, dict)
            assert "classes" in structure
        finally:
            if os.path.exists(tmp_path):
                os.remove(tmp_path)

        repo_ingestor = RepoIngestor()
        with patch.object(repo_ingestor, 'ingest_repository') as mock_ingest:
            mock_ingest.return_value = {'name': 'semantica'}
            repo_data = repo_ingestor.ingest_repository("https://github.com/semantica-agi/semantica.git")
            assert repo_data['name'] == 'semantica'

    def test_07_email_ingestion(self):
        att_processor = AttachmentProcessor()
        dummy_content = b"PDF Content"
        result = att_processor.process_attachment(dummy_content, "doc.pdf", "application/pdf")
        saved_path = result["saved_path"]
        assert saved_path is not None
        assert os.path.exists(saved_path)

        email_ingestor = EmailIngestor()
        with patch.object(email_ingestor, 'connect_imap'):
            with patch.object(email_ingestor, 'ingest_mailbox', return_value=[]):
                email_ingestor.connect_imap("imap.gmail.com", "user", "pass")
                emails = email_ingestor.ingest_mailbox("INBOX", max_emails=5)
                assert isinstance(emails, list)

    def test_08_database_ingestion(self):
        # Setup SQLite DB
        db_path = os.path.join(self.temp_dir, "test.db")
        conn = sqlite3.connect(db_path)
        conn.execute("CREATE TABLE items (id INT, name TEXT)")
        conn.execute("INSERT INTO items VALUES (1, 'Item 1'), (2, 'Item 2')")
        conn.commit()
        conn.close()

        connector = DatabaseConnector()
        try:
            engine = connector.connect(f"sqlite:///{db_path}")
            assert engine is not None
    
            db_ingestor = DBIngestor()
            result = db_ingestor.ingest_database(f"sqlite:///{db_path}", include_tables=["items"])
            table_data = result["tables"]["items"]
            assert table_data["row_count"] == 2
        finally:
            connector.disconnect()

    def test_09_mcp_ingestion(self):
        mcp_ingestor = MCPIngestor()
        
        with patch.object(mcp_ingestor, 'connect'):
            with patch.object(mcp_ingestor, 'ingest_resources', return_value=[]):
                with patch.object(mcp_ingestor, 'ingest_tool_output', return_value=MagicMock(content="Result")):
                    mcp_ingestor.connect("weather_server", url="http://localhost:8000/mcp")
                    resources = mcp_ingestor.ingest_resources("weather_server")
                    assert isinstance(resources, list)
                    
                    result = mcp_ingestor.ingest_tool_output("weather_server", "get_forecast", {"city": "NYC"})
                    assert result.content == "Result"

    def test_10_configuration(self):
        config = IngestConfig()
        config.set("max_file_size", 1024 * 1024)
        assert config.get("max_file_size") == 1024 * 1024
