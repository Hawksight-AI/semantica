import sys
import types
from unittest.mock import MagicMock

# --- Mock missing cloud modules ---
# We must mock these BEFORE importing the file_ingestor module
# and we must populate the attributes that the code tries to import/patch.

module_names = [
    "boto3",
    "google",
    "google.cloud",
    "google.cloud.storage",
    "azure",
    "azure.storage",
    "azure.storage.blob",
]

for name in module_names:
    if name not in sys.modules:
        mod = types.ModuleType(name)
        sys.modules[name] = mod

# Explicitly add the classes that will be patched/used
sys.modules["google.cloud.storage"].Client = MagicMock()
sys.modules["azure.storage.blob"].BlobServiceClient = MagicMock()
sys.modules["boto3"].client = MagicMock()

from pathlib import Path  # noqa: E402
from unittest.mock import patch  # noqa: E402

# Now proceed with normal imports
import pytest  # noqa: E402

from semantica.ingest.file_ingestor import (  # noqa: E402
    CloudStorageIngestor,
    FileIngestor,
    FileObject,
    FileTypeDetector,
    ProcessingError,
    ValidationError,
)


# --- Fixtures ---
@pytest.fixture
def temp_files(tmp_path: Path) -> Path:
    """Create a temporary directory with some dummy files."""
    txt_file = tmp_path / "test.txt"
    txt_file.write_text("Hello World", encoding="utf-8")  # 11 bytes

    # Binary file (PDF signature)
    pdf_file = tmp_path / "test.pdf"
    pdf_file.write_bytes(b"%PDF-1.4 content")

    # Subdirectory
    sub_dir = tmp_path / "subdir"
    sub_dir.mkdir()
    sub_file = sub_dir / "sub.log"
    sub_file.write_text("Log content")

    # Latin-1 file to test encoding fallback (4 bytes)
    latin_file = tmp_path / "latin.txt"
    latin_file.write_bytes(b"Caf\xe9")

    return tmp_path


# --- FileObject Tests ---
def test_file_object_text_decoding() -> None:
    """Test text property decoding logic."""
    f1 = FileObject(
        path="p",
        name="n",
        size=1,
        file_type="txt",
        content=b"Hello",
    )
    f2 = FileObject(
        path="p",
        name="n",
        size=1,
        file_type="txt",
        content=b"Caf\xe9",
    )
    f3 = FileObject(
        path="p",
        name="n",
        size=1,
        file_type="txt",
        content=None,
    )
    f4 = FileObject(
        path="p", name="n", size=1, file_type="txt", content="Already String"
    )

    assert f1.text == "Hello"
    assert f2.text == "Café"
    assert f3.text == ""
    assert f4.text == "Already String"


# --- FileTypeDetector Tests ---
def test_type_detector_extended() -> None:
    """Test extended file type detection logic."""

    detector = FileTypeDetector()
    png_sig = b"\x89\x50\x4e\x47\x0d\x0a\x1a\x0a"

    # We must mock .exists() so detect_type enters the mime detection block
    with patch("pathlib.Path.exists", return_value=True):
        with patch("mimetypes.guess_type", return_value=("video/mp4", None)):
            is_mp4 = detector.detect_type("movie.mp4")

    detected_gz = detector.detect_type("file.tar.gz")
    detected_png = detector.detect_type("test", content=png_sig)
    detected_unknown = detector.detect_type("unknown")

    assert detected_gz == "gz"
    assert is_mp4 == "mp4"
    assert detected_png == "png"
    assert detected_unknown == "unknown"


@pytest.mark.parametrize("suffix", [".jsonl", ".ndjson"])
def test_type_detector_supports_line_delimited_json(suffix: str) -> None:
    """Line-delimited JSON is a common interchange format for bulk data."""

    detector = FileTypeDetector()

    assert detector.detect_type(f"resources{suffix}") in {"jsonl", "ndjson"}
    assert detector.is_supported(suffix.lstrip("."))


def test_ingest_ndjson_file_preserves_content(tmp_path: Path) -> None:
    """FHIR Bulk/NDJSON resources can be ingested as a supported file."""

    path = tmp_path / "Patient.000.ndjson"
    path.write_text(
        '{"resourceType":"Patient","id":"synthetic-1"}\n'
        '{"resourceType":"Patient","id":"synthetic-2"}\n',
        encoding="utf-8",
    )

    result = FileIngestor().ingest_file(path)

    assert result.file_type == "ndjson"
    assert result.metadata["is_supported"] is True
    assert result.text.count('"resourceType":"Patient"') == 2


# --- CloudStorageIngestor Tests ---
@patch("boto3.client")
def test_cloud_storage_s3(mock_boto: MagicMock) -> None:
    """Test S3 provider."""

    mock_s3 = mock_boto.return_value
    mock_s3.get_paginator.return_value.paginate.return_value = [
        {
            "Contents": [
                {
                    "Key": "doc.txt",
                    "Size": 100,
                    "LastModified": "2025",
                    "ETag": "tag",
                }
            ]
        }
    ]
    mock_s3.get_object.return_value = {
        "Body": MagicMock(read=lambda: b"s3_data"),
    }

    ingestor = CloudStorageIngestor(
        "s3",
        access_key_id="x",
        secret_access_key="y",
    )
    objects = ingestor.list_objects("bucket")
    content = ingestor.download_object("bucket", "doc.txt")

    assert objects[0]["key"] == "doc.txt"
    assert content == b"s3_data"


