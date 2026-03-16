# Step 1: Force single-process topo, run Step 1, then run diagnose.
# Usage: .\scripts\run_step1_single_process_then_diagnose.ps1
# Optional: .\scripts\run_step1_single_process_then_diagnose.ps1 -WorkDir "D:\processing\tianfu\processing"

param(
    [string]$WorkDir = "D:\processing\tianfu\processing"
)

$ErrorActionPreference = "Stop"
$root = Split-Path -Parent $PSScriptRoot
$python = "D:\env\miniconda3\envs\isce2-build\python.exe"
$geomDir = Join-Path $WorkDir "geom_reference\IW1"
$hgtRdr = Join-Path $geomDir "hgt_01.rdr"
$configDir = Join-Path $WorkDir "configs"

Write-Host "=== 1. Force numProcess=1 in config_run_01_* ==="
if (-not (Test-Path $configDir)) {
    Write-Host "Config dir not found: $configDir"
    exit 1
}
$patched = 0
Get-ChildItem -Path $configDir -Filter "config_run_01*" -File | ForEach-Object {
    $content = Get-Content $_.FullName -Raw -Encoding UTF8
    if ($content -match 'numProcess\s*:\s*\d+') {
        $newContent = $content -replace 'numProcess\s*:\s*\d+', 'numProcess : 1'
        if ($newContent -ne $content) {
            Set-Content -Path $_.FullName -Value $newContent -Encoding UTF8 -NoNewline:$false
            Write-Host "  Patched: $($_.Name)"
            $patched++
        }
    }
}
if ($patched -eq 0) {
    Write-Host "  No config_run_01* with numProcess found (or already 1)."
}

Write-Host "`n=== 2. Run Step 1 (single process) ==="
& $python (Join-Path $root "scripts\run_topo_checks.py") --run-step1
if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }

Write-Host "`n=== 3. Diagnose geom_reference (troubleshoot + byteorder) ==="
& $python (Join-Path $root "scripts\diagnose_geom_troubleshoot.py") $geomDir
& $python (Join-Path $root "scripts\diagnose_topo_byteorder.py") --hgt $hgtRdr
& $python (Join-Path $root "scripts\diagnose_geom_one_line.py") $geomDir

Write-Host "`nDone. If LSB is still abnormal, check write-chain debug (Fortran/C++ logs) and/or Docker comparison."
