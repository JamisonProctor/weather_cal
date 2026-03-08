import asyncio
from unittest.mock import AsyncMock, MagicMock, patch

from src.events.discovery.fetcher import fetch_page_as_markdown


def _run(coro):
    return asyncio.get_event_loop().run_until_complete(coro)


@patch("src.events.discovery.fetcher.AsyncWebCrawler")
def test_fetch_returns_markdown(mock_crawler_class):
    mock_result = MagicMock()
    mock_result.markdown = "# Event Page\n\nConcert on March 15"
    mock_result.success = True

    mock_instance = MagicMock()
    mock_instance.__aenter__ = AsyncMock(return_value=mock_instance)
    mock_instance.__aexit__ = AsyncMock(return_value=False)
    mock_instance.arun = AsyncMock(return_value=mock_result)
    mock_crawler_class.return_value = mock_instance

    result = fetch_page_as_markdown("https://example.com/events")
    assert result is not None
    assert "Concert" in result


@patch("src.events.discovery.fetcher.AsyncWebCrawler")
def test_fetch_returns_none_on_failure(mock_crawler_class):
    mock_result = MagicMock()
    mock_result.markdown = ""
    mock_result.success = False

    mock_instance = MagicMock()
    mock_instance.__aenter__ = AsyncMock(return_value=mock_instance)
    mock_instance.__aexit__ = AsyncMock(return_value=False)
    mock_instance.arun = AsyncMock(return_value=mock_result)
    mock_crawler_class.return_value = mock_instance

    result = fetch_page_as_markdown("https://example.com/broken")
    assert result is None


@patch("src.events.discovery.fetcher.AsyncWebCrawler")
def test_fetch_returns_none_on_exception(mock_crawler_class):
    mock_instance = MagicMock()
    mock_instance.__aenter__ = AsyncMock(return_value=mock_instance)
    mock_instance.__aexit__ = AsyncMock(return_value=False)
    mock_instance.arun = AsyncMock(side_effect=Exception("Timeout"))
    mock_crawler_class.return_value = mock_instance

    result = fetch_page_as_markdown("https://example.com/timeout")
    assert result is None


@patch("src.events.discovery.fetcher.AsyncWebCrawler")
def test_fetch_returns_none_on_empty_markdown(mock_crawler_class):
    mock_result = MagicMock()
    mock_result.markdown = ""
    mock_result.success = True

    mock_instance = MagicMock()
    mock_instance.__aenter__ = AsyncMock(return_value=mock_instance)
    mock_instance.__aexit__ = AsyncMock(return_value=False)
    mock_instance.arun = AsyncMock(return_value=mock_result)
    mock_crawler_class.return_value = mock_instance

    result = fetch_page_as_markdown("https://example.com/empty")
    assert result is None
