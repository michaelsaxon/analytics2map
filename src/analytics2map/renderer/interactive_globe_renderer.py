from __future__ import annotations

import json
import math
from datetime import datetime
from pathlib import Path
from typing import Dict, Iterable, Tuple

from ..config import RendererConfig
from ..geo_lookup import GeoNamesLookup
from ..schemas import Location, RenderScale


class InteractiveGlobeRenderer:
    """Render a rotating 3D globe using D3.js."""

    def __init__(self, config: RendererConfig):
        self.config = config
        self.lookup = GeoNamesLookup()

    def render(
        self,
        aggregates: Dict[str, Tuple[Location, int, datetime | None]],
        output_path: Path | None = None,
    ) -> Path:
        """Write static HTML for the rotating globe (uses same JSON data).

        Args:
            aggregates: mapping of key -> (Location, total_visits, last_timestamp)
            output_path: optional explicit output path. Defaults to
                `<output_dir>/visitors-globe.html`.
        """
        output_dir = self.config.output_dir
        output_dir.mkdir(parents=True, exist_ok=True)
        if output_path is None:
            output_path = output_dir / "visitors-globe.html"

        # Use the same data file as the interactive map
        # (assuming it's already been generated)
        
        html = self._build_html()
        output_path.write_text(html, encoding="utf-8")
        return output_path

    def _build_html(self) -> str:
        """Generate the static HTML page for the rotating globe."""
        theme = self.config.theme
        
        # Use a square canvas for the globe
        size = 800
        min_radius = 3
        max_radius = 12

        return f"""<!DOCTYPE html>
<html lang="en">
  <head>
    <meta charset="utf-8" />
    <title>analytics2map – Rotating Globe</title>
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
        text-align: center;
      }}
      p {{
        margin: 8px auto 24px;
        max-width: 720px;
        font-size: 15px;
        line-height: 1.6;
        color: #c4c3d0;
        text-align: center;
      }}
      .globe-container {{
        max-width: {size}px;
        margin: 0 auto;
        position: relative;
      }}
      .globe-frame {{
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
      <h1>Rotating Globe Visualization</h1>
      <p>
        A 3D globe showing visitor locations. The globe rotates automatically,
        and the visible visitor count updates as different regions come into view.
      </p>
      <div class="globe-container">
        <div class="globe-frame" id="globe-frame">
          <div class="visitor-stats">
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
      </div>
    </main>

    <script>
      const size = {size};
      const minRadius = {min_radius};
      const maxRadius = {max_radius};
      const theme = {{
        landFill: "{theme.land_fill}",
        landStroke: "{theme.land_stroke}",
        waterFill: "{theme.background_color}",
        bubbleFill: "{theme.bubble_fill}",
        bubbleStroke: "{theme.bubble_stroke}",
        bubbleFillHover: "{theme.bubble_fill_recent}",
        bubbleStrokeHover: "{theme.bubble_stroke_recent}",
        bubbleOpacity: {theme.bubble_opacity},
      }};

      const container = d3.select("#globe-frame");
      const tooltip = d3.select("#tooltip");
      
      let svg, projection, path, visitData, worldData;
      let rotation = 0;
      const rotationSpeed = 0.3; // degrees per frame

      // Load data
      Promise.all([
        d3.json("https://unpkg.com/world-atlas@2/countries-50m.json"),
        d3.json("visitors-data.json")
      ]).then(([world, visitorData]) => {{
        worldData = topojson.feature(world, world.objects.countries);
        visitData = visitorData;
        
        // Calculate total visitors
        const totalVisitors = visitData.reduce((sum, d) => sum + d.visitors, 0);
        d3.select("#total-visitors").text(totalVisitors.toLocaleString());
        
        initGlobe();
        animate();
      }}).catch(error => {{
        console.error("Error loading data:", error);
        container.append("div")
          .style("padding", "20px")
          .style("color", "#ff6b6b")
          .text("Error loading data. Please ensure visitors-data.json is available.");
      }});

      function initGlobe() {{
        // Create SVG
        svg = container
          .append("svg")
          .attr("viewBox", `0 0 ${{size}} ${{size}}`);

        // Orthographic projection for globe
        projection = d3.geoOrthographic()
          .scale(size / 2.2)
          .translate([size / 2, size / 2])
          .clipAngle(90);

        path = d3.geoPath(projection);

        // Draw sphere (ocean)
        svg.append("path")
          .datum({{type: "Sphere"}})
          .attr("class", "sphere")
          .attr("d", path)
          .attr("fill", theme.waterFill)
          .attr("stroke", "rgba(148, 163, 184, 0.3)")
          .attr("stroke-width", 1.5);

        // Land
        svg.append("g")
          .attr("class", "land")
          .selectAll("path")
          .data(worldData.features)
          .join("path")
          .attr("d", path)
          .attr("fill", theme.landFill)
          .attr("stroke", theme.landStroke)
          .attr("stroke-width", 0.5)
          .attr("stroke-opacity", 0.6)
          .attr("fill-opacity", 0.9);

        // Points group
        svg.append("g").attr("class", "points");
      }}

      function animate() {{
        rotation += rotationSpeed;
        projection.rotate([rotation, -20, 0]);

        // Update land
        svg.select(".land")
          .selectAll("path")
          .attr("d", path);

        // Update points
        drawPoints();
        updateVisibleCount();

        requestAnimationFrame(animate);
      }}

      function drawPoints() {{
        if (!visitData || visitData.length === 0) return;

        const radii = visitData.map(d => d.normalized || 0);
        const maxNormalized = d3.max(radii) || 1;

        const radiusScale = d3.scaleLinear()
          .domain([0, maxNormalized])
          .range([minRadius, maxRadius]);

        // Sort by size (largest first) so smaller dots render on top
        const orderedData = [...visitData].sort((a, b) => (b.normalized || 0) - (a.normalized || 0));

        const circles = svg.select(".points")
          .selectAll("circle")
          .data(orderedData, d => `${{d.lat}},${{d.lon}}`);

        circles.exit().remove();

        const enter = circles.enter()
          .append("circle")
          .attr("fill", theme.bubbleFill)
          .attr("fill-opacity", theme.bubbleOpacity)
          .attr("stroke", theme.bubbleStroke)
          .attr("stroke-width", 1)
          .style("cursor", "default");

        circles.merge(enter)
          .attr("cx", d => {{
            const proj = projection([d.lon, d.lat]);
            return proj ? proj[0] : -999;
          }})
          .attr("cy", d => {{
            const proj = projection([d.lon, d.lat]);
            return proj ? proj[1] : -999;
          }})
          .attr("r", d => radiusScale(d.normalized || 0))
          .style("display", d => {{
            const proj = projection([d.lon, d.lat]);
            // Hide points on the back of the globe
            if (!proj) return "none";
            const distance = d3.geoDistance([d.lon, d.lat], projection.invert([size / 2, size / 2]));
            return distance > Math.PI / 2 ? "none" : null;
          }})
          .on("mouseover", function(event, d) {{
            d3.select(this)
              .attr("fill", theme.bubbleFillHover)
              .attr("stroke", theme.bubbleStrokeHover)
              .attr("stroke-width", 1.4);

            const city = d.city && d.city.trim();
            const country = d.country && d.country.trim();
            const title = city ? `${{city}}, ${{country || "Unknown"}}` : (country || "Unknown");

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
          .on("mousemove", function(event) {{
            const containerRect = container.node().getBoundingClientRect();
            const x = event.clientX - containerRect.left;
            const y = event.clientY - containerRect.top;
            
            tooltip
              .style("left", x + "px")
              .style("top", y + "px");
          }})
          .on("mouseout", function() {{
            d3.select(this)
              .attr("fill", theme.bubbleFill)
              .attr("stroke", theme.bubbleStroke)
              .attr("stroke-width", 1.0);

            tooltip.style("opacity", 0);
          }});
      }}

      function updateVisibleCount() {{
        let visibleVisitors = 0;
        
        visitData.forEach(d => {{
          const proj = projection([d.lon, d.lat]);
          if (!proj) return;
          
          // Check if point is on the visible hemisphere
          const distance = d3.geoDistance([d.lon, d.lat], projection.invert([size / 2, size / 2]));
          if (distance <= Math.PI / 2) {{
            visibleVisitors += d.visitors;
          }}
        }});
        
        d3.select("#visible-visitors").text(visibleVisitors.toLocaleString());
      }}

      function formatLastVisit(iso) {{
        if (!iso) return "unknown";
        const date = new Date(iso);
        if (isNaN(date.getTime())) return iso;

        const year = date.getFullYear();

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



