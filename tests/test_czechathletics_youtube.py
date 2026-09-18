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


def test_resolves_youtube_embedded_on_atletika_page_without_youtube_metadata():
    html = '''
    <html><body>
      <iframe src="https://www.youtube.com/embed/abc123"></iframe>
    </body></html>
    '''
    assert CzechAthleticsYouTubeScraper.resolve_youtube_from_atletika_html(
        html, "https://www.atletika.cz/stream-sobota/"
    ) == "https://www.youtube.com/embed/abc123"


def test_non_youtube_link_is_not_reported_as_youtube():
    html = '''<a href="https://example.com/live">jiný přenos</a>'''
    assert CzechAthleticsYouTubeScraper.resolve_youtube_from_atletika_html(
        html, "https://www.atletika.cz/stream/"
    ) is None


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


def test_fetch_atletika_never_follows_external_redirect(monkeypatch):
    scraper = CzechAthleticsYouTubeScraper()
    calls = []

    class Response:
        is_redirect = True
        is_permanent_redirect = False
        headers = {"Location": "https://www.youtube.com/watch?v=abc123"}
        text = ""
        url = "https://www.atletika.cz/stream/"
        def raise_for_status(self):
            return None

    def fake_get(url, **kwargs):
        calls.append((url, kwargs))
        return Response()

    monkeypatch.setattr(scraper.session, "get", fake_get)
    response = scraper._fetch_atletika("https://www.atletika.cz/stream/")

    assert len(calls) == 1
    assert calls[0][0] == "https://www.atletika.cz/stream/"
    assert calls[0][1]["allow_redirects"] is False
    assert response._atletika_external_redirect == "https://www.youtube.com/watch?v=abc123"


def test_resolver_returns_youtube_redirect_without_requesting_youtube(monkeypatch):
    scraper = CzechAthleticsYouTubeScraper()
    requested = []

    class Response:
        is_redirect = True
        is_permanent_redirect = False
        headers = {"Location": "https://youtu.be/abc123"}
        text = ""
        url = "https://www.atletika.cz/stream/"
        def raise_for_status(self):
            return None

    def fake_get(url, **kwargs):
        requested.append(url)
        if "youtube" in url or "youtu.be" in url:
            raise AssertionError("YouTube must never be requested")
        return Response()

    monkeypatch.setattr(scraper.session, "get", fake_get)
    assert scraper._resolve_stream_from_atletika("https://www.atletika.cz/stream/") == "https://youtu.be/abc123"
    assert requested == ["https://www.atletika.cz/stream/"]


def test_fetch_atletika_rejects_direct_youtube_url(monkeypatch):
    scraper = CzechAthleticsYouTubeScraper()

    def forbidden(*args, **kwargs):
        raise AssertionError("HTTP client must not be called")

    monkeypatch.setattr(scraper.session, "get", forbidden)

    try:
        scraper._fetch_atletika("https://www.youtube.com/watch?v=abc123")
    except ValueError as exc:
        assert "Refusing non-Atletika.cz request" in str(exc)
    else:
        raise AssertionError("Expected non-Atletika.cz URL to be rejected")
