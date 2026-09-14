# LocalMind one-command launcher (Windows PowerShell).
#
# Boots the FastAPI backend and the Next.js frontend in separate windows,
# installing dependencies on first run.

$ErrorActionPreference = "Stop"

$Root = Split-Path -Parent $PSScriptRoot
$Backend = Join-Path $Root "backend"
$Frontend = Join-Path $Root "frontend"

$BackendHost = if ($env:LOCALMIND_HOST) { $env:LOCALMIND_HOST } else { "127.0.0.1" }
$BackendPort = if ($env:LOCALMIND_PORT) { $env:LOCALMIND_PORT } else { "8000" }

Write-Host "> tanAI starting from $Root"

# --- Backend ---
Set-Location $Backend
if (-not (Test-Path ".venv")) {
    Write-Host "> Creating Python virtual environment..."
    python -m venv .venv
}
& ".venv\Scripts\Activate.ps1"
Write-Host "> Installing backend dependencies..."
python -m pip install --quiet --upgrade pip
pip install --quiet -r requirements.txt

Start-Process powershell -ArgumentList @(
    "-NoExit", "-Command",
    "Set-Location '$Backend'; .\.venv\Scripts\Activate.ps1; uvicorn app.main:app --host $BackendHost --port $BackendPort"
)

# --- Frontend ---
Set-Location $Frontend
if (-not (Test-Path "node_modules")) {
    Write-Host "> Installing frontend dependencies..."
    npm install --no-audit --no-fund
}
if (-not (Test-Path ".env.local")) {
    Copy-Item ".env.local.example" ".env.local"
}

Start-Process powershell -ArgumentList @(
    "-NoExit", "-Command", "Set-Location '$Frontend'; npm run dev"
)

Write-Host ""
Write-Host "tanAI is running:"
Write-Host "  UI:  http://localhost:3000"
Write-Host "  API: http://$BackendHost`:$BackendPort/docs"
