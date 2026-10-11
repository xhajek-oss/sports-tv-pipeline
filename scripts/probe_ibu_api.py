"""Manual IBU Datacenter connectivity probe (never modifies production data).

Run via GitHub Actions > IBU API Probe > Run workflow.
"""
from __future__ import annotations

import json
import os
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

from validation.ibu_datacenter import parse_official_competitions

EVENT_ID = os.environ.get("IBU_EVENT_ID", "BT2627SWRLCP01")
URL = f"https://api.biathlonresults.com/modules/sportapi/api/Competitions?EventId={EVENT_ID}"


def main() -> None:
    request = Request(URL, headers={"Accept": "application/json, application/xml;q=0.9", "User-Agent": "sports-tv-pipeline/ibu-probe"})
    try:
        with urlopen(request, timeout=25) as response:
            payload = response.read(2_000_001)
            content_type = response.headers.get("Content-Type", "")
            status = response.status
    except (HTTPError, URLError, TimeoutError) as exc:
        print(f"[IBU-PROBE] network error: {type(exc).__name__}: {exc}")
        raise SystemExit(1) from exc
    if len(payload) > 2_000_000:
        raise SystemExit("[IBU-PROBE] response too large")
    print(f"[IBU-PROBE] http={status} content_type={content_type} bytes={len(payload)} event_id={EVENT_ID}")
    text = payload.decode("utf-8-sig")
    try:
        parsed = parse_official_competitions(text)
    except (ValueError, Exception) as exc:
        print(f"[IBU-PROBE] parse error: {type(exc).__name__}: {exc}")
        raise SystemExit(1) from exc
    print(f"[IBU-PROBE] parsed_races={len(parsed)}")
    for race_id, start in list(sorted(parsed.items()))[:8]:
        print(f"[IBU-PROBE] race_id={race_id} start_utc={start.isoformat()}")
    if not parsed:
        raise SystemExit("[IBU-PROBE] no RaceId/StartTime pairs; schema or EventId needs investigation")


if __name__ == "__main__":
    main()
