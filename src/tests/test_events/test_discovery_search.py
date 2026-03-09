"""Tests for search module."""

from unittest.mock import MagicMock, patch

from src.events.discovery.search import execute_queries, search_free_events


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
