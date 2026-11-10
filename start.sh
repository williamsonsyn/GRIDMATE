#!/usr/bin/env bash
# One-command start for macOS/Linux. Run from the repository root:  ./start.sh
set -e
cd "$(dirname "$0")"
[ -d .venv ] || python3 -m venv .venv
[ -f backend/requirements-dev.txt ] && REQ="backend/requirements-dev.txt" || REQ="backend/requirements.txt"
.venv/bin/python -m pip install -q -r $REQ
.venv/bin/python -m uvicorn backend.main:app --port 8000 &
BACK=$!
trap 'kill $BACK' EXIT
cd frontend
[ -d node_modules ] || npm install
npm run dev
