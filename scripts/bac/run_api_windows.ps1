# Start FastAPI (uvicorn) on Windows using project .venv.
# Requires: Redis at localhost:6379 (e.g. docker run -p 6379:6379 redis:7-alpine).
# Run from project root; use a separate terminal for run_worker_windows.ps1.

$ProjectRoot = if ($env:INSAR_PROJECT_ROOT) { $env:INSAR_PROJECT_ROOT } else { (Resolve-Path (Join-Path $PSScriptRoot "..")).Path }
$VenvPython = Join-Path $ProjectRoot ".venv\Scripts\python.exe"
if (-not (Test-Path $VenvPython)) {
    Write-Error "Not found: $VenvPython. Create .venv and install backend requirements."
    exit 1
}

$env:PYTHONPATH = $ProjectRoot
$env:REDIS_URL = "redis://localhost:6379/0"
$env:INSAR_PROJECT_ROOT = $ProjectRoot
# Optional: INSAR_DATA_ROOT defaults to ./data when not set
if (-not $env:INSAR_DATA_ROOT) { $env:INSAR_DATA_ROOT = Join-Path $ProjectRoot "data" }

Write-Host "Starting API at http://127.0.0.1:8000 (PYTHONPATH=$env:PYTHONPATH)"
& $VenvPython -m uvicorn backend.app.main:app --host 127.0.0.1 --port 8000
exit $LASTEXITCODE
