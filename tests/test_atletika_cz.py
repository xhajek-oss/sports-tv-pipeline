from scrapers.atletika_cz import CzechAthleticsScraper


def test_targets_only_selected_senior_championships():
    kinds = {target["kind"] for target in CzechAthleticsScraper.TARGETS}
    assert kinds == {"mcr_outdoor_senior", "mcr_indoor_senior"}


def test_parse_outdoor_championship_metadata():
    scraper = CzechAthleticsScraper()
    html = "<html><body><h1>MČR mužů a žen 2026</h1><p>25. - 26. 7. 2026, Plzeň</p></body></html>"
    events = scraper._parse_target(html, scraper.TARGETS[0])

    assert len(events) == 2
    assert events[0].competition == "MČR mužů a žen"
    assert events[0].location == "Plzeň"
    assert events[0].country == "CZE"
    assert events[0].source == "atletika_cz"
    assert events[0].start_datetime.isoformat() == "2026-07-24T22:00:00+00:00"
    assert events[1].name == "MČR mužů a žen – 2. den"


def test_parse_indoor_championship_cross_month_metadata():
    scraper = CzechAthleticsScraper()
    html = "<html><body><p>28. 2. - 1. 3. 2026, Ostrava</p></body></html>"
    events = scraper._parse_target(html, scraper.TARGETS[1])

    assert len(events) == 2
    assert events[0].location == "Ostrava"
    assert events[0].source_id == "mcr_indoor_senior:2026-02-28"
    assert events[1].source_id == "mcr_indoor_senior:2026-03-01"
