from pydantic import BaseModel
from typing import Dict, Optional
from datetime import datetime

class Market(BaseModel):
    key: str  # e.g. "1x2"
    outcomes: Dict[str, float]  # {"1": 2.10, "X": 3.40, "2": 3.60}

class Event(BaseModel):
    booker: str
    event_id: Optional[str]
    league: Optional[str]
    home: str
    away: str
    start: datetime
    markets: Dict[str, Market]
