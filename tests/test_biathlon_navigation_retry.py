from unittest.mock import Mock, patch

import pytest
from playwright.sync_api import Error as PlaywrightError

from scrapers.biathlonworld import _navigate_with_retry


def _page(body="Calendar", status=200):
    page = Mock()
    page.goto.return_value.status = status
    page.locator.return_value.inner_text.return_value = body
    return page


def test_navigation_retries_socket_error():
    page = _page()
    page.goto.side_effect = [PlaywrightError("net::ERR_SOCKET_NOT_CONNECTED"), Mock(status=200)]
    with patch("scrapers.biathlonworld.time.sleep") as sleep:
        _navigate_with_retry(page, "https://example.com")
    assert page.goto.call_count == 2
    sleep.assert_called_once()


def test_navigation_retries_crashed_page():
    page = _page()
    page.locator.return_value.inner_text.side_effect = ["This function has crashed", "Calendar"]
    with patch("scrapers.biathlonworld.time.sleep"):
        _navigate_with_retry(page, "https://example.com")
    assert page.goto.call_count == 2


def test_navigation_fails_after_retries():
    page = _page(status=503)
    with patch("scrapers.biathlonworld.time.sleep"):
        with pytest.raises(RuntimeError, match="after 3 attempts"):
            _navigate_with_retry(page, "https://example.com")
    assert page.goto.call_count == 3
