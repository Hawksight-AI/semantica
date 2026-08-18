
import pytest
import os
import json
import csv
from pathlib import Path
from unittest.mock import MagicMock, patch
from semantica.seed.seed_manager import SeedDataManager, SeedDataSource, SeedData
from semantica.utils.exceptions import ProcessingError

@pytest.fixture
def seed_manager():
    return SeedDataManager()

@pytest.fixture
def temp_data_dir(tmp_path):
    data_dir = tmp_path / "data"
    data_dir.mkdir()
    return data_dir

def test_init():
    manager = SeedDataManager(config={"test": "config"})
    assert manager.config["test"] == "config"
    assert manager.sources == {}
    assert isinstance(manager.seed_data, SeedData)

def test_register_source(seed_manager):
    result = seed_manager.register_source(
        name="test_source",
        format="json",
        location="test.json",
        entity_type="Person",
        description="Test source"
    )
    assert result is True
    assert "test_source" in seed_manager.sources
    source = seed_manager.sources["test_source"]
    assert source.name == "test_source"
    assert source.format == "json"
    assert source.entity_type == "Person"
    assert source.metadata["description"] == "Test source"

    # Test update existing
    seed_manager.register_source(
        name="test_source",
        format="csv",
        location="test.csv"
    )
    assert seed_manager.sources["test_source"].format == "csv"

