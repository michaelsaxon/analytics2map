from __future__ import annotations

from pathlib import Path
from typing import List, Optional

import yaml
from pydantic import BaseModel, Field

from .schemas import RenderScale


class GoogleAnalyticsConfig(BaseModel):
    property_id: str
    credentials_path: Path
    dataset: str = "events"
    dimensions: List[str] = Field(
        default_factory=lambda: [
            "city",
            "region",
            "country",
            "dateHourMinute",
        ]
    )
    metrics: List[str] = Field(default_factory=lambda: ["totalUsers"])
    max_rows: int = 1000


class DatabaseConfig(BaseModel):
    path: Path = Path("data/visits.tsv")


class ThemeConfig(BaseModel):
    background_color: str = "#0b1221"
    land_fill: str = "#1f2d3d"
    land_stroke: str = "#101827"
    grid_stroke: str = "#132033"
    bubble_fill: str = "#ff6347"
    bubble_stroke: str = "#ff8261"
    bubble_fill_recent: str = "#957fb8"
    bubble_stroke_recent: str = "#938aa9"
    bubble_opacity: float = 0.7
    title_color: str = "#f8f8f2"
    title_font_family: str = "Inter, Arial, sans-serif"
    title_background: str = "#050505"


class RendererConfig(BaseModel):
    background_path: Optional[Path] = None
    output_dir: Path = Path("output")
    theme: ThemeConfig = Field(default_factory=ThemeConfig)
    most_recent_visits: Optional[int] = None
    scales: List[RenderScale] = Field(
        default_factory=lambda: [
            RenderScale(
                slug="small",
                width=800,
                height=400,
                dot_max_radius=10,
                title_font_size=24,
                land_resolution="110m",
                simplify_tolerance=0.75,
            ),
            RenderScale(
                slug="medium",
                width=1600,
                height=800,
                dot_max_radius=8,
                title_font_size=32,
                land_resolution="50m",
                simplify_tolerance=0.4,
            ),
        ]
    )


class ClustrmapsConfig(BaseModel):
    csv_path: Optional[Path] = None


class AppConfig(BaseModel):
    google_analytics: GoogleAnalyticsConfig
    database: DatabaseConfig = Field(default_factory=DatabaseConfig)
    renderer: RendererConfig = Field(default_factory=RendererConfig)
    clustrmaps: ClustrmapsConfig = Field(default_factory=ClustrmapsConfig)

    @classmethod
    def load(cls, path: Path) -> "AppConfig":
        with Path(path).expanduser().open("r", encoding="utf-8") as handle:
            raw = yaml.safe_load(handle)
        return cls.parse_obj(raw)

