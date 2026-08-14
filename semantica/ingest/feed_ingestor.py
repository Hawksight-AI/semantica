"""
Feed Ingestion Module

This module provides comprehensive feed ingestion capabilities for the
Semantica framework, enabling RSS, Atom, and other feed format processing,
discovery, and monitoring.

Key Features:
    - RSS/Atom feed parsing with format auto-detection
    - Feed discovery from websites
    - Content extraction from feed items
    - Update monitoring with callbacks
    - Feed validation
    - Date parsing with multiple format support

Main Classes:
    - FeedIngestor: Main feed ingestion class
    - FeedParser: Feed format parser
    - FeedMonitor: Feed update monitoring

Example Usage:
    >>> from semantica.ingest import FeedIngestor
    >>> ingestor = FeedIngestor()
    >>> feed_data = ingestor.ingest_feed("https://example.com/feed.xml")
    >>> feeds = ingestor.discover_feeds("https://example.com")

Author: Semantica Contributors
License: MIT
"""

import threading
import time
import xml.etree.ElementTree as ET
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Dict, List, Optional
from urllib.parse import urljoin, urlparse

import requests
from bs4 import BeautifulSoup

from ..utils.exceptions import ProcessingError, ValidationError
from ..utils.logging import get_logger
from ..utils.progress_tracker import get_progress_tracker
from .ssrf import parse_bool, request_with_ssrf_guard


@dataclass
class FeedItem:
    """
    Feed item representation.

    This dataclass represents a single item/entry from an RSS or Atom feed.

    Attributes:
        title: Item title
        link: Item URL
        description: Item description/summary
        content: Full item content (if available)
        author: Item author (optional)
        published: Publication date (optional)
        updated: Last update date (optional)
        guid: Unique identifier for the item
        categories: List of category tags
        metadata: Additional metadata dictionary
    """

    title: str
    link: str
    description: str = ""
    content: str = ""
    author: str = ""
    published: Optional[datetime] = None
    updated: Optional[datetime] = None
    guid: str = ""
    categories: List[str] = field(default_factory=list)
    metadata: Dict[str, Any] = field(default_factory=dict)


@dataclass
class FeedData:
    """
    Feed data representation.

    This dataclass represents a complete RSS or Atom feed with all its items.

    Attributes:
        title: Feed title
        link: Feed URL
        description: Feed description
        language: Feed language code
        updated: Last feed update date (optional)
        items: List of FeedItem objects
        metadata: Additional feed metadata dictionary
    """

    title: str
    link: str
    description: str = ""
    language: str = ""
    updated: Optional[datetime] = None
    items: List[FeedItem] = field(default_factory=list)
    metadata: Dict[str, Any] = field(default_factory=dict)


