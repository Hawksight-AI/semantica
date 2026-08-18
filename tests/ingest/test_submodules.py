import pytest
import os
import tempfile
import shutil
from unittest.mock import MagicMock, patch, mock_open
import sys
from datetime import datetime

# Import classes to test
from semantica.ingest.api_ingestor import RESTIngestor, APIData
from semantica.ingest.duckdb_ingestor import DuckDBIngestor, DuckDBData
from semantica.ingest.elastic_ingestor import ElasticIngestor, ElasticData
from semantica.ingest.mcp_ingestor import MCPIngestor, MCPData
from semantica.ingest.mcp_client import MCPClient, MCPResource, MCPTool
from semantica.ingest.gdrive_ingestor import GDriveIngestor, GDriveData
from semantica.ingest.huggingface_ingestor import HuggingFaceIngestor, HFData
from semantica.ingest.mongo_ingestor import MongoIngestor, MongoData, MongoConnector
from semantica.ingest.pandas_ingestor import PandasIngestor, PandasData
from semantica.ingest.repo_ingestor import RepoIngestor, CodeFile
from semantica.ingest.stream_ingestor import StreamIngestor

class TestRESTIngestor:
    def test_ingest_endpoint(self):
        with patch("requests.Session") as MockSession:
            mock_session = MockSession.return_value
            mock_response = MagicMock()
            mock_response.status_code = 200
            mock_response.json.return_value = {"key": "value"}
            mock_response.headers = {"Content-Type": "application/json"}
            # The ingestor uses session.request generic method
            mock_session.request.return_value = mock_response
            
            ingestor = RESTIngestor()
            data = ingestor.ingest_endpoint("https://api.example.com/data")
            
            assert isinstance(data, APIData)
            # If response.json() is mocked to return {"key": "value"}, data.data should be that dict
            assert data.data == {"key": "value"}
            assert data.endpoint == "https://api.example.com/data"
            assert data.response_status == 200

    def test_paginated_fetch(self):
        with patch("requests.Session") as MockSession:
            mock_session = MockSession.return_value
            
            # First page
            mock_resp1 = MagicMock()
            mock_resp1.status_code = 200
            # Default logic checks for "items", "data", "results" or falls back to list
            mock_resp1.json.return_value = {"items": [1, 2], "next_page": "https://api.example.com/data?page=2"}
            mock_resp1.headers = {}
            
            # Second page
            mock_resp2 = MagicMock()
            mock_resp2.status_code = 200
            mock_resp2.json.return_value = {"items": [3, 4], "next_page": None}
            mock_resp2.headers = {}
            
            mock_session.request.side_effect = [mock_resp1, mock_resp2]
            
            ingestor = RESTIngestor()
            # Note: paginated_fetch uses self.ingest_endpoint internally
            
            # The default logic for `has_more` checks `has_more` or `next` key if it's a dict.
            # But here we have `next_page`.
            # We can use the logic in paginated_fetch to stop if items are empty, but here they are not.
            # We need to make sure the loop continues.
            # The loop continues if `has_more` (boolean) or `next` (not None) is present in data.
            # Our mock data has `next_page`.
            # So `has_more = ... or page_data.data.get("next", None) is not None`.
            # It doesn't check `next_page`.
            # So it will stop after first page unless we adjust mock data to match default expectation
            # OR we rely on `items` check? No, `items` check is for empty list stop.
            
            # Let's adjust mock data to use "next" key which is standard in the code.
            mock_resp1.json.return_value = {"items": [1, 2], "next": "https://api.example.com/data?page=2"}
            mock_resp2.json.return_value = {"items": [3, 4], "next": None}
            
            results = ingestor.paginated_fetch(
                "https://api.example.com/data"
            )
            
            assert len(results) == 2
            assert results[0].data["items"] == [1, 2]
            assert results[1].data["items"] == [3, 4]

