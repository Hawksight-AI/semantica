"""
Public API Ingestion Module

This module provides no-auth public API ingestion built on top of the generic
RESTIngestor. It focuses on contributor-friendly endpoints, public API
detection, polite rate limiting, and response normalization for JSON, CSV, and
XML APIs.

Example Usage:
    >>> from semantica.ingest import PublicAPIIngestor
    >>> ingestor = PublicAPIIngestor(rate_limit_delay=1.0)
    >>> data = ingestor.ingest_public_api(
    ...     "https://jsonplaceholder.typicode.com/posts"
    ... )
    >>> data.metadata["record_count"]
    100
"""

from __future__ import annotations

import copy
import csv
import io
import time
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Dict, List, Optional, Tuple
from urllib.parse import parse_qs, urlparse

import requests
from lxml import etree as lxml_etree

try:
    from defusedxml import ElementTree as safe_xml_etree
    from defusedxml.common import DefusedXmlException
except ModuleNotFoundError:  # pragma: no cover - fallback for minimal installs
    safe_xml_etree = None

    class DefusedXmlException(Exception):
        """Fallback exception placeholder when defusedxml is unavailable."""

        pass


from ..utils.exceptions import ProcessingError, ValidationError
from ..utils.logging import get_logger
from .api_ingestor import APIData, RESTIngestor
from .ssrf import request_with_ssrf_guard

AUTH_HEADER_NAMES = {
    "authorization",
    "proxy-authorization",
    "x-api-key",
    "api-key",
    "apikey",
    "ocp-apim-subscription-key",
    "x-rapidapi-key",
    "x-auth-token",
    "x-access-token",
}

AUTH_PARAM_NAMES = {
    "api_key",
    "apikey",
    "access_token",
    "auth_token",
    "bearer_token",
    "client_secret",
    "token",
    "subscription_key",
    "subscription-key",
}

_SAFE_XML_PARSER = lxml_etree.XMLParser(
    resolve_entities=False,
    no_network=True,
    recover=False,
    huge_tree=False,
    load_dtd=False,
)


@dataclass
class PublicAPIExample:
    """Pre-configured public API endpoint definition."""

    name: str
    endpoint: str
    description: str
    method: str = "GET"
    params: Dict[str, Any] = field(default_factory=dict)
    headers: Dict[str, str] = field(default_factory=dict)
    response_format: str = "auto"
    record_path: Optional[str] = None
    tags: List[str] = field(default_factory=list)
    rate_limit_delay: Optional[float] = None


@dataclass
class PublicAPIDetection:
    """Result of checking whether an endpoint can be reached without auth."""

    endpoint: str
    is_public: bool
    requires_auth: bool
    response_status: Optional[int] = None
    reason: str = ""
    metadata: Dict[str, Any] = field(default_factory=dict)
    checked_at: datetime = field(default_factory=datetime.now)


