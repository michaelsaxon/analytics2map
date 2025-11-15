from __future__ import annotations

import logging
from typing import Iterable, List, Sequence, Tuple

import cartopy.io.shapereader as shpreader
from shapely.geometry import MultiPolygon, Polygon

LOGGER = logging.getLogger(__name__)

CoordinateSeq = Sequence[Tuple[float, float]]


class LandGeometryProvider:
    """Loads Natural Earth land polygons via Cartopy for rendering backgrounds."""

    def __init__(self) -> None:
        self._cache: dict[Tuple[str, float], List[CoordinateSeq]] = {}

    def get_polygons(
        self, resolution: str = "110m", simplify_tolerance: float = 0.5
    ) -> List[CoordinateSeq]:
        key = (resolution, simplify_tolerance)
        if key not in self._cache:
            self._cache[key] = self._load_polygons(resolution, simplify_tolerance)
        return self._cache[key]

    def _load_polygons(
        self, resolution: str, simplify_tolerance: float
    ) -> List[CoordinateSeq]:
        path = shpreader.natural_earth(
            resolution=resolution, category="physical", name="land"
        )
        reader = shpreader.Reader(path)
        polygons: List[CoordinateSeq] = []
        for geometry in reader.geometries():
            polygons.extend(self._extract_polygons(geometry, simplify_tolerance))
        LOGGER.info(
            "Loaded %d land polygons from Natural Earth (%s)",
            len(polygons),
            resolution,
        )
        return polygons

    def _extract_polygons(
        self, geometry, simplify_tolerance: float
    ) -> Iterable[CoordinateSeq]:
        simplified = geometry
        if simplify_tolerance:
            simplified = geometry.simplify(simplify_tolerance, preserve_topology=True)
        if isinstance(simplified, Polygon):
            yield list(simplified.exterior.coords)
        elif isinstance(simplified, MultiPolygon):
            for polygon in simplified.geoms:
                yield list(polygon.exterior.coords)
        else:
            LOGGER.debug("Skipping unsupported geometry type: %s", geometry.geom_type)

