"""
Unit tests for Amazon Neptune Graph Store with Neo4j Bolt driver.

Tests cover:
- Initialization with and without IAM authentication
- Connection management using Bolt driver
- Node CRUD operations
- Relationship CRUD operations
- OpenCypher query execution
- Graph analytics (neighbors, shortest path)
- Statistics and status
- NeptuneAuthTokenManager SigV4 signing
- Retry logic and connection recovery
"""

import unittest
from typing import Any, Dict, List, Optional
from unittest.mock import MagicMock, patch


class MockNeo4jRecord:
    """Mock Neo4j record for testing."""

    def __init__(self, data: Dict[str, Any]):
        self._data = data

    def __iter__(self):
        return iter(self._data.items())

    def __getitem__(self, key):
        return self._data[key]

    def keys(self):
        return self._data.keys()

    def values(self):
        return self._data.values()

    def items(self):
        return self._data.items()

    def get(self, key, default=None):
        return self._data.get(key, default)


class MockNeo4jResult:
    """Mock Neo4j query result."""

    def __init__(self, records: List[Dict[str, Any]]):
        self._records = [MockNeo4jRecord(r) for r in records]
        self._index = 0

    def __iter__(self):
        return iter(self._records)

    def single(self):
        return self._records[0] if self._records else None

    def peek(self):
        return self._records[0] if self._records else None


class MockNeo4jSession:
    """Mock Neo4j session for testing."""

    def __init__(self, driver):
        self.driver = driver
        self._closed = False

    def run(self, query: str, parameters: Optional[Dict] = None) -> MockNeo4jResult:
        """Execute a query and return mock results."""
        parameters = parameters or {}

        # Store query for inspection
        self.driver.last_query = query
        self.driver.last_parameters = parameters

        query_lower = query.lower()

        # Simple RETURN 1 test query
        if "return 1" in query_lower:
            return MockNeo4jResult([{"test": 1}])

        # CREATE node
        if "create" in query_lower and "(n:" in query_lower:
            return self._handle_create_node(query, parameters)

        # MERGE node
        if "merge" in query_lower and "(n:" in query_lower:
            return self._handle_create_node(query, parameters)

        # MATCH node by id
        if "match" in query_lower and "id(n)" in query_lower:
            return self._handle_get_node(query, parameters)

        # MATCH nodes by label
        if "match" in query_lower and "return n" in query_lower:
            return self._handle_get_nodes(query, parameters)

        # CREATE relationship
        if "create" in query_lower and "-[r:" in query_lower:
            return self._handle_create_relationship(query, parameters)

        # MATCH relationship
        if "match" in query_lower and "-[r" in query_lower:
            return self._handle_get_relationships(query, parameters)

        # DELETE
        if "delete" in query_lower:
            return self._handle_delete(query, parameters)

        # SET (update)
        if "set" in query_lower:
            return self._handle_update(query, parameters)

        # COUNT queries (stats)
        if "count" in query_lower:
            return self._handle_stats(query)

        # Default response
        return MockNeo4jResult([{"n": {}}])

    def _handle_create_node(self, query: str, parameters: Dict) -> MockNeo4jResult:
        """Handle node creation queries."""
        self.driver.node_counter += 1
        node_id = parameters.get("node_id", f"node_{self.driver.node_counter}")
        labels = ["TestLabel"]
        properties = {k: v for k, v in parameters.items() if k != "node_id"}

        node = {"id": node_id, "labels": labels, "properties": properties}
        self.driver.nodes[node_id] = node

        return MockNeo4jResult(
            [{"n": {"~id": node_id, "~labels": labels, **properties}}]
        )

    def _handle_get_node(self, query: str, parameters: Dict) -> MockNeo4jResult:
        """Handle get node by ID queries."""
        node_id = parameters.get("id")
        if node_id and node_id in self.driver.nodes:
            node = self.driver.nodes[node_id]
            return MockNeo4jResult(
                [
                    {
                        "n": {
                            "~id": node["id"],
                            "~labels": node["labels"],
                            **node["properties"],
                        },
                        "labels": node["labels"],
                    }
                ]
            )
        return MockNeo4jResult([])

    def _handle_get_nodes(self, query: str, parameters: Dict) -> MockNeo4jResult:
        """Handle get nodes queries."""
        results = []
        for node in self.driver.nodes.values():
            results.append(
                {
                    "n": {
                        "~id": node["id"],
                        "~labels": node["labels"],
                        **node["properties"],
                    },
                    "labels": node["labels"],
                }
            )
        return MockNeo4jResult(results)

    def _handle_create_relationship(
        self, query: str, parameters: Dict
    ) -> MockNeo4jResult:
        """Handle relationship creation queries."""
        self.driver.rel_counter += 1
        rel_id = parameters.get("rel_id", f"rel_{self.driver.rel_counter}")

        rel = {
            "id": rel_id,
            "start_node_id": parameters.get("start_id"),
            "end_node_id": parameters.get("end_id"),
            "type": "TEST_REL",
            "properties": {},
        }
        self.driver.relationships[rel_id] = rel

        return MockNeo4jResult([{"r": {"~id": rel_id, "~type": "TEST_REL"}}])

    def _handle_get_relationships(
        self, query: str, parameters: Dict
    ) -> MockNeo4jResult:
        """Handle get relationships queries."""
        results = []
        for rel in self.driver.relationships.values():
            results.append(
                {
                    "r": {"~id": rel["id"], "~type": rel["type"]},
                    "start_id": rel["start_node_id"],
                    "end_id": rel["end_node_id"],
                }
            )
        return MockNeo4jResult(results)

    def _handle_delete(self, query: str, parameters: Dict) -> MockNeo4jResult:
        """Handle delete queries."""
        node_id = parameters.get("id")
        if node_id and node_id in self.driver.nodes:
            del self.driver.nodes[node_id]
        return MockNeo4jResult([])

    def _handle_update(self, query: str, parameters: Dict) -> MockNeo4jResult:
        """Handle update queries."""
        node_id = parameters.get("id")
        if node_id and node_id in self.driver.nodes:
            props = parameters.get("props", {})
            self.driver.nodes[node_id]["properties"].update(props)
            node = self.driver.nodes[node_id]
            return MockNeo4jResult(
                [
                    {
                        "n": {
                            "~id": node["id"],
                            "~labels": node["labels"],
                            **node["properties"],
                        },
                        "labels": node["labels"],
                    }
                ]
            )
        return MockNeo4jResult([])

    def _handle_stats(self, query: str) -> MockNeo4jResult:
        """Handle statistics queries."""
        return MockNeo4jResult(
            [{"count": len(self.driver.nodes) + len(self.driver.relationships)}]
        )

    def close(self):
        """Close the session."""
        self._closed = True

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.close()


