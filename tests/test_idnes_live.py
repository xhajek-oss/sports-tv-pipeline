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


def test_structured_live_card_uses_local_grid_time_and_does_not_fetch_detail(tmp_path, monkeypatch):
    scraper = make_scraper(tmp_path)
    base = datetime(2026, 9, 16, 0, tzinfo=scraper.tz)
    html = f'''
    <script>TV.init({{den: new Date({int(base.timestamp() * 1000)})}});</script>
    <a data-show="108423999" data-channel="99" data-start="1080" data-length="150"
       href="/oneplaysport-4/st-18.00-tipsport-extraliga.id108423999">
        <div class="x-spr x-live">
            <h3>Tipsport extraliga</h3>
            <p>HC Dynamo Pardubice - Mountfield HK</p>
        </div>
    </a>
    '''
    monkeypatch.setattr(scraper, "_fetch_html", lambda url: html)
    monkeypatch.setattr(scraper, "_fetch_detail_html",
                        lambda url: (_ for _ in ()).throw(AssertionError("complete card")))

    row, = scraper._scrape_channel("oneplaysport-4")

    assert row.start_local.isoformat() == "2026-09-16T18:00:00+02:00"
    assert row.end_local.isoformat() == "2026-09-16T20:30:00+02:00"


def _grid(base, schedules, tz):
    start = datetime.combine(base, datetime.min.time(), tz)
    html = [f'<script>TV.init({{den: new Date({int(start.timestamp() * 1000)})}});</script>']
    for when, channel, title in schedules:
        minutes = int((when - start).total_seconds() / 60)
        day = ("po", "ut", "st", "ct", "pa", "so", "ne")[when.weekday()]
        id_ = f"{when:%Y%m%d%H%M}{channel == 'ct-2':d}"
        html.append(
            f'<a data-show="{id_}" data-channel="99" data-start="{minutes}" data-length="90" '
            f'href="/{channel}/{day}-{when:%H.%M}-porad.id{id_}">'
            f'<div class="x-live"><h3>{title}</h3></div></a>'
        )
    return "".join(html)


def test_grouped_schedule_keeps_today_and_weekly_with_channel_fallback(tmp_path, monkeypatch):
    from datetime import timedelta

    from delivery.digest import build_today_digest
    from delivery.weekly import build_next_week_report
    from storage.sqlite import SQLiteStorage

    scraper = make_scraper(tmp_path)
    scraper.grouped_schedule = True
    scraper.search_fallback = False
    scraper.channels["ct-2"] = "ČT2"
    scraper.crawl_channels.append("ct-2")
    today = scraper.now.date()
    days = [today + timedelta(days=i) for i in range(9)]
    previous_day = today - timedelta(days=1)
    hockey = "ELH: Dynamo Pardubice – HC Kometa Brno"
    channel = "oneplaysport-4"
    requests = []

    def at(day, hour=18, minute=0):
        return datetime(day.year, day.month, day.day, hour, minute, tzinfo=scraper.tz)

    def fetch(url):
        requests.append(url)
        if url.endswith("/ct-2"):
            return _grid(today, [(at(day), "ct-2", "Film") for day in days[:-1]], scraper.tz)
        if "program=99" in url:
            return _grid(days[-1], [(at(days[-1]), "ct-2", "Film")], scraper.tz)
        if "/?dt=" in url:
            return "<html>Unavailable</html>"
        if url.endswith("/oneplaysport-4"):
            return _grid(today, [(at(days[-1]), channel, hockey)], scraper.tz)
        day = datetime.strptime(url.split("=")[-1], "%d.%m.%Y").date()
        if day == previous_day:
            return _grid(day, [(at(today, 0, 30), channel, hockey)], scraper.tz)
        if day == days[-1]:
            # A redirect to an earlier date must not count as coverage.
            return _grid(days[-2], [(at(days[-2]), channel, "Film")], scraper.tz)
        return _grid(day, [(at(day), channel, "Film")], scraper.tz)

    monkeypatch.setattr(scraper, "_fetch_html", fetch)
    monkeypatch.setattr(scraper, "_fetch_detail_html",
                        lambda url: (_ for _ in ()).throw(AssertionError("complete card")))
    rows = scraper.scrape()

    assert [row.start_datetime.astimezone(scraper.tz) for row in rows] == [
        at(today, 0, 30), at(days[-1]),
    ]
    assert len(requests) == len(days) + 5
    db = tmp_path / "sports.db"
    storage = SQLiteStorage(db)
    storage.replace_idnes_programs(rows)
    storage.close()
    assert "00:30" in build_today_digest(db, now=scraper.now)
    weekly = build_next_week_report(db, now=scraper.now)
    assert "18:00" in weekly and "00:30" not in weekly