class FeedParser:
    """
    Feed format parser for RSS, Atom, and other formats.

    This class handles parsing of various feed formats with unified content
    extraction. Auto-detects feed format and parses accordingly.

    Example Usage:
        >>> parser = FeedParser()
        >>> feed_data = parser.parse_feed(xml_content, feed_url="https://example.com/feed.xml")
        >>> is_valid = parser.validate_feed(feed_data)
    """

    def __init__(self, **config):
        """
        Initialize feed parser.

        Sets up the parser with configuration options.

        Args:
            **config: Parser configuration options (currently unused)
        """
        self.logger = get_logger("feed_parser")
        self.config = config

    def parse_feed(self, feed_content: str, feed_url: Optional[str] = None) -> FeedData:
        """
        Parse feed content and extract items.

        This method auto-detects the feed format (RSS or Atom) and parses
        the content accordingly, extracting all feed metadata and items.

        Args:
            feed_content: Raw feed content (XML string)
            feed_url: Source feed URL (optional, used for link resolution)

        Returns:
            FeedData: Parsed feed data object with all items and metadata

        Raises:
            ProcessingError: If feed parsing fails or format is unsupported
        """
        try:
            # Detect feed format
            format_type = self.detect_format(feed_content)

            # Parse based on format
            if format_type == "rss":
                return self._parse_rss(feed_content, feed_url)
            elif format_type == "atom":
                return self._parse_atom(feed_content, feed_url)
            else:
                raise ProcessingError(f"Unsupported feed format: {format_type}")

        except Exception as e:
            self.logger.error(f"Failed to parse feed: {e}")
            raise ProcessingError(f"Failed to parse feed: {e}")

    def detect_format(self, feed_content: str) -> str:
        """
        Detect feed format from content.

        This method analyzes the XML structure to determine whether the feed
        is RSS or Atom format. Falls back to RSS if format is unclear.

        Args:
            feed_content: Raw feed content (XML string)

        Returns:
            str: Detected feed format ("rss" or "atom")
        """
        try:
            root = ET.fromstring(feed_content)

            # Check root element
            if root.tag.endswith("feed"):
                return "atom"
            elif root.tag.endswith("rss") or root.tag.endswith("RDF"):
                return "rss"
            else:
                # Default to RSS if unclear
                return "rss"

        except ET.ParseError:
            # Try to detect from string content
            content_lower = feed_content.lower()
            if "<feed" in content_lower or "xmlns:atom" in content_lower:
                return "atom"
            else:
                return "rss"

    def _parse_rss(self, feed_content: str, feed_url: Optional[str] = None) -> FeedData:
        """Parse RSS feed format."""
        root = ET.fromstring(feed_content)

        # Find channel element
        channel = root.find("channel")
        if channel is None:
            raise ProcessingError("Invalid RSS feed: no channel element found")

        # Extract feed metadata
        title = self._get_text(channel.find("title"))
        link = self._get_text(channel.find("link")) or (feed_url or "")
        description = self._get_text(channel.find("description"))
        language = self._get_text(channel.find("language"))

        # Extract items
        items = []
        for item in channel.findall("item"):
            item_title = self._get_text(item.find("title"))
            item_link = self._get_text(item.find("link"))
            item_description = self._get_text(item.find("description"))
            item_guid = self._get_text(item.find("guid")) or item_link or ""

            # Parse dates
            pub_date = None
            pub_date_elem = item.find("pubDate")
            if pub_date_elem is not None and pub_date_elem.text:
                pub_date = self._parse_date(pub_date_elem.text)

            # Extract categories
            categories = [cat.text for cat in item.findall("category") if cat.text]

            feed_item = FeedItem(
                title=item_title,
                link=item_link or "",
                description=item_description,
                guid=item_guid,
                published=pub_date,
                categories=categories,
            )
            items.append(feed_item)

        return FeedData(
            title=title,
            link=link,
            description=description,
            language=language,
            items=items,
        )

    def _parse_atom(
        self, feed_content: str, feed_url: Optional[str] = None
    ) -> FeedData:
        """Parse Atom feed format."""
        root = ET.fromstring(feed_content)

        # Extract feed metadata
        title_elem = root.find("{http://www.w3.org/2005/Atom}title")
        title = self._get_text(title_elem) if title_elem is not None else ""

        link_elem = root.find("{http://www.w3.org/2005/Atom}link[@rel='self']")
        if link_elem is None:
            link_elem = root.find("{http://www.w3.org/2005/Atom}link")
        link = link_elem.get("href") if link_elem is not None else (feed_url or "")

        subtitle_elem = root.find("{http://www.w3.org/2005/Atom}subtitle")
        description = self._get_text(subtitle_elem) if subtitle_elem is not None else ""

        updated_elem = root.find("{http://www.w3.org/2005/Atom}updated")
        updated = None
        if updated_elem is not None and updated_elem.text:
            updated = self._parse_date(updated_elem.text)

        # Extract entries
        items = []
        for entry in root.findall("{http://www.w3.org/2005/Atom}entry"):
            entry_title = entry.find("{http://www.w3.org/2005/Atom}title")
            item_title = self._get_text(entry_title) if entry_title is not None else ""

            entry_link = entry.find(
                "{http://www.w3.org/2005/Atom}link[@rel='alternate']"
            )
            if entry_link is None:
                entry_link = entry.find("{http://www.w3.org/2005/Atom}link")
            item_link = entry_link.get("href") if entry_link is not None else ""

            entry_summary = entry.find("{http://www.w3.org/2005/Atom}summary")
            entry_content = entry.find("{http://www.w3.org/2005/Atom}content")
            description = (
                self._get_text(entry_summary) if entry_summary is not None else ""
            )
            content = self._get_text(entry_content) if entry_content is not None else ""

            entry_id = entry.find("{http://www.w3.org/2005/Atom}id")
            guid = self._get_text(entry_id) if entry_id is not None else ""

            # Parse dates
            published = None
            updated = None
            pub_elem = entry.find("{http://www.w3.org/2005/Atom}published")
            upd_elem = entry.find("{http://www.w3.org/2005/Atom}updated")
            if pub_elem is not None and pub_elem.text:
                published = self._parse_date(pub_elem.text)
            if upd_elem is not None and upd_elem.text:
                updated = self._parse_date(upd_elem.text)

            # Extract categories
            categories = []
            for cat in entry.findall("{http://www.w3.org/2005/Atom}category"):
                term = cat.get("term")
                if term:
                    categories.append(term)

            feed_item = FeedItem(
                title=item_title,
                link=item_link,
                description=description,
                content=content,
                guid=guid,
                published=published,
                updated=updated,
                categories=categories,
            )
            items.append(feed_item)

        return FeedData(
            title=title,
            link=link,
            description=description,
            updated=updated,
            items=items,
        )

    def _get_text(self, element) -> str:
        """Extract text from XML element."""
        if element is None:
            return ""
        return element.text or ""

    def _parse_date(self, date_string: str) -> Optional[datetime]:
        """Parse date string to datetime."""
        from datetime import datetime as dt

        # Try common date formats
        formats = [
            "%a, %d %b %Y %H:%M:%S %z",  # RFC 822
            "%a, %d %b %Y %H:%M:%S %Z",  # RFC 822 with timezone name
            "%Y-%m-%dT%H:%M:%S%z",  # ISO 8601 with timezone
            "%Y-%m-%dT%H:%M:%SZ",  # ISO 8601 UTC
            "%Y-%m-%dT%H:%M:%S",  # ISO 8601 without timezone
            "%Y-%m-%d %H:%M:%S",  # Common format
            "%Y-%m-%d",  # Date only
        ]

        for fmt in formats:
            try:
                return dt.strptime(date_string.strip(), fmt)
            except ValueError:
                continue

        # Try with dateutil if available
        try:
            from dateutil import parser

            return parser.parse(date_string)
        except (ImportError, OSError):
            # If dateutil isn't available, fall through to raising ValueError
            pass
        except Exception as e:
            # If dateutil fails to parse, raise ValueError to signal invalid input
            raise ValueError(f"Invalid date format: {date_string}") from e

        # No known formats matched and dateutil is unavailable; raise ValueError
        raise ValueError(f"Invalid date format: {date_string}")

    def validate_feed(self, feed_data: FeedData) -> bool:
        """
        Validate parsed feed data.

        Args:
            feed_data: Parsed feed data

        Returns:
            bool: Whether feed is valid
        """
        # Check required fields
        if not feed_data.title:
            return False

        if not feed_data.items:
            return False

        # Validate items
        for item in feed_data.items:
            if not item.title and not item.description:
                return False

        return True


