from __future__ import annotations

from datetime import datetime
from enum import Enum
from typing import Optional

from pydantic import BaseModel, Field


class Source(str, Enum):
    GOOGLE_ANALYTICS = "google_analytics"
    CLUSTRMAPS = "clustrmaps"


class Location(BaseModel):
    city: Optional[str] = None
    region: Optional[str] = None
    country: Optional[str] = None
    latitude: Optional[float] = None
    longitude: Optional[float] = None

    def normalized_key(self) -> str:
        """Create a stable identifier for grouping locations."""
        return "|".join(
            part.strip().lower()
            for part in (
                self.city or "",
                self.country or "",
            )
        )


class VisitorEvent(BaseModel):
    source: Source
    visitor_id: str
    visit_id: str
    occurred_at: datetime
    location: Location = Field(default_factory=Location)
    metadata: dict = Field(default_factory=dict)


class RenderScale(BaseModel):
    slug: str
    width: int
    height: int
    dot_min_radius: float = 2.0
    dot_max_radius: float = 12.0
    label_threshold: int = 5
    title_font_size: int = 28
    land_resolution: str = "110m"
    simplify_tolerance: float = 0.5

