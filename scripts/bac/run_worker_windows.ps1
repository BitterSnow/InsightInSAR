# Start Celery worker on Windows using isce2-build Python (ISCE2 DLLs must match this env).
# Requires: Redis at localhost:6379; isce2-build has celery, redis, pydantic (see docs/windows-phase4.md).
# Run from project root; start API first with run_api_windows.ps1 in another terminal.

$ProjectRoot = if ($env:INSAR_PROJECT_ROOT) { $env:INSAR_PROJECT_ROOT } else { (Resolve-Path (Join-Path $PSScriptRoot "..")).Path }
$UCRT64   = Join-Path $ProjectRoot "tools\msys64\ucrt64\bin"
$Packages = Join-Path $ProjectRoot "lib\isce2-main\install\packages"
$CondaEnv = "D:\env\miniconda3\envs\isce2-build"
if (-not (Test-Path "$CondaEnv\python.exe")) {
    $CondaEnv = "C:\ProgramData\Anaconda3\envs\isce2-build"
}
if (-not (Test-Path "$CondaEnv\python.exe")) {
    Write-Error "isce2-build not found. Create env (e.g. tools\create-envs-miniconda3.bat) and install: pip install celery[redis] redis pydantic"
    exit 1
}
if (-not (Test-Path $Packages)) {
    Write-Error "ISCE2 packages not found: $Packages. Complete Phase 2 build first."
    exit 1
}

$env:Path = "$UCRT64;$CondaEnv\Library\bin;$CondaEnv\bin;" + $env:Path
$env:PYTHONPATH = "$ProjectRoot;$Packages"
$env:REDIS_URL = "redis://localhost:6379/0"
$env:CELERY_RESULT_BACKEND = "redis://localhost:6379/0"
$env:INSAR_PROJECT_ROOT = $ProjectRoot
$env:PYTHONIOENCODING = "utf-8"

Write-Host "Starting Celery worker (Python: $CondaEnv\python.exe)"
& "$CondaEnv\python.exe" -m celery -A backend.app.celery_app worker --loglevel=info
exit $LASTEXITCODE
