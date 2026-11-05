"""
conftest.py
===========
Pytest configuration for GridMate AI Forecasting test suite.
Ensures repository root is included in sys.path so modules can be imported reliably.
"""

from pathlib import Path
import sys

# Ensure repository root is on sys.path
REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

