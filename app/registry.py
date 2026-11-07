from __future__ import annotations

from dataclasses import dataclass
from typing import Callable, Literal

from scrapers.atletika_cz import CzechAthleticsScraper
from scrapers.czechathletics_youtube import CzechAthleticsYouTubeScraper
from scrapers.idnes_live import LiveIdnesTVScraper


SourceKind = Literal["sports", "tv"]


@dataclass(frozen=True)
class SourceSpec:
    name: str
    kind: SourceKind
    factory: Callable[[], object]
    allow_empty: bool = False


SOURCES: dict[str, SourceSpec] = {
    "atletika_cz": SourceSpec("atletika_cz", "sports", CzechAthleticsScraper),
    "idnes": SourceSpec("idnes", "tv", LiveIdnesTVScraper),
    "czechathletics_youtube": SourceSpec(
        "czechathletics_youtube", "tv", CzechAthleticsYouTubeScraper, allow_empty=True
    ),
}


def selected_sources(value: str) -> list[SourceSpec]:
    if value == "all":
        return list(SOURCES.values())
    names = [part.strip() for part in value.split(",") if part.strip()]
    unknown = [name for name in names if name not in SOURCES]
    if unknown:
        raise ValueError(f"Unknown source(s): {', '.join(unknown)}")
    return [SOURCES[name] for name in names]
