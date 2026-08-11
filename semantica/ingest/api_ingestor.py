"""
REST API Ingestion Module

This module provides comprehensive REST API ingestion capabilities for the
Semantica framework, enabling data extraction from any REST API endpoint.

Key Features:
    - Generic REST API client
    - Pagination support
    - Authentication (API key, OAuth, Bearer token)
    - Batch request handling
    - Error handling and retry logic

Main Classes:
    - RESTIngestor: Main REST API ingestion class
    - APIData: Data representation for API ingestion

Example Usage:
    >>> from semantica.ingest import RESTIngestor
    >>> ingestor = RESTIngestor()
    >>> data = ingestor.ingest_endpoint("https://api.example.com/data", headers={"Authorization": "Bearer token"})
    >>> paginated_data = ingestor.paginated_fetch("https://api.example.com/data", page_size=100)
"""

import json
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Dict, List, Optional, Union
from urllib.parse import urljoin, urlparse

import requests
from requests.adapters import HTTPAdapter
try:
    from urllib3.util.retry import Retry
except (ImportError, OSError):
    from requests.packages.urllib3.util.retry import Retry

from ..utils.exceptions import ProcessingError, ValidationError
from ..utils.logging import get_logger
from ..utils.progress_tracker import get_progress_tracker
from .ssrf import parse_bool, request_with_ssrf_guard


@dataclass
class APIData:
    """REST API data representation."""

    data: Union[List[Dict[str, Any]], Dict[str, Any]]
    response_status: int
    endpoint: str
    metadata: Dict[str, Any] = field(default_factory=dict)
    ingested_at: datetime = field(default_factory=datetime.now)