class MockNeo4jDriver:
    """Mock Neo4j driver for testing."""

    def __init__(self, *args, **kwargs):
        self.nodes = {}
        self.relationships = {}
        self.node_counter = 0
        self.rel_counter = 0
        self.last_query = None
        self.last_parameters = None
        self._closed = False

    def session(self, **kwargs):
        """Create a new session."""
        return MockNeo4jSession(self)

    def close(self):
        """Close the driver."""
        self._closed = True

    def verify_connectivity(self):
        """Verify driver connectivity."""
        pass


class MockGraphDatabase:
    """Mock Neo4j GraphDatabase class."""

    @staticmethod
    def driver(uri, auth=None, **kwargs):
        return MockNeo4jDriver(uri, auth=auth, **kwargs)


class MockBasicAuth:
    """Mock basic_auth function."""

    def __init__(self, username, password):
        self.username = username
        self.password = password


def mock_basic_auth(username, password):
    """Mock basic_auth function."""
    return MockBasicAuth(username, password)


# Create a real AuthManager base class for testing (not MagicMock)
class MockAuthManager:
    """Mock AuthManager base class for testing."""

    pass


# Create mock modules
mock_neo4j = MagicMock()
mock_neo4j.GraphDatabase = MockGraphDatabase
mock_neo4j.auth_management = MagicMock()
mock_neo4j.auth_management.AuthManager = MockAuthManager
mock_neo4j.api = MagicMock()
mock_neo4j.api.basic_auth = mock_basic_auth
mock_neo4j.exceptions = MagicMock()
mock_neo4j.exceptions.Neo4jError = Exception
mock_neo4j.exceptions.ServiceUnavailable = Exception
mock_neo4j.exceptions.DatabaseError = Exception
mock_neo4j.exceptions.ClientError = Exception
mock_neo4j.exceptions.AuthError = Exception

mock_boto3 = MagicMock()
mock_session = MagicMock()
mock_credentials = MagicMock()
mock_credentials.access_key = "test_access_key"
mock_credentials.secret_key = "test_secret_key"
mock_credentials.token = None
mock_session.get_credentials.return_value = mock_credentials
mock_boto3.Session.return_value = mock_session


class MockHeaders:
    """Mock headers object that supports both dict-like access and add_header."""

    def __init__(self):
        self._headers = {}

    def add_header(self, key, value):
        self._headers[key] = value

    def get(self, key, default=None):
        return self._headers.get(key, default)

    def __setitem__(self, key, value):
        self._headers[key] = value

    def __getitem__(self, key):
        return self._headers[key]

    def __contains__(self, key):
        return key in self._headers


class MockAWSRequest:
    """Mock AWSRequest for testing botocore SigV4 signing."""

    def __init__(self, method="GET", url="", data=None, headers=None):
        self.method = method
        self.url = url
        self.data = data
        self.headers = MockHeaders()
        if headers:
            for k, v in headers.items():
                self.headers[k] = v


class MockSigV4Auth:
    """Mock SigV4Auth for testing botocore signing."""

    def __init__(self, credentials, service_name, region):
        self.credentials = credentials
        self.service_name = service_name
        self.region = region

    def add_auth(self, request):
        """Add mock SigV4 authentication headers to the request."""
        from datetime import datetime, timezone

        # Generate a timestamp
        t = datetime.now(timezone.utc)
        amz_date = t.strftime("%Y%m%dT%H%M%SZ")
        date_stamp = t.strftime("%Y%m%d")

        # Extract host from URL
        import urllib.parse

        parsed = urllib.parse.urlparse(request.url)
        host = parsed.netloc

        # Build mock authorization header
        credential_scope = (
            f"{date_stamp}/{self.region}/{self.service_name}/aws4_request"
        )
        authorization = (
            f"AWS4-HMAC-SHA256 "
            f"Credential=test_access_key/{credential_scope}, "
            f"SignedHeaders=content-type;host;x-amz-date, "
            f"Signature=mocksignature123456789"
        )

        request.headers["Host"] = host
        request.headers["X-Amz-Date"] = amz_date
        request.headers["Authorization"] = authorization
        # Real SigV4Auth adds the session token header for temporary credentials
        if self.credentials.token:
            request.headers["X-Amz-Security-Token"] = self.credentials.token


def mock_host_from_url(url):
    """Mock _host_from_url function."""
    import urllib.parse

    parsed = urllib.parse.urlparse(url)
    return parsed.netloc


# Create mock botocore modules
mock_botocore = MagicMock()
mock_botocore_auth = MagicMock()
mock_botocore_auth.SigV4Auth = MockSigV4Auth
mock_botocore_auth._host_from_url = mock_host_from_url
mock_botocore_awsrequest = MagicMock()
mock_botocore_awsrequest.AWSRequest = MockAWSRequest