class FeedMonitor:
    """
    Feed update monitoring and notification.

    This class monitors feeds for updates and triggers processing when new
    content is available. Runs in a background thread and supports callbacks
    for new items.

    Example Usage:
        >>> monitor = FeedMonitor(check_interval=1800)  # 30 minutes
        >>> monitor.add_feed("https://example.com/feed.xml")
        >>> monitor.set_update_callback(lambda url, items: print(f"New items: {len(items)}"))
        >>> monitor.start_monitoring()
    """

    def __init__(self, **config):
        """
        Initialize feed monitor.

        Sets up the monitor with configuration and initializes monitoring state.

        Args:
            **config: Monitor configuration options:
                - check_interval: Interval between checks in seconds (default: 3600)
        """
        self.logger = get_logger("feed_monitor")
        self.config = config
        self.feeds: Dict[str, Dict[str, Any]] = {}
        self.monitoring: bool = False
        self.thread: Optional[threading.Thread] = None
        self.update_callback: Optional[callable] = None
        self.check_interval = config.get("check_interval", 3600)  # Default 1 hour
        self.allow_private_ips = parse_bool(
            config.get("allow_private_ips"), default=False
        )

    def add_feed(self, feed_url: str, **options):
        """
        Add feed to monitoring list.

        Args:
            feed_url: Feed URL to monitor
            **options: Monitoring options
        """
        if not feed_url:
            raise ValidationError("Feed URL is required")

        self.feeds[feed_url] = {
            "url": feed_url,
            "last_check": None,
            "last_items": [],
            "options": options,
        }
        self.logger.info(f"Added feed to monitoring: {feed_url}")

    def start_monitoring(self):
        """Start monitoring all added feeds."""
        if self.monitoring:
            self.logger.warning("Monitoring already started")
            return

        if not self.feeds:
            self.logger.warning("No feeds to monitor")
            return

        self.monitoring = True
        self.thread = threading.Thread(target=self._monitoring_loop, daemon=True)
        self.thread.start()
        self.logger.info("Feed monitoring started")

    def stop_monitoring(self):
        """Stop monitoring all feeds."""
        self.monitoring = False
        if self.thread:
            self.thread.join(timeout=5)
        self.logger.info("Feed monitoring stopped")

    def check_updates(self, feed_url: str) -> List[FeedItem]:
        """
        Check for updates in specific feed.

        Args:
            feed_url: Feed URL to check

        Returns:
            list: List of new items
        """
        if feed_url not in self.feeds:
            raise ValidationError(f"Feed {feed_url} not in monitoring list")

        feed_info = self.feeds[feed_url]
        parser = FeedParser()

        try:
            # Fetch feed
            response = request_with_ssrf_guard(
                "GET",
                feed_url,
                allow_private_ips=self.allow_private_ips,
                timeout=30,
            )
            response.raise_for_status()

            # Parse feed
            feed_data = parser.parse_feed(response.text, feed_url)

            # Compare with previous items
            last_items = feed_info["last_items"]
            current_items = feed_data.items

            # Find new items
            if not last_items:
                # First check - return all items
                feed_info["last_items"] = [
                    item.guid or item.link for item in current_items
                ]
                feed_info["last_check"] = datetime.now()
                return current_items

            # Find new items by comparing GUIDs/links
            last_guids = set(last_items)
            new_items = [
                item
                for item in current_items
                if (item.guid or item.link) not in last_guids
            ]

            # Update last items
            feed_info["last_items"] = [item.guid or item.link for item in current_items]
            feed_info["last_check"] = datetime.now()

            return new_items

        except Exception as e:
            self.logger.error(f"Failed to check feed {feed_url}: {e}")
            return []

    def _monitoring_loop(self):
        """Main monitoring loop."""
        while self.monitoring:
            for feed_url in list(self.feeds.keys()):
                try:
                    new_items = self.check_updates(feed_url)
                    if new_items and self.update_callback:
                        self.update_callback(feed_url, new_items)
                except Exception as e:
                    self.logger.error(f"Error checking feed {feed_url}: {e}")

            # Wait for next check interval
            time.sleep(self.check_interval)

    def set_update_callback(self, callback: callable):
        """Set callback for feed updates."""
        self.update_callback = callback


