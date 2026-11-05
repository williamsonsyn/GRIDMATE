"""
test_digital_twin.py
Pytest test suite for Member 3 "Lonavala Digital Twin & GIS" module.

Verifications:
1. GeoJSON validity, CRS EPSG:4326, [lon, lat] coordinate order inside Lonavala bbox.
2. Real OSM GIS verification: metadata source is manual OSM export, no fallback/synthetic flags,
   water has polygons with enough vertices.
3. Asset spatial constraints: no asset inside water polygons, hydro asset on real shoreline within
   100 m of water polygon edge, wind on higher ground inside Lonavala-Khandala area, all in bbox.
4. Demand zones & flow templates validity (base load totals 900 kW, correct spelling 'Bhushi').
5. Dispatch contract compliance and physical energy balance across all 5 scenario files.
6. Python map_utils and JS applyDispatch.js parity across all 5 scenarios.
"""

import json
from pathlib import Path
import subprocess
import pytest
import geopandas as gpd
from shapely.geometry import Point, shape
from pyproj import Transformer

from src.map_utils import load_dispatch, apply_dispatch, build_energy_flow

BASE_DIR = Path(__file__).resolve().parent.parent
DATA_DIR = BASE_DIR / "data"
RAW_DIR = DATA_DIR / "raw"
SCENARIO_DIR = DATA_DIR / "scenarios"

# Lonavala bounding box: longitude 73.33 to 73.48, latitude 18.68 to 18.81
LON_MIN, LON_MAX = 73.30, 73.50
LAT_MIN, LAT_MAX = 18.65, 18.85
STRICT_BBOX = [73.33, 18.68, 73.48, 18.81]

REQUIRED_ASSET_TYPES = {"solar", "wind", "hydro", "battery", "grid", "demand"}
REQUIRED_SCENARIOS = {"normal", "cloudy", "heavy_monsoon", "high_wind", "peak_demand"}


def extract_all_coordinates(geom_dict):
    """Recursively extracts [lon, lat] coordinates from GeoJSON geometry."""
    coords = geom_dict["coordinates"]
    gtype = geom_dict["type"]

    flat_coords = []
    if gtype == "Point":
        flat_coords.append(coords)
    elif gtype in ["LineString", "MultiPoint"]:
        flat_coords.extend(coords)
    elif gtype in ["Polygon", "MultiLineString"]:
        for ring in coords:
            flat_coords.extend(ring)
    elif gtype == "MultiPolygon":
        for poly in coords:
            for ring in poly:
                flat_coords.extend(ring)
    return flat_coords


# ==========================================
# 1. GeoJSON Validity & Coordinate Order
# ==========================================

@pytest.mark.parametrize("filename", [
    "assets.geojson",
    "demand_zones.geojson",
    "water_features.geojson",
    "roads.geojson",
    "energy_flow_template.geojson"
])
def test_geojson_validity_and_bounds(filename):
    filepath = DATA_DIR / filename
    assert filepath.exists(), f"Missing required file: {filename}"

    with open(filepath, "r", encoding="utf-8") as f:
        fc = json.load(f)

    assert fc.get("type") == "FeatureCollection", f"{filename} is not a FeatureCollection"
    assert "features" in fc and len(fc["features"]) > 0, f"{filename} has no features"

    for idx, feature in enumerate(fc["features"]):
        fid = feature.get("properties", {}).get("id", f"idx_{idx}")
        assert feature.get("type") == "Feature", f"Feature {fid} in {filename} is not a Feature"
        geom = feature.get("geometry")
        assert geom is not None, f"Feature {fid} in {filename} lacks geometry"

        s = shape(geom)
        assert s.is_valid, f"Feature {fid} geometry in {filename} is invalid"

        coords = extract_all_coordinates(geom)
        assert len(coords) > 0, f"Feature {fid} in {filename} has empty coordinates"

        for pt in coords:
            lon, lat = pt[0], pt[1]
            assert LON_MIN <= lon <= LON_MAX, (
                f"Longitude {lon} out of bounds [{LON_MIN}, {LON_MAX}] in feature {fid} ({filename}). "
                "Did coordinates get swapped (lat/lon instead of lon/lat)?"
            )
            assert LAT_MIN <= lat <= LAT_MAX, (
                f"Latitude {lat} out of bounds [{LAT_MIN}, {LAT_MAX}] in feature {fid} ({filename}). "
                "Did coordinates get swapped?"
            )


# ==========================================
# 2. Real OSM GIS Layer Verification
# ==========================================

