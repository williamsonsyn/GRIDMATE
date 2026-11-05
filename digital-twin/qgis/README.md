# QGIS Project & Styling Guide — Lonavala Digital Twin

This directory provides GIS integration instructions and styling references for QGIS 3.x.

## Included Layers

All vector layers are formatted in standard **GeoJSON (EPSG:4326)** and can be dragged directly into QGIS:

1. `../data/water_features.geojson`:
   - Natural water bodies, reservoirs (Valvan Lake, Bushi Dam, Tungarli Lake), and headwater streams.
   - Recommended style: Fill color `#38bdf8` (opacity 50%), outline `#0284c7` (width 0.4mm).
2. `../data/roads.geojson`:
   - Major transportation corridors (Mumbai-Pune Expressway, NH48 Old Highway, Khandala link).
   - Categorized symbology on `highway_type`:
     - `motorway`: `#f97316` (width 0.8mm)
     - `primary`: `#fbbf24` (width 0.6mm)
     - `secondary`: `#94a3b8` (width 0.4mm)
3. `../data/demand_zones.geojson`:
   - Zonal polygons for town residential, Khandala tourism, Valvan industrial, and Bushi recreation.
   - Categorized on `zone_type`:
     - `residential`: `#60a5fa`
     - `commercial`: `#a78bfa`
     - `industrial`: `#f472b6`
4. `../data/assets.geojson`:
   - Point features representing renewable generators, battery BESS, grid substation, and central demand hub.
   - Categorized symbology on `type`:
     - `solar`: `#f59e0b` (Circle, 3.5mm)
     - `wind`: `#06b6d4` (Circle, 3.5mm)
     - `hydro`: `#3b82f6` (Circle, 3.5mm)
     - `battery`: `#10b981` (Circle, 3.5mm)
     - `grid`: `#ef4444` (Square, 3.5mm)
     - `demand`: `#8b5cf6` (Diamond, 4.0mm)
5. `../data/energy_flow_template.geojson`:
   - Power line topology connecting generators to the central demand hub.

## Basemap

In QGIS Browser panel -> XYZ Tiles -> Add OpenStreetMap:
`https://tile.openstreetmap.org/{z}/{x}/{y}.png`

