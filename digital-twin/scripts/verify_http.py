"""
verify_http.py
Starts python http.server on port 8000 in digital-twin/, verifies HTTP 200 for every file
loaded by map/index.html, logs results, and cleanly stops the server.
"""

import sys
import time
import subprocess
import urllib.request
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent

FILES_TO_CHECK = [
    "/map/index.html",
    "/map/applyDispatch.js",
    "/map/gridmateMap.js",
    "/map/map_config.json",
    "/data/assets.geojson",
    "/data/water_features.geojson",
    "/data/roads.geojson",
    "/data/power_lines.geojson",
    "/data/demand_zones.geojson",
    "/data/energy_flow_template.geojson",
    "/data/sample_dispatch.json",
    "/data/scenarios/normal.json",
    "/data/scenarios/cloudy.json",
    "/data/scenarios/heavy_monsoon.json",
    "/data/scenarios/high_wind.json",
    "/data/scenarios/peak_demand.json",
]

def main():
    python_exe = sys.executable
    port = 8000
    server_cmd = [python_exe, "-m", "http.server", str(port)]
    
    print(f"Starting http.server on port {port} in {BASE_DIR}...")
    proc = subprocess.Popen(server_cmd, cwd=BASE_DIR, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    
    time.sleep(1.0) # allow server to bind
    
    all_ok = True
    results = []
    
    try:
        for file_path in FILES_TO_CHECK:
            url = f"http://127.0.0.1:{port}{file_path}"
            req = urllib.request.Request(url, method="GET")
            try:
                with urllib.request.urlopen(req, timeout=3) as resp:
                    status = resp.status
                    msg = f"HTTP {status} OK: {file_path}"
                    print(f"  ✓ {msg}")
                    results.append(msg)
                    if status != 200:
                        all_ok = False
            except Exception as e:
                err_msg = f"FAILED: {file_path} -> {e}"
                print(f"  ✗ {err_msg}")
                results.append(err_msg)
                all_ok = False
    finally:
        print("Stopping http.server...")
        proc.terminate()
        try:
            proc.wait(timeout=3)
        except subprocess.TimeoutExpired:
            proc.kill()
        print("http.server stopped.")
        
    log_file = BASE_DIR / "logs" / "http_check.log"
    log_file.write_text("\n".join(results) + ("\nALL PASSED" if all_ok else "\nFAILED"), encoding="utf-8")
    
    if not all_ok:
        sys.exit(1)
    print("All HTTP checks passed!")

if __name__ == "__main__":
    main()

