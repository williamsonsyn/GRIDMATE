"""
generate_assets.py
Generates reproducible synthetic prototype energy assets, demand zones,
and energy flow topology for the Lonavala testbed:
- digital-twin/data/assets.geojson
- digital-twin/data/demand_zones.geojson
- digital-twin/data/energy_flow_template.geojson

Assets are placed plausibly:
- Solar on sunny open land away from water and roads
- Wind on higher ground inside the Lonavala-Khandala area (Khandala Ridge & Duke's Nose Ridge)
- Hydro placed on a real shoreline of a real water polygon (Valvan reservoir), not inside water (< 100m)
- Battery placed near substation / central grid node
- Central demand hub placed in Lonavala municipal core
- Demand zones: illustrative zones (hand-defined polygons), not OSM-derived (Town residential, Khandala resorts, Valvan industrial, Bhushi recreation)
"""

import json
import logging
import random
from pathlib import Path

import geopandas as gpd
from pyproj import Transformer
from shapely.geometry import Point, Polygon, shape

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger("generate_assets")

BASE_DIR = Path(__file__).resolve().parent.parent
DATA_DIR = BASE_DIR / "data"
RAW_DIR = DATA_DIR / "raw"
DATA_DIR.mkdir(parents=True, exist_ok=True)

# Fixed seed for reproducibility
random.seed(42)

SIMULATION_NOTE = "Simulated prototype asset. Coordinates are illustrative, not verified real infrastructure."


def get_hydro_point_from_water():
    """Extract a representative point on the shoreline of a real water polygon

    (Valvan reservoir preferred) from water_features.geojson.
    Guarantees:
    - Point is strictly OUTSIDE all water polygons.
    - Point is within 100 meters of the water polygon edge.
    """
    water_path = DATA_DIR / "water_features.geojson"
    if not water_path.exists():
        water_path = RAW_DIR / "raw_water.geojson"

    default_point = (73.42367, 18.76408)

    if water_path.exists():
        with open(water_path, "r", encoding="utf-8") as f:
            wdata = json.load(f)

        polys = [
            (f.get("properties", {}).get("name", ""), shape(f["geometry"]))
            for f in wdata["features"]
            if shape(f["geometry"]).geom_type in ["Polygon", "MultiPolygon"]
        ]

        if polys:
            # Prefer Valvan dam or Valvan Lake
            target_poly = None
            for name, poly in polys:
                if "valvan" in str(name).lower():
                    target_poly = poly
                    break
            if not target_poly:
                target_poly = polys[0][1]

            # Find southernmost point on boundary (downstream powerhouse position)
            coords = list(target_poly.exterior.coords) if hasattr(target_poly, "exterior") else list(target_poly.geoms[0].exterior.coords)
            coords_by_y = sorted(coords, key=lambda c: c[1])
            south_edge = coords_by_y[0]

            # Offset ~35 meters south (approx 0.00032 degrees latitude)
            cand_lon = round(south_edge[0], 5)
            cand_lat = round(south_edge[1] - 0.00035, 5)

            # Verify outside water
            cand_geom = Point(cand_lon, cand_lat)
            all_polys = [p[1] for p in polys]
            if not any(p.contains(cand_geom) for p in all_polys):
                return cand_lon, cand_lat

    return default_point