def test_metadata_source_is_real_osm():
    metadata_path = RAW_DIR / "metadata.json"
    assert metadata_path.exists(), "metadata.json missing in data/raw/"
    with open(metadata_path, "r", encoding="utf-8") as f:
        meta = json.load(f)

    source_desc = meta.get("data_source", "") or meta.get("attribution", "")
    assert "manual overpass-turbo export" in source_desc.lower() or "openstreetmap" in source_desc.lower(), (
        f"Unexpected metadata source: {source_desc}. Expected manual OSM export."
    )
    assert meta.get("crs") == "EPSG:4326"


def test_water_and_roads_are_real_osm():
    water_path = DATA_DIR / "water_features.geojson"
    roads_path = DATA_DIR / "roads.geojson"

    with open(water_path, "r", encoding="utf-8") as f:
        wfc = json.load(f)
    with open(roads_path, "r", encoding="utf-8") as f:
        rfc = json.load(f)

    polygon_features = []
    for f in wfc["features"]:
        fid = f.get("properties", {}).get("id", "unknown_water")
        p = f["properties"]
        assert p.get("is_synthetic") is False, f"Water feature {fid} must not be synthetic"
        assert "fallback" not in str(p.get("source", "")).lower(), f"Water feature {fid} is marked fallback"

        s = shape(f["geometry"])
        if s.geom_type in ["Polygon", "MultiPolygon"]:
            polygon_features.append((fid, s))

    assert len(polygon_features) >= 10, f"Expected at least 10 real water polygons, got {len(polygon_features)}"

    # Check vertex density on polygons: real OSM lake polygons have many vertices
    for fid, poly in polygon_features:
        if poly.geom_type == "Polygon":
            vertex_count = len(poly.exterior.coords)
        else:
            vertex_count = sum(len(p.exterior.coords) for p in poly.geoms)
        assert vertex_count >= 5, f"Water polygon {fid} has too few vertices ({vertex_count}), possible synthetic box"

    for f in rfc["features"]:
        fid = f.get("properties", {}).get("id", "unknown_road")
        p = f["properties"]
        assert p.get("is_synthetic") is False, f"Road feature {fid} must not be synthetic"
        assert "fallback" not in str(p.get("source", "")).lower(), f"Road feature {fid} is marked fallback"


# ==========================================
# 3. Asset Placement & Spatial Constraints
# ==========================================

def test_asset_spatial_constraints():
    assets_path = DATA_DIR / "assets.geojson"
    water_path = DATA_DIR / "water_features.geojson"

    with open(assets_path, "r", encoding="utf-8") as f:
        afc = json.load(f)

    # Load water polygons into shapely objects
    gdf_water = gpd.read_file(water_path)
    water_polys = gdf_water[gdf_water.geometry.geom_type.isin(["Polygon", "MultiPolygon"])].copy()
    assert len(water_polys) > 0, "No water polygons found for spatial validation"

    # Union in projected CRS (UTM 43N) to measure accurate distances in meters
    water_polys_utm = water_polys.to_crs("EPSG:32643")
    water_union_utm = water_polys_utm.geometry.union_all()

    transformer_to_utm = Transformer.from_crs("EPSG:4326", "EPSG:32643", always_xy=True)

    hydro_found = False

    for feature in afc["features"]:
        props = feature["properties"]
        aid = props.get("id", "unknown_asset")
        coords = feature["geometry"]["coordinates"]
        lon, lat = coords[0], coords[1]
        pt_geom = Point(lon, lat)

        # 1. Coordinate inside bounding box
        assert STRICT_BBOX[0] <= lon <= STRICT_BBOX[2], f"Asset {aid} longitude {lon} out of strict bbox"
        assert STRICT_BBOX[1] <= lat <= STRICT_BBOX[3], f"Asset {aid} latitude {lat} out of strict bbox"

        # Transform to meters
        xm, ym = transformer_to_utm.transform(lon, lat)
        pt_utm = Point(xm, ym)

        # 2. No asset may fall inside a water polygon
        in_water = water_union_utm.contains(pt_utm)
        assert not in_water, f"Asset {aid} ({props.get('name')}) falls inside a water polygon!"

        # 3. Hydro asset checks
        if props.get("type") == "hydro":
            hydro_found = True
            dist_to_water = water_union_utm.distance(pt_utm)
            assert dist_to_water <= 100.0, (
                f"Hydro asset {aid} is {dist_to_water:.1f} m from water polygon edge; must be <= 100 m on shoreline"
            )

        # 4. Wind assets checks: high ground inside Lonavala-Khandala
        if props.get("type") == "wind":
            # Must be in elevated ridge longitude band (73.34 to 73.39) and not in valley/Khopoli
            assert 73.34 <= lon <= 73.39, (
                f"Wind asset {aid} ({props.get('name')}) at lon {lon} not on Lonavala-Khandala ridge"
            )
            assert 18.70 <= lat <= 18.80, (
                f"Wind asset {aid} ({props.get('name')}) at lat {lat} outside Lonavala-Khandala highlands"
            )

    assert hydro_found, "Missing required hydro asset in assets.geojson"