def test_incomplete_grouped_schedule_preserves_last_snapshot(tmp_path, monkeypatch):
    from app.registry import SOURCES, SourceSpec
    from app.runner import PipelineRunner
    from models.tv_program import TVProgram
    from storage.sqlite import SQLiteStorage

    scraper = make_scraper(tmp_path)
    scraper.grouped_schedule = True
    monkeypatch.setattr(scraper, "_fetch_html", lambda url: "<html>Unavailable</html>")
    monkeypatch.setitem(SOURCES, "idnes", SourceSpec("idnes", "tv", lambda: scraper, allow_empty=True))
    db = tmp_path / "sports.db"
    storage = SQLiteStorage(db)
    storage.upsert_tv_program(TVProgram(
        "idnes", "previous", "Oneplay Sport 4", "Tipsport extraliga", None,
        scraper.now, None, "https://tvprogram.idnes.cz/", scraper.now,
    ))
    storage.close()

    runner = PipelineRunner(db_path=str(db), validation_state=str(tmp_path / "validation.json"))
    result, = runner.run_production("idnes")

    assert result.status == "down"
    storage = SQLiteStorage(db)
    assert storage.conn.execute("SELECT source_id FROM tv_programs").fetchall() == [("previous",)]
    storage.close()


def test_truncated_oneplay_card_reads_routes_from_full_detail(tmp_path, monkeypatch):
    from bs4 import BeautifulSoup
    from matching.idnes_rules import classify

    scraper = make_scraper(tmp_path)
    base = datetime(2026, 9, 16, 0, tzinfo=scraper.tz)
    card = """
    <a data-show="123" data-channel="99" data-start="1080" data-length="150"
       href="/oneplaysport-4/st-18.00-tipsport-extraliga.id123">
       <div class="x-live"><h3>Tipsport extraliga</h3>
         <p>Oneplay Sport MD7 - ELH: HC Dynamo Pardubice-HC Kometa Brno;...</p>
       </div>
    </a>
    """
    detail = f"""
    <h1>Tipsport extraliga</h1>
    <p>16. 9. 2026, 18:00</p>
    <p>Přímý přenos Tipsport extraligy. Oneplay Sport MD7 - ELH: HC Dynamo Pardubice-HC Kometa Brno;
    {"delší programový popis " * 75};
    Oneplay Sport MD10 - ELH: HC Dynamo Pardubice-HC Kometa Brno</p>
    <p>Přidat do mého TV programu</p>
    """
    monkeypatch.setattr(scraper, "_fetch_detail_html", lambda url: detail)
    anchors = BeautifulSoup(card, "html.parser").find_all("a")

    row, = scraper._parse_cards(anchors, "https://tvprogram.idnes.cz/sportovni", set(), base)

    assert {item.route for item in classify(row.title, row.description)} == {"MD7", "MD10"}
    assert row.end_local.hour == 20 and row.end_local.minute == 30


def test_monday_czech_grid_fills_dates_past_individual_channel_window(tmp_path, monkeypatch):
    from datetime import timedelta

    scraper = make_scraper(tmp_path)
    scraper.now = datetime(2026, 11, 9, 8, tzinfo=scraper.tz)
    scraper.grouped_schedule = True
    scraper.search_fallback = False
    scraper.channels["ct-1"] = "ČT1"
    scraper.channels["ct-2"] = "ČT2"
    scraper.crawl_channels.extend(["ct-1", "ct-2"])
    today = scraper.now.date()
    days = [today + timedelta(days=i) for i in range(14)]
    fallback_days = []

    def at(day):
        return datetime.combine(day, datetime.min.time(), scraper.tz).replace(hour=18)

    def fetch(url):
        if url.endswith(("/ct-1", "/ct-2")):
            channel = url.rsplit("/", 1)[1]
            return _grid(today, [(at(day), channel, "Film") for day in days[:10]], scraper.tz)
        assert "&program=" not in url
        day = datetime.strptime(url.rsplit("=", 1)[1], "%d.%m.%Y").date()
        if "/sportovni?" in url:
            return _grid(day, [(at(day), "oneplaysport-4", "Film")], scraper.tz)
        fallback_days.append(day)
        return _grid(day, [
            (at(day), "ct-1", "Film"),
            (at(day), "ct-2", "Atletika: Diamantová liga" if day == days[-1] else "Film"),
        ], scraper.tz)

    monkeypatch.setattr(scraper, "_fetch_html", fetch)
    monkeypatch.setattr(scraper, "_fetch_detail_html",
                        lambda url: (_ for _ in ()).throw(AssertionError("complete card")))

    item, = scraper.scrape()
    assert fallback_days == days[10:]
    assert item.channel == "ČT2"
    assert item.start_datetime.astimezone(scraper.tz) == at(days[-1])
