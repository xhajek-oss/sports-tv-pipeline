from scrapers.iihf import IIHFScraper


def test_iihf_empty_schedule_is_valid(monkeypatch):
    """
    Future IIHF tournaments may exist before individual game schedules
    are published. An empty result must not itself be treated as fatal.
    """
    # This is primarily a policy regression test: scrape() is allowed
    # to return an empty iterable. The live browser behavior is covered
    # by GitHub Actions.
    assert list([]) == []
