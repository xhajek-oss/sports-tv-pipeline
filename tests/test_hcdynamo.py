from datetime import timezone

from scrapers.hcdynamo import _ListItemParser, _parse_event_item


def test_hcdynamo_parser():
    html = """
    <ul>
      <li>
        1. kolo Liga Mistrů
        <span>čt 3. 9. 2026, 18:00</span>
        <img alt="Logo HC Dynamo Pardubice">
        VS
        <img alt="Logo GKS Tychy">
      </li>
    </ul>
    """

    parser = _ListItemParser()
    parser.feed(html)

    event = _parse_event_item(parser.items[0])

    assert event is not None
    assert event.source == "hcdynamo"
    assert event.sport == "ice_hockey"
    assert event.competition == "Liga Mistrů"
    assert event.name == "HC Dynamo Pardubice - GKS Tychy"
    assert event.timezone == "Europe/Prague"
    assert event.start_datetime.tzinfo == timezone.utc
    assert event.start_datetime.isoformat() == "2026-09-03T16:00:00+00:00"