class PublicAPIExamples:
    """
    Catalog of no-auth public API examples for tests and demos.

    The examples intentionally avoid credentials and use endpoints suitable for
    CI-friendly mocked tests or quick local experiments.
    """

    _EXAMPLES: Dict[str, PublicAPIExample] = {
        "jsonplaceholder_posts": PublicAPIExample(
            name="jsonplaceholder_posts",
            endpoint="https://jsonplaceholder.typicode.com/posts",
            description="Fake blog post records for REST API testing.",
            response_format="json",
            tags=["json", "testing", "placeholder"],
            rate_limit_delay=0.5,
        ),
        "jsonplaceholder_users": PublicAPIExample(
            name="jsonplaceholder_users",
            endpoint="https://jsonplaceholder.typicode.com/users",
            description="Fake user records for REST API testing.",
            response_format="json",
            tags=["json", "testing", "placeholder"],
            rate_limit_delay=0.5,
        ),
        "jsonplaceholder_todos": PublicAPIExample(
            name="jsonplaceholder_todos",
            endpoint="https://jsonplaceholder.typicode.com/todos",
            description="Fake todo records for REST API testing.",
            response_format="json",
            tags=["json", "testing", "placeholder"],
            rate_limit_delay=0.5,
        ),
        "rest_countries_all": PublicAPIExample(
            name="rest_countries_all",
            endpoint="https://restcountries.com/v3.1/all",
            description="Country reference data from REST Countries.",
            params={
                "fields": "name,capital,region,population,cca2,cca3",
            },
            response_format="json",
            tags=["json", "countries", "reference"],
            rate_limit_delay=1.0,
        ),
        "data_gov_datasets": PublicAPIExample(
            name="data_gov_datasets",
            endpoint="https://catalog.data.gov/api/3/action/package_search",
            description="Data.gov catalog package search results.",
            params={"q": "climate", "rows": 10},
            response_format="json",
            record_path="result.results",
            tags=["json", "government", "datasets"],
            rate_limit_delay=1.0,
        ),
        "open_meteo_forecast": PublicAPIExample(
            name="open_meteo_forecast",
            endpoint="https://api.open-meteo.com/v1/forecast",
            description="Open-Meteo forecast sample for Berlin.",
            params={
                "latitude": 52.52,
                "longitude": 13.41,
                "current": "temperature_2m,wind_speed_10m",
            },
            response_format="json",
            tags=["json", "weather", "forecast"],
            rate_limit_delay=1.0,
        ),
    }

    _SAMPLE_RESPONSES: Dict[str, Any] = {
        "jsonplaceholder_posts": [
            {"userId": 1, "id": 1, "title": "sample post", "body": "body text"}
        ],
        "jsonplaceholder_users": [
            {"id": 1, "name": "Leanne Graham", "email": "leanne@example.com"}
        ],
        "jsonplaceholder_todos": [
            {"userId": 1, "id": 1, "title": "sample todo", "completed": False}
        ],
        "rest_countries_all": [
            {
                "name": {"common": "India", "official": "Republic of India"},
                "capital": ["New Delhi"],
                "region": "Asia",
                "population": 1407563842,
                "cca2": "IN",
                "cca3": "IND",
            }
        ],
        "data_gov_datasets": {
            "success": True,
            "result": {
                "count": 1,
                "results": [
                    {
                        "id": "sample-dataset",
                        "title": "Sample Dataset",
                        "metadata_created": "2026-01-01T00:00:00",
                    }
                ],
            },
        },
        "open_meteo_forecast": {
            "latitude": 52.52,
            "longitude": 13.41,
            "current": {"temperature_2m": 18.2, "wind_speed_10m": 9.1},
        },
    }

    @classmethod
    def list_examples(cls, tag: Optional[str] = None) -> List[PublicAPIExample]:
        """
        List available public API examples.

        Args:
            tag: Optional tag filter such as "json", "government", or "testing"

        Returns:
            List of public API example definitions
        """
        examples = cls._EXAMPLES.values()
        if tag:
            tag_lower = tag.lower()
            examples = [example for example in examples if tag_lower in example.tags]
        return [copy.deepcopy(example) for example in examples]

    @classmethod
    def names(cls, tag: Optional[str] = None) -> List[str]:
        """Return example names, optionally filtered by tag."""
        return [example.name for example in cls.list_examples(tag=tag)]

    @classmethod
    def endpoints(cls) -> Dict[str, str]:
        """Return a mapping of example name to endpoint URL."""
        return {name: example.endpoint for name, example in cls._EXAMPLES.items()}

    @classmethod
    def get(cls, name: str) -> PublicAPIExample:
        """
        Get a public API example by name.

        Args:
            name: Example name. Hyphens are normalized to underscores.

        Raises:
            ValidationError: If the example is unknown
        """
        normalized_name = name.lower().replace("-", "_")
        if normalized_name not in cls._EXAMPLES:
            available = ", ".join(sorted(cls._EXAMPLES))
            raise ValidationError(
                f"Unknown public API example: {name}. Available examples: {available}"
            )
        return copy.deepcopy(cls._EXAMPLES[normalized_name])

    @classmethod
    def sample_response(cls, name: str) -> Any:
        """
        Return a small mock response payload for an example.

        These fixtures are intended for tests and documentation snippets so
        contributors can exercise ingestion without making live network calls.
        """
        normalized_name = name.lower().replace("-", "_")
        if normalized_name not in cls._SAMPLE_RESPONSES:
            available = ", ".join(sorted(cls._SAMPLE_RESPONSES))
            raise ValidationError(
                f"No sample response for public API example: {name}. "
                f"Available samples: {available}"
            )
        return copy.deepcopy(cls._SAMPLE_RESPONSES[normalized_name])


