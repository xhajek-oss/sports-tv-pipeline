from zoneinfo import ZoneInfo
from datetime import datetime, timezone
from pathlib import Path

from scrapers.idnes import IdnesTVScraper


CONFIG = """
idnes:
  timezone: Europe/Prague
  max_pages_per_query: 2
  search_queries: [atletika]
  channels:
    ct-4-sport: "ČT sport"
    oneplaysport-1: "Oneplay Sport 1"
"""


def make_scraper(tmp_path: Path, now: datetime) -> IdnesTVScraper:
    config = tmp_path / "tv_channels.yaml"
    config.write_text(CONFIG, encoding="utf-8")
    return IdnesTVScraper(str(config), now=now)


def test_parses_program_and_converts_prague_to_utc(tmp_path):
    scraper = make_scraper(tmp_path, datetime(2026, 9, 3, 12, tzinfo=timezone.utc))
    html = """
    <div class="result-item">
      <div class="when">20:30 - 22:05</div>
      <div class="date">Sobota 5.9.</div>
      <a href="/ct-4-sport/so-20.30-atletika-diamantova-liga-2026.id107986263">
        Atletika: Diamantová liga 2026
      </a>
      <div class="meta">Sport skryté titulky, High Definition</div>
    </div>
    """
    rows = scraper.parse_search_html(html)
    assert len(rows) == 1
    row = rows[0]
    assert row.source_id == "107986263"
    assert row.channel_slug == "ct-4-sport"
    assert row.start_local.isoformat() == "2026-09-05T20:30:00+02:00"
    assert row.end_local.isoformat() == "2026-09-05T22:05:00+02:00"


def test_end_time_after_midnight_moves_to_next_day(tmp_path):
    scraper = make_scraper(tmp_path, datetime(2026, 9, 3, 12, tzinfo=timezone.utc))
    html = """
    <article>
      <span>22:30 - 0:30</span><span>Pátek 4.9.</span>
      <a href="/ct-4-sport/pa-22.30-atletika-diamantova-liga-2026.id107986261">Atletika: Diamantová liga 2026</a>
    </article>
    """
    row = scraper.parse_search_html(html)[0]
    assert row.start_local.isoformat() == "2026-09-04T22:30:00+02:00"
    assert row.end_local.isoformat() == "2026-09-05T00:30:00+02:00"


def test_year_rollover(tmp_path):
    scraper = make_scraper(tmp_path, datetime(2026, 12, 29, 12, tzinfo=timezone.utc))
    html = """
    <article>
      <span>18:00 - 20:00</span><span>Sobota 2.1.</span>
      <a href="/ct-4-sport/so-18.00-biatlon.id123456789">Biatlon</a>
    </article>
    """
    row = scraper.parse_search_html(html)[0]
    assert row.start_local.date().isoformat() == "2027-01-02"


def test_filters_non_allowlisted_channel_and_bad_neighbor_time(tmp_path):
    scraper = make_scraper(tmp_path, datetime(2026, 9, 3, 12, tzinfo=timezone.utc))
    html = """
    <div><span>20:30 - 22:05</span><span>Sobota 5.9.</span>
      <a href="/unknown-sport/so-20.30-atletika.id1">Atletika</a>
    </div>
    <div><span>21:00 - 22:00</span><span>Sobota 5.9.</span>
      <a href="/ct-4-sport/so-20.30-atletika.id2">Atletika</a>
    </div>
    """
    assert scraper.parse_search_html(html) == []


def test_parse_search_html_real_idnes_sibling_layout(tmp_path):
    config = tmp_path / "tv.yaml"
    config.write_text(
        """idnes:\n  timezone: Europe/Prague\n  channels:\n    ct-4-sport: \"ČT sport\"\n  search_queries: []\n""",
        encoding="utf-8",
    )
    scraper = IdnesTVScraper(
        config_path=str(config),
        now=datetime(2026, 9, 3, 12, 0, tzinfo=ZoneInfo("Europe/Prague")),
    )
    html = """
    <div class="result">
      <span class="time">20:30 - 22:05</span>
      <span class="date">Sobota 5.9.</span>
      <h3><a href="/ct-4-sport/so-20.30-atletika-diamantova-liga-2026.id107986263">Atletika: Diamantová liga 2026</a></h3>
      <p>Sport skryté titulky, stereo vysílání, High Definition, širokoúhlé</p>
    </div>
    """
    items = scraper.parse_search_html(html)
    assert len(items) == 1
    assert items[0].source_id == "107986263"
    assert items[0].start_local.isoformat() == "2026-09-05T20:30:00+02:00"
    assert items[0].end_local.isoformat() == "2026-09-05T22:05:00+02:00"