def test_assets_schema_and_types():
    filepath = DATA_DIR / "assets.geojson"
    with open(filepath, "r", encoding="utf-8") as f:
        fc = json.load(f)

    present_types = set()
    solar_count = 0
    wind_count = 0
    hydro_count = 0

    for f in fc["features"]:
        props = f["properties"]
        aid = props["id"]
        assert len(aid) > 0
        assert "type" in props
        assert "name" in props
        assert "(simulated)" in props["name"].lower(), f"Asset {aid} name must contain '(Simulated)'"
        assert "capacity_kw" in props and props["capacity_kw"] > 0
        assert "status" in props
        assert props.get("is_synthetic") is True, f"Asset {aid} must have is_synthetic: True"
        assert props.get("data_source") == "synthetic_demo"
        assert "note" in props and "simulated" in props["note"].lower()

        atype = props["type"]
        present_types.add(atype)

        if atype == "solar":
            solar_count += 1
        elif atype == "wind":
            wind_count += 1
        elif atype == "hydro":
            hydro_count += 1
        elif atype == "battery":
            assert "capacity_kwh" in props and props["capacity_kwh"] > 0

    assert REQUIRED_ASSET_TYPES.issubset(present_types), f"Missing asset types: {REQUIRED_ASSET_TYPES - present_types}"
    assert solar_count >= 2, f"Expected at least 2 solar sites, got {solar_count}"
    assert wind_count >= 2, f"Expected at least 2 wind sites, got {wind_count}"
    assert hydro_count >= 1, f"Expected at least 1 hydro plant, got {hydro_count}"


def test_demand_zones_properties():
    filepath = DATA_DIR / "demand_zones.geojson"
    with open(filepath, "r", encoding="utf-8") as f:
        fc = json.load(f)

    assert len(fc["features"]) >= 4, f"Expected at least 4 demand zones, got {len(fc['features'])}"
    total_base_load = 0.0
    bhushi_found = False

    for f in fc["features"]:
        props = f["properties"]
        zid = props["id"]
        assert "name" in props
        assert "zone_type" in props
        assert "base_load_kw" in props and props["base_load_kw"] > 0
        assert props.get("is_synthetic") is True

        if "bhushi" in props["name"].lower():
            bhushi_found = True
        total_base_load += props["base_load_kw"]

    assert bhushi_found, "Demand zones must include 'Bhushi' with correct spelling"
    assert total_base_load == pytest.approx(900.0, abs=0.1), f"Expected total base load 900 kW, got {total_base_load}"


# ==========================================
# 4. Energy Conservation & Scenario Validity
# ==========================================

@pytest.mark.parametrize("scenario_id", list(REQUIRED_SCENARIOS))
def test_scenario_dispatch_files(scenario_id):
    filepath = SCENARIO_DIR / f"{scenario_id}.json"
    assert filepath.exists(), f"Missing scenario file for {scenario_id}"

    with open(filepath, "r", encoding="utf-8") as f:
        data = json.load(f)

    assert data.get("location") == "Lonavala"
    assert "dispatch" in data and isinstance(data["dispatch"], list) and len(data["dispatch"]) > 0
    assert "metrics" in data and isinstance(data["metrics"], dict)

    row = data["dispatch"][0]
    required_fields = [
        "timestamp", "solar_kw", "wind_kw", "hydro_kw",
        "battery_kw", "grid_kw", "load_kw", "curtailment_kw", "battery_soc_kwh"
    ]
    for field in required_fields:
        assert field in row, f"Missing field '{field}' in {scenario_id} dispatch row"

    sol = row["solar_kw"]
    wnd = row["wind_kw"]
    hyd = row["hydro_kw"]
    bat = row["battery_kw"]
    grd = row["grid_kw"]
    ld = row["load_kw"]
    curt = row["curtailment_kw"]
    soc = row["battery_soc_kwh"]

    assert sol >= 0, f"Negative solar in {scenario_id}"
    assert wnd >= 0, f"Negative wind in {scenario_id}"
    assert hyd >= 0, f"Negative hydro in {scenario_id}"
    assert grd >= 0, f"Negative grid in {scenario_id}"
    assert ld > 0, f"Non-positive load in {scenario_id}"
    assert curt >= 0, f"Negative curtailment in {scenario_id}"
    assert 0.0 <= soc <= 1000.0, f"Battery SOC {soc} outside bounds [0, 1000] in {scenario_id}"

    balance = (sol + wnd + hyd + bat + grd) - (ld + curt)
    assert abs(balance) <= 0.5, f"Energy conservation failed in {scenario_id}: error={balance} kW"


