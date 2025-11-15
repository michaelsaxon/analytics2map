from __future__ import annotations

import logging
import math
from datetime import datetime
from pathlib import Path
from typing import Dict, Tuple

import svgwrite

from ..config import RendererConfig
from ..geo_lookup import GeoNamesLookup
from ..map_background import LandGeometryProvider
from ..schemas import Location, RenderScale

LOGGER = logging.getLogger(__name__)


class MapRenderer:
    def __init__(self, config: RendererConfig):
        self.config = config
        self.lookup = GeoNamesLookup()
        self.land_provider = LandGeometryProvider()

    def render(self, aggregates: Dict[str, Tuple[Location, int]]) -> None:
        output_dir = self.config.output_dir
        output_dir.mkdir(parents=True, exist_ok=True)
        LOGGER.info(
            "Rendering %d aggregated locations to %s",
            len(aggregates),
            output_dir,
        )

        for scale in self.config.scales:
            path = output_dir / f"visitors-{scale.slug}.svg"
            self._render_scale(scale, aggregates, path)

    def _render_scale(
        self,
        scale: RenderScale,
        aggregates: Dict[str, Tuple[Location, int]],
        output_path: Path,
    ) -> None:
        font_size = scale.title_font_size
        title_margin_top = 10
        title_margin_bottom = 10
        map_padding_bottom = 10
        rect_height = font_size + 20
        rect_y = title_margin_top
        total_height = (
            title_margin_top
            + rect_height
            + title_margin_bottom
            + scale.height
            + map_padding_bottom
        )
        dwg = svgwrite.Drawing(
            filename=str(output_path),
            size=(scale.width, total_height),
            profile="full",
        )

        # Base background
        dwg.add(
            dwg.rect(
                insert=(0, 0),
                size=("100%", "100%"),
                fill=self.config.theme.background_color,
            )
        )

        total_visits = sum(count for _, count in aggregates.values())
        as_of = datetime.utcnow().strftime("%Y-%m-%d")
        title_text = f"{total_visits:,} visits as of {as_of}"
        text_width_estimate = len(title_text) * (font_size * 0.6)
        rect_width = text_width_estimate + 40
        rect_x = (scale.width - rect_width) / 2
        dwg.add(
            dwg.rect(
                insert=(rect_x, rect_y),
                size=(rect_width, rect_height),
                fill=self.config.theme.title_background,
                rx=6,
                ry=6,
                opacity=0.85,
            )
        )
        dwg.add(
            dwg.text(
                title_text,
                insert=(scale.width / 2, rect_y + rect_height / 2 + 6),
                text_anchor="middle",
                font_size=font_size,
                font_weight="bold",
                fill=self.config.theme.title_color,
                font_family=self.config.theme.title_font_family,
            )
        )

        map_offset = rect_y + rect_height + title_margin_bottom
        effective_height = scale.height

        if self.config.background_path and self.config.background_path.exists():
            dwg.add(
                dwg.image(
                    href=self.config.background_path.as_posix(),
                    insert=(0, map_offset),
                    size=(scale.width, effective_height),
                )
            )
        else:
            dwg.add(
                dwg.rect(
                    insert=(0, map_offset),
                    size=(scale.width, effective_height),
                    fill=self.config.theme.background_color,
                )
            )
            self._draw_world_map(
                dwg,
                scale,
                y_offset=map_offset,
                effective_height=effective_height,
            )

        max_visits = max((count for _, count in aggregates.values()), default=1)
        for location, count in aggregates.values():
            coords = self.lookup.lookup(location.city, location.country)
            if not coords:
                LOGGER.debug(
                    "Skipping %s, %s due to missing coordinates",
                    location.city,
                    location.country,
                )
                continue
            latitude, longitude = coords
            x, y = project_point(
                latitude,
                longitude,
                scale,
                y_offset=map_offset,
                height_override=effective_height,
            )
            log_max = math.log(max_visits + 1)
            log_value = math.log(count + 1)
            normalized = log_value / log_max if log_max > 0 else 0
            radius = scale.dot_min_radius + normalized * (
                scale.dot_max_radius - scale.dot_min_radius
            )
            fill_color = self.config.theme.bubble_fill
            dwg.add(
                dwg.circle(
                    center=(x, y),
                    r=radius,
                    fill=fill_color,
                    fill_opacity=self.config.theme.bubble_opacity,
                    stroke=self.config.theme.bubble_stroke,
                    stroke_width=1,
                )
            )
        dwg.save()
        LOGGER.info("Rendered %s", output_path)

    def _draw_world_map(
        self,
        dwg: svgwrite.Drawing,
        scale: RenderScale,
        y_offset: float = 0.0,
        effective_height: float | None = None,
    ) -> None:
        polygons = self.land_provider.get_polygons(
            resolution=scale.land_resolution,
            simplify_tolerance=scale.simplify_tolerance,
        )
        land_group = dwg.add(
            dwg.g(
                fill=self.config.theme.land_fill,
                stroke=self.config.theme.land_stroke,
                stroke_width=1,
                opacity=0.85,
            )
        )
        for polygon in polygons:
            points = [
                project_point(
                    lat,
                    lon,
                    scale,
                    y_offset=y_offset,
                    height_override=effective_height,
                )
                for lon, lat in polygon
            ]
            land_group.add(dwg.polygon(points=points))
        # optional graticule lines
        grid = dwg.add(
            dwg.g(
                stroke=self.config.theme.grid_stroke,
                stroke_width=0.5,
                opacity=0.5,
            )
        )
        for lon in range(-180, 181, 30):
            start = project_point(85, lon, scale, y_offset, effective_height)
            end = project_point(-85, lon, scale, y_offset, effective_height)
            grid.add(dwg.line(start=start, end=end))
        for lat in range(-60, 90, 30):
            start = project_point(lat, -180, scale, y_offset, effective_height)
            end = project_point(lat, 180, scale, y_offset, effective_height)
            grid.add(dwg.line(start=start, end=end))

def project_point(
    latitude: float,
    longitude: float,
    scale: RenderScale,
    y_offset: float = 0.0,
    height_override: float | None = None,
) -> tuple[float, float]:
    """Project lat/lon onto an equirectangular canvas."""
    x = (longitude + 180) / 360 * scale.width
    height = height_override if height_override is not None else scale.height
    y = y_offset + (90 - latitude) / 180 * height
    return x, y

