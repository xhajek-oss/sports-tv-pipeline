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
URLS = [
    f"https://api.biathlonresults.com/modules/sportapi/api/Competitions?EventId={EVENT_ID}",
    f"https://biathlonresults.com/modules/sportapi/api/Competitions?EventId={EVENT_ID}",
]


def main() -> None:
    success = False
    for url in URLS:
        host = url.split("/")[2]
        request = Request(url, headers={
            "Accept": "application/json, application/xml;q=0.9",
            "User-Agent": "sports-tv-pipeline/ibu-probe",
        })
        try:
            with urlopen(request, timeout=25) as response:
                payload = response.read(2_000_001)
                content_type = response.headers.get("Content-Type", "")
                status = response.status
        except HTTPError as exc:
            challenge = exc.headers.get("WWW-Authenticate", "not provided")
            print(f"[IBU-PROBE] host={host} http={exc.code} auth_challenge={challenge!r}")
            continue
        except (URLError, TimeoutError) as exc:
            print(f"[IBU-PROBE] host={host} network_error={type(exc).__name__}: {exc}")
            continue
        if len(payload) > 2_000_000:
            print(f"[IBU-PROBE] host={host} response too large")
            continue
        print(f"[IBU-PROBE] host={host} http={status} content_type={content_type} bytes={len(payload)}")
        try:
            parsed = parse_official_competitions(payload.decode("utf-8-sig"))
        except Exception as exc:
            print(f"[IBU-PROBE] host={host} parse_error={type(exc).__name__}: {exc}")
            continue
        print(f"[IBU-PROBE] host={host} parsed_races={len(parsed)}")
        for race_id, start in list(sorted(parsed.items()))[:8]:
            print(f"[IBU-PROBE] race_id={race_id} start_utc={start.isoformat()}")
        success = success or bool(parsed)
    if not success:
        raise SystemExit("[IBU-PROBE] Neither official API host returned verifiable races")


if __name__ == "__main__":
    main()
