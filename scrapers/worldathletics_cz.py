from scrapers.worldathletics import WorldAthleticsScraper


class CzechWorldAthleticsScraper(WorldAthleticsScraper):
    """Keep source parsing unchanged while normalizing report metadata."""

    TARGETS = [
        {
            **target,
            **(
                {"location": "Kodaň", "country": "DNK"}
                if target["kind"] == "copenhagen"
                else {}
            ),
        }
        for target in WorldAthleticsScraper.TARGETS
    ]
