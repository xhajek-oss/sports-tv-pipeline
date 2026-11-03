from unittest.mock import Mock, patch

import pytest
from playwright.sync_api import TimeoutError as PlaywrightTimeoutError

from scrapers.idnes import IdnesTVScraper


def _scraper():
    scraper = IdnesTVScraper.__new__(IdnesTVScraper)
    scraper.timeout = 30
    scraper._ensure_browser = Mock()
    scraper._ensure_browser.return_value.new_page.return_value = Mock()
    return scraper


def test_idnes_retries_navigation_timeout():
    scraper = _scraper()
    page = scraper._ensure_browser.return_value.new_page.return_value
    page.goto.side_effect = [PlaywrightTimeoutError("timeout"), Mock(status=200)]
    page.content.return_value = "<html>ok</html>"
    with patch("scrapers.idnes.retry_time.sleep") as sleep:
        assert scraper._fetch_html("https://example.com") == "<html>ok</html>"
    assert page.goto.call_count == 2
    assert page.close.call_count == 2
    sleep.assert_called_once()


def test_idnes_retries_server_error_and_fails_closed():
    scraper = _scraper()
    page = scraper._ensure_browser.return_value.new_page.return_value
    page.goto.return_value.status = 503
    with patch("scrapers.idnes.retry_time.sleep"):
        with pytest.raises(RuntimeError, match="after 3 attempts"):
            scraper._fetch_html("https://example.com")
    assert page.goto.call_count == 3
    assert page.close.call_count == 3


def test_idnes_does_not_retry_client_error():
    scraper = _scraper()
    page = scraper._ensure_browser.return_value.new_page.return_value
    page.goto.return_value.status = 404
    with pytest.raises(ValueError, match="HTTP 404"):
        scraper._fetch_html("https://example.com")
    page.goto.assert_called_once()
