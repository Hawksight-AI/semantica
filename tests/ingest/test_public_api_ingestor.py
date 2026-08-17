from unittest.mock import MagicMock, patch

import pytest
import requests

from semantica.ingest import (
    APIData,
    PublicAPIDetection,
    PublicAPIExamples,
    PublicAPIIngestor,
    ingest,
    ingest_public_api,
    list_available_methods,
)
from semantica.utils.exceptions import ProcessingError, ValidationError


def _mock_response(
    status_code=200,
    json_payload=None,
    text="",
    headers=None,
):
    response = MagicMock()
    response.status_code = status_code
    response.headers = headers or {}
    response.text = text
    if json_payload is not None:
        response.json.return_value = json_payload
    else:
        response.json.side_effect = ValueError("not json")

    if status_code >= 400:
        response.raise_for_status.side_effect = requests.exceptions.HTTPError(
            f"{status_code} error"
        )
    else:
        response.raise_for_status.return_value = None
    return response


def test_public_api_examples_catalog_lists_endpoints_and_samples() -> None:
    names = PublicAPIExamples.names()
    endpoints = PublicAPIExamples.endpoints()
    testing_examples = PublicAPIExamples.list_examples(tag="testing")
    sample = PublicAPIExamples.sample_response("jsonplaceholder_posts")

    assert "jsonplaceholder_posts" in names
    assert endpoints["jsonplaceholder_posts"].startswith("https://")
    assert {example.name for example in testing_examples} >= {
        "jsonplaceholder_posts",
        "jsonplaceholder_users",
        "jsonplaceholder_todos",
    }
    assert sample[0]["title"] == "sample post"


def test_public_api_ingestor_ingests_json_records() -> None:
    payload = [{"id": 1, "title": "hello"}]

    with patch("requests.Session") as mock_session_class:
        mock_session = mock_session_class.return_value
        mock_session.headers = {}
        mock_session.request.return_value = _mock_response(
            json_payload=payload,
            text='[{"id": 1, "title": "hello"}]',
            headers={"Content-Type": "application/json"},
        )

        result = PublicAPIIngestor(rate_limit_delay=0).ingest_public_api(
            "https://jsonplaceholder.typicode.com/posts"
        )

    assert isinstance(result, APIData)
    assert result.data == payload
    assert result.metadata["public_api"] is True
    assert result.metadata["authentication"] == "none"
    assert result.metadata["response_format"] == "json"
    assert result.metadata["record_count"] == 1


def test_public_api_ingestor_extracts_nested_record_path() -> None:
    payload = {
        "success": True,
        "result": {
            "count": 1,
            "results": [{"id": "dataset-1", "title": "Dataset"}],
        },
    }

    with patch("requests.Session") as mock_session_class:
        mock_session = mock_session_class.return_value
        mock_session.headers = {}
        mock_session.request.return_value = _mock_response(
            json_payload=payload,
            text='{"success": true}',
            headers={"Content-Type": "application/json"},
        )

        result = PublicAPIIngestor(rate_limit_delay=0).ingest_public_api(
            "https://catalog.data.gov/api/3/action/package_search",
            record_path="result.results",
        )

    assert result.data == [{"id": "dataset-1", "title": "Dataset"}]
    assert result.metadata["record_path"] == "result.results"


def test_public_api_ingestor_parses_csv_records() -> None:
    csv_text = "id,name\n1,Ada\n2,Grace\n"

    with patch("requests.Session") as mock_session_class:
        mock_session = mock_session_class.return_value
        mock_session.headers = {}
        mock_session.request.return_value = _mock_response(
            text=csv_text,
            headers={"Content-Type": "text/csv"},
        )

        result = PublicAPIIngestor(rate_limit_delay=0).ingest_public_api(
            "https://example.com/data.csv"
        )

    assert result.data == [{"id": "1", "name": "Ada"}, {"id": "2", "name": "Grace"}]
    assert result.metadata["response_format"] == "csv"


def test_public_api_ingestor_parses_xml_records_with_record_path() -> None:
    xml_text = "<items><item id='1'>Ada</item><item id='2'>Grace</item></items>"

    with patch("requests.Session") as mock_session_class:
        mock_session = mock_session_class.return_value
        mock_session.headers = {}
        mock_session.request.return_value = _mock_response(
            text=xml_text,
            headers={"Content-Type": "application/xml"},
        )

        result = PublicAPIIngestor(rate_limit_delay=0).ingest_public_api(
            "https://example.com/data.xml",
            record_path="children",
        )

    assert result.metadata["response_format"] == "xml"
    assert result.data[0]["tag"] == "item"
    assert result.data[0]["attributes"] == {"id": "1"}
    assert result.data[0]["text"] == "Ada"


