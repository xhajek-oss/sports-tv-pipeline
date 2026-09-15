from scrapers.czechathletics_youtube import CzechAthleticsYouTubeScraper


def test_channel_parser_keeps_selected_senior_championships_only():
    html = '''<script>var ytInitialData = {"contents":{"videoRenderer":{"videoId":"senior1","title":{"runs":[{"text":"MČR mužů a žen 2026 - 1. den"}]}}},"other":{"videoRenderer":{"videoId":"youth1","title":{"simpleText":"MČR juniorů a dorostu 2026"}}}};</script>'''
    assert CzechAthleticsYouTubeScraper.parse_channel_html(html) == [
        ("senior1", "MČR mužů a žen 2026 - 1. den")
    ]


def test_channel_parser_accepts_indoor_senior_championship():
    html = '''<script>ytInitialData = {"contents":{"gridVideoRenderer":{"videoId":"indoor1","title":{"simpleText":"HMČR mužů a žen 2026 | Ostrava"}}}};</script>'''
    assert CzechAthleticsYouTubeScraper.parse_channel_html(html) == [
        ("indoor1", "HMČR mužů a žen 2026 | Ostrava")
    ]


def test_watch_parser_reads_live_broadcast_timestamps():
    html = '''<script>ytInitialPlayerResponse = {"videoDetails":{"title":"MČR mužů a žen 2026 - 1. den"},"microformat":{"playerMicroformatRenderer":{"liveBroadcastDetails":{"startTimestamp":"2026-07-25T10:00:00Z","endTimestamp":"2026-07-25T16:00:00Z"}}}};</script>'''
    start, end, title = CzechAthleticsYouTubeScraper.parse_watch_html(html)
    assert title == "MČR mužů a žen 2026 - 1. den"
    assert start.isoformat() == "2026-07-25T10:00:00+00:00"
    assert end.isoformat() == "2026-07-25T16:00:00+00:00"


def test_youth_stream_is_not_relevant():
    assert CzechAthleticsYouTubeScraper._is_relevant("HMČR juniorů a dorostu") is False
    assert CzechAthleticsYouTubeScraper._is_relevant("MČR do 22 let") is False