def test_sample_dispatch_contract():
    filepath = DATA_DIR / "sample_dispatch.json"
    assert filepath.exists()

    with open(filepath, "r", encoding="utf-8") as f:
        data = json.load(f)

    assert data.get("location") == "Lonavala"
    assert len(data["dispatch"]) >= 24

    for idx, row in enumerate(data["dispatch"]):
        balance = (row["solar_kw"] + row["wind_kw"] + row["hydro_kw"] + row["battery_kw"] + row["grid_kw"]) - (row["load_kw"] + row["curtailment_kw"])
        assert abs(balance) < 0.1, f"Hour {idx} energy balance failed: {balance}"
        assert 0.0 <= row["battery_soc_kwh"] <= 1000.0, f"Hour {idx} SOC out of bounds"


# ==========================================
# 5. Python map_utils vs JS applyDispatch Parity
# ==========================================

@pytest.mark.parametrize("scenario_id", list(REQUIRED_SCENARIOS))
def test_python_js_parity_per_scenario(scenario_id):
    """Verifies that Python map_utils and JS applyDispatch.js produce identical

    statuses and per-asset outputs for all 5 scenarios.
    """
    assets_file = DATA_DIR / "assets.geojson"
    scen_file = SCENARIO_DIR / f"{scenario_id}.json"

    py_row = load_dispatch(scen_file)
    py_applied = apply_dispatch(assets_file, py_row, scenario_id=scenario_id)

    # Execute Node script to run applyDispatch.js
    js_script = f"""
    const fs = require('fs');
    const GridMateDispatch = require('./map/applyDispatch.js');
    const assets = JSON.parse(fs.readFileSync('./data/assets.geojson', 'utf-8'));
    const scData = JSON.parse(fs.readFileSync('./data/scenarios/{scenario_id}.json', 'utf-8'));
    const row = GridMateDispatch.parseDispatchRow(scData, 0);
    const applied = GridMateDispatch.applyDispatch(assets, row, '{scenario_id}');
    console.log(JSON.stringify(applied));
    """
    result = subprocess.run(
        ["node", "-e", js_script],
        cwd=BASE_DIR,
        capture_output=True,
        text=True,
        check=True
    )
    js_applied = json.loads(result.stdout)

    assert len(py_applied["features"]) == len(js_applied["features"])

    for f_py, f_js in zip(py_applied["features"], js_applied["features"]):
        p_py = f_py["properties"]
        p_js = f_js["properties"]
        aid = p_py["id"]

        assert p_py["id"] == p_js["id"], f"Asset ID mismatch: {aid}"
        assert p_py["status"] == p_js["status"], (
            f"Status mismatch in {scenario_id} for asset {aid}: Python '{p_py['status']}' vs JS '{p_js['status']}'"
        )
        assert abs(p_py["forecast_output_kw"] - p_js["forecast_output_kw"]) < 0.05, (
            f"Output mismatch in {scenario_id} for asset {aid}: Python {p_py['forecast_output_kw']} vs JS {p_js['forecast_output_kw']}"
        )
        assert abs(p_py["utilization_percent"] - p_js["utilization_percent"]) < 0.2, (
            f"Utilization mismatch in {scenario_id} for asset {aid}"
        )


# ==========================================
# 6. Energy Flow Template Functionality
# ==========================================

def test_build_energy_flow():
    assets_file = DATA_DIR / "assets.geojson"
    row = load_dispatch(SCENARIO_DIR / "normal.json")
    flows = build_energy_flow(row, assets_file)

    assert flows["type"] == "FeatureCollection"
    assert len(flows["features"]) >= 7

    for f in flows["features"]:
        assert f["geometry"]["type"] == "LineString"
        p = f["properties"]
        assert "flow_kw" in p and p["flow_kw"] >= 0.0
        assert "status" in p
        assert p["direction"] in ["to_demand", "to_battery"]
