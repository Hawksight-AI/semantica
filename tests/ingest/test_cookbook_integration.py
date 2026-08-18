import pytest
import json
from unittest.mock import MagicMock, patch
from semantica.ingest import MCPIngestor, ingest_mcp, DBIngestor, FileIngestor
from semantica.ingest.mcp_ingestor import MCPData

pytestmark = pytest.mark.integration

class TestCookbookIntegration:
    
    @pytest.fixture
    def mock_mcp_server(self):
        # MCPClient._send_request_http now routes through request_with_ssrf_guard,
        # which calls requests.request (not httpx.post / requests.post directly).
        # Patch at the point where the guard issues the actual HTTP call.
        with patch("semantica.ingest.ssrf.requests.request") as mock_request:

            def side_effect(method, url, json=None, **kwargs):
                if not json:
                    return MagicMock()

                rpc_method = json.get("method")
                response_mock = MagicMock()
                response_mock.status_code = 200

                if rpc_method == "initialize":
                    response_mock.json.return_value = {
                        "jsonrpc": "2.0",
                        "id": json.get("id"),
                        "result": {
                            "protocolVersion": "2024-11-05",
                            "capabilities": {},
                            "serverInfo": {"name": "test_server", "version": "1.0"}
                        }
                    }
                elif rpc_method == "resources/list":
                    response_mock.json.return_value = {
                        "jsonrpc": "2.0",
                        "id": json.get("id"),
                        "result": {
                            "resources": [
                                {"uri": "resource://test/1", "name": "Test Resource 1", "description": "Desc 1"},
                                {"uri": "resource://test/2", "name": "Test Resource 2", "description": "Desc 2"},
                                {"uri": "resource://inventory/database", "name": "Inventory DB", "description": "Inventory"}
                            ]
                        }
                    }
                elif rpc_method == "tools/list":
                    response_mock.json.return_value = {
                        "jsonrpc": "2.0",
                        "id": json.get("id"),
                        "result": {
                            "tools": [
                                {"name": "test_tool_1", "description": "Tool 1", "inputSchema": {}},
                                {"name": "test_tool_2", "description": "Tool 2", "inputSchema": {}},
                                {"name": "query_inventory", "description": "Query Inventory", "inputSchema": {}}
                            ]
                        }
                    }
                elif rpc_method == "resources/read":
                    response_mock.json.return_value = {
                        "jsonrpc": "2.0",
                        "id": json.get("id"),
                        "result": {
                            "contents": [
                                {"uri": json.get("params", {}).get("uri"), "text": "Sample content"}
                            ]
                        }
                    }
                elif rpc_method == "tools/call":
                    tool_name = json.get("params", {}).get("name")
                    content = [{"type": "text", "text": "Tool Output"}]

                    if tool_name == "query_inventory":
                        content = [{"type": "text", "text": '{"warehouse_id": "WH001", "level": 100}'}]

                    response_mock.json.return_value = {
                        "jsonrpc": "2.0",
                        "id": json.get("id"),
                        "result": {
                            "content": content
                        }
                    }
                else:
                    response_mock.json.return_value = {
                        "jsonrpc": "2.0",
                        "id": json.get("id"),
                        "result": {}
                    }

                return response_mock

            mock_request.side_effect = side_effect
            yield mock_request

    def test_financial_data_integration(self, mock_mcp_server):
        """
        Validates the logic from cookbook/use_cases/finance/01_Financial_Data_Integration.ipynb
        """
        # 1. Initialize MCP ingestor
        mcp_ingestor = MCPIngestor()
        
        # 2. Connect to financial data MCP server
        financial_mcp_url = "http://localhost:8000/mcp"
        
        # Patching progress tracker to avoid console output issues during testing if needed
        # But MCPIngestor now handles it gracefully or we can let it run.
        # We need to mock get_progress_tracker to avoid 'NoneType' errors if not initialized properly in some envs
        # although my previous fixes should handle it. Let's patch it to be safe and clean.
        with patch("semantica.ingest.mcp_ingestor.get_progress_tracker") as mock_tracker:
            tracker_instance = MagicMock()
            mock_tracker.return_value = tracker_instance
            
            mcp_ingestor.connect(
                "financial_server",
                url=financial_mcp_url,
                headers={"Authorization": "Bearer token"}
            )
            
            # 3. List available resources
            resources = mcp_ingestor.list_available_resources("financial_server")
            assert len(resources) >= 2
            assert resources[0].name == "Test Resource 1"
            
            # 4. List available tools
            tools = mcp_ingestor.list_available_tools("financial_server")
            assert len(tools) >= 2
            assert tools[0].name == "test_tool_1"
            
            # 5. Ingest resources (simulating notebook logic)
            # The notebook likely calls ingest_resources
            ingested_data = mcp_ingestor.ingest_resources(
                "financial_server",
                resource_uris=["resource://test/1"]
            )
            assert len(ingested_data) == 1
            # content is the raw result from MCP read_resource
            assert ingested_data[0].content["contents"][0]["text"] == "Sample content"

    def test_supply_chain_data_integration(self, mock_mcp_server):
        """
        Validates the logic from cookbook/use_cases/supply_chain/01_Supply_Chain_Data_Integration.ipynb
        """
        mcp_ingestor = MCPIngestor()
        supply_chain_mcp_url = "http://localhost:8000/mcp"
        
        with patch("semantica.ingest.mcp_ingestor.get_progress_tracker") as mock_tracker:
            tracker_instance = MagicMock()
            mock_tracker.return_value = tracker_instance

            mcp_ingestor.connect(
                "supply_chain_server",
                url=supply_chain_mcp_url,
                headers={"Authorization": "Bearer token"}
            )
            
            # Resource ingestion
            inventory_data = mcp_ingestor.ingest_resources(
                "supply_chain_server",
                resource_uris=["resource://inventory/database"]
            )
            assert len(inventory_data) == 1
            
            # Tool ingestion
            inventory_levels = mcp_ingestor.ingest_tool_output(
                "supply_chain_server",
                tool_name="query_inventory",
                arguments={"warehouse_id": "WH001"}
            )
            assert inventory_levels is not None
            # Based on my mock, it returns a dict with 'content'
            if isinstance(inventory_levels, MCPData):
                assert inventory_levels.content is not None
            elif isinstance(inventory_levels, dict):
                assert "content" in inventory_levels
            else:
                # Should be list or MCPData
                assert isinstance(inventory_levels, list)

    def test_medical_database_integration(self, mock_mcp_server):
        """
        Validates the logic from cookbook/use_cases/healthcare/05_Medical_Database_Integration.ipynb
        """
        mcp_ingestor = MCPIngestor()
        medical_mcp_url = "http://localhost:8000/mcp"
        
        with patch("semantica.ingest.mcp_ingestor.get_progress_tracker") as mock_tracker:
            tracker_instance = MagicMock()
            mock_tracker.return_value = tracker_instance
            
            mcp_ingestor.connect(
                "medical_server",
                url=medical_mcp_url
            )
            
            resources = mcp_ingestor.list_available_resources("medical_server")
            assert len(resources) > 0

    def test_threat_intelligence_integration(self, mock_mcp_server):
        """
        Validates the logic from cookbook/use_cases/cybersecurity/05_Threat_Intelligence_Integration.ipynb
        """
        mcp_ingestor = MCPIngestor()
        threat_mcp_url = "http://localhost:8000/mcp"
        
        with patch("semantica.ingest.mcp_ingestor.get_progress_tracker") as mock_tracker:
            tracker_instance = MagicMock()
            mock_tracker.return_value = tracker_instance
            
            mcp_ingestor.connect(
                "threat_server",
                url=threat_mcp_url
            )
            
            tools = mcp_ingestor.list_available_tools("threat_server")
            assert len(tools) > 0