class FeedIngestor:
    """
    RSS/Atom feed ingestion handler.

    This class provides comprehensive feed ingestion capabilities, processing
    RSS, Atom, and other feed formats with support for content extraction
    and monitoring.

    Features:
        - RSS and Atom feed parsing
        - Feed discovery from websites
        - Feed update monitoring
        - Content extraction from feed items

    Example Usage:
        >>> ingestor = FeedIngestor()
        >>> feed_data = ingestor.ingest_feed("https://example.com/feed.xml")
        >>> feeds = ingestor.discover_feeds("https://example.com")
        >>> monitor = ingestor.monitor_feeds(feeds, check_interval=1800)
    """

    def __init__(self, config: Optional[Dict[str, Any]] = None, **kwargs):
        """
        Initialize feed ingestor.

        Sets up the ingestor with feed parser and monitor.

        Args:
            config: Optional feed ingestion configuration dictionary
            **kwargs: Additional configuration parameters (merged into config)
        """
        self.logger = get_logger("feed_ingestor")
        self.config = config or {}
        self.config.update(kwargs)
        self.allow_private_ips = parse_bool(
            self.config.get("allow_private_ips"), default=False
        )

        # Initialize feed parser
        self.parser = FeedParser(**self.config)

        # Setup feed monitor
        self.monitor = FeedMonitor(**self.config)

        # Update intervals
        self.update_intervals = self.config.get("update_intervals", {})

        # Initialize progress tracker
        self.progress_tracker = get_progress_tracker()

        self.logger.debug("Feed ingestor initialized")

    def ingest_feed(
        self,
        feed_url: str,
        timeout: Optional[int] = None,
        validate: bool = True,
        **options,
    ) -> FeedData:
        """
        Ingest content from a single feed.

        This method fetches a feed from the provided URL, parses it, and
        optionally validates it. Handles both RSS and Atom formats.

        Args:
            feed_url: URL of feed to ingest
            timeout: Request timeout in seconds (optional, default: 30)
            validate: Whether to validate the parsed feed (default: True)
            **options: Additional processing options (unused)

        Returns:
            FeedData: Parsed feed content object with all items and metadata

        Raises:
            ValidationError: If feed URL is invalid
            ProcessingError: If feed fetching or parsing fails
        """
        # Track feed ingestion
        tracking_id = self.progress_tracker.start_tracking(
            file=feed_url,
            module="ingest",
            submodule="FeedIngestor",
            message=f"Feed: {feed_url}",
        )

        try:
            # Validate feed URL
            try:
                parsed = urlparse(feed_url)
                if not parsed.scheme or not parsed.netloc:
                    raise ValidationError(f"Invalid feed URL: {feed_url}")
            except Exception as e:
                raise ValidationError(f"Invalid feed URL: {feed_url}") from e

            # Fetch feed content
            try:
                request_timeout = timeout or options.get(
                    "timeout", self.config.get("timeout", 30)
                )
                response = request_with_ssrf_guard(
                    "GET",
                    feed_url,
                    allow_private_ips=self.allow_private_ips,
                    timeout=request_timeout,
                )
                response.raise_for_status()
                self.logger.debug(
                    f"Fetched feed from {feed_url}: {len(response.text)} bytes"
                )
            except requests.RequestException as e:
                self.progress_tracker.stop_tracking(
                    tracking_id, status="failed", message=str(e)
                )
                self.logger.error(f"Failed to fetch feed {feed_url}: {e}")
                raise ProcessingError(f"Failed to fetch feed: {e}") from e

            # Parse feed format
            feed_data = self.parser.parse_feed(response.text, feed_url)

            # Validate feed
            if validate or options.get("validate", True):
                if not self.parser.validate_feed(feed_data):
                    self.logger.warning(f"Feed {feed_url} validation failed")

            self.progress_tracker.stop_tracking(
                tracking_id,
                status="completed",
                message=f"Ingested {len(feed_data.items)} items",
            )
            self.logger.info(
                f"Ingested feed {feed_url}: {len(feed_data.items)} item(s)"
            )

            return feed_data

        except Exception as e:
            self.progress_tracker.stop_tracking(
                tracking_id, status="failed", message=str(e)
            )
            raise

    def discover_feeds(self, website_url: str) -> List[str]:
        """
        Discover feeds from a website.

        This method scans a website for feed links, checking both HTML link
        tags and common feed paths. Validates discovered feeds by attempting
        to fetch them.

        Args:
            website_url: Website URL to scan for feeds

        Returns:
            list: List of discovered and validated feed URLs
        """
        feed_urls = []

        try:
            # Fetch website content
            response = request_with_ssrf_guard(
                "GET",
                website_url,
                allow_private_ips=self.allow_private_ips,
                timeout=30,
            )
            response.raise_for_status()

            # Parse HTML
            soup = BeautifulSoup(response.text, "html.parser")

            # Look for feed links
            # Check link tags with type="application/rss+xml" or "application/atom+xml"
            feed_links = soup.find_all(
                "link", type=lambda t: t and ("rss" in t.lower() or "atom" in t.lower())
            )
            for link in feed_links:
                href = link.get("href")
                if href:
                    # Resolve relative URLs
                    feed_url = urljoin(website_url, href)
                    feed_urls.append(feed_url)

            # Also check for common feed paths
            common_paths = [
                "/feed",
                "/rss",
                "/atom",
                "/feed.xml",
                "/rss.xml",
                "/atom.xml",
            ]
            for path in common_paths:
                try:
                    feed_url = urljoin(website_url, path)
                    test_response = request_with_ssrf_guard(
                        "HEAD",
                        feed_url,
                        allow_private_ips=self.allow_private_ips,
                        timeout=10,
                    )
                    if test_response.status_code == 200:
                        content_type = test_response.headers.get("Content-Type", "")
                        if (
                            "rss" in content_type.lower()
                            or "atom" in content_type.lower()
                            or "xml" in content_type.lower()
                        ):
                            if feed_url not in feed_urls:
                                feed_urls.append(feed_url)
                except Exception:
                    continue

            # Validate discovered feeds
            validated_feeds = []
            for feed_url in feed_urls:
                try:
                    # Quick validation by fetching feed
                    test_response = request_with_ssrf_guard(
                        "GET",
                        feed_url,
                        allow_private_ips=self.allow_private_ips,
                        timeout=10,
                    )
                    if test_response.status_code == 200:
                        validated_feeds.append(feed_url)
                except Exception:
                    continue

            return validated_feeds

        except Exception as e:
            self.logger.error(f"Failed to discover feeds from {website_url}: {e}")
            return []

    def monitor_feeds(self, feed_urls: List[str], **options) -> FeedMonitor:
        """
        Monitor multiple feeds for updates.

        Args:
            feed_urls: List of feed URLs to monitor
            **options: Monitoring options

        Returns:
            FeedMonitor: Active feed monitor
        """
        # Add all feeds to monitor
        for feed_url in feed_urls:
            self.monitor.add_feed(feed_url, **options)

        # Set callback if provided
        if options.get("update_callback"):
            self.monitor.set_update_callback(options["update_callback"])

        # Start monitoring if requested
        if options.get("start", True):
            self.monitor.start_monitoring()

        return self.monitor

    def extract_content(self, feed_item: FeedItem) -> Dict[str, Any]:
        """
        Extract content from feed item.

        Args:
            feed_item: Feed item to extract from

        Returns:
            dict: Extracted content and metadata
        """
        return {
            "title": feed_item.title,
            "description": feed_item.description,
            "content": feed_item.content or feed_item.description,
            "link": feed_item.link,
            "author": feed_item.author,
            "published": feed_item.published.isoformat()
            if feed_item.published
            else None,
            "updated": feed_item.updated.isoformat() if feed_item.updated else None,
            "categories": feed_item.categories,
            "guid": feed_item.guid,
            "metadata": feed_item.metadata,
        }
