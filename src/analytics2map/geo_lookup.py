from __future__ import annotations

import logging
import unicodedata
from functools import lru_cache
from typing import Dict, Iterable, Optional, Tuple

import geonamescache

LOGGER = logging.getLogger(__name__)


def _normalize(text: str | None) -> str:
    if not text:
        return ""
    normalized = unicodedata.normalize("NFKD", text)
    ascii_text = normalized.encode("ascii", "ignore").decode("ascii")
    return ascii_text.strip().lower()


UNKNOWN_TOKENS = {"unknown location", "(not set)", "unknown", "unspecified", "-"}


class GeoNamesLookup:
    def __init__(self) -> None:
        self.gc = geonamescache.GeonamesCache()
        self._country_index = self._build_country_index()
        self._city_index = self._build_city_index()
        self._country_centroids = self._build_country_centroids()

    def _build_country_index(self) -> Dict[str, str]:
        index: Dict[str, str] = {}
        for iso2, payload in self.gc.get_countries().items():
            names: Iterable[str | None] = [
                payload.get("name"),
                payload.get("iso"),
                payload.get("iso3"),
                payload.get("iso_numeric"),
                payload.get("fips"),
            ]
            for name in names:
                key = _normalize(name)
                if key:
                    index[key] = iso2
        # Common overrides for GA naming variants
        index["united states"] = "US"
        index["united states of america"] = "US"
        index["united kingdom"] = "GB"
        index["russia"] = "RU"
        index["south korea"] = "KR"
        index["north korea"] = "KP"
        index["czech republic"] = "CZ"
        index["viet nam"] = "VN"
        return index

    def _build_city_index(self) -> Dict[Tuple[str, str], Tuple[float, float]]:
        index: Dict[Tuple[str, str], Tuple[float, float]] = {}
        for city in self.gc.get_cities().values():
            country_code = city.get("countrycode")
            if not country_code:
                continue
            names = {city.get("name")}
            alternates = city.get("alternatenames")
            if isinstance(alternates, str) and alternates:
                names.update(part.strip() for part in alternates.split(","))
            for name in names:
                key = (_normalize(name), country_code)
                if not key[0]:
                    continue
                index[key] = (float(city["latitude"]), float(city["longitude"]))
        LOGGER.info("Indexed %d geonames cities", len(index))
        return index

    def _build_country_centroids(self) -> Dict[str, Tuple[float, float]]:
        centroids: Dict[str, Tuple[float, float]] = {}
        grouped: Dict[str, Tuple[float, float]] = {}
        # Prefer capital coordinates if available
        for iso2, payload in self.gc.get_countries().items():
            capital = payload.get("capital")
            if capital:
                coords = self._city_index.get((_normalize(capital), iso2))
                if coords:
                    centroids[iso2] = coords
        # fallback: first city in dataset for the country
        for (city_key, country_code), coords in self._city_index.items():
            if country_code not in centroids:
                grouped[country_code] = coords
        centroids.update(grouped)
        return centroids

    @lru_cache(maxsize=4096)
    def lookup(self, city: str | None, country: str | None) -> Optional[Tuple[float, float]]:
        if not country:
            return None
        country_code = self._country_index.get(_normalize(country))
        if not country_code:
            LOGGER.debug("Unknown country %s", country)
            return None
        fallback = self._country_centroids.get(country_code)
        normalized_city = _normalize(city)
        if not normalized_city or normalized_city in UNKNOWN_TOKENS:
            return fallback
        key = (normalized_city, country_code)
        coords = self._city_index.get(key)
        if coords:
            return coords
        LOGGER.debug("Missing coordinates for %s, %s; using country centroid", city, country)
        return fallback