class TestAmazonNeptuneStoreInit(unittest.TestCase):
    """Test AmazonNeptuneStore initialization."""

    def test_init_with_iam_auth(self):
        """Test initialization with IAM authentication enabled."""
        with patch.dict(
            "sys.modules",
            {
                "neo4j": mock_neo4j,
                "neo4j.auth_management": mock_neo4j.auth_management,
                "neo4j.api": mock_neo4j.api,
                "neo4j.exceptions": mock_neo4j.exceptions,
                "boto3": mock_boto3,
                "botocore": mock_botocore,
                "botocore.auth": mock_botocore_auth,
                "botocore.awsrequest": mock_botocore_awsrequest,
            },
        ):
            from importlib import reload

            from semantica.graph_store import amazon_neptune

            reload(amazon_neptune)

            store = amazon_neptune.AmazonNeptuneStore(
                endpoint="test-cluster.us-east-1.neptune.amazonaws.com",
                port=8182,
                region="us-east-1",
                iam_auth=True,
            )

            self.assertEqual(
                store.endpoint, "test-cluster.us-east-1.neptune.amazonaws.com"
            )
            self.assertEqual(store.port, 8182)
            self.assertEqual(store.region, "us-east-1")
            self.assertTrue(store.iam_auth)

    def test_init_without_iam_auth(self):
        """Test initialization without IAM authentication."""
        with patch.dict(
            "sys.modules",
            {
                "neo4j": mock_neo4j,
                "neo4j.auth_management": mock_neo4j.auth_management,
                "neo4j.api": mock_neo4j.api,
                "neo4j.exceptions": mock_neo4j.exceptions,
                "boto3": mock_boto3,
            },
        ):
            from importlib import reload

            from semantica.graph_store import amazon_neptune

            reload(amazon_neptune)

            store = amazon_neptune.AmazonNeptuneStore(
                endpoint="test-cluster.us-east-1.neptune.amazonaws.com",
                port=8182,
                region="us-east-1",
                iam_auth=False,
            )

            self.assertFalse(store.iam_auth)

    def test_init_default_port(self):
        """Test initialization with default port."""
        with patch.dict(
            "sys.modules",
            {
                "neo4j": mock_neo4j,
                "neo4j.auth_management": mock_neo4j.auth_management,
                "neo4j.api": mock_neo4j.api,
                "neo4j.exceptions": mock_neo4j.exceptions,
                "boto3": mock_boto3,
            },
        ):
            from importlib import reload

            from semantica.graph_store import amazon_neptune

            reload(amazon_neptune)

            store = amazon_neptune.AmazonNeptuneStore(
                endpoint="test-cluster.us-east-1.neptune.amazonaws.com",
                region="us-east-1",
            )

            self.assertEqual(store.port, 8182)

    def test_bolt_uri_property(self):
        """Test the bolt_uri property."""
        with patch.dict(
            "sys.modules",
            {
                "neo4j": mock_neo4j,
                "neo4j.auth_management": mock_neo4j.auth_management,
                "neo4j.api": mock_neo4j.api,
                "neo4j.exceptions": mock_neo4j.exceptions,
                "boto3": mock_boto3,
            },
        ):
            from importlib import reload

            from semantica.graph_store import amazon_neptune

            reload(amazon_neptune)

            store = amazon_neptune.AmazonNeptuneStore(
                endpoint="test.neptune.amazonaws.com",
                port=8182,
                region="us-east-1",
                iam_auth=False,
            )

            self.assertEqual(
                store.bolt_uri, "bolt://test.neptune.amazonaws.com:8182/opencypher"
            )


class TestAmazonNeptuneStoreOperations(unittest.TestCase):
    """Test AmazonNeptuneStore CRUD operations."""

    def setUp(self):
        """Set up test fixtures."""
        self.modules_patcher = patch.dict(
            "sys.modules",
            {
                "neo4j": mock_neo4j,
                "neo4j.auth_management": mock_neo4j.auth_management,
                "neo4j.api": mock_neo4j.api,
                "neo4j.exceptions": mock_neo4j.exceptions,
                "boto3": mock_boto3,
                "botocore": mock_botocore,
                "botocore.auth": mock_botocore_auth,
                "botocore.awsrequest": mock_botocore_awsrequest,
            },
        )
        self.modules_patcher.start()

        from importlib import reload

        from semantica.graph_store import amazon_neptune

        reload(amazon_neptune)

        self.store = amazon_neptune.AmazonNeptuneStore(
            endpoint="test-cluster.us-east-1.neptune.amazonaws.com",
            port=8182,
            region="us-east-1",
            iam_auth=False,
        )
        self.store.connect()

    def tearDown(self):
        """Clean up test fixtures."""
        if hasattr(self, "store"):
            self.store.close()
        self.modules_patcher.stop()

    def test_connect_success(self):
        """Test successful connection."""
        self.assertTrue(self.store._connected)

    def test_create_node_with_custom_id(self):
        """Test creating a node with custom ID (id in properties)."""
        node = self.store.create_node(
            labels=["Person"], properties={"id": "alice", "name": "Alice", "age": 30}
        )

        self.assertIsNotNone(node)
        self.assertEqual(node.get("id"), "alice")

    def test_create_node_with_generated_id(self):
        """Test creating a node with auto-generated UUID (no id in properties)."""
        node = self.store.create_node(labels=["Person"], properties={"name": "Bob"})

        self.assertIsNotNone(node)
        self.assertIn("id", node)

    def test_get_nodes(self):
        """Test retrieving nodes by label."""
        self.store.create_node(
            labels=["Person"], properties={"id": "alice", "name": "Alice"}
        )

        nodes = self.store.get_nodes(labels=["Person"], limit=10)
        self.assertIsInstance(nodes, list)

    def test_execute_query(self):
        """Test executing an OpenCypher query."""
        result = self.store.execute_query("MATCH (n) RETURN n LIMIT 10", parameters={})

        self.assertIsNotNone(result)
        self.assertIn("records", result)

    def test_execute_query_with_parameters(self):
        """Test executing a parameterized query."""
        result = self.store.execute_query(
            "MATCH (p:Person) WHERE p.age > $min_age RETURN p",
            parameters={"min_age": 25},
        )

        self.assertIsNotNone(result)

    def test_get_stats(self):
        """Test getting graph statistics."""
        stats = self.store.get_stats()

        self.assertIsNotNone(stats)
        self.assertIn("node_count", stats)
        self.assertEqual(stats["protocol"], "bolt")

    def test_get_status(self):
        """Test getting connection status."""
        status = self.store.get_status()

        self.assertIsNotNone(status)
        self.assertEqual(status["backend"], "amazon_neptune")
        self.assertEqual(status["protocol"], "bolt")
        self.assertEqual(status["connected"], True)

    def test_close_connection(self):
        """Test closing the connection."""
        self.store.close()
        self.assertFalse(self.store._connected)


