"""
Web Ingestion Module

This module provides comprehensive web scraping, crawling, and content extraction
capabilities for the Semantica framework, enabling ingestion from websites and
web-based sources.

Key Features:
    - HTTP/HTTPS content fetching with retry logic
    - Sitemap crawling and URL discovery
    - RSS/Atom feed processing
    - JavaScript rendering support (via optional dependencies)
    - Rate limiting and robots.txt compliance
    - Content extraction and cleaning
    - Link discovery and domain crawling

Main Classes:
    - WebIngestor: Main web ingestion class
    - SitemapCrawler: Sitemap-based crawling
    - ContentExtractor: Web content extraction
    - RateLimiter: Request rate limiting
    - RobotsChecker: Robots.txt compliance checker

Example Usage:
    >>> from semantica.ingest import WebIngestor
    >>> ingestor = WebIngestor(delay=1.0, respect_robots=True)
    >>> content = ingestor.ingest_url("https://example.com")
    >>> pages = ingestor.crawl_sitemap("https://example.com/sitemap.xml")

Author: Semantica Contributors
License: MIT
"""

import re
import time
import xml.etree.ElementTree as ET
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Dict, List, Optional, Set
from urllib.parse import urljoin, urlparse
from urllib.robotparser import RobotFileParser

import requests
from bs4 import BeautifulSoup
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

from ..utils.exceptions import ProcessingError, ValidationError
from ..utils.logging import get_logger
from ..utils.progress_tracker import get_progress_tracker
from .ssrf import parse_bool, request_with_ssrf_guard, validate_url_for_request


@dataclass
class WebContent:
    """Web content representation."""

    url: str
    title: str = ""
    text: str = ""
    html: str = ""
    metadata: Dict[str, Any] = field(default_factory=dict)
    links: List[str] = field(default_factory=list)
    fetched_at: datetime = field(default_factory=datetime.now)
    status_code: Optional[int] = None


class RateLimiter:
    """
    Simple rate limiter for web requests.

    This class enforces a minimum delay between web requests to ensure
    polite crawling behavior and avoid overwhelming target servers.

    Example Usage:
        >>> limiter = RateLimiter(delay=1.0)
        >>> limiter.wait_if_needed()  # Waits if needed before request
    """

    def __init__(self, delay: float = 1.0):
        """
        Initialize rate limiter.

        Sets up the rate limiter with a specified delay between requests.

        Args:
            delay: Minimum delay between requests in seconds (default: 1.0)
        """
        self.delay = delay
        self.last_request_time: float = 0.0

    def wait_if_needed(self):
        """
        Wait if necessary to respect rate limit.

        This method calculates the time elapsed since the last request and
        sleeps if necessary to maintain the minimum delay between requests.
        """
        elapsed = time.time() - self.last_request_time
        if elapsed < self.delay:
            sleep_time = self.delay - elapsed
            time.sleep(sleep_time)
        self.last_request_time = time.time()


class RobotsChecker:
    """
    Robots.txt compliance checker.

    This class checks robots.txt files to determine if URLs can be fetched
    according to the website's crawling policies. Caches parsed robots.txt
    files per domain for efficiency.

    Example Usage:
        >>> checker = RobotsChecker(user_agent="MyBot/1.0")
        >>> if checker.can_fetch("https://example.com/page"):
        ...     # Fetch the page
    """

    def __init__(self, user_agent: str = "SemanticaBot/1.0"):
        """
        Initialize robots checker.

        Sets up the checker with a user agent string for robots.txt compliance.

        Args:
            user_agent: User agent string to use for robots.txt checks
                       (default: "SemanticaBot/1.0")
        """
        self.user_agent = user_agent
        self.parsers: Dict[str, RobotFileParser] = {}

    def can_fetch(self, url: str) -> bool:
        """
        Check if URL can be fetched according to robots.txt.

        This method checks the robots.txt file for the URL's domain to determine
        if the specified user agent is allowed to fetch the URL. Caches parsed
        robots.txt files for efficiency.

        Args:
            url: URL to check for fetch permission

        Returns:
            bool: True if URL can be fetched, False if blocked by robots.txt
        """
        parsed = urlparse(url)
        domain = f"{parsed.scheme}://{parsed.netloc}"

        # Check if we already have a parser for this domain
        if domain not in self.parsers:
            # Create robots.txt URL
            robots_url = urljoin(domain, "/robots.txt")

            # Create and configure parser
            parser = RobotFileParser()
            parser.set_url(robots_url)

            try:
                parser.read()
            except Exception:
                # If robots.txt not available or unreadable, assume allowed
                # (per robots.txt spec: if file doesn't exist, all access is allowed)
                pass

            # Cache parser for this domain
            self.parsers[domain] = parser

        # Check permission using cached parser
        parser = self.parsers[domain]
        return parser.can_fetch(self.user_agent, url)


