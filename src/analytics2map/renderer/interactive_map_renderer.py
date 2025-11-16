from __future__ import annotations

import json
import math
from datetime import datetime
from pathlib import Path
from typing import Dict, Iterable, Tuple

from ..config import RendererConfig
from ..geo_lookup import GeoNamesLookup
from ..schemas import Location, RenderScale


class InteractiveMapRenderer:
    """Render an interactive HTML map using D3.js."""

    def __init__(self, config: RendererConfig):
        self.config = config
        self.lookup = GeoNamesLookup()

    def _select_scale(self) -> RenderScale:
        """Pick a 'large' scale for the interactive map.

        Strategy:
        - Prefer an explicitly configured 'large' or 'medium' slug.
        - Fallback to the last configured scale.
        """
        if not self.config.scales:
            # Sensible default if config is somehow empty
            return RenderScale(slug="interactive", width=1600, height=800)

        by_slug = {scale.slug: scale for scale in self.config.scales}
        for preferred in ("large", "medium"):
            if preferred in by_slug:
                return by_slug[preferred]
        return self.config.scales[-1]

    def render(
        self,
        aggregates: Dict[str, Tuple[Location, int, datetime | None]],
        output_path: Path | None = None,
    ) -> Path:
        """Write static HTML and JSON data files for the interactive map.

        Args:
            aggregates: mapping of key -> (Location, total_visits, last_timestamp)
            output_path: optional explicit output path. Defaults to
                `<output_dir>/visitors-interactive.html`.
        """
        scale = self._select_scale()
        output_dir = self.config.output_dir
        output_dir.mkdir(parents=True, exist_ok=True)
        if output_path is None:
            output_path = output_dir / "visitors-interactive.html"

        visit_points = list(self._build_visit_points(aggregates))
        
        # Write JSON data file
        json_path = output_dir / "visitors-data.json"
        json_path.write_text(json.dumps(visit_points, indent=2), encoding="utf-8")
        
        # Increase marker sizes for interactive map
        scale_copy = RenderScale(
            slug=scale.slug,
            width=scale.width,
            height=scale.height,
            dot_min_radius=scale.dot_min_radius * 2,
            dot_max_radius=scale.dot_max_radius * 2,
            label_threshold=scale.label_threshold,
            title_font_size=scale.title_font_size,
            land_resolution=scale.land_resolution,
            simplify_tolerance=scale.simplify_tolerance,
            recent_min_radius=scale.recent_min_radius,
        )
        html = self._build_html(scale_copy)
        output_path.write_text(html, encoding="utf-8")
        return output_path

    def _build_visit_points(
        self,
        aggregates: Dict[str, Tuple[Location, int, datetime | None]],
    ) -> Iterable[dict]:
        """Convert raw aggregates into a JSON-serializable list with lat/lon."""
        if not aggregates:
            return []

        max_visits = max((count for _, count, _ in aggregates.values()), default=1)
        log_max = math.log(max_visits + 1)

        points: list[dict] = []
        for location, count, last_ts in aggregates.values():
            coords = self.lookup.lookup(location.city, location.country)
            if not coords:
                continue
            lat, lon = coords
            last_visit_iso = last_ts.isoformat() if isinstance(last_ts, datetime) else None
            normalized = math.log(count + 1) / log_max if log_max > 0 else 0
            points.append(
                {
                    "city": location.city,
                    "country": location.country,
                    "visitors": count,
                    "lastVisit": last_visit_iso,
                    "lat": lat,
                    "lon": lon,
                    "normalized": normalized,
                }
            )
        return points

    def _build_html(self, scale: RenderScale) -> str:
        """Generate the static HTML page that loads data from JSON."""
        theme = self.config.theme
        base_width = scale.width
        base_height = scale.height
        min_radius = scale.dot_min_radius
        max_radius = scale.dot_max_radius

        # Use a neutral, light page wrapper but keep the map colors consistent with SVG theme.
        return f"""<!DOCTYPE html>
<html lang="en">
  <head>
    <meta charset="utf-8" />
    <title>analytics2map – Interactive Visitor Map</title>
    <meta name="viewport" content="width=device-width, initial-scale=1" />
    <script src="https://d3js.org/d3.v7.min.js"></script>
    <script src="https://unpkg.com/topojson-client@3"></script>
    <style>
      :root {{
        color-scheme: dark;
        font-family: system-ui, -apple-system, BlinkMacSystemFont, "SF Pro Text",
          -system-ui, sans-serif;
        background: #050814;
        color: #f8f8f2;
      }}
      body {{
        margin: 0;
        background: #050814;
        color: #f8f8f2;
      }}
      .page {{
        max-width: 100%;
        margin: 0 auto;
        padding: 24px 20px 40px;
        box-sizing: border-box;
      }}
      h1 {{
        font-size: 28px;
        margin: 0 0 12px;
      }}
      p {{
        margin: 8px 0 16px;
        max-width: 720px;
        font-size: 15px;
        line-height: 1.6;
        color: #c4c3d0;
      }}
      .map-frame {{
        position: relative;
        border-radius: 12px;
        overflow: hidden;
        background: {theme.background_color};
        box-shadow: 0 18px 45px rgba(0, 0, 0, 0.6);
        border: 1px solid rgba(148, 163, 184, 0.35);
        max-width: 100%;
      }}
      svg {{
        display: block;
        width: 100%;
        height: auto;
      }}
      .tooltip {{
        position: absolute;
        pointer-events: none;
        background: rgba(15, 23, 42, 0.94);
        color: #e5e7eb;
        padding: 8px 10px;
        border-radius: 8px;
        font-size: 12px;
        line-height: 1.4;
        box-shadow: 0 10px 25px rgba(0, 0, 0, 0.55);
        border: 1px solid rgba(148, 163, 184, 0.5);
        opacity: 0;
        transform: translate(-50%, -140%);
        white-space: nowrap;
        z-index: 5;
      }}
      .tooltip strong {{
        font-weight: 600;
      }}
      .legend {{
        position: absolute;
        bottom: 10px;
        right: 14px;
        padding: 6px 8px;
        border-radius: 8px;
        background: rgba(15, 23, 42, 0.78);
        font-size: 11px;
        color: #e5e7eb;
        border: 1px solid rgba(148, 163, 184, 0.4);
        display: flex;
        gap: 6px;
        align-items: center;
        backdrop-filter: blur(8px);
      }}
      .legend-dot {{
        width: 10px;
        height: 10px;
        border-radius: 999px;
        background: {theme.bubble_fill};
        box-shadow: 0 0 0 1px {theme.bubble_stroke};
      }}
      .zoom-controls {{
        position: absolute;
        top: 10px;
        left: 10px;
        display: flex;
        flex-direction: column;
        gap: 4px;
        z-index: 10;
      }}
      .zoom-button {{
        width: 28px;
        height: 28px;
        border-radius: 999px;
        border: 1px solid rgba(148, 163, 184, 0.6);
        background: rgba(15, 23, 42, 0.92);
        color: #e5e7eb;
        font-size: 16px;
        line-height: 1;
        cursor: pointer;
        display: inline-flex;
        align-items: center;
        justify-content: center;
        padding: 0;
      }}
      .zoom-button:hover {{
        background: rgba(30, 64, 175, 0.95);
        border-color: rgba(129, 140, 248, 0.9);
      }}
      .visitor-stats {{
        position: absolute;
        top: 10px;
        right: 14px;
        padding: 8px 12px;
        border-radius: 8px;
        background: rgba(15, 23, 42, 0.92);
        font-size: 12px;
        color: #e5e7eb;
        border: 1px solid rgba(148, 163, 184, 0.5);
        backdrop-filter: blur(8px);
        line-height: 1.6;
        font-family: system-ui, -apple-system, sans-serif;
      }}
      .visitor-stats strong {{
        font-weight: 600;
        color: #f8f8f2;
      }}
      .stat-row {{
        display: flex;
        justify-content: space-between;
        gap: 12px;
      }}
    </style>
  </head>
  <body>
    <main class="page">
      <h1>Interactive visitor map</h1>
      <p>
        This map shows approximate locations of visitors, aggregated by city and country.
        Hover over a point to see the location, total visitors, and the most recent visit time.
        Use the + and − buttons to zoom, or drag to pan the map.
      </p>
      <div class="map-frame" id="map-frame">
        <div class="zoom-controls">
          <button class="zoom-button" id="zoom-in" type="button">+</button>
          <button class="zoom-button" id="zoom-out" type="button">−</button>
        </div>
        <div class="visitor-stats" id="visitor-stats">
          <div class="stat-row">
            <span>Total:</span>
            <strong id="total-visitors">0</strong>
          </div>
          <div class="stat-row">
            <span>Visible:</span>
            <strong id="visible-visitors">0</strong>
          </div>
        </div>
        <div class="tooltip" id="tooltip"></div>
      </div>
    </main>

    <script>
      const baseWidth = {base_width};
      const baseHeight = {base_height};
      const minRadius = {min_radius};
      const maxRadius = {max_radius};
      const theme = {{
        landFill: "{theme.land_fill}",
        landStroke: "{theme.land_stroke}",
        gridStroke: "{theme.grid_stroke}",
        bubbleFill: "{theme.bubble_fill}",
        bubbleStroke: "{theme.bubble_stroke}",
        bubbleFillHover: "{theme.bubble_fill_recent}",
        bubbleStrokeHover: "{theme.bubble_stroke_recent}",
        bubbleOpacity: {theme.bubble_opacity},
      }};

      const container = d3.select("#map-frame");
      const tooltip = d3.select("#tooltip");
      
      // State: zoom level and pan offset
      let zoomState = {{
        scale: 1,
        translateX: 0,
        translateY: 0,
        isDragging: false,
        dragStartX: 0,
        dragStartY: 0,
        dragStartTranslateX: 0,
        dragStartTranslateY: 0
      }};

      // Determine initial scale based on viewport width
      const viewportWidth = window.innerWidth || document.documentElement.clientWidth;
      if (viewportWidth < 800) {{
        zoomState.scale = 0.6;
      }} else if (viewportWidth < 1200) {{
        zoomState.scale = 0.8;
      }}

      let svg, worldData, visitData;

      // Load both world map data and visitor data
      Promise.all([
        d3.json("https://unpkg.com/world-atlas@2/countries-110m.json"),
        d3.json("https://unpkg.com/world-atlas@2/countries-50m.json"),
        d3.json("visitors-data.json")
      ]).then(([world110m, world50m, visitorData]) => {{
        worldData = {{ low: world110m, high: world50m }};
        visitData = visitorData;
        
        // Calculate total visitors
        const totalVisitors = visitData.reduce((sum, d) => sum + d.visitors, 0);
        d3.select("#total-visitors").text(totalVisitors.toLocaleString());
        
        render();
        setupZoomButtons();
        
        // Add legend after first render
        const legend = d3.select("#map-frame")
          .append("div")
          .attr("class", "legend");
        legend.append("div").attr("class", "legend-dot");
        legend.append("span").text("Visitor locations (circle size ≈ relative visitors)");
      }}).catch(error => {{
        console.error("Error loading data:", error);
        d3.select("#map-frame").append("div")
          .style("padding", "20px")
          .style("color", "#ff6b6b")
          .text("Error loading visitor data. Please ensure visitors-data.json is available.");
      }});

      function render() {{
        // Clear existing SVG
        container.selectAll("svg").remove();

        // ViewBox stays constant, but we scale the projection
        const width = baseWidth;
        const height = baseHeight;

        // Create SVG
        svg = container
          .insert("svg", ":first-child")
          .style("cursor", zoomState.isDragging ? "grabbing" : "grab")
          .attr("viewBox", `0 0 ${{width}} ${{height}}`);

        // Background
        svg.append("rect")
          .attr("x", 0)
          .attr("y", 0)
          .attr("width", width)
          .attr("height", height)
          .attr("fill", "{theme.background_color}");

        // Always use high resolution map (50m) for better detail
        const world = worldData.high;
        const countries = topojson.feature(world, world.objects.countries);

        // Scale and translate the projection
        const baseProjection = d3.geoNaturalEarth1()
          .fitSize([width, height], {{ type: "Sphere" }});
        
        const baseScale = baseProjection.scale();
        const baseTranslate = baseProjection.translate();
        
        const projection = d3.geoNaturalEarth1()
          .scale(baseScale * zoomState.scale)
          .translate([
            baseTranslate[0] - zoomState.translateX,
            baseTranslate[1] - zoomState.translateY
          ]);

        const path = d3.geoPath(projection);

        // Graticule
        const graticule = d3.geoGraticule();

        svg.append("path")
          .datum(graticule.outline())
          .attr("fill", "{theme.background_color}")
          .attr("stroke", "none")
          .attr("d", path);

        svg.append("g")
          .selectAll("path")
          .data(countries.features)
          .join("path")
          .attr("fill", theme.landFill)
          .attr("stroke", theme.landStroke)
          .attr("stroke-width", 0.5)
          .attr("stroke-opacity", 0.6)
          .attr("fill-opacity", 0.9)
          .attr("d", path);

        svg.append("path")
          .datum(graticule())
          .attr("fill", "none")
          .attr("stroke", theme.gridStroke)
          .attr("stroke-width", 0.35)
          .attr("opacity", 0.5)
          .attr("d", path);

        // Draw points with constant screen size
        drawPoints(projection, width, height);

        // Update visible visitor count
        updateVisibleCount(projection);

        // Set up drag behavior
        setupDrag();
      }}

      function updateVisibleCount(projection) {{
        // Calculate which points are visible in the current viewport
        let visibleVisitors = 0;
        
        visitData.forEach(d => {{
          const projected = projection([d.lon, d.lat]);
          if (!projected) return;
          
          const [x, y] = projected;
          
          // Check if the point is within the viewBox bounds
          if (x >= 0 && x <= baseWidth && y >= 0 && y <= baseHeight) {{
            visibleVisitors += d.visitors;
          }}
        }});
        
        d3.select("#visible-visitors").text(visibleVisitors.toLocaleString());
      }}

      function drawPoints(projection, width, height) {{
        if (!visitData || visitData.length === 0) return;

        const radii = visitData.map(d => d.normalized || 0);
        const maxNormalized = d3.max(radii) || 1;

        const radiusScale = d3.scaleLinear()
          .domain([0, maxNormalized])
          .range([minRadius, maxRadius]);

        // Draw larger points first so smaller points render on top
        const orderedData = [...visitData].sort((a, b) => (b.normalized || 0) - (a.normalized || 0));

        const circles = svg.append("g")
          .selectAll("circle")
          .data(orderedData)
          .join("circle")
          .attr("cx", d => projection([d.lon, d.lat])[0])
          .attr("cy", d => projection([d.lon, d.lat])[1])
          .attr("r", d => radiusScale(d.normalized || 0))
          .attr("fill", theme.bubbleFill)
          .attr("fill-opacity", theme.bubbleOpacity)
          .attr("stroke", theme.bubbleStroke)
          .attr("stroke-width", 1);

        circles
          .style("cursor", "default")
          .on("mouseover", function (event, d) {{
            d3.select(this)
              .attr("fill", theme.bubbleFillHover)
              .attr("stroke", theme.bubbleStrokeHover)
              .attr("stroke-width", 1.4);

            const city = d.city && d.city.trim();
            const country = d.country && d.country.trim();
            const title = city ? `${{city}}, ${{country || "Unknown"}}` : (country || "Unknown");

            // Get screen coordinates relative to the map-frame container
            const svgRect = svg.node().getBoundingClientRect();
            const containerRect = container.node().getBoundingClientRect();
            const x = event.clientX - containerRect.left;
            const y = event.clientY - containerRect.top;

            tooltip
              .style("left", x + "px")
              .style("top", y + "px")
              .style("opacity", 1)
              .html(`
                <strong>${{title}}</strong><br/>
                Visitors: ${{d.visitors.toLocaleString()}}<br/>
                Most recent: ${{formatLastVisit(d.lastVisit)}}
              `);
          }})
          .on("mousemove", function (event) {{
            // Get screen coordinates relative to the map-frame container
            const containerRect = container.node().getBoundingClientRect();
            const x = event.clientX - containerRect.left;
            const y = event.clientY - containerRect.top;
            
            tooltip
              .style("left", x + "px")
              .style("top", y + "px");
          }})
          .on("mouseout", function () {{
            d3.select(this)
              .attr("fill", theme.bubbleFill)
              .attr("stroke", theme.bubbleStroke)
              .attr("stroke-width", 1.0);

            tooltip.style("opacity", 0);
          }});
      }}

      function setupDrag() {{
        svg.on("mousedown", (event) => {{
          zoomState.isDragging = true;
          zoomState.dragStartX = event.clientX;
          zoomState.dragStartY = event.clientY;
          zoomState.dragStartTranslateX = zoomState.translateX;
          zoomState.dragStartTranslateY = zoomState.translateY;
          svg.style("cursor", "grabbing");
          event.preventDefault();
        }})
        .on("dblclick", (event) => {{
          // Double-click to zoom in centered on mouse position
          const svgRect = svg.node().getBoundingClientRect();
          
          // Get mouse position relative to SVG in screen coordinates
          const mouseX = event.clientX - svgRect.left;
          const mouseY = event.clientY - svgRect.top;
          
          // Convert to viewBox coordinates (where the mouse is in the viewport)
          const viewBoxX = (mouseX / svgRect.width) * baseWidth;
          const viewBoxY = (mouseY / svgRect.height) * baseHeight;
          
          // Calculate what point in the world this corresponds to
          // The projection translates by: baseTranslate - zoomState.translate
          // So a point at viewBoxX in the viewport corresponds to a world point that,
          // when projected, gives us viewBoxX
          // Since projection.translate = [baseWidth/2 - translateX, baseHeight/2 - translateY]
          // A point at viewBoxX corresponds to world coordinates that project to viewBoxX
          
          // Store the old scale
          const oldScale = zoomState.scale;
          
          // Calculate the center offset before zoom (where in the viewport is the click relative to center)
          const offsetX = viewBoxX - baseWidth / 2;
          const offsetY = viewBoxY - baseHeight / 2;
          
          // Zoom in
          zoomState.scale = Math.min(8, zoomState.scale * 1.4);
          const zoomRatio = zoomState.scale / oldScale;
          
          // Adjust translation to keep the clicked point under the cursor
          // The offset from center should scale with the zoom
          zoomState.translateX = zoomState.translateX * zoomRatio + offsetX * (zoomRatio - 1);
          zoomState.translateY = zoomState.translateY * zoomRatio + offsetY * (zoomRatio - 1);
          
          // Constrain panning
          const scaledMapWidth = baseWidth * zoomState.scale;
          const scaledMapHeight = baseHeight * zoomState.scale;
          const maxTranslateX = Math.max(0, (scaledMapWidth - baseWidth) / 2);
          const maxTranslateY = Math.max(0, (scaledMapHeight - baseHeight) / 2);
          zoomState.translateX = Math.max(-maxTranslateX, Math.min(maxTranslateX, zoomState.translateX));
          zoomState.translateY = Math.max(-maxTranslateY, Math.min(maxTranslateY, zoomState.translateY));
          
          render();
          event.preventDefault();
        }});

        d3.select(window)
          .on("mousemove", (event) => {{
            if (!zoomState.isDragging) return;
            
            const dx = event.clientX - zoomState.dragStartX;
            const dy = event.clientY - zoomState.dragStartY;
            
            // Convert screen pixels to viewBox coordinates
            const svgRect = svg.node().getBoundingClientRect();
            const viewBoxWidth = baseWidth;
            const viewBoxHeight = baseHeight;
            const scaleX = viewBoxWidth / svgRect.width;
            const scaleY = viewBoxHeight / svgRect.height;
            
            zoomState.translateX = zoomState.dragStartTranslateX - dx * scaleX;
            zoomState.translateY = zoomState.dragStartTranslateY - dy * scaleY;
            
            // Constrain panning based on the scaled map size
            // When zoomed in, the map is larger than the viewBox, so we can pan more
            // The map should never show empty space beyond its edges
            const scaledMapWidth = viewBoxWidth * zoomState.scale;
            const scaledMapHeight = viewBoxHeight * zoomState.scale;
            
            // Max translate is how far we can pan before hitting the edge
            // At scale=1, maxTranslate=0 (can't pan at all)
            // At scale=2, maxTranslate=viewBoxWidth/2 (can pan half the width in each direction)
            const maxTranslateX = Math.max(0, (scaledMapWidth - viewBoxWidth) / 2);
            const maxTranslateY = Math.max(0, (scaledMapHeight - viewBoxHeight) / 2);
            
            zoomState.translateX = Math.max(-maxTranslateX, Math.min(maxTranslateX, zoomState.translateX));
            zoomState.translateY = Math.max(-maxTranslateY, Math.min(maxTranslateY, zoomState.translateY));
            
            render();
          }})
          .on("mouseup", () => {{
            if (zoomState.isDragging) {{
              zoomState.isDragging = false;
              if (svg) svg.style("cursor", "grab");
            }}
          }});
      }}

      function setupZoomButtons() {{
        d3.select("#zoom-in").on("click", () => {{
          const oldScale = zoomState.scale;
          zoomState.scale = Math.min(8, zoomState.scale * 1.4);
          const zoomRatio = zoomState.scale / oldScale;
          
          // Scale the translation to keep the center point stable
          zoomState.translateX = zoomState.translateX * zoomRatio;
          zoomState.translateY = zoomState.translateY * zoomRatio;
          
          // Constrain panning after zoom
          const scaledMapWidth = baseWidth * zoomState.scale;
          const scaledMapHeight = baseHeight * zoomState.scale;
          const maxTranslateX = Math.max(0, (scaledMapWidth - baseWidth) / 2);
          const maxTranslateY = Math.max(0, (scaledMapHeight - baseHeight) / 2);
          zoomState.translateX = Math.max(-maxTranslateX, Math.min(maxTranslateX, zoomState.translateX));
          zoomState.translateY = Math.max(-maxTranslateY, Math.min(maxTranslateY, zoomState.translateY));
          
          render();
        }});

        d3.select("#zoom-out").on("click", () => {{
          const oldScale = zoomState.scale;
          zoomState.scale = Math.max(0.5, zoomState.scale / 1.4);
          const zoomRatio = zoomState.scale / oldScale;
          
          // Scale the translation to keep the center point stable
          zoomState.translateX = zoomState.translateX * zoomRatio;
          zoomState.translateY = zoomState.translateY * zoomRatio;
          
          // Constrain panning after zoom out - important to prevent being out of bounds
          const scaledMapWidth = baseWidth * zoomState.scale;
          const scaledMapHeight = baseHeight * zoomState.scale;
          const maxTranslateX = Math.max(0, (scaledMapWidth - baseWidth) / 2);
          const maxTranslateY = Math.max(0, (scaledMapHeight - baseHeight) / 2);
          zoomState.translateX = Math.max(-maxTranslateX, Math.min(maxTranslateX, zoomState.translateX));
          zoomState.translateY = Math.max(-maxTranslateY, Math.min(maxTranslateY, zoomState.translateY));
          
          render();
        }});
      }}

      function formatLastVisit(iso) {{
        if (!iso) return "unknown";
        const date = new Date(iso);
        if (isNaN(date.getTime())) return iso;

        const year = date.getFullYear();

        // Bucketization rules:
        // - Dates in 2025: show "Mon 2025" (e.g., "Jan 2025")
        // - Dates in 2024 (before 2025-01-01): show "2024"
        // - Dates in 2023 or earlier (before 2024-01-01): show "2023"
        if (year >= 2025) {{
          return date.toLocaleString(undefined, {{
            year: "numeric",
            month: "short",
          }});
        }} else if (year === 2024) {{
          return "2024";
        }} else {{
          return "2023";
        }}
      }}
    </script>
  </body>
</html>
"""


