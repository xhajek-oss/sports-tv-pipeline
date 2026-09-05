from dataclasses import dataclass
from datetime import datetime
from typing import Optional


@dataclass
class SportsEvent:
    source: str
    source_id: Optional[str]
    sport: str
    competition: str
    name: str
    start_datetime: datetime
    end_datetime: Optional[datetime]
    location: Optional[str]
    country: Optional[str]
    source_url: str
    discovered_at: datetime
    timezone: Optional[str] = None
