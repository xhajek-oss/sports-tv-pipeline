from scrapers.atletika_cz import CzechAthleticsScraper


def test_targets_only_selected_senior_championships():
    kinds = {target["kind"] for target in CzechAthleticsScraper.TARGETS}
    assert kinds == {"mcr_outdoor_senior", "mcr_indoor_senior"}


def test_discover_targets_selects_current_senior_pages_and_excludes_youth():
    html = '''<html><body>
      <a href="/zpravodajstvi/vrcholne-akce/mcr-muzu-a-zen/">MČR mužů a žen</a>
      <a href="/zpravodajstvi/vrcholne-akce/mcr-muzu-a-zen-2025/">MČR mužů a žen 2025</a>
      <a href="/zpravodajstvi/vrcholne-akce/hmcr-muzu-a-zen-2026/">HMČR mužů a žen 2026</a>
      <a href="/zpravodajstvi/vrcholne-akce/hmcr-junioru-a-dorostu-2026/">HMČR juniorů a dorostu 2026</a>
      <a href="/zpravodajstvi/vrcholne-akce/mcr-muzu-a-zen-do-22-let-2026/">MČR mužů a žen do 22 let 2026</a>
    </body></html>'''
    targets = CzechAthleticsScraper.discover_targets(
        html, "https://www.atletika.cz/zpravodajstvi/vrcholne-akce/"
    )
    assert targets == [
        {
            "kind": "mcr_outdoor_senior",
            "competition": "Mistrovství ČR",
            "url": "https://www.atletika.cz/zpravodajstvi/vrcholne-akce/mcr-muzu-a-zen/",
        },
        {
            "kind": "mcr_indoor_senior",
            "competition": "Halové mistrovství ČR",
            "url": "https://www.atletika.cz/zpravodajstvi/vrcholne-akce/hmcr-muzu-a-zen-2026/",
        },
    ]


def test_parse_outdoor_championship_metadata():
    scraper = CzechAthleticsScraper()
    target = {"kind": "mcr_outdoor_senior", "competition": "Mistrovství ČR", "url": "https://example.test/mcr"}
    html = "<html><body><h1>MČR mužů a žen 2026</h1><p>25. - 26. 7. 2026, Plzeň</p></body></html>"
    events = scraper._parse_target(html, target)

    assert len(events) == 2
    assert events[0].competition == "Mistrovství ČR"
    assert events[0].location == "Plzeň"
    assert events[0].country is None
    assert events[0].source == "atletika_cz"
    assert events[0].start_datetime.isoformat() == "2026-07-24T22:00:00+00:00"
    assert events[1].name == "Mistrovství ČR – 2. den"


def test_parse_indoor_championship_cross_month_metadata():
    scraper = CzechAthleticsScraper()
    target = {"kind": "mcr_indoor_senior", "competition": "Halové mistrovství ČR", "url": "https://example.test/hmcr"}
    html = "<html><body><p>28. 2. - 1. 3. 2026, Ostrava</p></body></html>"
    events = scraper._parse_target(html, target)

    assert len(events) == 2
    assert events[0].competition == "Halové mistrovství ČR"
    assert events[0].location == "Ostrava"
    assert events[0].country is None
    assert events[0].source_id == "mcr_indoor_senior:2026-02-28"
    assert events[1].source_id == "mcr_indoor_senior:2026-03-01"
