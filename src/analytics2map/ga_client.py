from __future__ import annotations

import logging
from datetime import datetime
from typing import List, Sequence

from google.analytics.data_v1beta import (
    BetaAnalyticsDataClient,
    DateRange,
    Dimension,
    Metric,
    OrderBy,
    RunReportRequest,
)
from google.oauth2 import service_account

from .config import GoogleAnalyticsConfig
from .schemas import Location, Source, VisitorEvent

LOGGER = logging.getLogger(__name__)


class GoogleAnalyticsClient:
    def __init__(self, config: GoogleAnalyticsConfig):
        self.config = config
        credentials = service_account.Credentials.from_service_account_file(
            str(config.credentials_path)
        )
        self._client = BetaAnalyticsDataClient(credentials=credentials)

    def fetch_events(self, since: datetime | None = None) -> List[VisitorEvent]:
        request = self._build_request(since)
        LOGGER.info("Requesting GA events for property %s", self.config.property_id)
        response = self._client.run_report(request)

        events: List[VisitorEvent] = []
        for row in response.rows:
            dimensions = {
                dim.name: value_value(row.dimension_values, idx)
                for idx, dim in enumerate(request.dimensions)
            }
            metrics = {
                met.name: value_value(row.metric_values, idx)
                for idx, met in enumerate(request.metrics)
            }

            visitor_id = dimensions.get("dateHourMinute") or "anonymous"
            visit_id = self._compose_visit_id(dimensions)
            occurred_at = self._infer_timestamp(dimensions)

            location = Location(
                city=dimensions.get("city"),
                region=dimensions.get("region"),
                country=dimensions.get("country"),
            )
            events.append(
                VisitorEvent(
                    source=Source.GOOGLE_ANALYTICS,
                    visitor_id=visitor_id,
                    visit_id=visit_id,
                    occurred_at=occurred_at,
                    location=location,
                    metadata={"metrics": metrics, "dimensions": dimensions},
                )
            )

        LOGGER.info("Received %d events from Google Analytics", len(events))
        return events

    def _compose_visit_id(self, dimensions: dict) -> str:
        parts = [dimensions.get(name, "") for name in self.config.dimensions]
        composite = "|".join(parts)
        if composite.strip("|"):
            return composite
        return f"{datetime.utcnow().timestamp()}"

    def _build_request(self, since: datetime | None) -> RunReportRequest:
        dimensions = [Dimension(name=name) for name in self.config.dimensions]
        metrics = [Metric(name=name) for name in self.config.metrics]
        date_range = DateRange(
            start_date=(since.date().isoformat() if since else "30daysAgo"),
            end_date="today",
        )

        return RunReportRequest(
            property=f"properties/{self.config.property_id}",
            dimensions=dimensions,
            metrics=metrics,
            date_ranges=[date_range],
            limit=self.config.max_rows,
            order_bys=[
                OrderBy(
                    dimension=OrderBy.DimensionOrderBy(dimension_name="dateHourMinute"),
                    desc=True,
                )
            ],
        )

    @staticmethod
    def _infer_timestamp(dimensions: dict) -> datetime:
        if "dateHourMinute" in dimensions:
            raw = dimensions["dateHourMinute"]
            return datetime.strptime(raw, "%Y%m%d%H%M")
        if "date" in dimensions:
            return datetime.strptime(dimensions["date"], "%Y%m%d")
        return datetime.utcnow()


def value_value(items: Sequence, idx: int) -> str:
    if idx >= len(items):
        return ""
    return items[idx].value or ""

