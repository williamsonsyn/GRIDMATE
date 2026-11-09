"""
process_data.py
Cleans, simplifies, reprojects, and filters raw OpenStreetMap GIS data for Lonavala Digital Twin:
- Clips water, roads, and power lines to context_bbox [73.25, 18.62, 73.62, 18.92]
- Produces digital-twin/data/water_features.geojson
- Produces digital-twin/data/roads.geojson
- Produces digital-twin/data/power_lines.geojson
- Produces digital-twin/data/raw/metadata.json

Source: Real OpenStreetMap exports (overpass-turbo, GeoJSON).
Coordinates are strictly EPSG:4326 [longitude, latitude].
"""

import json
import logging
from datetime import date
from pathlib import Path

import geopandas as gpd
from shapely.geometry import box
from shapely.validation import make_valid

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger("process_data")

BASE_DIR = Path(__file__).resolve().parent.parent
RAW_DIR = BASE_DIR / "data" / "raw"
DATA_DIR = BASE_DIR / "data"
DATA_DIR.mkdir(parents=True, exist_ok=True)

# Context bounding box for regional GIS layers (water, roads, power lines)
CONTEXT_BBOX = [73.25, 18.60, 73.68, 18.97]  # [min_lon, min_lat, max_lon, max_lat]
# Asset bounding box covering energy assets, demand zones, and wind ridge
ASSET_BBOX = [73.33, 18.66, 73.66, 18.95]


def process_water():
    """Processes water features: keep polygons (drop tiny ponds < 2000 m2, keep named waterbodies
    including Valvan, Bhushi, Tungarli, Khandala, Pavana, Tata, Shirota) and major rivers/canals/streams
    as lines (>= 500m or named), clip to context_bbox, reproject to EPSG:4326, fix invalid geometries,
    and simplify lightly (~0.0001 deg).
    """
    raw_path = RAW_DIR / "raw_water.geojson"
    if not raw_path.exists():
        raise FileNotFoundError(f"Missing raw water data at {raw_path}")

    gdf = gpd.read_file(raw_path)
    logger.info(f"Loaded {len(gdf)} raw water features from {raw_path.name}.")

    if gdf.crs != "EPSG:4326":
        gdf = gdf.to_crs("EPSG:4326")

    gdf = gdf[~gdf.geometry.is_empty & gdf.geometry.notna()].copy()
    gdf["geometry"] = gdf["geometry"].apply(lambda g: make_valid(g) if not g.is_valid else g)

    # Calculate area and length in metric projection (UTM 43N)
    gdf_utm = gdf.to_crs("EPSG:32643")
    gdf["area_m2"] = gdf_utm.geometry.area
    gdf["length_m"] = gdf_utm.geometry.length

    # 1. Filter polygons: keep >= 2000 m2 or named water bodies
    polys = gdf[gdf.geometry.geom_type.isin(["Polygon", "MultiPolygon"])].copy()
    polys_kept = polys[(polys["area_m2"] >= 2000.0) | (polys["name"].notna())].copy()

    # 2. Filter lines: keep major rivers/streams/dams/canals (>= 500m or named)
    lines = gdf[gdf.geometry.geom_type.isin(["LineString", "MultiLineString"])].copy()
    lines_kept = lines[
        (lines["waterway"].isin(["river", "stream", "dam", "canal"]))
        & ((lines["length_m"] >= 500.0) | (lines["name"].notna()))
    ].copy()

    combined = gpd.pd.concat([polys_kept, lines_kept], ignore_index=True)

    # Clip to context bounding box
    clipped = gpd.clip(combined, CONTEXT_BBOX)
    clipped = clipped[~clipped.geometry.is_empty & clipped.geometry.notna()].copy()
    clipped["geometry"] = clipped["geometry"].apply(lambda g: make_valid(g) if not g.is_valid else g)
    clipped["geometry"] = clipped["geometry"].simplify(tolerance=0.0001, preserve_topology=True)

    records = []
    for idx, row in clipped.reset_index(drop=True).iterrows():
        raw_name = row.get("name")
        if raw_name is not None and str(raw_name) != "nan" and len(str(raw_name).strip()) > 0:
            name = str(raw_name).strip()
            # Standardize spelling of Bhushi
            if "bushi" in name.lower() and "bhushi" not in name.lower():
                name = name.replace("Bushi", "Bhushi").replace("bushi", "bhushi")
            # Clean double spaces
            name = " ".join(name.split())
        else:
            wtype = row.get("water") or row.get("waterway") or row.get("natural") or "water"
            name = f"Water Body {idx+1}"

        water_type = (
            row.get("water")
            or row.get("waterway")
            or row.get("natural")
            or "water"
        )
        water_id = f"water_{idx+1:03d}"

        records.append({
            "id": water_id,
            "name": str(name),
            "type": str(water_type),
            "source": "OpenStreetMap",
            "is_synthetic": False,
            "geometry": row.geometry
        })

    clean_gdf = gpd.GeoDataFrame(records, crs="EPSG:4326")
    out_path = DATA_DIR / "water_features.geojson"
    clean_gdf.to_file(out_path, driver="GeoJSON")
    file_size_mb = out_path.stat().st_size / (1024 * 1024)
    logger.info(f"Processed water features: {len(clean_gdf)} items -> {out_path} ({file_size_mb:.2f} MB)")
    return clean_gdf