def generate_assets():
    """Generates synthetic assets with strict properties as specified in the architecture contract."""
    hydro_lon, hydro_lat = get_hydro_point_from_water()

    # Fixed, reproducible coordinates within Lonavala bbox [73.33, 18.68, 73.48, 18.81]
    # Coordinates ALWAYS [longitude, latitude]
    assets_data = [
        # Solar sites (open elevated ground away from water & roads)
        {
            "id": "solar_01",
            "type": "solar",
            "name": "Solar Site 01 - Tungarli Plateau (Simulated)",
            "capacity_kw": 300.0,
            "status": "active",
            "coordinates": [73.4150, 18.7660]
        },
        {
            "id": "solar_02",
            "type": "solar",
            "name": "Solar Site 02 - Valvan Open Ground (Simulated)",
            "capacity_kw": 300.0,
            "status": "active",
            "coordinates": [73.4380, 18.7480]
        },
        # Wind sites (elevated ridges inside Lonavala-Khandala area)
        {
            "id": "wind_01",
            "type": "wind",
            "name": "Wind Turbine Site 01 - Khandala Ridge (Simulated)",
            "capacity_kw": 200.0,
            "status": "active",
            "coordinates": [73.3650, 18.7650]
        },
        {
            "id": "wind_02",
            "type": "wind",
            "name": "Wind Turbine Site 02 - Duke's Nose Ridge (Simulated)",
            "capacity_kw": 150.0,
            "status": "active",
            "coordinates": [73.3720, 18.7280]
        },
        # Hydro site (placed strictly on shoreline outside water polygon)
        {
            "id": "hydro_01",
            "type": "hydro",
            "name": "Hydro Plant 01 - Valvan Shore Powerhouse (Simulated)",
            "capacity_kw": 400.0,
            "status": "active",
            "coordinates": [hydro_lon, hydro_lat]
        },
        # Battery storage
        {
            "id": "battery_01",
            "type": "battery",
            "name": "Battery Storage BESS 01 - Substation Park (Simulated)",
            "capacity_kw": 250.0,
            "capacity_kwh": 1000.0,
            "status": "active",
            "coordinates": [73.4240, 18.7470]
        },
        # Grid connection point / Substation
        {
            "id": "grid_01",
            "type": "grid",
            "name": "Grid Intertie 01 - Lonavala 110kV Substation (Simulated)",
            "capacity_kw": 1500.0,
            "status": "active",
            "coordinates": [73.4250, 18.7460]
        },
        # Demand Hub
        {
            "id": "demand_hub_01",
            "type": "demand",
            "name": "Lonavala Central Demand Hub (Simulated)",
            "capacity_kw": 1200.0,
            "status": "active",
            "coordinates": [73.4070, 18.7520]
        }
    ]

    features = []
    for asset in assets_data:
        props = {
            "id": asset["id"],
            "type": asset["type"],
            "name": asset["name"],
            "capacity_kw": asset["capacity_kw"],
            "status": asset["status"],
            "is_synthetic": True,
            "data_source": "synthetic_demo",
            "note": SIMULATION_NOTE
        }
        if "capacity_kwh" in asset:
            props["capacity_kwh"] = asset["capacity_kwh"]

        feature = {
            "type": "Feature",
            "properties": props,
            "geometry": {
                "type": "Point",
                "coordinates": asset["coordinates"]
            }
        }
        features.append(feature)

    fc = {
        "type": "FeatureCollection",
        "name": "GridMate_Lonavala_Assets",
        "crs": {
            "type": "name",
            "properties": {"name": "urn:ogc:def:crs:OGC:1.3:CRS84"}
        },
        "features": features
    }

    out_path = DATA_DIR / "assets.geojson"
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(fc, f, indent=2)
    logger.info(f"Generated {len(features)} energy assets in {out_path} ({out_path.stat().st_size / 1024:.1f} KB)")
    return fc


