from matching.tv_matcher import _hockey_matchup, _hockey_team


def test_hockey_team_strips_common_club_prefixes_and_suffixes():
    assert _hockey_team("HC Dynamo Pardubice") == "dynamo pardubice"
    assert _hockey_team("Rögle BK") == "rogle"
    assert _hockey_team("Mountfield HK") == "mountfield"


def test_hockey_matchup_accepts_tv_title_without_bk_suffix():
    event = _hockey_matchup("HC Dynamo Pardubice - Rögle BK")
    tv = _hockey_matchup("Lední hokej: Dynamo Pardubice - Rögle")
    assert event == tv
