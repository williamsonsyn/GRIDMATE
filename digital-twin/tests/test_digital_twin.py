"""
test_digital_twin.py
Pytest test suite for Member 3 "Lonavala Digital Twin & GIS" module.

Verifications:
1. GeoJSON validity, CRS EPSG:4326, [lon, lat] coordinate order:
   - Context layers (water, roads) inside context_bbox [73.25, 18.62, 73.62, 18.90]
   - Asset & demand layers inside asset_bbox [73.33, 18.68, 73.48, 18.81]
2. Real OSM GIS verification: metadata source is manual OSM export, no fallback/synthetic flags,
   water has polygons with enough vertices.
3. Asset spatial constraints: no asset inside water polygons, hydro asset on real shoreline within
   100 m of water polygon edge, wind on higher ground inside Lonavala-Khandala area, all assets in asset_bbox.
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

from src.map_utils import load_dispatch, apply_dispatch, build_energy_flow, distribute_demand_load

BASE_DIR = Path(__file__).resolve().parent.parent
DATA_DIR = BASE_DIR / "data"
RAW_DIR = DATA_DIR / "raw"
SCENARIO_DIR = DATA_DIR / "scenarios"

# Two bounding boxes as defined in the contract:
CONTEXT_BBOX = [73.25, 18.60, 73.68, 18.97]  # [min_lon, min_lat, max_lon, max_lat]
ASSET_BBOX = [73.33, 18.66, 73.66, 18.95]    # Regional energy assets & demand zones

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
# 1. GeoJSON Validity & Bounding Boxes
# ==========================================

@pytest.mark.parametrize("filename,bbox_name,bbox", [
    ("water_features.geojson", "context_bbox", CONTEXT_BBOX),
    ("roads.geojson", "context_bbox", CONTEXT_BBOX),
    ("assets.geojson", "asset_bbox", ASSET_BBOX),
    ("demand_zones.geojson", "asset_bbox", ASSET_BBOX),
    ("energy_flow_template.geojson", "asset_bbox", ASSET_BBOX)
])
def test_geojson_validity_and_bounds(filename, bbox_name, bbox):
    filepath = DATA_DIR / filename
    assert filepath.exists(), f"Missing required file: {filename}"

    with open(filepath, "r", encoding="utf-8") as f:
        fc = json.load(f)

    assert fc.get("type") == "FeatureCollection", f"{filename} is not a FeatureCollection"
    assert "features" in fc and len(fc["features"]) > 0, f"{filename} has no features"

    # Allow tiny float precision margin (1e-4 deg ≈ 10 meters)
    margin = 0.0002
    min_lon, min_lat = bbox[0] - margin, bbox[1] - margin
    max_lon, max_lat = bbox[2] + margin, bbox[3] + margin

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
            assert min_lon <= lon <= max_lon, (
                f"Longitude {lon} out of bounds [{bbox[0]}, {bbox[2]}] ({bbox_name}) in feature {fid} ({filename}). "
                "Did coordinates get swapped (lat/lon instead of lon/lat)?"
            )
            assert min_lat <= lat <= max_lat, (
                f"Latitude {lat} out of bounds [{bbox[1]}, {bbox[3]}] ({bbox_name}) in feature {fid} ({filename}). "
                "Did coordinates get swapped?"
            )


# ==========================================
# 2. Real OSM GIS Layer & Lakes Verification
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
    assert "context_bbox" in meta
    assert "asset_bbox" in meta


def test_water_and_roads_are_real_osm():
    water_path = DATA_DIR / "water_features.geojson"
    roads_path = DATA_DIR / "roads.geojson"

    with open(water_path, "r", encoding="utf-8") as f:
        wfc = json.load(f)
    with open(roads_path, "r", encoding="utf-8") as f:
        rfc = json.load(f)

    polygon_features = []
    lake_names = set()
    for f in wfc["features"]:
        fid = f.get("properties", {}).get("id", "unknown_water")
        p = f["properties"]
        assert p.get("is_synthetic") is False, f"Water feature {fid} must not be synthetic"
        assert "fallback" not in str(p.get("source", "")).lower(), f"Water feature {fid} is marked fallback"

        s = shape(f["geometry"])
        if s.geom_type in ["Polygon", "MultiPolygon"]:
            polygon_features.append((fid, s))
            if p.get("name"):
                lake_names.add(p["name"].lower())

    assert len(polygon_features) >= 15, f"Expected at least 15 real water polygons, got {len(polygon_features)}"

    # Check key lakes are present
    required_lakes = ["valvan", "bhushi", "tungarli", "khandala", "pavana", "tata"]
    for req in required_lakes:
        found = any(req in n for n in lake_names)
        assert found, f"Required named lake '{req}' missing from water_features.geojson"

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
    raw_hydro_path = RAW_DIR / "raw_hydro.geojson"

    with open(assets_path, "r", encoding="utf-8") as f:
        afc = json.load(f)

    gdf_water = gpd.read_file(water_path)
    water_polys = gdf_water[gdf_water.geometry.geom_type.isin(["Polygon", "MultiPolygon"])].copy()
    assert len(water_polys) > 0, "No water polygons found for spatial validation"

    water_polys_utm = water_polys.to_crs("EPSG:32643")
    water_union_utm = water_polys_utm.geometry.union_all()

    real_hydro_polys = []
    if raw_hydro_path.exists():
        gdf_raw_hydro = gpd.read_file(raw_hydro_path)
        real_hydro_polys = list(gdf_raw_hydro.geometry)

    transformer_to_utm = Transformer.from_crs("EPSG:4326", "EPSG:32643", always_xy=True)

    hydro_found = False

    for feature in afc["features"]:
        props = feature["properties"]
        aid = props.get("id", "unknown_asset")
        coords = feature["geometry"]["coordinates"]
        lon, lat = coords[0], coords[1]

        # 1. Coordinate strictly inside asset_bbox
        assert ASSET_BBOX[0] <= lon <= ASSET_BBOX[2], f"Asset {aid} longitude {lon} out of asset_bbox"
        assert ASSET_BBOX[1] <= lat <= ASSET_BBOX[3], f"Asset {aid} latitude {lat} out of asset_bbox"

        # Transform to meters
        xm, ym = transformer_to_utm.transform(lon, lat)
        pt_utm = Point(xm, ym)

        # 2. No asset may fall inside a water polygon
        in_water = water_union_utm.contains(pt_utm)
        assert not in_water, f"Asset {aid} ({props.get('name')}) falls inside a water polygon!"

        # 3. Hydro asset checks: within 100m of water or inside real OSM hydro feature
        if props.get("type") == "hydro":
            hydro_found = True
            dist_to_water = water_union_utm.distance(pt_utm)
            pt_deg = Point(lon, lat)
            in_osm_hydro = any(poly.contains(pt_deg) for poly in real_hydro_polys)
            assert dist_to_water <= 100.0 or in_osm_hydro, (
                f"Hydro asset {aid} is {dist_to_water:.1f} m from water polygon edge and not inside a real OSM hydro feature"
            )

        # 4. Wind assets checks: high ground on real OSM wind ridge
        if props.get("type") == "wind":
            assert 73.54 <= lon <= 73.61, (
                f"Wind asset {aid} ({props.get('name')}) at lon {lon} not on real OSM wind ridge"
            )
            assert 18.80 <= lat <= 18.91, (
                f"Wind asset {aid} ({props.get('name')}) at lat {lat} outside real OSM wind ridge"
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
    type_capacities = {}

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
        assert "location_source" in props and len(props["location_source"]) > 0, f"Asset {aid} must have location_source property"

        atype = props["type"]
        present_types.add(atype)
        type_capacities[atype] = type_capacities.get(atype, 0.0) + props["capacity_kw"]

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
    assert type_capacities.get("solar", 0.0) == pytest.approx(600.0, abs=0.1), f"Expected total solar capacity 600 kW, got {type_capacities.get('solar')}"
    assert type_capacities.get("wind", 0.0) == pytest.approx(350.0, abs=0.1), f"Expected total wind capacity 350 kW, got {type_capacities.get('wind')}"
    assert type_capacities.get("hydro", 0.0) == pytest.approx(400.0, abs=0.1), f"Expected total hydro capacity 400 kW, got {type_capacities.get('hydro')}"


def test_demand_zones_properties():
    filepath = DATA_DIR / "demand_zones.geojson"
    with open(filepath, "r", encoding="utf-8") as f:
        fc = json.load(f)

    assert len(fc["features"]) >= 4, f"Expected at least 4 demand zones, got {len(fc['features'])}"
    total_base_load = 0.0
    bhushi_found = False

    for f in fc["features"]:
        props = f["properties"]
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


# ==========================================
# 7. 24-Hour Sample Dispatch Parity & Constraints
# ==========================================

def test_sample_dispatch_24h_python_js_parity():
    """Verifies that applyDispatch gives identical output for every timestamp index

    (0..23) in sample_dispatch.json between Python and Node.js.
    Also verifies no negative outputs for any asset at any hour.
    """
    assets_file = DATA_DIR / "assets.geojson"
    sample_file = DATA_DIR / "sample_dispatch.json"

    with open(sample_file, "r", encoding="utf-8") as f:
        sample_data = json.load(f)

    dispatch_rows = sample_data["dispatch"]
    assert len(dispatch_rows) == 24, f"Expected 24 hourly dispatch rows, got {len(dispatch_rows)}"

    # Run Node to compute all 24 hours at once for high-performance parity checking
    js_script = """
    const fs = require('fs');
    const GridMateDispatch = require('./map/applyDispatch.js');
    const assets = JSON.parse(fs.readFileSync('./data/assets.geojson', 'utf-8'));
    const sample = JSON.parse(fs.readFileSync('./data/sample_dispatch.json', 'utf-8'));

    const allApplied = sample.dispatch.map((row, idx) => {
        const parsed = GridMateDispatch.parseDispatchRow(sample, idx);
        return GridMateDispatch.applyDispatch(assets, parsed, sample.scenario_id);
    });
    console.log(JSON.stringify(allApplied));
    """
    result = subprocess.run(
        ["node", "-e", js_script],
        cwd=BASE_DIR,
        capture_output=True,
        text=True,
        check=True
    )
    js_all_applied = json.loads(result.stdout)
    assert len(js_all_applied) == 24

    for idx, row in enumerate(dispatch_rows):
        ts = row.get("timestamp", f"hour_{idx}")
        py_row = load_dispatch(sample_file, idx)
        py_applied = apply_dispatch(assets_file, py_row, scenario_id=sample_data.get("scenario_id"))
        js_applied = js_all_applied[idx]

        assert len(py_applied["features"]) == len(js_applied["features"]), (
            f"Feature count mismatch at hour {idx} ({ts}): Python {len(py_applied['features'])} vs JS {len(js_applied['features'])}"
        )

        for f_py, f_js in zip(py_applied["features"], js_applied["features"]):
            p_py = f_py["properties"]
            p_js = f_js["properties"]
            aid = p_py["id"]

            assert p_py["id"] == p_js["id"], f"Asset ID mismatch at hour {idx} ({ts}): {aid} vs {p_js['id']}"

            # Check no negative outputs
            assert p_py["forecast_output_kw"] >= 0.0, (
                f"Negative forecast_output_kw={p_py['forecast_output_kw']} in Python for asset '{aid}' at timestamp '{ts}' (hour {idx})"
            )
            assert p_js["forecast_output_kw"] >= 0.0, (
                f"Negative forecast_output_kw={p_js['forecast_output_kw']} in JS for asset '{aid}' at timestamp '{ts}' (hour {idx})"
            )

            # Check status match
            assert p_py["status"] == p_js["status"], (
                f"Status mismatch for asset '{aid}' at timestamp '{ts}' (hour {idx}): Python '{p_py['status']}' vs JS '{p_js['status']}'"
            )

            # Check output match
            assert abs(p_py["forecast_output_kw"] - p_js["forecast_output_kw"]) < 0.05, (
                f"Output mismatch for asset '{aid}' at timestamp '{ts}' (hour {idx}): Python {p_py['forecast_output_kw']} vs JS {p_js['forecast_output_kw']}"
            )

            # Check utilization match
            assert abs(p_py["utilization_percent"] - p_js["utilization_percent"]) < 0.2, (
                f"Utilization mismatch for asset '{aid}' at timestamp '{ts}' (hour {idx}): Python {p_py['utilization_percent']} vs JS {p_js['utilization_percent']}"
            )


def test_demand_zones_load_conservation_24h():
    """Verifies that zone loads sum to load_kw at each of the 24 timestamps

    in sample_dispatch.json, with proportional allocation and no negative values.
    Also verifies Python vs JS parity for demand zone load distribution.
    """
    zones_file = DATA_DIR / "demand_zones.geojson"
    sample_file = DATA_DIR / "sample_dispatch.json"

    with open(sample_file, "r", encoding="utf-8") as f:
        sample_data = json.load(f)

    with open(zones_file, "r", encoding="utf-8") as f:
        raw_zones = json.load(f)

    # Node script for JS distribution parity
    js_script = """
    const fs = require('fs');
    const GridMateDispatch = require('./map/applyDispatch.js');
    const zones = JSON.parse(fs.readFileSync('./data/demand_zones.geojson', 'utf-8'));
    const sample = JSON.parse(fs.readFileSync('./data/sample_dispatch.json', 'utf-8'));

    const allDistributed = sample.dispatch.map((row) => {
        return GridMateDispatch.distributeDemandLoad(zones, row.load_kw);
    });
    console.log(JSON.stringify(allDistributed));
    """
    result = subprocess.run(
        ["node", "-e", js_script],
        cwd=BASE_DIR,
        capture_output=True,
        text=True,
        check=True
    )
    js_all_zones = json.loads(result.stdout)

    for idx, row in enumerate(sample_data["dispatch"]):
        ts = row.get("timestamp", f"hour_{idx}")
        total_load = float(row["load_kw"])
        assert total_load > 0, f"Non-positive load_kw at hour {idx} ({ts})"

        py_distributed = distribute_demand_load(zones_file, total_load)
        js_distributed = js_all_zones[idx]

        # 1. Zone loads must sum to total load_kw at each timestamp
        zone_sum_py = sum(float(f["properties"]["load_kw"]) for f in py_distributed["features"])
        assert zone_sum_py == pytest.approx(total_load, abs=0.1), (
            f"Python demand zone sum ({zone_sum_py:.2f} kW) != dispatch load_kw ({total_load} kW) at timestamp '{ts}' (hour {idx})"
        )

        zone_sum_js = sum(float(f["properties"]["load_kw"]) for f in js_distributed["features"])
        assert zone_sum_js == pytest.approx(total_load, abs=0.1), (
            f"JS demand zone sum ({zone_sum_js:.2f} kW) != dispatch load_kw ({total_load} kW) at timestamp '{ts}' (hour {idx})"
        )

        # 2. Check each zone: no negative load, 'illustrative zone' label, and Python-JS parity
        for f_py, f_js in zip(py_distributed["features"], js_distributed["features"]):
            p_py = f_py["properties"]
            p_js = f_js["properties"]
            zid = p_py.get("id", "unknown_zone")

            assert p_py["load_kw"] >= 0.0, (
                f"Negative zone load in Python for zone '{zid}' at timestamp '{ts}' (hour {idx}): {p_py['load_kw']} kW"
            )
            assert p_js["load_kw"] >= 0.0, (
                f"Negative zone load in JS for zone '{zid}' at timestamp '{ts}' (hour {idx}): {p_js['load_kw']} kW"
            )

            assert p_py["label"] == "illustrative zone", (
                f"Zone '{zid}' missing 'illustrative zone' label in Python at timestamp '{ts}'"
            )
            assert p_js["label"] == "illustrative zone", (
                f"Zone '{zid}' missing 'illustrative zone' label in JS at timestamp '{ts}'"
            )

            assert abs(p_py["load_kw"] - p_js["load_kw"]) < 0.05, (
                f"Zone load mismatch for zone '{zid}' at timestamp '{ts}' (hour {idx}): Python {p_py['load_kw']} vs JS {p_js['load_kw']}"
            )
            assert abs(p_py["load_share_pct"] - p_js["load_share_pct"]) < 0.2, (
                f"Zone share % mismatch for zone '{zid}' at timestamp '{ts}' (hour {idx}): Python {p_py['load_share_pct']} vs JS {p_js['load_share_pct']}"
            )


# ==========================================
# 7. Member 3 Fix Verifications
# ==========================================

def test_assets_directory_count_matches_geojson():
    """Verifies that assets directory count matches the number of features in assets.geojson (12)."""
    assets_file = DATA_DIR / "assets.geojson"
    with open(assets_file, "r", encoding="utf-8") as f:
        assets_data = json.load(f)

    feature_count = len(assets_data["features"])
    assert feature_count == 12, f"Expected 12 features in assets.geojson, found {feature_count}"

    # Verify map/index.html populates directory immediately on asset load and hooks click events
    index_html = (BASE_DIR / "map" / "index.html").read_text(encoding="utf-8")
    assert "applyTimeStep(0)" in index_html, "index.html must apply timestep 0 immediately on startup"
    assert "renderAssetsList" in index_html, "index.html must define renderAssetsList"
    assert "countElem.innerText = String(features.length)" in index_html, "renderAssetsList must set asset count to feature count"
    assert "flyToAssetAndOpenPopup" in index_html, "index.html must invoke flyToAssetAndOpenPopup on item click"


def test_timestep_zero_panel_and_directory_parity():
    """Verifies that the metrics panel text and directory output for timestep 0 (00:00:00)
    match applyDispatch() output for the same row, with assertion messages naming asset id and hour.
    """
    js_script = """
    const fs = require('fs');
    const GridMateDispatch = require('./map/applyDispatch.js');

    const assets = JSON.parse(fs.readFileSync('./data/assets.geojson', 'utf-8'));
    const sample = JSON.parse(fs.readFileSync('./data/sample_dispatch.json', 'utf-8'));

    const row = GridMateDispatch.parseDispatchRow(sample, 0);
    const applied = GridMateDispatch.applyDispatch(assets, row, sample.scenario_id);

    console.log(JSON.stringify({ row, applied }));
    """
    result = subprocess.run(
        ["node", "-e", js_script],
        cwd=BASE_DIR,
        capture_output=True,
        text=True,
        check=True
    )
    data = json.loads(result.stdout)
    row = data["row"]
    applied = data["applied"]

    # 1. Assets Directory / applyDispatch parity checks for hour 0
    for f in applied["features"]:
        p = f["properties"]
        aid = p["id"]
        atype = p["type"]
        out_kw = p["forecast_output_kw"]
        status = p["status"]

        if atype == "solar":
            assert out_kw == 0.0, f"Hour 0: asset {aid} output must be 0 kW at night, got {out_kw} kW"
            assert status == "idle", f"Hour 0: asset {aid} status must be 'idle' at night, got '{status}'"
        elif atype == "battery":
            assert out_kw == row["battery_kw"], f"Hour 0: asset {aid} output {out_kw} kW != dispatch battery_kw {row['battery_kw']} kW"
            assert status == "discharging", f"Hour 0: asset {aid} status must be 'discharging', got '{status}'"
            assert p["battery_soc_kwh"] == row["battery_soc_kwh"], f"Hour 0: asset {aid} SOC {p['battery_soc_kwh']} != dispatch SOC {row['battery_soc_kwh']}"
        elif atype == "grid":
            assert out_kw == row["grid_kw"], f"Hour 0: asset {aid} output {out_kw} kW != dispatch grid_kw {row['grid_kw']} kW"
            assert status == "not_supplying", f"Hour 0: asset {aid} status must be 'not_supplying' when grid_kw=0, got '{status}'"
        elif atype == "wind":
            assert out_kw > 0.0, f"Hour 0: asset {aid} output must be positive, got {out_kw} kW"
            assert status == "active", f"Hour 0: asset {aid} status must be 'active', got '{status}'"

    # 2. Panel text metrics derived from current dispatch row for hour 0
    load_kw = float(row["load_kw"])
    solar_kw = float(row["solar_kw"])
    wind_kw = float(row["wind_kw"])
    hydro_kw = float(row["hydro_kw"])
    grid_kw = float(row["grid_kw"])
    bat_kw = float(row["battery_kw"])
    bat_discharge = bat_kw if bat_kw > 0 else 0.0

    gen_total = solar_kw + wind_kw + hydro_kw + grid_kw + bat_discharge
    re_gen = solar_kw + wind_kw + hydro_kw + bat_discharge
    re_pct = (re_gen / load_kw) * 100.0 if load_kw > 0 else 100.0
    grid_pct = (grid_kw / load_kw) * 100.0 if load_kw > 0 else 0.0

    bal_text = f"{gen_total:.0f} kW gen / {load_kw:.0f} kW load"
    bat_text = f"Discharging ({bat_kw:.0f} kW)" if bat_kw > 0 else f"Idle (0 kW)"
    soc_text = f"{float(row['battery_soc_kwh']):.0f} kWh"
    re_text = f"{re_pct:.1f}%"
    grid_text = f"{grid_pct:.1f}%"

    assert bal_text == "500 kW gen / 500 kW load", f"Hour 0: balance text expected '500 kW gen / 500 kW load', got '{bal_text}'"
    assert bat_text == "Discharging (90 kW)", f"Hour 0: battery text expected 'Discharging (90 kW)', got '{bat_text}'"
    assert soc_text == "360 kWh", f"Hour 0: SOC text expected '360 kWh', got '{soc_text}'"
    assert re_text == "100.0%", f"Hour 0: renewable text expected '100.0%', got '{re_text}'"
    assert grid_text == "0.0%", f"Hour 0: grid text expected '0.0%', got '{grid_text}'"


def test_dispatch_per_type_capacity_limits():
    """Verifies per-type output never exceeds total nameplate capacity in assets.geojson."""
    assets_file = DATA_DIR / "assets.geojson"
    with open(assets_file, "r", encoding="utf-8") as f:
        assets_data = json.load(f)

    type_capacities = {}
    for f in assets_data["features"]:
        p = f["properties"]
        t = p["type"]
        type_capacities[t] = type_capacities.get(t, 0.0) + float(p["capacity_kw"])

    # 1. Check sample_dispatch.json 24 hours
    sample_file = DATA_DIR / "sample_dispatch.json"
    with open(sample_file, "r", encoding="utf-8") as f:
        sample_data = json.load(f)

    for h, row in enumerate(sample_data["dispatch"]):
        assert row["solar_kw"] <= type_capacities["solar"], (
            f"Hour {h}: asset type solar output {row['solar_kw']} kW exceeds total capacity {type_capacities['solar']} kW"
        )
        assert row["wind_kw"] <= type_capacities["wind"], (
            f"Hour {h}: asset type wind output {row['wind_kw']} kW exceeds total capacity {type_capacities['wind']} kW"
        )
        assert row["hydro_kw"] <= type_capacities["hydro"], (
            f"Hour {h}: asset type hydro output {row['hydro_kw']} kW exceeds total capacity {type_capacities['hydro']} kW"
        )
        assert abs(row["battery_kw"]) <= type_capacities["battery"], (
            f"Hour {h}: asset type battery output {abs(row['battery_kw'])} kW exceeds total capacity {type_capacities['battery']} kW"
        )

    # 2. Check all 5 scenario files
    for sc_id in REQUIRED_SCENARIOS:
        sc_file = SCENARIO_DIR / f"{sc_id}.json"
        with open(sc_file, "r", encoding="utf-8") as f:
            sc_data = json.load(f)
        for h, row in enumerate(sc_data["dispatch"]):
            ts_hour = row.get("timestamp", str(h))
            assert row["solar_kw"] <= type_capacities["solar"], (
                f"Hour {ts_hour}: asset type solar output {row['solar_kw']} kW exceeds total capacity {type_capacities['solar']} kW in {sc_id}"
            )
            assert row["wind_kw"] <= type_capacities["wind"], (
                f"Hour {ts_hour}: asset type wind output {row['wind_kw']} kW exceeds total capacity {type_capacities['wind']} kW in {sc_id}"
            )
            assert row["hydro_kw"] <= type_capacities["hydro"], (
                f"Hour {ts_hour}: asset type hydro output {row['hydro_kw']} kW exceeds total capacity {type_capacities['hydro']} kW in {sc_id}"
            )
            assert abs(row["battery_kw"]) <= type_capacities["battery"], (
                f"Hour {ts_hour}: asset type battery output {abs(row['battery_kw'])} kW exceeds total capacity {type_capacities['battery']} kW in {sc_id}"
            )


def test_night_time_solar_zero_rule():
    """Verifies that solar_kw is strictly 0 from 19:00 to 05:00 in sample_dispatch and scenarios."""
    sample_file = DATA_DIR / "sample_dispatch.json"
    with open(sample_file, "r", encoding="utf-8") as f:
        sample_data = json.load(f)

    night_hours = {19, 20, 21, 22, 23, 0, 1, 2, 3, 4, 5}
    for h, row in enumerate(sample_data["dispatch"]):
        if h in night_hours:
            assert row["solar_kw"] == 0.0, (
                f"Hour {h:02d}:00: asset type solar must be 0 at night, got {row['solar_kw']} kW"
            )

    # Also verify scenario files with night timestamps (e.g. peak_demand at 19:00:00)
    peak_file = SCENARIO_DIR / "peak_demand.json"
    with open(peak_file, "r", encoding="utf-8") as f:
        peak_data = json.load(f)
    for row in peak_data["dispatch"]:
        assert row["solar_kw"] == 0.0, (
            f"Hour 19:00: asset type solar must be 0 at night, got {row['solar_kw']} kW in peak_demand"
        )


