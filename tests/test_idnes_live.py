from datetime import datetime, timezone
from pathlib import Path

from scrapers.idnes_live import LiveIdnesTVScraper


CONFIG = """
idnes:
  timezone: Europe/Prague
  crawl_channels: [oneplaysport-4]
  search_queries: [hokej]
  channels:
    oneplaysport-4: "Oneplay Sport 4"
"""


def make_scraper(tmp_path: Path) -> LiveIdnesTVScraper:
    config = tmp_path / "tv_channels.yaml"
    config.write_text(CONFIG, encoding="utf-8")
    return LiveIdnesTVScraper(
        str(config),
        now=datetime(2026, 9, 12, 10, tzinfo=timezone.utc),
    )


def test_channel_page_is_used_as_discovery_index(tmp_path, monkeypatch):
    scraper = make_scraper(tmp_path)
    channel_html = """
    <table><tr><td>
      <a href="/oneplaysport-4/st-18.00-tipsport-extraliga.id108423999">
        Tipsport extraliga 18:00 Přímý přenos HC Dynamo Pardubice - Mountfield HK
      </a>
    </td></tr></table>
    """
    detail_html = """
    <html><body>
      <h1>Tipsport extraliga</h1>
      <div>16. 9. 2026, 18:00</div>
      <div>Sport</div>
      <p>Přímý přenos utkání HC Dynamo Pardubice - Mountfield HK</p>
      <div>Přidat do mého TV programu</div>
      <h1>Televizní program</h1>
    </body></html>
    """
    monkeypatch.setattr(scraper, "_fetch_html", lambda url: channel_html)
    monkeypatch.setattr(scraper, "_fetch_detail_html", lambda url: detail_html)

    rows = list(scraper._scrape_channel("oneplaysport-4"))

    assert len(rows) == 1
    row = rows[0]
    assert row.title == "Tipsport extraliga"
    assert row.start_local.isoformat() == "2026-09-16T18:00:00+02:00"
    assert "HC Dynamo Pardubice - Mountfield HK" in row.description


def test_irrelevant_channel_programme_does_not_fetch_detail(tmp_path, monkeypatch):
    scraper = make_scraper(tmp_path)
    channel_html = """
    <a href="/oneplaysport-4/st-20.00-film.id108424000">Večerní film 20:00</a>
    """
    monkeypatch.setattr(scraper, "_fetch_html", lambda url: channel_html)
    monkeypatch.setattr(
        scraper,
        "_fetch_detail_html",
        lambda url: (_ for _ in ()).throw(AssertionError("detail must not be fetched")),
    )

    assert list(scraper._scrape_channel("oneplaysport-4")) == []
