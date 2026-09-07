from delivery.digest import _country_cs, _location_cs
from scrapers.worldathletics_cz import CzechWorldAthleticsScraper


def test_copenhagen_metadata_is_ready_for_daily_and_weekly_reports():
    target = next(
        item for item in CzechWorldAthleticsScraper.TARGETS
        if item["kind"] == "copenhagen"
    )

    assert target["location"] == "Kodaň"
    assert target["country"] == "DNK"
    assert _location_cs(target["location"]) == "Kodaň"
    assert _country_cs(target["country"]) == "Dánsko"