def test_public_api_ingestor_rejects_malicious_xml_entities() -> None:
    xml_text = """<?xml version="1.0"?>
<!DOCTYPE items [
<!ENTITY xxe SYSTEM "file:///etc/passwd">
]>
<items><item>&xxe;</item></items>
"""

    with patch("requests.Session") as mock_session_class:
        mock_session = mock_session_class.return_value
        mock_session.headers = {}
        mock_session.request.return_value = _mock_response(
            text=xml_text,
            headers={"Content-Type": "application/xml"},
        )

        with pytest.raises(
            ProcessingError, match="Failed to parse XML public API response"
        ):
            PublicAPIIngestor(rate_limit_delay=0).ingest_public_api(
                "https://example.com/data.xml"
            )


def test_public_api_detection_reports_public_endpoint() -> None:
    with patch("requests.Session") as mock_session_class:
        mock_session = mock_session_class.return_value
        mock_session.headers = {}
        mock_session.request.return_value = _mock_response(
            headers={"Content-Type": "application/json"}
        )

        detection = PublicAPIIngestor(rate_limit_delay=0).detect_public_api(
            "https://jsonplaceholder.typicode.com/posts"
        )

    assert isinstance(detection, PublicAPIDetection)
    assert detection.is_public is True
    assert detection.requires_auth is False
    assert detection.response_status == 200


def test_public_api_detection_reports_auth_required() -> None:
    with patch("requests.Session") as mock_session_class:
        mock_session = mock_session_class.return_value
        mock_session.headers = {}
        mock_session.request.return_value = _mock_response(
            status_code=401,
            headers={"WWW-Authenticate": "Bearer"},
        )

        with patch(
            "semantica.ingest.ssrf.socket.getaddrinfo",
            return_value=[(None, None, None, None, ("93.184.216.34", 0))],
        ):
            detection = PublicAPIIngestor(rate_limit_delay=0).detect_public_api(
                "https://api.example.com/private"
            )

    assert detection.is_public is False
    assert detection.requires_auth is True
    assert detection.response_status == 401


def test_detect_public_api_propagates_ssrf_validation_error() -> None:
    """detect_public_api() must surface ValidationError, not swallow it.

    request_with_ssrf_guard() raises ValidationError (not
    requests.exceptions.RequestException) for SSRF-blocked hosts, so
    detect_public_api()'s error handling must catch it explicitly like its
    sibling ingest_public_api() already does.
    """
    with patch("requests.Session") as mock_session_class:
        mock_session = mock_session_class.return_value
        mock_session.headers = {}

        with patch(
            "semantica.ingest.ssrf.socket.getaddrinfo",
            return_value=[(None, None, None, None, ("127.0.0.1", 0))],
        ):
            with pytest.raises(ValidationError):
                PublicAPIIngestor(rate_limit_delay=0).detect_public_api(
                    "https://blocked.example.com/data"
                )


def test_detect_public_api_rejects_duplicate_session_and_allow_private_ips_kwargs() -> None:
    """Passing session/allow_private_ips through **options must not crash.

    Both are always supplied explicitly to request_with_ssrf_guard(); caller
    copies must be dropped from **options rather than causing a
    'got multiple values for keyword argument' TypeError.
    """
    with patch("requests.Session") as mock_session_class:
        mock_session = mock_session_class.return_value
        mock_session.headers = {}
        mock_session.request.return_value = _mock_response(
            headers={"Content-Type": "application/json"}
        )

        detection = PublicAPIIngestor(rate_limit_delay=0).detect_public_api(
            "https://jsonplaceholder.typicode.com/posts",
            allow_private_ips=True,
            session=object(),
        )

    assert detection.is_public is True


def test_ingest_public_api_rejects_duplicate_session_and_allow_private_ips_kwargs() -> None:
    with patch("requests.Session") as mock_session_class:
        mock_session = mock_session_class.return_value
        mock_session.headers = {}
        mock_session.request.return_value = _mock_response(
            json_payload=[{"id": 1}],
            headers={"Content-Type": "application/json"},
        )

        result = PublicAPIIngestor(rate_limit_delay=0).ingest_public_api(
            "https://jsonplaceholder.typicode.com/posts",
            allow_private_ips=True,
            session=object(),
        )

    assert result.response_status == 200


def test_public_api_ingestor_rejects_authentication_inputs() -> None:
    with patch("requests.Session") as mock_session_class:
        mock_session = mock_session_class.return_value
        mock_session.headers = {}
        ingestor = PublicAPIIngestor(rate_limit_delay=0)

        with pytest.raises(ValidationError, match="no-auth endpoints"):
            ingestor.ingest_public_api(
                "https://api.example.com/data",
                headers={"Authorization": "Bearer token"},
            )

        mock_session.request.assert_not_called()