class TestDuckDBIngestor:
    def test_init_raises_if_no_duckdb(self):
        # Simulate missing duckdb
        with patch("semantica.ingest.duckdb_ingestor.duckdb", None):
            with pytest.raises(ImportError):
                DuckDBIngestor()

    def test_ingest_csv(self):
        # Create a real temporary CSV file
        import tempfile
        import csv
        
        with tempfile.NamedTemporaryFile(mode='w', suffix='.csv', delete=False, newline='') as tmp:
            writer = csv.writer(tmp)
            writer.writerow(['col1', 'col2'])
            writer.writerow(['1', 'a'])
            tmp_path = tmp.name
            
        try:
            # Mock duckdb connection/execution only, but let file check pass
            mock_duckdb = MagicMock()
            mock_conn = MagicMock()
            mock_duckdb.connect.return_value = mock_conn
            
            # Mock query result
            # fetchall returns list of tuples
            mock_conn.execute.return_value.fetchall.return_value = [(1, 'a')]
            # description returns list of tuples (name, type, ...)
            mock_conn.description = [('col1', 'INTEGER'), ('col2', 'VARCHAR')]
            
            with patch("semantica.ingest.duckdb_ingestor.duckdb", mock_duckdb):
                ingestor = DuckDBIngestor()
                result = ingestor.ingest_csv(tmp_path)
                
                assert isinstance(result, DuckDBData)
                assert result.row_count == 1
                assert result.columns == ['col1', 'col2']
                # The mocked return value is [(1, 'a')], and zipped with cols:
                # {'col1': 1, 'col2': 'a'}
                assert result.data[0]['col1'] == 1
                mock_conn.execute.assert_called()
        finally:
            if os.path.exists(tmp_path):
                os.remove(tmp_path)

class TestElasticIngestor:
    def test_init_raises_if_no_elastic(self):
        with patch("semantica.ingest.elastic_ingestor.Elasticsearch", None):
            with pytest.raises(ImportError):
                ElasticIngestor()

    def test_ingest_index(self):
        mock_es_class = MagicMock()
        mock_es_instance = MagicMock()
        mock_es_class.return_value = mock_es_instance
        
        # Mock scan helper
        mock_scan = MagicMock()
        mock_scan.return_value = [
            {"_source": {"id": 1, "field": "val1"}},
            {"_source": {"id": 2, "field": "val2"}}
        ]
        
        with patch("semantica.ingest.elastic_ingestor.Elasticsearch", mock_es_class), \
             patch("semantica.ingest.elastic_ingestor.scan", mock_scan):
            
            ingestor = ElasticIngestor()
            result = ingestor.ingest_index("http://localhost:9200", "test_index")
            
            assert isinstance(result, ElasticData)
            assert result.document_count == 2
            assert result.index_name == "test_index"
            mock_scan.assert_called()

class TestMCPIngestor:
    def test_connect_and_ingest(self):
        # Mock MCPClient and ProgressTracker
        with patch("semantica.ingest.mcp_ingestor.MCPClient") as MockClient, \
             patch("semantica.ingest.mcp_ingestor.get_progress_tracker") as mock_get_tracker:
            
            mock_tracker = MagicMock()
            mock_get_tracker.return_value = mock_tracker
            
            mock_client = MockClient.return_value
            # list_resources returns list of MCPResource objects
            mock_client.list_resources.return_value = [
                MCPResource(uri="mcp://res1", name="Res1")
            ]
            # read_resource returns content
            mock_client.read_resource.return_value = "Resource Content"
            
            ingestor = MCPIngestor()
            ingestor.connect("server1", "http://localhost:8000")
            
            # List resources
            resources = ingestor.list_available_resources("server1")
            assert len(resources) == 1
            assert resources[0].name == "Res1"
            
            # Ingest resource
            data = ingestor.ingest_resources("server1", ["mcp://res1"])
            assert len(data) == 1
            assert data[0].content == "Resource Content"
            assert data[0].server_name == "server1"
            
            # Verify tracker usage
            mock_tracker.start_tracking.assert_called()
            mock_tracker.update_tracking.assert_called()

class TestMCPClient:
    def test_call_tool(self):
        # MCPClient._send_request_http now routes through request_with_ssrf_guard,
        # which calls requests.request (not requests.post) with allow_redirects=False.
        # Patch the requests.request call inside ssrf.py.
        with patch("semantica.ingest.ssrf.requests.request") as mock_request:
            mock_response = MagicMock()
            mock_response.status_code = 200

            # Response for initialize
            init_response = {
                "jsonrpc": "2.0",
                "result": {"serverInfo": {"name": "test", "version": "1.0"}},
                "id": 1,
            }

            # Response for tool call
            tool_response = {
                "jsonrpc": "2.0",
                "result": {"content": [{"type": "text", "text": "Tool Result"}]},
                "id": 2,
            }

            mock_response.json.side_effect = [init_response, tool_response]
            mock_request.return_value = mock_response

            client = MCPClient(url="http://localhost:8000")
            client.connect()

            client.call_tool("my_tool", {"arg": "val"})

    def test_call_tool_mock_check(self):
        # Redo with the corrected patch target.
        with patch("semantica.ingest.ssrf.requests.request") as mock_request:
            mock_response = MagicMock()
            mock_response.status_code = 200

            init_response = {
                "jsonrpc": "2.0",
                "result": {"serverInfo": {"name": "test", "version": "1.0"}},
                "id": 1,
            }

            tool_response = {
                "jsonrpc": "2.0",
                "result": {"content": [{"type": "text", "text": "Tool Result"}]},
                "id": 2,
            }

            mock_response.json.side_effect = [init_response, tool_response]
            mock_request.return_value = mock_response

            client = MCPClient(url="http://localhost:8000")
            client.connect()

            result = client.call_tool("my_tool", {"arg": "val"})

            assert result["content"] == [{"type": "text", "text": "Tool Result"}]

