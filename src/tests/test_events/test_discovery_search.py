"""Tests for search module."""

from unittest.mock import MagicMock, patch

from src.events.discovery.search import (
    BLOCKED_DOMAINS,
    _is_relevant_url,
    execute_queries,
    search_free_events,
)


@patch("src.events.discovery.search.DDGS")
def test_execute_queries_returns_urls(mock_ddgs_class):
    mock_instance = MagicMock()
    mock_ddgs_class.return_value.__enter__ = MagicMock(return_value=mock_instance)
    mock_ddgs_class.return_value.__exit__ = MagicMock(return_value=False)
    mock_instance.text.return_value = [
        {"href": "https://example.com/events1"},
        {"href": "https://example.com/events2"},
    ]
    urls = execute_queries(["free events Munich March 2026"])
    assert "https://example.com/events1" in urls
    assert "https://example.com/events2" in urls


@patch("src.events.discovery.search.DDGS")
def test_execute_queries_deduplicates(mock_ddgs_class):
    mock_instance = MagicMock()
    mock_ddgs_class.return_value.__enter__ = MagicMock(return_value=mock_instance)
    mock_ddgs_class.return_value.__exit__ = MagicMock(return_value=False)
    mock_instance.text.return_value = [
        {"href": "https://example.com/same"},
        {"href": "https://example.com/same"},
        {"href": "https://example.com/other"},
    ]
    urls = execute_queries(["query1", "query2"])
    assert urls.count("https://example.com/same") == 1


@patch("src.events.discovery.search.DDGS")
def test_execute_queries_handles_exception(mock_ddgs_class):
    mock_instance = MagicMock()
    mock_ddgs_class.return_value.__enter__ = MagicMock(return_value=mock_instance)
    mock_ddgs_class.return_value.__exit__ = MagicMock(return_value=False)
    mock_instance.text.side_effect = Exception("Network error")
    urls = execute_queries(["failing query"])
    assert isinstance(urls, list)
    assert urls == []


@patch("src.events.discovery.search.DDGS")
def test_execute_queries_empty_list(mock_ddgs_class):
    mock_instance = MagicMock()
    mock_ddgs_class.return_value.__enter__ = MagicMock(return_value=mock_instance)
    mock_ddgs_class.return_value.__exit__ = MagicMock(return_value=False)
    urls = execute_queries([])
    assert urls == []


@patch("src.events.discovery.search.DDGS")
def test_execute_queries_multiple_queries(mock_ddgs_class):
    mock_instance = MagicMock()
    mock_ddgs_class.return_value.__enter__ = MagicMock(return_value=mock_instance)
    mock_ddgs_class.return_value.__exit__ = MagicMock(return_value=False)
    mock_instance.text.side_effect = [
        [{"href": "https://example.com/a"}],
        [{"href": "https://example.com/b"}],
        [{"href": "https://example.com/c"}],
    ]
    urls = execute_queries(["q1", "q2", "q3"])
    assert len(urls) == 3


@patch("src.events.discovery.search.execute_queries")
def test_legacy_search_free_events(mock_exec):
    """Legacy interface should still work."""
    mock_exec.return_value = ["https://example.com/events"]
    urls = search_free_events("Munich", weeks_ahead=2)
    assert urls == ["https://example.com/events"]
    mock_exec.assert_called_once()


@patch("src.events.discovery.search.DDGS")
def test_execute_queries_skips_empty_hrefs(mock_ddgs_class):
    mock_instance = MagicMock()
    mock_ddgs_class.return_value.__enter__ = MagicMock(return_value=mock_instance)
    mock_ddgs_class.return_value.__exit__ = MagicMock(return_value=False)
    mock_instance.text.return_value = [
        {"href": ""},
        {"href": "https://example.com/valid"},
        {},
    ]
    urls = execute_queries(["query"])
    assert urls == ["https://example.com/valid"]


def test_is_relevant_url_blocks_known_domains():
    assert not _is_relevant_url("https://www.zhihu.com/question/123")
    assert not _is_relevant_url("https://support.google.com/mail/answer/1")
    assert not _is_relevant_url("https://www.instagram.com/explore/")
    assert not _is_relevant_url("https://de.wikipedia.org/wiki/Munich")
    assert not _is_relevant_url("https://www.youtube.com/watch?v=abc")


def test_is_relevant_url_allows_event_sites():
    assert _is_relevant_url("https://www.muenchen.de/veranstaltungen")
    assert _is_relevant_url("https://rausgegangen.de/events")
    assert _is_relevant_url("https://www.eventfinder.de/muenchen")


@patch("src.events.discovery.search.DDGS")
def test_execute_queries_filters_blocked_domains(mock_ddgs_class):
    mock_instance = MagicMock()
    mock_ddgs_class.return_value.__enter__ = MagicMock(return_value=mock_instance)
    mock_ddgs_class.return_value.__exit__ = MagicMock(return_value=False)
    mock_instance.text.return_value = [
        {"href": "https://www.zhihu.com/question/123"},
        {"href": "https://support.google.com/mail/answer/1"},
        {"href": "https://www.muenchen.de/veranstaltungen"},
    ]
    urls = execute_queries(["free events Munich"])
    assert urls == ["https://www.muenchen.de/veranstaltungen"]


def test_blocked_domains_has_key_entries():
    assert "www.zhihu.com" in BLOCKED_DOMAINS
    assert "support.google.com" in BLOCKED_DOMAINS
    assert "www.instagram.com" in BLOCKED_DOMAINS
