from unittest.mock import MagicMock, patch

import httpx

from src.events.discovery.fetcher import fetch_page_as_markdown


def _mock_response(text="<h1>Events</h1><p>Concert on March 15</p>", status_code=200):
    resp = MagicMock(spec=httpx.Response)
    resp.status_code = status_code
    resp.text = text
    resp.raise_for_status = MagicMock()
    if status_code >= 400:
        resp.raise_for_status.side_effect = httpx.HTTPStatusError(
            "error", request=MagicMock(), response=resp
        )
    return resp


@patch("src.events.discovery.fetcher.httpx.get")
def test_fetch_returns_markdown(mock_get):
    mock_get.return_value = _mock_response()
    result = fetch_page_as_markdown("https://example.com/events")
    assert result is not None
    assert "Concert" in result
    assert "Events" in result


@patch("src.events.discovery.fetcher.httpx.get")
def test_fetch_returns_none_on_http_error(mock_get):
    mock_get.return_value = _mock_response(status_code=404)
    result = fetch_page_as_markdown("https://example.com/broken")
    assert result is None


@patch("src.events.discovery.fetcher.httpx.get")
def test_fetch_returns_none_on_exception(mock_get):
    mock_get.side_effect = httpx.TimeoutException("Timeout")
    result = fetch_page_as_markdown("https://example.com/timeout")
    assert result is None


@patch("src.events.discovery.fetcher.httpx.get")
def test_fetch_returns_none_on_empty_html(mock_get):
    mock_get.return_value = _mock_response(text="")
    result = fetch_page_as_markdown("https://example.com/empty")
    assert result is None


@patch("src.events.discovery.fetcher.httpx.get")
def test_fetch_strips_whitespace(mock_get):
    mock_get.return_value = _mock_response(text="  <p>Hello</p>  ")
    result = fetch_page_as_markdown("https://example.com/whitespace")
    assert result is not None
    assert result == result.strip()
