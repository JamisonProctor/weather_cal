# forecast.py

from dataclasses import dataclass, field
from typing import List, Optional

@dataclass
class Forecast:
    """
    Weather forecast for a single day at a single location.
    """
    date: str                       # e.g. "2025-08-01"
    location: str                   # e.g. "Munich, Germany"
    high: float                     # Daily high temperature
    low: float                      # Daily low temperature
    summary: str                    # Short summary, e.g. "AM⛅15° / PM☁️19°"
    times: List[str] = field(default_factory=list)     # e.g. ["2025-08-01T06:00", ...]
    temps: List[float] = field(default_factory=list)   # temperatures for each time slot
    codes: List[int] = field(default_factory=list)     # weather codes for each time slot
    rain: List[float] = field(default_factory=list)    # % chance of rain per time slot
    winds: List[float] = field(default_factory=list)   # wind speed per time slot
    details: Optional[str] = None                      # Multiline description for calendar event
    fetch_time: Optional[str] = None                   # When the forecast was retrieved (ISO string)

    def __post_init__(self):
        if self.fetch_time is None:
            from datetime import datetime
            self.fetch_time = datetime.now().isoformat()