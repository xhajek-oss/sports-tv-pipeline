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


def source_names(kind: SourceKind | None = None) -> list[str]:
    names = []
    for name, spec in SOURCES.items():
        if kind is None or spec.kind == kind:
            names.append(name)
    return names


def get_source(name: str) -> SourceSpec:
    try:
        return SOURCES[name]
    except KeyError as exc:
        choices = ", ".join(source_names())
        raise ValueError(f"Unknown source {name!r}. Available: {choices}") from exc