class TestAmazonNeptuneStoreIAMAuth(unittest.TestCase):
    """Test IAM authentication functionality."""

    def test_auth_manager_creation(self):
        """Test that AuthManager is created correctly for IAM auth."""
        with patch.dict(
            "sys.modules",
            {
                "neo4j": mock_neo4j,
                "neo4j.auth_management": mock_neo4j.auth_management,
                "neo4j.api": mock_neo4j.api,
                "neo4j.exceptions": mock_neo4j.exceptions,
                "boto3": mock_boto3,
                "botocore": mock_botocore,
                "botocore.auth": mock_botocore_auth,
                "botocore.awsrequest": mock_botocore_awsrequest,
            },
        ):
            from importlib import reload

            from semantica.graph_store import amazon_neptune

            reload(amazon_neptune)

            store = amazon_neptune.AmazonNeptuneStore(
                endpoint="test-cluster.us-east-1.neptune.amazonaws.com",
                port=8182,
                region="us-east-1",
                iam_auth=True,
            )
            store.connect()

            # Verify auth manager was created
            self.assertIsNotNone(store._auth_manager)
            self.assertEqual(store._auth_manager.aws_region, "us-east-1")

            store.close()

    def test_signed_auth_headers_not_logged(self):
        """Signed SigV4 headers (Authorization, security token) must never be logged (#1365)."""
        with patch.dict(
            "sys.modules",
            {
                "neo4j": mock_neo4j,
                "neo4j.auth_management": mock_neo4j.auth_management,
                "neo4j.api": mock_neo4j.api,
                "neo4j.exceptions": mock_neo4j.exceptions,
                "boto3": mock_boto3,
                "botocore": mock_botocore,
                "botocore.auth": mock_botocore_auth,
                "botocore.awsrequest": mock_botocore_awsrequest,
            },
        ):
            from importlib import reload

            from semantica.graph_store import amazon_neptune

            reload(amazon_neptune)

            manager = amazon_neptune.NeptuneAuthTokenManager(
                neptune_endpoint="bolt://test-cluster.us-east-1.neptune.amazonaws.com:8182",
                aws_region="us-east-1",
            )

            # Use temporary credentials so the signer emits X-Amz-Security-Token
            with patch.object(
                mock_credentials, "token", "mocksessiontoken987654321"
            ):
                with self.assertLogs(
                    "semantica.neptune_auth_token_manager", level="DEBUG"
                ) as captured:
                    auth = manager.get_auth()

            self.assertIsNotNone(auth)
            logged = "\n".join(captured.output)
            # The signed Authorization header (containing the SigV4 signature)
            # and the STS session token are live, replayable credentials and
            # must not appear in logs at any level.
            self.assertNotIn("mocksignature123456789", logged)
            self.assertNotIn("Authorization", logged)
            self.assertNotIn("mocksessiontoken987654321", logged)

    def test_refresh_auth_token(self):
        """Test manual token refresh."""
        with patch.dict(
            "sys.modules",
            {
                "neo4j": mock_neo4j,
                "neo4j.auth_management": mock_neo4j.auth_management,
                "neo4j.api": mock_neo4j.api,
                "neo4j.exceptions": mock_neo4j.exceptions,
                "boto3": mock_boto3,
                "botocore": mock_botocore,
                "botocore.auth": mock_botocore_auth,
                "botocore.awsrequest": mock_botocore_awsrequest,
            },
        ):
            from importlib import reload

            from semantica.graph_store import amazon_neptune

            reload(amazon_neptune)

            store = amazon_neptune.AmazonNeptuneStore(
                endpoint="test-cluster.us-east-1.neptune.amazonaws.com",
                port=8182,
                region="us-east-1",
                iam_auth=True,
            )
            store.connect()

            # Refresh should not raise
            store.refresh_auth_token()

            store.close()

    def test_update_auth_context(self):
        """Test updating auth context (for Lambda)."""
        with patch.dict(
            "sys.modules",
            {
                "neo4j": mock_neo4j,
                "neo4j.auth_management": mock_neo4j.auth_management,
                "neo4j.api": mock_neo4j.api,
                "neo4j.exceptions": mock_neo4j.exceptions,
                "boto3": mock_boto3,
                "botocore": mock_botocore,
                "botocore.auth": mock_botocore_auth,
                "botocore.awsrequest": mock_botocore_awsrequest,
            },
        ):
            from importlib import reload

            from semantica.graph_store import amazon_neptune

            reload(amazon_neptune)

            store = amazon_neptune.AmazonNeptuneStore(
                endpoint="test-cluster.us-east-1.neptune.amazonaws.com",
                port=8182,
                region="us-east-1",
                iam_auth=True,
            )
            store.connect()

            # Mock Lambda context
            mock_context = MagicMock()
            # update_auth_context should not raise - it logs but doesn't store
            # (Neo4j driver can't serialize complex objects as instance attributes)
            store.update_auth_context(mock_context)

            # The method should complete without error
            self.assertIsNotNone(store._auth_manager)

            store.close()


class TestAmazonNeptuneStoreGraphAnalytics(unittest.TestCase):
    """Test graph analytics methods."""

    def setUp(self):
        """Set up test fixtures."""
        self.modules_patcher = patch.dict(
            "sys.modules",
            {
                "neo4j": mock_neo4j,
                "neo4j.auth_management": mock_neo4j.auth_management,
                "neo4j.api": mock_neo4j.api,
                "neo4j.exceptions": mock_neo4j.exceptions,
                "boto3": mock_boto3,
            },
        )
        self.modules_patcher.start()

        from importlib import reload

        from semantica.graph_store import amazon_neptune

        reload(amazon_neptune)

        self.store = amazon_neptune.AmazonNeptuneStore(
            endpoint="test-cluster.us-east-1.neptune.amazonaws.com",
            region="us-east-1",
            iam_auth=False,
        )
        self.store.connect()

    def tearDown(self):
        """Clean up test fixtures."""
        if hasattr(self, "store"):
            self.store.close()
        self.modules_patcher.stop()

    def test_get_neighbors(self):
        """Test getting neighbors of a node."""
        self.store.create_node(
            labels=["Person"], properties={"id": "alice", "name": "Alice"}
        )

        neighbors = self.store.get_neighbors(node_id="alice", direction="both", depth=1)

        self.assertIsInstance(neighbors, list)

    def test_shortest_path(self):
        """Test finding shortest path between nodes."""
        self.store.create_node(
            labels=["Person"], properties={"id": "alice", "name": "Alice"}
        )
        self.store.create_node(
            labels=["Person"], properties={"id": "bob", "name": "Bob"}
        )

        path = self.store.shortest_path(
            start_node_id="alice", end_node_id="bob", max_depth=5
        )

        # Path may be None if no path exists, which is valid
        self.assertTrue(path is None or isinstance(path, dict))


class TestGraphStoreNeptuneBackend(unittest.TestCase):
    """Test GraphStore with Neptune backend."""

    def test_graphstore_neptune_initialization(self):
        """Test GraphStore initialization with Neptune backend."""
        with patch.dict(
            "sys.modules",
            {
                "neo4j": mock_neo4j,
                "neo4j.auth_management": mock_neo4j.auth_management,
                "neo4j.api": mock_neo4j.api,
                "neo4j.exceptions": mock_neo4j.exceptions,
                "boto3": mock_boto3,
            },
        ):
            from importlib import reload

            from semantica.graph_store import amazon_neptune, graph_store

            reload(amazon_neptune)
            reload(graph_store)

            store = graph_store.GraphStore(
                backend="neptune",
                endpoint="test-cluster.us-east-1.neptune.amazonaws.com",
                region="us-east-1",
                iam_auth=False,
            )

            self.assertEqual(store.backend, "neptune")


