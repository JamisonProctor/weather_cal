from unittest.mock import MagicMock, patch

from src.events.discovery.search import search_free_events, _build_queries


def _mock_result(href):
    return {"href": href}


def test_build_queries_default():
    queries = _build_queries("Munich", 2)
    assert len(queries) >= 3
    assert any("Munich" in q for q in queries)
    assert any("free" in q.lower() or "kostenlos" in q.lower() for q in queries)


def test_build_queries_custom_location():
    queries = _build_queries("Berlin", 2)
    assert any("Berlin" in q for q in queries)
    assert not any("Munich" in q for q in queries)


@patch("src.events.discovery.search.DDGS")
def test_search_returns_urls(mock_ddgs_class):
    mock_instance = MagicMock()
    mock_ddgs_class.return_value.__enter__ = MagicMock(return_value=mock_instance)
    mock_ddgs_class.return_value.__exit__ = MagicMock(return_value=False)
    mock_instance.text.return_value = [
        {"href": "https://example.com/events1"},
        {"href": "https://example.com/events2"},
    ]
    urls = search_free_events("Munich", weeks_ahead=2)
    assert "https://example.com/events1" in urls
    assert "https://example.com/events2" in urls


@patch("src.events.discovery.search.DDGS")
def test_search_deduplicates_urls(mock_ddgs_class):
    mock_instance = MagicMock()
    mock_ddgs_class.return_value.__enter__ = MagicMock(return_value=mock_instance)
    mock_ddgs_class.return_value.__exit__ = MagicMock(return_value=False)
    mock_instance.text.return_value = [
        {"href": "https://example.com/same"},
        {"href": "https://example.com/same"},
        {"href": "https://example.com/other"},
    ]
    urls = search_free_events("Munich", weeks_ahead=2)
    assert urls.count("https://example.com/same") == 1


@patch("src.events.discovery.search.DDGS")
def test_search_handles_exception(mock_ddgs_class):
    mock_instance = MagicMock()
    mock_ddgs_class.return_value.__enter__ = MagicMock(return_value=mock_instance)
    mock_ddgs_class.return_value.__exit__ = MagicMock(return_value=False)
    mock_instance.text.side_effect = Exception("Network error")
    urls = search_free_events("Munich", weeks_ahead=2)
    assert isinstance(urls, list)


@patch("src.events.discovery.search.DDGS")
def test_search_empty_results(mock_ddgs_class):
    mock_instance = MagicMock()
    mock_ddgs_class.return_value.__enter__ = MagicMock(return_value=mock_instance)
    mock_ddgs_class.return_value.__exit__ = MagicMock(return_value=False)
    mock_instance.text.return_value = []
    urls = search_free_events("Munich", weeks_ahead=2)
    assert urls == []
