from abc import ABC, abstractmethod
from typing import Iterable

from models.sports_event import SportsEvent


class BaseScraper(ABC):
    source: str

    @abstractmethod
    def scrape(self) -> Iterable[SportsEvent]:
        raise NotImplementedError
