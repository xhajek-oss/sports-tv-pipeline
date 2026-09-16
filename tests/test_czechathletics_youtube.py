from scrapers.atletika_cz import CzechAthleticsScraper
from scrapers.czechathletics_youtube import CzechAthleticsYouTubeScraper


def test_atletika_parser_finds_only_stream_links():
    html = '''
    <html><body>
      <a href="stream-sobota/">Stream - sobota</a>
      <a href="stream-nedele/">Stream - neděle</a>
      <a href="propozice/">Propozice</a>
    </body></html>
    '''
    links = CzechAthleticsYouTubeScraper.parse_atletika_stream_links(
        html,
        "https://www.atletika.cz/zpravodajstvi/vrcholne-akce/hmcr-muzu-a-zen-2026/",
    )
    assert links == [
        "https://www.atletika.cz/zpravodajstvi/vrcholne-akce/hmcr-muzu-a-zen-2026/stream-sobota/",
        "https://www.atletika.cz/zpravodajstvi/vrcholne-akce/hmcr-muzu-a-zen-2026/stream-nedele/",
    ]


def test_atletika_parser_accepts_direct_youtube_stream():
    html = '''<a href="https://www.youtube.com/watch?v=abc123">Stream (YouTube)</a>'''
    links = CzechAthleticsYouTubeScraper.parse_atletika_stream_links(
        html, "https://www.atletika.cz/event/"
    )
    assert links == ["https://www.youtube.com/watch?v=abc123"]


def test_watch_parser_reads_live_broadcast_timestamps():
    html = '''<script>ytInitialPlayerResponse = {"videoDetails":{"title":"MČR mužů a žen 2026 - 1. den"},"microformat":{"playerMicroformatRenderer":{"liveBroadcastDetails":{"startTimestamp":"2026-07-25T10:00:00Z","endTimestamp":"2026-07-25T16:00:00Z"}}}};</script>'''
    start, end, title = CzechAthleticsYouTubeScraper.parse_watch_html(html)
    assert title == "MČR mužů a žen 2026 - 1. den"
    assert start.isoformat() == "2026-07-25T10:00:00+00:00"
    assert end.isoformat() == "2026-07-25T16:00:00+00:00"


def test_watch_parser_stops_at_balanced_json_object():
    html = '''<script>ytInitialPlayerResponse = {"videoDetails":{"title":"MČR {finále}"},"microformat":{"playerMicroformatRenderer":{"liveBroadcastDetails":{"startTimestamp":"2026-07-25T10:00:00Z"}}}}; window.after = {"unrelated":true};</script>'''
    start, end, title = CzechAthleticsYouTubeScraper.parse_watch_html(html)
    assert title == "MČR {finále}"
    assert start.isoformat() == "2026-07-25T10:00:00+00:00"
    assert end is None


def test_watch_parser_handles_braces_and_escaped_quotes_inside_strings():
    html = '<script>ytInitialPlayerResponse = {"videoDetails":{"title":"MČR \\"A{B}\\""},"microformat":{"playerMicroformatRenderer":{"liveBroadcastDetails":{"startTimestamp":"2026-07-25T10:00:00Z"}}}};</script>'
    start, _, title = CzechAthleticsYouTubeScraper.parse_watch_html(html)
    assert title == 'MČR "A{B}"'
    assert start.isoformat() == "2026-07-25T10:00:00+00:00"


def test_stream_source_reuses_selected_czech_senior_discovery():
    listing = '''
    <a href="/hmcr-muzu-a-zen-2026/">HMČR mužů a žen 2026</a>
    <a href="/mcr-muzu-a-zen/">MČR mužů a žen 2026</a>
    <a href="/mcr-muzu-a-zen-do-22-let/">MČR mužů a žen do 22 let 2026</a>
    '''
    targets = CzechAthleticsScraper.discover_targets(listing)
    assert {target["competition"] for target in targets} == {
        "Mistrovství ČR",
        "Halové mistrovství ČR",
    }