class TestAmazonNeptuneStoreCRUD(unittest.TestCase):
    """Test complete CRUD operations including update and delete."""

    def setUp(self):
        """Set up test fixtures."""
        self.modules_patcher = patch.dict(
            "sys.modules",
            {
                "neo4j": mock_neo4j,
                "neo4j.auth_management": mock_neo4j.auth_management,
                "neo4j.api": mock_neo4j.api,
                "neo4j.exceptions": mock_neo4j.exceptions,
                "boto3": mock_boto3,
            },
        )
        self.modules_patcher.start()

        from importlib import reload

        from semantica.graph_store import amazon_neptune

        reload(amazon_neptune)

        self.store = amazon_neptune.AmazonNeptuneStore(
            endpoint="test-cluster.us-east-1.neptune.amazonaws.com",
            port=8182,
            region="us-east-1",
            iam_auth=False,
        )
        self.store.connect()

    def tearDown(self):
        """Clean up test fixtures."""
        if hasattr(self, "store"):
            self.store.close()
        self.modules_patcher.stop()

    def test_update_node(self):
        """Test updating a node's properties."""
        self.store.create_node(
            labels=["Person"],
            properties={"id": "update_test", "name": "Original", "age": 25},
        )

        updated = self.store.update_node(
            node_id="update_test",
            properties={"name": "Updated", "city": "NYC"},
            merge=True,
        )

        self.assertIsNotNone(updated)

    def test_update_node_replace(self):
        """Test replacing a node's properties (merge=False)."""
        self.store.create_node(
            labels=["Person"],
            properties={"id": "replace_test", "name": "Original", "age": 25},
        )

        updated = self.store.update_node(
            node_id="replace_test", properties={"name": "Replaced"}, merge=False
        )

        self.assertIsNotNone(updated)

    def test_delete_node(self):
        """Test deleting a node."""
        self.store.create_node(
            labels=["Person"], properties={"id": "delete_test", "name": "ToDelete"}
        )

        result = self.store.delete_node(node_id="delete_test", detach=True)
        self.assertTrue(result)

    def test_delete_node_without_detach(self):
        """Test deleting a node without detaching relationships."""
        self.store.create_node(
            labels=["Person"], properties={"id": "delete_test_2", "name": "ToDelete"}
        )

        result = self.store.delete_node(node_id="delete_test_2", detach=False)
        self.assertTrue(result)

    def test_get_node_by_id(self):
        """Test getting a specific node by ID."""
        self.store.create_node(
            labels=["Person"], properties={"id": "get_test", "name": "GetMe"}
        )

        node = self.store.get_node(node_id="get_test")
        self.assertTrue(node is None or isinstance(node, dict))


class TestAmazonNeptuneStoreRelationships(unittest.TestCase):
    """Test relationship CRUD operations."""

    def setUp(self):
        """Set up test fixtures."""
        self.modules_patcher = patch.dict(
            "sys.modules",
            {
                "neo4j": mock_neo4j,
                "neo4j.auth_management": mock_neo4j.auth_management,
                "neo4j.api": mock_neo4j.api,
                "neo4j.exceptions": mock_neo4j.exceptions,
                "boto3": mock_boto3,
            },
        )
        self.modules_patcher.start()

        from importlib import reload

        from semantica.graph_store import amazon_neptune

        reload(amazon_neptune)

        self.store = amazon_neptune.AmazonNeptuneStore(
            endpoint="test-cluster.us-east-1.neptune.amazonaws.com",
            port=8182,
            region="us-east-1",
            iam_auth=False,
        )
        self.store.connect()

        # Create test nodes for relationship tests
        self.store.create_node(
            labels=["Person"], properties={"id": "rel_alice", "name": "Alice"}
        )
        self.store.create_node(
            labels=["Person"], properties={"id": "rel_bob", "name": "Bob"}
        )

    def tearDown(self):
        """Clean up test fixtures."""
        if hasattr(self, "store"):
            self.store.close()
        self.modules_patcher.stop()

    def test_create_relationship(self):
        """Test creating a relationship between nodes."""
        rel = self.store.create_relationship(
            start_node_id="rel_alice",
            end_node_id="rel_bob",
            rel_type="KNOWS",
            properties={"since": 2020},
        )

        self.assertIsNotNone(rel)
        self.assertEqual(rel["type"], "KNOWS")
        self.assertEqual(rel["start_node_id"], "rel_alice")
        self.assertEqual(rel["end_node_id"], "rel_bob")

    def test_create_relationship_with_custom_id(self):
        """Test creating a relationship with a custom ID."""
        rel = self.store.create_relationship(
            start_node_id="rel_alice",
            end_node_id="rel_bob",
            rel_type="FRIENDS",
            properties={"id": "custom_rel_id", "level": "close"},
        )

        self.assertIsNotNone(rel)
        self.assertEqual(rel["id"], "custom_rel_id")

    def test_get_relationships_outgoing(self):
        """Test getting outgoing relationships from a node."""
        self.store.create_relationship(
            start_node_id="rel_alice", end_node_id="rel_bob", rel_type="KNOWS"
        )

        rels = self.store.get_relationships(node_id="rel_alice", direction="out")

        self.assertIsInstance(rels, list)

    def test_get_relationships_incoming(self):
        """Test getting incoming relationships to a node."""
        self.store.create_relationship(
            start_node_id="rel_alice", end_node_id="rel_bob", rel_type="KNOWS"
        )

        rels = self.store.get_relationships(node_id="rel_bob", direction="in")

        self.assertIsInstance(rels, list)

    def test_get_relationships_both(self):
        """Test getting all relationships for a node."""
        rels = self.store.get_relationships(node_id="rel_alice", direction="both")

        self.assertIsInstance(rels, list)

    def test_get_relationships_by_type(self):
        """Test filtering relationships by type."""
        rels = self.store.get_relationships(node_id="rel_alice", rel_type="KNOWS")

        self.assertIsInstance(rels, list)

    def test_get_all_relationships(self):
        """Test getting all relationships without node filter."""
        rels = self.store.get_relationships(limit=10)
        self.assertIsInstance(rels, list)

    def test_delete_relationship(self):
        """Test deleting a relationship."""
        self.store.create_relationship(
            start_node_id="rel_alice",
            end_node_id="rel_bob",
            rel_type="TEMPORARY",
            properties={"id": "rel_to_delete"},
        )

        result = self.store.delete_relationship(rel_id="rel_to_delete")
        self.assertTrue(result)