def test_public_api_ingestor_parses_string_boolean_config() -> None:
    payload = [{"id": 1, "title": "hello"}]

    with patch("requests.Session") as mock_session_class:
        mock_session = mock_session_class.return_value
        mock_session.headers = {}
        mock_session.request.return_value = _mock_response(
            json_payload=payload,
            text='[{"id": 1, "title": "hello"}]',
            headers={"Content-Type": "application/json"},
        )

        ingestor = PublicAPIIngestor(
            config={"validate_no_auth": "false"},
            rate_limit_delay=0,
        )
        with patch(
            "semantica.ingest.ssrf.socket.getaddrinfo",
            return_value=[(None, None, None, None, ("93.184.216.34", 0))],
        ):
            result = ingestor.ingest_public_api(
                "https://api.example.com/data",
                headers={"Authorization": "Bearer token"},
            )

    assert ingestor.validate_no_auth is False
    assert result.data == payload


def test_public_api_convenience_methods_and_registry_dispatch() -> None:
    payload = [{"id": 1}]

    with patch("requests.Session") as mock_session_class:
        mock_session = mock_session_class.return_value
        mock_session.headers = {}
        mock_session.request.return_value = _mock_response(
            json_payload=payload,
            text='[{"id": 1}]',
            headers={"Content-Type": "application/json"},
        )

        direct = ingest_public_api(
            "https://jsonplaceholder.typicode.com/posts",
            rate_limit_delay=0,
        )
        unified = ingest(
            "https://jsonplaceholder.typicode.com/posts",
            source_type="public_api",
            rate_limit_delay=0,
        )
        methods = list_available_methods("public_api")

    assert isinstance(direct, APIData)
    assert direct.data == payload
    assert unified["data"].data == payload
    assert "endpoint" in methods["public_api"]
    assert "detect" in methods["public_api"]


@pytest.mark.parametrize("url", [
    "https://api.example.com/data?api_key=SECRET",
    "https://api.example.com/data?token=abc123",
    "https://api.example.com/data?access_token=xyz&other=1",
])
def test_public_api_ingestor_rejects_auth_credential_in_url(url: str) -> None:
    with patch("requests.Session") as mock_session_class:
        mock_session = mock_session_class.return_value
        mock_session.headers = {}

        with pytest.raises(ValidationError, match="no-auth endpoints"):
            PublicAPIIngestor(rate_limit_delay=0).ingest_public_api(url)

        mock_session.request.assert_not_called()


def test_public_api_detection_returns_not_public_for_url_with_auth_param() -> None:
    # detect_public_api does not raise; it returns a detection result with is_public=False
    with patch("requests.Session") as mock_session_class:
        mock_session = mock_session_class.return_value
        mock_session.headers = {}

        detection = PublicAPIIngestor(rate_limit_delay=0).detect_public_api(
            "https://api.example.com/data?api_key=SECRET"
        )

    assert detection.is_public is False
    assert detection.requires_auth is True
    assert "url_param:api_key" in detection.metadata.get("auth_indicators", [])
    mock_session.request.assert_not_called()


def test_require_public_false_allows_successful_response() -> None:
    payload = [{"id": 1}]

    with patch("requests.Session") as mock_session_class:
        mock_session = mock_session_class.return_value
        mock_session.headers = {}
        mock_session.request.return_value = _mock_response(
            json_payload=payload,
            text='[{"id": 1}]',
            headers={"Content-Type": "application/json"},
        )

        result = PublicAPIIngestor(rate_limit_delay=0).ingest_public_api(
            "https://example.com/api/data",
            require_public=False,
        )

    assert result.data == payload
    assert result.metadata["requires_auth"] is False


def test_require_public_false_with_401_still_raises_via_raise_for_status() -> None:
    with patch("requests.Session") as mock_session_class:
        mock_session = mock_session_class.return_value
        mock_session.headers = {}
        mock_session.request.return_value = _mock_response(status_code=401)

        with pytest.raises(ProcessingError):
            PublicAPIIngestor(rate_limit_delay=0).ingest_public_api(
                "https://example.com/api/data",
                require_public=False,
            )


def test_html_response_is_not_misclassified_as_xml() -> None:
    html = "<!DOCTYPE html><html><body>403 Forbidden</body></html>"

    with patch("requests.Session") as mock_session_class:
        mock_session = mock_session_class.return_value
        mock_session.headers = {}
        mock_session.request.return_value = _mock_response(
            text=html,
            headers={"Content-Type": "text/html; charset=utf-8"},
        )

        result = PublicAPIIngestor(
            rate_limit_delay=0, validate_no_auth=False
        ).ingest_public_api(
            "https://example.com/api/data",
            require_public=False,
        )

    assert result.metadata["response_format"] == "text"
