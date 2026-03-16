# Run Step 1 and diagnose inside Docker container (Linux) for comparison with Windows.
# Container name: insar-system. Project is assumed mounted at /app/project (geom under /app/project or /app/project/processing).
# Usage: .\scripts\run_step1_and_diagnose_in_docker.ps1
#        .\scripts\run_step1_and_diagnose_in_docker.ps1 -ProjectInContainer /app/project -ProcessingSubDir processing

param(
    [string]$ContainerName = "insar-system",
    [string]$ProjectInContainer = "/app/project",
    [string]$ProcessingSubDir = "processing"
)

$ErrorActionPreference = "Stop"
$root = Split-Path -Parent $PSScriptRoot
$workInContainer = if ($ProcessingSubDir) { "$ProjectInContainer/$ProcessingSubDir" } else { $ProjectInContainer }
$geomInContainer = "$workInContainer/geom_reference/IW1"
$outFile = Join-Path $root "diagnose_result_docker.txt"

Write-Host "=== Start container $ContainerName (if stopped) ==="
docker start $ContainerName 2>$null
Start-Sleep -Seconds 2

Write-Host "`n=== Run Step 1 inside container (Linux) ==="
docker exec $ContainerName bash -c "cd '$ProjectInContainer' && export WORK_DIR='$workInContainer' && python3 scripts/run_topo_checks.py --run-step1"
if ($LASTEXITCODE -ne 0) {
    Write-Warning "Step 1 in Docker failed (exit $LASTEXITCODE). Check project path and ISCE2 in container."
    exit $LASTEXITCODE
}

Write-Host "`n=== Run diagnose inside container, save to $outFile ==="
$diagScript = @"
cd '$ProjectInContainer'
python3 scripts/diagnose_geom_troubleshoot.py '$geomInContainer' 2>&1
echo '---'
python3 scripts/diagnose_topo_byteorder.py --hgt '$geomInContainer/hgt_01.rdr' 2>&1
"@
docker exec $ContainerName bash -c $diagScript | Out-File -FilePath $outFile -Encoding utf8
Write-Host "Diagnose output saved to: $outFile"
Write-Host "`nCompare with Windows: run on host: python scripts/diagnose_geom_troubleshoot.py <geom_iw1> and compare LSB/first32bytes with content of $outFile"