def process_roads():
    """Processes road features: keep motorway, trunk, primary, and secondary (and links),
    clip to context_bbox, reproject to EPSG:4326, fix invalid geometries, simplify lightly (~0.0001 deg).
    """
    raw_path = RAW_DIR / "raw_roads.geojson"
    if not raw_path.exists():
        raise FileNotFoundError(f"Missing raw roads data at {raw_path}")

    gdf = gpd.read_file(raw_path)
    logger.info(f"Loaded {len(gdf)} raw road features from {raw_path.name}.")

    if gdf.crs != "EPSG:4326":
        gdf = gdf.to_crs("EPSG:4326")

    gdf = gdf[~gdf.geometry.is_empty & gdf.geometry.notna()].copy()
    gdf["geometry"] = gdf["geometry"].apply(lambda g: make_valid(g) if not g.is_valid else g)

    # Filter to motorway, trunk, primary, secondary (plus motorway_link and trunk_link)
    allowed_highways = ["motorway", "trunk", "primary", "secondary", "motorway_link", "trunk_link"]
    roads_filtered = gdf[gdf["highway"].isin(allowed_highways)].copy()

    # Clip to context bounding box
    clipped = gpd.clip(roads_filtered, CONTEXT_BBOX)
    clipped = clipped[~clipped.geometry.is_empty & clipped.geometry.notna()].copy()
    clipped["geometry"] = clipped["geometry"].apply(lambda g: make_valid(g) if not g.is_valid else g)
    clipped["geometry"] = clipped["geometry"].simplify(tolerance=0.0001, preserve_topology=True)

    records = []
    for idx, row in clipped.reset_index(drop=True).iterrows():
        raw_name = row.get("name")
        highway = str(row.get("highway") or "road")
        if raw_name is not None and str(raw_name) != "nan" and len(str(raw_name).strip()) > 0:
            name = str(raw_name).strip()
            if "bushi" in name.lower() and "bhushi" not in name.lower():
                name = name.replace("Bushi", "Bhushi").replace("bushi", "bhushi")
        else:
            name = f"Road Segment {idx+1}"

        road_id = f"road_{idx+1:03d}"
        records.append({
            "id": road_id,
            "name": str(name),
            "type": highway,
            "highway_type": highway,
            "source": "OpenStreetMap",
            "is_synthetic": False,
            "geometry": row.geometry
        })

    clean_gdf = gpd.GeoDataFrame(records, crs="EPSG:4326")
    out_path = DATA_DIR / "roads.geojson"
    clean_gdf.to_file(out_path, driver="GeoJSON")
    file_size_mb = out_path.stat().st_size / (1024 * 1024)
    logger.info(f"Processed roads: {len(clean_gdf)} items -> {out_path} ({file_size_mb:.2f} MB)")
    return clean_gdf


def process_power_lines():
    """Processes real power transmission lines from raw_power.geojson:
    Clips to context_bbox, simplifies lightly, and outputs digital-twin/data/power_lines.geojson (< 1 MB).
    """
    raw_path = RAW_DIR / "raw_power.geojson"
    if not raw_path.exists():
        logger.warning(f"Raw power file not found at {raw_path}")
        return gpd.GeoDataFrame([], crs="EPSG:4326")

    gdf = gpd.read_file(raw_path)
    logger.info(f"Loaded {len(gdf)} raw power features from {raw_path.name}.")

    if gdf.crs != "EPSG:4326":
        gdf = gdf.to_crs("EPSG:4326")

    # Filter to power lines/cables
    lines_gdf = gdf[
        gdf.geometry.geom_type.isin(["LineString", "MultiLineString"])
        & gdf["power"].isin(["line", "minor_line", "cable"])
    ].copy()

    # Clip to context bounding box
    clipped = gpd.clip(lines_gdf, CONTEXT_BBOX)
    clipped = clipped[~clipped.geometry.is_empty & clipped.geometry.notna()].copy()
    clipped["geometry"] = clipped["geometry"].apply(lambda g: make_valid(g) if not g.is_valid else g)
    clipped["geometry"] = clipped["geometry"].simplify(tolerance=0.0001, preserve_topology=True)

    records = []
    for idx, row in clipped.reset_index(drop=True).iterrows():
        raw_name = row.get("name")
        name = str(raw_name).strip() if (raw_name and str(raw_name) != "nan") else f"Transmission Line {idx+1}"
        voltage = str(row.get("voltage") or "110000")
        cables = str(row.get("cables") or "3")

        records.append({
            "id": f"power_line_{idx+1:03d}",
            "name": name,
            "type": "transmission_line",
            "voltage": voltage,
            "cables": cables,
            "source": "OpenStreetMap",
            "is_synthetic": False,
            "geometry": row.geometry
        })

    clean_gdf = gpd.GeoDataFrame(records, crs="EPSG:4326")
    out_path = DATA_DIR / "power_lines.geojson"
    clean_gdf.to_file(out_path, driver="GeoJSON")
    file_size_kb = out_path.stat().st_size / 1024
    logger.info(f"Processed power lines: {len(clean_gdf)} items -> {out_path} ({file_size_kb:.1f} KB)")
    return clean_gdf


