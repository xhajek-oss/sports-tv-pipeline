from datetime import datetime, timezone
from pathlib import Path

from scrapers.idnes import IdnesTVScraper


CONFIG = """
idnes:
  timezone: Europe/Prague
  max_pages_per_query: 2
  crawl_channels:
    - oneplaysport-4
  search_queries:
    - hokej
  channels:
    oneplaysport-4: "Oneplay Sport 4"
"""


def make_scraper(tmp_path: Path) -> IdnesTVScraper:
    config = tmp_path / "tv_channels.yaml"
    config.write_text(CONFIG, encoding="utf-8")
    return IdnesTVScraper(
        str(config),
        now=datetime(2026, 9, 12, 10, tzinfo=timezone.utc),
    )


def test_channel_page_discovers_generic_extraliga_programme(tmp_path, monkeypatch):
    scraper = make_scraper(tmp_path)
    html = """
    <div class="result-item">
      <div class="when">18:00 - 20:30</div>
      <div class="date">Středa 16.9.</div>
      <a href="/oneplaysport-4/st-18.00-tipsport-extraliga.id108423999">
        Tipsport extraliga
      </a>
      <div class="description">HC Dynamo Pardubice - Mountfield HK</div>
      <div class="meta">Přímý přenos</div>
    </div>
    """
    monkeypatch.setattr(scraper, "_fetch_html", lambda url: html)

    rows = list(scraper._scrape_channel("oneplaysport-4"))

    assert len(rows) == 1
    assert rows[0].title == "Tipsport extraliga"
    assert "HC Dynamo Pardubice - Mountfield HK" in rows[0].description
    assert rows[0].start_local.isoformat() == "2026-09-16T18:00:00+02:00"


def test_channel_and_search_results_are_deduplicated(tmp_path, monkeypatch):
    scraper = make_scraper(tmp_path)
    html = """
    <div class="result-item">
      <div class="when">18:00 - 20:30</div>
      <div class="date">Středa 16.9.</div>
      <a href="/oneplaysport-4/st-18.00-tipsport-extraliga.id108423999">
        Tipsport extraliga
      </a>
      <div class="description">HC Dynamo Pardubice - Mountfield HK</div>
      <div class="meta">Přímý přenos</div>
    </div>
    """
    row = scraper.parse_search_html(html)[0]
    monkeypatch.setattr(scraper, "_scrape_channel", lambda slug: iter([row]))
    monkeypatch.setattr(scraper, "_scrape_query", lambda query: iter([row]))
    monkeypatch.setattr(scraper, "_close_browser", lambda: None)

    programs = scraper.scrape()

    assert len(programs) == 1
    assert programs[0].channel == "Oneplay Sport 4"
    assert programs[0].start_datetime.isoformat() == "2026-09-16T16:00:00+00:00"
