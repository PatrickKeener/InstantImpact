# InstantImpact local dev launcher (Windows native)
# Usage: from repo root:  .\scripts\dev_up.ps1

$ErrorActionPreference = "Stop"
$Root = Split-Path -Parent (Split-Path -Parent $MyInvocation.MyCommand.Path)
Set-Location $Root

Write-Host "== InstantImpact dev_up ==" -ForegroundColor Magenta

if (-not (Test-Path ".venv")) {
  Write-Host "Creating .venv..."
  python -m venv .venv
}

$py = Join-Path $Root ".venv\Scripts\python.exe"
$pip = Join-Path $Root ".venv\Scripts\pip.exe"

& $pip install -q -e ".[dev]"

if (-not (Test-Path ".env")) {
  Copy-Item ".env.example" ".env"
  Write-Host "Created .env from .env.example"
}

New-Item -ItemType Directory -Force -Path "data\db" | Out-Null

# Frontend deps
if (-not (Test-Path "apps\web\node_modules")) {
  Write-Host "npm install (web)..."
  Push-Location "apps\web"
  npm install
  Pop-Location
}

Write-Host ""
Write-Host "Recommended host: nemesis (10.10.101.150) — all-in-one with L40S" -ForegroundColor Yellow
Write-Host "chamber (10.10.30.184) can just open the nemesis URL in a browser." -ForegroundColor Yellow
Write-Host ""
Write-Host "Start these in separate terminals on nemesis:" -ForegroundColor Cyan
Write-Host "  1) API:   .\.venv\Scripts\python.exe -m uvicorn app.main:app --app-dir apps\api --reload --host 0.0.0.0 --port 8000"
Write-Host "  2) Web:   cd apps\web; npm run dev"
Write-Host "  3) Redis (localhost) + worker when not using mock fallback"
Write-Host "  4) ComfyUI on 127.0.0.1:8188 for real stills"
Write-Host ""
Write-Host "Mock generation is ON by default (INSTANTIMPACT_MOCK_GENERATION=true)."
Write-Host "Open http://10.10.101.150:5173  (or http://127.0.0.1:5173 on nemesis)"
Write-Host "See docs/deployment.md"
