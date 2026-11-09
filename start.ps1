# One-command start for Windows PowerShell. Run from the repository root:  .\start.ps1
# If scripts are blocked:  Set-ExecutionPolicy -Scope Process -ExecutionPolicy RemoteSigned
$ErrorActionPreference = "Stop"
$root = Split-Path -Parent $MyInvocation.MyCommand.Path
Set-Location $root

if (-not (Test-Path ".venv\Scripts\python.exe")) { python -m venv .venv }
& ".venv\Scripts\python.exe" -m pip install -q -r backend/requirements.txt

# Backend in its own window
Start-Process powershell -ArgumentList "-NoExit","-Command","Set-Location '$root'; .\.venv\Scripts\python.exe -m uvicorn backend.main:app --port 8000"

# Frontend in this window
Set-Location "$root\frontend"
if (-not (Test-Path "node_modules")) { npm install }
Start-Process "http://localhost:5173"
npm run dev