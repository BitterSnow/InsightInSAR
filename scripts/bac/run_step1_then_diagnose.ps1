# Run Step 1 (topo) to completion, then run geom_reference diagnostics.
# Usage: .\scripts\run_step1_then_diagnose.ps1
# No timeout - run in a terminal and wait for Step 1 to finish (may take 30+ min).

$ErrorActionPreference = "Stop"
$root = Split-Path -Parent $PSScriptRoot
$python = "D:\env\miniconda3\envs\isce2-build\python.exe"
$geomDir = "D:\processing\tianfu\processing\geom_reference\IW1"
$hgtRdr = Join-Path $geomDir "hgt_01.rdr"

Write-Host "=== Step 1 (SentinelWrapper topo) - no timeout, wait for completion ===`n"
& $python (Join-Path $root "scripts\run_topo_checks.py") --run-step1
if ($LASTEXITCODE -ne 0) {
    Write-Error "Step 1 exit code: $LASTEXITCODE"
}

Write-Host "`n=== Diagnose hgt_01.rdr byte order and value range ===`n"
& $python (Join-Path $root "scripts\diagnose_topo_byteorder.py") --hgt $hgtRdr

Write-Host "`n=== Diagnose geom_reference IW1 first line hgt/lat/lon ===`n"
& $python (Join-Path $root "scripts\diagnose_geom_one_line.py") $geomDir

Write-Host "`nDone. If LSB is in reasonable height range and hgt/lat/lon line 0 show [OK], the fix is active."
