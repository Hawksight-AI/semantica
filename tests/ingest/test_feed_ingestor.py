from unittest.mock import MagicMock, patch

import pytest
import requests

from semantica.ingest.feed_ingestor import (
    FeedData,
    FeedIngestor,
    FeedItem,
    FeedParser,
    ProcessingError,
)


# --- Fixtures ---
@pytest.fixture
def complex_atom_xml() -> str:
    """Return a complex Atom feed XML string."""

    return """
    <feed xmlns="http://www.w3.org/2005/Atom">
        <title>Atom</title>
        <link href="http://example.com" rel="self"/>
        <subtitle>Subtitle</subtitle>
        <updated>2025-01-01T00:00:00Z</updated>
        <entry>
            <title>Entry 1</title>
            <link href="http://example.com/1" rel="alternate"/>
            <summary>Summary</summary>
            <content>Full Content</content>
            <id>uuid:123</id>
            <published>2025-01-01T00:00:00Z</published>
            <updated>2025-01-02T00:00:00Z</updated>
            <category term="tech"/>
            <category term="news"/>
        </entry>
    </feed>
    """


# --- Tests ---
def test_parse_atom_complex(complex_atom_xml: str) -> None:
    """Test parsing a complex Atom feed."""

    parser = FeedParser()
    data = parser.parse_feed(complex_atom_xml)
    item = data.items[0]

    assert data.title == "Atom"
    assert len(data.items) == 1
    assert item.description == "Summary"
    assert item.content == "Full Content"
    assert "tech" in item.categories
    assert "news" in item.categories
    assert item.published.year == 2025


def test_parse_rss_dates() -> None:
    """Test date parsing logic specific to RSS."""

    xml = """
    <rss version="2.0">
        <channel>
            <title>T</title>
            <link>http://l.com</link>
            <item>
                <title>T</title>
                <pubDate>Mon, 27 Jan 2025 12:00:00 GMT</pubDate>
            </item>
        </channel>
    </rss>
    """
    parser = FeedParser()
    data = parser.parse_feed(xml)

    assert data.items[0].published.year == 2025


def test_ingest_feed_errors() -> None:
    """Test error handling in ingest_feed."""

    ingestor = FeedIngestor()

    with pytest.raises(Exception):
        ingestor.ingest_feed("not_a_url")

    with patch(
        "semantica.ingest.ssrf.socket.getaddrinfo",
        return_value=[(2, 1, 6, "", ("93.184.216.34", 0))],
    ):
        with patch(
            "requests.request",
            side_effect=requests.exceptions.RequestException("Fail"),
        ):
            with pytest.raises(ProcessingError):
                ingestor.ingest_feed("http://valid.com")


def test_monitor_loop_lifecycle() -> None:
    """Test start, run loop once, and stop."""

    ingestor = FeedIngestor()
    ingestor.monitor.add_feed("http://test.com")

    def side_effect_sleep(seconds: float) -> None:
        ingestor.monitor.monitoring = False

    with patch("time.sleep", side_effect=side_effect_sleep):
        with patch.object(
            ingestor.monitor,
            "check_updates",
            side_effect=Exception("Check Fail"),
        ):
            ingestor.monitor.monitoring = True
            ingestor.monitor._monitoring_loop()

    assert ingestor.monitor.monitoring is False


def test_monitor_threading() -> None:
    """Test that start_monitoring actually spawns a thread."""

    ingestor = FeedIngestor()
    ingestor.monitor.add_feed("http://test.com")

    with patch("threading.Thread") as mock_thread:
        ingestor.monitor.start_monitoring()
        mock_thread.return_value.start.assert_called_once()

    # Test double start and stop
    ingestor.monitor.start_monitoring()
    ingestor.monitor.stop_monitoring()

    assert ingestor.monitor.monitoring is False


def test_extract_content_helper() -> None:
    """Test the extract_content method full fields."""

    ingestor = FeedIngestor()
    item = FeedItem(
        title="T",
        link="L",
        description="D",
        content="C",
        categories=["cat"],
    )

    res = ingestor.extract_content(item)

    assert res["content"] == "C"
    assert res["categories"] == ["cat"]


def test_extract_content_missing_fields() -> None:
    """Test extract_content with missing optional fields."""

    ingestor = FeedIngestor()
    item = FeedItem(title="T", link="L", description="D")

    res = ingestor.extract_content(item)

    assert res["content"] == "D"
    assert res["published"] is None
    assert res["updated"] is None


def test_parse_date_formats() -> None:
    """Test various date formats."""

    parser = FeedParser()
    d1 = parser._parse_date("Mon, 27 Jan 2025 12:00:00 GMT")
    d2 = parser._parse_date("2025-01-27T12:00:00Z")
    d3 = parser._parse_date("2025-01-27")

    assert d1.year == 2025
    assert d2.year == 2025
    assert d3.year == 2025
    with pytest.raises(ValueError):
        parser._parse_date("Not a date")


def test_validate_feed() -> None:
    """Test feed validation logic."""

    parser = FeedParser()

    f1 = FeedData(
        title="T",
        link="http://e.com",
        items=[MagicMock(title="t")],
    )
    f2 = FeedData(
        title="",
        link="http://e.com",
        items=[MagicMock(title="t")],
    )
    f3 = FeedData(title="T", link="http://e.com", items=[])

    assert parser.validate_feed(f1) is True
    assert parser.validate_feed(f2) is False
    assert parser.validate_feed(f3) is False


def test_discover_feeds_empty() -> None:
    """Test discovery finding nothing."""

    ingestor = FeedIngestor()
    html = "<html><body>No feeds here</body></html>"

    mock_response = MagicMock()
    mock_response.text = html
    mock_response.status_code = 200
    mock_response.headers = {}

    def fake_request(method, url, **kwargs):
        if url == "http://site.com":
            return mock_response
        raise requests.exceptions.RequestException("not found")

    with patch(
        "semantica.ingest.ssrf.socket.getaddrinfo",
        return_value=[(2, 1, 6, "", ("93.184.216.34", 0))],
    ):
        with patch("requests.Session.request", side_effect=fake_request):
            feeds = ingestor.discover_feeds("http://site.com")

    assert len(feeds) == 0


def test_discover_feeds_found() -> None:
    """Test discovering feeds in HTML content."""
    ingestor = FeedIngestor()
    html = """
    <html>
    <head>
        <link rel="alternate" type="application/rss+xml" href="/rss.xml">
    </head>
    <body>
        <a href="/feed">RSS</a>
    </body>
    </html>
    """

    mock_response = MagicMock()
    mock_response.text = html
    mock_response.status_code = 200
    mock_response.headers = {"Content-Type": "application/rss+xml"}

    def fake_request(method, url, **kwargs):
        return mock_response

    with patch(
        "semantica.ingest.ssrf.socket.getaddrinfo",
        return_value=[(2, 1, 6, "", ("93.184.216.34", 0))],
    ):
        with patch("requests.Session.request", side_effect=fake_request):
            feeds = ingestor.discover_feeds("http://site.com")

    assert "http://site.com/rss.xml" in feeds
    assert "http://site.com/feed" in feeds


def test_feed_monitor_options() -> None:
    """Test adding feeds with specific options."""

    ingestor = FeedIngestor()

    with patch.object(ingestor.monitor, "add_feed") as mock_add:
        with patch.object(ingestor.monitor, "start_monitoring") as mock_start:
            ingestor.monitor_feeds(["http://f.com"], interval=60, start=True)

            mock_add.assert_called_with(
                "http://f.com",
                interval=60,
                start=True,
            )
            mock_start.assert_called_once()
