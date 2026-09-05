from datetime import date

from monitoring.token_expiry import build_expiry_alert, days_until_expiry, parse_expiry


def test_parse_expiry_requires_iso_date():
    assert parse_expiry("2026-12-01") == date(2026, 12, 1)


def test_days_until_expiry():
    assert days_until_expiry(date(2026, 12, 1), today=date(2026, 11, 24)) == 7


def test_alert_is_sent_only_on_thresholds_before_expiry():
    expiry = date(2026, 12, 1)
    assert build_expiry_alert(expiry, 29) is None
    assert "za 30 dní" in build_expiry_alert(expiry, 30)
    assert "za 14 dní" in build_expiry_alert(expiry, 14)
    assert "za 7 dní" in build_expiry_alert(expiry, 7)
    assert "za 3 dní" in build_expiry_alert(expiry, 3)
    assert "za 1 dní" in build_expiry_alert(expiry, 1)


def test_alert_on_expiry_day_and_after_expiry():
    expiry = date(2026, 12, 1)
    assert "expiruje dnes" in build_expiry_alert(expiry, 0)
    assert "po expiraci" in build_expiry_alert(expiry, -2)
    assert "před 2 dny" in build_expiry_alert(expiry, -2)