class TestGDriveIngestor:
    def test_init_raises_if_no_google_libs(self):
        with patch("semantica.ingest.gdrive_ingestor.build", None):
            with pytest.raises(ImportError):
                GDriveIngestor()

    def test_ingest_folder(self):
        mock_service = MagicMock()
        mock_files = MagicMock()
        mock_service.files.return_value = mock_files
        
        # Mock files.list
        mock_list = MagicMock()
        mock_list.execute.return_value = {
            "files": [
                {"id": "file1", "name": "test.txt", "mimeType": "text/plain", "size": "100"},
                {"id": "folder1", "name": "subfolder", "mimeType": "application/vnd.google-apps.folder"}
            ]
        }
        mock_files.list.return_value = mock_list
        
        # Mock files.get_media
        mock_get_media = MagicMock()
        mock_files.get_media.return_value = mock_get_media
        
        # Mock downloader
        with patch("semantica.ingest.gdrive_ingestor.MediaIoBaseDownload") as MockDownloader, \
             patch("semantica.ingest.gdrive_ingestor.build") as mock_build, \
             patch("semantica.ingest.gdrive_ingestor.InstalledAppFlow"), \
             patch("semantica.ingest.gdrive_ingestor.Credentials"):
            
            mock_build.return_value = mock_service
            
            # Setup downloader to finish immediately
            mock_downloader_instance = MockDownloader.return_value
            mock_downloader_instance.next_chunk.return_value = (None, True)
            
            ingestor = GDriveIngestor(credentials_path="dummy.json")
            # We need to mock _authenticate or allow it to pass if we mock credentials
            ingestor.service = mock_service
            
            # Test ingest_folder
            data = ingestor.ingest_folder("root_folder_id")
            
            assert isinstance(data, GDriveData)
            # ingest_folder should ingest files in the folder.
            # Based on mocks, it finds one file.
            assert len(data.files) >= 1
            assert data.files[0]["name"] == "test.txt"

class TestHuggingFaceIngestor:
    def test_init_raises_if_no_datasets(self):
        with patch("semantica.ingest.huggingface_ingestor.load_dataset", None):
            with pytest.raises(ImportError):
                HuggingFaceIngestor()

    def test_ingest_dataset(self):
        with patch("semantica.ingest.huggingface_ingestor.load_dataset") as mock_load:
            # Mock dataset
            mock_data = [
                {"col1": "val1", "col2": 1},
                {"col1": "val2", "col2": 2}
            ]
            # Dataset acts like a list/dict
            mock_dataset = MagicMock()
            mock_dataset.__iter__.return_value = iter(mock_data)
            mock_dataset.__len__.return_value = 2
            mock_dataset.column_names = ["col1", "col2"]
            mock_dataset.info.description = "Test Dataset"
            
            mock_load.return_value = mock_dataset
            
            ingestor = HuggingFaceIngestor()
            result = ingestor.ingest_dataset("test/dataset", split="train")
            
            assert isinstance(result, HFData)
            assert result.row_count == 2
            assert result.columns == ["col1", "col2"]
            assert result.data[0]["col1"] == "val1"

