from dataclasses import dataclass
from datetime import datetime
from typing import Optional


@dataclass(frozen=True)
class TVProgram:
    source: str
    source_id: Optional[str]
    channel: str
    title: str
    description: Optional[str]
    start_datetime: datetime
    end_datetime: Optional[datetime]
    source_url: str
    discovered_at: datetime
    timezone: str = "Europe/Prague"
    distribution: str = "tv"