@patch("google.cloud.storage.Client")
def test_cloud_storage_gcs(mock_gcs_cls: MagicMock) -> None:
    """Test Google Cloud Storage provider."""

    mock_client = mock_gcs_cls.return_value
    mock_blob = MagicMock()
    mock_blob.name = "gcs.txt"
    mock_blob.size = 200
    mock_blob.updated = "2025"
    mock_blob.etag = "tag"
    mock_blob.download_as_bytes.return_value = b"gcs_data"

    mock_client.bucket.return_value.list_blobs.return_value = [mock_blob]
    mock_client.bucket.return_value.blob.return_value = mock_blob

    ingestor = CloudStorageIngestor("gcs")
    objects = ingestor.list_objects("bucket")
    content = ingestor.download_object("bucket", "gcs.txt")

    assert objects[0]["key"] == "gcs.txt"
    assert content == b"gcs_data"


@patch("azure.storage.blob.BlobServiceClient.from_connection_string")
def test_cloud_storage_azure(mock_azure_cls: MagicMock) -> None:
    """Test Azure Blob Storage provider."""

    mock_client = mock_azure_cls.return_value
    mock_blob = MagicMock()
    mock_blob.name = "azure.txt"
    mock_blob.size = 300
    mock_blob.last_modified = "2025"
    mock_blob.etag = "tag"

    mock_container = mock_client.get_container_client.return_value
    mock_container.list_blobs.return_value = [mock_blob]

    mock_blob_client = mock_container.get_blob_client.return_value
    mock_download = mock_blob_client.download_blob.return_value
    mock_download.readall.return_value = b"azure_data"

    ingestor = CloudStorageIngestor("azure", connection_string="conn")
    objects = ingestor.list_objects("bucket")
    content = ingestor.download_object("bucket", "azure.txt")

    assert objects[0]["key"] == "azure.txt"
    assert content == b"azure_data"


def test_cloud_storage_invalid() -> None:
    """Test invalid cloud provider raises error."""

    with pytest.raises(ValueError):
        CloudStorageIngestor("dropbox")


def test_cloud_storage_list_error() -> None:
    """Test error handling in list_objects."""

    with patch("boto3.client") as mock_boto:
        # Raise error on the METHOD call, not the constructor
        mock_boto.return_value.get_paginator.side_effect = Exception(
            "Auth Fail",
        )

        ingestor = CloudStorageIngestor("s3")
        with pytest.raises(ProcessingError):
            ingestor.list_objects("bucket")


def test_cloud_storage_download_error() -> None:
    """Test error handling in download_object."""

    with patch("boto3.client") as mock_boto:
        mock_boto.return_value.get_object.side_effect = Exception("Fail")
        ingestor = CloudStorageIngestor("s3")
        with pytest.raises(ProcessingError):
            ingestor.download_object("bucket", "key")


# --- FileIngestor Tests ---
def test_ingest_directory_recursive(temp_files: Path) -> None:
    """Test recursive directory ingestion."""

    ingestor = FileIngestor()
    results = ingestor.ingest_directory(temp_files, recursive=True)

    assert len(results) >= 3


def test_ingest_directory_non_recursive(temp_files: Path) -> None:
    """Test scanning only top level."""

    ingestor = FileIngestor()
    results = ingestor.ingest_directory(temp_files, recursive=False)
    has_sub_log = any("sub.log" in f.name for f in results)

    assert len(results) == 3
    assert not has_sub_log


def test_ingest_file_callback(temp_files: Path) -> None:
    """Test progress callback."""

    ingestor = FileIngestor()
    mock_cb = MagicMock()
    ingestor.set_progress_callback(mock_cb)

    ingestor.ingest_directory(temp_files, recursive=False)

    assert mock_cb.called


def test_ingest_file_fail_fast(temp_files: Path) -> None:
    """Test directory ingestion failure handling."""

    ingestor = FileIngestor(fail_fast=True)

    with patch.object(ingestor, "ingest_file", side_effect=Exception("Boom")):
        with pytest.raises(ProcessingError):
            ingestor.ingest_directory(temp_files)


def test_ingest_alias(temp_files: Path) -> None:
    """Test the .ingest() alias method."""

    ingestor = FileIngestor()
    res_dir = ingestor.ingest(temp_files)
    res_file = ingestor.ingest(temp_files / "test.txt")

    assert len(res_dir) > 0
    assert len(res_file) == 1
    with pytest.raises(ValidationError):
        ingestor.ingest("ghost_path")


@patch("semantica.ingest.file_ingestor.CloudStorageIngestor")
def test_ingest_cloud_loop_errors(mock_cloud_cls: MagicMock) -> None:
    """Test cloud ingestion where one file fails."""

    ingestor = FileIngestor(fail_fast=False)
    mock_inst = mock_cloud_cls.return_value
    mock_inst.list_objects.return_value = [
        {"key": "good.txt", "size": 10, "last_modified": "2025", "etag": "1"},
        {"key": "bad.txt", "size": 10, "last_modified": "2025", "etag": "2"},
    ]
    mock_inst.download_object.side_effect = [b"good", Exception("Bad dl")]

    results = ingestor.ingest_cloud("s3", "bucket")

    assert len(results) == 1
    assert results[0].name == "good.txt"


def test_scan_directory_filters(temp_files: Path) -> None:
    """Deep dive into filter logic."""

    ingestor = FileIngestor()

    # latin.txt is 4 bytes. 4 <= 5 is True.
    # So we expect latin.txt to survive.
    res_max = ingestor.scan_directory(temp_files, max_size=5)

    # All files are small.
    res_min = ingestor.scan_directory(temp_files, min_size=1)

    assert len(res_max) == 1  # Expect latin.txt
    assert len(res_min) >= 3