class RESTIngestor:
    """
    REST API ingestion handler.

    This class provides comprehensive REST API ingestion capabilities,
    supporting generic API endpoints with authentication, pagination, and
    error handling.

    Features:
        - Generic REST API client
        - Pagination support
        - Authentication (API key, OAuth, Bearer token)
        - Batch request handling
        - Error handling and retry logic

    Example Usage:
        >>> ingestor = RESTIngestor()
        >>> data = ingestor.ingest_endpoint("https://api.example.com/data")
        >>> paginated_data = ingestor.paginated_fetch("https://api.example.com/data", page_size=100)
    """

    def __init__(self, config: Optional[Dict[str, Any]] = None, **kwargs):
        """
        Initialize REST API ingestor.

        Args:
            config: Optional REST API ingestion configuration dictionary
            **kwargs: Additional configuration parameters (merged into config).
                Recognized keys include ``allow_private_ips`` (default False) to
                opt into fetching private/loopback/link-local endpoints.
        """
        self.logger = get_logger("api_ingestor")
        self.config = config or {}
        self.config.update(kwargs)
        self.allow_private_ips = parse_bool(
            self.config.get("allow_private_ips"), default=False
        )

        # Initialize session with retry strategy
        self.session = requests.Session()
        retry_strategy = Retry(
            total=self.config.get("max_retries", 3),
            backoff_factor=self.config.get("backoff_factor", 1),
            status_forcelist=[429, 500, 502, 503, 504],
        )
        adapter = HTTPAdapter(max_retries=retry_strategy)
        self.session.mount("http://", adapter)
        self.session.mount("https://", adapter)

        # Set default headers
        default_headers = self.config.get("headers", {})
        if default_headers:
            self.session.headers.update(default_headers)

        # Initialize progress tracker
        self.progress_tracker = get_progress_tracker()

        self.logger.debug(
            "REST API ingestor initialized (allow_private_ips=%s)",
            self.allow_private_ips,
        )

    def ingest_endpoint(
        self,
        endpoint: str,
        method: str = "GET",
        headers: Optional[Dict[str, str]] = None,
        params: Optional[Dict[str, Any]] = None,
        data: Optional[Union[Dict, str]] = None,
        json_data: Optional[Dict[str, Any]] = None,
        **options,
    ) -> APIData:
        """
        Ingest data from REST API endpoint.

        This method makes a request to a REST API endpoint and returns the response data.

        Args:
            endpoint: API endpoint URL
            method: HTTP method (GET, POST, PUT, DELETE, etc.)
            headers: Optional request headers
            params: Optional query parameters
            data: Optional request body (for form data)
            json_data: Optional JSON request body
            **options: Additional request options

        Returns:
            APIData: Ingested data object containing:
                - data: Response data (parsed JSON or raw text)
                - response_status: HTTP status code
                - endpoint: Endpoint URL
                - metadata: Additional metadata

        Raises:
            ValidationError: If endpoint is invalid or fails SSRF checks
            ProcessingError: If request fails
        """
        tracking_id = self.progress_tracker.start_tracking(
            file=endpoint,
            module="ingest",
            submodule="RESTIngestor",
            message=f"Requesting: {method} {endpoint}",
        )

        try:
            # Prepare request
            request_headers = self.session.headers.copy()
            if headers:
                request_headers.update(headers)

            # Make request (SSRF-safe; validates URL and each redirect hop)
            response = request_with_ssrf_guard(
                method,
                endpoint,
                session=self.session,
                allow_private_ips=self.allow_private_ips,
                headers=request_headers,
                params=params,
                data=data,
                json=json_data,
                timeout=self.config.get("timeout", 30),
                **options,
            )

            # Check for errors
            response.raise_for_status()

            # Parse response
            try:
                response_data = response.json()
            except ValueError:
                # Not JSON, return as text
                response_data = response.text

            self.progress_tracker.stop_tracking(
                tracking_id,
                status="completed",
                message=f"Request successful: {response.status_code}",
            )

            self.logger.info(
                f"API request completed: {method} {endpoint} - {response.status_code}"
            )

            return APIData(
                data=response_data,
                response_status=response.status_code,
                endpoint=endpoint,
                metadata={
                    "method": method,
                    "headers": dict(response.headers),
                    "content_type": response.headers.get("Content-Type"),
                },
            )

        except ValidationError:
            self.progress_tracker.stop_tracking(
                tracking_id, status="failed", message=f"Invalid endpoint URL: {endpoint}"
            )
            raise
        except requests.exceptions.RequestException as e:
            self.progress_tracker.stop_tracking(
                tracking_id, status="failed", message=str(e)
            )
            self.logger.error(f"Failed to ingest endpoint {endpoint}: {e}")
            raise ProcessingError(f"Failed to ingest endpoint: {e}") from e

    def paginated_fetch(
        self,
        endpoint: str,
        page_size: int = 100,
        page_param: str = "page",
        size_param: str = "size",
        limit: Optional[int] = None,
        **options,
    ) -> List[APIData]:
        """
        Fetch paginated data from REST API endpoint.

        This method handles pagination automatically, fetching all pages or up to
        a specified limit.

        Args:
            endpoint: API endpoint URL
            page_size: Number of items per page
            page_param: Query parameter name for page number
            size_param: Query parameter name for page size
            limit: Maximum number of items to fetch (optional)
            **options: Additional request options

        Returns:
            List of APIData objects, one per page

        Raises:
            ProcessingError: If pagination fails
        """
        tracking_id = self.progress_tracker.start_tracking(
            file=endpoint,
            module="ingest",
            submodule="RESTIngestor",
            message=f"Fetching paginated data from: {endpoint}",
        )

        try:
            all_pages = []
            page = 1
            total_fetched = 0

            while True:
                # Build query parameters
                params = options.get("params", {}).copy()
                params[page_param] = page
                params[size_param] = page_size

                # Fetch page
                page_options = options.copy()
                page_options["params"] = params

                page_data = self.ingest_endpoint(endpoint, **page_options)

                # Extract items from response
                if isinstance(page_data.data, list):
                    items = page_data.data
                elif isinstance(page_data.data, dict):
                    # Try common pagination response formats
                    items = (
                        page_data.data.get("items", [])
                        or page_data.data.get("data", [])
                        or page_data.data.get("results", [])
                        or [page_data.data]
                    )
                else:
                    items = []

                if not items:
                    # No more items, stop pagination
                    break

                all_pages.append(page_data)
                total_fetched += len(items)

                # Check limit
                if limit and total_fetched >= limit:
                    break

                # Check if there are more pages
                if isinstance(page_data.data, dict):
                    has_more = (
                        page_data.data.get("has_more", False)
                        or page_data.data.get("next", None) is not None
                    )
                    if not has_more:
                        break

                page += 1

            self.progress_tracker.stop_tracking(
                tracking_id,
                status="completed",
                message=f"Fetched {len(all_pages)} pages, {total_fetched} items",
            )

            self.logger.info(
                f"Paginated fetch completed: {len(all_pages)} page(s), {total_fetched} item(s)"
            )

            return all_pages

        except Exception as e:
            self.progress_tracker.stop_tracking(
                tracking_id, status="failed", message=str(e)
            )
            self.logger.error(f"Failed to fetch paginated data: {e}")
            raise ProcessingError(f"Failed to fetch paginated data: {e}") from e

    def batch_request(
        self,
        endpoints: List[str],
        method: str = "GET",
        **options,
    ) -> List[APIData]:
        """
        Make batch requests to multiple endpoints.

        This method makes requests to multiple endpoints and returns all results.

        Args:
            endpoints: List of endpoint URLs
            method: HTTP method
            **options: Additional request options

        Returns:
            List of APIData objects, one per endpoint

        Raises:
            ProcessingError: If batch request fails
        """
        tracking_id = self.progress_tracker.start_tracking(
            file="batch",
            module="ingest",
            submodule="RESTIngestor",
            message=f"Batch request: {len(endpoints)} endpoints",
        )

        try:
            results = []
            for endpoint in endpoints:
                try:
                    data = self.ingest_endpoint(endpoint, method=method, **options)
                    results.append(data)
                except Exception as e:
                    self.logger.warning(f"Failed to fetch {endpoint}: {e}")
                    if self.config.get("fail_fast", False):
                        raise

            self.progress_tracker.stop_tracking(
                tracking_id,
                status="completed",
                message=f"Batch request completed: {len(results)}/{len(endpoints)} successful",
            )

            self.logger.info(
                f"Batch request completed: {len(results)}/{len(endpoints)} successful"
            )

            return results

        except Exception as e:
            self.progress_tracker.stop_tracking(
                tracking_id, status="failed", message=str(e)
            )
            self.logger.error(f"Failed to execute batch request: {e}")
            raise ProcessingError(f"Failed to execute batch request: {e}") from e

