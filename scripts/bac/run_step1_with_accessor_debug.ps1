# Run Step 1 with ISCE_DEBUG_ACCESSOR=1 to see getStream start/end (locate hang after "API open (R) done").
# Usage: .\scripts\run_step1_with_accessor_debug.ps1

$ErrorActionPreference = "Stop"
$root = Split-Path -Parent $PSScriptRoot
$python = "D:\env\miniconda3\envs\isce2-build\python.exe"

$env:ISCE_DEBUG_ACCESSOR = "1"
Write-Host "ISCE_DEBUG_ACCESSOR=1 (getStream start/end will be printed). Running Step 1...`n"
& $python (Join-Path $root "scripts\run_topo_checks.py") --run-step1