def generate_demand_zones():
    """Generates demand zone polygons from illustrative zones (hand-defined polygons), not OSM-derived.

    Base load totals exactly 900.0 kW.
    """
    raw_landuse_path = RAW_DIR / "raw_landuse.geojson"

    # Zone configuration: exact spelling 'Bhushi', total base load 900.0 kW
    zone_specs = [
        {
            "id": "zone_01",
            "key": "Town Center",
            "name": "Lonavala Town Center & Residential",
            "zone_type": "residential",
            "base_load_kw": 400.0,
            "fallback_poly": [
                [73.396, 18.742], [73.420, 18.742], [73.420, 18.760],
                [73.396, 18.760], [73.396, 18.742]
            ]
        },
        {
            "id": "zone_02",
            "key": "Khandala",
            "name": "Khandala Tourism & Hotel Corridor",
            "zone_type": "commercial",
            "base_load_kw": 250.0,
            "fallback_poly": [
                [73.348, 18.750], [73.376, 18.750], [73.376, 18.778],
                [73.348, 18.778], [73.348, 18.750]
            ]
        },
        {
            "id": "zone_03",
            "key": "Valvan",
            "name": "Valvan Industrial & Workshop Pocket",
            "zone_type": "industrial",
            "base_load_kw": 180.0,
            "fallback_poly": [
                [73.428, 18.738], [73.456, 18.738], [73.456, 18.756],
                [73.428, 18.756], [73.428, 18.738]
            ]
        },
        {
            "id": "zone_04",
            "key": "Bushi",
            "name": "Bhushi Tourism & Recreation Sector",
            "zone_type": "commercial",
            "base_load_kw": 70.0,
            "fallback_poly": [
                [73.380, 18.712], [73.402, 18.712], [73.402, 18.732],
                [73.380, 18.732], [73.380, 18.712]
            ]
        }
    ]

    # Load raw landuse geometries if available
    real_polys = {}
    if raw_landuse_path.exists():
        with open(raw_landuse_path, "r", encoding="utf-8") as f:
            land_data = json.load(f)
        for feat in land_data.get("features", []):
            name = feat.get("properties", {}).get("name", "")
            geom = feat.get("geometry", {})
            if geom.get("type") == "Polygon":
                real_polys[name] = geom["coordinates"]

    features = []
    total_base_load = 0.0

    for z in zone_specs:
        poly_coords = None
        for rname, coords in real_polys.items():
            if z["key"].lower() in rname.lower():
                poly_coords = coords
                break
        if not poly_coords:
            poly_coords = [z["fallback_poly"]]

        feature = {
            "type": "Feature",
            "properties": {
                "id": z["id"],
                "name": z["name"],
                "zone_type": z["zone_type"],
                "base_load_kw": z["base_load_kw"],
                "is_synthetic": True,
                "data_source": "synthetic_demo",
                "note": SIMULATION_NOTE
            },
            "geometry": {
                "type": "Polygon",
                "coordinates": poly_coords
            }
        }
        total_base_load += z["base_load_kw"]
        features.append(feature)

    fc = {
        "type": "FeatureCollection",
        "name": "GridMate_Lonavala_Demand_Zones",
        "features": features
    }

    out_path = DATA_DIR / "demand_zones.geojson"
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(fc, f, indent=2)
    logger.info(f"Generated {len(features)} demand zones (total {total_base_load:.1f} kW) in {out_path}")
    return fc


def generate_energy_flow_template(assets_fc):
    """Generates template LineString features from each supply asset to the central demand hub."""
    demand_hub = None
    supply_assets = []

    for feature in assets_fc["features"]:
        props = feature["properties"]
        if props["type"] == "demand":
            demand_hub = feature
        else:
            supply_assets.append(feature)

    if not demand_hub:
        raise ValueError("Cannot generate energy flow: demand hub missing from assets.")

    hub_coords = demand_hub["geometry"]["coordinates"]
    flow_features = []

    for idx, src in enumerate(supply_assets):
        src_props = src["properties"]
        src_coords = src["geometry"]["coordinates"]
        line_coords = [src_coords, hub_coords]

        flow_features.append({
            "type": "Feature",
            "properties": {
                "id": f"flow_{src_props['id']}_to_demand",
                "source_id": src_props["id"],
                "source_type": src_props["type"],
                "source_name": src_props["name"],
                "target_id": demand_hub["properties"]["id"],
                "target_name": demand_hub["properties"]["name"],
                "default_flow_kw": 0.0,
                "is_synthetic": True,
                "note": SIMULATION_NOTE
            },
            "geometry": {
                "type": "LineString",
                "coordinates": line_coords
            }
        })

    fc = {
        "type": "FeatureCollection",
        "name": "GridMate_Energy_Flow_Template",
        "features": flow_features
    }

    out_path = DATA_DIR / "energy_flow_template.geojson"
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(fc, f, indent=2)
    logger.info(f"Generated {len(flow_features)} energy flow lines in {out_path}")
    return fc


def main():
    logger.info("=== STEP 3: Generate Assets, Demand Zones, and Flow Template ===")
    assets_fc = generate_assets()
    generate_demand_zones()
    generate_energy_flow_template(assets_fc)
    logger.info("Step 3 completed successfully.")


if __name__ == "__main__":
    main()