class TestAmazonNeptuneStoreErrors(unittest.TestCase):
    """Test error handling and edge cases."""

    def setUp(self):
        """Set up test fixtures."""
        self.modules_patcher = patch.dict(
            "sys.modules",
            {
                "neo4j": mock_neo4j,
                "neo4j.auth_management": mock_neo4j.auth_management,
                "neo4j.api": mock_neo4j.api,
                "neo4j.exceptions": mock_neo4j.exceptions,
                "boto3": mock_boto3,
            },
        )
        self.modules_patcher.start()

        from importlib import reload

        from semantica.graph_store import amazon_neptune

        reload(amazon_neptune)
        self.amazon_neptune = amazon_neptune

    def tearDown(self):
        """Clean up test fixtures."""
        self.modules_patcher.stop()

    def test_missing_endpoint(self):
        """Test initialization with missing endpoint."""
        store = self.amazon_neptune.AmazonNeptuneStore(
            endpoint=None, region="us-east-1", iam_auth=False
        )
        # Connection should fail due to missing endpoint
        with self.assertRaises(Exception):
            store.connect()

    def test_create_node_without_labels(self):
        """Test creating a node with empty labels."""
        store = self.amazon_neptune.AmazonNeptuneStore(
            endpoint="test-cluster.us-east-1.neptune.amazonaws.com",
            region="us-east-1",
            iam_auth=False,
        )
        store.connect()

        try:
            # Empty labels should still work - defaults to "Node"
            created_node = store.create_node(labels=[], properties={"name": "NoLabel"})
            self.assertIsNotNone(created_node)
        finally:
            store.close()

    def test_create_node_with_merge_false(self):
        """Test creating a node with merge=False option."""
        store = self.amazon_neptune.AmazonNeptuneStore(
            endpoint="test-cluster.us-east-1.neptune.amazonaws.com",
            region="us-east-1",
            iam_auth=False,
        )
        store.connect()

        try:
            created_node = store.create_node(
                labels=["Person"],
                properties={"name": "MergeFalse"},
                merge=False,
            )
            self.assertIsNotNone(created_node)
        finally:
            store.close()

    def test_get_nodes_with_property_filter(self):
        """Test getting nodes with property filters."""
        store = self.amazon_neptune.AmazonNeptuneStore(
            endpoint="test-cluster.us-east-1.neptune.amazonaws.com",
            region="us-east-1",
            iam_auth=False,
        )
        store.connect()

        try:
            nodes = store.get_nodes(
                labels=["Person"], properties={"name": "Alice", "age": 30}, limit=5
            )
            self.assertIsInstance(nodes, list)
        finally:
            store.close()

    def test_create_index(self):
        """Test create_index (Neptune handles indexes automatically)."""
        store = self.amazon_neptune.AmazonNeptuneStore(
            endpoint="test-cluster.us-east-1.neptune.amazonaws.com",
            region="us-east-1",
            iam_auth=False,
        )

        # Should return True and log info about Neptune's index management
        result = store.create_index(label="Person", property_name="name")
        self.assertTrue(result)


class TestNeptuneWrapperClasses(unittest.TestCase):
    """Test Neptune wrapper classes."""

    def setUp(self):
        """Set up test fixtures."""
        self.modules_patcher = patch.dict(
            "sys.modules",
            {
                "neo4j": mock_neo4j,
                "neo4j.auth_management": mock_neo4j.auth_management,
                "neo4j.api": mock_neo4j.api,
                "neo4j.exceptions": mock_neo4j.exceptions,
                "boto3": mock_boto3,
            },
        )
        self.modules_patcher.start()

        from importlib import reload

        from semantica.graph_store import amazon_neptune

        reload(amazon_neptune)
        self.amazon_neptune = amazon_neptune

    def tearDown(self):
        """Clean up test fixtures."""
        self.modules_patcher.stop()

    def test_neptune_driver_session(self):
        """Test NeptuneDriver.session() method."""
        mock_driver = MockNeo4jDriver()
        wrapper = self.amazon_neptune.NeptuneDriver(mock_driver)

        session = wrapper.session()
        self.assertIsInstance(session, self.amazon_neptune.NeptuneSession)

    def test_neptune_driver_verify_connectivity(self):
        """Test NeptuneDriver.verify_connectivity() method."""
        mock_driver = MockNeo4jDriver()
        wrapper = self.amazon_neptune.NeptuneDriver(mock_driver)

        result = wrapper.verify_connectivity()
        self.assertTrue(result)

    def test_neptune_driver_close(self):
        """Test NeptuneDriver.close() method."""
        mock_driver = MockNeo4jDriver()
        wrapper = self.amazon_neptune.NeptuneDriver(mock_driver)

        wrapper.close()
        self.assertTrue(mock_driver._closed)

    def test_neptune_session_run(self):
        """Test NeptuneSession.run() method."""
        mock_driver = MockNeo4jDriver()
        mock_session = MockNeo4jSession(mock_driver)
        wrapper = self.amazon_neptune.NeptuneSession(mock_session)

        result = wrapper.run("RETURN 1 as test")
        self.assertIsNotNone(result)

    def test_neptune_session_close(self):
        """Test NeptuneSession.close() method."""
        mock_driver = MockNeo4jDriver()
        mock_session = MockNeo4jSession(mock_driver)
        wrapper = self.amazon_neptune.NeptuneSession(mock_session)

        wrapper.close()
        self.assertTrue(mock_session._closed)

    def test_neptune_session_context_manager(self):
        """Test NeptuneSession context manager."""
        mock_driver = MockNeo4jDriver()
        mock_session = MockNeo4jSession(mock_driver)
        wrapper = self.amazon_neptune.NeptuneSession(mock_session)

        with wrapper as session:
            self.assertIsNotNone(session)
        self.assertTrue(mock_session._closed)


class TestAmazonNeptuneStoreBatchOperations(unittest.TestCase):
    """Test batch operations."""

    def setUp(self):
        """Set up test fixtures."""
        self.modules_patcher = patch.dict(
            "sys.modules",
            {
                "neo4j": mock_neo4j,
                "neo4j.auth_management": mock_neo4j.auth_management,
                "neo4j.api": mock_neo4j.api,
                "neo4j.exceptions": mock_neo4j.exceptions,
                "boto3": mock_boto3,
            },
        )
        self.modules_patcher.start()

        from importlib import reload

        from semantica.graph_store import amazon_neptune

        reload(amazon_neptune)

        self.store = amazon_neptune.AmazonNeptuneStore(
            endpoint="test-cluster.us-east-1.neptune.amazonaws.com",
            port=8182,
            region="us-east-1",
            iam_auth=False,
        )
        self.store.connect()

    def tearDown(self):
        """Clean up test fixtures."""
        if hasattr(self, "store"):
            self.store.close()
        self.modules_patcher.stop()

    def test_create_nodes_batch(self):
        """Test creating multiple nodes in batch."""
        nodes_data = [
            {"labels": ["Person"], "properties": {"id": "batch1", "name": "Alice"}},
            {"labels": ["Person"], "properties": {"id": "batch2", "name": "Bob"}},
            {"labels": ["Company"], "properties": {"id": "batch3", "name": "Acme"}},
        ]

        created = self.store.create_nodes(nodes_data)

        self.assertEqual(len(created), 3)
        self.assertEqual(created[0]["id"], "batch1")
        self.assertEqual(created[1]["id"], "batch2")
        self.assertEqual(created[2]["id"], "batch3")

    def test_create_nodes_empty(self):
        """Test creating empty batch."""
        created = self.store.create_nodes([])
        self.assertEqual(len(created), 0)