class ContentExtractor:
    """
    Web content extraction and cleaning.

    This class extracts text, metadata, and structured data from web pages
    using various extraction strategies. Handles HTML parsing, text cleaning,
    and metadata extraction.

    Example Usage:
        >>> extractor = ContentExtractor()
        >>> text = extractor.extract_text(html_content)
        >>> metadata = extractor.extract_metadata(html_content, url="https://example.com")
    """

    def __init__(self, **config):
        """
        Initialize content extractor.

        Sets up the extractor with configuration options.

        Args:
            **config: Extraction configuration options (currently unused)
        """
        self.logger = get_logger("content_extractor")
        self.config = config

    def extract_text(self, html_content: str) -> str:
        """
        Extract clean text from HTML content.

        This method removes script and style elements, extracts text content,
        and cleans up whitespace to produce readable text.

        Args:
            html_content: Raw HTML content string

        Returns:
            str: Cleaned text content extracted from HTML
        """
        soup = BeautifulSoup(html_content, "html.parser")

        # Remove script and style elements (not useful for text extraction)
        for element in soup(["script", "style"]):
            element.decompose()

        # Extract text content
        text = soup.get_text()

        # Clean whitespace: split into lines, strip each, then split on double spaces
        lines = (line.strip() for line in text.splitlines())
        chunks = (phrase.strip() for line in lines for phrase in line.split("  "))
        text = " ".join(chunk for chunk in chunks if chunk)

        return text

    def extract_metadata(
        self, html_content: str, url: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        Extract metadata from HTML content.

        This method extracts various metadata from HTML including:
        - Page title
        - Meta tags (description, keywords, etc.)
        - Open Graph data (og:title, og:description, etc.)
        - Source URL

        Args:
            html_content: Raw HTML content string
            url: Source URL for the page (optional)

        Returns:
            dict: Extracted metadata dictionary with keys:
                - url: Source URL (if provided)
                - title: Page title
                - description: Meta description (if available)
                - keywords: Meta keywords (if available)
                - og: Open Graph data dictionary (if available)
                - Additional meta tag values
        """
        metadata = {"url": url} if url else {}

        soup = BeautifulSoup(html_content, "html.parser")

        # Extract page title
        title_tag = soup.find("title")
        if title_tag:
            metadata["title"] = title_tag.get_text().strip()

        # Extract standard meta tags
        for meta_tag in soup.find_all("meta"):
            name = meta_tag.get("name") or meta_tag.get("property")
            content = meta_tag.get("content")
            if name and content:
                metadata[name.lower()] = content

        # Extract Open Graph data (for social media sharing)
        og_data = {}
        for meta_tag in soup.find_all("meta", property=re.compile(r"^og:")):
            property_name = meta_tag.get("property", "").replace("og:", "")
            content = meta_tag.get("content")
            if property_name and content:
                og_data[property_name] = content

        if og_data:
            metadata["og"] = og_data

        return metadata

    def extract_links(
        self, html_content: str, base_url: Optional[str] = None
    ) -> List[str]:
        """
        Extract links from HTML content.

        This method extracts all hyperlinks from HTML, resolves relative URLs
        to absolute URLs, and filters to only include HTTP/HTTPS links.

        Args:
            html_content: Raw HTML content string
            base_url: Base URL for resolving relative links (optional)

        Returns:
            list: List of extracted absolute URLs (HTTP/HTTPS only)
        """
        links = []

        soup = BeautifulSoup(html_content, "html.parser")

        # Extract all anchor tags with href attributes
        for link_tag in soup.find_all("a", href=True):
            href = link_tag["href"]

            # Resolve relative URLs to absolute URLs
            if base_url:
                link = urljoin(base_url, href)
            else:
                link = href

            # Filter to only include HTTP/HTTPS links
            parsed = urlparse(link)
            if parsed.scheme in ("http", "https"):
                links.append(link)

        return links


class SitemapCrawler:
    """
    Sitemap-based web crawling.

    This class provides specialized functionality for processing XML sitemaps
    and extracting URLs for web crawling. Supports both standard sitemaps
    and sitemap index files.

    Example Usage:
        >>> crawler = SitemapCrawler()
        >>> urls = crawler.parse_sitemap("https://example.com/sitemap.xml")
        >>> all_urls = crawler.crawl_sitemap_index("https://example.com/sitemap_index.xml")
    """

    def __init__(self, **config):
        """
        Initialize sitemap crawler.

        Sets up the crawler with configuration options.

        Args:
            **config: Crawler configuration options. Recognized keys:
                - allow_private_ips: Allow private/loopback sitemap hosts
        """
        self.logger = get_logger("sitemap_crawler")
        self.config = config
        self.allow_private_ips = parse_bool(
            config.get("allow_private_ips"), default=False
        )

    def parse_sitemap(self, sitemap_url: str) -> List[str]:
        """
        Parse sitemap and extract URLs.

        This method fetches and parses an XML sitemap, extracting all URLs
        listed in the sitemap. Supports both namespaced and non-namespaced
        sitemap formats.

        Args:
            sitemap_url: URL of the sitemap XML file

        Returns:
            list: List of URLs extracted from the sitemap

        Raises:
            ProcessingError: If sitemap cannot be fetched or parsed
            ValidationError: If sitemap_url fails SSRF checks
        """
        try:
            # Fetch sitemap (SSRF-safe; validates URL and each redirect hop)
            response = request_with_ssrf_guard(
                "GET",
                sitemap_url,
                allow_private_ips=self.allow_private_ips,
                timeout=30,
            )
            response.raise_for_status()

            # Parse XML
            root = ET.fromstring(response.content)

            # Standard sitemap namespace
            namespaces = {"sitemap": "http://www.sitemaps.org/schemas/sitemap/0.9"}

            urls = []

            # Extract URLs from urlset (namespaced format)
            for url_elem in root.findall(".//sitemap:url", namespaces):
                loc_elem = url_elem.find("sitemap:loc", namespaces)
                if loc_elem is not None and loc_elem.text:
                    urls.append(loc_elem.text.strip())

            # Also handle non-namespaced sitemaps (fallback)
            if not urls:
                for url_elem in root.findall(".//url"):
                    loc_elem = url_elem.find("loc")
                    if loc_elem is not None and loc_elem.text:
                        urls.append(loc_elem.text.strip())

            self.logger.debug(
                f"Extracted {len(urls)} URL(s) from sitemap: {sitemap_url}"
            )
            return urls

        except ValidationError:
            raise
        except Exception as e:
            self.logger.error(f"Failed to parse sitemap {sitemap_url}: {e}")
            raise ProcessingError(f"Failed to parse sitemap: {e}") from e

    def crawl_sitemap_index(self, index_url: str) -> List[str]:
        """
        Crawl sitemap index and all referenced sitemaps.

        This method fetches a sitemap index file, extracts references to
        individual sitemaps, and parses each referenced sitemap to collect
        all URLs. Useful for large websites with multiple sitemap files.

        Args:
            index_url: URL of the sitemap index XML file

        Returns:
            list: List of all URLs from all referenced sitemaps

        Raises:
            ProcessingError: If sitemap index cannot be fetched or parsed
            ValidationError: If index_url fails SSRF checks
        """
        try:
            # Fetch sitemap index (SSRF-safe; validates URL and each redirect hop)
            response = request_with_ssrf_guard(
                "GET",
                index_url,
                allow_private_ips=self.allow_private_ips,
                timeout=30,
            )
            response.raise_for_status()

            # Parse XML
            root = ET.fromstring(response.content)

            # Standard sitemap namespace
            namespaces = {"sitemap": "http://www.sitemaps.org/schemas/sitemap/0.9"}

            all_urls = []

            # Find sitemap references (namespaced format)
            for sitemap_elem in root.findall(".//sitemap:sitemap", namespaces):
                loc_elem = sitemap_elem.find("sitemap:loc", namespaces)
                if loc_elem is not None and loc_elem.text:
                    sitemap_url = loc_elem.text.strip()
                    # Parse each referenced sitemap
                    urls = self.parse_sitemap(sitemap_url)
                    all_urls.extend(urls)

            # Also handle non-namespaced sitemaps (fallback)
            if not all_urls:
                for sitemap_elem in root.findall(".//sitemap"):
                    loc_elem = sitemap_elem.find("loc")
                    if loc_elem is not None and loc_elem.text:
                        sitemap_url = loc_elem.text.strip()
                        urls = self.parse_sitemap(sitemap_url)
                        all_urls.extend(urls)

            self.logger.debug(
                f"Extracted {len(all_urls)} URL(s) from sitemap index: {index_url}"
            )
            return all_urls

        except ValidationError:
            raise
        except Exception as e:
            self.logger.error(f"Failed to crawl sitemap index {index_url}: {e}")
            raise ProcessingError(f"Failed to crawl sitemap index: {e}") from e


class WebIngestor:
    """
    Web content ingestion handler.

    This class provides comprehensive web content ingestion capabilities including
    single URL fetching, sitemap crawling, and domain-wide crawling. Includes
    rate limiting, robots.txt compliance, and content extraction.

    Features:
        - HTTP/HTTPS content fetching with retry logic
        - Sitemap crawling and URL discovery
        - Domain-wide crawling with link following
        - Rate limiting and politeness
        - Robots.txt compliance checking
        - Content extraction and cleaning

    Example Usage:
        >>> ingestor = WebIngestor(
        ...     delay=1.0,
        ...     respect_robots=True,
        ...     max_retries=3
        ... )
        >>> content = ingestor.ingest_url("https://example.com")
        >>> pages = ingestor.crawl_sitemap("https://example.com/sitemap.xml")
    """

    def __init__(
        self,
        user_agent: str = "SemanticaBot/1.0",
        delay: float = 1.0,
        respect_robots: bool = True,
        max_retries: int = 3,
        backoff_factor: float = 1.0,
        timeout: int = 30,
        allow_private_ips: bool = False,
        config: Optional[Dict[str, Any]] = None,
        **kwargs,
    ):
        """
        Initialize web ingestor.

        Sets up the ingestor with HTTP session, rate limiting, content extraction,
        and robots.txt compliance checking.

        Args:
            user_agent: User agent string for HTTP requests (default: "SemanticaBot/1.0")
            delay: Minimum delay between requests in seconds (default: 1.0)
            respect_robots: Whether to respect robots.txt (default: True)
            max_retries: Maximum number of retry attempts (default: 3)
            backoff_factor: Backoff factor for retries (default: 1.0)
            timeout: Request timeout in seconds (default: 30)
            allow_private_ips: Allow fetching private/loopback/link-local hosts
                (default: False). Opt in only for trusted internal deployments.
            config: Optional configuration dictionary (merged with kwargs)
            **kwargs: Additional configuration parameters
        """
        self.logger = get_logger("web_ingestor")
        self.config = config or {}
        self.config.update(kwargs)
        self.allow_private_ips = parse_bool(
            self.config.get("allow_private_ips", allow_private_ips),
            default=False,
        )
        self.config["allow_private_ips"] = self.allow_private_ips

        # Initialize HTTP session with retry strategy
        self.session = requests.Session()

        # Configure user agent
        user_agent = user_agent or self.config.get("user_agent", "SemanticaBot/1.0")
        self.session.headers.update({"User-Agent": user_agent})

        # Setup retry strategy for transient errors
        retry_strategy = Retry(
            total=max_retries,
            backoff_factor=backoff_factor,
            status_forcelist=[429, 500, 502, 503, 504],  # Retry on these status codes
        )
        adapter = HTTPAdapter(max_retries=retry_strategy)
        self.session.mount("http://", adapter)
        self.session.mount("https://", adapter)

        # Setup rate limiting
        self.rate_limiter = RateLimiter(delay=delay)

        # Initialize content extractor
        self.content_extractor = ContentExtractor(**self.config)

        # Setup robots checker if requested
        if respect_robots:
            self.robots_checker = RobotsChecker(user_agent=user_agent)
        else:
            self.robots_checker = None

        # Initialize progress tracker
        self.progress_tracker = get_progress_tracker()

        self.logger.debug(
            f"Web ingestor initialized: user_agent={user_agent}, "
            f"delay={delay}, respect_robots={respect_robots}, "
            f"allow_private_ips={self.allow_private_ips}"
        )

    def ingest_url(
        self, url: str, timeout: Optional[int] = None, **options
    ) -> WebContent:
        """
        Ingest content from a single URL.

        This method fetches content from a URL, checks robots.txt compliance,
        applies rate limiting, and extracts content and metadata.

        Args:
            url: URL to ingest (must be HTTP or HTTPS)
            timeout: Request timeout in seconds (default: self.config timeout or 30)
            **options: Additional processing options (unused)

        Returns:
            WebContent: Extracted web content with text, HTML, metadata, and links

        Raises:
            ValidationError: If URL is invalid
            ProcessingError: If URL is blocked by robots.txt or fetch fails
        """
        # Track URL ingestion
        tracking_id = self.progress_tracker.start_tracking(
            file=url, module="ingest", submodule="WebIngestor", message=f"URL: {url}"
        )

        try:
            # Validate before robots check: RobotsChecker.read() makes an unguarded
            # HTTP request to <host>/robots.txt and must not reach blocked addresses.
            validate_url_for_request(url, allow_private_ips=self.allow_private_ips)

            # Check robots.txt compliance
            if self.robots_checker and not self.robots_checker.can_fetch(url):
                self.logger.warning(f"URL {url} blocked by robots.txt")
                raise ProcessingError(f"URL blocked by robots.txt: {url}")

            # Apply rate limiting (wait if necessary)
            self.rate_limiter.wait_if_needed()

            # Fetch content with retry logic (SSRF-safe redirects)
            try:
                request_timeout = timeout or self.config.get("timeout", 30)
                response = request_with_ssrf_guard(
                    "GET",
                    url,
                    session=self.session,
                    allow_private_ips=self.allow_private_ips,
                    timeout=request_timeout,
                )
                response.raise_for_status()
            except ValidationError:
                raise
            except requests.RequestException as e:
                self.progress_tracker.stop_tracking(
                    tracking_id, status="failed", message=str(e)
                )
                self.logger.error(f"Failed to fetch URL {url}: {e}")
                raise ProcessingError(f"Failed to fetch URL: {e}") from e

            # Extract content and metadata
            html_content = response.text
            web_content = self.extract_content(html_content, url=url)
            web_content.status_code = response.status_code

            self.progress_tracker.stop_tracking(
                tracking_id,
                status="completed",
                message=f"Ingested {url} ({response.status_code})",
            )
            self.logger.debug(
                f"Ingested URL: {url}, status={response.status_code}, "
                f"text_length={len(web_content.text)}, links={len(web_content.links)}"
            )

            return web_content

        except Exception as e:
            self.progress_tracker.stop_tracking(
                tracking_id, status="failed", message=str(e)
            )
            raise

    def crawl_sitemap(
        self,
        sitemap_url: str,
        max_urls: Optional[int] = None,
        fail_fast: bool = False,
        **filters,
    ) -> List[WebContent]:
        """
        Crawl URLs from sitemap.

        This method parses a sitemap (or sitemap index), extracts URLs, applies
        filters, and ingests content from each URL. Supports both standard sitemaps
        and sitemap index files.

        Args:
            sitemap_url: URL of the sitemap XML file
            max_urls: Maximum number of URLs to crawl (default: None, crawl all)
            fail_fast: Whether to stop on first error (default: False)
            **filters: URL filtering criteria:
                - pattern: Regex pattern to match URLs
                - domains: List of allowed domains
                - exclude_pattern: Regex pattern to exclude URLs

        Returns:
            list: List of WebContent objects for successfully crawled URLs

        Raises:
            ProcessingError: If sitemap cannot be parsed or fail_fast=True and error occurs
        """
        # Track sitemap crawling
        tracking_id = self.progress_tracker.start_tracking(
            file=sitemap_url,
            module="ingest",
            submodule="WebIngestor",
            message=f"Sitemap: {sitemap_url}",
        )

        try:
            crawler = SitemapCrawler(**self.config)

            # Parse sitemap (try as regular sitemap first, then as index)
            try:
                urls = crawler.parse_sitemap(sitemap_url)
            except Exception as e:
                # Try as sitemap index
                try:
                    urls = crawler.crawl_sitemap_index(sitemap_url)
                except Exception:
                    raise ProcessingError(f"Failed to parse sitemap: {e}") from e

            self.logger.debug(f"Found {len(urls)} URL(s) in sitemap: {sitemap_url}")

            # Apply URL filters
            if filters:
                urls = self._apply_url_filters(urls, filters)
                self.logger.debug(f"After filtering: {len(urls)} URL(s)")

            # Process each URL
            web_contents = []
            max_urls = (
                max_urls or filters.get("max_urls") or self.config.get("max_urls")
            )

            self.progress_tracker.update_tracking(
                tracking_id, message=f"Crawling {len(urls)} URLs"
            )

            for idx, url in enumerate(urls):
                if max_urls and idx >= max_urls:
                    self.logger.debug(
                        f"Reached max_urls limit ({max_urls}), stopping crawl"
                    )
                    break

                try:
                    web_content = self.ingest_url(url)
                    web_contents.append(web_content)
                    self.logger.debug(
                        f"Crawled URL {idx+1}/{min(len(urls), max_urls or len(urls))}: {url}"
                    )
                except Exception as e:
                    self.logger.error(f"Failed to crawl URL {url}: {e}")
                    if fail_fast or self.config.get("fail_fast", False):
                        raise ProcessingError(f"Failed to crawl URL: {e}") from e

            self.progress_tracker.stop_tracking(
                tracking_id,
                status="completed",
                message=f"Crawled {len(web_contents)}/{len(urls)} URLs",
            )
            self.logger.info(
                f"Crawled {len(web_contents)}/{len(urls)} URL(s) from sitemap: {sitemap_url}"
            )

            return web_contents

        except Exception as e:
            self.progress_tracker.stop_tracking(
                tracking_id, status="failed", message=str(e)
            )
            raise

    def crawl_domain(
        self, domain: str, max_pages: int = 100, fail_fast: bool = False, **options
    ) -> List[WebContent]:
        """
        Crawl entire domain starting from root.

        This method performs a breadth-first crawl of a domain, starting from
        the root URL and following links within the same domain. Maintains a
        visited set to avoid duplicate crawling.

        Args:
            domain: Domain to crawl (with or without http/https prefix)
            max_pages: Maximum number of pages to crawl (default: 100)
            fail_fast: Whether to stop on first error (default: False)
            **options: Additional crawling options (unused)

        Returns:
            list: List of WebContent objects for successfully crawled pages

        Raises:
            ProcessingError: If fail_fast=True and error occurs during crawling
        """
        # Normalize domain URL
        if not domain.startswith(("http://", "https://")):
            domain = f"https://{domain}"

        # Initialize crawl state
        visited: Set[str] = set()
        to_visit: List[str] = [domain]
        web_contents = []

        self.logger.debug(f"Starting domain crawl: {domain}, max_pages={max_pages}")

        # Breadth-first crawl
        while to_visit and len(web_contents) < max_pages:
            url = to_visit.pop(0)

            # Skip if already visited
            if url in visited:
                continue

            visited.add(url)

            try:
                # Ingest current URL
                web_content = self.ingest_url(url)
                web_contents.append(web_content)

                # Discover and queue links from same domain
                parsed_domain = urlparse(domain)
                for link in web_content.links:
                    parsed_link = urlparse(link)

                    # Only follow links from same domain
                    if parsed_link.netloc == parsed_domain.netloc:
                        if link not in visited and link not in to_visit:
                            to_visit.append(link)

                self.logger.debug(
                    f"Crawled page {len(web_contents)}/{max_pages}: {url}, "
                    f"queued={len(to_visit)}"
                )

            except Exception as e:
                self.logger.error(f"Failed to crawl URL {url}: {e}")
                if fail_fast or self.config.get("fail_fast", False):
                    raise ProcessingError(f"Failed to crawl URL: {e}") from e

        self.logger.info(
            f"Domain crawl completed: {len(web_contents)} page(s) crawled, "
            f"{len(visited)} URL(s) visited"
        )

        return web_contents

    def extract_content(
        self, html_content: str, url: Optional[str] = None
    ) -> WebContent:
        """
        Extract content from HTML.

        This method extracts text, metadata, and links from HTML content using
        the content extractor. Creates a WebContent object with all extracted
        information.

        Args:
            html_content: Raw HTML content string to extract from
            url: Source URL for context (used for link resolution and metadata)

        Returns:
            WebContent: Extracted content object with:
                - url: Source URL
                - title: Page title
                - text: Cleaned text content
                - html: Original HTML content
                - metadata: Extracted metadata dictionary
                - links: List of extracted links
        """
        # Extract text content (cleaned)
        text = self.content_extractor.extract_text(html_content)

        # Extract metadata (title, meta tags, Open Graph, etc.)
        metadata = self.content_extractor.extract_metadata(html_content, url=url)

        # Extract links (absolute URLs)
        links = self.content_extractor.extract_links(html_content, base_url=url)

        # Get title from metadata
        title = metadata.get("title", "")

        # Create web content object
        web_content = WebContent(
            url=url or "",
            title=title,
            text=text,
            html=html_content,
            metadata=metadata,
            links=links,
        )

        return web_content

    def _apply_url_filters(self, urls: List[str], filters: Dict[str, Any]) -> List[str]:
        """Apply filters to URL list."""
        filtered = urls

        if "pattern" in filters:
            pattern = filters["pattern"]
            import re

            regex = re.compile(pattern)
            filtered = [url for url in filtered if regex.search(url)]

        if "domains" in filters:
            allowed_domains = filters["domains"]
            filtered = [
                url
                for url in filtered
                if any(domain in url for domain in allowed_domains)
            ]

        if "exclude_pattern" in filters:
            pattern = filters["exclude_pattern"]
            import re

            regex = re.compile(pattern)
            filtered = [url for url in filtered if not regex.search(url)]

        return filtered
