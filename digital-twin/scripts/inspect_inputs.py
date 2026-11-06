"""
inspect_inputs.py
Inspects new raw inputs in data/raw/:
- raw_hydro.geojson
- raw_dams.geojson
- raw_solar.geojson
Computes feature counts, geometry types, bounds, tags, names, and whether they lie inside context_bbox.
"""

import json
from pathlib import Path
from collections import Counter
import geopandas as gpd

BASE_DIR = Path(__file__).resolve().parent.parent
RAW_DIR = BASE_DIR / "data" / "raw"

CONTEXT_BBOX = [73.25, 18.62, 73.62, 18.92]

def inspect_file(filename):
    filepath = RAW_DIR / filename
    print(f"\n{'='*20} {filename} {'='*20}")
    if not filepath.exists():
        print("FILE NOT FOUND")
        return

    sz = filepath.stat().st_size
    print(f"File size: {sz} bytes")

    with open(filepath, "r", encoding="utf-8") as f:
        data = json.load(f)

    features = data.get("features", [])
    count = len(features)
    print(f"Feature count: {count}")

    if count == 0:
        print("EMPTY (0 features)")
        return

    geom_types = Counter(f.get("geometry", {}).get("type") for f in features if f.get("geometry"))
    print(f"Geometry types: {dict(geom_types)}")

    gdf = gpd.read_file(filepath)
    bounds = list(gdf.total_bounds) # minx, miny, maxx, maxy
    print(f"Total bounds [min_lon, min_lat, max_lon, max_lat]: {[round(b, 5) for b in bounds]}")

    inside_context = (
        bounds[0] >= CONTEXT_BBOX[0] and
        bounds[1] >= CONTEXT_BBOX[1] and
        bounds[2] <= CONTEXT_BBOX[2] and
        bounds[3] <= CONTEXT_BBOX[3]
    )
    print(f"Inside context_bbox ({CONTEXT_BBOX}): {inside_context}")

    # Inspect names and tags
    all_keys = Counter()
    names = []
    for f in features:
        props = f.get("properties", {})
        for k in props.keys():
            all_keys[k] += 1
        name = props.get("name") or props.get("name:en")
        if name:
            names.append((name, f.get("geometry", {}).get("type"), props.get("power"), props.get("waterway")))
        else:
            names.append(("<unnamed>", f.get("geometry", {}).get("type"), props.get("power"), props.get("waterway")))

    print(f"Top 10 tags: {all_keys.most_common(10)}")
    print(f"Sample names/tags (up to 5): {names[:5]}")
    if len(names) > 5:
        print(f"Total named / identified: {len(names)}")

if __name__ == "__main__":
    for fname in ["raw_hydro.geojson", "raw_dams.geojson", "raw_solar.geojson"]:
        inspect_file(fname)

