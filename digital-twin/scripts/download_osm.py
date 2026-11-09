"""
download_osm.py  —  STEP 1
Downloads REAL OpenStreetMap data for Lonavala & Khandala via OSMnx / Overpass API.
- Saves raw GeoJSON to data/raw/
- Writes metadata.json recording the actual data source (osmnx / manual)
- If download fails, the script exits with a non-zero code and prints the error.
  It does NOT silently fall back to hand-made geometry.

Coordinate order: ALWAYS [longitude, latitude] in EPSG:4326.
Bounding box (tightened to Lonavala–Khandala cluster):
  min_lon=73.35, min_lat=18.72, max_lon=73.46, max_lat=18.80
"""

import sys
import json
import datetime
import logging
from pathlib import Path

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger("download_osm")

BASE_DIR = Path(__file__).resolve().parent.parent
RAW_DIR  = BASE_DIR / "data" / "raw"
RAW_DIR.mkdir(parents=True, exist_ok=True)

# Tightened bbox around Lonavala town + Khandala + main lakes (excludes far-south Khopoli)
BBOX = {
    "min_lon": 73.35,
    "min_lat": 18.72,
    "max_lon": 73.46,
    "max_lat": 18.80,
}
# OSMnx 2.x convention: bbox = (left, bottom, right, top) = (min_lon, min_lat, max_lon, max_lat)
OSMNX_BBOX = (BBOX["min_lon"], BBOX["min_lat"], BBOX["max_lon"], BBOX["max_lat"])


def _serialize_cols(gdf):
    """Convert dict/list columns to strings so GeoJSON serialiser is happy."""
    for col in gdf.columns:
        if col == "geometry":
            continue
        sample = gdf[col].dropna()
        if len(sample) and isinstance(sample.iloc[0], (dict, list)):
            gdf = gdf.copy()
            gdf[col] = gdf[col].astype(str)
    return gdf


def download_water(ox):
    """natural=water + waterway lines (river/stream/canal) + landuse=reservoir."""
    logger.info("Downloading water features (natural=water, waterway, landuse=reservoir)…")
    tags = {
        "natural": "water",
        "waterway": ["river", "stream", "canal"],
        "landuse": "reservoir",
    }
    gdf = ox.features_from_bbox(bbox=OSMNX_BBOX, tags=tags)
    logger.info(f"  → {len(gdf)} raw water features downloaded from Overpass")
    return gdf


def download_roads(ox):
    """motorway / trunk / primary / secondary roads only (kept small)."""
    logger.info("Downloading major road network (motorway|trunk|primary|secondary)…")
    # Build filter string in Python to avoid shell quoting issues
    road_filter = '["highway"~"motorway|trunk|primary|secondary"]'
    G = ox.graph_from_bbox(
        bbox=OSMNX_BBOX,
        network_type="drive",
        custom_filter=road_filter,
    )
    gdf = ox.graph_to_gdfs(G, nodes=False)
    logger.info(f"  → {len(gdf)} raw road edges downloaded from Overpass")
    return gdf


def download_landuse(ox):
    """landuse and place polygons for demand-zone context."""
    logger.info("Downloading landuse / place features…")
    tags = {
        "landuse": ["residential", "commercial", "industrial", "retail"],
        "place":   ["town", "suburb", "neighbourhood", "village"],
    }
    gdf = ox.features_from_bbox(bbox=OSMNX_BBOX, tags=tags)
    logger.info(f"  → {len(gdf)} raw landuse/place features downloaded from Overpass")
    return gdf


def save_geojson(gdf, path: Path):
    gdf = _serialize_cols(gdf)
    if gdf.crs is None or str(gdf.crs).upper() != "EPSG:4326":
        gdf = gdf.to_crs("EPSG:4326")
    gdf.to_file(path, driver="GeoJSON")
    logger.info(f"  Saved → {path.name}  ({path.stat().st_size / 1024:.1f} KB, {len(gdf)} features)")


def main():
    logger.info("=== STEP 1: Real OSM download for Lonavala Digital Twin ===")

    try:
        import osmnx as ox
    except ImportError:
        logger.error("OSMnx is not installed. Run: pip install osmnx")
        sys.exit(1)

    # Configure
    ox.settings.requests_timeout = 90
    ox.settings.use_cache = True
    ox.settings.log_console = False

    errors = {}

    # --- Water ---
    try:
        water_gdf = download_water(ox)
    except Exception as e:
        logger.error(f"Water download FAILED: {e}")
        errors["water"] = str(e)
        water_gdf = None

    # --- Roads ---
    try:
        roads_gdf = download_roads(ox)
    except Exception as e:
        logger.error(f"Roads download FAILED: {e}")
        errors["roads"] = str(e)
        roads_gdf = None

    # --- Landuse ---
    try:
        landuse_gdf = download_landuse(ox)
    except Exception as e:
        logger.warning(f"Landuse download failed (non-critical): {e}")
        landuse_gdf = None

    # Hard-stop if critical layers failed
    if errors:
        logger.error("=" * 60)
        logger.error("DOWNLOAD FAILED — not saving fallback geometry.")
        for layer, msg in errors.items():
            logger.error(f"  {layer}: {msg}")
        logger.error("Check your network / Overpass API availability and retry.")
        sys.exit(1)

    # --- Save ---
    save_geojson(water_gdf,   RAW_DIR / "raw_water.geojson")
    save_geojson(roads_gdf,   RAW_DIR / "raw_roads.geojson")
    if landuse_gdf is not None:
        save_geojson(landuse_gdf, RAW_DIR / "raw_landuse.geojson")

    # --- Metadata ---
    meta = {
        "testbed": "Lonavala & Khandala, Maharashtra, India",
        "downloaded_at": datetime.datetime.utcnow().isoformat() + "Z",
        "data_source": "osmnx_overpass",   # <-- real OSM, not synthetic
        "overpass_endpoint": ox.settings.overpass_endpoint,
        "osmnx_version": ox.__version__,
        "bbox": BBOX,
        "crs": "EPSG:4326",
        "attribution": "© OpenStreetMap contributors (ODbL 1.0)",
        "water_count": int(len(water_gdf)),
        "roads_count": int(len(roads_gdf)),
        "landuse_count": int(len(landuse_gdf)) if landuse_gdf is not None else 0,
    }
    with open(RAW_DIR / "metadata.json", "w", encoding="utf-8") as f:
        json.dump(meta, f, indent=2)
    logger.info("Metadata written to data/raw/metadata.json")
    logger.info("Step 1 finished — real OSM data saved.")


if __name__ == "__main__":
    main()