def write_metadata(water_gdf, roads_gdf, power_gdf):
    """Writes data/raw/metadata.json documenting sources, counts, and bboxes."""
    raw_water_path = RAW_DIR / "raw_water.geojson"
    raw_roads_path = RAW_DIR / "raw_roads.geojson"
    raw_landuse_path = RAW_DIR / "raw_landuse.geojson"
    raw_wind_path = RAW_DIR / "raw_wind.geojson"
    raw_power_path = RAW_DIR / "raw_power.geojson"
    raw_hydro_path = RAW_DIR / "raw_hydro.geojson"
    raw_dams_path = RAW_DIR / "raw_dams.geojson"
    raw_solar_path = RAW_DIR / "raw_solar.geojson"

    raw_water_count = len(gpd.read_file(raw_water_path)) if raw_water_path.exists() else 0
    raw_roads_count = len(gpd.read_file(raw_roads_path)) if raw_roads_path.exists() else 0
    raw_landuse_count = len(gpd.read_file(raw_landuse_path)) if raw_landuse_path.exists() else 0
    raw_wind_count = len(gpd.read_file(raw_wind_path)) if raw_wind_path.exists() else 0
    raw_power_count = len(gpd.read_file(raw_power_path)) if raw_power_path.exists() else 0
    raw_hydro_count = len(gpd.read_file(raw_hydro_path)) if raw_hydro_path.exists() else 0
    raw_dams_count = len(gpd.read_file(raw_dams_path)) if raw_dams_path.exists() else 0
    raw_solar_count = len(gpd.read_file(raw_solar_path)) if raw_solar_path.exists() else 0

    metadata = {
        "testbed": "Lonavala & Khandala Regional Context, Maharashtra, India",
        "data_source": "manual overpass-turbo export, OSM ODbL",
        "attribution": "© OpenStreetMap contributors (ODbL 1.0)",
        "date_exported": date.today().isoformat(),
        "crs": "EPSG:4326",
        "context_bbox": {
            "min_lon": CONTEXT_BBOX[0],
            "min_lat": CONTEXT_BBOX[1],
            "max_lon": CONTEXT_BBOX[2],
            "max_lat": CONTEXT_BBOX[3]
        },
        "asset_bbox": {
            "min_lon": ASSET_BBOX[0],
            "min_lat": ASSET_BBOX[1],
            "max_lon": ASSET_BBOX[2],
            "max_lat": ASSET_BBOX[3]
        },
        "provenance": {
            "real_osm_assets": [
                "hydro (3 plants from raw_hydro.geojson: Khopoli, Bhivpuri, Pawana)",
                "solar (3 sites from raw_solar.geojson: Campole Valley, Rajmachi Foothills, Urse)",
                "wind (4 clusters from 28 turbines in raw_wind.geojson)"
            ],
            "approximate_osm_assets": [
                "grid intertie (adjacent to real OSM substation)",
                "battery storage (adjacent to substation intertie)"
            ],
            "synthetic_assets": [
                "central demand hub (sited in municipal core)",
                "demand zone load distribution (geometries from real OSM landuse)"
            ]
        },
        "raw_counts": {
            "raw_water": raw_water_count,
            "raw_roads": raw_roads_count,
            "raw_landuse": raw_landuse_count,
            "raw_wind": raw_wind_count,
            "raw_power": raw_power_count,
            "raw_hydro": raw_hydro_count,
            "raw_dams": raw_dams_count,
            "raw_solar": raw_solar_count
        },
        "processed_counts": {
            "water_features": len(water_gdf),
            "roads": len(roads_gdf),
            "power_lines": len(power_gdf)
        }
    }

    out_path = RAW_DIR / "metadata.json"
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(metadata, f, indent=2)
    logger.info(f"Updated metadata saved to {out_path}")


def main():
    logger.info("=== Process & Clean Real OSM GIS Data for Context BBox ===")
    water_gdf = process_water()
    roads_gdf = process_roads()
    power_gdf = process_power_lines()
    write_metadata(water_gdf, roads_gdf, power_gdf)
    logger.info("process_data completed successfully.")


if __name__ == "__main__":
    main()
