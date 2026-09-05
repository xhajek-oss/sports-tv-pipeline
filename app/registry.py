from __future__ import annotations

from dataclasses import dataclass
from typing import Callable, Literal

from scrapers.biathlonworld import BiathlonWorldScraper
from scrapers.diamondleague import DiamondLeagueScraper
from scrapers.hcdynamo import HCDynamoScraper
from scrapers.idnes import IdnesTVScraper
from scrapers.iihf import IIHFScraper
from scrapers.worldathletics import WorldAthleticsScraper


SourceKind = Literal["sports", "tv"]


@dataclass(frozen=True)
class SourceSpec:
    name: str
    kind: SourceKind
    factory: Callable[[], object]
    allow_empty: bool = False


SOURCES: dict[str, SourceSpec] = {
    "hcdynamo": SourceSpec("hcdynamo", "sports", HCDynamoScraper),
    "biathlonworld": SourceSpec("biathlonworld", "sports", BiathlonWorldScraper),
    "iihf": SourceSpec("iihf", "sports", IIHFScraper, allow_empty=True),
    "diamondleague": SourceSpec("diamondleague", "sports", DiamondLeagueScraper),
    "worldathletics": SourceSpec("worldathletics", "sports", WorldAthleticsScraper),
    "idnes": SourceSpec("idnes", "tv", IdnesTVScraper),
}


def selected_sources(value: str) -> list[SourceSpec]:
    if value == "all":
        return list(SOURCES.values())
    names = [part.strip() for part in value.split(",") if part.strip()]
    unknown = [name for name in names if name not in SOURCES]
    if unknown:
        raise ValueError(f"Unknown source(s): {', '.join(unknown)}")
    return [SOURCES[name] for name in names]