class TestAmazonNeptuneStoreRetryLogic(unittest.TestCase):
    """Test retry logic and error handling."""

    def setUp(self):
        """Set up test fixtures."""
        self.modules_patcher = patch.dict(
            "sys.modules",
            {
                "neo4j": mock_neo4j,
                "neo4j.auth_management": mock_neo4j.auth_management,
                "neo4j.api": mock_neo4j.api,
                "neo4j.exceptions": mock_neo4j.exceptions,
                "boto3": mock_boto3,
            },
        )
        self.modules_patcher.start()

        from importlib import reload

        from semantica.graph_store import amazon_neptune

        reload(amazon_neptune)
        self.amazon_neptune = amazon_neptune

        self.store = amazon_neptune.AmazonNeptuneStore(
            endpoint="test-cluster.us-east-1.neptune.amazonaws.com",
            port=8182,
            region="us-east-1",
            iam_auth=False,
        )
        self.store.connect()

    def tearDown(self):
        """Clean up test fixtures."""
        if hasattr(self, "store"):
            self.store.close()
        self.modules_patcher.stop()

    def test_is_retriable_error_signature_expired(self):
        """Test that 'Signature expired' is retriable."""
        error = Exception("Signature expired")
        result = self.store._is_retriable_error(error)
        self.assertTrue(result)

    def test_is_retriable_error_connection_closed(self):
        """Test that 'Connection is closed' is retriable."""
        error = Exception("Connection is closed")
        result = self.store._is_retriable_error(error)
        self.assertTrue(result)

    def test_is_retriable_error_not_retriable(self):
        """Test that generic errors are not retriable."""
        error = Exception("Some other error")
        result = self.store._is_retriable_error(error)
        self.assertFalse(result)

    def test_is_non_retriable_error(self):
        """Test _is_non_retriable_error method."""
        error = Exception("Some other error")
        result = self.store._is_non_retriable_error(error)
        self.assertTrue(result)

    def test_is_non_retriable_error_retriable(self):
        """Test _is_non_retriable_error with retriable error."""
        error = Exception("Signature expired")
        result = self.store._is_non_retriable_error(error)
        self.assertFalse(result)


class TestAmazonNeptuneStoreSession(unittest.TestCase):
    """Test session management."""

    def setUp(self):
        """Set up test fixtures."""
        self.modules_patcher = patch.dict(
            "sys.modules",
            {
                "neo4j": mock_neo4j,
                "neo4j.auth_management": mock_neo4j.auth_management,
                "neo4j.api": mock_neo4j.api,
                "neo4j.exceptions": mock_neo4j.exceptions,
                "boto3": mock_boto3,
            },
        )
        self.modules_patcher.start()

        from importlib import reload

        from semantica.graph_store import amazon_neptune

        reload(amazon_neptune)
        self.amazon_neptune = amazon_neptune

        self.store = amazon_neptune.AmazonNeptuneStore(
            endpoint="test-cluster.us-east-1.neptune.amazonaws.com",
            port=8182,
            region="us-east-1",
            iam_auth=False,
        )
        self.store.connect()

    def tearDown(self):
        """Clean up test fixtures."""
        if hasattr(self, "store"):
            self.store.close()
        self.modules_patcher.stop()

    def test_get_session(self):
        """Test getting a session."""
        session = self.store.get_session()
        self.assertIsInstance(session, self.amazon_neptune.NeptuneSession)

    def test_get_session_with_database_param(self):
        """Test getting a session with database parameter (ignored for Neptune)."""
        session = self.store.get_session(database="ignored")
        self.assertIsInstance(session, self.amazon_neptune.NeptuneSession)


class TestAmazonNeptuneStoreGraphAnalyticsDirections(unittest.TestCase):
    """Test graph analytics with different directions."""

    def setUp(self):
        """Set up test fixtures."""
        self.modules_patcher = patch.dict(
            "sys.modules",
            {
                "neo4j": mock_neo4j,
                "neo4j.auth_management": mock_neo4j.auth_management,
                "neo4j.api": mock_neo4j.api,
                "neo4j.exceptions": mock_neo4j.exceptions,
                "boto3": mock_boto3,
            },
        )
        self.modules_patcher.start()

        from importlib import reload

        from semantica.graph_store import amazon_neptune

        reload(amazon_neptune)

        self.store = amazon_neptune.AmazonNeptuneStore(
            endpoint="test-cluster.us-east-1.neptune.amazonaws.com",
            region="us-east-1",
            iam_auth=False,
        )
        self.store.connect()

    def tearDown(self):
        """Clean up test fixtures."""
        if hasattr(self, "store"):
            self.store.close()
        self.modules_patcher.stop()

    def test_get_neighbors_outgoing(self):
        """Test getting outgoing neighbors."""
        self.store.create_node(
            labels=["Person"], properties={"id": "alice", "name": "Alice"}
        )

        neighbors = self.store.get_neighbors(node_id="alice", direction="out", depth=1)

        self.assertIsInstance(neighbors, list)

    def test_get_neighbors_incoming(self):
        """Test getting incoming neighbors."""
        self.store.create_node(
            labels=["Person"], properties={"id": "alice", "name": "Alice"}
        )

        neighbors = self.store.get_neighbors(node_id="alice", direction="in", depth=1)

        self.assertIsInstance(neighbors, list)

    def test_get_neighbors_with_rel_type(self):
        """Test getting neighbors filtered by relationship type."""
        self.store.create_node(
            labels=["Person"], properties={"id": "alice", "name": "Alice"}
        )

        neighbors = self.store.get_neighbors(
            node_id="alice", rel_type="KNOWS", direction="both", depth=2
        )

        self.assertIsInstance(neighbors, list)

    def test_shortest_path_with_rel_type(self):
        """Test shortest path with relationship type filter."""
        self.store.create_node(
            labels=["Person"], properties={"id": "alice", "name": "Alice"}
        )
        self.store.create_node(
            labels=["Person"], properties={"id": "bob", "name": "Bob"}
        )

        path = self.store.shortest_path(
            start_node_id="alice", end_node_id="bob", rel_type="KNOWS", max_depth=3
        )

        # Path may be None if no path exists
        self.assertTrue(path is None or isinstance(path, dict))