class TestMongoIngestor:
    def test_init_raises_if_no_pymongo(self):
        with patch("semantica.ingest.mongo_ingestor.MongoClient", None):
            with pytest.raises(ImportError):
                MongoIngestor()

    def test_ingest_collection(self):
        with patch("semantica.ingest.mongo_ingestor.MongoClient") as MockClient:
            mock_client = MockClient.return_value
            mock_db = MagicMock()
            mock_coll = MagicMock()
            mock_client.__getitem__.return_value = mock_db
            mock_db.__getitem__.return_value = mock_coll
            
            # Mock find
            mock_cursor = MagicMock()
            mock_cursor.__iter__.return_value = iter([
                {"_id": "1", "field": "val1"},
                {"_id": "2", "field": "val2"}
            ])
            mock_coll.find.return_value = mock_cursor
            mock_coll.count_documents.return_value = 2
            
            ingestor = MongoIngestor()
            # Inject client/connector
            ingestor.connector = MongoConnector()
            ingestor.connector.client = mock_client
            
            data = ingestor.ingest_collection("mongodb://localhost:27017", "db", "coll")
            
            assert isinstance(data, MongoData)
            assert data.document_count == 2
            assert data.collection_name == "coll"
            assert data.documents[0]["field"] == "val1"

class TestPandasIngestor:
    def test_ingest_dataframe(self):
        try:
            import pandas as pd
            df = pd.DataFrame({"a": [1, 2], "b": ["x", "y"]})
            
            ingestor = PandasIngestor()
            result = ingestor.ingest_dataframe(df)
            
            assert isinstance(result, PandasData)
            assert result.row_count == 2
            assert result.columns == ["a", "b"]
        except ImportError:
            pytest.skip("Pandas not installed")

    def test_from_csv(self):
        try:
            import pandas as pd
            import tempfile
            
            with tempfile.NamedTemporaryFile(mode='w', suffix='.csv', delete=False, newline='') as tmp:
                tmp.write("a,b\n1,x\n2,y\n")
                tmp_path = tmp.name
                
            try:
                ingestor = PandasIngestor()
                result = ingestor.from_csv(tmp_path)
                
                assert isinstance(result, PandasData)
                assert result.row_count == 2
                assert result.columns == ["a", "b"]
            finally:
                if os.path.exists(tmp_path):
                    os.remove(tmp_path)
        except ImportError:
            pytest.skip("Pandas not installed")

class TestRepoIngestor:
    def test_ingest_repository(self):
        # Create a real temp dir and populate it
        real_temp_dir = tempfile.mkdtemp()
        try:
            # Create some dummy files
            with open(os.path.join(real_temp_dir, "main.py"), "w") as f:
                f.write("print('hello')")
            with open(os.path.join(real_temp_dir, "README.md"), "w") as f:
                f.write("# Repo")
                
            with patch("semantica.ingest.repo_ingestor.git.Repo") as MockRepo, \
                 patch("semantica.ingest.repo_ingestor.tempfile.mkdtemp") as mock_mkdtemp, \
                 patch("semantica.ingest.repo_ingestor.shutil.rmtree"), \
                 patch("semantica.ingest.repo_ingestor.get_progress_tracker") as mock_get_tracker:
                
                mock_tracker = MagicMock()
                mock_get_tracker.return_value = mock_tracker
                
                # Make RepoIngestor use our populated temp dir
                mock_mkdtemp.return_value = real_temp_dir
                
                # Setup MockRepo
                mock_repo_instance = MockRepo.return_value
                mock_commit = MagicMock()
                mock_commit.hexsha = "abc1234"
                mock_commit.message = "Initial commit"
                mock_commit.author.name = "Test Author"
                mock_commit.committed_datetime.isoformat.return_value = "2023-01-01T00:00:00"
                mock_repo_instance.iter_commits.return_value = [mock_commit]
                
                # Ensure clone_from returns our mock repo
                MockRepo.clone_from.return_value = mock_repo_instance
                
                ingestor = RepoIngestor()
                result = ingestor.ingest_repository("https://github.com/user/repo.git")
                
                # Check result structure
                # Note: RepoIngestor returns 'code_files' instead of 'files'
                assert "code_files" in result
                assert len(result["code_files"]) >= 2
                assert "commits" in result
                assert len(result["commits"]) == 1
                
                # Check progress tracker calls
                mock_tracker.start_tracking.assert_called()
                mock_tracker.update_tracking.assert_called()
        finally:
            import shutil
            shutil.rmtree(real_temp_dir, ignore_errors=True)

class TestStreamIngestor:
    def test_ingest_kafka(self):
        with patch("semantica.ingest.stream_ingestor.KafkaProcessor") as MockProcessor:
            ingestor = StreamIngestor()
            processor = ingestor.ingest_kafka("topic", ["localhost:9092"])
            
            assert processor is not None
            MockProcessor.assert_called()