class PublicAPIIngestor(RESTIngestor):
    """
    Public, no-auth API ingestion handler.

    PublicAPIIngestor uses RESTIngestor's HTTP session and retry behavior while
    adding no-auth validation, endpoint-level public detection, response
    normalization, and built-in public API examples.
    """

    def __init__(
        self,
        config: Optional[Dict[str, Any]] = None,
        rate_limit_delay: Optional[float] = None,
        validate_no_auth: Optional[bool] = None,
        **kwargs,
    ):
        """
        Initialize public API ingestor.

        Args:
            config: Optional ingestion configuration dictionary
            rate_limit_delay: Minimum seconds between public API requests
            validate_no_auth: Reject auth headers/params before requests
            **kwargs: Additional configuration values
        """
        merged_config = (config or {}).copy()
        merged_config.update(kwargs)
        if rate_limit_delay is not None:
            merged_config["rate_limit_delay"] = rate_limit_delay
        if validate_no_auth is not None:
            merged_config["validate_no_auth"] = validate_no_auth

        super().__init__(config=merged_config)
        self.logger = get_logger("public_api_ingestor")
        self.rate_limit_delay = float(
            self.config.get("rate_limit_delay", self.config.get("delay", 1.0)) or 0.0
        )
        self.validate_no_auth = self._coerce_bool(
            self.config.get("validate_no_auth", True),
            default=True,
        )
        self._last_request_time = 0.0

        self.logger.debug("Public API ingestor initialized")

    def detect_public_api(
        self,
        endpoint: str,
        method: str = "GET",
        headers: Optional[Dict[str, str]] = None,
        params: Optional[Dict[str, Any]] = None,
        **options,
    ) -> PublicAPIDetection:
        """
        Detect whether an endpoint is reachable without authentication.

        Detection is endpoint-level: a successful unauthenticated request means
        this specific endpoint appears public, not necessarily the entire API.
        """
        self._validate_endpoint(endpoint)
        auth_indicators = self._auth_indicators(
            headers=headers, params=params, options=options, endpoint=endpoint
        )
        if auth_indicators:
            return PublicAPIDetection(
                endpoint=endpoint,
                is_public=False,
                requires_auth=True,
                reason=(
                    "Authentication credentials were provided; "
                    "no-auth access was not tested."
                ),
                metadata={"auth_indicators": auth_indicators},
            )

        request_options = options.copy()
        timeout = request_options.pop("timeout", self.config.get("timeout", 30))
        rate_limit_delay = request_options.pop("rate_limit_delay", None)
        # session and allow_private_ips are always supplied explicitly below;
        # drop any caller-provided copies so request_with_ssrf_guard() does
        # not receive duplicate keyword arguments.
        request_options.pop("session", None)
        request_options.pop("allow_private_ips", None)
        request_headers = self._merged_headers(headers)

        try:
            self._wait_if_needed(rate_limit_delay=rate_limit_delay)
            # Route through the SSRF guard so that:
            #   * redirects to private/loopback IPs are blocked, and
            #   * Authorization / Proxy-Authorization are stripped on
            #     cross-origin redirects (issue #947).
            response = request_with_ssrf_guard(
                method,
                endpoint,
                session=self.session,
                headers=request_headers,
                params=params,
                timeout=timeout,
                allow_private_ips=self.allow_private_ips,
                **request_options,
            )
        except (ValidationError, ProcessingError):
            raise
        except requests.exceptions.RequestException as exc:
            self.logger.error(f"Failed to detect public API {endpoint}: {exc}")
            raise ProcessingError(f"Failed to detect public API: {exc}") from exc

        is_public, requires_auth, reason = self._classify_public_response(response)
        return PublicAPIDetection(
            endpoint=endpoint,
            is_public=is_public,
            requires_auth=requires_auth,
            response_status=response.status_code,
            reason=reason,
            metadata={
                "method": method,
                "content_type": response.headers.get("Content-Type"),
                "www_authenticate": response.headers.get("WWW-Authenticate"),
            },
        )

    def is_public_api(self, endpoint: str, **options) -> bool:
        """Return True when an endpoint appears reachable without auth."""
        return self.detect_public_api(endpoint, **options).is_public

    def ingest_public_api(
        self,
        endpoint: str,
        method: str = "GET",
        headers: Optional[Dict[str, str]] = None,
        params: Optional[Dict[str, Any]] = None,
        data: Optional[Any] = None,
        json_data: Optional[Dict[str, Any]] = None,
        response_format: str = "auto",
        record_path: Optional[str] = None,
        normalize_records: bool = True,
        require_public: bool = True,
        rate_limit_delay: Optional[float] = None,
        **options,
    ) -> APIData:
        """
        Ingest data from a public API endpoint without authentication.

        Args:
            endpoint: Public API endpoint URL
            method: HTTP method, usually GET
            headers: Optional non-auth request headers
            params: Optional query parameters
            data: Optional request body
            json_data: Optional JSON request body
            response_format: "auto", "json", "csv", "xml", or "text"
            record_path: Dot path to records inside nested JSON/XML data
            normalize_records: Convert response into a list of dictionaries
            require_public: Raise if response indicates auth is required
            rate_limit_delay: Per-request delay override
            **options: Additional requests options

        Returns:
            APIData: Normalized public API response and metadata
        """
        self._validate_endpoint(endpoint)
        self._validate_no_auth_request(headers=headers, params=params, options=options, endpoint=endpoint)

        tracking_id = self.progress_tracker.start_tracking(
            file=endpoint,
            module="ingest",
            submodule="PublicAPIIngestor",
            message=f"Requesting public API: {method} {endpoint}",
        )

        request_options = options.copy()
        timeout = request_options.pop("timeout", self.config.get("timeout", 30))
        # session and allow_private_ips are always supplied explicitly below;
        # drop any caller-provided copies so request_with_ssrf_guard() does
        # not receive duplicate keyword arguments.
        request_options.pop("session", None)
        request_options.pop("allow_private_ips", None)
        request_headers = self._merged_headers(headers)

        try:
            self._wait_if_needed(rate_limit_delay=rate_limit_delay)
            # Route through the SSRF guard so that:
            #   * redirects to private/loopback IPs are blocked, and
            #   * Authorization / Proxy-Authorization are stripped on
            #     cross-origin redirects even when validate_no_auth=False
            #     (issue #947).
            response = request_with_ssrf_guard(
                method,
                endpoint,
                session=self.session,
                headers=request_headers,
                params=params,
                data=data,
                json=json_data,
                timeout=timeout,
                allow_private_ips=self.allow_private_ips,
                **request_options,
            )

            is_public, requires_auth, reason = self._classify_public_response(response)
            if require_public and requires_auth:
                raise ValidationError(
                    f"Endpoint appears to require authentication: {endpoint} "
                    f"({response.status_code}). Use RESTIngestor for "
                    "authenticated APIs."
                )

            response.raise_for_status()
            parsed_data, detected_format = self._parse_response(
                response=response,
                response_format=response_format,
                endpoint=endpoint,
            )

            if normalize_records:
                result_data = self._to_records(parsed_data, record_path=record_path)
            elif record_path:
                result_data = self._extract_record_path(parsed_data, record_path)
            else:
                result_data = parsed_data

            record_count = len(result_data) if isinstance(result_data, list) else 1

            self.progress_tracker.stop_tracking(
                tracking_id,
                status="completed",
                message=f"Public API request successful: {response.status_code}",
            )
            self.logger.info(
                f"Public API request completed: {method} {endpoint} - "
                f"{response.status_code}"
            )

            return APIData(
                data=result_data,
                response_status=response.status_code,
                endpoint=endpoint,
                metadata={
                    "method": method,
                    "headers": dict(response.headers),
                    "content_type": response.headers.get("Content-Type"),
                    "public_api": is_public,
                    "authentication": "none",
                    "public_detection_reason": reason,
                    "requires_auth": requires_auth,
                    "response_format": detected_format,
                    "record_path": record_path,
                    "normalized_records": normalize_records,
                    "record_count": record_count,
                    "source_data_type": type(parsed_data).__name__,
                },
            )

        except (ValidationError, ProcessingError):
            self.progress_tracker.stop_tracking(
                tracking_id, status="failed", message="Public API ingestion failed"
            )
            raise
        except requests.exceptions.RequestException as exc:
            self.progress_tracker.stop_tracking(
                tracking_id, status="failed", message=str(exc)
            )
            self.logger.error(f"Failed to ingest public API {endpoint}: {exc}")
            raise ProcessingError(f"Failed to ingest public API: {exc}") from exc
        except Exception as exc:
            self.progress_tracker.stop_tracking(
                tracking_id, status="failed", message=str(exc)
            )
            self.logger.error(f"Failed to ingest public API {endpoint}: {exc}")
            raise ProcessingError(f"Failed to ingest public API: {exc}") from exc

    def ingest_example(self, name: str, **overrides) -> APIData:
        """
        Ingest one of the pre-configured public API examples.

        Args:
            name: Example name from PublicAPIExamples
            **overrides: Optional endpoint, params, headers, record_path, or
                response_format overrides
        """
        example = PublicAPIExamples.get(name)
        params = example.params.copy()
        params.update(overrides.pop("params", {}) or {})
        headers = example.headers.copy()
        headers.update(overrides.pop("headers", {}) or {})

        endpoint = overrides.pop("endpoint", example.endpoint)
        method = overrides.pop("method", example.method)
        response_format = overrides.pop("response_format", example.response_format)
        record_path = overrides.pop("record_path", example.record_path)
        rate_limit_delay = overrides.pop("rate_limit_delay", example.rate_limit_delay)

        result = self.ingest_public_api(
            endpoint=endpoint,
            method=method,
            headers=headers or None,
            params=params or None,
            response_format=response_format,
            record_path=record_path,
            rate_limit_delay=rate_limit_delay,
            **overrides,
        )
        result.metadata["example_name"] = example.name
        result.metadata["example_description"] = example.description
        result.metadata["example_tags"] = example.tags
        return result

    def ingest_examples(self, names: List[str], **options) -> List[APIData]:
        """Ingest multiple pre-configured public API examples."""
        return [self.ingest_example(name, **copy.deepcopy(options)) for name in names]

    def batch_public_apis(
        self,
        endpoints: List[str],
        method: str = "GET",
        **options,
    ) -> List[APIData]:
        """Ingest multiple public API endpoints with no-auth validation."""
        results: List[APIData] = []
        for endpoint in endpoints:
            try:
                results.append(
                    self.ingest_public_api(endpoint, method=method, **copy.deepcopy(options))
                )
            except Exception as exc:
                self.logger.warning(f"Failed to fetch public API {endpoint}: {exc}")
                if self.config.get("fail_fast", False):
                    raise
        return results

    def _validate_endpoint(self, endpoint: str) -> None:
        parsed = urlparse(endpoint)
        if parsed.scheme not in {"http", "https"} or not parsed.netloc:
            raise ValidationError(
                f"Public API endpoint must be an absolute HTTP(S) URL: {endpoint}"
            )

    def _merged_headers(
        self, headers: Optional[Dict[str, str]] = None
    ) -> Dict[str, str]:
        base_headers = dict(getattr(self.session, "headers", {}) or {})
        if headers:
            base_headers.update(headers)
        return base_headers

    def _auth_indicators(
        self,
        headers: Optional[Dict[str, str]] = None,
        params: Optional[Dict[str, Any]] = None,
        options: Optional[Dict[str, Any]] = None,
        endpoint: Optional[str] = None,
    ) -> List[str]:
        indicators: List[str] = []
        merged_headers = self._merged_headers(headers)
        for header_name in merged_headers:
            if header_name.lower() in AUTH_HEADER_NAMES:
                indicators.append(f"header:{header_name}")

        for param_name in params or {}:
            if param_name.lower() in AUTH_PARAM_NAMES:
                indicators.append(f"param:{param_name}")

        if options and options.get("auth") is not None:
            indicators.append("request:auth")

        if endpoint:
            for param_name in parse_qs(urlparse(endpoint).query):
                if param_name.lower() in AUTH_PARAM_NAMES:
                    indicators.append(f"url_param:{param_name}")

        return indicators

    def _validate_no_auth_request(
        self,
        headers: Optional[Dict[str, str]] = None,
        params: Optional[Dict[str, Any]] = None,
        options: Optional[Dict[str, Any]] = None,
        endpoint: Optional[str] = None,
    ) -> None:
        if not self.validate_no_auth:
            return

        auth_indicators = self._auth_indicators(
            headers=headers,
            params=params,
            options=options,
            endpoint=endpoint,
        )
        if auth_indicators:
            indicators = ", ".join(auth_indicators)
            raise ValidationError(
                "Public API ingestion only supports no-auth endpoints. "
                f"Authentication indicators found: {indicators}. "
                "Use RESTIngestor for authenticated APIs."
            )

    def _wait_if_needed(self, rate_limit_delay: Optional[float] = None) -> None:
        delay = self.rate_limit_delay if rate_limit_delay is None else rate_limit_delay
        delay = float(delay or 0.0)
        now = time.time()

        if delay > 0 and self._last_request_time:
            elapsed = now - self._last_request_time
            if elapsed < delay:
                time.sleep(delay - elapsed)

        self._last_request_time = time.time()

    def _classify_public_response(
        self, response: requests.Response
    ) -> Tuple[bool, bool, str]:
        status_code = response.status_code
        if 200 <= status_code < 300:
            return True, False, "Endpoint responded successfully without auth."
        if status_code in {401, 403}:
            return (
                False,
                True,
                "Endpoint returned an authentication or authorization status.",
            )
        if status_code == 429:
            return False, False, "Endpoint is rate limited; public access is unclear."
        return False, False, f"Endpoint returned status {status_code}."

    def _parse_response(
        self,
        response: requests.Response,
        response_format: str,
        endpoint: str,
    ) -> Tuple[Any, str]:
        detected_format = self._detect_response_format(
            response=response,
            requested_format=response_format,
            endpoint=endpoint,
        )

        try:
            if detected_format == "json":
                return response.json(), "json"
            if detected_format == "csv":
                return self._parse_csv(response.text), "csv"
            if detected_format == "xml":
                return self._parse_xml(response.text), "xml"
            return response.text, "text"
        except ValueError as exc:
            raise ProcessingError(
                f"Failed to parse {detected_format.upper()} public API response"
            ) from exc
        except (DefusedXmlException, lxml_etree.XMLSyntaxError) as exc:
            raise ProcessingError("Failed to parse XML public API response") from exc

    def _detect_response_format(
        self,
        response: requests.Response,
        requested_format: str,
        endpoint: str,
    ) -> str:
        requested = requested_format.lower()
        if requested != "auto":
            if requested not in {"json", "csv", "xml", "text"}:
                raise ValidationError(
                    "response_format must be one of: auto, json, csv, xml, text"
                )
            return requested

        content_type = response.headers.get("Content-Type", "").lower()
        endpoint_lower = endpoint.lower()
        text = (response.text or "").lstrip()

        if "json" in content_type or endpoint_lower.endswith(".json"):
            return "json"
        if "csv" in content_type or endpoint_lower.endswith(".csv"):
            return "csv"
        if "xml" in content_type or endpoint_lower.endswith(".xml"):
            return "xml"
        if text.startswith(("{", "[")):
            return "json"
        if text.startswith("<") and "text/html" not in content_type:
            return "xml"
        return "text"

    def _parse_csv(self, csv_text: str) -> List[Dict[str, Any]]:
        reader = csv.DictReader(io.StringIO(csv_text))
        return [dict(row) for row in reader]

    def _parse_xml(self, xml_text: str) -> Dict[str, Any]:
        if safe_xml_etree is not None:
            root = safe_xml_etree.fromstring(xml_text)
        else:
            root = lxml_etree.fromstring(
                xml_text.encode("utf-8"),
                parser=_SAFE_XML_PARSER,
            )
        return self._element_to_dict(root)

    def _element_to_dict(self, element: Any) -> Dict[str, Any]:
        children = [self._element_to_dict(child) for child in list(element)]
        return {
            "tag": self._strip_namespace(element.tag),
            "attributes": {
                self._strip_namespace(key): value
                for key, value in element.attrib.items()
            },
            "text": (element.text or "").strip(),
            "children": children,
        }

    def _strip_namespace(self, value: str) -> str:
        if value.startswith("{") and "}" in value:
            return value.split("}", 1)[1]
        return value

    @staticmethod
    def _coerce_bool(value: Any, default: bool = True) -> bool:
        """
        Coerce common boolean config values safely.

        Strings such as "false", "0", "no", and "off" become False, while
        "true", "1", "yes", and "on" become True. Unknown strings are rejected
        so config mistakes fail closed instead of silently enabling behavior.
        """
        if value is None:
            return default
        if isinstance(value, bool):
            return value
        if isinstance(value, str):
            normalized = value.strip().lower()
            if normalized in {"1", "true", "yes", "on"}:
                return True
            if normalized in {"0", "false", "no", "off"}:
                return False
            raise ValidationError(
                f"Invalid boolean value for validate_no_auth: {value!r}"
            )
        return bool(value)

    def _extract_record_path(self, data: Any, record_path: str) -> Any:
        current = data
        for part in record_path.split("."):
            if isinstance(current, dict):
                if part not in current:
                    raise ValidationError(
                        f"Record path '{record_path}' not found at '{part}'"
                    )
                current = current[part]
            elif isinstance(current, list):
                if part.isdigit():
                    index = int(part)
                    try:
                        current = current[index]
                    except IndexError as exc:
                        raise ValidationError(
                            f"Record path '{record_path}' index out of range: {part}"
                        ) from exc
                else:
                    values = []
                    for item in current:
                        if not isinstance(item, dict) or part not in item:
                            raise ValidationError(
                                f"Record path '{record_path}' not found at '{part}'"
                            )
                        value = item[part]
                        if isinstance(value, list):
                            values.extend(value)
                        else:
                            values.append(value)
                    current = values
            else:
                raise ValidationError(
                    f"Record path '{record_path}' cannot traverse "
                    f"{type(current).__name__}"
                )
        return current

    def _to_records(
        self, data: Any, record_path: Optional[str] = None
    ) -> List[Dict[str, Any]]:
        selected = self._extract_record_path(data, record_path) if record_path else data

        if isinstance(selected, dict):
            for key in ("items", "data", "results", "records"):
                value = selected.get(key)
                if isinstance(value, list):
                    selected = value
                    break
            else:
                selected = [selected]
        elif not isinstance(selected, list):
            selected = [selected]

        records: List[Dict[str, Any]] = []
        for item in selected:
            if isinstance(item, dict):
                records.append(item)
            else:
                records.append({"value": item})
        return records
