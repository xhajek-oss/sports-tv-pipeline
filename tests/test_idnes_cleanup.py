from scrapers.idnes import IdnesTVScraper


def test_query_relevance_filters_atletico_false_positive():
    assert IdnesTVScraper._is_query_relevant("atletika", "Atletika: Diamantová liga 2026")
    assert IdnesTVScraper._is_query_relevant("atletika", "World Athletics Ultimate Championship 2026")
    assert not IdnesTVScraper._is_query_relevant("atletika", "Liverpool FC - Atlético Madrid")


def test_query_relevance_accepts_hockey_aliases():
    assert IdnesTVScraper._is_query_relevant("hokej", "Hokej: Maxa liga 2026/2027")
    assert IdnesTVScraper._is_query_relevant("hokej", "ELH: HC Dynamo Pardubice - Mountfield HK")
    assert IdnesTVScraper._is_query_relevant("hokej", "Studio HOKEJ (L)")
    assert not IdnesTVScraper._is_query_relevant("hokej", "Real Sociedad - Atlético Madrid")


def test_normalize_text_removes_accents_and_punctuation():
    assert IdnesTVScraper._normalize_text("ČT sport – Atletika") == "ct sport atletika"
