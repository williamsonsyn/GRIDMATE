"""
test_gridmate_map_node.py
Pytest wrapper executing test_gridmate_map.mjs to ensure Node.js integration tests
run within the full pytest suite.
"""

from pathlib import Path
import subprocess

BASE_DIR = Path(__file__).resolve().parent.parent


def test_gridmate_map_node_exports_and_parity():
    """Runs digital-twin/tests/test_gridmate_map.mjs with Node.js and asserts success."""
    test_script = BASE_DIR / "tests" / "test_gridmate_map.mjs"
    assert test_script.exists(), "test_gridmate_map.mjs missing in tests/"

    result = subprocess.run(
        ["node", str(test_script)],
        cwd=BASE_DIR,
        capture_output=True,
        text=True
    )

    assert result.returncode == 0, (
        f"Node test failed (exit code {result.returncode}):\n{result.stderr}\n{result.stdout}"
    )
    assert "All Node tests in test_gridmate_map.mjs PASSED!" in result.stdout