class TestNeptuneAuthTokenManager(unittest.TestCase):
    """Test NeptuneAuthTokenManager class directly."""

    def test_auth_token_generation(self):
        """Test that SigV4 auth token is generated."""
        with patch.dict(
            "sys.modules",
            {
                "neo4j": mock_neo4j,
                "neo4j.auth_management": mock_neo4j.auth_management,
                "neo4j.api": mock_neo4j.api,
                "neo4j.exceptions": mock_neo4j.exceptions,
                "boto3": mock_boto3,
                "botocore": mock_botocore,
                "botocore.auth": mock_botocore_auth,
                "botocore.awsrequest": mock_botocore_awsrequest,
            },
        ):
            from importlib import reload

            from semantica.graph_store import amazon_neptune

            reload(amazon_neptune)

            endpoint = (
                "bolt://test-cluster.us-east-1.neptune.amazonaws.com" ":8182/opencypher"
            )
            auth_manager = amazon_neptune.NeptuneAuthTokenManager(
                neptune_endpoint=endpoint,
                aws_region="us-east-1",
                access_key="AKIAIOSFODNN7EXAMPLE",
                secret_key="wJalrXUtnFEMI/K7MDENG/bPxRfiCYEXAMPLEKEY",
            )

            # get_auth should return a basic auth object
            auth = auth_manager.get_auth()
            self.assertIsNotNone(auth)

    def test_auth_token_caching(self):
        """Test that auth token is cached."""
        with patch.dict(
            "sys.modules",
            {
                "neo4j": mock_neo4j,
                "neo4j.auth_management": mock_neo4j.auth_management,
                "neo4j.api": mock_neo4j.api,
                "neo4j.exceptions": mock_neo4j.exceptions,
                "boto3": mock_boto3,
                "botocore": mock_botocore,
                "botocore.auth": mock_botocore_auth,
                "botocore.awsrequest": mock_botocore_awsrequest,
            },
        ):
            from importlib import reload

            from semantica.graph_store import amazon_neptune

            reload(amazon_neptune)

            endpoint = (
                "bolt://test-cluster.us-east-1.neptune.amazonaws.com" ":8182/opencypher"
            )
            auth_manager = amazon_neptune.NeptuneAuthTokenManager(
                neptune_endpoint=endpoint,
                aws_region="us-east-1",
            )

            # First call generates token, second returns cached
            first_auth = auth_manager.get_auth()
            second_auth = auth_manager.get_auth()

            self.assertIs(first_auth, second_auth)

    def test_token_refresh(self):
        """Test token refresh functionality."""
        with patch.dict(
            "sys.modules",
            {
                "neo4j": mock_neo4j,
                "neo4j.auth_management": mock_neo4j.auth_management,
                "neo4j.api": mock_neo4j.api,
                "neo4j.exceptions": mock_neo4j.exceptions,
                "boto3": mock_boto3,
                "botocore": mock_botocore,
                "botocore.auth": mock_botocore_auth,
                "botocore.awsrequest": mock_botocore_awsrequest,
            },
        ):
            from importlib import reload

            from semantica.graph_store import amazon_neptune

            reload(amazon_neptune)

            endpoint = (
                "bolt://test-cluster.us-east-1.neptune.amazonaws.com" ":8182/opencypher"
            )
            auth_manager = amazon_neptune.NeptuneAuthTokenManager(
                neptune_endpoint=endpoint,
                aws_region="us-east-1",
            )

            # Get initial token
            auth_manager.get_auth()

            # Force refresh
            auth_manager.refresh_token()

            # Cached token should be None
            self.assertIsNone(auth_manager.cached_auth)

            # Next get_auth call should generate new token
            new_auth = auth_manager.get_auth()
            self.assertIsNotNone(new_auth)

    def test_handle_security_exception(self):
        """Test security exception handling."""
        with patch.dict(
            "sys.modules",
            {
                "neo4j": mock_neo4j,
                "neo4j.auth_management": mock_neo4j.auth_management,
                "neo4j.api": mock_neo4j.api,
                "neo4j.exceptions": mock_neo4j.exceptions,
                "boto3": mock_boto3,
                "botocore": mock_botocore,
                "botocore.auth": mock_botocore_auth,
                "botocore.awsrequest": mock_botocore_awsrequest,
            },
        ):
            from importlib import reload

            from semantica.graph_store import amazon_neptune

            reload(amazon_neptune)

            endpoint = (
                "bolt://test-cluster.us-east-1.neptune.amazonaws.com" ":8182/opencypher"
            )
            auth_manager = amazon_neptune.NeptuneAuthTokenManager(
                neptune_endpoint=endpoint,
                aws_region="us-east-1",
            )

            # Get initial token
            auth = auth_manager.get_auth()

            # Simulate security exception
            mock_error = Exception("Signature expired")
            result = auth_manager.handle_security_exception(auth, mock_error)

            # Should return True to retry
            self.assertTrue(result)
            # Token should be cleared
            self.assertIsNone(auth_manager.cached_auth)

    def test_endpoint_conversion(self):
        """Test that bolt:// is converted to https:// for signing."""
        with patch.dict(
            "sys.modules",
            {
                "neo4j": mock_neo4j,
                "neo4j.auth_management": mock_neo4j.auth_management,
                "neo4j.api": mock_neo4j.api,
                "neo4j.exceptions": mock_neo4j.exceptions,
                "boto3": mock_boto3,
                "botocore": mock_botocore,
                "botocore.auth": mock_botocore_auth,
                "botocore.awsrequest": mock_botocore_awsrequest,
            },
        ):
            from importlib import reload

            from semantica.graph_store import amazon_neptune

            reload(amazon_neptune)

            endpoint = (
                "bolt://test-cluster.us-east-1.neptune.amazonaws.com" ":8182/opencypher"
            )
            auth_manager = amazon_neptune.NeptuneAuthTokenManager(
                neptune_endpoint=endpoint,
                aws_region="us-east-1",
            )

            # Endpoint should be converted to https for signing
            self.assertTrue(auth_manager.neptune_endpoint.startswith("https://"))


if __name__ == "__main__":
    unittest.main()