def test_load_from_csv(seed_manager, temp_data_dir):
    csv_file = temp_data_dir / "test.csv"
    with open(csv_file, "w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        writer.writerow(["id", "name", "age"])
        writer.writerow(["1", "Alice", "30"])
        writer.writerow(["2", "Bob", "25"])

    records = seed_manager.load_from_csv(
        csv_file,
        entity_type="Person",
        source_name="test_csv"
    )
    
    assert len(records) == 2
    assert records[0]["id"] == "1"
    assert records[0]["name"] == "Alice"
    assert records[0]["entity_type"] == "Person"
    assert records[0]["source"] == "test_csv"

def test_load_from_csv_not_found(seed_manager):
    with pytest.raises(ProcessingError):
        seed_manager.load_from_csv("non_existent.csv")

def test_load_from_json_list(seed_manager, temp_data_dir):
    json_file = temp_data_dir / "test_list.json"
    data = [
        {"id": "1", "name": "Alice"},
        {"id": "2", "name": "Bob"}
    ]
    with open(json_file, "w") as f:
        json.dump(data, f)

    records = seed_manager.load_from_json(
        json_file,
        entity_type="Person",
        source_name="test_json"
    )
    
    assert len(records) == 2
    assert records[0]["entity_type"] == "Person"
    assert records[0]["source"] == "test_json"

def test_load_from_json_dict_entities(seed_manager, temp_data_dir):
    json_file = temp_data_dir / "test_dict.json"
    data = {
        "entities": [
            {"id": "1", "name": "Alice"}
        ]
    }
    with open(json_file, "w") as f:
        json.dump(data, f)

    records = seed_manager.load_from_json(json_file)
    assert len(records) == 1
    assert records[0]["id"] == "1"

def test_load_from_json_not_found(seed_manager):
    with pytest.raises(ProcessingError):
        seed_manager.load_from_json("non_existent.json")

@patch("semantica.ingest.db_ingestor.DBIngestor")
def test_load_from_database(mock_db_ingestor_cls, seed_manager):
    mock_db_ingestor = MagicMock()
    mock_db_ingestor_cls.return_value = mock_db_ingestor
    
    # Mock execute_query result
    mock_db_ingestor.execute_query.return_value = [{"id": 1, "name": "Alice"}]
    
    records = seed_manager.load_from_database(
        connection_string="sqlite:///:memory:",
        query="SELECT * FROM users",
        entity_type="User"
    )
    
    assert len(records) == 1
    assert records[0]["id"] == 1
    assert records[0]["entity_type"] == "User"
    # Regression for #973: the ingestor methods receive the connection
    # string as their first argument — the constructor config is not enough.
    mock_db_ingestor.execute_query.assert_called_once_with(
        "sqlite:///:memory:", "SELECT * FROM users"
    )

    # Mock export_table result
    mock_table_data = MagicMock()
    mock_table_data.rows = [{"id": 2, "name": "Bob"}]
    mock_db_ingestor.export_table.return_value = mock_table_data
    
    records = seed_manager.load_from_database(
        connection_string="sqlite:///:memory:",
        table_name="users"
    )
    assert len(records) == 1
    assert records[0]["id"] == 2
    mock_db_ingestor.export_table.assert_called_once_with("sqlite:///:memory:", "users")

def test_load_from_database_os_error_not_misreported(seed_manager):
    # Regression for #973: a real OSError from the ingestor must surface as a
    # database failure with the cause chained, not as a missing module.
    import semantica.ingest.db_ingestor as dbi

    with patch.object(
        dbi.DBIngestor, "execute_query", side_effect=OSError(111, "Connection refused")
    ):
        with pytest.raises(ProcessingError) as excinfo:
            seed_manager.load_from_database(
                "postgresql://u:p@10.0.0.9/db", query="SELECT 1"
            )
        assert "Failed to load from database" in str(excinfo.value)
        assert "module not available" not in str(excinfo.value)
        assert isinstance(excinfo.value.__cause__, OSError)

def test_load_from_database_import_error(seed_manager):
    with patch.dict("sys.modules", {"semantica.ingest.db_ingestor": None}):
        # This simulates the module not existing.
        with pytest.raises(ProcessingError) as excinfo:
            seed_manager.load_from_database("sqlite:///:memory:", query="SELECT 1")
        assert "Database ingestion module not available" in str(excinfo.value)

@patch("semantica.seed.seed_manager.request_with_ssrf_guard")
def test_load_from_api(mock_guard, seed_manager):
    mock_response = MagicMock()
    mock_response.json.return_value = {"results": [{"id": 1, "name": "Alice"}]}
    mock_guard.return_value = mock_response

    records = seed_manager.load_from_api(
        api_url="http://api.example.com",
        endpoint="users",
        entity_type="User"
    )

    assert len(records) == 1
    assert records[0]["id"] == 1
    assert records[0]["entity_type"] == "User"
    mock_guard.assert_called_once()

def test_load_from_api_blocks_private_by_default(seed_manager):
    with pytest.raises(ProcessingError) as excinfo:
        seed_manager.load_from_api(api_url="http://127.0.0.1:8000/secret")
    assert "blocked" in str(excinfo.value).lower() or "not allowed" in str(excinfo.value).lower()

@patch("semantica.seed.seed_manager.request_with_ssrf_guard")
def test_load_from_api_allows_private_when_configured(mock_guard, seed_manager):
    mock_response = MagicMock()
    mock_response.json.return_value = {"results": [{"id": 1, "name": "Alice"}]}
    mock_guard.return_value = mock_response

    manager = SeedDataManager(config={"allow_private_ips": True})
    records = manager.load_from_api(
        api_url="http://127.0.0.1:8000",
        endpoint="users",
        entity_type="User"
    )

    assert len(records) == 1
    mock_guard.assert_called_once()
    # The opt-in flag must reach the guard
    call_kwargs = mock_guard.call_args[1]
    assert call_kwargs["allow_private_ips"] is True


@patch("semantica.seed.seed_manager.request_with_ssrf_guard")
def test_load_from_api_does_not_mutate_caller_headers_dict(mock_guard, seed_manager):
    """Regression test for issue #947 audit: load_from_api must not mutate the
    caller's headers dict in-place when api_key is provided.

    Before the fix, ``request_headers = headers or {}`` aliased the caller's dict.
    Writing ``request_headers["Authorization"] = ...`` then silently modified the
    caller's original dict, potentially leaking credentials to subsequent calls
    that reused the same headers dict without expecting it to carry Authorization.
    """
    mock_response = MagicMock()
    mock_response.json.return_value = {"results": []}
    mock_guard.return_value = mock_response

    # Caller owns this dict and expects it to be unchanged after the call.
    original_headers = {"X-Custom-Header": "value"}
    headers_before = dict(original_headers)  # snapshot

    seed_manager.load_from_api(
        api_url="http://api.example.com",
        api_key="secret-key",
        headers=original_headers,
    )

    # The caller's dict must be unchanged — Authorization must NOT have been added.
    assert original_headers == headers_before, (
        "load_from_api must not mutate the caller's headers dict; "
        f"expected {headers_before!r}, got {original_headers!r}"
    )

    # The guard must still have received Authorization (in its own copy).
    call_kwargs = mock_guard.call_args[1]
    guard_headers = call_kwargs.get("headers", {})
    assert guard_headers.get("Authorization") == "Bearer secret-key"


@patch("semantica.seed.seed_manager.request_with_ssrf_guard")
def test_load_from_api_does_not_mutate_empty_headers_dict(mock_guard, seed_manager):
    """When headers=None, a fresh dict is created — no aliasing to a shared mutable default."""
    mock_response = MagicMock()
    mock_response.json.return_value = {"results": []}
    mock_guard.return_value = mock_response

    seed_manager.load_from_api(
        api_url="http://api.example.com",
        api_key="key",
        headers=None,
    )

    call_kwargs = mock_guard.call_args[1]
    guard_headers = call_kwargs.get("headers", {})
    assert guard_headers.get("Authorization") == "Bearer key"

def test_load_source(seed_manager, temp_data_dir):
    json_file = temp_data_dir / "source.json"
    with open(json_file, "w") as f:
        json.dump([{"id": "1", "name": "Alice"}], f)

    seed_manager.register_source(
        name="test_source",
        format="json",
        location=str(json_file)
    )

    records = seed_manager.load_source("test_source")
    assert len(records) == 1

def test_load_source_not_registered(seed_manager):
    with pytest.raises(ProcessingError):
        seed_manager.load_source("unknown_source")

def test_load_source_unsupported_format(seed_manager):
    seed_manager.sources["bad_source"] = SeedDataSource(
        name="bad_source",
        format="xml",
        location="test.xml"
    )
    with pytest.raises(ProcessingError):
        seed_manager.load_source("bad_source")

def test_create_foundation_graph(seed_manager, temp_data_dir):
    # Setup sources
    entities_file = temp_data_dir / "entities.json"
    with open(entities_file, "w") as f:
        json.dump([
            {"id": "e1", "name": "Entity1", "type": "Type1"},
            {"id": "e2", "name": "Entity2", "type": "Type2"}
        ], f)
    
    rels_file = temp_data_dir / "rels.json"
    with open(rels_file, "w") as f:
        json.dump([
            {"source_id": "e1", "target_id": "e2", "type": "LINKS_TO"}
        ], f)

    seed_manager.register_source("entities", "json", str(entities_file))
    seed_manager.register_source("rels", "json", str(rels_file))

    foundation = seed_manager.create_foundation_graph()
    
    assert len(foundation["entities"]) == 2
    assert len(foundation["relationships"]) == 1
    assert foundation["metadata"]["source_count"] == 2
    assert foundation["entities"][0]["id"] == "e1"
    assert foundation["relationships"][0]["source_id"] == "e1"

def test_integrate_with_extracted(seed_manager):
    seed_data = {
        "entities": [{"id": "1", "name": "Seed", "prop": "A"}],
        "relationships": [{"source_id": "1", "target_id": "2", "type": "R1"}]
    }
    extracted_data = {
        "entities": [{"id": "1", "name": "Extracted", "prop": "B"}, {"id": "2", "name": "New"}],
        "relationships": [{"source_id": "1", "target_id": "2", "type": "R1"}, {"source_id": "2", "target_id": "3", "type": "R2"}]
    }

    # Test seed_first
    integrated = seed_manager.integrate_with_extracted(seed_data, extracted_data, "seed_first")
    assert len(integrated["entities"]) == 2
    entity1 = next(e for e in integrated["entities"] if e["id"] == "1")
    assert entity1["name"] == "Seed" # Seed priority
    assert len(integrated["relationships"]) == 2

    # Test extracted_first
    integrated = seed_manager.integrate_with_extracted(seed_data, extracted_data, "extracted_first")
    entity1 = next(e for e in integrated["entities"] if e["id"] == "1")
    assert entity1["name"] == "Extracted" # Extracted priority

    # Test merge
    integrated = seed_manager.integrate_with_extracted(seed_data, extracted_data, "merge")
    entity1 = next(e for e in integrated["entities"] if e["id"] == "1")
    assert entity1["name"] == "Seed" # Seed overwrites conflict but keeps other props?
    # Logic in code: merged = {**extracted_entity, **seed_entity} -> seed overwrites extracted
    
def test_validate_quality(seed_manager):
    valid_data = {
        "entities": [{"id": "1", "type": "Person"}],
        "relationships": [{"source_id": "1", "target_id": "2", "type": "KNOWS"}]
    }
    result = seed_manager.validate_quality(valid_data)
    assert result["valid"] is True
    assert len(result["errors"]) == 0

    invalid_data = {
        "entities": [{"name": "No ID"}],
        "relationships": [{"type": "KNOWS"}]
    }
    result = seed_manager.validate_quality(invalid_data)
    assert result["valid"] is False
    assert len(result["errors"]) > 0

def test_export_seed_data(seed_manager, temp_data_dir):
    # Setup seed data
    seed_manager.seed_data.entities = [{"id": "1", "name": "Alice"}]
    seed_manager.seed_data.relationships = [{"source_id": "1", "target_id": "2", "type": "KNOWS"}]

    # Test JSON export
    json_file = temp_data_dir / "export.json"
    seed_manager.export_seed_data(json_file, format="json")
    assert json_file.exists()
    with open(json_file) as f:
        data = json.load(f)
        assert len(data["entities"]) == 1

    # Test CSV export
    csv_file = temp_data_dir / "export.csv"
    seed_manager.export_seed_data(csv_file, format="csv")
    
    entities_csv = temp_data_dir / "export_entities.csv"
    assert entities_csv.exists()
    with open(entities_csv) as f:
        reader = csv.DictReader(f)
        rows = list(reader)
        assert len(rows) == 1
        assert rows[0]["id"] == "1"

