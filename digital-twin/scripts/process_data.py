"""
process_data.py
Cleans, simplifies, reprojects, and filters raw OpenStreetMap GIS data for Lonavala:
- Produces digital-twin/data/water_features.geojson
- Produces digital-twin/data/roads.geojson
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

LONAVALA_BBOX = [73.33, 18.68, 73.48, 18.81]  # [min_lon, min_lat, max_lon, max_lat]
BBOX_POLYGON = box(*LONAVALA_BBOX)


def process_water():
    """Processes water features: keep polygons (drop tiny ponds < 2000 m2, keep named waterbodies)

    and major rivers/streams as lines, clip to bbox, reproject to EPSG:4326, fix invalid geometries,
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

    # Clip cleanly to bounding box
    clipped = gpd.clip(combined, LONAVALA_BBOX)
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
            name = f"Lonavala {str(wtype).capitalize()} {idx+1}"

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

    clip to bbox, reproject to EPSG:4326, fix invalid geometries, simplify lightly (~0.0001 deg).
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

    # Clip to bounding box
    clipped = gpd.clip(roads_filtered, LONAVALA_BBOX)
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
            name = f"Lonavala {highway.capitalize()} Segment {idx+1}"

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


def write_metadata(water_gdf, roads_gdf):
    """Writes data/raw/metadata.json documenting sources, counts, and bbox."""
    raw_water_path = RAW_DIR / "raw_water.geojson"
    raw_roads_path = RAW_DIR / "raw_roads.geojson"
    raw_landuse_path = RAW_DIR / "raw_landuse.geojson"

    raw_water_count = len(gpd.read_file(raw_water_path)) if raw_water_path.exists() else 0
    raw_roads_count = len(gpd.read_file(raw_roads_path)) if raw_roads_path.exists() else 0
    raw_landuse_count = len(gpd.read_file(raw_landuse_path)) if raw_landuse_path.exists() else 0

    metadata = {
        "testbed": "Lonavala & Khandala, Maharashtra, India",
        "data_source": "manual overpass-turbo export, OSM ODbL",
        "attribution": "© OpenStreetMap contributors (ODbL 1.0)",
        "date_exported": date.today().isoformat(),
        "crs": "EPSG:4326",
        "bbox": {
            "min_lon": LONAVALA_BBOX[0],
            "min_lat": LONAVALA_BBOX[1],
            "max_lon": LONAVALA_BBOX[2],
            "max_lat": LONAVALA_BBOX[3]
        },
        "raw_counts": {
            "raw_water": raw_water_count,
            "raw_roads": raw_roads_count,
            "raw_landuse": raw_landuse_count
        },
        "processed_counts": {
            "water_features": len(water_gdf),
            "roads": len(roads_gdf)
        }
    }

    out_path = RAW_DIR / "metadata.json"
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(metadata, f, indent=2)
    logger.info(f"Updated metadata saved to {out_path}")


def main():
    logger.info("=== STEP 2: Process & Clean Real OSM GIS Data ===")
    water_gdf = process_water()
    roads_gdf = process_roads()
    write_metadata(water_gdf, roads_gdf)
    logger.info("Step 2 completed successfully.")


if __name__ == "__main__":
    main()
